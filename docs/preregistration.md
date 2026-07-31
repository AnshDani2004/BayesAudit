# Preregistration Draft

## Study Title

BayesAudit: Adaptive, Budget-Constrained Oversight for Hierarchical LLM Agents

## Confirmatory Research Questions

1. How does constraint compliance change as delegation depth increases?
2. Which workflow steps are most likely to produce violations?
3. At a fixed oversight budget, which auditing policy minimizes undetected violations?
4. Does Bayesian adaptive oversight outperform random, fixed, heuristic, and LLM-judge policies?
5. Do policies effective against accidental failures remain effective against strategically selected violations?
6. Does structured constraint inheritance reduce oversight needs?
7. Does final-output-only evaluation underestimate trajectory-level failures?
8. How reliable and calibrated are automated monitors compared with human annotations?

## Primary Hypotheses

1. Violation probability increases with delegation depth.
2. Delegation and tool-use transitions have higher conditional risk than ordinary reasoning steps.
3. Structured constraint inheritance reduces accidental constraint drift.
4. Random auditing performs poorly against strategic attack selection.
5. Bayesian adaptive oversight produces fewer undetected violations than fixed policies at equal oversight cost.
6. Final-output-only evaluation underestimates total trajectory violations.
7. LLM judges become less reliable under strategic concealment and distribution shift.
8. Structured inheritance and adaptive oversight provide complementary safety benefits.
9. Stronger baseline models do not necessarily produce more oversight-efficient systems.
10. Monitor calibration matters independently of monitor classification accuracy.

## Primary Outcomes

- severity-weighted undetected harm
- trajectory-level violation rate
- final-output violation rate
- internal-only violation rate
- task success
- oversight cost
- harm prevented per audit
- regret relative to oracle

## Planned Experimental Factors

- workflow architecture
- delegation depth
- oversight policy
- oversight budget
- behavioral condition
- domain
- model family
- task difficulty

## Confirmatory Analysis

The main confirmatory model is a hierarchical logistic regression for trajectory-level violation. Secondary confirmatory models estimate undetected violation and final-output-only undercount. Predictors and interactions are specified in `docs/methodology.md`.

All confirmatory estimates must include uncertainty intervals and effect sizes. Exploratory analyses must be labeled exploratory.

## Exclusions

Runs may be excluded only for documented infrastructure failure, invalid task serialization, failed scoring due to a bug confirmed before inspecting policy outcomes, or provider outage. All exclusions must be recorded.

## Benchmark Freeze

After the pilot phase, benchmark tasks, primary metrics, and confirmatory models are frozen. Changes after freeze must be documented as preregistration deviations.

## Results Status

No empirical results have been collected at this stage.

