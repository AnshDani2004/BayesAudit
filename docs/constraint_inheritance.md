# Constraint Inheritance

Phase 3 implements two new synthetic workflow architectures.

## Structured Inheritance

Structured inheritance sends natural-language subtask text separately from a typed `ConstraintEnvelope`. Each delegated branch receives an independent envelope instance that references the same immutable canonical registry. Constraint snapshots are generated from the envelope actually received by the worker.

Structured inheritance improves observability, but it is not treated as infallible. The same mutation schedules can remove, corrupt, weaken, or reroute envelopes.

## Verified Inheritance

Verified inheritance checks the received envelope before the worker acts. It validates task linkage, canonical hashes, integrity checksum, branch identifiers, required constraints, versions, scopes, privilege levels, unknown entries, and critical-constraint acknowledgment.

Verification responses are architecture controls, not oversight-policy decisions:

- continue
- repair from canonical
- minimal repair
- request clarification
- refuse subtask
- escalate
- terminate branch

Phase 3 implements deterministic refusal and repair paths. It does not simulate human oversight.

## Canonical Registry

Every run builds an immutable canonical registry from the benchmark task constraints. Delegated agents receive derived envelopes but cannot mutate the registry directly.

## Synthetic Scope

All Phase 3 architecture comparisons are synthetic benchmark-mechanics checks. They do not establish how real LLMs preserve constraints.

