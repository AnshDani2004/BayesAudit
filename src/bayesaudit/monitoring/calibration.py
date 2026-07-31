"""Calibration methods and metrics for monitor probabilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.monitoring.types import (
    CalibrationArtifact,
    LabelValue,
    MonitorExample,
    MonitorPrediction,
)
from bayesaudit.schemas import StrictModel
from bayesaudit.storage.jsonl import write_json_atomic


class CalibrationConfig(StrictModel):
    calibration_id: str
    method: str = "platt"
    predictions_path: Path | None = None
    dataset_dir: Path | None = None
    artifact_dir: Path = Path("results/tables/calibration")
    target: str = "current_violation_label"
    iterations: int = 200
    learning_rate: float = 0.1
    base_monitor: str = "monitor"
    base_artifact_hash: str = ""


def load_calibration_config(path: Path) -> CalibrationConfig:
    import yaml

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"calibration config must be a mapping: {path}")
    return CalibrationConfig.model_validate(payload)


def fit_calibrator(
    config: CalibrationConfig, predictions: list[MonitorPrediction], examples: list[MonitorExample]
) -> CalibrationArtifact:
    labels = _labels_for_predictions(predictions, examples, config.target)
    probs = np.array(
        [prediction.current_violation_probability for prediction in predictions],
        dtype=float,
    )
    if config.method == "platt":
        params = _fit_platt(probs, labels, config.iterations, config.learning_rate)
    elif config.method == "temperature":
        params = {"temperature": _fit_temperature(probs, labels)}
    elif config.method == "isotonic":
        params = _fit_isotonic(probs, labels)
    elif config.method == "beta":
        params = _fit_platt(_beta_features(probs), labels, config.iterations, config.learning_rate)
    else:
        raise ValueError(f"unknown calibration method: {config.method}")
    artifact_hash = canonical_json_hash(
        {
            "config": config.model_dump(mode="json"),
            "prediction_ids": [prediction.prediction_id for prediction in predictions],
            "params": params,
        }
    )
    artifact = CalibrationArtifact(
        calibration_id=config.calibration_id,
        base_monitor=config.base_monitor,
        base_artifact_hash=config.base_artifact_hash,
        calibration_method=config.method,
        calibration_dataset_hash=canonical_json_hash([example.example_id for example in examples]),
        fitting_configuration=config.model_dump(mode="json"),
        artifact_hash=artifact_hash,
        parameters=params,
    )
    config.artifact_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        config.artifact_dir / f"{config.calibration_id}.json",
        artifact.model_dump(mode="json"),
    )
    return artifact


def apply_calibration(probability: float, artifact: CalibrationArtifact) -> float:
    p = min(1.0 - 1e-9, max(1e-9, probability))
    if artifact.calibration_method == "platt":
        return _sigmoid(
            float(artifact.parameters["a"]) * _logit_scalar(p)
            + float(artifact.parameters["b"])
        )
    if artifact.calibration_method == "temperature":
        temperature = max(1e-6, float(artifact.parameters["temperature"]))
        return _sigmoid(_logit_scalar(p) / temperature)
    if artifact.calibration_method == "isotonic":
        xs: object = artifact.parameters.get("x", [])
        ys: object = artifact.parameters.get("y", [])
        if not isinstance(xs, list) or not isinstance(ys, list) or not xs:
            return probability
        return float(np.interp(p, np.array(xs, dtype=float), np.array(ys, dtype=float)))
    if artifact.calibration_method == "beta":
        x1 = np.log(p)
        x2 = np.log1p(-p)
        return _sigmoid(float(artifact.parameters["a"]) * x1 + float(artifact.parameters["b"]) * x2)
    return probability


def calibration_metrics(
    probabilities: list[float], labels: list[int], *, bins: int = 10
) -> dict[str, float]:
    probs = np.array(probabilities, dtype=float)
    y = np.array(labels, dtype=float)
    if len(y) == 0:
        return {"brier": 0.0, "log_loss": 0.0, "ece": 0.0, "slope": 0.0, "intercept": 0.0}
    clipped = np.clip(probs, 1e-9, 1.0 - 1e-9)
    brier = float(np.mean((clipped - y) ** 2))
    log_loss = float(-np.mean(y * np.log(clipped) + (1.0 - y) * np.log1p(-clipped)))
    ece = expected_calibration_error(clipped.tolist(), labels, bins=bins)
    slope, intercept = calibration_slope_intercept(clipped.tolist(), labels)
    return {
        "brier": brier,
        "log_loss": log_loss,
        "ece": ece,
        "slope": slope,
        "intercept": intercept,
    }


def expected_calibration_error(
    probabilities: list[float], labels: list[int], *, bins: int = 10
) -> float:
    if not probabilities:
        return 0.0
    total = len(probabilities)
    ece = 0.0
    for low in np.linspace(0, 1, bins, endpoint=False):
        high = low + 1 / bins
        indices = [
            i
            for i, probability in enumerate(probabilities)
            if low <= probability < high or (high >= 1 and probability <= 1)
        ]
        if not indices:
            continue
        confidence = float(np.mean([probabilities[i] for i in indices]))
        accuracy = float(np.mean([labels[i] for i in indices]))
        ece += len(indices) / total * abs(confidence - accuracy)
    return float(ece)


def calibration_slope_intercept(
    probabilities: list[float], labels: list[int]
) -> tuple[float, float]:
    if len(set(labels)) < 2 or len(set(probabilities)) < 2 or not probabilities:
        return (0.0, float(np.mean(labels)) if labels else 0.0)
    logits = np.array([_logit_scalar(min(1 - 1e-9, max(1e-9, p))) for p in probabilities])
    y = np.array(labels, dtype=float)
    slope, intercept = np.polyfit(logits, y, deg=1)
    return float(slope), float(intercept)


def reliability_bins(
    probabilities: list[float], labels: list[int], *, bins: int = 10
) -> list[dict[str, float]]:
    rows = []
    for low in np.linspace(0, 1, bins, endpoint=False):
        high = low + 1 / bins
        indices = [
            i
            for i, probability in enumerate(probabilities)
            if low <= probability < high or (high >= 1 and probability <= 1)
        ]
        rows.append(
            {
                "bin_low": float(low),
                "bin_high": float(high),
                "count": float(len(indices)),
                "mean_probability": float(np.mean([probabilities[i] for i in indices]))
                if indices
                else 0.0,
                "empirical_rate": float(np.mean([labels[i] for i in indices])) if indices else 0.0,
            }
        )
    return rows


def _fit_platt(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    iterations: int,
    learning_rate: float,
) -> dict[str, float]:
    features = _logit_array(np.clip(x, 1e-9, 1 - 1e-9))[:, None] if x.ndim == 1 else x
    weights = np.zeros(features.shape[1], dtype=float)
    bias = 0.0
    for _ in range(iterations):
        probs = 1.0 / (1.0 + np.exp(-np.clip(features @ weights + bias, -30, 30)))
        error = probs - y
        weights -= learning_rate * features.T @ error / max(1, len(y))
        bias -= learning_rate * float(np.mean(error))
    params = {chr(ord("a") + i): float(value) for i, value in enumerate(weights)}
    params["b"] = float(bias)
    return params


def _fit_temperature(probs: NDArray[np.float64], labels: NDArray[np.float64]) -> float:
    best = 1.0
    best_loss = float("inf")
    for temperature in np.linspace(0.5, 5.0, 30):
        calibrated = 1.0 / (
            1.0 + np.exp(-_logit_array(np.clip(probs, 1e-9, 1 - 1e-9)) / temperature)
        )
        loss = float(np.mean((calibrated - labels) ** 2))
        if loss < best_loss:
            best_loss = loss
            best = float(temperature)
    return best


def _fit_isotonic(probs: NDArray[np.float64], labels: NDArray[np.float64]) -> dict[str, Any]:
    order = np.argsort(probs)
    xs = probs[order]
    ys = labels[order].astype(float)
    for index in range(1, len(ys)):
        if ys[index] < ys[index - 1]:
            ys[index] = ys[index - 1]
    return {"x": [float(value) for value in xs], "y": [float(value) for value in ys]}


def _beta_features(probs: NDArray[np.float64]) -> NDArray[np.float64]:
    clipped = np.clip(probs, 1e-9, 1 - 1e-9)
    return np.column_stack([np.log(clipped), np.log1p(-clipped)])


def _labels_for_predictions(
    predictions: list[MonitorPrediction], examples: list[MonitorExample], target: str
) -> NDArray[np.float64]:
    by_id = {example.example_id: example for example in examples}
    labels = []
    for prediction in predictions:
        example = by_id[prediction.example_id]
        value = getattr(example, target)
        labels.append(1.0 if value == LabelValue.POSITIVE else 0.0)
    return np.array(labels, dtype=float)


def _logit_array(value: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.log(value / (1.0 - value))


def _logit_scalar(value: float) -> float:
    return float(np.log(value / (1.0 - value)))


def _sigmoid(value: float) -> float:
    return min(1.0, max(0.0, 1.0 / (1.0 + float(np.exp(-np.clip(value, -30, 30))))))
