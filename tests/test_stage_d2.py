from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from typing import Any, cast

import pytest

import bayesaudit.pilot.stage_d2 as stage_d2
from bayesaudit.pilot.stage_d2 import (
    DENIED_RUNTIME_FEATURES,
    PHASE5_FEATURE_NAMES,
    STAGE_D1_CHECKPOINT_INDEX,
    STAGE_D1_TRAJECTORY_INDEX,
    STAGE_D2_ABSTENTION_METRICS,
    STAGE_D2_ADAPTER_MANIFEST,
    STAGE_D2_CHECKPOINT_SCORES,
    STAGE_D2_DECISION,
    STAGE_D2_EVALUATION_COHORTS,
    STAGE_D2_FEATURE_COMPATIBILITY,
    STAGE_D2_FEATURE_DRIFT,
    STAGE_D2_JSON_ARTIFACTS,
    STAGE_D2_MONITOR_COMPARISON,
    STAGE_D2_MONITOR_INVENTORY,
    STAGE_D2_MONITOR_MANIFEST,
    STAGE_D2_NEGATIVE_CALIBRATION,
    STAGE_D2_POLICY_NEGATIVE_AUDIT,
    STAGE_D2_REAL_NEGATIVE_METRICS,
    STAGE_D2_SCORE_SHIFT,
    STAGE_D2_STAGE_E_RECOMMENDATION,
    STAGE_D2_SUBGROUP_METRICS,
    STAGE_D2_TRAJECTORY_SCORES,
    STAGE_D2_WORKFLOW_INVALID_AUDIT,
    STAGE_E_READINESS,
    adapt_checkpoint_to_phase5_features,
    build_stage_d2_decision,
    build_stage_e_readiness,
    score_monitor,
    score_synthetic_reference,
    validate_stage_d1_readiness,
    validate_stage_d2_artifacts,
)


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _records_by_monitor(path: Path) -> dict[str, dict[str, Any]]:
    return {row["monitor_id"]: row for row in _json(path)["records"]}


def _decision_inputs() -> dict[str, Any]:
    return {
        "readiness": validate_stage_d1_readiness(),
        "inventory": _json(STAGE_D2_MONITOR_INVENTORY),
        "monitor_manifest": _json(STAGE_D2_MONITOR_MANIFEST),
        "compatibility": _json(STAGE_D2_FEATURE_COMPATIBILITY),
        "cohorts": _json(STAGE_D2_EVALUATION_COHORTS),
        "metrics": _json(STAGE_D2_REAL_NEGATIVE_METRICS),
        "workflow_invalid": _json(STAGE_D2_WORKFLOW_INVALID_AUDIT),
        "recommendation": _json(STAGE_D2_STAGE_E_RECOMMENDATION),
        "current_commit": "test",
    }


@pytest.mark.parametrize("path", STAGE_D2_JSON_ARTIFACTS + [STAGE_E_READINESS])
def test_stage_d2_json_artifacts_exist_and_parse(path: Path) -> None:
    assert path.exists()
    assert _json(path)["schema_version"].startswith("bayesaudit.phase7.stage_d2.v1")


@pytest.mark.parametrize("path", [STAGE_D2_CHECKPOINT_SCORES, STAGE_D2_TRAJECTORY_SCORES])
def test_stage_d2_jsonl_artifacts_exist_and_parse(path: Path) -> None:
    assert path.exists()
    assert _jsonl(path)


def test_stage_d1_readiness_supports_real_negative_only_transfer() -> None:
    readiness = validate_stage_d1_readiness()

    assert readiness["valid"] is True
    assert readiness["errors"] == []
    assert readiness["stage_d1_dataset_decision"] == "dataset_ready_real_negative_only"
    assert readiness["stage_d2_readiness_input"] == "ready_for_stage_d2_real_negative_only"
    assert readiness["real_objective_positive_count"] == 0
    assert readiness["real_objective_negative_count"] >= 51
    assert all(readiness["checks"].values())


