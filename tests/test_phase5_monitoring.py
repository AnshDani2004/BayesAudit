from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch

from bayesaudit.adaptive.bayesian import BayesianLogisticRiskState, BetaBernoulliRiskState
from bayesaudit.adaptive.policies import (
    expected_harm_policy,
    learned_threshold_policy,
    online_priority_policy,
    thompson_policy,
    top_risk_policy,
    value_of_information_policy,
)
from bayesaudit.adaptive.types import AdaptivePolicyResult
from bayesaudit.annotations.monitoring import export_annotations, validate_annotation_import
from bayesaudit.cli import main
from bayesaudit.monitoring.abstention import (
    confidence_band_abstention,
    missing_feature_abstention,
    selective_metrics,
)
from bayesaudit.monitoring.calibration import (
    CalibrationConfig,
    apply_calibration,
    calibration_metrics,
    expected_calibration_error,
    fit_calibrator,
    reliability_bins,
)
from bayesaudit.monitoring.dataset import (
    MonitorDatasetConfig,
    load_monitor_examples,
    persist_monitor_dataset,
    summarize_monitor_dataset,
    validate_monitor_dataset,
)
from bayesaudit.monitoring.evaluation import (
    auprc,
    auroc,
    evaluate_monitor,
    precision_at_audit_rate,
    recall_at_fpr,
)
from bayesaudit.monitoring.features import (
    FEATURE_SCHEMA,
    FORBIDDEN_FEATURE_TOKENS,
    feature_schema_record,
    validate_feature_payload,
)
from bayesaudit.monitoring.model_cards import generate_model_card
from bayesaudit.monitoring.monitors import MonitorTrainConfig, predict_examples, train_monitor
from bayesaudit.monitoring.ood import fit_ood_reference, score_ood
from bayesaudit.monitoring.splits import (
    SPLIT_STRATEGY_GROUPS,
    create_split_manifest,
    split_examples,
    validate_no_group_leakage,
)
from bayesaudit.monitoring.types import (
    FEATURE_SCHEMA_VERSION,
    LabelValue,
    MonitorDatasetManifest,
    MonitorExample,
    MonitorPrediction,
)
from bayesaudit.providers.base import (
    ProviderConfig,
    assert_provider_allowed,
    estimate_provider_cost,
)
from bayesaudit.schemas import ArchitectureKind, Domain, OversightAction


