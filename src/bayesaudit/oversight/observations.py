"""Redacted oversight observation builder."""

from __future__ import annotations

from typing import Any

from bayesaudit.oversight.budget import BudgetLedger
from bayesaudit.oversight.types import (
    OversightCheckpoint,
    OversightObservation,
    RedactedToolCall,
    WorkflowMode,
)
from bayesaudit.schemas import BenchmarkTask, Trajectory

FORBIDDEN_OBSERVATION_KEYS = {
    "violations",
    "mutation_events",
    "mutation_event_ids",
    "scores",
    "ground_truth",
    "script",
    "raw_config",
    "future_steps",
    "oracle",
}


def build_observation(
    *,
    task: BenchmarkTask,
    trajectory: Trajectory,
    checkpoint: OversightCheckpoint,
    budget: BudgetLedger,
    mode: str = WorkflowMode.SHADOW,
    prior_public_audit_outcomes: list[dict[str, Any]] | None = None,
    prior_policy_actions: list[dict[str, Any]] | None = None,
) -> OversightObservation:
    step = next(step for step in trajectory.steps if step.step_id == checkpoint.step_id)
    messages = list(step.input_messages)
    proposed = step.model_response.message if step.model_response is not None else None
    features = observable_risk_features(task, step.model_dump(mode="json"))
    prior_architecture_events = _public_architecture_events(trajectory, step.sequence_index)
    observation = OversightObservation(
        observation_id=f"{trajectory.run_id}_{checkpoint.checkpoint_id}_obs",
        trajectory_id=trajectory.trajectory_id,
        task_id=trajectory.task_id,
        current_step_id=step.step_id,
        sequence_index=step.sequence_index,
        architecture=trajectory.architecture,
        workflow_mode=mode,
        agent_id=step.agent_id,
        agent_role=step.role,
        depth=step.depth,
        branch_id=step.branch_id,
        delegation_id=step.delegation_id,
        current_step_kind=str(step.kind),
        checkpoint=checkpoint,
        current_messages=messages,
        proposed_model_response=proposed,
        proposed_tool_calls=[RedactedToolCall.from_tool_call(call) for call in step.tool_calls],
        current_constraint_snapshots=[
            _redact_snapshot(snapshot.model_dump(mode="json"))
            for snapshot in step.constraint_snapshots
        ],
        current_constraint_envelope_verification_status=_verification_status(step.metadata),
        prior_architecture_events=prior_architecture_events,
        prior_public_audit_outcomes=prior_public_audit_outcomes or [],
        prior_policy_actions=prior_policy_actions or [],
        current_budget_state=budget.state.model_dump(mode="json"),
        task_metadata_observable={
            "domain": task.domain,
            "difficulty": task.difficulty,
            "authorized_tools": task.authorized_tools,
            "prohibited_tools": task.prohibited_tools,
            "expected_escalation_points": task.expected_escalation_points,
        },
        observable_risk_features=features,
    )
    _assert_redacted(observation.model_dump(mode="json"))
    return observation


