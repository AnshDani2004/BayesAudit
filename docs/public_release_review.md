# BayesAudit Public Release Review

Review date: 2026-08-03
Branch: `docs/public-release-hardening`
Pull request: `#4`
Release decision: `public_release_ready_with_documented_limitations`

## Executive Decision

BayesAudit is ready for public-release review with documented limitations after manual PR review and merge. The repository now presents a coherent research portfolio, preserves negative and nonreplicated findings, reconciles Phase 9 provider accounting, and includes release-facing figures, tables, metadata, release notes, and security checks.

The repository must still be merged manually. No tag was created and no GitHub Release was published during this hardening pass.

## Four-Reader Review

### Quantitative Researcher

- First-screen impression: the README frames a specific empirical question about oversight under constrained audit budgets rather than a generic AI-safety claim.
- Clear: matched denominators, non-significant Phase 8 p-value, Phase 9 nonreplication, and the distinction between internal-only positives and final-output violations.
- Confusing: historical Phase 7/8 machine-readable decision enums remain visible in archival JSON and legacy reports if a reader browses raw artifacts directly.
- Strongest evidence: Phase 8 and Phase 9 matched analyses, final claim registry, final statistical synthesis, and generated final results table.
- Credibility risks: small synthetic benchmark, one provider model, developer-run adjudication, and no population-prevalence estimate.
- Unsupported claims: no production-readiness, cross-model-generalization, prevalence, statistical-significance, or clean causal-prevention claim remains in recruiter-facing docs.
- Final edits made: public docs now foreground denominators, nulls, nonreplication, provider accounting, and limitations.

### ML or AI Safety Engineer

- First-screen impression: the project shows real systems engineering around provider gates, typed artifacts, monitors, policies, adjudication, caching, and validators.
- Clear: offline-first reproduction, explicit provider-call gate, request hashing, cache semantics, token/cost accounting, and synthetic/sandboxed scope.
- Confusing: legacy Phase 7 branch-name requirements in old executable pilot code are historical and not part of the current public reproduction path.
- Strongest evidence: 1,945 passing tests, typed schemas, validators, release security script, Gitleaks CI, and deterministic generated assets.
- Credibility risks: Bayesian/logistic monitor underperformed in Phase 9, and monitor behavior is benchmark-specific.
- Unsupported claims: no claim that BayesAudit is a deployable monitoring system remains.
- Final edits made: README and release notes describe the system as a research prototype and direct users to offline validators before provider-backed experiments.

### Technical Recruiter

- First-screen impression: BayesAudit now reads as a substantial research-engineering portfolio project with clear authorship and navigable documentation.
- Clear: what was built, why it matters, headline results, what did not replicate, and how to reproduce.
- Confusing: the repository still contains many archival Phase files because the project preserves a full evidence trail.
- Strongest evidence: concise README, final report, portfolio summary, cards, architecture diagram, release notes, and test count.
- Credibility risks: deeply technical artifacts can overwhelm a quick skim if the reader enters through raw JSON rather than README/docs.
- Unsupported claims: polished docs avoid inflated production or significance language.
- Final edits made: README links to high-signal public docs, figures, tables, release notes, and citation metadata.

### Potential Engineering Client

- First-screen impression: the project demonstrates careful experiment lifecycle management, validation discipline, and transparent limitation handling.
- Clear: provider costs, provider-call gates, cache accounting, security posture, and reproducibility commands.
- Confusing: BayesAudit is not a turnkey product or service; it is a research framework and evidence package.
- Strongest evidence: release checklist, security audit script, Gitleaks configuration, CI wiring, and final reproducibility guide.
- Credibility risks: single-provider scope and synthetic tasks limit direct deployment value.
- Unsupported claims: no production assurance or external-action safety guarantee is implied.
- Final edits made: docs specify out-of-scope uses and keep provider-backed reproduction behind explicit ceilings.

## Residue Classification

Required tool-specific identifier grep: no current tracked-tree matches.

The current public tree contains no matches for the tool-specific identifier. The normalized labels are classified as follows:

