"""Interpretable learned monitor baselines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.monitoring.dataset import load_monitor_examples
from bayesaudit.monitoring.types import (
    LabelValue,
    MonitorArtifact,
    MonitorExample,
    MonitorPrediction,
    SplitManifest,
)
from bayesaudit.schemas import StrictModel
from bayesaudit.storage.jsonl import read_json, write_json_atomic


class MonitorTrainConfig(StrictModel):
    monitor_name: str
    monitor_type: str = "logistic"
    dataset_dir: Path
    split_manifest_path: Path | None = None
    artifact_dir: Path = Path("results/tables/monitors")
    target: str = "current_violation_label"
    seed: int = 1
    class_weight: float = 1.0
    learning_rate: float = 0.1
    iterations: int = 200
    max_depth: int = 2
    feature_names: list[str] = Field(default_factory=list)


def load_monitor_train_config(path: Path) -> MonitorTrainConfig:
    import yaml

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"monitor train config must be a mapping: {path}")
    return MonitorTrainConfig.model_validate(payload)


def train_monitor(config: MonitorTrainConfig) -> MonitorArtifact:
    examples = load_monitor_examples(config.dataset_dir)
    train_ids = _train_ids(config.split_manifest_path)
    train_examples = [
        example for example in examples if not train_ids or example.example_id in train_ids
    ]
    labeled_examples = [
        example
        for example in train_examples
        if getattr(example, config.target) != LabelValue.UNKNOWN
    ]
    train_examples = labeled_examples or train_examples
    feature_names = config.feature_names or _numeric_feature_names(train_examples)
    x = _feature_matrix(train_examples, feature_names)
    y = _labels(train_examples, config.target)
    parameters: dict[str, Any]
    if config.monitor_type == "constant":
        parameters = {"prevalence": float(np.mean(y)) if len(y) else 0.0}
    elif config.monitor_type == "rule_score":
        parameters = {"scale": 1.0, "bias": 0.0}
    elif config.monitor_type == "tree":
        parameters = _fit_tree_stumps(x, y, feature_names, max_depth=config.max_depth)
    elif config.monitor_type == "bayesian_logistic":
        parameters = _fit_logistic(
            x,
            y,
            learning_rate=config.learning_rate,
            iterations=config.iterations,
            class_weight=config.class_weight,
        )
        parameters["posterior_variance"] = _posterior_variance(x, y, parameters)
        parameters["prior"] = "normal(0, 2.5)"
    elif config.monitor_type == "logistic":
        parameters = _fit_logistic(
            x,
            y,
            learning_rate=config.learning_rate,
            iterations=config.iterations,
            class_weight=config.class_weight,
        )
    else:
        raise ValueError(f"unknown monitor type: {config.monitor_type}")
    artifact_hash = canonical_json_hash(
        {
            "config": config.model_dump(mode="json"),
            "feature_names": feature_names,
            "parameters": parameters,
        }
    )
    artifact = MonitorArtifact(
        monitor_name=config.monitor_name,
        monitor_version="phase5_v1",
        monitor_type=config.monitor_type,
        target=config.target,
        feature_names=feature_names,
        artifact_hash=artifact_hash,
        training_dataset_hash=canonical_json_hash(
            [example.example_id for example in train_examples]
        ),
        split_manifest_hash=_split_hash(config.split_manifest_path),
        hyperparameters={
            "learning_rate": config.learning_rate,
            "iterations": config.iterations,
            "class_weight": config.class_weight,
        },
        parameters=parameters,
    )
    config.artifact_dir.mkdir(parents=True, exist_ok=True)
    path = config.artifact_dir / f"{config.monitor_name}.json"
    artifact.artifact_path = str(path)
    write_json_atomic(path, artifact.model_dump(mode="json"))
    return artifact


def load_monitor_artifact(path: Path) -> MonitorArtifact:
    return MonitorArtifact.model_validate(read_json(path))


def predict_examples(
    artifact: MonitorArtifact, examples: list[MonitorExample]
) -> list[MonitorPrediction]:
    predictions: list[MonitorPrediction] = []
    for example in examples:
        probability = _predict_probability(artifact, example)
        predictions.append(
            MonitorPrediction(
                prediction_id="pred_"
                + canonical_json_hash(
                    {
                        "artifact": artifact.artifact_hash,
                        "example": example.example_id,
                    }
                )[:20],
                monitor_name=artifact.monitor_name,
                monitor_version=artifact.monitor_version,
                model_artifact_hash=artifact.artifact_hash,
                example_id=example.example_id,
                current_violation_probability=probability,
                imminent_violation_probability=probability,
                preventable_violation_probability=probability
                if example.preventable_imminent_violation_label != LabelValue.UNKNOWN
                else 0.0,
                expected_severity=float(example.severity_target or 0.0) * probability,
                intervention_usefulness_probability=probability
                if example.intervention_usefulness_label != LabelValue.UNKNOWN
                else 0.0,
                predicted_violation_categories=_predicted_categories(example),
                explanation=f"{artifact.monitor_type} monitor probability",
            )
        )
    return predictions


def _predict_probability(artifact: MonitorArtifact, example: MonitorExample) -> float:
    if artifact.monitor_type == "constant":
        return _clip(float(artifact.parameters.get("prevalence", 0.0)))
    if artifact.monitor_type == "rule_score":
        score = _rule_score(example)
        scale = float(artifact.parameters.get("scale", 1.0))
        bias = float(artifact.parameters.get("bias", 0.0))
        return _sigmoid(scale * score + bias)
    if artifact.monitor_type == "tree":
        return _predict_tree(artifact, example)
    weights = artifact.parameters.get("weights", [])
    bias = float(artifact.parameters.get("bias", 0.0))
    if not isinstance(weights, list):
        return 0.0
    value = bias + sum(
        float(weight) * float(example.observable_feature_payload.get(name, 0.0) or 0.0)
        for weight, name in zip(weights, artifact.feature_names, strict=False)
    )
    return _sigmoid(value)


def _fit_logistic(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    learning_rate: float,
    iterations: int,
    class_weight: float,
) -> dict[str, Any]:
    if x.size == 0:
        return {"weights": [], "bias": 0.0}
    weights = np.zeros(x.shape[1], dtype=float)
    bias = 0.0
    for _ in range(iterations):
        logits = x @ weights + bias
        probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
        sample_weights = np.where(y > 0.5, class_weight, 1.0)
        error = (probs - y) * sample_weights
        weights -= learning_rate * (x.T @ error / max(1, len(y)) + 0.01 * weights)
        bias -= learning_rate * float(np.mean(error))
    return {"weights": [float(value) for value in weights], "bias": float(bias)}


def _posterior_variance(
    x: NDArray[np.float64], y: NDArray[np.float64], parameters: dict[str, Any]
) -> list[float]:
    if x.size == 0:
        return []
    weights = np.array(parameters["weights"], dtype=float)
    logits = x @ weights + float(parameters["bias"])
    probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
    fisher_diag = np.sum((probs * (1.0 - probs))[:, None] * x * x, axis=0) + 1.0
    return [float(1.0 / value) for value in fisher_diag]


def _fit_tree_stumps(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    feature_names: list[str],
    *,
    max_depth: int,
) -> dict[str, Any]:
    if x.size == 0:
        return {"base_rate": 0.0, "stumps": []}
    residual = y.copy()
    stumps: list[dict[str, Any]] = []
    for _ in range(max_depth):
        best_feature = 0
        best_score = -1.0
        best_threshold = 0.0
        for index in range(x.shape[1]):
            threshold = float(np.median(x[:, index]))
            left = residual[x[:, index] <= threshold]
            right = residual[x[:, index] > threshold]
            score = (
                abs(float(np.mean(left)) - float(np.mean(right)))
                if len(left) and len(right)
                else 0.0
            )
            if score > best_score:
                best_score = score
                best_feature = index
                best_threshold = threshold
        stumps.append(
            {
                "feature": feature_names[best_feature],
                "threshold": best_threshold,
                "left_rate": float(np.mean(y[x[:, best_feature] <= best_threshold])),
                "right_rate": float(np.mean(y[x[:, best_feature] > best_threshold]))
                if np.any(x[:, best_feature] > best_threshold)
                else float(np.mean(y)),
            }
        )
    return {"base_rate": float(np.mean(y)), "stumps": stumps}


def _predict_tree(artifact: MonitorArtifact, example: MonitorExample) -> float:
    stumps = artifact.parameters.get("stumps", [])
    if not isinstance(stumps, list) or not stumps:
        return _clip(float(artifact.parameters.get("base_rate", 0.0)))
    estimates = []
    for stump in stumps:
        if not isinstance(stump, dict):
            continue
        value = float(example.observable_feature_payload.get(str(stump["feature"]), 0.0) or 0.0)
        estimates.append(
            float(stump["right_rate"])
            if value > float(stump["threshold"])
            else float(stump["left_rate"])
        )
    return _clip(float(np.mean(estimates))) if estimates else 0.0


def _feature_matrix(
    examples: list[MonitorExample], feature_names: list[str]
) -> NDArray[np.float64]:
    rows = [
        [float(example.observable_feature_payload.get(name, 0.0) or 0.0) for name in feature_names]
        for example in examples
    ]
    return np.array(rows, dtype=float)


def _labels(examples: list[MonitorExample], target: str) -> NDArray[np.float64]:
    return np.array(
        [
            1.0 if getattr(example, target) == LabelValue.POSITIVE else 0.0
            for example in examples
            if getattr(example, target) != LabelValue.UNKNOWN
        ],
        dtype=float,
    )


def _numeric_feature_names(examples: list[MonitorExample]) -> list[str]:
    if not examples:
        return []
    first = examples[0].observable_feature_payload
    names = []
    for key, value in first.items():
        if isinstance(value, bool | int | float):
            names.append(key)
    return names


def _rule_score(example: MonitorExample) -> float:
    values = example.observable_feature_payload
    return float(
        sum(
            bool(values.get(name, False))
            for name in (
                "missing_required_constraints",
                "weakened_constraints",
                "contradicted_constraints",
                "privilege_demotions",
                "verification_failures",
                "prohibited_tool_indicator",
                "sensitive_token_indicator",
                "unknown_citation_count",
            )
        )
    )


def _predicted_categories(example: MonitorExample) -> list[str]:
    features = example.observable_feature_payload
    categories = []
    if features.get("sensitive_token_indicator"):
        categories.append("privacy")
    if features.get("prohibited_tool_indicator"):
        categories.append("authorization")
    if features.get("missing_required_constraints") or features.get("weakened_constraints"):
        categories.append("constraint_inheritance")
    return sorted(set(categories))


def _sigmoid(value: float) -> float:
    return _clip(1.0 / (1.0 + float(np.exp(-np.clip(value, -30, 30)))))


def _clip(value: float) -> float:
    return min(1.0, max(0.0, value))


def _train_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    manifest = SplitManifest.model_validate(read_json(path))
    return {
        assignment.example_id
        for assignment in manifest.assignments
        if assignment.split == "train"
    }


def _split_hash(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return SplitManifest.model_validate(read_json(path)).manifest_hash
