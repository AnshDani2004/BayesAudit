# Constraint Mutations

Phase 3 introduces explicit, serializable mutation profiles under `configs/mutations/`.

Mutation profiles are provider-independent. They are applied by the workflow architecture, not inferred from model text. Scoring and comparison inspect the resulting visible state rather than trusting the mutation label as the result.

Supported families:

- content mutations: drop, weaken, strengthen, contradict, equivalent paraphrase, unrelated replacement, unauthorized addition
- structural mutations: missing envelope, removed entries, duplicated entries, corrupted hashes, stale versions, wrong task or branch IDs, broken parent linkage
- privilege mutations: demotion, removed privilege metadata, source-level mislabeling
- routing mutations: branch-specific drops and stale aggregation state
- context-pressure mutations: deterministic truncation rules
- negative controls: metadata changes, order permutation, valid branch copies, equivalent paraphrases

Phase 3 does not claim general semantic equivalence detection. Equivalent paraphrase is recognized only when produced by a controlled deterministic transformation.

