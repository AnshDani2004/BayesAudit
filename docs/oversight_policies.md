# Oversight Policies

Phase 4 implements five deterministic baseline families.

- `no_oversight`: never audits and never intervenes.
- `random`: seeded Bernoulli auditing with a configured audit fraction.
- `fixed`: audits configured checkpoint types, such as `before_tool_request` or `before_final_output`.
- `rule_based`: audits when observable risk features exceed a configured threshold.
- `oracle`: evaluation-only upper-bound baseline that may inspect scorer labels through replay metadata.

The deployable registry rejects oracle policies unless `evaluation=True`. All non-oracle policies consume the same redacted observation schema and do not receive hidden labels.

Policy configs live under `configs/policies/`. Phase 4 experiment configs can inline policies through `oversight_policies`, combine them with `oversight_budgets`, and choose `oversight_mode: shadow` or `oversight_mode: intervention`.
