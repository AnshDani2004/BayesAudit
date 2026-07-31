# Verification And Repair

Verified inheritance validates envelopes before worker execution.

## Verification Checks

- envelope exists
- task ID and task version match
- branch ID matches
- canonical set hash matches
- integrity checksum matches
- required constraints are present
- unknown constraints are detected
- constraint versions are current
- required scopes are preserved
- privilege levels are not demoted
- critical constraints are acknowledged

## Repair Strategies

Strict refusal rejects invalid required state.

Canonical restoration reconstructs the envelope from the canonical registry when a deterministic repair is configured.

Minimal repair currently uses the same deterministic reconstruction path for recoverable synthetic corruption.

Clarification request records an architectural pause/refusal outcome. It is not human oversight.

Repair outcomes are stored as `RepairEvent` records and kept separate from `DetectionEvent` and `InterventionEvent`.

