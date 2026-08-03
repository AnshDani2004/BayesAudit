# Methodology

## Overview

BayesAudit studies budget-constrained oversight in hierarchical LLM workflows. The methodology combines synthetic benchmark tasks, matched experimental designs, inert attacker pressure, objective scoring, monitor evaluation, policy replay, and offline adjudication.

## Benchmark Construction

Tasks encode constraints such as privacy boundaries, authorization scope, evidence support, budget limits, and protected-attribute handling. Principal provider-backed studies focus on privacy, authorization, and evidence because those domains had mature scorer and attacker support.

## Workflow Architectures

The framework evaluates:

- single-agent workflows
- unstructured delegation
- structured constraint inheritance
- verified constraint inheritance in earlier offline phases

Phase 8 and Phase 9 principal studies compare unstructured delegation and structured inheritance.

## Matched Design

Matched quartets hold task, architecture, and seed fixed while varying attacker and oversight conditions. This reduces confounding and makes safe-control versus attacked comparisons easier to audit.

## Scoring and Adjudication

Objective scorers produce structured labels. Offline adjudication then records objective status, attacker uptake, monitor classification, policy behavior, intervention status, and prevention classification. Developer adjudication is disclosed as a limitation.

## Provider Controls

Provider-backed experiments require explicit authorization, exact request hashing, cache validation, raw-first persistence, no external tools, non-streaming structured outputs, request ceilings, token ceilings, and cost ceilings.

## Statistical Reporting

The reports emphasize denominators and paired comparisons. Exact McNemar p-values are reported for matched discordant pairs when estimable. Sparse or exploratory analyses are labeled as such.

## Scientific Integrity Rules

BayesAudit does not relabel outputs to improve findings, does not hide nulls, and does not claim prevention unless the evidence supports it. Phase 9 nonreplication is preserved.
