#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -1)"
EXT_DIR="guanlan/browser_bridge/extension"
OUT_DIR="dist"
OUT_ZIP="$OUT_DIR/openguanlan-browser-bridge-${VERSION}.zip"

if [[ ! -f "$EXT_DIR/manifest.json" ]]; then
  echo "missing extension manifest: $EXT_DIR/manifest.json" >&2
  exit 1
fi

python3 - "$VERSION" "$EXT_DIR" <<'PY'
import json
import pathlib
import sys

version = sys.argv[1]
extension_dir = pathlib.Path(sys.argv[2])
manifest = json.loads((extension_dir / "manifest.json").read_text(encoding="utf-8"))
if manifest.get("manifest_version") != 3:
    raise SystemExit("manifest_version must be 3")
if manifest.get("version") != version:
    raise SystemExit(f"manifest version {manifest.get('version')} != project version {version}")
permissions = set(manifest.get("permissions") or [])
for forbidden in {"cookies", "storage", "debugger", "downloads", "nativeMessaging"}:
    if forbidden in permissions:
        raise SystemExit(f"forbidden permission requested: {forbidden}")
required = {"activeTab", "scripting", "tabs"}
missing = required - permissions
if missing:
    raise SystemExit(f"missing required permissions: {sorted(missing)}")
host_permissions = set(manifest.get("host_permissions") or [])
if "<all_urls>" in host_permissions:
    raise SystemExit("<all_urls> must stay optional, not default host_permissions")
optional_hosts = set(manifest.get("optional_host_permissions") or [])
if "<all_urls>" not in optional_hosts:
    raise SystemExit("optional_host_permissions must include <all_urls> for per-site grants")
PY

mkdir -p "$OUT_DIR"
rm -f "$OUT_ZIP"

python3 - "$EXT_DIR" "$OUT_ZIP" <<'PY'
from __future__ import annotations

import pathlib
import sys
import zipfile

extension_dir = pathlib.Path(sys.argv[1])
out_zip = pathlib.Path(sys.argv[2])
allowed_suffixes = {".html", ".css", ".js", ".json", ".png"}
with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(extension_dir.rglob("*")):
        if path.is_dir():
            continue
        if path.name.startswith(".") or path.suffix not in allowed_suffixes:
            continue
        archive.write(path, path.relative_to(extension_dir).as_posix())
print(out_zip)
PY

echo "Built $OUT_ZIP"
