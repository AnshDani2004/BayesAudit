"""Policy interface and shared helpers for Phase 4 oversight baselines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bayesaudit.oversight.types import (
    AuditDecisionRecord,
    AuditFeedbackRecord,
    InterventionDecisionRecord,
    OversightObservation,
    PolicyStateRecord,
    WorkflowMode,
)
from bayesaudit.schemas import BenchmarkTask, OversightAction


@dataclass
class OversightPolicyConfig:
    name: str
    policy_type: str
    budget: float = 0.0
    mode: str = WorkflowMode.SHADOW
    seed: int = 0
    enabled: bool = True
    evaluation_only: bool = False
    parameters: dict[str, Any] = field(default_factory=dict)


class Phase4Policy:
    """Deterministic lifecycle used by shadow and intervention replay."""

    policy_type = "base"
    version = "phase4_v1"

    def __init__(self, config: OversightPolicyConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    async def initialize(self, task: BenchmarkTask, state: PolicyStateRecord) -> PolicyStateRecord:
        state.policy_specific_state.update(
            {
                "task_id": task.task_id,
                "policy_type": self.policy_type,
                "mode": self.config.mode,
            }
        )
        return state

    async def decide_audit(
        self,
        observation: OversightObservation,
        state: PolicyStateRecord,
        *,
        oracle_metadata: dict[str, Any] | None = None,
    ) -> AuditDecisionRecord:
        del oracle_metadata
        return self._decision(
            observation,
            audit_requested=False,
            probability=0.0,
            reason="base policy does not request audits",
            risk_score=0.0,
            recommended_action=OversightAction.CONTINUE.value,
        )

    async def observe_feedback(
        self, feedback: AuditFeedbackRecord, state: PolicyStateRecord
    ) -> PolicyStateRecord:
        state.prior_feedback.append(feedback.model_dump(mode="json"))
        return state

    async def decide_intervention(
        self,
        observation: OversightObservation,
        state: PolicyStateRecord,
        *,
        feedback: AuditFeedbackRecord | None = None,
        decision_index: int = 0,
    ) -> InterventionDecisionRecord | None:
        if feedback is None or not feedback.findings:
            return None
        action = _strongest_recommended_action(feedback)
        if action == OversightAction.CONTINUE.value:
            return None
        return InterventionDecisionRecord(
            intervention_decision_id=f"{feedback.policy_run_id}_intervention_{decision_index}",
            policy_run_id=feedback.policy_run_id,
            observation_id=observation.observation_id,
            audit_id=feedback.audit_id,
            action=action,
            target=observation.current_step_id,
            reason="audit feedback recommended intervention",
            cost=observation.checkpoint.intervention_cost,
            still_preventable=observation.checkpoint.intervention_still_possible,
            mode=self.config.mode,
        )

    async def finalize(self, state: PolicyStateRecord) -> PolicyStateRecord:
        state.finalized = True
        state.finalization_metadata["decision_count"] = len(state.prior_audit_decisions)
        state.finalization_metadata["feedback_count"] = len(state.prior_feedback)
        state.finalization_metadata["intervention_count"] = len(state.prior_interventions)
        return state

    def _decision(
        self,
        observation: OversightObservation,
        *,
        audit_requested: bool,
        probability: float,
        reason: str,
        risk_score: float,
        recommended_action: str,
        sampling_method: str | None = None,
    ) -> AuditDecisionRecord:
        return AuditDecisionRecord(
            decision_id=f"{self.config.name}_{observation.observation_id}_decision",
            policy_run_id=str(
                observation.current_budget_state.get("policy_run_id", self.config.name)
            ),
            policy_name=self.config.name,
            policy_version=self.version,
            observation_id=observation.observation_id,
            checkpoint_type=observation.checkpoint.checkpoint_type,
            audit_requested=audit_requested,
            audit_probability=probability,
            sampling_method=sampling_method,
            reason=reason,
            budget_available=bool(
                observation.current_budget_state.get("remaining_budget", 0.0)
                >= observation.checkpoint.audit_cost
            ),
            audit_cost=observation.checkpoint.audit_cost if audit_requested else 0.0,
            risk_score=risk_score,
            recommended_action=recommended_action,
            mode=self.config.mode,
        )


_ACTION_RANK: dict[str, int] = {
    OversightAction.CONTINUE.value: 0,
    OversightAction.REQUEST_CLARIFICATION.value: 1,
    OversightAction.ESCALATE.value: 2,
    OversightAction.BLOCK.value: 3,
    OversightAction.TERMINATE.value: 4,
}


def _strongest_recommended_action(feedback: AuditFeedbackRecord) -> str:
    return max(
        (str(finding.recommended_intervention) for finding in feedback.findings),
        key=lambda action: _ACTION_RANK.get(action, 0),
        default=OversightAction.CONTINUE.value,
    )
