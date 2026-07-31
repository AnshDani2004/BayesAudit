"""Unstructured deterministic planner-worker hierarchy for Phase 2."""

from __future__ import annotations

from datetime import datetime, timezone

from bayesaudit.architectures.common import add_usage, make_trajectory, tool_requests_from_response
from bayesaudit.constraints.mutations import MutationProfile, MutationSchedule
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


class UnstructuredDelegationWorkflow:
    def __init__(
        self,
        *,
        max_depth: int | None = None,
        branching_factor: int | None = None,
        mutation_schedule: MutationSchedule | None = None,
    ) -> None:
        self.max_depth = max_depth
        self.branching_factor = branching_factor
        self.mutation_schedule = mutation_schedule or MutationSchedule()

    @property
    def name(self) -> str:
        return ArchitectureKind.UNSTRUCTURED_DELEGATION.value

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
        max_depth = (
            self.max_depth if self.max_depth is not None else max(1, task.delegation.max_depth)
        )
        branching_factor = self.branching_factor or task.delegation.planned_branching_factor
        trajectory = make_trajectory(
            task=task,
            model=model,
            architecture=ArchitectureKind.UNSTRUCTURED_DELEGATION,
            experiment_id=experiment_id,
            run_id=run_id,
            seed=seed,
        )
        environment = ToolEnvironment(task)
        mutation_events: list[dict[str, object]] = []
        sequence = 1

        root_prompt = MessageRecord(role="user", content=task.description, agent_id="planner")
        root_response = await model.complete(
            [root_prompt],
            seed=seed,
            metadata={
                "agent_id": "planner",
                "step_kind": WorkflowStepKind.PLANNING.value,
                "task_id": task.task_id,
            },
        )
        root_step_id = f"{run_id}_step_{sequence:03d}"
        root_snapshots = snapshot_constraints(
            task.constraints, current_source_level=0, inherited_from_step_id=None
        )
        trajectory.steps.append(
            TrajectoryStep(
                step_id=root_step_id,
                sequence_index=sequence,
                agent_id="planner",
                role="planner",
                depth=0,
                kind=WorkflowStepKind.PLANNING,
                input_messages=[root_prompt],
                model_response=root_response,
                constraint_snapshots=root_snapshots,
            )
        )

        async def add_children(
            parent_step_id: str, parent_agent_id: str, depth: int, branch_prefix: str
        ) -> list[str]:
            nonlocal sequence
            if depth > max_depth:
                return []
            child_outputs: list[str] = []
            for branch in range(branching_factor):
                sequence += 1
                agent_id = f"worker_d{depth}_b{branch_prefix}{branch}"
                branch_id = f"{branch_prefix}{branch}"
                scheduled = self.mutation_schedule.for_step("delegation", branch_id=branch_id)
                dropped = set(model.script.drop_constraint_ids) if depth == 1 else set()
                weakened = set(model.script.weaken_constraint_ids) if depth == 1 else set()
                strengthened: set[str] = set()
                paraphrased: set[str] = set()
                contradicted: set[str] = set()
                for profile in scheduled:
                    target = _target_constraint_id(task, profile)
                    if profile.mutation_type in {"drop_constraint", "remove_constraint_entry"}:
                        dropped.add(target)
                    elif profile.mutation_type == "weaken_constraint":
                        weakened.add(target)
                    elif profile.mutation_type == "strengthen_constraint":
                        strengthened.add(target)
                    elif profile.mutation_type == "paraphrase_equivalent":
                        paraphrased.add(target)
                    elif profile.mutation_type in {
                        "contradict_constraint",
                        "replace_with_unrelated_rule",
                    }:
                        contradicted.add(target)
                    mutation_events.append(
                        _unstructured_mutation_event(
                            profile, step_id=f"{run_id}_step_{sequence:03d}", seed=seed + sequence
                        )
                    )
                snapshots = snapshot_constraints(
                    task.constraints,
                    current_source_level=depth,
                    inherited_from_step_id=parent_step_id,
                    dropped_constraint_ids=dropped,
                    weakened_constraint_ids=weakened,
                    strengthened_constraint_ids=strengthened,
                    paraphrased_constraint_ids=paraphrased,
                    contradicted_constraint_ids=contradicted,
                    acknowledged=False,
                )
                visible_constraints = "; ".join(
                    snapshot.visible_rule for snapshot in snapshots if snapshot.visible_rule
                )
                message = MessageRecord(
                    role="user",
                    content=f"Delegated subtask depth {depth}. Constraints: {visible_constraints}",
                    agent_id=agent_id,
                )
                response = await model.complete(
                    [message],
                    seed=seed + sequence,
                    metadata={
                        "agent_id": agent_id,
                        "step_kind": WorkflowStepKind.DELEGATION.value,
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
                            tool_call_id=f"{run_id}_tool_{sequence}_{index}",
                            tool_name=str(request.get("tool_name", "")),
                            arguments=arguments,
                            requested_by_agent=agent_id,
                            approval_reference=approval_reference,
                        )
                    )
                step_id = f"{run_id}_step_{sequence:03d}"
                trajectory.steps.append(
                    TrajectoryStep(
                        step_id=step_id,
                        sequence_index=sequence,
                        parent_step_id=parent_step_id,
                        delegation_id=f"{run_id}_delegation_{depth}",
                        branch_id=branch_id,
                        agent_id=agent_id,
                        parent_agent_id=parent_agent_id,
                        role="worker",
                        depth=depth,
                        kind=WorkflowStepKind.DELEGATION,
                        input_messages=[message],
                        model_response=response,
                        constraint_snapshots=snapshots,
                        tool_calls=tool_calls,
                    )
                )
                child_outputs.append(response.message.content)
                child_outputs.extend(
                    await add_children(step_id, agent_id, depth + 1, f"{branch_id}.")
                )
            return child_outputs

        child_outputs = await add_children(root_step_id, "planner", 1, "")
        sequence += 1
        combine_prompt = MessageRecord(
            role="user", content="\n".join(child_outputs), agent_id="planner"
        )
        final_response = await model.complete(
            [combine_prompt],
            seed=seed,
            metadata={
                "agent_id": "planner",
                "step_kind": WorkflowStepKind.FINAL_OUTPUT.value,
                "task_id": task.task_id,
            },
        )
        trajectory.steps.append(
            TrajectoryStep(
                step_id=f"{run_id}_step_{sequence:03d}",
                sequence_index=sequence,
                parent_step_id=root_step_id,
                agent_id="planner",
                role="planner",
                depth=0,
                kind=WorkflowStepKind.FINAL_OUTPUT,
                input_messages=[combine_prompt],
                model_response=final_response,
                constraint_snapshots=root_snapshots,
            )
        )
        trajectory.status = TrajectoryStatus.COMPLETED
        trajectory.completed_at = datetime.now(timezone.utc)
        if mutation_events:
            trajectory.metadata["inheritance"] = {
                "mutation_events": mutation_events,
                "note": "unstructured delegation has no typed envelopes",
            }
        add_usage(trajectory)
        return Trajectory.model_validate(trajectory.model_dump())


def _target_constraint_id(task: BenchmarkTask, profile: MutationProfile) -> str:
    if profile.target_constraint_id:
        return profile.target_constraint_id
    return task.constraints[0].id


def _unstructured_mutation_event(
    profile: MutationProfile, *, step_id: str, seed: int
) -> dict[str, object]:
    return {
        "schema_version": "bayesaudit.inheritance.v1",
        "mutation_id": f"mutation_{profile.name}_{step_id}_{seed}",
        "mutation_type": profile.mutation_type,
        "target_constraint_id": profile.target_constraint_id,
        "target_step_id": step_id,
        "scheduled_step": profile.scheduled_step,
        "actual_applied_step": step_id,
        "deterministic_seed": seed,
        "injection_source": "phase3_mutation_schedule",
        "expected_retention_classification": profile.expected_retention_classification,
        "metadata": profile.metadata,
    }
