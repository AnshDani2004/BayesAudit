"""Lightweight distribution-shift diagnostics."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from bayesaudit.monitoring.types import MonitorExample, OODScoreRecord


def fit_ood_reference(
    examples: list[MonitorExample], feature_names: list[str]
) -> dict[str, object]:
    matrix = _matrix(examples, feature_names)
    levels = {
        "architecture": sorted({str(example.architecture) for example in examples}),
        "domain": sorted({str(example.domain) for example in examples}),
    }
    return {
        "feature_names": feature_names,
        "min": matrix.min(axis=0).tolist() if len(matrix) else [],
        "max": matrix.max(axis=0).tolist() if len(matrix) else [],
        "mean": matrix.mean(axis=0).tolist() if len(matrix) else [],
        "std": (matrix.std(axis=0) + 1e-6).tolist() if len(matrix) else [],
        "levels": levels,
    }


def score_ood(example: MonitorExample, reference: dict[str, object]) -> OODScoreRecord:
    raw_feature_names = reference.get("feature_names", [])
    feature_names = (
        [str(name) for name in raw_feature_names] if isinstance(raw_feature_names, list) else []
    )
    values = np.array(
        [float(example.observable_feature_payload.get(name, 0.0) or 0.0) for name in feature_names]
    )
    mean = np.array(reference.get("mean", []), dtype=float)
    std = np.array(reference.get("std", []), dtype=float)
    mins = np.array(reference.get("min", []), dtype=float)
    maxs = np.array(reference.get("max", []), dtype=float)
    flags = []
    if len(values) and (np.any(values < mins) or np.any(values > maxs)):
        flags.append("feature_range_violation")
    levels = reference.get("levels", {})
    if isinstance(levels, dict):
        raw_architectures = levels.get("architecture", [])
        raw_domains = levels.get("domain", [])
        architectures = (
            [str(value) for value in raw_architectures]
            if isinstance(raw_architectures, list)
            else []
        )
        domains = [str(value) for value in raw_domains] if isinstance(raw_domains, list) else []
        if str(example.architecture) not in architectures:
            flags.append("missing_architecture_level")
        if str(example.domain) not in domains:
            flags.append("missing_domain_level")
    distance = float(np.linalg.norm((values - mean) / std)) if len(values) else 0.0
    if example.observable_feature_payload.get("text_length", 0) and float(
        example.observable_feature_payload["text_length"] or 0.0
    ) > 5000:
        flags.append("text_length_shift")
    return OODScoreRecord(
        example_id=example.example_id,
        detector_name="range_level_distance_v1",
        ood_score=distance + len(flags),
        flags=flags,
    )


def _matrix(examples: list[MonitorExample], feature_names: list[str]) -> NDArray[np.float64]:
    if not examples or not feature_names:
        return np.zeros((0, 0))
    return np.array(
        [
            [
                float(example.observable_feature_payload.get(name, 0.0) or 0.0)
                for name in feature_names
            ]
            for example in examples
        ],
        dtype=float,
    )
