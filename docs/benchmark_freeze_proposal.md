# Benchmark Freeze Proposal

Status: not frozen.

The generated Phase 7 freeze artifact is a proposal only. It must include final task set, removed tasks, redesigned tasks, scorer versions, prompt-renderer versions, domain definitions, architecture definitions, constraint schema, tool environment, annotation guide, exclusion rules, metrics, planned monitors, policy conditions, attacker conditions, limitations, unresolved risks, and a recommendation.

Current dry-run proposed task set:

- `task_privacy_aggregate_only`
- `task_privacy_department_counts`
- `task_privacy_final_masking`
- `task_privacy_tool_argument_minimization`
- `task_authorization_external_scope`
- `task_authorization_local_only`
- `task_authorization_no_email`
- `task_authorization_approval_claim`
- `task_evidence_claim_support`
- `task_evidence_supplied_docs_only`
- `task_evidence_inference_boundary`
- `task_evidence_no_fabricated_metric`

Task-readiness classification is provisional because no real-provider trajectories or human labels exist. Scorer-readiness classification is also provisional for the same reason.

Removed tasks: none yet.

Repaired tasks: none yet.

Redesigned tasks: none yet.

Prompt-template version: `phase7_prompt_v1`.

Tool-environment version: inert synthetic tool environment only.

Known limitations:

- No Stage A real-provider response has been obtained.
- No Stage B workflow has been manually reviewed.
- No real trajectory has been scored or annotated.
- No real monitor-transfer, calibration-transfer, or OOD result exists.

Unresolved risks:

- Provider/model choice may materially affect workflow quality and costs.
- Scorer disagreement modes on real traces are unknown.
- Human annotation burden and agreement are unknown.

Benchmark freeze requires explicit approval before Phase 8.

Recommendation: Not ready to freeze.
