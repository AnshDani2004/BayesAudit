"""Atomic oversight budget reservation and consumption."""

from __future__ import annotations

from bayesaudit.oversight.types import BudgetTransaction, OversightBudgetState
from bayesaudit.schemas import BudgetUnit


class BudgetLedger:
    def __init__(
        self,
        *,
        policy_run_id: str,
        initial_budget: float,
        budget_unit: BudgetUnit | str = BudgetUnit.AUDIT_COUNT,
    ) -> None:
        self.policy_run_id = policy_run_id
        self.state = OversightBudgetState(
            initial_budget=initial_budget,
            remaining_budget=initial_budget,
            budget_unit=budget_unit,
        )
        self.transactions: list[BudgetTransaction] = []
        self._counter = 0

    def reserve(self, amount: float, *, observation_id: str | None, reason: str) -> bool:
        self._counter += 1
        before = self.state.remaining_budget
        success = amount <= self.state.remaining_budget
        if success:
            self.state.remaining_budget -= amount
            self.state.reserved_budget += amount
        else:
            self.state.rejected_actions_due_to_insufficient_budget += 1
        self.transactions.append(
            BudgetTransaction(
                transaction_id=f"{self.policy_run_id}_budget_{self._counter}",
                policy_run_id=self.policy_run_id,
                observation_id=observation_id,
                action="reserve",
                amount=amount,
                budget_before=before,
                budget_after=self.state.remaining_budget,
                reserved_after=self.state.reserved_budget,
                success=success,
                reason=reason,
            )
        )
        return success

    def consume_reserved(
        self, amount: float, *, observation_id: str | None, kind: str, reason: str
    ) -> bool:
        self._counter += 1
        before = self.state.remaining_budget
        success = amount <= self.state.reserved_budget
        if success:
            self.state.reserved_budget -= amount
            if kind == "audit":
                self.state.consumed_audit_cost += amount
                self.state.audit_count += 1
            elif kind == "intervention":
                self.state.consumed_intervention_cost += amount
                self.state.intervention_count += 1
            elif kind == "escalation":
                self.state.consumed_escalation_cost += amount
                self.state.escalation_count += 1
        else:
            self.state.budget_violations += 1
        self.transactions.append(
            BudgetTransaction(
                transaction_id=f"{self.policy_run_id}_budget_{self._counter}",
                policy_run_id=self.policy_run_id,
                observation_id=observation_id,
                action=f"consume_{kind}",
                amount=amount,
                budget_before=before,
                budget_after=self.state.remaining_budget,
                reserved_after=self.state.reserved_budget,
                success=success,
                reason=reason,
            )
        )
        return success

    def refund(self, amount: float, *, observation_id: str | None, reason: str) -> bool:
        self._counter += 1
        before = self.state.remaining_budget
        success = amount <= self.state.reserved_budget
        if success:
            self.state.reserved_budget -= amount
            self.state.remaining_budget += amount
        self.transactions.append(
            BudgetTransaction(
                transaction_id=f"{self.policy_run_id}_budget_{self._counter}",
                policy_run_id=self.policy_run_id,
                observation_id=observation_id,
                action="refund",
                amount=amount,
                budget_before=before,
                budget_after=self.state.remaining_budget,
                reserved_after=self.state.reserved_budget,
                success=success,
                reason=reason,
            )
        )
        return success

    def can_spend(self, amount: float) -> bool:
        return amount <= self.state.remaining_budget

    def finalize(self) -> OversightBudgetState:
        if self.state.reserved_budget:
            self.state.remaining_budget += self.state.reserved_budget
            self.state.reserved_budget = 0.0
        self.state.final_reconciled = True
        return self.state

