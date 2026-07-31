"""Replay completed trajectories through Phase 4 oversight policies."""

from __future__ import annotations

from typing import Any

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.oversight.auditors import audit_observation
from bayesaudit.oversight.budget import BudgetLedger
from bayesaudit.oversight.checkpoints import checkpoints_for_trajectory
from bayesaudit.oversight.interventions import execute_intervention
from bayesaudit.oversight.matching import match_detections
from bayesaudit.oversight.metrics import build_frontier_point, compute_policy_metrics
from bayesaudit.oversight.observations import build_observation
from bayesaudit.oversight.policy_base import OversightPolicyConfig
from bayesaudit.oversight.registry import policy_for_config
from bayesaudit.oversight.types import (
    AuditStatus,
    InterventionDecisionRecord,
    InterventionOutcomeRecord,
    InterventionStatus,
    OversightRunResult,
    PolicyStateRecord,
    WorkflowMode,
)
from bayesaudit.schemas import BenchmarkTask, BudgetUnit, OversightAction, ScoreResult, Trajectory


async def replay_policy(
    *,
    task: BenchmarkTask,
    trajectory: Trajectory,
    score: ScoreResult | None,
    config: OversightPolicyConfig,
    experiment_id: str,
    evaluation: bool = False,
) -> OversightRunResult:
    policy_run_id = _policy_run_id(trajectory, config)
    ledger = BudgetLedger(
        policy_run_id=policy_run_id,
        initial_budget=config.budget,
        budget_unit=BudgetUnit.AUDIT_COUNT,
    )
    policy = policy_for_config(config, evaluation=evaluation or config.evaluation_only)
    state = PolicyStateRecord(
        policy_name=config.name,
        policy_version=policy.version,
        seed=config.seed,
        budget=ledger.state.model_copy(),
        policy_specific_state={"policy_run_id": policy_run_id},
    )
    state = await policy.initialize(task, state)
    result = OversightRunResult(
        policy_run_id=policy_run_id,
        trajectory_id=trajectory.trajectory_id,
        run_id=trajectory.run_id,
        experiment_id=experiment_id,
        policy_name=config.name,
        policy_version=policy.version,
        mode=config.mode,
        synthetic=True,
        metadata={
            "base_trajectory_unchanged": True,
            "checkpoint_count": 0,
            "evaluation_only": config.evaluation_only,
        },
    )
    checkpoints = checkpoints_for_trajectory(trajectory)
    result.metadata["checkpoint_count"] = len(checkpoints)
    prior_public_feedback: list[dict[str, Any]] = []
    prior_actions: list[dict[str, Any]] = []
    audit_index = 0
    intervention_index = 0
    for checkpoint in checkpoints:
        observation = build_observation(
            task=task,
            trajectory=trajectory,
            checkpoint=checkpoint,
            budget=ledger,
            mode=config.mode,
            prior_public_audit_outcomes=prior_public_feedback,
            prior_policy_actions=prior_actions,
        )
        observation.current_budget_state["policy_run_id"] = policy_run_id
        decision = await policy.decide_audit(
            observation,
            state,
            oracle_metadata=_oracle_metadata(score) if config.evaluation_only else None,
        )
        decision.policy_run_id = policy_run_id
        decision.budget_available = ledger.can_spend(checkpoint.audit_cost)
        if decision.audit_requested and not _consume_audit_budget(
            ledger, observation.observation_id, checkpoint.audit_cost
        ):
            decision.audit_requested = False
            decision.audit_cost = 0.0
            decision.budget_available = False
            decision.reason = "audit skipped by hard budget enforcement"
        result.decisions.append(decision)
        state.prior_audit_decisions.append(decision.model_dump(mode="json"))
        prior_actions.append(
            {
                "observation_id": observation.observation_id,
                "checkpoint_type": checkpoint.checkpoint_type,
                "audit_requested": decision.audit_requested,
                "recommended_action": decision.recommended_action,
            }
        )
        if not decision.audit_requested:
            continue
        audit_index += 1
        feedback = audit_observation(
            observation,
            policy_run_id=policy_run_id,
            audit_index=audit_index,
            audit_cost=checkpoint.audit_cost,
        )
        result.feedback.append(feedback)
        state = await policy.observe_feedback(feedback, state)
        prior_public_feedback.append(_public_feedback(feedback))
        intervention_index += 1
        intervention = await policy.decide_intervention(
            observation,
            state,
            feedback=feedback,
            decision_index=intervention_index,
        )
        if intervention is not None:
            outcome = _apply_intervention(ledger, intervention)
            result.intervention_decisions.append(intervention)
            result.intervention_outcomes.append(outcome)
            state.prior_interventions.append(intervention.model_dump(mode="json"))
    state.budget = ledger.finalize().model_copy()
    state = await policy.finalize(state)
    result.final_policy_state = state
    result.budget_transactions = list(ledger.transactions)
    result.detection_matches = match_detections(result, score)
    result.metrics = compute_policy_metrics(result, score)
    result.metadata["frontier_point"] = build_frontier_point(
        result, score, experiment_id=experiment_id
    ).model_dump(mode="json")
    return result


