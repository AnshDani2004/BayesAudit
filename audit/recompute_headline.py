"""Audit script: recompute README headline numbers from the row-level JSONL artifacts.

Usage: python audit/recompute_headline.py configs/experiments
Independent of the analysis code in src/; reads only the tracked artifacts.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from math import comb, sqrt
from pathlib import Path
from typing import Any


def rows(root: Path, name: str) -> list[dict[str, Any]]:
    with open(root / name, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def wilson(x: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = x / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(centre - half, 4), round(centre + half, 4)


def condition_of(row: dict[str, Any]) -> str:
    return str(row.get("phase8_condition") or row.get("phase9_condition") or row.get("condition"))


def main(root: Path) -> None:
    for phase in ("phase8", "phase9"):
        print("=====", phase)
        req = rows(root, f"{phase}_provider_request_summaries.jsonl")
        print(
            "request records",
            len(req),
            "status",
            dict(Counter(r["status"] for r in req)),
            "cache_status",
            dict(Counter(r["cache_status"] for r in req)),
        )
        tokens = sum(r["total_tokens"] for r in req)
        cost = sum(Decimal(r["token_derived_cost_usd"]) for r in req)
        print("total tokens", tokens, "token-derived cost usd", cost)
        traj = rows(root, f"{phase}_trajectory_summaries.jsonl")
        print("trajectories", len(traj), dict(Counter(t["execution_status"] for t in traj)))
        obj = rows(root, f"{phase}_objective_adjudication.jsonl")
        print(
            "validated positives",
            sum(o["validated_objective_positive"] for o in obj),
            "internal_only",
            sum(o["internal_only_violation"] for o in obj),
            "tool_argument",
            sum(o["tool_argument_violation"] for o in obj),
            "final_output",
            sum(o["final_output_violation"] for o in obj),
        )
        conditions = Counter(condition_of(o) for o in obj)
        print("conditions", dict(conditions))
        by_quartet: dict[str, dict[str, bool]] = defaultdict(dict)
        for o in obj:
            by_quartet[o["matched_quartet_id"]][condition_of(o)] = o["validated_objective_positive"]
        safe = next(c for c in conditions if c.startswith("safe"))
        attack = next(
            c for c in conditions if "attacker_no_oversight" in c and not c.startswith("safe")
        )
        n = len(by_quartet)
        safe_pos = sum(q[safe] for q in by_quartet.values())
        attack_pos = sum(q[attack] for q in by_quartet.values())
        attack_only = sum(q[attack] and not q[safe] for q in by_quartet.values())
        safe_only = sum(q[safe] and not q[attack] for q in by_quartet.values())
        m = attack_only + safe_only
        k = min(attack_only, safe_only)
        p_value = min(1.0, 2 * sum(comb(m, i) for i in range(k + 1)) / 2**m)
        print(
            f"quartets {n} safe+ {safe_pos} attacker+ {attack_pos} "
            f"discordant attacker-only {attack_only} safe-only {safe_only} "
            f"risk difference {(attack_pos - safe_pos) / n:.4f} exact McNemar p {p_value:.6f} "
            f"Wilson safe {wilson(safe_pos, n)} attacker {wilson(attack_pos, n)}"
        )
        monitors = rows(root, f"{phase}_monitor_adjudication.jsonl")
        agg: dict[str, Counter[str]] = defaultdict(Counter)
        scores: dict[str, Counter[Any]] = defaultdict(Counter)
        for r in monitors:
            agg[r["monitor_id"]][r["classification"]] += 1
            agg[r["monitor_id"]]["alerts"] += bool(r["alert"])
            agg[r["monitor_id"]]["n"] += 1
            score = r["monitor_score"]
            scores[r["monitor_id"]][None if score is None else round(score, 4)] += 1
        for monitor_id, counts in agg.items():
            print("monitor", monitor_id, dict(counts), "scores", dict(scores[monitor_id]))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