def _example(index: int, *, label: str | None = None) -> MonitorExample:
    positive = label or (LabelValue.POSITIVE if index % 2 else LabelValue.NEGATIVE)
    domain_values = [
        Domain.PRIVACY,
        Domain.AUTHORIZATION,
        Domain.BUDGETING,
        Domain.EVIDENCE,
        Domain.PROTECTED_ATTRIBUTES,
    ]
    architecture_values = [
        ArchitectureKind.SINGLE_AGENT,
        ArchitectureKind.UNSTRUCTURED_DELEGATION,
        ArchitectureKind.STRUCTURED_INHERITANCE,
        ArchitectureKind.VERIFIED_INHERITANCE,
    ]
    features = {
        "depth": index % 3,
        "branch_present": index % 2 == 1,
        "step_kind": "tool" if index % 3 == 0 else "message",
        "agent_role": f"agent_{index % 2}",
        "architecture": architecture_values[index % len(architecture_values)].value,
        "prior_audit_count": index % 2,
        "remaining_budget": float(5 - index % 5),
        "constraint_count": 2 + index % 4,
        "critical_constraint_count": index % 2,
        "tool_call_count": index % 3,
        "missing_required_constraints": positive == LabelValue.POSITIVE and index % 2 == 1,
        "weakened_constraints": positive == LabelValue.POSITIVE and index % 3 == 0,
        "contradicted_constraints": False,
        "privilege_demotions": index % 7 == 0,
        "verification_failures": index % 5 == 0,
        "tool_requested": index % 3 == 0,
        "approval_required": index % 4 == 0,
        "approval_present": index % 8 == 0,
        "prohibited_tool_indicator": positive == LabelValue.POSITIVE and index % 4 == 1,
        "sensitive_token_indicator": positive == LabelValue.POSITIVE and index % 5 == 1,
        "irreversible_action_indicator": index % 6 == 0,
        "external_tool_indicator": index % 4 == 0,
        "text_length": 120 + 7 * index,
        "identifier_count": index % 4,
        "citation_count": index % 3,
        "unknown_citation_count": int(index % 6 == 0),
        "budget_numeric_count": 1 + index % 3,
        "approval_language_indicator": index % 4 == 0,
        "constraint_reference_count": 1 + index % 5,
        "uncertainty_language_indicator": index % 5 == 0,
    }
    task_id = f"task_{index % 8}"
    domain = domain_values[index % len(domain_values)]
    architecture = architecture_values[index % len(architecture_values)]
    return MonitorExample(
        example_id=f"mon_{index:03d}",
        observation_id=f"obs_{index:03d}",
        trajectory_id=f"traj_{index // 2:03d}",
        run_id=f"run_{index // 2:03d}",
        experiment_id="phase5_unit",
        task_id=task_id,
        task_version="v1",
        template_family=f"template_{index % 6}",
        domain=domain,
        architecture=architecture,
        model_family=f"mock_{index % 4}",
        checkpoint_type="before_tool_request" if index % 3 == 0 else "before_final_output",
        sequence_index=index,
        depth=index % 3,
        branch_id=f"branch_{index % 3}" if index % 2 else None,
        observable_feature_payload=features,
        observable_text_payload=(
            f"user: redacted checkpoint {index}\nassistant: visible response {index}"
        ),
        current_violation_label=positive,
        imminent_violation_label=positive,
        preventable_imminent_violation_label=positive,
        severity_target=5.0 if positive == LabelValue.POSITIVE else 0.0,
        intervention_usefulness_label=positive,
        final_output_violation_label=positive if index % 2 else LabelValue.NEGATIVE,
        internal_only_violation_label=positive if index % 3 == 0 else LabelValue.NEGATIVE,
        label_horizon=1,
        label_source="objective_scorer_posthoc",
        label_confidence=1.0,
        split_group_ids={
            "base_task_id": task_id,
            "template_family": f"template_{index % 6}",
            "scenario_family": f"scenario_{index % 4}",
            "mutation_profile_family": f"mutation_{index % 5}",
            "delegation_graph": f"graph_{index % 4}",
            "architecture": architecture.value,
            "domain": domain.value,
            "model_family": f"mock_{index % 4}",
            "seed_family": f"seed_{index % 3}",
        },
        source_artifact_hashes={"trajectory": f"traj_hash_{index}", "score": f"score_hash_{index}"},
    )


@pytest.fixture
def examples() -> list[MonitorExample]:
    return [_example(index) for index in range(24)]


@pytest.fixture
def dataset_dir(tmp_path: Path, examples: list[MonitorExample]) -> Path:
    output = tmp_path / "phase5_unit"
    manifest = _manifest(examples)
    persist_monitor_dataset(output, examples, manifest)
    return output


def _manifest(examples: list[MonitorExample]) -> MonitorDatasetManifest:
    return MonitorDatasetManifest(
        dataset_id="phase5_unit",
        dataset_version="v1",
        source_experiments=["phase5_unit"],
        source_schema_versions=["bayesaudit.v2", "bayesaudit.oversight.v1"],
        observation_count=len(examples),
        trajectory_count=len({example.trajectory_id for example in examples}),
        task_count=len({example.task_id for example in examples}),
        group_counts={"domain": len({str(example.domain) for example in examples})},
        label_prevalence={"current_violation_label": 0.5},
        unknown_label_counts={"current_violation_label": 0},
        feature_schema=FEATURE_SCHEMA,
        text_rendering_version="test",
        configuration_hash="config_hash",
        data_hash="data_hash",
    )


