"""Command-line entry points for benchmark utilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bayesaudit.benchmark.io import load_tasks


def generate_tasks_main() -> None:
    """Validate existing task fixtures and print a compact JSON summary.

    Full parameterized generation is intentionally deferred to Phase 2.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("scenarios"))
    args = parser.parse_args()

    tasks = load_tasks(args.root)
    summary = {
        "task_count": len(tasks),
        "domains": sorted({task.domain for task in tasks}),
        "phase": "phase_2_fixture_validation",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


def validate_scenarios_main() -> None:
    generate_tasks_main()
