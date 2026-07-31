"""Configuration loading and validation for Phase 6 attackers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bayesaudit.attackers.lifecycle import Phase6ExperimentConfig, default_attack_objective
from bayesaudit.attackers.models import ATTACKER_CLASSES
from bayesaudit.attackers.primitives import validate_primitives
from bayesaudit.attackers.types import AttackerConfig
from bayesaudit.oversight.policy_base import OversightPolicyConfig


def load_attacker_config(path: Path) -> AttackerConfig:
    payload = _read_yaml(path)
    if "objective" not in payload:
        payload["objective"] = default_attack_objective().model_dump(mode="json")
    return AttackerConfig.model_validate(payload)


def load_attacker_configs(root: Path) -> list[AttackerConfig]:
    paths = [root] if root.is_file() else sorted(root.glob("*/*.yaml"))
    return [load_attacker_config(path) for path in paths]


def validate_attackers(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    configs = load_attacker_configs(root)
    seen: set[str] = set()
    for config in configs:
        if config.name in seen:
            errors.append(f"duplicate attacker name: {config.name}")
        seen.add(config.name)
        if config.attacker_type not in ATTACKER_CLASSES:
            errors.append(f"{config.name}: unknown attacker type {config.attacker_type}")
        if config.attacker_type == "oracle" and not config.evaluation_only:
            errors.append(f"{config.name}: oracle attacker must be evaluation_only")
        if not config.objective.allowed_attack_methods:
            errors.append(f"{config.name}: objective must declare allowed attack methods")
    return {"valid": not errors, "errors": errors, "attacker_count": len(configs)}


def validate_attacks() -> dict[str, Any]:
    return validate_primitives()


def load_phase6_experiment_config(path: Path) -> Phase6ExperimentConfig:
    payload = _read_yaml(path)
    attackers = [
        _coerce_attacker(raw)
        for raw in payload.get("attackers", [])
    ]
    defenders = [
        _coerce_defender(raw)
        for raw in payload.get("defenders", [])
    ]
    payload["attackers"] = attackers
    payload["defenders"] = defenders
    return Phase6ExperimentConfig.model_validate(payload)


def _coerce_attacker(raw: object) -> dict[str, Any]:
    if isinstance(raw, str):
        config = load_attacker_config(Path(raw))
        return config.model_dump(mode="json")
    if not isinstance(raw, dict):
        raise ValueError(f"invalid attacker config: {raw!r}")
    payload = dict(raw)
    if "objective" not in payload:
        payload["objective"] = default_attack_objective(
            payload.get("allowed_attack_methods")
            if isinstance(payload.get("allowed_attack_methods"), list)
            else None
        ).model_dump(mode="json")
    return AttackerConfig.model_validate(payload).model_dump(mode="json")


def _coerce_defender(raw: object) -> OversightPolicyConfig:
    if not isinstance(raw, dict):
        raise ValueError(f"invalid defender config: {raw!r}")
    return OversightPolicyConfig(
        name=str(raw["name"]),
        policy_type=str(raw["policy_type"]),
        budget=float(raw.get("budget", 0.0)),
        mode=str(raw.get("mode", "shadow")),
        seed=int(raw.get("seed", 0)),
        evaluation_only=bool(raw.get("evaluation_only", False)),
        parameters=dict(raw.get("parameters", {})),
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"YAML config must be a mapping: {path}")
    return payload
