# CLI

Phase 6 adds:

```bash
python -m bayesaudit.cli validate-attackers
python -m bayesaudit.cli validate-attacks
python -m bayesaudit.cli run-attacker --config configs/experiments/phase6_smoke.yaml --dry-run
python -m bayesaudit.cli run-attacker-defender --config configs/experiments/phase6_smoke.yaml
python -m bayesaudit.cli compare-attack-selection --config configs/experiments/phase6_selection.yaml --dry-run
python -m bayesaudit.cli build-payoff-matrix --config configs/experiments/phase6_smoke.yaml
python -m bayesaudit.cli evaluate-exploitability --config configs/experiments/phase6_smoke.yaml
python -m bayesaudit.cli inspect-attack-run --config configs/experiments/phase6_smoke.yaml
python -m bayesaudit.cli inspect-attacker-state --config configs/experiments/phase6_smoke.yaml
python -m bayesaudit.cli run-red-team-loop --config configs/experiments/phase6_red_team_loop.yaml --dry-run
python -m bayesaudit.cli summarize-phase6 --config configs/experiments/phase6_smoke.yaml
```

All Phase 6 commands are credential-free and synthetic-only.

Phase 7 adds mock-safe real-pilot infrastructure commands:

```bash
python -m bayesaudit.cli validate-provider-config --config configs/providers/mock/smoke.yaml
python -m bayesaudit.cli estimate-pilot-cost --config configs/experiments/phase7_connectivity.yaml
python -m bayesaudit.cli authorize-provider-run --config configs/experiments/phase7_connectivity.yaml
python -m bayesaudit.cli run-provider-connectivity --config configs/experiments/phase7_connectivity.yaml --dry-run
python -m bayesaudit.cli run-real-workflow-pilot --config configs/experiments/phase7_workflow.yaml --dry-run
python -m bayesaudit.cli run-measurement-pilot --config configs/experiments/phase7_measurement.yaml --dry-run
python -m bayesaudit.cli evaluate-real-scorers --config configs/experiments/phase7_measurement.yaml
python -m bayesaudit.cli build-real-annotation-sample --config configs/experiments/phase7_annotation_sample.yaml
python -m bayesaudit.cli evaluate-monitor-transfer --config configs/experiments/phase7_monitor_transfer.yaml --dry-run
python -m bayesaudit.cli evaluate-calibration-transfer --config configs/experiments/phase7_monitor_transfer.yaml --dry-run
python -m bayesaudit.cli run-real-oversight-pilot --config configs/experiments/phase7_oversight.yaml --dry-run
python -m bayesaudit.cli summarize-real-pilot --config configs/experiments/phase7_connectivity.yaml
python -m bayesaudit.cli classify-pilot-tasks --config configs/experiments/phase7_measurement.yaml
python -m bayesaudit.cli generate-freeze-proposal --config configs/experiments/phase7_measurement.yaml
python -m bayesaudit.cli plan-phase8 --config configs/experiments/phase7_full_pilot.yaml
```

An actual real-provider run also requires explicit ceilings:

```bash
python -m bayesaudit.cli run-provider-connectivity \
  --config configs/experiments/phase7_connectivity.yaml \
  --allow-provider-calls \
  --max-cost 1.00 \
  --max-tokens 1000 \
  --max-requests 1 \
  --max-trajectories 1
```

Default repository configs do not authorize real provider calls.
