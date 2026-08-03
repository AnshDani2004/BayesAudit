from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, cast

import bayesaudit.pilot.phase7_closeout as closeout
from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.pilot.phase7_closeout import (
    PHASE7_ARTIFACT_INDEX,
    PHASE7_CLOSEOUT_DECISION,
    PHASE7_CLOSEOUT_JSON_ARTIFACTS,
    PHASE7_FINAL_CLAIM_REGISTRY,
    PHASE7_FINAL_LIMITATIONS,
    PHASE7_MERGE_READINESS,
    PHASE7_REPOSITORY_HYGIENE_AUDIT,
    PHASE7_REPRODUCIBILITY_MANIFEST,
    validate_phase7_closeout_artifacts,
)


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_phase7_closeout_artifacts_validate() -> None:
    assert validate_phase7_closeout_artifacts() == {"valid": True, "errors": []}


def test_phase7_closeout_source_is_provider_disabled() -> None:
    source = inspect.getsource(closeout)
    assert "assert_provider_disabled()" in source
    assert "make_provider_request" not in source
    assert "execute_provider_or_cached" not in source


def test_phase7_closeout_json_hashes_are_stable_and_offline() -> None:
    for path in PHASE7_CLOSEOUT_JSON_ARTIFACTS:
        payload = _json(path)
        expected = canonical_json_hash(
            {key: value for key, value in payload.items() if key != "artifact_hash"}
        )
        assert payload["artifact_hash"] == expected
        assert payload["provider_calls_performed"] == 0
        assert payload["stage_e2_rerun_performed"] is False
        assert payload["phase8_started"] is False


def test_phase7_artifact_index_is_comprehensive_and_redacted() -> None:
    index = _json(PHASE7_ARTIFACT_INDEX)
    assert index["artifact_count"] >= 260
    assert index["ignored_artifact_reference_count"] == 3
    stages = set(index["stages"])
    assert "Stage E.3" in stages
    assert "Benchmark refinement" in stages
    assert "Phase 7 closeout" in stages
    assert all(not row["path"].startswith("/Users/") for row in index["artifacts"])


def test_phase7_reproducibility_manifest_lists_required_commands() -> None:
    manifest = _json(PHASE7_REPRODUCIBILITY_MANIFEST)
    assert manifest["installation_command"] == 'python -m pip install -e ".[dev]"'
    assert manifest["full_test_command"] == "python -m pytest -q"
    assert "python -m ruff check ." in manifest["static_check_commands"]
    assert "python -m bayesaudit.cli validate-attacks" in manifest["validator_commands"]
    assert any(
        "evaluate-calibration-transfer" in cmd for cmd in manifest["mock_safe_dry_run_commands"]
    )
    assert manifest["expected_full_pytest_count"] == 1886
    assert manifest["expected_full_pytest_count_lower_bound"] == 1886
    assert len(manifest["config_hashes"]["benchmark_hash"]) == 64


def test_phase7_final_claim_registry_is_limited_and_honest() -> None:
    registry = _json(PHASE7_FINAL_CLAIM_REGISTRY)
    assert registry["claim_count"] == 5
    assert registry["validated_with_limitation_claims"] == 4
    assert registry["unsupported_claims"] == 1
    assert registry["contradicted_claims"] == 0
    assert any("clean prevention" in row["wording"] for row in registry["claims"])


def test_phase7_final_limitations_include_required_scientific_limits() -> None:
    limitations = _json(PHASE7_FINAL_LIMITATIONS)
    text = "\n".join(limitations["limitations"])
    assert limitations["limitation_count"] == 10
    assert "small real-model sample" in text
    assert "single provider model" in text
    assert "synthetic tasks and inert tools" in text
    assert "developer adjudication rather than independent annotation" in text
    assert "no production-readiness conclusion" in text
    assert "separate authorization" in limitations["phase8_prerequisites"]


def test_phase7_repository_hygiene_audit_passes() -> None:
    hygiene = _json(PHASE7_REPOSITORY_HYGIENE_AUDIT)
    assert hygiene["repository_hygiene_result"] == "passed"
    assert hygiene["api_key_tracked"] is False
    assert hygiene["authorization_header_tracked"] is False
    assert hygiene["secret_shaped_token_tracked"] is False
    assert hygiene["raw_provider_response_tracked"] is False
    assert hygiene["local_cache_tracked"] is False
    assert hygiene["absolute_user_path_tracked"] is False
    assert hygiene["json_yaml_parse_failures"] == []


def test_phase7_readme_and_report_match_closeout_status() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    report = Path("docs/phase7_report.md").read_text(encoding="utf-8")
    assert "Phase 7 built and stress-tested" in readme
    assert "production readiness" in readme
    assert "validate-phase10" in readme
    assert "Phase 7 Final Closeout" in report
    assert "phase7_complete_with_documented_limitations_merge_ready" in report


def test_phase7_closeout_and_merge_readiness_decisions() -> None:
    decision = _json(PHASE7_CLOSEOUT_DECISION)
    merge = _json(PHASE7_MERGE_READINESS)
    assert (
        decision["closeout_decision"] == "phase7_complete_with_documented_limitations_merge_ready"
    )
    assert decision["remaining_blockers"] == []
    assert merge["merge_readiness_decision"] == "merge_ready_with_documented_limitations"
    assert merge["manual_merge_required"] is True
    assert merge["recommended_manual_merge_method"] == "Create a merge commit"
    assert "Squash and merge" in merge["disallowed_manual_merge_methods"]
    assert "Rebase and merge" in merge["disallowed_manual_merge_methods"]
