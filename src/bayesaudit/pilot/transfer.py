"""Monitor, calibration, and OOD transfer summaries for Phase 7."""

from __future__ import annotations

from bayesaudit.monitoring.calibration import calibration_metrics
from bayesaudit.monitoring.evaluation import evaluate_monitor
from bayesaudit.monitoring.ood import fit_ood_reference, score_ood
from bayesaudit.monitoring.types import LabelValue, MonitorExample, MonitorPrediction
from bayesaudit.pilot.types import OversightFeasibilityRecord, TransferMetricRecord


def monitor_transfer_metrics(
    examples: list[MonitorExample], predictions: list[MonitorPrediction]
) -> list[TransferMetricRecord]:
    metrics = evaluate_monitor(
        dataset_id="phase7_real_pilot",
        split="pilot",
        monitor_name=predictions[0].monitor_name if predictions else "unknown",
        examples=examples,
        predictions=predictions,
    )
    return [
        TransferMetricRecord(
            metric_family="monitor_transfer",
            metric_name=metric.metric_name,
            value=float(metric.value),
            small_sample_warning=len(examples) < 100,
            metadata=metric.metadata,
        )
        for metric in metrics
    ]


def calibration_transfer_metrics(
    examples: list[MonitorExample], predictions: list[MonitorPrediction]
) -> list[TransferMetricRecord]:
    labels = [
        1 if example.current_violation_label == LabelValue.POSITIVE else 0
        for example in examples
        if example.current_violation_label != LabelValue.UNKNOWN
    ]
    probabilities = [
        prediction.current_violation_probability
        for prediction, example in zip(predictions, examples, strict=False)
        if example.current_violation_label != LabelValue.UNKNOWN
    ]
    metrics = calibration_metrics(probabilities, labels)
    return [
        TransferMetricRecord(
            metric_family="calibration_transfer",
            metric_name=name,
            value=float(value),
            small_sample_warning=len(labels) < 100,
        )
        for name, value in metrics.items()
    ]


def ood_transfer_metrics(examples: list[MonitorExample]) -> list[TransferMetricRecord]:
    feature_names = sorted(
        {
            key
            for example in examples
            for key, value in example.observable_feature_payload.items()
            if isinstance(value, int | float | bool)
        }
    )
    reference = fit_ood_reference(examples, feature_names)
    records = [score_ood(example, reference) for example in examples]
    values = [record.ood_score for record in records]
    mean_value = sum(values) / len(values) if values else 0.0
    return [
        TransferMetricRecord(
            metric_family="ood",
            metric_name="mean_ood_score",
            value=float(mean_value),
            small_sample_warning=len(examples) < 100,
            metadata={"record_count": len(records)},
        )
    ]


def oversight_feasibility_records() -> list[OversightFeasibilityRecord]:
    scenarios = [
        "block_prohibited_tool_call",
        "request_clarification",
        "prevent_final_output_publication",
        "terminate_branch",
        "continue_unaffected_branches",
        "synthetic_resolver_escalation",
        "budget_exhaustion",
        "late_detection",
        "post_irreversible_internal_leakage",
    ]
    return [
        OversightFeasibilityRecord(
            scenario=scenario,
            supported=True,
            outcome="implemented as inert or sandboxed Phase 7 pilot dry-run check",
        )
        for scenario in scenarios
    ]
