"""Adaptive audit-allocation policies for Phase 5."""

from __future__ import annotations

import random

from bayesaudit.adaptive.bayesian import BetaBernoulliRiskState
from bayesaudit.adaptive.types import AdaptivePolicyDecision, AdaptivePolicyResult
from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.monitoring.types import LabelValue, MonitorExample, MonitorPrediction
from bayesaudit.schemas import OversightAction


def learned_threshold_policy(
    examples: list[MonitorExample],
    predictions: list[MonitorPrediction],
    *,
    threshold: float = 0.5,
    budget: int = 1,
    policy_name: str = "learned_threshold",
) -> AdaptivePolicyResult:
    return _risk_policy(
        examples,
        predictions,
        threshold=threshold,
        budget=budget,
        policy_name=policy_name,
    )


def top_risk_policy(
    examples: list[MonitorExample],
    predictions: list[MonitorPrediction],
    *,
    budget: int,
    policy_name: str = "top_risk",
) -> AdaptivePolicyResult:
    selected = {
        prediction.example_id
        for prediction in sorted(
            predictions, key=lambda item: item.current_violation_probability, reverse=True
        )[:budget]
    }
    return _selective_policy(
        examples,
        predictions,
        selected,
        budget=budget,
        policy_name=policy_name,
        online=False,
    )


def online_priority_policy(
    examples: list[MonitorExample],
    predictions: list[MonitorPrediction],
    *,
    budget: int,
    estimated_remaining_opportunities: int | None = None,
    policy_name: str = "online_priority",
) -> AdaptivePolicyResult:
    remaining = budget
    decisions = []
    by_id = {prediction.example_id: prediction for prediction in predictions}
    for index, example in enumerate(examples):
        prediction = by_id[example.example_id]
        remaining_opportunities = estimated_remaining_opportunities or max(1, len(examples) - index)
        threshold = max(0.1, remaining / remaining_opportunities)
        audit = remaining > 0 and prediction.current_violation_probability >= threshold
        if audit:
            remaining -= 1
        decisions.append(_decision(policy_name, example, prediction, audit, remaining, online=True))
    return AdaptivePolicyResult(
        policy_name=policy_name,
        decisions=decisions,
        metrics=_policy_metrics(decisions, examples),
    )


def thompson_policy(
    examples: list[MonitorExample],
    *,
    budget: int,
    seed: int = 1,
    policy_name: str = "thompson",
) -> AdaptivePolicyResult:
    rng = random.Random(seed)
    state = BetaBernoulliRiskState(group_key="domain")
    decisions = []
    updates = []
    remaining = budget
    for example in examples:
        risk = rng.betavariate(
            state.posteriors[state._group(example)][0],
            state.posteriors[state._group(example)][1],
        )
        prediction = _prediction_from_risk(example, risk)
        audit = remaining > 0 and risk >= 0.5
        if audit:
            remaining -= 1
        decisions.append(_decision(policy_name, example, prediction, audit, remaining, online=True))
        label = example.current_violation_label == LabelValue.POSITIVE
        updates.append(state.update_from_audit(example, label_positive=label, audited=audit))
    result = AdaptivePolicyResult(policy_name=policy_name, decisions=decisions, updates=updates)
    result.posterior_snapshots.append(state.snapshot(seed=seed))
    result.metrics = _policy_metrics(decisions, examples)
    return result


def expected_harm_policy(
    examples: list[MonitorExample],
    predictions: list[MonitorPrediction],
    *,
    budget: int,
    audit_cost: float = 1.0,
    intervention_cost: float = 1.0,
    policy_name: str = "expected_harm",
) -> AdaptivePolicyResult:
    remaining = budget
    decisions = []
    by_id = {prediction.example_id: prediction for prediction in predictions}
    for example in examples:
        prediction = by_id[example.example_id]
        value = (
            prediction.preventable_violation_probability
            * max(1.0, prediction.expected_severity)
            * prediction.intervention_usefulness_probability
            - audit_cost
            - 0.1 * intervention_cost
        )
        audit = remaining > 0 and value > 0.0
        if audit:
            remaining -= 1
        decisions.append(
            _decision(
                policy_name,
                example,
                prediction,
                audit,
                remaining,
                online=True,
                net_value=value,
            )
        )
    return AdaptivePolicyResult(
        policy_name=policy_name,
        decisions=decisions,
        metrics=_policy_metrics(decisions, examples),
    )