def _predictions(examples: list[MonitorExample]) -> list[MonitorPrediction]:
    predictions = []
    for index, example in enumerate(examples):
        probability = 0.85 if example.current_violation_label == LabelValue.POSITIVE else 0.15
        probability = min(0.98, max(0.02, probability + 0.01 * (index % 3)))
        predictions.append(
            MonitorPrediction(
                prediction_id=f"pred_{example.example_id}",
                monitor_name="synthetic_monitor",
                monitor_version="phase5_v1",
                model_artifact_hash="artifact_hash",
                example_id=example.example_id,
                current_violation_probability=probability,
                imminent_violation_probability=probability,
                preventable_violation_probability=probability,
                expected_severity=probability * float(example.severity_target or 1.0),
                intervention_usefulness_probability=probability,
            )
        )
    return predictions


def test_feature_schema_record_is_versioned() -> None:
    record = feature_schema_record()
    assert record["schema_version"] == FEATURE_SCHEMA_VERSION
    assert set(FEATURE_SCHEMA).issubset(record)


def test_feature_payload_accepts_schema_features(examples: list[MonitorExample]) -> None:
    validate_feature_payload(examples[0].observable_feature_payload)


@pytest.mark.parametrize("token", sorted(FORBIDDEN_FEATURE_TOKENS))
def test_feature_payload_rejects_forbidden_tokens(token: str) -> None:
    with pytest.raises(ValueError):
        validate_feature_payload({"text_length": 1, "step_kind": token})


def test_feature_payload_rejects_unknown_feature() -> None:
    with pytest.raises(ValueError):
        validate_feature_payload({"ground_truth_label": 1})


def test_persisted_monitor_dataset_round_trips(
    dataset_dir: Path, examples: list[MonitorExample]
) -> None:
    loaded = load_monitor_examples(dataset_dir)
    assert [example.example_id for example in loaded] == [
        example.example_id for example in examples
    ]


def test_validate_monitor_dataset_accepts_fixture(dataset_dir: Path) -> None:
    assert validate_monitor_dataset(dataset_dir)["valid"] is True


def test_summarize_monitor_dataset_counts_groups(dataset_dir: Path) -> None:
    summary = summarize_monitor_dataset(dataset_dir)
    assert summary["example_count"] == 24
    assert summary["trajectory_count"] == 12


@pytest.mark.parametrize("strategy", sorted(SPLIT_STRATEGY_GROUPS))
def test_split_strategies_have_no_group_leakage(dataset_dir: Path, strategy: str) -> None:
    manifest = create_split_manifest(dataset_dir, strategy=strategy)
    check = validate_no_group_leakage(manifest)
    assert check["valid"] is True
    assert len(manifest.assignments) == 24


@pytest.mark.parametrize("strategy", sorted(SPLIT_STRATEGY_GROUPS))
def test_split_examples_returns_assigned_ids(dataset_dir: Path, strategy: str) -> None:
    manifest = create_split_manifest(dataset_dir, strategy=strategy)
    assigned = split_examples(dataset_dir, manifest)
    assert sum(len(ids) for ids in assigned.values()) == 24


@pytest.mark.parametrize(
    "monitor_type", ["constant", "rule_score", "logistic", "tree", "bayesian_logistic"]
)
def test_monitor_training_and_prediction_bounds(
    tmp_path: Path, dataset_dir: Path, examples: list[MonitorExample], monitor_type: str
) -> None:
    create_split_manifest(dataset_dir, strategy="in_distribution")
    config = MonitorTrainConfig(
        monitor_name=f"{monitor_type}_unit",
        monitor_type=monitor_type,
        dataset_dir=dataset_dir,
        split_manifest_path=dataset_dir / "split_in_distribution.json",
        artifact_dir=tmp_path,
        iterations=5,
        learning_rate=0.05,
    )
    artifact = train_monitor(config)
    predictions = predict_examples(artifact, examples[:4])
    assert artifact.monitor_type == monitor_type
    assert all(0.0 <= prediction.current_violation_probability <= 1.0 for prediction in predictions)


