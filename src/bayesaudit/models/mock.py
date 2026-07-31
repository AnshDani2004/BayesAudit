"""Deterministic scripted mock model for offline tests and Phase 2 runs."""

from __future__ import annotations

import random
from typing import Any

from pydantic import Field

from bayesaudit.schemas import MessageRecord, ModelResponse, StrictModel


class MockToolRequest(StrictModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_reference: str | None = None


class MockScript(StrictModel):
    profile: str = "compliant"
    final_answer: str | None = None
    incorrect_answer: str | None = None
    internal_leak_tokens: list[str] = Field(default_factory=list)
    final_leak_tokens: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    selected_actions: list[str] = Field(default_factory=list)
    protected_field_mentions: list[str] = Field(default_factory=list)
    tool_requests: list[MockToolRequest] = Field(default_factory=list)
    fail_at_call: int | None = None
    drop_constraint_ids: list[str] = Field(default_factory=list)
    weaken_constraint_ids: list[str] = Field(default_factory=list)


class MockModel:
    """A provider-neutral model double controlled by explicit typed script data."""

    def __init__(
        self, script: MockScript | None = None, *, model_id: str = "mock-deterministic-v1"
    ) -> None:
        self.script = script or MockScript()
        self._model_id = model_id
        self._call_count = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    async def complete(
        self,
        messages: list[MessageRecord],
        *,
        seed: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ModelResponse:
        self._call_count += 1
        if self.script.fail_at_call == self._call_count:
            raise RuntimeError(f"mock failure at call {self._call_count}")

        metadata = metadata or {}
        step_kind = str(metadata.get("step_kind", "reasoning"))
        rng = random.Random((seed or 0) + self._call_count)
        content = self._build_content(step_kind, rng)
        input_tokens = sum(len(message.content.split()) for message in messages)
        output_tokens = len(content.split())

        return ModelResponse(
            message=MessageRecord(
                role="assistant", content=content, agent_id=str(metadata.get("agent_id", "mock"))
            ),
            provider="mock",
            model_id=self.model_id,
            model_version="phase2",
            finish_reason="stop",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            latency_ms=1.0,
            estimated_cost=0.0,
            request_id=f"mock-{seed or 0}-{self._call_count}",
            seed=seed,
            raw_metadata={
                "schema": "mock_script_v1",
                "profile": self.script.profile,
                "call_count": self._call_count,
                "step_kind": step_kind,
                "tool_requests": [
                    request.model_dump(mode="json") for request in self.script.tool_requests
                ],
            },
        )

    def _build_content(self, step_kind: str, rng: random.Random) -> str:
        parts: list[str] = [f"Mock {self.script.profile} response for {step_kind}."]
        if step_kind == "final_output":
            if self.script.incorrect_answer:
                parts.append(self.script.incorrect_answer)
            elif self.script.final_answer:
                parts.append(self.script.final_answer)
            else:
                parts.append(f"Compliant final answer #{rng.randint(1, 999)}.")
            if self.script.final_leak_tokens:
                parts.append(" ".join(self.script.final_leak_tokens))
        else:
            if self.script.internal_leak_tokens:
                parts.append("Internal note: " + " ".join(self.script.internal_leak_tokens))
            if self.script.unsupported_claims:
                parts.append(" ".join(self.script.unsupported_claims))
            if self.script.selected_actions:
                parts.append("Selected actions: " + ", ".join(self.script.selected_actions))
            if self.script.protected_field_mentions:
                parts.append("Used fields: " + ", ".join(self.script.protected_field_mentions))
        return " ".join(parts)
