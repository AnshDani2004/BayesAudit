# Phase 7 Report

Implementation status: provider-neutral pilot infrastructure has been added, with all validation paths mock-safe and credential-free by default.

Repository:

- Base branch: `main`
- Base commit: `f5c1962`
- Phase 7 branch: `codex/phase7-real-model-pilot`
- PR: `#1`
- CI status before empirical authorization: green

Provider integrations:

- Mock provider config for CI and local validation.
- OpenAI Stage A and Stage A.1 connectivity configs for tightly capped real-provider requests.
- Disabled remote API template.
- Disabled local/open-weight template.

Safety gates:

- Real calls require explicit config enablement, `--allow-provider-calls`, exact provider/model IDs, credentials where applicable, hard cost/token/request/trajectory ceilings, manifest generation, writable output, adapter dry-run validation, and non-CI execution.

Pilot scope:

- Domains: privacy, authorization, evidence.
- Architectures: single-agent connectivity, unstructured delegation, structured inheritance.
- Depths: 1 and 2 after connectivity.
- Behaviors: honest, opportunistic, and one predefined synthetic selective-attacker condition in the full config.
- Oversight: none, rule-based, and one adaptive feasibility condition.

Current empirical status:

- Models used: `mock-deterministic-phase7` and Stage A/A.1 requests to `gpt-5-nano-2025-08-07`.
- Provider selected for Stage A and A.1 real execution: `openai`.
- Exact model selected for Stage A and A.1 real execution: `gpt-5-nano-2025-08-07`.
- Provider authorization result: allowed after explicit config enablement, `OPENAI_API_KEY` presence check, non-CI check, and CLI ceilings.
- Requests planned for default connectivity dry run: `1`.
- Requests completed against real providers: `1`.
- Requests cached from real providers: `1`.
- Requests failed against real providers: `1`.
- Actual cost: Stage A unreconciled; Stage A.1 reconciled at `$0.000064`.
- Actual token usage: Stage A unreconciled; Stage A.1 used `64` total tokens.
- Real-model trajectory count: `2` attempted across Stage A and Stage A.1.
- Valid real-model trajectory count: `1`.
- Excluded real-model trajectory count: `1`.
- Pilot observations: Stage A failed before cache verification; Stage A.1 passed and cache verification passed.
- Synthetic comparisons: previous phases only.
- Test status after Stage A.1 adapter coverage: `472 passed`.

## Stage A: Real-Provider Connectivity

- Date: `2026-07-31`
- Branch: `codex/phase7-real-model-pilot`
- Base commit: `f5c1962`
- Starting commit: `055009a`
- Stage A execution commit: `be0e693`
- Provider: `openai`
- Exact model ID: `gpt-5-nano-2025-08-07`
- Credential environment variable: `OPENAI_API_KEY`
- Task: `task_privacy_aggregate_only`
- Architecture: `single_agent`
- Behavior: `honest`
- Oversight condition: `none`
- Attacker condition: `none`
- Planned trajectories: `1`
- Attempted trajectories: `1`
- Valid trajectories: `0`
- Excluded trajectories: `1`
- Planned provider requests: `1`
- Actual provider requests: `1`
- Cached executions: `0`
- Failed requests: `1`
- Estimated input tokens: `1000`
- Cached input tokens: not available
- Estimated output tokens: `300`
- Reasoning tokens: not available
- Estimated total tokens: `1300`
- Estimated cost: `$0.0013`
- Actual cost: not reconciled
- Cost ceiling utilization: estimated `13%`; actual not reconciled
- Token ceiling utilization: estimated `43.3%`; actual not reconciled
- Request ceiling utilization: `50%`
- Trajectory ceiling utilization: `100%`
- Structured parsing result: not attempted; no usable model-output text was preserved.
- Cache verification result: failed; no complete cache entry was created.
- Duplicate-billing verification result: no duplicate paid request was made; the identical rerun was not executed because it would not have been cache-served.
- Credential-redaction result: passed; the `OPENAI_API_KEY` value was not found in workspace files or Stage A artifacts by redacted scan.
- Raw-response preservation result: failed for this execution; adapter repair added raw failure-payload preservation for future empty-output responses.
- External-action result: passed; no external tools were configured or invoked.
- Stage A status: `failed`

## Stage A.1: Response Diagnostic and Connectivity Retry

- Date: `2026-07-31`
- Branch: `codex/phase7-real-model-pilot`
- Starting commit: `7b31e00`
- Stage A.1 repair commit: `fee7e2a`
- Provider: `openai`
- Exact model ID: `gpt-5-nano-2025-08-07`
- Credential environment variable: `OPENAI_API_KEY`
- Task: `task_privacy_aggregate_only`
- Architecture: `single_agent`
- Behavior: `honest`
- Oversight condition: `none`
- Attacker condition: `none`
- Reasoning effort: `minimal`
- Max output tokens: `1000`
- Streaming: disabled
- Structured output request: not used
- Planned provider requests: `1`
- Actual provider requests: `1`
- Cached local executions: `1`
- Failed requests: `0`
- Response status: `completed`
- Incomplete reason: none
- Output item types: `reasoning`, `message`
- Message content item types: `output_text`
- Extraction path: `output.message.content.output_text`
- Structured parsing result: exact diagnostic JSON matched expected value.
- Input tokens: `31`
- Cached input tokens: `0`
- Output tokens: `33`
- Reasoning tokens: `0`
- Total tokens: `64`
- Estimated cost: `$0.0015`
- Reconciled cost: `$0.000064`
- Token ceiling utilization: `2.13%`
- Cost ceiling utilization: `0.64%`
- Request ceiling utilization: `100%` for actual provider requests
- Trajectory ceiling utilization: `100%`
- Cache verification result: passed; second local execution used the same request hash and the complete cache entry.
- Duplicate-billing result: passed; second local execution performed zero provider calls.
- Raw-response preservation result: passed; redacted raw provider response was written before extraction.
- Previous Stage A reconciliation status: unreconciled from preserved artifacts.
- External-action result: passed; no tools were configured or invoked.
- Stage A.1 status: `passed`

Measurement validation:

- Workflow-quality findings: not available for real traces; mock-safe dry-run artifacts only.
- Scorer-human agreement: not available; no real trace annotation has been performed.
- Annotation agreement: not available; no two-annotator real trace sample exists.
- Internal-only violations: none observed in real traces because no real traces exist.
- Constraint drift: none observed in real traces because no real traces exist.
- Monitor transfer, calibration transfer, OOD diagnostics, and oversight feasibility outputs have mock-safe dry-run artifacts only.

Readiness:

- Task-readiness counts from dry-run placeholder classification: `ready_after_minor_repair = 12`.
- Scorer-readiness counts from dry-run placeholder classification: `ready_after_minor_repair = 3`.
- Benchmark-freeze recommendation: not ready to freeze until an explicitly authorized real-provider pilot is completed and reviewed.

Limitations:

- Stage A made one real provider request and failed before cache verification.
- Stage A.1 passed connectivity and cache verification but does not freeze the benchmark.
- Stage B has not begun.
- All Phase 7 results produced by default commands are implementation validation, dry-run plans, or placeholder artifacts for downstream review.
- No benchmark freeze or Phase 8 start is authorized by this report.
