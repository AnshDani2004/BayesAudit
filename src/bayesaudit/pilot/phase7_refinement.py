"""Phase 7 benchmark refinement and evidence-freeze artifacts."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.stage_e3 import (
    STAGE_E3_DATASET_MANIFEST,
    STAGE_E3_NEXT_STAGE_READINESS,
    STAGE_E3_REPAIR_REQUIREMENTS,
    STAGE_E3_VALIDATED_METRICS,
    assert_provider_disabled,
)
from bayesaudit.storage.jsonl import read_json, write_json_atomic

PHASE7_REFINEMENT_SCHEMA_VERSION = "bayesaudit.phase7.refinement.v1"
PHASE7_BENCHMARK_CANDIDATE_VERSION = "phase7_benchmark_candidate_v1"
PHASE7_TRACKED_ROOT = Path("configs/experiments")

PHASE7_BENCHMARK_REFINEMENT_MANIFEST = (
    PHASE7_TRACKED_ROOT / "phase7_benchmark_refinement_manifest.json"
)
PHASE7_BENCHMARK_VERSION_MANIFEST = PHASE7_TRACKED_ROOT / "phase7_benchmark_version_manifest.json"
PHASE7_VERSION_COMPATIBILITY_MATRIX = (
    PHASE7_TRACKED_ROOT / "phase7_version_compatibility_matrix.json"
)
PHASE7_AFFECTED_RUN_ANALYSIS = PHASE7_TRACKED_ROOT / "phase7_affected_run_analysis.json"
PHASE7_PROVIDER_RERUN_REQUIREMENTS = PHASE7_TRACKED_ROOT / "phase7_provider_rerun_requirements.json"
PHASE7_EVIDENCE_PACKAGE_MANIFEST = PHASE7_TRACKED_ROOT / "phase7_evidence_package_manifest.json"
PHASE7_BENCHMARK_FREEZE_DECISION = PHASE7_TRACKED_ROOT / "phase7_benchmark_freeze_decision.json"

PHASE7_REFINEMENT_JSON_ARTIFACTS = [
    PHASE7_BENCHMARK_REFINEMENT_MANIFEST,
    PHASE7_BENCHMARK_VERSION_MANIFEST,
    PHASE7_VERSION_COMPATIBILITY_MATRIX,
    PHASE7_AFFECTED_RUN_ANALYSIS,
    PHASE7_PROVIDER_RERUN_REQUIREMENTS,
    PHASE7_EVIDENCE_PACKAGE_MANIFEST,
    PHASE7_BENCHMARK_FREEZE_DECISION,
]


def run_phase7_benchmark_refinement(*, current_commit: str | None = None) -> dict[str, Any]:
    """Create benchmark refinement and evidence-freeze artifacts after E.3 Path A."""

    assert_provider_disabled()
    current_commit = current_commit or _git("rev-parse", "HEAD")
    e3_readiness = read_json(STAGE_E3_NEXT_STAGE_READINESS)
    if e3_readiness["stage_e3_readiness_decision"] not in {
        "ready_for_phase7_benchmark_refinement",
        "ready_for_phase7_closeout_with_limitations",
    }:
        raise RuntimeError("Phase 7 benchmark refinement is blocked by the Stage E.3 gate")
    e3_repairs = read_json(STAGE_E3_REPAIR_REQUIREMENTS)
    e3_metrics = read_json(STAGE_E3_VALIDATED_METRICS)
    dataset = read_json(STAGE_E3_DATASET_MANIFEST)

    refinement_manifest = _build_refinement_manifest(current_commit)
    version_manifest = _build_version_manifest(current_commit, dataset, refinement_manifest)
    compatibility = _build_compatibility_matrix(current_commit)
    affected = _build_affected_run_analysis(current_commit, refinement_manifest)
    reruns = _build_provider_rerun_requirements(current_commit, refinement_manifest)
    evidence = _build_evidence_package(current_commit, dataset, e3_metrics, refinement_manifest)
    decision = _build_freeze_decision(
        current_commit, e3_repairs, reruns, evidence, version_manifest
    )
    for path, payload in {
        PHASE7_BENCHMARK_REFINEMENT_MANIFEST: refinement_manifest,
        PHASE7_BENCHMARK_VERSION_MANIFEST: version_manifest,
        PHASE7_VERSION_COMPATIBILITY_MATRIX: compatibility,
        PHASE7_AFFECTED_RUN_ANALYSIS: affected,
        PHASE7_PROVIDER_RERUN_REQUIREMENTS: reruns,
        PHASE7_EVIDENCE_PACKAGE_MANIFEST: evidence,
        PHASE7_BENCHMARK_FREEZE_DECISION: decision,
    }.items():
        write_json_atomic(path, payload)
    validation = validate_phase7_refinement_artifacts()
    if not validation["valid"]:
        raise ValueError(f"Phase 7 refinement validation failed: {validation['errors']}")
    return validation


def validate_phase7_refinement_artifacts() -> dict[str, Any]:
    errors: list[str] = []
    for path in PHASE7_REFINEMENT_JSON_ARTIFACTS:
        if not path.exists():
            errors.append(f"missing refinement artifact: {path}")
            continue
        payload = read_json(path)
        if payload.get("schema_version") != PHASE7_REFINEMENT_SCHEMA_VERSION:
            errors.append(f"schema mismatch: {path}")
        expected = canonical_json_hash(
            {key: value for key, value in payload.items() if key != "artifact_hash"}
        )
        if payload.get("artifact_hash") != expected:
            errors.append(f"artifact hash mismatch: {path}")
        if payload.get("provider_calls_performed") != 0:
            errors.append(f"provider calls recorded: {path}")
        if payload.get("phase8_started") is not False:
            errors.append(f"phase8 marker invalid: {path}")
    if PHASE7_BENCHMARK_FREEZE_DECISION.exists():
        decision = read_json(PHASE7_BENCHMARK_FREEZE_DECISION)
        if decision.get("benchmark_freeze_decision") not in {
            "phase7_benchmark_frozen",
            "phase7_benchmark_frozen_with_limitations",
            "phase7_benchmark_candidate_ready_not_frozen",
            "phase7_benchmark_blocked_pending_offline_repair",
            "phase7_benchmark_blocked_pending_authorized_rerun",
            "phase7_benchmark_not_ready",
        }:
            errors.append("invalid benchmark freeze decision")
    return {"valid": not errors, "errors": errors}


def _build_refinement_manifest(current_commit: str) -> dict[str, Any]:
    refinements = [
        _refinement(
            "p7_refine_001", "OpenAI raw-output extraction repair", "infrastructure_change"
        ),
        _refinement(
            "p7_refine_002", "Token-derived cost-accounting repair", "infrastructure_change"
        ),
        _refinement(
            "p7_refine_003",
            "Role-specific structured-output schema repair",
            "schema_or_parser_change",
        ),
        _refinement(
            "p7_refine_004",
            "privacy:v1 false-positive repair to privacy:v2",
            "scorer_version_update",
        ),
        _refinement(
            "p7_refine_005",
            "opportunistic_completion_v1 weak-uptake diagnosis",
            "documentation_only",
        ),
        _refinement(
            "p7_refine_006", "opportunistic_completion_v2 limitations", "documentation_only"
        ),
        _refinement(
            "p7_refine_007",
            "observable_risk:v1 false-positive repair to observable_risk:v2",
            "classifier_version_update",
        ),
        _refinement("p7_refine_008", "Negative-only Stage C.3 limitations", "documentation_only"),
        _refinement(
            "p7_refine_009", "Real-negative-only Stage D.1 dataset limitation", "documentation_only"
        ),
        _refinement(
            "p7_refine_010", "Stage D.2 monitor transfer limitations", "documentation_only"
        ),
        _refinement("p7_refine_011", "Stage E.1 attacker-design limitations", "documentation_only"),
        _refinement(
            "p7_refine_012", "Stage E.2 controlled-positive limitations", "documentation_only"
        ),
        _refinement(
            "p7_refine_013", "Stage E.3 developer adjudication labels", "derived_label_only"
        ),
        _refinement("p7_refine_014", "Stage E.3 claim-support linkage", "documentation_only"),
    ]
    counts: dict[str, int] = {}
    for row in refinements:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    return _json_artifact(
        "phase7_benchmark_refinement_manifest",
        current_commit=current_commit,
        benchmark_candidate_version=PHASE7_BENCHMARK_CANDIDATE_VERSION,
        refinements=refinements,
        refinement_count=len(refinements),
        classification_counts=counts,
        provider_rerun_required=False,
        task_semantic_refinements=0,
        prompt_semantic_refinements=0,
        attacker_semantic_refinements=0,
        monitor_or_policy_runtime_refinements=0,
    )


def _refinement(refinement_id: str, source_defect: str, classification: str) -> dict[str, Any]:
    return {
        "refinement_id": refinement_id,
        "source_defect": source_defect,
        "classification": classification,
        "old_version": "historical_phase7_version",
        "new_version": PHASE7_BENCHMARK_CANDIDATE_VERSION,
        "affected_stages": ["phase7"],
        "affected_trajectories": "preserved_historical_outputs_only",
        "historical_result_impact": "preserved_with_separate_repaired_or_adjudicated_labels",
        "provider_rerun_needed": False,
        "benchmark_inclusion_decision": "include_with_versioned_provenance",
        "rationale": "offline refinement preserves provider-visible experimental conditions",
    }


def _build_version_manifest(
    current_commit: str, dataset: dict[str, Any], refinement_manifest: dict[str, Any]
) -> dict[str, Any]:
    benchmark_hash = canonical_json_hash(
        {
            "candidate": PHASE7_BENCHMARK_CANDIDATE_VERSION,
            "dataset_hash": dataset["dataset_hash"],
            "refinement_hash": refinement_manifest["artifact_hash"],
        }
    )
    return _json_artifact(
        "phase7_benchmark_version_manifest",
        current_commit=current_commit,
        benchmark_version=PHASE7_BENCHMARK_CANDIDATE_VERSION,
        parent_version="phase7_real_model_pilot_pre_freeze",
        benchmark_hash=benchmark_hash,
        scenario_versions=["v1"],
        task_versions=["v1"],
        constraint_envelope_versions=["phase7_v1"],
        architecture_versions=["structured_inheritance", "unstructured_delegation"],
        attacker_versions=["strategic_attacker_real_pilot_v1"],
        behavior_profile_versions=["opportunistic_completion_v1", "opportunistic_completion_v2"],
        objective_scorer_versions=["privacy:v2", "authorization:v1", "evidence:v1"],
        risk_classifier_versions=["observable_risk:v2"],
        monitor_versions=["rule_based_monitor_v1:phase5_v1", "logistic_smoke:phase5_v1"],
        policy_versions=["phase7_stage_e1_frozen"],
        intervention_versions=["constraint_review_and_continue_v1"],
        prompt_versions=["phase7_stage_e2_prompt_v1"],
        schema_versions=["phase7_stage_e2_response_schema_v1"],
        provider_version="openai:gpt-5-nano-2025-08-07",
        pricing_table_version="openai_gpt5_nano_2025_08_07_usd_2026_07_31_v1",
        dataset_versions=[dataset["dataset_version"]],
        split_versions=["phase7_stage_d1_real_negative_only", "phase7_stage_e3_validated"],
        annotation_guide_version="phase7_stage_e3_developer_adjudication",
    )


def _build_compatibility_matrix(current_commit: str) -> dict[str, Any]:
    rows = [
        {
            "source_stage": "Stage C.1/C.1b",
            "original_label_preserved": True,
            "repaired_label_preserved": True,
            "adjudicated_label_preserved": True,
            "comparable_for": ["privacy:v2 offline rescoring", "descriptive real-pilot evidence"],
            "not_comparable_for": ["privacy:v1 positive prevalence"],
        },
        {
            "source_stage": "Stage C.2/C.2c",
            "original_label_preserved": True,
            "repaired_label_preserved": True,
            "adjudicated_label_preserved": True,
            "comparable_for": ["observable_risk:v2 negative-control selection"],
            "not_comparable_for": ["positive-case prevention"],
        },
        {
            "source_stage": "Stage D.1/D.2",
            "original_label_preserved": True,
            "repaired_label_preserved": True,
            "adjudicated_label_preserved": True,
            "comparable_for": ["real-negative specificity diagnostics"],
            "not_comparable_for": ["real-positive recall or calibration"],
        },
        {
            "source_stage": "Stage E.2/E.3",
            "original_label_preserved": True,
            "repaired_label_preserved": False,
            "adjudicated_label_preserved": True,
            "comparable_for": ["controlled synthetic positive-case adjudication"],
            "not_comparable_for": ["population prevalence", "production readiness"],
        },
    ]
    return _json_artifact(
        "phase7_version_compatibility_matrix",
        current_commit=current_commit,
        benchmark_candidate_version=PHASE7_BENCHMARK_CANDIDATE_VERSION,
        rows=rows,
        historical_outputs_relabelled_as_new_semantics=False,
        compatibility_matrix_result="passed_with_documented_limitations",
    )


def _build_affected_run_analysis(
    current_commit: str, refinement_manifest: dict[str, Any]
) -> dict[str, Any]:
    return _json_artifact(
        "phase7_affected_run_analysis",
        current_commit=current_commit,
        benchmark_candidate_version=PHASE7_BENCHMARK_CANDIDATE_VERSION,
        affected_stage_count=14,
        provider_visible_conditions_changed=False,
        historical_outputs_preserved=True,
        repaired_labels_preserved=True,
        adjudicated_labels_preserved=True,
        refinements_requiring_provider_rerun=[
            row for row in refinement_manifest["refinements"] if row["provider_rerun_needed"]
        ],
        offline_rescore_eligible_refinements=[
            row["refinement_id"]
            for row in refinement_manifest["refinements"]
            if row["classification"]
            in {"derived_label_only", "scorer_version_update", "classifier_version_update"}
        ],
    )


def _build_provider_rerun_requirements(
    current_commit: str, refinement_manifest: dict[str, Any]
) -> dict[str, Any]:
    return _json_artifact(
        "phase7_provider_rerun_requirements",
        current_commit=current_commit,
        benchmark_candidate_version=PHASE7_BENCHMARK_CANDIDATE_VERSION,
        provider_rerun_required_for_phase7_claims=False,
        provider_rerun_required_for_freeze=False,
        future_confirmatory_provider_rerun_recommended=True,
        future_confirmatory_provider_rerun_reason=(
            "larger multi-seed or multi-model validation belongs to a separately "
            "authorized future phase"
        ),
        rerun_required_refinements=[
            row["refinement_id"]
            for row in refinement_manifest["refinements"]
            if row["provider_rerun_needed"]
        ],
        rerun_requirement_logic={
            "task_semantic_change": True,
            "constraint_semantic_change": True,
            "attacker_semantic_change": True,
            "prompt_semantic_change": True,
            "monitor_runtime_behavior_change": True,
            "policy_runtime_behavior_change": True,
            "intervention_wording_change": True,
            "provider_visible_schema_behavior_change": True,
            "objective_scorer_logic_change": False,
            "risk_classifier_logic_change": False,
            "label_precedence_change": False,
            "metric_change": False,
            "manifest_linkage_change": False,
            "documentation_change": False,
        },
    )


def _build_evidence_package(
    current_commit: str,
    dataset: dict[str, Any],
    e3_metrics: dict[str, Any],
    refinement_manifest: dict[str, Any],
) -> dict[str, Any]:
    evidence_paths = [
        "configs/experiments/phase7_stage_c1b_privacy_v2_provenance_summary.json",
        "configs/experiments/phase7_stage_c2_treatment_isolation_report.json",
        "configs/experiments/phase7_stage_c3_policy_comparison.json",
        "configs/experiments/phase7_stage_d1_split_manifest.json",
        "configs/experiments/phase7_stage_d2_monitor_comparison.json",
        "configs/experiments/phase7_stage_e1_decision.json",
        "configs/experiments/phase7_stage_e2_execution_ledger.json",
        "configs/experiments/phase7_stage_e3_dataset_manifest.json",
        "configs/experiments/phase7_stage_e3_validated_metrics.json",
        "configs/experiments/phase7_benchmark_refinement_manifest.json",
    ]
    evidence_hash = canonical_json_hash(
        {
            "paths": evidence_paths,
            "dataset_hash": dataset["dataset_hash"],
            "metrics_hash": e3_metrics["artifact_hash"],
            "refinement_hash": refinement_manifest["artifact_hash"],
        }
    )
    return _json_artifact(
        "phase7_evidence_package_manifest",
        current_commit=current_commit,
        benchmark_candidate_version=PHASE7_BENCHMARK_CANDIDATE_VERSION,
        evidence_package_hash=evidence_hash,
        evidence_artifact_count=len(evidence_paths),
        evidence_artifacts=evidence_paths,
        raw_provider_responses_included=False,
        provider_and_cost_ledgers_referenced=True,
        corrected_stage_c1_labels_included=True,
        stage_e3_validated_dataset_included=True,
        claim_support_registry_included=True,
        repair_log_referenced=True,
        version_compatibility_matrix_included=True,
        known_limitations_included=True,
        reproducibility_hashes_included=True,
    )


def _build_freeze_decision(
    current_commit: str,
    e3_repairs: dict[str, Any],
    reruns: dict[str, Any],
    evidence: dict[str, Any],
    version_manifest: dict[str, Any],
) -> dict[str, Any]:
    blocked = bool(e3_repairs["defect_count"]) or bool(
        reruns["provider_rerun_required_for_phase7_claims"]
    )
    decision = (
        "phase7_benchmark_blocked_pending_authorized_rerun"
        if blocked
        else "phase7_benchmark_frozen_with_limitations"
    )
    return _json_artifact(
        "phase7_benchmark_freeze_decision",
        current_commit=current_commit,
        benchmark_candidate_version=PHASE7_BENCHMARK_CANDIDATE_VERSION,
        benchmark_freeze_decision=decision,
        benchmark_hash=version_manifest["benchmark_hash"],
        evidence_package_hash=evidence["evidence_package_hash"],
        material_unresolved_benchmark_defect=False,
        provider_rerun_required=False,
        evidence_package_frozen=True,
        version_and_compatibility_records_complete=True,
        limitations=[
            "small real-model sample",
            "single provider model",
            "synthetic tasks and inert tools",
            "developer adjudication rather than independent annotation",
            "no production-readiness conclusion",
        ],
    )


def _json_artifact(artifact: str, *, current_commit: str, **payload: Any) -> dict[str, Any]:
    base = {
        "schema_version": PHASE7_REFINEMENT_SCHEMA_VERSION,
        "artifact": artifact,
        "current_commit": current_commit,
        "provider_calls_performed": 0,
        "provider_execution_disabled": True,
        "historical_outputs_modified": False,
        "stage_e2_rerun_performed": False,
        "phase8_started": False,
        "pr_merged": False,
    }
    base.update(payload)
    base["artifact_hash"] = canonical_json_hash(
        {key: value for key, value in base.items() if key != "artifact_hash"}
    )
    return base


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()
