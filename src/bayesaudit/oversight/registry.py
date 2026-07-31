"""Configuration loading and policy registry for Phase 4 oversight."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bayesaudit.oversight.policies import (
    FixedCheckpointBaseline,
    NoOversightBaseline,
    OracleEvaluationBaseline,
    RandomBaseline,
    RuleBasedBaseline,
)
from bayesaudit.oversight.policy_base import OversightPolicyConfig, Phase4Policy
from bayesaudit.oversight.types import WorkflowMode

_POLICY_TYPES: dict[str, type[Phase4Policy]] = {
    "no_oversight": NoOversightBaseline,
    "random": RandomBaseline,
    "fixed": FixedCheckpointBaseline,
    "fixed_checkpoints": FixedCheckpointBaseline,
    "rule_based": RuleBasedBaseline,
    "oracle": OracleEvaluationBaseline,
}

_CHECKPOINT_ALIASES: dict[str, str] = {
    "after_initial_planning": "after_planning",
    "before_tool_execution": "before_tool_request",
    "before_final_response": "before_final_output",
}


def policy_for_config(config: OversightPolicyConfig, *, evaluation: bool = False) -> Phase4Policy:
    policy_type = config.policy_type
    if policy_type == "oracle" and not evaluation:
        raise ValueError("oracle policy is evaluation-only and requires evaluation=True")
    if policy_type not in _POLICY_TYPES:
        raise ValueError(f"unknown oversight policy type: {policy_type}")
    return _POLICY_TYPES[policy_type](config)


def coerce_policy_config(
    payload: dict[str, Any],
    *,
    default_mode: str = WorkflowMode.SHADOW,
    default_budget: float = 0.0,
) -> OversightPolicyConfig:
    policy_type = str(payload.get("policy_type", payload.get("type", payload.get("name", ""))))
    name = str(payload.get("name", policy_type))
    parameters = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "name",
            "policy_type",
            "type",
            "budget",
            "mode",
            "seed",
            "enabled",
            "evaluation_only",
            "parameters",
        }
    }
    explicit_parameters = payload.get("parameters", {})
    if isinstance(explicit_parameters, dict):
        parameters.update(explicit_parameters)
    if "expected_audit_fraction" in parameters and "audit_fraction" not in parameters:
        parameters["audit_fraction"] = parameters["expected_audit_fraction"]
    if "checkpoints" in parameters and "checkpoint_types" not in parameters:
        parameters["checkpoint_types"] = [
            _CHECKPOINT_ALIASES.get(str(value), str(value)) for value in parameters["checkpoints"]
        ]
    return OversightPolicyConfig(
        name=name,
        policy_type=policy_type,
        budget=float(payload.get("budget", default_budget)),
        mode=str(payload.get("mode", default_mode)),
        seed=int(payload.get("seed", 0)),
        enabled=bool(payload.get("enabled", True)),
        evaluation_only=bool(payload.get("evaluation_only", policy_type == "oracle")),
        parameters=parameters,
    )


def load_policy_configs(
    root: Path,
    *,
    default_mode: str = WorkflowMode.SHADOW,
    default_budget: float = 0.0,
) -> list[OversightPolicyConfig]:
    configs: list[OversightPolicyConfig] = []
    files = [root] if root.is_file() else sorted(root.rglob("*.yaml"))
    for path in files:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
        if not isinstance(payload, dict):
            continue
        rows = payload.get("policies")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    configs.append(
                        coerce_policy_config(
                            row, default_mode=default_mode, default_budget=default_budget
                        )
                    )
        elif "policy_type" in payload or "type" in payload:
            configs.append(
                coerce_policy_config(
                    payload, default_mode=default_mode, default_budget=default_budget
                )
            )
    return [config for config in configs if config.enabled]
