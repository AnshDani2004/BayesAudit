from __future__ import annotations

from pathlib import Path

from conftest import named_task, run

from bayesaudit.architectures.structured import StructuredInheritanceWorkflow
from bayesaudit.architectures.unstructured import UnstructuredDelegationWorkflow
from bayesaudit.architectures.verified import VerifiedInheritanceWorkflow
from bayesaudit.constraints.comparison import compare_envelope
from bayesaudit.constraints.inheritance import (
    CanonicalConstraintRegistry,
    ConstraintEnvelope,
    VerificationResponse,
    build_registry,
    create_envelope,
    envelope_checksum,
    verify_envelope,
)
from bayesaudit.constraints.metrics import branch_consistency, retention_metrics
from bayesaudit.constraints.mutations import (
    MutationProfile,
    MutationSchedule,
    apply_mutation,
    load_mutation_profiles,
)
from bayesaudit.models.mock import MockModel, MockScript
from bayesaudit.schemas import TrajectoryStatus
from bayesaudit.storage.normalize import normalized_records


def registry_and_envelope() -> tuple[CanonicalConstraintRegistry, ConstraintEnvelope]:
    task = named_task("task_privacy_aggregate_only")
    registry = build_registry(task, creation_step="step_001")
    envelope = create_envelope(
        registry,
        envelope_id="env_001",
        sender_agent_id="planner",
        recipient_agent_id="worker",
        created_step_id="step_002",
        branch_id="0",
        acknowledged=True,
    )
    return registry, envelope


def test_valid_envelope_construction() -> None:
    registry, envelope = registry_and_envelope()
    assert envelope.task_id == registry.task_id
    assert envelope.canonical_set_hash == registry.registry_hash
    assert envelope.integrity_checksum == envelope_checksum(envelope)


def test_envelope_hash_stability() -> None:
    registry, first = registry_and_envelope()
    second = create_envelope(
        registry,
        envelope_id="env_001",
        sender_agent_id="planner",
        recipient_agent_id="worker",
        created_step_id="step_002",
        branch_id="0",
        acknowledged=True,
    )
    assert first.visible_set_hash == second.visible_set_hash
    assert first.integrity_checksum == second.integrity_checksum


def test_parent_linkage_and_branch_copy() -> None:
    registry, parent = registry_and_envelope()
    child = create_envelope(
        registry,
        envelope_id="env_child",
        sender_agent_id="worker",
        recipient_agent_id="child",
        created_step_id="step_003",
        parent_envelope_id=parent.envelope_id,
        branch_id="0.1",
        acknowledged=True,
    )
    assert child.parent_envelope_id == "env_001"
    assert child.branch_id == "0.1"
    assert child.canonical_set_hash == parent.canonical_set_hash


def test_valid_envelope_accepted() -> None:
    registry, envelope = registry_and_envelope()
    outcome = verify_envelope(
        registry,
        envelope,
        step_id="step_002",
        agent_id="worker",
        branch_id="0",
        response=VerificationResponse.REFUSE_SUBTASK,
    )
    assert outcome.event.passed


def test_invalid_task_linkage_detected() -> None:
    registry, envelope = registry_and_envelope()
    bad = envelope.model_copy(update={"task_id": "task_wrong"})
    outcome = verify_envelope(
        registry,
        bad,
        step_id="step_002",
        agent_id="worker",
        branch_id="0",
        response=VerificationResponse.REFUSE_SUBTASK,
    )
    assert "wrong_task_id" in outcome.event.reasons


def test_unknown_constraint_detected() -> None:
    registry, envelope = registry_and_envelope()
    mutated, _ = apply_mutation(
        envelope,
        MutationProfile(name="add", mutation_type="add_unauthorized_constraint"),
        actual_step_id="step_002",
        seed=1,
    )
    outcome = verify_envelope(
        registry,
        mutated,
        step_id="step_002",
        agent_id="worker",
        branch_id="0",
        response=VerificationResponse.REFUSE_SUBTASK,
    )
    assert any(reason.startswith("unknown_constraint") for reason in outcome.event.reasons)


def test_missing_envelope_detected() -> None:
    registry, _ = registry_and_envelope()
    outcome = verify_envelope(
        registry,
        None,
        step_id="step_002",
        agent_id="worker",
        branch_id="0",
        response=VerificationResponse.REFUSE_SUBTASK,
    )
    assert outcome.event.reasons == ["missing_envelope"]


