from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from typing import Any, cast

import pytest

import bayesaudit.pilot.stage_d1 as stage_d1
from bayesaudit.pilot.stage_d1 import (
    STAGE_D1_ANNOTATION_MANIFEST,
    STAGE_D1_CHECKPOINT_INDEX,
    STAGE_D1_CLASS_SUFFICIENCY,
    STAGE_D1_DECISION,
    STAGE_D1_FEATURE_LEAKAGE_AUDIT,
    STAGE_D1_INCLUSION_MANIFEST,
    STAGE_D1_INTEGRITY_REPORT,
    STAGE_D1_LABEL_REGISTRY,
    STAGE_D1_LINEAGE_MANIFEST,
    STAGE_D1_METRIC_FEASIBILITY,
    STAGE_D1_PRIMARY_LABEL_RESOLUTION,
    STAGE_D1_RUNTIME_FEATURE_SCHEMA,
    STAGE_D1_SCORER_CONSISTENCY,
    STAGE_D1_SOURCE_INVENTORY,
    STAGE_D1_SPLIT_LEAKAGE_MATRIX,
    STAGE_D1_SPLIT_MANIFEST,
    STAGE_D1_STAGE_D2_PROTOCOL,
    STAGE_D1_TRAJECTORY_INDEX,
    STAGE_D2_READINESS,
    build_stage_d1_decision,
    build_stage_d2_readiness,
    policy_evaluation_records,
    provider_ledger_state,
    validate_stage_d1_artifacts,
)


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _bundle_for_decision() -> dict[str, Any]:
    return {
        "integrity": _json(STAGE_D1_INTEGRITY_REPORT),
        "leakage_audit": _json(STAGE_D1_FEATURE_LEAKAGE_AUDIT),
        "split_leakage": _json(STAGE_D1_SPLIT_LEAKAGE_MATRIX),
        "class_sufficiency": _json(STAGE_D1_CLASS_SUFFICIENCY),
        "scorer_consistency": _json(STAGE_D1_SCORER_CONSISTENCY),
        "annotation_manifest": _json(STAGE_D1_ANNOTATION_MANIFEST),
        "metric_feasibility": _json(STAGE_D1_METRIC_FEASIBILITY),
    }


@pytest.mark.parametrize(
    "path",
    [
        STAGE_D1_SOURCE_INVENTORY,
        STAGE_D1_INTEGRITY_REPORT,
        STAGE_D1_TRAJECTORY_INDEX,
        STAGE_D1_CHECKPOINT_INDEX,
        STAGE_D1_LABEL_REGISTRY,
        STAGE_D1_PRIMARY_LABEL_RESOLUTION,
        STAGE_D1_LINEAGE_MANIFEST,
        STAGE_D1_INCLUSION_MANIFEST,
        STAGE_D1_RUNTIME_FEATURE_SCHEMA,
        STAGE_D1_FEATURE_LEAKAGE_AUDIT,
        STAGE_D1_SPLIT_MANIFEST,
        STAGE_D1_SPLIT_LEAKAGE_MATRIX,
        STAGE_D1_CLASS_SUFFICIENCY,
        STAGE_D1_SCORER_CONSISTENCY,
        STAGE_D1_ANNOTATION_MANIFEST,
        STAGE_D1_METRIC_FEASIBILITY,
        STAGE_D1_STAGE_D2_PROTOCOL,
        STAGE_D1_DECISION,
        STAGE_D2_READINESS,
    ],
)
def test_stage_d1_artifacts_exist_and_parse(path: Path) -> None:
    assert path.exists()
    if path.suffix == ".jsonl":
        assert _jsonl(path)
    else:
        assert _json(path)["schema_version"].startswith("bayesaudit.real_pilot_dataset.v1")


def test_stage_d1_artifact_validator_passes() -> None:
    assert validate_stage_d1_artifacts() == {"valid": True, "errors": []}


