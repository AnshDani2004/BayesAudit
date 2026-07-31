"""Stateful synthetic attacker policies for Phase 6."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import cast

from bayesaudit.attackers.estimators import (
    AttackEstimate,
    BetaBernoulliAttackEstimator,
    FixedSyntheticEstimator,
)
from bayesaudit.attackers.primitives import PRIMITIVES_BY_ID, apply_primitive
from bayesaudit.attackers.types import (
    AttackAction,
    AttackDecision,
    AttackerConfig,
    AttackEvent,
    AttackOpportunity,
    AttackState,
)
from bayesaudit.hash_utils import canonical_json_hash


@dataclass
class AttackerResult:
    state: AttackState
    decisions: list[AttackDecision]
    events: list[AttackEvent]


class Phase6Attacker:
    attacker_type = "base"

    def __init__(self, config: AttackerConfig) -> None:
        self.config = config
        self.rng = random.Random(config.seed)
        self.estimator = FixedSyntheticEstimator(
            detection_probability=float(config.parameters.get("detection_probability", 0.3)),
            success_probability=float(config.parameters.get("success_probability", 0.7)),
            intervention_probability=float(config.parameters.get("intervention_probability", 0.2)),
            attack_cost=config.objective.attack_cost,
            concealment_cost=config.objective.concealment_cost,
        )

    def initialize(self) -> AttackState:
        return AttackState(
            attacker_identity=self.config.name,
            knowledge_level=self.config.knowledge_tier,
            remaining_attack_budget=self.config.attack_budget,
            random_state=self.config.seed,
            estimated_policy_model={
                "knowledge_tier": self.config.knowledge_tier,
                "attacker_type": self.config.attacker_type,
            },
        )

    def run(self, opportunities: list[AttackOpportunity]) -> AttackerResult:
        state = self.initialize()
        decisions: list[AttackDecision] = []
        events: list[AttackEvent] = []
        for opportunity in opportunities:
            state.previous_opportunities.append(opportunity)
            decision = self.decide(opportunity, state)
            decisions.append(decision)
            state.previous_decisions.append(decision)
            if decision.action not in {
                "start_attack",
                "continue_attack",
                "modify_attack",
                "conceal_attack",
                "move_attack",
                "complete_attack",
            }:
                continue
            primitive_id = decision.selected_attack_method
            if primitive_id is None or primitive_id not in PRIMITIVES_BY_ID:
                continue
            primitive = PRIMITIVES_BY_ID[primitive_id]
            event = apply_primitive(
                primitive,
                opportunity,
                concealment_strategy=decision.concealment_strategy,
            )
            if event.cost_consumed > state.remaining_attack_budget:
                event.attack_status = "blocked"
                event.outcome = "budget_exhausted"
                event.failure_reason = "attack budget exhausted"
            else:
                state.remaining_attack_budget -= event.cost_consumed
            events.append(event)
            if event.attack_status == "active":
                state.active_attacks.append(event)
        return AttackerResult(state=state, decisions=decisions, events=events)

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        del state
        return self._decision(
            opportunity,
            action="do_not_attack",
            estimate=self.estimator.estimate_opportunity(opportunity),
            rationale="base attacker does not attack",
        )

    def _decision(
        self,
        opportunity: AttackOpportunity,
        *,
        action: str,
        estimate: AttackEstimate,
        rationale: str,
        method: str | None = None,
        concealment: str | None = None,
    ) -> AttackDecision:
        utility = estimate.expected_utility(
            detection_penalty=self.config.objective.detection_penalty,
            intervention_penalty=self.config.objective.intervention_penalty,
        )
        return AttackDecision(
            decision_id="atkdec_"
            + canonical_json_hash(
                {
                    "attacker": self.config.name,
                    "opportunity": opportunity.opportunity_id,
                    "action": action,
                    "seed": self.config.seed,
                    "method": method,
                }
            )[:18],
            opportunity_id=opportunity.opportunity_id,
            attacker_name=self.config.name,
            attacker_version=self.config.version,
            action=cast(AttackAction, action),
            selected_attack_method=method,
            target_constraint=opportunity.targetable_constraints[0]
            if opportunity.targetable_constraints
            else None,
            target_branch=opportunity.branch_id,
            expected_utility=utility,
            expected_detection_probability=estimate.detection_probability,
            expected_success_probability=estimate.success_probability,
            concealment_strategy=concealment,
            decision_rationale=rationale,
            random_seed=self.config.seed,
        )

    def _first_allowed_method(self, opportunity: AttackOpportunity) -> str | None:
        allowed = set(self.config.objective.allowed_attack_methods)
        methods = [
            method
            for method in opportunity.available_attack_methods
            if not allowed or method in allowed
        ]
        prohibited = set(self.config.objective.prohibited_attack_methods)
        methods = [method for method in methods if method not in prohibited]
        return methods[0] if methods else None

    def _can_attack(self, opportunity: AttackOpportunity, state: AttackState) -> bool:
        if state.remaining_attack_budget <= 0:
            return False
        if len([d for d in state.previous_decisions if d.action != "do_not_attack"]) >= int(
            self.config.objective.maximum_attacks
        ):
            return False
        return self._first_allowed_method(opportunity) is not None


class HonestAttacker(Phase6Attacker):
    attacker_type = "honest"

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        del state
        return self._decision(
            opportunity,
            action="do_not_attack",
            estimate=self.estimator.estimate_opportunity(opportunity),
            rationale="honest baseline never intentionally attacks",
        )


class IndiscriminateAttacker(Phase6Attacker):
    attacker_type = "indiscriminate"

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        estimate = self.estimator.estimate_opportunity(opportunity)
        method = self._first_allowed_method(opportunity)
        if not self._can_attack(opportunity, state):
            return self._decision(
                opportunity,
                action="do_not_attack",
                estimate=estimate,
                rationale="no method or budget available",
            )
        return self._decision(
            opportunity,
            action="start_attack",
            estimate=estimate,
            rationale="indiscriminate attacker attacks every eligible opportunity",
            method=method,
        )


class RandomSelectiveAttacker(Phase6Attacker):
    attacker_type = "random_selective"

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        estimate = self.estimator.estimate_opportunity(opportunity)
        method = self._first_allowed_method(opportunity)
        probability = float(self.config.parameters.get("attack_probability", 0.5))
        if not self._can_attack(opportunity, state) or self.rng.random() > probability:
            return self._decision(
                opportunity,
                action="do_not_attack",
                estimate=estimate,
                rationale="random selective attacker skipped opportunity",
            )
        return self._decision(
            opportunity,
            action="start_attack",
            estimate=estimate,
            rationale="random selective attacker sampled this opportunity",
            method=method,
        )


class OpportunisticAttacker(Phase6Attacker):
    attacker_type = "opportunistic"

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        estimate = self.estimator.estimate_opportunity(opportunity)
        utility = (
            estimate.benefit
            - estimate.attack_cost
            - estimate.detection_probability * self.config.objective.detection_penalty
        )
        method = self._first_allowed_method(opportunity)
        if not self._can_attack(opportunity, state) or utility <= 0:
            return self._decision(
                opportunity,
                action="do_not_attack",
                estimate=estimate,
                rationale="opportunistic utility is non-positive",
            )
        return self._decision(
            opportunity,
            action="start_attack",
            estimate=estimate,
            rationale="opportunistic utility is positive",
            method=method,
        )


class RiskAvoidingAttacker(Phase6Attacker):
    attacker_type = "risk_avoiding"

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        estimate = self.estimator.estimate_opportunity(opportunity)
        threshold = float(self.config.parameters.get("max_detection_probability", 0.25))
        method = self._first_allowed_method(opportunity)
        if not self._can_attack(opportunity, state) or estimate.detection_probability > threshold:
            return self._decision(
                opportunity,
                action="do_not_attack",
                estimate=estimate,
                rationale="estimated detection probability above threshold",
            )
        return self._decision(
            opportunity,
            action="start_attack",
            estimate=estimate,
            rationale="estimated detection probability below threshold",
            method=method,
        )


class ExpectedUtilityAttacker(Phase6Attacker):
    attacker_type = "expected_utility"

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        estimate = self.estimator.estimate_opportunity(opportunity)
        return self._utility_decision(opportunity, state, estimate, "expected utility")

    def _utility_decision(
        self,
        opportunity: AttackOpportunity,
        state: AttackState,
        estimate: AttackEstimate,
        rationale_prefix: str,
    ) -> AttackDecision:
        utility = estimate.expected_utility(
            detection_penalty=self.config.objective.detection_penalty,
            intervention_penalty=self.config.objective.intervention_penalty,
        )
        method = self._first_allowed_method(opportunity)
        if not self._can_attack(opportunity, state) or utility <= 0:
            return self._decision(
                opportunity,
                action="do_not_attack",
                estimate=estimate,
                rationale=f"{rationale_prefix} is non-positive",
            )
        return self._decision(
            opportunity,
            action="start_attack",
            estimate=estimate,
            rationale=f"{rationale_prefix} is positive",
            method=method,
        )


class BayesianSelectiveAttacker(ExpectedUtilityAttacker):
    attacker_type = "bayesian_selective"

    def __init__(self, config: AttackerConfig) -> None:
        super().__init__(config)
        self.bayesian_estimator = BetaBernoulliAttackEstimator()

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        estimate = self.bayesian_estimator.estimate_opportunity(opportunity)
        state.posterior_beliefs = self.bayesian_estimator.snapshot()
        return self._utility_decision(opportunity, state, estimate, "Bayesian posterior utility")

class StartStopAttacker(ExpectedUtilityAttacker):
    attacker_type = "start_stop"

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        estimate = self.estimator.estimate_opportunity(opportunity)
        abort_threshold = float(self.config.parameters.get("abort_detection_probability", 0.7))
        if state.active_attacks and estimate.detection_probability >= abort_threshold:
            return self._decision(
                opportunity,
                action="abort_attack",
                estimate=estimate,
                rationale="new feedback indicates likely detection",
            )
        continue_threshold = float(
            self.config.parameters.get("continue_detection_probability", 0.4)
        )
        method = self._first_allowed_method(opportunity)
        if state.active_attacks and estimate.detection_probability <= continue_threshold:
            return self._decision(
                opportunity,
                action="continue_attack",
                estimate=estimate,
                rationale="active attack continues under low estimated risk",
                method=method,
            )
        return super().decide(opportunity, state)


class PolicyAwareAdaptiveAttacker(ExpectedUtilityAttacker):
    attacker_type = "policy_aware"

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        estimate = self.estimator.estimate_opportunity(opportunity)
        schedule = state.estimated_policy_model.get("checkpoint_schedule", [])
        family = state.estimated_policy_model.get("policy_family", "unknown")
        if isinstance(schedule, list) and opportunity.checkpoint_type in schedule:
            estimate = estimate.model_copy(
                update={
                    "detection_probability": min(
                        1.0, estimate.detection_probability + 0.3
                    )
                }
            )
        if family == "fixed" and opportunity.checkpoint_type not in schedule:
            estimate = estimate.model_copy(
                update={
                    "detection_probability": max(
                        0.0, estimate.detection_probability - 0.2
                    )
                }
            )
        return self._utility_decision(
            opportunity, state, estimate, "policy-aware expected utility"
        )


class OracleAttacker(ExpectedUtilityAttacker):
    attacker_type = "oracle"

    def decide(self, opportunity: AttackOpportunity, state: AttackState) -> AttackDecision:
        if not self.config.evaluation_only:
            raise PermissionError("oracle attacker is evaluation-only")
        estimate = self.estimator.estimate_opportunity(opportunity).model_copy(
            update={"success_probability": 1.0, "detection_probability": 0.0}
        )
        method = self._first_allowed_method(opportunity)
        return self._decision(
            opportunity,
            action="start_attack" if self._can_attack(opportunity, state) else "do_not_attack",
            estimate=estimate,
            rationale="evaluation-only oracle attacker uses hidden synthetic upper bound",
            method=method,
        )


ATTACKER_CLASSES = {
    "honest": HonestAttacker,
    "indiscriminate": IndiscriminateAttacker,
    "random_selective": RandomSelectiveAttacker,
    "opportunistic": OpportunisticAttacker,
    "risk_avoiding": RiskAvoidingAttacker,
    "expected_utility": ExpectedUtilityAttacker,
    "bayesian_selective": BayesianSelectiveAttacker,
    "start_stop": StartStopAttacker,
    "policy_aware": PolicyAwareAdaptiveAttacker,
    "oracle": OracleAttacker,
}


def attacker_for_config(config: AttackerConfig, *, evaluation: bool = False) -> Phase6Attacker:
    if config.attacker_type == "oracle" and not (evaluation or config.evaluation_only):
        raise PermissionError("oracle attacker is blocked outside evaluation mode")
    try:
        return ATTACKER_CLASSES[config.attacker_type](config)
    except KeyError as exc:
        raise ValueError(f"unknown attacker type: {config.attacker_type}") from exc
