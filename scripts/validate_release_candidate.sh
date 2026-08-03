#!/usr/bin/env bash
set -euo pipefail
python -m ruff check .
python -m mypy --no-incremental src tests
python -m pytest -q
python -m compileall -q src tests scripts
python -m bayesaudit.cli validate-phase9
python -m bayesaudit.cli validate-phase10
