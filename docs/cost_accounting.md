# Cost Accounting

Phase 7 estimates cost before every provider run from planned requests, estimated input tokens, estimated output tokens, provider pricing fields, cache assumptions, and retry assumptions.

Hard ceilings are supplied on the CLI for real calls:

- `--max-cost`
- `--max-tokens`
- `--max-requests`
- `--max-trajectories`

Execution aborts before the next request if a hard ceiling would be exceeded. Request ledger rows and response records preserve estimated usage and cost. Provider-reported usage and cost are preserved where available.

Mock validation uses a monetary ceiling of `0.0`.

