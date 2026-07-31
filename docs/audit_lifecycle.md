# Audit Lifecycle

Phase 4 separates detection, audit feedback, and intervention.

1. A completed synthetic trajectory is converted into ordered checkpoints.
2. A redacted observation is built for each checkpoint.
3. A policy decides whether to audit, subject to hard budget enforcement.
4. The deterministic auditor emits findings from observable features only.
5. The policy observes feedback and may emit an intervention decision.
6. Shadow mode records the intervention decision without changing the trajectory.
7. Intervention mode records synthetic execution outcomes and charges intervention or escalation cost.
8. Detection-to-violation matching is performed posthoc against scorer outputs.
9. Metrics and frontier points are computed from stored decisions, feedback, matches, and budget records.

Verified-inheritance repair and branch-refusal records remain architecture events. They are not rewritten as oversight interventions.