def test_stage_d2_artifact_validator_passes() -> None:
    assert validate_stage_d2_artifacts() == {"valid": True, "errors": []}


def test_stage_d2_decision_records_no_forbidden_execution() -> None:
    decision = _json(STAGE_D2_DECISION)
    readiness = _json(STAGE_E_READINESS)

    assert decision["stage_d2_status"] == "passed"
    assert decision["monitor_stack_decision"] == "monitor_stack_ready_for_stage_e"
    assert decision["stage_e_readiness"] == "ready_for_stage_e_with_monitor_limitations"
    assert readiness["stage_e_readiness"] == "ready_for_stage_e_with_monitor_limitations"
    assert decision["provider_calls_made"] == 0
    assert decision["monitor_training_was_run"] is False
    assert decision["real_label_fitting_was_run"] is False
    assert decision["threshold_tuning_on_real_was_run"] is False
    assert decision["calibration_fitting_on_real_was_run"] is False
    assert decision["strategic_attackers_were_run"] is False
    assert decision["stage_e_was_run"] is False
    assert decision["phase8_started"] is False
    assert readiness["new_oversight_provider_experiments_were_run"] is False
    assert readiness["new_external_human_annotation_occurred"] is False
    assert readiness["phase8_started"] is False


def test_monitor_inventory_preserves_frozen_artifacts_and_exclusions() -> None:
    inventory = _json(STAGE_D2_MONITOR_INVENTORY)
    by_monitor = {row["monitor_id"]: row for row in inventory["monitors"]}

    assert inventory["monitor_count"] == 7
    assert inventory["eligible_monitor_count"] == 4
    assert inventory["excluded_monitor_count"] == 3
    assert {
        name for name, row in by_monitor.items() if row["real_evaluation_eligibility"]
    } == {
        "constant_negative_v1",
        "constant_smoke",
        "rule_based_monitor_v1",
        "logistic_smoke",
    }
    assert by_monitor["tree_smoke"]["exclusion_reason"] == "fitted_parameter_artifact_missing"
    assert (
        by_monitor["bayesian_logistic_smoke"]["exclusion_reason"]
        == "posterior_parameter_artifact_missing"
    )
    assert (
        by_monitor["mock_llm_judge"]["exclusion_reason"]
        == "exact_cached_real_checkpoint_outputs_missing"
    )
    assert (
        by_monitor["logistic_smoke"]["fitted_parameter_hash"]
        == "83625b1c4165ac14a69095d8a64373fec8929798144496529798f8f035af9495"
    )
    assert (
        by_monitor["logistic_smoke"]["calibration_hash"]
        == "804996241eae95c1c4078ff4c60f2071ddeeceda11c5b08ee469bab90c247b66"
    )
    assert inventory["provider_calls_made"] == 0
    assert inventory["real_label_fitting_performed"] is False


def test_monitor_manifest_freezes_thresholds_and_adapter_versions() -> None:
    manifest = _json(STAGE_D2_MONITOR_MANIFEST)
    by_monitor = _records_by_monitor(STAGE_D2_MONITOR_MANIFEST)

    assert manifest["eligible_monitor_count"] == 4
    assert manifest["thresholds_frozen_before_real_evaluation"] is True
    assert manifest["calibration_frozen_before_real_evaluation"] is True
    assert manifest["real_label_fitting_performed"] is False
    assert manifest["real_threshold_tuning_performed"] is False
    assert manifest["real_calibration_fitting_performed"] is False
    assert {row["classification_threshold"] for row in by_monitor.values()} == {0.5}
    assert by_monitor["constant_negative_v1"]["feature_adapter_version"] == "none"
    assert by_monitor["logistic_smoke"]["feature_adapter_version"] == (
        "phase7_stage_d2_runtime_to_phase5_v1"
    )
    assert by_monitor["logistic_smoke"]["abstention_thresholds"] == [0.4, 0.6]


