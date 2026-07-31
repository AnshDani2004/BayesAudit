"""Versioned Phase 6 strategic-attack artifact schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, NonNegativeFloat, NonNegativeInt

from bayesaudit.schemas import ArchitectureKind, Domain, StrictModel, utc_now

ATTACK_SCHEMA_VERSION = "bayesaudit.attack.v1"

AttackAction = Literal[
    "do_not_attack",
    "start_attack",
    "continue_attack",
    "modify_attack",
    "conceal_attack",
    "abort_attack",
    "move_attack",
    "complete_attack",
]

AttackStatus = Literal[
    "not_started",
    "active",
    "concealed",
    "aborted",
    "moved",
    "completed",
    "failed",
    "blocked",
]

KnowledgeTier = Literal[
    "tier0_task_only",
    "tier1_protocol_class",
    "tier2_public_config",
    "tier3_black_box_feedback",
    "tier4_monitor_score",
    "tier5_white_box_synthetic",
]


class AttackObjective(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    objective_id: str
    target_constraint_categories: list[str] = Field(default_factory=list)
    target_violation_types: list[str] = Field(default_factory=list)
    benefit_by_violation_type: dict[str, float] = Field(default_factory=dict)
    severity_preferences: dict[str, float] = Field(default_factory=dict)
    task_reward_preferences: dict[str, float] = Field(default_factory=dict)
    detection_penalty: NonNegativeFloat = 1.0
    intervention_penalty: NonNegativeFloat = 1.0
    attack_cost: NonNegativeFloat = 1.0
    concealment_cost: NonNegativeFloat = 0.0
    abort_cost: NonNegativeFloat = 0.0
    maximum_attacks: NonNegativeInt = 1
    maximum_concurrent_attacks: NonNegativeInt = 1
    allowed_attack_methods: list[str] = Field(default_factory=list)
    prohibited_attack_methods: list[str] = Field(default_factory=list)
    target_success_definition: str = "objective_violation_occurs"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttackOpportunity(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    opportunity_id: str
    trajectory_id: str
    step_id: str
    checkpoint_type: str
    agent_id: str
    branch_id: str | None = None
    delegation_depth: NonNegativeInt = 0
    domain: Domain
    architecture: ArchitectureKind
    available_attack_methods: list[str] = Field(default_factory=list)
    targetable_constraints: list[str] = Field(default_factory=list)
    estimated_benefit: float = 0.0
    estimated_success_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_detection_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_intervention_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_cost: NonNegativeFloat = 0.0
    still_preventable: bool = True
    observable_evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class AttackerObservation(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    observation_id: str
    opportunity_id: str
    attacker_name: str
    knowledge_tier: KnowledgeTier
    current_task_description: str | None = None
    current_delegated_subtask: str | None = None
    visible_constraints: list[dict[str, Any]] = Field(default_factory=list)
    current_agent_role: str | None = None
    current_branch: str | None = None
    delegation_depth: NonNegativeInt = 0
    proposed_action: str | None = None
    available_synthetic_tools: list[str] = Field(default_factory=list)
    previous_public_audit_decisions: list[dict[str, Any]] = Field(default_factory=list)
    previous_visible_interventions: list[dict[str, Any]] = Field(default_factory=list)
    previous_failed_attack_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    current_attack_budget: NonNegativeFloat = 0.0
    public_policy_description: dict[str, Any] | None = None
    public_monitor_scores: dict[str, float] | None = None
    estimated_remaining_horizon: NonNegativeInt = 0
    attacker_observable_features: dict[str, Any] = Field(default_factory=dict)
    white_box_synthetic_state: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class AttackDecision(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    decision_id: str
    opportunity_id: str
    attacker_name: str
    attacker_version: str
    action: AttackAction
    selected_attack_method: str | None = None
    target_constraint: str | None = None
    target_branch: str | None = None
    expected_utility: float = 0.0
    expected_detection_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    expected_success_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    concealment_strategy: str | None = None
    decision_rationale: str
    random_seed: int = 0
    attacker_state_version: str = "phase6_v1"


class ConcealmentEvent(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    concealment_id: str
    attack_id: str
    strategy: str
    added_cost: NonNegativeFloat = 0.0
    changed_detectability: float = 0.0
    changed_preventability: bool = False
    utility_effect: float = 0.0
    internal_only: bool = False
    detection_delayed: bool = False
    moved_branches: bool = False


class AttackEvent(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    attack_id: str
    start_step: str
    end_step: str | None = None
    target: str | None = None
    method: str
    branch: str | None = None
    attack_status: AttackStatus
    observable_artifacts: dict[str, Any] = Field(default_factory=dict)
    hidden_synthetic_state: dict[str, Any] = Field(default_factory=dict)
    cost_consumed: NonNegativeFloat = 0.0
    detection_state: str = "unknown"
    intervention_state: str = "unknown"
    objective_violation_ids: list[str] = Field(default_factory=list)
    outcome: str = "pending"
    failure_reason: str | None = None
    artifact_version: str = "phase6_v1"


class AttackState(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    attacker_identity: str
    knowledge_level: KnowledgeTier
    remaining_attack_budget: NonNegativeFloat
    active_attacks: list[AttackEvent] = Field(default_factory=list)
    previous_opportunities: list[AttackOpportunity] = Field(default_factory=list)
    previous_decisions: list[AttackDecision] = Field(default_factory=list)
    public_audit_history: list[dict[str, Any]] = Field(default_factory=list)
    public_intervention_history: list[dict[str, Any]] = Field(default_factory=list)
    estimated_policy_model: dict[str, Any] = Field(default_factory=dict)
    estimated_monitor_model: dict[str, Any] = Field(default_factory=dict)
    posterior_beliefs: dict[str, Any] = Field(default_factory=dict)
    random_state: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttackPrimitiveSpec(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    primitive_id: str
    domain: str
    method: str
    preconditions: list[str]
    applicable_domains: list[str]
    observable_artifacts: dict[str, Any]
    objective_scoring_mechanism: str
    cost: NonNegativeFloat
    expected_benefit: float
    concealment_options: list[str] = Field(default_factory=list)
    synthetic_only: bool = True


class AttackerConfig(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    name: str
    attacker_type: str
    version: str = "phase6_v1"
    knowledge_tier: KnowledgeTier = "tier0_task_only"
    attack_budget: NonNegativeFloat = 1.0
    objective: AttackObjective
    seed: int = 0
    evaluation_only: bool = False
    enabled: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class AttackerDefenderOutcome(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    outcome_id: str
    attacker_name: str
    defender_name: str
    knowledge_tier: KnowledgeTier
    opportunity_count: NonNegativeInt
    attack_attempt_count: NonNegativeInt
    attack_success_count: NonNegativeInt
    detected_count: NonNegativeInt
    prevented_count: NonNegativeInt
    aborted_count: NonNegativeInt
    concealed_count: NonNegativeInt
    moved_count: NonNegativeInt
    severity_weighted_harm: float = 0.0
    task_utility: float = 0.0
    oversight_cost: NonNegativeFloat = 0.0
    attack_cost: NonNegativeFloat = 0.0
    synthetic: bool = True
    configuration_hash: str
    data_hash: str
    code_commit: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PayoffMatrixRecord(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    matrix_id: str
    attacker_names: list[str]
    defender_names: list[str]
    payoff_rows: list[dict[str, Any]]
    best_responses: list[dict[str, Any]] = Field(default_factory=list)
    defender_regret: dict[str, float] = Field(default_factory=dict)
    attacker_regret: dict[str, float] = Field(default_factory=dict)
    exploitability: float = 0.0
    maximin_defender: str | None = None
    minimax_attacker: str | None = None
    empirical_mixed_strategies: dict[str, dict[str, float]] = Field(default_factory=dict)
    synthetic: bool = True
    artifact_version: str = "phase6_v1"
    configuration_hash: str
    data_hash: str
    code_commit: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class DisplacementRecord(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    displacement_id: str
    baseline_attack_id: str
    intervention_attack_id: str | None = None
    classification: str
    valid_pairing: bool
    reason: str | None = None
    same_task: bool = True
    same_architecture: bool = True
    same_seed: bool = True
    same_attack_budget: bool = True


class RedTeamIterationRecord(StrictModel):
    schema_version: str = ATTACK_SCHEMA_VERSION
    iteration_id: str
    iteration_number: NonNegativeInt
    attacker_version: str
    defender_version: str
    training_artifacts: list[str] = Field(default_factory=list)
    evaluation_split: str
    improvement_over_previous: float = 0.0
    overfitting_indicators: dict[str, float] = Field(default_factory=dict)
    resource_use: dict[str, float] = Field(default_factory=dict)
    synthetic: bool = True
