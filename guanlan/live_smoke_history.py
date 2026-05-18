# -*- coding: utf-8 -*-
"""Optional trend history for Guanlan live smoke probes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LIVE_SMOKE_HISTORY_PATH = Path.home() / ".guanlan" / "quality" / "live-smoke-history.jsonl"


def attach_live_smoke_trend(
    report: dict[str, Any],
    *,
    history_path: str | Path | None = None,
    trend_window: int = 10,
    record_history: bool = False,
) -> dict[str, Any]:
    """Attach a non-blocking trend report and optionally append the run to history."""

    path = Path(history_path).expanduser() if history_path else DEFAULT_LIVE_SMOKE_HISTORY_PATH
    previous = read_live_smoke_history(path) if (history_path is not None or record_history) else []
    current = live_smoke_record(report)
    window = max(int(trend_window or 0), 1)
    trend = build_live_smoke_trend(previous + [current], window=window)
    trend["history_path"] = str(path)
    trend["recorded"] = bool(record_history)
    report["live_trend_report"] = trend
    if record_history:
        append_live_smoke_history(current, path)
    return report


def live_smoke_record(report: dict[str, Any]) -> dict[str, Any]:
    """Convert a quality report into a compact JSONL-safe history record."""

    checks = []
    for item in report.get("checks") or []:
        checks.append(
            {
                "id": str(item.get("id") or ""),
                "status": str(item.get("status") or "warn"),
                "scenario_group": str(item.get("scenario_group") or "misc"),
                "dimension": str(item.get("dimension") or ""),
                "message": str(item.get("message") or ""),
            }
        )
    return {
        "recorded_at": _utc_now(),
        "mode": report.get("mode", "live"),
        "summary": dict(report.get("summary") or {}),
        "network_summary": dict(report.get("network_summary") or {}),
        "contract": {
            "profile": (report.get("contract") or {}).get("profile"),
            "timeout_budget_seconds": (report.get("contract") or {}).get("timeout_budget_seconds"),
        },
        "checks": checks,
    }


def read_live_smoke_history(path: str | Path) -> list[dict[str, Any]]:
    """Read JSONL history, skipping malformed lines instead of failing probes."""

    history_path = Path(path).expanduser()
    if not history_path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def append_live_smoke_history(record: dict[str, Any], path: str | Path) -> None:
    """Append one live smoke history record, creating the directory on demand."""

    history_path = Path(path).expanduser()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build_live_smoke_trend(records: list[dict[str, Any]], *, window: int = 10) -> dict[str, Any]:
    """Summarize recent live smoke drift without making it a release gate."""

    recent = records[-max(int(window or 0), 1):]
    current = recent[-1] if recent else {}
    previous = recent[-2] if len(recent) >= 2 else {}
    current_status = _check_status_map(current)
    previous_status = _check_status_map(previous)
    current_problematic = {key for key, status in current_status.items() if status in {"warn", "fail"}}
    previous_problematic = {key for key, status in previous_status.items() if status in {"warn", "fail"}}
    recovered = sorted(previous_problematic - current_problematic)
    new_failures = sorted(current_problematic - previous_problematic)
    persistent_failures = sorted(current_problematic & previous_problematic)
    current_checks = list(current.get("checks") or [])
    return {
        "runs_considered": len(recent),
        "latest_run_at": current.get("recorded_at"),
        "groups": _group_status_summary(recent),
        "current_warn_or_fail": sorted(current_problematic),
        "new_failures": new_failures,
        "recovered": recovered,
        "persistent_failures": persistent_failures,
        "likely_network_or_upstream": sum(
            1
            for item in current_checks
            if str(item.get("status") or "") in {"warn", "fail"} and _looks_network_or_upstream(item)
        ),
        "blocking": False,
        "principle": "live-smoke 趋势只帮助发现公网/源站/后端漂移；默认不阻断发版，--strict 仍只看本次 summary.fail。",
    }


def _check_status_map(record: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("id") or ""): str(item.get("status") or "warn")
        for item in record.get("checks") or []
        if item.get("id")
    }


def _group_status_summary(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    for record in records:
        for item in record.get("checks") or []:
            group = str(item.get("scenario_group") or "misc")
            status = str(item.get("status") or "warn")
            bucket = groups.setdefault(group, {"total": 0, "pass": 0, "warn": 0, "fail": 0})
            bucket["total"] += 1
            if status in {"pass", "warn", "fail"}:
                bucket[status] += 1
            else:
                bucket["warn"] += 1
    return groups


def _looks_network_or_upstream(item: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(item.get(key) or "").lower()
        for key in ("id", "dimension", "scenario_group", "message")
    )
    return any(
        term in haystack
        for term in (
            "timeout",
            "timed out",
            "network",
            "upstream",
            "connection",
            "rate",
            "blocked",
            "cache",
            "backend",
            "unavailable",
        )
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
