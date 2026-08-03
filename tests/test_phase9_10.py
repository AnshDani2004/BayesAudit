from __future__ import annotations

import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import bayesaudit.pilot.phase9_10 as phase9
from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.phase9_10 import (
    ARCHITECTURES,
    CONDITIONS,
    DOMAINS,
    MAX_COST_USD,
    MAX_REQUESTS,
    MAX_TOKENS,
    MAX_TRAJECTORIES,
    PHASE9_A_JSON,
    PHASE9_ATTACKER_MANIFEST,
    PHASE9_AUTHORIZATION,
    PHASE9_CLAIM_SUPPORT,
    PHASE9_COST_SUMMARY,
    PHASE9_DATASET_MANIFEST,
    PHASE9_EVIDENCE_DECISION,
    PHASE9_EXECUTION_DECISION,
    PHASE9_EXECUTION_PROTOCOL,
    PHASE9_MATCHED_QUARTET_AUDIT,
    PHASE9_MATRIX,
    PHASE9_MONITOR_ADJUDICATION,
    PHASE9_NEGATIVE_DATASET,
    PHASE9_OBJECTIVE_ADJUDICATION,
    PHASE9_PHASE10_READINESS,
    PHASE9_POLICY_REPLAY,
    PHASE9_POSITIVE_DATASET,
    PHASE9_PREVENTION_ADJUDICATION,
    PHASE9_PRIMARY_ANALYSIS,
    PHASE9_PROTOCOL,
    PHASE9_PROTOCOL_DECISION,
    PHASE9_PROVIDER_SUMMARY,
    PHASE9_REQUEST_SUMMARIES,
    PHASE9_SAP,
    PHASE9_SECONDARY_ANALYSIS,
    PHASE9_SEED_MANIFEST,
    PHASE9_THRESHOLD_SENSITIVITY,
    PHASE9_TOKEN_SUMMARY,
    PHASE9_TRAJECTORY_SUMMARIES,
    PHASE9_WAVE_SUMMARIES,
    validate_phase9_analysis_artifacts,
    validate_phase9_execution_artifacts,
    validate_phase9_protocol_artifacts,
)


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_phase9_protocol_artifacts_validate() -> None:
    assert validate_phase9_protocol_artifacts() == {"valid": True, "errors": []}


def test_phase9_protocol_hashes_are_stable_and_secret_safe() -> None:
    for path in PHASE9_A_JSON:
        payload = _json(path)
        expected = canonical_json_hash(
            {key: value for key, value in payload.items() if key != "artifact_hash"}
        )
        assert payload["artifact_hash"] == expected
        assert "sk-" not in json.dumps(payload, sort_keys=True)
        assert payload["schema_version"] == phase9.SCHEMA_VERSION
        assert payload["phase11_started"] is False


def test_phase9_matrix_is_exact_heldout_grid() -> None:
    matrix = _json(PHASE9_MATRIX)
    records = matrix["records"]
    assert matrix["matrix_size"] == MAX_TRAJECTORIES
    assert len(records) == MAX_TRAJECTORIES
    assert {row["family_id"] for row in records} == set(DOMAINS)
    assert {row["architecture"] for row in records} == set(ARCHITECTURES)
    assert {row["phase9_condition"] for row in records} == set(CONDITIONS)
    assert {row["seed"] for row in records} == {5, 6}
    assert {row["provider_calls_planned"] for row in records} == {3}
    assert all(row["no_real_external_tools"] is True for row in records)


def test_phase9_quartets_are_matched_and_complete() -> None:
    records = _json(PHASE9_MATRIX)["records"]
    quartets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        quartets[row["matched_quartet_id"]].append(row)
    assert len(quartets) == 12
    for rows in quartets.values():
        assert (
            sorted(
                (row["phase9_condition"] for row in rows),
                key=lambda value: CONDITIONS.index(value),
            )
            == CONDITIONS
        )
        assert len({row["task_id"] for row in rows}) == 1
        assert len({row["family_id"] for row in rows}) == 1
        assert len({row["architecture"] for row in rows}) == 1
        assert len({row["seed"] for row in rows}) == 1
        safe = next(row for row in rows if row["phase9_condition"] == CONDITIONS[0])
        assert safe["safe_control"] is True
        assert safe["attacker_insertions_per_trajectory"] == 0
        for row in rows:
            if row["phase9_condition"] != CONDITIONS[0]:
                assert row["matched_safe_condition_id"] == safe["condition_id"]


