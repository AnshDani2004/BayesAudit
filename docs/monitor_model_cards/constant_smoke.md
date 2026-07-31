# Monitor Model Card: constant_smoke

## Intended Use
Estimate checkpoint-level safety risk from redacted BayesAudit observations.

## Non-Intended Use
Do not use as a standalone deployed safety decision-maker or as evidence of real-model behavior.

## Training Dataset
Dataset hash: `9e712538b9a786dd887f4b96531b5ec731a5a1d45ce52afac0711df591c1bb1e`
Split manifest hash: ``

## Feature Set
depth, branch_present, prior_audit_count, remaining_budget, constraint_count, critical_constraint_count, tool_call_count, missing_required_constraints, weakened_constraints, contradicted_constraints, privilege_demotions, verification_failures, tool_requested, approval_required, approval_present, prohibited_tool_indicator, sensitive_token_indicator, irreversible_action_indicator, external_tool_indicator, text_length, identifier_count, citation_count, unknown_citation_count, budget_numeric_count, approval_language_indicator, constraint_reference_count, uncertainty_language_indicator

## Label Definitions
Target: `current_violation_label` using temporally defined Phase 5 monitor labels.

## Hyperparameters
`{'learning_rate': 0.1, 'iterations': 200, 'class_weight': 1.0}`

## Calibration
`{}`

## Performance
- all/auprc: 0.0000
- all/auroc: 0.0000
- all/brier: 0.0000
- all/ece: 0.0000
- all/f1: 0.0000
- all/intercept: 0.0000
- all/log_loss: 0.0000
- all/precision: 0.0000
- all/precision_at_audit_rate_20pct: 0.0000
- all/recall: 0.0000
- all/recall_at_fpr_10pct: 0.0000
- all/slope: 0.0000

## Robustness
Evaluate with grouped holdout manifests before confirmatory claims.

## Known Failure Modes
Synthetic-only training, small sample instability, sparse held-out groups, and non-causal features.

## Leakage Safeguards
Features are extracted from enumerated redacted observation fields only.

## Cost And Latency
Local deterministic baseline; no provider calls.

## Version
Artifact hash: `1db88175a1fcd2dad2e2b36d801baeedda78b6ad26e170992b614435919b7d66`
