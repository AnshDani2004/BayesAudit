"""Typed asynchronous interfaces for BayesAudit components."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from bayesaudit.schemas import (
    AuditDecision,
    AuditFeedback,
    BenchmarkTask,
    BudgetState,
    MessageRecord,
    ModelResponse,
    MonitorEstimate,
    OversightObservation,
    PolicyState,
    ScoreResult,
    Trajectory,
    TrajectoryStep,
)


@runtime_checkable
class ModelClient(Protocol):
    """Provider-neutral interface for local, API, and mock models."""

    @property
    def model_id(self) -> str: ...

    async def complete(
        self,
        messages: list[MessageRecord],
        *,
        seed: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ModelResponse: ...


@runtime_checkable
class WorkflowArchitecture(Protocol):
    """Executes a task into a trajectory under a configured architecture."""

    @property
    def name(self) -> str: ...

    async def run(
        self,
        task: BenchmarkTask,
        model: ModelClient,
        *,
        experiment_id: str,
        run_id: str,
        seed: int,
    ) -> Trajectory: ...


@runtime_checkable
class OversightPolicy(Protocol):
    """Stateful oversight-policy lifecycle interface."""

    @property
    def name(self) -> str: ...

    async def initialize(
        self,
        task: BenchmarkTask,
        budget: BudgetState,
        *,
        seed: int,
    ) -> PolicyState: ...

    async def decide(
        self,
        observation: OversightObservation,
        state: PolicyState,
    ) -> AuditDecision: ...

    async def observe_feedback(
        self,
        feedback: AuditFeedback,
        state: PolicyState,
    ) -> PolicyState: ...


@runtime_checkable
class Scorer(Protocol):
    """Deterministic or validated scorer for a benchmark domain."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def score(self, task: BenchmarkTask, trajectory: Trajectory) -> ScoreResult: ...


@runtime_checkable
class Monitor(Protocol):
    """Automated monitor whose reliability must be validated."""

    @property
    def name(self) -> str: ...

    async def estimate(
        self,
        task: BenchmarkTask,
        trajectory: Trajectory,
        current_step: TrajectoryStep,
    ) -> MonitorEstimate: ...
