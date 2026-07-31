# Dataset Splits

Phase 5 uses immutable grouped split manifests. Examples are assigned by group, not by row, so related checkpoints do not leak across train, development, calibration, confirmatory-test, and exploratory-test use.

Supported strategies:

- `in_distribution`: groups by base task id
- `template_holdout`: groups by template family
- `mutation_holdout`: groups by mutation-profile family
- `domain_holdout`: groups by domain
- `architecture_holdout`: groups by architecture
- `model_holdout`: groups by model family

Split manifests are deterministic for a fixed dataset and strategy. Confirmatory-test assignments should be treated as frozen and should not be used for feature engineering or threshold selection.

```bash
python -m bayesaudit.cli create-monitor-splits --config configs/experiments/phase5_smoke.yaml
```