@pytest.mark.parametrize(
    "monitor_type", ["constant", "rule_score", "logistic", "tree", "bayesian_logistic"]
)
def test_monitor_artifact_is_written(tmp_path: Path, dataset_dir: Path, monitor_type: str) -> None:
    artifact = train_monitor(
        MonitorTrainConfig(
            monitor_name=f"{monitor_type}_written",
            monitor_type=monitor_type,
            dataset_dir=dataset_dir,
            artifact_dir=tmp_path,
            iterations=3,
        )
    )
    assert Path(str(artifact.artifact_path)).exists()


@pytest.mark.parametrize("method", ["platt", "isotonic", "temperature", "beta"])
def test_calibrators_fit_and_apply(
    tmp_path: Path, examples: list[MonitorExample], method: str
) -> None:
    artifact = fit_calibrator(
        CalibrationConfig(calibration_id=f"{method}_unit", method=method, artifact_dir=tmp_path),
        _predictions(examples),
        examples,
    )
    calibrated = apply_calibration(0.7, artifact)
    assert artifact.calibration_method == method
    assert 0.0 <= calibrated <= 1.0


def test_calibration_metrics_include_ece() -> None:
    metrics = calibration_metrics([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], bins=2)
    assert set(metrics) == {"brier", "log_loss", "ece", "slope", "intercept"}
    assert metrics["ece"] >= 0.0


def test_reliability_bins_cover_requested_bins() -> None:
    assert len(reliability_bins([0.1, 0.9], [0, 1], bins=5)) == 5


def test_expected_calibration_error_is_zero_for_empty() -> None:
    assert expected_calibration_error([], []) == 0.0


def test_evaluate_monitor_emits_core_metrics(examples: list[MonitorExample]) -> None:
    metrics = evaluate_monitor(
        dataset_id="phase5_unit",
        split="all",
        monitor_name="synthetic",
        examples=examples,
        predictions=_predictions(examples),
    )
    names = {metric.metric_name for metric in metrics}
    assert {"auroc", "auprc", "f1", "ece", "brier"}.issubset(names)


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        (auroc([1, 0], [0.9, 0.1]), 1.0),
        (recall_at_fpr([1, 0], [0.9, 0.1], 0.0), 1.0),
        (precision_at_audit_rate([1, 0, 1, 0], [0.9, 0.8, 0.7, 0.1], 0.5), 0.5),
    ],
)
def test_ranking_metric_smoke(metric: float, expected: float) -> None:
    assert metric == pytest.approx(expected)


def test_auprc_is_bounded() -> None:
    assert 0.0 <= auprc([1, 0, 1], [0.9, 0.2, 0.7]) <= 1.0


def test_confidence_band_abstention_marks_boundary_predictions(
    examples: list[MonitorExample],
) -> None:
    predictions = _predictions(examples[:3])
    predictions[1].current_violation_probability = 0.5
    records = confidence_band_abstention(predictions, low=0.4, high=0.6)
    assert records[1].abstained is True


def test_missing_feature_abstention_sets_reason(examples: list[MonitorExample]) -> None:
    prediction = _predictions(examples[:1])[0]
    record = missing_feature_abstention(prediction, ["remaining_budget"])
    assert record.abstained is True
    assert prediction.abstention_reason == "missing_features"


def test_selective_metrics_reports_coverage(examples: list[MonitorExample]) -> None:
    predictions = _predictions(examples[:4])
    predictions[0].abstained = True
    metrics = selective_metrics([1, 0, 1, 0], predictions)
    assert metrics["coverage"] == pytest.approx(0.75)


