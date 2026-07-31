"""Shared machinery for structured and verified inheritance workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bayesaudit.architectures.common import add_usage, make_trajectory, tool_requests_from_response
from bayesaudit.constraints.comparison import compare_envelope
from bayesaudit.constraints.inheritance import (
    AggregationProvenance,
    CanonicalConstraintRegistry,
    ConstraintEnvelope,
    RepairEvent,
    VerificationEvent,
    VerificationResponse,
    build_registry,
    create_envelope,
    envelope_to_snapshots,
    verify_envelope,
)
from bayesaudit.constraints.metrics import RetentionMetricRecord, retention_metrics
from bayesaudit.constraints.mutations import MutationSchedule, apply_schedule
from bayesaudit.interfaces import ModelClient
from bayesaudit.models.mock import MockModel
from bayesaudit.schemas import (
    ArchitectureKind,
    BenchmarkTask,
    ErrorRecord,
    MessageRecord,
    Trajectory,
    TrajectoryStatus,
    TrajectoryStep,
    WorkflowStepKind,
)
from bayesaudit.tools.environment import ToolEnvironment


class InheritanceRunArtifacts:
    def __init__(self, registry: CanonicalConstraintRegistry) -> None:
        self.registry = registry
        self.envelopes: list[ConstraintEnvelope] = []
        self.mutations: list[Any] = []
        self.verifications: list[VerificationEvent] = []
        self.repairs: list[RepairEvent] = []
        self.comparisons: list[Any] = []
        self.metrics: list[RetentionMetricRecord] = []
        self.aggregation: AggregationProvenance | None = None


class InheritanceWorkflowBase:
    def __init__(
        self,
        *,
        architecture: ArchitectureKind,
        max_depth: int | None = None,
        branching_factor: int | None = None,
        mutation_schedule: MutationSchedule | None = None,
        verification_response: str = VerificationResponse.REFUSE_SUBTASK,
    ) -> None:
        self.architecture = architecture
        self.max_depth = max_depth
        self.branching_factor = branching_factor
        self.mutation_schedule = mutation_schedule or MutationSchedule()
        self.verification_response = verification_response

    @property
    def name(self) -> str:
        return self.architecture.value

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
            raise TypeError("Phase 3 workflows support MockModel only")
        max_depth = (
            self.max_depth if self.max_depth is not None else max(1, task.delegation.max_depth)
        )
        branching_factor = self.branching_factor or task.delegation.planned_branching_factor
        trajectory = make_trajectory(
            task=task,
            model=model,
            architecture=self.architecture,
            experiment_id=experiment_id,
            run_id=run_id,
            seed=seed,
        )
        environment = ToolEnvironment(task)
        registry = build_registry(task, creation_step=f"{run_id}_step_001")
        artifacts = InheritanceRunArtifacts(registry)
        sequence = 1
        root_envelope = create_envelope(
            registry,
            envelope_id=f"{run_id}_env_root",
            sender_agent_id="system",
            recipient_agent_id="planner",
            created_step_id=f"{run_id}_step_001",
            acknowledged=self.architecture == ArchitectureKind.VERIFIED_INHERITANCE,
        )
        artifacts.envelopes.append(root_envelope)
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
                constraint_snapshots=envelope_to_snapshots(
                    root_envelope,
                    registry,
                    current_source_level=0,
                    inherited_from_step_id=None,
                ),
                metadata={"envelope_id": root_envelope.envelope_id},
            )
        )
        child_step_ids: list[str] = []
        child_branch_ids: list[str] = []
        child_envelopes: list[ConstraintEnvelope] = []

        async def add_children(
            parent_step_id: str,
            parent_agent_id: str,
            parent_envelope: ConstraintEnvelope | None,
            depth: int,
            branch_prefix: str,
        ) -> list[str]:
            nonlocal sequence
            if depth > max_depth:
                return []
            outputs: list[str] = []
            for branch in range(branching_factor):
                sequence += 1
                branch_id = f"{branch_prefix}{branch}"
                agent_id = f"{self.architecture.value}_d{depth}_b{branch_id}"
                step_id = f"{run_id}_step_{sequence:03d}"
                delegation_id = f"{run_id}_delegation_{depth}"
                envelope = (
                    create_envelope(
                        registry,
                        envelope_id=f"{run_id}_env_{sequence:03d}",
                        sender_agent_id=parent_agent_id,
                        recipient_agent_id=agent_id,
                        created_step_id=step_id,
                        parent_envelope_id=parent_envelope.envelope_id if parent_envelope else None,
                        delegation_id=delegation_id,
                        branch_id=branch_id,
                        acknowledged=self.architecture == ArchitectureKind.VERIFIED_INHERITANCE,
                    )
                    if parent_envelope is not None
                    else None
                )
                envelope, mutation_events = apply_schedule(
                    envelope,
                    self.mutation_schedule,
                    scheduled_step="delegation",
                    actual_step_id=step_id,
                    seed=seed + sequence,
                    branch_id=branch_id,
                )
                artifacts.mutations.extend(mutation_events)
                if envelope is not None:
                    artifacts.envelopes.append(envelope)
                verification_event: VerificationEvent | None = None
                repair_event: RepairEvent | None = None
                refused = False
                if self.architecture == ArchitectureKind.VERIFIED_INHERITANCE:
                    outcome = verify_envelope(
                        registry,
                        envelope,
                        step_id=step_id,
                        agent_id=agent_id,
                        branch_id=branch_id,
                        response=self.verification_response,
                    )
                    envelope = outcome.envelope
                    verification_event = outcome.event
                    repair_event = outcome.repair
                    artifacts.verifications.append(verification_event)
                    if repair_event is not None:
                        artifacts.repairs.append(repair_event)
                        if envelope is not None:
                            artifacts.envelopes.append(envelope)
                    refused = not verification_event.passed
                comparisons = compare_envelope(registry, envelope, depth=depth)
                artifacts.comparisons.extend(comparisons)
                snapshots = envelope_to_snapshots(
                    envelope,
                    registry,
                    current_source_level=depth,
                    inherited_from_step_id=parent_step_id,
                )
                visible_constraints = "; ".join(
                    snapshot.visible_rule for snapshot in snapshots if snapshot.visible_rule
                )
                if refused:
                    response = None
                    output = f"Branch {branch_id} refused due to invalid envelope."
                else:
                    message = MessageRecord(
                        role="user",
                        content=(
                            f"Subtask depth {depth}. "
                            f"Constraints envelope separate: {visible_constraints}"
                        ),
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
                    output = response.message.content
                tool_calls = []
                if response is not None:
                    for index, request in enumerate(
                        tool_requests_from_response(response.raw_metadata), start=1
                    ):
                        raw_arguments = request.get("arguments")
                        arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
                        tool_calls.append(
                            environment.execute(
                                tool_call_id=f"{run_id}_tool_{sequence}_{index}",
                                tool_name=str(request.get("tool_name", "")),
                                arguments=arguments,
                                requested_by_agent=agent_id,
                            )
                        )
                metadata = {
                    "envelope_id": envelope.envelope_id if envelope else None,
                    "mutation_event_ids": [event.mutation_id for event in mutation_events],
                    "verification_event_id": verification_event.verification_id
                    if verification_event
                    else None,
                    "repair_event_id": repair_event.repair_id if repair_event else None,
                    "branch_refused": refused,
                }
                trajectory.steps.append(
                    TrajectoryStep(
                        step_id=step_id,
                        sequence_index=sequence,
                        parent_step_id=parent_step_id,
                        delegation_id=delegation_id,
                        branch_id=branch_id,
                        agent_id=agent_id,
                        parent_agent_id=parent_agent_id,
                        role="worker",
                        depth=depth,
                        kind=WorkflowStepKind.DELEGATION,
                        input_messages=[
                            MessageRecord(
                                role="user", content=f"Subtask depth {depth}", agent_id=agent_id
                            )
                        ],
                        model_response=response,
                        constraint_snapshots=snapshots,
                        tool_calls=tool_calls,
                        metadata=metadata,
                    )
                )
                child_step_ids.append(step_id)
                child_branch_ids.append(branch_id)
                if envelope is not None:
                    child_envelopes.append(envelope)
                outputs.append(output)
                if not refused:
                    outputs.extend(
                        await add_children(step_id, agent_id, envelope, depth + 1, f"{branch_id}.")
                    )
            return outputs

        child_outputs = await add_children(root_step_id, "planner", root_envelope, 1, "")
        sequence += 1
        aggregation_step_id = f"{run_id}_step_{sequence:03d}"
        aggregation_envelope, aggregation_mutations = apply_schedule(
            root_envelope,
            self.mutation_schedule,
            scheduled_step="aggregation",
            actual_step_id=aggregation_step_id,
            seed=seed + sequence,
            branch_id=None,
        )
        artifacts.mutations.extend(aggregation_mutations)
        aggregation_comparisons = compare_envelope(registry, aggregation_envelope, depth=0)
        artifacts.comparisons.extend(aggregation_comparisons)
        provenance = AggregationProvenance(
            step_id=aggregation_step_id,
            child_step_ids=child_step_ids,
            branch_ids=child_branch_ids,
            envelope_ids=[envelope.envelope_id for envelope in child_envelopes],
            envelope_versions=[envelope.envelope_version for envelope in child_envelopes],
            used_current_canonical_state=aggregation_envelope is root_envelope,
            stale_envelope_ids=[
                envelope.envelope_id
                for envelope in child_envelopes
                if any(entry.constraint_version != "v1" for entry in envelope.constraint_entries)
            ],
        )
        artifacts.aggregation = provenance
        combine_prompt = MessageRecord(
            role="user",
            content="\n".join(child_outputs),
            agent_id="planner",
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
                step_id=aggregation_step_id,
                sequence_index=sequence,
                parent_step_id=root_step_id,
                agent_id="planner",
                role="planner",
                depth=0,
                kind=WorkflowStepKind.FINAL_OUTPUT,
                input_messages=[combine_prompt],
                model_response=final_response,
                constraint_snapshots=envelope_to_snapshots(
                    aggregation_envelope,
                    registry,
                    current_source_level=0,
                    inherited_from_step_id=root_step_id,
                ),
                metadata={
                    "aggregation_provenance": provenance.model_dump(mode="json"),
                    "mutation_event_ids": [event.mutation_id for event in aggregation_mutations],
                },
            )
        )
        artifacts.metrics = retention_metrics(
            registry,
            artifacts.comparisons,
            verification_events=artifacts.verifications,
            repair_events=artifacts.repairs,
        )
        trajectory.status = TrajectoryStatus.COMPLETED
        if self.architecture == ArchitectureKind.VERIFIED_INHERITANCE and any(
            not event.passed
            and event.response
            in {
                VerificationResponse.REFUSE_SUBTASK,
                VerificationResponse.TERMINATE_BRANCH,
                VerificationResponse.REQUEST_CLARIFICATION,
            }
            for event in artifacts.verifications
        ):
            trajectory.metadata["architecture_refusals"] = True
        trajectory.completed_at = datetime.now(timezone.utc)
        trajectory.metadata["inheritance"] = {
            "registry": registry.model_dump(mode="json"),
            "envelopes": [envelope.model_dump(mode="json") for envelope in artifacts.envelopes],
            "mutation_events": [event.model_dump(mode="json") for event in artifacts.mutations],
            "verification_events": [
                event.model_dump(mode="json") for event in artifacts.verifications
            ],
            "repair_events": [event.model_dump(mode="json") for event in artifacts.repairs],
            "comparisons": [
                comparison.model_dump(mode="json") for comparison in artifacts.comparisons
            ],
            "metrics": [metric.model_dump(mode="json") for metric in artifacts.metrics],
            "aggregation_provenance": provenance.model_dump(mode="json"),
        }
        add_usage(trajectory)
        try:
            return Trajectory.model_validate(trajectory.model_dump())
        except Exception as exc:
            trajectory.status = TrajectoryStatus.FAILED
            trajectory.error = ErrorRecord(
                error_type=type(exc).__name__,
                message=str(exc),
                recoverable=True,
            )
            return trajectory
