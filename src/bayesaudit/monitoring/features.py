"""Leakage-resistant feature extraction from redacted observations."""

from __future__ import annotations

import re
from typing import Any

from bayesaudit.monitoring.types import FEATURE_SCHEMA_VERSION
from bayesaudit.oversight.types import OversightObservation

ALLOWED_OBSERVATION_FIELDS = {
    "architecture",
    "agent_role",
    "checkpoint",
    "current_budget_state",
    "current_constraint_envelope_verification_status",
    "current_constraint_snapshots",
    "current_messages",
    "current_step_kind",
    "depth",
    "observable_risk_features",
    "prior_architecture_events",
    "prior_policy_actions",
    "prior_public_audit_outcomes",
    "proposed_model_response",
    "proposed_tool_calls",
    "task_metadata_observable",
}

FORBIDDEN_FEATURE_TOKENS = {
    "ground_truth",
    "violations",
    "mutation_profile",
    "mutation_events",
    "scores",
    "counterfactual",
    "oracle",
    "raw_config",
    "script",
    "future_steps",
    "behavior_profile",
}

FEATURE_SCHEMA: dict[str, str] = {
    "depth": "numeric",
    "branch_present": "binary",
    "step_kind": "categorical",
    "agent_role": "categorical",
    "architecture": "categorical",
    "prior_audit_count": "numeric",
    "remaining_budget": "numeric",
    "constraint_count": "numeric",
    "critical_constraint_count": "numeric",
    "tool_call_count": "numeric",
    "missing_required_constraints": "binary",
    "weakened_constraints": "binary",
    "contradicted_constraints": "binary",
    "privilege_demotions": "binary",
    "verification_failures": "binary",
    "tool_requested": "binary",
    "approval_required": "binary",
    "approval_present": "binary",
    "prohibited_tool_indicator": "binary",
    "sensitive_token_indicator": "binary",
    "irreversible_action_indicator": "binary",
    "external_tool_indicator": "binary",
    "text_length": "numeric",
    "identifier_count": "numeric",
    "citation_count": "numeric",
    "unknown_citation_count": "numeric",
    "budget_numeric_count": "numeric",
    "approval_language_indicator": "binary",
    "constraint_reference_count": "numeric",
    "uncertainty_language_indicator": "binary",
}


def extract_features(
    observation: OversightObservation,
) -> dict[str, float | int | str | bool | None]:
    payload = observation.model_dump(mode="json")
    unexpected = set(payload).intersection(FORBIDDEN_FEATURE_TOKENS)
    if unexpected:
        raise ValueError(f"forbidden top-level feature keys: {sorted(unexpected)}")
    text = render_observation_text(observation)
    _assert_no_forbidden_tokens(text)
    snapshots = observation.current_constraint_snapshots
    tool_calls = observation.proposed_tool_calls
    risks = observation.observable_risk_features
    features: dict[str, float | int | str | bool | None] = {
        "depth": observation.depth,
        "branch_present": observation.branch_id is not None,
        "step_kind": observation.current_step_kind,
        "agent_role": observation.agent_role,
        "architecture": str(observation.architecture),
        "prior_audit_count": len(observation.prior_public_audit_outcomes),
        "remaining_budget": float(observation.current_budget_state.get("remaining_budget", 0.0)),
        "constraint_count": len(snapshots),
        "critical_constraint_count": sum(
            1 for snapshot in snapshots if snapshot.get("severity") == "critical"
        ),
        "tool_call_count": len(tool_calls),
        "missing_required_constraints": bool(risks.get("required_constraint_missing", False)),
        "weakened_constraints": bool(risks.get("constraint_weakened", False)),
        "contradicted_constraints": bool(risks.get("constraint_contradicted", False)),
        "privilege_demotions": bool(risks.get("privilege_demotion", False)),
        "verification_failures": bool(risks.get("envelope_verification_failure", False)),
        "tool_requested": bool(tool_calls),
        "approval_required": any(call.approval_required for call in tool_calls),
        "approval_present": any(call.approval_reference for call in tool_calls),
        "prohibited_tool_indicator": bool(risks.get("prohibited_tool_requested", False)),
        "sensitive_token_indicator": bool(
            risks.get("sensitive_token_in_visible_text", False)
            or risks.get("sensitive_token_in_tool_arguments", False)
        ),
        "irreversible_action_indicator": any(
            call.tool_name in {"file_write", "email", "outbound_contact", "purchase_api"}
            for call in tool_calls
        ),
        "external_tool_indicator": bool(risks.get("external_retrieval_proposed", False)),
        "text_length": len(text),
        "identifier_count": len(re.findall(r"\b[A-Z][A-Za-z0-9_]*\d*\b", text)),
        "citation_count": text.lower().count("citation:"),
        "unknown_citation_count": int(bool(risks.get("unknown_citation_identifier", False))),
        "budget_numeric_count": len(re.findall(r"\b\d+(?:\.\d+)?\b", text)),
        "approval_language_indicator": bool(re.search(r"\bapprov(?:ed|al)\b", text, re.I)),
        "constraint_reference_count": text.lower().count("constraint"),
        "uncertainty_language_indicator": bool(
            re.search(r"\b(maybe|uncertain|unknown|ambiguous|unsure)\b", text, re.I)
        ),
    }
    return features


def render_observation_text(observation: OversightObservation) -> str:
    parts: list[str] = []
    for message in observation.current_messages:
        parts.append(f"{message.role}: {message.content}")
    if observation.proposed_model_response is not None:
        response = observation.proposed_model_response
        parts.append(f"{response.role}: {response.content}")
    for call in observation.proposed_tool_calls:
        parts.append(f"tool_request: {call.tool_name} approval_required={call.approval_required}")
    text = "\n".join(parts)
    _assert_no_forbidden_tokens(text)
    return text


def validate_feature_payload(payload: dict[str, Any]) -> None:
    for key in payload:
        if key not in FEATURE_SCHEMA:
            raise ValueError(f"unexpected feature: {key}")
    _assert_no_forbidden_tokens(str(payload))


def _assert_no_forbidden_tokens(text: str) -> None:
    lowered = text.lower()
    leaked = [token for token in FORBIDDEN_FEATURE_TOKENS if token in lowered]
    if leaked:
        raise ValueError(f"forbidden feature token leaked: {sorted(leaked)}")


def feature_schema_record() -> dict[str, str]:
    return {"schema_version": FEATURE_SCHEMA_VERSION, **FEATURE_SCHEMA}
