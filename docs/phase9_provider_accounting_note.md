# Phase 9 Provider and Cache Accounting Note

This note reconciles Phase 9 accounting for the public release. It does not change model
outputs, labels, scorer decisions, denominators, request hashes, token counts, or cost records.

## Supported Interpretation

The preserved evidence supports this interpretation:

1. The original Phase 9 acquisition run made **144 unique provider calls**.
2. The tracked final request summaries were regenerated from cache and contain **144 cache-hit
   request records**.
3. The ignored provider ledger currently contains **432 rows**: 144 `completed` acquisition rows
   and 288 `cached` replay rows. The second set of 144 cached rows was produced by a later
   validation/regeneration pass and is not a new acquisition.
4. Token and cost totals in tracked Phase 9 artifacts represent provider-reported usage and
   token-derived cost for the original acquired responses, carried through cached response
   records. They are not incremental cost from the replay pass.

## Source Artifacts

| Quantity | Value | Evidence |
|---|---:|---|
| Planned trajectories | 48 | `configs/experiments/phase9_heldout_attack_matrix.json` |
| Planned provider requests | 144 | `configs/experiments/phase9_execution_protocol.json` |
| Tracked request records | 144 | `configs/experiments/phase9_provider_request_summaries.jsonl` |
| Tracked cache-hit request records | 144 | `configs/experiments/phase9_provider_request_summaries.jsonl` |
| Original unique completed provider calls | 144 | `results/tables/phase9/phase9_robustness_openai/provider_request_ledger.jsonl` |
| Unique cached replay request hashes in ignored ledger | 144 | `results/tables/phase9/phase9_robustness_openai/provider_request_ledger.jsonl` |
| Ignored ledger rows at audit time | 432 | `results/tables/phase9/phase9_robustness_openai/provider_request_ledger.jsonl` |
| Run ID | `phase9_6315bab02fba1dd2` | `configs/experiments/phase9_run_identity.json` |
| Total tokens | 164,693 | `configs/experiments/phase9_token_summary.json` |
| Token-derived cost | $0.01751875 | `configs/experiments/phase9_cost_summary.json` |

The ignored ledger is intentionally not tracked as release evidence because it is under
`results/`, but it was present locally during this hardening pass and provides provenance for the
otherwise confusing acquisition-versus-replay distinction.

## Canonical Public Accounting

For public documentation, use these canonical values:

- Phase 9 planned trajectories: **48**
- Phase 9 tracked request records: **144**
- Phase 9 original provider calls: **144**
- Phase 9 final tracked regeneration provider calls: **0**
- Phase 9 tracked cache hits: **144**
- Phase 9 total tokens: **164,693**
- Phase 9 token-derived cost: **$0.01751875**

Avoid saying that the final tracked request summaries themselves made 144 provider calls. They
did not; they are cache-hit records produced after the acquisition run.

## Cost Meaning

The cost figure is token-derived from provider-reported usage attached to the acquired responses.
It should be interpreted as the estimated cost of the original acquisition run, not the cost of
the cache replay. The replay did not make new provider requests.

## Denominator Clarification

The Phase 9 primary analysis has two denominator families:

- Matched safe versus held-out-attacker no-oversight pairs: 12 matched quartets.
- All monitored held-out-attacker trajectories: 12 rule-based trajectories and 12 Bayesian
  adaptive trajectories.

The original fields remain historically preserved. Public reporting should prefer the explicit
denominator fields added during this hardening pass:

- `safe_positive_matched_no_oversight_quartets`
- `heldout_attacker_positive_matched_no_oversight_quartets`
- `alerts_among_no_oversight_positive_matched_quartets`
- `bayesian_alerts_among_no_oversight_positive_matched_quartets`
- `true_positives_across_all_rule_based_trajectories`
- `false_positives_across_all_rule_based_trajectories`
- `true_positives_across_all_bayesian_trajectories`
- `false_negatives_across_all_bayesian_trajectories`

The clarified denominators do not alter the result: Phase 9 did **not** replicate the held-out
attacker effect. Safe controls had 8 positives out of 12 matched quartets, while held-out attacker
no-oversight trajectories had 4 positives out of 12 matched quartets.

## Unresolved Ambiguity

The ignored ledger records acquisition and cache-replay events but is not tracked in Git. The
unique request hashes and timestamps support the interpretation above, but future public claims
should cite this note and the tracked repaired summary fields rather than relying on an untracked
local ledger.
