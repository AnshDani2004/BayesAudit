# Changelog

All notable public-release changes are summarized here.

## v1.0.0 - Planned Public Release

### Added

- Public-facing README for BayesAudit as a reproducible research framework for budget-constrained oversight in hierarchical LLM workflows.
- Substantive final report, methodology, benchmark card, dataset card, model/provider card, oversight-policy card, attacker card, and Phase 9 robustness report.
- Deterministic public figures under `docs/assets/` and compact result tables under `docs/tables/`.
- Phase 9 provider-accounting note clarifying original acquisition calls, cache replay records, token accounting, and cost interpretation.
- Narrow Gitleaks configuration and local release security audit script.
- Release notes and pre-release checklist for manual publication after merge.

### Changed

- Project metadata now targets version `1.0.0`, names Ansh Hemang Dani as author, and points to `https://github.com/AnshDani2004/BayesAudit`.
- Recruiter-facing documentation now preserves the Phase 9 nonreplication, null final-output results, and absence of clean causal-prevention claims.
- Temporary development-workflow wording was replaced with neutral manual-review and developer-adjudication terminology in current public surfaces.

### Security

- Added fail-fast checks for populated provider-key assignments, sk-style keys, private key blocks, bearer credentials, local absolute paths, placeholder repository URLs, and stale release-facing package versions.
- Added a scoped `.gitleaks.toml` allowlist for known hash-field false positives without disabling generic secret detection.

### Scientific Notes

- Phase 8 observed a positive but statistically limited attack-effect direction: 7/24 attacked no-oversight positives versus 3/24 safe positives.
- Phase 9 did not replicate the held-out attacker effect: 4/12 held-out attacker positives versus 8/12 safe positives.
- No final-output violations were observed in the Phase 8 or Phase 9 principal studies.
- BayesAudit remains a synthetic, sandboxed research prototype, not a production safety system.
