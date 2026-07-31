# Phase 3 Report

## Implemented

- canonical constraint registries
- typed constraint envelopes
- structured inheritance workflow
- verified inheritance workflow
- deterministic mutation schedules
- constraint comparison engine
- retention metrics
- verification and repair events
- aggregation provenance
- normalized inheritance storage tables
- CLI commands for envelope validation, inheritance summary, trajectory inspection, and architecture comparison
- 34 reusable mutation profiles
- Phase 3 smoke, manageable, and full synthetic configs
- 85 total tests

## Synthetic Architecture Comparison

The Phase 3 smoke config runs unstructured, structured, and verified inheritance against the same task set, delegation graph, mutation profile choices, mock behavior, tool environment, and seeds. Results are synthetic and validate benchmark mechanics only.

## Real-World Claims Not Supported

Phase 3 does not show that real LLMs preserve or lose constraints at any particular rate. It does not compare real oversight policies, does not use LLM judges, and does not make Bayesian-policy claims.

## Known Limitations

- semantic equivalence is recognized only for controlled paraphrase transformations
- unstructured delegation records mutation effects as snapshots, not typed envelopes
- repair is deterministic and registry-based
- no human oversight or annotation flow is implemented
- no real model-provider integrations are used

## Phase 4 Prerequisites

Phase 4 can implement oversight baselines against the now-separated architecture records: domain violations, constraint mutations, verification failures, repair events, and intervention records.

