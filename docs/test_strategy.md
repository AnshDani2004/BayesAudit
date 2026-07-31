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

- LLM judge structured output validates
- calibration metrics match known toy examples
- Bayesian posterior updates are deterministic under fixed seeds
- adaptive policy accounts for remaining budget

## Phase 6 Tests

- opportunistic attacker improves reward or reduces effort when undetected
- strategic attacker changes target selection when policy observability changes
- concealment can produce compliant final output despite internal violation

## Continuous Integration

The default CI target should run:

```bash
ruff check .
mypy src tests
pytest
```

No CI job may require real API keys.
