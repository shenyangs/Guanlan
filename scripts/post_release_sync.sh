#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-$(sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -1)}"
TAG="v$VERSION"
REPO="${GUANLAN_GITHUB_REPO:-shenyangs/Guanlan}"
RELEASE_WORKFLOW_PATH="${GUANLAN_RELEASE_WORKFLOW_PATH:-release-pypi.yml}"
PYPI_PACKAGE="${GUANLAN_PYPI_PACKAGE:-guanlan}"
TAP_REPO="${GUANLAN_HOMEBREW_TAP_REPO:-shenyangs/homebrew-tap}"
TAP_FORMULA_PATH="${GUANLAN_HOMEBREW_FORMULA_PATH:-Formula/guanlan.rb}"
SITE_URL="${GUANLAN_RELEASE_SITE_URL:-http://101.37.70.222}"
SYNC_TIMEOUT_SECONDS="${GUANLAN_SYNC_TIMEOUT_SECONDS:-1500}"
SYNC_INTERVAL_SECONDS="${GUANLAN_SYNC_INTERVAL_SECONDS:-15}"
SKIP_DIST_WAIT="${GUANLAN_SYNC_SKIP_DISTRIBUTION_WAIT:-0}"
DEPLOY_WEBSITE="${GUANLAN_RELEASE_DEPLOY_WEBSITE:-1}"
SYNC_LOCAL_INSTALLS="${GUANLAN_SYNC_LOCAL_INSTALLS:-1}"

fail() {
  echo "post-release sync failed: $*" >&2
  exit 1
}

extract_version() {
  local bin_path="$1"
  local text
  text="$("$bin_path" version 2>/dev/null || "$bin_path" --version 2>/dev/null || true)"
  printf '%s' "$text" | sed -n 's/.*v\([0-9][0-9.]*\).*/\1/p' | head -1
}

require_tools() {
  command -v python3 >/dev/null 2>&1 || fail "python3 not found"
  command -v curl >/dev/null 2>&1 || fail "curl not found"
}

wait_for_condition() {
  local label="$1"
  local probe_cmd="$2"
  local started now
  started="$(date +%s)"
  while true; do
    if eval "$probe_cmd"; then
      echo "[sync] $label: ready"
      return 0
    fi
    now="$(date +%s)"
    if [ $((now - started)) -ge "$SYNC_TIMEOUT_SECONDS" ]; then
      fail "$label not ready after ${SYNC_TIMEOUT_SECONDS}s"
    fi
    echo "[sync] waiting for $label..."
    sleep "$SYNC_INTERVAL_SECONDS"
  done
}

check_github_release_workflow() {
  python3 - "$REPO" "$TAG" "$RELEASE_WORKFLOW_PATH" <<'PY'
import json
import sys
import subprocess

repo = sys.argv[1]
tag = sys.argv[2]
workflow_path = sys.argv[3]
if "/" in workflow_path:
    workflow_path = workflow_path.rsplit("/", 1)[-1]
url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_path}/runs?branch={tag}&per_page=5"
headers = ["-H", "Accept: application/vnd.github+json"]
token = ""
try:
    token = subprocess.check_output(["bash", "-lc", "printf %s \"${GITHUB_TOKEN:-}\""], text=True).strip()
except Exception:
    token = ""
if token:
    headers += ["-H", f"Authorization: Bearer {token}"]

try:
    raw = subprocess.check_output(
        ["curl", "-fsSL", "--max-time", "20", *headers, url],
        text=True,
    )
    payload = json.loads(raw)
except Exception:
    sys.exit(1)

runs = payload.get("workflow_runs") or []
if not runs:
    sys.exit(1)

run = runs[0]
status = str(run.get("status") or "")
conclusion = str(run.get("conclusion") or "")
if status == "completed" and conclusion == "success":
    sys.exit(0)
sys.exit(1)
PY
}

check_pypi_release() {
  python3 - "$PYPI_PACKAGE" "$VERSION" <<'PY'
import sys
import subprocess

package = sys.argv[1]
version = sys.argv[2]
url = f"https://pypi.org/pypi/{package}/{version}/json"
try:
    subprocess.check_output(
        ["curl", "-fsSL", "--max-time", "20", "-H", "Accept: application/json", url],
        text=True,
    )
    sys.exit(0)
except Exception:
    sys.exit(1)
PY
}