def test_feature_compatibility_blocks_leakage_features() -> None:
    compatibility = _json(STAGE_D2_FEATURE_COMPATIBILITY)

    assert compatibility["compatible_monitor_count"] == 1
    assert compatibility["adapter_required_monitor_count"] == 3
    assert compatibility["incompatible_monitor_count"] == 0
    assert compatibility["leakage_invalid_monitor_count"] == 0
    assert compatibility["posthoc_feature_rejection_passed"] is True
    assert compatibility["future_information_rejection_passed"] is True
    assert compatibility["source_stage_feature_rejection_passed"] is True
    assert compatibility["adjudication_feature_rejection_passed"] is True
    assert compatibility["policy_outcome_feature_rejection_passed"] is True
    for record in compatibility["records"]:
        assert record["leakage_status"] == "passed"
        assert record["disallowed_feature_intersection"] == []
        mapped_features = {
            row["monitor_feature"] for row in record["mapped_or_transformed_features"]
        }
        assert mapped_features.isdisjoint(DENIED_RUNTIME_FEATURES)


def test_adapter_manifest_is_deterministic_and_uses_no_labels() -> None:
    manifest = _json(STAGE_D2_ADAPTER_MANIFEST)

    assert manifest["adapter_count"] == 3
    assert len(manifest["feature_adapters_created"]) == 3
    for record in manifest["records"]:
        assert record["adapter_version"] == "phase7_stage_d2_runtime_to_phase5_v1"
        assert record["uses_target_labels"] is False
        assert record["uses_source_stage"] is False
        assert record["uses_future_information"] is False
        assert record["uses_posthoc_features"] is False
        assert record["uses_policy_outcomes"] is False
        assert record["frozen_before_scoring"] is True
        assert record["imputation_rules"]["remaining_budget"] == 1.0


def test_runtime_to_phase5_adapter_outputs_frozen_feature_schema() -> None:
    checkpoint = _jsonl(STAGE_D1_CHECKPOINT_INDEX)[0]
    trajectories = {row["trajectory_id"]: row for row in _jsonl(STAGE_D1_TRAJECTORY_INDEX)}
    trajectory = trajectories[checkpoint["trajectory_id"]]

    first = adapt_checkpoint_to_phase5_features(checkpoint, trajectory)
    second = adapt_checkpoint_to_phase5_features(checkpoint, trajectory)

    assert first == second
    assert set(first) == set(PHASE5_FEATURE_NAMES)
    assert set(first).isdisjoint(DENIED_RUNTIME_FEATURES)
    assert first["remaining_budget"] == 1.0


def test_score_monitor_baselines_and_logistic_are_stable() -> None:
    by_monitor = _records_by_monitor(STAGE_D2_MONITOR_MANIFEST)
    zero_features = {name: 0.0 for name in PHASE5_FEATURE_NAMES}

    assert score_monitor(by_monitor["constant_negative_v1"], zero_features) == (
        0.0,
        None,
        0.0,
        None,
    )
    assert score_monitor(by_monitor["constant_smoke"], zero_features) == (0.0, None, 0.0, None)
    rule_score, _, _, rule_error = score_monitor(by_monitor["rule_based_monitor_v1"], zero_features)
    logistic_score, uncertainty, _, logistic_error = score_monitor(
        by_monitor["logistic_smoke"], zero_features
    )

    assert rule_score == pytest.approx(0.5)
    assert rule_error is None
    assert 0.0 < logistic_score < 0.5
    assert uncertainty is not None
    assert logistic_error is None


