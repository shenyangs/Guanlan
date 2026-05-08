#!/usr/bin/env bash
set -euo pipefail

MODE="uv"
SKIP_SMOKE="0"
EXPECTED_VERSION="${GUANLAN_EXPECTED_VERSION:-}"

usage() {
  cat <<'EOF'
Install or update Guanlan and run path/version checks.

Usage:
  install_or_update_guanlan.sh [--mode uv|brew|pipx] [--expected VERSION] [--skip-smoke]

Defaults:
  --mode uv

Examples:
  install_or_update_guanlan.sh
  install_or_update_guanlan.sh --mode brew --expected 0.5.26
  install_or_update_guanlan.sh --skip-smoke
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --expected)
      EXPECTED_VERSION="${2:-}"
      shift 2
      ;;
    --skip-smoke)
      SKIP_SMOKE="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

run() {
  echo "+ $*"
  "$@"
}

extract_version() {
  sed -n 's/.*v\([0-9][0-9.]*\).*/\1/p' | head -1
}

echo "[guanlan-skill] clearing local update-check cache"
rm -f "${HOME}/.guanlan/cache/update-check.json" || true

case "$MODE" in
  uv)
    command -v uv >/dev/null 2>&1 || { echo "uv not found" >&2; exit 1; }
    run uv tool install --force --upgrade --refresh --index-url https://pypi.org/simple guanlan
    ;;
  brew|homebrew)
    command -v brew >/dev/null 2>&1 || { echo "brew not found" >&2; exit 1; }
    run brew update
    run brew reinstall shenyangs/tap/guanlan
    ;;
  pipx)
    command -v pipx >/dev/null 2>&1 || { echo "pipx not found" >&2; exit 1; }
    run pipx install --force guanlan
    ;;
  *)
    echo "unsupported mode: $MODE" >&2
    exit 2
    ;;
esac

hash -r 2>/dev/null || true

echo
echo "[guanlan-skill] executable paths"
run command -v guanlan
run which -a guanlan

echo
echo "[guanlan-skill] active version"
VERSION_TEXT="$(guanlan version)"
echo "$VERSION_TEXT"
ACTIVE_VERSION="$(printf '%s\n' "$VERSION_TEXT" | extract_version)"

if [ -n "$EXPECTED_VERSION" ] && [ "$ACTIVE_VERSION" != "$EXPECTED_VERSION" ]; then
  echo "expected Guanlan $EXPECTED_VERSION but active version is ${ACTIVE_VERSION:-unknown}" >&2
  exit 1
fi

echo
echo "[guanlan-skill] install check"
guanlan doctor --install-check

if [ "$SKIP_SMOKE" = "1" ]; then
  echo "[guanlan-skill] smoke checks skipped"
  exit 0
fi

echo
echo "[guanlan-skill] smoke checks"
guanlan capabilities >/tmp/guanlan-capabilities-smoke.txt
echo "capabilities lines: $(wc -l < /tmp/guanlan-capabilities-smoke.txt | tr -d ' ')"
guanlan doctor --trace >/tmp/guanlan-doctor-trace-smoke.txt
echo "doctor trace lines: $(wc -l < /tmp/guanlan-doctor-trace-smoke.txt | tr -d ' ')"
guanlan search "人工智能 政策" --profile china --limit 5 --trace >/tmp/guanlan-search-smoke.txt
echo "search smoke lines: $(wc -l < /tmp/guanlan-search-smoke.txt | tr -d ' ')"
guanlan hotnews today --limit 5 --trends >/tmp/guanlan-hotnews-smoke.txt
echo "hotnews smoke lines: $(wc -l < /tmp/guanlan-hotnews-smoke.txt | tr -d ' ')"

echo
echo "[guanlan-skill] ok"
