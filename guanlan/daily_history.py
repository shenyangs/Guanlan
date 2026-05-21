# -*- coding: utf-8 -*-
"""Local history support for Guanlan daily reports."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_DAILY_HISTORY_PATH = "~/.guanlan/daily/history.jsonl"


def resolve_daily_history_path(path: str | None = None) -> Path:
    return Path(path or DEFAULT_DAILY_HISTORY_PATH).expanduser()


def load_daily_history(
    path: str | None = None,
    *,
    query: str = "",
    compare_days: int = 7,
    generated_at: str = "",
) -> list[dict[str, Any]]:
    """Load compact daily history records."""
    history_path = resolve_daily_history_path(path)
    if not history_path.exists():
        return []
    now = _parse_time(generated_at) or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(int(compare_days or 7), 1))
    records: list[dict[str, Any]] = []
    query_key = _normalize_query(query)
    for line in history_path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        created = _parse_time(str(row.get("generated_at") or ""))
        if created and created < cutoff:
            continue
        if query_key and _normalize_query(str(row.get("query") or "")) != query_key:
            continue
        records.append(row)
    return records


def build_daily_history_delta(
    report: dict[str, Any],
    *,
    history_path: str | None = None,
    compare_days: int = 0,
) -> dict[str, Any]:
    """Compare current storylines with recent saved daily history."""
    days = max(int(compare_days or 0), 0)
    if days <= 0:
        return {
            "enabled": False,
            "history_path": str(resolve_daily_history_path(history_path)),
            "compare_days": 0,
            "new_storylines": [],
            "continued_storylines": [],
            "cooled_storylines": [],
            "persistent_risks": [],
        }
    records = load_daily_history(
        history_path,
        query=str(report.get("query") or ""),
        compare_days=days,
        generated_at=str(report.get("generated_at") or ""),
    )
    current = _current_story_map(report.get("storylines") or [])
    previous: dict[str, dict[str, Any]] = {}
    for record in records:
        for story in record.get("storylines") or []:
            if not isinstance(story, dict):
                continue
            key = str(story.get("id") or story.get("headline") or "")
            if key:
                previous[key] = story
    current_keys = set(current)
    previous_keys = set(previous)
    new = [_compact_story(current[key]) for key in sorted(current_keys - previous_keys)]
    continued = [_compact_story(current[key]) for key in sorted(current_keys & previous_keys)]
    cooled = [_compact_story(previous[key]) for key in sorted(previous_keys - current_keys)][:8]
    persistent_risks = [
        _compact_story(current[key])
        for key in sorted(current_keys & previous_keys)
        if str(current[key].get("risk_level") or "") in {"high", "medium"}
        or str(previous[key].get("risk_level") or "") in {"high", "medium"}
    ]
    return {
        "enabled": True,
        "history_path": str(resolve_daily_history_path(history_path)),
        "compare_days": days,
        "records_checked": len(records),
        "new_storylines": new,
        "continued_storylines": continued,
        "cooled_storylines": cooled,
        "persistent_risks": persistent_risks,
    }


def record_daily_history(report: dict[str, Any], *, history_path: str | None = None) -> Path:
    """Append one compact daily report record to history JSONL."""
    path = resolve_daily_history_path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = compact_daily_history_record(report)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def compact_daily_history_record(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "daily_history_v1",
        "generated_at": report.get("generated_at", ""),
        "query": report.get("query", ""),
        "title": report.get("title", ""),
        "time_window": report.get("time_window", ""),
        "edition": report.get("edition", ""),
        "storylines": [_compact_story(story) for story in report.get("storylines") or []],
        "source_health": report.get("source_health") or {},
    }


def _current_story_map(storylines: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for story in storylines:
        if not isinstance(story, dict):
            continue
        key = str(story.get("id") or story.get("headline") or "")
        if key:
            result[key] = story
    return result


def _compact_story(story: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": story.get("id", ""),
        "headline": story.get("headline", ""),
        "freshness": story.get("freshness", ""),
        "risk_level": story.get("risk_level", ""),
        "recommended_action": story.get("recommended_action", ""),
        "confidence": story.get("confidence", ""),
    }


def _parse_time(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_query(value: str) -> str:
    return "".join(str(value or "").lower().split())
