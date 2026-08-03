"""BayesAudit command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from bayesaudit.adaptive.bayesian import BetaBernoulliRiskState
from bayesaudit.adaptive.policies import (
    expected_harm_policy,
    learned_threshold_policy,
    online_priority_policy,
    thompson_policy,
    top_risk_policy,
    value_of_information_policy,
)
from bayesaudit.annotations.monitoring import export_annotations, validate_annotation_import
from bayesaudit.attackers.analysis import build_payoff_matrix, red_team_loop
from bayesaudit.attackers.config import (
    load_phase6_experiment_config,
    validate_attackers,
    validate_attacks,
)
from bayesaudit.attackers.lifecycle import run_attacker_defender_matrix
from bayesaudit.benchmark.io import load_tasks
from bayesaudit.constraints.inheritance import build_registry, create_envelope, verify_envelope
from bayesaudit.monitoring.calibration import (
    CalibrationConfig,
    fit_calibrator,
    load_calibration_config,
)
from bayesaudit.monitoring.dataset import (
    build_monitor_dataset,
    ensure_source_experiments,
    load_monitor_dataset_config,
    load_monitor_examples,
    summarize_monitor_dataset,
    validate_monitor_dataset,
)
from bayesaudit.monitoring.evaluation import evaluate_monitor
from bayesaudit.monitoring.model_cards import generate_model_card
from bayesaudit.monitoring.monitors import (
    MonitorTrainConfig,
    load_monitor_artifact,
    load_monitor_train_config,
    predict_examples,
    train_monitor,
)
from bayesaudit.monitoring.splits import create_split_manifest, validate_no_group_leakage
from bayesaudit.monitoring.types import MonitorArtifact
from bayesaudit.oversight.registry import load_policy_configs, policy_for_config
from bayesaudit.oversight.replay import replay_policies
from bayesaudit.oversight.types import WorkflowMode
from bayesaudit.pilot.config import validate_provider_config
from bayesaudit.pilot.lifecycle import (
    authorize_pilot_provider_run,
    build_real_annotation_sample,
    classify_pilot_tasks,
    estimate_pilot_cost,
    generate_freeze_proposal,
    inspect_provider_request,
    plan_phase8,
    run_measurement_pilot,
    run_provider_connectivity,
    run_real_oversight_pilot,
    run_real_workflow_pilot,
    summarize_real_pilot,
)
from bayesaudit.pilot.lifecycle import (
    evaluate_monitor_transfer as evaluate_phase7_monitor_transfer,
)
from bayesaudit.pilot.phase8 import (
    freeze_phase8_protocol,
    run_phase8_closeout,
    run_phase8_offline_adjudication,
    run_phase8_provider_execution,
    validate_phase8_artifacts,
    validate_phase8_protocol_artifacts,
)
from bayesaudit.pilot.phase9_10 import (
    freeze_phase9_protocol,
    run_phase9_closeout,
    run_phase9_offline_adjudication,
    run_phase9_provider_execution,
    run_phase10a,
    run_phase10b,
    run_phase10c,
    run_phase10d,
    validate_phase9_artifacts,
    validate_phase9_protocol_artifacts,
    validate_phase10_artifacts,
)
from bayesaudit.providers.base import ProviderConfig, estimate_provider_cost
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

    build_dataset = subparsers.add_parser("build-monitor-dataset")
    build_dataset.add_argument("--config", type=Path, required=True)
    build_dataset.add_argument("--dry-run", action="store_true")

    validate_dataset = subparsers.add_parser("validate-monitor-dataset")
    validate_dataset.add_argument("--dataset-dir", type=Path, required=True)

    summarize_dataset = subparsers.add_parser("summarize-monitor-dataset")
    summarize_dataset.add_argument("--dataset-dir", type=Path, required=True)

    create_splits = subparsers.add_parser("create-monitor-splits")
    create_splits.add_argument("--config", type=Path, required=True)
    create_splits.add_argument("--strategy", default=None)

    train_monitor_parser = subparsers.add_parser("train-monitor")
    train_monitor_parser.add_argument("--config", type=Path, required=True)

    calibrate = subparsers.add_parser("calibrate-monitor")
    calibrate.add_argument("--config", type=Path, required=True)

    evaluate = subparsers.add_parser("evaluate-monitor")
    evaluate.add_argument("--config", type=Path, required=True)

    inspect_prediction = subparsers.add_parser("inspect-monitor-prediction")
    inspect_prediction.add_argument("--artifact", type=Path, required=True)
    inspect_prediction.add_argument("--dataset-dir", type=Path, required=True)
    inspect_prediction.add_argument("--example-id", required=True)

    adaptive = subparsers.add_parser("run-adaptive-policy")
    adaptive.add_argument("--config", type=Path, required=True)

    evaluate_adaptive = subparsers.add_parser("evaluate-adaptive-policies")
    evaluate_adaptive.add_argument("--config", type=Path, required=True)

    inspect_posterior = subparsers.add_parser("inspect-posterior")
    inspect_posterior.add_argument("--dataset-dir", type=Path, required=True)

    compare_pairs = subparsers.add_parser("compare-monitor-policy-pairs")
    compare_pairs.add_argument("--config", type=Path, required=True)

    export_ann = subparsers.add_parser("export-annotations")
    export_ann.add_argument("--dataset-dir", type=Path, required=True)
    export_ann.add_argument("--output", type=Path, required=True)
    export_ann.add_argument("--max-items", type=int)

    import_ann = subparsers.add_parser("import-annotations")
    import_ann.add_argument("--path", type=Path, required=True)

    estimate_cost = subparsers.add_parser("estimate-provider-cost")
    estimate_cost.add_argument("--config", type=Path, required=True)

    real_pilot = subparsers.add_parser("run-real-pilot")
    real_pilot.add_argument("--config", type=Path, required=True)
    real_pilot.add_argument("--dry-run", action="store_true")
    real_pilot.add_argument("--allow-provider-calls", action="store_true")

    validate_attackers_parser = subparsers.add_parser("validate-attackers")
    validate_attackers_parser.add_argument("--root", type=Path, default=Path("configs/attackers"))

    subparsers.add_parser("validate-attacks")

    run_attacker = subparsers.add_parser("run-attacker")
    run_attacker.add_argument("--config", type=Path, required=True)
    run_attacker.add_argument("--dry-run", action="store_true")

    run_attacker_defender = subparsers.add_parser("run-attacker-defender")
    run_attacker_defender.add_argument("--config", type=Path, required=True)
    run_attacker_defender.add_argument("--dry-run", action="store_true")
    run_attacker_defender.add_argument("--allow-large-run", action="store_true")

    compare_selection = subparsers.add_parser("compare-attack-selection")
    compare_selection.add_argument("--config", type=Path, required=True)
    compare_selection.add_argument("--dry-run", action="store_true")

    payoff = subparsers.add_parser("build-payoff-matrix")
    payoff.add_argument("--config", type=Path, required=True)

    exploit = subparsers.add_parser("evaluate-exploitability")
    exploit.add_argument("--config", type=Path, required=True)

    inspect_attack = subparsers.add_parser("inspect-attack-run")
    inspect_attack.add_argument("--config", type=Path, required=True)

    inspect_attacker_state = subparsers.add_parser("inspect-attacker-state")
    inspect_attacker_state.add_argument("--config", type=Path, required=True)

    red_team = subparsers.add_parser("run-red-team-loop")
    red_team.add_argument("--config", type=Path, required=True)
    red_team.add_argument("--dry-run", action="store_true")

    summarize_phase6 = subparsers.add_parser("summarize-phase6")
    summarize_phase6.add_argument("--config", type=Path, required=True)

    validate_provider = subparsers.add_parser("validate-provider-config")
    validate_provider.add_argument("--config", type=Path, required=True)

    pilot_cost = subparsers.add_parser("estimate-pilot-cost")
    pilot_cost.add_argument("--config", type=Path, required=True)

    authorize_provider = subparsers.add_parser("authorize-provider-run")
    authorize_provider.add_argument("--config", type=Path, required=True)
    _add_provider_ceiling_args(authorize_provider)

    connectivity = subparsers.add_parser("run-provider-connectivity")
    connectivity.add_argument("--config", type=Path, required=True)
    connectivity.add_argument("--dry-run", action="store_true")
    _add_provider_ceiling_args(connectivity)

    workflow_pilot = subparsers.add_parser("run-real-workflow-pilot")
    workflow_pilot.add_argument("--config", type=Path, required=True)
    workflow_pilot.add_argument("--dry-run", action="store_true")
    workflow_pilot.add_argument("--domain-block", choices=["privacy", "authorization", "evidence"])
    workflow_pilot.add_argument(
        "--architecture-block",
        choices=["unstructured_delegation", "structured_inheritance"],
    )
    _add_provider_ceiling_args(workflow_pilot)

    measurement_pilot = subparsers.add_parser("run-measurement-pilot")
    measurement_pilot.add_argument("--config", type=Path, required=True)
    measurement_pilot.add_argument("--dry-run", action="store_true")
    measurement_pilot.add_argument(
        "--domain-block", choices=["privacy", "authorization", "evidence"]
    )
    measurement_pilot.add_argument("--depth-block", type=int, choices=[1, 2])
    _add_provider_ceiling_args(measurement_pilot)

    scorer_validation = subparsers.add_parser("evaluate-real-scorers")
    scorer_validation.add_argument("--config", type=Path, required=True)

    annotation_sample = subparsers.add_parser("build-real-annotation-sample")
    annotation_sample.add_argument("--config", type=Path, required=True)

    monitor_transfer = subparsers.add_parser("evaluate-monitor-transfer")
    monitor_transfer.add_argument("--config", type=Path, required=True)
    monitor_transfer.add_argument("--dry-run", action="store_true")

    calibration_transfer = subparsers.add_parser("evaluate-calibration-transfer")
    calibration_transfer.add_argument("--config", type=Path, required=True)
    calibration_transfer.add_argument("--dry-run", action="store_true")

    oversight_pilot = subparsers.add_parser("run-real-oversight-pilot")
    oversight_pilot.add_argument("--config", type=Path, required=True)
    oversight_pilot.add_argument("--dry-run", action="store_true")

    summarize_pilot = subparsers.add_parser("summarize-real-pilot")
    summarize_pilot.add_argument("--config", type=Path, required=True)

    inspect_request = subparsers.add_parser("inspect-provider-request")
    inspect_request.add_argument("--config", type=Path, required=True)
    inspect_request.add_argument("--request-hash", required=True)

    inspect_real_trajectory = subparsers.add_parser("inspect-real-trajectory")
    inspect_real_trajectory.add_argument("--config", type=Path, required=True)
    inspect_real_trajectory.add_argument("--trajectory-id", required=True)

    classify_tasks = subparsers.add_parser("classify-pilot-tasks")
    classify_tasks.add_argument("--config", type=Path, required=True)

    freeze = subparsers.add_parser("generate-freeze-proposal")
    freeze.add_argument("--config", type=Path, required=True)

    phase8 = subparsers.add_parser("plan-phase8")
    phase8.add_argument("--config", type=Path, required=True)

    phase8_freeze = subparsers.add_parser("freeze-phase8-protocol")
    phase8_freeze.set_defaults(command="freeze-phase8-protocol")

    phase8_provider = subparsers.add_parser("run-phase8-provider")
    phase8_provider.add_argument("--allow-provider-calls", action="store_true")
    phase8_provider.add_argument("--max-cost", type=float, required=True)
    phase8_provider.add_argument("--max-tokens", type=int, required=True)
    phase8_provider.add_argument("--max-requests", type=int, required=True)
    phase8_provider.add_argument("--max-trajectories", type=int, required=True)

    phase8_adjudicate = subparsers.add_parser("adjudicate-phase8")
    phase8_adjudicate.set_defaults(command="adjudicate-phase8")

    phase8_closeout = subparsers.add_parser("closeout-phase8")
    phase8_closeout.set_defaults(command="closeout-phase8")

    validate_phase8 = subparsers.add_parser("validate-phase8")
    validate_phase8.add_argument("--protocol-only", action="store_true")

    subparsers.add_parser("freeze-phase9-protocol")

    phase9_provider = subparsers.add_parser("run-phase9-provider")
    phase9_provider.add_argument("--allow-provider-calls", action="store_true")
    phase9_provider.add_argument("--max-cost", type=float, required=True)
    phase9_provider.add_argument("--max-tokens", type=int, required=True)
    phase9_provider.add_argument("--max-requests", type=int, required=True)
    phase9_provider.add_argument("--max-trajectories", type=int, required=True)

    subparsers.add_parser("adjudicate-phase9")
    subparsers.add_parser("closeout-phase9")

    validate_phase9 = subparsers.add_parser("validate-phase9")
    validate_phase9.add_argument("--protocol-only", action="store_true")

    subparsers.add_parser("phase10a")
    subparsers.add_parser("phase10b")
    subparsers.add_parser("phase10c")
    subparsers.add_parser("phase10d")
    subparsers.add_parser("validate-phase10")

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
    elif args.command == "build-monitor-dataset":
        dataset_config = load_monitor_dataset_config(args.config)
        if args.dry_run:
            payload = _monitor_dataset_plan(dataset_config)
        else:
            asyncio.run(ensure_source_experiments(dataset_config))
            examples, dataset_manifest = build_monitor_dataset(dataset_config)
            payload = {
                "dataset_id": dataset_manifest.dataset_id,
                "example_count": len(examples),
                "manifest_hash": dataset_manifest.data_hash,
                "output_dir": str(dataset_config.output_root / dataset_config.dataset_id),
            }
    elif args.command == "validate-monitor-dataset":
        payload = validate_monitor_dataset(args.dataset_dir)
    elif args.command == "summarize-monitor-dataset":
        payload = summarize_monitor_dataset(args.dataset_dir)
    elif args.command == "create-monitor-splits":
        split_config = load_monitor_dataset_config(args.config)
        dataset_dir = split_config.output_root / split_config.dataset_id
        split_manifest = create_split_manifest(
            dataset_dir,
            strategy=args.strategy or split_config.split_strategy,
        )
        payload = {
            "split_manifest_id": split_manifest.split_manifest_id,
            "assignment_count": len(split_manifest.assignments),
            "manifest_hash": split_manifest.manifest_hash,
            "leakage_check": validate_no_group_leakage(split_manifest),
        }
    elif args.command == "train-monitor":
        artifact = train_monitor(load_monitor_train_config(args.config))
        payload = artifact.model_dump(mode="json")
    elif args.command == "calibrate-monitor":
        calibration_config = load_calibration_config(args.config)
        dataset_dir = calibration_config.dataset_dir or Path(
            "data/processed/monitoring/phase5_smoke"
        )
        examples = load_monitor_examples(dataset_dir)
        artifact = _default_monitor_artifact(calibration_config)
        predictions = predict_examples(artifact, examples)
        payload = fit_calibrator(calibration_config, predictions, examples).model_dump(mode="json")
    elif args.command == "evaluate-monitor":
        eval_config = load_monitor_dataset_config(args.config)
        dataset_dir = eval_config.output_root / eval_config.dataset_id
        examples = load_monitor_examples(dataset_dir)
        artifact = _default_monitor_artifact(CalibrationConfig(calibration_id="eval"))
        predictions = predict_examples(artifact, examples)
        metrics = evaluate_monitor(
            dataset_id=eval_config.dataset_id,
            split="all",
            monitor_name=artifact.monitor_name,
            examples=examples,
            predictions=predictions,
        )
        generate_model_card(artifact, metrics)
        payload = {
            "metric_count": len(metrics),
            "metrics": [metric.model_dump(mode="json") for metric in metrics],
        }
    elif args.command == "inspect-monitor-prediction":
        artifact = load_monitor_artifact(args.artifact)
        examples = load_monitor_examples(args.dataset_dir)
        example = next(example for example in examples if example.example_id == args.example_id)
        payload = predict_examples(artifact, [example])[0].model_dump(mode="json")
    elif args.command == "run-adaptive-policy" or args.command == "evaluate-adaptive-policies":
        payload = _run_adaptive_payload(load_monitor_dataset_config(args.config))
    elif args.command == "inspect-posterior":
        examples = load_monitor_examples(args.dataset_dir)
        state = BetaBernoulliRiskState()
        for example in examples[:5]:
            state.update_from_audit(
                example,
                label_positive=example.current_violation_label == "positive",
                audited=True,
            )
        payload = state.snapshot().model_dump(mode="json")
    elif args.command == "compare-monitor-policy-pairs":
        payload = _monitor_policy_pairs(load_monitor_dataset_config(args.config))
    elif args.command == "export-annotations":
        payload = export_annotations(args.dataset_dir, args.output, max_items=args.max_items)
    elif args.command == "import-annotations":
        payload = validate_annotation_import(args.path)
    elif args.command == "estimate-provider-cost":
        payload = estimate_provider_cost(_load_provider_config(args.config)).model_dump(mode="json")
    elif args.command == "run-real-pilot":
        provider = _load_provider_config(args.config)
        provider.dry_run = bool(args.dry_run)
        provider.allow_provider_calls = bool(args.allow_provider_calls)
        provider_manifest = estimate_provider_cost(provider)
        if not args.dry_run and provider_manifest.status == "blocked":
            raise PermissionError("real pilot blocked by provider safety gates")
        payload = provider_manifest.model_dump(mode="json")
    elif args.command == "validate-attackers":
        payload = validate_attackers(args.root)
    elif args.command == "validate-attacks":
        payload = validate_attacks()
    elif args.command == "run-attacker":
        phase6_config = load_phase6_experiment_config(args.config)
        payload = run_attacker_defender_matrix(phase6_config, dry_run=args.dry_run)
    elif args.command == "run-attacker-defender":
        phase6_config = load_phase6_experiment_config(args.config)
        if args.allow_large_run:
            phase6_config.allow_large_run = True
        payload = run_attacker_defender_matrix(phase6_config, dry_run=args.dry_run)
    elif args.command == "compare-attack-selection":
        phase6_config = load_phase6_experiment_config(args.config)
        payload = run_attacker_defender_matrix(phase6_config, dry_run=args.dry_run)
        payload["comparison"] = {
            "capability_held_fixed": True,
            "selection_policies": [attacker.name for attacker in phase6_config.attackers],
            "synthetic_only": True,
        }
    elif args.command == "build-payoff-matrix" or args.command == "evaluate-exploitability":
        phase6_config = load_phase6_experiment_config(args.config)
        run_payload = run_attacker_defender_matrix(phase6_config)
        outcomes_path = Path(run_payload["output_dir"]) / "attacker_defender_outcomes.json"
        from bayesaudit.attackers.types import AttackerDefenderOutcome
        from bayesaudit.storage.jsonl import read_json

        outcomes_payload = read_json(outcomes_path)
        raw_outcomes = outcomes_payload.get("records", [])
        outcomes = (
            [AttackerDefenderOutcome.model_validate(row) for row in raw_outcomes]
            if isinstance(raw_outcomes, list)
            else []
        )
        matrix = build_payoff_matrix(outcomes)
        payload = matrix.model_dump(mode="json")
    elif args.command == "inspect-attack-run":
        phase6_config = load_phase6_experiment_config(args.config)
        payload = run_attacker_defender_matrix(phase6_config)
        payload["inspection"] = {
            "delegation_tree": "synthetic monitor-example checkpoints",
            "attack_opportunities": payload.get("planned_attacker_defender_evaluations", 0),
            "defender_observations": "redacted oversight observations only",
            "final_attack_outcome": "see attack_events.json",
        }
    elif args.command == "inspect-attacker-state":
        phase6_config = load_phase6_experiment_config(args.config)
        first = phase6_config.attackers[0] if phase6_config.attackers else None
        payload = {
            "found": first is not None,
            "attacker": first.name if first is not None else None,
            "knowledge_tier": first.knowledge_tier if first is not None else None,
            "attack_budget": first.attack_budget if first is not None else 0,
            "oracle_evaluation_only": bool(first.evaluation_only) if first is not None else False,
        }
    elif args.command == "run-red-team-loop":
        phase6_config = load_phase6_experiment_config(args.config)
        iterations = (
            int(phase6_config.attackers[0].parameters.get("iterations", 2))
            if phase6_config.attackers
            else 2
        )
        payload = red_team_loop(iterations, dry_run=args.dry_run)
    elif args.command == "summarize-phase6":
        phase6_config = load_phase6_experiment_config(args.config)
        payload = run_attacker_defender_matrix(phase6_config, dry_run=True)
    elif args.command == "validate-provider-config":
        payload = validate_provider_config(args.config)
    elif args.command == "estimate-pilot-cost":
        payload = estimate_pilot_cost(args.config)
    elif args.command == "authorize-provider-run":
        payload = authorize_pilot_provider_run(
            args.config,
            allow_provider_calls=args.allow_provider_calls,
            max_cost=args.max_cost,
            max_tokens=args.max_tokens,
            max_requests=args.max_requests,
            max_trajectories=args.max_trajectories,
            allow_large_run=args.allow_large_run,
        )
    elif args.command == "run-provider-connectivity":
        payload = run_provider_connectivity(
            args.config,
            dry_run=args.dry_run,
            allow_provider_calls=args.allow_provider_calls,
            max_cost=args.max_cost,
            max_tokens=args.max_tokens,
            max_requests=args.max_requests,
            max_trajectories=args.max_trajectories,
            allow_large_run=args.allow_large_run,
        )
    elif args.command == "run-real-workflow-pilot":
        payload = run_real_workflow_pilot(
            args.config,
            dry_run=args.dry_run,
            allow_provider_calls=args.allow_provider_calls,
            max_cost=args.max_cost,
            max_tokens=args.max_tokens,
            max_requests=args.max_requests,
            max_trajectories=args.max_trajectories,
            allow_large_run=args.allow_large_run,
            domain_block=args.domain_block,
            architecture_block=args.architecture_block,
        )
    elif args.command == "run-measurement-pilot" or args.command == "evaluate-real-scorers":
        payload = run_measurement_pilot(
            args.config,
            dry_run=getattr(args, "dry_run", True),
            allow_provider_calls=getattr(args, "allow_provider_calls", False),
            max_cost=getattr(args, "max_cost", None),
            max_tokens=getattr(args, "max_tokens", None),
            max_requests=getattr(args, "max_requests", None),
            max_trajectories=getattr(args, "max_trajectories", None),
            allow_large_run=getattr(args, "allow_large_run", False),
            domain_block=getattr(args, "domain_block", None),
            depth_block=getattr(args, "depth_block", None),
        )
    elif args.command == "build-real-annotation-sample":
        payload = build_real_annotation_sample(args.config)
    elif (
        args.command == "evaluate-monitor-transfer"
        or args.command == "evaluate-calibration-transfer"
    ):
        payload = evaluate_phase7_monitor_transfer(args.config, dry_run=args.dry_run)
    elif args.command == "run-real-oversight-pilot":
        payload = run_real_oversight_pilot(args.config, dry_run=args.dry_run)
    elif args.command == "summarize-real-pilot":
        payload = summarize_real_pilot(args.config)
    elif args.command == "inspect-provider-request":
        payload = inspect_provider_request(args.config, args.request_hash)
    elif args.command == "inspect-real-trajectory":
        payload = {
            "found": False,
            "trajectory_id": args.trajectory_id,
            "note": "real-provider trajectories are stored only after authorized pilot runs",
        }
    elif args.command == "classify-pilot-tasks":
        payload = classify_pilot_tasks(args.config)
    elif args.command == "generate-freeze-proposal":
        payload = generate_freeze_proposal(args.config)
    elif args.command == "plan-phase8":
        payload = plan_phase8(args.config)
    elif args.command == "freeze-phase8-protocol":
        payload = freeze_phase8_protocol()
    elif args.command == "run-phase8-provider":
        if not args.allow_provider_calls:
            payload = {
                "valid": False,
                "errors": ["--allow-provider-calls is required for Phase 8 provider execution"],
            }
        elif (
            args.max_cost != 0.20
            or args.max_tokens != 500000
            or args.max_requests != 400
            or args.max_trajectories != 96
        ):
            payload = {
                "valid": False,
                "errors": ["Phase 8 hard ceilings must be exactly the user-authorized values"],
            }
        else:
            payload = run_phase8_provider_execution()
    elif args.command == "adjudicate-phase8":
        payload = run_phase8_offline_adjudication()
    elif args.command == "closeout-phase8":
        payload = run_phase8_closeout()
    elif args.command == "validate-phase8":
        payload = (
            validate_phase8_protocol_artifacts()
            if args.protocol_only
            else validate_phase8_artifacts()
        )
    elif args.command == "freeze-phase9-protocol":
        payload = freeze_phase9_protocol()
    elif args.command == "run-phase9-provider":
        if not args.allow_provider_calls:
            payload = {
                "valid": False,
                "errors": ["--allow-provider-calls is required for Phase 9 provider execution"],
            }
        elif (
            args.max_cost != 0.12
            or args.max_tokens != 300000
            or args.max_requests != 300
            or args.max_trajectories != 48
        ):
            payload = {
                "valid": False,
                "errors": ["Phase 9 hard ceilings must be exactly the user-authorized values"],
            }
        else:
            payload = run_phase9_provider_execution()
    elif args.command == "adjudicate-phase9":
        payload = run_phase9_offline_adjudication()
    elif args.command == "closeout-phase9":
        payload = run_phase9_closeout()
    elif args.command == "validate-phase9":
        payload = (
            validate_phase9_protocol_artifacts()
            if args.protocol_only
            else validate_phase9_artifacts()
        )
    elif args.command == "phase10a":
        payload = run_phase10a()
    elif args.command == "phase10b":
        payload = run_phase10b()
    elif args.command == "phase10c":
        payload = run_phase10c()
    elif args.command == "phase10d":
        payload = run_phase10d()
    elif args.command == "validate-phase10":
        payload = validate_phase10_artifacts()
    else:
        raise AssertionError(args.command)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _add_provider_ceiling_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-provider-calls", action="store_true")
    parser.add_argument("--allow-large-run", action="store_true")
    parser.add_argument("--max-cost", type=float)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--max-trajectories", type=int)


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
            value = float(metric_value) if isinstance(metric_value, int | float | str) else 0.0
            target[metric_name] = target.get(metric_name, 0.0) + value
    return {
        "policies": {
            name: {metric: value / counts[name] for metric, value in sorted(metrics.items())}
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


def _monitor_dataset_plan(config: object) -> dict[str, object]:
    from bayesaudit.monitoring.dataset import MonitorDatasetConfig

    if not isinstance(config, MonitorDatasetConfig):
        raise TypeError("expected monitor dataset config")
    return {
        "dataset_id": config.dataset_id,
        "source_experiments": config.source_experiments,
        "label_horizon": config.label_horizon,
        "output_dir": str(config.output_root / config.dataset_id),
        "allow_large_run": config.allow_large_run,
        "provider_cost_estimate": 0.0,
        "synthetic_only": True,
    }


def _default_monitor_artifact(config: CalibrationConfig) -> MonitorArtifact:
    del config
    artifact_dir = Path("results/tables/monitors")
    artifact_path = artifact_dir / "constant_smoke.json"
    if artifact_path.exists():
        return load_monitor_artifact(artifact_path)
    train_config = MonitorTrainConfig(
        monitor_name="constant_smoke",
        monitor_type="constant",
        dataset_dir=Path("data/processed/monitoring/phase5_smoke"),
    )
    if train_config.dataset_dir.exists():
        return train_monitor(train_config)
    return MonitorArtifact(
        monitor_name="constant_smoke",
        monitor_version="phase5_v1",
        monitor_type="constant",
        target="current_violation_label",
        feature_names=[],
        artifact_hash="constant_untrained",
        training_dataset_hash="",
        split_manifest_hash="",
        parameters={"prevalence": 0.1},
    )


def _run_adaptive_payload(config: object) -> dict[str, object]:
    from bayesaudit.monitoring.dataset import MonitorDatasetConfig

    if not isinstance(config, MonitorDatasetConfig):
        raise TypeError("expected monitor dataset config")
    dataset_dir = config.output_root / config.dataset_id
    examples = load_monitor_examples(dataset_dir)
    artifact = _default_monitor_artifact(CalibrationConfig(calibration_id="adaptive"))
    predictions = predict_examples(artifact, examples)
    policies = [
        learned_threshold_policy(examples, predictions, threshold=0.5, budget=2),
        top_risk_policy(examples, predictions, budget=2),
        online_priority_policy(examples, predictions, budget=2),
        thompson_policy(examples, budget=2, seed=1),
        expected_harm_policy(examples, predictions, budget=2),
        value_of_information_policy(examples, predictions, budget=2),
    ]
    return {
        "policy_count": len(policies),
        "example_count": len(examples),
        "policies": [
            {
                "policy_name": policy.policy_name,
                "decision_count": len(policy.decisions),
                "metrics": policy.metrics,
            }
            for policy in policies
        ],
    }


def _monitor_policy_pairs(config: object) -> dict[str, object]:
    payload = _run_adaptive_payload(config)
    pairs = []
    raw_policies = payload.get("policies", [])
    policies = raw_policies if isinstance(raw_policies, list) else []
    for policy in policies:
        if isinstance(policy, dict):
            metrics = policy.get("metrics")
            pairs.append(
                {
                    "monitor": "constant_smoke",
                    "policy": str(policy.get("policy_name", "unknown")),
                    "audit_yield": metrics.get("audit_yield", 0.0)
                    if isinstance(metrics, dict)
                    else 0.0,
                }
            )
    return {"pair_count": len(pairs), "pairs": pairs, "synthetic_only": True}


def _load_provider_config(path: Path) -> ProviderConfig:
    import yaml

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"provider config must be a mapping: {path}")
    provider_payload = payload.get("provider", payload)
    if not isinstance(provider_payload, dict):
        raise ValueError("provider config must contain a mapping")
    return ProviderConfig.model_validate(provider_payload)


if __name__ == "__main__":
    main()
