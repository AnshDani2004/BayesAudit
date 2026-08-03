from __future__ import annotations

import inspect
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import bayesaudit.pilot.phase8 as phase8
from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.phase8 import (
    ARCHITECTURES,
    CONDITIONS,
    DOMAINS,
    MAX_COST_USD,
    MAX_REQUESTS,
    MAX_TOKENS,
    MAX_TRAJECTORIES,
    PHASE8_AUTHORIZATION,
    PHASE8_EXECUTION_PROTOCOL,
    PHASE8_JSON_ARTIFACTS_A,
    PHASE8_MATRIX,
    PHASE8_PROTOCOL,
    PHASE8_PROTOCOL_DECISION,
    PHASE8_SAP,
    PHASE8_SEED_MANIFEST,
    PROVIDER,
    validate_phase8_protocol_artifacts,
)


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_phase8_protocol_artifacts_validate() -> None:
    assert validate_phase8_protocol_artifacts() == {"valid": True, "errors": []}


def test_phase8_protocol_hashes_are_stable_and_secret_safe() -> None:
    for path in PHASE8_JSON_ARTIFACTS_A:
        payload = _json(path)
        expected = canonical_json_hash(
            {key: value for key, value in payload.items() if key != "artifact_hash"}
        )
        assert payload["artifact_hash"] == expected
        assert "sk-" not in json.dumps(payload, sort_keys=True)
        assert payload["schema_version"] == phase8.PHASE8_SCHEMA_VERSION


def test_phase8_matrix_is_exact_confirmatory_grid() -> None:
    matrix = _json(PHASE8_MATRIX)
    records = matrix["records"]
    assert matrix["matrix_size"] == MAX_TRAJECTORIES
    assert len(records) == MAX_TRAJECTORIES
    assert {row["family_id"] for row in records} == set(DOMAINS)
    assert {row["architecture"] for row in records} == set(ARCHITECTURES)
    assert {row["phase8_condition"] for row in records} == set(CONDITIONS)
    assert {row["seed"] for row in records} == {1, 2, 3, 4}
    assert {row["provider_calls_planned"] for row in records} == {3}
    assert all(row["no_real_external_tools"] is True for row in records)


def test_phase8_quartets_are_matched_and_complete() -> None:
    records = _json(PHASE8_MATRIX)["records"]
    quartets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        quartets[row["matched_quartet_id"]].append(row)
    assert len(quartets) == 24
    for rows in quartets.values():
        assert (
            sorted(
                (row["phase8_condition"] for row in rows),
                key=lambda value: CONDITIONS.index(value),
            )
            == CONDITIONS
        )
        assert len({row["task_id"] for row in rows}) == 1
        assert len({row["family_id"] for row in rows}) == 1
        assert len({row["architecture"] for row in rows}) == 1
        assert len({row["seed"] for row in rows}) == 1
        safe = next(row for row in rows if row["phase8_condition"] == CONDITIONS[0])
        assert safe["safe_control"] is True
        assert safe["attacker_insertions_per_trajectory"] == 0
        for row in rows:
            if row["phase8_condition"] != CONDITIONS[0]:
                assert row["matched_safe_condition_id"] == safe["condition_id"]


def test_phase8_fresh_seed_selection_does_not_reuse_phase7_real_seed() -> None:
    seed_manifest = _json(PHASE8_SEED_MANIFEST)
    assert seed_manifest["fresh_confirmatory_seeds"] == [1, 2, 3, 4]
    assert 20260802 in seed_manifest["phase7_real_model_seeds"]
    assert seed_manifest["seed_reuse_with_phase7"] is False


def test_phase8_wave_ordering_is_frozen() -> None:
    records = _json(PHASE8_MATRIX)["records"]
    by_wave = Counter(row["wave_id"] for row in records)
    assert by_wave == {"wave_0": 4, "wave_1": 20, "wave_2": 48, "wave_3": 24}
    assert [row["execution_order"] for row in records] == list(range(1, 97))
    execution = _json(PHASE8_EXECUTION_PROTOCOL)
    assert execution["planned_trajectories"] == 96
    assert execution["planned_requests"] == 288
    assert execution["waves"][-1]["cumulative"] == 96


def test_phase8_authorization_uses_exact_provider_and_ceilings() -> None:
    authorization = _json(PHASE8_AUTHORIZATION)
    assert authorization["provider"] == PROVIDER
    assert authorization["exact_model"] == phase8.MODEL
    assert authorization["credential_env_var"] == "OPENAI_API_KEY"
    assert authorization["pricing_table_version"] == phase8.PRICING_TABLE_VERSION
    assert authorization["planned_trajectories"] == MAX_TRAJECTORIES
    assert authorization["planned_provider_requests"] == 288
    assert authorization["maximum_actual_provider_requests"] == MAX_REQUESTS
    assert authorization["maximum_total_tokens"] == MAX_TOKENS
    assert authorization["maximum_token_derived_cost_usd"] == str(MAX_COST_USD)
    assert authorization["authorization_decision"] == "allow"
    assert all(gate["status"] == "passed" for gate in authorization["gate_results"])


def test_phase8_protocol_freezes_statistics_and_outcomes() -> None:
    protocol = _json(PHASE8_PROTOCOL)
    sap = _json(PHASE8_SAP)
    assert "controlled_attack_effect" in protocol["primary_questions"]
    assert sap["primary_attack_effect"]["test"] == "exact_mcnemar"
    assert sap["proportion_interval"] == "wilson_95_percent"
    assert "Holm" in sap["multiplicity"]
    assert (
        sap["sparse_data_rule"]
        == "record not_estimable_zero_denominator when denominator is zero"
    )


def test_phase8_protocol_decision_and_no_phase9() -> None:
    decision = _json(PHASE8_PROTOCOL_DECISION)
    assert decision["protocol_decision"] == "phase8_protocol_frozen_with_limitations"
    assert decision["gate_a_passed"] is True
    assert decision["phase9_started"] is False
    assert "do not begin Phase 9" in _json(PHASE8_PROTOCOL)["prohibited_actions"]


def test_phase8_provider_execution_is_not_disabled_in_source_but_closeout_is_guarded() -> None:
    source = inspect.getsource(phase8)
    assert "run_phase8_provider_execution" in source
    assert "Phase 8 provider execution is disabled in CI" in source
    assert "run_phase9" not in source
