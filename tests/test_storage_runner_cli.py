from __future__ import annotations

from pathlib import Path

from conftest import named_task, run
from pytest import CaptureFixture, MonkeyPatch

from bayesaudit.architectures.single_agent import SingleAgentWorkflow
from bayesaudit.cli import main
from bayesaudit.models.mock import MockModel, MockScript
from bayesaudit.runner import ExperimentConfig, planned_runs, run_experiment
from bayesaudit.scoring.registry import scorer_for_task
from bayesaudit.storage.jsonl import append_jsonl, read_jsonl
from bayesaudit.storage.normalize import normalized_records, write_parquet_tables


def test_jsonl_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    append_jsonl(path, {"run_id": "a"})
    append_jsonl(path, {"run_id": "b"})
    assert [row["run_id"] for row in read_jsonl(path)] == ["a", "b"]


def test_normalized_tables_have_stable_names(tmp_path: Path) -> None:
    task = named_task("task_privacy_aggregate_only")
    trajectory = run(
        SingleAgentWorkflow().run(
            task,
            MockModel(MockScript(final_answer="North 150")),
            experiment_id="exp",
            run_id="norm",
            seed=1,
        )
    )
    score = scorer_for_task(task).score(task, trajectory)
    tables = normalized_records(trajectory, score)
    assert {
        "steps",
        "messages",
        "tool_calls",
        "constraint_snapshots",
        "violations",
        "usage",
    }.issubset(tables)
    write_parquet_tables(tmp_path, tables)
    assert (tmp_path / "steps.parquet").exists()


def test_runner_dry_run_counts() -> None:
    config = ExperimentConfig(
        experiment_id="dry",
        task_roots=[Path("scenarios/evidence")],
        architectures=["single_agent"],
        behavior_profiles=[{"name": "compliant", "script": {"final_answer": "ok"}}],
        seeds=[1, 2],
    )
    assert len(planned_runs(config)) == 10
    summary = run(run_experiment(config, dry_run=True))
    assert summary["planned"] == 10


def test_runner_persists_success_and_resume_skips(tmp_path: Path) -> None:
    config = ExperimentConfig(
        experiment_id="resume_case",
        task_roots=[Path("scenarios/privacy")],
        architectures=["single_agent"],
        behavior_profiles=[{"name": "compliant", "script": {"final_answer": "ok"}}],
        seeds=[1],
        output_root=tmp_path,
    )
    first = run(run_experiment(config))
    second = run(run_experiment(config))
    assert first["completed"] == 5
    assert second["skipped"] == 5
    assert len(read_jsonl(tmp_path / "resume_case" / "raw_trajectories.jsonl")) == 5


def test_runner_preserves_failures(tmp_path: Path) -> None:
    config = ExperimentConfig(
        experiment_id="failure_case",
        task_roots=[Path("scenarios/evidence")],
        architectures=["single_agent"],
        behavior_profiles=[{"name": "fail", "script": {"fail_at_call": 1}}],
        seeds=[1],
        output_root=tmp_path,
    )
    summary = run(run_experiment(config))
    rows = read_jsonl(tmp_path / "failure_case" / "raw_trajectories.jsonl")
    assert summary["failed"] == 5
    assert all(row["status"] == "failed" for row in rows)


def test_cli_validate_scenarios(capsys: CaptureFixture[str], monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["bayesaudit", "validate-scenarios", "--root", "scenarios"])
    main()
    captured = capsys.readouterr()
    assert '"task_count": 25' in captured.out
