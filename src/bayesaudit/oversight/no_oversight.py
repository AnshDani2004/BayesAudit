"""No-oversight baseline policy for Phase 2 execution contracts."""

from __future__ import annotations

from bayesaudit.schemas import (
    AuditDecision,
    AuditFeedback,
    BenchmarkTask,
    BudgetState,
    OversightAction,
    OversightObservation,
    PolicyState,
)


class NoOversightPolicy:
    @property
    def name(self) -> str:
        return "no_oversight"

    async def initialize(
        self, task: BenchmarkTask, budget: BudgetState, *, seed: int
    ) -> PolicyState:
        return PolicyState(
            policy_name=self.name, budget=budget, seed=seed, state={"task_id": task.task_id}
        )

    async def decide(self, observation: OversightObservation, state: PolicyState) -> AuditDecision:
        return AuditDecision(
            action=OversightAction.CONTINUE,
            reason="No oversight configured.",
            policy_name=self.name,
        )

    async def observe_feedback(self, feedback: AuditFeedback, state: PolicyState) -> PolicyState:
        return state
