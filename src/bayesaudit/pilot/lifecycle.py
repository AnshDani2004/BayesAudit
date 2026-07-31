"""Phase 7 pilot lifecycle commands and artifact writers."""

from __future__ import annotations

import json
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from bayesaudit.benchmark.io import load_tasks
from bayesaudit.monitoring.monitors import load_monitor_artifact, predict_examples
from bayesaudit.monitoring.types import LabelValue, MonitorExample, MonitorPrediction
from bayesaudit.pilot.annotation import build_annotation_sample
from bayesaudit.pilot.config import (
    config_hash,
    load_pilot_experiment_config,
    load_pilot_provider_config,
)
from bayesaudit.pilot.costs import (
    calculate_cost_accounting,
    load_pricing_record,
    response_attempt_from_usage,
)
from bayesaudit.pilot.prompts import openai_stage_a1_diagnostic_prompt, render_prompt
from bayesaudit.pilot.providers import (
    ProviderLedger,
    RequestCache,
    authorize_provider_run,
    classify_provider_failure,
    estimate_pilot_plan,
    execute_provider_or_cached,
    make_provider_request,
    write_permission_record,
)
from bayesaudit.pilot.stage_b import (
    run_stage_b_domain_block,
    stage_b_request_plan,
    summarize_stage_b,
    validate_stage_b_config,
)
from bayesaudit.pilot.structured import parse_structured_output
from bayesaudit.pilot.transfer import (
    calibration_transfer_metrics,
    monitor_transfer_metrics,
    ood_transfer_metrics,
    oversight_feasibility_records,
)
from bayesaudit.pilot.types import (
    PILOT_ARTIFACT_VERSION,
    PILOT_SCHEMA_VERSION,
    CostAccountingRecord,
    CostReconciliationStatus,
    PilotExperimentConfig,
    PilotManifest,
    PilotPlan,
    PilotProviderConfig,
    PilotStatus,
)
from bayesaudit.pilot.validation import (
    default_scorer_readiness,
    default_task_readiness,
    readiness_counts,
)
from bayesaudit.schemas import ArchitectureKind, BenchmarkTask, Domain
from bayesaudit.storage.jsonl import append_jsonl, read_json, read_jsonl, write_json_atomic


def estimate_pilot_cost(config_path: Path) -> dict[str, Any]:
    config, provider, plan = _config_provider_plan(config_path)
    del config
    return plan.model_dump(mode="json")


def authorize_pilot_provider_run(
    config_path: Path,
    *,
    allow_provider_calls: bool,
    max_cost: float | None,
    max_tokens: int | None,
    max_requests: int | None,
    max_trajectories: int | None,
    allow_large_run: bool = False,
) -> dict[str, Any]:
    config, provider, plan = _config_provider_plan(config_path)
    output_dir = _output_dir(config)
    manifest = write_pilot_manifest(config, provider, plan, status="planned")
    record = authorize_provider_run(
        config,
        provider,
        plan,
        allow_provider_calls=allow_provider_calls,
        max_cost=max_cost,
        max_tokens=max_tokens,
        max_requests=max_requests,
        max_trajectories=max_trajectories,
        allow_large_run=allow_large_run,
        output_writable=_writable(output_dir),
        manifest_written=True,
        current_code_commit=_git("rev-parse", "--short", "HEAD"),
    )
    path = write_permission_record(output_dir, record)
    return {
        "authorization": record.model_dump(mode="json"),
        "permission_record_path": str(path),
        "manifest_id": manifest.pilot_id,
        "allowed": record.final_authorization_decision == "allow",
    }


