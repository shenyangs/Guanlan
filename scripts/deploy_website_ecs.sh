#!/usr/bin/env bash
set -euo pipefail

# Deploy website/ to ECS without touching telemetry service config.
# Usage:
#   scripts/deploy_website_ecs.sh root@101.37.70.222 ~/.ssh/guanlan_telemetry_deploy

TARGET="${1:-root@101.37.70.222}"
SSH_KEY="${2:-$HOME/.ssh/guanlan_telemetry_deploy}"
WORKDIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$WORKDIR"
python3 scripts/sync_website_version.py

tar --no-xattrs -C website -czf /tmp/guanlan-site.tar.gz .
scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 -o ServerAliveInterval=15 \
  /tmp/guanlan-site.tar.gz "$TARGET":/tmp/guanlan-site.tar.gz

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
'

curl -fsSI --connect-timeout 8 "http://${TARGET#*@}/" | sed -n "1,12p"
curl -fsS --connect-timeout 8 "http://${TARGET#*@}/guanlan-telemetry/healthz"