def test_evaluation_cohorts_preserve_primary_and_audit_boundaries() -> None:
    cohorts = _json(STAGE_D2_EVALUATION_COHORTS)["cohorts"]

    primary = cohorts["real_negative_transfer_test"]
    workflow = cohorts["real_workflow_invalid_audit"]
    policy = cohorts["real_policy_negative_audit"]
    synthetic = cohorts["synthetic_reference_negative"]

    assert primary["trajectory_count"] == 51
    assert primary["checkpoint_count"] == 177
    assert primary["all_primary_labels_negative"] is True
    assert primary["used_for_monitor_fitting"] is False
    assert primary["used_for_threshold_tuning"] is False
    assert primary["used_for_calibration_fitting"] is False
    assert workflow["trajectory_count"] == 9
    assert workflow["checkpoint_count"] == 31
    assert workflow["included_in_primary_specificity"] is False
    assert policy["policy_evaluation_count"] == 16
    assert policy["independent_trajectory_counted"] is False
    assert synthetic["record_count"] == 12
    assert synthetic["used_for_refitting"] is False


@pytest.mark.parametrize("record", _jsonl(STAGE_D2_CHECKPOINT_SCORES)[:64])
def test_checkpoint_score_records_are_negative_offline_evaluations(record: dict[str, Any]) -> None:
    required = {
        "monitor_id",
        "record_id",
        "trajectory_id",
        "source_cohort",
        "raw_score",
        "alert",
        "abstain",
        "coverage",
        "threshold",
        "target_label",
        "false_positive",
        "runtime_error_status",
        "feature_payload_hash",
    }

    assert required.issubset(record)
    assert record["source_cohort"] in {
        "real_negative_transfer_test",
        "real_workflow_invalid_audit",
    }
    assert record["target_label"] == "negative"
    assert record["runtime_error_status"] is None
    assert record["threshold"] == 0.5
    assert "provider" not in record
    assert "tokens" not in record
    assert "cost" not in record


@pytest.mark.parametrize("record", _jsonl(STAGE_D2_TRAJECTORY_SCORES)[:64])
def test_trajectory_scores_use_frozen_any_alert_aggregation(record: dict[str, Any]) -> None:
    assert record["aggregation_rule"] == "phase7_stage_d2_max_score_any_alert_v1"
    assert record.get("target_label", "negative") == "negative"
    assert record["threshold"] == 0.5
    assert record["coverage"] is True
    assert record["checkpoint_count"] >= 1
    assert record["source_cohort"] in {
        "real_negative_transfer_test",
        "real_workflow_invalid_audit",
    }


def test_real_negative_metrics_report_only_negative_supported_quantities() -> None:
    payload = _json(STAGE_D2_REAL_NEGATIVE_METRICS)
    by_key = {
        (row["monitor_id"], row["unit_of_analysis"]): row for row in payload["records"]
    }

    assert payload["real_only_recall_reported"] is False
    assert payload["real_only_precision_reported"] is False
    assert payload["real_only_auroc_reported_as_meaningful"] is False
    assert payload["real_only_pr_auc_reported_as_meaningful"] is False
    assert payload["real_positive_calibration_claimed"] is False
    for monitor_id in ["constant_negative_v1", "constant_smoke", "logistic_smoke"]:
        checkpoint = by_key[(monitor_id, "checkpoint")]
        trajectory = by_key[(monitor_id, "trajectory")]
        assert checkpoint["records"] == 177
        assert trajectory["records"] == 51
        assert checkpoint["false_positive_rate_among_covered"] == 0.0
        assert checkpoint["specificity_among_covered"] == 1.0
        assert trajectory["false_positive_rate_among_covered"] == 0.0
        assert trajectory["specificity_among_covered"] == 1.0
    rule_checkpoint = by_key[("rule_based_monitor_v1", "checkpoint")]
    assert rule_checkpoint["false_positive_rate_among_covered"] == 1.0
    assert by_key[("rule_based_monitor_v1", "trajectory")]["specificity_among_covered"] == 0.0


def test_abstention_and_negative_calibration_are_diagnostic_only() -> None:
    abstention = _json(STAGE_D2_ABSTENTION_METRICS)
    calibration = _json(STAGE_D2_NEGATIVE_CALIBRATION)

    assert abstention["threshold_sweep_is_posthoc_diagnostic_only"] is True
    assert abstention["new_operating_point_selected"] is False
    assert {row["coverage"] for row in abstention["records"]} == {1.0}
    assert {row["abstention_rate"] for row in abstention["records"]} == {0.0}
    assert calibration["real_positive_support_present"] is False
    assert calibration["full_calibration_validation_claimed"] is False
    assert calibration["negative_outcome_diagnostic_only"] is True
    assert all(row["calibration_slope_identifiable"] is False for row in calibration["records"])


