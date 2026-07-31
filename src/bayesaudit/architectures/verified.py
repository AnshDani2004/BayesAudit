"""Verified constraint inheritance workflow."""

from __future__ import annotations

from bayesaudit.architectures.inheritance_common import InheritanceWorkflowBase
from bayesaudit.constraints.inheritance import VerificationResponse
from bayesaudit.constraints.mutations import MutationSchedule
from bayesaudit.schemas import ArchitectureKind


class VerifiedInheritanceWorkflow(InheritanceWorkflowBase):
    def __init__(
        self,
        *,
        max_depth: int | None = None,
        branching_factor: int | None = None,
        mutation_schedule: MutationSchedule | None = None,
        verification_response: str = VerificationResponse.REFUSE_SUBTASK,
    ) -> None:
        super().__init__(
            architecture=ArchitectureKind.VERIFIED_INHERITANCE,
            max_depth=max_depth,
            branching_factor=branching_factor,
            mutation_schedule=mutation_schedule,
            verification_response=verification_response,
        )