def run_provider_connectivity(
    config_path: Path,
    *,
    dry_run: bool,
    allow_provider_calls: bool = False,
    max_cost: float | None = None,
    max_tokens: int | None = None,
    max_requests: int | None = None,
    max_trajectories: int | None = None,
    allow_large_run: bool = False,
) -> dict[str, Any]:
    config, provider, plan = _config_provider_plan(config_path)
    output_dir = _output_dir(config)
    manifest = write_pilot_manifest(
        config, provider, plan, status="dry_run" if dry_run else "planned"
    )
    permission_payload = authorize_pilot_provider_run(
        config_path,
        allow_provider_calls=allow_provider_calls,
        max_cost=max_cost,
        max_tokens=max_tokens,
        max_requests=max_requests,
        max_trajectories=max_trajectories,
        allow_large_run=allow_large_run,
    )
    if dry_run:
        return {
            **plan.model_dump(mode="json"),
            "dry_run": True,
            "pilot_manifest_status": manifest.status,
            "provider_calls_performed": 0,
            "permission_decision": permission_payload["authorization"][
                "final_authorization_decision"
            ],
        }
    if provider.provider_class != "mock" and not permission_payload["allowed"]:
        raise PermissionError("provider run blocked by Phase 7 safety gates")
    task = _selected_tasks(config)[0]
    if config.pilot_id == "phase7_connectivity_openai_stage_a1":
        prompt = openai_stage_a1_diagnostic_prompt(task)
    else:
        prompt = render_prompt(
            template_name="single_agent",
            task=task,
            architecture=ArchitectureKind.SINGLE_AGENT.value,
            agent_role="connectivity",
            delegation_depth=0,
        )
    request = make_provider_request(
        provider,
        prompt_hash=prompt.prompt_hash,
        rendered_prompt=prompt.rendered_prompt,
    )
    write_json_atomic(output_dir / "prompt_render_record.json", prompt.model_dump(mode="json"))
    write_json_atomic(output_dir / "provider_request_record.json", request.model_dump(mode="json"))
    cache = RequestCache(output_dir / "request_cache")
    ledger = ProviderLedger(output_dir / "provider_request_ledger.jsonl")
    try:
        response, cached = execute_provider_or_cached(
            provider,
            request,
            rendered_prompt=prompt.rendered_prompt,
            cache=cache,
            ledger=ledger,
            raw_response_hook=lambda artifact: write_json_atomic(
                output_dir / "provider_raw_response.json", artifact
            ),
            cache_validator=(
                _valid_stage_a1_diagnostic_response
                if config.pilot_id == "phase7_connectivity_openai_stage_a1"
                else None
            ),
        )
    except Exception as exc:
        failure = classify_provider_failure(
            exc, provider=provider, request_hash=request.request_hash
        )
        ledger.append_request(request.model_copy(update={"status": "failed", "attempt_count": 1}))
        append_jsonl(output_dir / "provider_failures.jsonl", failure.model_dump(mode="json"))
        write_json_atomic(
            output_dir / "provider_failure_record.json", failure.model_dump(mode="json")
        )
        raw_failure_payload = getattr(exc, "payload", None)
        if isinstance(raw_failure_payload, dict) and raw_failure_payload:
            write_json_atomic(
                output_dir / "provider_failure_raw_response.json", raw_failure_payload
            )
        write_pilot_manifest(config, provider, plan, status="failed")
        return {
            **plan.model_dump(mode="json"),
            "dry_run": False,
            "provider_calls_performed": 1,
            "cached_requests": 0,
            "completed_requests": 0,
            "failed_requests": 1,
            "failure_type": failure.failure_type,
            "failure_message": failure.message,
            "output_dir": str(output_dir),
        }
    parsed = (
        _parse_stage_a1_diagnostic_response(response.raw_output)
        if config.pilot_id == "phase7_connectivity_openai_stage_a1"
        else parse_structured_output(response.raw_output).model_dump(mode="json")
    )
    write_json_atomic(output_dir / "connectivity_response.json", response.model_dump(mode="json"))
    write_json_atomic(output_dir / "connectivity_structured_output.json", parsed)
    manifest_status: PilotStatus = "completed"
    final_manifest = write_pilot_manifest(config, provider, plan, status=manifest_status)
    ledger_rows = read_jsonl(output_dir / "provider_request_ledger.jsonl")
    completed_rows = [row for row in ledger_rows if row.get("status") == "completed"]
    cached_rows = [row for row in ledger_rows if row.get("status") == "cached"]
    final_manifest.completed_requests = len(completed_rows)
    final_manifest.cached_requests = len(cached_rows)
    final_manifest.actual_tokens = response.total_tokens
    final_manifest.estimated_cost_usd = Decimal(str(plan.estimated_cost))
    final_manifest.token_derived_cost_usd = response.token_derived_cost_usd
    final_manifest.provider_reported_cost_usd = response.provider_reported_cost_usd
    final_manifest.billed_cost_usd = response.billed_cost_usd
    final_manifest.conservative_upper_bound_usd = Decimal(str(plan.maximum_possible_cost))
    final_manifest.cost_reconciliation_status = response.cost_reconciliation_status
    final_manifest.pricing_table_version = response.pricing_table_version
    final_manifest.pricing_components = response.pricing_components
    write_json_atomic(output_dir / "pilot_manifest.json", final_manifest.model_dump(mode="json"))
    incremental_cost = _incremental_cost_accounting(
        provider,
        plan,
        response.provider_reported_usage,
        cached=cached,
    )
    return {
        **plan.model_dump(mode="json"),
        "dry_run": False,
        "provider_calls_performed": 0 if cached else 1,
        "cached_requests": 1 if cached else 0,
        "completed_requests": 1,
        "failed_requests": 0,
        "request_hash": request.request_hash,
        "prompt_hash": prompt.prompt_hash,
        "input_tokens": response.input_tokens,
        "cached_input_tokens": response.provider_reported_usage.get("cached_input_tokens", 0),
        "output_tokens": response.output_tokens,
        "reasoning_tokens": response.provider_reported_usage.get("reasoning_tokens", 0),
        "total_tokens": response.total_tokens,
        "estimated_cost_usd": str(Decimal(str(plan.estimated_cost))),
        "token_derived_cost_usd": (
            str(incremental_cost.token_derived_cost_usd)
            if incremental_cost.token_derived_cost_usd is not None
            else None
        ),
        "provider_reported_cost_usd": (
            str(incremental_cost.provider_reported_cost_usd)
            if incremental_cost.provider_reported_cost_usd is not None
            else None
        ),
        "billed_cost_usd": (
            str(incremental_cost.billed_cost_usd)
            if incremental_cost.billed_cost_usd is not None
            else None
        ),
        "conservative_upper_bound_usd": str(Decimal(str(plan.maximum_possible_cost))),
        "cost_reconciliation_status": incremental_cost.cost_reconciliation_status,
        "pricing_table_version": incremental_cost.pricing_table_version,
        "finish_reason": response.finish_reason,
        "structured_output_valid": bool(parsed.get("valid")),
        "output_dir": str(output_dir),
    }