- Historical machine-readable provenance: prior commits preserve old branch names, reviewer strings, and merge flags. The current public tree normalizes those labels without changing experimental evidence.
- Executable compatibility requirement: legacy Phase 7/8 pilot source now uses neutral manual-merge fields and phase labels for the public release tree.
- Test fixtures: tests assert neutral artifact compatibility so the old pilot evidence remains reproducible without tool-specific identifiers.
- Public-facing current docs: README, final report, release notes, checklist, metadata, and current cards do not use tool-specific workflow instructions as release guidance.

Required grep: `git grep -n "OPENAI_API_KEY="`

- Remaining occurrence: `.env.example` contains an empty placeholder only. `scripts/security_audit.py` explicitly allows empty placeholders and rejects populated assignments.

Required grep: `git grep -n -E "sk-[A-Za-z0-9_-]{10,}"`

- Remaining occurrences: two `Task-selection-manifest` strings in `docs/phase7_report.md`. These are ordinary prose strings, not credentials. The local security audit uses a stricter token boundary and does not flag them.

Required greps with no findings:

- local absolute path for the repository owner's machine
- placeholder repository URL ending in the project name
- bearer-token literal pattern

## Validation Record

- Ruff: `python -m ruff check .` passed.
- Mypy: `python -m mypy --no-incremental src tests` passed for 141 source files.
- Pytest: `python -m pytest -q` passed with 1,945 tests.
- Compileall: `python -m compileall -q src tests scripts` passed.
- Scenario validator: 25 tasks across authorization, budgeting, evidence, privacy, and protected-attribute domains.
- Envelope validator: 25 valid envelopes, 0 failures.
- Policy validator: 11 valid policies, 0 errors.
- Attacker validator: 10 valid attackers, 0 errors.
- Attack primitive validator: 15 valid primitives, 0 errors.
- Phase 8 validator: valid with 0 errors.
- Phase 9 validator: valid with 0 errors.
- Phase 10 validator: valid with 0 errors.
- Figure and table generation: `python scripts/generate_public_assets.py` passed.
- Local security audit: `python scripts/security_audit.py` passed.
- Gitleaks working-tree scan: `gitleaks detect --source . --redact` found no leaks.
- Gitleaks history scan: `gitleaks git --redact --log-opts="--all"` found no leaks.
- Markdown local-link check: passed.
- Provider calls during hardening: none.

## Public Presentation Status

- README: current, recruiter-facing, linked to public assets and docs.
- Final report: substantive and limitation-preserving.
- Phase 9 report: explains held-out attacker selection, cache/provider accounting, monitor behavior, and nonreplication.
- Benchmark card: substantive and scoped to synthetic benchmark use.
- Dataset card: substantive and scoped to tracked evidence.
- Model/provider card: substantive and scoped to one provider model.
- Oversight policy card: substantive and scoped to research evaluation.
- Attacker card: substantive and scoped to synthetic attacker families.
- Paper source: expanded technical-report draft; Markdown final report remains canonical.
- Figures: 7 public assets under `docs/assets/`.
- Tables: 2 public Markdown tables under `docs/tables/`.
- Changelog: present.
- Release notes: present and suitable for GitHub Release body after merge/tag.
- Release checklist: present.

## Scientific Integrity Status

- Phase 9 provider-call interpretation: original acquisition used 144 provider calls; final tracked regeneration used 0 new calls and 144 cache-hit request records.
- Canonical Phase 9 request count: 144 tracked request records.
- Canonical Phase 9 provider-call count: 144 original acquisition provider calls; 0 final regeneration provider calls.
- Canonical Phase 9 token count: 164,693 token-accounted original acquired responses.
- Canonical Phase 9 cost: `$0.01751875` token-derived original acquisition cost.
- Denominators clarified: matched no-oversight positives, all rule-based trajectories, all Bayesian trajectories, objective-positive trajectories, and objective-negative trajectories are distinguished in artifacts and docs.
- Preserved nulls: no final-output violations in principal Phase 8/9 studies.
- Preserved nonreplication: Phase 9 did not replicate the Phase 8 attack-effect direction.
- Unsupported claims removed: production readiness, real-world prevalence, cross-model generalization, statistical significance, and clean causal prevention.

## Final Decision

`public_release_ready_with_documented_limitations`

The repository is ready for manual PR review and merge with documented scientific limitations. The release tag and GitHub Release must be created only after the PR is merged into `main`.
