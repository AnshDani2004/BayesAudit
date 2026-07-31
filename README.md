# BayesAudit

Adaptive, budget-constrained oversight for hierarchical LLM agents.

BayesAudit is an open-source research project for studying when a human or automated monitor should inspect, interrupt, or escalate a hierarchical LLM workflow under a limited oversight budget. The core outcome is not a chatbot or dashboard; it is a reproducible empirical benchmark, policy interface, and analysis pipeline for measuring trajectory-level constraint violations.

## Research Focus

BayesAudit studies how safety constraints weaken or fail as tasks are delegated through agent hierarchies, and whether Bayesian adaptive auditing can reduce undetected severity-weighted harm at equal oversight cost. The project compares single-agent workflows, unstructured delegation, structured constraint inheritance, and verified constraint inheritance across honest, opportunistic, and strategic agent behavior.

Primary comparison policies:

- no oversight
- random auditing
- fixed checkpoints
- rule-based risk scoring
- LLM-judge monitoring
- Bayesian adaptive oversight
- oracle auditing for evaluation upper bounds only

## Phase Status

This repository is currently at Phase 4: Budget-Constrained Oversight Baselines.

Implemented now:

- project specification and milestone acceptance criteria
- threat model, methodology, annotation guide, and preregistration draft
- typed async schema and interface definitions for tasks, constraints, trajectories, policies, and scoring
- 25 manually inspectable benchmark fixtures, five per domain
- deterministic mock model execution
- single-agent and unstructured-delegation workflows
- synthetic offline tool environment
- deterministic scorers for all five domains
- append-only JSONL and normalized Parquet storage
- offline experiment runner with resume skipping
- structured and verified constraint inheritance workflows
- canonical constraint registries, typed envelopes, mutation profiles, verification events, repair events, and retention metrics
- redacted oversight observations and checkpoint replay
- no-oversight, random, fixed-checkpoint, rule-based, and evaluation-only oracle baselines
- hard oversight budget accounting
- shadow-mode and intervention-mode oversight records
- posthoc detection matching, policy metrics, and harm-cost frontier points
- tests for schema validity, workflows, scorers, storage, and integration

Not implemented yet:

- real model-provider integrations
- empirical claims about real LLM behavior
- Bayesian adaptive oversight
- LLM-judge monitoring
- strategic attacker behavior
- human annotation workflow

## Repository Layout

```text
bayesaudit/
├── configs/
├── docs/
├── scenarios/
├── src/bayesaudit/
├── scripts/
├── tests/
├── data/
├── results/
└── notebooks/
```

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m mypy src tests
python -m compileall -q src tests scripts
```

Validate fixtures:

```bash
python -m bayesaudit.cli validate-scenarios --root scenarios
```

Run a small offline synthetic experiment:

```bash
python -m bayesaudit.cli run --config configs/experiments/phase2_mock.yaml
python -m bayesaudit.cli summarize --experiment phase2_mock
```

Run Phase 3 inheritance smoke checks:

```bash
python -m bayesaudit.cli validate-envelopes
python -m bayesaudit.cli run --config configs/experiments/phase3_smoke.yaml
python -m bayesaudit.cli summarize-inheritance --experiment phase3_smoke
python -m bayesaudit.cli compare-architectures --experiment phase3_smoke
```

Run Phase 4 oversight baselines:

```bash
python -m bayesaudit.cli validate-policies --root configs/policies
python -m bayesaudit.cli run --config configs/experiments/phase4_smoke.yaml --dry-run
python -m bayesaudit.cli run --config configs/experiments/phase4_smoke.yaml --max-runs 5
python -m bayesaudit.cli summarize-oversight --experiment phase4_smoke
python -m bayesaudit.cli compare-policies --experiment phase4_smoke
python -m bayesaudit.cli build-frontier --experiment phase4_smoke
```

## Research Integrity

BayesAudit must not report fabricated findings. Hypotheses, primary metrics, and confirmatory analyses are recorded before main-study execution. Pilot results may be used to repair tasks and scorers, but main benchmark changes after preregistration freeze must be documented as deviations.

All Phase 2 through Phase 4 trajectories are synthetic mock-model trajectories. They are useful for validating benchmark mechanics and scorer behavior, but they are not evidence about real LLM systems.