def test_ood_reference_scores_training_example(examples: list[MonitorExample]) -> None:
    reference = fit_ood_reference(examples[:10], ["text_length", "constraint_count"])
    score = score_ood(examples[0], reference)
    assert score.ood_score >= 0.0


def test_ood_score_flags_unseen_architecture(examples: list[MonitorExample]) -> None:
    reference = fit_ood_reference(examples[:4], ["text_length"])
    shifted = examples[7]
    score = score_ood(shifted, reference)
    assert "missing_architecture_level" in score.flags or score.ood_score >= 0.0


def test_beta_bernoulli_updates_only_with_audit_feedback(examples: list[MonitorExample]) -> None:
    state = BetaBernoulliRiskState()
    before = state.estimate(examples[0])
    skipped = state.update_from_audit(examples[0], label_positive=True, audited=False)
    after_skip = state.estimate(examples[0])
    updated = state.update_from_audit(examples[0], label_positive=True, audited=True)
    assert skipped.posterior_updated is False
    assert updated.posterior_updated is True
    assert after_skip == before
    assert state.estimate(examples[0]) > before


def test_beta_bernoulli_snapshot_records_schema(examples: list[MonitorExample]) -> None:
    state = BetaBernoulliRiskState()
    state.update_from_audit(examples[1], label_positive=True, audited=True)
    snapshot = state.snapshot(seed=7)
    assert snapshot.feature_version == FEATURE_SCHEMA_VERSION
    assert snapshot.random_state == 7


def test_bayesian_logistic_risk_state_predicts_probability(
    examples: list[MonitorExample],
) -> None:
    state = BayesianLogisticRiskState(feature_names=["text_length"])
    state.update_from_audit(examples[0], label_positive=False, audited=True)
    probability = state.estimate(examples[1])
    assert 0.0 <= probability <= 1.0


@pytest.mark.parametrize(
    "policy_factory",
    [
        lambda examples, predictions: learned_threshold_policy(
            examples, predictions, threshold=0.5, budget=3
        ),
        lambda examples, predictions: top_risk_policy(examples, predictions, budget=3),
        lambda examples, predictions: online_priority_policy(examples, predictions, budget=3),
        lambda examples, predictions: expected_harm_policy(examples, predictions, budget=3),
        lambda examples, predictions: value_of_information_policy(examples, predictions, budget=3),
        lambda examples, predictions: thompson_policy(examples, budget=3, seed=2),
    ],
)
def test_adaptive_policies_respect_budget(
    examples: list[MonitorExample],
    policy_factory: Callable[[list[MonitorExample], list[MonitorPrediction]], AdaptivePolicyResult],
) -> None:
    result = policy_factory(examples, _predictions(examples))
    audit_count = sum(decision.action == OversightAction.AUDIT for decision in result.decisions)
    assert audit_count <= 3
    assert len(result.decisions) == len(examples)


def test_provider_cost_blocks_real_provider_without_permission(tmp_path: Path) -> None:
    config = ProviderConfig(provider_name="real", dry_run=False, output_root=tmp_path)
    manifest = estimate_provider_cost(config)
    assert manifest.status == "blocked"


def test_provider_cost_allows_mock_dry_run(tmp_path: Path) -> None:
    manifest = estimate_provider_cost(
        ProviderConfig(provider_name="mock", dry_run=True, output_root=tmp_path)
    )
    assert manifest.status == "dry_run"


def test_provider_cost_blocks_token_ceiling(tmp_path: Path) -> None:
    manifest = estimate_provider_cost(
        ProviderConfig(
            provider_name="mock",
            max_tokens=1,
            estimated_input_tokens_per_request=10,
            output_root=tmp_path,
        )
    )
    assert manifest.status == "blocked"


