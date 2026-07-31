# Provider Configuration

Phase 7 provider configs live under `configs/providers/`.

Rules:

- `configs/providers/mock/smoke.yaml` is the only enabled default provider.
- `configs/providers/remote/disabled_template.yaml` is disabled and contains no credentials.
- `configs/providers/local/disabled_template.yaml` is disabled and records local endpoint/runtime assumptions.
- Remote credentials must come from the named environment variable.
- Exact provider and model identifiers are required before real calls.
- No provider config may include an API key, bearer token, password, or secret value.

Changing a provider config changes the provider configuration hash stored in the pilot manifest and request hashes used for duplicate-billing protection.

