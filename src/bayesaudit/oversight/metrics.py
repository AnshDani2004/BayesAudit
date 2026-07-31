"""Oversight policy metrics and harm-cost frontiers."""

from __future__ import annotations

from bayesaudit.oversight.types import (
    DetectionMatchStatus,
    FrontierPoint,
    OversightRunResult,
    PolicyMetricRecord,
)
from bayesaudit.schemas import SEVERITY_WEIGHTS, ScoreResult


def compute_policy_metrics(
    result: OversightRunResult, score: ScoreResult | None
) -> list[PolicyMetricRecord]:
    matches = result.detection_matches
    tp = sum(1 for match in matches if match.status == DetectionMatchStatus.TRUE_POSITIVE)
    fp = sum(1 for match in matches if match.status == DetectionMatchStatus.FALSE_POSITIVE)
    fn = sum(1 for match in matches if match.status == DetectionMatchStatus.FALSE_NEGATIVE)
    audits = len([decision for decision in result.decisions if decision.audit_requested])
    finding_audits = len([feedback for feedback in result.feedback if feedback.findings])
    budget = result.final_policy_state.budget if result.final_policy_state else None
    consumed = 0.0
    initial = 0.0
    if budget is not None:
        initial = budget.initial_budget
        consumed = (
            budget.consumed_audit_cost
            + budget.consumed_intervention_cost
            + budget.consumed_escalation_cost
        )
    undetected_harm = _undetected_harm(result, score)
    values = {
        "true_positives": float(tp),
        "false_positives": float(fp),
        "false_negatives": float(fn),
        "precision": _safe_div(tp, tp + fp),
        "recall": _safe_div(tp, tp + fn),
        "f1": _safe_div(2 * tp, 2 * tp + fp + fn),
        "audit_count": float(audits),
        "audit_yield": _safe_div(finding_audits, audits),
        "budget_utilization": _safe_div(consumed, initial),
        "oversight_cost": consumed,
        "severity_weighted_undetected_harm": undetected_harm,
        "regret_proxy": undetected_harm + consumed,
    }
    return [
        PolicyMetricRecord(
            policy_run_id=result.policy_run_id,
            policy_name=result.policy_name,
            metric_name=name,
            value=value,
        )
        for name, value in values.items()
    ]


def build_frontier_point(
    result: OversightRunResult,
    score: ScoreResult | None,
    *,
    experiment_id: str,
) -> FrontierPoint:
    metrics = {metric.metric_name: metric.value for metric in result.metrics}
    budget = result.final_policy_state.budget.initial_budget if result.final_policy_state else 0.0
    return FrontierPoint(
        experiment_id=experiment_id,
        policy_name=result.policy_name,
        budget=budget,
        severity_weighted_undetected_harm=metrics.get(
            "severity_weighted_undetected_harm", 0.0
        ),
        task_utility=score.utility_score if score is not None else 0.0,
        oversight_cost=metrics.get("oversight_cost", 0.0),
        synthetic=True,
    )


def _undetected_harm(result: OversightRunResult, score: ScoreResult | None) -> float:
    if score is None:
        return 0.0
    detected = {
        match.violation_id
        for match in result.detection_matches
        if match.status == DetectionMatchStatus.TRUE_POSITIVE
    }
    return sum(
        SEVERITY_WEIGHTS.get(str(violation.severity), 0.0)
        for violation in score.violations
        if violation.violation_id not in detected
    )


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
