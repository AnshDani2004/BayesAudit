"""Phase 7 configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.types import PilotExperimentConfig, PilotProviderConfig


def load_pilot_provider_config(path: Path) -> PilotProviderConfig:
    payload = _read_yaml_mapping(path)
    provider_payload = payload.get("provider", payload)
    if not isinstance(provider_payload, dict):
        raise ValueError("provider config must contain a mapping")
    return PilotProviderConfig.model_validate(provider_payload)


def load_pilot_experiment_config(path: Path) -> PilotExperimentConfig:
    return PilotExperimentConfig.model_validate(_read_yaml_mapping(path))


def validate_provider_config(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    config: PilotProviderConfig | None = None
    try:
        config = load_pilot_provider_config(path)
    except Exception as exc:
        errors.append(str(exc))
    return {
        "valid": not errors,
        "errors": errors,
        "config_path": str(path),
        "provider_class": config.provider_class if config else None,
        "provider_name": config.provider_name if config else None,
        "model_identifier": config.model_identifier if config else None,
        "enabled": bool(config.enabled) if config else False,
        "credential_free_config": _credential_free(path),
    }


def config_hash(config: PilotExperimentConfig | PilotProviderConfig) -> str:
    return canonical_json_hash(config.model_dump(mode="json"))


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"YAML config must be a mapping: {path}")
    return payload


def _credential_free(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    forbidden = ["api_key:", "secret:", "token:", "password:", "sk-"]
    return not any(token in text.lower() for token in forbidden)

