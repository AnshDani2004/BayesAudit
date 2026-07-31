"""Deterministic constraint-envelope mutation framework."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from bayesaudit.constraints.inheritance import (
    ConstraintEnvelope,
    ConstraintEnvelopeEntry,
    ConstraintMutationEvent,
    finalize_envelope,
    normalize_rule,
)
from bayesaudit.hash_utils import text_hash
from bayesaudit.schemas import StrictModel


class MutationProfile(StrictModel):
    name: str
    mutation_type: str
    scheduled_step: str = "delegation"
    target_constraint_id: str | None = None
    target_branch_id: str | None = None
    expected_retention_classification: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MutationSchedule(StrictModel):
    profiles: list[MutationProfile] = Field(default_factory=list)

    def for_step(
        self, scheduled_step: str, *, branch_id: str | None = None
    ) -> list[MutationProfile]:
        selected: list[MutationProfile] = []
        for profile in self.profiles:
            if profile.scheduled_step != scheduled_step:
                continue
            if profile.target_branch_id is not None and profile.target_branch_id != branch_id:
                continue
            selected.append(profile)
        return selected


def load_mutation_profile(path: Path) -> MutationProfile:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"mutation profile must be a mapping: {path}")
    return MutationProfile.model_validate(payload)


def load_mutation_profiles(root: Path) -> list[MutationProfile]:
    return [load_mutation_profile(path) for path in sorted(root.rglob("*.yaml"))]


def apply_schedule(
    envelope: ConstraintEnvelope | None,
    schedule: MutationSchedule,
    *,
    scheduled_step: str,
    actual_step_id: str,
    seed: int,
    branch_id: str | None,
) -> tuple[ConstraintEnvelope | None, list[ConstraintMutationEvent]]:
    events: list[ConstraintMutationEvent] = []
    current = envelope
    for index, profile in enumerate(
        schedule.for_step(scheduled_step, branch_id=branch_id), start=1
    ):
        current, event = apply_mutation(
            current,
            profile,
            actual_step_id=actual_step_id,
            seed=seed + index,
        )
        events.append(event)
    return current, events


def apply_mutation(
    envelope: ConstraintEnvelope | None,
    profile: MutationProfile,
    *,
    actual_step_id: str,
    seed: int,
) -> tuple[ConstraintEnvelope | None, ConstraintMutationEvent]:
    before = envelope.model_dump(mode="json") if envelope is not None else None
    mutation_id = f"mutation_{profile.name}_{actual_step_id}_{seed}"
    if profile.mutation_type == "remove_envelope":
        return None, _event(profile, mutation_id, envelope, before, None, actual_step_id, seed)
    if envelope is None:
        return None, _event(profile, mutation_id, envelope, before, None, actual_step_id, seed)

    updated = envelope.model_copy(deep=True)
    entries = list(updated.constraint_entries)
    target_id = profile.target_constraint_id or (entries[0].constraint_id if entries else None)

    if profile.mutation_type in {
        "drop_constraint",
        "remove_constraint_entry",
        "truncate_oldest_constraint",
    }:
        entries = [entry for entry in entries if entry.constraint_id != target_id]
    elif profile.mutation_type == "weaken_constraint":
        entries = [
            _with_visible(entry, f"Weakened: {entry.visible_rule}")
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "strengthen_constraint":
        entries = [
            _with_visible(entry, f"Strengthened: {entry.visible_rule}")
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "contradict_constraint":
        entries = [
            _with_visible(entry, f"Contradicts: {entry.visible_rule}")
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "paraphrase_equivalent":
        entries = [
            _with_visible(entry, f"Equivalent paraphrase: {entry.visible_rule}")
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "replace_with_unrelated_rule":
        entries = [
            _with_visible(entry, "Unrelated rule: prefer concise answers.")
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "add_unauthorized_constraint":
        entries.append(
            ConstraintEnvelopeEntry(
                constraint_id=f"unauthorized_{seed}",
                visible_rule="Unauthorized added constraint.",
                canonical_hash_reference="unknown",
                visible_hash=text_hash("unauthorized added constraint."),
                severity="low",
                scope=["messages"],
                required_for_execution=False,
            )
        )
    elif profile.mutation_type == "duplicate_constraint_entry" and entries:
        entries.append(entries[0].model_copy())
    elif profile.mutation_type == "corrupt_canonical_reference":
        entries = [
            entry.model_copy(update={"canonical_hash_reference": "corrupted"})
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "corrupt_visible_hash":
        entries = [
            entry.model_copy(update={"visible_hash": "corrupted"})
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "corrupt_set_hash":
        updated = updated.model_copy(update={"visible_set_hash": "corrupted"})
    elif profile.mutation_type == "use_stale_constraint_version":
        entries = [
            entry.model_copy(update={"constraint_version": "v0"})
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "use_wrong_task_id":
        updated = updated.model_copy(update={"task_id": "task_wrong"})
    elif profile.mutation_type == "use_wrong_branch_id":
        updated = updated.model_copy(update={"branch_id": "wrong_branch"})
    elif profile.mutation_type == "break_parent_envelope_linkage":
        updated = updated.model_copy(update={"parent_envelope_id": "missing_parent"})
    elif profile.mutation_type == "mark_incomplete_complete":
        updated = updated.model_copy(update={"declared_complete": True})
        entries = entries[: max(0, len(entries) - 1)]
    elif profile.mutation_type in {"demote_privilege", "preserve_wording_change_source_level"}:
        entries = [
            entry.model_copy(update={"current_privilege_level": entry.source_privilege_level + 1})
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "remove_privilege_metadata":
        entries = [
            entry.model_copy(update={"current_privilege_level": 999})
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "mislabel_user_text_system":
        entries = [
            entry.model_copy(update={"current_privilege_level": 0, "source_privilege_level": 5})
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "truncate_lowest_severity_constraint":
        entries = entries[1:] if len(entries) > 1 else []
    elif profile.mutation_type == "truncate_longest_constraint" and entries:
        longest = max(entries, key=lambda entry: len(entry.visible_rule))
        entries = [entry for entry in entries if entry.constraint_id != longest.constraint_id]
    elif profile.mutation_type == "preserve_first_n_constraints":
        n = int(profile.metadata.get("n", 1))
        entries = entries[:n]
    elif profile.mutation_type in {
        "noncritical_metadata_change",
        "additional_irrelevant_metadata",
        "correct_branch_specific_copy",
        "preserve_task_prose_truncate_details",
    }:
        metadata = dict(updated.metadata)
        metadata[f"mutation_{profile.mutation_type}"] = True
        updated = updated.model_copy(update={"metadata": metadata})
    elif profile.mutation_type == "constraint_order_permutation":
        entries = list(reversed(entries))
    elif profile.mutation_type == "valid_constraint_version_increment":
        entries = [
            entry.model_copy(update={"constraint_version": "v1"})
            if entry.constraint_id == target_id
            else entry
            for entry in entries
        ]
    elif profile.mutation_type == "restore_previously_dropped_constraint":
        pass

    updated = updated.model_copy(
        update={
            "constraint_entries": entries,
            "mutation_event_ids": [*updated.mutation_event_ids, mutation_id],
        }
    )
    preserve_checksum = profile.mutation_type in {"corrupt_set_hash", "corrupt_visible_hash"}
    updated = finalize_envelope(updated, preserve_checksum=preserve_checksum)
    return updated, _event(
        profile,
        mutation_id,
        envelope,
        before,
        updated.model_dump(mode="json"),
        actual_step_id,
        seed,
    )


def _with_visible(entry: ConstraintEnvelopeEntry, visible_rule: str) -> ConstraintEnvelopeEntry:
    return entry.model_copy(
        update={
            "visible_rule": visible_rule,
            "visible_hash": text_hash(normalize_rule(visible_rule)),
        }
    )


def _event(
    profile: MutationProfile,
    mutation_id: str,
    envelope: ConstraintEnvelope | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actual_step_id: str,
    seed: int,
) -> ConstraintMutationEvent:
    return ConstraintMutationEvent(
        mutation_id=mutation_id,
        mutation_type=profile.mutation_type,
        target_envelope_id=envelope.envelope_id if envelope else None,
        target_constraint_id=profile.target_constraint_id,
        target_step_id=actual_step_id,
        scheduled_step=profile.scheduled_step,
        actual_applied_step=actual_step_id,
        before_state=before,
        after_state=after,
        deterministic_seed=seed,
        expected_retention_classification=profile.expected_retention_classification,
        metadata=profile.metadata,
    )
