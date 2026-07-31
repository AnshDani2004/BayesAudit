from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pytest import CaptureFixture, MonkeyPatch

from bayesaudit.benchmark.io import load_tasks
from bayesaudit.cli import main
from bayesaudit.pilot.annotation import agreement_records, build_annotation_sample
from bayesaudit.pilot.config import (
    load_pilot_experiment_config,
    load_pilot_provider_config,
    validate_provider_config,
)
from bayesaudit.pilot.costs import (
    calculate_cost_accounting,
    load_pricing_record,
    load_pricing_record_path,
)
from bayesaudit.pilot.lifecycle import (
    build_real_annotation_sample,
    classify_pilot_tasks,
    estimate_pilot_cost,
    evaluate_monitor_transfer,
    generate_freeze_proposal,
    plan_phase8,
    run_measurement_pilot,
    run_provider_connectivity,
    run_real_oversight_pilot,
    run_real_workflow_pilot,
    summarize_real_pilot,
)
from bayesaudit.pilot.prompts import (
    FORBIDDEN_PROMPT_TOKENS,
    TEMPLATE_VERSIONS,
    render_prompt,
    repair_prompt,
)
from bayesaudit.pilot.providers import (
    OpenAIProviderError,
    ProviderAdapter,
    ProviderLedger,
    RequestCache,
    authorize_provider_run,
    classify_provider_failure,
    estimate_pilot_plan,
    execute_mock_or_cached,
    execute_provider_or_cached,
    extract_openai_response,
    make_provider_request,
)
from bayesaudit.pilot.structured import parse_structured_output
from bayesaudit.pilot.transfer import oversight_feasibility_records
from bayesaudit.pilot.types import (
    CostAccountingRecord,
    PilotExperimentConfig,
    PilotPlan,
    PilotProviderConfig,
    PricingRecord,
    ProviderAttemptCostInput,
    ProviderResponseRecord,
)
from bayesaudit.pilot.validation import (
    compare_scorer_to_human,
    default_scorer_readiness,
    default_task_readiness,
    readiness_counts,
)
from bayesaudit.pilot.workflow_quality import workflow_quality_flags
from bayesaudit.schemas import (
    ArchitectureKind,
    BehaviorCondition,
    BenchmarkTask,
    BudgetState,
    MessageRecord,
    ModelConfigRecord,
    ModelResponse,
    Trajectory,
    TrajectoryStatus,
    TrajectoryStep,
    WorkflowStepKind,
)
from bayesaudit.storage.jsonl import read_jsonl

ROOT = Path("configs/experiments")
CONNECTIVITY = ROOT / "phase7_connectivity.yaml"
WORKFLOW = ROOT / "phase7_workflow.yaml"
MEASUREMENT = ROOT / "phase7_measurement.yaml"
TRANSFER = ROOT / "phase7_monitor_transfer.yaml"
OVERSIGHT = ROOT / "phase7_oversight.yaml"
ANNOTATION = ROOT / "phase7_annotation_sample.yaml"
FULL = ROOT / "phase7_full_pilot.yaml"
MOCK_PROVIDER_CONFIG = "configs/providers/mock/smoke.yaml"
CONNECTIVITY_CONFIG = "configs/experiments/phase7_connectivity.yaml"
WORKFLOW_CONFIG = "configs/experiments/phase7_workflow.yaml"
MEASUREMENT_CONFIG = "configs/experiments/phase7_measurement.yaml"
TRANSFER_CONFIG = "configs/experiments/phase7_monitor_transfer.yaml"
OVERSIGHT_CONFIG = "configs/experiments/phase7_oversight.yaml"
ANNOTATION_CONFIG = "configs/experiments/phase7_annotation_sample.yaml"
FULL_CONFIG = "configs/experiments/phase7_full_pilot.yaml"
OPENAI_STAGE_A = ROOT / "phase7_connectivity_openai_stage_a.yaml"
OPENAI_STAGE_A_CONFIG = "configs/experiments/phase7_connectivity_openai_stage_a.yaml"
OPENAI_PROVIDER = Path("configs/providers/remote/openai_phase7_stage_a.yaml")
OPENAI_PROVIDER_CONFIG = "configs/providers/remote/openai_phase7_stage_a.yaml"
OPENAI_STAGE_A1 = ROOT / "phase7_connectivity_openai_stage_a1.yaml"
OPENAI_STAGE_A1_CONFIG = "configs/experiments/phase7_connectivity_openai_stage_a1.yaml"
OPENAI_PROVIDER_A1 = Path("configs/providers/remote/openai_phase7_stage_a1.yaml")
OPENAI_PROVIDER_A1_CONFIG = "configs/providers/remote/openai_phase7_stage_a1.yaml"


def _task() -> BenchmarkTask:
    return load_tasks(Path("scenarios"))[0]


def _provider() -> PilotProviderConfig:
    return load_pilot_provider_config(Path("configs/providers/mock/smoke.yaml"))


def _config(path: Path = CONNECTIVITY) -> PilotExperimentConfig:
    return load_pilot_experiment_config(path)


def _plan(path: Path = CONNECTIVITY) -> PilotPlan:
    config = _config(path)
    return estimate_pilot_plan(config, _provider(), task_count=1)


@pytest.mark.parametrize(
    "path",
    [
        Path("configs/providers/mock/smoke.yaml"),
        Path("configs/providers/remote/disabled_template.yaml"),
        Path("configs/providers/local/disabled_template.yaml"),
        OPENAI_PROVIDER,
        OPENAI_PROVIDER_A1,
    ],
)
def test_phase7_provider_configs_validate(path: Path) -> None:
    payload = validate_provider_config(path)
    assert payload["valid"] is True
    assert payload["credential_free_config"] is True


@pytest.mark.parametrize(
    "path",
    [
        CONNECTIVITY,
        WORKFLOW,
        MEASUREMENT,
        TRANSFER,
        OVERSIGHT,
        ANNOTATION,
        FULL,
        OPENAI_STAGE_A,
        OPENAI_STAGE_A1,
    ],
)
def test_phase7_experiment_configs_have_plans(path: Path) -> None:
    payload = estimate_pilot_cost(path)
    assert payload["schema_version"] == "bayesaudit.pilot.v1"
    assert payload["planned_trajectories"] >= 0
    assert payload["estimated_cost"] >= 0.0


