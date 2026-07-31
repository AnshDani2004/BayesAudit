# Calibration

Phase 5 supports Platt scaling, isotonic calibration, temperature scaling, and beta calibration over monitor probabilities. Calibration artifacts record the base monitor, base artifact hash, calibration dataset hash, fitting configuration, method, and parameters.

Reported calibration metrics include Brier score, log loss, expected calibration error, calibration slope, and intercept. Constant-probability monitors return a stable zero-slope summary instead of fitting an ill-conditioned line.

```bash
python -m bayesaudit.cli calibrate-monitor --config configs/calibration/platt/smoke.yaml
python -m bayesaudit.cli evaluate-monitor --config configs/experiments/phase5_smoke.yaml
```
