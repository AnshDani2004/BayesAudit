# Adaptive Policies

Phase 5 adaptive policies consume monitor predictions and checkpoint examples, then allocate an audit budget.

Implemented policies:

- learned threshold
- top risk
- online priority
- Thompson-style grouped risk allocation
- expected harm
- value of information

Each decision records risk estimate, expected severity, intervention effectiveness, expected net value, action, reason, remaining budget, and whether the policy is online. Shadow evaluation compares allocation choices without executing interventions; intervention evaluation can execute budgeted actions through the existing Phase 4 replay/intervention machinery.

```bash
python -m bayesaudit.cli run-adaptive-policy --config configs/experiments/phase5_smoke.yaml
python -m bayesaudit.cli compare-monitor-policy-pairs --config configs/experiments/phase5_smoke.yaml
```