def test_phase9_fresh_seed_selection_excludes_phase7_and_phase8_seeds() -> None:
    seed_manifest = _json(PHASE9_SEED_MANIFEST)
    assert seed_manifest["historical_excluded_seeds"] == [1, 2, 3, 4, 20260802]
    assert seed_manifest["fresh_phase9_seeds"] == [5, 6]


def test_phase9_heldout_attackers_are_phase6_assets() -> None:
    manifest = _json(PHASE9_ATTACKER_MANIFEST)
    selected = {row["domain"]: row for row in manifest["selected_attackers"]}
    assert set(selected) == set(DOMAINS)
    assert selected["privacy"]["family"] == "random_selective"
    assert selected["authorization"]["family"] == "policy_aware"
    assert selected["evidence"]["family"] == "opportunistic"
    for row in selected.values():
        assert Path(row["config_path"]).exists()
        assert row["phase8_nonuse_evidence"] == "not the Phase 8 strategic attacker construct"


def test_phase9_wave_ordering_is_frozen() -> None:
    records = _json(PHASE9_MATRIX)["records"]
    by_wave = Counter(row["wave_id"] for row in records)
    assert by_wave == {"wave_0": 4, "wave_1": 20, "wave_2": 24}
    assert [row["execution_order"] for row in records] == list(range(1, 49))
    execution = _json(PHASE9_EXECUTION_PROTOCOL)
    assert execution["planned_trajectories"] == 48
    assert execution["planned_requests"] == 144
    assert execution["waves"][-1]["cumulative"] == 48


def test_phase9_authorization_uses_exact_provider_and_ceilings() -> None:
    authorization = _json(PHASE9_AUTHORIZATION)
    assert authorization["provider"] == "openai"
    assert authorization["exact_model"] == phase9.MODEL
    assert authorization["credential_env_var"] == "OPENAI_API_KEY"
    assert authorization["pricing_table_version"] == phase9.PRICING_TABLE_VERSION
    assert authorization["planned_trajectories"] == MAX_TRAJECTORIES
    assert authorization["planned_provider_requests"] == 144
    assert authorization["maximum_actual_provider_requests"] == MAX_REQUESTS
    assert authorization["maximum_total_tokens"] == MAX_TOKENS
    assert authorization["maximum_token_derived_cost_usd"] == str(MAX_COST_USD)
    assert Decimal(authorization["estimated_token_derived_cost_usd"]) <= MAX_COST_USD
    assert authorization["authorization_decision"] == "allow"
    assert all(gate["status"] == "passed" for gate in authorization["gate_results"])


def test_phase9_protocol_decision_and_no_phase10_or_phase11() -> None:
    protocol = _json(PHASE9_PROTOCOL)
    sap = _json(PHASE9_SAP)
    decision = _json(PHASE9_PROTOCOL_DECISION)
    assert (
        sap["heldout_attack_effect"]["comparison"]
        == "safe_no_attacker_no_oversight versus heldout_attacker_no_oversight"
    )
    assert "do not begin Phase 11" in protocol["prohibited_actions"]
    assert decision["protocol_decision"] == "phase9_protocol_frozen_with_limitations"
    assert decision["gate_1_passed"] is True
    assert decision["phase10_started"] is False
    assert decision["phase11_started"] is False


def test_phase9_execution_artifacts_validate_when_present() -> None:
    assert validate_phase9_execution_artifacts() == {"valid": True, "errors": []}


def test_phase9_execution_covers_exact_frozen_matrix() -> None:
    matrix_ids = {row["condition_id"] for row in _json(PHASE9_MATRIX)["records"]}
    trajectories = _jsonl(PHASE9_TRAJECTORY_SUMMARIES)
    executed_ids = {row["condition_id"] for row in trajectories}
    assert len(trajectories) == 48
    assert executed_ids == matrix_ids
    assert {row["execution_status"] for row in trajectories} == {"completed"}
    assert sum(row["provider_requests"] for row in trajectories) == 144


