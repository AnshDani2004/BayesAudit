# BayesAudit Dataset Card

## Intended Use

The tracked BayesAudit datasets support offline validation of oversight experiments and monitor behavior. They are designed for reproducible research, teaching, and portfolio review.

## Data Sources

Datasets are derived from synthetic benchmark tasks, inert workflow traces, provider response summaries, objective scorers, and offline adjudication artifacts. No real user data or real external tool results are included.

## Principal Datasets

- Phase 8 confirmatory validated dataset: `configs/experiments/phase8_dataset_manifest.json`
- Phase 9 positive dataset: `configs/experiments/phase9_validated_positive_dataset.jsonl`
- Phase 9 negative dataset: `configs/experiments/phase9_validated_negative_dataset.jsonl`

## Labels

Labels include objective-positive/negative status, violation location, internal-only status, monitor alert classification, policy decision, intervention status, and prevention classification. Phase 9 contains 24 validated positives and 24 validated negatives.

## Provenance

Every dataset manifest contains canonical hashes. JSONL rows include record hashes. Provider-backed datasets are linked to request summaries and token/cost summaries.

## Limitations

The datasets are synthetic, small, and benchmark-specific. They do not represent production traffic, population prevalence, or independent human annotation agreement.

## Reproduction

Run:

```bash
python -m bayesaudit.cli validate-phase8
python -m bayesaudit.cli validate-phase9
```

## Misuse Risks

Do not train or report a production monitor using these labels as if they were real-world incidents. They are controlled research labels for an inert benchmark.
