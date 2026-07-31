"""Phase 4 oversight artifact schemas.

These records extend, but do not replace, core schema version `bayesaudit.v2`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, NonNegativeFloat, NonNegativeInt

from bayesaudit.schemas import (
    ArchitectureKind,
    BudgetUnit,
    MessageRecord,
    OversightAction,
    Severity,
    StrictModel,
    ToolCallRecord,
    utc_now,
)

OVERSIGHT_SCHEMA_VERSION = "bayesaudit.oversight.v1"


class WorkflowMode(str):
    SHADOW = "shadow"
    INTERVENTION = "intervention"


class CheckpointType(str):
    BEFORE_PLANNING = "before_planning"
    AFTER_PLANNING = "after_planning"
    BEFORE_DELEGATION = "before_delegation"
    AFTER_DELEGATION = "after_delegation"
    ON_CHILD_RESULT = "on_receiving_child_result"
    BEFORE_TOOL_REQUEST = "before_tool_request"
    AFTER_TOOL_RESULT = "after_tool_result"
    BEFORE_AGGREGATION = "before_aggregation"
    BEFORE_FINAL_OUTPUT = "before_final_output"
    ON_VERIFICATION_FAILURE = "on_verification_failure"
    ON_REPAIR_FAILURE = "on_repair_failure"
    ON_BRANCH_REFUSAL = "on_branch_refusal"


class AuditStatus(str):
    NOT_REQUESTED = "not_requested"
    COMPLETED = "completed"
    SKIPPED_INSUFFICIENT_BUDGET = "skipped_insufficient_budget"
    ERROR = "error"


class InterventionStatus(str):
    NOT_APPLICABLE = "not_applicable"
    EXECUTED = "executed"
    FAILED = "failed"
    TOO_LATE = "too_late"
    INSUFFICIENT_BUDGET = "insufficient_budget"


class DetectionMatchStatus(str):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
    DUPLICATE_DETECTION = "duplicate_detection"
    LATE_DETECTION = "late_detection"
    CATEGORY_ONLY = "correct_category_wrong_instance"
    SEVERITY_OVERESTIMATE = "severity_overestimate"
    SEVERITY_UNDERESTIMATE = "severity_underestimate"


class OversightCheckpoint(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    checkpoint_id: str
    checkpoint_type: str
    step_id: str
    sequence_index: NonNegativeInt
    audit_eligible: bool = True
    intervention_still_possible: bool = True
    available_actions: list[str] = Field(default_factory=lambda: [OversightAction.CONTINUE.value])
    default_action_if_budget_exhausted: str = OversightAction.CONTINUE.value
    audit_cost: NonNegativeFloat = 1.0
    intervention_cost: NonNegativeFloat = 1.0
    mandatory: bool = False


class RedactedToolCall(StrictModel):
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    requested_by_agent: str
    approval_required: bool = False
    approval_reference: str | None = None
    environment_authorized: bool
    execution_status: str

    @classmethod
    def from_tool_call(cls, call: ToolCallRecord) -> RedactedToolCall:
        return cls(
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            arguments=call.arguments,
            requested_by_agent=call.requested_by_agent,
            approval_required=call.approval_required,
            approval_reference=call.approval_reference,
            environment_authorized=call.environment_authorized,
            execution_status=str(call.execution_status),
        )


class OversightObservation(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    observation_id: str
    trajectory_id: str
    task_id: str
    current_step_id: str
    sequence_index: NonNegativeInt
    architecture: ArchitectureKind
    workflow_mode: str
    agent_id: str
    agent_role: str
    depth: NonNegativeInt
    branch_id: str | None = None
    delegation_id: str | None = None
    current_step_kind: str
    checkpoint: OversightCheckpoint
    current_messages: list[MessageRecord] = Field(default_factory=list)
    proposed_model_response: MessageRecord | None = None
    proposed_tool_calls: list[RedactedToolCall] = Field(default_factory=list)
    current_constraint_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    current_constraint_envelope_verification_status: str | None = None
    prior_architecture_events: list[dict[str, Any]] = Field(default_factory=list)
    prior_public_audit_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    prior_policy_actions: list[dict[str, Any]] = Field(default_factory=list)
    current_budget_state: dict[str, Any]
    task_metadata_observable: dict[str, Any] = Field(default_factory=dict)
    observable_risk_features: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class OversightBudgetState(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    initial_budget: NonNegativeFloat
    remaining_budget: NonNegativeFloat
    reserved_budget: NonNegativeFloat = 0.0
    consumed_audit_cost: NonNegativeFloat = 0.0
    consumed_intervention_cost: NonNegativeFloat = 0.0
    consumed_escalation_cost: NonNegativeFloat = 0.0
    budget_unit: BudgetUnit = BudgetUnit.AUDIT_COUNT
    audit_count: NonNegativeInt = 0
    intervention_count: NonNegativeInt = 0
    escalation_count: NonNegativeInt = 0
    rejected_actions_due_to_insufficient_budget: NonNegativeInt = 0
    budget_violations: NonNegativeInt = 0
    final_reconciled: bool = False


class BudgetTransaction(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    transaction_id: str
    policy_run_id: str
    observation_id: str | None = None
    action: str
    amount: NonNegativeFloat
    budget_before: NonNegativeFloat
    budget_after: NonNegativeFloat
    reserved_after: NonNegativeFloat
    success: bool
    reason: str


class PolicyStateRecord(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    policy_name: str
    policy_version: str
    seed: int
    budget: OversightBudgetState
    prior_audit_decisions: list[dict[str, Any]] = Field(default_factory=list)
    prior_feedback: list[dict[str, Any]] = Field(default_factory=list)
    prior_interventions: list[dict[str, Any]] = Field(default_factory=list)
    policy_specific_state: dict[str, Any] = Field(default_factory=dict)
    finalized: bool = False
    finalization_metadata: dict[str, Any] = Field(default_factory=dict)


class AuditDecisionRecord(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    decision_id: str
    policy_run_id: str
    policy_name: str
    policy_version: str
    observation_id: str
    checkpoint_type: str
    audit_requested: bool
    audit_probability: float = Field(ge=0.0, le=1.0)
    sampling_method: str | None = None
    reason: str
    budget_available: bool
    audit_cost: NonNegativeFloat = 0.0
    risk_score: float = Field(default=0.0, ge=0.0)
    recommended_action: str = OversightAction.CONTINUE.value
    mode: str = WorkflowMode.SHADOW


class AuditFinding(StrictModel):
    rule_id: str
    description: str
    severity: Severity
    risk_score: float = Field(ge=0.0)
    suspected_violation_category: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommended_intervention: str = OversightAction.CONTINUE.value


class AuditFeedbackRecord(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    audit_id: str
    policy_run_id: str
    observation_id: str
    auditor_name: str
    findings: list[AuditFinding] = Field(default_factory=list)
    estimated_violation_probability: float = Field(ge=0.0, le=1.0)
    estimated_severity: Severity
    suspected_violation_categories: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    audit_cost: NonNegativeFloat = 0.0
    audit_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    intervention_still_useful: bool = True
    audit_status: str = AuditStatus.COMPLETED
    error: str | None = None


class InterventionDecisionRecord(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    intervention_decision_id: str
    policy_run_id: str
    observation_id: str
    audit_id: str | None = None
    action: OversightAction
    target: str
    reason: str
    cost: NonNegativeFloat = 0.0
    still_preventable: bool = True
    mode: str = WorkflowMode.SHADOW


class InterventionOutcomeRecord(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    outcome_id: str
    intervention_decision_id: str
    policy_run_id: str
    observation_id: str
    action: OversightAction
    status: str
    blocked_action: bool = False
    requested_clarification: bool = False
    escalated: bool = False
    terminated_branch: bool = False
    terminated_workflow: bool = False
    changed_task_output: bool = False
    utility_consequence: float = 0.0
    cost: NonNegativeFloat = 0.0
    synthetic_resolver_output: str | None = None


class EscalationEvent(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    escalation_id: str
    policy_run_id: str
    observation_id: str
    resolver_outcome: Literal["approve", "deny", "modify", "request_more_info", "timeout"]
    synthetic: bool = True


class DetectionMatchRecord(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    match_id: str
    policy_run_id: str
    detection_audit_id: str | None
    violation_id: str | None
    observation_id: str | None
    status: str
    matched_constraint_id: str | None = None
    matched_violation_type: str | None = None
    severity_relation: str | None = None


class CounterfactualOutcome(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    pair_id: str
    baseline_run_id: str
    intervention_run_id: str
    shared_experimental_key: str
    target_violation_id: str | None
    violation_occurred_in_baseline: bool
    violation_occurred_under_intervention: bool
    prevented: bool | None
    displaced_to_another_step: bool = False
    changed_violation_type: bool = False
    changed_severity: bool = False
    utility_difference: float = 0.0
    additional_cost: float = 0.0
    counterfactual_validity_status: str = "valid"


class PolicyMetricRecord(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    policy_run_id: str
    policy_name: str
    metric_name: str
    value: float
    level: str = "policy_run"
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrontierPoint(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    experiment_id: str
    policy_name: str
    budget: float
    severity_weighted_undetected_harm: float
    task_utility: float
    oversight_cost: float
    synthetic: bool = True


class OversightRunResult(StrictModel):
    schema_version: str = OVERSIGHT_SCHEMA_VERSION
    policy_run_id: str
    trajectory_id: str
    run_id: str
    experiment_id: str
    policy_name: str
    policy_version: str
    mode: str
    synthetic: bool = True
    decisions: list[AuditDecisionRecord] = Field(default_factory=list)
    feedback: list[AuditFeedbackRecord] = Field(default_factory=list)
    intervention_decisions: list[InterventionDecisionRecord] = Field(default_factory=list)
    intervention_outcomes: list[InterventionOutcomeRecord] = Field(default_factory=list)
    budget_transactions: list[BudgetTransaction] = Field(default_factory=list)
    detection_matches: list[DetectionMatchRecord] = Field(default_factory=list)
    counterfactuals: list[CounterfactualOutcome] = Field(default_factory=list)
    metrics: list[PolicyMetricRecord] = Field(default_factory=list)
    final_policy_state: PolicyStateRecord | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

