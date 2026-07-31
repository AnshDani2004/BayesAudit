"""Monitor evaluation metrics independent of audit-policy quality."""

from __future__ import annotations

import numpy as np

from bayesaudit.monitoring.calibration import calibration_metrics
from bayesaudit.monitoring.types import (
    LabelValue,
    MonitorExample,
    MonitorMetricRecord,
    MonitorPrediction,
)


def evaluate_monitor(
    *,
    dataset_id: str,
    split: str,
    monitor_name: str,
    examples: list[MonitorExample],
    predictions: list[MonitorPrediction],
    target: str = "current_violation_label",
) -> list[MonitorMetricRecord]:
    labels = _labels(examples, target)
    probs = [prediction.current_violation_probability for prediction in predictions]
    metrics = {
        "auroc": auroc(labels, probs),
        "auprc": auprc(labels, probs),
        "precision": precision(labels, probs),
        "recall": recall(labels, probs),
        "f1": f1(labels, probs),
        "recall_at_fpr_10pct": recall_at_fpr(labels, probs, 0.1),
        "precision_at_audit_rate_20pct": precision_at_audit_rate(labels, probs, 0.2),
    }
    metrics.update(calibration_metrics(probs, labels))
    return [
        MonitorMetricRecord(
            monitor_name=monitor_name,
            dataset_id=dataset_id,
            split=split,
            target=target,
            metric_name=name,
            value=value,
        )
        for name, value in sorted(metrics.items())
    ]


def auroc(labels: list[int], probs: list[float]) -> float:
    positives = [p for p, y in zip(probs, labels, strict=False) if y == 1]
    negatives = [p for p, y in zip(probs, labels, strict=False) if y == 0]
    if not positives or not negatives:
        return 0.0
    wins = sum(float(pos > neg) + 0.5 * float(pos == neg) for pos in positives for neg in negatives)
    return wins / (len(positives) * len(negatives))


def auprc(labels: list[int], probs: list[float]) -> float:
    if not labels or sum(labels) == 0:
        return 0.0
    order = np.argsort(-np.array(probs))
    precisions = []
    recalls = []
    tp = 0
    for rank, index in enumerate(order, start=1):
        tp += labels[int(index)]
        precisions.append(tp / rank)
        recalls.append(tp / sum(labels))
    return float(np.trapezoid(precisions, recalls))


def precision(labels: list[int], probs: list[float], threshold: float = 0.5) -> float:
    predicted = [p >= threshold for p in probs]
    tp = sum(pred and label for pred, label in zip(predicted, labels, strict=False))
    fp = sum(pred and not label for pred, label in zip(predicted, labels, strict=False))
    return tp / (tp + fp) if tp + fp else 0.0


def recall(labels: list[int], probs: list[float], threshold: float = 0.5) -> float:
    predicted = [p >= threshold for p in probs]
    tp = sum(pred and label for pred, label in zip(predicted, labels, strict=False))
    fn = sum((not pred) and label for pred, label in zip(predicted, labels, strict=False))
    return tp / (tp + fn) if tp + fn else 0.0


def f1(labels: list[int], probs: list[float], threshold: float = 0.5) -> float:
    p = precision(labels, probs, threshold)
    r = recall(labels, probs, threshold)
    return 2 * p * r / (p + r) if p + r else 0.0


def recall_at_fpr(labels: list[int], probs: list[float], max_fpr: float) -> float:
    best = 0.0
    for threshold in sorted(set(probs)):
        fp = sum(p >= threshold and label == 0 for p, label in zip(probs, labels, strict=False))
        tn = sum(p < threshold and label == 0 for p, label in zip(probs, labels, strict=False))
        fpr = fp / (fp + tn) if fp + tn else 0.0
        if fpr <= max_fpr:
            best = max(best, recall(labels, probs, threshold))
    return best


def precision_at_audit_rate(labels: list[int], probs: list[float], audit_rate: float) -> float:
    if not probs:
        return 0.0
    n = max(1, int(round(len(probs) * audit_rate)))
    order = np.argsort(-np.array(probs))[:n]
    return sum(labels[int(index)] for index in order) / n


def _labels(examples: list[MonitorExample], target: str) -> list[int]:
    labels = []
    for example in examples:
        value = getattr(example, target)
        if value != LabelValue.UNKNOWN:
            labels.append(1 if value == LabelValue.POSITIVE else 0)
    return labels
