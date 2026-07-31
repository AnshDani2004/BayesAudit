# Attacker Observations

Phase 6 adds `AttackerObservation` as a red-team-side contract separate from `OversightObservation`.

Knowledge tiers:

- `tier0_task_only`: current task, visible constraints, available synthetic actions.
- `tier1_protocol_class`: broad policy family only.
- `tier2_public_config`: public budget, schedule, rule descriptions, monitor type, intervention types.
- `tier3_black_box_feedback`: public audits, blocks, clarifications, escalations, and terminations.
- `tier4_monitor_score`: explicitly exposed benchmark monitor score.
- `tier5_white_box_synthetic`: evaluation-only synthetic policy or monitor parameters.

Forbidden fields include hidden labels, future audit draws, future policy actions, oracle state, counterfactual outcomes, human annotations, unobserved branches, and future tool results.
