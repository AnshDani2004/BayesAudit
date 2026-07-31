# Phase 4 Report

Phase 4 adds budget-constrained oversight baselines for completed synthetic trajectories.

Implemented:

- redacted oversight observations
- lifecycle checkpoints for planning, delegation, child results, tools, aggregation, final output, verification failures, and branch refusals
- hard budget reservation, consumption, refund, and final reconciliation
- no-oversight, random, fixed-checkpoint, rule-based, and evaluation-only oracle policies
- deterministic auditor findings from observable features
- shadow-mode and intervention-mode intervention outcome records
- posthoc detection-to-violation matching
- policy metrics, harm-cost frontier points, and counterfactual outcome helpers
- runner integration for `oversight_policies`, `oversight_budgets`, `oversight_mode`, `max_runs`, and large-run safeguards
- CLI commands for policy validation, replay, summarization, comparison, inspection, and frontier building
- normalized Parquet tables for oversight runs, decisions, feedback, findings, interventions, budgets, matches, counterfactuals, and metrics

Not implemented in Phase 4:

- LLM judges
- Bayesian or contextual-bandit oversight
- strategic attacker adaptation
- real model-provider calls
- empirical claims about deployed LLM behavior

Verification:

```bash
ruff check src tests
python -m mypy src tests
python -m pytest -q
```

The current suite contains 131 passing tests.
