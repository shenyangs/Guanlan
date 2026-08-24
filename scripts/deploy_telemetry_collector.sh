#!/usr/bin/env bash
set -euo pipefail

# Deploy the standalone telemetry collector with a recoverable server-side
# backup. It intentionally does not deploy website assets.
# Usage:
#   scripts/deploy_telemetry_collector.sh root@101.37.70.222 ~/.ssh/guanlan_telemetry_deploy

TARGET="${1:-root@101.37.70.222}"
SSH_KEY="${2:-$HOME/.ssh/guanlan_telemetry_deploy}"
WORKDIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$WORKDIR/scripts/telemetry_collector.py"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$WORKDIR/pyproject.toml" | head -1)"
REMOTE_STAGE="/tmp/guanlan-telemetry-collector-${VERSION}.py"

test -s "$SOURCE"
scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 "$SOURCE" "$TARGET:$REMOTE_STAGE"
ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=12 "$TARGET" "
set -e
source=/opt/guanlan-telemetry/telemetry_collector.py
stage=$REMOTE_STAGE
backup_dir=/opt/guanlan-telemetry/backups
backup=\$backup_dir/telemetry_collector-\$(date +%Y%m%d%H%M%S)-${VERSION}.py
test -s \$stage
/usr/bin/python3 -m py_compile \$stage
mkdir -p \$backup_dir
cp \$source \$backup
install -m 0644 \$stage \$source
rm -f \$stage
systemctl restart guanlan-telemetry
# The collector commonly sits behind Nginx on a non-default loopback port.
# Read its service EnvironmentFile locally instead of hard-coding 8080, so a
# healthy deployment is never reported as failed solely by the probe script.
set -a
. /etc/guanlan-telemetry.env
set +a
health_url=http://127.0.0.1:\${GUANLAN_PORT:-8080}/healthz
ready=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if curl -fsS --max-time 2 \$health_url 2>/dev/null | grep -qx 'ok'; then
    ready=1
    break
  fi
  sleep 1
done
test \$ready = 1
printf 'backup=%s\n' \$backup
"
