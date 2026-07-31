# Pre-Pilot Checkpoint

Repository: `AnshDani2004/BayesAudit`

Default branch: `main`

Phase 7 implementation branch: `codex/phase7-real-model-pilot`

Pre-pilot base commit: `f5c1962`

Phase 6 validation at the checkpoint:

- `python -m ruff check .` passed.
- `python -m mypy src tests` passed.
- `python -m pytest -q` reported `331 passed`.
- `python -m compileall -q src tests scripts` passed.
- GitHub Actions was green.

Artifact versions at the checkpoint:

- Core schema version: `bayesaudit.v2`
- Inheritance artifact version: `bayesaudit.inheritance.v1`
- Monitoring artifact version: `bayesaudit.monitoring.v1`
- Attack artifact version: `bayesaudit.attack.v1`
- Existing policy config count: 14
- Existing attacker config count: 10

All results through Phase 6 were synthetic and offline. No real-provider experiments existed at the checkpoint. Provider calls were permission gated, and strategic attackers operated only in synthetic benchmark environments.

Intended Phase 7 scope:

- Build provider-neutral real-model pilot infrastructure.
- Preserve credential-free CI and mock-only validation.
- Support remote API, local/open-weight, and mock provider classes.
- Add permission records, pilot manifests, prompt-render records, request caches, ledgers, failure records, annotation exports, transfer analyses, readiness classifications, freeze proposals, and Phase 8 planning outputs.
- Do not merge into `main`, freeze the benchmark, or begin Phase 8 automatically.

Initial ceilings for mock-safe pilot configs:

- Initial token ceiling: `1000` for connectivity, larger explicit ceilings in dry-run pilot configs.
- Initial monetary ceiling: `0.0` for mock validation.
- Initial trajectory ceiling: `1` for connectivity, explicit stage-specific ceilings in Phase 7 configs.

Planned model families:

- `mock-deterministic-phase7` for CI and local validation.
- Remote and local real-provider templates are disabled by default and require exact model identifiers before use.

Planned benchmark domains:

- Privacy
- Authorization
- Evidence

Planned architectures:

- Single agent for connectivity/reference checks.
- Unstructured delegation.
- Structured constraint inheritance.

Planned oversight conditions:

- No oversight.
- Rule-based oversight.
- One calibrated adaptive policy placeholder for feasibility dry-runs.

Planned human-review sample:

- Stage-specific stratified samples from 1 to 12 items in mock-safe configs.
- Blind annotation exports hide model, policy, monitor prediction, and scorer conclusion where practical.

Criteria for benchmark freeze:

- Pilot tasks classified as ready or repaired.
- Scorer readiness documented with false-positive and false-negative modes.
- Human-review agreement reported.
- Monitor and calibration transfer measured without pilot-test retraining.
- Repair log complete.
- Explicit approval given before any Phase 8 freeze.