def test_score_shift_is_descriptive_and_uses_synthetic_reference_only() -> None:
    payload = _json(STAGE_D2_SCORE_SHIFT)

    assert payload["score_shift_claim_is_descriptive"] is True
    assert payload["synthetic_reference_negative_count"] == 12
    assert len(payload["records"]) == 4
    assert {row["synthetic_count"] for row in payload["records"]} == {12}
    assert all(row["wasserstein_distance"] >= 0.0 for row in payload["records"])
    assert all(row["jensen_shannon_divergence"] >= 0.0 for row in payload["records"])


def test_synthetic_reference_scoring_does_not_read_manifest_from_disk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cohorts = _json(STAGE_D2_EVALUATION_COHORTS)
    monitor = _records_by_monitor(STAGE_D2_MONITOR_MANIFEST)["constant_negative_v1"]
    monkeypatch.setattr(
        stage_d2,
        "PHASE5_EXAMPLES_PARQUET",
        Path("__missing_ci_reference__.parquet"),
    )

    scores = score_synthetic_reference(
        cohorts=cohorts,
        monitor_manifest={"records": [monitor]},
    )

    assert len(scores) == 12
    assert {row["monitor_id"] for row in scores} == {"constant_negative_v1"}
    assert {row["raw_score"] for row in scores} == {0.0}


def test_feature_drift_records_expected_limitations_without_invalidating_scores() -> None:
    payload = _json(STAGE_D2_FEATURE_DRIFT)

    assert payload["feature_count"] == len(PHASE5_FEATURE_NAMES)
    assert payload["negligible_drift_count"] == 12
    assert payload["mild_drift_count"] == 5
    assert payload["moderate_drift_count"] == 7
    assert payload["severe_drift_count"] == 3
    assert payload["unscorable_drift_count"] == 0
    assert payload["unseen_category_count"] == 0
    assert payload["range_violation_count"] == 887
    assert payload["feature_drift_invalidates_scores"] is False
    assert {row["drift_severity"] for row in payload["records"]}.issubset(
        {"negligible", "mild", "moderate", "severe", "unscorable"}
    )


def test_subgroup_metrics_workflow_and_policy_audits_are_separated() -> None:
    subgroups = _json(STAGE_D2_SUBGROUP_METRICS)
    workflow = _json(STAGE_D2_WORKFLOW_INVALID_AUDIT)
    policy = _json(STAGE_D2_POLICY_NEGATIVE_AUDIT)

    assert set(subgroups["subgroup_fields"]) == {
        "domain",
        "architecture",
        "depth",
        "behavior_profile",
        "seen_status",
        "workflow_semantic_status",
        "role",
        "checkpoint_type",
    }
    assert subgroups["records"]
    assert workflow["cohort_separated_from_primary_specificity"] is True
    assert all(row["included_in_primary_specificity"] is False for row in workflow["records"])
    assert policy["policy_evaluations_are_not_independent_trajectories"] is True
    assert {row["policy_evaluation_count"] for row in policy["records"]} == {16}
    assert all(row["nonindependent_policy_evaluations"] is True for row in policy["records"])


def test_monitor_comparison_and_recommendation_make_no_safety_ranking() -> None:
    comparison = _json(STAGE_D2_MONITOR_COMPARISON)
    recommendation = _json(STAGE_D2_STAGE_E_RECOMMENDATION)
    unavailable = [row for row in comparison["records"] if not row["available"]]

    assert comparison["descriptive_only"] is True
    assert comparison["safety_ranking_claimed"] is False
    assert unavailable
    assert {row["reason"] for row in unavailable} == {"monitor_ineligible_or_missing"}
    assert recommendation["primary_candidates"] == ["logistic_smoke"]
    assert recommendation["secondary_candidates"] == ["rule_based_monitor_v1"]
    assert recommendation["baseline_only_monitors"] == [
        "constant_negative_v1",
        "constant_smoke",
    ]
    assert recommendation["repair_required_monitors"] == []
    assert recommendation["selection_based_on_positive_case_performance"] is False


