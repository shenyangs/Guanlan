#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ALLOW_DIRTY="${GUANLAN_RELEASE_ALLOW_DIRTY:-0}"
EXPECTED_VERSION="${1:-}"

fail() {
  echo "pre-release check failed: $*" >&2
  exit 1
}

version_from_pyproject="$(sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -1)"
version_from_init="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' guanlan/__init__.py | head -1)"

[ -n "$version_from_pyproject" ] || fail "pyproject.toml version not found"
[ -n "$version_from_init" ] || fail "guanlan.__version__ not found"
[ "$version_from_pyproject" = "$version_from_init" ] || fail "version mismatch: pyproject=$version_from_pyproject init=$version_from_init"

if [ -n "$EXPECTED_VERSION" ] && [ "$EXPECTED_VERSION" != "$version_from_pyproject" ]; then
  fail "expected version $EXPECTED_VERSION but project is $version_from_pyproject"
fi

if [ -f uv.lock ] && ! grep -q "version = \"$version_from_pyproject\"" uv.lock; then
  fail "uv.lock does not contain project version $version_from_pyproject"
fi

for file in README.md docs/full-guide.md docs/telemetry.md website/index.html; do
  if [ -f "$file" ] && ! grep -q "$version_from_pyproject" "$file"; then
    fail "$file does not mention version $version_from_pyproject"
  fi
done

if [ -f SECURITY.md ]; then
  supported_line="$(printf '%s' "$version_from_pyproject" | awk -F. '{print $1 "." $2 ".x"}')"
  if ! grep -q "Latest $supported_line" SECURITY.md; then
    fail "SECURITY.md does not mention supported line Latest $supported_line"
  fi
fi

if [ -f CHANGELOG.md ] && ! grep -q "## v$version_from_pyproject" CHANGELOG.md; then
  fail "CHANGELOG.md missing v$version_from_pyproject entry"
fi

tap_formula="${GUANLAN_HOMEBREW_FORMULA:-}"
if [ -z "$tap_formula" ]; then
  for candidate in ../homebrew-tap/Formula/guanlan.rb /opt/homebrew/Library/Taps/shenyangs/homebrew-tap/Formula/guanlan.rb; do
    if [ -f "$candidate" ]; then
      tap_formula="$candidate"
      break
    fi
  done
fi

if [ -n "$tap_formula" ]; then
  [ -f "$tap_formula" ] || fail "Homebrew formula not found: $tap_formula"
  if ! grep -q "guanlan-$version_from_pyproject.tar.gz" "$tap_formula" \
    && ! grep -q "version \"$version_from_pyproject\"" "$tap_formula"; then
    if [ "${GUANLAN_RELEASE_REQUIRE_DISTRIBUTIONS:-0}" = "1" ]; then
      fail "Homebrew formula $tap_formula does not reference version $version_from_pyproject"
    fi
    echo "pre-release warning: Homebrew formula $tap_formula does not reference version $version_from_pyproject" >&2
  fi
fi

if [ -n "${GUANLAN_RELEASE_SITE_URL:-}" ]; then
  site_html="$(curl -fsSL --max-time 8 "$GUANLAN_RELEASE_SITE_URL" || true)"
  if [ -z "$site_html" ]; then
    fail "official website check failed: $GUANLAN_RELEASE_SITE_URL"
  fi
  if ! printf '%s' "$site_html" | grep -q "$version_from_pyproject"; then
    if [ "${GUANLAN_RELEASE_REQUIRE_DISTRIBUTIONS:-0}" = "1" ]; then
      fail "official website $GUANLAN_RELEASE_SITE_URL does not mention version $version_from_pyproject"
    fi
    echo "pre-release warning: official website $GUANLAN_RELEASE_SITE_URL does not mention version $version_from_pyproject" >&2
  fi
fi

status="$(git status --short)"
if [ -n "$status" ] && [ "$ALLOW_DIRTY" != "1" ]; then
  echo "$status" >&2
  fail "working tree is dirty; commit/stash unrelated changes or set GUANLAN_RELEASE_ALLOW_DIRTY=1 for local diagnostics only"
fi

branch="$(git branch --show-current 2>/dev/null || true)"
upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"

echo "pre-release status ok"
echo "version=$version_from_pyproject"
echo "branch=${branch:-detached}"
echo "upstream=${upstream:-none}"
if [ -n "$status" ]; then
  echo "dirty_allowed=1"
fi