def test_pilot_manifest_records_base_branch_and_commit(tmp_path: Path) -> None:
    config = _config().model_copy(update={"output_root": tmp_path})
    provider = _provider()
    plan = estimate_pilot_plan(config, provider, task_count=1)
    from bayesaudit.pilot.lifecycle import write_pilot_manifest

    manifest = write_pilot_manifest(config, provider, plan, status="planned")
    assert manifest.base_branch == "main"
    assert manifest.base_commit == "f5c1962"
    assert manifest.phase7_branch == "codex/phase7-real-model-pilot"


@pytest.mark.parametrize(
    "gate_name",
    [
        "provider_calls_enabled_in_config",
        "experiment_provider_calls_enabled",
        "provider_cache_enabled",
        "experiment_cache_enabled",
        "provider_resume_enabled",
        "experiment_resume_enabled",
        "provider_raw_response_preservation_enabled",
        "provider_secret_redaction_enabled",
        "provider_external_tools_disabled",
        "experiment_external_tools_disabled",
        "provider_fallback_model_absent",
        "cli_allow_provider_calls",
        "provider_named",
        "model_identifier_named",
        "cost_ceiling_set",
        "token_ceiling_set",
        "request_ceiling_set",
        "trajectory_ceiling_set",
        "estimated_cost_within_ceiling",
        "estimated_tokens_within_ceiling",
        "planned_requests_within_ceiling",
        "planned_trajectories_within_ceiling",
        "large_run_protection",
        "configuration_valid",
        "pilot_manifest_written",
        "output_location_writable",
        "provider_adapter_dry_run_valid",
        "no_ci_environment",
    ],
)
def test_provider_permission_record_names_required_gates(gate_name: str) -> None:
    record = authorize_provider_run(
        _config(),
        _provider(),
        _plan(),
        allow_provider_calls=False,
        max_cost=None,
        max_tokens=None,
        max_requests=None,
        max_trajectories=None,
    )
    assert gate_name in {gate.gate_name for gate in record.gates}


@pytest.mark.parametrize(
    ("kwargs", "failed_gate"),
    [
        (
            {"max_cost": -0.1, "max_tokens": 1000, "max_requests": 1, "max_trajectories": 1},
            "estimated_cost_within_ceiling",
        ),
        (
            {"max_cost": 0.0, "max_tokens": 1, "max_requests": 1, "max_trajectories": 1},
            "estimated_tokens_within_ceiling",
        ),
        (
            {"max_cost": 0.0, "max_tokens": 1000, "max_requests": 0, "max_trajectories": 1},
            "planned_requests_within_ceiling",
        ),
        (
            {"max_cost": 0.0, "max_tokens": 1000, "max_requests": 1, "max_trajectories": 0},
            "planned_trajectories_within_ceiling",
        ),
    ],
)
def test_provider_permission_hard_ceilings_block(kwargs: dict[str, Any], failed_gate: str) -> None:
    record = authorize_provider_run(
        _config(),
        _provider(),
        _plan(),
        allow_provider_calls=True,
        **kwargs,
    )
    failed = {gate.gate_name for gate in record.gates if gate.status == "failed"}
    assert failed_gate in failed
    assert record.final_authorization_decision == "block"


def test_openai_stage_a_config_is_exact_and_tightly_capped() -> None:
    provider = load_pilot_provider_config(OPENAI_PROVIDER)
    config = load_pilot_experiment_config(OPENAI_STAGE_A)
    plan = estimate_pilot_plan(config, provider, task_count=1)
    assert provider.provider_name == "openai"
    assert provider.model_identifier == "gpt-5-nano-2025-08-07"
    assert provider.credential_env_var == "OPENAI_API_KEY"
    assert provider.enabled is True
    assert provider.external_tools_enabled is False
    assert provider.fallback_model_identifier is None
    assert config.provider_calls_enabled is True
    assert config.cache_enabled is True
    assert config.resume_enabled is True
    assert config.external_tools_enabled is False
    assert config.behavior_conditions == ["honest"]
    assert config.attacker_conditions == ["none"]
    assert config.oversight_conditions == ["none"]
    assert plan.planned_trajectories == 1
    assert plan.planned_requests == 1
    assert plan.estimated_total_tokens <= 3000
    assert plan.estimated_cost <= 0.01


def test_openai_stage_a1_config_uses_diagnostic_budget_and_reasoning() -> None:
    provider = load_pilot_provider_config(OPENAI_PROVIDER_A1)
    config = load_pilot_experiment_config(OPENAI_STAGE_A1)
    plan = estimate_pilot_plan(config, provider, task_count=1)
    assert provider.provider_name == "openai"
    assert provider.model_identifier == "gpt-5-nano-2025-08-07"
    assert provider.credential_env_var == "OPENAI_API_KEY"
    assert provider.sampling_parameters["reasoning_effort"] == "minimal"
    assert provider.sampling_parameters["max_output_tokens"] == 1000
    assert provider.max_retries == 0
    assert config.request_ceiling == 1
    assert config.local_execution_ceiling == 2
    assert config.attacker_conditions == ["none"]
    assert config.oversight_conditions == ["none"]
    assert plan.planned_trajectories == 1
    assert plan.planned_requests == 1
    assert plan.estimated_total_tokens <= 3000
    assert plan.estimated_cost <= 0.01


def _stage_a1_pricing() -> PricingRecord:
    return load_pricing_record("openai", "gpt-5-nano-2025-08-07")


def _cost_for_attempt(
    attempt: ProviderAttemptCostInput,
    *,
    estimated: Decimal | None = Decimal("0.0015"),
    pricing: PricingRecord | None = None,
) -> CostAccountingRecord:
    return calculate_cost_accounting(
        provider="openai",
        model_identifier="gpt-5-nano-2025-08-07",
        attempts=[attempt],
        pricing=_stage_a1_pricing() if pricing is None else pricing,
        estimated_cost_usd=estimated,
        conservative_upper_bound_usd=estimated,
    )


def test_stage_a1_token_derived_cost_uses_versioned_pricing() -> None:
    record = _cost_for_attempt(
        ProviderAttemptCostInput(input_tokens=31, output_tokens=33, reasoning_tokens=0)
    )
    assert record.input_cost_usd == Decimal("0.00000155")
    assert record.cached_input_cost_usd == Decimal("0")
    assert record.output_cost_usd == Decimal("0.0000132")
    assert record.token_derived_cost_usd == Decimal("0.00001475")
    assert record.cost_reconciliation_status == "token_derived"
    assert (
        record.pricing_table_version
        == "openai_gpt5_nano_2025_08_07_usd_2026_07_31_v1"
    )


