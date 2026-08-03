# BayesAudit v1.0.0 Release Checklist

## Pre-Merge Checks

- [ ] Pull request targets `main`.
- [ ] Pull request uses the `docs/public-release-hardening` branch.
- [ ] No `v1.0.0` local or remote tag exists before merge.
- [ ] No GitHub Release has been published.
- [ ] Public README explains the project in the first screen.
- [ ] Final report, methodology, cards, Phase 9 report, and reproducibility guide are substantive.
- [ ] Public figures exist under `docs/assets/`.
- [ ] Public tables exist under `docs/tables/`.
- [ ] `CHANGELOG.md` exists.
- [ ] `docs/RELEASE_NOTES_v1.0.0.md` exists and is suitable for the GitHub Release body.
- [ ] Phase 9 provider accounting is documented in `docs/phase9_provider_accounting_note.md`.
- [ ] Phase 9 nonreplication is visible in README, final report, Phase 9 report, and release notes.
- [ ] No production-readiness, cross-model-generalization, prevalence, or clean-causal-prevention claim is introduced.
- [ ] `.env` remains ignored and `.env.example` remains empty.
- [ ] `scripts/security_audit.py` passes.
- [ ] Gitleaks working-tree and reachable-history scans are run or any tool-availability issue is documented.
- [ ] Ruff, mypy, pytest, compileall, and project validators pass.

## Manual Merge

- [ ] Review the full pull request diff.
- [ ] Confirm CI passes.
- [ ] Merge the pull request manually using "Create a merge commit."
- [ ] Sync local `main` after merge.

## Post-Merge Release

- [ ] Recreate annotated tag `v1.0.0` at the new `main` merge commit.
- [ ] Push tag `v1.0.0`.
- [ ] Publish the GitHub Release using `docs/RELEASE_NOTES_v1.0.0.md`.
- [ ] Confirm the release source archive points to the cleaned merge commit.