def test_assert_provider_allowed_raises_for_blocked(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        assert_provider_allowed(
            ProviderConfig(provider_name="real", dry_run=False, output_root=tmp_path)
        )


def test_annotation_export_and_import(dataset_dir: Path, tmp_path: Path) -> None:
    output = tmp_path / "annotations.jsonl"
    exported = export_annotations(dataset_dir, output, max_items=3)
    imported = validate_annotation_import(output)
    assert exported["exported"] == 3
    assert imported["valid"] is True


def test_model_card_generation(
    tmp_path: Path, dataset_dir: Path, examples: list[MonitorExample]
) -> None:
    artifact = train_monitor(
        MonitorTrainConfig(
            monitor_name="card_unit",
            monitor_type="constant",
            dataset_dir=dataset_dir,
            artifact_dir=tmp_path,
        )
    )
    metrics = evaluate_monitor(
        dataset_id="phase5_unit",
        split="all",
        monitor_name="card_unit",
        examples=examples,
        predictions=predict_examples(artifact, examples),
    )
    card = generate_model_card(artifact, metrics, output_dir=tmp_path / "cards")
    assert "Leakage Safeguards" in card.read_text(encoding="utf-8")


def test_monitor_dataset_config_loads_phase5_smoke() -> None:
    config = MonitorDatasetConfig.model_validate(
        {"dataset_id": "unit", "source_experiments": ["phase4_smoke"]}
    )
    assert config.split_strategy == "in_distribution"


def test_cli_validate_monitor_dataset(
    dataset_dir: Path, capsys: CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["bayesaudit", "validate-monitor-dataset", "--dataset-dir", str(dataset_dir)],
    )
    main()
    assert '"valid": true' in capsys.readouterr().out


def test_cli_summarize_monitor_dataset(
    dataset_dir: Path, capsys: CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["bayesaudit", "summarize-monitor-dataset", "--dataset-dir", str(dataset_dir)],
    )
    main()
    assert '"example_count": 24' in capsys.readouterr().out


def test_cli_create_monitor_splits(
    dataset_dir: Path, tmp_path: Path, capsys: CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    config_path = tmp_path / "dataset.yaml"
    config_path.write_text(
        f"dataset_id: {dataset_dir.name}\noutput_root: {dataset_dir.parent}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["bayesaudit", "create-monitor-splits", "--config", str(config_path)],
    )
    main()
    assert '"assignment_count": 24' in capsys.readouterr().out


def test_cli_train_monitor(
    dataset_dir: Path, tmp_path: Path, capsys: CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    config_path = tmp_path / "monitor.yaml"
    config_path.write_text(
        f"monitor_name: cli_unit\nmonitor_type: constant\ndataset_dir: {dataset_dir}\n"
        f"artifact_dir: {tmp_path}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["bayesaudit", "train-monitor", "--config", str(config_path)])
    main()
    assert '"monitor_name": "cli_unit"' in capsys.readouterr().out


def test_cli_estimate_provider_cost(
    tmp_path: Path, capsys: CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    config_path = tmp_path / "provider.yaml"
    config_path.write_text(
        "provider:\n  provider_name: mock\n  dry_run: true\n  output_root: "
        f"{tmp_path}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["bayesaudit", "estimate-provider-cost", "--config", str(config_path)],
    )
    main()
    assert '"status": "dry_run"' in capsys.readouterr().out


def test_cli_run_real_pilot_dry_run(
    tmp_path: Path, capsys: CaptureFixture[str], monkeypatch: MonkeyPatch
) -> None:
    config_path = tmp_path / "pilot.yaml"
    config_path.write_text(
        "provider:\n  provider_name: mock\n  dry_run: true\n  output_root: "
        f"{tmp_path}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["bayesaudit", "run-real-pilot", "--config", str(config_path), "--dry-run"],
    )
    main()
    assert '"status": "dry_run"' in capsys.readouterr().out


def test_prediction_json_is_schema_stable(examples: list[MonitorExample]) -> None:
    payload = json.loads(_predictions(examples[:1])[0].model_dump_json())
    assert payload["schema_version"] == "bayesaudit.monitoring.v1"