def test_cached_input_pricing_uses_cached_rate() -> None:
    record = _cost_for_attempt(ProviderAttemptCostInput(input_tokens=10, cached_input_tokens=10))
    assert record.input_cost_usd == Decimal("0")
    assert record.cached_input_cost_usd == Decimal("0.00000005")
    assert record.token_derived_cost_usd == Decimal("0.00000005")


def test_mixed_cached_and_noncached_input_pricing() -> None:
    record = _cost_for_attempt(
        ProviderAttemptCostInput(input_tokens=100, cached_input_tokens=40, output_tokens=10)
    )
    assert record.noncached_input_tokens == 60
    assert record.input_cost_usd == Decimal("0.000003")
    assert record.cached_input_cost_usd == Decimal("0.0000002")
    assert record.output_cost_usd == Decimal("0.000004")
    assert record.token_derived_cost_usd == Decimal("0.0000072")


def test_zero_token_response_has_zero_token_derived_cost() -> None:
    record = _cost_for_attempt(ProviderAttemptCostInput())
    assert record.token_derived_cost_usd == Decimal("0")
    assert record.cost_reconciliation_status == "token_derived"


def test_reasoning_tokens_are_not_double_counted() -> None:
    baseline = _cost_for_attempt(ProviderAttemptCostInput(input_tokens=31, output_tokens=33))
    with_reasoning = _cost_for_attempt(
        ProviderAttemptCostInput(input_tokens=31, output_tokens=33, reasoning_tokens=20)
    )
    assert with_reasoning.token_derived_cost_usd == baseline.token_derived_cost_usd
    assert "not double counted" in " ".join(with_reasoning.notes)


def test_missing_usage_is_estimated_only() -> None:
    record = _cost_for_attempt(ProviderAttemptCostInput(usage_present=False))
    assert record.token_derived_cost_usd is None
    assert record.cost_reconciliation_status == "estimated_only"


def test_missing_pricing_record_blocks_token_derived_cost() -> None:
    record = _cost_for_attempt(
        ProviderAttemptCostInput(input_tokens=31, output_tokens=33),
        pricing=None,
        estimated=Decimal("0.0015"),
    )
    assert record.token_derived_cost_usd == Decimal("0.00001475")
    no_pricing = calculate_cost_accounting(
        provider="openai",
        model_identifier="gpt-5-nano-2025-08-07",
        attempts=[ProviderAttemptCostInput(input_tokens=31, output_tokens=33)],
        pricing=None,
        estimated_cost_usd=Decimal("0.0015"),
    )
    assert no_pricing.token_derived_cost_usd is None
    assert no_pricing.cost_reconciliation_status == "estimated_only"


def test_unknown_model_has_no_pricing_record() -> None:
    with pytest.raises(KeyError):
        load_pricing_record("openai", "unknown-model")


def test_regional_uplift_is_explicit_component() -> None:
    pricing = _stage_a1_pricing().model_copy(
        update={"regional_uplift_multiplier": Decimal("1.10")}
    )
    record = _cost_for_attempt(
        ProviderAttemptCostInput(input_tokens=31, output_tokens=33),
        pricing=pricing,
    )
    assert record.regional_uplift_usd == Decimal("0.000001475")
    assert record.token_derived_cost_usd == Decimal("0.000016225")


def test_fixed_tool_charge_is_explicit_component() -> None:
    pricing = _stage_a1_pricing().model_copy(update={"fixed_tool_charge_usd": Decimal("0.0002")})
    record = _cost_for_attempt(
        ProviderAttemptCostInput(input_tokens=31, output_tokens=33),
        pricing=pricing,
    )
    assert record.fixed_tool_charge_usd == Decimal("0.0002")
    assert record.token_derived_cost_usd == Decimal("0.00021475")


def test_retry_with_one_billed_and_one_unbilled_attempt() -> None:
    record = calculate_cost_accounting(
        provider="openai",
        model_identifier="gpt-5-nano-2025-08-07",
        attempts=[
            ProviderAttemptCostInput(input_tokens=31, output_tokens=33, billed=True),
            ProviderAttemptCostInput(input_tokens=999, output_tokens=999, billed=False),
        ],
        pricing=_stage_a1_pricing(),
    )
    assert record.billed_attempt_count == 1
    assert record.unbilled_attempt_count == 1
    assert record.token_derived_cost_usd == Decimal("0.00001475")


def test_cache_hit_adds_zero_incremental_provider_cost() -> None:
    record = calculate_cost_accounting(
        provider="openai",
        model_identifier="gpt-5-nano-2025-08-07",
        attempts=[
            ProviderAttemptCostInput(
                status="cached",
                input_tokens=31,
                output_tokens=33,
                billed=False,
            )
        ],
        pricing=_stage_a1_pricing(),
    )
    assert record.cache_hit_count == 1
    assert record.token_derived_cost_usd == Decimal("0")
    assert record.cost_reconciliation_status == "token_derived"


def test_failed_request_with_reported_usage_is_token_derived() -> None:
    record = _cost_for_attempt(
        ProviderAttemptCostInput(status="failed", input_tokens=31, output_tokens=33)
    )
    assert record.token_derived_cost_usd == Decimal("0.00001475")
    assert record.cost_reconciliation_status == "token_derived"


def test_failed_request_without_usage_remains_unreconciled() -> None:
    record = _cost_for_attempt(
        ProviderAttemptCostInput(status="failed", usage_present=False),
        estimated=None,
    )
    assert record.token_derived_cost_usd is None
    assert record.cost_reconciliation_status == "unreconciled"


def test_cost_accounting_uses_decimal_precision() -> None:
    record = _cost_for_attempt(
        ProviderAttemptCostInput(input_tokens=3, cached_input_tokens=1, output_tokens=7)
    )
    assert record.token_derived_cost_usd == Decimal("0.000002905")
    assert isinstance(record.token_derived_cost_usd, Decimal)


def test_pricing_table_version_and_hash_are_preserved() -> None:
    pricing = _stage_a1_pricing()
    record = _cost_for_attempt(ProviderAttemptCostInput(input_tokens=31, output_tokens=33))
    assert record.pricing_table_version == pricing.pricing_table_version
    assert record.pricing_configuration_hash == pricing.configuration_hash


def test_provider_reported_cost_is_distinct_from_token_derived_cost() -> None:
    record = _cost_for_attempt(
        ProviderAttemptCostInput(
            input_tokens=31,
            output_tokens=33,
            provider_reported_cost_usd=Decimal("0.01"),
        )
    )
    assert record.provider_reported_cost_usd == Decimal("0.01")
    assert record.token_derived_cost_usd == Decimal("0.00001475")
    assert record.cost_reconciliation_status == "provider_reported"


