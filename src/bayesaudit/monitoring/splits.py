"""Grouped leakage-resistant split manifest generation."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.monitoring.dataset import load_monitor_examples
from bayesaudit.monitoring.types import SplitAssignment, SplitManifest, SplitName
from bayesaudit.storage.jsonl import write_json_atomic

SPLIT_STRATEGY_GROUPS: dict[str, str] = {
    "in_distribution": "base_task_id",
    "template_holdout": "template_family",
    "mutation_holdout": "mutation_profile_family",
    "domain_holdout": "domain",
    "architecture_holdout": "architecture",
    "model_holdout": "model_family",
}


def create_split_manifest(
    dataset_dir: Path,
    *,
    strategy: str = "in_distribution",
    confirmatory_fraction: float = 0.2,
    calibration_fraction: float = 0.2,
    development_fraction: float = 0.2,
) -> SplitManifest:
    examples = load_monitor_examples(dataset_dir)
    if strategy not in SPLIT_STRATEGY_GROUPS:
        raise ValueError(f"unknown split strategy: {strategy}")
    group_key = SPLIT_STRATEGY_GROUPS[strategy]
    group_values = sorted({example.split_group_ids[group_key] for example in examples})
    group_to_split = _assign_groups(
        group_values,
        confirmatory_fraction=confirmatory_fraction,
        calibration_fraction=calibration_fraction,
        development_fraction=development_fraction,
    )
    assignments = [
        SplitAssignment(
            example_id=example.example_id,
            split=group_to_split[example.split_group_ids[group_key]],
            group_key=group_key,
            group_value=example.split_group_ids[group_key],
            strategy=strategy,
        )
        for example in examples
    ]
    group_counts: dict[str, dict[str, int]] = defaultdict(dict)
    for split, count in Counter(assignment.split for assignment in assignments).items():
        group_counts["examples"][split] = count
    for split, count in Counter(group_to_split.values()).items():
        group_counts["groups"][split] = count
    payload = [assignment.model_dump(mode="json") for assignment in assignments]
    manifest_hash = canonical_json_hash(payload)
    manifest = SplitManifest(
        split_manifest_id=f"split_{strategy}_{manifest_hash[:12]}",
        dataset_id=dataset_dir.name,
        strategy=strategy,
        assignments=assignments,
        group_counts=dict(group_counts),
        manifest_hash=manifest_hash,
    )
    write_json_atomic(
        dataset_dir / f"split_{strategy}.json",
        manifest.model_dump(mode="json"),
    )
    return manifest


def validate_no_group_leakage(manifest: SplitManifest) -> dict[str, Any]:
    group_to_split: dict[tuple[str, str], str] = {}
    errors: list[str] = []
    for assignment in manifest.assignments:
        key = (assignment.group_key, assignment.group_value)
        previous = group_to_split.get(key)
        if previous is not None and previous != assignment.split:
            errors.append(f"group {key} appears in {previous} and {assignment.split}")
        group_to_split[key] = assignment.split
    return {"valid": not errors, "errors": errors, "group_count": len(group_to_split)}


def split_examples(dataset_dir: Path, manifest: SplitManifest) -> dict[str, list[str]]:
    examples_by_split: dict[str, list[str]] = defaultdict(list)
    for assignment in manifest.assignments:
        examples_by_split[assignment.split].append(assignment.example_id)
    return {key: sorted(value) for key, value in examples_by_split.items()}


def _assign_groups(
    groups: list[str],
    *,
    confirmatory_fraction: float,
    calibration_fraction: float,
    development_fraction: float,
) -> dict[str, str]:
    if not groups:
        return {}
    count = len(groups)
    confirmatory_n = max(1, int(round(count * confirmatory_fraction))) if count >= 4 else 1
    calibration_n = max(1, int(round(count * calibration_fraction))) if count >= 4 else 1
    development_n = max(1, int(round(count * development_fraction))) if count >= 4 else 1
    assignments: dict[str, str] = {}
    for index, group in enumerate(groups):
        if index < confirmatory_n:
            split = SplitName.CONFIRMATORY_TEST
        elif index < confirmatory_n + calibration_n:
            split = SplitName.CALIBRATION
        elif index < confirmatory_n + calibration_n + development_n:
            split = SplitName.DEVELOPMENT
        else:
            split = SplitName.TRAIN
        assignments[group] = split
    return assignments
