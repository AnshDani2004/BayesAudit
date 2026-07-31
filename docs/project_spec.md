# Project Specification

## Purpose

BayesAudit is a reproducible research benchmark for adaptive oversight in hierarchical LLM workflows. It measures when oversight should inspect, interrupt, or escalate a step to reduce undetected constraint violations under a fixed audit budget.

## Core Research Claim To Test

When oversight is scarce, policies that adapt to posterior risk over roles, depth, constraint type, tool use, monitor score, task difficulty, and prior audit outcomes should prevent more severity-weighted harm than random or fixed policies at equal oversight cost.

## Benchmark Requirements

Each benchmark task must contain:

- unique task ID
- domain
- difficulty
- full task description
- ground truth or deterministic scoring function
- constraints with severity and scope
- authorized and prohibited tools
- delegation configuration
- expected escalation points
- detectable violation types
- random seed
- statistical metadata

The first manually inspected seed set must prioritize objective scoring. Parameterized generation starts only after seed tasks and scorers pass tests.

## Objective Checks First

The five starting domains are designed so most violations can be detected by deterministic checks:

- evidence: unsupported claims, fabricated citations, unauthorized retrieval
- privacy: direct identifier leakage, sensitive tool arguments, final-output masking
- budgeting: global budget and action-count violations
- authorization: unauthorized tool calls and false approval claims
- protected attributes: prohibited field use and ranking deviations

Human labels validate monitors and ambiguous cases; they are not a substitute for deterministic scoring where objective scoring is possible.

## Initial Outputs

Phase 1 produces:

- research methodology
- threat model
- preregistration draft
- annotation protocol
- milestone plan
- typed data models
- component interfaces
- five example tasks
- fixture validation tests

## Non-Goals For Phase 1

- no paid model calls
- no empirical conclusions
- no fabricated pilot numbers
- no full task generator
- no final statistical report