def test_stage_d1_enforces_zero_provider_calls_and_disables_d2() -> None:
    decision = _json(STAGE_D1_DECISION)
    protocol = _json(STAGE_D1_STAGE_D2_PROTOCOL)
    readiness = _json(STAGE_D2_READINESS)

    assert decision["provider_calls_made"] == 0
    assert decision["monitor_training_was_run"] is False
    assert decision["monitor_transfer_was_run"] is False
    assert decision["calibration_was_run"] is False
    assert decision["ood_evaluation_was_run"] is False
    assert decision["strategic_attackers_were_run"] is False
    assert protocol["stage_d2_was_run"] is False
    assert readiness["stage_d2_was_run"] is False


def test_provider_ledgers_remain_at_stage_c_counts() -> None:
    ledgers = _json(STAGE_D1_INTEGRITY_REPORT)["provider_ledger_state"]

    assert ledgers["phase7_stage_c1"]["status_counts"] == {"completed": 72, "cached": 12}
    assert ledgers["phase7_stage_c2"]["status_counts"] == {"completed": 72, "cached": 12}
    assert ledgers["phase7_stage_c2b"]["status_counts"] == {"completed": 16}
    assert ledgers["phase7_stage_c3"]["provider_requests_caused"] == 0
    assert ledgers["cached_execution_total"] == 24

    local_ledgers = provider_ledger_state()
    if local_ledgers["phase7_stage_c1"]["status_counts"]:
        assert local_ledgers == ledgers


def test_source_inventory_contains_real_and_synthetic_sources() -> None:
    inventory = _json(STAGE_D1_SOURCE_INVENTORY)
    source_types = {row["source_type"] for row in inventory["records"]}

    assert inventory["source_count"] == 30
    assert inventory["usable_source_count"] == 30
    assert {"real_model", "synthetic"}.issubset(source_types)
    assert "phase7_stage_c3" in inventory["real_source_stages"]
    assert "phase6_smoke" in inventory["synthetic_source_stages"]
    assert inventory["provider_calls_made"] == 0


@pytest.mark.parametrize("source", _json(STAGE_D1_SOURCE_INVENTORY)["records"])
def test_source_inventory_records_have_required_fields(source: dict[str, Any]) -> None:
    required = {
        "source_id",
        "source_stage",
        "location",
        "tracked_or_ignored",
        "artifact_type",
        "record_count",
        "hash",
        "usable_for_dataset_construction",
        "integrity_status",
    }

    assert required.issubset(source)
    assert source["record_count"] >= 0
    assert source["integrity_status"] != "missing"
    assert source["record_hash"]


def test_integrity_report_records_nonblocking_schema_warnings_only() -> None:
    integrity = _json(STAGE_D1_INTEGRITY_REPORT)

    assert integrity["blocking_issue_count"] == 0
    assert integrity["issue_count"] == 2
    assert integrity["real_track_integrity_valid"] is True
    assert all(issue["severity"] != "blocking" for issue in integrity["issues"])
    assert integrity["raw_artifacts_remain_ignored"] is True


def test_runtime_schemas_define_required_record_shapes() -> None:
    schema = _json(STAGE_D1_RUNTIME_FEATURE_SCHEMA)
    schemas = schema["schemas"]

    for name in ["trajectory", "checkpoint", "label", "policy_evaluation"]:
        assert name in schemas
        assert schema["schema_hashes"][name]
    assert "trajectory_id" in schemas["trajectory"]
    assert "checkpoint_id" in schemas["checkpoint"]
    assert "label_version" in schemas["label"]
    assert "policy_information_boundary_status" in schemas["policy_evaluation"]


@pytest.mark.parametrize("record", _jsonl(STAGE_D1_TRAJECTORY_INDEX))
def test_trajectory_index_records_match_schema(record: dict[str, Any]) -> None:
    fields = set(_json(STAGE_D1_RUNTIME_FEATURE_SCHEMA)["schemas"]["trajectory"])

    assert fields.issubset(record)
    assert record["real_or_synthetic"] in {"real", "synthetic"}
    assert record["source_type"] in {"real_model", "synthetic"}
    assert record["raw_text_redacted"] is True
    assert record["trajectory_lineage_id"].startswith("lineage_")


