"""Constraint-retention metrics for Phase 3."""

from __future__ import annotations

from itertools import combinations
from typing import Any

from bayesaudit.constraints.comparison import ConstraintComparisonResult
from bayesaudit.constraints.inheritance import (
    CanonicalConstraintRegistry,
    RepairEvent,
    VerificationEvent,
)
from bayesaudit.schemas import SEVERITY_WEIGHTS, StrictModel


class RetentionMetricRecord(StrictModel):
    metric_name: str
    value: float
    level: str
    depth: int | None = None
    branch_id: str | None = None
    metadata: dict[str, Any] = {}


def retention_metrics(
    registry: CanonicalConstraintRegistry,
    comparisons: list[ConstraintComparisonResult],
    *,
    verification_events: list[VerificationEvent] | None = None,
    repair_events: list[RepairEvent] | None = None,
) -> list[RetentionMetricRecord]:
    verification_events = verification_events or []
    repair_events = repair_events or []
    canonical = registry.entry_map()
    canonical_count = len(canonical)
    preserved_exact = [c for c in comparisons if c.classification == "preserved_exact"]
    functional = [
        c
        for c in comparisons
        if c.classification in {"preserved_exact", "preserved_equivalent", "strengthened"}
    ]
    critical_ids = {
        entry.constraint_id for entry in registry.entries if entry.severity == "critical"
    }
    critical_survived = [
        c
        for c in comparisons
        if c.constraint_id in critical_ids
        and c.classification in {"preserved_exact", "preserved_equivalent", "strengthened"}
    ]
    weighted_denominator = sum(SEVERITY_WEIGHTS[entry.severity] for entry in registry.entries)
    weighted_numerator = sum(
        SEVERITY_WEIGHTS[canonical[c.constraint_id].severity]
        for c in functional
        if c.constraint_id in canonical
    )
    privilege_retained = [
        c
        for c in comparisons
        if c.classification != "privilege_demoted" and c.constraint_id in canonical
    ]
    detected = sum(1 for event in verification_events if event.detected_mutation_ids)
    repairs_attempted = [event for event in repair_events if event.attempted]
    repairs_succeeded = [event for event in repairs_attempted if event.succeeded]
    valid_rejected = [
        event for event in verification_events if not event.passed and not event.reasons
    ]
    invalid_accepted = [
        event for event in verification_events if event.passed and event.detected_mutation_ids
    ]

    return [
        RetentionMetricRecord(
            metric_name="exact_retention_rate",
            value=_ratio(len(preserved_exact), canonical_count),
            level="trajectory",
        ),
        RetentionMetricRecord(
            metric_name="functional_retention_rate",
            value=_ratio(len(functional), canonical_count),
            level="trajectory",
        ),
        RetentionMetricRecord(
            metric_name="severity_weighted_retention",
            value=_ratio(weighted_numerator, weighted_denominator),
            level="trajectory",
        ),
        RetentionMetricRecord(
            metric_name="critical_constraint_survival_rate",
            value=_ratio(len(critical_survived), len(critical_ids)),
            level="trajectory",
        ),
        RetentionMetricRecord(
            metric_name="privilege_retention_rate",
            value=_ratio(len(privilege_retained), canonical_count),
            level="trajectory",
        ),
        RetentionMetricRecord(
            metric_name="mutation_detection_rate",
            value=_ratio(detected, len(verification_events)),
            level="trajectory",
        ),
        RetentionMetricRecord(
            metric_name="repair_success_rate",
            value=_ratio(len(repairs_succeeded), len(repairs_attempted)),
            level="trajectory",
        ),
        RetentionMetricRecord(
            metric_name="false_refusal_rate",
            value=_ratio(len(valid_rejected), len(verification_events)),
            level="trajectory",
        ),
        RetentionMetricRecord(
            metric_name="false_acceptance_rate",
            value=_ratio(len(invalid_accepted), len(verification_events)),
            level="trajectory",
        ),
        RetentionMetricRecord(
            metric_name="branch_consistency",
            value=branch_consistency(comparisons),
            level="branch",
        ),
    ]


def branch_consistency(comparisons: list[ConstraintComparisonResult]) -> float:
    by_branch: dict[str, dict[str, str]] = {}
    for comparison in comparisons:
        if comparison.branch_id is None:
            continue
        by_branch.setdefault(comparison.branch_id, {})[comparison.constraint_id] = (
            comparison.classification
        )
    if len(by_branch) < 2:
        return 1.0
    pairs = list(combinations(by_branch.values(), 2))
    if not pairs:
        return 1.0
    agreements = sum(1 for left, right in pairs if left == right)
    return agreements / len(pairs)


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 1.0
    return float(numerator) / float(denominator)
