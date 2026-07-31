# Schema Migration: v2 To v3

Phase 3 does not change the core trajectory schema version. `bayesaudit.v2` remains the active data contract for tasks, trajectories, steps, model responses, tool calls, domain violations, detections, interventions, budgets, and score results.

Phase 3 adds separate inheritance artifact records with schema version `bayesaudit.inheritance.v1`:

- canonical constraint registries
- constraint envelopes
- mutation events
- verification events
- repair events
- comparison results
- retention metrics
- aggregation provenance

These records are stored in trajectory metadata and normalized Phase 3 tables. Existing Phase 2 artifacts remain readable because no required v2 fields were removed or reinterpreted.

No `bayesaudit.v3` core migration is required at this point.

