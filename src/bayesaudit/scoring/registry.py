"""Scorer registry."""

from __future__ import annotations

from bayesaudit.interfaces import Scorer
from bayesaudit.schemas import BenchmarkTask
from bayesaudit.scoring.authorization import AuthorizationScorer
from bayesaudit.scoring.budgeting import BudgetingScorer
from bayesaudit.scoring.evidence import EvidenceScorer
from bayesaudit.scoring.privacy import PrivacyScorer
from bayesaudit.scoring.protected_attributes import ProtectedAttributeScorer

SCORERS: dict[tuple[str, str], Scorer] = {
    ("evidence", "v1"): EvidenceScorer(),
    ("privacy", "v1"): PrivacyScorer(),
    ("budgeting", "v1"): BudgetingScorer(),
    ("authorization", "v1"): AuthorizationScorer(),
    ("protected_attributes", "v1"): ProtectedAttributeScorer(),
}


def scorer_for_task(task: BenchmarkTask) -> Scorer:
    key = (task.scoring.scorer_name, task.scoring.scorer_version)
    try:
        return SCORERS[key]
    except KeyError as exc:
        raise KeyError(f"unknown scorer {key[0]} {key[1]} for task {task.task_id}") from exc
