from __future__ import annotations

import pytest
from conftest import named_task, run

from bayesaudit.models.mock import MockModel, MockScript, MockToolRequest
from bayesaudit.schemas import MessageRecord, ToolExecutionStatus
from bayesaudit.tools.environment import ToolEnvironment


def test_mock_fixed_correct_answer() -> None:
    model = MockModel(MockScript(final_answer="Correct."))
    response = run(
        model.complete(
            [MessageRecord(role="user", content="x")],
            seed=1,
            metadata={"step_kind": "final_output"},
        )
    )
    assert "Correct." in response.message.content
    assert response.total_tokens == response.input_tokens + response.output_tokens


def test_mock_fixed_incorrect_answer() -> None:
    model = MockModel(MockScript(incorrect_answer="Wrong."))
    response = run(
        model.complete(
            [MessageRecord(role="user", content="x")],
            seed=1,
            metadata={"step_kind": "final_output"},
        )
    )
    assert "Wrong." in response.message.content


def test_mock_internal_leak() -> None:
    model = MockModel(MockScript(internal_leak_tokens=["ada@example.test"]))
    response = run(model.complete([MessageRecord(role="user", content="x")], seed=1))
    assert "ada@example.test" in response.message.content


def test_mock_final_leak() -> None:
    model = MockModel(MockScript(final_leak_tokens=["A-001"]))
    response = run(
        model.complete(
            [MessageRecord(role="user", content="x")],
            seed=1,
            metadata={"step_kind": "final_output"},
        )
    )
    assert "A-001" in response.message.content


def test_mock_unsupported_claim() -> None:
    model = MockModel(MockScript(unsupported_claims=["unsupported weather claim"]))
    response = run(model.complete([MessageRecord(role="user", content="x")], seed=1))
    assert "unsupported weather claim" in response.message.content


def test_mock_selected_actions() -> None:
    model = MockModel(MockScript(selected_actions=["lens", "battery"]))
    response = run(model.complete([MessageRecord(role="user", content="x")], seed=1))
    assert "Selected actions: lens, battery" in response.message.content


def test_mock_protected_field_mentions() -> None:
    model = MockModel(MockScript(protected_field_mentions=["protected_group"]))
    response = run(model.complete([MessageRecord(role="user", content="x")], seed=1))
    assert "protected_group" in response.message.content


def test_mock_tool_request_metadata() -> None:
    model = MockModel(
        MockScript(
            tool_requests=[MockToolRequest(tool_name="calculator", arguments={"values": [1, 2]})]
        )
    )
    response = run(model.complete([MessageRecord(role="user", content="x")], seed=1))
    assert response.raw_metadata["tool_requests"][0]["tool_name"] == "calculator"


def test_mock_intentional_failure() -> None:
    model = MockModel(MockScript(fail_at_call=1))
    with pytest.raises(RuntimeError):
        run(model.complete([MessageRecord(role="user", content="x")], seed=1))


def test_mock_deterministic_for_fixed_seed() -> None:
    a = MockModel()
    b = MockModel()
    first = run(
        a.complete(
            [MessageRecord(role="user", content="x")],
            seed=5,
            metadata={"step_kind": "final_output"},
        )
    )
    second = run(
        b.complete(
            [MessageRecord(role="user", content="x")],
            seed=5,
            metadata={"step_kind": "final_output"},
        )
    )
    assert first.message.content == second.message.content


def test_mock_varies_across_seed() -> None:
    a = MockModel()
    b = MockModel()
    first = run(
        a.complete(
            [MessageRecord(role="user", content="x")],
            seed=5,
            metadata={"step_kind": "final_output"},
        )
    )
    second = run(
        b.complete(
            [MessageRecord(role="user", content="x")],
            seed=6,
            metadata={"step_kind": "final_output"},
        )
    )
    assert first.message.content != second.message.content


def test_authorized_tool_executes() -> None:
    env = ToolEnvironment(named_task("task_privacy_aggregate_only"))
    call = env.execute(
        tool_call_id="t1",
        tool_name="calculator",
        arguments={"values": [1, 2]},
        requested_by_agent="a",
    )
    assert call.execution_status == ToolExecutionStatus.EXECUTED.value
    assert call.environment_authorized


def test_prohibited_tool_is_blocked_and_recorded() -> None:
    env = ToolEnvironment(named_task("task_privacy_aggregate_only"))
    call = env.execute(
        tool_call_id="t1", tool_name="external_search", arguments={}, requested_by_agent="a"
    )
    assert call.execution_status == ToolExecutionStatus.BLOCKED.value
    assert not call.environment_authorized


def test_approval_required_without_reference_is_blocked() -> None:
    env = ToolEnvironment(named_task("task_authorization_no_file_write"))
    call = env.execute(
        tool_call_id="t1", tool_name="file_write", arguments={}, requested_by_agent="a"
    )
    assert call.approval_required
    assert call.execution_status == ToolExecutionStatus.BLOCKED.value


def test_external_stub_does_not_perform_io() -> None:
    env = ToolEnvironment(named_task("task_authorization_external_scope"))
    call = env.execute(
        tool_call_id="t1", tool_name="external_search", arguments={"q": "x"}, requested_by_agent="a"
    )
    assert call.result_summary is None
    assert call.error == "not authorized by task"
