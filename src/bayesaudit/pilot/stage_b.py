"""Phase 7 Stage B real-model workflow runner and review artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

from bayesaudit.architectures.common import add_usage
from bayesaudit.constraints.inheritance import (
    build_registry,
    create_envelope,
    envelope_to_snapshots,
)
from bayesaudit.constraints.snapshots import snapshot_constraints
from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.costs import (
    calculate_cost_accounting,
    cost_record_json,
    load_pricing_record,
    response_attempt_from_usage,
)
from bayesaudit.pilot.prompts import render_stage_b_prompt, stage_b1_repair_prompt
from bayesaudit.pilot.providers import (
    ProviderLedger,
    RequestCache,
    classify_provider_failure,
    execute_provider_or_cached,
    make_provider_request,
)
from bayesaudit.pilot.structured import (
    STAGE_B1_SCHEMA_VERSION,
    StageBRole,
    parse_stage_b1_role_output,
    parse_structured_output,
    stage_b1_response_schema_metadata,
)
from bayesaudit.pilot.types import (
    CostAccountingRecord,
    PilotExperimentConfig,
    PilotPlan,
    PilotProviderConfig,
)
from bayesaudit.pilot.workflow_quality import workflow_quality_flags
from bayesaudit.schemas import (
    ArchitectureKind,
    BehaviorCondition,
    BenchmarkTask,
    BudgetState,
    BudgetUnit,
    MessageRecord,
    ModelConfigRecord,
    ModelResponse,
    ScoreResult,
    ToolCallRecord,
    ToolExecutionStatus,
    Trajectory,
    TrajectoryStatus,
    TrajectoryStep,
    UsageTotals,
    WorkflowStepKind,
)
from bayesaudit.scoring.registry import scorer_for_task
from bayesaudit.storage.jsonl import append_jsonl, read_jsonl, write_json_atomic

StageBClassification = Literal[
    "valid",
    "valid_with_minor_issue",
    "invalid_model_workflow",
    "invalid_infrastructure",
    "excluded_provider_failure",
    "excluded_task_ambiguity",
]

STAGE_B_ARCHITECTURES = [
    ArchitectureKind.UNSTRUCTURED_DELEGATION,
    ArchitectureKind.STRUCTURED_INHERITANCE,
]
STAGE_B_DOMAIN_ORDER = ["privacy", "authorization", "evidence"]
STAGE_B_REQUESTS_PER_TRAJECTORY = 3
STAGE_B_REVIEW_ROOT = Path("data/derived/phase7_stage_b/review_packets")
STAGE_B2_REVIEW_ROOT = Path("data/derived/phase7_stage_b2/review_packets")
STAGE_B1_PILOT_ID = "phase7_workflow_openai_stage_b1_privacy"
STAGE_B2_PILOT_ID = "phase7_workflow_openai_stage_b2_auth_evidence"
STAGE_C1_PILOT_ID = "phase7_measurement_openai_stage_c1"
STAGE_B1_MAX_REPAIR_REQUESTS = 2
STAGE_B2_MAX_REPAIR_REQUESTS = 4
STAGE_C1_MAX_REPAIR_REQUESTS = 24
STAGE_B_NATIVE_CONTRACT_PILOT_IDS = {
    STAGE_B1_PILOT_ID,
    STAGE_B2_PILOT_ID,
    STAGE_C1_PILOT_ID,
}
STAGE_B_REAL_PILOT_IDS = {
    "phase7_workflow_openai_stage_b",
    STAGE_B1_PILOT_ID,
    STAGE_B2_PILOT_ID,
}


@dataclass(frozen=True)
class StageBStepResult:
    prompt: Any
    request_hash: str
    response: Any
    cached: bool
    parsed: Any
    raw_output_text: str
    parsed_payload: dict[str, Any]


class StageBProviderStepFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        role: str,
        request_hash: str,
        failure_record: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.role = role
        self.request_hash = request_hash
        self.failure_record = failure_record


def stage_b_request_plan(
    config: PilotExperimentConfig,
    provider: PilotProviderConfig,
    plan: PilotPlan,
) -> dict[str, Any]:
    trajectories = _trajectory_specs(config)
    max_repair_requests = _stage_b_max_repair_requests(config)
    maximum_possible_requests = (
        len(trajectories) * STAGE_B_REQUESTS_PER_TRAJECTORY * (1 + int(provider.max_retries))
        + max_repair_requests
    )
    normal_requests = len(trajectories) * STAGE_B_REQUESTS_PER_TRAJECTORY
    maximum_possible_input_tokens = (
        maximum_possible_requests * provider.estimated_input_tokens_per_request
    )
    maximum_possible_output_tokens = (
        maximum_possible_requests * provider.estimated_output_tokens_per_request
    )
    maximum_possible_cost = (
        maximum_possible_input_tokens / 1000.0 * provider.estimated_cost_per_1k_input_tokens
        + maximum_possible_output_tokens
        / 1000.0
        * provider.estimated_cost_per_1k_output_tokens
    )
    return {
        "pilot_id": config.pilot_id,
        "provider": provider.provider_name or provider.provider_class,
        "model_identifier": provider.model_identifier,
        "pricing_table_version": _pricing_table_version(provider),
        "task_ids": list(dict.fromkeys(str(spec["task_id"]) for spec in trajectories)),
        "domains": list(dict.fromkeys(str(spec["domain"]) for spec in trajectories)),
        "architectures": sorted({str(spec["architecture"]) for spec in trajectories}),
        "planned_trajectories": len(trajectories),
        "planner_requests_per_trajectory": 1,
        "worker_requests_per_trajectory": 1,
        "aggregator_requests_per_trajectory": 1,
        "verification_requests_per_trajectory": 0,
        "structured_output_repair_requests_per_trajectory": 0,
        "maximum_repair_requests": max_repair_requests,
        "expected_requests_per_trajectory": STAGE_B_REQUESTS_PER_TRAJECTORY,
        "expected_total_requests": normal_requests,
        "maximum_possible_requests": maximum_possible_requests,
        "max_retries": int(provider.max_retries),
        "estimated_input_tokens": plan.estimated_input_tokens,
        "estimated_output_tokens": plan.estimated_output_tokens,
        "estimated_total_tokens": plan.estimated_total_tokens,
        "estimated_token_derived_cost_usd": str(Decimal(str(plan.estimated_cost))),
        "conservative_upper_bound_usd": str(Decimal(str(plan.maximum_possible_cost))),
        "maximum_possible_input_tokens": maximum_possible_input_tokens,
        "maximum_possible_output_tokens": maximum_possible_output_tokens,
        "maximum_possible_total_tokens": maximum_possible_input_tokens
        + maximum_possible_output_tokens,
        "maximum_possible_token_derived_cost_usd": str(Decimal(str(maximum_possible_cost))),
        "prompt_template_versions": _stage_b_prompt_versions(config),
        "schema_versions": _stage_b_schema_versions(config),
        "storage_estimate_mb": plan.storage_estimate_mb,
        "request_rows": [
            {
                "trajectory_id": _trajectory_id(config, spec["task_id"], spec["architecture"]),
                "task_id": spec["task_id"],
                "domain": spec["domain"],
                "architecture": spec["architecture"],
                "planner_requests": 1,
                "worker_requests": 1,
                "aggregator_requests": 1,
                "verification_requests": 0,
                "structured_output_repair_requests": int(
                    max_repair_requests / max(len(trajectories), 1)
                )
                if _uses_stage_b_native_contract(config)
                else 0,
                "expected_request_count": STAGE_B_REQUESTS_PER_TRAJECTORY,
                "maximum_possible_request_count": STAGE_B_REQUESTS_PER_TRAJECTORY
                * (1 + int(provider.max_retries))
                + (1 if _uses_stage_b_native_contract(config) else 0),
            }
            for spec in trajectories
        ],
    }


def _is_stage_b1(config: PilotExperimentConfig) -> bool:
    return config.pilot_id == STAGE_B1_PILOT_ID


def _is_stage_b2(config: PilotExperimentConfig) -> bool:
    return config.pilot_id == STAGE_B2_PILOT_ID


def _is_stage_c1(config: PilotExperimentConfig) -> bool:
    return config.pilot_id == STAGE_C1_PILOT_ID


def _uses_stage_b_native_contract(config: PilotExperimentConfig) -> bool:
    return config.pilot_id in STAGE_B_NATIVE_CONTRACT_PILOT_IDS


def _stage_b_max_repair_requests(config: PilotExperimentConfig) -> int:
    if _is_stage_b1(config):
        return STAGE_B1_MAX_REPAIR_REQUESTS
    if _is_stage_b2(config):
        return STAGE_B2_MAX_REPAIR_REQUESTS
    if _is_stage_c1(config):
        return STAGE_C1_MAX_REPAIR_REQUESTS
    return 0


def _stage_b_prompt_versions(config: PilotExperimentConfig) -> dict[str, str]:
    if not _uses_stage_b_native_contract(config):
        return {
            "planner": "phase7_prompt_v1",
            "worker": "phase7_prompt_v1",
            "aggregator": "phase7_prompt_v1",
        }
    return {
        "planner": "phase7_prompt_v2",
        "worker": "phase7_prompt_v2",
        "aggregator": "phase7_prompt_v2",
    }


def _stage_b_schema_versions(config: PilotExperimentConfig) -> dict[str, str]:
    if not _uses_stage_b_native_contract(config):
        return {"shared": "PilotStructuredResponse"}
    return {
        "planner": STAGE_B1_SCHEMA_VERSION,
        "worker": STAGE_B1_SCHEMA_VERSION,
        "aggregator": STAGE_B1_SCHEMA_VERSION,
    }


def validate_stage_b_config(config: PilotExperimentConfig) -> dict[str, Any]:
    trajectories = _trajectory_specs(config)
    domains = sorted({str(spec["domain"]) for spec in trajectories})
    architectures = sorted({str(spec["architecture"]) for spec in trajectories})
    errors = []
    if _is_stage_b1(config):
        if len(trajectories) != 2:
            errors.append("Stage B.1 must contain exactly two privacy trajectories")
        if domains != ["privacy"]:
            errors.append("Stage B.1 must contain privacy only")
        if config.task_ids != ["task_privacy_aggregate_only"]:
            errors.append("Stage B.1 must use task_privacy_aggregate_only only")
        if architectures != sorted(arch.value for arch in STAGE_B_ARCHITECTURES):
            errors.append("Stage B.1 must contain unstructured and structured architectures")
    elif _is_stage_b2(config):
        if len(trajectories) != 4:
            errors.append("Stage B.2 must contain exactly four trajectories")
        if domains != ["authorization", "evidence"]:
            errors.append("Stage B.2 must contain authorization and evidence only")
        if config.task_ids != [
            "task_authorization_local_only",
            "task_evidence_claim_support",
        ]:
            errors.append("Stage B.2 must use authorization and evidence task IDs only")
        if architectures != sorted(arch.value for arch in STAGE_B_ARCHITECTURES):
            errors.append("Stage B.2 must contain unstructured and structured architectures")
    elif len(trajectories) != 6:
        errors.append("Stage B must contain exactly six trajectories")
    if (
        not _is_stage_b1(config)
        and not _is_stage_b2(config)
        and set(domains) != set(STAGE_B_DOMAIN_ORDER)
    ):
        errors.append("Stage B must contain privacy, authorization, and evidence domains")
    if architectures != sorted(arch.value for arch in STAGE_B_ARCHITECTURES):
        errors.append("Stage B must contain unstructured and structured architectures only")
    if config.delegation_depths != [1]:
        errors.append("Stage B depth must be exactly one")
    if config.branching_factors != [1]:
        errors.append("Stage B branching factor must be exactly one")
    if config.behavior_conditions != ["honest"]:
        errors.append("Stage B behavior must be honest only")
    if config.attacker_conditions != ["none"]:
        errors.append("Stage B must not use attackers")
    if config.oversight_conditions != ["none"]:
        errors.append("Stage B must not use oversight")
    if config.external_tools_enabled:
        errors.append("Stage B must disable external tools")
    return {"valid": not errors, "errors": errors, "trajectory_count": len(trajectories)}


def run_stage_b_domain_block(
    *,
    config: PilotExperimentConfig,
    provider: PilotProviderConfig,
    plan: PilotPlan,
    tasks: list[BenchmarkTask],
    output_dir: Path,
    domain_block: str,
    max_requests: int,
    max_tokens: int,
    max_cost: float,
    architecture_block: str | None = None,
) -> dict[str, Any]:
    if domain_block not in _stage_b_domain_order(config):
        raise ValueError(f"unknown Stage B domain block: {domain_block}")
    _assert_prior_domains_valid(output_dir, domain_block, config=config)
    tasks_by_id = {task.task_id: task for task in tasks}
    specs = [spec for spec in _trajectory_specs(config) if str(spec["domain"]) == domain_block]
    if architecture_block is not None:
        specs = [spec for spec in specs if str(spec["architecture"]) == architecture_block]
        if not specs:
            raise ValueError(f"unknown Stage B architecture block: {architecture_block}")
    cache = RequestCache(output_dir / "request_cache")
    ledger = ProviderLedger(output_dir / "provider_request_ledger.jsonl")
    attempted: list[dict[str, Any]] = []
    for spec in specs:
        trajectory_id = _trajectory_id(config, spec["task_id"], spec["architecture"])
        if _trajectory_exists(output_dir, trajectory_id):
            attempted.append({"trajectory_id": trajectory_id, "cached_skip": True})
            continue
        _assert_request_ceiling(output_dir, max_requests)
        task = tasks_by_id[str(spec["task_id"])]
        try:
            trajectory_payload = _run_one_trajectory(
                config=config,
                provider=provider,
                plan=plan,
                task=task,
                architecture=ArchitectureKind(str(spec["architecture"])),
                output_dir=output_dir,
                cache=cache,
                ledger=ledger,
                max_requests=max_requests,
            )
        except StageBProviderStepFailure as exc:
            trajectory_payload = _write_provider_failure_exclusion(
                output_dir=output_dir,
                config=config,
                task=task,
                architecture=ArchitectureKind(str(spec["architecture"])),
                failure=exc,
            )
        attempted.append(trajectory_payload)
        _assert_ceiling_reconciliation(
            output_dir,
            provider,
            max_requests=max_requests,
            max_tokens=max_tokens,
            max_cost=max_cost,
        )
    domain_summary = summarize_stage_b(config, provider, plan, output_dir)
    infrastructure_valid = (
        _domain_architecture_infrastructure_valid(output_dir, domain_block, architecture_block)
        if architecture_block is not None
        else _domain_infrastructure_valid(output_dir, domain_block)
    )
    domain_payload = {
        "domain": domain_block,
        "architecture_block": architecture_block,
        "attempted": attempted,
        "summary": domain_summary,
        "infrastructure_valid": infrastructure_valid,
    }
    append_jsonl(output_dir / "stage_b_domain_summaries.jsonl", domain_payload)
    write_json_atomic(output_dir / "stage_b_summary.json", domain_summary)
    if not domain_payload["infrastructure_valid"]:
        raise RuntimeError(f"Stage B infrastructure failed after {domain_block} block")
    return domain_payload


def summarize_stage_b(
    config: PilotExperimentConfig,
    provider: PilotProviderConfig,
    plan: PilotPlan,
    output_dir: Path,
) -> dict[str, Any]:
    trajectory_rows = read_jsonl(output_dir / "raw_trajectories.jsonl")
    classification_rows = read_jsonl(output_dir / "workflow_classifications.jsonl")
    quality_rows = read_jsonl(output_dir / "workflow_quality_records.jsonl")
    ledger_rows = read_jsonl(output_dir / "provider_request_ledger.jsonl")
    response_rows = read_jsonl(output_dir / "provider_responses.jsonl")
    failure_rows = read_jsonl(output_dir / "provider_failures.jsonl")
    completed_requests = [row for row in ledger_rows if row.get("status") == "completed"]
    cached_requests = [row for row in ledger_rows if row.get("status") == "cached"]
    attempts = [
        response_attempt_from_usage(row.get("provider_reported_usage", {}))
        for row in response_rows
        if isinstance(row.get("provider_reported_usage"), dict)
    ]
    cost_record = _aggregate_cost(provider, plan, attempts)
    classifications = [str(row.get("classification")) for row in classification_rows]
    valid_count = classifications.count("valid")
    minor_count = classifications.count("valid_with_minor_issue")
    status = stage_b_status(
        classification_rows,
        len(failure_rows),
        planned_trajectories=plan.planned_trajectories,
        stage_b1=_is_stage_b1(config),
    )
    return {
        "pilot_id": config.pilot_id,
        "stage_b_status": status,
        "provider": provider.provider_name or provider.provider_class,
        "model_identifier": provider.model_identifier,
        "pricing_table_version": cost_record.pricing_table_version,
        "planned_trajectories": plan.planned_trajectories,
        "attempted_trajectories": len(trajectory_rows) + len(failure_rows),
        "completed_trajectories": len(trajectory_rows),
        "valid_trajectories": valid_count,
        "valid_with_minor_issue_trajectories": minor_count,
        "invalid_model_workflow_trajectories": classifications.count("invalid_model_workflow"),
        "invalid_infrastructure_trajectories": classifications.count("invalid_infrastructure"),
        "exclusions": classifications.count("excluded_provider_failure")
        + classifications.count("excluded_task_ambiguity"),
        "planned_requests": plan.planned_requests,
        "actual_requests": len(completed_requests),
        "cached_executions": len(cached_requests),
        "failed_requests": len(failure_rows),
        "input_tokens": cost_record.input_tokens,
        "cached_input_tokens": cost_record.cached_input_tokens,
        "output_tokens": cost_record.output_tokens,
        "reasoning_tokens": cost_record.reasoning_tokens,
        "total_tokens": cost_record.input_tokens + cost_record.output_tokens,
        "estimated_cost_usd": str(Decimal(str(plan.estimated_cost))),
        "token_derived_cost_usd": str(cost_record.token_derived_cost_usd or Decimal("0")),
        "provider_reported_cost_usd": None,
        "billed_cost_usd": None,
        "cost_reconciliation_status": cost_record.cost_reconciliation_status,
        "cost_by_domain": _cost_breakdown(response_rows, "domain"),
        "cost_by_architecture": _cost_breakdown(response_rows, "architecture"),
        "meaningful_planner_count": sum(
            bool(row.get("meaningful_planner")) for row in classification_rows
        ),
        "meaningful_worker_count": sum(
            bool(row.get("meaningful_worker")) for row in classification_rows
        ),
        "narrower_subtask_count": sum(
            bool(row.get("worker_subtask_narrower")) for row in classification_rows
        ),
        "aggregator_used_worker_count": sum(
            bool(row.get("aggregator_used_worker")) for row in classification_rows
        ),
        "prompt_echo_count": _flag_count(quality_rows, "prompt_echo"),
        "empty_delegation_count": _flag_count(quality_rows, "empty_delegation"),
        "unused_worker_count": _flag_count(quality_rows, "worker_output_unused"),
        "scorable_output_count": sum(
            bool(row.get("final_output_scorable")) for row in classification_rows
        ),
        "structured_output_repair_count": sum(
            int(row.get("structured_output_repair_count", 0) or 0) for row in classification_rows
        ),
        "refusal_count": sum(int(row.get("refusal_count", 0) or 0) for row in classification_rows),
        "constraint_state_issues": sum(
            bool(row.get("constraint_state_issue")) for row in classification_rows
        ),
        "semantically_valid_trajectories": sum(
            row.get("workflow_semantic_status")
            in {"semantically_valid", "semantically_valid_with_minor_issue"}
            for row in classification_rows
        ),
        "native_valid_role_responses": sum(
            int(row.get("native_valid_role_responses", 0) or 0) for row in classification_rows
        ),
        "normalized_valid_role_responses": sum(
            int(row.get("normalized_valid_role_responses", 0) or 0)
            for row in classification_rows
        ),
        "repaired_valid_role_responses": sum(
            int(row.get("repaired_valid_role_responses", 0) or 0) for row in classification_rows
        ),
        "invalid_role_responses": sum(
            int(row.get("invalid_role_responses", 0) or 0) for row in classification_rows
        ),
        "workflow_classifications": classification_rows,
        "quality_flags": quality_rows,
    }


def stage_b_status(
    classification_rows: list[dict[str, Any]],
    provider_failures: int,
    *,
    planned_trajectories: int = 6,
    stage_b1: bool = False,
) -> str:
    classifications = [str(row.get("classification")) for row in classification_rows]
    documented_failures = classifications.count("excluded_provider_failure")
    undocumented_failures = max(provider_failures - documented_failures, 0)
    if len(classification_rows) + undocumented_failures < planned_trajectories:
        return "blocked"
    if "invalid_infrastructure" in classifications:
        return "failed"
    if stage_b1:
        if provider_failures:
            return "failed"
        if len(classification_rows) != 2:
            return "blocked"
        if not all(
            row.get("trajectory_execution_status") == "complete"
            for row in classification_rows
        ):
            return "failed"
        if not all(
            row.get("workflow_semantic_status")
            in {"semantically_valid", "semantically_valid_with_minor_issue"}
            for row in classification_rows
        ):
            return "failed"
        if not all(row.get("worker_subtask_narrower") for row in classification_rows):
            return "failed"
        if not all(row.get("final_output_scorable") for row in classification_rows):
            return "failed"
        native_valid_total = sum(
            int(row.get("native_valid_role_responses", 0) or 0)
            for row in classification_rows
        )
        if native_valid_total < 4:
            return "failed"
        repair_total = sum(
            int(row.get("structured_output_repair_count", 0) or 0)
            for row in classification_rows
        )
        if repair_total > STAGE_B1_MAX_REPAIR_REQUESTS:
            return "failed"
        if not all(
            row.get("aggregator_structured_output_status")
            in {"native_valid", "normalized_valid", "repaired_valid"}
            for row in classification_rows
        ):
            return "failed"
        return "passed"
    validish = classifications.count("valid") + classifications.count("valid_with_minor_issue")
    architectures = {str(row.get("architecture")) for row in classification_rows}
    architecture_valid = {
        architecture: any(
            row.get("architecture") == architecture
            and row.get("classification") in {"valid", "valid_with_minor_issue"}
            for row in classification_rows
        )
        for architecture in architectures
    }
    domains = {str(row.get("domain")) for row in classification_rows}
    domain_scorable = {
        domain: any(
            row.get("domain") == domain and row.get("final_output_scorable")
            for row in classification_rows
        )
        for domain in domains
    }
    if validish >= 4 and all(architecture_valid.values()) and all(domain_scorable.values()):
        return "passed"
    return "failed"


def combined_stage_b_status(
    classification_rows: list[dict[str, Any]],
    provider_failures: int,
    *,
    planned_trajectories: int = 6,
) -> str:
    """Evaluate the final Stage B pass criteria across B.1 and B.2 artifacts."""
    classifications = [str(row.get("classification")) for row in classification_rows]
    documented_failures = classifications.count("excluded_provider_failure")
    undocumented_failures = max(provider_failures - documented_failures, 0)
    if len(classification_rows) + undocumented_failures < planned_trajectories:
        return "blocked"
    if "invalid_infrastructure" in classifications:
        return "failed"

    validish_rows = [
        row
        for row in classification_rows
        if row.get("classification") in {"valid", "valid_with_minor_issue"}
        or row.get("workflow_semantic_status")
        in {"semantically_valid", "semantically_valid_with_minor_issue"}
    ]
    if len(validish_rows) < 4:
        return "failed"

    for domain in STAGE_B_DOMAIN_ORDER:
        domain_rows = [row for row in classification_rows if row.get("domain") == domain]
        if len(domain_rows) < 2:
            return "blocked"
        architectures = {str(row.get("architecture")) for row in domain_rows}
        if architectures != {arch.value for arch in STAGE_B_ARCHITECTURES}:
            return "blocked"
        if not any(
            row.get("trajectory_execution_status") == "complete"
            or row.get("classification") == "excluded_provider_failure"
            for row in domain_rows
        ):
            return "blocked"
        if not any(row in validish_rows for row in domain_rows):
            return "failed"
        if not any(row.get("final_output_scorable") for row in domain_rows):
            return "failed"
    return "passed"


def _run_one_trajectory(
    *,
    config: PilotExperimentConfig,
    provider: PilotProviderConfig,
    plan: PilotPlan,
    task: BenchmarkTask,
    architecture: ArchitectureKind,
    output_dir: Path,
    cache: RequestCache,
    ledger: ProviderLedger,
    max_requests: int,
) -> dict[str, Any]:
    del plan
    trajectory_id = _trajectory_id(config, task.task_id, architecture.value)
    run_id = trajectory_id.replace("traj_", "run_")
    root_step_id = f"{run_id}_step_001"
    worker_step_id = f"{run_id}_step_002"
    final_step_id = f"{run_id}_step_003"
    root_snapshots, worker_snapshots, final_snapshots, inheritance_metadata = _constraint_contexts(
        task=task,
        architecture=architecture,
        run_id=run_id,
        root_step_id=root_step_id,
        worker_step_id=worker_step_id,
        final_step_id=final_step_id,
    )
    planner = _call_stage_b_step(
        config=config,
        provider=provider,
        task=task,
        architecture=architecture,
        trajectory_id=trajectory_id,
        role="planner",
        depth=0,
        branch=None,
        output_dir=output_dir,
        cache=cache,
        ledger=ledger,
        max_requests=max_requests,
    )
    subtask = _proposed_subtask(planner.parsed_payload, task)
    worker_constraint_context = "\n".join(
        f"- {snapshot.constraint_id}: {snapshot.visible_rule}"
        for snapshot in worker_snapshots
        if snapshot.visible_rule
    )
    worker = _call_stage_b_step(
        config=config,
        provider=provider,
        task=task,
        architecture=architecture,
        trajectory_id=trajectory_id,
        role="worker",
        depth=1,
        branch="0",
        output_dir=output_dir,
        cache=cache,
        ledger=ledger,
        max_requests=max_requests,
        subtask=subtask,
        constraint_context=worker_constraint_context,
    )
    worker_output = _answer_text(worker.parsed_payload, worker.raw_output_text)
    aggregator = _call_stage_b_step(
        config=config,
        provider=provider,
        task=task,
        architecture=architecture,
        trajectory_id=trajectory_id,
        role="aggregator",
        depth=0,
        branch=None,
        output_dir=output_dir,
        cache=cache,
        ledger=ledger,
        max_requests=max_requests,
        subtask=subtask,
        worker_output=worker_output,
    )
    trajectory = _trajectory_from_steps(
        config=config,
        provider=provider,
        task=task,
        architecture=architecture,
        trajectory_id=trajectory_id,
        run_id=run_id,
        planner=planner,
        worker=worker,
        aggregator=aggregator,
        root_snapshots=root_snapshots,
        worker_snapshots=worker_snapshots,
        final_snapshots=final_snapshots,
        inheritance_metadata=inheritance_metadata,
        subtask=subtask,
    )
    score = scorer_for_task(task).score(task, trajectory)
    quality = workflow_quality_flags(trajectory)
    extra_flags = _extra_workflow_flags(trajectory, subtask, worker_output, quality.flags)
    if extra_flags:
        quality = quality.model_copy(update={"flags": sorted(set([*quality.flags, *extra_flags]))})
    classification = classify_stage_b_trajectory(
        trajectory=trajectory,
        score=score,
        parsed_records=[planner.parsed, worker.parsed, aggregator.parsed],
        quality_flags=quality.flags,
        architecture=architecture,
    )
    _write_trajectory_artifacts(
        output_dir=output_dir,
        trajectory=trajectory,
        score=score,
        quality=quality,
        classification=classification,
        stage_results=[planner, worker, aggregator],
        task=task,
    )
    return {
        "trajectory_id": trajectory.trajectory_id,
        "task_id": task.task_id,
        "domain": str(task.domain),
        "architecture": architecture.value,
        "classification": classification["classification"],
    }


def _call_stage_b_step(
    *,
    config: PilotExperimentConfig,
    provider: PilotProviderConfig,
    task: BenchmarkTask,
    architecture: ArchitectureKind,
    trajectory_id: str,
    role: str,
    depth: int,
    branch: str | None,
    output_dir: Path,
    cache: RequestCache,
    ledger: ProviderLedger,
    max_requests: int,
    subtask: str | None = None,
    worker_output: str | None = None,
    constraint_context: str | None = None,
) -> StageBStepResult:
    _assert_request_ceiling(output_dir, max_requests)
    is_stage_b_native = _uses_stage_b_native_contract(config)
    role_schema = (
        stage_b1_response_schema_metadata(cast(StageBRole, role)) if is_stage_b_native else {}
    )
    prompt = render_stage_b_prompt(
        task=task,
        architecture=architecture.value,
        agent_role=role,
        delegation_depth=depth,
        branch=branch,
        subtask=subtask,
        worker_output=worker_output,
        constraint_context=constraint_context,
        contract_version="stage_b1" if is_stage_b_native else "stage_b",
    )
    request = make_provider_request(
        provider,
        prompt_hash=prompt.prompt_hash,
        rendered_prompt=prompt.rendered_prompt,
        response_schema=role_schema,
    )
    write_json_atomic(
        output_dir / "prompt_records" / f"{request.request_id}_{role}.json",
        prompt.model_dump(mode="json"),
    )
    write_json_atomic(
        output_dir / "provider_request_records" / f"{request.request_id}.json",
        request.model_dump(mode="json"),
    )
    try:
        response, cached = execute_provider_or_cached(
            provider,
            request,
            rendered_prompt=prompt.rendered_prompt,
            cache=cache,
            ledger=ledger,
            raw_response_hook=lambda artifact: write_json_atomic(
                output_dir / "provider_raw_responses" / f"{request.request_hash}.json",
                artifact,
            ),
        )
    except Exception as exc:
        failure = classify_provider_failure(
            exc, provider=provider, request_hash=request.request_hash
        )
        failure_record = failure.model_dump(mode="json")
        append_jsonl(output_dir / "provider_failures.jsonl", failure_record)
        raw_failure_payload = getattr(exc, "payload", None)
        if isinstance(raw_failure_payload, dict) and raw_failure_payload:
            write_json_atomic(
                output_dir / "provider_failure_raw_responses" / f"{request.request_hash}.json",
                raw_failure_payload,
            )
        raise StageBProviderStepFailure(
            str(exc),
            role=role,
            request_hash=request.request_hash,
            failure_record=failure_record,
        ) from exc
    parsed = (
        parse_stage_b1_role_output(
            response.raw_output,
            role=cast(StageBRole, role),
            response_status=str(response.raw_provider_response.get("status") or ""),
            refusal_count=len(response.raw_provider_response.get("refusals", []) or []),
            incomplete_reason=str(response.raw_provider_response.get("incomplete_details") or ""),
        )
        if is_stage_b_native
        else parse_structured_output(response.raw_output, repair_limit=0)
    )
    row = response.model_dump(mode="json")
    row["task_id"] = task.task_id
    row["domain"] = str(task.domain)
    row["architecture"] = architecture.value
    row["agent_role"] = role
    row["trajectory_id"] = trajectory_id
    row["native_structured_output_valid"] = parsed.native_schema_valid
    row["structured_output_status"] = parsed.structured_output_status
    row["schema_name"] = parsed.schema_name
    row["role_schema_version"] = parsed.role_schema_version
    row["schema_hash"] = parsed.schema_hash
    append_jsonl(output_dir / "provider_responses.jsonl", row)
    write_json_atomic(
        output_dir / "provider_response_records" / f"{response.response_id}.json",
        row,
    )
    write_json_atomic(
        output_dir / "structured_records" / f"{request.request_id}_{role}.json",
        parsed.model_dump(mode="json"),
    )
    if is_stage_b_native and not parsed.valid:
        parsed = _maybe_repair_stage_b1_output(
            config=config,
            provider=provider,
            task=task,
            architecture=architecture,
            trajectory_id=trajectory_id,
            role=cast(StageBRole, role),
            output_dir=output_dir,
            cache=cache,
            ledger=ledger,
            max_requests=max_requests,
            original=parsed,
            response_schema=role_schema,
        )
        write_json_atomic(
            output_dir / "structured_records" / f"{request.request_id}_{role}.json",
            parsed.model_dump(mode="json"),
        )
    return StageBStepResult(
        prompt=prompt,
        request_hash=request.request_hash,
        response=response,
        cached=cached,
        parsed=parsed,
        raw_output_text=response.raw_output,
        parsed_payload=parsed.parsed_output,
    )


def _maybe_repair_stage_b1_output(
    *,
    config: PilotExperimentConfig,
    provider: PilotProviderConfig,
    task: BenchmarkTask,
    architecture: ArchitectureKind,
    trajectory_id: str,
    role: StageBRole,
    output_dir: Path,
    cache: RequestCache,
    ledger: ProviderLedger,
    max_requests: int,
    original: Any,
    response_schema: dict[str, Any],
) -> Any:
    if original.structured_output_status not in {
        "schema_invalid",
        "recoverable_nonconforming",
        "invalid_json",
    }:
        return original
    if _stage_b1_repair_count(output_dir, trajectory_id=trajectory_id) >= 1:
        return original
    if _stage_b1_repair_count(output_dir) >= _stage_b_max_repair_requests(config):
        return original
    _assert_request_ceiling(output_dir, max_requests)
    prompt = stage_b1_repair_prompt(
        role=role,
        raw_output=original.raw_output,
        schema_name=str(original.schema_name or response_schema.get("name") or ""),
        schema_version=str(original.role_schema_version or response_schema.get("version") or ""),
        schema=_schema_payload(response_schema),
    )
    request = make_provider_request(
        provider,
        prompt_hash=prompt.prompt_hash,
        rendered_prompt=prompt.rendered_prompt,
        response_schema=response_schema,
    )
    write_json_atomic(
        output_dir / "prompt_records" / f"{request.request_id}_{role}_repair.json",
        prompt.model_dump(mode="json"),
    )
    write_json_atomic(
        output_dir / "provider_request_records" / f"{request.request_id}.json",
        request.model_dump(mode="json"),
    )
    try:
        response, cached = execute_provider_or_cached(
            provider,
            request,
            rendered_prompt=prompt.rendered_prompt,
            cache=cache,
            ledger=ledger,
            raw_response_hook=lambda artifact: write_json_atomic(
                output_dir / "provider_raw_responses" / f"{request.request_hash}.json",
                artifact,
            ),
        )
    except Exception as exc:
        failure = classify_provider_failure(
            exc, provider=provider, request_hash=request.request_hash
        )
        failure_record = failure.model_dump(mode="json")
        append_jsonl(output_dir / "provider_failures.jsonl", failure_record)
        raw_failure_payload = getattr(exc, "payload", None)
        if isinstance(raw_failure_payload, dict) and raw_failure_payload:
            write_json_atomic(
                output_dir / "provider_failure_raw_responses" / f"{request.request_hash}.json",
                raw_failure_payload,
            )
        raise StageBProviderStepFailure(
            str(exc),
            role=f"{role}_repair",
            request_hash=request.request_hash,
            failure_record=failure_record,
        ) from exc
    repaired = parse_stage_b1_role_output(
        response.raw_output,
        role=role,
        response_status=str(response.raw_provider_response.get("status") or ""),
        refusal_count=len(response.raw_provider_response.get("refusals", []) or []),
        incomplete_reason=str(response.raw_provider_response.get("incomplete_details") or ""),
    )
    row = response.model_dump(mode="json")
    row["task_id"] = task.task_id
    row["domain"] = str(task.domain)
    row["architecture"] = architecture.value
    row["agent_role"] = f"{role}_repair"
    row["trajectory_id"] = trajectory_id
    row["native_structured_output_valid"] = repaired.native_schema_valid
    row["structured_output_status"] = repaired.structured_output_status
    row["schema_name"] = repaired.schema_name
    row["role_schema_version"] = repaired.role_schema_version
    row["schema_hash"] = repaired.schema_hash
    append_jsonl(output_dir / "provider_responses.jsonl", row)
    write_json_atomic(
        output_dir / "provider_response_records" / f"{response.response_id}.json",
        row,
    )
    repair_record = {
        "trajectory_id": trajectory_id,
        "role": role,
        "request_hash": request.request_hash,
        "prompt_hash": prompt.prompt_hash,
        "cached": cached,
        "original_output_id": original.output_id,
        "repaired_output_id": repaired.output_id,
        "repaired_valid": repaired.valid,
        "schema_name": repaired.schema_name,
        "role_schema_version": repaired.role_schema_version,
        "schema_hash": repaired.schema_hash,
    }
    append_jsonl(output_dir / "structured_repair_records.jsonl", repair_record)
    write_json_atomic(
        output_dir / "structured_repair_records" / f"{request.request_id}_{role}.json",
        {
            "repair": repair_record,
            "structured_output": repaired.model_dump(mode="json"),
        },
    )
    if not repaired.valid:
        return original.model_copy(
            update={
                "repair_attempts": 1,
                "repair_prompt_hashes": [prompt.prompt_hash],
                "repaired_output": response.raw_output,
                "repaired_valid": False,
            }
        )
    return original.model_copy(
        update={
            "parsed_output": repaired.parsed_output,
            "repair_attempts": 1,
            "repair_prompt_hashes": [prompt.prompt_hash],
            "repaired_output": response.raw_output,
            "repaired_valid": True,
            "valid": True,
            "structured_output_status": "repaired_valid",
        }
    )


def _stage_b1_repair_count(output_dir: Path, *, trajectory_id: str | None = None) -> int:
    rows = read_jsonl(output_dir / "structured_repair_records.jsonl")
    if trajectory_id is None:
        return len(rows)
    return sum(row.get("trajectory_id") == trajectory_id for row in rows)


def _schema_payload(response_schema: dict[str, Any]) -> dict[str, Any]:
    schema = response_schema.get("schema")
    return schema if isinstance(schema, dict) else {}


def _trajectory_from_steps(
    *,
    config: PilotExperimentConfig,
    provider: PilotProviderConfig,
    task: BenchmarkTask,
    architecture: ArchitectureKind,
    trajectory_id: str,
    run_id: str,
    planner: StageBStepResult,
    worker: StageBStepResult,
    aggregator: StageBStepResult,
    root_snapshots: list[Any],
    worker_snapshots: list[Any],
    final_snapshots: list[Any],
    inheritance_metadata: dict[str, Any],
    subtask: str,
) -> Trajectory:
    final_text = _answer_text(aggregator.parsed_payload, aggregator.raw_output_text)
    worker_output = _answer_text(worker.parsed_payload, worker.raw_output_text)
    steps = [
        TrajectoryStep(
            step_id=f"{run_id}_step_001",
            sequence_index=1,
            agent_id="planner",
            role="planner",
            depth=0,
            kind=WorkflowStepKind.PLANNING,
            input_messages=[
                MessageRecord(
                    role="user", content=planner.prompt.rendered_prompt, agent_id="planner"
                )
            ],
            model_response=_model_response(provider, planner, "planner"),
            constraint_snapshots=root_snapshots,
            metadata={
                "prompt_hash": planner.prompt.prompt_hash,
                "request_hash": planner.request_hash,
                "proposed_subtask": subtask,
            },
        ),
        TrajectoryStep(
            step_id=f"{run_id}_step_002",
            sequence_index=2,
            parent_step_id=f"{run_id}_step_001",
            delegation_id=f"{run_id}_delegation_001",
            branch_id="0",
            agent_id="worker_d1_b0",
            parent_agent_id="planner",
            role="worker",
            depth=1,
            kind=WorkflowStepKind.DELEGATION,
            input_messages=[
                MessageRecord(
                    role="user", content=worker.prompt.rendered_prompt, agent_id="worker_d1_b0"
                )
            ],
            model_response=_model_response(provider, worker, "worker"),
            constraint_snapshots=worker_snapshots,
            tool_calls=_tool_calls(worker.parsed_payload, task, run_id),
            metadata={
                "prompt_hash": worker.prompt.prompt_hash,
                "request_hash": worker.request_hash,
                "delegated_subtask": subtask,
                "architecture_constraint_context": architecture.value,
            },
        ),
        TrajectoryStep(
            step_id=f"{run_id}_step_003",
            sequence_index=3,
            parent_step_id=f"{run_id}_step_001",
            agent_id="planner",
            role="planner",
            depth=0,
            kind=WorkflowStepKind.FINAL_OUTPUT,
            input_messages=[
                MessageRecord(
                    role="user",
                    content=f"Worker output for aggregation:\n{worker_output}",
                    agent_id="planner",
                )
            ],
            model_response=_model_response(provider, aggregator, "aggregator", content=final_text),
            constraint_snapshots=final_snapshots,
            metadata={
                "prompt_hash": aggregator.prompt.prompt_hash,
                "request_hash": aggregator.request_hash,
                "worker_step_id": f"{run_id}_step_002",
            },
        ),
    ]
    trajectory = Trajectory(
        trajectory_id=trajectory_id,
        task_id=task.task_id,
        task_version=task.task_version,
        scenario_hash=task.scenario_hash,
        experiment_id=config.pilot_id,
        run_id=run_id,
        architecture=architecture,
        behavior_condition=BehaviorCondition.HONEST,
        model_configuration=ModelConfigRecord(
            provider=provider.provider_name or provider.provider_class,
            model_id=provider.model_identifier or "unknown",
            model_version="phase7_stage_b",
            behavior_profile="honest",
            raw_config={
                "sampling_parameters": provider.sampling_parameters,
                "pricing_table_version": _pricing_table_version(provider),
            },
        ),
        oversight_policy="none",
        oversight_budget=BudgetState(
            initial_budget=0.0,
            remaining_budget=0.0,
            consumed_budget=0.0,
            budget_unit=BudgetUnit.AUDIT_COUNT,
        ),
        seed=config.seeds[0] if config.seeds else task.seed,
        status=TrajectoryStatus.COMPLETED,
        git_commit=_git_commit(),
        configuration_hash=canonical_json_hash(
            {
                "pilot_id": config.pilot_id,
                "task_id": task.task_id,
                "architecture": architecture.value,
                "model": provider.model_identifier,
            }
        ),
        prompt_version="phase7_prompt_v1",
        steps=steps,
        metadata={
            "synthetic": False,
            "stage": "phase7_stage_b",
            "domain": str(task.domain),
            "inheritance": inheritance_metadata,
            "provider_request_hashes": [
                planner.request_hash,
                worker.request_hash,
                aggregator.request_hash,
            ],
        },
    )
    add_usage(trajectory)
    trajectory.usage_totals = UsageTotals(
        input_tokens=sum(result.response.input_tokens for result in [planner, worker, aggregator]),
        output_tokens=sum(
            result.response.output_tokens for result in [planner, worker, aggregator]
        ),
        total_tokens=sum(result.response.total_tokens for result in [planner, worker, aggregator]),
        estimated_cost=0.0,
    )
    return Trajectory.model_validate(trajectory.model_dump())


def classify_stage_b_trajectory(
    *,
    trajectory: Trajectory,
    score: ScoreResult,
    parsed_records: list[Any],
    quality_flags: list[str],
    architecture: ArchitectureKind,
) -> dict[str, Any]:
    planner = trajectory.steps[0]
    worker = trajectory.steps[1]
    aggregator = trajectory.steps[2]
    subtask = str(planner.metadata.get("proposed_subtask") or "")
    worker_output = worker.model_response.message.content if worker.model_response else ""
    final_output = aggregator.model_response.message.content if aggregator.model_response else ""
    meaningful_planner = (
        bool(subtask.strip())
        and subtask.strip() != trajectory.steps[0].input_messages[0].content.strip()
    )
    meaningful_worker = bool(worker_output.strip()) and worker_output.strip() != subtask.strip()
    narrower = _subtask_is_narrower(subtask, trajectory.steps[0].input_messages[0].content)
    aggregator_used = _text_overlap(final_output, worker_output)
    parsed_valid = all(record.valid for record in parsed_records)
    constraint_state_issue = (
        architecture == ArchitectureKind.STRUCTURED_INHERITANCE
        and not trajectory.metadata.get("inheritance", {}).get("envelopes")
    )
    final_scorable = bool(final_output.strip()) and score.scoring_status != "error"
    semantic_valid = (
        meaningful_planner
        and meaningful_worker
        and aggregator_used
        and final_scorable
    )
    native_valid_count = sum(
        bool(getattr(record, "native_schema_valid", False)) for record in parsed_records
    )
    normalized_valid_count = sum(
        bool(getattr(record, "normalized_schema_valid", False)) for record in parsed_records
    )
    repaired_valid_count = sum(
        bool(getattr(record, "repaired_valid", False)) for record in parsed_records
    )
    invalid_role_count = len(parsed_records) - sum(bool(record.valid) for record in parsed_records)
    structured_statuses = [
        str(getattr(record, "structured_output_status", "unknown")) for record in parsed_records
    ]
    workflow_semantic_status = (
        "semantically_valid_with_minor_issue"
        if semantic_valid and quality_flags
        else "semantically_valid"
        if semantic_valid
        else "semantically_invalid"
    )
    trajectory_execution_status = (
        "infrastructure_failed"
        if constraint_state_issue
        else "incomplete"
        if any(step.model_response is None for step in trajectory.steps)
        else "complete"
    )
    classification: StageBClassification = "valid"
    reasons: list[str] = []
    if (
        constraint_state_issue
        or not trajectory.steps
        or any(step.model_response is None for step in trajectory.steps)
    ):
        classification = "invalid_infrastructure"
        reasons.append("missing required infrastructure artifact")
    elif not parsed_valid:
        classification = "invalid_model_workflow"
        reasons.append("structured output contract not satisfied")
    elif not semantic_valid:
        classification = "invalid_model_workflow"
        reasons.append("workflow semantics failed")
    elif quality_flags:
        classification = "valid_with_minor_issue"
        reasons.append("heuristic workflow flags present")
    return {
        "trajectory_id": trajectory.trajectory_id,
        "task_id": trajectory.task_id,
        "domain": str(trajectory.metadata.get("domain")),
        "architecture": architecture.value,
        "classification": classification,
        "primary_reason": reasons[0] if reasons else "workflow executed and was scorable",
        "secondary_reasons": reasons[1:],
        "delegation_meaningful": meaningful_planner,
        "worker_subtask_narrower": narrower,
        "aggregator_used_worker": aggregator_used,
        "constraints_delivered_correctly": not constraint_state_issue,
        "final_output_scorable": final_scorable,
        "repair_recommended": classification == "invalid_infrastructure",
        "rerun_would_change_comparability": classification == "invalid_infrastructure",
        "meaningful_planner": meaningful_planner,
        "meaningful_worker": meaningful_worker,
        "structured_output_repair_count": sum(
            int(record.repair_attempts) for record in parsed_records
        ),
        "refusal_count": 0,
        "constraint_state_issue": constraint_state_issue,
        "workflow_flags": quality_flags,
        "workflow_semantic_status": workflow_semantic_status,
        "structured_output_statuses": structured_statuses,
        "structured_output_status": "native_valid"
        if native_valid_count == len(parsed_records)
        else "repaired_valid"
        if parsed_valid and repaired_valid_count
        else "normalized_valid"
        if parsed_valid and normalized_valid_count
        else "schema_invalid"
        if not parsed_valid
        else "unknown",
        "trajectory_execution_status": trajectory_execution_status,
        "scorer_available": score.scoring_status != "error",
        "native_valid_role_responses": native_valid_count,
        "normalized_valid_role_responses": normalized_valid_count,
        "repaired_valid_role_responses": repaired_valid_count,
        "invalid_role_responses": invalid_role_count,
        "planner_structured_output_status": structured_statuses[0]
        if len(structured_statuses) > 0
        else "unknown",
        "worker_structured_output_status": structured_statuses[1]
        if len(structured_statuses) > 1
        else "unknown",
        "aggregator_structured_output_status": structured_statuses[2]
        if len(structured_statuses) > 2
        else "unknown",
    }


def _write_trajectory_artifacts(
    *,
    output_dir: Path,
    trajectory: Trajectory,
    score: ScoreResult,
    quality: Any,
    classification: dict[str, Any],
    stage_results: list[StageBStepResult],
    task: BenchmarkTask,
) -> None:
    append_jsonl(output_dir / "raw_trajectories.jsonl", trajectory.model_dump(mode="json"))
    append_jsonl(output_dir / "scores.jsonl", score.model_dump(mode="json"))
    append_jsonl(output_dir / "workflow_quality_records.jsonl", quality.model_dump(mode="json"))
    append_jsonl(output_dir / "workflow_classifications.jsonl", classification)
    review_packet = _review_packet(
        trajectory=trajectory,
        score=score,
        quality_flags=quality.flags,
        classification=classification,
        stage_results=stage_results,
        task=task,
    )
    review_path = _review_packet_path(trajectory.trajectory_id)
    write_json_atomic(review_path, review_packet)
    write_json_atomic(
        output_dir / "review_packet_index" / f"{trajectory.trajectory_id}.json",
        {"review_packet_path": str(review_path), "trajectory_id": trajectory.trajectory_id},
    )


def _write_provider_failure_exclusion(
    *,
    output_dir: Path,
    config: PilotExperimentConfig,
    task: BenchmarkTask,
    architecture: ArchitectureKind,
    failure: StageBProviderStepFailure,
) -> dict[str, Any]:
    trajectory_id = _trajectory_id(config, task.task_id, architecture.value)
    classification = {
        "trajectory_id": trajectory_id,
        "task_id": task.task_id,
        "domain": str(task.domain),
        "architecture": architecture.value,
        "classification": "excluded_provider_failure",
        "primary_reason": f"provider request failed during {failure.role}",
        "secondary_reasons": [failure.failure_record.get("failure_type", "provider_failure")],
        "meaningful_planner": False,
        "meaningful_worker": False,
        "delegation_meaningful": False,
        "worker_subtask_narrower": False,
        "aggregator_used_worker": False,
        "constraints_delivered_correctly": False,
        "constraint_state_issue": False,
        "final_output_scorable": False,
        "structured_output_repair_count": 0,
        "refusal_count": 0,
        "repair_recommended": False,
        "rerun_would_change_comparability": True,
        "provider_failure": failure.failure_record,
    }
    quality = {
        "trajectory_id": trajectory_id,
        "task_id": task.task_id,
        "domain": str(task.domain),
        "architecture": architecture.value,
        "flags": ["provider_failure_exclusion", "incomplete_trajectory"],
    }
    append_jsonl(output_dir / "workflow_quality_records.jsonl", quality)
    append_jsonl(output_dir / "workflow_classifications.jsonl", classification)
    review_packet = {
        "packet_label": "developer workflow inspection packet",
        "trajectory_id": trajectory_id,
        "task_id": task.task_id,
        "domain": str(task.domain),
        "architecture": architecture.value,
        "planner_prompt_summary": "",
        "planner_output": "",
        "delegated_subtask": "",
        "worker_visible_constraints": [],
        "worker_output": "",
        "aggregator_visible_inputs": "",
        "final_output": "",
        "constraint_snapshots": [],
        "workflow_quality_flags": quality["flags"],
        "scorer_result": {},
        "token_usage": {},
        "cost": {},
        "failures": [failure.failure_record],
        "suggested_workflow_classification": classification,
    }
    review_path = _review_packet_path(trajectory_id)
    write_json_atomic(review_path, review_packet)
    write_json_atomic(
        output_dir / "review_packet_index" / f"{trajectory_id}.json",
        {"review_packet_path": str(review_path), "trajectory_id": trajectory_id},
    )
    return {
        "trajectory_id": trajectory_id,
        "task_id": task.task_id,
        "domain": str(task.domain),
        "architecture": architecture.value,
        "classification": "excluded_provider_failure",
        "failed_role": failure.role,
    }


def _review_packet(
    *,
    trajectory: Trajectory,
    score: ScoreResult,
    quality_flags: list[str],
    classification: dict[str, Any],
    stage_results: list[StageBStepResult],
    task: BenchmarkTask,
) -> dict[str, Any]:
    planner, worker, aggregator = trajectory.steps
    return {
        "packet_label": "developer workflow inspection packet",
        "trajectory_id": trajectory.trajectory_id,
        "task_id": task.task_id,
        "domain": str(task.domain),
        "architecture": str(trajectory.architecture),
        "planner_prompt_summary": _summarize_prompt(planner.input_messages[0].content),
        "planner_output": planner.model_response.message.content if planner.model_response else "",
        "delegated_subtask": planner.metadata.get("proposed_subtask"),
        "worker_visible_constraints": [
            snapshot.model_dump(mode="json") for snapshot in worker.constraint_snapshots
        ],
        "worker_output": worker.model_response.message.content if worker.model_response else "",
        "aggregator_visible_inputs": aggregator.input_messages[0].content,
        "final_output": aggregator.model_response.message.content
        if aggregator.model_response
        else "",
        "constraint_snapshots": [
            [snapshot.model_dump(mode="json") for snapshot in step.constraint_snapshots]
            for step in trajectory.steps
        ],
        "workflow_quality_flags": quality_flags,
        "scorer_result": score.model_dump(mode="json"),
        "token_usage": trajectory.usage_totals.model_dump(mode="json"),
        "cost": _trajectory_cost(stage_results) if stage_results else {},
        "failures": [],
        "suggested_workflow_classification": classification,
    }


def _constraint_contexts(
    *,
    task: BenchmarkTask,
    architecture: ArchitectureKind,
    run_id: str,
    root_step_id: str,
    worker_step_id: str,
    final_step_id: str,
) -> tuple[list[Any], list[Any], list[Any], dict[str, Any]]:
    if architecture == ArchitectureKind.STRUCTURED_INHERITANCE:
        registry = build_registry(task, creation_step=root_step_id)
        root_envelope = create_envelope(
            registry,
            envelope_id=f"{run_id}_env_root",
            sender_agent_id="system",
            recipient_agent_id="planner",
            created_step_id=root_step_id,
        )
        worker_envelope = create_envelope(
            registry,
            envelope_id=f"{run_id}_env_worker",
            sender_agent_id="planner",
            recipient_agent_id="worker_d1_b0",
            created_step_id=worker_step_id,
            parent_envelope_id=root_envelope.envelope_id,
            delegation_id=f"{run_id}_delegation_001",
            branch_id="0",
        )
        final_envelope = create_envelope(
            registry,
            envelope_id=f"{run_id}_env_aggregator",
            sender_agent_id="worker_d1_b0",
            recipient_agent_id="planner",
            created_step_id=final_step_id,
            parent_envelope_id=worker_envelope.envelope_id,
        )
        return (
            envelope_to_snapshots(
                root_envelope, registry, current_source_level=0, inherited_from_step_id=None
            ),
            envelope_to_snapshots(
                worker_envelope,
                registry,
                current_source_level=1,
                inherited_from_step_id=root_step_id,
            ),
            envelope_to_snapshots(
                final_envelope,
                registry,
                current_source_level=0,
                inherited_from_step_id=root_step_id,
            ),
            {
                "registry": registry.model_dump(mode="json"),
                "envelopes": [
                    root_envelope.model_dump(mode="json"),
                    worker_envelope.model_dump(mode="json"),
                    final_envelope.model_dump(mode="json"),
                ],
                "aggregation_provenance": {
                    "step_id": final_step_id,
                    "child_step_ids": [worker_step_id],
                    "branch_ids": ["0"],
                    "envelope_ids": [worker_envelope.envelope_id],
                    "envelope_versions": [worker_envelope.envelope_version],
                    "used_current_canonical_state": True,
                    "stale_envelope_ids": [],
                },
            },
        )
    root = snapshot_constraints(
        task.constraints, current_source_level=0, inherited_from_step_id=None
    )
    worker = snapshot_constraints(
        task.constraints, current_source_level=1, inherited_from_step_id=root_step_id
    )
    final = snapshot_constraints(
        task.constraints, current_source_level=0, inherited_from_step_id=root_step_id
    )
    return (
        root,
        worker,
        final,
        {"note": "unstructured delegation has no typed envelopes", "envelopes": []},
    )


def _model_response(
    provider: PilotProviderConfig,
    result: StageBStepResult,
    agent_id: str,
    *,
    content: str | None = None,
) -> ModelResponse:
    return ModelResponse(
        message=MessageRecord(
            role="assistant",
            content=content if content is not None else result.response.raw_output,
            agent_id=agent_id,
        ),
        provider=provider.provider_name or provider.provider_class,
        model_id=provider.model_identifier or "unknown",
        model_version="phase7_stage_b",
        finish_reason=result.response.finish_reason or "unknown",
        input_tokens=result.response.input_tokens,
        output_tokens=result.response.output_tokens,
        total_tokens=result.response.total_tokens,
        estimated_cost=0.0,
        request_id=result.response.provider_request_id or result.response.response_id,
        raw_metadata={
            "request_hash": result.request_hash,
            "provider_reported_usage": result.response.provider_reported_usage,
            "parsed_output": result.parsed_payload,
        },
    )


def _tool_calls(payload: dict[str, Any], task: BenchmarkTask, run_id: str) -> list[ToolCallRecord]:
    calls = []
    raw_requests = payload.get("tool_requests", [])
    if not isinstance(raw_requests, list):
        return []
    for index, request in enumerate(raw_requests, start=1):
        if not isinstance(request, dict):
            continue
        tool_name = str(request.get("tool_name") or request.get("name") or "")
        if not tool_name:
            continue
        prohibited = tool_name in task.prohibited_tools
        calls.append(
            ToolCallRecord(
                tool_call_id=f"{run_id}_tool_{index}",
                tool_name=tool_name,
                arguments=request.get("arguments")
                if isinstance(request.get("arguments"), dict)
                else {},
                requested_by_agent="worker_d1_b0",
                approval_required=prohibited,
                authorization_basis="stage_b_inert_record_only",
                environment_authorized=not prohibited and tool_name in task.authorized_tools,
                execution_status=ToolExecutionStatus.BLOCKED
                if prohibited
                else ToolExecutionStatus.REQUESTED,
                result_summary="recorded only; Stage B did not execute tools",
            )
        )
    return calls


def _aggregate_cost(
    provider: PilotProviderConfig,
    plan: PilotPlan,
    attempts: list[Any],
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
        attempts=attempts,
        pricing=pricing,
        estimated_cost_usd=Decimal(str(plan.estimated_cost)),
        conservative_upper_bound_usd=Decimal(str(plan.maximum_possible_cost)),
    )


def _trajectory_cost(stage_results: list[StageBStepResult]) -> dict[str, Any]:
    attempts = [
        response_attempt_from_usage(result.response.provider_reported_usage)
        for result in stage_results
    ]
    provider = stage_results[0].response.raw_provider_response.get("provider", "openai")
    model = stage_results[0].response.raw_provider_response.get("model_identifier", "")
    pricing = load_pricing_record(str(provider), str(model)) if model else None
    record = calculate_cost_accounting(
        provider=str(provider),
        model_identifier=str(model),
        attempts=attempts,
        pricing=pricing,
    )
    return cost_record_json(record)


def _cost_breakdown(response_rows: list[dict[str, Any]], key: str) -> dict[str, str]:
    grouped: dict[str, list[Any]] = {}
    for row in response_rows:
        group = str(row.get(key) or "unknown")
        usage = row.get("provider_reported_usage", {})
        if isinstance(usage, dict):
            grouped.setdefault(group, []).append(response_attempt_from_usage(usage))
    output = {}
    for group, attempts in grouped.items():
        provider = str(response_rows[0].get("raw_provider_response", {}).get("provider", "openai"))
        model = str(response_rows[0].get("raw_provider_response", {}).get("model_identifier", ""))
        pricing = load_pricing_record(provider, model) if model else None
        record = calculate_cost_accounting(
            provider=provider,
            model_identifier=model,
            attempts=attempts,
            pricing=pricing,
        )
        output[group] = str(record.token_derived_cost_usd or Decimal("0"))
    return output


def _trajectory_specs(config: PilotExperimentConfig) -> list[dict[str, Any]]:
    specs = []
    for task_id in config.task_ids:
        domain = _task_domain_from_id(task_id)
        for architecture in config.architectures:
            specs.append(
                {
                    "task_id": task_id,
                    "domain": domain,
                    "architecture": str(architecture),
                }
            )
    architecture_order = {
        str(architecture): index for index, architecture in enumerate(config.architectures)
    }
    specs.sort(
        key=lambda row: (
            STAGE_B_DOMAIN_ORDER.index(str(row["domain"])),
            architecture_order.get(str(row["architecture"]), 999),
        )
    )
    return specs


def _stage_b_domain_order(config: PilotExperimentConfig | None = None) -> list[str]:
    if config is not None and _is_stage_b2(config):
        return ["authorization", "evidence"]
    return STAGE_B_DOMAIN_ORDER


def _task_domain_from_id(task_id: str) -> str:
    if task_id.startswith("task_privacy_"):
        return "privacy"
    if task_id.startswith("task_authorization_"):
        return "authorization"
    if task_id.startswith("task_evidence_"):
        return "evidence"
    return "unknown"


def _trajectory_id(config: PilotExperimentConfig, task_id: str, architecture: str) -> str:
    return f"traj_{config.pilot_id}_{task_id}_{architecture}"


def _proposed_subtask(payload: dict[str, Any], task: BenchmarkTask) -> str:
    proposed = payload.get("proposed_subtask") or payload.get("subtask")
    if isinstance(proposed, str) and proposed.strip():
        return proposed.strip()
    objective = payload.get("objective")
    if isinstance(objective, str) and objective.strip():
        return objective.strip()
    return f"Perform the domain-specific evidence/calculation work needed for {task.task_id}."


def _answer_text(payload: dict[str, Any], fallback: str) -> str:
    for key in ("final_answer", "result", "expected_output", "worker_instructions"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback.strip()


def _subtask_is_narrower(subtask: str, original: str) -> bool:
    return bool(subtask.strip()) and len(subtask.split()) < max(len(original.split()), 1) * 0.9


def _text_overlap(left: str, right: str) -> bool:
    left_words = {word.lower().strip(".,:;{}[]()\"'") for word in left.split() if len(word) > 3}
    right_words = {word.lower().strip(".,:;{}[]()\"'") for word in right.split() if len(word) > 3}
    return len(left_words.intersection(right_words)) >= 2


def _extra_workflow_flags(
    trajectory: Trajectory,
    subtask: str,
    worker_output: str,
    current_flags: list[str],
) -> list[str]:
    del current_flags
    flags = []
    worker = trajectory.steps[1]
    final = trajectory.steps[2]
    if not subtask.strip():
        flags.append("empty_delegation")
    if (
        worker.model_response
        and worker.input_messages
        and worker.input_messages[0].content[:80] in worker.model_response.message.content
    ):
        flags.append("worker_repeats_original_task")
    if final.model_response and not _text_overlap(
        final.model_response.message.content, worker_output
    ):
        flags.append("worker_output_unused")
    if (
        not worker.constraint_snapshots
        and trajectory.architecture == ArchitectureKind.STRUCTURED_INHERITANCE
    ):
        flags.append("missing_constraint_state")
    return flags


def _flag_count(rows: list[dict[str, Any]], flag: str) -> int:
    return sum(flag in row.get("flags", []) for row in rows if isinstance(row.get("flags"), list))


def _domain_infrastructure_valid(output_dir: Path, domain: str) -> bool:
    rows = read_jsonl(output_dir / "workflow_classifications.jsonl")
    domain_rows = [row for row in rows if row.get("domain") == domain]
    return len(domain_rows) == 2 and not any(
        row.get("classification") == "invalid_infrastructure" for row in domain_rows
    )


def _domain_architecture_infrastructure_valid(
    output_dir: Path, domain: str, architecture: str | None
) -> bool:
    rows = read_jsonl(output_dir / "workflow_classifications.jsonl")
    domain_rows = [
        row
        for row in rows
        if row.get("domain") == domain and row.get("architecture") == architecture
    ]
    return len(domain_rows) == 1 and not any(
        row.get("classification") == "invalid_infrastructure" for row in domain_rows
    )


def _assert_prior_domains_valid(
    output_dir: Path,
    domain_block: str,
    *,
    config: PilotExperimentConfig | None = None,
) -> None:
    domain_order = _stage_b_domain_order(config)
    index = domain_order.index(domain_block)
    for prior in domain_order[:index]:
        if not _domain_infrastructure_valid(output_dir, prior):
            raise RuntimeError(f"prior Stage B domain block is not infrastructure-valid: {prior}")


def _assert_request_ceiling(output_dir: Path, max_requests: int) -> None:
    ledger_rows = read_jsonl(output_dir / "provider_request_ledger.jsonl")
    actual = sum(1 for row in ledger_rows if row.get("status") == "completed")
    if actual >= max_requests:
        raise RuntimeError("Stage B request ceiling would be exceeded")


def _assert_ceiling_reconciliation(
    output_dir: Path,
    provider: PilotProviderConfig,
    *,
    max_requests: int,
    max_tokens: int,
    max_cost: float,
) -> None:
    ledger_rows = read_jsonl(output_dir / "provider_request_ledger.jsonl")
    actual = sum(1 for row in ledger_rows if row.get("status") == "completed")
    if actual > max_requests:
        raise RuntimeError("Stage B request ceiling exceeded")
    response_rows = read_jsonl(output_dir / "provider_responses.jsonl")
    attempts = [
        response_attempt_from_usage(row.get("provider_reported_usage", {}))
        for row in response_rows
        if isinstance(row.get("provider_reported_usage"), dict)
    ]
    dummy_plan = PilotPlan(
        pilot_id="stage_b_ceiling",
        stage="workflow",
        provider=provider.provider_name,
        model_identifier=provider.model_identifier,
        task_count=0,
        architecture_count=0,
        depth_count=0,
        behavior_count=0,
        attacker_count=0,
        policy_count=0,
        seed_count=0,
        planned_trajectories=0,
        planned_requests=0,
        estimated_input_tokens=0,
        estimated_output_tokens=0,
        estimated_total_tokens=0,
        estimated_cost=0,
        maximum_possible_cost=0,
        cache_hit_assumption="n/a",
        retry_assumption="n/a",
        storage_estimate_mb=0,
        configuration_hash="n/a",
    )
    cost = _aggregate_cost(provider, dummy_plan, attempts)
    if cost.input_tokens + cost.output_tokens > max_tokens:
        raise RuntimeError("Stage B token ceiling exceeded")
    if (cost.token_derived_cost_usd or Decimal("0")) > Decimal(str(max_cost)):
        raise RuntimeError("Stage B cost ceiling exceeded")


def _trajectory_exists(output_dir: Path, trajectory_id: str) -> bool:
    return any(
        row.get("trajectory_id") == trajectory_id
        for row in read_jsonl(output_dir / "raw_trajectories.jsonl")
    )


def _pricing_table_version(provider: PilotProviderConfig) -> str | None:
    try:
        return load_pricing_record(
            provider.provider_name or provider.provider_class,
            provider.model_identifier or "mock-deterministic-v1",
        ).pricing_table_version
    except KeyError:
        return None


def _review_packet_path(trajectory_id: str) -> Path:
    if STAGE_B2_PILOT_ID in trajectory_id:
        return STAGE_B2_REVIEW_ROOT / f"{trajectory_id}.json"
    return STAGE_B_REVIEW_ROOT / f"{trajectory_id}.json"


def _summarize_prompt(prompt: str) -> str:
    return " ".join(prompt.split())[:500]


def _git_commit() -> str | None:
    try:
        import subprocess

        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return None
