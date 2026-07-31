"""Heuristic workflow-quality checks for real-model pilot traces."""

from __future__ import annotations

from bayesaudit.pilot.types import WorkflowQualityRecord
from bayesaudit.schemas import Trajectory, WorkflowStepKind


def workflow_quality_flags(trajectory: Trajectory) -> WorkflowQualityRecord:
    steps = trajectory.steps
    delegation_steps = [step for step in steps if step.kind == WorkflowStepKind.DELEGATION]
    final_steps = [step for step in steps if step.kind == WorkflowStepKind.FINAL_OUTPUT]
    flags: list[str] = []
    if not delegation_steps and trajectory.architecture != "single_agent":
        flags.append("empty_delegation")
    if _prompt_echo(steps):
        flags.append("prompt_echo")
    if _identical_planner_worker(steps):
        flags.append("identical_planner_and_worker_outputs")
    if (
        final_steps
        and delegation_steps
        and not _final_references_worker(final_steps[-1], delegation_steps)
    ):
        flags.append("aggregator_ignores_worker")
    if _repeated_tool_request(steps):
        flags.append("repeated_tool_request")
    if final_steps and not delegation_steps and trajectory.architecture != "single_agent":
        flags.append("premature_final_answer")
    if any(step.branch_id and step.parent_step_id is None for step in steps):
        flags.append("invalid_branch_reference")
    worker_outputs = {
        step.model_response.message.content
        for step in delegation_steps
        if step.model_response is not None
    }
    if len(worker_outputs) == 1 and len(delegation_steps) > 1:
        flags.append("identical_branch_outputs")
    metrics = {
        "delegation_step_count": float(len(delegation_steps)),
        "final_step_count": float(len(final_steps)),
        "structured_output_validity_rate": 1.0
        if all(step.model_response is not None for step in steps)
        else 0.0,
        "flag_count": float(len(flags)),
    }
    return WorkflowQualityRecord(
        trajectory_id=trajectory.trajectory_id,
        flags=sorted(set(flags)),
        metrics=metrics,
    )


def _prompt_echo(steps) -> bool:  # type: ignore[no-untyped-def]
    for step in steps:
        if step.model_response is None or not step.input_messages:
            continue
        input_text = " ".join(message.content for message in step.input_messages).strip()
        output = step.model_response.message.content.strip()
        if input_text and input_text[:80] in output:
            return True
    return False


def _identical_planner_worker(steps) -> bool:  # type: ignore[no-untyped-def]
    planner_outputs = {
        step.model_response.message.content
        for step in steps
        if step.role == "planner" and step.model_response is not None
    }
    worker_outputs = {
        step.model_response.message.content
        for step in steps
        if step.role == "worker" and step.model_response is not None
    }
    return bool(planner_outputs.intersection(worker_outputs))


def _final_references_worker(final_step, delegation_steps) -> bool:  # type: ignore[no-untyped-def]
    if final_step.input_messages:
        final_input = " ".join(message.content for message in final_step.input_messages)
        return any(
            step.model_response is not None
            and step.model_response.message.content[:40] in final_input
            for step in delegation_steps
        )
    return False


def _repeated_tool_request(steps) -> bool:  # type: ignore[no-untyped-def]
    seen: set[tuple[str, str]] = set()
    for step in steps:
        for call in step.tool_calls:
            key = (call.tool_name, str(call.arguments))
            if key in seen:
                return True
            seen.add(key)
    return False
