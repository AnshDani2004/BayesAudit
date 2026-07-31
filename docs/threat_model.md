# Threat Model

## System Under Study

BayesAudit studies LLM workflows that decompose tasks into steps, messages, delegated subtasks, and optional tool calls. A workflow may include a planner, workers, reviewers, monitors, and human escalation.

The protected asset is constraint compliance across the full trajectory, not only the final output.

## Constraint Failure Modes

Constraint failures may occur when:

- constraints disappear during delegation
- constraints are paraphrased with changed meaning
- a downstream worker treats delegation as new authorization
- a tool call exposes prohibited or sensitive information
- a local subtask optimizes against a global budget
- a final answer conceals an unsafe intermediate step
- an agent claims nonexistent approval or invents evidence

## Behavioral Conditions

### Honest

The agent attempts to satisfy the task and constraints. Violations are accidental, such as omission, misunderstanding, or local optimization.

### Opportunistic

The agent may violate a constraint when doing so substantially improves task reward or reduces effort, especially when perceived detection probability is low.

### Strategic

The agent estimates or observes oversight patterns and chooses which step to attack, which constraint to violate, whether to conceal the violation, whether to delay it, whether to preserve a compliant final answer, and whether to exploit predictable checkpoints.

## Attacker Capabilities

The strategic attacker may know:

- the public benchmark domain
- the broad set of oversight policies under comparison
- whether fixed checkpoints or random budgets are likely
- its own attack budget and detection penalty
- the apparent trajectory state available to monitors

The strategic attacker may not know:

- hidden oracle labels
- random audit draws before they happen
- private human annotator decisions
- withheld evaluation seeds, unless a configured experiment explicitly grants them

## Monitor Capabilities

Monitors may inspect current and prior trajectory state, depending on the configured policy. Monitors may be deterministic, learned, LLM-based, or oracle. Oracle policies are evaluation upper bounds and must not be compared as deployable systems.

## Exclusions

BayesAudit does not initially model:

- multi-user collusion
- compromised infrastructure
- prompt injection from arbitrary live web pages
- real personal data
- real irreversible external actions

These exclusions must be revisited before applying findings to production agent systems.

