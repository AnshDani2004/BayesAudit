# BayesAudit Final Report

## 1. Executive Summary

BayesAudit is a reproducible research framework for studying budget-constrained oversight in hierarchical LLM workflows. It evaluates when monitors and policies should inspect, escalate, or intervene as constraints move through delegated agent structures.

The v1.0.0 release includes a synthetic benchmark, hierarchical workflow engine, attacker framework, rule-based and Bayesian monitoring policies, objective scorers, provider-call accounting, offline adjudication, and deterministic artifact validation. The final evidence supports the framework as an auditable research prototype. It does not support production-safety claims, cross-model generalization, or population-level violation prevalence estimates.

The principal studies found internal-only objective violations in synthetic workflows, no final-output violations, and no clean causal prevention claim. Phase 8 showed a benchmark-specific positive attacker effect. Phase 9, using fresh seeds and held-out attacker assets, did not replicate that effect.

## 2. Research Question

BayesAudit asks: under limited oversight budgets, which checkpoints in a hierarchical LLM workflow should be inspected or escalated to reduce undetected constraint violations while preserving task utility?

This question matters because real systems rarely have enough review capacity to inspect every delegated step. BayesAudit therefore focuses on measurement infrastructure: matched experimental designs, monitors, policies, objective scorers, and reproducible evidence records.

## 3. System Design

The system has five main layers:

1. Synthetic benchmark tasks across privacy, authorization, evidence, budgeting, and protected-attributes domains.
2. Hierarchical workflow runners for single-agent baselines, unstructured delegation, and structured constraint inheritance.
3. Attacker and safe-control conditions with inert, sandboxed tools.
4. Oversight monitors and policies, including rule-based selective monitoring and Bayesian adaptive monitoring.
5. Offline adjudication and evidence packaging with canonical artifact hashes.

Provider-backed stages use exact request hashes, raw-first persistence, cache validation, token summaries, and cost summaries. Offline validation does not require a provider credential.

## 4. Threat Model

The benchmark models constraint failures in delegated work: privacy leakage, unauthorized tool or approval claims, unsupported evidence, budget violations, and protected-attribute handling failures. Attacker strategies are synthetic and safe. They pressure the workflow to violate a constraint but do not perform real external actions.

Out of scope: real-world exploitation, production deployment, real user data, real external tool execution, and claims about all LLM providers or models.

## 5. Experimental Design

The release emphasizes three studies:

- Phase 7 pilot: real-provider pipeline and benchmark freeze.
- Phase 8 confirmatory study: 96 trajectories, 24 matched quartets, four fresh seeds, three domains, two architectures, and one provider model.
- Phase 9 held-out robustness study: 48 trajectories, 12 matched quartets, two fresh seeds, and held-out Phase 6 attacker assets.

Matched designs compare safe-control and attacked conditions while holding task, architecture, and seed fixed. Monitor comparisons distinguish matched positive subsets from all monitored trajectories.

## 6. Phase 7 Pilot

Phase 7 established that the provider/cost/cache/ledger pipeline could run under hard ceilings. It also produced the strategic-attacker construct, objective scoring flow, offline adjudication process, and benchmark freeze artifacts used by Phase 8.

Phase 7 did not establish real-world prevalence, broad attacker robustness, production readiness, independent human agreement, or clean causal prevention.

## 7. Phase 8 Confirmation

Phase 8 executed all 96 planned trajectories and all 24 matched quartets. It recorded 288 request summaries, 285 new provider calls, 312,174 total tokens, and $0.03363020 token-derived cost.

Key Phase 8 results:

- 21 validated objective positives and 75 validated negatives.
- 21 internal-only violations.
- 0 tool-argument violations.
- 0 final-output violations.
- Attacked no-oversight positives: 7/24 matched quartets.
- Safe-control positives: 3/24 matched quartets.
- Paired risk difference: 0.1667.
- Exact McNemar p-value: 0.289062.

The Phase 8 result is a benchmark-specific confirmatory finding with documented limitations, not a population-level safety claim.

## 8. Phase 9 Robustness

Phase 9 tested held-out attacker assets and fresh seeds. It completed 48 trajectories and 144 tracked request records.

Canonical Phase 9 accounting:

- Original acquisition provider calls: 144.
- Final tracked regeneration provider calls: 0.
- Tracked cache-hit request records: 144.
- Total tokens: 164,693.
- Token-derived cost: $0.01751875.

Key Phase 9 outcome:

- Safe-control positives: 8/12 matched quartets.
- Held-out attacker no-oversight positives: 4/12 matched quartets.
- Paired risk difference: -0.3333.
- Exact McNemar p-value: 0.289062.

This did not replicate the Phase 8 attacker-effect direction. The nonreplication is preserved as a central result.

## 9. Cross-Phase Results

Across the principal studies, BayesAudit demonstrates a reproducible way to create, run, adjudicate, and validate oversight experiments. It also demonstrates why public reporting must remain careful: a Phase 8 result did not generalize cleanly to Phase 9 held-out attackers and fresh seeds.

The strongest release claim is methodological: BayesAudit provides an auditable framework for budget-constrained oversight research. The evidence does not justify a broad claim that a particular monitor or policy is generally safer in production.

## 10. Monitor Comparison

Rule-based monitoring was more sensitive in the Phase 8 and Phase 9 synthetic runs, but false positives were substantial. In Phase 9, across all 12 rule-based monitored trajectories, the rule-based monitor had 7 true positives and 5 false positives. Across all 12 Bayesian/logistic monitored trajectories, the Bayesian monitor had 0 true positives and 5 false negatives.

Matched-subset alert fields use a different denominator: the 4 no-oversight-positive matched quartets. See [Phase 9 provider accounting note](phase9_provider_accounting_note.md) for the denominator clarification.

## 11. Failure Analysis

Important negative findings:

- No final-output violations were observed in the principal studies.
- Clean causal prevention was not established.
- Bayesian/logistic monitoring missed validated positives in Phase 9.
- Phase 9 did not replicate the Phase 8 held-out attacker effect.
- Offline adjudication was developer-run rather than a blinded multi-annotator process.

These results are not release blockers; they are part of the scientific record.

## 12. Provider and Cost Accounting

Provider-backed runs were bounded by explicit request, token, and cost ceilings. Phase 9 accounting required a public-release repair because tracked request summaries were cache-hit records regenerated after an original acquisition run. The repaired derived artifacts now distinguish original acquisition calls from final tracked replay calls.

See [Phase 9 provider accounting note](phase9_provider_accounting_note.md).

## 13. Limitations

BayesAudit is synthetic, sandboxed, single-provider, and benchmark-specific. It does not use real user data or real external tools. It does not estimate real-world violation prevalence, establish cross-model generalization, or certify production readiness. Prevention claims remain exploratory and conditional.

## 14. Reproducibility

Offline reproduction is the default path:

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m mypy --no-incremental src tests
python -m pytest -q
python -m compileall -q src tests scripts
python -m bayesaudit.cli validate-phase8
python -m bayesaudit.cli validate-phase9
python -m bayesaudit.cli validate-phase10
```

Provider-backed reproduction requires an explicit `OPENAI_API_KEY` environment variable and hard ceilings. It is not required to inspect the release evidence.

## 15. Conclusion

BayesAudit is release-ready as a research portfolio with documented limitations. Its contribution is a technically credible framework for auditing budget-constrained oversight in hierarchical LLM workflows, with enough rigor to preserve null results and nonreplications rather than hiding them.
