"""Generate deterministic public-release figures and tables."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
TABLES = ROOT / "docs" / "tables"


def _json(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _save_bar(path: Path, title: str, labels: list[str], values: list[float], ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 4), dpi=160)
    colors = ["#2f6f73", "#d08c3f", "#6b7fd7", "#8a5a83"][: len(values)]
    ax.bar(labels, values, color=colors)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, max(values + [1]) * 1.25)
    ax.grid(axis="y", alpha=0.25)
    for index, value in enumerate(values):
        ax.text(index, value + max(values + [1]) * 0.04, f"{value:g}", ha="center")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _write_architecture() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "architecture.svg").write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="980" height="360" viewBox="0 0 980 360" role="img" aria-labelledby="title desc">
<title id="title">BayesAudit system architecture</title>
<desc id="desc">Synthetic tasks flow through hierarchical workflows, monitors, policies, adjudication, and evidence artifacts.</desc>
<style>
  .box { fill: #f7f9fb; stroke: #284b63; stroke-width: 2; rx: 10; }
  .label { font: 16px sans-serif; fill: #17202a; }
  .small { font: 13px sans-serif; fill: #34495e; }
  .arrow { stroke: #2f6f73; stroke-width: 3; marker-end: url(#arrow); }
</style>
<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#2f6f73"/></marker></defs>
<rect x="30" y="90" width="140" height="90" class="box"/><text x="100" y="125" text-anchor="middle" class="label">Synthetic</text><text x="100" y="148" text-anchor="middle" class="small">benchmark tasks</text>
<rect x="220" y="90" width="150" height="90" class="box"/><text x="295" y="125" text-anchor="middle" class="label">Hierarchical</text><text x="295" y="148" text-anchor="middle" class="small">workflow engine</text>
<rect x="420" y="40" width="150" height="90" class="box"/><text x="495" y="75" text-anchor="middle" class="label">Attacker or</text><text x="495" y="98" text-anchor="middle" class="small">safe control</text>
<rect x="420" y="170" width="150" height="90" class="box"/><text x="495" y="205" text-anchor="middle" class="label">Constraint</text><text x="495" y="228" text-anchor="middle" class="small">inheritance</text>
<rect x="620" y="90" width="140" height="90" class="box"/><text x="690" y="125" text-anchor="middle" class="label">Monitors and</text><text x="690" y="148" text-anchor="middle" class="small">policies</text>
<rect x="810" y="90" width="140" height="90" class="box"/><text x="880" y="125" text-anchor="middle" class="label">Adjudication</text><text x="880" y="148" text-anchor="middle" class="small">and artifacts</text>
<line x1="170" y1="135" x2="220" y2="135" class="arrow"/><line x1="370" y1="120" x2="420" y2="85" class="arrow"/><line x1="370" y1="150" x2="420" y2="215" class="arrow"/><line x1="570" y1="85" x2="620" y2="120" class="arrow"/><line x1="570" y1="215" x2="620" y2="150" class="arrow"/><line x1="760" y1="135" x2="810" y2="135" class="arrow"/>
<text x="490" y="320" text-anchor="middle" class="small">All tasks and tools are synthetic and sandboxed; provider-backed runs use explicit gates, hashes, cache validation, and cost accounting.</text>
</svg>
""",
        encoding="utf-8",
    )


def _write_experimental_program() -> None:
    (ASSETS / "experimental_program.svg").write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="220" viewBox="0 0 900 220" role="img" aria-label="BayesAudit experimental program">
