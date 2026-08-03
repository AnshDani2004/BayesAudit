from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, cast

import bayesaudit.pilot.phase7_refinement as refinement
from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.phase7_refinement import (
    PHASE7_AFFECTED_RUN_ANALYSIS,
    PHASE7_BENCHMARK_CANDIDATE_VERSION,
    PHASE7_BENCHMARK_FREEZE_DECISION,
    PHASE7_BENCHMARK_REFINEMENT_MANIFEST,
    PHASE7_BENCHMARK_VERSION_MANIFEST,
    PHASE7_EVIDENCE_PACKAGE_MANIFEST,
    PHASE7_PROVIDER_RERUN_REQUIREMENTS,
    PHASE7_REFINEMENT_JSON_ARTIFACTS,
    PHASE7_VERSION_COMPATIBILITY_MATRIX,
    validate_phase7_refinement_artifacts,
)


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_phase7_refinement_artifacts_validate() -> None:
    assert validate_phase7_refinement_artifacts() == {"valid": True, "errors": []}


def test_phase7_refinement_source_is_provider_disabled() -> None:
    source = inspect.getsource(refinement)
    assert "assert_provider_disabled()" in source
    assert "make_provider_request" not in source
    assert "execute_provider_or_cached" not in source


def test_phase7_refinement_versioned_benchmark_candidate_created() -> None:
    manifest = _json(PHASE7_BENCHMARK_VERSION_MANIFEST)
    assert manifest["benchmark_version"] == PHASE7_BENCHMARK_CANDIDATE_VERSION
    assert manifest["parent_version"] == "phase7_real_model_pilot_pre_freeze"
    assert "phase7_stage_e3_validated_dataset_v1" in manifest["dataset_versions"]
    assert len(manifest["benchmark_hash"]) == 64


def test_phase7_refinement_classifies_refinements_without_semantic_replacements() -> None:
    manifest = _json(PHASE7_BENCHMARK_REFINEMENT_MANIFEST)
    assert manifest["refinement_count"] == 14
    assert manifest["classification_counts"]["documentation_only"] == 8
    assert manifest["classification_counts"]["derived_label_only"] == 1
    assert manifest["classification_counts"]["scorer_version_update"] == 1
    assert manifest["classification_counts"]["classifier_version_update"] == 1
    assert manifest["task_semantic_refinements"] == 0
    assert manifest["prompt_semantic_refinements"] == 0
    assert manifest["attacker_semantic_refinements"] == 0
    assert all(row["provider_rerun_needed"] is False for row in manifest["refinements"])


def test_phase7_compatibility_matrix_preserves_historical_labels() -> None:
    matrix = _json(PHASE7_VERSION_COMPATIBILITY_MATRIX)
    assert matrix["compatibility_matrix_result"] == "passed_with_documented_limitations"
    assert matrix["historical_outputs_relabelled_as_new_semantics"] is False
    assert all(row["original_label_preserved"] for row in matrix["rows"])
    assert all(row["adjudicated_label_preserved"] for row in matrix["rows"])


def test_phase7_affected_run_analysis_preserves_versions_and_labels() -> None:
    analysis = _json(PHASE7_AFFECTED_RUN_ANALYSIS)
    assert analysis["provider_visible_conditions_changed"] is False
    assert analysis["historical_outputs_preserved"] is True
    assert analysis["repaired_labels_preserved"] is True
    assert analysis["adjudicated_labels_preserved"] is True
    assert analysis["refinements_requiring_provider_rerun"] == []
    assert set(analysis["offline_rescore_eligible_refinements"]) == {
        "p7_refine_004",
        "p7_refine_007",
        "p7_refine_013",
    }


def test_phase7_provider_rerun_logic_distinguishes_offline_repairs() -> None:
    reruns = _json(PHASE7_PROVIDER_RERUN_REQUIREMENTS)
    logic = reruns["rerun_requirement_logic"]
    assert reruns["provider_rerun_required_for_phase7_claims"] is False
    assert reruns["provider_rerun_required_for_freeze"] is False
    assert reruns["future_confirmatory_provider_rerun_recommended"] is True
    assert logic["task_semantic_change"] is True
    assert logic["prompt_semantic_change"] is True
    assert logic["attacker_semantic_change"] is True
    assert logic["objective_scorer_logic_change"] is False
    assert logic["risk_classifier_logic_change"] is False
    assert logic["documentation_change"] is False


def test_phase7_evidence_package_integrity() -> None:
    evidence = _json(PHASE7_EVIDENCE_PACKAGE_MANIFEST)
    assert evidence["evidence_artifact_count"] == 10
    assert evidence["raw_provider_responses_included"] is False
    assert evidence["stage_e3_validated_dataset_included"] is True
    assert evidence["version_compatibility_matrix_included"] is True
    assert len(evidence["evidence_package_hash"]) == 64
    assert not any(path.startswith("results/tables/") for path in evidence["evidence_artifacts"])


def test_phase7_benchmark_freeze_decision_is_honest_with_limitations() -> None:
    decision = _json(PHASE7_BENCHMARK_FREEZE_DECISION)
    assert decision["benchmark_freeze_decision"] == "phase7_benchmark_frozen_with_limitations"
    assert decision["material_unresolved_benchmark_defect"] is False
    assert decision["provider_rerun_required"] is False
    assert decision["evidence_package_frozen"] is True
    assert decision["version_and_compatibility_records_complete"] is True
    assert "no production-readiness conclusion" in decision["limitations"]


def test_phase7_refinement_json_hashes_are_stable_and_offline() -> None:
    for path in PHASE7_REFINEMENT_JSON_ARTIFACTS:
        payload = _json(path)
        expected = canonical_json_hash(
            {key: value for key, value in payload.items() if key != "artifact_hash"}
        )
        assert payload["artifact_hash"] == expected
        assert payload["provider_calls_performed"] == 0
        assert payload["stage_e2_rerun_performed"] is False
        assert payload["phase8_started"] is False