def observable_risk_features(task: BenchmarkTask, step_payload: dict[str, Any]) -> dict[str, Any]:
    text = _visible_text(step_payload).lower()
    snapshots = step_payload.get("constraint_snapshots", [])
    tools = step_payload.get("tool_calls", [])
    sensitive_tokens = _sensitive_tokens(task)
    prohibited_fields = [
        str(field).lower() for field in task.scoring.criteria.get("prohibited_fields", [])
    ]
    source_ids = {
        str(material.get("doc_id"))
        for material in task.source_materials
        if material.get("doc_id") is not None
    }
    citations = [
        token.split("citation:", 1)[1].strip(" .,;")
        for token in text.split()
        if token.startswith("citation:")
    ]
    selected_actions = "selected actions:" in text
    actions = _selected_actions_from_visible_text(text)
    return {
        "required_constraint_missing": any(
            snapshot.get("retention_status") == "dropped" for snapshot in snapshots
        ),
        "constraint_weakened": any(
            snapshot.get("retention_status") == "weakened" for snapshot in snapshots
        ),
        "constraint_contradicted": any(
            snapshot.get("retention_status") == "contradicted" for snapshot in snapshots
        ),
        "privilege_demotion": any(
            snapshot.get("current_source_level", 0) > snapshot.get("original_source_level", 0)
            for snapshot in snapshots
        ),
        "envelope_verification_failure": bool(
            step_payload.get("metadata", {}).get("branch_refused")
        ),
        "prohibited_tool_requested": any(
            call.get("tool_name") in task.prohibited_tools for call in tools
        ),
        "approval_missing": any(
            call.get("approval_required") and not call.get("approval_reference") for call in tools
        ),
        "sensitive_token_in_visible_text": any(token in text for token in sensitive_tokens),
        "sensitive_token_in_tool_arguments": any(
            token in str(call.get("arguments", "")).lower()
            for call in tools
            for token in sensitive_tokens
        ),
        "unknown_citation_identifier": any(citation not in source_ids for citation in citations),
        "external_retrieval_proposed": any(
            call.get("tool_name") in {"external_search", "web_browser"} for call in tools
        ),
        "prohibited_field_named": any(field in text for field in prohibited_fields),
        "duplicate_action_selection": selected_actions and len(actions) != len(set(actions)),
        "combined_branch_cost_exceeds_budget": _combined_cost_exceeds_budget(task, actions),
    }


def _sensitive_tokens(task: BenchmarkTask) -> list[str]:
    tokens = [str(token).lower() for token in task.scoring.criteria.get("sensitive_tokens", [])]
    for material in task.source_materials:
        rows = material.get("rows", [])
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    for key in ("name", "email", "account_id", "customer_id", "record_id"):
                        if key in row:
                            tokens.append(str(row[key]).lower())
    return sorted(set(tokens), key=len, reverse=True)


def _visible_text(step_payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for message in step_payload.get("input_messages", []):
        if isinstance(message, dict):
            parts.append(str(message.get("content", "")))
    response = step_payload.get("model_response")
    if isinstance(response, dict):
        message = response.get("message")
        if isinstance(message, dict):
            parts.append(str(message.get("content", "")))
    return "\n".join(parts)


def _selected_actions_from_visible_text(text: str) -> list[str]:
    marker = "selected actions:"
    for line in text.splitlines():
        lowered = line.lower()
        if marker in lowered:
            raw = line[lowered.index(marker) + len(marker) :]
            return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def _combined_cost_exceeds_budget(task: BenchmarkTask, actions: list[str]) -> bool:
    if not actions:
        return False
    max_total = task.scoring.criteria.get("max_total_cost")
    if max_total is None:
        return False
    rows: dict[str, float] = {}
    for material in task.source_materials:
        for row in material.get("rows", []):
            if isinstance(row, dict) and "action" in row and "cost" in row:
                rows[str(row["action"])] = float(row["cost"])
    return sum(rows.get(action, 0.0) for action in actions) > float(max_total)


def _redact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        key: snapshot[key]
        for key in (
            "constraint_id",
            "visible_rule",
            "category",
            "severity",
            "original_source_level",
            "current_source_level",
            "retention_status",
            "verification_status",
        )
        if key in snapshot
    }


def _verification_status(metadata: dict[str, Any]) -> str | None:
    if metadata.get("branch_refused"):
        return "failed"
    if metadata.get("verification_event_id"):
        return "checked"
    return None


def _public_architecture_events(
    trajectory: Trajectory, sequence_index: int
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for step in trajectory.steps:
        if step.sequence_index >= sequence_index:
            continue
        if step.metadata.get("branch_refused"):
            events.append(
                {
                    "step_id": step.step_id,
                    "event_type": "branch_refusal",
                    "branch_id": step.branch_id,
                }
            )
    return events


def _assert_redacted(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in FORBIDDEN_OBSERVATION_KEYS:
                raise ValueError(f"forbidden observation key leaked: {key}")
            _assert_redacted(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_redacted(value)
