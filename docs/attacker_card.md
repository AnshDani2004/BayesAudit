# Attacker Card

## Intended Use

BayesAudit attackers are synthetic benchmark components for testing whether hierarchical workflows preserve constraints under pressure. They are safe, inert, and limited to controlled tasks.

## Attacker Families

The repository includes ten attacker configurations and fifteen attack primitives. Phase 9 selected held-out Phase 6 assets:

- Privacy: `random_selective`
- Authorization: `policy_aware`
- Evidence: `opportunistic`

## Provenance

Attacker configs live under `configs/attackers/`; primitives live under `configs/attacks/`. Phase 9 selection is recorded in `configs/experiments/phase9_heldout_attacker_manifest.json`.

## Labels

Attacker adjudication distinguishes attempted attack, uptake, valid strategy, refusal, unscorable output, and safe-control contamination.

## Limitations

Attacks are synthetic and do not perform real exfiltration, unauthorized approval, external browsing, or evidence fabrication outside inert benchmark text.

## Reproduction

Run:

```bash
python -m bayesaudit.cli validate-attackers
python -m bayesaudit.cli validate-attacks
python -m bayesaudit.cli validate-phase9
```

## Misuse Risks

Do not treat these attackers as operational red-team tools. They are benchmark stimuli for controlled oversight measurement.
