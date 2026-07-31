# Phase 5 Report

Phase 5 adds calibrated learned monitoring and Bayesian adaptive oversight on top of the Phase 4 budget-constrained replay layer.

Implemented:

- monitor dataset builder from completed redacted observations
- explicit feature schema and leakage guards
- grouped split manifests for in-distribution and holdout evaluations
- local monitor baselines and mock structured LLM judge
- calibration, abstention, OOD scoring, and model-card generation
- Beta-Bernoulli and Bayesian-logistic online risk states
- budget-aware adaptive allocation policies
- annotation export/import for future human labels
- dry-run provider manifests and real-provider gates

Limitations:

- smoke results are synthetic and should not be interpreted as real-model findings
- monitor baselines are intentionally lightweight
- strategic attacker behavior remains Phase 6
- human annotation has a workflow but not a completed labeled dataset

Phase 6 should start by adding strategic behavior profiles and attacker-defender matrices while preserving the Phase 5 monitor and adaptive-policy interfaces.
