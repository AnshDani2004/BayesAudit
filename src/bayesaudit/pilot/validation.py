"""Pilot scorer validation and readiness helpers."""

from __future__ import annotations

from collections import Counter

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.types import ReadinessRecord, ScorerHumanComparisonRecord


def compare_scorer_to_human(
    *,
    trajectory_id: str,
    domain: str,
    automated_positive: bool,
    human_positive: bool,
    disagreement_type: str | None = None,
    scorer_error_category: str | None = None,
) -> ScorerHumanComparisonRecord:
    agreement = automated_positive == human_positive
    return ScorerHumanComparisonRecord(
        comparison_id="cmp_"
        + canonical_json_hash(
            {
                "trajectory": trajectory_id,
                "domain": domain,
                "automated": automated_positive,
                "human": human_positive,
            }
        )[:20],
        trajectory_id=trajectory_id,
        domain=domain,
        automated_scorer_result="positive" if automated_positive else "negative",
        human_label="positive" if human_positive else "negative",
        agreement=agreement,
        disagreement_type=None if agreement else disagreement_type or "unspecified_disagreement",
        scorer_error_category=None if agreement else scorer_error_category or "needs_review",
        recommended_correction=None if agreement else "inspect task and scorer before freeze",
        responsible_component="unknown" if agreement else "scorer",
    )


def readiness_counts(records: list[ReadinessRecord]) -> dict[str, int]:
    return dict(Counter(record.category for record in records))


def default_task_readiness(task_ids: list[str]) -> list[ReadinessRecord]:
    return [
        ReadinessRecord(
            item_id=task_id,
            item_type="task",
            category="ready_after_minor_repair",
            rationale=(
                "pilot infrastructure generated a pre-review placeholder; "
                "human review required"
            ),
        )
        for task_id in task_ids
    ]


def default_scorer_readiness(domains: list[str]) -> list[ReadinessRecord]:
    return [
        ReadinessRecord(
            item_id=f"{domain}_scorer",
            item_type="scorer",
            category="ready_after_minor_repair",
            rationale="deterministic scorer exists; real-trace human agreement still required",
        )
        for domain in sorted(set(domains))
    ]
