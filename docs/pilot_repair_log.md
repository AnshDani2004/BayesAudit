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
- Current commit: pending Stage B.1 repair commit after validation.