def run_real_workflow_pilot(
    config_path: Path,
    *,
    dry_run: bool,
    allow_provider_calls: bool = False,
    max_cost: float | None = None,
    max_tokens: int | None = None,
    max_requests: int | None = None,
    max_trajectories: int | None = None,
    allow_large_run: bool = False,
    domain_block: str | None = None,
) -> dict[str, Any]:
    config, provider, plan = _config_provider_plan(config_path)
    output_dir = _output_dir(config)
    manifest = write_pilot_manifest(
        config, provider, plan, status="dry_run" if dry_run else "planned"
    )
    if config.pilot_id == "phase7_workflow_openai_stage_b":
        validation = validate_stage_b_config(config)
        request_plan = stage_b_request_plan(config, provider, plan)
        if not validation["valid"]:
            raise ValueError(f"invalid Stage B config: {validation['errors']}")
        if request_plan["maximum_possible_requests"] > int(
            max_requests or config.request_ceiling or 0
        ):
            raise PermissionError("Stage B maximum possible requests exceed ceiling")
        if plan.estimated_total_tokens > int(max_tokens or config.token_ceiling or 0):
            raise PermissionError("Stage B estimated tokens exceed ceiling")
        if plan.maximum_possible_cost > float(max_cost or config.cost_ceiling or 0.0):
            raise PermissionError("Stage B estimated cost exceeds ceiling")
        if dry_run:
            return {
                **plan.model_dump(mode="json"),
                **request_plan,
                "dry_run": True,
                "pilot_manifest_status": manifest.status,
                "provider_calls_performed": 0,
                "output_dir": str(output_dir),
                "cost_ceiling": max_cost if max_cost is not None else config.cost_ceiling,
                "token_ceiling": max_tokens if max_tokens is not None else config.token_ceiling,
                "request_ceiling": max_requests
                if max_requests is not None
                else config.request_ceiling,
                "trajectory_ceiling": max_trajectories
                if max_trajectories is not None
                else config.trajectory_ceiling,
            }
        permission_payload = authorize_pilot_provider_run(
            config_path,
            allow_provider_calls=allow_provider_calls,
            max_cost=max_cost,
            max_tokens=max_tokens,
            max_requests=max_requests,
            max_trajectories=max_trajectories,
            allow_large_run=allow_large_run,
        )
        if not permission_payload["allowed"]:
            raise PermissionError("Stage B provider run blocked by Phase 7 safety gates")
        if domain_block is None:
            raise ValueError("Stage B real execution requires --domain-block")
        payload = run_stage_b_domain_block(
            config=config,
            provider=provider,
            plan=plan,
            tasks=_selected_tasks(config),
            output_dir=output_dir,
            domain_block=domain_block,
            max_requests=int(max_requests or config.request_ceiling or 0),
            max_tokens=int(max_tokens or config.token_ceiling or 0),
            max_cost=float(max_cost or config.cost_ceiling or 0.0),
        )
        final_summary = summarize_stage_b(config, provider, plan, output_dir)
        final_manifest = write_pilot_manifest(config, provider, plan, status="completed")
        final_manifest.completed_requests = int(final_summary["actual_requests"])
        final_manifest.cached_requests = int(final_summary["cached_executions"])
        final_manifest.failed_requests = int(final_summary["failed_requests"])
        final_manifest.actual_tokens = int(final_summary["total_tokens"])
        final_manifest.token_derived_cost_usd = Decimal(
            str(final_summary["token_derived_cost_usd"])
        )
        final_manifest.provider_reported_cost_usd = None
        final_manifest.billed_cost_usd = None
        final_manifest.cost_reconciliation_status = cast(
            CostReconciliationStatus,
            str(final_summary["cost_reconciliation_status"]),
        )
        final_manifest.pricing_table_version = str(final_summary["pricing_table_version"])
        write_json_atomic(
            output_dir / "pilot_manifest.json", final_manifest.model_dump(mode="json")
        )
        return {
            **payload,
            "final_summary": final_summary,
            "provider_calls_performed": payload["summary"]["actual_requests"],
            "output_dir": str(output_dir),
        }
    write_json_atomic(
        output_dir / "workflow_quality_flags.json",
        _workflow_quality_placeholder(config, plan),
    )
    return {
        **plan.model_dump(mode="json"),
        "dry_run": dry_run,
        "pilot_manifest_status": manifest.status,
        "workflow_quality_results_generated": True,
        "provider_calls_performed": 0,
        "output_dir": str(output_dir),
    }


