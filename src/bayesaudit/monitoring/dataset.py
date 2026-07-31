"""Build leakage-resistant monitoring datasets from completed artifacts."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import Field

from bayesaudit.benchmark.io import load_tasks
from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.monitoring.features import (
    FEATURE_SCHEMA,
    extract_features,
    render_observation_text,
    validate_feature_payload,
)
from bayesaudit.monitoring.types import (
    LabelValue,
    MonitorDatasetManifest,
    MonitorExample,
)
from bayesaudit.oversight.budget import BudgetLedger
from bayesaudit.oversight.checkpoints import checkpoints_for_trajectory
from bayesaudit.oversight.observations import build_observation
from bayesaudit.oversight.types import WorkflowMode
from bayesaudit.runner import load_experiment_config, run_experiment
from bayesaudit.schemas import BenchmarkTask, ScoreResult, StrictModel, Trajectory, ViolationEvent
from bayesaudit.storage.jsonl import read_jsonl, write_json_atomic
from bayesaudit.storage.normalize import write_parquet_tables


class MonitorDatasetConfig(StrictModel):
    dataset_id: str
    dataset_version: str = "v1"
    source_experiments: list[str] = Field(default_factory=list)
    source_experiment_configs: list[Path] = Field(default_factory=list)
    task_root: Path = Path("scenarios")
    data_root: Path = Path("data/raw")
    output_root: Path = Path("data/processed/monitoring")
    label_horizon: int = 1
    max_runs: int | None = None
    auto_build_sources: bool = False
    allow_large_run: bool = False
    large_run_threshold: int = 5000
    split_strategy: str = "in_distribution"


def load_monitor_dataset_config(path: Path) -> MonitorDatasetConfig:
    import yaml

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"monitor dataset config must be a mapping: {path}")
    return MonitorDatasetConfig.model_validate(payload)


async def ensure_source_experiments(config: MonitorDatasetConfig, *, dry_run: bool = False) -> None:
    if not config.auto_build_sources:
        return
    for source_config_path in config.source_experiment_configs:
        experiment_config = load_experiment_config(source_config_path)
        if config.max_runs is not None:
            experiment_config.max_runs = config.max_runs
        experiment_config.allow_large_run = config.allow_large_run
        await run_experiment(experiment_config, dry_run=dry_run)


def build_monitor_dataset(
    config: MonitorDatasetConfig,
) -> tuple[list[MonitorExample], MonitorDatasetManifest]:
    tasks = {task.task_id: task for task in load_tasks(config.task_root)}
    examples_by_id: dict[str, MonitorExample] = {}
    trajectory_count = 0
    source_versions = {"bayesaudit.v2", "bayesaudit.oversight.v1"}
    for experiment in config.source_experiments:
        root = config.data_root / experiment
        scores = _scores_by_trajectory(root)
        trajectory_rows = read_jsonl(root / "raw_trajectories.jsonl")
        if config.max_runs is not None:
            trajectory_rows = trajectory_rows[: config.max_runs]
        for row in trajectory_rows:
            trajectory = Trajectory.model_validate(row)
            task = tasks[trajectory.task_id]
            score = scores.get(trajectory.trajectory_id)
            trajectory_count += 1
            for example in _examples_for_trajectory(
                task=task,
                trajectory=trajectory,
                score=score,
                label_horizon=config.label_horizon,
                source_experiment=experiment,
            ):
                examples_by_id[example.example_id] = example
    examples = sorted(examples_by_id.values(), key=lambda item: item.example_id)
    manifest = _manifest(config, examples, trajectory_count, source_versions)
    persist_monitor_dataset(config.output_root / config.dataset_id, examples, manifest)
    return examples, manifest


def persist_monitor_dataset(
    output_dir: Path, examples: list[MonitorExample], manifest: MonitorDatasetManifest
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [example.model_dump(mode="json") for example in examples]
    pd.DataFrame(records).to_parquet(output_dir / "monitor_examples.parquet", index=False)
    write_json_atomic(output_dir / "manifest.json", manifest.model_dump(mode="json"))
    write_parquet_tables(
        output_dir / "normalized",
        {
            "monitor_examples": records,
            "monitor_labels": [_label_row(example) for example in examples],
            "monitor_features": [_feature_row(example) for example in examples],
        },
    )


def load_monitor_examples(dataset_dir: Path) -> list[MonitorExample]:
    path = dataset_dir / "monitor_examples.parquet"
    if not path.exists():
        return []
    rows = pd.read_parquet(path).to_dict(orient="records")
    return [
        MonitorExample.model_validate(
            _unflatten_payload({str(key): value for key, value in row.items()})
        )
        for row in rows
    ]


def validate_monitor_dataset(dataset_dir: Path) -> dict[str, Any]:
    examples = load_monitor_examples(dataset_dir)
    errors = []
    seen: set[str] = set()
    for example in examples:
        if example.example_id in seen:
            errors.append(f"duplicate example_id: {example.example_id}")
        seen.add(example.example_id)
        try:
            validate_feature_payload(example.observable_feature_payload)
        except ValueError as exc:
            errors.append(f"{example.example_id}: {exc}")
    return {"example_count": len(examples), "valid": not errors, "errors": errors}


def summarize_monitor_dataset(dataset_dir: Path) -> dict[str, Any]:
    examples = load_monitor_examples(dataset_dir)
    domains = Counter(str(example.domain) for example in examples)
    labels = Counter(example.current_violation_label for example in examples)
    return {
        "example_count": len(examples),
        "trajectory_count": len({example.trajectory_id for example in examples}),
        "task_count": len({example.task_id for example in examples}),
        "domains": dict(sorted(domains.items())),
        "current_violation_labels": dict(sorted(labels.items())),
    }


def _examples_for_trajectory(
    *,
    task: BenchmarkTask,
    trajectory: Trajectory,
    score: ScoreResult | None,
    label_horizon: int,
    source_experiment: str,
) -> list[MonitorExample]:
    ledger = BudgetLedger(policy_run_id=f"dataset_{trajectory.run_id}", initial_budget=0.0)
    examples: list[MonitorExample] = []
    for checkpoint in checkpoints_for_trajectory(trajectory):
        observation = build_observation(
            task=task,
            trajectory=trajectory,
            checkpoint=checkpoint,
            budget=ledger,
            mode=WorkflowMode.SHADOW,
        )
        features = extract_features(observation)
        validate_feature_payload(features)
        text = render_observation_text(observation)
        labels = _labels_for_checkpoint(
            checkpoint_step_id=checkpoint.step_id,
            sequence_index=checkpoint.sequence_index,
            score=score,
            trajectory=trajectory,
            horizon=label_horizon,
            intervention_possible=checkpoint.intervention_still_possible,
        )
        example_id = "mon_" + canonical_json_hash(
            {
                "observation_id": observation.observation_id,
                "horizon": label_horizon,
                "feature_schema": sorted(features),
            }
        )[:20]
        examples.append(
            MonitorExample(
                example_id=example_id,
                observation_id=observation.observation_id,
                trajectory_id=trajectory.trajectory_id,
                run_id=trajectory.run_id,
                experiment_id=source_experiment,
                task_id=task.task_id,
                task_version=task.task_version,
                template_family=task.template_family,
                domain=task.domain,
                architecture=trajectory.architecture,
                model_family=trajectory.model_configuration.model_id.split("-")[0],
                checkpoint_type=checkpoint.checkpoint_type,
                sequence_index=checkpoint.sequence_index,
                depth=observation.depth,
                branch_id=observation.branch_id,
                observable_feature_payload=features,
                observable_text_payload=text,
                current_violation_label=labels["current"],
                imminent_violation_label=labels["imminent"],
                preventable_imminent_violation_label=labels["preventable"],
                severity_target=labels["severity"],
                intervention_usefulness_label=labels["intervention_useful"],
                final_output_violation_label=labels["final_output"],
                internal_only_violation_label=labels["internal_only"],
                label_horizon=label_horizon,
                label_source="objective_scorer_posthoc",
                label_confidence=1.0 if score is not None else 0.0,
                unknown_label_reasons=[] if score is not None else ["score_missing"],
                split_group_ids=_split_groups(task, trajectory),
                source_artifact_hashes={
                    "trajectory": canonical_json_hash(trajectory.model_dump(mode="json")),
                    "score": canonical_json_hash(score.model_dump(mode="json"))
                    if score is not None
                    else "",
                },
            )
        )
    return examples


def _labels_for_checkpoint(
    *,
    checkpoint_step_id: str,
    sequence_index: int,
    score: ScoreResult | None,
    trajectory: Trajectory,
    horizon: int,
    intervention_possible: bool,
) -> dict[str, Any]:
    if score is None:
        return {
            "current": LabelValue.UNKNOWN,
            "imminent": LabelValue.UNKNOWN,
            "preventable": LabelValue.UNKNOWN,
            "severity": None,
            "intervention_useful": LabelValue.UNKNOWN,
            "final_output": LabelValue.UNKNOWN,
            "internal_only": LabelValue.UNKNOWN,
        }
    step_index = {step.step_id: step.sequence_index for step in trajectory.steps}
    current = [
        violation
        for violation in score.violations
        if violation.first_step_id == checkpoint_step_id
    ]
    horizon_violations = [
        violation
        for violation in score.violations
        if sequence_index
        <= step_index.get(violation.first_step_id, 10**9)
        <= sequence_index + horizon
    ]
    final = [violation for violation in score.violations if not violation.internal_only]
    internal = [violation for violation in score.violations if violation.internal_only]
    return {
        "current": _binary(current),
        "imminent": _binary(horizon_violations),
        "preventable": _binary(horizon_violations) if intervention_possible else LabelValue.UNKNOWN,
        "severity": float(score.severity_weighted_harm) if horizon_violations else 0.0,
        "intervention_useful": _binary(horizon_violations)
        if intervention_possible
        else LabelValue.UNKNOWN,
        "final_output": _binary(final),
        "internal_only": _binary(internal),
    }


def _binary(violations: list[ViolationEvent]) -> str:
    return LabelValue.POSITIVE if violations else LabelValue.NEGATIVE


def _split_groups(task: BenchmarkTask, trajectory: Trajectory) -> dict[str, str]:
    metadata = trajectory.metadata.get("inheritance", {})
    mutation_family = "none"
    if isinstance(metadata, dict) and metadata.get("mutation_events"):
        events = metadata.get("mutation_events", [])
        if isinstance(events, list) and events and isinstance(events[0], dict):
            mutation_family = str(events[0].get("mutation_type", "unknown")).split("_")[0]
    return {
        "base_task_id": task.task_id,
        "template_family": task.template_family,
        "scenario_family": task.template_family.split("_")[0],
        "mutation_profile_family": mutation_family,
        "delegation_graph": (
            f"{trajectory.architecture}:{max((s.depth for s in trajectory.steps), default=0)}"
        ),
        "architecture": str(trajectory.architecture),
        "domain": str(task.domain),
        "model_family": trajectory.model_configuration.model_id.split("-")[0],
        "seed_family": str(trajectory.seed),
    }


def _manifest(
    config: MonitorDatasetConfig,
    examples: list[MonitorExample],
    trajectory_count: int,
    source_versions: set[str],
) -> MonitorDatasetManifest:
    records = [example.model_dump(mode="json") for example in examples]
    label_counts = Counter(example.current_violation_label for example in examples)
    unknown_counts = {
        "current_violation": sum(
            example.current_violation_label == LabelValue.UNKNOWN for example in examples
        ),
        "imminent_violation": sum(
            example.imminent_violation_label == LabelValue.UNKNOWN for example in examples
        ),
    }
    return MonitorDatasetManifest(
        dataset_id=config.dataset_id,
        dataset_version=config.dataset_version,
        source_experiments=config.source_experiments,
        source_schema_versions=sorted(source_versions),
        observation_count=len(examples),
        trajectory_count=trajectory_count,
        task_count=len({example.task_id for example in examples}),
        group_counts={
            "base_task_id": len({example.split_group_ids["base_task_id"] for example in examples}),
            "domain": len({example.split_group_ids["domain"] for example in examples}),
            "architecture": len({example.split_group_ids["architecture"] for example in examples}),
        },
        label_prevalence={
            key: count / len(examples) if examples else 0.0
            for key, count in label_counts.items()
        },
        unknown_label_counts=unknown_counts,
        feature_schema=FEATURE_SCHEMA,
        text_rendering_version="redacted_observation_text_v1",
        split_strategy=config.split_strategy,
        build_configuration=config.model_dump(mode="json"),
        configuration_hash=canonical_json_hash(config.model_dump(mode="json")),
        data_hash=canonical_json_hash(records),
    )


def _scores_by_trajectory(root: Path) -> dict[str, ScoreResult]:
    scores: dict[str, ScoreResult] = {}
    for row in read_jsonl(root / "scores.jsonl"):
        if "trajectory_id" in row:
            scores[str(row["trajectory_id"])] = ScoreResult.model_validate(
                {key: value for key, value in row.items() if key != "correct"}
            )
    return scores


def _label_row(example: MonitorExample) -> dict[str, Any]:
    return {
        "example_id": example.example_id,
        "current_violation_label": example.current_violation_label,
        "imminent_violation_label": example.imminent_violation_label,
        "preventable_imminent_violation_label": example.preventable_imminent_violation_label,
        "severity_target": example.severity_target,
        "intervention_usefulness_label": example.intervention_usefulness_label,
    }


def _feature_row(example: MonitorExample) -> dict[str, Any]:
    return {"example_id": example.example_id, **example.observable_feature_payload}


def _unflatten_payload(row: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "observable_feature_payload",
        "unknown_label_reasons",
        "split_group_ids",
        "source_artifact_hashes",
    ):
        value = row.get(key)
        if isinstance(value, str):
            import json

            row[key] = json.loads(value)
    return row