@pytest.mark.parametrize("record", _jsonl(STAGE_D1_CHECKPOINT_INDEX))
def test_checkpoint_index_records_match_schema(record: dict[str, Any]) -> None:
    fields = set(_json(STAGE_D1_RUNTIME_FEATURE_SCHEMA)["schemas"]["checkpoint"])

    assert fields.issubset(record)
    assert record["runtime_feature_view_version"] == "runtime_observable_v1"
    assert record["posthoc_feature_view_version"] == "posthoc_analysis_v1"
    assert record["future_information_present"] is False
    assert record["label_fields_present"] is False
    assert record["observable_artifact_hash"]


def test_label_registry_preserves_historical_repaired_and_adjudicated_versions() -> None:
    registry = _json(STAGE_D1_LABEL_REGISTRY)
    names = {row["label_name"] for row in registry["entries"]}

    assert "privacy:v1" in names
    assert "privacy:v2" in names
    assert "stage_c1a_adjudication" in names
    assert "observable_risk:v1" in names
    assert "observable_risk:v2" in names
    assert "stage_c2c_adjudication" in names
    assert registry["diagnostic_labels_cannot_replace_objective_labels"] is True


@pytest.mark.parametrize("record", _jsonl(STAGE_D1_PRIMARY_LABEL_RESOLUTION))
def test_primary_label_resolution_is_deterministic_and_keeps_lower_labels(
    record: dict[str, Any],
) -> None:
    assert record["resolution_hash"]
    assert record["label_precedence_applied"][0] == "developer_adjudication"
    assert record["lower_priority_labels_preserved"] >= 1
    assert record["treatment_uptake_used_as_objective_label"] is False


def test_real_primary_labels_have_zero_objective_positives_after_repairs() -> None:
    resolutions = _jsonl(STAGE_D1_PRIMARY_LABEL_RESOLUTION)
    real = [row for row in resolutions if row["real_or_synthetic"] == "real"]

    assert sum(row["primary_objective_label_value"] == "positive" for row in real) == 0
    assert sum(row["primary_objective_label_value"] == "negative" for row in real) >= 60


def test_observable_risk_adjudications_resolve_to_negative_or_stylistic() -> None:
    resolutions = _jsonl(STAGE_D1_PRIMARY_LABEL_RESOLUTION)
    adjudicated = [
        row
        for row in resolutions
        if row["primary_observable_risk_value"]
        in {"ordinary_negative", "stylistic_opportunism"}
    ]

    assert len(adjudicated) >= 4
    assert all(row["primary_objective_label_value"] == "negative" for row in adjudicated)


def test_lineage_and_deduplication_counts_are_frozen() -> None:
    lineage = _json(STAGE_D1_LINEAGE_MANIFEST)

    assert lineage["trajectory_record_count"] == 69
    assert lineage["checkpoint_record_count"] == 242
    assert lineage["duplicate_execution_count"] == 4
    assert lineage["cached_execution_count_excluded"] == 24
    assert lineage["rescoring_records_excluded_as_trajectories"] == 24
    assert lineage["policy_evaluations_kept_separate"] == 16


def test_inclusion_manifest_keeps_workflow_and_policy_audits_separate() -> None:
    inclusion = _json(STAGE_D1_INCLUSION_MANIFEST)

    assert inclusion["real_primary_count"] == 51
    assert inclusion["real_workflow_audit_count"] == 9
    assert inclusion["policy_audit_count"] == 16
    assert "included_policy_audit" in inclusion["rules"]
    assert inclusion["synthetic_positive_challenge_status"] == (
        "insufficient_for_group_disjoint_fitting"
    )


def test_policy_evaluation_records_are_not_trajectories() -> None:
    policy_records = policy_evaluation_records(current_commit="test")
    trajectory_ids = {row["dataset_record_id"] for row in _jsonl(STAGE_D1_TRAJECTORY_INDEX)}

    assert len(policy_records) == 16
    assert all(row["record_kind"] == "policy_evaluation" for row in policy_records)
    assert not any(row["dataset_record_id"] in trajectory_ids for row in policy_records)


@pytest.mark.parametrize("record", policy_evaluation_records(current_commit="test"))
def test_policy_evaluation_schema_and_budget_fields(record: dict[str, Any]) -> None:
    fields = set(_json(STAGE_D1_RUNTIME_FEATURE_SCHEMA)["schemas"]["policy_evaluation"])

    assert fields.issubset(record)
    assert record["provider_requests_caused"] == 0
    assert record["token_overhead"] == 0
    assert record["cost_overhead"] == "0"
    assert record["policy_information_boundary_status"] == "passed"