def value_of_information_policy(
    examples: list[MonitorExample],
    predictions: list[MonitorPrediction],
    *,
    budget: int,
    uncertainty_weight: float = 0.25,
    policy_name: str = "value_of_information",
) -> AdaptivePolicyResult:
    remaining = budget
    decisions = []
    by_id = {prediction.example_id: prediction for prediction in predictions}
    for example in examples:
        prediction = by_id[example.example_id]
        uncertainty = 1.0 - abs(prediction.current_violation_probability - 0.5) * 2
        value = (
            prediction.current_violation_probability * max(1.0, prediction.expected_severity)
            + uncertainty_weight * uncertainty
        )
        audit = remaining > 0 and value > 1.0
        if audit:
            remaining -= 1
        decisions.append(
            _decision(
                policy_name,
                example,
                prediction,
                audit,
                remaining,
                online=True,
                net_value=value,
            )
        )
    return AdaptivePolicyResult(
        policy_name=policy_name,
        decisions=decisions,
        metrics=_policy_metrics(decisions, examples),
    )


def _risk_policy(
    examples: list[MonitorExample],
    predictions: list[MonitorPrediction],
    *,
    threshold: float,
    budget: int,
    policy_name: str,
) -> AdaptivePolicyResult:
    selected: set[str] = set()
    remaining = budget
    for prediction in predictions:
        if remaining > 0 and prediction.current_violation_probability >= threshold:
            selected.add(prediction.example_id)
            remaining -= 1
    return _selective_policy(
        examples,
        predictions,
        selected,
        budget=budget,
        policy_name=policy_name,
        online=True,
    )


def _selective_policy(
    examples: list[MonitorExample],
    predictions: list[MonitorPrediction],
    selected: set[str],
    *,
    budget: int,
    policy_name: str,
    online: bool,
) -> AdaptivePolicyResult:
    remaining = budget
    by_id = {prediction.example_id: prediction for prediction in predictions}
    decisions = []
    for example in examples:
        audit = example.example_id in selected and remaining > 0
        if audit:
            remaining -= 1
        decisions.append(
            _decision(
                policy_name,
                example,
                by_id[example.example_id],
                audit,
                remaining,
                online=online,
            )
        )
    return AdaptivePolicyResult(
        policy_name=policy_name,
        decisions=decisions,
        metrics=_policy_metrics(decisions, examples),
    )


def _decision(
    policy_name: str,
    example: MonitorExample,
    prediction: MonitorPrediction,
    audit: bool,
    remaining: int,
    *,
    online: bool,
    net_value: float | None = None,
) -> AdaptivePolicyDecision:
    return AdaptivePolicyDecision(
        adaptive_decision_id="adapt_"
        + canonical_json_hash({"policy": policy_name, "example": example.example_id})[:16],
        policy_name=policy_name,
        observation_id=example.observation_id,
        risk_estimate=prediction.current_violation_probability,
        expected_severity=prediction.expected_severity,
        intervention_effectiveness=prediction.intervention_usefulness_probability,
        expected_net_value=net_value
        if net_value is not None
        else prediction.current_violation_probability * max(1.0, prediction.expected_severity),
        action=OversightAction.AUDIT if audit else OversightAction.CONTINUE,
        reason="budgeted risk allocation"
        if audit
        else "below allocation threshold or budget exhausted",
        budget_remaining=float(remaining),
        online=online,
    )


def _prediction_from_risk(example: MonitorExample, risk: float) -> MonitorPrediction:
    return MonitorPrediction(
        prediction_id="thompson_" + example.example_id,
        monitor_name="beta_bernoulli_risk_state",
        monitor_version="phase5_v1",
        model_artifact_hash="online",
        example_id=example.example_id,
        current_violation_probability=risk,
        imminent_violation_probability=risk,
        preventable_violation_probability=risk,
        expected_severity=float(example.severity_target or 1.0) * risk,
        intervention_usefulness_probability=risk,
    )


def _policy_metrics(
    decisions: list[AdaptivePolicyDecision], examples: list[MonitorExample]
) -> dict[str, float]:
    by_observation = {example.observation_id: example for example in examples}
    audits = [decision for decision in decisions if decision.action == OversightAction.AUDIT]
    true_audits = sum(
        by_observation[decision.observation_id].current_violation_label == LabelValue.POSITIVE
        for decision in audits
    )
    positives = sum(example.current_violation_label == LabelValue.POSITIVE for example in examples)
    return {
        "audit_count": float(len(audits)),
        "audit_yield": true_audits / len(audits) if audits else 0.0,
        "recall": true_audits / positives if positives else 0.0,
        "budget_used": float(len(audits)),
        "oracle_regret_proxy": float(max(0, positives - true_audits)),
    }
