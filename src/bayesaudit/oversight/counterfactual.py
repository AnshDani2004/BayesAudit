"""Counterfactual outcome helpers for paired oversight evaluations."""

from __future__ import annotations

from bayesaudit.oversight.types import CounterfactualOutcome
from bayesaudit.schemas import ScoreResult


def compare_counterfactual_pair(
    baseline: ScoreResult | None,
    intervention: ScoreResult | None,
    *,
    pair_id: str,
    baseline_run_id: str,
    intervention_run_id: str,
    shared_experimental_key: str,
    additional_cost: float = 0.0,
) -> CounterfactualOutcome:
    baseline_has_violation = bool(baseline and baseline.violations)
    intervention_has_violation = bool(intervention and intervention.violations)
    valid = baseline is not None and intervention is not None
    target = baseline.violations[0].violation_id if baseline and baseline.violations else None
    utility_difference = (
        intervention.utility_score - baseline.utility_score
        if baseline is not None and intervention is not None
        else 0.0
    )
    return CounterfactualOutcome(
        pair_id=pair_id,
        baseline_run_id=baseline_run_id,
        intervention_run_id=intervention_run_id,
        shared_experimental_key=shared_experimental_key,
        target_violation_id=target,
        violation_occurred_in_baseline=baseline_has_violation,
        violation_occurred_under_intervention=intervention_has_violation,
        prevented=(baseline_has_violation and not intervention_has_violation) if valid else None,
        changed_violation_type=_changed_type(baseline, intervention),
        changed_severity=_changed_severity(baseline, intervention),
        utility_difference=utility_difference,
        additional_cost=additional_cost,
        counterfactual_validity_status="valid" if valid else "unknown",
    )


def _changed_type(baseline: ScoreResult | None, intervention: ScoreResult | None) -> bool:
    if not baseline or not intervention or not baseline.violations or not intervention.violations:
        return False
    return baseline.violations[0].violation_type != intervention.violations[0].violation_type


def _changed_severity(baseline: ScoreResult | None, intervention: ScoreResult | None) -> bool:
    if not baseline or not intervention or not baseline.violations or not intervention.violations:
        return False
    return str(baseline.violations[0].severity) != str(intervention.violations[0].severity)
