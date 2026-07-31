"""Constraint snapshot construction for Phase 2 workflows."""

from __future__ import annotations

from bayesaudit.hash_utils import text_hash
from bayesaudit.schemas import (
    Constraint,
    ConstraintSnapshot,
    MutationType,
    RetentionStatus,
    VerificationStatus,
)


def snapshot_constraints(
    constraints: list[Constraint],
    *,
    current_source_level: int,
    inherited_from_step_id: str | None,
    dropped_constraint_ids: set[str] | None = None,
    weakened_constraint_ids: set[str] | None = None,
    strengthened_constraint_ids: set[str] | None = None,
    paraphrased_constraint_ids: set[str] | None = None,
    contradicted_constraint_ids: set[str] | None = None,
    acknowledged: bool = False,
) -> list[ConstraintSnapshot]:
    """Create deterministic snapshots with injected mutation labels.

    Phase 2 does not attempt semantic equivalence detection. Mutation labels come
    from explicit mock behavior so tests can probe the data contract.
    """

    dropped_constraint_ids = dropped_constraint_ids or set()
    weakened_constraint_ids = weakened_constraint_ids or set()
    strengthened_constraint_ids = strengthened_constraint_ids or set()
    paraphrased_constraint_ids = paraphrased_constraint_ids or set()
    contradicted_constraint_ids = contradicted_constraint_ids or set()
    snapshots: list[ConstraintSnapshot] = []
    for constraint in constraints:
        retention = RetentionStatus.PRESERVED
        mutation = MutationType.NONE
        visible_rule = constraint.rule
        if constraint.id in dropped_constraint_ids:
            retention = RetentionStatus.DROPPED
            mutation = MutationType.OMITTED
            visible_rule = ""
        elif constraint.id in weakened_constraint_ids:
            retention = RetentionStatus.WEAKENED
            mutation = MutationType.WEAKENED_SCOPE
            visible_rule = f"Weakened: {constraint.rule}"
        elif constraint.id in strengthened_constraint_ids:
            retention = RetentionStatus.STRENGTHENED
            mutation = MutationType.STRENGTHENED_SCOPE
            visible_rule = f"Strengthened: {constraint.rule}"
        elif constraint.id in paraphrased_constraint_ids:
            retention = RetentionStatus.PARAPHRASED_EQUIVALENT
            mutation = MutationType.PARAPHRASED
            visible_rule = f"Equivalent paraphrase: {constraint.rule}"
        elif constraint.id in contradicted_constraint_ids:
            retention = RetentionStatus.CONTRADICTED
            mutation = MutationType.CONTRADICTION
            visible_rule = f"Contradicts: {constraint.rule}"

        snapshots.append(
            ConstraintSnapshot(
                constraint_id=constraint.id,
                canonical_rule=constraint.rule,
                visible_rule=visible_rule,
                category=constraint.category,
                severity=constraint.severity,
                original_source_level=0,
                current_source_level=current_source_level,
                inherited_from_step_id=inherited_from_step_id,
                canonical_hash=text_hash(constraint.rule),
                visible_hash=text_hash(visible_rule),
                retention_status=retention,
                mutation_type=mutation,
                acknowledged_by_agent=acknowledged,
                verification_status=(
                    VerificationStatus.ACKNOWLEDGED
                    if acknowledged
                    else VerificationStatus.NOT_REQUIRED
                ),
            )
        )
    return snapshots