def run_measurement_pilot(config_path: Path, *, dry_run: bool) -> dict[str, Any]:
    config, provider, plan = _config_provider_plan(config_path)
    output_dir = _output_dir(config)
    manifest = write_pilot_manifest(
        config, provider, plan, status="dry_run" if dry_run else "planned"
    )
    tasks = _selected_tasks(config)
    readiness = default_task_readiness([task.task_id for task in tasks])
    scorer_readiness = default_scorer_readiness([str(task.domain) for task in tasks])
    write_json_atomic(
        output_dir / "task_readiness.json",
        {"records": [record.model_dump(mode="json") for record in readiness]},
    )
    write_json_atomic(
        output_dir / "scorer_readiness.json",
        {"records": [record.model_dump(mode="json") for record in scorer_readiness]},
    )
    return {
        **plan.model_dump(mode="json"),
        "dry_run": dry_run,
        "pilot_manifest_status": manifest.status,
        "task_readiness_counts": readiness_counts(readiness),
        "scorer_readiness_counts": readiness_counts(scorer_readiness),
        "provider_calls_performed": 0,
    }


def evaluate_monitor_transfer(config_path: Path, *, dry_run: bool) -> dict[str, Any]:
    config, provider, plan = _config_provider_plan(config_path)
    output_dir = _output_dir(config)
    write_pilot_manifest(config, provider, plan, status="dry_run" if dry_run else "planned")
    examples = _pilot_monitor_examples(config)
    predictions = _pilot_predictions(config, examples)
    monitor_metrics = monitor_transfer_metrics(examples, predictions)
    calibration_metrics_records = calibration_transfer_metrics(examples, predictions)
    ood_metrics = ood_transfer_metrics(examples)
    write_json_atomic(
        output_dir / "monitor_transfer_results.json",
        {"records": [record.model_dump(mode="json") for record in monitor_metrics]},
    )
    write_json_atomic(
        output_dir / "calibration_transfer_results.json",
        {"records": [record.model_dump(mode="json") for record in calibration_metrics_records]},
    )
    write_json_atomic(
        output_dir / "ood_results.json",
        {"records": [record.model_dump(mode="json") for record in ood_metrics]},
    )
    return {
        "pilot_id": config.pilot_id,
        "dry_run": dry_run,
        "example_count": len(examples),
        "monitor_metric_count": len(monitor_metrics),
        "calibration_metric_count": len(calibration_metrics_records),
        "ood_metric_count": len(ood_metrics),
        "no_pilot_test_retraining": True,
        "provider_calls_performed": 0,
    }


