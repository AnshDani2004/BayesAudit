"""Structured model-output validation with bounded repair bookkeeping."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field, ValidationError

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.prompts import repair_prompt
from bayesaudit.pilot.types import StructuredOutputRecord
from bayesaudit.schemas import StrictModel


class PilotStructuredResponse(StrictModel):
    agent_role: str
    proposed_subtask: str | None = None
    constraint_acknowledgments: list[str] = Field(default_factory=list)
    delegated_constraints: list[str] = Field(default_factory=list)
    tool_requests: list[dict[str, Any]] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    selected_actions: list[str] = Field(default_factory=list)
    cost_estimates: dict[str, float] = Field(default_factory=dict)
    final_answer: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    escalation_request: str | None = None


StageBRole = Literal["planner", "worker", "aggregator"]
STAGE_B1_SCHEMA_VERSION = "phase7_stage_b1_role_schema_v1"


class StageB1PlannerResponse(StrictModel):
    role: Literal["planner"]
    subtask: str
    objective: str
    relevant_constraints: list[str]
    worker_instructions: str
    expected_output: str
    tool_requests: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: str | None
    escalation_request: str | None


class StageB1WorkerResponse(StrictModel):
    role: Literal["worker"]
    subtask_understood: str
    constraint_acknowledgments: list[str]
    result: str
    supporting_details: list[str]
    tool_requests: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: str | None
    escalation_request: str | None


class StageB1AggregatorResponse(StrictModel):
    role: Literal["aggregator"]
    child_result_used: bool
    constraint_acknowledgments: list[str]
    final_answer: str
    evidence_references: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: str | None
    escalation_request: str | None


ROLE_SCHEMAS: dict[StageBRole, type[StrictModel]] = {
    "planner": StageB1PlannerResponse,
    "worker": StageB1WorkerResponse,
    "aggregator": StageB1AggregatorResponse,
}


def stage_b1_schema_name(role: StageBRole) -> str:
    return f"bayesaudit_stage_b1_{role}"


def stage_b1_json_schema(role: StageBRole) -> dict[str, Any]:
    schema = ROLE_SCHEMAS[role].model_json_schema()
    schema.pop("title", None)
    return schema


def stage_b1_schema_hash(role: StageBRole) -> str:
    return canonical_json_hash(
        {
            "name": stage_b1_schema_name(role),
            "version": STAGE_B1_SCHEMA_VERSION,
            "schema": stage_b1_json_schema(role),
        }
    )


def stage_b1_response_schema_metadata(role: StageBRole) -> dict[str, Any]:
    return {
        "name": stage_b1_schema_name(role),
        "version": STAGE_B1_SCHEMA_VERSION,
        "schema_hash": stage_b1_schema_hash(role),
        "schema": stage_b1_json_schema(role),
        "strict": True,
    }


def parse_structured_output(raw_output: str, *, repair_limit: int = 1) -> StructuredOutputRecord:
    errors: list[str] = []
    repair_hashes: list[str] = []
    parsed: dict[str, Any] = {}
    valid = False
    try:
        payload = json.loads(raw_output)
        if not isinstance(payload, dict):
            raise ValueError("structured output must be a JSON object")
        response = PilotStructuredResponse.model_validate(payload)
        parsed = response.model_dump(mode="json")
        valid = True
    except Exception as exc:
        errors.append(str(exc))
        if repair_limit > 0:
            repair_hashes.append(repair_prompt(raw_output, errors).prompt_hash)
    return StructuredOutputRecord(
        output_id="structured_" + canonical_json_hash({"raw": raw_output, "errors": errors})[:20],
        raw_output=raw_output,
        parsed_output=parsed,
        parse_errors=errors,
        repair_attempts=len(repair_hashes),
        repair_prompt_hashes=repair_hashes,
        repair_cost=0.0,
        valid=valid,
    )


def parse_stage_b1_role_output(
    raw_output: str,
    *,
    role: StageBRole,
    response_status: str | None = None,
    refusal_count: int = 0,
    incomplete_reason: str | None = None,
) -> StructuredOutputRecord:
    schema_name = stage_b1_schema_name(role)
    schema_hash = stage_b1_schema_hash(role)
    native_payload, native_json_error, native_taxonomy = _parse_json_exact(raw_output)
    parse_errors: list[str] = []
    taxonomy = list(native_taxonomy)
    parsed: dict[str, Any] = {}
    native_schema_valid = False
    normalized_schema_valid = False
    normalizations: list[str] = []
    status = "unknown"
    if response_status and response_status.startswith("incomplete"):
        taxonomy.append("provider_output_incomplete")
        status = "incomplete"
    if incomplete_reason:
        taxonomy.append("provider_output_incomplete")
        status = "incomplete"
    if refusal_count:
        taxonomy.append("refusal")
        status = "refusal"
    if not raw_output.strip():
        taxonomy.append("provider_output_empty")
        status = "empty"
    provider_status_locked = status in {"incomplete", "refusal", "empty"}
    if native_payload is not None:
        parsed, parse_errors, native_schema_valid = _validate_role_payload(native_payload, role)
        if native_schema_valid:
            if not provider_status_locked:
                status = "native_valid"
        else:
            taxonomy.extend(_schema_error_taxonomy(parse_errors))
            if not provider_status_locked:
                status = "schema_invalid"
    elif status == "unknown":
        parse_errors.append(native_json_error or "invalid JSON")
        status = "invalid_json"
        normalized = _normalize_single_json_fence(raw_output)
        if normalized is not None:
            normalizations.append("removed_single_markdown_json_fence")
            payload, error, norm_taxonomy = _parse_json_exact(normalized)
            taxonomy.extend(item for item in norm_taxonomy if item not in taxonomy)
            if payload is not None:
                parsed, parse_errors, normalized_schema_valid = _validate_role_payload(
                    payload, role
                )
                if normalized_schema_valid:
                    status = "normalized_valid"
                else:
                    parse_errors = parse_errors or [error or "schema validation failed"]
                    taxonomy.extend(_schema_error_taxonomy(parse_errors))
                    status = "schema_invalid"
    taxonomy = sorted(set(taxonomy or (["unknown"] if not native_schema_valid else [])))
    return StructuredOutputRecord(
        output_id="structured_" + canonical_json_hash({"raw": raw_output, "role": role})[:20],
        raw_output=raw_output,
        parsed_output=parsed if native_schema_valid or normalized_schema_valid else {},
        parse_errors=parse_errors,
        repair_attempts=0,
        repair_prompt_hashes=[],
        repair_cost=0.0,
        valid=native_schema_valid or normalized_schema_valid,
        agent_role=role,
        schema_name=schema_name,
        role_schema_version=STAGE_B1_SCHEMA_VERSION,
        schema_hash=schema_hash,
        native_json_valid=native_payload is not None,
        native_schema_valid=native_schema_valid,
        normalized_schema_valid=normalized_schema_valid,
        structured_output_status=status,
        normalization_applied=normalizations,
        failure_taxonomy=taxonomy,
        native_json_payload=native_payload or {},
    )


def _parse_json_exact(raw_output: str) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    stripped = raw_output.strip()
    if not stripped:
        return None, "empty output", ["provider_output_empty"]
    if stripped.startswith("```"):
        return None, "markdown fenced JSON is not native JSON", ["markdown_fenced_json"]
    decoder = json.JSONDecoder()
    try:
        payload, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError as exc:
        taxonomy = ["invalid_json_syntax"]
        if "Unterminated" in exc.msg or exc.pos >= max(len(stripped) - 2, 0):
            taxonomy.append("truncated_json")
        if stripped and not stripped.startswith(("{", "[")):
            taxonomy.append("prose_before_json")
        return None, str(exc), taxonomy
    remainder = stripped[end:].strip()
    if remainder:
        if remainder.startswith("{"):
            return None, "multiple JSON objects", ["multiple_json_objects"]
        return None, "prose after JSON object", ["prose_after_json"]
    if not isinstance(payload, dict):
        return None, "structured output must be a JSON object", ["unsupported_response_shape"]
    return payload, None, []


def _normalize_single_json_fence(raw_output: str) -> str | None:
    stripped = raw_output.strip()
    if not stripped.startswith("```"):
        return None
    lines = stripped.splitlines()
    if len(lines) < 3:
        return None
    first = lines[0].strip().lower()
    if first not in {"```", "```json"}:
        return None
    if lines[-1].strip() != "```":
        return None
    return "\n".join(lines[1:-1]).strip()


def _validate_role_payload(
    payload: dict[str, Any], role: StageBRole
) -> tuple[dict[str, Any], list[str], bool]:
    try:
        parsed = ROLE_SCHEMAS[role].model_validate(payload)
    except ValidationError as exc:
        return {}, [str(exc)], False
    return parsed.model_dump(mode="json"), [], True


def _schema_error_taxonomy(errors: list[str]) -> list[str]:
    joined = "\n".join(errors)
    taxonomy: list[str] = []
    if "Field required" in joined or "missing" in joined.lower():
        taxonomy.append("missing_required_field")
    if "Extra inputs are not permitted" in joined:
        taxonomy.append("unexpected_field")
    if "literal_error" in joined:
        taxonomy.extend(["enum_mismatch", "role_schema_mismatch"])
    if "Input should be a valid" in joined or "type=" in joined:
        taxonomy.append("wrong_field_type")
    if "None" in joined or "none_required" in joined:
        taxonomy.append("null_not_allowed")
    if "list_type" in joined or "dict_type" in joined:
        taxonomy.append("nested_shape_mismatch")
    return taxonomy or ["schema_bug"]
