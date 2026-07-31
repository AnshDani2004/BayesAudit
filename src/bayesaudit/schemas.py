"""Core data models for BayesAudit benchmark tasks, execution, and scoring."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    computed_field,
    model_validator,
)


class StrEnum(str, Enum):
    """Compatibility shim matching the behavior needed by these schemas."""


SCHEMA_VERSION = "bayesaudit.v2"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    """Base schema that rejects misspelled or undeclared fields."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class Domain(StrEnum):
    EVIDENCE = "evidence"
    PRIVACY = "privacy"
    BUDGETING = "budgeting"
    AUTHORIZATION = "authorization"
    PROTECTED_ATTRIBUTES = "protected_attributes"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_WEIGHTS: dict[str, float] = {
    Severity.LOW.value: 1.0,
    Severity.MEDIUM.value: 2.0,
    Severity.HIGH.value: 5.0,
    Severity.CRITICAL.value: 10.0,
}


class ConstraintCategory(StrEnum):
    EVIDENCE = "evidence"
    PRIVACY = "privacy"
    BUDGET = "budget"
    AUTHORIZATION = "authorization"
    FAIRNESS = "fairness"


class ConstraintScope(StrEnum):
    MESSAGES = "messages"
    TOOLS = "tools"
    FINAL_OUTPUT = "final_output"


class ArchitectureKind(StrEnum):
    SINGLE_AGENT = "single_agent"
    UNSTRUCTURED_DELEGATION = "unstructured_delegation"
    STRUCTURED_INHERITANCE = "structured_inheritance"
    VERIFIED_INHERITANCE = "verified_inheritance"


class BehaviorCondition(StrEnum):
    HONEST = "honest"
    OPPORTUNISTIC = "opportunistic"
    STRATEGIC = "strategic"


class OversightAction(StrEnum):
    CONTINUE = "continue"
    AUDIT = "audit_current_step"
    REQUEST_CLARIFICATION = "request_clarification"
    BLOCK = "block_proposed_action"
    ESCALATE = "escalate_to_human"
    TERMINATE = "terminate_workflow"


class WorkflowStepKind(StrEnum):
    PLANNING = "planning"
    DELEGATION = "delegation"
    REASONING = "reasoning"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    REVIEW = "review"
    FINAL_OUTPUT = "final_output"


class RetentionStatus(StrEnum):
    PRESERVED = "preserved"
    PARAPHRASED_EQUIVALENT = "paraphrased_equivalent"
    WEAKENED = "weakened"
    STRENGTHENED = "strengthened"
    DROPPED = "dropped"
    CONTRADICTED = "contradicted"
    ADDED = "added"


class MutationType(StrEnum):
    NONE = "none"
    OMITTED = "omitted"
    PARAPHRASED = "paraphrased"
    WEAKENED_SCOPE = "weakened_scope"
    STRENGTHENED_SCOPE = "strengthened_scope"
    CONTRADICTION = "contradiction"
    NEW_CONSTRAINT = "new_constraint"


class VerificationStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    ACKNOWLEDGED = "acknowledged"
    UNACKNOWLEDGED = "unacknowledged"
    FAILED = "failed"


class ToolExecutionStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    BLOCKED = "blocked"
    EXECUTED = "executed"
    FAILED = "failed"


class TrajectoryStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    EXCLUDED = "excluded"


class BudgetUnit(StrEnum):
    AUDIT_COUNT = "audit_count"
    MONETARY_COST = "monetary_cost"
    HUMAN_MINUTES = "human_minutes"
    ABSTRACT_COST = "abstract_cost"


class ScoringStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    ERROR = "error"


class Constraint(StrictModel):
    id: str = Field(min_length=1)
    rule: str = Field(min_length=1)
    category: ConstraintCategory
    severity: Severity
    scope: list[ConstraintScope] = Field(min_length=1)
    requires_escalation: bool = False


class DelegationConfig(StrictModel):
    architecture: ArchitectureKind
    max_depth: NonNegativeInt = 0
    planned_branching_factor: PositiveInt = 1
    constraint_inheritance_required: bool = False
    verification_required: bool = False


class GroundTruth(StrictModel):
    kind: str = Field(min_length=1)
    value: dict[str, Any] = Field(default_factory=dict)


class ScoringSpec(StrictModel):
    kind: str = Field(min_length=1)
    scorer_name: str = Field(min_length=1)
    scorer_version: str = Field(min_length=1)
    deterministic: bool = True
    criteria: dict[str, Any] = Field(default_factory=dict)


