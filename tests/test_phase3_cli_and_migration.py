from __future__ import annotations

from pytest import CaptureFixture, MonkeyPatch

from bayesaudit.cli import _inspect_payload, main
from bayesaudit.schemas import Trajectory


def test_phase2_minimal_artifact_still_loads() -> None:
    payload = {
        "trajectory_id": "traj_phase2",
        "task_id": "task_evidence_claim_support",
        "task_version": "v1",
        "scenario_hash": "hash",
        "experiment_id": "phase2",
        "run_id": "run_phase2",
        "architecture": "single_agent",
        "behavior_condition": "honest",
        "model_configuration": {"provider": "mock", "model_id": "mock"},
        "oversight_policy": "no_oversight",
        "oversight_budget": {"initial_budget": 0, "remaining_budget": 0, "consumed_budget": 0},
        "seed": 1,
        "configuration_hash": "config",
        "steps": [],
    }
    trajectory = Trajectory.model_validate(payload)
    assert trajectory.schema_version == "bayesaudit.v2"


def test_cli_validate_envelopes(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["bayesaudit", "validate-envelopes"])
    main()
    captured = capsys.readouterr()
    assert '"valid_envelopes": 25' in captured.out


def test_inspect_payload_missing_run() -> None:
    assert _inspect_payload(None) == {"found": False}


def test_inspect_payload_delegation_tree() -> None:
    payload = _inspect_payload(
        {
            "run_id": "run_x",
            "status": "completed",
            "steps": [
                {
                    "step_id": "step_1",
                    "parent_step_id": None,
                    "depth": 0,
                    "branch_id": None,
                    "kind": "planning",
                    "metadata": {"envelope_id": "env_1"},
                }
            ],
            "metadata": {"inheritance": {"mutation_events": [], "verification_events": []}},
        }
    )
    assert payload["found"]
    tree = payload["delegation_tree"]
    assert isinstance(tree, list)
    first = tree[0]
    assert isinstance(first, dict)
    assert first["envelope_id"] == "env_1"
