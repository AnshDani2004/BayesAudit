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

This repository is currently at Phase 7: Real Model Pilot, Measurement Validation, and Benchmark Refinement.

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
- leakage-resistant monitor datasets built from redacted oversight observations
- grouped train/development/calibration/confirmatory split manifests
- constant, rule-score, logistic, tree-stump, Bayesian-logistic, and mock LLM-judge monitors
- Platt, isotonic, temperature, and beta calibration helpers
- abstention, OOD diagnostics, model cards, and annotation export/import
- Beta-Bernoulli and online Bayesian-logistic risk states
- budget-aware adaptive audit policies for shadow and intervention evaluation
- dry-run provider cost manifests and hard real-provider safety gates
- synthetic attacker observations with explicit knowledge tiers
- safe deterministic attack primitives
- ten attacker families, including evaluation-only oracle attacker
- attacker-defender smoke matrices and restricted empirical-game analysis
- selection-bias, displacement, and offline red-team-loop helpers
- Phase 7 pre-pilot checkpoint, provider configs, pilot manifests, permission records, request cache/ledger contracts, prompt rendering, structured-output parsing, workflow-quality flags, annotation sampling, transfer summaries, readiness classification, freeze proposal generation, and Phase 8 planning scaffolds
- tests for schema validity, workflows, scorers, storage, and integration

Not implemented yet:

- ungated real model-provider execution
- completed authorized real-provider pilot runs
- empirical claims about real LLM behavior
- completed human annotation campaign

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

Run Phase 5 learned-monitoring smoke checks:

```bash
python -m bayesaudit.cli build-monitor-dataset --config configs/experiments/phase5_smoke.yaml
python -m bayesaudit.cli create-monitor-splits --config configs/experiments/phase5_smoke.yaml
python -m bayesaudit.cli train-monitor --config configs/monitors/logistic/smoke.yaml
python -m bayesaudit.cli calibrate-monitor --config configs/calibration/platt/smoke.yaml
python -m bayesaudit.cli evaluate-monitor --config configs/experiments/phase5_smoke.yaml
python -m bayesaudit.cli run-adaptive-policy --config configs/experiments/phase5_smoke.yaml
python -m bayesaudit.cli run-real-pilot --config configs/experiments/phase5_real_pilot.yaml --dry-run
```

Run Phase 6 synthetic attacker smoke checks:

```bash
python -m bayesaudit.cli validate-attackers
python -m bayesaudit.cli validate-attacks
python -m bayesaudit.cli run-attacker-defender --config configs/experiments/phase6_smoke.yaml
python -m bayesaudit.cli compare-attack-selection --config configs/experiments/phase6_selection.yaml --dry-run
python -m bayesaudit.cli build-payoff-matrix --config configs/experiments/phase6_smoke.yaml
python -m bayesaudit.cli run-red-team-loop --config configs/experiments/phase6_red_team_loop.yaml --dry-run
```

Run Phase 7 mock-safe pilot infrastructure checks:

```bash
python -m bayesaudit.cli validate-provider-config --config configs/providers/mock/smoke.yaml
python -m bayesaudit.cli estimate-pilot-cost --config configs/experiments/phase7_connectivity.yaml
python -m bayesaudit.cli run-provider-connectivity --config configs/experiments/phase7_connectivity.yaml --dry-run
python -m bayesaudit.cli run-real-workflow-pilot --config configs/experiments/phase7_workflow.yaml --dry-run
python -m bayesaudit.cli run-measurement-pilot --config configs/experiments/phase7_measurement.yaml --dry-run
python -m bayesaudit.cli evaluate-monitor-transfer --config configs/experiments/phase7_monitor_transfer.yaml --dry-run
python -m bayesaudit.cli run-real-oversight-pilot --config configs/experiments/phase7_oversight.yaml --dry-run
```

## Research Integrity

BayesAudit must not report fabricated findings. Hypotheses, primary metrics, and confirmatory analyses are recorded before main-study execution. Pilot results may be used to repair tasks and scorers, but main benchmark changes after preregistration freeze must be documented as deviations.

All Phase 2 through Phase 6 trajectories, learned-monitor smoke results, and attacker-defender outputs are synthetic mock-model artifacts. Phase 7 introduces real-provider pilot infrastructure, but default configs and CI remain mock-safe and credential-free. Real-provider results may be created only through explicitly authorized commands with hard cost, token, request, and trajectory ceilings, and must be labeled exploratory pilot data.
