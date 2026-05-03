#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Guanlan release gate =="
echo "1/11 ruff"
uv run ruff check $(git ls-files '*.py')

echo "2/11 pytest"
uv run pytest -q

echo "3/11 foundational guard"
uv run guanlan quality foundational

echo "4/11 coverage guard"
uv run guanlan quality coverage

echo "5/11 regression guard"
uv run guanlan quality regression

echo "6/11 robustness guard"
uv run guanlan quality robustness

echo "7/11 benchmark"
uv run guanlan eval benchmark

echo "8/11 performance guard"
uv run guanlan quality performance

echo "9/11 eval suite"
uv run guanlan eval suite run chinese-web-v1

echo "10/11 build"
uv build

echo "11/11 install smoke + version"
scripts/release_smoke.sh
uv run guanlan version

echo "Guanlan release gate passed."
