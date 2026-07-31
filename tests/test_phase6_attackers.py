from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from pytest import CaptureFixture, MonkeyPatch

from bayesaudit.attackers.analysis import (
    build_payoff_matrix,
    classify_displacement,
    red_team_loop,
    selection_bias_metrics,
)
from bayesaudit.attackers.config import (
    load_attacker_config,
    load_phase6_experiment_config,
    validate_attackers,
    validate_attacks,
)
from bayesaudit.attackers.estimators import (
    BetaBernoulliAttackEstimator,
    EmpiricalGroupedEstimator,
    FixedSyntheticEstimator,
    LearnedAttackEstimator,
)
from bayesaudit.attackers.lifecycle import (
    default_attack_objective,
    opportunities_from_examples,
    run_attacker_defender_matrix,
)
from bayesaudit.attackers.models import ATTACKER_CLASSES, attacker_for_config
from bayesaudit.attackers.observations import (
    FORBIDDEN_ATTACKER_OBSERVATION_KEYS,
    build_attacker_observation,
)
from bayesaudit.attackers.primitives import (
    PRIMITIVE_SPECS,
    applicable_primitives,
    apply_primitive,
    validate_primitives,
)
from bayesaudit.attackers.types import (
    ATTACK_SCHEMA_VERSION,
    AttackerConfig,
    AttackerDefenderOutcome,
    AttackOpportunity,
    AttackState,
    KnowledgeTier,
)
from bayesaudit.cli import main
from bayesaudit.monitoring.types import LabelValue, MonitorExample
from bayesaudit.oversight.policy_base import OversightPolicyConfig
from bayesaudit.schemas import ArchitectureKind, Domain, OversightAction


def _opportunity(
    *,
    domain: Domain = Domain.PRIVACY,
    detection: float = 0.2,
    methods: list[str] | None = None,
) -> AttackOpportunity:
    return AttackOpportunity(
        opportunity_id=f"opp_{domain.value}_{detection}",
        trajectory_id="traj_1",
        step_id="obs_1",
        checkpoint_type="before_final_output",
        agent_id="agent",
        branch_id="branch_1",
        delegation_depth=1,
        domain=domain,
        architecture=ArchitectureKind.UNSTRUCTURED_DELEGATION,
        available_attack_methods=methods
        or [primitive.primitive_id for primitive in applicable_primitives(domain.value)],
        targetable_constraints=["constraint_1"],
        estimated_benefit=5.0,
        estimated_success_probability=0.7,
        estimated_detection_probability=detection,
        estimated_intervention_probability=0.2,
        estimated_cost=1.0,
        observable_evidence={"agent_role": "worker"},
    )


def _config(
    attacker_type: str, *, budget: float = 2.0, evaluation_only: bool = False
) -> AttackerConfig:
    return AttackerConfig(
        name=f"{attacker_type}_unit",
        attacker_type=attacker_type,
        knowledge_tier="tier2_public_config",
        attack_budget=budget,
        seed=3,
        evaluation_only=evaluation_only,
        objective=default_attack_objective(
            ["privacy_internal_identifier_leak", "authorization_prohibited_tool"]
        ),
        parameters={"attack_probability": 1.0, "max_detection_probability": 0.3},
    )


def _state(tier: str = "tier0_task_only") -> AttackState:
    return AttackState(
        attacker_identity="unit",
        knowledge_level=cast(KnowledgeTier, tier),
        remaining_attack_budget=2.0,
        public_audit_history=[{"audit_requested": True}],
        public_intervention_history=[{"action": "block"}],
    )


