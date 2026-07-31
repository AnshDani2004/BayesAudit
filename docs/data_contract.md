# Data Contract

Phase 2 and Phase 3 use core schema version `bayesaudit.v2`.

## Key Migration Decisions

- `ModelClient.complete()` and workflow execution are async.
- `ModelResponse` stores provider, model ID/version, token usage, latency, request ID, seed, and raw metadata.
- Objective `ViolationEvent` records are separate from `DetectionEvent` and `InterventionEvent`.
- Ground-truth violations do not contain `detected` or `prevented` fields.
- `ToolCallRecord` stores environment-derived authorization and execution status. Agents do not supply ground-truth authorization.
- `TrajectoryStep` stores hierarchy fields: sequence index, parent step, delegation ID, branch ID, agent IDs, role, depth, kind, input messages, model response, constraint snapshots, tools, detections, interventions, and metadata.
- `ConstraintSnapshot` stores canonical and visible rules, hashes, source levels, retention status, mutation type, acknowledgment, and verification status.
- `Trajectory` stores task version, scenario hash, experiment/run IDs, model configuration, budget state, status, timestamps, configuration hash, prompt version, usage totals, and errors.
- `ScoreResult` stores task success, correctness, utility, trajectory/final/internal violation counts, severity-weighted harm, component scores, evidence, warnings, and status.

## Validation

Benchmark tasks validate that:

- unknown fields are rejected
- constraint IDs are unique within a task
- authorized and prohibited tool sets are disjoint
- task and scorer versions are explicit
- scenario hashes are stable under repeated loads

Trajectory validation ensures parent steps precede child steps and root steps have depth zero.

## Phase 2 Limits

Constraint-retention labels are injected by mock behavior. Phase 2 does not claim to solve semantic equivalence or proxy detection generally.

## Phase 3 Inheritance Artifacts

Phase 3 adds separate inheritance artifacts with schema version `bayesaudit.inheritance.v1`. These records live in trajectory metadata and normalized storage tables. They do not require a core `bayesaudit.v3` migration.

## Phase 4 Oversight Artifacts

Phase 4 adds separate oversight artifacts with schema version `bayesaudit.oversight.v1`. Core `bayesaudit.v2` trajectories remain readable.

Oversight artifacts include checkpoints, redacted observations, policy state records, audit decisions, audit feedback, findings, intervention decisions, intervention outcomes, budget transactions, detection matches, counterfactual outcomes, metrics, and frontier points.

Normalized Phase 4 tables are prefixed with `oversight_`.

## Phase 5 Monitoring Artifacts

Phase 5 adds separate monitoring artifacts with schema version `bayesaudit.monitoring.v1`. Core `bayesaudit.v2` trajectories and Phase 4 oversight observations remain readable.

Monitoring artifacts include monitor examples, monitor predictions, dataset manifests, grouped split manifests, monitor artifacts, calibration artifacts, OOD score records, abstention records, judge responses, provider call manifests, posterior snapshots, Bayesian update records, and adaptive policy decisions.

Normalized Phase 5 dataset tables are `monitor_examples`, `monitor_labels`, and `monitor_features`.

## Phase 6 Attack Artifacts

Phase 6 adds `bayesaudit.attack.v1` artifacts. They include objectives, opportunities, attacker observations, decisions, states, events, concealment events, attacker-defender outcomes, payoff matrices, displacement records, red-team iterations, and evaluation manifests. Core trajectories remain unchanged.

## Phase 7 Pilot Artifacts

Phase 7 adds `bayesaudit.pilot.v1` artifacts. They include pilot manifests, provider permission records, cost plans, provider request records, provider response records, provider failure records, request-cache entries, billed-request ledger rows, prompt-render records, structured-output parse records, workflow-quality records, scorer-human comparison records, annotation sample records, annotation agreement records, monitor-transfer metrics, calibration-transfer metrics, OOD metrics, oversight-feasibility records, task-readiness records, scorer-readiness records, freeze proposals, and Phase 8 planning estimates.

Core `bayesaudit.v2` trajectories remain readable. Credentials are never part of any Phase 7 artifact.
