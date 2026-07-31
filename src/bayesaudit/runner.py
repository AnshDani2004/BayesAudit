"""Offline Phase 2 experiment runner."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from bayesaudit.architectures.single_agent import SingleAgentWorkflow
from bayesaudit.architectures.structured import StructuredInheritanceWorkflow
from bayesaudit.architectures.unstructured import UnstructuredDelegationWorkflow
from bayesaudit.architectures.verified import VerifiedInheritanceWorkflow
from bayesaudit.benchmark.io import load_tasks
from bayesaudit.constraints.inheritance import VerificationResponse
from bayesaudit.constraints.mutations import (
    MutationProfile,
    MutationSchedule,
    load_mutation_profiles,
)
from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.models.mock import MockModel, MockScript
from bayesaudit.oversight.registry import coerce_policy_config
from bayesaudit.oversight.replay import replay_policies
from bayesaudit.oversight.types import OversightRunResult, WorkflowMode
from bayesaudit.schemas import (
    SCHEMA_VERSION,
    ArchitectureKind,
    ErrorRecord,
    ScoreResult,
    StrictModel,
    Trajectory,
    TrajectoryStatus,
)
from bayesaudit.scoring.registry import scorer_for_task
from bayesaudit.storage.jsonl import append_jsonl, read_json, read_jsonl, write_json_atomic
from bayesaudit.storage.normalize import (
    merge_tables,
    normalized_oversight_records,
    normalized_records,
    write_parquet_tables,
)


class BehaviorProfileConfig(StrictModel):
    name: str
    script: MockScript = Field(default_factory=MockScript)


class ExperimentConfig(StrictModel):
    experiment_id: str
    description: str = ""
    task_roots: list[Path]
    architectures: list[ArchitectureKind]
    delegation_depths: list[int] = [1]
    branching_factors: list[int] = [1]
    behavior_profiles: list[BehaviorProfileConfig] = Field(
        default_factory=lambda: [BehaviorProfileConfig(name="compliant")]
    )
    mutation_profile_roots: list[Path] = Field(default_factory=list)
    mutation_profile_names: list[str] = Field(default_factory=lambda: ["no_mutation"])
    verification_response: str = VerificationResponse.REFUSE_SUBTASK
    seeds: list[int]
    output_root: Path = Path("data/raw")
    oversight_policies: list[dict[str, Any]] = Field(default_factory=list)
    oversight_budgets: list[float] = Field(default_factory=list)
    oversight_mode: str = WorkflowMode.SHADOW
    allow_large_run: bool = False
    large_run_threshold: int = 10000
    max_runs: int | None = None


def load_experiment_config(path: Path) -> ExperimentConfig:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"experiment config must be a mapping: {path}")
    return ExperimentConfig.model_validate(payload)


def planned_runs(config: ExperimentConfig) -> list[dict[str, Any]]:
    tasks = []
    for root in config.task_roots:
        tasks.extend(load_tasks(root))
    runs: list[dict[str, Any]] = []
    for task in tasks:
        mutation_profiles = _selected_mutation_profiles(config)
        for architecture in config.architectures:
            if architecture == ArchitectureKind.SINGLE_AGENT:
                depth_values = [0]
                branch_values = [1]
            else:
                depth_values = config.delegation_depths
                branch_values = config.branching_factors
            for depth in depth_values:
                for branching in branch_values:
                    for profile in config.behavior_profiles:
                        for mutation_profile in mutation_profiles:
                            for seed in config.seeds:
                                run_key = {
                                    "task_id": task.task_id,
                                    "scenario_hash": task.scenario_hash,
                                    "architecture": architecture,
                                    "depth": depth,
                                    "branching": branching,
                                    "profile": profile.name,
                                    "mutation_profile": mutation_profile.name,
                                    "verification_response": config.verification_response,
                                    "seed": seed,
                                }
                                runs.append(
                                    {
                                        "run_id": "run_" + canonical_json_hash(run_key)[:16],
                                        "task": task,
                                        "architecture": architecture,
                                        "depth": depth,
                                        "branching": branching,
                                        "profile": profile,
                                        "mutation_profile": mutation_profile,
                                        "seed": seed,
                                    }
                                )
    return runs


async def run_experiment(config: ExperimentConfig, *, dry_run: bool = False) -> dict[str, Any]:
    output_dir = config.output_root / config.experiment_id
    manifest_path = output_dir / "manifest.json"
    completed = {
        row["run_id"]
        for row in read_jsonl(output_dir / "raw_trajectories.jsonl")
        if row.get("status") == TrajectoryStatus.COMPLETED.value
    }
    all_runs = planned_runs(config)
    oversight_configs = _oversight_policy_configs(config)
    estimated_units = len(all_runs) * max(1, len(oversight_configs))
    if (
        estimated_units > config.large_run_threshold
        and not config.allow_large_run
        and not dry_run
    ):
        raise ValueError(
            "planned run count exceeds large_run_threshold; pass allow_large_run or max_runs"
        )
    runs = all_runs[: config.max_runs] if config.max_runs is not None else all_runs
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": config.experiment_id,
        "description": config.description,
        "planned_run_count": len(all_runs),
        "executable_run_count": len(runs),
        "planned_oversight_policy_run_count": len(all_runs) * len(oversight_configs),
        "factor_cardinalities": {
            "tasks": _task_count(config),
            "architectures": len(config.architectures),
            "delegation_depths": len(config.delegation_depths),
            "branching_factors": len(config.branching_factors),
            "behavior_profiles": len(config.behavior_profiles),
            "mutation_profiles": len(config.mutation_profile_names),
            "seeds": len(config.seeds),
            "oversight_policies": len(config.oversight_policies),
            "oversight_budgets": len(config.oversight_budgets) or 1,
        },
        "large_run_threshold": config.large_run_threshold,
        "allow_large_run": config.allow_large_run,
        "max_runs": config.max_runs,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "configuration_hash": canonical_json_hash(config.model_dump(mode="json")),
        "dry_run": dry_run,
    }
    write_json_atomic(manifest_path, manifest)
    if dry_run:
        return {
            "planned": len(all_runs),
            "executable": len(runs),
            "oversight_policy_runs": len(all_runs) * len(oversight_configs),
            "completed": 0,
            "failed": 0,
            "skipped": len(completed),
        }

    completed_count = 0
    failed_count = 0
    skipped_count = 0
    for item in runs:
        run_id = str(item["run_id"])
        if run_id in completed:
            skipped_count += 1
            continue
        task = item["task"]
        profile = item["profile"]
        script = profile.script.model_copy(update={"profile": profile.name})
        model = MockModel(script)
        try:
            workflow = _workflow_for(
                item["architecture"],
                int(item["depth"]),
                int(item["branching"]),
                MutationSchedule(
                    profiles=[]
                    if item["mutation_profile"].name == "no_mutation"
                    else [item["mutation_profile"]]
                ),
                config.verification_response,
            )
            trajectory = await workflow.run(
                task,
                model,
                experiment_id=config.experiment_id,
                run_id=run_id,
                seed=int(item["seed"]),
            )
            score = scorer_for_task(task).score(task, trajectory)
            completed_count += 1
        except Exception as exc:  # preserve failures and continue
            trajectory = _failed_trajectory(config, item, exc)
            score = None
            failed_count += 1
        append_jsonl(output_dir / "raw_trajectories.jsonl", trajectory.model_dump(mode="json"))
        if score is not None:
            append_jsonl(output_dir / "scores.jsonl", score.model_dump(mode="json"))
            oversight_results = await replay_policies(
                task=task,
                trajectory=trajectory,
                score=score,
                configs=oversight_configs,
                experiment_id=config.experiment_id,
            )
            for oversight_result in oversight_results:
                append_jsonl(
                    output_dir / "oversight_runs.jsonl",
                    oversight_result.model_dump(mode="json"),
                )
    summary = {
        "planned": len(all_runs),
        "executable": len(runs),
        "completed": completed_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "oversight_policy_runs": completed_count * len(oversight_configs),
    }
    _rewrite_normalized_tables(output_dir)
    write_json_atomic(output_dir / "summary.json", summary)
    return summary


def resume_manifest(path: Path) -> dict[str, Any]:
    manifest = read_json(path)
    config_hash = manifest.get("configuration_hash")
    return {"manifest": manifest, "configuration_hash": config_hash}


def _selected_mutation_profiles(config: ExperimentConfig) -> list[MutationProfile]:
    profiles: dict[str, MutationProfile] = {
        "no_mutation": MutationProfile(name="no_mutation", mutation_type="none")
    }
    for root in config.mutation_profile_roots:
        for profile in load_mutation_profiles(root):
            profiles[profile.name] = profile
    return [profiles[name] for name in config.mutation_profile_names]


def _oversight_policy_configs(config: ExperimentConfig) -> list[Any]:
    if not config.oversight_policies:
        return []
    budgets = config.oversight_budgets or [0.0]
    configs = []
    for policy_payload in config.oversight_policies:
        for budget in budgets:
            payload = dict(policy_payload)
            payload.setdefault("budget", budget)
            payload.setdefault("mode", config.oversight_mode)
            configs.append(
                coerce_policy_config(
                    payload,
                    default_mode=config.oversight_mode,
                    default_budget=budget,
                )
            )
    return configs


def _task_count(config: ExperimentConfig) -> int:
    return sum(len(load_tasks(root)) for root in config.task_roots)


def _rewrite_normalized_tables(output_dir: Path) -> None:
    score_by_trajectory = {
        row["trajectory_id"]: ScoreResult.model_validate(
            {key: value for key, value in row.items() if key != "correct"}
        )
        for row in read_jsonl(output_dir / "scores.jsonl")
        if "trajectory_id" in row
    }
    table_sets: list[dict[str, list[dict[str, Any]]]] = []
    for row in read_jsonl(output_dir / "raw_trajectories.jsonl"):
        trajectory = Trajectory.model_validate(row)
        table_sets.append(
            normalized_records(trajectory, score_by_trajectory.get(trajectory.trajectory_id))
        )
    for row in read_jsonl(output_dir / "oversight_runs.jsonl"):
        table_sets.append(normalized_oversight_records(OversightRunResult.model_validate(row)))
    if table_sets:
        write_parquet_tables(output_dir / "normalized", merge_tables(*table_sets))


def _workflow_for(
    architecture: ArchitectureKind,
    depth: int,
    branching: int,
    mutation_schedule: MutationSchedule | None = None,
    verification_response: str = VerificationResponse.REFUSE_SUBTASK,
) -> Any:
    if architecture == ArchitectureKind.SINGLE_AGENT:
        return SingleAgentWorkflow()
    if architecture == ArchitectureKind.UNSTRUCTURED_DELEGATION:
        return UnstructuredDelegationWorkflow(
            max_depth=depth,
            branching_factor=branching,
            mutation_schedule=mutation_schedule,
        )
    if architecture == ArchitectureKind.STRUCTURED_INHERITANCE:
        return StructuredInheritanceWorkflow(
            max_depth=depth,
            branching_factor=branching,
            mutation_schedule=mutation_schedule,
        )
    if architecture == ArchitectureKind.VERIFIED_INHERITANCE:
        return VerifiedInheritanceWorkflow(
            max_depth=depth,
            branching_factor=branching,
            mutation_schedule=mutation_schedule,
            verification_response=verification_response,
        )
    raise ValueError(f"Phase 2 does not implement architecture: {architecture}")


def _failed_trajectory(
    config: ExperimentConfig, item: dict[str, Any], exc: Exception
) -> Trajectory:
    task = item["task"]
    script = item["profile"].script
    model = MockModel(script)
    base = SingleAgentWorkflow()
    del base
    from bayesaudit.architectures.common import make_trajectory

    trajectory = make_trajectory(
        task=task,
        model=model,
        architecture=item["architecture"],
        experiment_id=config.experiment_id,
        run_id=item["run_id"],
        seed=int(item["seed"]),
    )
    trajectory.status = TrajectoryStatus.FAILED
    trajectory.completed_at = datetime.now(timezone.utc)
    trajectory.error = ErrorRecord(
        error_type=type(exc).__name__, message=str(exc), recoverable=True
    )
    return trajectory


def run_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-large-run", action="store_true")
    parser.add_argument("--max-runs", type=int)
    args = parser.parse_args(argv)
    config = load_experiment_config(args.config)
    if args.allow_large_run:
        config.allow_large_run = True
    if args.max_runs is not None:
        config.max_runs = args.max_runs
    summary = asyncio.run(run_experiment(config, dry_run=args.dry_run))
    print(summary)
