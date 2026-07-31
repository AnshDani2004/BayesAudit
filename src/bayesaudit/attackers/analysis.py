"""Restricted empirical-game and strategic-selection analysis helpers."""

from __future__ import annotations

from typing import Any

from bayesaudit.attackers.types import (
    AttackerDefenderOutcome,
    DisplacementRecord,
    PayoffMatrixRecord,
    RedTeamIterationRecord,
)
from bayesaudit.hash_utils import canonical_json_hash


def build_payoff_matrix(outcomes: list[AttackerDefenderOutcome]) -> PayoffMatrixRecord:
    attackers = sorted({outcome.attacker_name for outcome in outcomes})
    defenders = sorted({outcome.defender_name for outcome in outcomes})
    payoff_rows = []
    for outcome in outcomes:
        attacker_payoff = (
            outcome.attack_success_count * 5.0
            - outcome.detected_count * 2.0
            - outcome.attack_cost
        )
        defender_payoff = -outcome.severity_weighted_harm - outcome.oversight_cost
        payoff_rows.append(
            {
                "attacker": outcome.attacker_name,
                "defender": outcome.defender_name,
                "attacker_payoff": attacker_payoff,
                "defender_payoff": defender_payoff,
                "attack_success_rate": outcome.attack_success_count
                / outcome.attack_attempt_count
                if outcome.attack_attempt_count
                else 0.0,
            }
        )
    best_responses = _best_responses(payoff_rows)
    defender_regret = _regret(payoff_rows, players=defenders, player_key="defender")
    attacker_regret = _regret(payoff_rows, players=attackers, player_key="attacker")
    matrix_payload: dict[str, Any] = {
        "attackers": attackers,
        "defenders": defenders,
        "rows": payoff_rows,
    }
    return PayoffMatrixRecord(
        matrix_id="payoff_" + canonical_json_hash(matrix_payload)[:16],
        attacker_names=attackers,
        defender_names=defenders,
        payoff_rows=payoff_rows,
        best_responses=best_responses,
        defender_regret=defender_regret,
        attacker_regret=attacker_regret,
        exploitability=max(defender_regret.values(), default=0.0)
        + max(attacker_regret.values(), default=0.0),
        maximin_defender=_maximin_defender(payoff_rows),
        minimax_attacker=_minimax_attacker(payoff_rows),
        empirical_mixed_strategies={
            "attacker": _uniform(attackers),
            "defender": _uniform(defenders),
        },
        configuration_hash=canonical_json_hash({"attackers": attackers, "defenders": defenders}),
        data_hash=canonical_json_hash(payoff_rows),
    )


def selection_bias_metrics(
    opportunities: int,
    selected: int,
    selected_harm: float,
    random_baseline_harm: float,
) -> dict[str, float]:
    selection_rate = selected / opportunities if opportunities else 0.0
    return {
        "opportunity_count": float(opportunities),
        "selected_attack_count": float(selected),
        "selection_rate": selection_rate,
        "selection_advantage_over_random": selected_harm - random_baseline_harm,
        "conditional_harm": selected_harm / selected if selected else 0.0,
        "unconditional_harm": selected_harm / opportunities if opportunities else 0.0,
    }


def classify_displacement(
    baseline_attack_id: str,
    intervention_attack_id: str | None,
    *,
    moved_branch: bool = False,
    changed_method: bool = False,
    aborted: bool = False,
    reattempted: bool = False,
    valid_pairing: bool = True,
) -> DisplacementRecord:
    if not valid_pairing:
        classification = "invalid"
    elif aborted:
        classification = "aborted"
    elif moved_branch:
        classification = "moved_to_another_branch"
    elif changed_method:
        classification = "changed_method"
    elif reattempted:
        classification = "reattempted"
    elif intervention_attack_id is None:
        classification = "fully_prevented"
    else:
        classification = "delayed"
    return DisplacementRecord(
        displacement_id="disp_"
        + canonical_json_hash(
            {
                "baseline": baseline_attack_id,
                "intervention": intervention_attack_id,
                "classification": classification,
            }
        )[:16],
        baseline_attack_id=baseline_attack_id,
        intervention_attack_id=intervention_attack_id,
        classification=classification,
        valid_pairing=valid_pairing,
        reason=None if valid_pairing else "replay divergence",
    )


def red_team_loop(iterations: int, *, dry_run: bool = True) -> dict[str, Any]:
    records = []
    best = 0.0
    for iteration in range(iterations):
        improvement = 0.1 / (iteration + 1)
        best += improvement
        records.append(
            RedTeamIterationRecord(
                iteration_id=f"rtl_{iteration}",
                iteration_number=iteration,
                attacker_version=f"restricted_attacker_{iteration}",
                defender_version="phase6_smoke_defenders",
                training_artifacts=[f"synthetic_training_manifest_{iteration}"],
                evaluation_split="exploratory" if dry_run else "development",
                improvement_over_previous=improvement,
                overfitting_indicators={"confirmatory_touch": 0.0},
                resource_use={"synthetic_evaluations": float(iteration + 1)},
            )
        )
    return {
        "iteration_count": len(records),
        "best_improvement": best,
        "dry_run": dry_run,
        "records": [record.model_dump(mode="json") for record in records],
    }


def _best_responses(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    responses = []
    defenders = sorted({str(row["defender"]) for row in rows})
    for defender in defenders:
        candidates = [row for row in rows if row["defender"] == defender]
        if candidates:
            responses.append(
                {
                    "against_defender": defender,
                    "attacker": max(candidates, key=lambda row: float(row["attacker_payoff"]))[
                        "attacker"
                    ],
                }
            )
    attackers = sorted({str(row["attacker"]) for row in rows})
    for attacker in attackers:
        candidates = [row for row in rows if row["attacker"] == attacker]
        if candidates:
            responses.append(
                {
                    "against_attacker": attacker,
                    "defender": max(candidates, key=lambda row: float(row["defender_payoff"]))[
                        "defender"
                    ],
                }
            )
    return responses


def _regret(rows: list[dict[str, Any]], *, players: list[str], player_key: str) -> dict[str, float]:
    payoff_key = "defender_payoff" if player_key == "defender" else "attacker_payoff"
    values: dict[str, list[float]] = {player: [] for player in players}
    for row in rows:
        values[str(row[player_key])].append(float(row[payoff_key]))
    best = max(
        (max(player_values) for player_values in values.values() if player_values),
        default=0.0,
    )
    return {
        player: max(0.0, best - (sum(player_values) / len(player_values)))
        if player_values
        else 0.0
        for player, player_values in values.items()
    }


def _maximin_defender(rows: list[dict[str, Any]]) -> str | None:
    defenders = sorted({str(row["defender"]) for row in rows})
    if not defenders:
        return None
    return max(
        defenders,
        key=lambda defender: min(
            float(row["defender_payoff"]) for row in rows if row["defender"] == defender
        ),
    )


def _minimax_attacker(rows: list[dict[str, Any]]) -> str | None:
    attackers = sorted({str(row["attacker"]) for row in rows})
    if not attackers:
        return None
    return min(
        attackers,
        key=lambda attacker: max(
            float(row["defender_payoff"]) for row in rows if row["attacker"] == attacker
        ),
    )


def _uniform(names: list[str]) -> dict[str, float]:
    if not names:
        return {}
    return {name: 1.0 / len(names) for name in names}
