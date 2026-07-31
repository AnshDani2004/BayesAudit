# Real Model Pilot

Real provider calls are not part of default Phase 5 operation. The real-pilot config is a costed dry-run manifest unless the caller explicitly passes an allow flag and the provider config remains within cost, token, request, and trajectory ceilings.

Dry-run command:

```bash
python -m bayesaudit.cli run-real-pilot --config configs/experiments/phase5_real_pilot.yaml --dry-run
```

Non-mock providers are blocked when `allow_provider_calls` is false. A successful dry-run means the pilot plan is internally consistent; it does not mean any real provider call occurred.
