#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Guanlan release gate =="
echo "1/8 ruff"
uv run ruff check $(git ls-files '*.py')

echo "2/8 pytest"
uv run pytest -q

echo "3/8 coverage guard"
uv run guanlan quality coverage

echo "4/8 regression guard"
uv run guanlan quality regression

echo "5/8 robustness guard"
uv run guanlan quality robustness

echo "6/8 benchmark"
uv run guanlan eval benchmark

echo "7/8 build"
uv build

echo "8/8 install smoke + version"
scripts/release_smoke.sh
uv run guanlan version

echo "Guanlan release gate passed."
