#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

python3 -m venv "$TMP/venv"
"$TMP/venv/bin/python" -m pip install --upgrade pip >/dev/null
"$TMP/venv/bin/python" -m pip install "$ROOT"
"$TMP/venv/bin/guanlan" --version
"$TMP/venv/bin/guanlan" version
HOME="$TMP/home" "$TMP/venv/bin/guanlan" install --env=auto --safe --dry-run
HOME="$TMP/home" "$TMP/venv/bin/guanlan" status

if command -v pipx >/dev/null 2>&1; then
  export PIPX_HOME="$TMP/pipx-home"
  export PIPX_BIN_DIR="$TMP/pipx-bin"
  mkdir -p "$PIPX_HOME" "$PIPX_BIN_DIR"
  pipx install "$ROOT"
  "$PIPX_BIN_DIR/guanlan" --version
else
  echo "pipx not found; skipped pipx install smoke."
fi
