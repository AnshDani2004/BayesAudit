# Milestone Plan

## Phase 1: Research Specification

Status: complete.

Goal: establish internally consistent research design and a working repository scaffold.

Files:

- `README.md`
- `docs/methodology.md`
- `docs/threat_model.md`
- `docs/preregistration.md`
- `docs/annotation_guide.md`
- `docs/milestones.md`
- `src/bayesaudit/schemas.py`
- `src/bayesaudit/interfaces.py`
- `scenarios/*/*.yaml`
- `tests/*`

Risks:

- defining metrics too vaguely to score
- mixing hypotheses with unobserved results
- overbuilding implementation before task validity is settled

Acceptance criteria:

- docs define objective, hypotheses, assumptions, metrics, and threat model
- five objective example tasks validate against typed schemas
- tests run without external model access

## Phase 2: Minimal Benchmark

Status: complete for the offline synthetic MVP.

Goal: implement deterministic scorers, trajectory logging, mock model execution, single-agent baseline, and unstructured delegation.

Acceptance criteria:

- at least five tasks per domain
- deterministic scorer tests for every task family
- mock-model integration test produces complete trajectories
- trajectory logs include prompts, messages, tools, constraints, audits, scores, costs, seeds, and model versions
- all five domains have at least five manually inspectable fixtures
- raw JSONL and normalized Parquet outputs are produced
- resume skips duplicate completed run IDs
- no real model-provider calls are made

## Phase 3: Constraint Architectures

Status: complete for the synthetic inheritance MVP.

Goal: implement structured and verified constraint inheritance.

Acceptance criteria:

- structured constraint object is preserved across delegation
- verified architecture refuses missing constraint state
- constraint-retention metrics are computed per delegation step
- depth experiments run with mocked models
- verified inheritance validates envelopes before branch execution
- deterministic repair/refusal events are recorded separately from oversight interventions
- mutation schedules can be reused across unstructured, structured, and verified architectures

## Phase 4: Oversight Baselines

Status: complete for deterministic synthetic baselines.

Goal: implement no oversight, random, fixed-checkpoint, rule-based, and oracle policies behind a common interface.

Acceptance criteria:

- policies consume the same trajectory-state object
- budget accounting is tested
- oracle policy is restricted to evaluation mode
- policies emit long-form audit records
- shadow and intervention modes record separate outcomes
- detection matching and frontier metrics are computed posthoc
- large-run safeguards block accidental oversized executions

## Phase 5: Learned And Bayesian Oversight

Status: complete for deterministic synthetic monitor and adaptive-policy infrastructure.

Goal: implement LLM-judge monitor, calibration pipeline, Bayesian risk model, and adaptive audit policy.

Acceptance criteria:

- LLM judge returns structured output
- monitor metrics include calibration
- Bayesian policy uses posterior risk and budget-aware value logic
- adaptive policy is reproducible under fixed seeds
- monitor datasets are built only from redacted observation fields
- grouped split manifests prevent train/test group leakage
- real provider pilots are dry-run by default and blocked unless explicitly allowed

## Phase 6: Strategic Attacks

Goal: implement opportunistic and strategic attacker behavior.

Acceptance criteria:

- attacker budget and detection penalty are configurable
- attacks can target step, constraint, timing, and concealment
- attacker-defender matrix runs with mock models

## Phase 7: Pilot

Goal: run a small costed pilot and inspect task quality.

Acceptance criteria:

- broken or trivial tasks are identified before benchmark freeze
- preliminary monitor calibration is measured
- cost estimate is generated before paid runs
- deviations are logged

## Phase 8: Main Study

Goal: run the frozen experiment matrix.

Acceptance criteria:

- benchmark, hypotheses, and primary analyses are frozen
- all exclusions are recorded
- raw outputs are preserved
- main results are not used to rewrite primary hypotheses

## Phase 9: Analysis And Release

Goal: produce public benchmark, report, figures, and reproduction package.

Acceptance criteria:

- clean tables and figures are generated from preserved raw outputs
- statistical models include effect sizes and uncertainty intervals
- dataset card and limitations are included
- release instructions reproduce the public results