class BenchmarkTask(StrictModel):
    schema_version: str = SCHEMA_VERSION
    task_id: str = Field(pattern=r"^task_[a-z0-9_]+$")
    task_version: str = Field(min_length=1)
    template_family: str = Field(min_length=1)
    domain: Domain
    difficulty: Difficulty
    description: str = Field(min_length=1)
    source_materials: list[dict[str, Any]] = Field(default_factory=list)
    ground_truth: GroundTruth
    scoring: ScoringSpec
    constraints: list[Constraint] = Field(min_length=1)
    authorized_tools: list[str] = Field(default_factory=list)
    prohibited_tools: list[str] = Field(default_factory=list)
    delegation: DelegationConfig
    expected_escalation_points: list[str] = Field(default_factory=list)
    detectable_violation_types: list[str] = Field(min_length=1)
    seed: int
    scenario_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_task_contract(self) -> BenchmarkTask:
        ids = [constraint.id for constraint in self.constraints]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate constraint IDs in {self.task_id}")
        overlap = set(self.authorized_tools).intersection(self.prohibited_tools)
        if overlap:
            raise ValueError(f"authorized and prohibited tools overlap: {sorted(overlap)}")
        return self


class MessageRecord(StrictModel):
    role: str = Field(min_length=1)
    content: str
    agent_id: str | None = None


class ModelResponse(StrictModel):
    message: MessageRecord
    provider: str
    model_id: str
    model_version: str | None = None
    finish_reason: str
    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    total_tokens: NonNegativeInt = 0
    latency_ms: NonNegativeFloat = 0.0
    estimated_cost: NonNegativeFloat = 0.0
    request_id: str
    seed: int | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class ConstraintSnapshot(StrictModel):
    constraint_id: str
    canonical_rule: str
    visible_rule: str
    category: ConstraintCategory
    severity: Severity
    original_source_level: NonNegativeInt = 0
    current_source_level: NonNegativeInt = 0
    inherited_from_step_id: str | None = None
    canonical_hash: str
    visible_hash: str
    retention_status: RetentionStatus = RetentionStatus.PRESERVED
    mutation_type: MutationType = MutationType.NONE
    acknowledged_by_agent: bool = False
    verification_status: VerificationStatus = VerificationStatus.NOT_REQUIRED


class ToolCallRecord(StrictModel):
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    requested_by_agent: str
    approval_required: bool = False
    approval_reference: str | None = None
    authorization_basis: str
    environment_authorized: bool
    execution_status: ToolExecutionStatus
    result_summary: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ViolationEvent(StrictModel):
    violation_id: str
    violation_type: str
    constraint_id: str
    severity: Severity
    first_step_id: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    internal_only: bool = False
    objectively_determinable: bool = True
    scorer_name: str
    scorer_version: str


class DetectionEvent(StrictModel):
    detection_id: str
    target_step_id: str
    detector_name: str
    estimated_probability: float = Field(ge=0.0, le=1.0)
    estimated_severity: Severity
    predicted_violation_type: str
    rationale: str
    audit_cost: NonNegativeFloat = 0.0
    true_positive: bool | None = None
    matched_violation_id: str | None = None


class InterventionEvent(StrictModel):
    intervention_id: str
    target_step_id: str
    action: OversightAction
    actor: str
    reason: str
    cost: NonNegativeFloat = 0.0
    blocked_execution: bool = False
    escalation_requested: bool = False
    escalation_completed: bool = False
    outcome: str | None = None
    prevented_violation_ids: list[str] = Field(default_factory=list)


class AuditDecision(StrictModel):
    action: OversightAction
    reason: str
    policy_name: str
    estimated_violation_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    estimated_severity: Severity | None = None
    expected_cost: NonNegativeFloat = 0.0
    detections: list[DetectionEvent] = Field(default_factory=list)
    interventions: list[InterventionEvent] = Field(default_factory=list)


