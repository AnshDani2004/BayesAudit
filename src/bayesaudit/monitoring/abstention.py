"""Abstention mechanisms and selective metrics."""

from __future__ import annotations

from bayesaudit.monitoring.types import AbstentionRecord, MonitorPrediction


def confidence_band_abstention(
    predictions: list[MonitorPrediction], *, low: float = 0.4, high: float = 0.6
) -> list[AbstentionRecord]:
    records: list[AbstentionRecord] = []
    abstained_count = 0
    for index, prediction in enumerate(predictions, start=1):
        probability = prediction.current_violation_probability
        abstained = low <= probability <= high
        abstained_count += int(abstained)
        prediction.abstained = abstained
        prediction.abstention_reason = "confidence_band" if abstained else None
        records.append(
            AbstentionRecord(
                prediction_id=prediction.prediction_id,
                mechanism="confidence_band",
                abstained=abstained,
                reason="probability near decision boundary" if abstained else None,
                coverage_after_abstention=1.0 - abstained_count / index,
            )
        )
    return records


def missing_feature_abstention(
    prediction: MonitorPrediction, missing_features: list[str]
) -> AbstentionRecord:
    abstained = bool(missing_features)
    if abstained:
        prediction.abstained = True
        prediction.abstention_reason = "missing_features"
    return AbstentionRecord(
        prediction_id=prediction.prediction_id,
        mechanism="missing_features",
        abstained=abstained,
        reason=",".join(missing_features) if missing_features else None,
        coverage_after_abstention=0.0 if abstained else 1.0,
    )


def selective_metrics(labels: list[int], predictions: list[MonitorPrediction]) -> dict[str, float]:
    retained = [
        (label, prediction)
        for label, prediction in zip(labels, predictions, strict=False)
        if not prediction.abstained
    ]
    coverage = len(retained) / len(predictions) if predictions else 0.0
    if not retained:
        return {"coverage": coverage, "selective_risk": 0.0, "abstention_rate": 1.0}
    errors = [
        int((prediction.current_violation_probability >= 0.5) != bool(label))
        for label, prediction in retained
    ]
    return {
        "coverage": coverage,
        "selective_risk": sum(errors) / len(errors),
        "abstention_rate": 1.0 - coverage,
    }
