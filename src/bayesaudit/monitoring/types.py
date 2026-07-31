"""Versioned Phase 5 monitoring artifact schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, NonNegativeFloat, NonNegativeInt

from bayesaudit.schemas import ArchitectureKind, Domain, StrictModel, utc_now

MONITORING_SCHEMA_VERSION = "bayesaudit.monitoring.v1"
FEATURE_SCHEMA_VERSION = "bayesaudit.features.interpretable.v1"


class SplitName(str):
    TRAIN = "train"
    DEVELOPMENT = "development"
    CALIBRATION = "calibration"
    CONFIRMATORY_TEST = "confirmatory_test"
    EXPLORATORY_TEST = "exploratory_test"


class LabelValue(str):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class MonitorExample(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    example_id: str
    observation_id: str
    trajectory_id: str
    run_id: str
    experiment_id: str
    task_id: str
    task_version: str
    template_family: str
    domain: Domain
    architecture: ArchitectureKind
    model_family: str
    checkpoint_type: str
    sequence_index: NonNegativeInt
    depth: NonNegativeInt
    branch_id: str | None = None
    observable_feature_payload: dict[str, float | int | str | bool | None]
    observable_text_payload: str
    current_violation_label: str
    imminent_violation_label: str
    preventable_imminent_violation_label: str
    severity_target: NonNegativeFloat | None = None
    intervention_usefulness_label: str
    final_output_violation_label: str
    internal_only_violation_label: str
    label_horizon: NonNegativeInt
    label_source: str
    label_confidence: float = Field(ge=0.0, le=1.0)
    unknown_label_reasons: list[str] = Field(default_factory=list)
    split_group_ids: dict[str, str] = Field(default_factory=dict)
    source_artifact_hashes: dict[str, str] = Field(default_factory=dict)
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    synthetic: bool = True


class MonitorPrediction(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    prediction_id: str
    monitor_name: str
    monitor_version: str
    model_artifact_hash: str
    prompt_version: str | None = None
    example_id: str
    current_violation_probability: float = Field(ge=0.0, le=1.0)
    imminent_violation_probability: float = Field(ge=0.0, le=1.0)
    preventable_violation_probability: float = Field(ge=0.0, le=1.0)
    expected_severity: NonNegativeFloat
    intervention_usefulness_probability: float = Field(ge=0.0, le=1.0)
    predicted_violation_categories: list[str] = Field(default_factory=list)
    abstained: bool = False
    abstention_reason: str | None = None
    explanation: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    latency_ms: NonNegativeFloat = 0.0
    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    estimated_cost: NonNegativeFloat = 0.0
    ood_score: NonNegativeFloat | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class MonitorDatasetManifest(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    dataset_id: str
    dataset_version: str
    source_experiments: list[str]
    source_schema_versions: list[str]
    observation_count: NonNegativeInt
    trajectory_count: NonNegativeInt
    task_count: NonNegativeInt
    group_counts: dict[str, int]
    label_prevalence: dict[str, float]
    unknown_label_counts: dict[str, int]
    feature_schema: dict[str, str]
    text_rendering_version: str
    split_strategy: str | None = None
    split_manifest_hash: str | None = None
    build_commit: str | None = None
    build_configuration: dict[str, Any] = Field(default_factory=dict)
    configuration_hash: str
    data_hash: str
    artifact_version: str = "phase5_v1"
    created_at: datetime = Field(default_factory=utc_now)


class SplitAssignment(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    example_id: str
    split: str
    group_key: str
    group_value: str
    strategy: str


class SplitManifest(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    split_manifest_id: str
    dataset_id: str
    strategy: str
    immutable: bool = True
    assignments: list[SplitAssignment]
    group_counts: dict[str, dict[str, int]]
    manifest_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class MonitorArtifact(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    monitor_name: str
    monitor_version: str
    monitor_type: str
    target: str
    feature_names: list[str]
    artifact_hash: str
    artifact_path: str | None = None
    training_dataset_hash: str
    split_manifest_hash: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    calibration: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class CalibrationArtifact(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    calibration_id: str
    base_monitor: str
    base_artifact_hash: str
    calibration_method: str
    calibration_dataset_hash: str
    fitting_configuration: dict[str, Any] = Field(default_factory=dict)
    artifact_version: str = "phase5_calibration_v1"
    artifact_hash: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class MonitorMetricRecord(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    monitor_name: str
    dataset_id: str
    split: str
    target: str
    metric_name: str
    value: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class OODScoreRecord(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    example_id: str
    detector_name: str
    ood_score: NonNegativeFloat
    flags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AbstentionRecord(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    prediction_id: str
    mechanism: str
    abstained: bool
    reason: str | None = None
    coverage_after_abstention: float = Field(ge=0.0, le=1.0)


class JudgeResponse(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    current_violation_probability: float = Field(ge=0.0, le=1.0)
    imminent_violation_probability: float = Field(ge=0.0, le=1.0)
    preventable_violation_probability: float = Field(ge=0.0, le=1.0)
    expected_severity: NonNegativeFloat
    intervention_usefulness_probability: float = Field(ge=0.0, le=1.0)
    suspected_violation_categories: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool = False
    abstention_reason: str | None = None
    rationale: str = ""


class ProviderCallManifest(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    provider_manifest_id: str
    provider_name: str
    model_identifier: str | None
    allow_provider_calls: bool = False
    dry_run: bool = True
    estimated_cost: NonNegativeFloat
    max_cost: NonNegativeFloat
    estimated_tokens: NonNegativeInt
    max_tokens: NonNegativeInt
    trajectory_ceiling: NonNegativeInt
    request_count: NonNegativeInt
    status: Literal["blocked", "dry_run", "ready", "completed"] = "dry_run"
    created_at: datetime = Field(default_factory=utc_now)
