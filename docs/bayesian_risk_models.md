# Bayesian Risk Models

Phase 5 includes two online risk states:

- grouped Beta-Bernoulli risk state
- approximate Bayesian logistic state with diagonal precision

Both states update only from audited examples with feedback. Unaudited examples can be scored, but they do not alter posterior state. Posterior snapshots record priors, posterior parameters, audit outcomes, feature version, random state, effective sample size, and uncertainty.

These models are allocation tools for synthetic oversight experiments, not claims about real deployed model risk.
