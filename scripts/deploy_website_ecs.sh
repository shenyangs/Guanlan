#!/usr/bin/env bash
set -euo pipefail

# Deploy website/ to ECS without touching telemetry service config.
# Falls back to Alibaba Cloud Assistant when a local VPN/TUN captures SSH.
# Usage:
#   scripts/deploy_website_ecs.sh root@101.37.70.222 ~/.ssh/guanlan_telemetry_deploy

TARGET="${1:-root@101.37.70.222}"
SSH_KEY="${2:-$HOME/.ssh/guanlan_telemetry_deploy}"
WORKDIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$WORKDIR"
python3 scripts/sync_website_version.py
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -1)"
TARGET_HOST="${TARGET#*@}"
ARCHIVE="/tmp/guanlan-site-${VERSION}.tar.gz"

deploy_via_ssh() {
  tar --no-xattrs -C website -czf "$ARCHIVE" . || return 1
  scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o ServerAliveInterval=15 \
    "$ARCHIVE" "$TARGET":/tmp/guanlan-site.tar.gz || return 1

  ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o ServerAliveInterval=15 "$TARGET" '
set -e
release=/var/www/guanlan-site/releases/$(date +%Y%m%d%H%M%S)
current=/var/www/guanlan-site/current
previous="$(readlink "$current" || true)"
mkdir -p "$release"
tar -xzf /tmp/guanlan-site.tar.gz -C "$release"
chown -R nginx:nginx "$release" || true
find "$release" -type d -exec chmod 755 {} \;
find "$release" -type f -exec chmod 644 {} \;
test -s "$release/index.html"
nginx -t
ln -sfn "$release" "$current"
if ! systemctl reload nginx; then
  if [ -n "$previous" ]; then
    ln -sfn "$previous" "$current"
    systemctl reload nginx || true
  fi
  exit 1
fi
echo "release=$release"
' || return 1
}

if ! deploy_via_ssh; then
  echo "[deploy] direct SSH path unavailable; trying Cloud Assistant fallback." >&2
  if [ -n "${GUANLAN_ALIYUN_ACCESS_KEY_ID:-}" ] && [ -n "${GUANLAN_ALIYUN_ACCESS_KEY_SECRET:-}" ]; then
    python3 scripts/deploy_website_cloud_assistant.py --version "$VERSION"
  else
    echo "[deploy] Cloud Assistant fallback needs GUANLAN_ALIYUN_ACCESS_KEY_ID and GUANLAN_ALIYUN_ACCESS_KEY_SECRET in this process environment." >&2
    exit 1
  fi
fi

rm -f "$ARCHIVE"
if ! curl -fsSI --connect-timeout 8 "http://${TARGET_HOST}/" | sed -n "1,12p"; then
  echo "[deploy] server-side deployment succeeded, but this machine could not probe the public IP." >&2
  echo "[deploy] run scripts/post_release_sync.sh ${VERSION} to determine public release status." >&2
fi
if ! curl -fsS --connect-timeout 8 "http://${TARGET_HOST}/guanlan-telemetry/healthz"; then
  echo "[deploy] local telemetry health probe unavailable from this network; server-side website verification already ran." >&2
fi
