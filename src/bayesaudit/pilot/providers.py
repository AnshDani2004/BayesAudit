"""Provider safety gates, request caching, and mock-safe adapters for Phase 7."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from bayesaudit.hash_utils import canonical_json_hash, text_hash
from bayesaudit.pilot.types import (
    PermissionGateRecord,
    PilotExperimentConfig,
    PilotPlan,
    PilotProviderConfig,
    ProviderFailureRecord,
    ProviderPermissionRecord,
    ProviderRequestRecord,
    ProviderResponseRecord,
)
from bayesaudit.storage.jsonl import append_jsonl, read_json, read_jsonl, write_json_atomic


class ProviderAdapter:
    def __init__(self, config: PilotProviderConfig) -> None:
        self.config = config

    def validate_dry_run(self) -> dict[str, Any]:
        return {
            "provider_class": self.config.provider_class,
            "provider_name": self.provider_name,
            "model_identifier": self.model_identifier,
            "valid": True,
            "real_call_performed": False,
        }

    @property
    def provider_name(self) -> str:
        return self.config.provider_name or self.config.provider_class

    @property
    def model_identifier(self) -> str:
        return self.config.model_identifier or "mock-deterministic-v1"

    def complete_mock(self, request: ProviderRequestRecord, prompt: str) -> ProviderResponseRecord:
        del prompt
        raw_output = (
            '{"agent_role":"assistant","final_answer":"mock connectivity ok",'
            '"confidence":0.9,"constraint_acknowledgments":["synthetic"]}'
        )
        return ProviderResponseRecord(
            response_id="resp_" + request.request_hash[:20],
            request_hash=request.request_hash,
            response_hash=text_hash(raw_output),
            provider_request_id="mock-provider-" + request.request_hash[:12],
            finish_reason="stop",
            raw_output=raw_output,
            parsed_output={
                "agent_role": "assistant",
                "final_answer": "mock connectivity ok",
                "confidence": 0.9,
                "constraint_acknowledgments": ["synthetic"],
            },
            provider_reported_usage={
                "input_tokens": request.estimated_input_tokens,
                "output_tokens": request.estimated_output_tokens,
            },
            input_tokens=request.estimated_input_tokens,
            output_tokens=request.estimated_output_tokens,
            total_tokens=request.estimated_input_tokens + request.estimated_output_tokens,
            estimated_cost=request.estimated_cost,
        )


def adapter_for(config: PilotProviderConfig) -> ProviderAdapter:
    return ProviderAdapter(config)


def estimate_pilot_plan(
    config: PilotExperimentConfig,
    provider: PilotProviderConfig,
    *,
    task_count: int,
) -> PilotPlan:
    architecture_count = max(1, len(config.architectures))
    depth_count = max(1, len(config.delegation_depths))
    behavior_count = max(1, len(config.behavior_conditions))
    attacker_count = max(1, len(config.attacker_conditions))
    policy_count = max(1, len(config.oversight_conditions))
    seed_count = max(1, len(config.seeds))
    branch_count = max(1, len(config.branching_factors))
    planned_trajectories = (
        max(1, task_count)
        * architecture_count
        * depth_count
        * branch_count
        * behavior_count
        * attacker_count
        * policy_count
        * seed_count
    )
    if config.max_runs is not None:
        planned_trajectories = min(planned_trajectories, int(config.max_runs))
    planned_requests = planned_trajectories * _requests_per_trajectory(config.stage)
    estimated_input_tokens = planned_requests * provider.estimated_input_tokens_per_request
    estimated_output_tokens = planned_requests * provider.estimated_output_tokens_per_request
    estimated_cost = (
        estimated_input_tokens / 1000.0 * provider.estimated_cost_per_1k_input_tokens
        + estimated_output_tokens / 1000.0 * provider.estimated_cost_per_1k_output_tokens
    )
    maximum_possible_cost = estimated_cost * (1.0 + float(provider.max_retries))
    payload = {
        "config": config.model_dump(mode="json"),
        "provider": provider.model_dump(mode="json"),
        "task_count": task_count,
        "planned_requests": planned_requests,
    }
    return PilotPlan(
        pilot_id=config.pilot_id,
        stage=config.stage,
        provider=provider.provider_name or provider.provider_class,
        model_identifier=provider.model_identifier,
        task_count=task_count,
        architecture_count=architecture_count,
        depth_count=depth_count,
        behavior_count=behavior_count,
        attacker_count=attacker_count,
        policy_count=policy_count,
        seed_count=seed_count,
        planned_trajectories=planned_trajectories,
        planned_requests=planned_requests,
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        estimated_total_tokens=estimated_input_tokens + estimated_output_tokens,
        estimated_cost=estimated_cost,
        maximum_possible_cost=maximum_possible_cost,
        cache_hit_assumption="zero cache hits for conservative pre-run planning",
        retry_assumption=f"up to {provider.max_retries} bounded retries per request",
        storage_estimate_mb=round(max(0.01, planned_requests * 0.02), 4),
        configuration_hash=canonical_json_hash(payload),
    )


def authorize_provider_run(
    config: PilotExperimentConfig,
    provider: PilotProviderConfig,
    plan: PilotPlan,
    *,
    allow_provider_calls: bool,
    max_cost: float | None,
    max_tokens: int | None,
    max_requests: int | None,
    max_trajectories: int | None,
    allow_large_run: bool = False,
    output_writable: bool = True,
    manifest_written: bool = False,
) -> ProviderPermissionRecord:
    gates = [
        _gate("provider_calls_enabled_in_config", provider.enabled, "provider config enabled"),
        _gate("cli_allow_provider_calls", allow_provider_calls, "CLI allow flag supplied"),
        _gate("provider_named", bool(provider.provider_name), "provider name is explicit"),
        _gate("model_identifier_named", bool(provider.model_identifier), "model ID is explicit"),
        _credential_gate(provider),
        _gate("cost_ceiling_set", max_cost is not None, "cost ceiling supplied on CLI"),
        _gate("token_ceiling_set", max_tokens is not None, "token ceiling supplied on CLI"),
        _gate("request_ceiling_set", max_requests is not None, "request ceiling supplied on CLI"),
        _gate(
            "trajectory_ceiling_set",
            max_trajectories is not None,
            "trajectory ceiling supplied on CLI",
        ),
        _gate(
            "estimated_cost_within_ceiling",
            max_cost is not None and plan.estimated_cost <= float(max_cost),
            "estimated cost within ceiling",
        ),
        _gate(
            "estimated_tokens_within_ceiling",
            max_tokens is not None and plan.estimated_total_tokens <= int(max_tokens),
            "estimated tokens within ceiling",
        ),
        _gate(
            "planned_requests_within_ceiling",
            max_requests is not None and plan.planned_requests <= int(max_requests),
            "planned requests within ceiling",
        ),
        _gate(
            "planned_trajectories_within_ceiling",
            max_trajectories is not None
            and plan.planned_trajectories <= int(max_trajectories),
            "planned trajectories within ceiling",
        ),
        _gate(
            "large_run_protection",
            allow_large_run or plan.planned_trajectories <= config.large_run_threshold,
            "large-run threshold satisfied",
        ),
        _gate("configuration_valid", True, "configuration parsed successfully"),
        _gate("pilot_manifest_written", manifest_written, "pilot manifest exists before calls"),
        _gate("output_location_writable", output_writable, "output location is writable"),
        _gate(
            "provider_adapter_dry_run_valid",
            adapter_for(provider).validate_dry_run()["valid"] is True,
            "adapter dry-run validation passed",
        ),
        _gate(
            "no_ci_environment",
            not _ci_environment(),
            "CI environment is not detected",
        ),
    ]
    allowed = all(gate.status == "passed" for gate in gates)
    record = ProviderPermissionRecord(
        permission_id="perm_" + canonical_json_hash([gate.model_dump() for gate in gates])[:20],
        provider=provider.provider_name or provider.provider_class,
        model_identifier=provider.model_identifier,
        configuration_hash=plan.configuration_hash,
        command_line_authorization=allow_provider_calls,
        environment_classification="ci" if _ci_environment() else "local",
        gates=gates,
        final_authorization_decision="allow" if allowed else "block",
    )
    return record


def write_permission_record(root: Path, record: ProviderPermissionRecord) -> Path:
    path = root / "permission_records" / f"{record.permission_id}.json"
    write_json_atomic(path, record.model_dump(mode="json"))
    return path


def make_provider_request(
    provider: PilotProviderConfig,
    *,
    prompt_hash: str,
    rendered_prompt: str,
    sampling_parameters: dict[str, Any] | None = None,
) -> ProviderRequestRecord:
    sampling = sampling_parameters or provider.sampling_parameters
    request_hash = canonical_json_hash(
        {
            "provider": provider.provider_name or provider.provider_class,
            "model": provider.model_identifier or "mock-deterministic-v1",
            "prompt_hash": prompt_hash,
            "sampling": sampling,
        }
    )
    estimated_input = max(
        provider.estimated_input_tokens_per_request, len(rendered_prompt.split())
    )
    estimated_output = provider.estimated_output_tokens_per_request
    estimated_cost = (
        estimated_input / 1000.0 * provider.estimated_cost_per_1k_input_tokens
        + estimated_output / 1000.0 * provider.estimated_cost_per_1k_output_tokens
    )
    return ProviderRequestRecord(
        request_id="req_" + request_hash[:20],
        request_hash=request_hash,
        prompt_hash=prompt_hash,
        provider=provider.provider_name or provider.provider_class,
        model_identifier=provider.model_identifier or "mock-deterministic-v1",
        sampling_parameters=sampling,
        timeout_seconds=provider.timeout_seconds,
        estimated_input_tokens=estimated_input,
        estimated_output_tokens=estimated_output,
        estimated_cost=estimated_cost,
    )


class RequestCache:
    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root

    def path_for(self, request_hash: str) -> Path:
        return self.cache_root / f"{request_hash}.json"

    def get(self, request_hash: str) -> ProviderResponseRecord | None:
        path = self.path_for(request_hash)
        if not path.exists():
            return None
        payload = read_json(path)
        if payload.get("request_hash") != request_hash or not payload.get("response_hash"):
            return None
        return ProviderResponseRecord.model_validate(payload)

    def put(self, response: ProviderResponseRecord) -> Path:
        path = self.path_for(response.request_hash)
        write_json_atomic(path, response.model_dump(mode="json"))
        return path


class ProviderLedger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def seen_completed(self, request_hash: str) -> bool:
        return any(
            row.get("request_hash") == request_hash and row.get("status") in {"completed", "cached"}
            for row in read_jsonl(self.path)
        )

    def append_request(self, request: ProviderRequestRecord) -> None:
        append_jsonl(self.path, request.model_dump(mode="json"))


def execute_mock_or_cached(
    provider: PilotProviderConfig,
    request: ProviderRequestRecord,
    *,
    rendered_prompt: str,
    cache: RequestCache,
    ledger: ProviderLedger,
) -> tuple[ProviderResponseRecord, bool]:
    cached = cache.get(request.request_hash)
    if cached is not None:
        cached_request = request.model_copy(update={"status": "cached", "attempt_count": 0})
        ledger.append_request(cached_request)
        return cached, True
    response = adapter_for(provider).complete_mock(
        request.model_copy(update={"status": "completed", "attempt_count": 1}),
        rendered_prompt,
    )
    cache.put(response)
    ledger.append_request(request.model_copy(update={"status": "completed", "attempt_count": 1}))
    return response, False


def classify_provider_failure(
    exc: Exception, *, provider: PilotProviderConfig, request_hash: str
) -> ProviderFailureRecord:
    message = str(exc).lower()
    failure_type = "unknown_provider_error"
    retry = "do_not_retry"
    if "auth" in message:
        failure_type = "authentication_failure"
    elif "rate" in message:
        failure_type = "rate_limit"
        retry = "bounded_retry"
    elif "timeout" in message:
        failure_type = "timeout"
        retry = "bounded_retry"
    elif "server" in message:
        failure_type = "provider_server_error"
        retry = "bounded_retry"
    elif "invalid" in message:
        failure_type = "invalid_request"
    return ProviderFailureRecord(
        failure_id="fail_"
        + canonical_json_hash({"request": request_hash, "message": str(exc)})[:20],
        failure_type=failure_type,
        provider=provider.provider_name or provider.provider_class,
        model_identifier=provider.model_identifier,
        request_hash=request_hash,
        attempt_count=1,
        retry_decision=retry,
        final_status="failed",
        message=str(exc),
    )


def _requests_per_trajectory(stage: str) -> int:
    return {
        "connectivity": 1,
        "workflow": 3,
        "measurement": 3,
        "monitor_transfer": 0,
        "oversight": 3,
        "annotation_sample": 0,
        "full_pilot": 3,
    }.get(stage, 1)


def _gate(name: str, passed: bool, reason: str) -> PermissionGateRecord:
    return PermissionGateRecord(
        gate_name=name,
        status="passed" if passed else "failed",
        reason=reason if passed else f"missing or failed: {reason}",
    )


def _credential_gate(provider: PilotProviderConfig) -> PermissionGateRecord:
    if provider.provider_class != "remote_api":
        return PermissionGateRecord(
            gate_name="credential_environment_variable_present",
            status="not_applicable",
            reason="credentials are not required for mock/local dry-run validation",
        )
    key = provider.credential_env_var
    return _gate(
        "credential_environment_variable_present",
        bool(key and os.environ.get(key)),
        "credential environment variable is present",
    )


def _ci_environment() -> bool:
    return os.environ.get("CI", "").lower() in {"1", "true", "yes"} or bool(
        os.environ.get("GITHUB_ACTIONS")
    )