def test_corrupt_integrity_checksum_detected() -> None:
    registry, envelope = registry_and_envelope()
    bad = envelope.model_copy(update={"integrity_checksum": "bad"})
    outcome = verify_envelope(
        registry,
        bad,
        step_id="step_002",
        agent_id="worker",
        branch_id="0",
        response=VerificationResponse.REFUSE_SUBTASK,
    )
    assert "integrity_checksum_mismatch" in outcome.event.reasons


def test_missing_critical_constraint_rejected() -> None:
    registry, envelope = registry_and_envelope()
    mutated, _ = apply_mutation(
        envelope,
        MutationProfile(
            name="drop",
            mutation_type="drop_constraint",
            target_constraint_id="privacy_01",
        ),
        actual_step_id="step_002",
        seed=1,
    )
    outcome = verify_envelope(
        registry,
        mutated,
        step_id="step_002",
        agent_id="worker",
        branch_id="0",
        response=VerificationResponse.REFUSE_SUBTASK,
    )
    assert any(reason.startswith("missing_required_constraint") for reason in outcome.event.reasons)


def test_equivalent_paraphrase_negative_control_accepted_by_comparison() -> None:
    registry, envelope = registry_and_envelope()
    mutated, _ = apply_mutation(
        envelope,
        MutationProfile(name="para", mutation_type="paraphrase_equivalent"),
        actual_step_id="step_002",
        seed=1,
    )
    classifications = {result.classification for result in compare_envelope(registry, mutated)}
    assert "preserved_equivalent" in classifications


def test_stale_version_detected() -> None:
    registry, envelope = registry_and_envelope()
    mutated, _ = apply_mutation(
        envelope,
        MutationProfile(name="stale", mutation_type="use_stale_constraint_version"),
        actual_step_id="step_002",
        seed=1,
    )
    classifications = {result.classification for result in compare_envelope(registry, mutated)}
    assert "stale" in classifications


def test_privilege_demotion_detected() -> None:
    registry, envelope = registry_and_envelope()
    mutated, _ = apply_mutation(
        envelope,
        MutationProfile(name="demote", mutation_type="demote_privilege"),
        actual_step_id="step_002",
        seed=1,
    )
    classifications = {result.classification for result in compare_envelope(registry, mutated)}
    assert "privilege_demoted" in classifications


def test_repair_from_canonical_succeeds() -> None:
    registry, envelope = registry_and_envelope()
    mutated, _ = apply_mutation(
        envelope,
        MutationProfile(name="corrupt", mutation_type="corrupt_canonical_reference"),
        actual_step_id="step_002",
        seed=1,
    )
    outcome = verify_envelope(
        registry,
        mutated,
        step_id="step_002",
        agent_id="worker",
        branch_id="0",
        response=VerificationResponse.REPAIR_FROM_CANONICAL,
    )
    assert outcome.event.passed
    assert outcome.repair is not None
    assert outcome.repair.succeeded


def test_minimal_repair_succeeds() -> None:
    registry, envelope = registry_and_envelope()
    bad = envelope.model_copy(update={"integrity_checksum": "bad"})
    outcome = verify_envelope(
        registry,
        bad,
        step_id="step_002",
        agent_id="worker",
        branch_id="0",
        response=VerificationResponse.MINIMAL_REPAIR,
    )
    assert outcome.event.passed
    assert outcome.repair is not None


def test_false_refusal_negative_control_zero() -> None:
    registry, envelope = registry_and_envelope()
    outcome = verify_envelope(
        registry,
        envelope,
        step_id="step_002",
        agent_id="worker",
        branch_id="0",
        response=VerificationResponse.REFUSE_SUBTASK,
    )
    metrics = retention_metrics(
        registry, compare_envelope(registry, envelope), verification_events=[outcome.event]
    )
    false_refusal = next(metric for metric in metrics if metric.metric_name == "false_refusal_rate")
    assert false_refusal.value == 0.0


def test_exact_retention_metric() -> None:
    registry, envelope = registry_and_envelope()
    metric = next(
        metric
        for metric in retention_metrics(registry, compare_envelope(registry, envelope))
        if metric.metric_name == "exact_retention_rate"
    )
    assert metric.value == 1.0


def test_functional_retention_counts_equivalent() -> None:
    registry, envelope = registry_and_envelope()
    mutated, _ = apply_mutation(
        envelope,
        MutationProfile(name="para", mutation_type="paraphrase_equivalent"),
        actual_step_id="step_002",
        seed=1,
    )
    metric = next(
        metric
        for metric in retention_metrics(registry, compare_envelope(registry, mutated))
        if metric.metric_name == "functional_retention_rate"
    )
    assert metric.value == 1.0


