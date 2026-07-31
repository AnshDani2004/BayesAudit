"""Single-agent Phase 2 workflow."""

from __future__ import annotations

from datetime import datetime, timezone

from bayesaudit.architectures.common import add_usage, make_trajectory, tool_requests_from_response
from bayesaudit.constraints.snapshots import snapshot_constraints
from bayesaudit.interfaces import ModelClient
from bayesaudit.models.mock import MockModel
from bayesaudit.schemas import (
    ArchitectureKind,
    BenchmarkTask,
    MessageRecord,
    Trajectory,
    TrajectoryStatus,
    TrajectoryStep,
    WorkflowStepKind,
)
from bayesaudit.tools.environment import ToolEnvironment


class SingleAgentWorkflow:
    @property
    def name(self) -> str:
        return ArchitectureKind.SINGLE_AGENT.value

    async def run(
        self,
        task: BenchmarkTask,
        model: ModelClient,
        *,
        experiment_id: str,
        run_id: str,
        seed: int,
    ) -> Trajectory:
        if not isinstance(model, MockModel):
            raise TypeError("Phase 2 workflows support MockModel only")
        trajectory = make_trajectory(
            task=task,
            model=model,
            architecture=ArchitectureKind.SINGLE_AGENT,
            experiment_id=experiment_id,
            run_id=run_id,
            seed=seed,
        )
        environment = ToolEnvironment(task)
        snapshots = snapshot_constraints(
            task.constraints,
            current_source_level=0,
            inherited_from_step_id=None,
            acknowledged=True,
        )
        prompt = MessageRecord(
            role="user",
            content=f"{task.description}\nConstraints: "
            + "; ".join(c.rule for c in task.constraints),
            agent_id="agent_root",
        )
        response = await model.complete(
            [prompt],
            seed=seed,
            metadata={
                "agent_id": "agent_root",
                "step_kind": WorkflowStepKind.REASONING.value,
                "task_id": task.task_id,
            },
        )
        tool_calls = []
        for index, request in enumerate(
            tool_requests_from_response(response.raw_metadata), start=1
        ):
            raw_arguments = request.get("arguments")
            arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
            raw_approval = request.get("approval_reference")
            approval_reference = raw_approval if isinstance(raw_approval, str) else None
            tool_calls.append(
                environment.execute(
                    tool_call_id=f"{run_id}_tool_{index}",
                    tool_name=str(request.get("tool_name", "")),
                    arguments=arguments,
                    requested_by_agent="agent_root",
                    approval_reference=approval_reference,
                )
            )
        trajectory.steps.append(
            TrajectoryStep(
                step_id=f"{run_id}_step_001",
                sequence_index=1,
                agent_id="agent_root",
                role="single_agent",
                depth=0,
                kind=WorkflowStepKind.REASONING,
                input_messages=[prompt],
                model_response=response,
                constraint_snapshots=snapshots,
                tool_calls=tool_calls,
            )
        )
        final_response = await model.complete(
            [response.message],
            seed=seed,
            metadata={
                "agent_id": "agent_root",
                "step_kind": WorkflowStepKind.FINAL_OUTPUT.value,
                "task_id": task.task_id,
            },
        )
        trajectory.steps.append(
            TrajectoryStep(
                step_id=f"{run_id}_step_002",
                sequence_index=2,
                parent_step_id=f"{run_id}_step_001",
                agent_id="agent_root",
                role="single_agent",
                depth=0,
                kind=WorkflowStepKind.FINAL_OUTPUT,
                input_messages=[response.message],
                model_response=final_response,
                constraint_snapshots=snapshots,
            )
        )
        trajectory.status = TrajectoryStatus.COMPLETED
        trajectory.completed_at = datetime.now(timezone.utc)
        add_usage(trajectory)
        return Trajectory.model_validate(trajectory.model_dump())