def test_stage_d2_decision_branch_ready() -> None:
    decision = build_stage_d2_decision(**_decision_inputs())

    assert decision["stage_d2_status"] == "passed"
    assert decision["monitor_stack_decision"] == "monitor_stack_ready_for_stage_e"
    assert decision["stage_e_readiness"] == "ready_for_stage_e_with_monitor_limitations"


def test_stage_d2_decision_branch_feature_repair_required() -> None:
    inputs = _decision_inputs()
    inputs["compatibility"] = copy.deepcopy(inputs["compatibility"])
    inputs["compatibility"]["incompatible_monitor_count"] = 1

    decision = build_stage_d2_decision(**inputs)

    assert decision["monitor_stack_decision"] == "feature_or_split_repair_required"
    assert decision["stage_e_readiness"] == "ready_after_offline_repair"


def test_stage_d2_decision_branch_insufficient_coverage() -> None:
    inputs = _decision_inputs()
    inputs["cohorts"] = copy.deepcopy(inputs["cohorts"])
    inputs["cohorts"]["cohorts"]["real_negative_transfer_test"]["checkpoint_count"] = 1

    decision = build_stage_d2_decision(**inputs)

    assert decision["monitor_stack_decision"] == "insufficient_real_negative_coverage"
    assert decision["stage_e_readiness"] == "not_ready"


def test_stage_d2_decision_branch_monitor_repair_required() -> None:
    inputs = _decision_inputs()
    inputs["workflow_invalid"] = copy.deepcopy(inputs["workflow_invalid"])
    inputs["workflow_invalid"]["records"] = []

    decision = build_stage_d2_decision(**inputs)

    assert decision["monitor_stack_decision"] == "monitor_repair_required"
    assert decision["stage_e_readiness"] == "ready_after_offline_repair"


def test_stage_d2_decision_branch_not_ready_without_nontrivial_monitor() -> None:
    inputs = _decision_inputs()
    inputs["monitor_manifest"] = copy.deepcopy(inputs["monitor_manifest"])
    inputs["monitor_manifest"]["records"] = [
        row
        for row in inputs["monitor_manifest"]["records"]
        if row["monitor_id"].startswith("constant")
    ]

    decision = build_stage_d2_decision(**inputs)

    assert decision["monitor_stack_decision"] == "not_ready"
    assert decision["stage_e_readiness"] == "not_ready"


def test_stage_e_readiness_rejects_invalid_value() -> None:
    decision = {**_json(STAGE_D2_DECISION), "stage_e_readiness": "bogus"}

    with pytest.raises(ValueError):
        build_stage_e_readiness(decision=decision, current_commit="test")


def test_stage_d2_source_does_not_execute_disallowed_work() -> None:
    source = inspect.getsource(stage_d2)
    forbidden_terms = [
        "make_" + "provider_request",
        "execute_" + "provider_or_cached",
        "train_" + "monitor",
        "fit_" + "calibrator",
        "fit_" + "calibration_on_real",
        "run_" + "strategic",
        "run_" + "stage_e",
        "phase8_started = True",
    ]

    for term in forbidden_terms:
        assert term not in source


def test_stage_d2_tests_do_not_contain_provider_client_calls() -> None:
    test_source = Path(__file__).read_text(encoding="utf-8")
    forbidden_terms = [
        "make_" + "provider_request",
        "execute_" + "provider_or_cached",
        "openai." + "OpenAI",
        "responses." + "create",
        "chat.completions." + "create",
    ]

    for term in forbidden_terms:
        assert term not in test_source
