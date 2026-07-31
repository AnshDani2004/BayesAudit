# Provider Execution

Phase 7 introduces provider-neutral execution contracts under `bayesaudit.pilot`.

Supported provider classes:

- `mock`: deterministic, credential-free, allowed in CI.
- `remote_api`: disabled by default, requires exact provider, exact model ID, credential environment variable, explicit CLI authorization, and hard ceilings.
- `local`: disabled by default, requires exact model ID plus endpoint or runtime metadata. Local execution is tracked separately from remote API execution and is not treated as free.

No provider is selected by default for real runs. Real-provider configs must be edited deliberately and must not contain credentials.

Every planned run records provider name, exact model identifier, sampling parameters, prompt version, usage estimates, request counts, cost ceilings, and cache assumptions. Raw responses and invalid outputs are preserved in controlled artifacts when an authorized run is executed.

