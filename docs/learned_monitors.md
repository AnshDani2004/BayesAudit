# Learned Monitors

Phase 5 monitor artifacts implement deterministic local baselines over leakage-resistant features:

- constant prevalence
- rule-score risk monitor
- logistic regression
- shallow tree-stump ensemble
- approximate Bayesian logistic regression
- structured mock LLM judge

Each artifact records monitor name, type, target, feature names, training dataset hash, split manifest hash, hyperparameters, and learned parameters. The confirmatory split is not required for smoke training and should be reserved for preregistered evaluation.

```bash
python -m bayesaudit.cli train-monitor --config configs/monitors/logistic/smoke.yaml
python -m bayesaudit.cli inspect-monitor-prediction --artifact results/tables/monitors/logistic_smoke.json --dataset-dir data/processed/monitoring/phase5_smoke --example-id <example_id>
```