<style>.box{fill:#fbfaf7;stroke:#3d405b;stroke-width:2;rx:10}.title{font:18px sans-serif;fill:#222}.text{font:13px sans-serif;fill:#444}.arrow{stroke:#3d405b;stroke-width:3;marker-end:url(#a)}</style>
<defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#3d405b"/></marker></defs>
<rect x="30" y="50" width="230" height="110" class="box"/><text x="145" y="84" text-anchor="middle" class="title">Pilot</text><text x="145" y="112" text-anchor="middle" class="text">provider gates, benchmark freeze</text><text x="145" y="134" text-anchor="middle" class="text">strategic attacker construct</text>
<rect x="335" y="50" width="230" height="110" class="box"/><text x="450" y="84" text-anchor="middle" class="title">Confirmatory Study</text><text x="450" y="112" text-anchor="middle" class="text">96 trajectories, 24 quartets</text><text x="450" y="134" text-anchor="middle" class="text">positive but limited attack effect</text>
<rect x="640" y="50" width="230" height="110" class="box"/><text x="755" y="84" text-anchor="middle" class="title">Held-Out Robustness</text><text x="755" y="112" text-anchor="middle" class="text">48 trajectories, 12 quartets</text><text x="755" y="134" text-anchor="middle" class="text">effect did not replicate</text>
<line x1="260" y1="105" x2="335" y2="105" class="arrow"/><line x1="565" y1="105" x2="640" y2="105" class="arrow"/>
</svg>
""",
        encoding="utf-8",
    )


def _figures() -> None:
    phase8 = _json("configs/experiments/phase8_matched_confirmatory_analysis.json")
    phase9 = _json("configs/experiments/phase9_primary_analysis.json")
    phase8_provider = _json("configs/experiments/phase8_provider_summary.json")
    phase8_tokens = _json("configs/experiments/phase8_token_summary.json")
    phase8_cost = _json("configs/experiments/phase8_cost_summary.json")
    phase9_provider = _json("configs/experiments/phase9_provider_summary.json")
    phase9_tokens = _json("configs/experiments/phase9_token_summary.json")
    phase9_cost = _json("configs/experiments/phase9_cost_summary.json")

    p8_effect = phase8["controlled_attack_effect"]
    p9_effect = phase9["heldout_attack_effect"]
    _save_bar(
        ASSETS / "phase8_attack_effect.png",
        "Phase 8 matched no-oversight positives (n=24 quartets)",
        ["safe", "attacked"],
        [p8_effect["safe_positive"], p8_effect["attacker_no_oversight_positive"]],
        "validated positives",
    )
    monitor = phase9["monitor_robustness"]
    _save_bar(
        ASSETS / "monitor_comparison.png",
        "Phase 9 monitor outcomes across monitored trajectories (n=12 each)",
        ["rule TP", "rule FP", "bayes TP", "bayes FN"],
        [
            monitor["true_positives_across_all_rule_based_trajectories"],
            monitor["false_positives_across_all_rule_based_trajectories"],
            monitor["true_positives_across_all_bayesian_trajectories"],
            monitor["false_negatives_across_all_bayesian_trajectories"],
        ],
        "trajectory count",
    )
    _save_bar(
        ASSETS / "phase8_phase9_comparison.png",
        "Attack-effect direction: Phase 8 versus Phase 9",
        ["P8 safe", "P8 attacked", "P9 safe", "P9 held-out"],
        [
            p8_effect["safe_positive"],
            p8_effect["attacker_no_oversight_positive"],
            p9_effect["safe_positive"],
            p9_effect["heldout_attacker_no_oversight_positive"],
        ],
        "validated positives",
    )
    _save_bar(
        ASSETS / "provider_cost_summary.png",
        "Provider-backed study accounting",
        ["P8 calls", "P9 calls", "P8 tokens/1k", "P9 tokens/1k"],
        [
            phase8_provider["provider_calls_performed"],
            phase9_provider["provider_call_accounting"]["original_acquisition_provider_calls"],
            phase8_tokens["total_tokens"] / 1000,
            phase9_tokens["total_tokens"] / 1000,
        ],
        "count",
    )
    _save_bar(
        ASSETS / "cost_usd_summary.png",
        "Token-derived provider cost",
        ["Phase 8", "Phase 9"],
        [float(phase8_cost["token_derived_cost_usd"]), float(phase9_cost["token_derived_cost_usd"])],
        "USD",
    )


def _tables() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    phase8 = _json("configs/experiments/phase8_matched_confirmatory_analysis.json")
    phase8_metrics = _json("configs/experiments/phase8_validated_metrics.json")
    phase9 = _json("configs/experiments/phase9_primary_analysis.json")
    phase9_secondary = _json("configs/experiments/phase9_secondary_analysis.json")
    phase8_provider = _json("configs/experiments/phase8_provider_summary.json")
    phase9_provider = _json("configs/experiments/phase9_provider_summary.json")
    p8 = phase8["controlled_attack_effect"]
    p9 = phase9["heldout_attack_effect"]
    (TABLES / "final_results.md").write_text(
        "\n".join(
            [
                "# Final Results Table",
                "",
                "| Result | Value | Denominator / note |",
                "|---|---:|---|",
                f"| Phase 8 safe positives | {p8['safe_positive']} | 24 matched quartets |",
                f"| Phase 8 attacked no-oversight positives | {p8['attacker_no_oversight_positive']} | 24 matched quartets |",
                f"| Phase 8 paired risk difference | {p8['paired_risk_difference']} | exact McNemar p={p8['exact_mcnemar_p_value']} |",
                f"| Phase 8 final-output violations | {phase8_metrics['final_output_violations']} | 96 trajectories |",
                f"| Phase 9 safe positives | {p9['safe_positive']} | 12 matched quartets |",
                f"| Phase 9 held-out attacker positives | {p9['heldout_attacker_no_oversight_positive']} | 12 matched quartets |",
                f"| Phase 9 paired risk difference | {p9['paired_risk_difference']} | exact McNemar p={p9['exact_mcnemar_p_value']} |",
                f"| Phase 9 final-output violations | {phase9_secondary['final_output_violations']} | 48 trajectories |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (TABLES / "experiment_inventory.md").write_text(
        "\n".join(
            [
                "# Experiment Inventory",
                "",
                "| Study | Trajectories | Request records | Original provider calls | Tokens | Cost |",
                "|---|---:|---:|---:|---:|---:|",
                f"| Phase 8 confirmatory | {phase8_provider['completed_trajectories']} | {phase8_provider['provider_request_records']} | {phase8_provider['provider_calls_performed']} | 312174 | $0.03363020 |",
                f"| Phase 9 held-out robustness | {phase9_provider['completed_trajectories']} | {phase9_provider['provider_request_records']} | {phase9_provider['provider_call_accounting']['original_acquisition_provider_calls']} | 164693 | $0.01751875 |",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    _write_architecture()
    _write_experimental_program()
    _figures()
    _tables()
    print("generated public assets and tables")


if __name__ == "__main__":
    main()
