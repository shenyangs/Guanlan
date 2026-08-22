#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

python3 -m venv "$TMP/venv"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$ROOT/pyproject.toml" | head -1)"
WHEEL="$ROOT/dist/guanlan-${VERSION}-py3-none-any.whl"
INSTALL_TARGET="$ROOT"
if [[ -f "$WHEEL" ]]; then
  INSTALL_TARGET="$WHEEL"
fi

if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$TMP/venv/bin/python" "$INSTALL_TARGET"
else
  CERT_PATH="$(python3 -c 'import certifi; print(certifi.where())' 2>/dev/null || true)"
  if [[ -n "$CERT_PATH" ]]; then
    export PIP_CERT="$CERT_PATH"
  fi
  "$TMP/venv/bin/python" -m pip install "$INSTALL_TARGET"
fi
"$TMP/venv/bin/guanlan" --version
"$TMP/venv/bin/guanlan" version
"$TMP/venv/bin/python" "$ROOT/scripts/installed_read_smoke.py"
HOME="$TMP/home" "$TMP/venv/bin/guanlan" install --env=auto --safe --dry-run
HOME="$TMP/home" "$TMP/venv/bin/guanlan" status

if command -v pipx >/dev/null 2>&1; then
  export PIPX_HOME="$TMP/pipx-home"
  export PIPX_BIN_DIR="$TMP/pipx-bin"
  CERT_PATH="$(python3 -c 'import certifi; print(certifi.where())' 2>/dev/null || true)"
  if [[ -n "$CERT_PATH" ]]; then
    export PIP_CERT="$CERT_PATH"
  fi
  mkdir -p "$PIPX_HOME" "$PIPX_BIN_DIR"
  pipx install "$INSTALL_TARGET"
  "$PIPX_BIN_DIR/guanlan" --version
else
  echo "pipx not found; skipped pipx install smoke."
fi