class TrajectoryStep(StrictModel):
    step_id: str
    sequence_index: NonNegativeInt
    parent_step_id: str | None = None
    delegation_id: str | None = None
    branch_id: str | None = None
    agent_id: str
    parent_agent_id: str | None = None
    role: str
    depth: NonNegativeInt
    kind: WorkflowStepKind
    input_messages: list[MessageRecord] = Field(default_factory=list)
    model_response: ModelResponse | None = None
    constraint_snapshots: list[ConstraintSnapshot] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    detections: list[DetectionEvent] = Field(default_factory=list)
    interventions: list[InterventionEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelConfigRecord(StrictModel):
    provider: str
    model_id: str
    model_version: str | None = None
    behavior_profile: str = "compliant"
    raw_config: dict[str, Any] = Field(default_factory=dict)


class UsageTotals(StrictModel):
    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    total_tokens: NonNegativeInt = 0
    estimated_cost: NonNegativeFloat = 0.0
    latency_ms: NonNegativeFloat = 0.0


class ErrorRecord(StrictModel):
    error_type: str
    message: str
    step_id: str | None = None
    recoverable: bool = True
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class BudgetState(StrictModel):
    initial_budget: NonNegativeFloat
    remaining_budget: NonNegativeFloat
    consumed_budget: NonNegativeFloat
    budget_unit: BudgetUnit = BudgetUnit.AUDIT_COUNT
    per_action_costs: dict[str, NonNegativeFloat] = Field(default_factory=dict)
    audit_count: NonNegativeInt = 0
    escalation_count: NonNegativeInt = 0

    @model_validator(mode="after")
    def validate_budget(self) -> BudgetState:
        expected = round(float(self.initial_budget - self.consumed_budget), 10)
        if abs(float(self.remaining_budget) - expected) > 1e-9:
            raise ValueError("remaining_budget must equal initial_budget minus consumed_budget")
        return self


class PolicyState(StrictModel):
    policy_name: str
    budget: BudgetState
    seed: int
    state: dict[str, Any] = Field(default_factory=dict)


class OversightObservation(StrictModel):
    task_id: str
    trajectory_id: str
    current_step: TrajectoryStep
    prior_steps: list[TrajectoryStep] = Field(default_factory=list)
    budget: BudgetState
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditFeedback(StrictModel):
    task_id: str
    trajectory_id: str
    step_id: str
    detections: list[DetectionEvent] = Field(default_factory=list)
    interventions: list[InterventionEvent] = Field(default_factory=list)
    violations: list[ViolationEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Trajectory(StrictModel):
    schema_version: str = SCHEMA_VERSION
    trajectory_id: str
    task_id: str
    task_version: str
    scenario_hash: str
    experiment_id: str
    run_id: str
    architecture: ArchitectureKind
    behavior_condition: BehaviorCondition
    model_configuration: ModelConfigRecord
    oversight_policy: str
    oversight_budget: BudgetState
    seed: int
    status: TrajectoryStatus = TrajectoryStatus.PENDING
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    git_commit: str | None = None
    configuration_hash: str
    prompt_version: str = "phase2_mock_v1"
    steps: list[TrajectoryStep] = Field(default_factory=list)
    usage_totals: UsageTotals = Field(default_factory=UsageTotals)
    error: ErrorRecord | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_hierarchy(self) -> Trajectory:
        seen: dict[str, TrajectoryStep] = {}
        previous_index = -1
        for step in self.steps:
            if step.sequence_index <= previous_index:
                raise ValueError("trajectory steps must be strictly ordered by sequence_index")
            previous_index = step.sequence_index
            if step.step_id in seen:
                raise ValueError(f"duplicate step_id: {step.step_id}")
            if step.parent_step_id is not None:
                parent = seen.get(step.parent_step_id)
                if parent is None:
                    raise ValueError(f"parent step does not precede child: {step.parent_step_id}")
                if step.depth != parent.depth + 1 and step.kind == WorkflowStepKind.DELEGATION:
                    raise ValueError("delegation child depth must equal parent depth plus one")
                if step.depth < parent.depth:
                    raise ValueError("child depth cannot be less than parent depth")
            elif step.depth != 0:
                raise ValueError("root steps must have depth zero")
            seen[step.step_id] = step
        return self


class ScoreResult(StrictModel):
    schema_version: str = SCHEMA_VERSION
    task_id: str
    trajectory_id: str
    scorer_name: str
    scorer_version: str
    task_success: bool
    task_correctness_score: float = Field(ge=0.0, le=1.0)
    utility_score: float
    trajectory_violation_count: NonNegativeInt
    final_output_violation_count: NonNegativeInt
    internal_only_violation_count: NonNegativeInt
    severity_weighted_harm: NonNegativeFloat
    violations: list[ViolationEvent] = Field(default_factory=list)
    component_scores: dict[str, float] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    scoring_status: ScoringStatus = ScoringStatus.PASSED

    @computed_field  # type: ignore[prop-decorator]
    @property
    def correct(self) -> bool:
        return self.task_success and self.task_correctness_score >= 1.0


class MonitorEstimate(StrictModel):
    violation_probability: float = Field(ge=0.0, le=1.0)
    future_violation_probability: float = Field(ge=0.0, le=1.0)
    severity: Severity
    intervention_still_useful: bool
    rationale: str
    output_format: Literal["bayesaudit_monitor_v1"] = "bayesaudit_monitor_v1"
