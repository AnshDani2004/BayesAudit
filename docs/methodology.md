# Methodology

## Formal Problem Statement

BayesAudit evaluates oversight policies for hierarchical LLM workflows under a constrained audit budget. A workflow trajectory is a sequence of states containing task context, messages, delegated subtasks, tool requests, inherited constraints, audits, interventions, and final outputs.

An oversight policy observes the available trajectory state and chooses one action:

- continue autonomously
- audit current step
- request clarification
- block proposed action
- escalate to human oversight
- terminate workflow

The research objective is to approximately maximize:

```text
expected task reward
- severity-weighted undetected harm
- oversight cost
- unnecessary intervention cost
```

subject to:

```text
expected audits <= oversight budget B
```

For strategic behavior, the attacker approximately maximizes:

```text
benefit from successful violation
- attack cost
- probability(detection) * detection penalty
```

## Scope

BayesAudit studies oversight timing and policy quality. It does not claim to measure every possible safety failure in deployed agent systems. The benchmark emphasizes constraints with deterministic or highly reliable scoring:

- evidence grounding
- privacy-preserving data analysis
- budget-constrained planning
- tool authorization
- protected-attribute exclusion

## Workflow Architectures

### Single Agent

One agent receives the full task, context, tools, and constraints. There is no delegation depth beyond zero.

### Unstructured Delegation Hierarchy

A planner delegates subtasks in natural language. Constraints may be summarized, rewritten, omitted, or distorted. Delegation depth is configurable from zero through at least four.

### Structured Constraint Inheritance

Constraints are stored separately from task prose in a typed object. Delegated agents receive the same machine-readable constraint object alongside the natural-language subtask.

### Verified Constraint Inheritance

Each delegated agent must acknowledge every inherited constraint, explain subtask compliance, forward the structured constraint object unchanged, record requested constraint changes, refuse missing constraint state, and escalate ambiguous high-impact actions.

## Assumptions

1. Objective task scoring is preferred over subjective outcome assessment.
2. Some violation types are trajectory-level and may be invisible in the final answer.
3. Automated monitors are imperfect and must be validated against objective checks and human labels.
4. Strategic agents can estimate or observe broad policy regularities, but do not receive hidden oracle labels.
5. Oversight has real cost, so detecting every possible issue is not the target optimum.
6. Human escalation is treated as a scarce action with cost and latency, not as a perfect free intervention.
7. Phase 2 mock trajectories validate software contracts and scorers; they do not estimate real LLM violation rates.
8. Constraint mutation labels in Phase 2 are injected by explicit mock behavior. Semantic equivalence detection is deferred.
9. Phase 3 architecture comparisons use controlled synthetic mutation schedules shared across architectures where possible.
10. Phase 4 oversight baselines operate on redacted observations and match detections to violations only after scoring.
11. Phase 5 learned monitors are trained on redacted checkpoint examples, with labels joined only after feature extraction.
12. Phase 5 smoke evaluations remain synthetic and do not estimate real LLM violation rates.

## Unresolved Design Decisions

1. Whether the first public release should use Inspect AI directly or wrap it behind an internal trajectory interface first.
2. Which API and open-weight models will be included in the first costed pilot.
3. How much policy information the strategic attacker can observe before acting.
4. Whether human labels should adjudicate all pilot disagreements or only high-severity disagreements.
5. Which Bayesian model should be primary after the initial Beta-Bernoulli and contextual-bandit baselines.
6. Whether task-level random effects should group by generated template family, base task, or both.

## Metrics

### Safety

- total trajectory violation rate
- final-output violation rate
- internal-only violation rate
- undetected violation rate
- severity-weighted harm
- time to detection
- fraction of violations prevented before execution
- constraint retention rate per delegation step

### Utility

- task success
- answer correctness
- completion rate
- latency
- token usage
- monetary cost

### Oversight Efficiency

- violations detected per audit
- violations prevented per audit
- harm prevented per unit cost
- oversight-budget utilization
- regret relative to oracle
- false-intervention rate
- precision, recall, F1, audit yield, budget utilization, regret proxy, and harm-cost frontier points for Phase 4 baselines
- adaptive audit yield, recall at budget, expected-harm proxy, value-of-information allocation, and oracle-regret proxy for Phase 5 policies

### Monitor Quality

- precision
- recall
- F1
- area under the precision-recall curve
- Brier score
- expected calibration error
- calibration slope and intercept
- selective risk under abstention
- OOD flag rate
- false-alert burden
- detection lead time

## Statistical Analysis Plan

The main violation model will estimate trajectory-level violation probability using hierarchical logistic regression. Predictors include:

- delegation depth
- oversight policy
- constraint category
- workflow architecture
- attacker type
- model family
- tool-use status
- task difficulty
- oversight budget
- policy-by-attacker interaction

Where data support it, the model includes task-level and model-level random effects. Every confirmatory result must report effect sizes and uncertainty intervals. Statistical significance without effect sizes is not sufficient.

Additional analyses:

- Bayesian posterior intervals
- bootstrap confidence intervals
- difference-in-proportions analysis
- multi-seed variability
- interaction effects
- monitor calibration analysis
- ablations
- sensitivity analysis
- power analysis

## Acceptance Criteria For Phase 1

- The formal objective and threat model are documented.
- Core schemas can validate example benchmark tasks.
- At least five example tasks exist, one from each required domain.
- The preregistration draft clearly separates hypotheses from results.
- No empirical claims are presented as observed results.
- Tests pass without model-provider credentials.
