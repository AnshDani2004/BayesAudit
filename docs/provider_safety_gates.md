# Provider Safety Gates

Real provider calls are blocked unless all Phase 7 gates pass:

- provider calls enabled in configuration
- CLI `--allow-provider-calls`
- explicit provider
- explicit model identifier
- credential environment variable for remote APIs
- explicit cost, token, request, and trajectory ceilings
- estimate within all ceilings
- planned requests and trajectories within ceilings
- large-run guard satisfied
- configuration valid
- pilot manifest written
- output directory writable
- adapter dry-run validation passed
- no CI environment detected

The command `bayesaudit authorize-provider-run` writes a permission record listing every gate, pass/fail status, timestamp, configuration hash, command-line authorization, environment classification, and final decision.

CI remains credential-free. Missing gates fail before any provider request is attempted.

