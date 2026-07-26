#!/usr/bin/env python3
"""Deploy a tagged Guanlan website through Alibaba Cloud Assistant.

This is the release-path fallback for machines whose direct SSH traffic is
temporarily captured by a VPN or TUN interface.  Credentials are read only
from the current process environment and never written to disk or echoed.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

API_VERSION = "2014-05-26"
DEFAULT_REGION = "cn-hangzhou"
DEFAULT_INSTANCE_ID = "i-bp1ja5af6unrbi1wupb4"
DEFAULT_ENDPOINT = "https://ecs.aliyuncs.com/"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
TERMINAL_STATUSES = {"Success", "Failed", "Stopped"}


class CloudAssistantError(RuntimeError):
    """A safe, user-actionable Cloud Assistant failure."""


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise CloudAssistantError(f"missing required environment variable: {name}")
    return value


def percent_encode(value: object) -> str:
    return urllib.parse.quote(str(value), safe="~")


def signed_params(
    action: str, params: dict[str, object], access_key_id: str, access_key_secret: str
) -> dict[str, str]:
    """Create a Signature Version 1 ECS request without SDK dependencies."""
    request = {
        "Action": action,
        "Format": "JSON",
        "Version": API_VERSION,
        "AccessKeyId": access_key_id,
        "SignatureMethod": "HMAC-SHA1",
        "Timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "SignatureVersion": "1.0",
        "SignatureNonce": str(uuid.uuid4()),
    }
    request.update({key: str(value) for key, value in params.items()})
    canonical = "&".join(
        f"{percent_encode(key)}={percent_encode(value)}" for key, value in sorted(request.items())
    )
    string_to_sign = f"GET&%2F&{percent_encode(canonical)}"
    digest = hmac.new(
        f"{access_key_secret}&".encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    request["Signature"] = base64.b64encode(digest).decode("ascii")
    return request


def safe_api_error(payload: str) -> str:
    """Return API error metadata without reflecting credentials or signed URLs."""
    try:
        data = json.loads(payload)
    except Exception:
        return "request failed without a readable API response"
    code = str(data.get("Code") or data.get("code") or "unknown_error")
    message = str(data.get("Message") or data.get("message") or "")
    request_id = str(data.get("RequestId") or data.get("requestId") or "")
    parts = [code]
    if message:
        parts.append(message[:300])
    if request_id:
        parts.append(f"request_id={request_id}")
    return "; ".join(parts)


def curl_get(url: str) -> str:
    """Use the system TLS store without putting the signed URL in argv."""
    result = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--max-time", "25", "--config", "-"],
        input=f'url = "{url}"\n',
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise CloudAssistantError("Cloud Assistant request failed through system curl")
    return result.stdout


def api_request(endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    url = f"{endpoint}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote, safe='~')}"
    try:
        with urllib.request.urlopen(
            url, timeout=25, context=ssl.create_default_context()
        ) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise CloudAssistantError(
            f"Cloud Assistant rejected the request: {safe_api_error(body)}"
        ) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            body = curl_get(url)
        else:
            raise CloudAssistantError(f"Cloud Assistant request unavailable: {exc.reason}") from exc
    except (ssl.SSLCertVerificationError, TimeoutError) as exc:
        raise CloudAssistantError(
            f"Cloud Assistant request unavailable: {exc.reason if hasattr(exc, 'reason') else exc}"
        ) from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise CloudAssistantError("Cloud Assistant returned a non-JSON response") from exc


def deployment_script(version: str) -> str:
    if not VERSION_RE.fullmatch(version):
        raise CloudAssistantError("version must use MAJOR.MINOR.PATCH format")
    return f"""set -euo pipefail
version='{version}'
base=/var/www/guanlan-site
releases=\"$base/releases\"
current=\"$base/current\"
workdir=\"$(mktemp -d)\"
trap 'rm -rf \"$workdir\"' EXIT

mkdir -p \"$releases\"
archive=\"$workdir/guanlan.tar.gz\"
curl -fsSL --retry 2 --connect-timeout 15 --max-time 150 \\
  -o \"$archive\" \"https://github.com/shenyangs/Guanlan/archive/refs/tags/v${{version}}.tar.gz\"
tar -xzf \"$archive\" -C \"$workdir\"
source_dir=\"$workdir/Guanlan-${{version}}/website\"
test -d \"$source_dir\"
test -s \"$source_dir/index.html\"
grep -Fq \"Guanlan v${{version}}\" \"$source_dir/index.html\"