def test_runtime_feature_allowlist_and_denylist_are_separated() -> None:
    schema = _json(STAGE_D1_RUNTIME_FEATURE_SCHEMA)
    runtime = schema["runtime_observable_view"]
    posthoc = schema["posthoc_analysis_view"]

    assert schema["runtime_feature_count"] == 14
    assert schema["denied_feature_count"] == 17
    assert "objective_scorer_results" in runtime["denied_features"]
    assert "adjudicated_labels" in runtime["denied_features"]
    assert "source_stage" in runtime["denied_features"]
    assert posthoc["may_be_used_as_monitor_input"] is False


@pytest.mark.parametrize("record", _json(STAGE_D1_FEATURE_LEAKAGE_AUDIT)["records"])
def test_feature_leakage_audit_records_allow_or_repair_each_feature(
    record: dict[str, Any],
) -> None:
    assert record["feature_name"]
    assert record["test_coverage"] == "tests/test_stage_d1.py"
    if record["allowed"]:
        assert record["repair_action"] == "none_required"
    else:
        assert record["repair_action"] == "exclude_from_runtime_observable_v1"
        assert record["leakage_type"] is not None


def test_feature_leakage_audit_passes_after_repair_actions() -> None:
    audit = _json(STAGE_D1_FEATURE_LEAKAGE_AUDIT)

    assert audit["passes"] is True
    assert audit["leakage_issues_found"] == 17
    assert audit["leakage_issues_repaired"] == 17
    assert audit["allowed_feature_count"] == 14
    assert audit["denied_feature_count"] == 17


def test_split_manifest_keeps_real_and_synthetic_tracks_separate() -> None:
    split = _json(STAGE_D1_SPLIT_MANIFEST)

    assert split["split_plan_version"] == "phase7_stage_d1_real_negative_only_v1"
    assert split["split_counts"]["real_negative_transfer_test"] == 51
    assert split["split_counts"]["real_workflow_invalid_audit"] == 9
    assert split["split_counts"]["real_policy_negative_audit"] == 16
    assert split["split_counts"]["synthetic_id_test"] == 27
    assert split["split_counts"]["synthetic_ood_attack_test"] == 12
    assert split["real_records_in_synthetic_train"] == 0
    assert split["real_records_in_synthetic_calibration"] == 0
    assert split["real_labels_used_for_threshold_tuning"] is False
    assert split["synthetic_real_tracks_separate"] is True


@pytest.mark.parametrize("record", _json(STAGE_D1_SPLIT_LEAKAGE_MATRIX)["records"])
def test_split_leakage_matrix_has_no_prohibited_overlap(record: dict[str, Any]) -> None:
    assert record["record_id_overlap_count"] == 0
    assert record["prohibited_overlap"] is False
    if record["protected_group_overlap_count"]:
        assert record["relation_overlap_allowed"] is True


def test_split_leakage_matrix_passes_all_pair_checks() -> None:
    matrix = _json(STAGE_D1_SPLIT_LEAKAGE_MATRIX)

    assert matrix["passes"] is True
    assert matrix["prohibited_split_overlap_count"] == 0
    assert "counterfactual_group" in matrix["tested_overlap_types"]
    assert "matched_condition" in matrix["tested_overlap_types"]


def test_synthetic_train_and_calibration_are_empty_pending_repair() -> None:
    split = _json(STAGE_D1_SPLIT_MANIFEST)

    assert split["splits"]["synthetic_train"]["status"] == "empty_pending_synthetic_repair"
    assert split["splits"]["synthetic_calibration"]["status"] == (
        "empty_pending_synthetic_repair"
    )
    assert "synthetic_train" not in split["split_counts"]
    assert "synthetic_calibration" not in split["split_counts"]