def test_conservative_upper_bound_is_not_labeled_actual_cost() -> None:
    record = _cost_for_attempt(ProviderAttemptCostInput(input_tokens=31, output_tokens=33))
    payload = record.model_dump(mode="json")
    assert payload["conservative_upper_bound_usd"] == "0.0015"
    assert "actual_cost" not in payload
    assert "reconciled_cost" not in payload


def test_report_summary_preserves_nullable_billed_cost(tmp_path: Path) -> None:
    config = load_pilot_experiment_config(OPENAI_STAGE_A1).model_copy(
        update={"output_root": tmp_path}
    )
    path = tmp_path / "stage_a1.yaml"
    path.write_text(config.model_dump_json(), encoding="utf-8")
    output_dir = tmp_path / config.pilot_id
    output_dir.mkdir(parents=True)
    (output_dir / "provider_request_ledger.jsonl").write_text(
        json.dumps({"request_hash": "abc", "status": "completed"}) + "\n",
        encoding="utf-8",
    )
    (output_dir / "provider_failures.jsonl").write_text("", encoding="utf-8")
    (output_dir / "connectivity_response.json").write_text(
        json.dumps(
            {
                "total_tokens": 64,
                "provider_reported_usage": {
                    "input_tokens": 31,
                    "cached_input_tokens": 0,
                    "output_tokens": 33,
                    "reasoning_tokens": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    summary = summarize_real_pilot(path)
    assert summary["token_derived_cost_usd"] == "0.00001475"
    assert summary["provider_reported_cost_usd"] is None
    assert summary["billed_cost_usd"] is None


def test_historical_stage_a_failure_summary_remains_unreconciled(tmp_path: Path) -> None:
    config = load_pilot_experiment_config(OPENAI_STAGE_A).model_copy(
        update={"output_root": tmp_path}
    )
    path = tmp_path / "stage_a.yaml"
    path.write_text(config.model_dump_json(), encoding="utf-8")
    output_dir = tmp_path / config.pilot_id
    output_dir.mkdir(parents=True)
    (output_dir / "provider_request_ledger.jsonl").write_text(
        json.dumps({"request_hash": "abc", "status": "failed"}) + "\n",
        encoding="utf-8",
    )
    (output_dir / "provider_failures.jsonl").write_text(
        json.dumps({"failure_type": "unknown_provider_error"}) + "\n",
        encoding="utf-8",
    )
    summary = summarize_real_pilot(path)
    assert summary["failed_requests"] == 1
    assert summary["token_derived_cost_usd"] is None
    assert summary["cost_reconciliation_status"] == "unreconciled"


def test_pricing_record_path_validates_configuration_hash() -> None:
    record = load_pricing_record_path(Path("configs/pricing/openai_gpt5_nano_2025_08_07.yaml"))
    assert (
        record.configuration_hash
        == "767fa5ca39aac5617fb39d81e6cb9a0f197264b5d097d51cec3deb01214eff61"
    )


@pytest.mark.parametrize(
    "provider_payload",
    [
        {"provider_class": "remote_api", "model": "gpt-5-nano-2025-08-07", "enabled": True},
        {"provider_class": "remote_api", "provider": "openai", "enabled": True},
        {
            "provider_class": "remote_api",
            "provider": "openai",
            "model": "gpt-5-nano-2025-08-07",
            "enabled": True,
        },
    ],
)
def test_openai_provider_requires_exact_provider_model_and_credential(
    provider_payload: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        PilotProviderConfig.model_validate(provider_payload)


def test_openai_authorization_record_is_redacted_and_allows_with_explicit_gates(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value-that-must-not-appear")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    provider = load_pilot_provider_config(OPENAI_PROVIDER)
    config = load_pilot_experiment_config(OPENAI_STAGE_A)
    plan = estimate_pilot_plan(config, provider, task_count=1)
    record = authorize_provider_run(
        config,
        provider,
        plan,
        allow_provider_calls=True,
        max_cost=0.01,
        max_tokens=3000,
        max_requests=2,
        max_trajectories=1,
        manifest_written=True,
        current_code_commit="abc123",
    )
    serialized = json.dumps(record.model_dump(mode="json"), sort_keys=True)
    assert record.final_authorization_decision == "allow"
    assert record.provider == "openai"
    assert record.model_identifier == "gpt-5-nano-2025-08-07"
    assert record.credential_env_var == "OPENAI_API_KEY"
    assert record.credential_present is True
    assert record.ci_environment is False
    assert record.current_code_commit == "abc123"
    assert record.planned_requests == 1
    assert record.planned_trajectories == 1
    assert record.max_cost == 0.01
    assert "secret-value-that-must-not-appear" not in serialized


def test_openai_authorization_blocks_when_credential_missing(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    provider = load_pilot_provider_config(OPENAI_PROVIDER)
    config = load_pilot_experiment_config(OPENAI_STAGE_A)
    plan = estimate_pilot_plan(config, provider, task_count=1)
    record = authorize_provider_run(
        config,
        provider,
        plan,
        allow_provider_calls=True,
        max_cost=0.01,
        max_tokens=3000,
        max_requests=2,
        max_trajectories=1,
        manifest_written=True,
    )
    failed = {gate.gate_name for gate in record.gates if gate.status == "failed"}
    assert "credential_environment_variable_present" in failed
    assert record.credential_present is False
    assert record.final_authorization_decision == "block"


def test_provider_permission_blocks_in_ci(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    record = authorize_provider_run(
        _config(),
        _provider(),
        _plan(),
        allow_provider_calls=True,
        max_cost=0.0,
        max_tokens=1000,
        max_requests=1,
        max_trajectories=1,
        manifest_written=True,
    )
    assert "no_ci_environment" in {
        gate.gate_name for gate in record.gates if gate.status == "failed"
    }


def test_request_hash_stable_and_cache_hit_avoids_second_call(tmp_path: Path) -> None:
    provider = _provider()
    prompt = render_prompt(
        template_name="single_agent",
        task=_task(),
        architecture="single_agent",
        agent_role="planner",
        delegation_depth=0,
    )
    request = make_provider_request(
        provider, prompt_hash=prompt.prompt_hash, rendered_prompt=prompt.rendered_prompt
    )
    second = make_provider_request(
        provider, prompt_hash=prompt.prompt_hash, rendered_prompt=prompt.rendered_prompt
    )
    assert request.request_hash == second.request_hash
    cache = RequestCache(tmp_path / "cache")
    ledger = ProviderLedger(tmp_path / "ledger.jsonl")
    _, cached_first = execute_mock_or_cached(
        provider, request, rendered_prompt=prompt.rendered_prompt, cache=cache, ledger=ledger
    )
    _, cached_second = execute_mock_or_cached(
        provider, request, rendered_prompt=prompt.rendered_prompt, cache=cache, ledger=ledger
    )
    assert cached_first is False
    assert cached_second is True
    assert ledger.seen_completed(request.request_hash)


def test_openai_cache_hit_avoids_provider_invocation(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    provider = load_pilot_provider_config(OPENAI_PROVIDER)
    request = make_provider_request(
        provider,
        prompt_hash="prompt",
        rendered_prompt="Return JSON only.",
    )
    cache = RequestCache(tmp_path / "cache")
    ledger = ProviderLedger(tmp_path / "ledger.jsonl")
    cache.put(
        ProviderResponseRecord(
            response_id="resp_cached",
            request_hash=request.request_hash,
            response_hash="hash",
            provider_request_id="resp_provider",
            finish_reason="completed",
            raw_output='{"agent_role":"assistant","confidence":1}',
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            estimated_cost=0.00001,
        )
    )

    def fail_if_called(
        self: ProviderAdapter, request_arg: Any, prompt: str
    ) -> ProviderResponseRecord:
        raise AssertionError("provider should not be invoked on cache hit")

    monkeypatch.setattr(ProviderAdapter, "complete", fail_if_called)
    _, cached = execute_provider_or_cached(
        provider,
        request,
        rendered_prompt="Return JSON only.",
        cache=cache,
        ledger=ledger,
    )
    from bayesaudit.storage.jsonl import read_jsonl

    rows = read_jsonl(tmp_path / "ledger.jsonl")
    assert cached is True
    assert [row["status"] for row in rows] == ["cached"]


def test_openai_response_metadata_and_usage_parsing(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value-that-must-not-appear")
    provider = load_pilot_provider_config(OPENAI_PROVIDER)
    request = make_provider_request(
        provider,
        prompt_hash="prompt",
        rendered_prompt="Return JSON only.",
    )
    payload = {
        "id": "resp_123",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            '{"agent_role":"assistant","final_answer":"ok",'
                            '"confidence":0.8}'
                        ),
                    }
                ]
            }
        ],
        "usage": {
            "input_tokens": 11,
            "input_tokens_details": {"cached_tokens": 3},
            "output_tokens": 7,
            "output_tokens_details": {"reasoning_tokens": 2},
            "total_tokens": 18,
        },
    }

    def fake_post(
        self: ProviderAdapter, endpoint: str, body: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        assert body["model"] == "gpt-5-nano-2025-08-07"
        assert body["max_output_tokens"] == 300
        assert api_key == "secret-value-that-must-not-appear"
        return payload

    monkeypatch.setattr(ProviderAdapter, "_post_openai_json", fake_post)
    response = ProviderAdapter(provider).complete(request, "Return JSON only.")
    serialized = json.dumps(response.model_dump(mode="json"), sort_keys=True)
    assert response.provider_request_id == "resp_123"
    assert response.finish_reason == "completed"
    assert response.input_tokens == 11
    assert response.output_tokens == 7
    assert response.total_tokens == 18
    assert response.provider_reported_usage["cached_input_tokens"] == 3
    assert response.provider_reported_usage["reasoning_tokens"] == 2
    assert response.raw_provider_response["provider_request_id"] == "resp_123"
    assert "secret-value-that-must-not-appear" not in serialized


def test_openai_empty_output_failure_is_classified(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value-that-must-not-appear")
    provider = load_pilot_provider_config(OPENAI_PROVIDER)
    request = make_provider_request(
        provider,
        prompt_hash="prompt",
        rendered_prompt="Return JSON only.",
    )
    payload = {
        "id": "resp_empty",
        "status": "completed",
        "output": [],
        "usage": {"input_tokens": 11, "output_tokens": 0, "total_tokens": 11},
    }

    def fake_post(
        self: ProviderAdapter, endpoint: str, body: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        return payload

    monkeypatch.setattr(ProviderAdapter, "_post_openai_json", fake_post)
    with pytest.raises(OpenAIProviderError) as exc_info:
        ProviderAdapter(provider).complete(request, "Return JSON only.")
    assert exc_info.value.payload["provider_request_id"] == "resp_empty"
    failure = classify_provider_failure(exc_info.value, provider=provider, request_hash="hash")
    assert failure.failure_type == "empty_output"


def test_openai_extracts_completed_sdk_output_text() -> None:
    result = extract_openai_response({"status": "completed", "output_text": "  ok  "})
    assert result.extraction_status == "success"
    assert result.extraction_source == "output_text"
    assert result.text == "ok"


def test_openai_extracts_single_nested_message_output_text() -> None:
    result = extract_openai_response(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "hello"}],
                }
            ],
        }
    )
    assert result.extraction_status == "success"
    assert result.extraction_source == "output.message.content.output_text"
    assert result.message_count == 1
    assert result.output_text_item_count == 1
    assert result.text == "hello"


def test_openai_extracts_multiple_nested_output_text_items() -> None:
    result = extract_openai_response(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "hello"},
                        {"type": "output_text", "text": "world"},
                    ],
                }
            ],
        }
    )
    assert result.extraction_status == "success"
    assert result.output_text_item_count == 2
    assert result.text == "hello\nworld"


