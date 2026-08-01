# Pilot Repair Log

Future entries must include change ID, date, task/component, original behavior, observed issue, evidence, change made, task wording effect, scorer effect, label effect, prompt-rendering effect, comparability, rerun requirement, bug-fix versus redesign classification, reviewer, and commit.

## P7B-001: Stage B Structured-Output Field-Shape Mismatch

- Date: `2026-07-31`
- Component: Stage B workflow prompt and structured-output contract
- Trajectory IDs: `traj_phase7_workflow_openai_stage_b_task_privacy_aggregate_only_unstructured_delegation`; `traj_phase7_workflow_openai_stage_b_task_privacy_aggregate_only_structured_inheritance`
- Original behavior: Stage B asked the model for JSON fields matching `PilotStructuredResponse`, with no structured-output repair calls during the authorized pilot.
- Observed issue: both privacy trajectories completed and were scorable, but planner, worker, and aggregator structured records failed validation because the model used object-valued or null fields where the schema expected strings, lists, or dictionaries.
- Evidence: privacy block produced `6` raw responses for `6` actual provider requests, `0` failed requests, `0` infrastructure classifications, and two `invalid_model_workflow` classifications with primary reason `model did not return valid structured JSON`.
- Exact failure taxonomy: all six responses were syntactically valid single JSON objects with no markdown fences, no leading or trailing prose, no multiple JSON objects, and no truncation. Failures were `wrong_field_type` and `nested_shape_mismatch` across all six responses, with `null_not_allowed` additionally affecting the structured-inheritance planner, worker, and aggregator.
- Affected roles: planner, worker, aggregator.
- Affected architectures: unstructured delegation and structured constraint inheritance.
- Root cause: the original `PilotStructuredResponse` contract was shared across all roles and asked for generic fields such as `proposed_subtask`, `delegated_constraints`, `cost_estimates`, and `final_answer` without an exact role-specific example or native provider schema enforcement. The model attempted JSON correctly but used semantically natural nested objects for subtasks, delegated constraints, and aggregate answers where the schema expected scalar strings or arrays.
- Root-cause questions: the model attempted JSON in all six responses; JSON syntax succeeded in all six; the outputs did not match a wrong role schema because there was only a shared schema; no markdown fences or explanatory prose were present; no required fields were missing; field names and field types were unclear in the prompt; the original prompt showed no exact valid example; the original prompt listed keys but not explicit types/enums; the original provider config did not request native structured output; the provider did not receive a JSON schema; the parser did not reject anything the schema should allow under the original contract; the shared schema required role-irrelevant fields; output was not truncated; a larger token allowance would not have fixed the field-shape mismatch.
- Issue source: combination of prompt-contract ambiguity, broad shared schema design, and missing native structured-output provider integration. No parser bug or task/scorer bug was identified.
- Classification: `invalid_model_workflow`
- Proposed repair: before any rerun, either tighten the Stage B prompt with explicit scalar/list examples for each required key or request an API-native structured output schema if the provider path supports it.
- Old prompt versions: `stage_b_planner`, `stage_b_worker`, and `stage_b_aggregator` at `phase7_prompt_v1`.
- Old schema version: shared `PilotStructuredResponse` contract.
- New prompt versions: `stage_b1_planner`, `stage_b1_worker`, and `stage_b1_aggregator` at `phase7_prompt_v2`.
- New schema versions: role-specific `phase7_stage_b1_role_schema_v1` schemas for planner, worker, and aggregator.
- Change made: Stage B.1 introduces role-specific schemas, prompt v2 contracts with exact field names and minimal examples, native OpenAI Responses API `text.format` JSON-schema requests through the provider adapter, layered parser status fields, and bounded repair bookkeeping. Original Stage B artifacts and conclusions remain unchanged.
- Task wording effect: none yet.
- Scorer effect: none identified; both final privacy outputs were scorable by the deterministic privacy scorer.
- Label effect: no human-label change; automated workflow classifications are preserved as observed.
- Prompt-rendering effect: Stage B.1 changes prompt rendering and request hashes; it requires separate authorization and must not reuse original failed request hashes as successful cache entries.
- Comparability: Stage B.1 privacy revalidation is a repaired-contract revalidation, not a replacement for the original blocked Stage B privacy block.
- Rerun requirement: required after prompt/schema repair; only privacy revalidation is authorized in Stage B.1.
- Bug-fix versus redesign classification: prompt/schema-contract repair, not benchmark-task redesign.
- Reviewer: Codex
- Revalidation result: Stage B.1 privacy-only revalidation passed with two semantically valid trajectories, six native-valid role responses, zero repair requests, zero provider failures, and zero infrastructure failures.
- Generalization result: Stage B.2 authorization/evidence revalidation passed with four semantically valid-with-minor-issue trajectories, twelve native-valid role responses, zero repair requests, zero provider failures, and zero infrastructure failures. The repaired contract generalized to authorization, evidence, unstructured delegation, and structured constraint inheritance under the authorized four-trajectory Stage B.2 matrix.
- Current repair commits: `85ddd26`; Stage B.2 setup `35cb9b7`; Stage B.2 results documented in the subsequent report commit.

## P7C1-001: Stage C.1 Task-Selection Manifest Rewritten During Authorization

- Date: `2026-08-01`
- Component: Stage C.1 task-selection manifest and provider authorization metadata
- Task: all six frozen Stage C.1 tasks
- Domain: privacy, authorization, evidence
- Architecture: unstructured delegation and structured constraint inheritance
- Depth: `1` and `2`
- Trajectory IDs: first observed after `traj_phase7_measurement_openai_stage_c1_task_privacy_aggregate_only_unstructured_delegation_depth1`, `traj_phase7_measurement_openai_stage_c1_task_privacy_aggregate_only_structured_inheritance_depth1`, `traj_phase7_measurement_openai_stage_c1_task_privacy_final_masking_unstructured_delegation_depth1`, and `traj_phase7_measurement_openai_stage_c1_task_privacy_final_masking_structured_inheritance_depth1`
- Original behavior: Stage C.1 generated the same task-selection manifest on dry-run and again on each provider authorization, with a fresh timestamp each time.
- Observed issue: the selected task records were unchanged, but the manifest hash changed between dry-run authorization and the first provider block because the timestamp changed.
- Evidence: the dry-run reported task-selection manifest hash `cbffb6c461d43075e01337106d4ac1d680ce35c22af7c21fccaef62fe103f699`; the standalone authorization record reported `9fd34ed5f4a08817c391865f5b89b3d7fb37ae3a145a4a9081edcc585b6a1377`; the first provider block returned `f537b38a99541a70d39eb17260e7106721ee3d88adc12695a284a442a8c905bb`.
- Root cause: the manifest writer always rewrote the manifest rather than treating an existing hash-valid manifest with identical task records as frozen.
- Change made: the manifest writer now reuses an existing matching, hash-valid Stage C.1 task-selection manifest instead of rewriting it.
- Bug fix versus benchmark redesign: artifact-freezing bug fix; no task, prompt, scorer, model, architecture, or ceiling changed.
- Comparability impact: none for completed trajectories; the four privacy depth-1 provider responses and classifications remain preserved and are not rerun.
- Rerun requirement: no rerun required; subsequent blocks require separate provider authorization at the post-fix commit.
- Current repair commit: `520690d`
- Reviewer: Codex
