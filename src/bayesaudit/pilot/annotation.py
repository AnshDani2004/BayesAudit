"""Real-pilot annotation sampling, exports, and agreement metrics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.types import AnnotationAgreementRecord, AnnotationSampleItem


def build_annotation_sample(
    trajectory_rows: list[dict[str, Any]],
    *,
    sample_size: int,
    mode: str = "blind",
) -> dict[str, Any]:
    selected = trajectory_rows[:sample_size] if sample_size else trajectory_rows
    probability = (len(selected) / len(trajectory_rows)) if trajectory_rows else 0.0
    items = [
        AnnotationSampleItem(
            annotation_id="ann_" + canonical_json_hash(row.get("trajectory_id", row))[:20],
            trajectory_id=str(row.get("trajectory_id", row.get("run_id", "unknown"))),
            sampling_stratum=str(row.get("domain", row.get("task_id", "overall"))),
            sampling_probability=probability,
            blind_payload=_blind_payload(row),
            adjudication_payload=_adjudication_payload(row),
            error_analysis_payload=_error_analysis_payload(row),
        )
        for row in selected
    ]
    return {
        "mode": mode,
        "sample_size": len(items),
        "sampling_probability": probability,
        "items": [item.model_dump(mode="json") for item in items],
    }


def agreement_records(rows: list[dict[str, Any]]) -> list[AnnotationAgreementRecord]:
    by_label: dict[str, list[tuple[str | None, str | None]]] = defaultdict(list)
    for row in rows:
        labels_a = row.get("annotator_a", {})
        labels_b = row.get("annotator_b", {})
        if not isinstance(labels_a, dict) or not isinstance(labels_b, dict):
            continue
        for label in sorted(set(labels_a).union(labels_b)):
            by_label[label].append((labels_a.get(label), labels_b.get(label)))
    records: list[AnnotationAgreementRecord] = []
    for label, pairs in by_label.items():
        agreements = sum(1 for left, right in pairs if left == right)
        percent = agreements / len(pairs) if pairs else 0.0
        records.append(
            AnnotationAgreementRecord(
                label_name=label,
                item_count=len(pairs),
                percent_agreement=percent,
                cohens_kappa=_cohens_kappa(pairs),
                krippendorff_alpha=None,
            )
        )
    return records


def _blind_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "trajectory_id": row.get("trajectory_id"),
        "redacted_steps": _redacted_steps(row),
    }


def _adjudication_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "trajectory_id": row.get("trajectory_id"),
        "redacted_steps": _redacted_steps(row),
        "automated_scores": row.get("automated_scores", {}),
    }


def _error_analysis_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "trajectory_id": row.get("trajectory_id"),
        "model_configuration": row.get("model_configuration", {}),
        "oversight_policy": row.get("oversight_policy"),
        "monitor_predictions": row.get("monitor_predictions", []),
        "automated_scores": row.get("automated_scores", {}),
    }


def _redacted_steps(row: dict[str, Any]) -> list[dict[str, Any]]:
    steps = row.get("steps", [])
    redacted = []
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                redacted.append(
                    {
                        "step_id": step.get("step_id"),
                        "role": step.get("role"),
                        "kind": step.get("kind"),
                        "content": _response_content(step),
                    }
                )
    return redacted


def _response_content(step: dict[str, Any]) -> str:
    response = step.get("model_response", {})
    if not isinstance(response, dict):
        return ""
    message = response.get("message", {})
    return str(message.get("content", "")) if isinstance(message, dict) else ""


def _cohens_kappa(pairs: list[tuple[str | None, str | None]]) -> float:
    if not pairs:
        return 0.0
    observed = sum(1 for left, right in pairs if left == right) / len(pairs)
    left_counts: dict[str | None, int] = defaultdict(int)
    right_counts: dict[str | None, int] = defaultdict(int)
    for left, right in pairs:
        left_counts[left] += 1
        right_counts[right] += 1
    expected = sum(
        (left_counts[label] / len(pairs)) * (right_counts[label] / len(pairs))
        for label in set(left_counts).union(right_counts)
    )
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)

