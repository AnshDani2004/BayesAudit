# Reproducibility Guide

## Offline-First Validation

Most release validation is offline and requires no provider key:

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m mypy --no-incremental src tests
python -m pytest -q
python -m compileall -q src tests scripts
python -m bayesaudit.cli validate-scenarios --root scenarios
python -m bayesaudit.cli validate-envelopes
python -m bayesaudit.cli validate-policies
python -m bayesaudit.cli validate-attackers
python -m bayesaudit.cli validate-attacks
python -m bayesaudit.cli validate-phase8
python -m bayesaudit.cli validate-phase9
python -m bayesaudit.cli validate-phase10
```

## Provider-Backed Reproduction

Provider-backed reproduction is optional and should be run only with explicit ceilings:

```bash
read -s OPENAI_API_KEY
export OPENAI_API_KEY
python -m bayesaudit.cli run-phase9-provider \
  --allow-provider-calls \
  --max-cost 0.12 \
  --max-tokens 300000 \
  --max-requests 300 \
  --max-trajectories 48
```

## Artifact Lineage

Tracked JSON artifacts include canonical hashes. JSONL rows include record hashes. Release-facing summaries cite source manifests rather than relying on prose alone.

## Provider Cache Semantics

Phase 9 tracked request summaries are cache-hit records regenerated after the original acquisition run. See [Phase 9 provider accounting note](phase9_provider_accounting_note.md) before reporting request, token, or cost values.

## Security Reproduction

The public release hardening pass adds local security audit scripts and Gitleaks configuration. If Gitleaks is installed, run:

```bash
gitleaks detect --source . --redact
gitleaks git --redact --log-opts="--all"
```

## Expected Baseline

The baseline before hardening was 1,937 passing tests. Any intentional test-count change must be documented.
