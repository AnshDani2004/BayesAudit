# Oversight Observations

Phase 4 adds redacted oversight observations with schema version `bayesaudit.oversight.v1`.
They are separate from core trajectory schema `bayesaudit.v2`.

An observation contains:

- the current checkpoint and current step identifiers
- current input messages and proposed model response
- redacted tool-call requests
- current constraint snapshot public fields
- prior public architecture events, such as branch refusals
- prior public audit outcomes and policy actions
- current budget state
- observable task metadata, including domain, difficulty, authorized tools, prohibited tools, and expected escalation points
- deterministic observable risk features

An observation must not contain scorer labels, future steps, raw mock scripts, ground truth, violations, mutation-event labels, score objects, or oracle metadata. Oracle labels are passed only to the evaluation-only oracle policy by replay code and are never inserted into deployable observations.

Current risk features include constraint loss or weakening, privilege demotion, verification failure, prohibited tools, missing approval, sensitive tokens in visible text or tool arguments, unknown citations, external retrieval, prohibited protected-attribute fields, duplicate actions, and visible budget overrun.
