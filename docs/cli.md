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
