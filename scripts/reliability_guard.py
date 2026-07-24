#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail closed when deterministic Guanlan quality drops below a release baseline.

The guard intentionally evaluates only deterministic reports.  It does not
turn transient public-network conditions into a release verdict; those belong
to live-smoke and distribution diagnostics.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "docs" / "reports" / "reliability-baseline-v0.7.9.json"
COMMANDS: dict[str, list[str]] = {
    "quality_regression": ["uv", "run", "guanlan", "quality", "regression", "--format", "json"],
    "quality_robustness": ["uv", "run", "guanlan", "quality", "robustness", "--format", "json"],
    "benchmark": ["uv", "run", "guanlan", "eval", "benchmark", "--format", "json"],
    "eval_suite": ["uv", "run", "guanlan", "eval", "suite", "run", "chinese-web-v1", "--format", "json"],
}


def run_command(command: list[str]) -> dict[str, Any]:
    process = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
    return {"returncode": process.returncode, "stdout": process.stdout, "stderr": process.stderr}


def load_baseline(path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "guanlan_reliability_baseline_v1":
        raise ValueError(f"unsupported reliability baseline: {path}")
    if not isinstance(payload.get("checks"), dict) or not payload["checks"]:
        raise ValueError(f"reliability baseline has no checks: {path}")
    return payload


def compare_summary(summary: dict[str, Any], threshold: dict[str, Any]) -> list[str]:
    """Return concrete reliability regressions; an empty list is a pass."""

    actual = {key: float(summary.get(key) or 0) for key in ("total", "pass", "warn", "fail", "score")}
    failures = []
    if actual["total"] < float(threshold.get("minimum_total") or 0):
        failures.append(f"total {actual['total']:g} < {threshold['minimum_total']}")
    if actual["pass"] < float(threshold.get("minimum_pass") or 0):
        failures.append(f"pass {actual['pass']:g} < {threshold['minimum_pass']}")
    if actual["warn"] > float(threshold.get("maximum_warn") or 0):
        failures.append(f"warn {actual['warn']:g} > {threshold['maximum_warn']}")
    if actual["fail"] > float(threshold.get("maximum_fail") or 0):
        failures.append(f"fail {actual['fail']:g} > {threshold['maximum_fail']}")
    if actual["score"] < float(threshold.get("minimum_score") or 0):
        failures.append(f"score {actual['score']:g} < {threshold['minimum_score']}")
    return failures


def build_guard_report(
    *,
    baseline: dict[str, Any],
    run: Callable[[list[str]], dict[str, Any]] = run_command,
) -> dict[str, Any]:
    checks = []
    for name, threshold in baseline["checks"].items():
        command = COMMANDS.get(name)
        if command is None:
            checks.append({"name": name, "status": "fail", "reason": "unknown baseline check"})
            continue
        result = run(command)
        if result.get("returncode") != 0:
            checks.append(
                {
                    "name": name,
                    "status": "fail",
                    "reason": "command failed",
                    "detail": _trim(str(result.get("stderr") or result.get("stdout") or "")),
                }
            )
            continue
        try:
            payload = json.loads(str(result.get("stdout") or ""))
        except json.JSONDecodeError:
            checks.append({"name": name, "status": "fail", "reason": "invalid JSON output"})
            continue
        summary = dict(payload.get("summary") or {})
        regressions = compare_summary(summary, threshold)
        checks.append(
            {
                "name": name,
                "status": "pass" if not regressions else "fail",
                "summary": summary,
                "threshold": threshold,
                "regressions": regressions,
            }
        )
    return {
        "schema_version": "guanlan_reliability_guard_v1",
        "reference_version": baseline.get("reference_version"),
        "status": "pass" if all(item["status"] == "pass" for item in checks) else "fail",
        "checks": checks,
        "boundary": baseline.get("boundary"),
    }


def _trim(value: str, limit: int = 400) -> str:
    return " ".join(value.split())[:limit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check deterministic Guanlan reliability against a baseline.")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    report = build_guard_report(baseline=load_baseline(Path(args.baseline)))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"reliability guard: {report['status']} (baseline v{report.get('reference_version')})")
        for item in report["checks"]:
            detail = "; ".join(item.get("regressions") or [str(item.get("reason") or "")])
            print(f"- {item['name']}: {item['status']}{f' - {detail}' if detail else ''}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
