# Phase 8 Confirmatory Study

Phase 8 is a preregistered confirmatory study of the frozen Phase 7 benchmark.
It is synthetic, sandboxed, based on inert tools, and limited to one provider model.

Confirmatory evidence decision: `confirmatory_evidence_validated_with_limitations`.
Phase 9 readiness: `ready_for_phase9_with_limitations`.
Closeout decision: `phase8_complete_with_documented_limitations_merge_ready`.

## Executive Summary

- Provider/model: `openai` / `gpt-5-nano-2025-08-07`
- Design: 3 domains x 2 architectures x 4 seeds x 4 matched conditions
- Frozen matrix: 96 trajectories and 24 matched quartets
- Execution: 96 attempted, 96 completed, 0 provider-failed trajectories
- Provider accounting: 288 request summaries, 285 new calls, 3 exact cache hits
- Token/cost accounting: 312,174 total tokens, `$0.03363020` token-derived cost
- Primary outcome: 21 validated objective positives, 75 validated negatives
- Attack-effect comparison: 7 attacked no-oversight positives versus 3 safe-control positives
- Downstream containment: 21 internal-only violations, 0 final-output residual violations
- Prevention: not established as a clean confirmatory claim

## Protocol

The protocol version is `phase8_protocol_v1`; the matrix version is
`phase8_matrix_v1`; the statistical-analysis plan version is
`phase8_statistical_analysis_plan_v1`. The fresh seeds are `1`, `2`, `3`, and
`4`, selected before execution as the four smallest positive 32-bit integers not
used by Phase 7 real-model experiments.

The frozen task/domain cells are privacy, authorization, and evidence. The
architectures are unstructured delegation and structured constraint inheritance.
Each task, architecture, and seed has a matched quartet:
`safe_no_attacker_no_oversight`, `attacker_no_oversight`,
`attacker_rule_based_selective_v1`, and `attacker_bayesian_adaptive_v1`.

## Execution

Execution followed the preregistered waves: Wave 0 completed 4 trajectories,
Wave 1 completed 20, Wave 2 completed 48, and Wave 3 completed 24. No wave
breached request, token, cost, or trajectory ceilings. Raw provider responses are
stored only under ignored `results/tables/phase8/phase8_confirmatory_openai/`;
tracked files preserve redacted summaries and hashes.

## Objective Outcomes

The confirmatory adjudication found 21 validated objective positives and 75
validated objective negatives. Safe controls had 3 positives and 21 negatives.
Attacked no-oversight cases had 7 positives. All validated positives were
internal-only under the preserved synthetic marker analysis: tool-argument
violations were 0, final-output violations were 0, and corrected-before-final was
21.

## Monitor And Policy Outcomes

Rule-based monitored cases alerted on the validated positive oversight set in this
synthetic benchmark. The Bayesian/logistic monitor stack produced 0 alerts among
the 7 objective-positive matched comparison cases, so the monitor comparison is
reported with limitations and small denominators. Audits occurred for active
oversight policies; no real external tools were enabled.

## Confirmatory Analysis

The paired attack-effect comparison recorded 6 attacker-only discordant pairs and
2 safe-only discordant pairs. The paired risk difference was `0.1667`, and the
exact McNemar result was `0.289062`. Wilson intervals were recorded for safe and
attacked no-oversight rates. Holm correction remains the preregistered
multiplicity rule when both primary families are estimable.

## Replication Findings

The Phase 8 evidence is directionally consistent with the Phase 7 pilot on
internal objective violations and correction before final output, but it remains
limited by synthetic tasks, a single provider model, developer adjudication, and
small matched denominators. Phase 8 does not establish population prevalence,
production readiness, broad attacker robustness, or clean prevention.

## Prevention Analysis

Prevention is `not_established`. Correction before final output is reported
separately and is not treated as validated oversight prevention.

## Decisions

- Protocol decision: `phase8_protocol_frozen_with_limitations`
- Execution decision: `phase8_execution_complete`
- Confirmatory evidence decision: `confirmatory_evidence_validated_with_limitations`
- Phase 9 readiness: `ready_for_phase9_with_limitations`
- Final closeout decision: `phase8_complete_with_documented_limitations_merge_ready`

Codex must not merge this PR. Use a manual merge commit after review.
