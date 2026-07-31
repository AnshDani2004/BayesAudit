# Monitoring Dataset

Phase 5 converts completed synthetic trajectories into checkpoint-level monitor examples. Each example joins a redacted `OversightObservation`, an interpretable observable feature payload, rendered visible text, and posthoc labels derived from objective scorers.

The feature payload is created before labels are attached. Feature extraction enumerates allowed observation fields and rejects tokens such as `ground_truth`, `violations`, `oracle`, `scores`, `counterfactual`, `future_steps`, `mutation_profile`, and `script`. This keeps monitor inputs aligned with what an online monitor would have seen at the checkpoint.

The dataset writer emits:

- `monitor_examples.parquet`
- `manifest.json`
- normalized `monitor_examples`, `monitor_labels`, and `monitor_features` parquet tables

Useful commands:

```bash
python -m bayesaudit.cli build-monitor-dataset --config configs/experiments/phase5_smoke.yaml
python -m bayesaudit.cli validate-monitor-dataset --dataset-dir data/processed/monitoring/phase5_smoke
python -m bayesaudit.cli summarize-monitor-dataset --dataset-dir data/processed/monitoring/phase5_smoke
```