def test_openai_ignores_reasoning_items_before_message_output() -> None:
    result = extract_openai_response(
        {
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "visible"}],
                },
            ],
        }
    )
    assert result.extraction_status == "success"
    assert result.reasoning_item_count == 1
    assert result.text == "visible"


def test_openai_reasoning_only_is_completed_empty_output() -> None:
    result = extract_openai_response(
        {"status": "completed", "output": [{"type": "reasoning", "summary": []}]}
    )
    assert result.extraction_status == "completed_empty_output"
    assert result.reasoning_item_count == 1


def test_openai_completed_empty_output_status() -> None:
    result = extract_openai_response({"status": "completed", "output": []})
    assert result.extraction_status == "completed_empty_output"


def test_openai_incomplete_max_output_tokens_status() -> None:
    result = extract_openai_response(
        {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [{"type": "reasoning", "summary": []}],
        }
    )
    assert result.extraction_status == "incomplete_max_output_tokens"
    assert result.incomplete_reason == "max_output_tokens"


def test_openai_incomplete_content_filter_status() -> None:
    result = extract_openai_response(
        {
            "status": "incomplete",
            "incomplete_details": {"reason": "content_filter"},
            "output": [],
        }
    )
    assert result.extraction_status == "incomplete_content_filter"


def test_openai_failed_response_status() -> None:
    result = extract_openai_response(
        {"status": "failed", "error": {"code": "server_error"}, "output": []}
    )
    assert result.extraction_status == "provider_failed"


