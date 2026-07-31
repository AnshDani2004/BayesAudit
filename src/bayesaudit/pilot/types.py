"""Versioned Phase 7 pilot artifact schemas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    model_validator,
)

from bayesaudit.schemas import ArchitectureKind, Domain, StrictModel, utc_now

PILOT_SCHEMA_VERSION = "bayesaudit.pilot.v1"
PILOT_ARTIFACT_VERSION = "phase7_v1"
PROMPT_RENDERER_VERSION = "phase7_prompt_v1"

ProviderClass = Literal["mock", "remote_api", "local"]
PilotStage = Literal[
    "connectivity",
    "workflow",
    "measurement",
    "monitor_transfer",
    "oversight",
    "annotation_sample",
    "full_pilot",
]
PilotStatus = Literal[
    "planned", "authorized", "blocked", "dry_run", "running", "completed", "failed"
]
GateStatus = Literal["passed", "failed", "not_applicable"]
ProviderFailureType = Literal[
    "authentication_failure",
    "authorization_failure",
    "rate_limit",
    "timeout",
    "network_error",
    "provider_server_error",
    "invalid_request",
    "context_length_failure",
    "content_filter",
    "invalid_structured_output",
    "empty_output",
    "partial_output",
    "unknown_provider_error",
]


class PilotProviderConfig(StrictModel):
    provider_class: ProviderClass
    provider_name: str | None = Field(
        default=None, validation_alias=AliasChoices("provider_name", "provider")
    )
    model_identifier: str | None = Field(
        default=None, validation_alias=AliasChoices("model_identifier", "model")
    )
    enabled: bool = False
    credential_env_var: str | None = None
    endpoint: str | None = None
    local_runtime: str | None = None
    timeout_seconds: PositiveInt = 30
    max_retries: NonNegativeInt = 0
    backoff_initial_seconds: NonNegativeFloat = 0.25
    estimated_input_tokens_per_request: NonNegativeInt = 400
    estimated_output_tokens_per_request: NonNegativeInt = 200
    estimated_cost_per_1k_input_tokens: NonNegativeFloat = 0.0
    estimated_cost_per_1k_output_tokens: NonNegativeFloat = 0.0
    sampling_parameters: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    cache_enabled: bool = True
    resume_enabled: bool = True
    raw_response_preservation_enabled: bool = True
    secret_redaction_enabled: bool = True
    external_tools_enabled: bool = False
    fallback_model_identifier: str | None = None
    local_cost_assumption: str | None = None
    runtime_metadata: dict[str, str] = Field(default_factory=dict)
    hardware_metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_provider_contract(self) -> PilotProviderConfig:
        if self.provider_class != "mock":
            if not self.provider_name:
                raise ValueError("real provider configs must name provider_name explicitly")
            if not self.model_identifier:
                raise ValueError("real provider configs must name model_identifier explicitly")
        if self.provider_class == "remote_api" and not self.credential_env_var:
            raise ValueError("remote_api provider configs must name credential_env_var")
        if self.provider_class == "local" and not (self.endpoint or self.local_runtime):
            raise ValueError("local provider configs must name endpoint or local_runtime")
        if self.provider_class == "remote_api" and self.external_tools_enabled:
            raise ValueError("remote_api Stage A configs must not enable external tools")
        if self.provider_class == "remote_api" and self.fallback_model_identifier:
            raise ValueError("remote_api Stage A configs must not define fallback models")
        return self


class PilotExperimentConfig(StrictModel):
    pilot_id: str
    pilot_version: str = "phase7_pilot_v1"
    stage: PilotStage
    provider_config: Path
    output_root: Path = Path("results/tables/phase7")
    task_roots: list[Path] = Field(default_factory=lambda: [Path("scenarios")])
    domains: list[Domain] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    architectures: list[ArchitectureKind] = Field(default_factory=list)
    delegation_depths: list[int] = Field(default_factory=lambda: [1])
    branching_factors: list[int] = Field(default_factory=lambda: [1])
    behavior_conditions: list[str] = Field(default_factory=lambda: ["honest"])
    attacker_conditions: list[str] = Field(default_factory=lambda: ["none"])
    oversight_conditions: list[str] = Field(default_factory=lambda: ["none"])
    monitor_artifacts: list[Path] = Field(default_factory=list)
    calibration_artifacts: list[Path] = Field(default_factory=list)
    seeds: list[int] = Field(default_factory=lambda: [1])
    sampling_parameters: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    cost_ceiling: NonNegativeFloat | None = Field(
        default=None, validation_alias=AliasChoices("cost_ceiling", "max_cost_usd")
    )
    token_ceiling: NonNegativeInt | None = Field(
        default=None, validation_alias=AliasChoices("token_ceiling", "max_total_tokens")
    )
    request_ceiling: NonNegativeInt | None = Field(
        default=None, validation_alias=AliasChoices("request_ceiling", "max_requests")
    )
    trajectory_ceiling: NonNegativeInt | None = Field(
        default=None, validation_alias=AliasChoices("trajectory_ceiling", "max_trajectories")
    )
    provider_calls_enabled: bool = False
    cache_enabled: bool = True
    resume_enabled: bool = True
    external_tools_enabled: bool = False
    max_runs: NonNegativeInt | None = None
    large_run_threshold: NonNegativeInt = 100
    allow_large_run: bool = False
    human_review_sample_size: NonNegativeInt = 0
    human_review_sampling_plan: str = "stratified_small_pilot"
    prompt_renderer_version: str = PROMPT_RENDERER_VERSION
    base_branch: str = "main"
    base_commit: str = "f5c1962"
    phase7_branch: str = "codex/phase7-real-model-pilot"
    repository: str = "AnshDani2004/BayesAudit"
    benchmark_version: str = "phase7_pilot_subset_v1"
    notes: str = ""


class PilotPlan(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    artifact_version: str = PILOT_ARTIFACT_VERSION
    pilot_id: str
    stage: PilotStage
    provider: str | None
    model_identifier: str | None
    task_count: NonNegativeInt
    architecture_count: NonNegativeInt
    depth_count: NonNegativeInt
    behavior_count: NonNegativeInt
    attacker_count: NonNegativeInt
    policy_count: NonNegativeInt
    seed_count: NonNegativeInt
    planned_trajectories: NonNegativeInt
    planned_requests: NonNegativeInt
    estimated_input_tokens: NonNegativeInt
    estimated_output_tokens: NonNegativeInt
    estimated_total_tokens: NonNegativeInt
    estimated_cost: NonNegativeFloat
    maximum_possible_cost: NonNegativeFloat
    cache_hit_assumption: str
    retry_assumption: str
    storage_estimate_mb: NonNegativeFloat
    configuration_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class PermissionGateRecord(StrictModel):
    gate_name: str
    status: GateStatus
    reason: str


class ProviderPermissionRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    artifact_version: str = PILOT_ARTIFACT_VERSION
    permission_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    provider: str | None
    model_identifier: str | None
    credential_env_var: str | None = None
    credential_present: bool = False
    ci_environment: bool = False
    current_code_commit: str | None = None
    configuration_hash: str
    command_line_authorization: bool
    planned_requests: int = 0
    planned_trajectories: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_total_tokens: int = 0
    estimated_cost: float = 0.0
    max_cost: float | None = None
    max_tokens: int | None = None
    max_requests: int | None = None
    max_trajectories: int | None = None
    environment_classification: str
    gates: list[PermissionGateRecord]
    final_authorization_decision: Literal["allow", "block"] = "block"


class PilotManifest(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    artifact_version: str = PILOT_ARTIFACT_VERSION
    pilot_id: str
    pilot_version: str
    repository: str
    base_branch: str
    base_commit: str
    phase7_branch: str
    current_code_commit: str
    working_tree_status: str
    experiment_configuration_hash: str
    benchmark_version: str
    scenario_hashes: dict[str, str]
    prompt_renderer_version: str
    provider_configuration_hash: str
    provider: str | None
    exact_model_identifier: str | None
    architecture_conditions: list[str]
    domains: list[str]
    tasks: list[str]
    delegation_depths: list[int]
    branching_factors: list[int]
    behavior_conditions: list[str]
    attacker_conditions: list[str]
    oversight_conditions: list[str]
    monitor_artifacts: list[str]
    calibration_artifacts: list[str]
    seeds: list[int]
    sampling_parameters: dict[str, Any]
    cost_ceiling: float | None
    token_ceiling: int | None
    request_ceiling: int | None
    trajectory_ceiling: int | None
    estimated_cost: float
    actual_cost: float = 0.0
    estimated_tokens: int
    actual_tokens: int = 0
    planned_requests: int
    completed_requests: int = 0
    cached_requests: int = 0
    failed_requests: int = 0
    human_review_sampling_plan: str
    start_timestamp: datetime = Field(default_factory=utc_now)
    end_timestamp: datetime | None = None
    status: PilotStatus = "planned"
    deviations: list[str] = Field(default_factory=list)
    notes: str = ""


class PromptRenderRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    template_name: str
    template_version: str
    task_id: str
    constraint_envelope_version: str
    architecture: str
    agent_role: str
    delegation_depth: int
    branch: str | None = None
    available_tools: list[str] = Field(default_factory=list)
    oversight_context: dict[str, Any] = Field(default_factory=dict)
    attack_context: dict[str, Any] = Field(default_factory=dict)
    rendered_prompt: str
    prompt_hash: str


class ProviderRequestRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    request_id: str
    request_hash: str
    prompt_hash: str
    provider: str
    model_identifier: str
    sampling_parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int
    attempt_count: int = 0
    status: Literal["planned", "cached", "completed", "failed"] = "planned"
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost: float = 0.0
    timestamp: datetime = Field(default_factory=utc_now)


class ProviderResponseRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    response_id: str
    request_hash: str
    response_hash: str
    provider_request_id: str | None = None
    finish_reason: str | None = None
    raw_output: str
    raw_provider_response: dict[str, Any] = Field(default_factory=dict)
    parsed_output: dict[str, Any] = Field(default_factory=dict)
    provider_reported_usage: dict[str, Any] = Field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    provider_reported_cost: float | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class ProviderFailureRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    failure_id: str
    failure_type: ProviderFailureType
    provider: str | None
    model_identifier: str | None
    request_hash: str
    attempt_count: int
    retry_decision: str
    final_status: str
    cost: float = 0.0
    usage: dict[str, Any] = Field(default_factory=dict)
    message: str = ""
    timestamp: datetime = Field(default_factory=utc_now)


class StructuredOutputRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    output_id: str
    raw_output: str
    parsed_output: dict[str, Any] = Field(default_factory=dict)
    parse_errors: list[str] = Field(default_factory=list)
    repair_attempts: int = 0
    repair_prompt_hashes: list[str] = Field(default_factory=list)
    repair_cost: float = 0.0
    valid: bool


class WorkflowQualityRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    trajectory_id: str
    flags: list[str]
    metrics: dict[str, float]
    definitive_human_judgment: bool = False


class ScorerHumanComparisonRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    comparison_id: str
    trajectory_id: str
    domain: str
    automated_scorer_result: str
    human_label: str
    agreement: bool
    disagreement_type: str | None = None
    scorer_error_category: str | None = None
    recommended_correction: str | None = None
    correction_changes_historical_output: bool = False
    responsible_component: Literal["task", "scorer", "annotation", "unknown"] = "unknown"


class AnnotationSampleItem(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    annotation_id: str
    trajectory_id: str
    sampling_stratum: str
    sampling_probability: float = Field(ge=0.0, le=1.0)
    blind_payload: dict[str, Any]
    adjudication_payload: dict[str, Any]
    error_analysis_payload: dict[str, Any]


class AnnotationAgreementRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    label_name: str
    item_count: int
    percent_agreement: float
    cohens_kappa: float
    krippendorff_alpha: float | None = None


class TransferMetricRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    metric_family: Literal["monitor_transfer", "calibration_transfer", "ood"]
    metric_name: str
    value: float
    group: str = "overall"
    confidence_interval: tuple[float, float] | None = None
    small_sample_warning: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class OversightFeasibilityRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    scenario: str
    supported: bool
    inert_or_sandboxed: bool = True
    outcome: str


class ReadinessRecord(StrictModel):
    schema_version: str = PILOT_SCHEMA_VERSION
    item_id: str
    item_type: Literal["task", "scorer"]
    category: str
    rationale: str
