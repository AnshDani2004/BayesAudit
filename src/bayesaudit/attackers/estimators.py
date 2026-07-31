"""Synthetic attacker-side probability and utility estimators."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import NonNegativeFloat

from bayesaudit.attackers.types import AttackOpportunity
from bayesaudit.schemas import StrictModel


class AttackEstimate(StrictModel):
    success_probability: float
    detection_probability: float
    intervention_probability: float
    expected_severity: float
    benefit: float
    attack_cost: NonNegativeFloat
    concealment_cost: NonNegativeFloat = 0.0

    def expected_utility(
        self, *, detection_penalty: float, intervention_penalty: float
    ) -> float:
        return (
            self.success_probability * self.benefit
            - self.detection_probability * detection_penalty
            - self.intervention_probability * intervention_penalty
            - self.attack_cost
            - self.concealment_cost
        )


class FixedSyntheticEstimator:
    def __init__(
        self,
        *,
        success_probability: float = 0.7,
        detection_probability: float = 0.3,
        intervention_probability: float = 0.2,
        expected_severity: float = 5.0,
        benefit: float = 5.0,
        attack_cost: float = 1.0,
        concealment_cost: float = 0.0,
    ) -> None:
        self.estimate = AttackEstimate(
            success_probability=success_probability,
            detection_probability=detection_probability,
            intervention_probability=intervention_probability,
            expected_severity=expected_severity,
            benefit=benefit,
            attack_cost=attack_cost,
            concealment_cost=concealment_cost,
        )

    def estimate_opportunity(self, opportunity: AttackOpportunity) -> AttackEstimate:
        return self.estimate.model_copy(
            update={
                "benefit": opportunity.estimated_benefit or self.estimate.benefit,
                "success_probability": opportunity.estimated_success_probability
                or self.estimate.success_probability,
                "detection_probability": opportunity.estimated_detection_probability
                or self.estimate.detection_probability,
                "intervention_probability": opportunity.estimated_intervention_probability
                or self.estimate.intervention_probability,
                "attack_cost": opportunity.estimated_cost or self.estimate.attack_cost,
            }
        )


class EmpiricalGroupedEstimator:
    def __init__(self, *, default: FixedSyntheticEstimator | None = None) -> None:
        self.default = default or FixedSyntheticEstimator()
        self.outcomes: dict[str, list[dict[str, bool]]] = defaultdict(list)

    def update(self, opportunity: AttackOpportunity, *, success: bool, detected: bool) -> None:
        self.outcomes[_group_key(opportunity)].append({"success": success, "detected": detected})

    def estimate_opportunity(self, opportunity: AttackOpportunity) -> AttackEstimate:
        base = self.default.estimate_opportunity(opportunity)
        rows = self.outcomes.get(_group_key(opportunity), [])
        if not rows:
            return base
        return base.model_copy(
            update={
                "success_probability": sum(row["success"] for row in rows) / len(rows),
                "detection_probability": sum(row["detected"] for row in rows) / len(rows),
            }
        )


class BetaBernoulliAttackEstimator:
    def __init__(self, *, alpha: float = 1.0, beta: float = 1.0) -> None:
        self.alpha0 = alpha
        self.beta0 = beta
        self.success: dict[str, list[float]] = defaultdict(lambda: [self.alpha0, self.beta0])
        self.detection: dict[str, list[float]] = defaultdict(lambda: [self.alpha0, self.beta0])

    def estimate_opportunity(self, opportunity: AttackOpportunity) -> AttackEstimate:
        key = _group_key(opportunity)
        succ_a, succ_b = self.success[key]
        det_a, det_b = self.detection[key]
        return AttackEstimate(
            success_probability=float(succ_a / (succ_a + succ_b)),
            detection_probability=float(det_a / (det_a + det_b)),
            intervention_probability=opportunity.estimated_intervention_probability,
            expected_severity=max(1.0, opportunity.estimated_benefit),
            benefit=opportunity.estimated_benefit,
            attack_cost=opportunity.estimated_cost,
        )

    def update(
        self,
        opportunity: AttackOpportunity,
        *,
        attacked: bool,
        success: bool | None,
        detected: bool | None,
        observable: bool,
    ) -> None:
        if not attacked or not observable:
            return
        key = _group_key(opportunity)
        if success is not None:
            self.success[key][0 if success else 1] += 1.0
        if detected is not None:
            self.detection[key][0 if detected else 1] += 1.0

    def snapshot(self) -> dict[str, Any]:
        return {
            "success": dict(self.success),
            "detection": dict(self.detection),
            "prior": {"alpha": self.alpha0, "beta": self.beta0},
        }


class LearnedAttackEstimator:
    """Tiny attacker-observable surrogate over explicit features."""

    def __init__(self, feature_weights: dict[str, float] | None = None) -> None:
        self.feature_weights = feature_weights or {
            "delegation_depth": -0.05,
            "estimated_detection_probability": -0.8,
            "estimated_benefit": 0.15,
        }

    def estimate_opportunity(self, opportunity: AttackOpportunity) -> AttackEstimate:
        logit = -0.2
        logit += self.feature_weights.get("delegation_depth", 0.0) * opportunity.delegation_depth
        logit += (
            self.feature_weights.get("estimated_detection_probability", 0.0)
            * opportunity.estimated_detection_probability
        )
        logit += self.feature_weights.get("estimated_benefit", 0.0) * opportunity.estimated_benefit
        success = 1.0 / (1.0 + pow(2.718281828, -max(-20.0, min(20.0, logit))))
        return AttackEstimate(
            success_probability=success,
            detection_probability=opportunity.estimated_detection_probability,
            intervention_probability=opportunity.estimated_intervention_probability,
            expected_severity=max(1.0, opportunity.estimated_benefit),
            benefit=opportunity.estimated_benefit,
            attack_cost=opportunity.estimated_cost,
        )


def _group_key(opportunity: AttackOpportunity) -> str:
    return "|".join(
        [
            opportunity.checkpoint_type,
            str(opportunity.domain),
            str(opportunity.architecture),
            str(opportunity.delegation_depth),
        ]
    )
