#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check Guanlan distribution surfaces without confusing local TLS errors for stale releases."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE_URLS = (
    "https://guanlan.xin/",
    "https://www.guanlan.xin/",
    "http://101.37.70.222/",
)


@dataclass
class HttpResponse:
    ok: bool
    status_code: int
    body: str
    error: str = ""


def project_version(root: Path = ROOT) -> str:
    match = re.search(
        r'(?m)^version = "([^"]+)"$',
        (root / "pyproject.toml").read_text(encoding="utf-8"),
    )
    return match.group(1) if match else ""


def run_command(args: list[str], *, timeout: int = 30) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:  # pragma: no cover - defensive around local tools.
        return {"returncode": 127, "stdout": "", "stderr": str(exc)}
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def fetch_url(url: str, *, timeout: int = 20) -> HttpResponse:
    request = urllib.request.Request(
        url,
        headers={"Cache-Control": "no-cache", "User-Agent": "guanlan-distribution-status"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return HttpResponse(True, int(resp.status), body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResponse(False, int(exc.code), body, str(exc))
    except Exception as exc:
        return HttpResponse(False, 0, "", str(exc))


def _status(name: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "status": status, **extra}


def _version_from_text(text: str) -> str:
    match = re.search(r"v?([0-9]+(?:\.[0-9]+){1,3})", text or "")
    return match.group(1) if match else ""


def check_github_tag(version: str, run: Callable[[list[str]], dict[str, Any]] = run_command) -> dict[str, Any]:
    tag = f"v{version}"
    result = run(["git", "ls-remote", "--tags", "origin", tag])
    stdout = result.get("stdout", "")
    if result.get("returncode") == 0 and tag in stdout:
        return _status("github_tag", "ok", expected=version, tag=tag)
    return _status(
        "github_tag",
        "stale_or_missing",
        expected=version,
        tag=tag,
        detail=(result.get("stderr") or stdout or "").strip(),
    )


def check_pypi_json(
    version: str,
    fetch: Callable[[str], HttpResponse] = fetch_url,
    package: str = "guanlan",
) -> dict[str, Any]:
    url = f"https://pypi.org/pypi/{package}/json"
    response = fetch(url)
    if not response.ok:
        return _status("pypi_json", "unavailable", expected=version, http_status=response.status_code, error=response.error)
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError:
        return _status("pypi_json", "parse_error", expected=version)
    actual = str((payload.get("info") or {}).get("version") or "")
    return _status("pypi_json", "ok" if actual == version else "stale", expected=version, actual=actual)


def check_pypi_simple(
    version: str,
    fetch: Callable[[str], HttpResponse] = fetch_url,
    package: str = "guanlan",
) -> dict[str, Any]:
    response = fetch(f"https://pypi.org/simple/{package}/")
    if not response.ok:
        return _status("pypi_simple", "unavailable", expected=version, http_status=response.status_code, error=response.error)
    hit = f"{package}-{version}" in response.body
    return _status("pypi_simple", "ok" if hit else "stale", expected=version)


def check_pip_index(
    version: str,
    run: Callable[[list[str]], dict[str, Any]] = run_command,
    package: str = "guanlan",
) -> dict[str, Any]:
    result = run([sys.executable, "-m", "pip", "index", "versions", package, "--index-url", "https://pypi.org/simple"])
    combined = "\n".join([str(result.get("stdout") or ""), str(result.get("stderr") or "")])
    if "CERTIFICATE_VERIFY_FAILED" in combined or "certificate verify failed" in combined:
        return _status("pip_index", "local_tls_error", expected=version, detail=_trim(combined))
    if result.get("returncode") != 0:
        return _status("pip_index", "unavailable", expected=version, detail=_trim(combined))
    match = re.search(r"Available versions:\s*([^\n]+)", combined)
    actual = ""
    if match:
        actual = match.group(1).split(",", 1)[0].strip()
    if not actual:
        actual = _version_from_text(combined)
    return _status("pip_index", "ok" if actual == version else "stale", expected=version, actual=actual)


def check_homebrew_tap(
    version: str,
    fetch: Callable[[str], HttpResponse] = fetch_url,
    tap_repo: str = "shenyangs/homebrew-tap",
    formula_path: str = "Formula/guanlan.rb",
) -> dict[str, Any]:
    url = f"https://raw.githubusercontent.com/{tap_repo}/main/{formula_path}"
    response = fetch(url)
    if not response.ok:
        return _status("homebrew_tap", "unavailable", expected=version, http_status=response.status_code, error=response.error)
    body = response.body
    hit = f"guanlan-{version}.tar.gz" in body or f'version "{version}"' in body
    actual = _version_from_text(body)
    return _status("homebrew_tap", "ok" if hit else "stale", expected=version, actual=actual)


def check_local_entrypoints(
    version: str,
    run: Callable[[list[str]], dict[str, Any]] = run_command,
) -> dict[str, Any]:
    paths_result = run(["bash", "-lc", "which -a guanlan 2>/dev/null | awk 'NF && !seen[$0]++'"])
    paths = [line.strip() for line in str(paths_result.get("stdout") or "").splitlines() if line.strip()]
    if not paths:
        return _status("local_entrypoints", "unavailable", expected=version)
    entries = []
    problems = []
    for path in paths:
        result = run([path, "version"])
        output = "\n".join([str(result.get("stdout") or ""), str(result.get("stderr") or "")])
        actual = _version_from_text(output)
        entry_status = "ok" if actual == version else ("unknown" if not actual else "stale")
        entries.append({"path": path, "version": actual, "status": entry_status})
        if entry_status != "ok":
            problems.append(path)
    return _status(
        "local_entrypoints",
        "ok" if not problems else "stale_or_unknown",
        expected=version,
        entries=entries,
    )


def check_websites(
    version: str,
    fetch: Callable[[str], HttpResponse] = fetch_url,
    urls: tuple[str, ...] = DEFAULT_SITE_URLS,
) -> dict[str, Any]:
    entries = []
    public_problem = False
    source_ok = False
    for url in urls:
        response = fetch(url)
        body = response.body or ""
        if response.ok and f"Guanlan v{version}" in body:
            status = "ok"
        elif response.status_code == 403 and _looks_icp_block(body):
            status = "blocked_icp"
        elif response.ok:
            status = "old_or_unexpected_content"
        else:
            status = "unavailable"
        is_source = url.rstrip("/") == "http://101.37.70.222"
        source_ok = source_ok or (is_source and status == "ok")
        public_problem = public_problem or (not is_source and status != "ok")
        entries.append({"url": url, "status": status, "http_status": response.status_code, "error": response.error})
    if public_problem and source_ok:
        status = "source_deployed_but_public_site_blocked"
    elif any(item["status"] != "ok" for item in entries):
        status = "incomplete"
    else:
        status = "ok"
    return _status("website", status, expected=version, entries=entries)


def build_distribution_report(version: str | None = None) -> dict[str, Any]:
    expected = version or project_version()
    checks = [
        check_github_tag(expected),
        check_pypi_json(expected),
        check_pypi_simple(expected),
        check_pip_index(expected),
        check_homebrew_tap(expected),
        check_websites(expected),
        check_local_entrypoints(expected),
    ]
    hard_fail = [
        item
        for item in checks
        if item["status"] not in {"ok", "local_tls_error", "source_deployed_but_public_site_blocked"}
    ]
    public_incomplete = any(item["status"] == "source_deployed_but_public_site_blocked" for item in checks)
    return {
        "schema_version": "distribution_status_v1",
        "generated_at": _utc_now(),
        "expected_version": expected,
        "status": "fail" if hard_fail else ("incomplete" if public_incomplete else "ok"),
        "checks": checks,
    }


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Guanlan Distribution Status",
        "",
        f"- Expected version: `{report.get('expected_version')}`",
        f"- Status: `{report.get('status')}`",
        f"- Generated at: `{report.get('generated_at')}`",
        "",
        "| Surface | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for item in report.get("checks") or []:
        detail = _check_detail(item)
        if item.get("name") == "website":
            detail = ", ".join(_website_entry_detail(e) for e in item.get("entries") or [])
        if item.get("name") == "local_entrypoints":
            detail = ", ".join(f"{e['path']}={e.get('version') or 'unknown'}" for e in item.get("entries") or [])
        lines.append(f"| `{item.get('name')}` | `{item.get('status')}` | {_escape_table_cell(detail)} |")
    return "\n".join(lines) + "\n"


def _check_detail(item: dict[str, Any]) -> str:
    parts = []
    for key in ("actual", "tag", "detail", "error"):
        value = str(item.get(key) or "").strip()
        if value:
            parts.append(value)
            break
    http_status = item.get("http_status")
    if http_status:
        parts.append(f"HTTP {http_status}")
    return _trim(" ".join(parts))


def _website_entry_detail(entry: dict[str, Any]) -> str:
    url = str(entry.get("url") or "")
    status = str(entry.get("status") or "unknown")
    detail = str(entry.get("error") or "").strip()
    http_status = entry.get("http_status")
    suffix_parts = [part for part in (f"HTTP {http_status}" if http_status else "", detail) if part]
    suffix = f" ({_trim(' '.join(suffix_parts), limit=180)})" if suffix_parts else ""
    return f"{url}={status}{suffix}"


def _escape_table_cell(value: str) -> str:
    return (value or "").replace("|", "\\|")


def _looks_icp_block(body: str) -> bool:
    lower = body.lower()
    return "icp" in lower or "non-compliance" in lower or "备案" in body


def _trim(text: str, limit: int = 500) -> str:
    compact = " ".join((text or "").split())
    return compact[:limit]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Guanlan distribution status.")
    parser.add_argument("--version", default="", help="Expected version. Defaults to pyproject.toml.")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", default="", help="Optional output path.")
    args = parser.parse_args(argv)

    report = build_distribution_report(args.version or None)
    rendered = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else format_markdown(report)
    )
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
