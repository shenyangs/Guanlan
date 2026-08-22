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
SOURCE_SITE_URL="${GUANLAN_RELEASE_SOURCE_SITE_URL:-http://101.37.70.222/}"
if [ "${GUANLAN_RELEASE_SOURCE_ONLY:-0}" = "1" ]; then
  SITE_URLS="${GUANLAN_RELEASE_SITE_URLS:-$SOURCE_SITE_URL}"
else
  SITE_URLS="${GUANLAN_RELEASE_SITE_URLS:-https://guanlan.xin/ https://www.guanlan.xin/ $SOURCE_SITE_URL}"
fi
SYNC_TIMEOUT_SECONDS="${GUANLAN_SYNC_TIMEOUT_SECONDS:-1500}"
SYNC_INTERVAL_SECONDS="${GUANLAN_SYNC_INTERVAL_SECONDS:-15}"
SKIP_DIST_WAIT="${GUANLAN_SYNC_SKIP_DISTRIBUTION_WAIT:-0}"
DEPLOY_WEBSITE="${GUANLAN_RELEASE_DEPLOY_WEBSITE:-1}"
SKIP_WEBSITE="${GUANLAN_RELEASE_SKIP_WEBSITE:-0}"
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
        ["curl", "-sSL", "--max-time", "20", *headers, "-w", "\nHTTP_STATUS:%{http_code}\n", url],
        text=True,
    )
except Exception:
    sys.exit(1)

marker = "\nHTTP_STATUS:"
if marker not in raw:
    sys.exit(1)
body, status_text = raw.rsplit(marker, 1)
status_code = int((status_text or "").strip() or "0")
if status_code == 403:
    sys.exit(2)
if status_code >= 400:
    sys.exit(1)

try:
    payload = json.loads(body)
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