def run_real_oversight_pilot(config_path: Path, *, dry_run: bool) -> dict[str, Any]:
    config, provider, plan = _config_provider_plan(config_path)
    output_dir = _output_dir(config)
    write_pilot_manifest(config, provider, plan, status="dry_run" if dry_run else "planned")
    records = oversight_feasibility_records()
    write_json_atomic(
        output_dir / "oversight_feasibility_results.json",
        {"records": [record.model_dump(mode="json") for record in records]},
    )
    return {
        **plan.model_dump(mode="json"),
        "dry_run": dry_run,
        "oversight_feasibility_count": len(records),
        "all_tool_actions_inert_or_sandboxed": all(record.inert_or_sandboxed for record in records),
        "provider_calls_performed": 0,
    }


def build_real_annotation_sample(config_path: Path) -> dict[str, Any]:
    config = load_pilot_experiment_config(config_path)
    output_dir = _output_dir(config)
    rows = _placeholder_trajectory_rows(config)
    payload = build_annotation_sample(
        rows,
        sample_size=int(config.human_review_sample_size or len(rows)),
    )
    write_json_atomic(output_dir / "annotation_sample_blind.json", payload)
    return payload


def summarize_real_pilot(config_path: Path) -> dict[str, Any]:
    config, provider, plan = _config_provider_plan(config_path)
    output_dir = _output_dir(config)
    ledger_rows = read_jsonl(output_dir / "provider_request_ledger.jsonl")
    completed = [row for row in ledger_rows if row.get("status") == "completed"]
    cached = [row for row in ledger_rows if row.get("status") == "cached"]
    failed = read_jsonl(output_dir / "provider_failures.jsonl")
    response = (
        read_json(output_dir / "connectivity_response.json")
        if (output_dir / "connectivity_response.json").exists()
        else {}
    )
    actual_tokens = int(response.get("total_tokens", 0) or 0) if completed else 0
    cost_record = (
        _preserved_response_cost_accounting(provider, plan, response) if completed else None
    )
    derived_cost = None
    if cost_record and cost_record.token_derived_cost_usd is not None:
        derived_cost = str(cost_record.token_derived_cost_usd)
    token_cost = response.get("token_derived_cost_usd") or derived_cost
    cost_status = response.get("cost_reconciliation_status") or (
        cost_record.cost_reconciliation_status if cost_record else "unreconciled"
    )
    return {
        "pilot_id": config.pilot_id,
        "provider": provider.provider_name or provider.provider_class,
        "model_identifier": provider.model_identifier,
        "planned_requests": plan.planned_requests,
        "completed_requests": len(completed),
        "cached_requests": len(cached),
        "failed_requests": len(failed),
        "estimated_tokens": plan.estimated_total_tokens,
        "actual_tokens": actual_tokens,
        "estimated_cost": plan.estimated_cost,
        "estimated_cost_usd": str(Decimal(str(plan.estimated_cost))),
        "token_derived_cost_usd": token_cost,
        "provider_reported_cost_usd": response.get("provider_reported_cost_usd")
        or (
            str(cost_record.provider_reported_cost_usd)
            if cost_record and cost_record.provider_reported_cost_usd is not None
            else None
        ),
        "billed_cost_usd": response.get("billed_cost_usd")
        or (
            str(cost_record.billed_cost_usd)
            if cost_record and cost_record.billed_cost_usd is not None
            else None
        ),
        "conservative_upper_bound_usd": str(Decimal(str(plan.maximum_possible_cost))),
        "cost_reconciliation_status": cost_status,
        "pricing_table_version": response.get("pricing_table_version")
        or (cost_record.pricing_table_version if cost_record else None),
        "real_model_trajectory_count": len(completed),
        "valid_trajectory_count": len(completed),
        "excluded_trajectory_count": 0,
        "exploratory_only": True,
    }


def inspect_provider_request(config_path: Path, request_hash: str) -> dict[str, Any]:
    config = load_pilot_experiment_config(config_path)
    for row in read_jsonl(_output_dir(config) / "provider_request_ledger.jsonl"):
        if row.get("request_hash") == request_hash or row.get("request_id") == request_hash:
            safe = dict(row)
            safe.pop("credentials", None)
            return {"found": True, "request": safe}
    return {"found": False}


def classify_pilot_tasks(config_path: Path) -> dict[str, Any]:
    config = load_pilot_experiment_config(config_path)
    tasks = _selected_tasks(config)
    records = default_task_readiness([task.task_id for task in tasks])
    payload = {
        "records": [record.model_dump(mode="json") for record in records],
        "counts": readiness_counts(records),
    }
    write_json_atomic(_output_dir(config) / "task_readiness.json", payload)
    return payload


