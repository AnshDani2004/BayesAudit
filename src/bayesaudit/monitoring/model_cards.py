"""Monitor model-card generation."""

from __future__ import annotations

from pathlib import Path

from bayesaudit.monitoring.types import MonitorArtifact, MonitorMetricRecord


def generate_model_card(
    artifact: MonitorArtifact,
    metrics: list[MonitorMetricRecord],
    *,
    output_dir: Path = Path("docs/monitor_model_cards"),
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{artifact.monitor_name}.md"
    lines = [
        f"# Monitor Model Card: {artifact.monitor_name}",
        "",
        "## Intended Use",
        "Estimate checkpoint-level safety risk from redacted BayesAudit observations.",
        "",
        "## Non-Intended Use",
        "Do not use as a standalone deployed safety decision-maker or as evidence "
        "of real-model behavior.",
        "",
        "## Training Dataset",
        f"Dataset hash: `{artifact.training_dataset_hash}`",
        f"Split manifest hash: `{artifact.split_manifest_hash}`",
        "",
        "## Feature Set",
        ", ".join(artifact.feature_names),
        "",
        "## Label Definitions",
        f"Target: `{artifact.target}` using temporally defined Phase 5 monitor labels.",
        "",
        "## Hyperparameters",
        f"`{artifact.hyperparameters}`",
        "",
        "## Calibration",
        f"`{artifact.calibration}`",
        "",
        "## Performance",
    ]
    for metric in metrics:
        lines.append(f"- {metric.split}/{metric.metric_name}: {metric.value:.4f}")
    lines.extend(
        [
            "",
            "## Robustness",
            "Evaluate with grouped holdout manifests before confirmatory claims.",
            "",
            "## Known Failure Modes",
            "Synthetic-only training, small sample instability, sparse held-out groups, "
            "and non-causal features.",
            "",
            "## Leakage Safeguards",
            "Features are extracted from enumerated redacted observation fields only.",
            "",
            "## Cost And Latency",
            "Local deterministic baseline; no provider calls.",
            "",
            "## Version",
            f"Artifact hash: `{artifact.artifact_hash}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
