"""Adaptive oversight schemas for Phase 5."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, NonNegativeFloat, NonNegativeInt

from bayesaudit.monitoring.types import MONITORING_SCHEMA_VERSION
from bayesaudit.schemas import OversightAction, StrictModel, utc_now


class PosteriorSnapshot(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    snapshot_id: str
    model_name: str
    prior: dict[str, Any]
    posterior_parameters: dict[str, Any]
    audit_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    feature_version: str
    random_state: int
    effective_sample_size: NonNegativeFloat = 0.0
    uncertainty: NonNegativeFloat = 0.0
    timestamp: datetime = Field(default_factory=utc_now)


class BayesianUpdateRecord(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    update_id: str
    observation_id: str
    audited: bool
    feedback_available: bool
    posterior_updated: bool
    feedback_delay_steps: NonNegativeInt = 0
    feedback_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    label_corrected_later: bool = False
    reason: str


class AdaptivePolicyDecision(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    adaptive_decision_id: str
    policy_name: str
    observation_id: str
    risk_estimate: float = Field(ge=0.0, le=1.0)
    expected_severity: NonNegativeFloat = 0.0
    intervention_effectiveness: float = Field(default=0.0, ge=0.0, le=1.0)
    expected_net_value: float = 0.0
    action: OversightAction
    reason: str
    budget_remaining: NonNegativeFloat
    online: bool = True


class AdaptivePolicyResult(StrictModel):
    schema_version: str = MONITORING_SCHEMA_VERSION
    policy_name: str
    decisions: list[AdaptivePolicyDecision] = Field(default_factory=list)
    posterior_snapshots: list[PosteriorSnapshot] = Field(default_factory=list)
    updates: list[BayesianUpdateRecord] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