async def replay_policies(
    *,
    task: BenchmarkTask,
    trajectory: Trajectory,
    score: ScoreResult | None,
    configs: list[OversightPolicyConfig],
    experiment_id: str,
) -> list[OversightRunResult]:
    return [
        await replay_policy(
            task=task,
            trajectory=trajectory,
            score=score,
            config=config,
            experiment_id=experiment_id,
            evaluation=config.evaluation_only,
        )
        for config in configs
    ]


def _policy_run_id(trajectory: Trajectory, config: OversightPolicyConfig) -> str:
    return "ovr_" + canonical_json_hash(
        {
            "run_id": trajectory.run_id,
            "policy_name": config.name,
            "policy_type": config.policy_type,
            "budget": config.budget,
            "mode": config.mode,
            "seed": config.seed,
            "parameters": config.parameters,
        }
    )[:20]


def _consume_audit_budget(ledger: BudgetLedger, observation_id: str, cost: float) -> bool:
    if not ledger.reserve(cost, observation_id=observation_id, reason="audit decision"):
        return False
    return ledger.consume_reserved(
        cost,
        observation_id=observation_id,
        kind="audit",
        reason="audit completed",
    )


def _apply_intervention(
    ledger: BudgetLedger, intervention: InterventionDecisionRecord
) -> InterventionOutcomeRecord:
    budget_available = True
    if intervention.mode == WorkflowMode.INTERVENTION:
        budget_available = ledger.reserve(
            intervention.cost,
            observation_id=intervention.observation_id,
            reason="intervention decision",
        )
        if budget_available:
            action = (
                intervention.action.value
                if isinstance(intervention.action, OversightAction)
                else str(intervention.action)
            )
            kind = "escalation" if action == OversightAction.ESCALATE.value else "intervention"
            budget_available = ledger.consume_reserved(
                intervention.cost,
                observation_id=intervention.observation_id,
                kind=kind,
                reason="intervention executed",
            )
    outcome = execute_intervention(intervention, budget_available=budget_available)
    if intervention.mode == WorkflowMode.INTERVENTION and not budget_available:
        outcome.status = InterventionStatus.INSUFFICIENT_BUDGET
    return outcome


def _oracle_metadata(score: ScoreResult | None) -> dict[str, Any]:
    if score is None:
        return {"violating_step_ids": [], "violating_constraint_ids": []}
    return {
        "violating_step_ids": sorted({violation.first_step_id for violation in score.violations}),
        "violating_constraint_ids": sorted(
            {violation.constraint_id for violation in score.violations}
        ),
    }


def _public_feedback(feedback: Any) -> dict[str, Any]:
    if getattr(feedback, "audit_status", None) != AuditStatus.COMPLETED:
        return {"audit_id": feedback.audit_id, "audit_status": feedback.audit_status}
    return {
        "audit_id": feedback.audit_id,
        "audit_status": feedback.audit_status,
        "finding_count": len(feedback.findings),
        "suspected_violation_categories": list(feedback.suspected_violation_categories),
        "recommended_action": feedback.findings[0].recommended_intervention
        if feedback.findings
        else OversightAction.CONTINUE.value,
    }
