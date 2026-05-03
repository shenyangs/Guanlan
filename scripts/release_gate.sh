#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Guanlan release gate =="
echo "1/9 ruff"
uv run ruff check $(git ls-files '*.py')

echo "2/9 pytest"
uv run pytest -q

echo "3/9 foundational guard"
uv run guanlan quality foundational

echo "4/9 coverage guard"
uv run guanlan quality coverage

echo "5/9 regression guard"
uv run guanlan quality regression

echo "6/9 robustness guard"
uv run guanlan quality robustness

echo "7/9 benchmark"
uv run guanlan eval benchmark

echo "8/9 build"
uv build

echo "9/9 install smoke + version"
scripts/release_smoke.sh
uv run guanlan version

echo "Guanlan release gate passed."
