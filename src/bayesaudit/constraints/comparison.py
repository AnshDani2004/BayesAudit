"""Compare canonical registry state to received envelope state."""

from __future__ import annotations

from pydantic import Field

from bayesaudit.constraints.inheritance import (
    INHERITANCE_SCHEMA_VERSION,
    CanonicalConstraintRegistry,
    ConstraintEnvelope,
    ConstraintEnvelopeEntry,
    ConstraintRegistryEntry,
    normalize_rule,
)
from bayesaudit.hash_utils import text_hash
from bayesaudit.schemas import StrictModel


class ConstraintComparisonResult(StrictModel):
    schema_version: str = INHERITANCE_SCHEMA_VERSION
    constraint_id: str
    envelope_id: str | None
    classification: str
    canonical_hash: str | None = None
    visible_hash: str | None = None
    depth: int = 0
    branch_id: str | None = None
    evidence: dict[str, str] = Field(default_factory=dict)


def compare_envelope(
    registry: CanonicalConstraintRegistry,
    envelope: ConstraintEnvelope | None,
    *,
    depth: int = 0,
) -> list[ConstraintComparisonResult]:
    if envelope is None:
        return [
            ConstraintComparisonResult(
                constraint_id=entry.constraint_id,
                envelope_id=None,
                classification="missing_envelope",
                canonical_hash=entry.canonical_hash,
                depth=depth,
            )
            for entry in registry.entries
        ]

    registry_map = registry.entry_map()
    results: list[ConstraintComparisonResult] = []
    seen: set[str] = set()
    for entry in envelope.constraint_entries:
        canonical = registry_map.get(entry.constraint_id)
        seen.add(entry.constraint_id)
        if canonical is None:
            results.append(
                ConstraintComparisonResult(
                    constraint_id=entry.constraint_id,
                    envelope_id=envelope.envelope_id,
                    classification="added",
                    visible_hash=entry.visible_hash,
                    depth=depth,
                    branch_id=envelope.branch_id,
                )
            )
            continue
        classification = classify_entry(canonical, entry)
        results.append(
            ConstraintComparisonResult(
                constraint_id=entry.constraint_id,
                envelope_id=envelope.envelope_id,
                classification=classification,
                canonical_hash=canonical.canonical_hash,
                visible_hash=entry.visible_hash,
                depth=depth,
                branch_id=envelope.branch_id,
                evidence={"visible_rule": entry.visible_rule},
            )
        )
    for canonical in registry.entries:
        if canonical.constraint_id not in seen:
            results.append(
                ConstraintComparisonResult(
                    constraint_id=canonical.constraint_id,
                    envelope_id=envelope.envelope_id,
                    classification="dropped",
                    canonical_hash=canonical.canonical_hash,
                    depth=depth,
                    branch_id=envelope.branch_id,
                )
            )
    return sorted(results, key=lambda result: result.constraint_id)


def classify_entry(canonical: ConstraintRegistryEntry, entry: ConstraintEnvelopeEntry) -> str:
    canonical_hash = canonical.canonical_hash
    source_privilege = int(canonical.source_privilege_level)
    current_privilege = int(entry.current_privilege_level)
    visible_rule = entry.visible_rule
    normalized_visible = normalize_rule(visible_rule)
    expected_visible_hash = text_hash(normalized_visible)
    if entry.canonical_hash_reference != canonical_hash:
        return "corrupted"
    if entry.visible_hash != expected_visible_hash:
        return "corrupted"
    if entry.constraint_version != canonical.constraint_version:
        return "stale"
    if current_privilege > source_privilege:
        return "privilege_demoted"
    if not set(canonical.scope).issubset(set(entry.scope)):
        return "weakened"
    if normalized_visible == canonical.canonical_normalized:
        return "preserved_exact"
    if visible_rule.startswith("Equivalent paraphrase:"):
        return "preserved_equivalent"
    if visible_rule.startswith("Weakened:") or visible_rule.startswith("Unrelated rule:"):
        return "weakened"
    if visible_rule.startswith("Strengthened:"):
        return "strengthened"
    if visible_rule.startswith("Contradicts:"):
        return "contradicted"
    return "unverifiable"
