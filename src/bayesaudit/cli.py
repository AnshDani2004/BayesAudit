"""BayesAudit command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from bayesaudit.benchmark.io import load_tasks
from bayesaudit.constraints.inheritance import build_registry, create_envelope, verify_envelope
from bayesaudit.oversight.registry import load_policy_configs, policy_for_config
from bayesaudit.oversight.replay import replay_policies
from bayesaudit.oversight.types import WorkflowMode
from bayesaudit.runner import (
    _rewrite_normalized_tables,
    load_experiment_config,
    resume_manifest,
    run_experiment,
)
from bayesaudit.schemas import ScoreResult, Trajectory
from bayesaudit.storage.jsonl import append_jsonl, read_jsonl


def _inspect_payload(row: dict[str, object] | None) -> dict[str, object]:
    if row is None:
        return {"found": False}
    steps = row.get("steps", [])
    metadata = row.get("metadata", {})
    inheritance = metadata.get("inheritance", {}) if isinstance(metadata, dict) else {}
    return {
        "found": True,
        "run_id": row.get("run_id"),
        "status": row.get("status"),
        "delegation_tree": [
            {
                "step_id": step.get("step_id"),
                "parent_step_id": step.get("parent_step_id"),
                "depth": step.get("depth"),
                "branch_id": step.get("branch_id"),
                "kind": step.get("kind"),
                "envelope_id": _step_envelope_id(step),
            }
            for step in _dict_rows(steps)
        ],
        "mutations": inheritance.get("mutation_events", [])
        if isinstance(inheritance, dict)
        else [],
        "verifications": inheritance.get("verification_events", [])
        if isinstance(inheritance, dict)
        else [],
        "repairs": inheritance.get("repair_events", []) if isinstance(inheritance, dict) else [],
        "final_outcome": row.get("status"),
    }


def _step_envelope_id(step: dict[str, object]) -> object:
    metadata = step.get("metadata", {})
    if isinstance(metadata, dict):
        return metadata.get("envelope_id")
    return None


def _dict_rows(rows: object) -> list[dict[str, object]]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def main() -> None:
    parser = argparse.ArgumentParser(prog="bayesaudit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-scenarios")
    validate.add_argument("--root", type=Path, default=Path("scenarios"))

    run = subparsers.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--allow-large-run", action="store_true")
    run.add_argument("--max-runs", type=int)

    resume = subparsers.add_parser("resume")
    resume.add_argument("--manifest", type=Path, required=True)

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("--experiment", required=True)
    summarize.add_argument("--root", type=Path, default=Path("data/raw"))

    score = subparsers.add_parser("score")
    score.add_argument("--experiment", required=True)
    score.add_argument("--root", type=Path, default=Path("data/raw"))

    validate_envelopes = subparsers.add_parser("validate-envelopes")
    validate_envelopes.add_argument("--root", type=Path, default=Path("scenarios"))

    inheritance = subparsers.add_parser("summarize-inheritance")
    inheritance.add_argument("--experiment", required=True)
    inheritance.add_argument("--root", type=Path, default=Path("data/raw"))

    inspect = subparsers.add_parser("inspect-trajectory")
    inspect.add_argument("--run-id", required=True)
    inspect.add_argument("--experiment", default="phase3_smoke")
    inspect.add_argument("--root", type=Path, default=Path("data/raw"))

    compare = subparsers.add_parser("compare-architectures")
    compare.add_argument("--experiment", required=True)
    compare.add_argument("--root", type=Path, default=Path("data/raw"))

    validate_policies = subparsers.add_parser("validate-policies")
    validate_policies.add_argument("--root", type=Path, default=Path("configs/policies"))

    replay = subparsers.add_parser("replay-policies")
    replay.add_argument("--experiment", required=True)
    replay.add_argument("--root", type=Path, default=Path("data/raw"))
    replay.add_argument("--policies-root", type=Path, default=Path("configs/policies"))
    replay.add_argument("--task-root", type=Path, default=Path("scenarios"))
    replay.add_argument("--mode", default=WorkflowMode.SHADOW)
    replay.add_argument("--budget", type=float, default=3.0)

    summarize_oversight = subparsers.add_parser("summarize-oversight")
    summarize_oversight.add_argument("--experiment", required=True)
    summarize_oversight.add_argument("--root", type=Path, default=Path("data/raw"))

    compare_policies = subparsers.add_parser("compare-policies")
    compare_policies.add_argument("--experiment", required=True)
    compare_policies.add_argument("--root", type=Path, default=Path("data/raw"))

    inspect_policy = subparsers.add_parser("inspect-policy-run")
    inspect_policy.add_argument("--run-id", required=True)
    inspect_policy.add_argument("--experiment", required=True)
    inspect_policy.add_argument("--root", type=Path, default=Path("data/raw"))

    frontier = subparsers.add_parser("build-frontier")
    frontier.add_argument("--experiment", required=True)
    frontier.add_argument("--root", type=Path, default=Path("data/raw"))

    args = parser.parse_args()
    if args.command == "validate-scenarios":
        tasks = load_tasks(args.root)
        payload = {"task_count": len(tasks), "domains": sorted({task.domain for task in tasks})}
    elif args.command == "run":
        config = load_experiment_config(args.config)
        if args.allow_large_run:
            config.allow_large_run = True
        if args.max_runs is not None:
            config.max_runs = args.max_runs
        payload = asyncio.run(run_experiment(config, dry_run=args.dry_run))
    elif args.command == "resume":
        payload = resume_manifest(args.manifest)
    elif args.command == "summarize":
        rows = read_jsonl(args.root / args.experiment / "raw_trajectories.jsonl")
        payload = {
            "trajectory_count": len(rows),
            "completed": sum(1 for row in rows if row.get("status") == "completed"),
        }
    elif args.command == "score":
        rows = read_jsonl(args.root / args.experiment / "scores.jsonl")
        payload = {"score_count": len(rows)}
    elif args.command == "validate-envelopes":
        tasks = load_tasks(args.root)
        failures = []
        for task in tasks:
            registry = build_registry(task, creation_step="validation_step")
            envelope = create_envelope(
                registry,
                envelope_id=f"validation_{task.task_id}",
                sender_agent_id="validator",
                recipient_agent_id="validator",
                created_step_id="validation_step",
                branch_id="0",
                acknowledged=True,
            )
            outcome = verify_envelope(
                registry,
                envelope,
                step_id="validation_step",
                agent_id="validator",
                branch_id="0",
                response="refuse_subtask",
            )
            if not outcome.event.passed:
                failures.append({"task_id": task.task_id, "reasons": outcome.event.reasons})
        payload = {
            "task_count": len(tasks),
            "valid_envelopes": len(tasks) - len(failures),
            "failures": failures,
        }
    elif args.command == "summarize-inheritance":
        rows = read_jsonl(args.root / args.experiment / "raw_trajectories.jsonl")
        inheritance_rows = [
            row for row in rows if isinstance(row.get("metadata", {}).get("inheritance"), dict)
        ]
        mutation_count = sum(
            len(row["metadata"]["inheritance"].get("mutation_events", []))
            for row in inheritance_rows
        )
        verification_count = sum(
            len(row["metadata"]["inheritance"].get("verification_events", []))
            for row in inheritance_rows
        )
        payload = {
            "trajectory_count": len(rows),
            "inheritance_trajectory_count": len(inheritance_rows),
            "mutation_event_count": mutation_count,
            "verification_event_count": verification_count,
        }
    elif args.command == "inspect-trajectory":
        rows = read_jsonl(args.root / args.experiment / "raw_trajectories.jsonl")
        match = next((row for row in rows if row.get("run_id") == args.run_id), None)
        payload = _inspect_payload(match)
    elif args.command == "compare-architectures":
        rows = read_jsonl(args.root / args.experiment / "raw_trajectories.jsonl")
        grouped: dict[str, int] = {}
        for row in rows:
            grouped[str(row.get("architecture"))] = grouped.get(str(row.get("architecture")), 0) + 1
        payload = {"architectures": grouped, "synthetic_only": True}
    elif args.command == "validate-policies":
        configs = load_policy_configs(args.root)
        errors = []
        for policy_config in configs:
            try:
                policy_for_config(policy_config, evaluation=policy_config.evaluation_only)
            except Exception as exc:  # report all invalid configs together
                errors.append({"policy_name": policy_config.name, "error": str(exc)})
        payload = {
            "policy_count": len(configs),
            "valid_policy_count": len(configs) - len(errors),
            "errors": errors,
            "oracle_evaluation_only": all(
                config.evaluation_only for config in configs if config.policy_type == "oracle"
            ),
        }
    elif args.command == "replay-policies":
        payload = asyncio.run(
            _replay_policies_cli(
                args.root,
                args.experiment,
                args.policies_root,
                args.task_root,
                args.mode,
                args.budget,
            )
        )
    elif args.command == "summarize-oversight":
        rows = read_jsonl(args.root / args.experiment / "oversight_runs.jsonl")
        payload = {
            "policy_run_count": len(rows),
            "policy_names": sorted({str(row.get("policy_name")) for row in rows}),
            "audit_decision_count": sum(len(_dict_rows(row.get("decisions", []))) for row in rows),
            "audit_feedback_count": sum(len(_dict_rows(row.get("feedback", []))) for row in rows),
            "intervention_decision_count": sum(
                len(_dict_rows(row.get("intervention_decisions", []))) for row in rows
            ),
        }
    elif args.command == "compare-policies":
        payload = _compare_policies_payload(
            read_jsonl(args.root / args.experiment / "oversight_runs.jsonl")
        )
    elif args.command == "inspect-policy-run":
        rows = read_jsonl(args.root / args.experiment / "oversight_runs.jsonl")
        match = next(
            (
                row
                for row in rows
                if row.get("policy_run_id") == args.run_id or row.get("run_id") == args.run_id
            ),
            None,
        )
        payload = _inspect_policy_payload(match)
    elif args.command == "build-frontier":
        payload = {
            "frontier": _frontier_rows(
                read_jsonl(args.root / args.experiment / "oversight_runs.jsonl")
            )
        }
    else:
        raise AssertionError(args.command)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


async def _replay_policies_cli(
    root: Path,
    experiment: str,
    policies_root: Path,
    task_root: Path,
    mode: str,
    budget: float,
) -> dict[str, object]:
    output_dir = root / experiment
    tasks = {task.task_id: task for task in load_tasks(task_root)}
    scores = {
        row["trajectory_id"]: ScoreResult.model_validate(
            {key: value for key, value in row.items() if key != "correct"}
        )
        for row in read_jsonl(output_dir / "scores.jsonl")
        if "trajectory_id" in row
    }
    configs = load_policy_configs(policies_root, default_mode=mode, default_budget=budget)
    existing = {
        str(row.get("policy_run_id"))
        for row in read_jsonl(output_dir / "oversight_runs.jsonl")
        if row.get("policy_run_id")
    }
    written = 0
    skipped = 0
    for row in read_jsonl(output_dir / "raw_trajectories.jsonl"):
        trajectory = Trajectory.model_validate(row)
        task = tasks[trajectory.task_id]
        results = await replay_policies(
            task=task,
            trajectory=trajectory,
            score=scores.get(trajectory.trajectory_id),
            configs=configs,
            experiment_id=experiment,
        )
        for result in results:
            if result.policy_run_id in existing:
                skipped += 1
                continue
            append_jsonl(output_dir / "oversight_runs.jsonl", result.model_dump(mode="json"))
            existing.add(result.policy_run_id)
            written += 1
    _rewrite_normalized_tables(output_dir)
    return {
        "trajectory_count": len(read_jsonl(output_dir / "raw_trajectories.jsonl")),
        "policy_count": len(configs),
        "written": written,
        "skipped": skipped,
    }


def _compare_policies_payload(rows: list[dict[str, object]]) -> dict[str, object]:
    grouped: dict[str, dict[str, float]] = {}
    counts: dict[str, int] = {}
    for row in rows:
        name = str(row.get("policy_name"))
        counts[name] = counts.get(name, 0) + 1
        metrics = row.get("metrics", [])
        if not isinstance(metrics, list):
            continue
        target = grouped.setdefault(name, {})
        for metric in _dict_rows(metrics):
            metric_name = str(metric.get("metric_name"))
            metric_value = metric.get("value", 0.0)
            value = (
                float(metric_value)
                if isinstance(metric_value, int | float | str)
                else 0.0
            )
            target[metric_name] = target.get(metric_name, 0.0) + value
    return {
        "policies": {
            name: {
                metric: value / counts[name]
                for metric, value in sorted(metrics.items())
            }
            for name, metrics in sorted(grouped.items())
        },
        "policy_run_counts": counts,
        "synthetic_only": True,
    }


def _inspect_policy_payload(row: dict[str, object] | None) -> dict[str, object]:
    if row is None:
        return {"found": False}
    return {
        "found": True,
        "policy_run_id": row.get("policy_run_id"),
        "run_id": row.get("run_id"),
        "policy_name": row.get("policy_name"),
        "mode": row.get("mode"),
        "audit_decisions": row.get("decisions", []),
        "feedback": row.get("feedback", []),
        "interventions": row.get("intervention_decisions", []),
        "budget": row.get("final_policy_state", {}),
        "metrics": row.get("metrics", []),
    }


def _frontier_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    frontiers = []
    for row in rows:
        metadata = row.get("metadata", {})
        if isinstance(metadata, dict) and isinstance(metadata.get("frontier_point"), dict):
            frontiers.append(metadata["frontier_point"])
    return frontiers


if __name__ == "__main__":
    main()
