# -*- coding: utf-8 -*-
"""Replay the 2026-05-18 Guanlan stress-report queries against current behavior."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from guanlan import webtools

STRESS_REPORT_FIXTURE = Path(__file__).resolve().parent / "data" / "stress_report_20260518.jsonl"


def load_stress_report_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    fixture = Path(path).expanduser() if path else STRESS_REPORT_FIXTURE
    cases: list[dict[str, Any]] = []
    for line in fixture.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            cases.append(json.loads(text))
    return cases


def replay_stress_report(
    *,
    path: str | Path | None = None,
    limit: int = 10,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    cases = load_stress_report_cases(path)
    selected = {item.strip() for item in case_ids or [] if item.strip()}
    if selected:
        cases = [case for case in cases if str(case.get("id") or "") in selected]
    rows = [replay_stress_case(case, limit=limit) for case in cases]
    pass_count = sum(1 for row in rows if row["status"] == "pass")
    warn_count = sum(1 for row in rows if row["status"] == "warn")
    return {
        "fixture": str(Path(path).expanduser() if path else STRESS_REPORT_FIXTURE),
        "limit": max(int(limit or 0), 1),
        "summary": {
            "total": len(rows),
            "pass": pass_count,
            "warn": warn_count,
            "score": round(pass_count / max(len(rows), 1) * 100, 1),
        },
        "cases": rows,
        "principle": "这是 live replay：用当前 Guanlan 行为复跑历史压测词，帮助发现语义改写、垂直路由和公网结果质量是否继续漂移。",
    }


def replay_stress_case(case: dict[str, Any], *, limit: int = 10) -> dict[str, Any]:
    query = str(case.get("query") or "")
    profile = str(case.get("profile") or "china")
    results = webtools.search_web(query, profile=profile, limit=max(int(limit or 0), 1), trace=True)
    if results:
        trace = dict(results[0].get("trace") or {})
    else:
        trace = dict(getattr(results, "diagnostics", {}) or {})
    route_plan = dict(trace.get("route_plan") or {})
    query_quality = dict(trace.get("query_quality") or {})
    quality_summary = dict(trace.get("quality_summary") or {})
    query_shape = dict(trace.get("query_shape") or {})
    route_intents = list(route_plan.get("primary_intents") or []) + list(route_plan.get("secondary_intents") or [])
    expected_intents = {str(item) for item in case.get("expected_intents_any", []) if str(item)}
    route_match = bool(set(route_intents) & expected_intents) if expected_intents else True
    result_count = len(results)
    preferred_hit_count = int(quality_summary.get("preferred_hit_count") or 0)
    warnings = [str(item) for item in quality_summary.get("warnings") or []]
    status = "pass" if route_match and result_count > 0 and preferred_hit_count > 0 else "warn"
    top_results = []
    for item in list(results)[:3]:
        top_results.append(
            {
                "title": str(item.get("title") or ""),
                "domain": str(item.get("domain") or ""),
                "source_type": str(item.get("source_type") or ""),
                "evidence_role": str(item.get("evidence_role") or ""),
                "url": str(item.get("url") or ""),
            }
        )
    return {
        "id": str(case.get("id") or ""),
        "category": str(case.get("category") or "general"),
        "query": query,
        "profile": profile,
        "status": status,
        "expected_intents_any": sorted(expected_intents),
        "route_intents": route_intents,
        "route_match": route_match,
        "quality_intent": str(query_quality.get("intent") or ""),
        "rewritten_query": str(query_shape.get("backend_query") or query),
        "semantic_rules": list(query_shape.get("semantic_rules") or []),
        "result_count": result_count,
        "preferred_hit_count": preferred_hit_count,
        "quality_status": str(quality_summary.get("quality_status") or ""),
        "warnings": warnings[:5],
        "source_mix": dict(quality_summary.get("source_mix") or {}),
        "top_results": top_results,
    }


def format_stress_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# Guanlan Stress Report Replay",
        "",
        f"- fixture: {report.get('fixture', '')}",
        f"- limit: {report.get('limit', 0)}",
        f"- score: {summary.get('score', 0)}",
        f"- status: pass={summary.get('pass', 0)} warn={summary.get('warn', 0)}",
        f"- principle: {report.get('principle', '')}",
        "",
        "## Cases",
    ]
    for case in report.get("cases") or []:
        lines.append(
            f"- [{case.get('status')}] {case.get('id')}: {case.get('query')} "
            f"route={','.join(case.get('route_intents') or []) or 'general'} "
            f"quality={case.get('quality_intent') or 'general'} "
            f"results={case.get('result_count', 0)} preferred={case.get('preferred_hit_count', 0)}"
        )
        if case.get("rewritten_query") and case.get("rewritten_query") != case.get("query"):
            lines.append(f"  rewritten: {case.get('rewritten_query')}")
        if case.get("warnings"):
            lines.append(f"  warnings: {'；'.join(case.get('warnings') or [])}")
    return "\n".join(lines)
