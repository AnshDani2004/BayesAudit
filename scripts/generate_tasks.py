#!/usr/bin/env python
"""Validate benchmark task fixtures.

Parameterized generation starts after seed tasks and scorers are stable.
"""

from bayesaudit.benchmark.cli import generate_tasks_main

if __name__ == "__main__":
    generate_tasks_main()
