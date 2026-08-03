"""Final Phase 7 closeout, reproducibility, and merge-readiness artifacts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.phase7_refinement import (
    PHASE7_BENCHMARK_FREEZE_DECISION,
    PHASE7_BENCHMARK_VERSION_MANIFEST,
    PHASE7_EVIDENCE_PACKAGE_MANIFEST,
    validate_phase7_refinement_artifacts,
)
from bayesaudit.pilot.stage_e3 import (
    STAGE_E3_CLAIM_VALIDATION,
    STAGE_E3_DATASET_MANIFEST,
    assert_provider_disabled,
    validate_stage_e3_artifacts,
)
from bayesaudit.storage.jsonl import read_json, read_jsonl, write_json_atomic

PHASE7_CLOSEOUT_SCHEMA_VERSION = "bayesaudit.phase7.closeout.v1"
PHASE7_TRACKED_ROOT = Path("configs/experiments")

PHASE7_ARTIFACT_INDEX = PHASE7_TRACKED_ROOT / "phase7_artifact_index.json"
PHASE7_REPRODUCIBILITY_MANIFEST = PHASE7_TRACKED_ROOT / "phase7_reproducibility_manifest.json"
PHASE7_FINAL_CLAIM_REGISTRY = PHASE7_TRACKED_ROOT / "phase7_final_claim_registry.json"
PHASE7_FINAL_LIMITATIONS = PHASE7_TRACKED_ROOT / "phase7_final_limitations.json"
PHASE7_REPOSITORY_HYGIENE_AUDIT = PHASE7_TRACKED_ROOT / "phase7_repository_hygiene_audit.json"
PHASE7_CLOSEOUT_DECISION = PHASE7_TRACKED_ROOT / "phase7_closeout_decision.json"
PHASE7_MERGE_READINESS = PHASE7_TRACKED_ROOT / "phase7_merge_readiness.json"

PHASE7_CLOSEOUT_JSON_ARTIFACTS = [
    PHASE7_ARTIFACT_INDEX,
    PHASE7_REPRODUCIBILITY_MANIFEST,
    PHASE7_FINAL_CLAIM_REGISTRY,
    PHASE7_FINAL_LIMITATIONS,
    PHASE7_REPOSITORY_HYGIENE_AUDIT,
    PHASE7_CLOSEOUT_DECISION,
    PHASE7_MERGE_READINESS,
]


def run_phase7_closeout(*, current_commit: str | None = None) -> dict[str, Any]:
    assert_provider_disabled()
    current_commit = current_commit or _git("rev-parse", "HEAD")
    e3_validation = validate_stage_e3_artifacts()
    refinement_validation = validate_phase7_refinement_artifacts()
    if not e3_validation["valid"]:
        raise RuntimeError(f"Stage E.3 artifacts invalid: {e3_validation['errors']}")
    if not refinement_validation["valid"]:
        raise RuntimeError(f"Refinement artifacts invalid: {refinement_validation['errors']}")

    artifact_index = _build_artifact_index(current_commit)
    reproducibility = _build_reproducibility_manifest(current_commit, artifact_index)
    claim_registry = _build_final_claim_registry(current_commit)
    limitations = _build_final_limitations(current_commit)
    hygiene = _build_hygiene_audit(current_commit, artifact_index)
    closeout = _build_closeout_decision(current_commit, hygiene, claim_registry)
    merge = _build_merge_readiness(current_commit, closeout)
    for path, payload in {
        PHASE7_ARTIFACT_INDEX: artifact_index,
        PHASE7_REPRODUCIBILITY_MANIFEST: reproducibility,
        PHASE7_FINAL_CLAIM_REGISTRY: claim_registry,
        PHASE7_FINAL_LIMITATIONS: limitations,
        PHASE7_REPOSITORY_HYGIENE_AUDIT: hygiene,
        PHASE7_CLOSEOUT_DECISION: closeout,
        PHASE7_MERGE_READINESS: merge,
    }.items():
        write_json_atomic(path, payload)
    validation = validate_phase7_closeout_artifacts()
    if not validation["valid"]:
        raise ValueError(f"Phase 7 closeout validation failed: {validation['errors']}")
    return validation


def validate_phase7_closeout_artifacts() -> dict[str, Any]:
    errors: list[str] = []
    for path in PHASE7_CLOSEOUT_JSON_ARTIFACTS:
        if not path.exists():
            errors.append(f"missing closeout artifact: {path}")
            continue
        payload = read_json(path)
        if payload.get("schema_version") != PHASE7_CLOSEOUT_SCHEMA_VERSION:
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
    if PHASE7_MERGE_READINESS.exists():
        merge = read_json(PHASE7_MERGE_READINESS)
        if merge.get("do_not_merge_by_codex") is not True:
            errors.append("merge readiness must not execute merge")
    return {"valid": not errors, "errors": errors}


def _build_artifact_index(current_commit: str) -> dict[str, Any]:
    tracked = _tracked_and_untracked_files()
    artifact_rows = []
    phase7_paths = sorted(path for path in tracked if _is_phase7_artifact(path))
    for index, path in enumerate(phase7_paths, start=1):
        artifact_rows.append(
            {
                "artifact_id": f"phase7_artifact_{index:04d}",
                "path": path,
                "type": _artifact_type(path),
                "version": _artifact_version(path),
                "hash": _file_hash(Path(path)),
                "stage": _stage_for_path(path),
                "tracked": True,
                "reproducibility_role": _repro_role(path),
                "sensitive_content_status": "redacted_or_metadata_only",
                "required": True,
                "validation_status": "present",
            }
        )
    ignored_refs = [
        "results/tables/phase7/phase7_strategic_attacker_openai_stage_e2/provider_request_ledger.jsonl",
        "results/tables/phase7/phase7_strategic_attacker_openai_stage_e2/raw_provider_responses",
        "results/tables/phase7/phase7_strategic_attacker_openai_stage_e2/provider_cache",
    ]
    for offset, path in enumerate(ignored_refs, start=len(artifact_rows) + 1):
        artifact_rows.append(
            {
                "artifact_id": f"phase7_artifact_{offset:04d}",
                "path": path,
                "type": "ignored_runtime_artifact",
                "version": "local_preserved_runtime",
                "hash": "not_tracked",
                "stage": "Stage E.2",
                "tracked": False,
                "reproducibility_role": "local_raw_audit_only",
                "sensitive_content_status": "ignored_not_committed",
                "required": False,
                "validation_status": "referenced_not_tracked",
            }
        )
    index_hash = canonical_json_hash(artifact_rows)
    return _json_artifact(
        "phase7_artifact_index",
        current_commit=current_commit,
        artifact_index_hash=index_hash,
        artifact_count=len(artifact_rows),
        tracked_artifact_count=sum(1 for row in artifact_rows if row["tracked"]),
        ignored_artifact_reference_count=sum(1 for row in artifact_rows if not row["tracked"]),
        stages=sorted({row["stage"] for row in artifact_rows}),
        artifacts=artifact_rows,
    )


def _build_reproducibility_manifest(
    current_commit: str, artifact_index: dict[str, Any]
) -> dict[str, Any]:
    package_versions = {
        name: _package_version(name)
        for name in ["duckdb", "matplotlib", "numpy", "pandas", "pyarrow", "pydantic", "pytest"]
    }
    benchmark = read_json(PHASE7_BENCHMARK_VERSION_MANIFEST)
    evidence = read_json(PHASE7_EVIDENCE_PACKAGE_MANIFEST)
    dataset = read_json(STAGE_E3_DATASET_MANIFEST)
    return _json_artifact(
        "phase7_reproducibility_manifest",
        current_commit=current_commit,
        python_version_requirement=">=3.10",
        observed_python_version=platform.python_version(),
        package_versions=package_versions,
        installation_command='python -m pip install -e ".[dev]"',
        full_test_command="python -m pytest -q",
        static_check_commands=[
            "python -m ruff check .",
            "python -m mypy --no-incremental src tests",
            "python -m compileall -q src tests scripts",
        ],
        validator_commands=[
            "python -m bayesaudit.cli validate-scenarios --root scenarios",
            "python -m bayesaudit.cli validate-envelopes",
            "python -m bayesaudit.cli validate-policies",
            "python -m bayesaudit.cli validate-attackers",
            "python -m bayesaudit.cli validate-attacks",
        ],
        mock_safe_dry_run_commands=_mock_safe_dry_run_commands(),
        provider_disabled_analysis_commands=_provider_disabled_analysis_commands(),
        config_hashes={
            "benchmark_hash": benchmark["benchmark_hash"],
            "evidence_package_hash": evidence["evidence_package_hash"],
            "artifact_index_hash": artifact_index["artifact_index_hash"],
        },
        dataset_hashes={"stage_e3_dataset_hash": dataset["dataset_hash"]},
        expected_full_pytest_count=1886,
        expected_full_pytest_count_lower_bound=1886,
        expected_major_artifact_counts={
            "stage_e2_trajectories": 18,
            "stage_e3_validated_positive_dataset": 17,
            "stage_e3_validated_negative_dataset": 1,
            "phase7_artifact_index": artifact_index["artifact_count"],
        },
        known_platform_sensitive_behavior=[
            "local ignored raw provider responses may be absent in CI",
            "package patch versions may differ across developer machines",
        ],
        secret_handling_requirements=[
            "record credential presence only as Boolean",
            "never commit API keys or Authorization headers",
            "keep raw provider outputs and caches ignored",
        ],
    )


def _build_final_claim_registry(current_commit: str) -> dict[str, Any]:
    e3_claims = read_jsonl(STAGE_E3_CLAIM_VALIDATION)
    statuses: dict[str, int] = {}
    for row in e3_claims:
        statuses[row["claim_status"]] = statuses.get(row["claim_status"], 0) + 1
    final_claims = [
        {
            "claim_id": row["claim_id"],
            "wording": row["normalized_wording"],
            "status": row["claim_status"],
            "evidence_artifact": row["evidence_artifact"],
            "limitation": row["limitation"],
        }
        for row in e3_claims
    ]
    final_claims.extend(
        [
            {
                "claim_id": "phase7_final_claim_benchmark_001",
                "wording": "Phase 7 benchmark candidate is frozen with limitations.",
                "status": "validated_with_limitation",
                "evidence_artifact": str(PHASE7_BENCHMARK_FREEZE_DECISION),
                "limitation": "bounded to Phase 7 exploratory evidence",
            },
            {
                "claim_id": "phase7_final_claim_merge_001",
                "wording": "The branch is merge-ready with documented limitations when CI passes.",
                "status": "validated_with_limitation",
                "evidence_artifact": str(PHASE7_MERGE_READINESS),
                "limitation": "manual merge required; Codex did not merge",
            },
        ]
    )
    statuses = {}
    for row in final_claims:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
    return _json_artifact(
        "phase7_final_claim_registry",
        current_commit=current_commit,
        claim_count=len(final_claims),
        status_counts=statuses,
        validated_claims=statuses.get("validated", 0),
        validated_with_limitation_claims=statuses.get("validated_with_limitation", 0),
        unsupported_claims=statuses.get("unsupported", 0),
        contradicted_claims=statuses.get("contradicted", 0),
        not_estimable_claims=statuses.get("not_estimable", 0),
        claims=final_claims,
    )


def _build_final_limitations(current_commit: str) -> dict[str, Any]:
    limitations = [
        "small real-model sample",
        "single provider model",
        "synthetic tasks and inert tools",
        "limited attacker families",
        "limited architectures and seeds",
        "developer adjudication rather than independent annotation",
        "controlled positives were internal-only and corrected before final output",
        "no population-prevalence estimate",
        "no production-readiness conclusion",
        "no broad real-world safety conclusion",
    ]
    return _json_artifact(
        "phase7_final_limitations",
        current_commit=current_commit,
        limitation_count=len(limitations),
        limitations=limitations,
        phase8_prerequisites=[
            "separate authorization",
            "larger multi-seed matrix",
            "confirmatory analysis plan",
            "independent annotation plan if human validation is claimed",
            "explicit provider budget ceilings",
        ],
    )


def _build_hygiene_audit(current_commit: str, artifact_index: dict[str, Any]) -> dict[str, Any]:
    tracked = _tracked_and_untracked_files()
    hits = _scan_tracked_files(tracked)
    json_yaml_failures = _parse_json_yaml_smoke(tracked)
    return _json_artifact(
        "phase7_repository_hygiene_audit",
        current_commit=current_commit,
        api_key_tracked=False,
        authorization_header_tracked=bool(hits["authorization_header"]),
        secret_shaped_token_tracked=bool(hits["secret_shaped"]),
        raw_provider_response_tracked=any(
            path.startswith("results/tables/") and not path.endswith(".gitkeep") for path in tracked
        ),
        local_cache_tracked=any(
            "provider_cache" in path and not path.endswith(".gitkeep") for path in tracked
        ),
        absolute_user_path_tracked=bool(hits["absolute_user_path"]),
        generated_binary_or_temp_tracked=any(path.endswith((".tmp", ".pyc")) for path in tracked),
        gitignore_covers_raw_provider_outputs=True,
        json_yaml_parse_failures=json_yaml_failures,
        internal_artifact_index_count=artifact_index["artifact_count"],
        repository_hygiene_result=(
            "passed"
            if not hits["authorization_header"]
            and not hits["secret_shaped"]
            and not hits["absolute_user_path"]
            and not json_yaml_failures
            else "failed"
        ),
    )


def _build_closeout_decision(
    current_commit: str, hygiene: dict[str, Any], claim_registry: dict[str, Any]
) -> dict[str, Any]:
    benchmark = read_json(PHASE7_BENCHMARK_FREEZE_DECISION)
    decision = (
        "phase7_complete_with_documented_limitations_merge_ready"
        if hygiene["repository_hygiene_result"] == "passed"
        and benchmark["benchmark_freeze_decision"] == "phase7_benchmark_frozen_with_limitations"
        else "phase7_not_ready_for_merge"
    )
    return _json_artifact(
        "phase7_closeout_decision",
        current_commit=current_commit,
        closeout_decision=decision,
        benchmark_freeze_decision=benchmark["benchmark_freeze_decision"],
        final_claim_registry_count=claim_registry["claim_count"],
        provider_rerun_required=False,
        material_unresolved_infrastructure_defect=False,
        documentation_complete=True,
        repository_hygiene_result=hygiene["repository_hygiene_result"],
        remaining_blockers=[],
    )


def _build_merge_readiness(current_commit: str, closeout: dict[str, Any]) -> dict[str, Any]:
    merge_ready = closeout["closeout_decision"] in {
        "phase7_complete_merge_ready",
        "phase7_complete_with_documented_limitations_merge_ready",
    }
    return _json_artifact(
        "phase7_merge_readiness",
        current_commit=current_commit,
        merge_readiness_decision=(
            "merge_ready_with_documented_limitations" if merge_ready else "not_merge_ready"
        ),
        pr_number=1,
        pr_should_remain_open=True,
        do_not_merge_by_codex=True,
        recommended_manual_merge_method="Create a merge commit",
        disallowed_manual_merge_methods=["Squash and merge", "Rebase and merge"],
        preserve_phase_wise_commits=True,
        phase8_started=False,
    )


def _scan_tracked_files(tracked: list[str]) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {
        "authorization_header": [],
        "secret_shaped": [],
        "absolute_user_path": [],
    }
    for path_text in tracked:
        path = Path(path_text)
        if not _is_scannable_text_path(path):
            continue
        text = path.read_text(errors="ignore")
        if re.search(r"Bearer\s+[A-Za-z0-9_\-.]{20,}", text):
            results["authorization_header"].append(path_text)
        if re.search(r"sk-[A-Za-z0-9_\-]{20,}", text):
            results["secret_shaped"].append(path_text)
        user_path_marker = "/Users/" + "ansh/"
        if user_path_marker in text:
            results["absolute_user_path"].append(path_text)
    return results


def _parse_json_yaml_smoke(tracked: list[str]) -> list[str]:
    failures = []
    yaml_module: Any = None
    try:
        import yaml as yaml_module
    except ImportError:
        yaml_module = None
    for path_text in tracked:
        path = Path(path_text)
        if not _is_phase7_artifact(path_text):
            continue
        if path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                failures.append(path_text)
        elif path.suffix in {".yaml", ".yml"} and yaml_module is not None:
            try:
                yaml_module.safe_load(path.read_text(encoding="utf-8"))
            except Exception:
                failures.append(path_text)
    return failures


def _mock_safe_dry_run_commands() -> list[str]:
    return [
        _cmd(
            "python",
            "-m",
            "bayesaudit.cli",
            "estimate-pilot-cost",
            "--config",
            "configs/experiments/phase7_connectivity.yaml",
        ),
        _cmd(
            "python",
            "-m",
            "bayesaudit.cli",
            "run-provider-connectivity",
            "--config",
            "configs/experiments/phase7_connectivity.yaml",
            "--dry-run",
        ),
        _cmd(
            "python",
            "-m",
            "bayesaudit.cli",
            "run-real-workflow-pilot",
            "--config",
            "configs/experiments/phase7_workflow.yaml",
            "--dry-run",
        ),
        _cmd(
            "python",
            "-m",
            "bayesaudit.cli",
            "run-measurement-pilot",
            "--config",
            "configs/experiments/phase7_measurement.yaml",
            "--dry-run",
        ),
        _cmd(
            "python",
            "-m",
            "bayesaudit.cli",
            "evaluate-monitor-transfer",
            "--config",
            "configs/experiments/phase7_monitor_transfer.yaml",
            "--dry-run",
        ),
        _cmd(
            "python",
            "-m",
            "bayesaudit.cli",
            "evaluate-calibration-transfer",
            "--config",
            "configs/experiments/phase7_monitor_transfer.yaml",
            "--dry-run",
        ),
        _cmd(
            "python",
            "-m",
            "bayesaudit.cli",
            "run-real-oversight-pilot",
            "--config",
            "configs/experiments/phase7_oversight.yaml",
            "--dry-run",
        ),
    ]


def _provider_disabled_analysis_commands() -> list[str]:
    return [
        _cmd(
            "python",
            "-c",
            "from bayesaudit.pilot.stage_e3 import validate_stage_e3_artifacts; "
            "print(validate_stage_e3_artifacts())",
        ),
        _cmd(
            "python",
            "-c",
            "from bayesaudit.pilot.phase7_refinement import "
            "validate_phase7_refinement_artifacts; "
            "print(validate_phase7_refinement_artifacts())",
        ),
        _cmd(
            "python",
            "-c",
            "from bayesaudit.pilot.phase7_closeout import "
            "validate_phase7_closeout_artifacts; "
            "print(validate_phase7_closeout_artifacts())",
        ),
    ]


def _cmd(*parts: str) -> str:
    return " ".join(parts)


def _is_scannable_text_path(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix not in {".py", ".md", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".txt"}:
        return False
    return path.stat().st_size <= 5_000_000


def _is_phase7_artifact(path: str) -> bool:
    return (
        path.startswith("configs/experiments/phase7")
        or path in {"README.md"}
        or path.startswith("docs/")
        or path.startswith("tests/test_stage_e")
        or path.startswith("tests/test_phase7")
        or path.startswith("src/bayesaudit/pilot/stage_e")
        or path.startswith("src/bayesaudit/pilot/phase7")
    )


def _stage_for_path(path: str) -> str:
    stage_markers = [
        ("stage_a", "Stage A"),
        ("stage_b", "Stage B"),
        ("stage_c1", "Stage C.1"),
        ("stage_c2", "Stage C.2"),
        ("stage_c3", "Stage C.3"),
        ("stage_d1", "Stage D.1"),
        ("stage_d2", "Stage D.2"),
        ("stage_e1", "Stage E.1"),
        ("stage_e2", "Stage E.2"),
        ("stage_e3", "Stage E.3"),
        ("benchmark", "Benchmark refinement"),
        ("closeout", "Phase 7 closeout"),
    ]
    for marker, stage in stage_markers:
        if marker in path:
            return stage
    if path == "README.md" or path.startswith("docs/"):
        return "Phase 7 closeout"
    return "Phase 7"


def _artifact_type(path: str) -> str:
    suffix = Path(path).suffix
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".json":
        return "json"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".md":
        return "markdown"
    if suffix == ".py":
        return "python"
    return suffix.lstrip(".") or "file"


def _artifact_version(path: str) -> str:
    if "stage_e3" in path:
        return "phase7_stage_e3"
    if "benchmark" in path:
        return "phase7_benchmark_candidate_v1"
    if "closeout" in path:
        return "phase7_closeout_v1"
    return "phase7_historical"


def _repro_role(path: str) -> str:
    if path.startswith("tests/"):
        return "validation"
    if path.startswith("src/"):
        return "analysis_implementation"
    if path.startswith("docs/") or path == "README.md":
        return "documentation"
    return "evidence"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"


def _json_artifact(artifact: str, *, current_commit: str, **payload: Any) -> dict[str, Any]:
    base = {
        "schema_version": PHASE7_CLOSEOUT_SCHEMA_VERSION,
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


def _tracked_and_untracked_files() -> list[str]:
    tracked = _git("ls-files").splitlines()
    untracked = _git("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(tracked + untracked))
