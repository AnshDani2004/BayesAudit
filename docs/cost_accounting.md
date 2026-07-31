# Cost Accounting

Phase 7 separates pre-run estimates from post-run accounting. Pre-run gates use planned requests, estimated input tokens, estimated output tokens, cache assumptions, retry assumptions, and conservative provider-config estimates. Post-run accounting uses provider-reported token usage and a versioned local pricing table when the provider does not directly return monetary cost.

Hard ceilings are supplied on the CLI for real calls:

- `--max-cost`
- `--max-tokens`
- `--max-requests`
- `--max-trajectories`

Execution aborts before the next request if a hard ceiling would be exceeded. Request ledger rows preserve planned request estimates. Response records preserve provider-reported usage, nullable provider-reported monetary cost, nullable externally billed cost, and token-derived local cost where pricing is available.

Mock validation uses a monetary ceiling of `0.0`.

## Terms

- `estimated_cost_usd`: pre-run prediction based on estimated token counts.
- `token_derived_cost_usd`: post-run local calculation from provider-reported token usage and the versioned pricing table.
- `provider_reported_cost_usd`: monetary cost returned directly by the provider, nullable when unavailable.
- `billed_cost_usd`: cost confirmed from an external billing source, nullable unless explicitly reconciled.
- `conservative_upper_bound_usd`: deliberately conservative maximum estimate used for safety gates.
- `cost_reconciliation_status`: one of `provider_reported`, `token_derived`, `externally_billed`, `estimated_only`, or `unreconciled`.

`actual_cost` and `reconciled_cost` are not used for new Phase 7 cost reporting because they blur provider billing, local token math, and conservative estimates.

## Pricing

Pricing records live under `configs/pricing/`. Each record includes provider, exact model ID, USD input/cached-input/output prices per million tokens, effective date, pricing source description, regional uplift, fixed fees, a configuration hash, and a pricing-table version. A response stores the pricing-table version and pricing configuration hash used for its token-derived calculation so later pricing changes do not silently rewrite historical calculations.

Reasoning tokens are treated as usage metadata. They are not billed a second time when they are already included in output token usage.