def generate_freeze_proposal(config_path: Path) -> dict[str, Any]:
    config = load_pilot_experiment_config(config_path)
    tasks = _selected_tasks(config)
    payload = {
        "schema_version": PILOT_SCHEMA_VERSION,
        "artifact_version": PILOT_ARTIFACT_VERSION,
        "pilot_id": config.pilot_id,
        "recommendation": "not_ready_to_freeze",
        "final_proposed_task_set": [task.task_id for task in tasks],
        "removed_tasks": [],
        "redesigned_tasks": [],
        "known_limitations": [
            "proposal is generated before any authorized real-provider pilot observations",
            "benchmark freeze requires explicit approval after real-pilot review",
        ],
        "requires_explicit_freeze_approval": True,
    }
    write_json_atomic(_output_dir(config) / "benchmark_freeze_proposal.json", payload)
    return payload


def plan_phase8(config_path: Path) -> dict[str, Any]:
    config, provider, plan = _config_provider_plan(config_path)
    payload = {
        "schema_version": PILOT_SCHEMA_VERSION,
        "artifact_version": PILOT_ARTIFACT_VERSION,
        "pilot_id": config.pilot_id,
        "approximate": True,
        "candidate_designs": [
            {
                "name": "small_confirmatory",
                "required_trajectories": max(100, plan.planned_trajectories * 5),
                "estimated_cost": round(plan.maximum_possible_cost * 5, 4),
                "model_families": 2,
                "human_labeled_subset": max(30, config.human_review_sample_size * 3),
            },
            {
                "name": "medium_confirmatory",
                "required_trajectories": max(300, plan.planned_trajectories * 10),
                "estimated_cost": round(plan.maximum_possible_cost * 10, 4),
                "model_families": 3,
                "human_labeled_subset": max(60, config.human_review_sample_size * 5),
            },
        ],
        "provider": provider.provider_name or provider.provider_class,
        "phase8_not_started": True,
    }
    write_json_atomic(_output_dir(config) / "phase8_planning_estimates.json", payload)
    return payload


def write_pilot_manifest(
    config: PilotExperimentConfig,
    provider: PilotProviderConfig,
    plan: PilotPlan,
    *,
    status: PilotStatus,
) -> PilotManifest:
    tasks = _selected_tasks(config)
    manifest = PilotManifest(
        pilot_id=config.pilot_id,
        pilot_version=config.pilot_version,
        repository=config.repository,
        base_branch=config.base_branch,
        base_commit=config.base_commit,
        phase7_branch=config.phase7_branch,
        current_code_commit=_git("rev-parse", "--short", "HEAD"),
        working_tree_status=_working_tree_status(),
        experiment_configuration_hash=config_hash(config),
        benchmark_version=config.benchmark_version,
        scenario_hashes={task.task_id: task.scenario_hash for task in tasks},
        prompt_renderer_version=config.prompt_renderer_version,
        provider_configuration_hash=config_hash(provider),
        provider=provider.provider_name or provider.provider_class,
        exact_model_identifier=provider.model_identifier,
        architecture_conditions=[str(value) for value in config.architectures],
        domains=[str(value) for value in config.domains],
        tasks=[task.task_id for task in tasks],
        delegation_depths=config.delegation_depths,
        branching_factors=config.branching_factors,
        behavior_conditions=config.behavior_conditions,
        attacker_conditions=config.attacker_conditions,
        oversight_conditions=config.oversight_conditions,
        monitor_artifacts=[str(path) for path in config.monitor_artifacts],
        calibration_artifacts=[str(path) for path in config.calibration_artifacts],
        seeds=config.seeds,
        sampling_parameters={**provider.sampling_parameters, **config.sampling_parameters},
        cost_ceiling=config.cost_ceiling,
        token_ceiling=config.token_ceiling,
        request_ceiling=config.request_ceiling,
        trajectory_ceiling=config.trajectory_ceiling,
        estimated_cost=plan.estimated_cost,
        estimated_cost_usd=Decimal(str(plan.estimated_cost)),
        conservative_upper_bound_usd=Decimal(str(plan.maximum_possible_cost)),
        estimated_tokens=plan.estimated_total_tokens,
        planned_requests=plan.planned_requests,
        human_review_sampling_plan=config.human_review_sampling_plan,
        status=status,
        notes=config.notes,
    )
    write_json_atomic(_output_dir(config) / "pilot_manifest.json", manifest.model_dump(mode="json"))
    return manifest