def test_class_sufficiency_supports_real_negative_only() -> None:
    sufficiency = _json(STAGE_D1_CLASS_SUFFICIENCY)

    assert sufficiency["class_sufficiency_result"] == "real_negative_only_ready"
    assert sufficiency["real_support"]["specificity"] is True
    assert sufficiency["real_support"]["false_positive_rate"] is True
    assert sufficiency["real_support"]["recall"] is False
    assert sufficiency["real_support"]["pr_auc"] is False
    assert sufficiency["synthetic_support"]["overall_monitor_fitting"] is False
    assert sufficiency["synthetic_support"]["calibration"] is False


def test_phase6_attack_and_mutation_families_are_grouped() -> None:
    checkpoints = _jsonl(STAGE_D1_CHECKPOINT_INDEX)
    attack_rows = [
        row for row in checkpoints if row.get("synthetic_anchor_type") == "phase6_attack_event"
    ]

    assert len(attack_rows) == 12
    assert {row["split_group_ids"]["attack_family_group"] for row in attack_rows} == {
        "privacy_internal_identifier_leak"
    }
    assert {row["split_group_ids"]["mutation_family_group"] for row in attack_rows} == {
        "privacy_internal_identifier_leak"
    }


def test_scorer_consistency_resolves_known_disagreements() -> None:
    consistency = _json(STAGE_D1_SCORER_CONSISTENCY)
    by_family = {row["domain_or_label_family"]: row for row in consistency["records"]}

    assert consistency["disagreement_count"] == 12
    assert consistency["resolved_disagreement_count"] == 12
    assert consistency["unresolved_disagreement_count"] == 0
    assert by_family["privacy"]["disagreement_count"] == 8
    assert by_family["observable_risk"]["disagreement_count"] == 4
    assert consistency["observable_risk_not_used_as_objective_label"] is True


def test_annotation_manifest_freezes_expected_sampling_strata() -> None:
    manifest = _json(STAGE_D1_ANNOTATION_MANIFEST)

    assert manifest["item_count"] == 36
    assert manifest["historical_disagreement_item_count"] == 12
    assert manifest["real_negative_item_count"] == 12
    assert manifest["synthetic_anchor_item_count"] == 12
    assert manifest["independent_human_annotations_performed"] == 0
    assert manifest["developer_review_not_independent_human_agreement"] is True
    assert manifest["frozen_before_packet_review"] is True


@pytest.mark.parametrize("item", _json(STAGE_D1_ANNOTATION_MANIFEST)["items"])
def test_annotation_manifest_items_hide_labels_before_review(item: dict[str, Any]) -> None:
    assert item["original_label_hidden"] is True
    assert item["scorer_output_hidden"] is True
    assert item["architecture_hidden"] is True
    assert item["behavior_hidden"] is True
    assert len(item["manifest_hash"]) == 64
    assert len(item["item_hash"]) == 64


def test_blind_and_adjudication_packets_are_generated_and_redacted() -> None:
    manifest = _json(STAGE_D1_ANNOTATION_MANIFEST)
    blind_dir = Path(manifest["blind_packet_dir"])
    adjudication_dir = Path(manifest["adjudication_packet_dir"])
    blind_packets = sorted(blind_dir.glob("*.json"))
    adjudication_packets = sorted(adjudication_dir.glob("*.json"))

    assert len(blind_packets) == manifest["item_count"]
    assert len(adjudication_packets) == manifest["item_count"]
    blind = _json(blind_packets[0])
    adjudication = _json(adjudication_packets[0])
    assert blind["automated_labels_hidden"] is True
    assert blind["scorer_outputs_hidden"] is True
    assert blind["raw_text_included"] is False
    assert "known_label_reference" in adjudication
    assert adjudication["developer_review_only"] is True
    assert adjudication["independent_review_completed"] is False
    assert adjudication["raw_text_included"] is False


def test_metric_feasibility_prohibits_real_positive_metrics() -> None:
    metrics = _json(STAGE_D1_METRIC_FEASIBILITY)

    assert metrics["real_metrics_supported"] == [
        "specificity",
        "false_positive_rate",
        "alert_rate",
        "abstention_rate",
        "negative_log_likelihood",
        "brier_score",
    ]
    assert "recall" in metrics["real_metrics_prohibited"]
    assert "pr_auc" in metrics["real_metrics_prohibited"]
    assert "auroc" in metrics["real_metrics_prohibited"]
    assert metrics["synthetic_metrics_supported"] == []
    assert metrics["real_only_recall_prohibited"] is True
    assert metrics["real_only_pr_auc_prohibited"] is True


