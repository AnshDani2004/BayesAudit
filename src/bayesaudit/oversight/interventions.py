"""Synthetic intervention execution records for Phase 4."""

from __future__ import annotations

from bayesaudit.oversight.types import (
    InterventionDecisionRecord,
    InterventionOutcomeRecord,
    InterventionStatus,
    WorkflowMode,
)
from bayesaudit.schemas import OversightAction


def execute_intervention(
    decision: InterventionDecisionRecord, *, budget_available: bool
) -> InterventionOutcomeRecord:
    if decision.mode == WorkflowMode.SHADOW:
        status = InterventionStatus.NOT_APPLICABLE
        executed = False
    elif not decision.still_preventable:
        status = InterventionStatus.TOO_LATE
        executed = False
    elif not budget_available:
        status = InterventionStatus.INSUFFICIENT_BUDGET
        executed = False
    else:
        status = InterventionStatus.EXECUTED
        executed = True
    action = (
        decision.action.value
        if isinstance(decision.action, OversightAction)
        else str(decision.action)
    )
    return InterventionOutcomeRecord(
        outcome_id=f"{decision.intervention_decision_id}_outcome",
        intervention_decision_id=decision.intervention_decision_id,
        policy_run_id=decision.policy_run_id,
        observation_id=decision.observation_id,
        action=decision.action,
        status=status,
        blocked_action=executed and action == OversightAction.BLOCK.value,
        requested_clarification=executed and action == OversightAction.REQUEST_CLARIFICATION.value,
        escalated=executed and action == OversightAction.ESCALATE.value,
        terminated_workflow=executed and action == OversightAction.TERMINATE.value,
        changed_task_output=executed and action != OversightAction.CONTINUE.value,
        utility_consequence=-0.05 if executed else 0.0,
        cost=decision.cost if executed else 0.0,
        synthetic_resolver_output="deny"
        if executed and action == OversightAction.ESCALATE.value
        else None,
    )