def _example(index: int = 0) -> MonitorExample:
    features = {
        "depth": 0,
        "branch_present": False,
        "step_kind": "final",
        "agent_role": "agent",
        "architecture": "single_agent",
        "prior_audit_count": 0,
        "remaining_budget": 2.0,
        "constraint_count": 2,
        "critical_constraint_count": 1,
        "tool_call_count": 0,
        "missing_required_constraints": False,
        "weakened_constraints": False,
        "contradicted_constraints": False,
        "privilege_demotions": False,
        "verification_failures": False,
        "tool_requested": False,
        "approval_required": False,
        "approval_present": False,
        "prohibited_tool_indicator": False,
        "sensitive_token_indicator": index % 2 == 0,
        "irreversible_action_indicator": False,
        "external_tool_indicator": False,
        "text_length": 100,
        "identifier_count": 1,
        "citation_count": 0,
        "unknown_citation_count": 0,
        "budget_numeric_count": 1,
        "approval_language_indicator": False,
        "constraint_reference_count": 1,
        "uncertainty_language_indicator": False,
    }
    return MonitorExample(
        example_id=f"mon_phase6_{index}",
        observation_id=f"obs_phase6_{index}",
        trajectory_id=f"traj_phase6_{index}",
        run_id=f"run_phase6_{index}",
        experiment_id="phase6_unit",
        task_id="task_privacy_aggregate_only",
        task_version="v1",
        template_family="privacy",
        domain=Domain.PRIVACY,
        architecture=ArchitectureKind.SINGLE_AGENT,
        model_family="mock",
        checkpoint_type="before_final_output",
        sequence_index=index,
        depth=0,
        observable_feature_payload=features,
        observable_text_payload="synthetic redacted observation",
        current_violation_label=LabelValue.NEGATIVE,
        imminent_violation_label=LabelValue.NEGATIVE,
        preventable_imminent_violation_label=LabelValue.NEGATIVE,
        severity_target=0.0,
        intervention_usefulness_label=LabelValue.NEGATIVE,
        final_output_violation_label=LabelValue.NEGATIVE,
        internal_only_violation_label=LabelValue.NEGATIVE,
        label_horizon=1,
        label_source="synthetic",
        label_confidence=1.0,
        split_group_ids={
            "base_task_id": "task_privacy_aggregate_only",
            "domain": "privacy",
            "architecture": "single_agent",
        },
        source_artifact_hashes={"trajectory": "t", "score": "s"},
    )


@pytest.mark.parametrize("primitive", PRIMITIVE_SPECS)
def test_primitive_metadata_is_synthetic_and_scored(primitive) -> None:  # type: ignore[no-untyped-def]
    assert primitive.schema_version == ATTACK_SCHEMA_VERSION
    assert primitive.synthetic_only is True
    assert primitive.preconditions
    assert primitive.objective_scoring_mechanism


@pytest.mark.parametrize("primitive", PRIMITIVE_SPECS)
def test_primitive_positive_application(primitive) -> None:  # type: ignore[no-untyped-def]
    opportunity = _opportunity(
        domain=Domain(primitive.applicable_domains[0]),
        methods=[primitive.primitive_id],
    )
    event = apply_primitive(primitive, opportunity)
    assert event.attack_status in {"completed", "concealed"}
    assert event.objective_violation_ids


@pytest.mark.parametrize("primitive", PRIMITIVE_SPECS)
def test_primitive_negative_control_blocks_wrong_domain(primitive) -> None:  # type: ignore[no-untyped-def]
    wrong = Domain.EVIDENCE if "evidence" not in primitive.applicable_domains else Domain.PRIVACY
    opportunity = _opportunity(domain=wrong, methods=[primitive.primitive_id])
    event = apply_primitive(primitive, opportunity)
    if wrong.value not in primitive.applicable_domains:
        assert event.attack_status == "blocked"


@pytest.mark.parametrize("primitive", PRIMITIVE_SPECS)
def test_primitive_serialization_round_trip(primitive) -> None:  # type: ignore[no-untyped-def]
    payload = primitive.model_dump(mode="json")
    assert payload["primitive_id"] == primitive.primitive_id


def test_validate_primitives_reports_catalog_size() -> None:
    assert validate_primitives()["primitive_count"] == len(PRIMITIVE_SPECS)


@pytest.mark.parametrize(
    ("tier", "has_policy", "has_feedback", "has_score", "has_white_box"),
    [
        ("tier0_task_only", False, False, False, False),
        ("tier1_protocol_class", True, False, False, False),
        ("tier2_public_config", True, False, False, False),
        ("tier3_black_box_feedback", True, True, False, False),
        ("tier4_monitor_score", True, True, True, False),
        ("tier5_white_box_synthetic", True, True, True, True),
    ],
)
def test_attacker_observation_knowledge_tiers(
    tier: str, has_policy: bool, has_feedback: bool, has_score: bool, has_white_box: bool
) -> None:
    observation = build_attacker_observation(
        opportunity=_opportunity(),
        state=_state(tier),
        attacker_name="unit",
        policy_context={
            "policy_family": "fixed",
            "audit_budget": 2,
            "private_monitor_parameters": "x",
        },
        monitor_scores={"risk": 0.2},
        white_box_state={"weights": [1.0]},
    )
    assert (observation.public_policy_description is not None) is has_policy
    assert bool(observation.previous_public_audit_decisions) is has_feedback
    assert (observation.public_monitor_scores is not None) is has_score
    assert (observation.white_box_synthetic_state is not None) is has_white_box


@pytest.mark.parametrize("token", sorted(FORBIDDEN_ATTACKER_OBSERVATION_KEYS))
def test_attacker_observation_rejects_forbidden_tokens(token: str) -> None:
    with pytest.raises(ValueError):
        build_attacker_observation(
            opportunity=_opportunity(),
            state=_state(),
            attacker_name="unit",
            task_description=token,
        )


