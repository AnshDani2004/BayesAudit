from __future__ import annotations

from conftest import named_task, run

from bayesaudit.architectures.single_agent import SingleAgentWorkflow
from bayesaudit.architectures.unstructured import UnstructuredDelegationWorkflow
from bayesaudit.models.mock import MockModel, MockScript, MockToolRequest
from bayesaudit.schemas import RetentionStatus, TrajectoryStatus
from bayesaudit.scoring.registry import scorer_for_task


def test_single_agent_trajectory_completeness() -> None:
    task = named_task("task_evidence_claim_support")
    trajectory = run(
        SingleAgentWorkflow().run(
            task,
            MockModel(MockScript(final_answer="Riverton six months")),
            experiment_id="exp",
            run_id="single_ok",
            seed=1,
        )
    )
    assert trajectory.status == TrajectoryStatus.COMPLETED.value
    assert len(trajectory.steps) == 2
    assert trajectory.usage_totals.total_tokens > 0
    assert trajectory.steps[0].constraint_snapshots


def test_unstructured_depth_and_parent_links() -> None:
    task = named_task("task_privacy_aggregate_only")
    trajectory = run(
        UnstructuredDelegationWorkflow(max_depth=3, branching_factor=1).run(
            task, MockModel(), experiment_id="exp", run_id="hier", seed=1
        )
    )
    assert max(step.depth for step in trajectory.steps) == 3
    seen = set()
    for step in trajectory.steps:
        if step.parent_step_id:
            assert step.parent_step_id in seen
        seen.add(step.step_id)


def test_unstructured_branching() -> None:
    task = named_task("task_privacy_aggregate_only")
    trajectory = run(
        UnstructuredDelegationWorkflow(max_depth=1, branching_factor=2).run(
            task, MockModel(), experiment_id="exp", run_id="branch", seed=1
        )
    )
    workers = [step for step in trajectory.steps if step.role == "worker"]
    assert len(workers) == 2


def test_constraint_snapshots_per_handoff() -> None:
    task = named_task("task_privacy_aggregate_only")
    trajectory = run(
        UnstructuredDelegationWorkflow(max_depth=1, branching_factor=1).run(
            task, MockModel(), experiment_id="exp", run_id="snap", seed=1
        )
    )
    assert all(step.constraint_snapshots for step in trajectory.steps)


def test_drop_constraint_snapshot_is_recorded() -> None:
    task = named_task("task_privacy_aggregate_only")
    model = MockModel(MockScript(drop_constraint_ids=["privacy_01"]))
    trajectory = run(
        UnstructuredDelegationWorkflow(max_depth=1, branching_factor=1).run(
            task, model, experiment_id="exp", run_id="drop", seed=1
        )
    )
    statuses = [
        snapshot.retention_status
        for step in trajectory.steps
        for snapshot in step.constraint_snapshots
    ]
    assert RetentionStatus.DROPPED.value in statuses


def test_weaken_constraint_snapshot_is_recorded() -> None:
    task = named_task("task_privacy_aggregate_only")
    model = MockModel(MockScript(weaken_constraint_ids=["privacy_01"]))
    trajectory = run(
        UnstructuredDelegationWorkflow(max_depth=1, branching_factor=1).run(
            task, model, experiment_id="exp", run_id="weaken", seed=1
        )
    )
    statuses = [
        snapshot.retention_status
        for step in trajectory.steps
        for snapshot in step.constraint_snapshots
    ]
    assert RetentionStatus.WEAKENED.value in statuses


def test_privacy_internal_only_violation_preserved() -> None:
    task = named_task("task_privacy_aggregate_only")
    model = MockModel(
        MockScript(
            internal_leak_tokens=["Ada Lim"], final_answer="North average 150; South average 100."
        )
    )
    trajectory = run(
        UnstructuredDelegationWorkflow(max_depth=1, branching_factor=1).run(
            task, model, experiment_id="exp", run_id="privacy_internal", seed=1
        )
    )
    score = scorer_for_task(task).score(task, trajectory)
    assert score.trajectory_violation_count >= 1
    assert score.final_output_violation_count == 0
    assert score.internal_only_violation_count >= 1


def test_privacy_final_output_violation() -> None:
    task = named_task("task_privacy_aggregate_only")
    model = MockModel(MockScript(final_leak_tokens=["ada@example.test"]))
    trajectory = run(
        SingleAgentWorkflow().run(task, model, experiment_id="exp", run_id="privacy_final", seed=1)
    )
    score = scorer_for_task(task).score(task, trajectory)
    assert score.final_output_violation_count >= 1


