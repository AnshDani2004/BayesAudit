# Phase 2 Report

## Implemented

- Corrected async data contract with separated violations, detections, and interventions.
- Full constraint snapshots at each trajectory step.
- Environment-authored tool authorization and execution records.
- Deterministic scripted mock model with usage metadata.
- Offline synthetic tool environment.
- Single-agent workflow.
- Unstructured delegation workflow with depths one through four and branching.
- Deterministic scorers for all five domains.
- Scorer registry with clear failure for unknown versions.
- 25 manually inspectable fixtures, five per domain.
- JSONL raw persistence and normalized Parquet tables.
- Offline experiment runner with dry-run, failure preservation, and resume skipping.
- CLI commands for scenario validation, running, scoring summary, and experiment summary.
- CI configuration requiring no credentials.

## What Remains Mocked

- All model behavior is scripted mock behavior.
- Tool calls are synthetic local stubs.
- Oversight is no-oversight only.
- Constraint mutation labels are injected, not semantically inferred.
- No human annotation interface is implemented.

## Objectively Scored

- Evidence citation IDs, unsupported configured claims, and unauthorized retrieval.
- Privacy identifier leakage in messages, tool arguments, and final output.
- Budget action count, duplicate actions, and total cost.
- Authorization tool requests, missing approval, and false approval claims.
- Direct protected-field use and protected fields in tool arguments.

## Not Yet Objectively Scored

- General semantic equivalence of paraphrased constraints.
- Broad proxy discrimination beyond configured field names.
- Human-judgment severity disagreements.
- Real LLM calibration or monitor reliability.

## Test Results

Latest local checks:

```text
python -m ruff check .                 passed
python -m mypy src tests               passed
python -m pytest -q                    50 passed
python -m compileall -q src tests scripts passed
```

## Known Limitations

Phase 2 validates benchmark mechanics only. It produces no empirical claims about real LLM behavior, real oversight effectiveness, or Bayesian policy superiority.

## Recommended Phase 3 Start

Implement structured constraint inheritance and verified constraint inheritance using the `ConstraintSnapshot` fields already present in the Phase 2 data contract.