release=\"$releases/${{version}}-$(date +%Y%m%d%H%M%S)\"
previous=\"$(readlink \"$current\" || true)\"
mkdir -p \"$release\"
cp -a \"$source_dir\"/. \"$release\"/
chown -R nginx:nginx \"$release\" || true
find \"$release\" -type d -exec chmod 755 {{}} +
find \"$release\" -type f -exec chmod 644 {{}} +
nginx -t
ln -sfn \"$release\" \"$current\"
if ! systemctl reload nginx; then
  if [ -n \"$previous\" ]; then
    ln -sfn \"$previous\" \"$current\"
    systemctl reload nginx || true
  fi
  exit 1
fi
curl -fsS --connect-timeout 8 http://127.0.0.1/ | grep -Fq \"Guanlan v${{version}}\"
echo \"release=$release\"
"""


def find_first(value: Any, field: str) -> str:
    if isinstance(value, dict):
        if field in value and value[field] is not None:
            return str(value[field])
        for item in value.values():
            found = find_first(item, field)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_first(item, field)
            if found:
                return found
    return ""


def describe_invocation(
    *, endpoint: str, access_key_id: str, access_key_secret: str, region: str, invoke_id: str
) -> dict[str, Any]:
    params = signed_params(
        "DescribeInvocations",
        {
            "RegionId": region,
            "InvokeId": invoke_id,
            "IncludeOutput": "true",
            "ContentEncoding": "PlainText",
        },
        access_key_id,
        access_key_secret,
    )
    return api_request(endpoint, params)


def deploy(version: str, *, timeout_seconds: int = 720) -> None:
    if not VERSION_RE.fullmatch(version):
        raise CloudAssistantError("version must use MAJOR.MINOR.PATCH format")
    access_key_id = require_env("GUANLAN_ALIYUN_ACCESS_KEY_ID")
    access_key_secret = require_env("GUANLAN_ALIYUN_ACCESS_KEY_SECRET")
    region = os.environ.get("GUANLAN_ALIYUN_REGION", DEFAULT_REGION).strip() or DEFAULT_REGION
    instance_id = (
        os.environ.get("GUANLAN_ALIYUN_INSTANCE_ID", DEFAULT_INSTANCE_ID).strip()
        or DEFAULT_INSTANCE_ID
    )
    endpoint = (
        os.environ.get("GUANLAN_ALIYUN_ECS_ENDPOINT", DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT
    )
    if not endpoint.startswith("https://"):
        raise CloudAssistantError("GUANLAN_ALIYUN_ECS_ENDPOINT must use https")

    content = base64.b64encode(deployment_script(version).encode("utf-8")).decode("ascii")
    request = signed_params(
        "RunCommand",
        {
            "RegionId": region,
            "InstanceId.1": instance_id,
            "Type": "RunShellScript",
            "Name": f"guanlan-website-deploy-v{version}",
            "Description": "Deploy tagged Guanlan website release",
            "Username": "root",
            "Timeout": "600",
            "ContentEncoding": "Base64",
            "CommandContent": content,
        },
        access_key_id,
        access_key_secret,
    )
    response = api_request(endpoint, request)
    invoke_id = str(response.get("InvokeId") or "")
    if not invoke_id:
        raise CloudAssistantError(
            f"Cloud Assistant did not return an invoke id: {safe_api_error(json.dumps(response))}"
        )
    print(
        f"Cloud Assistant accepted website deploy (invoke_id={invoke_id}); waiting for completion."
    )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(4)
        status_response = describe_invocation(
            endpoint=endpoint,
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region=region,
            invoke_id=invoke_id,
        )
        status = find_first(status_response, "InvocationStatus")
        if status in TERMINAL_STATUSES:
            if status == "Success":
                print("website deployment completed via Cloud Assistant")
                return
            exit_code = find_first(status_response, "ExitCode")
            output = find_first(status_response, "Output")
            detail = f"status={status}"
            if exit_code:
                detail += f", exit_code={exit_code}"
            if output:
                detail += f", output={output[:600]}"
            raise CloudAssistantError(f"website deployment failed via Cloud Assistant ({detail})")
    raise CloudAssistantError(
        f"website deployment timed out waiting for Cloud Assistant invoke_id={invoke_id}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", required=True, help="Guanlan MAJOR.MINOR.PATCH version to deploy"
    )
    parser.add_argument(
        "--timeout-seconds", type=int, default=720, help="Cloud Assistant polling budget in seconds"
    )
    args = parser.parse_args()
    if args.timeout_seconds < 30 or args.timeout_seconds > 1800:
        parser.error("--timeout-seconds must be between 30 and 1800")
    try:
        deploy(args.version, timeout_seconds=args.timeout_seconds)
    except CloudAssistantError as exc:
        print(f"Cloud Assistant website deployment failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
