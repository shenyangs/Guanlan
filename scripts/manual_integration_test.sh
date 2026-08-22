#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "== Guanlan manual integration smoke =="
echo "workspace: $ROOT"
echo

python3 -m venv "$TMP/venv"
"$TMP/venv/bin/python" -m pip install --upgrade pip >/dev/null
"$TMP/venv/bin/python" -m pip install "$ROOT"

export HOME="$TMP/home"
mkdir -p "$HOME"

"$TMP/venv/bin/guanlan" --version
"$TMP/venv/bin/guanlan" welcome
"$TMP/venv/bin/guanlan" capabilities >/dev/null
"$TMP/venv/bin/guanlan" search --list-scopes >/dev/null
"$TMP/venv/bin/guanlan" research --list-presets >/dev/null
"$TMP/venv/bin/guanlan" doctor --trace
"$TMP/venv/bin/guanlan" status
"$TMP/venv/bin/guanlan" read "https://example.com/" --backend direct --no-fallback-search --format json --max-chars 2000 >/dev/null

echo
echo "Manual integration smoke passed."
