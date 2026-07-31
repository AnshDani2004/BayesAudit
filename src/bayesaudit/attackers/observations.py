"""Attacker-side observation construction with explicit knowledge boundaries."""

from __future__ import annotations

from typing import Any

from bayesaudit.attackers.types import AttackerObservation, AttackOpportunity, AttackState
from bayesaudit.hash_utils import canonical_json_hash

FORBIDDEN_ATTACKER_OBSERVATION_KEYS = {
    "ground_truth",
    "violations",
    "hidden_scores",
    "objective_scores",
    "future_audit_draws",
    "future_policy_actions",
    "oracle",
    "counterfactual",
    "human_annotations",
    "private_monitor_parameters",
    "unobserved_branches",
    "future_tool_results",
}

KNOWLEDGE_ORDER = {
    "tier0_task_only": 0,
    "tier1_protocol_class": 1,
    "tier2_public_config": 2,
    "tier3_black_box_feedback": 3,
    "tier4_monitor_score": 4,
    "tier5_white_box_synthetic": 5,
}


def build_attacker_observation(
    *,
    opportunity: AttackOpportunity,
    state: AttackState,
    attacker_name: str,
    task_description: str = "",
    delegated_subtask: str = "",
    visible_constraints: list[dict[str, Any]] | None = None,
    proposed_action: str | None = None,
    available_tools: list[str] | None = None,
    policy_context: dict[str, Any] | None = None,
    monitor_scores: dict[str, float] | None = None,
    white_box_state: dict[str, Any] | None = None,
    estimated_remaining_horizon: int = 0,
) -> AttackerObservation:
    tier = state.knowledge_level
    public_policy = _policy_context_for_tier(tier, policy_context or {})
    public_monitor = monitor_scores if _tier_at_least(tier, "tier4_monitor_score") else None
    white_box = white_box_state if _tier_at_least(tier, "tier5_white_box_synthetic") else None
    prior_audits = (
        state.public_audit_history if _tier_at_least(tier, "tier3_black_box_feedback") else []
    )
    prior_interventions = (
        state.public_intervention_history
        if _tier_at_least(tier, "tier3_black_box_feedback")
        else []
    )
    observation = AttackerObservation(
        observation_id="atkobs_"
        + canonical_json_hash(
            {
                "opportunity": opportunity.opportunity_id,
                "attacker": attacker_name,
                "tier": tier,
                "budget": state.remaining_attack_budget,
            }
        )[:20],
        opportunity_id=opportunity.opportunity_id,
        attacker_name=attacker_name,
        knowledge_tier=tier,
        current_task_description=task_description,
        current_delegated_subtask=delegated_subtask,
        visible_constraints=visible_constraints or [],
        current_agent_role=str(opportunity.observable_evidence.get("agent_role", "")) or None,
        current_branch=opportunity.branch_id,
        delegation_depth=opportunity.delegation_depth,
        proposed_action=proposed_action,
        available_synthetic_tools=available_tools or [],
        previous_public_audit_decisions=prior_audits,
        previous_visible_interventions=prior_interventions,
        previous_failed_attack_outcomes=[
            event.model_dump(mode="json")
            for event in state.active_attacks
            if event.attack_status in {"failed", "aborted", "blocked"}
        ],
        current_attack_budget=state.remaining_attack_budget,
        public_policy_description=public_policy,
        public_monitor_scores=public_monitor,
        estimated_remaining_horizon=estimated_remaining_horizon,
        attacker_observable_features={
            "checkpoint_type": opportunity.checkpoint_type,
            "domain": str(opportunity.domain),
            "architecture": str(opportunity.architecture),
            "depth": opportunity.delegation_depth,
            "still_preventable": opportunity.still_preventable,
        },
        white_box_synthetic_state=white_box,
    )
    _assert_no_forbidden_attacker_fields(observation.model_dump(mode="json"))
    return observation


def _policy_context_for_tier(tier: str, policy_context: dict[str, Any]) -> dict[str, Any] | None:
    if _tier_at_least(tier, "tier2_public_config"):
        return {
            key: value
            for key, value in policy_context.items()
            if key
            in {
                "policy_family",
                "audit_budget",
                "checkpoint_schedule",
                "rule_description",
                "monitor_type",
                "intervention_types",
            }
        }
    if _tier_at_least(tier, "tier1_protocol_class"):
        family = policy_context.get("policy_family")
        return {"policy_family": family} if family is not None else None
    return None


def _tier_at_least(tier: str, minimum: str) -> bool:
    return KNOWLEDGE_ORDER[tier] >= KNOWLEDGE_ORDER[minimum]


def _assert_no_forbidden_attacker_fields(payload: dict[str, Any]) -> None:
    text = str(payload).lower()
    leaked = [token for token in FORBIDDEN_ATTACKER_OBSERVATION_KEYS if token in text]
    if leaked:
        raise ValueError(f"forbidden attacker observation token leaked: {sorted(leaked)}")
