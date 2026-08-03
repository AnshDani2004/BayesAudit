# Public Release Hardening Plan

This inventory verifies the public-facing audit against the current repository state at
`d3368c2` on `docs/public-release-hardening`. It is a remediation plan, not a change to
historical experimental evidence. Experimental outputs, labels, scorer outcomes, raw model
responses, and denominators remain immutable unless a derived accounting field is explicitly
repaired with provenance.

## Baseline Verification

- Branch: `docs/public-release-hardening`
- Starting commit: `d3368c2`
- `d3368c2` ancestry: verified
- Working tree before remediation: clean
- Local `v1.0.0` tag: absent
- `origin/main`: `d3368c2`
- Provider execution required for hardening: no
- Baseline validation:
  - `python -m pip install -e ".[dev]"`: passed
  - `python -m ruff check .`: passed
  - `python -m mypy --no-incremental src tests`: passed
  - `python -m pytest -q`: 1937 passed
  - `python -m compileall -q src tests scripts`: passed
  - scenario, envelope, policy, attacker, attack, Phase 8, Phase 9, and Phase 10 validators: passed

## Findings

| ID | Audit claim | Repository evidence | Status | Severity | Files affected | Planned remediation | Scientific risk | Historical artifacts immutable? | Validation required |
|---|---|---|---|---|---|---|---|---|---|
| PHR-01 | README is stale and not recruiter-ready. | `README.md` says Phase 8 closeout and contains long implementation inventory plus raw decision enums. | verified | high | `README.md` | Replace with concise public-facing README linked to final docs, assets, and reproducibility commands. | Medium: public summary must not overclaim results. | yes | docs link check, tests |
| PHR-02 | Final-facing docs are placeholders. | `docs/final_report.md`, `docs/phase9_report.md`, cards, and `paper/bayesaudit.tex` are skeletal. | verified | high | `docs/*.md`, `paper/bayesaudit.tex` | Expand Markdown docs and either expand or remove misleading paper placeholder. | Medium: preserve nulls and limitations. | yes | docs link check, tests |
| PHR-03 | Release/citation metadata are stale. | `pyproject.toml` and `CITATION.cff` report `0.1.0`, placeholder author, and example repository URL; `LICENSE` says contributors. | verified | high | `pyproject.toml`, `CITATION.cff`, `LICENSE` | Align metadata to Ansh Hemang Dani, v1.0.0, real repository URL, and planned release date. | Low | yes | version consistency tests |
| PHR-04 | Release notes are unusable or missing. | No `CHANGELOG.md`; no substantive `docs/RELEASE_NOTES_v1.0.0.md`; release candidate file contains merge/tag instructions. | verified | high | release docs | Create professional changelog, release notes, and checklist; replace obsolete candidate note. | Low | yes | docs link check |
| PHR-05 | Public-facing development workflow residue exists. | README/docs/source/generated artifacts contain `Codex`, `codex/`, `do_not_merge_by_codex`, and merge-readiness enums. | partially verified | medium | docs, selected source/tests, selected derived artifacts | Remove public-facing residue; preserve scientifically necessary historical provenance in archival artifacts with classification. | Medium if hashes are changed without provenance. | yes | `git grep` classification, tests |
| PHR-06 | Phase 9 provider accounting is inconsistent. | `phase9_provider_summary.json` says 144 provider calls and 144 cache hits; tracked requests are all cached; ignored ledger has 144 completed and 288 cached rows. | verified | high | Phase 9 derived accounting artifacts, docs, tests | Add `docs/phase9_provider_accounting_note.md`; add explicit acquisition vs replay fields and provenance to derived artifacts. | High if calls/costs are invented; use preserved ledger only. | raw/model outputs yes; derived accounting repair allowed | Phase 9 validators, regression tests |
| PHR-07 | Phase 9 monitor denominator labels are unclear. | `phase9_primary_analysis.json` mixes matched no-oversight subset fields and all monitored trajectory fields. | verified | high | `phase9_primary_analysis.json`, tests, reports | Add explicit denominator/renamed companion fields while preserving original fields. | Medium: denominator changes must not alter counts. | yes | regression tests |
| PHR-08 | Final figure/table manifests do not provide recruiter-visible assets. | `docs/assets` and `docs/tables` do not contain generated public assets. | verified | medium | docs assets/tables/scripts | Generate deterministic SVG/PNG/Markdown assets from tracked JSON evidence. | Medium: figures must show nulls and denominators. | yes | asset existence and generation tests |
| PHR-09 | Missing public portfolio documentation. | Dataset, provider, policy, attacker, methodology, and reproducibility docs are absent or thin. | verified | medium | docs | Add substantive public docs and omit private career-prep material. | Low | yes | docs link check |
| PHR-10 | Security hardening should include gitleaks and repository checks. | `.env` is ignored and `.env.example` empty, but no `.gitleaks.toml` or security audit script exists. | verified | high | `.gitleaks.toml`, CI, scripts, tests | Add narrow allowlist, CI step, local security audit script/tests. | Low | yes | gitleaks if installed, grep checks, tests |
| PHR-11 | Public review should be performed from several reader perspectives. | No tracked recruiter-facing review document exists. | verified | medium | `docs/public_release_review.md` | Add four-reader quality review and final release decision. | Low | yes | docs link check |
| PHR-12 | Existing secret scan report says hash false positives, not real credentials. | Uploaded audit says Gitleaks findings were hash fields; current tracked files need independent grep/gitleaks checks. | partially verified | high | security docs/config | Re-run scanner when tool is available; otherwise record blocker or install requirement without committing external report. | Low | yes | gitleaks/grep results |

## Commit Plan

1. `Public hardening: audit repository and reconcile release evidence`
2. `Public hardening: rewrite README and final documentation`
3. `Public hardening: remove development residue and align metadata`
4. `Public hardening: add figures tables release notes and security checks`
5. `Public hardening: complete final recruiter-facing audit`

No provider calls are planned or required. The branch must not create or push `v1.0.0`, publish a GitHub Release, merge a PR, rewrite Git history, or begin Phase 11.
