#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Guanlan release gate =="
echo "1/13 pre-release status"
scripts/pre_release_status.sh

echo "2/13 ruff"
uv run ruff check $(git ls-files '*.py')

echo "3/13 pytest"
uv run pytest -q

echo "4/13 foundational guard"
uv run guanlan quality foundational

echo "5/13 coverage guard"
uv run guanlan quality coverage

echo "6/13 regression guard"
uv run guanlan quality regression

echo "7/13 robustness guard"
uv run guanlan quality robustness

echo "8/13 backend fixture guard"
uv run guanlan quality backend-fixtures

echo "9/13 benchmark"
uv run guanlan eval benchmark

echo "10/13 performance guard"
uv run guanlan quality performance

echo "11/13 eval suite"
uv run guanlan eval suite run chinese-web-v1

echo "12/13 build"
uv build

echo "13/13 install smoke + version"
scripts/release_smoke.sh
uv run guanlan version

echo "Guanlan release gate passed."
