"""Canonical registries, envelopes, verification, and repair for Phase 3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import Field, NonNegativeInt

from bayesaudit.hash_utils import canonical_json_hash, text_hash
from bayesaudit.schemas import (
    BenchmarkTask,
    MutationType,
    RetentionStatus,
    Severity,
    StrictModel,
    VerificationStatus,
)

INHERITANCE_SCHEMA_VERSION = "bayesaudit.inheritance.v1"


class VerificationResponse(str):
    CONTINUE = "continue"
    REPAIR_FROM_CANONICAL = "repair_from_canonical"
    MINIMAL_REPAIR = "minimal_repair"
    REQUEST_CLARIFICATION = "request_clarification"
    REFUSE_SUBTASK = "refuse_subtask"
    ESCALATE = "escalate"
    TERMINATE_BRANCH = "terminate_branch"


class ConstraintRegistryEntry(StrictModel):
    constraint_id: str
    canonical_rule: str
    canonical_normalized: str
    canonical_hash: str
    task_version: str
    constraint_version: str = "v1"
    category: str
    severity: str
    scope: list[str]
    requires_escalation: bool
    source_privilege_level: NonNegativeInt = 0
    creation_step: str
    superseded_version: str | None = None


class CanonicalConstraintRegistry(StrictModel):
    schema_version: str = INHERITANCE_SCHEMA_VERSION
    registry_id: str
    task_id: str
    task_version: str
    entries: tuple[ConstraintRegistryEntry, ...]
    registry_hash: str

    def entry_map(self) -> dict[str, ConstraintRegistryEntry]:
        return {entry.constraint_id: entry for entry in self.entries}


class ConstraintEnvelopeEntry(StrictModel):
    constraint_id: str
    visible_rule: str
    canonical_hash_reference: str
    visible_hash: str
    source_privilege_level: NonNegativeInt = 0
    current_privilege_level: NonNegativeInt = 0
    severity: str
    scope: list[str]
    required_for_execution: bool
    constraint_version: str = "v1"
    acknowledgment_status: bool = False
    verification_status: str = VerificationStatus.NOT_REQUIRED.value


class ConstraintEnvelope(StrictModel):
    schema_version: str = INHERITANCE_SCHEMA_VERSION
    envelope_id: str
    task_id: str
    task_version: str
    envelope_version: str = "v1"
    sender_agent_id: str
    recipient_agent_id: str
    parent_envelope_id: str | None = None
    delegation_id: str | None = None
    branch_id: str | None = None
    created_step_id: str
    constraint_entries: list[ConstraintEnvelopeEntry]
    canonical_set_hash: str
    visible_set_hash: str
    integrity_checksum: str
    declared_complete: bool = True
    acknowledged: bool = False
    verified: bool = False
    verification_result: str | None = None
    mutation_event_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConstraintMutationEvent(StrictModel):
    schema_version: str = INHERITANCE_SCHEMA_VERSION
    mutation_id: str
    mutation_type: str
    target_envelope_id: str | None = None
    target_constraint_id: str | None = None
    target_step_id: str | None = None
    scheduled_step: str
    actual_applied_step: str | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    deterministic_seed: int
    injection_source: str = "phase3_mutation_schedule"
    expected_retention_classification: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationEvent(StrictModel):
    schema_version: str = INHERITANCE_SCHEMA_VERSION
    verification_id: str
    envelope_id: str | None
    step_id: str
    agent_id: str
    passed: bool
    response: str
    reasons: list[str] = Field(default_factory=list)
    detected_mutation_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepairEvent(StrictModel):
    schema_version: str = INHERITANCE_SCHEMA_VERSION
    repair_id: str
    envelope_id: str | None
    step_id: str
    strategy: str
    attempted: bool
    succeeded: bool
    failed: bool
    information_used: list[str] = Field(default_factory=list)
    original_mutation_observable: bool = True
    execution_resumed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AggregationProvenance(StrictModel):
    schema_version: str = INHERITANCE_SCHEMA_VERSION
    step_id: str
    child_step_ids: list[str]
    branch_ids: list[str]
    envelope_ids: list[str]
    envelope_versions: list[str]
    used_current_canonical_state: bool
    stale_envelope_ids: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class VerificationOutcome:
    envelope: ConstraintEnvelope | None
    event: VerificationEvent
    repair: RepairEvent | None = None


def build_registry(task: BenchmarkTask, *, creation_step: str) -> CanonicalConstraintRegistry:
    entries = tuple(
        ConstraintRegistryEntry(
            constraint_id=constraint.id,
            canonical_rule=constraint.rule,
            canonical_normalized=normalize_rule(constraint.rule),
            canonical_hash=text_hash(normalize_rule(constraint.rule)),
            task_version=task.task_version,
            category=str(constraint.category),
            severity=str(constraint.severity),
            scope=[str(scope) for scope in constraint.scope],
            requires_escalation=constraint.requires_escalation,
            source_privilege_level=0,
            creation_step=creation_step,
        )
        for constraint in task.constraints
    )
    registry_hash = canonical_json_hash([entry.model_dump(mode="json") for entry in entries])
    return CanonicalConstraintRegistry(
        registry_id=f"registry_{task.task_id}_{registry_hash[:12]}",
        task_id=task.task_id,
        task_version=task.task_version,
        entries=entries,
        registry_hash=registry_hash,
    )


def normalize_rule(rule: str) -> str:
    return " ".join(rule.strip().lower().split())


def create_envelope(
    registry: CanonicalConstraintRegistry,
    *,
    envelope_id: str,
    sender_agent_id: str,
    recipient_agent_id: str,
    created_step_id: str,
    parent_envelope_id: str | None = None,
    delegation_id: str | None = None,
    branch_id: str | None = None,
    acknowledged: bool = False,
) -> ConstraintEnvelope:
    entries = [
        ConstraintEnvelopeEntry(
            constraint_id=entry.constraint_id,
            visible_rule=entry.canonical_rule,
            canonical_hash_reference=entry.canonical_hash,
            visible_hash=text_hash(normalize_rule(entry.canonical_rule)),
            source_privilege_level=entry.source_privilege_level,
            current_privilege_level=entry.source_privilege_level,
            severity=entry.severity,
            scope=entry.scope,
            required_for_execution=entry.requires_escalation
            or entry.severity == Severity.CRITICAL.value,
            constraint_version=entry.constraint_version,
            acknowledgment_status=acknowledged,
        )
        for entry in registry.entries
    ]
    return finalize_envelope(
        ConstraintEnvelope(
            envelope_id=envelope_id,
            task_id=registry.task_id,
            task_version=registry.task_version,
            sender_agent_id=sender_agent_id,
            recipient_agent_id=recipient_agent_id,
            parent_envelope_id=parent_envelope_id,
            delegation_id=delegation_id,
            branch_id=branch_id,
            created_step_id=created_step_id,
            constraint_entries=entries,
            canonical_set_hash=registry.registry_hash,
            visible_set_hash="",
            integrity_checksum="",
            acknowledged=acknowledged,
        )
    )


def finalize_envelope(
    envelope: ConstraintEnvelope, *, preserve_checksum: bool = False
) -> ConstraintEnvelope:
    visible_set_hash = canonical_json_hash(
        [
            {
                "constraint_id": entry.constraint_id,
                "visible_rule": entry.visible_rule,
                "visible_hash": entry.visible_hash,
                "canonical_hash_reference": entry.canonical_hash_reference,
                "current_privilege_level": entry.current_privilege_level,
                "scope": entry.scope,
                "constraint_version": entry.constraint_version,
            }
            for entry in sorted(envelope.constraint_entries, key=lambda item: item.constraint_id)
        ]
    )
    checksum = (
        envelope.integrity_checksum
        if preserve_checksum
        else envelope_checksum(envelope, visible_set_hash)
    )
    return envelope.model_copy(
        update={"visible_set_hash": visible_set_hash, "integrity_checksum": checksum}
    )


def envelope_checksum(envelope: ConstraintEnvelope, visible_set_hash: str | None = None) -> str:
    return canonical_json_hash(
        {
            "envelope_id": envelope.envelope_id,
            "task_id": envelope.task_id,
            "task_version": envelope.task_version,
            "parent_envelope_id": envelope.parent_envelope_id,
            "delegation_id": envelope.delegation_id,
            "branch_id": envelope.branch_id,
            "canonical_set_hash": envelope.canonical_set_hash,
            "visible_set_hash": visible_set_hash or envelope.visible_set_hash,
            "declared_complete": envelope.declared_complete,
        }
    )


def envelope_to_snapshots(
    envelope: ConstraintEnvelope | None,
    registry: CanonicalConstraintRegistry,
    *,
    current_source_level: int,
    inherited_from_step_id: str | None,
) -> list[Any]:
    from bayesaudit.constraints.comparison import compare_envelope

    comparisons = compare_envelope(registry, envelope)
    entries = (
        {entry.constraint_id: entry for entry in envelope.constraint_entries} if envelope else {}
    )
    snapshots = []
    for comparison in comparisons:
        registry_entry = registry.entry_map().get(comparison.constraint_id)
        envelope_entry = entries.get(comparison.constraint_id)
        if registry_entry is None and envelope_entry is None:
            continue
        canonical_rule = registry_entry.canonical_rule if registry_entry else ""
        visible_rule = envelope_entry.visible_rule if envelope_entry else ""
        snapshots.append(
            _snapshot(
                comparison.constraint_id,
                canonical_rule,
                visible_rule,
                registry_entry.category if registry_entry else "evidence",
                registry_entry.severity if registry_entry else Severity.LOW.value,
                current_source_level,
                inherited_from_step_id,
                comparison.classification,
                envelope_entry.acknowledgment_status if envelope_entry else False,
            )
        )
    return snapshots


def _snapshot(
    constraint_id: str,
    canonical_rule: str,
    visible_rule: str,
    category: str,
    severity: str,
    current_source_level: int,
    inherited_from_step_id: str | None,
    classification: str,
    acknowledged: bool,
) -> Any:
    from bayesaudit.schemas import ConstraintSnapshot

    retention = _classification_to_retention(classification)
    return ConstraintSnapshot(
        constraint_id=constraint_id,
        canonical_rule=canonical_rule,
        visible_rule=visible_rule,
        category=category,
        severity=severity,
        original_source_level=0,
        current_source_level=current_source_level,
        inherited_from_step_id=inherited_from_step_id,
        canonical_hash=text_hash(normalize_rule(canonical_rule)),
        visible_hash=text_hash(normalize_rule(visible_rule)),
        retention_status=retention,
        mutation_type=_retention_to_mutation(retention),
        acknowledged_by_agent=acknowledged,
        verification_status=(
            VerificationStatus.ACKNOWLEDGED.value
            if acknowledged
            else VerificationStatus.NOT_REQUIRED.value
        ),
    )


def _classification_to_retention(classification: str) -> str:
    if classification == "preserved_exact":
        return RetentionStatus.PRESERVED.value
    if classification == "preserved_equivalent":
        return RetentionStatus.PARAPHRASED_EQUIVALENT.value
    if classification == "strengthened":
        return RetentionStatus.STRENGTHENED.value
    if classification == "contradicted":
        return RetentionStatus.CONTRADICTED.value
    if classification == "added":
        return RetentionStatus.ADDED.value
    if classification in {"dropped", "missing_envelope"}:
        return RetentionStatus.DROPPED.value
    return RetentionStatus.WEAKENED.value


def _retention_to_mutation(retention: str) -> str:
    mapping = {
        RetentionStatus.PRESERVED.value: MutationType.NONE.value,
        RetentionStatus.PARAPHRASED_EQUIVALENT.value: MutationType.PARAPHRASED.value,
        RetentionStatus.WEAKENED.value: MutationType.WEAKENED_SCOPE.value,
        RetentionStatus.STRENGTHENED.value: MutationType.STRENGTHENED_SCOPE.value,
        RetentionStatus.DROPPED.value: MutationType.OMITTED.value,
        RetentionStatus.CONTRADICTED.value: MutationType.CONTRADICTION.value,
        RetentionStatus.ADDED.value: MutationType.NEW_CONSTRAINT.value,
    }
    return mapping.get(retention, MutationType.WEAKENED_SCOPE.value)


def verify_envelope(
    registry: CanonicalConstraintRegistry,
    envelope: ConstraintEnvelope | None,
    *,
    step_id: str,
    agent_id: str,
    branch_id: str | None,
    response: str,
) -> VerificationOutcome:
    reasons = verification_reasons(registry, envelope, branch_id=branch_id)
    passed = not reasons
    repaired: ConstraintEnvelope | None = None
    repair: RepairEvent | None = None
    final_response = response

    if not passed and response in {
        VerificationResponse.REPAIR_FROM_CANONICAL,
        VerificationResponse.MINIMAL_REPAIR,
    }:
        repaired = create_envelope(
            registry,
            envelope_id=(envelope.envelope_id if envelope else f"repaired_{step_id}"),
            sender_agent_id=(envelope.sender_agent_id if envelope else "architecture"),
            recipient_agent_id=agent_id,
            created_step_id=step_id,
            parent_envelope_id=(envelope.parent_envelope_id if envelope else None),
            delegation_id=(envelope.delegation_id if envelope else None),
            branch_id=branch_id,
            acknowledged=True,
        )
        passed = True
        final_response = VerificationResponse.CONTINUE
        repair = RepairEvent(
            repair_id=f"repair_{step_id}",
            envelope_id=envelope.envelope_id if envelope else None,
            step_id=step_id,
            strategy=response,
            attempted=True,
            succeeded=True,
            failed=False,
            information_used=["canonical_registry"],
            execution_resumed=True,
        )
    elif passed:
        final_response = VerificationResponse.CONTINUE

    event = VerificationEvent(
        verification_id=f"verify_{step_id}",
        envelope_id=envelope.envelope_id if envelope else None,
        step_id=step_id,
        agent_id=agent_id,
        passed=passed,
        response=final_response if passed else response,
        reasons=reasons,
        detected_mutation_ids=envelope.mutation_event_ids if envelope and reasons else [],
    )
    return VerificationOutcome(envelope=repaired or envelope, event=event, repair=repair)


def verification_reasons(
    registry: CanonicalConstraintRegistry,
    envelope: ConstraintEnvelope | None,
    *,
    branch_id: str | None,
) -> list[str]:
    if envelope is None:
        return ["missing_envelope"]
    reasons: list[str] = []
    if envelope.task_id != registry.task_id:
        reasons.append("wrong_task_id")
    if envelope.task_version != registry.task_version:
        reasons.append("wrong_task_version")
    if envelope.canonical_set_hash != registry.registry_hash:
        reasons.append("canonical_set_hash_mismatch")
    if envelope.integrity_checksum != envelope_checksum(envelope):
        reasons.append("integrity_checksum_mismatch")
    if branch_id is not None and envelope.branch_id != branch_id:
        reasons.append("wrong_branch_id")
    registry_map = registry.entry_map()
    entries = {entry.constraint_id: entry for entry in envelope.constraint_entries}
    if len(entries) != len(envelope.constraint_entries):
        reasons.append("duplicate_constraint_entry")
    for constraint_id, entry in registry_map.items():
        candidate = entries.get(constraint_id)
        if candidate is None:
            reasons.append(f"missing_required_constraint:{constraint_id}")
            continue
        if candidate.canonical_hash_reference != entry.canonical_hash:
            reasons.append(f"canonical_hash_mismatch:{constraint_id}")
        if candidate.constraint_version != entry.constraint_version:
            reasons.append(f"stale_constraint_version:{constraint_id}")
        if candidate.current_privilege_level > entry.source_privilege_level:
            reasons.append(f"privilege_demoted:{constraint_id}")
        if not set(entry.scope).issubset(set(candidate.scope)):
            reasons.append(f"required_scope_removed:{constraint_id}")
        if entry.severity == Severity.CRITICAL.value and not candidate.acknowledgment_status:
            reasons.append(f"critical_unacknowledged:{constraint_id}")
    for constraint_id in entries:
        if constraint_id not in registry_map:
            reasons.append(f"unknown_constraint:{constraint_id}")
    return reasons