wait_for_github_release_workflow() {
  local started now status
  started="$(date +%s)"
  while true; do
    set +e
    check_github_release_workflow
    status=$?
    set -e
    if [ "$status" = "0" ]; then
      echo "[sync] github release workflow (${TAG}): ready"
      return 0
    fi
    if [ "$status" = "2" ]; then
      echo "[sync] github workflow probe hit API 403/rate-limit; defer to PyPI/Homebrew/website confirmation."
      return 0
    fi
    now="$(date +%s)"
    if [ $((now - started)) -ge "$SYNC_TIMEOUT_SECONDS" ]; then
      fail "github release workflow (${TAG}) not ready after ${SYNC_TIMEOUT_SECONDS}s"
    fi
    echo "[sync] waiting for github release workflow (${TAG})..."
    sleep "$SYNC_INTERVAL_SECONDS"
  done
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

_site_is_source() {
  local url="$1"
  [ "$url" = "$SOURCE_SITE_URL" ] || [ "$url" = "${SOURCE_SITE_URL%/}" ]
}

check_website_release() {
  local url body ok_any source_ok public_failures
  ok_any=0
  source_ok=0
  public_failures=()
  for url in $SITE_URLS; do
    if body="$(curl -fsSL --max-time 12 -H "Cache-Control: no-cache" "$url" 2>/dev/null)"; then
      if printf '%s' "$body" | grep -q "Guanlan v${VERSION}"; then
        ok_any=1
        if _site_is_source "$url"; then
          source_ok=1
        fi
        continue
      fi
      public_failures+=("$url:old_or_block_page")
    else
      public_failures+=("$url:request_failed")
    fi
  done
  if [ "${GUANLAN_RELEASE_SOURCE_ONLY:-0}" = "1" ]; then
    [ "$ok_any" = "1" ]
    return
  fi
  if [ "${#public_failures[@]}" -gt 0 ]; then
    if [ "$source_ok" = "1" ]; then
      echo "source_deployed_but_public_site_blocked: ${public_failures[*]}" >&2
    else
      echo "public_site_not_ready: ${public_failures[*]}" >&2
    fi
    return 1
  fi
  return 0
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

uv_tool_bin_path() {
  local tool_dir
  tool_dir="$(uv tool dir 2>/dev/null || true)"
  if [ -z "$tool_dir" ]; then
    return 0
  fi
  printf '%s/guanlan/bin/guanlan\n' "$tool_dir"
}

verify_single_bin_version() {
  local label="$1"
  local bin_path="$2"
  local version
  [ -x "$bin_path" ] || fail "$label path not executable: $bin_path"
  version="$(extract_version "$bin_path")"
  [ -n "$version" ] || fail "$label path $bin_path returned unknown version"
  [ "$version" = "$VERSION" ] || fail "$label path $bin_path version $version != expected $VERSION"
}

sync_local_installs() {
  if [ "$SYNC_LOCAL_INSTALLS" != "1" ]; then
    echo "[sync] local installer sync skipped (GUANLAN_SYNC_LOCAL_INSTALLS=$SYNC_LOCAL_INSTALLS)"
    return 0
  fi

  if command -v uv >/dev/null 2>&1; then
    echo "[sync] refreshing uv tool install..."
    uv tool install --force --upgrade --reinstall-package guanlan --refresh --no-sources --default-index https://pypi.org/simple guanlan
    local uv_bin
    uv_bin="$(uv_tool_bin_path)"
    if [ -n "$uv_bin" ] && [ -x "$uv_bin" ]; then
      local uv_version
      uv_version="$(extract_version "$uv_bin")"
      if [ "$uv_version" != "$VERSION" ]; then
        echo "[sync] uv tool path resolved v${uv_version:-unknown}; retrying once with --no-cache..."
        uv tool install --force --upgrade --reinstall-package guanlan --refresh --no-sources --no-cache --default-index https://pypi.org/simple guanlan
      fi
      verify_single_bin_version "uv tool" "$uv_bin"
    fi
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
  paths="$(which -a guanlan 2>/dev/null || true)"
  if [ -z "$paths" ]; then
    fail "no guanlan executable found in PATH"
  fi
  unique_paths="$(printf '%s\n' "$paths" | awk 'NF && !seen[$0]++')"

  echo "[sync] local guanlan entrypoints:"
  while IFS= read -r path; do
    [ -z "$path" ] && continue
    version="$(extract_version "$path")"
    echo "  - $path => v${version:-unknown}"
    if [ -z "$version" ]; then
      fail "entrypoint $path returned unknown version"
    fi
    if [ "$version" != "$VERSION" ]; then
      fail "entrypoint $path version $version != expected $VERSION"
    fi
  done <<< "$unique_paths"

  if command -v guanlan >/dev/null 2>&1; then
    echo "[sync] running install-check..."
    guanlan doctor --install-check
  fi
}

verify_installed_read() {
  echo "[sync] running installed public read smoke..."
  guanlan read "https://example.com/" \
    --backend direct \
    --no-fallback-search \
    --format json \
    | python3 -c 'import json,sys; packet=json.load(sys.stdin); assert packet["extract_contract"]["can_cite_as_page_body"] is True; assert packet["trace"]["selected_backend"] == "direct"'
  echo "[sync] installed public read smoke: ready"
}

require_tools

if [ "$SKIP_DIST_WAIT" != "1" ]; then
  echo "[sync] waiting for release workflow/PyPI/Homebrew..."
  wait_for_github_release_workflow
  wait_for_condition "pypi ${PYPI_PACKAGE}==${VERSION}" "check_pypi_release"
  wait_for_condition "homebrew tap formula ${VERSION}" "check_homebrew_tap_release"
else
  echo "[sync] distribution waits skipped (GUANLAN_SYNC_SKIP_DISTRIBUTION_WAIT=1)"
fi

if [ "$SKIP_WEBSITE" = "1" ]; then
  echo "[sync] website deploy and version checks skipped (GUANLAN_RELEASE_SKIP_WEBSITE=1)"
else
  deploy_website_if_needed
  wait_for_condition "website public surfaces version ${VERSION}" "check_website_release"
fi
sync_local_installs
verify_local_entrypoints
verify_installed_read

if [ "${GUANLAN_RELEASE_SOURCE_ONLY:-0}" = "1" ]; then
  echo "release incomplete: source-only website validation used (GUANLAN_RELEASE_SOURCE_ONLY=1)"
else
  echo "post-release sync ok"
fi
echo "version=$VERSION"
echo "tag=$TAG"
echo "site_urls=$SITE_URLS"
echo "website_skipped=$SKIP_WEBSITE"
