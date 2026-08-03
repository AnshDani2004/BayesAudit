# BayesAudit Benchmark Card

## Intended Use

The BayesAudit benchmark is intended for research on oversight of hierarchical LLM workflows under limited audit budgets. It supports experiments on constraint inheritance, attacker pressure, monitoring, policy replay, objective scoring, and offline adjudication.

## Out-of-Scope Use

The benchmark must not be used as a production-safety certification, real-world violation-prevalence estimate, or broad cross-model generalization claim.

## Versions and Provenance

- Phase 7 benchmark candidate: `phase7_benchmark_candidate_v1`
- Phase 8 confirmatory dataset: `phase8_confirmatory_validated_dataset_v1`
- Phase 9 held-out robustness dataset: `phase9_heldout_robustness_dataset_v1`
- Final claim registry: `configs/experiments/final_claim_registry.json`

## Domains

The full synthetic fixture set includes privacy, authorization, evidence, budgeting, and protected-attributes tasks. The principal Phase 8 and Phase 9 provider-backed studies focus on privacy, authorization, and evidence.

## Labels and Scoring

Objective labels are produced from deterministic scorers and developer-run offline adjudication. Labels distinguish internal-only violations, tool-argument violations, final-output violations, corrected-before-final behavior, monitor classifications, policy decisions, and prevention claims.

## Limitations

All tasks are synthetic and sandboxed. Tools are inert. The benchmark is intentionally small and inspectable. It should be used for method development and reproducibility demonstrations, not for production claims.

## Reproduction

Use:

```bash
python -m bayesaudit.cli validate-scenarios --root scenarios
python -m bayesaudit.cli validate-phase8
python -m bayesaudit.cli validate-phase9
python -m bayesaudit.cli validate-phase10
```

## Misuse Risks

The main misuse risk is overstating benchmark-specific findings as real-world safety guarantees. Public materials should preserve null results, nonreplications, false positives, and false negatives.