check_homebrew_tap_release() {
  local formula_url
  formula_url="https://raw.githubusercontent.com/${TAP_REPO}/main/${TAP_FORMULA_PATH}"
  curl -fsSL --max-time 12 "$formula_url" | grep -q "guanlan-${VERSION}\.tar\.gz"
}

check_website_release() {
  curl -fsSL --max-time 12 "$SITE_URL" | grep -q "Guanlan v${VERSION}"
}

deploy_website_if_needed() {
  if [ "$DEPLOY_WEBSITE" != "1" ]; then
    echo "[sync] website deploy skipped (GUANLAN_RELEASE_DEPLOY_WEBSITE=$DEPLOY_WEBSITE)"
    return 0
  fi
  if [ -x "scripts/deploy_website_ecs.sh" ]; then
    echo "[sync] deploying website..."
    scripts/deploy_website_ecs.sh
    return 0
  fi
  echo "[sync] website deploy script not found, skip deploy."
}

sync_local_installs() {
  if [ "$SYNC_LOCAL_INSTALLS" != "1" ]; then
    echo "[sync] local installer sync skipped (GUANLAN_SYNC_LOCAL_INSTALLS=$SYNC_LOCAL_INSTALLS)"
    return 0
  fi

  if command -v uv >/dev/null 2>&1; then
    echo "[sync] refreshing uv tool install..."
    uv tool install --force --upgrade --refresh --index-url https://pypi.org/simple guanlan
  else
    echo "[sync] uv not found, skip uv sync."
  fi

  if command -v brew >/dev/null 2>&1; then
    echo "[sync] refreshing homebrew install..."
    brew update
    brew reinstall shenyangs/tap/guanlan
  else
    echo "[sync] brew not found, skip brew sync."
  fi

  if command -v pipx >/dev/null 2>&1; then
    echo "[sync] refreshing pipx install..."
    CERT_PATH="$(python3 -c 'import certifi; print(certifi.where())' 2>/dev/null || true)"
    if [ -n "$CERT_PATH" ]; then
      export PIP_CERT="$CERT_PATH"
    fi
    pipx install --force guanlan
  else
    echo "[sync] pipx not found, skip pipx sync."
  fi
}

verify_local_entrypoints() {
  local paths unique_paths path version
  hash -r || true
  mapfile -t paths < <(which -a guanlan 2>/dev/null || true)
  if [ "${#paths[@]}" -eq 0 ]; then
    fail "no guanlan executable found in PATH"
  fi
  mapfile -t unique_paths < <(printf '%s\n' "${paths[@]}" | awk '!seen[$0]++')

  echo "[sync] local guanlan entrypoints:"
  for path in "${unique_paths[@]}"; do
    version="$(extract_version "$path")"
    echo "  - $path => v${version:-unknown}"
    if [ -n "$version" ] && [ "$version" != "$VERSION" ]; then
      fail "entrypoint $path version $version != expected $VERSION"
    fi
  done

  if command -v guanlan >/dev/null 2>&1; then
    echo "[sync] running install-check..."
    guanlan doctor --install-check || true
  fi
}

require_tools

if [ "$SKIP_DIST_WAIT" != "1" ]; then
  echo "[sync] waiting for release workflow/PyPI/Homebrew..."
  wait_for_condition "github release workflow (${TAG})" "check_github_release_workflow"
  wait_for_condition "pypi ${PYPI_PACKAGE}==${VERSION}" "check_pypi_release"
  wait_for_condition "homebrew tap formula ${VERSION}" "check_homebrew_tap_release"
else
  echo "[sync] distribution waits skipped (GUANLAN_SYNC_SKIP_DISTRIBUTION_WAIT=1)"
fi

deploy_website_if_needed
wait_for_condition "website ${SITE_URL} version ${VERSION}" "check_website_release"
sync_local_installs
verify_local_entrypoints

echo "post-release sync ok"
echo "version=$VERSION"
echo "tag=$TAG"
echo "site_url=$SITE_URL"
