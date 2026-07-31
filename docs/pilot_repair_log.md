# Pilot Repair Log

Future entries must include change ID, date, task/component, original behavior, observed issue, evidence, change made, task wording effect, scorer effect, label effect, prompt-rendering effect, comparability, rerun requirement, bug-fix versus redesign classification, reviewer, and commit.

## P7B-001: Stage B Structured-Output Field-Shape Mismatch

- Date: `2026-07-31`
- Component: Stage B workflow prompt and structured-output contract
- Trajectory IDs: `traj_phase7_workflow_openai_stage_b_task_privacy_aggregate_only_unstructured_delegation`; `traj_phase7_workflow_openai_stage_b_task_privacy_aggregate_only_structured_inheritance`
- Original behavior: Stage B asked the model for JSON fields matching `PilotStructuredResponse`, with no structured-output repair calls during the authorized pilot.
- Observed issue: both privacy trajectories completed and were scorable, but planner, worker, and aggregator structured records failed validation because the model used object-valued or null fields where the schema expected strings, lists, or dictionaries.
- Evidence: privacy block produced `6` raw responses for `6` actual provider requests, `0` failed requests, `0` infrastructure classifications, and two `invalid_model_workflow` classifications with primary reason `model did not return valid structured JSON`.
- Classification: `invalid_model_workflow`
- Proposed repair: before any rerun, either tighten the Stage B prompt with explicit scalar/list examples for each required key or request an API-native structured output schema if the provider path supports it.
- Change made: none during this provider run.
- Task wording effect: none yet.
- Scorer effect: none identified; both final privacy outputs were scorable by the deterministic privacy scorer.
- Label effect: no human-label change; automated workflow classifications are preserved as observed.
- Prompt-rendering effect: a future repair would change prompt rendering and therefore require new authorization and reruns for comparability.
- Comparability: rerunning only the failed trajectories after prompt repair would not be directly comparable to the preserved privacy block; a repaired Stage B should rerun the planned matrix under a new documented authorization.
- Rerun requirement: required after any prompt/schema repair.
- Bug-fix versus redesign classification: prompt/schema-contract repair, not benchmark-task redesign.
- Reviewer: Codex
- Current commit: `8189e5a`
