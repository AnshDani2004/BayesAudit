# LLM Judge

The Phase 5 LLM-judge interface returns structured probabilities for current violation, imminent violation, preventability, expected severity, intervention usefulness, suspected categories, evidence references, confidence, and abstention.

Current smoke behavior uses a mock provider. Real providers are blocked unless explicit provider gates are opened, and prompts are rendered from the redacted observation text only. The judge prompt rejects forbidden leakage terms before any provider path can run.

Provider safety constraints:

- `dry_run` defaults to true
- non-mock providers are blocked when `allow_provider_calls` is false
- cost, token, trajectory, and request ceilings are checked before use
- dry-run manifests are persisted for auditability
