"""Shared helpers for Phase 2 workflow implementations."""

from __future__ import annotations

from datetime import datetime, timezone

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.models.mock import MockModel
from bayesaudit.schemas import (
    ArchitectureKind,
    BehaviorCondition,
    BenchmarkTask,
    BudgetState,
    BudgetUnit,
    ModelConfigRecord,
    ToolCallRecord,
    Trajectory,
    TrajectoryStatus,
    UsageTotals,
)


def make_trajectory(
    *,
    task: BenchmarkTask,
    model: MockModel,
    architecture: ArchitectureKind,
    experiment_id: str,
    run_id: str,
    seed: int,
) -> Trajectory:
    config_hash = canonical_json_hash(
        {
            "task_id": task.task_id,
            "scenario_hash": task.scenario_hash,
            "architecture": architecture,
            "model_id": model.model_id,
            "profile": model.script.profile,
            "seed": seed,
        }
    )
    return Trajectory(
        trajectory_id=f"traj_{run_id}",
        task_id=task.task_id,
        task_version=task.task_version,
        scenario_hash=task.scenario_hash,
        experiment_id=experiment_id,
        run_id=run_id,
        architecture=architecture,
        behavior_condition=BehaviorCondition.HONEST,
        model_configuration=ModelConfigRecord(
            provider="mock",
            model_id=model.model_id,
            model_version="phase2",
            behavior_profile=model.script.profile,
            raw_config=model.script.model_dump(mode="json"),
        ),
        oversight_policy="no_oversight",
        oversight_budget=BudgetState(
            initial_budget=0.0,
            remaining_budget=0.0,
            consumed_budget=0.0,
            budget_unit=BudgetUnit.AUDIT_COUNT,
        ),
        seed=seed,
        status=TrajectoryStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
        git_commit=None,
        configuration_hash=config_hash,
        metadata={"synthetic": True},
    )


def add_usage(trajectory: Trajectory) -> None:
    input_tokens = 0
    output_tokens = 0
    estimated_cost = 0.0
    latency_ms = 0.0
    for step in trajectory.steps:
        if step.model_response is not None:
            input_tokens += step.model_response.input_tokens
            output_tokens += step.model_response.output_tokens
            estimated_cost += step.model_response.estimated_cost
            latency_ms += step.model_response.latency_ms
    trajectory.usage_totals = UsageTotals(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost=estimated_cost,
        latency_ms=latency_ms,
    )


def tool_requests_from_response(response_metadata: dict[str, object]) -> list[dict[str, object]]:
    requests = response_metadata.get("tool_requests", [])
    if not isinstance(requests, list):
        return []
    return [request for request in requests if isinstance(request, dict)]


def final_text(trajectory: Trajectory) -> str:
    for step in reversed(trajectory.steps):
        if step.model_response is not None and str(step.kind) == "final_output":
            return step.model_response.message.content
    return ""


def all_tool_calls(trajectory: Trajectory) -> list[ToolCallRecord]:
    calls: list[ToolCallRecord] = []
    for step in trajectory.steps:
        calls.extend(step.tool_calls)
    return calls
