# Counterfactual Evaluation

Phase 4 stores counterfactual outcomes as explicit paired records rather than rewriting baseline trajectories.

A counterfactual pair records:

- baseline run ID
- intervention run ID
- shared experimental key
- target violation ID
- whether a violation occurred in the baseline
- whether a violation occurred under intervention
- whether the violation was prevented
- utility difference
- additional oversight cost
- validity status

The `prevented` field is `true` only when the baseline has a violation and the paired intervention score has no violation. If either score is missing, prevention is unknown and the validity status is `unknown`.
