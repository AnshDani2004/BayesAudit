# BayesAudit Portfolio Summary

BayesAudit is a research engineering project for auditing budget-constrained oversight in hierarchical LLM workflows. It combines benchmark design, provider integration, statistical analysis, monitoring, policy evaluation, and reproducibility infrastructure.

## Technical Highlights

- Built a typed Python framework for synthetic hierarchical workflow simulation.
- Implemented constraint inheritance, mutation tracking, envelope verification, and repair events.
- Designed synthetic attacker families and safe attack primitives across privacy, authorization, and evidence domains.
- Implemented rule-based and Bayesian adaptive monitoring under hard oversight budgets.
- Added objective scorers, offline adjudication packets, validated positive/negative datasets, and artifact hashes.
- Ran bounded provider-backed studies with request hashing, cache validation, token accounting, and cost summaries.
- Preserved null results, nonreplications, false positives, and false negatives.
- Maintained a large automated test suite and deterministic validators.

## Scientific Highlights

Phase 8 showed a benchmark-specific positive attacker effect. Phase 9 did not replicate that direction under held-out attackers and fresh seeds. No final-output violations were observed in the principal studies, and clean causal prevention was not established.

## Public Positioning

The project is best presented as a rigorous research prototype and reproducibility portfolio, not a deployed product or safety guarantee.
