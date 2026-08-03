# Oversight Policy Card

## Intended Use

BayesAudit oversight policies study how to allocate limited audit budget across hierarchical workflow checkpoints. They are research policies, not production enforcement systems.

## Policies

- No oversight
- Random auditing
- Fixed checkpoint auditing
- Rule-based selective auditing
- Bayesian adaptive auditing
- Oracle auditing for evaluation upper bounds only

## Monitor Inputs

Policies consume redacted checkpoint observations, deterministic risk indicators, monitor scores, and budget state. They do not receive real external tool outputs.

## Labels and Metrics

Metrics include alert counts, true positives, false positives, false negatives, audit decisions, intervention decisions, and exploratory prevention classifications.

## Limitations

Rule-based monitoring was sensitive in the principal synthetic studies but produced false positives. The Bayesian/logistic monitor missed positives in Phase 9. Clean causal prevention was not established.

## Reproduction

Run:

```bash
python -m bayesaudit.cli validate-policies
python -m bayesaudit.cli validate-phase8
python -m bayesaudit.cli validate-phase9
```

## Misuse Risks

Do not deploy these policies as production safety controls. They are benchmark policies for studying oversight tradeoffs.