@pytest.mark.parametrize("record", _json(STAGE_D1_METRIC_FEASIBILITY)["records"])
def test_metric_registry_has_interpretation_for_each_metric(record: dict[str, Any]) -> None:
    assert record["metric_name"]
    assert record["track"] in {"track_a", "track_b"}
    assert record["required_score_type"] == "frozen_monitor_score"
    assert record["allowed_interpretation"]


def test_stage_d2_protocol_is_design_only_and_dual_track_separated() -> None:
    protocol = _json(STAGE_D1_STAGE_D2_PROTOCOL)

    assert protocol["stage_d2_was_run"] is False
    assert protocol["training"]["allowed_training_split"] == "synthetic_train"
    assert protocol["training"]["train_on_real_pilot_labels"] is False
    assert protocol["training"]["use_posthoc_features"] is False
    assert protocol["calibration"]["fit_on_real_pilot_labels"] is False
    assert protocol["reporting"]["pool_synthetic_and_real_headline_metric"] is False


def test_stage_d1_decision_selects_real_negative_only_readiness() -> None:
    decision = _json(STAGE_D1_DECISION)
    readiness = _json(STAGE_D2_READINESS)

    assert decision["stage_d1_status"] == "passed"
    assert decision["dataset_decision"] == "dataset_ready_real_negative_only"
    assert decision["stage_d2_readiness"] == "ready_for_stage_d2_real_negative_only"
    assert readiness["stage_d2_readiness"] == "ready_for_stage_d2_real_negative_only"
    assert decision["benchmark_status"] == "not_ready_to_freeze"
    assert all(decision["completion_checks"].values())


def test_stage_d1_decision_dual_track_branch() -> None:
    bundle = _bundle_for_decision()
    bundle["class_sufficiency"] = copy.deepcopy(bundle["class_sufficiency"])
    bundle["class_sufficiency"]["synthetic_support"]["overall_monitor_fitting"] = True
    bundle["class_sufficiency"]["synthetic_support"]["calibration"] = True

    decision = build_stage_d1_decision(current_commit="test", **bundle)

    assert decision["dataset_decision"] == "dataset_ready_dual_track"
    assert decision["stage_d2_readiness"] == "ready_for_stage_d2_dual_track"


def test_stage_d1_decision_offline_repair_branch() -> None:
    bundle = _bundle_for_decision()
    bundle["split_leakage"] = {**bundle["split_leakage"], "passes": False}

    decision = build_stage_d1_decision(current_commit="test", **bundle)

    assert decision["dataset_decision"] == "dataset_repair_required"
    assert decision["stage_d2_readiness"] == "ready_after_offline_repair"


def test_stage_d1_decision_not_ready_branch() -> None:
    bundle = _bundle_for_decision()
    bundle["integrity"] = {
        **bundle["integrity"],
        "real_track_integrity_valid": False,
        "blocking_issue_count": 1,
    }

    decision = build_stage_d1_decision(current_commit="test", **bundle)

    assert decision["dataset_decision"] == "dataset_not_ready"
    assert decision["stage_d2_readiness"] == "not_ready"


def test_stage_d2_readiness_rejects_invalid_value() -> None:
    decision = {**_json(STAGE_D1_DECISION), "stage_d2_readiness": "bogus"}

    with pytest.raises(ValueError):
        build_stage_d2_readiness(decision=decision, current_commit="test")


def test_stage_d1_source_does_not_execute_disallowed_work() -> None:
    source = inspect.getsource(stage_d1)
    forbidden_terms = [
        "make_" + "provider_request",
        "execute_" + "provider_or_cached",
        "train_" + "monitor",
        "run_" + "monitor_transfer",
        "fit_" + "calibrator",
        "run_" + "ood",
        "run_" + "strategic",
        "run_" + "stage_e",
        "phase8_started = True",
    ]

    for term in forbidden_terms:
        assert term not in source


def test_stage_d1_tests_do_not_contain_provider_client_calls() -> None:
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
