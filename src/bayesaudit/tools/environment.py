"""Offline synthetic tool environment."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from bayesaudit.schemas import BenchmarkTask, ToolCallRecord, ToolExecutionStatus


class ToolEnvironment:
    """Executes safe synthetic tools and records environment-derived authorization."""

    def __init__(self, task: BenchmarkTask) -> None:
        self.task = task

    def execute(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        requested_by_agent: str,
        approval_reference: str | None = None,
        blocked_by_intervention: bool = False,
    ) -> ToolCallRecord:
        started = datetime.now(timezone.utc)
        environment_authorized = tool_name in self.task.authorized_tools
        approval_required = tool_name in {"file_write", "email", "outbound_contact", "purchase_api"}
        if approval_required and not approval_reference:
            environment_authorized = False
        status = ToolExecutionStatus.REQUESTED
        result_summary: str | None = None
        error: str | None = None

        if blocked_by_intervention or not environment_authorized:
            status = ToolExecutionStatus.BLOCKED
            error = (
                "blocked by intervention" if blocked_by_intervention else "not authorized by task"
            )
        else:
            status = ToolExecutionStatus.EXECUTED
            result_summary = self._synthetic_result(tool_name, arguments)

        return ToolCallRecord(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            requested_by_agent=requested_by_agent,
            approval_required=approval_required,
            approval_reference=approval_reference,
            authorization_basis="task.authorized_tools plus approval state",
            environment_authorized=environment_authorized,
            execution_status=status,
            result_summary=result_summary,
            error=error,
            started_at=started,
            completed_at=datetime.now(timezone.utc),
        )

    def _synthetic_result(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if tool_name == "calculator":
            return self._calculator(arguments)
        if tool_name in {"local_document_lookup", "local_manifest_read", "synthetic_record_lookup"}:
            return f"synthetic local result for {tool_name}"
        if tool_name in {"external_search", "web_browser"}:
            return "external search stub did not contact the network"
        if tool_name in {"file_write", "email", "outbound_contact", "purchase_api"}:
            return f"{tool_name} stub did not perform external action"
        return f"synthetic result for {tool_name}"

    def _calculator(self, arguments: dict[str, Any]) -> str:
        op = str(arguments.get("op", "sum"))
        values = [Decimal(str(value)) for value in arguments.get("values", [])]
        if op == "sum":
            return str(sum(values, Decimal("0")))
        if op == "avg" and values:
            return str(sum(values, Decimal("0")) / Decimal(len(values)))
        return "unsupported calculator operation"
