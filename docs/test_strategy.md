# Test Strategy

## Principles

Tests should protect scientific validity as much as software correctness. A passing run should mean that tasks validate, scorers are deterministic, policies account for budget correctly, and stored results remain analyzable.

## Phase 1 Tests

- schema imports succeed
- all example scenario YAML files validate against `BenchmarkTask`
- every required domain has at least one fixture
- constraint IDs are unique within a task
- structured or verified delegation settings are internally consistent
- CLI fixture validation runs without credentials

## Phase 2 Tests

- deterministic scorer tests for every seed task family
- mock model produces complete trajectories
- single-agent and unstructured delegation write complete logs
- final-output-only and trajectory-level violation labels differ when an internal-only failure is injected
- storage round trips JSONL and writes stable normalized Parquet tables
- experiment runner dry-runs, resumes without duplicate completed runs, and preserves failures

Current Phase 2 coverage contains 50 tests across schema validation, mock behavior, tool environment, workflows, scorers, storage, runner, and CLI.

## Phase 3 Tests

Current total coverage contains 85 tests. Phase 3 adds envelope construction, hash stability, parent linkage, branch copies, mutation serialization and determinism, verification positive and negative controls, repair strategies, retention metrics, branching, depth-four workflows, normalized inheritance storage, and same-schedule architecture checks.

## Phase 3 Tests

- structured inheritance forwards the constraint object unchanged
- verified inheritance refuses missing constraint state
- retention metrics detect dropped, changed, or added constraints

## Phase 4 Tests

Current total coverage contains 131 tests. Phase 4 adds redacted observation checks, checkpoint lifecycle checks, deterministic auditor checks, hard budget accounting, five baseline policy families, oracle isolation, shadow and intervention outcomes, detection matching, counterfactual outcomes, normalized oversight storage, runner safeguards, and CLI commands.

- no-oversight policy never intervenes
- random policy respects expected audit budget over many seeds
- fixed policy audits configured checkpoints
- rule-based policy fires on every documented risk indicator
- oracle policy is unavailable outside evaluation mode

## Phase 5 Tests

Current total coverage contains 210 collected tests. Phase 5 adds feature leakage guards, monitoring dataset persistence, grouped splits, monitor training and prediction bounds, calibration methods, ranking and calibration metrics, abstention, OOD diagnostics, Bayesian risk-state updates, adaptive budget policies, provider safety gates, annotation export/import, model-card generation, and CLI smoke commands.

- LLM judge structured output validates
- calibration metrics match known toy examples
- Bayesian posterior updates are deterministic under fixed seeds
- adaptive policy accounts for remaining budget
- real-provider calls are blocked unless explicitly enabled

## Phase 6 Tests

Current total coverage contains 331 collected tests. Phase 6 adds attacker-observation leakage checks, attack primitive metadata/application/negative controls, attacker determinism and budget enforcement, Bayesian estimator updates, start-stop behavior, matrix and restricted-game helpers, displacement classification, red-team loop safeguards, and CLI smoke commands.

- opportunistic attacker improves expected utility only under favorable estimates
- strategic attacker changes target selection when policy observability changes
- concealment is represented as synthetic artifact metadata
- oracle attacker access is blocked outside evaluation mode

## Phase 7 Tests

Current total coverage contains 426 collected tests. The previous structured-output repair-template skip was removed; the repair prompt now has direct coverage and no Phase 7 test skip is required for mock/offline behavior. Phase 7 tests cover branch/base manifest metadata, provider gate failures, credential-free configs, CI blocking, cost/token/request/trajectory ceilings, permission records, cache hits, stable request hashes, sampling/model/prompt cache invalidation, partial cache rejection, mock connectivity, prompt rendering, hidden-label leakage checks, structured-output parsing and bounded repair, workflow-quality flags, scorer-human disagreement records, blind annotation exports, sampling probabilities, agreement metrics, monitor/calibration/OOD transfer summaries, oversight feasibility, task/scorer readiness, freeze proposal generation, Phase 8 planning, and CLI dry-run commands.

## Continuous Integration

The default CI target should run:

```bash
ruff check .
mypy src tests
pytest
```

No CI job may require real API keys.
