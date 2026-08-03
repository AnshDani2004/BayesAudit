# Model and Provider Card

## Intended Use

This card documents the provider-backed portions of BayesAudit. The provider integration is used to run bounded research experiments with exact request hashing, structured outputs, cache validation, and token/cost accounting.

## Provider and Model

- Provider: OpenAI
- API family: Responses API
- Model used in principal studies: `gpt-5-nano-2025-08-07`
- Streaming: disabled
- External tools: disabled
- Structured output: native JSON schema

## Credential Handling

Provider-backed reproduction reads `OPENAI_API_KEY` from the environment. Credentials are not required for offline validation and should never be committed. `.env.example` intentionally contains empty values only.

## Request and Cache Provenance

Requests use exact prompt/request hashes. Raw provider responses and caches are stored under ignored `results/` paths. Tracked release artifacts preserve summaries, hashes, token usage, cost estimates, and reproducibility manifests.

Phase 9 accounting is reconciled in [Phase 9 provider accounting note](phase9_provider_accounting_note.md).

## Limitations

Only one provider model was tested. The findings do not establish cross-model generalization or production readiness.

## Reproduction

Provider-backed runs require explicit ceilings, for example:

```bash
python -m bayesaudit.cli run-phase9-provider \
  --allow-provider-calls \
  --max-cost 0.12 \
  --max-tokens 300000 \
  --max-requests 300 \
  --max-trajectories 48
```

## Misuse Risks

Do not compare providers or models using this release unless new experiments are designed and preregistered. Do not publish token/cost claims without distinguishing acquisition calls from cache replay.