def test_severity_weighting_decreases_after_drop() -> None:
    registry, envelope = registry_and_envelope()
    mutated, _ = apply_mutation(
        envelope,
        MutationProfile(name="drop", mutation_type="drop_constraint"),
        actual_step_id="step_002",
        seed=1,
    )
    metric = next(
        metric
        for metric in retention_metrics(registry, compare_envelope(registry, mutated))
        if metric.metric_name == "severity_weighted_retention"
    )
    assert metric.value < 1.0


def test_branch_consistency_detects_difference() -> None:
    registry, envelope = registry_and_envelope()
    left = envelope.model_copy(update={"branch_id": "0"})
    right, _ = apply_mutation(
        envelope.model_copy(update={"branch_id": "1"}),
        MutationProfile(name="drop", mutation_type="drop_constraint"),
        actual_step_id="step_002",
        seed=1,
    )
    assert (
        branch_consistency([*compare_envelope(registry, left), *compare_envelope(registry, right)])
        < 1.0
    )


def test_mutation_profiles_load() -> None:
    profiles = load_mutation_profiles(Path("configs/mutations"))
    assert len(profiles) >= 20
    assert {profile.mutation_type for profile in profiles}


def test_mutation_serialization_round_trip() -> None:
    profile = MutationProfile(name="drop", mutation_type="drop_constraint")
    loaded = MutationProfile.model_validate(profile.model_dump())
    assert loaded == profile


def test_mutation_determinism_fixed_seed() -> None:
    _, envelope = registry_and_envelope()
    profile = MutationProfile(name="drop", mutation_type="drop_constraint")
    first, first_event = apply_mutation(envelope, profile, actual_step_id="step_002", seed=7)
    second, second_event = apply_mutation(envelope, profile, actual_step_id="step_002", seed=7)
    assert first is not None
    assert second is not None
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first_event.model_dump(mode="json") == second_event.model_dump(mode="json")


def test_unaffected_negative_control() -> None:
    registry, envelope = registry_and_envelope()
    mutated, _ = apply_mutation(
        envelope,
        MutationProfile(name="meta", mutation_type="additional_irrelevant_metadata"),
        actual_step_id="step_002",
        seed=1,
    )
    assert {result.classification for result in compare_envelope(registry, mutated)} == {
        "preserved_exact"
    }


def test_structured_valid_inheritance_workflow() -> None:
    task = named_task("task_privacy_aggregate_only")
    trajectory = run(
        StructuredInheritanceWorkflow(max_depth=1, branching_factor=2).run(
            task,
            MockModel(MockScript(final_answer="Synthetic final")),
            experiment_id="exp",
            run_id="structured_valid",
            seed=1,
        )
    )
    assert trajectory.status == TrajectoryStatus.COMPLETED.value
    assert trajectory.metadata["inheritance"]["envelopes"]


def test_structured_missing_envelope_continues() -> None:
    task = named_task("task_privacy_aggregate_only")
    schedule = MutationSchedule(
        profiles=[MutationProfile(name="remove", mutation_type="remove_envelope")]
    )
    trajectory = run(
        StructuredInheritanceWorkflow(
            max_depth=1, branching_factor=1, mutation_schedule=schedule
        ).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="structured_missing",
            seed=1,
        )
    )
    assert trajectory.status == TrajectoryStatus.COMPLETED.value


def test_structured_aggregation_provenance_recorded() -> None:
    task = named_task("task_privacy_aggregate_only")
    trajectory = run(
        StructuredInheritanceWorkflow(max_depth=1, branching_factor=2).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="structured_provenance",
            seed=1,
        )
    )
    provenance = trajectory.metadata["inheritance"]["aggregation_provenance"]
    assert len(provenance["child_step_ids"]) == 2
    assert len(provenance["envelope_ids"]) == 2


def test_verified_valid_inheritance_workflow() -> None:
    task = named_task("task_privacy_aggregate_only")
    trajectory = run(
        VerifiedInheritanceWorkflow(max_depth=1, branching_factor=1).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="verified_valid",
            seed=1,
        )
    )
    assert trajectory.status == TrajectoryStatus.COMPLETED.value
    assert trajectory.metadata["inheritance"]["verification_events"][0]["passed"]


def test_verified_detects_and_refuses_drop() -> None:
    task = named_task("task_privacy_aggregate_only")
    schedule = MutationSchedule(
        profiles=[
            MutationProfile(
                name="drop",
                mutation_type="drop_constraint",
                target_constraint_id="privacy_01",
            )
        ]
    )
    trajectory = run(
        VerifiedInheritanceWorkflow(
            max_depth=1, branching_factor=1, mutation_schedule=schedule
        ).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="verified_drop",
            seed=1,
        )
    )
    event = trajectory.metadata["inheritance"]["verification_events"][0]
    assert not event["passed"]
    assert trajectory.metadata["architecture_refusals"]