def _incremental_cost_accounting(
    provider: PilotProviderConfig,
    plan: PilotPlan,
    usage: dict[str, Any],
    *,
    cached: bool,
) -> CostAccountingRecord:
    provider_name = provider.provider_name or provider.provider_class
    model_identifier = provider.model_identifier or "mock-deterministic-v1"
    try:
        pricing = load_pricing_record(provider_name, model_identifier)
    except KeyError:
        pricing = None
    return calculate_cost_accounting(
        provider=provider_name,
        model_identifier=model_identifier,
        attempts=[response_attempt_from_usage(usage, status="cached" if cached else "completed")],
        pricing=pricing,
        estimated_cost_usd=Decimal(str(plan.estimated_cost)),
        conservative_upper_bound_usd=Decimal(str(plan.maximum_possible_cost)),
    )


def _preserved_response_cost_accounting(
    provider: PilotProviderConfig,
    plan: PilotPlan,
    response: dict[str, Any],
) -> CostAccountingRecord:
    provider_name = provider.provider_name or provider.provider_class
    model_identifier = provider.model_identifier or "mock-deterministic-v1"
    try:
        pricing = load_pricing_record(provider_name, model_identifier)
    except KeyError:
        pricing = None
    usage = response.get("provider_reported_usage")
    if not isinstance(usage, dict):
        usage = {
            "input_tokens": int(response.get("input_tokens", 0) or 0),
            "cached_input_tokens": 0,
            "output_tokens": int(response.get("output_tokens", 0) or 0),
            "reasoning_tokens": 0,
        }
        if not any(usage.values()):
            usage = {}
    return calculate_cost_accounting(
        provider=provider_name,
        model_identifier=model_identifier,
        attempts=[response_attempt_from_usage(usage, status="completed")],
        pricing=pricing,
        estimated_cost_usd=Decimal(str(plan.estimated_cost)),
        conservative_upper_bound_usd=Decimal(str(plan.maximum_possible_cost)),
    )


def _valid_stage_a1_diagnostic_response(response: Any) -> bool:
    return bool(_parse_stage_a1_diagnostic_response(str(response.raw_output)).get("valid"))


def _parse_stage_a1_diagnostic_response(raw_output: str) -> dict[str, Any]:
    expected = {
        "status": "ok",
        "message": "BayesAudit Stage A connectivity passed",
    }
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        return {
            "schema_version": PILOT_SCHEMA_VERSION,
            "valid": False,
            "parse_errors": [str(exc)],
            "parsed_output": {},
            "expected_output": expected,
        }
    valid = payload == expected
    return {
        "schema_version": PILOT_SCHEMA_VERSION,
        "valid": valid,
        "parse_errors": [] if valid else ["diagnostic JSON did not match expected value"],
        "parsed_output": payload if isinstance(payload, dict) else {},
        "expected_output": expected,
    }


def _config_provider_plan(
    config_path: Path,
) -> tuple[PilotExperimentConfig, PilotProviderConfig, PilotPlan]:
    config = load_pilot_experiment_config(config_path)
    provider = load_pilot_provider_config(config.provider_config)
    plan = estimate_pilot_plan(config, provider, task_count=len(_selected_tasks(config)))
    return config, provider, plan


def _selected_tasks(config: PilotExperimentConfig) -> list[BenchmarkTask]:
    tasks: list[BenchmarkTask] = []
    for root in config.task_roots:
        tasks.extend(load_tasks(root))
    if config.domains:
        allowed = {str(domain) for domain in config.domains}
        tasks = [task for task in tasks if str(task.domain) in allowed]
    if config.task_ids:
        selected = set(config.task_ids)
        tasks = [task for task in tasks if task.task_id in selected]
    if config.max_runs is not None:
        tasks = tasks[: max(1, min(len(tasks), int(config.max_runs)))]
    return tasks


