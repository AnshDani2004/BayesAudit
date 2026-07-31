"""Structured model-output validation with bounded repair bookkeeping."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

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

