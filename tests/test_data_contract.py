from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from bayesaudit.benchmark.io import load_task, load_tasks
from bayesaudit.schemas import (
    ArchitectureKind,
    AuditDecision,
    BudgetState,
    Domain,
    OversightAction,
    ToolCallRecord,
    ToolExecutionStatus,
    Trajectory,
    TrajectoryStep,
    ViolationEvent,
    WorkflowStepKind,
)

ROOT = Path(__file__).resolve().parents[1]


def test_all_25_fixtures_validate() -> None:
    tasks = load_tasks(ROOT / "scenarios")
    assert len(tasks) == 25
    counts = {domain.value: 0 for domain in Domain}
    for task in tasks:
        counts[task.domain] += 1
    assert counts == {domain.value: 5 for domain in Domain}


def test_unknown_fields_are_rejected() -> None:
    task = load_task(ROOT / "scenarios/privacy/task_privacy_aggregate_only.yaml")
    payload = task.model_dump()
    payload["surprise"] = True
    with pytest.raises(ValidationError):
        type(task).model_validate(payload)


def test_duplicate_constraint_ids_are_rejected() -> None:
    task = load_task(ROOT / "scenarios/privacy/task_privacy_aggregate_only.yaml")
    payload = task.model_dump()
    payload["constraints"][1]["id"] = payload["constraints"][0]["id"]
    with pytest.raises(ValidationError):
        type(task).model_validate(payload)


def test_tool_allow_and_deny_lists_cannot_overlap() -> None:
    task = load_task(ROOT / "scenarios/privacy/task_privacy_aggregate_only.yaml")
    payload = task.model_dump()
    payload["prohibited_tools"].append(payload["authorized_tools"][0])
    with pytest.raises(ValidationError):
        type(task).model_validate(payload)


def test_scenario_hash_is_stable() -> None:
    first = load_task(ROOT / "scenarios/evidence/task_evidence_claim_support.yaml")
    second = load_task(ROOT / "scenarios/evidence/task_evidence_claim_support.yaml")
    assert first.scenario_hash
    assert first.scenario_hash == second.scenario_hash


def test_task_versions_are_preserved() -> None:
    task = load_task(ROOT / "scenarios/evidence/task_evidence_claim_support.yaml")
    assert task.task_version == "v1"
    assert task.scoring.scorer_version == "v1"


def test_invalid_budget_state_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BudgetState(initial_budget=2.0, consumed_budget=1.0, remaining_budget=2.0)


def test_invalid_hierarchy_link_is_rejected() -> None:
    step = TrajectoryStep(
        step_id="child",
        sequence_index=1,
        parent_step_id="missing",
        agent_id="worker",
        role="worker",
        depth=1,
        kind=WorkflowStepKind.DELEGATION,
    )
    with pytest.raises(ValidationError):
        _trajectory([step])


def test_parent_steps_must_precede_children() -> None:
    parent = TrajectoryStep(
        step_id="parent",
        sequence_index=2,
        agent_id="planner",
        role="planner",
        depth=0,
        kind=WorkflowStepKind.PLANNING,
    )
    child = TrajectoryStep(
        step_id="child",
        sequence_index=1,
        parent_step_id="parent",
        agent_id="worker",
        role="worker",
        depth=1,
        kind=WorkflowStepKind.DELEGATION,
    )
    with pytest.raises(ValidationError):
        _trajectory([child, parent])


def test_violation_event_has_no_policy_outcome_fields() -> None:
    fields = set(ViolationEvent.model_fields)
    assert "detected" not in fields
    assert "prevented" not in fields
    assert {"violation_id", "evidence", "scorer_name", "scorer_version"}.issubset(fields)


def test_tool_call_uses_environment_authorization_fields() -> None:
    fields = set(ToolCallRecord.model_fields)
    assert "authorized" not in fields
    assert {"environment_authorized", "execution_status", "approval_required"}.issubset(fields)


def test_audit_decision_separates_detections_and_interventions() -> None:
    decision = AuditDecision(
        action=OversightAction.CONTINUE, reason="test", policy_name="no_oversight"
    )
    assert decision.detections == []
    assert decision.interventions == []


def _trajectory(steps: list[TrajectoryStep]) -> Trajectory:
    return Trajectory(
        trajectory_id="traj_test",
        task_id="task_evidence_claim_support",
        task_version="v1",
        scenario_hash="hash",
        experiment_id="exp",
        run_id="run",
        architecture=ArchitectureKind.SINGLE_AGENT,
        behavior_condition="honest",
        model_configuration={"provider": "mock", "model_id": "mock"},
        oversight_policy="no_oversight",
        oversight_budget={"initial_budget": 0, "remaining_budget": 0, "consumed_budget": 0},
        seed=1,
        configuration_hash="config",
        steps=steps,
    )


def test_tool_status_enum_contains_required_states() -> None:
    assert {status.value for status in ToolExecutionStatus} == {
        "requested",
        "approved",
        "blocked",
        "executed",
        "failed",
    }