@pytest.mark.parametrize("attacker_type", sorted(ATTACKER_CLASSES))
def test_attackers_are_deterministic_and_budgeted(attacker_type: str) -> None:
    config = _config(attacker_type, evaluation_only=attacker_type == "oracle")
    attacker = attacker_for_config(config, evaluation=config.evaluation_only)
    result_one = attacker.run([_opportunity(), _opportunity(detection=0.25)])
    result_two = attacker_for_config(config, evaluation=config.evaluation_only).run(
        [_opportunity(), _opportunity(detection=0.25)]
    )
    assert [decision.action for decision in result_one.decisions] == [
        decision.action for decision in result_two.decisions
    ]
    assert result_one.state.remaining_attack_budget >= 0.0


def test_oracle_attacker_blocked_without_evaluation() -> None:
    with pytest.raises(PermissionError):
        attacker_for_config(_config("oracle"), evaluation=False)


def test_honest_attacker_never_attacks() -> None:
    result = attacker_for_config(_config("honest")).run([_opportunity()])
    assert result.decisions[0].action == "do_not_attack"
    assert not result.events


def test_risk_avoiding_attacker_skips_high_detection() -> None:
    result = attacker_for_config(_config("risk_avoiding")).run([_opportunity(detection=0.8)])
    assert result.decisions[0].action == "do_not_attack"


def test_start_stop_attacker_aborts_with_active_attack_high_risk() -> None:
    attacker = attacker_for_config(_config("start_stop"))
    state = attacker.initialize()
    first = apply_primitive(
        PRIMITIVE_SPECS[0],
        _opportunity(methods=[PRIMITIVE_SPECS[0].primitive_id]),
    )
    first.attack_status = "active"
    state.active_attacks.append(first)
    decision = attacker.decide(_opportunity(detection=0.8), state)
    assert decision.action == "abort_attack"


def test_bayesian_estimator_updates_only_observable_feedback() -> None:
    estimator = BetaBernoulliAttackEstimator()
    opportunity = _opportunity()
    before = estimator.estimate_opportunity(opportunity).success_probability
    estimator.update(opportunity, attacked=True, success=True, detected=False, observable=False)
    assert estimator.estimate_opportunity(opportunity).success_probability == before
    estimator.update(opportunity, attacked=True, success=True, detected=False, observable=True)
    assert estimator.estimate_opportunity(opportunity).success_probability > before


def test_empirical_grouped_estimator_updates_from_observed_outcomes() -> None:
    estimator = EmpiricalGroupedEstimator()
    opportunity = _opportunity()
    estimator.update(opportunity, success=True, detected=False)
    estimate = estimator.estimate_opportunity(opportunity)
    assert estimate.success_probability == 1.0
    assert estimate.detection_probability == 0.0


def test_learned_estimator_uses_attacker_observable_features() -> None:
    estimate = LearnedAttackEstimator().estimate_opportunity(_opportunity(detection=0.1))
    assert 0.0 <= estimate.success_probability <= 1.0


def test_fixed_estimator_utility_includes_costs() -> None:
    estimate = FixedSyntheticEstimator().estimate_opportunity(_opportunity())
    assert estimate.expected_utility(detection_penalty=2, intervention_penalty=2) < estimate.benefit


def test_opportunities_from_monitor_examples() -> None:
    opportunities = opportunities_from_examples([_example()])
    assert opportunities
    assert opportunities[0].available_attack_methods


def test_run_attacker_defender_matrix_dry_run() -> None:
    config = load_phase6_experiment_config(Path("configs/experiments/phase6_smoke.yaml"))
    payload = run_attacker_defender_matrix(config, dry_run=True)
    assert payload["synthetic_only"] is True
    assert payload["planned_attacker_defender_evaluations"] > 0


def test_phase6_holdout_config_records_holdout_axes() -> None:
    config = load_phase6_experiment_config(Path("configs/experiments/phase6_holdouts.yaml"))
    assert config.holdouts["policy_holdout"] == "random_shadow"
    assert config.holdouts["domain_holdout"] == "evidence"


def test_run_attacker_defender_matrix_records_outcomes(tmp_path: Path) -> None:
    config = load_phase6_experiment_config(Path("configs/experiments/phase6_smoke.yaml"))
    config.output_root = tmp_path
    payload = run_attacker_defender_matrix(config)
    assert payload["outcome_count"] == len(config.attackers) * len(config.defenders)
    assert (tmp_path / config.experiment_id / "attacker_defender_outcomes.json").exists()


