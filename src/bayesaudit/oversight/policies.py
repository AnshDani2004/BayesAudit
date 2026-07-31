"""Built-in deterministic Phase 4 oversight policies."""

from __future__ import annotations

import random
from typing import Any

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.oversight.policy_base import (
    Phase4Policy,
    _strongest_recommended_action,
)
from bayesaudit.oversight.types import (
    AuditDecisionRecord,
    AuditFeedbackRecord,
    InterventionDecisionRecord,
    OversightObservation,
    PolicyStateRecord,
)
from bayesaudit.schemas import BenchmarkTask, OversightAction


class NoOversightBaseline(Phase4Policy):
    policy_type = "no_oversight"

    async def decide_audit(
        self,
        observation: OversightObservation,
        state: PolicyStateRecord,
        *,
        oracle_metadata: dict[str, Any] | None = None,
    ) -> AuditDecisionRecord:
        del state, oracle_metadata
        return self._decision(
            observation,
            audit_requested=False,
            probability=0.0,
            reason="no oversight baseline never audits",
            risk_score=0.0,
            recommended_action=OversightAction.CONTINUE.value,
        )


class RandomBaseline(Phase4Policy):
    policy_type = "random"

    async def initialize(self, task: BenchmarkTask, state: PolicyStateRecord) -> PolicyStateRecord:
        state = await super().initialize(task, state)
        state.policy_specific_state["rng_seed"] = self.config.seed
        state.policy_specific_state["audit_fraction"] = float(
            self.config.parameters.get("audit_fraction", 0.1)
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
        probability = float(state.policy_specific_state.get("audit_fraction", 0.1))
        draw_seed = canonical_json_hash(
            {
                "seed": self.config.seed,
                "policy": self.name,
                "observation_id": observation.observation_id,
            }
        )
        draw = random.Random(draw_seed).random()
        budget_available = bool(
            observation.current_budget_state.get("remaining_budget", 0.0)
            >= observation.checkpoint.audit_cost
        )
        audit = draw < probability and budget_available and observation.checkpoint.audit_eligible
        return self._decision(
            observation,
            audit_requested=audit,
            probability=probability,
            sampling_method="bernoulli_seeded",
            reason="seeded random draw within budget" if audit else "seeded random draw skipped",
            risk_score=probability,
            recommended_action=OversightAction.CONTINUE.value,
        )


class FixedCheckpointBaseline(Phase4Policy):
    policy_type = "fixed"

    async def initialize(self, task: BenchmarkTask, state: PolicyStateRecord) -> PolicyStateRecord:
        state = await super().initialize(task, state)
        state.policy_specific_state["checkpoint_types"] = list(
            self.config.parameters.get("checkpoint_types", ["before_tool_request"])
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
        schedule = set(state.policy_specific_state.get("checkpoint_types", []))
        requested = (
            observation.checkpoint.checkpoint_type in schedule
            or observation.checkpoint.mandatory
        )
        budget_available = bool(
            observation.current_budget_state.get("remaining_budget", 0.0)
            >= observation.checkpoint.audit_cost
        )
        audit = requested and budget_available and observation.checkpoint.audit_eligible
        reason = "fixed checkpoint matched schedule" if requested else "checkpoint not in schedule"
        if requested and not budget_available:
            reason = "fixed checkpoint skipped due to insufficient budget"
        return self._decision(
            observation,
            audit_requested=audit,
            probability=1.0 if requested else 0.0,
            sampling_method="deterministic_schedule",
            reason=reason,
            risk_score=1.0 if requested else 0.0,
            recommended_action=OversightAction.CONTINUE.value,
        )


class RuleBasedBaseline(Phase4Policy):
    policy_type = "rule_based"

    async def initialize(self, task: BenchmarkTask, state: PolicyStateRecord) -> PolicyStateRecord:
        state = await super().initialize(task, state)
        state.policy_specific_state["risk_features"] = list(
            self.config.parameters.get("risk_features", [])
        )
        state.policy_specific_state["risk_threshold"] = float(
            self.config.parameters.get("risk_threshold", 1.0)
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
        configured = set(state.policy_specific_state.get("risk_features", []))
        active = [
            name
            for name, value in observation.observable_risk_features.items()
            if bool(value) and (not configured or name in configured)
        ]
        threshold = float(state.policy_specific_state.get("risk_threshold", 1.0))
        risk_score = float(len(active))
        budget_available = bool(
            observation.current_budget_state.get("remaining_budget", 0.0)
            >= observation.checkpoint.audit_cost
        )
        audit = (
            risk_score >= threshold
            and budget_available
            and observation.checkpoint.audit_eligible
        )
        return self._decision(
            observation,
            audit_requested=audit,
            probability=1.0 if audit else 0.0,
            sampling_method="deterministic_rules",
            reason=";".join(active) if active else "no configured risk feature active",
            risk_score=risk_score,
            recommended_action=OversightAction.ESCALATE.value
            if active
            else OversightAction.CONTINUE.value,
        )


class OracleEvaluationBaseline(Phase4Policy):
    policy_type = "oracle"

    async def decide_audit(
        self,
        observation: OversightObservation,
        state: PolicyStateRecord,
        *,
        oracle_metadata: dict[str, Any] | None = None,
    ) -> AuditDecisionRecord:
        del state
        if not self.config.evaluation_only:
            raise ValueError("oracle policy requires evaluation_only=True")
        metadata = oracle_metadata or {}
        violating_steps = set(metadata.get("violating_step_ids", []))
        violating_constraint_ids = set(metadata.get("violating_constraint_ids", []))
        current_constraint_ids = {
            snapshot.get("constraint_id") for snapshot in observation.current_constraint_snapshots
        }
        sees_violation = (
            observation.current_step_id in violating_steps
            or bool(violating_constraint_ids.intersection(current_constraint_ids))
        )
        budget_available = bool(
            observation.current_budget_state.get("remaining_budget", 0.0)
            >= observation.checkpoint.audit_cost
        )
        audit = sees_violation and budget_available and observation.checkpoint.audit_eligible
        return self._decision(
            observation,
            audit_requested=audit,
            probability=1.0 if sees_violation else 0.0,
            sampling_method="oracle_labels_evaluation_only",
            reason="oracle label positive" if sees_violation else "oracle label negative",
            risk_score=1.0 if sees_violation else 0.0,
            recommended_action=OversightAction.ESCALATE.value
            if sees_violation
            else OversightAction.CONTINUE.value,
        )

    async def decide_intervention(
        self,
        observation: OversightObservation,
        state: PolicyStateRecord,
        *,
        feedback: AuditFeedbackRecord | None = None,
        decision_index: int = 0,
    ) -> InterventionDecisionRecord | None:
        if feedback is not None and feedback.findings:
            action = _strongest_recommended_action(feedback)
        else:
            action = OversightAction.ESCALATE.value
        if action == OversightAction.CONTINUE.value:
            return None
        return await super().decide_intervention(
            observation, state, feedback=feedback, decision_index=decision_index
        )