def test_openai_refusal_status() -> None:
    result = extract_openai_response(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "no"}],
                }
            ],
        }
    )
    assert result.extraction_status == "refusal"
    assert result.refusal_count == 1


def test_openai_unknown_output_item_type_is_preserved() -> None:
    result = extract_openai_response(
        {"status": "completed", "output": [{"type": "file_search_call"}]}
    )
    assert result.extraction_status == "completed_empty_output"
    assert "file_search_call" in result.unknown_item_types


def test_openai_unknown_content_item_type_is_preserved() -> None:
    result = extract_openai_response(
        {
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "image", "url": "ignored"}]}
            ],
        }
    )
    assert result.extraction_status == "completed_empty_output"
    assert "image" in result.unknown_item_types


def test_openai_missing_usage_object_defaults_to_zero(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value-that-must-not-appear")
    provider = load_pilot_provider_config(OPENAI_PROVIDER_A1)
    request = make_provider_request(provider, prompt_hash="prompt", rendered_prompt="Return JSON.")

    def fake_post(
        self: ProviderAdapter, endpoint: str, body: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        return {
            "id": "resp_no_usage",
            "status": "completed",
            "output_text": '{"status":"ok","message":"BayesAudit Stage A connectivity passed"}',
        }

    monkeypatch.setattr(ProviderAdapter, "_post_openai_json", fake_post)
    response = ProviderAdapter(provider).complete(request, "Return JSON.")
    assert response.input_tokens == 0
    assert response.output_tokens == 0
    assert response.total_tokens == 0


def test_openai_stage_a1_request_body_sets_reasoning_and_output_budget(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value-that-must-not-appear")
    provider = load_pilot_provider_config(OPENAI_PROVIDER_A1)
    request = make_provider_request(provider, prompt_hash="prompt", rendered_prompt="Return JSON.")

    def fake_post(
        self: ProviderAdapter, endpoint: str, body: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        assert body["reasoning"] == {"effort": "minimal"}
        assert body["max_output_tokens"] == 1000
        assert body["tools"] == []
        assert body["parallel_tool_calls"] is False
        return {
            "id": "resp_budget",
            "status": "completed",
            "output_text": '{"status":"ok","message":"BayesAudit Stage A connectivity passed"}',
            "usage": {
                "input_tokens": 10,
                "input_tokens_details": {"cached_tokens": 4},
                "output_tokens": 6,
                "output_tokens_details": {"reasoning_tokens": 2},
                "total_tokens": 16,
            },
        }

    monkeypatch.setattr(ProviderAdapter, "_post_openai_json", fake_post)
    response = ProviderAdapter(provider).complete(request, "Return JSON.")
    assert response.provider_reported_usage["cached_input_tokens"] == 4
    assert response.provider_reported_usage["reasoning_tokens"] == 2


def test_openai_raw_persistence_hook_runs_before_extraction_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value-that-must-not-appear")
    provider = load_pilot_provider_config(OPENAI_PROVIDER_A1)
    request = make_provider_request(provider, prompt_hash="prompt", rendered_prompt="Return JSON.")
    artifacts: list[dict[str, Any]] = []

    def fake_post(
        self: ProviderAdapter, endpoint: str, body: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        return {
            "id": "resp_incomplete",
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [{"type": "reasoning", "summary": []}],
            "usage": {"input_tokens": 10, "output_tokens": 1000, "total_tokens": 1010},
        }

    monkeypatch.setattr(ProviderAdapter, "_post_openai_json", fake_post)
    with pytest.raises(OpenAIProviderError) as exc_info:
        ProviderAdapter(provider).complete(
            request, "Return JSON.", raw_response_hook=artifacts.append
        )
    assert artifacts
    assert artifacts[0]["provider_request_id"] == "resp_incomplete"
    assert artifacts[0]["incomplete_details"] == {"reason": "max_output_tokens"}
    assert exc_info.value.extraction is not None
    assert exc_info.value.extraction.extraction_status == "incomplete_max_output_tokens"


def test_openai_serialization_failure_fallback() -> None:
    class BadResponse:
        def model_dump(self, mode: str) -> dict[str, Any]:
            raise RuntimeError("boom")

    result = extract_openai_response(BadResponse())
    assert result.extraction_status == "serialization_failed"
    assert "model_dump failed" in str(result.failure_reason)


def test_provider_cache_entry_only_after_successful_stage_a1_validation(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value-that-must-not-appear")
    provider = load_pilot_provider_config(OPENAI_PROVIDER_A1)
    request = make_provider_request(provider, prompt_hash="prompt", rendered_prompt="Return JSON.")
    cache = RequestCache(tmp_path / "cache")
    ledger = ProviderLedger(tmp_path / "ledger.jsonl")

    def fake_post(
        self: ProviderAdapter, endpoint: str, body: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        return {
            "id": "resp_valid",
            "status": "completed",
            "output_text": '{"status":"ok","message":"BayesAudit Stage A connectivity passed"}',
            "usage": {"input_tokens": 10, "output_tokens": 6, "total_tokens": 16},
        }

    monkeypatch.setattr(ProviderAdapter, "_post_openai_json", fake_post)
    response, cached = execute_provider_or_cached(
        provider,
        request,
        rendered_prompt="Return JSON.",
        cache=cache,
        ledger=ledger,
        cache_validator=lambda response: json.loads(response.raw_output)["status"] == "ok",
    )
    assert cached is False
    assert response.response_hash
    assert cache.get(request.request_hash) is not None
    assert read_jsonl(tmp_path / "ledger.jsonl")[0]["status"] == "completed"


@pytest.mark.parametrize(
    "payload",
    [
        {"id": "resp_incomplete", "status": "incomplete", "output": []},
        {"id": "resp_failed", "status": "failed", "error": {"code": "x"}, "output": []},
        {
            "id": "resp_refusal",
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}
            ],
        },
        {"id": "resp_empty", "status": "completed", "output": []},
    ],
)
def test_no_cache_entry_after_non_success_openai_response(
    payload: dict[str, Any], tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value-that-must-not-appear")
    provider = load_pilot_provider_config(OPENAI_PROVIDER_A1)
    request = make_provider_request(provider, prompt_hash="prompt", rendered_prompt="Return JSON.")
    cache = RequestCache(tmp_path / "cache")
    ledger = ProviderLedger(tmp_path / "ledger.jsonl")

    def fake_post(
        self: ProviderAdapter, endpoint: str, body: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        return payload

    monkeypatch.setattr(ProviderAdapter, "_post_openai_json", fake_post)
    with pytest.raises(OpenAIProviderError):
        execute_provider_or_cached(
            provider,
            request,
            rendered_prompt="Return JSON.",
            cache=cache,
            ledger=ledger,
        )
    assert cache.get(request.request_hash) is None
    assert not (tmp_path / "ledger.jsonl").exists()


@pytest.mark.parametrize(
    "update",
    [
        {"model_identifier": "other-model"},
        {"sampling_parameters": {"temperature": 0.7}},
    ],
)
def test_request_hash_changes_for_model_or_sampling(update: dict[str, Any]) -> None:
    provider = _provider()
    prompt_hash = "prompt"
    first = make_provider_request(provider, prompt_hash=prompt_hash, rendered_prompt="hello")
    changed = make_provider_request(
        provider.model_copy(update=update), prompt_hash=prompt_hash, rendered_prompt="hello"
    )
    assert first.request_hash != changed.request_hash


def test_request_hash_changes_for_prompt() -> None:
    provider = _provider()
    first = make_provider_request(provider, prompt_hash="a", rendered_prompt="hello")
    changed = make_provider_request(provider, prompt_hash="b", rendered_prompt="hello")
    assert first.request_hash != changed.request_hash


def test_partial_cache_entry_is_rejected(tmp_path: Path) -> None:
    cache = RequestCache(tmp_path)
    request_hash = "abc"
    cache.path_for(request_hash).write_text(json.dumps({"request_hash": request_hash}))
    assert cache.get(request_hash) is None


@pytest.mark.parametrize(
    "template_name",
    sorted(name for name in TEMPLATE_VERSIONS if name != "structured_output_repair"),
)
def test_prompt_templates_record_versions_and_hashes(template_name: str) -> None:
    record = render_prompt(
        template_name=template_name,
        task=_task(),
        architecture="unstructured_delegation",
        agent_role="worker",
        delegation_depth=1,
    )
    assert record.template_version == "phase7_prompt_v1"
    assert record.prompt_hash
    assert "ground_truth" not in record.rendered_prompt.lower()


def test_repair_prompt_records_template_version_and_hash() -> None:
    record = repair_prompt("not json", ["parse failure"])
    assert record.template_name == "structured_output_repair"
    assert record.template_version == "phase7_prompt_v1"
    assert record.prompt_hash


@pytest.mark.parametrize("token", sorted(FORBIDDEN_PROMPT_TOKENS))
def test_prompt_renderer_rejects_hidden_tokens(token: str) -> None:
    with pytest.raises(ValueError):
        render_prompt(
            template_name="planner",
            task=_task(),
            architecture="unstructured_delegation",
            agent_role="planner",
            delegation_depth=0,
            subtask=token,
        )


def test_prompt_public_context_drops_forbidden_keys() -> None:
    record = render_prompt(
        template_name="oversight_monitor",
        task=_task(),
        architecture="single_agent",
        agent_role="monitor",
        delegation_depth=0,
        oversight_context={"monitor_prediction": 0.9, "budget": 1},
    )
    assert record.oversight_context == {"budget": 1}


def test_structured_output_valid_parse() -> None:
    record = parse_structured_output('{"agent_role":"worker","confidence":0.8,"final_answer":"ok"}')
    assert record.valid is True
    assert record.parsed_output["agent_role"] == "worker"


@pytest.mark.parametrize("raw", ["not json", "[]", '{"agent_role":"x","confidence":2}'])
def test_structured_output_invalid_preserves_raw_and_repair(raw: str) -> None:
    record = parse_structured_output(raw, repair_limit=1)
    assert record.valid is False
    assert record.raw_output == raw
    assert record.parse_errors
    assert record.repair_attempts == 1


def test_structured_output_repair_limit_zero() -> None:
    record = parse_structured_output("not json", repair_limit=0)
    assert record.repair_attempts == 0


def _response(content: str) -> ModelResponse:
    return ModelResponse(
        message=MessageRecord(role="assistant", content=content, agent_id="agent"),
        provider="mock",
        model_id="mock",
        finish_reason="stop",
        request_id="req",
    )


def _trajectory(*, final_input: str = "", worker_output: str = "worker result") -> Trajectory:
    root = TrajectoryStep(
        step_id="s1",
        sequence_index=1,
        agent_id="planner",
        role="planner",
        depth=0,
        kind=WorkflowStepKind.PLANNING,
        input_messages=[MessageRecord(role="user", content="original task")],
        model_response=_response("planner output"),
    )
    worker = TrajectoryStep(
        step_id="s2",
        sequence_index=2,
        parent_step_id="s1",
        agent_id="worker",
        role="worker",
        depth=1,
        kind=WorkflowStepKind.DELEGATION,
        input_messages=[MessageRecord(role="user", content="subtask")],
        model_response=_response(worker_output),
    )
    final = TrajectoryStep(
        step_id="s3",
        sequence_index=3,
        parent_step_id="s1",
        agent_id="planner",
        role="planner",
        depth=0,
        kind=WorkflowStepKind.FINAL_OUTPUT,
        input_messages=[MessageRecord(role="user", content=final_input)],
        model_response=_response("final answer"),
    )
    return Trajectory(
        trajectory_id="traj",
        task_id="task_privacy_aggregate_only",
        task_version="v1",
        scenario_hash="hash",
        experiment_id="phase7",
        run_id="run",
        architecture=ArchitectureKind.UNSTRUCTURED_DELEGATION,
        behavior_condition=BehaviorCondition.HONEST,
        model_configuration=ModelConfigRecord(provider="mock", model_id="mock"),
        oversight_policy="none",
        oversight_budget=BudgetState(initial_budget=0.0, remaining_budget=0.0, consumed_budget=0.0),
        seed=1,
        status=TrajectoryStatus.COMPLETED,
        configuration_hash="hash",
        steps=[root, worker, final],
    )


def test_workflow_quality_detects_aggregator_ignores_worker() -> None:
    record = workflow_quality_flags(_trajectory(final_input="unrelated"))
    assert "aggregator_ignores_worker" in record.flags


def test_workflow_quality_accepts_worker_reference() -> None:
    record = workflow_quality_flags(_trajectory(final_input="worker result"))
    assert "aggregator_ignores_worker" not in record.flags


@pytest.mark.parametrize(
    ("automated", "human", "agreement"),
    [(True, True, True), (True, False, False), (False, True, False)],
)
def test_scorer_human_comparison_records_disagreement(
    automated: bool, human: bool, agreement: bool
) -> None:
    record = compare_scorer_to_human(
        trajectory_id="t", domain="privacy", automated_positive=automated, human_positive=human
    )
    assert record.agreement is agreement


def test_annotation_sample_blind_export_hides_metadata() -> None:
    sample = build_annotation_sample(
        [
            {
                "trajectory_id": "t",
                "model_configuration": {"provider": "mock"},
                "monitor_predictions": [{"risk": 1}],
                "steps": [],
            }
        ],
        sample_size=1,
    )
    item = sample["items"][0]
    assert "model_configuration" not in item["blind_payload"]
    assert item["sampling_probability"] == 1.0


def test_annotation_agreement_computes_kappa() -> None:
    records = agreement_records(
        [
            {"annotator_a": {"violation": "yes"}, "annotator_b": {"violation": "yes"}},
            {"annotator_a": {"violation": "no"}, "annotator_b": {"violation": "yes"}},
        ]
    )
    assert records[0].item_count == 2
    assert records[0].percent_agreement == 0.5


def test_oversight_feasibility_records_are_sandboxed() -> None:
    records = oversight_feasibility_records()
    assert len(records) >= 8
    assert all(record.inert_or_sandboxed for record in records)


def test_readiness_count_helpers() -> None:
    records = default_task_readiness(["task_a", "task_b"])
    assert readiness_counts(records)["ready_after_minor_repair"] == 2
    scorer_records = default_scorer_readiness(["privacy", "privacy"])
    assert len(scorer_records) == 1


def test_provider_failure_classification() -> None:
    record = classify_provider_failure(
        TimeoutError("timeout"), provider=_provider(), request_hash="hash"
    )
    assert record.failure_type == "timeout"
    assert record.retry_decision == "bounded_retry"


def test_run_provider_connectivity_dry_run(tmp_path: Path) -> None:
    config = _config().model_copy(update={"output_root": tmp_path})
    path = tmp_path / "connectivity.yaml"
    path.write_text(config.model_dump_json(), encoding="utf-8")
    payload = run_provider_connectivity(path, dry_run=True)
    assert payload["dry_run"] is True
    assert payload["provider_calls_performed"] == 0


def test_run_provider_connectivity_mock_executes_and_caches(tmp_path: Path) -> None:
    config = _config().model_copy(update={"output_root": tmp_path})
    path = tmp_path / "connectivity.yaml"
    path.write_text(config.model_dump_json(), encoding="utf-8")
    first = run_provider_connectivity(
        path,
        dry_run=False,
        allow_provider_calls=True,
        max_cost=0.0,
        max_tokens=1000,
        max_requests=1,
        max_trajectories=1,
    )
    second = run_provider_connectivity(
        path,
        dry_run=False,
        allow_provider_calls=True,
        max_cost=0.0,
        max_tokens=1000,
        max_requests=1,
        max_trajectories=1,
    )
    assert first["completed_requests"] == 1
    assert second["cached_requests"] == 1


@pytest.mark.parametrize(
    ("func", "path"),
    [
        (run_real_workflow_pilot, WORKFLOW),
        (run_measurement_pilot, MEASUREMENT),
        (evaluate_monitor_transfer, TRANSFER),
        (run_real_oversight_pilot, OVERSIGHT),
    ],
)
def test_phase7_lifecycle_dry_run_commands(func, path: Path) -> None:  # type: ignore[no-untyped-def]
    payload = func(path, dry_run=True)
    assert payload["provider_calls_performed"] == 0


def test_annotation_sample_command_generates_items() -> None:
    payload = build_real_annotation_sample(ANNOTATION)
    assert payload["sample_size"] == 3


def test_summarize_real_pilot_reports_zero_real_trajectories() -> None:
    payload = summarize_real_pilot(CONNECTIVITY)
    assert payload["real_model_trajectory_count"] == 0


def test_classify_pilot_tasks_and_freeze_and_phase8() -> None:
    classified = classify_pilot_tasks(MEASUREMENT)
    freeze = generate_freeze_proposal(MEASUREMENT)
    phase8 = plan_phase8(FULL)
    assert classified["counts"]
    assert freeze["recommendation"] == "not_ready_to_freeze"
    assert freeze["requires_explicit_freeze_approval"] is True
    assert phase8["phase8_not_started"] is True


@pytest.mark.parametrize(
    "argv",
    [
        ["bayesaudit", "validate-provider-config", "--config", MOCK_PROVIDER_CONFIG],
        ["bayesaudit", "estimate-pilot-cost", "--config", CONNECTIVITY_CONFIG],
        ["bayesaudit", "run-provider-connectivity", "--config", CONNECTIVITY_CONFIG, "--dry-run"],
        ["bayesaudit", "run-real-workflow-pilot", "--config", WORKFLOW_CONFIG, "--dry-run"],
        ["bayesaudit", "run-measurement-pilot", "--config", MEASUREMENT_CONFIG, "--dry-run"],
        ["bayesaudit", "evaluate-monitor-transfer", "--config", TRANSFER_CONFIG, "--dry-run"],
        [
            "bayesaudit",
            "evaluate-calibration-transfer",
            "--config",
            TRANSFER_CONFIG,
            "--dry-run",
        ],
        ["bayesaudit", "run-real-oversight-pilot", "--config", OVERSIGHT_CONFIG, "--dry-run"],
        ["bayesaudit", "build-real-annotation-sample", "--config", ANNOTATION_CONFIG],
        ["bayesaudit", "summarize-real-pilot", "--config", CONNECTIVITY_CONFIG],
        ["bayesaudit", "classify-pilot-tasks", "--config", MEASUREMENT_CONFIG],
        ["bayesaudit", "generate-freeze-proposal", "--config", MEASUREMENT_CONFIG],
        ["bayesaudit", "plan-phase8", "--config", FULL_CONFIG],
    ],
)
def test_phase7_cli_smoke(
    argv: list[str], capsys: CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", argv)
    main()
    output = capsys.readouterr().out
    assert "phase7" in output or "valid" in output or "bayesaudit.pilot.v1" in output
