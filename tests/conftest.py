from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

from bayesaudit.benchmark.io import load_tasks
from bayesaudit.schemas import BenchmarkTask, Domain

ROOT = Path(__file__).resolve().parents[1]
T = TypeVar("T")


def run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def task_for(domain: Domain | str) -> BenchmarkTask:
    for task in load_tasks(ROOT / "scenarios"):
        if task.domain == str(domain):
            return task
    raise AssertionError(f"missing task for {domain}")


def named_task(task_id: str) -> BenchmarkTask:
    for task in load_tasks(ROOT / "scenarios"):
        if task.task_id == task_id:
            return task
    raise AssertionError(f"missing task {task_id}")
