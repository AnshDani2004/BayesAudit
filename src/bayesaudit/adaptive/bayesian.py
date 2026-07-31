"""Bayesian online risk state for adaptive oversight."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from bayesaudit.adaptive.types import BayesianUpdateRecord, PosteriorSnapshot
from bayesaudit.hash_utils import canonical_json_hash
from bayesaudit.monitoring.types import FEATURE_SCHEMA_VERSION, MonitorExample


class BetaBernoulliRiskState:
    def __init__(self, *, alpha: float = 1.0, beta: float = 1.0, group_key: str = "domain") -> None:
        self.alpha0 = alpha
        self.beta0 = beta
        self.group_key = group_key
        self.posteriors: dict[str, list[float]] = defaultdict(lambda: [self.alpha0, self.beta0])
        self.updates: list[BayesianUpdateRecord] = []

    def estimate(self, example: MonitorExample) -> float:
        alpha, beta = self.posteriors[self._group(example)]
        return float(alpha / (alpha + beta))

    def uncertainty(self, example: MonitorExample) -> float:
        alpha, beta = self.posteriors[self._group(example)]
        total = alpha + beta
        return float((alpha * beta / ((total**2) * (total + 1))) ** 0.5)

    def update_from_audit(
        self,
        example: MonitorExample,
        *,
        label_positive: bool | None,
        audited: bool,
        feedback_available: bool = True,
        delay_steps: int = 0,
        confidence: float = 1.0,
    ) -> BayesianUpdateRecord:
        should_update = audited and feedback_available and label_positive is not None
        if should_update:
            params = self.posteriors[self._group(example)]
            params[0 if label_positive else 1] += confidence
        record = BayesianUpdateRecord(
            update_id="upd_"
            + canonical_json_hash(
                {
                    "example": example.example_id,
                    "audited": audited,
                    "feedback": feedback_available,
                    "label": label_positive,
                    "n": len(self.updates),
                }
            )[:16],
            observation_id=example.observation_id,
            audited=audited,
            feedback_available=feedback_available,
            posterior_updated=should_update,
            feedback_delay_steps=delay_steps,
            feedback_confidence=confidence,
            reason="audit feedback" if should_update else "no eligible audit feedback",
        )
        self.updates.append(record)
        return record

    def snapshot(self, *, seed: int = 0) -> PosteriorSnapshot:
        parameters = {
            group: {"alpha": values[0], "beta": values[1]}
            for group, values in self.posteriors.items()
        }
        ess = sum(sum(values) for values in self.posteriors.values())
        uncertainty = (
            sum(1.0 / sum(values) for values in self.posteriors.values())
            if self.posteriors
            else 0.0
        )
        return PosteriorSnapshot(
            snapshot_id="post_" + canonical_json_hash(parameters)[:16],
            model_name="beta_bernoulli_group_risk",
            prior={"alpha": self.alpha0, "beta": self.beta0, "group_key": self.group_key},
            posterior_parameters=parameters,
            audit_outcomes=[update.model_dump(mode="json") for update in self.updates],
            feature_version=FEATURE_SCHEMA_VERSION,
            random_state=seed,
            effective_sample_size=ess,
            uncertainty=uncertainty,
        )

    def _group(self, example: MonitorExample) -> str:
        return example.split_group_ids.get(
            self.group_key,
            str(getattr(example, self.group_key, "global")),
        )


class BayesianLogisticRiskState:
    """Small online approximate Bayesian logistic state with diagonal precision."""

    def __init__(self, feature_names: list[str], *, prior_precision: float = 1.0) -> None:
        self.feature_names = feature_names
        self.weights = [0.0 for _ in feature_names]
        self.precision = [prior_precision for _ in feature_names]
        self.updates: list[BayesianUpdateRecord] = []

    def estimate(self, example: MonitorExample) -> float:
        import math

        logit = sum(
            weight * float(example.observable_feature_payload.get(name, 0.0) or 0.0)
            for weight, name in zip(self.weights, self.feature_names, strict=False)
        )
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logit))))

    def update_from_audit(
        self, example: MonitorExample, *, label_positive: bool | None, audited: bool
    ) -> BayesianUpdateRecord:
        posterior_updated = audited and label_positive is not None
        if posterior_updated:
            pred = self.estimate(example)
            error = (1.0 if label_positive else 0.0) - pred
            for index, name in enumerate(self.feature_names):
                value = float(example.observable_feature_payload.get(name, 0.0) or 0.0)
                self.weights[index] += 0.05 * error * value / self.precision[index]
                self.precision[index] += abs(value)
        record = BayesianUpdateRecord(
            update_id="upd_log_"
            + canonical_json_hash({"example": example.example_id, "n": len(self.updates)})[:12],
            observation_id=example.observation_id,
            audited=audited,
            feedback_available=label_positive is not None,
            posterior_updated=posterior_updated,
            reason="logistic audit feedback" if posterior_updated else "no eligible audit feedback",
        )
        self.updates.append(record)
        return record

    def snapshot(self) -> PosteriorSnapshot:
        params: dict[str, Any] = {
            name: {"weight": weight, "precision": precision}
            for name, weight, precision in zip(
                self.feature_names,
                self.weights,
                self.precision,
                strict=False,
            )
        }
        return PosteriorSnapshot(
            snapshot_id="post_log_" + canonical_json_hash(params)[:16],
            model_name="bayesian_logistic_online",
            prior={"precision": self.precision[0] if self.precision else 0.0},
            posterior_parameters=params,
            audit_outcomes=[update.model_dump(mode="json") for update in self.updates],
            feature_version=FEATURE_SCHEMA_VERSION,
            random_state=0,
            effective_sample_size=float(len(self.updates)),
            uncertainty=sum(1.0 / p for p in self.precision) if self.precision else 0.0,
        )
