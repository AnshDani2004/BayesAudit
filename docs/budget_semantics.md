# Budget Semantics

Phase 4 uses a hard budget ledger for every policy run.

Budget state tracks:

- initial budget
- remaining budget
- reserved budget
- consumed audit cost
- consumed intervention cost
- consumed escalation cost
- audit, intervention, and escalation counts
- rejected actions due to insufficient budget
- budget violations
- final reconciliation status

Replay reserves cost before an audit or intervention and consumes only reserved funds. If funds are insufficient, the action is skipped or marked insufficient budget. Finalization refunds any unconsumed reserved amount and marks the ledger reconciled.

Budgets are independent across policies and across budget values. Shadow mode still charges audit cost because inspection would consume oversight resources, but it does not charge intervention cost.
