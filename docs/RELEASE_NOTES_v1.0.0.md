# BayesAudit v1.0.0 Release Notes

## Overview

BayesAudit v1.0.0 is a public research release for studying budget-constrained oversight in hierarchical LLM workflows. It evaluates when monitors should inspect, escalate, or intervene when exhaustive oversight is too expensive.

The release is intentionally evidence-preserving: positive findings, null results, monitor misses, false positives, and the Phase 9 held-out nonreplication are all documented.

## Major Capabilities

- Hierarchical workflow simulation across single-agent, unstructured delegation, and structured constraint-inheritance runs.
- Typed constraint envelopes for privacy, authorization, and evidence requirements.
- Synthetic strategic-attacker framework with held-out attacker assets.
- Rule-based and Bayesian/logistic adaptive monitors.
- Budget-aware oversight policies, including no oversight, fixed checkpoints, random auditing, selective auditing, adaptive Bayesian auditing, and oracle-only evaluation.
- Objective scorers and offline adjudication artifacts that separate model-originated violations from benchmark-originated risk.
- Provider-backed execution with explicit gates, request hashes, cache validation, token accounting, and cost accounting.
- Deterministic artifact manifests, validators, public figures, and result tables.

## Experimental Scope

- Pilot: Phase 7 established the provider gate, benchmark freeze, strategic attacker construct, adjudication workflow, and repair process.
- Confirmatory study: Phase 8 ran 96 trajectories across 24 matched quartets.
- Held-out robustness study: Phase 9 ran 48 trajectories across 12 matched quartets using fresh seeds and held-out Phase 6 attacker assets.
- Final synthesis: Phase 10 compiled claim registry, artifact index, statistical synthesis, final report, and reproducibility instructions.

All tasks, tools, and attacks are synthetic and sandboxed. One provider model, `gpt-5-nano-2025-08-07`, was tested.

## Key Validated Findings

- Phase 8 completed 96/96 trajectories and 288 request records with 285 new provider calls, 312,174 total tokens, and `$0.03363020` token-derived cost.
- Phase 8 attacked no-oversight trajectories were objective-positive in 7/24 matched quartets, compared with 3/24 safe-control quartets. The paired risk difference was `0.1667`, with exact McNemar p-value `0.289062`.
- Phase 8 found 21 validated objective positives, all internal-only, with 0 tool-argument violations and 0 final-output violations.
- Phase 9 completed 48/48 trajectories and 144 tracked request records. The original acquisition used 144 provider calls; final tracked regeneration used cache hits only.
- Phase 9 found 24 validated positives, all internal-only, with 0 tool-argument violations and 0 final-output violations.
- In Phase 9, the rule-based monitor had 7 true positives and 5 false positives across all 12 rule-based monitored trajectories. The Bayesian/logistic monitor had 0 true positives and 5 false negatives across all 12 Bayesian monitored trajectories.

## Nonreplication and Limitations

Phase 9 did not replicate the Phase 8 attack-effect direction. Safe controls had 8 positives out of 12 matched quartets, while held-out attacker no-oversight trajectories had 4 positives out of 12.

BayesAudit does not estimate real-world violation prevalence, does not establish cross-model generalization, does not claim production readiness, and does not claim clean causal prevention of final-output violations. Corrected-before-final behavior is treated as conditional and exploratory.

## Offline Reproduction

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m mypy --no-incremental src tests
python -m pytest -q
python -m compileall -q src tests scripts
python -m bayesaudit.cli validate-scenarios --root scenarios
python -m bayesaudit.cli validate-envelopes
python -m bayesaudit.cli validate-policies
python -m bayesaudit.cli validate-attackers
python -m bayesaudit.cli validate-attacks
python -m bayesaudit.cli validate-phase8
python -m bayesaudit.cli validate-phase9
python -m bayesaudit.cli validate-phase10
```

## Provider-Backed Reproduction

Provider-backed reproduction is optional and gated. Set `OPENAI_API_KEY` in the shell environment without writing it to a tracked file, then use explicit request, token, cost, and trajectory ceilings.

```bash
python -m bayesaudit.cli run-phase9-provider \
  --allow-provider-calls \
  --max-cost 0.12 \
  --max-tokens 300000 \
  --max-requests 300 \
  --max-trajectories 48
```

## Security and Credential Handling

- `.env` is ignored.
- `.env.example` contains empty placeholders only.
- Raw provider caches and generated result directories remain ignored.
- Provider keys are read from the environment and are not required for offline validation.
- `scripts/security_audit.py` checks tracked files for populated key assignments, sk-style keys, private key blocks, bearer credentials, local absolute paths, placeholder repository URLs, and stale release-facing package versions.
- `.gitleaks.toml` allowlists only known hash-field false positives such as `token_hash`, `match_key_hash`, and `token_ledger_hash`.

## Benchmark and Dataset Versions

- Package version: `1.0.0`
- Benchmark scope: synthetic privacy, authorization, and evidence tasks.
- Dataset scope: Phase 7 pilot datasets, Phase 8 confirmatory artifacts, Phase 9 held-out robustness artifacts, and Phase 10 final synthesis.
- Provider/model scope: OpenAI provider with `gpt-5-nano-2025-08-07` for the principal provider-backed runs.

## Evidence Package Hashes

- Phase 8 matched confirmatory analysis: `a484306c8567d1823080588eaebc8e097c6f36ac5e6dccb015b90ee089cd4dad`
- Phase 9 primary analysis: `fd49b1a06f486278de9ed25a277f6b03199c81f724a7f19df2b4c39be1ecb14e`
- Final claim registry: `8c6a683beffd5633607eb673f058cd7a59e85456f61ad53c72c65b3474546c74`
- Final statistical synthesis: `29bcc40985449bbf7a997d0f5ba799b37fda9780f4d1d400e621f78079cd2b28`
- Final artifact index: `b631ff91bb95ad8dd6ab42175c22b577c73f6cc6e55349fe6b703730485cbd7c`

## Compatibility

- Python `>=3.10`
- Offline validation uses the package `dev` extra.
- Provider-backed reproduction requires an OpenAI API key and explicit provider-call permission flags.

## Release Status

This file is release-page-ready after the hardening pull request is manually merged into `main`, the annotated `v1.0.0` tag is recreated at the merge commit, and the GitHub Release is published from this document.