def test_unauthorized_tool_request_blocked_before_execution() -> None:
    task = named_task("task_authorization_external_scope")
    model = MockModel(
        MockScript(
            tool_requests=[MockToolRequest(tool_name="external_search", arguments={"q": "release"})]
        )
    )
    trajectory = run(
        SingleAgentWorkflow().run(task, model, experiment_id="exp", run_id="auth_tool", seed=1)
    )
    score = scorer_for_task(task).score(task, trajectory)
    assert any(v.violation_type == "prohibited_tool_request" for v in score.violations)
    assert score.final_output_violation_count == 0


def test_evidence_unsupported_internal_claim_corrected_final() -> None:
    task = named_task("task_evidence_citation_audit")
    model = MockModel(
        MockScript(
            unsupported_claims=["opened on June 10"], final_answer="June 3 citation:depot_memo"
        )
    )
    trajectory = run(
        UnstructuredDelegationWorkflow(max_depth=1, branching_factor=1).run(
            task, model, experiment_id="exp", run_id="evidence_internal", seed=1
        )
    )
    score = scorer_for_task(task).score(task, trajectory)
    assert any(
        v.violation_type == "unsupported_claim" and v.internal_only for v in score.violations
    )


def test_evidence_fabricated_citation() -> None:
    task = named_task("task_evidence_citation_audit")
    model = MockModel(MockScript(final_answer="June 3 citation:fake_doc"))
    trajectory = run(
        SingleAgentWorkflow().run(task, model, experiment_id="exp", run_id="evidence_fake", seed=1)
    )
    score = scorer_for_task(task).score(task, trajectory)
    assert any(v.violation_type == "fabricated_citation" for v in score.violations)


def test_budget_combined_overflow_internal() -> None:
    task = named_task("task_budgeting_shared_budget")
    model = MockModel(
        MockScript(
            selected_actions=["lens", "battery"], final_answer="Selected actions: lens, case"
        )
    )
    trajectory = run(
        UnstructuredDelegationWorkflow(max_depth=1, branching_factor=1).run(
            task, model, experiment_id="exp", run_id="budget_over", seed=1
        )
    )
    score = scorer_for_task(task).score(task, trajectory)
    assert any(
        v.violation_type == "global_budget_violation" and v.internal_only for v in score.violations
    )


def test_budget_duplicate_action() -> None:
    task = named_task("task_budgeting_duplicate_spend")
    model = MockModel(MockScript(final_answer="Selected actions: print_flyers, print_flyers"))
    trajectory = run(
        SingleAgentWorkflow().run(task, model, experiment_id="exp", run_id="budget_dup", seed=1)
    )
    score = scorer_for_task(task).score(task, trajectory)
    assert any(v.violation_type == "duplicate_spending" for v in score.violations)


def test_protected_attribute_used_internally_only() -> None:
    task = named_task("task_protected_ranking")
    model = MockModel(
        MockScript(
            protected_field_mentions=["protected_group"], final_answer="Ranking: [C2, C1, C3]"
        )
    )
    trajectory = run(
        UnstructuredDelegationWorkflow(max_depth=1, branching_factor=1).run(
            task, model, experiment_id="exp", run_id="fair_internal", seed=1
        )
    )
    score = scorer_for_task(task).score(task, trajectory)
    assert any(
        v.violation_type == "direct_prohibited_field_use" and v.internal_only
        for v in score.violations
    )


def test_protected_attribute_in_tool_arguments() -> None:
    task = named_task("task_protected_tool_args")
    model = MockModel(
        MockScript(
            tool_requests=[
                MockToolRequest(tool_name="calculator", arguments={"protected_group": "A"})
            ]
        )
    )
    trajectory = run(
        SingleAgentWorkflow().run(task, model, experiment_id="exp", run_id="fair_tool", seed=1)
    )
    score = scorer_for_task(task).score(task, trajectory)
    assert any(v.violation_type == "prohibited_field_in_tool_arguments" for v in score.violations)


def test_unknown_scorer_version_fails() -> None:
    task = named_task("task_privacy_aggregate_only").model_copy(deep=True)
    task.scoring.scorer_version = "missing"
    try:
        scorer_for_task(task)
    except KeyError as exc:
        assert "unknown scorer" in str(exc)
    else:
        raise AssertionError("unknown scorer should fail")
