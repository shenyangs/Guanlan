#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Guanlan release gate =="
echo "1/14 pre-release status"
scripts/pre_release_status.sh

echo "2/14 ruff"
uv run ruff check $(git ls-files '*.py')

echo "3/14 pytest"
uv run pytest -q

echo "4/14 foundational guard"
uv run guanlan quality foundational

echo "5/14 coverage guard"
uv run guanlan quality coverage

echo "6/14 regression guard"
uv run guanlan quality regression

echo "7/14 robustness guard"
uv run guanlan quality robustness

echo "8/14 backend fixture guard"
uv run guanlan quality backend-fixtures

echo "9/14 benchmark"
uv run guanlan eval benchmark

echo "10/14 performance guard"
uv run guanlan quality performance

echo "11/14 eval suite"
uv run guanlan eval suite run chinese-web-v1

echo "12/14 deterministic reliability baseline"
uv run python scripts/reliability_guard.py

echo "13/14 build"
uv build

echo "14/14 install smoke + version"
scripts/release_smoke.sh
uv run guanlan version

echo "Guanlan release gate passed."