def test_verified_canonical_restoration_resumes() -> None:
    task = named_task("task_privacy_aggregate_only")
    schedule = MutationSchedule(
        profiles=[MutationProfile(name="corrupt", mutation_type="corrupt_canonical_reference")]
    )
    trajectory = run(
        VerifiedInheritanceWorkflow(
            max_depth=1,
            branching_factor=1,
            mutation_schedule=schedule,
            verification_response=VerificationResponse.REPAIR_FROM_CANONICAL,
        ).run(task, MockModel(), experiment_id="exp", run_id="verified_repair", seed=1)
    )
    repair = trajectory.metadata["inheritance"]["repair_events"][0]
    assert repair["succeeded"]


def test_branch_specific_mutation_only_hits_target_branch() -> None:
    task = named_task("task_privacy_aggregate_only")
    schedule = MutationSchedule(
        profiles=[
            MutationProfile(
                name="branch_drop",
                mutation_type="drop_constraint",
                target_branch_id="1",
            )
        ]
    )
    trajectory = run(
        StructuredInheritanceWorkflow(
            max_depth=1, branching_factor=2, mutation_schedule=schedule
        ).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="branch_drop",
            seed=1,
        )
    )
    mutation_events = trajectory.metadata["inheritance"]["mutation_events"]
    assert len(mutation_events) == 1
    assert mutation_events[0]["actual_applied_step"].endswith("003")


def test_depth_four_verified_workflow() -> None:
    task = named_task("task_privacy_aggregate_only")
    trajectory = run(
        VerifiedInheritanceWorkflow(max_depth=4, branching_factor=1).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="verified_depth4",
            seed=1,
        )
    )
    assert max(step.depth for step in trajectory.steps) == 4


def test_branching_factor_three_workflow() -> None:
    task = named_task("task_privacy_aggregate_only")
    trajectory = run(
        StructuredInheritanceWorkflow(max_depth=1, branching_factor=3).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="structured_b3",
            seed=1,
        )
    )
    assert len([step for step in trajectory.steps if step.role == "worker"]) == 3


def test_normalized_inheritance_tables_present() -> None:
    task = named_task("task_privacy_aggregate_only")
    trajectory = run(
        StructuredInheritanceWorkflow(max_depth=1, branching_factor=1).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="normalized_inheritance",
            seed=1,
        )
    )
    tables = normalized_records(trajectory)
    assert tables["constraint_registries"]
    assert tables["constraint_envelopes"]
    assert tables["constraint_comparisons"]
    assert tables["retention_metrics"]


def test_same_schedule_across_structured_and_verified() -> None:
    task = named_task("task_privacy_aggregate_only")
    schedule = MutationSchedule(
        profiles=[MutationProfile(name="weaken", mutation_type="weaken_constraint")]
    )
    structured = run(
        StructuredInheritanceWorkflow(
            max_depth=1, branching_factor=1, mutation_schedule=schedule
        ).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="same_structured",
            seed=1,
        )
    )
    verified = run(
        VerifiedInheritanceWorkflow(
            max_depth=1, branching_factor=1, mutation_schedule=schedule
        ).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="same_verified",
            seed=1,
        )
    )
    assert (
        structured.metadata["inheritance"]["mutation_events"][0]["mutation_type"]
        == "weaken_constraint"
    )
    assert (
        verified.metadata["inheritance"]["mutation_events"][0]["mutation_type"]
        == "weaken_constraint"
    )


def test_same_schedule_affects_unstructured_too() -> None:
    task = named_task("task_privacy_aggregate_only")
    schedule = MutationSchedule(
        profiles=[
            MutationProfile(
                name="weaken",
                mutation_type="weaken_constraint",
                target_constraint_id="privacy_01",
            )
        ]
    )
    trajectory = run(
        UnstructuredDelegationWorkflow(
            max_depth=1,
            branching_factor=1,
            mutation_schedule=schedule,
        ).run(
            task,
            MockModel(),
            experiment_id="exp",
            run_id="same_unstructured",
            seed=1,
        )
    )
    statuses = [
        snapshot.retention_status
        for step in trajectory.steps
        for snapshot in step.constraint_snapshots
    ]
    assert "weakened" in statuses
    assert (
        trajectory.metadata["inheritance"]["mutation_events"][0]["mutation_type"]
        == "weaken_constraint"
    )
