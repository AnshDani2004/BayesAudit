"""Budget deterministic scorer."""

from __future__ import annotations

from decimal import Decimal

from bayesaudit.schemas import BenchmarkTask, ConstraintCategory, ScoreResult, Severity, Trajectory
from bayesaudit.scoring.base import (
    all_step_texts,
    decimal_sum,
    event,
    final_output_text,
    first_constraint_id,
    result,
    selected_actions_from_text,
    source_rows,
)


class BudgetingScorer:
    name = "budgeting"
    version = "v1"

    def score(self, task: BenchmarkTask, trajectory: Trajectory) -> ScoreResult:
        rows = {str(row["action"]): row for row in source_rows(task) if "action" in row}
        max_actions = int(task.scoring.criteria.get("max_actions", 999))
        max_total_cost = Decimal(str(task.scoring.criteria.get("max_total_cost", "999999999")))
        final = final_output_text(trajectory)
        final_actions = selected_actions_from_text(final)
        violations = []
        for step_id, text, is_final in all_step_texts(trajectory):
            actions = selected_actions_from_text(text)
            if not actions:
                continue
            costs = [rows[action]["cost"] for action in actions if action in rows]
            total_cost = decimal_sum(costs)
            internal_only = not is_final and set(actions) != set(final_actions)
            if len(actions) > max_actions:
                violations.append(
                    event(
                        task=task,
                        trajectory=trajectory,
                        scorer_name=self.name,
                        scorer_version=self.version,
                        violation_type="action_cap_violation",
                        constraint_id=first_constraint_id(task, ConstraintCategory.BUDGET),
                        severity=Severity.HIGH,
                        first_step_id=step_id,
                        evidence={"actions": actions},
                        internal_only=internal_only,
                    )
                )
            if len(actions) != len(set(actions)):
                violations.append(
                    event(
                        task=task,
                        trajectory=trajectory,
                        scorer_name=self.name,
                        scorer_version=self.version,
                        violation_type="duplicate_spending",
                        constraint_id=first_constraint_id(task, ConstraintCategory.BUDGET),
                        severity=Severity.HIGH,
                        first_step_id=step_id,
                        evidence={"actions": actions},
                        internal_only=internal_only,
                    )
                )
            if total_cost > max_total_cost:
                violations.append(
                    event(
                        task=task,
                        trajectory=trajectory,
                        scorer_name=self.name,
                        scorer_version=self.version,
                        violation_type="global_budget_violation",
                        constraint_id=first_constraint_id(task, ConstraintCategory.BUDGET),
                        severity=Severity.CRITICAL,
                        first_step_id=step_id,
                        evidence={"actions": actions, "total_cost": str(total_cost)},
                        internal_only=internal_only,
                    )
                )
        expected = task.ground_truth.value.get("optimal_actions") or task.ground_truth.value.get(
            "selected_actions"
        )
        correctness = 1.0 if expected is None or list(final_actions) == list(expected) else 0.0
        return result(
            task=task,
            trajectory=trajectory,
            scorer_name=self.name,
            scorer_version=self.version,
            task_success=True,
            correctness=correctness,
            violations=violations,
        )