def test_phase9_execution_requests_and_waves_reconcile() -> None:
    requests = _jsonl(PHASE9_REQUEST_SUMMARIES)
    trajectories = _jsonl(PHASE9_TRAJECTORY_SUMMARIES)
    waves = _jsonl(PHASE9_WAVE_SUMMARIES)
    assert len(requests) == 144
    assert len(waves) == 3
    assert [row["wave_id"] for row in waves] == ["wave_0", "wave_1", "wave_2"]
    assert [row["expected_trajectories"] for row in waves] == [4, 20, 24]
    assert all(row["raw_first_persistence"] is True for row in requests)
    assert all(len(row["request_hashes"]) == 3 for row in trajectories)
    assert all(len(row["raw_response_hashes"]) == 3 for row in trajectories)


def test_phase9_execution_summaries_stay_within_authorized_ceilings() -> None:
    provider = _json(PHASE9_PROVIDER_SUMMARY)
    token = _json(PHASE9_TOKEN_SUMMARY)
    cost = _json(PHASE9_COST_SUMMARY)
    decision = _json(PHASE9_EXECUTION_DECISION)
    assert provider["completed_trajectories"] == 48
    assert provider["provider_request_records"] == 144
    assert provider["provider_calls_performed"] == 144
    assert provider["cache_hits"] == 144
    assert token["total_tokens"] <= MAX_TOKENS
    assert Decimal(cost["token_derived_cost_usd"]) <= MAX_COST_USD
    assert decision["execution_decision"] == "phase9_execution_complete"
    assert decision["phase10_started"] is False
    assert decision["phase11_started"] is False


def test_phase9_analysis_artifacts_validate_when_present() -> None:
    assert validate_phase9_analysis_artifacts() == {"valid": True, "errors": []}


def test_phase9_offline_adjudication_includes_all_execution_records() -> None:
    assert len(_jsonl(PHASE9_OBJECTIVE_ADJUDICATION)) == 48
    assert len(_jsonl(PHASE9_MONITOR_ADJUDICATION)) == 48
    assert len(_jsonl(PHASE9_PREVENTION_ADJUDICATION)) == 48
    assert len(_jsonl(PHASE9_MATCHED_QUARTET_AUDIT)) == 12
    assert len(_jsonl(PHASE9_POSITIVE_DATASET)) == 24
    assert len(_jsonl(PHASE9_NEGATIVE_DATASET)) == 24


def test_phase9_primary_analysis_preserves_heldout_nonreplication() -> None:
    primary = _json(PHASE9_PRIMARY_ANALYSIS)
    effect = primary["heldout_attack_effect"]
    monitor = primary["monitor_robustness"]
    assert primary["pair_count"] == 12
    assert effect["safe_positive"] == 8
    assert effect["heldout_attacker_no_oversight_positive"] == 4
    assert effect["paired_risk_difference"] == "-0.3333"
    assert effect["exact_mcnemar_p_value"] == "0.289062"
    assert monitor["objective_positive_pair_count"] == 4
    assert monitor["rule_based_alerts"] == 4
    assert monitor["bayesian_alerts"] == 0


def test_phase9_secondary_dataset_and_readiness_are_frozen() -> None:
    secondary = _json(PHASE9_SECONDARY_ANALYSIS)
    dataset = _json(PHASE9_DATASET_MANIFEST)
    evidence = _json(PHASE9_EVIDENCE_DECISION)
    readiness = _json(PHASE9_PHASE10_READINESS)
    claims = _json(PHASE9_CLAIM_SUPPORT)
    assert secondary["positive_by_domain"] == {
        "authorization": 9,
        "evidence": 3,
        "privacy": 12,
    }
    assert dataset["positive_row_count"] == 24
    assert dataset["negative_row_count"] == 24
    assert (
        evidence["phase9_evidence_decision"]
        == "phase9_null_or_nonreplication_preserved_with_limitations"
    )
    assert readiness["phase10_readiness"] == "ready_for_phase10_with_documented_limitations"
    assert readiness["provider_rerun_required"] is False
    assert claims["claims"][-1]["support_status"] == "unsupported"


def test_phase9_sensitivity_and_policy_replay_are_offline_only() -> None:
    threshold = _json(PHASE9_THRESHOLD_SENSITIVITY)
    replay = _json(PHASE9_POLICY_REPLAY)
    assert threshold["provider_calls_performed"] == 0
    assert replay["provider_calls_performed"] == 0
    assert len(threshold["records"]) == 10
    assert {row["policy_id"] for row in replay["records"]} == {
        "zero_audit_budget",
        "frozen_phase9_policy_one_audit",
        "deterministic_final_checkpoint",
    }
