"""Annotation export and import validation for monitor labels."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import Field

from bayesaudit.monitoring.dataset import load_monitor_examples
from bayesaudit.monitoring.types import LabelValue
from bayesaudit.schemas import StrictModel


class AnnotationItem(StrictModel):
    annotation_id: str
    example_id: str
    redacted_observation_text: str
    current_proposed_action: str
    available_constraints: list[str]
    tool_request: str | None = None
    labels: dict[str, str | None] = Field(default_factory=dict)
    evidence_spans: list[str] = Field(default_factory=list)


def export_annotations(
    dataset_dir: Path, output_path: Path, *, max_items: int | None = None
) -> dict[str, Any]:
    examples = load_monitor_examples(dataset_dir)
    if max_items is not None:
        examples = examples[:max_items]
    items = [
        AnnotationItem(
            annotation_id=f"ann_{example.example_id}",
            example_id=example.example_id,
            redacted_observation_text=example.observable_text_payload,
            current_proposed_action=example.checkpoint_type,
            available_constraints=[
                key
                for key, value in example.observable_feature_payload.items()
                if key.endswith("constraints") and bool(value)
            ],
            tool_request="present"
            if example.observable_feature_payload.get("tool_requested")
            else None,
            labels={
                "current_violation": None,
                "imminent_violation": None,
                "preventability": None,
                "severity": None,
                "intervention_usefulness": None,
            },
        )
        for example in examples
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([item.model_dump(mode="json") for item in items]).to_json(
        output_path, orient="records", indent=2
    )
    return {"exported": len(items), "path": str(output_path)}


def validate_annotation_import(path: Path) -> dict[str, Any]:
    rows = pd.read_json(path).to_dict(orient="records")
    errors = []
    allowed = {LabelValue.POSITIVE, LabelValue.NEGATIVE, LabelValue.UNKNOWN, None}
    for row in rows:
        try:
            item = AnnotationItem.model_validate(row)
        except Exception as exc:
            errors.append(str(exc))
            continue
        for name, value in item.labels.items():
            if value not in allowed:
                errors.append(f"{item.annotation_id}:{name}: invalid label {value}")
    return {"valid": not errors, "item_count": len(rows), "errors": errors}