def _pilot_monitor_examples(config: PilotExperimentConfig) -> list[MonitorExample]:
    examples: list[MonitorExample] = []
    for index, task in enumerate(_selected_tasks(config)[: max(1, int(config.max_runs or 5))]):
        features = {
            "depth": config.delegation_depths[0] if config.delegation_depths else 1,
            "branch_present": False,
            "tool_requested": task.domain == Domain.AUTHORIZATION,
            "sensitive_token_indicator": task.domain == Domain.PRIVACY,
            "missing_required_constraints": False,
            "text_length": len(task.description),
            "constraint_count": len(task.constraints),
        }
        examples.append(
            MonitorExample(
                example_id=f"phase7_example_{index}",
                observation_id=f"phase7_obs_{index}",
                trajectory_id=f"phase7_traj_{index}",
                run_id=f"phase7_run_{index}",
                experiment_id=config.pilot_id,
                task_id=task.task_id,
                task_version=task.task_version,
                template_family=str(task.domain),
                domain=task.domain,
                architecture=config.architectures[0]
                if config.architectures
                else ArchitectureKind.UNSTRUCTURED_DELEGATION,
                model_family="real_pilot_mock",
                checkpoint_type="before_final_output",
                sequence_index=index,
                depth=int(features["depth"]),
                observable_feature_payload=features,
                observable_text_payload="redacted real-pilot placeholder observation",
                current_violation_label=LabelValue.POSITIVE if index % 2 else LabelValue.NEGATIVE,
                imminent_violation_label=LabelValue.POSITIVE if index % 2 else LabelValue.NEGATIVE,
                preventable_imminent_violation_label=LabelValue.NEGATIVE,
                severity_target=1.0 if index % 2 else 0.0,
                intervention_usefulness_label=LabelValue.NEGATIVE,
                final_output_violation_label=(
                    LabelValue.POSITIVE if index % 3 == 0 else LabelValue.NEGATIVE
                ),
                internal_only_violation_label=(
                    LabelValue.POSITIVE if index % 4 == 0 else LabelValue.NEGATIVE
                ),
                label_horizon=1,
                label_source="pilot_placeholder",
                label_confidence=0.5,
                split_group_ids={"task_id": task.task_id, "domain": str(task.domain)},
                source_artifact_hashes={"scenario": task.scenario_hash},
                synthetic=False,
            )
        )
    return examples


def _pilot_predictions(
    config: PilotExperimentConfig, examples: list[MonitorExample]
) -> list[MonitorPrediction]:
    if config.monitor_artifacts and config.monitor_artifacts[0].exists():
        return predict_examples(load_monitor_artifact(config.monitor_artifacts[0]), examples)
    return [
        MonitorPrediction(
            prediction_id=f"phase7_pred_{index}",
            monitor_name="constant_transfer_baseline",
            monitor_version="phase5_v1",
            model_artifact_hash="constant_transfer_placeholder",
            example_id=example.example_id,
            current_violation_probability=0.25 + 0.1 * (index % 3),
            imminent_violation_probability=0.25 + 0.1 * (index % 3),
            preventable_violation_probability=0.2,
            expected_severity=float(example.severity_target or 0.0),
            intervention_usefulness_probability=0.2,
            explanation="pilot transfer placeholder without retraining",
            ood_score=0.0,
        )
        for index, example in enumerate(examples)
    ]


def _placeholder_trajectory_rows(config: PilotExperimentConfig) -> list[dict[str, Any]]:
    return [
        {
            "trajectory_id": f"phase7_placeholder_{index}",
            "task_id": task.task_id,
            "domain": str(task.domain),
            "model_configuration": {"provider": "hidden_for_blind_export"},
            "steps": [
                {
                    "step_id": "step_1",
                    "role": "planner",
                    "kind": "planning",
                    "model_response": {"message": {"content": "redacted planner output"}},
                }
            ],
            "automated_scores": {"current_violation": "unknown"},
        }
        for index, task in enumerate(_selected_tasks(config))
    ]


def _workflow_quality_placeholder(config: PilotExperimentConfig, plan: PilotPlan) -> dict[str, Any]:
    return {
        "schema_version": PILOT_SCHEMA_VERSION,
        "artifact_version": PILOT_ARTIFACT_VERSION,
        "pilot_id": config.pilot_id,
        "planned_trajectories": plan.planned_trajectories,
        "flags": [
            "prompt_echo",
            "empty_delegation",
            "unused_child_result",
            "aggregator_ignores_worker",
            "trivial_delegation",
        ],
        "definitive_human_judgment": False,
    }


def _output_dir(config: PilotExperimentConfig) -> Path:
    return config.output_root / config.pilot_id


def _writable(path: Path) -> bool:
    path.mkdir(parents=True, exist_ok=True)
    marker = path / ".write_test"
    marker.write_text("ok", encoding="utf-8")
    marker.unlink()
    return True


def _working_tree_status() -> str:
    status = _git("status", "--porcelain")
    return "clean" if not status else "dirty"


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except Exception:
        return "unknown"
