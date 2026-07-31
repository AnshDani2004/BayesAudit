"""Provider safety gates, request caching, and mock-safe adapters for Phase 7."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
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


class OpenAIProviderError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = payload or {}


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

    def complete(self, request: ProviderRequestRecord, prompt: str) -> ProviderResponseRecord:
        if self.config.provider_class == "mock":
            return self.complete_mock(request, prompt)
        if (
            self.config.provider_class == "remote_api"
            and (self.config.provider_name or "").lower() == "openai"
        ):
            return self._complete_openai(request, prompt)
        raise ValueError(f"unsupported provider adapter: {self.config.provider_class}")

    def _complete_openai(
        self, request: ProviderRequestRecord, prompt: str
    ) -> ProviderResponseRecord:
        credential_name = self.config.credential_env_var
        api_key = os.environ.get(credential_name or "")
        if not credential_name or not api_key:
            raise PermissionError("OpenAI credential environment variable is not present")
        endpoint = self.config.endpoint or "https://api.openai.com/v1/responses"
        max_output_tokens = int(
            self.config.sampling_parameters.get(
                "max_output_tokens", self.config.estimated_output_tokens_per_request
            )
            or self.config.estimated_output_tokens_per_request
        )
        body: dict[str, Any] = {
            "model": self.model_identifier,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
        }
        if "temperature" in self.config.sampling_parameters:
            body["temperature"] = self.config.sampling_parameters["temperature"]
        if "top_p" in self.config.sampling_parameters:
            body["top_p"] = self.config.sampling_parameters["top_p"]
        payload = self._post_openai_json(endpoint, body, api_key)
        raw_output = _extract_openai_text(payload)
        usage = _extract_openai_usage(payload)
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
        estimated_cost = _estimated_response_cost(self.config, input_tokens, output_tokens)
        if not raw_output:
            raise OpenAIProviderError(
                "OpenAI response did not contain output text", payload=payload
            )
        return ProviderResponseRecord(
            response_id="resp_" + text_hash(json.dumps(payload, sort_keys=True, default=str))[:20],
            request_hash=request.request_hash,
            response_hash=text_hash(raw_output),
            provider_request_id=str(payload.get("id") or ""),
            finish_reason=_extract_openai_finish_reason(payload),
            raw_output=raw_output,
            raw_provider_response=payload,
            parsed_output={},
            provider_reported_usage=usage,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            provider_reported_cost=None,
        )

    def _post_openai_json(
        self, endpoint: str, body: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        data = json.dumps(body, sort_keys=True).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_error: Exception | None = None
        attempts = int(self.config.max_retries) + 1
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(
                    request, timeout=int(self.config.timeout_seconds)
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("OpenAI response payload was not a JSON object")
                return payload
            except Exception as exc:
                last_error = exc
                if attempt >= attempts - 1 or not _retryable_openai_error(exc):
                    break
                time.sleep(float(self.config.backoff_initial_seconds) * (2**attempt))
        raise _redacted_openai_exception(last_error)


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
    current_code_commit: str | None = None,
) -> ProviderPermissionRecord:
    gates = [
        _gate("provider_calls_enabled_in_config", provider.enabled, "provider config enabled"),
        _gate(
            "experiment_provider_calls_enabled",
            config.provider_calls_enabled,
            "experiment config enables provider calls",
        ),
        _gate("provider_cache_enabled", provider.cache_enabled, "provider cache enabled"),
        _gate("experiment_cache_enabled", config.cache_enabled, "experiment cache enabled"),
        _gate("provider_resume_enabled", provider.resume_enabled, "provider resume enabled"),
        _gate("experiment_resume_enabled", config.resume_enabled, "experiment resume enabled"),
        _gate(
            "provider_raw_response_preservation_enabled",
            provider.raw_response_preservation_enabled,
            "provider raw-response preservation enabled",
        ),
        _gate(
            "provider_secret_redaction_enabled",
            provider.secret_redaction_enabled,
            "provider secret redaction enabled",
        ),
        _gate(
            "provider_external_tools_disabled",
            not provider.external_tools_enabled,
            "provider external tools disabled",
        ),
        _gate(
            "experiment_external_tools_disabled",
            not config.external_tools_enabled,
            "experiment external tools disabled",
        ),
        _gate(
            "provider_fallback_model_absent",
            not provider.fallback_model_identifier,
            "provider fallback model absent",
        ),
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
        credential_env_var=provider.credential_env_var,
        credential_present=bool(
            provider.credential_env_var and os.environ.get(provider.credential_env_var)
        ),
        ci_environment=_ci_environment(),
        current_code_commit=current_code_commit,
        configuration_hash=plan.configuration_hash,
        command_line_authorization=allow_provider_calls,
        planned_requests=plan.planned_requests,
        planned_trajectories=plan.planned_trajectories,
        estimated_input_tokens=plan.estimated_input_tokens,
        estimated_output_tokens=plan.estimated_output_tokens,
        estimated_total_tokens=plan.estimated_total_tokens,
        estimated_cost=plan.estimated_cost,
        max_cost=max_cost,
        max_tokens=max_tokens,
        max_requests=max_requests,
        max_trajectories=max_trajectories,
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


def execute_provider_or_cached(
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
    response = adapter_for(provider).complete(
        request.model_copy(update={"status": "completed", "attempt_count": 1}),
        rendered_prompt,
    )
    cache.put(response)
    ledger.append_request(request.model_copy(update={"status": "completed", "attempt_count": 1}))
    return response, False


def execute_mock_or_cached(
    provider: PilotProviderConfig,
    request: ProviderRequestRecord,
    *,
    rendered_prompt: str,
    cache: RequestCache,
    ledger: ProviderLedger,
) -> tuple[ProviderResponseRecord, bool]:
    return execute_provider_or_cached(
        provider,
        request,
        rendered_prompt=rendered_prompt,
        cache=cache,
        ledger=ledger,
    )


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
    elif "did not contain output text" in message or "empty" in message:
        failure_type = "empty_output"
    elif "invalid" in message:
        failure_type = "invalid_request"
    elif "context" in message:
        failure_type = "context_length_failure"
    elif "content" in message and "filter" in message:
        failure_type = "content_filter"
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


def _extract_openai_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    parts: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "\n".join(part for part in parts if part.strip())


def _extract_openai_usage(payload: dict[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {}
    normalized = dict(usage)
    input_details = usage.get("input_tokens_details")
    if isinstance(input_details, dict):
        normalized["cached_input_tokens"] = int(input_details.get("cached_tokens", 0) or 0)
    output_details = usage.get("output_tokens_details")
    if isinstance(output_details, dict):
        normalized["reasoning_tokens"] = int(output_details.get("reasoning_tokens", 0) or 0)
    return normalized


def _extract_openai_finish_reason(payload: dict[str, Any]) -> str:
    if payload.get("status"):
        return str(payload["status"])
    incomplete = payload.get("incomplete_details")
    if isinstance(incomplete, dict) and incomplete.get("reason"):
        return "incomplete:" + str(incomplete["reason"])
    return "unknown"


def _estimated_response_cost(
    provider: PilotProviderConfig, input_tokens: int, output_tokens: int
) -> float:
    return (
        input_tokens / 1000.0 * provider.estimated_cost_per_1k_input_tokens
        + output_tokens / 1000.0 * provider.estimated_cost_per_1k_output_tokens
    )


def _retryable_openai_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in {408, 409, 429, 500, 502, 503, 504}
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, urllib.error.URLError):
        return True
    message = str(exc).lower()
    return "timeout" in message or "rate" in message or "server" in message


def _redacted_openai_exception(exc: Exception | None) -> Exception:
    if exc is None:
        return RuntimeError("unknown OpenAI provider error")
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read().decode("utf-8", errors="replace")
        return RuntimeError(f"openai_http_error status={exc.code} body={_redact(body)}")
    return RuntimeError(_redact(str(exc)))


def _redact(text: str) -> str:
    redacted = text
    for key_name in ("OPENAI_API_KEY",):
        key = os.environ.get(key_name)
        if key:
            redacted = redacted.replace(key, "[REDACTED]")
    return redacted
