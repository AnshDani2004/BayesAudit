# Phase 9 Held-Out Robustness Study

Phase 9 tested whether Phase 8 findings remained directionally stable under fresh seeds and held-out attacker assets from the existing Phase 6 inventory. It was a robustness study, not a population-prevalence estimate and not a cross-model generalization test.

## Design

- Provider: OpenAI Responses API.
- Model: `gpt-5-nano-2025-08-07`.
- Domains: privacy, authorization, evidence.
- Architectures: unstructured delegation and structured inheritance.
- Fresh seeds: 5 and 6.
- Matched quartets: 12.
- Planned trajectories: 48.
- Planned request records: 144.

Each quartet compared:

1. safe control, no attacker, no oversight
2. held-out attacker, no oversight
3. held-out attacker, rule-based selective oversight
4. held-out attacker, Bayesian adaptive oversight

## Held-Out Attacker Selection

Phase 9 used existing Phase 6 assets rather than inventing new attacker behavior:

- Privacy: `random_selective`, primitive `privacy_tool_identifier_leak`
- Authorization: `policy_aware`, primitive `authorization_false_approval`
- Evidence: `opportunistic`, primitive `evidence_fabricated_citation`

The design intentionally avoided reusing the Phase 8 strategic-attacker construct as the sole attacker evidence.

## Provider and Cache Accounting

The original acquisition run made 144 unique provider calls. The final tracked request summaries were regenerated from cache and contain 144 cache-hit request records. Token and cost totals represent provider-reported usage from the acquired responses, not incremental cache-replay cost.

Canonical values:

- Original acquisition provider calls: 144
- Final tracked regeneration provider calls: 0
- Tracked request records: 144
- Cache-hit request records in tracked summaries: 144
- Total tokens: 164,693
- Token-derived cost: $0.01751875

See [Phase 9 provider accounting note](phase9_provider_accounting_note.md).

## Objective Outcomes

Phase 9 produced 24 validated positives and 24 validated negatives. All positives were internal-only; there were no tool-argument or final-output violations.

Matched no-oversight comparison:

- Safe-control positives: 8/12 matched quartets.
- Held-out attacker no-oversight positives: 4/12 matched quartets.
- Paired risk difference: -0.3333.
- Exact McNemar p-value: 0.289062.

This did not replicate the Phase 8 attacker-effect direction.

## Monitor Results

Denominators matter:

- The matched monitor subset contains 4 no-oversight-positive quartets.
- All rule-based monitored trajectories: 12.
- All Bayesian monitored trajectories: 12.

Results:

- Rule-based alerts among no-oversight-positive matched quartets: 4/4.
- Bayesian alerts among no-oversight-positive matched quartets: 0/4.
- Rule-based true positives across all rule-based trajectories: 7/12.
- Rule-based false positives across all rule-based trajectories: 5/12.
- Bayesian true positives across all Bayesian trajectories: 0/12.
- Bayesian false negatives across all Bayesian trajectories: 5/12.

## Threshold Sensitivity and Policy Replay

Threshold sensitivity and policy replay were offline analyses. They made no provider calls and should be interpreted as exploratory diagnostics over frozen records.

## Nonreplication

Phase 9 is a documented nonreplication. The held-out attacker condition did not increase objective positives relative to safe controls under the matched no-oversight comparison. This limits any public claim that the Phase 8 effect is robust to fresh seeds and held-out attackers.

## Limitations

Phase 9 remains synthetic, sandboxed, single-provider, restricted to three domains and two architectures, and developer-adjudicated. It is not evidence of production readiness or broad model generalization.
