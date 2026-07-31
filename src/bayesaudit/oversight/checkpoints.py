"""Oversight checkpoint extraction from completed synthetic trajectories."""

from __future__ import annotations

from bayesaudit.oversight.types import CheckpointType, OversightCheckpoint
from bayesaudit.schemas import OversightAction, Trajectory, WorkflowStepKind


def checkpoints_for_trajectory(trajectory: Trajectory) -> list[OversightCheckpoint]:
    checkpoints: list[OversightCheckpoint] = []
    for step in trajectory.steps:
        kind = str(step.kind)
        if kind == WorkflowStepKind.PLANNING.value:
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.BEFORE_PLANNING,
                    True,
                    True,
                    [OversightAction.CONTINUE.value, OversightAction.REQUEST_CLARIFICATION.value],
                )
            )
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.AFTER_PLANNING,
                    True,
                    True,
                    [OversightAction.CONTINUE.value, OversightAction.REQUEST_CLARIFICATION.value],
                )
            )
        if kind == WorkflowStepKind.DELEGATION.value:
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.BEFORE_DELEGATION,
                    True,
                    True,
                    [OversightAction.CONTINUE.value, OversightAction.BLOCK.value],
                )
            )
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.AFTER_DELEGATION,
                    True,
                    False,
                    [OversightAction.CONTINUE.value, OversightAction.ESCALATE.value],
                )
            )
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.ON_CHILD_RESULT,
                    True,
                    False,
                    [OversightAction.CONTINUE.value, OversightAction.ESCALATE.value],
                )
            )
        if step.tool_calls:
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.BEFORE_TOOL_REQUEST,
                    True,
                    True,
                    [
                        OversightAction.CONTINUE.value,
                        OversightAction.BLOCK.value,
                        OversightAction.ESCALATE.value,
                    ],
                )
            )
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.AFTER_TOOL_RESULT,
                    True,
                    False,
                    [OversightAction.CONTINUE.value, OversightAction.ESCALATE.value],
                )
            )
        if kind == WorkflowStepKind.FINAL_OUTPUT.value:
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.BEFORE_AGGREGATION,
                    True,
                    True,
                    [OversightAction.CONTINUE.value, OversightAction.REQUEST_CLARIFICATION.value],
                )
            )
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.BEFORE_FINAL_OUTPUT,
                    True,
                    True,
                    [OversightAction.CONTINUE.value, OversightAction.BLOCK.value],
                )
            )
        if step.metadata.get("branch_refused"):
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.ON_BRANCH_REFUSAL,
                    True,
                    False,
                    [OversightAction.CONTINUE.value, OversightAction.ESCALATE.value],
                    mandatory=True,
                )
            )
        if step.metadata.get("verification_event_id"):
            checkpoints.append(
                _checkpoint(
                    trajectory.run_id,
                    step.step_id,
                    step.sequence_index,
                    CheckpointType.ON_VERIFICATION_FAILURE,
                    True,
                    False,
                    [OversightAction.CONTINUE.value, OversightAction.ESCALATE.value],
                    mandatory=True,
                )
            )
    return sorted(
        checkpoints,
        key=lambda checkpoint: (checkpoint.sequence_index, checkpoint.checkpoint_type),
    )


def _checkpoint(
    run_id: str,
    step_id: str,
    sequence_index: int,
    checkpoint_type: str,
    audit_eligible: bool,
    intervention_still_possible: bool,
    available_actions: list[str],
    *,
    mandatory: bool = False,
) -> OversightCheckpoint:
    return OversightCheckpoint(
        checkpoint_id=f"{run_id}_{step_id}_{checkpoint_type}",
        checkpoint_type=checkpoint_type,
        step_id=step_id,
        sequence_index=sequence_index,
        audit_eligible=audit_eligible,
        intervention_still_possible=intervention_still_possible,
        available_actions=available_actions,
        default_action_if_budget_exhausted=OversightAction.CONTINUE.value,
        audit_cost=1.0,
        intervention_cost=1.0,
        mandatory=mandatory,
    )
