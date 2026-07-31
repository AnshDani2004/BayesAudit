"""I/O helpers for benchmark task fixtures."""

from __future__ import annotations

from pathlib import Path

import yaml

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.schemas import BenchmarkTask


def load_task(path: Path) -> BenchmarkTask:
    """Load and validate one benchmark task YAML file."""

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"task fixture must be a mapping: {path}")
    payload = dict(payload)
    payload["scenario_hash"] = canonical_json_hash(
        {key: value for key, value in payload.items() if key != "scenario_hash"}
    )
    return BenchmarkTask.model_validate(payload)


def load_tasks(root: Path) -> list[BenchmarkTask]:
    """Load all benchmark task YAML files below a directory."""

    return [load_task(path) for path in sorted(root.rglob("*.yaml"))]