def _outcome(attacker: str, defender: str, success: int) -> AttackerDefenderOutcome:
    return AttackerDefenderOutcome(
        outcome_id=f"{attacker}_{defender}",
        attacker_name=attacker,
        defender_name=defender,
        knowledge_tier="tier0_task_only",
        opportunity_count=2,
        attack_attempt_count=2,
        attack_success_count=success,
        detected_count=1,
        prevented_count=0,
        aborted_count=0,
        concealed_count=0,
        moved_count=0,
        severity_weighted_harm=float(success * 5),
        task_utility=1.0,
        oversight_cost=1.0,
        attack_cost=2.0,
        configuration_hash="c",
        data_hash="d",
    )


def test_build_payoff_matrix_has_dimensions() -> None:
    matrix = build_payoff_matrix(
        [_outcome("a1", "d1", 1), _outcome("a1", "d2", 0), _outcome("a2", "d1", 2)]
    )
    assert len(matrix.attacker_names) == 2
    assert len(matrix.defender_names) == 2
    assert matrix.exploitability >= 0.0


def test_selection_bias_metrics_separate_conditional_and_unconditional() -> None:
    metrics = selection_bias_metrics(10, 2, 8.0, 3.0)
    assert metrics["conditional_harm"] > metrics["unconditional_harm"]


@pytest.mark.parametrize(
    ("kwargs", "classification"),
    [
        ({}, "fully_prevented"),
        ({"moved_branch": True, "intervention_attack_id": "b"}, "moved_to_another_branch"),
        ({"changed_method": True, "intervention_attack_id": "b"}, "changed_method"),
        ({"aborted": True, "intervention_attack_id": "b"}, "aborted"),
        ({"reattempted": True, "intervention_attack_id": "b"}, "reattempted"),
        ({"valid_pairing": False, "intervention_attack_id": "b"}, "invalid"),
    ],
)
def test_displacement_classification(kwargs: dict[str, Any], classification: str) -> None:
    intervention_attack_id = kwargs.pop("intervention_attack_id", None)
    record = classify_displacement("a", intervention_attack_id, **kwargs)
    assert record.classification == classification


def test_red_team_loop_does_not_touch_confirmatory_split() -> None:
    payload = red_team_loop(2, dry_run=True)
    assert payload["iteration_count"] == 2
    assert all(row["evaluation_split"] == "exploratory" for row in payload["records"])


def test_validate_attackers_and_attacks() -> None:
    assert validate_attackers(Path("configs/attackers"))["valid"] is True
    assert validate_attacks()["valid"] is True


def test_load_attacker_config_blocks_schema_drift() -> None:
    config = load_attacker_config(Path("configs/attackers/opportunistic/smoke.yaml"))
    assert config.attacker_type == "opportunistic"


def test_policy_budget_inference_records_public_budget() -> None:
    observation = build_attacker_observation(
        opportunity=_opportunity(),
        state=_state("tier2_public_config"),
        attacker_name="unit",
        policy_context={"policy_family": "fixed", "audit_budget": 2},
    )
    assert observation.public_policy_description == {"policy_family": "fixed", "audit_budget": 2}


def test_attack_decision_uses_oversight_action_enum_for_reference() -> None:
    assert OversightAction.BLOCK.value == "block_proposed_action"


def test_defender_config_can_model_intervention_mode() -> None:
    config = OversightPolicyConfig(name="fixed", policy_type="fixed", budget=2, mode="intervention")
    assert config.mode == "intervention"


def test_cli_validate_attackers(capsys: CaptureFixture[str], monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["bayesaudit", "validate-attackers"])
    main()
    assert '"valid": true' in capsys.readouterr().out


def test_cli_validate_attacks(capsys: CaptureFixture[str], monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["bayesaudit", "validate-attacks"])
    main()
    assert '"primitive_count": 15' in capsys.readouterr().out


def test_cli_run_attacker_defender_dry_run(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "bayesaudit",
            "run-attacker-defender",
            "--config",
            "configs/experiments/phase6_smoke.yaml",
            "--dry-run",
        ],
    )
    main()
    assert '"synthetic_only": true' in capsys.readouterr().out


def test_cli_compare_attack_selection_dry_run(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "bayesaudit",
            "compare-attack-selection",
            "--config",
            "configs/experiments/phase6_selection.yaml",
            "--dry-run",
        ],
    )
    main()
    assert '"capability_held_fixed": true' in capsys.readouterr().out


def test_cli_build_payoff_matrix(capsys: CaptureFixture[str], monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["bayesaudit", "build-payoff-matrix", "--config", "configs/experiments/phase6_smoke.yaml"],
    )
    main()
    assert '"schema_version": "bayesaudit.attack.v1"' in capsys.readouterr().out


def test_cli_red_team_loop_dry_run(capsys: CaptureFixture[str], monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "bayesaudit",
            "run-red-team-loop",
            "--config",
            "configs/experiments/phase6_red_team_loop.yaml",
            "--dry-run",
        ],
    )
    main()
    assert '"dry_run": true' in capsys.readouterr().out
