# -*- coding: utf-8 -*-
"""Higher-level research workflows built on Guanlan evidence packets."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from guanlan.limits import DEFAULT_RESEARCH_LIMIT
from guanlan.web.research import build_research_packet
from guanlan.web.search import detect_recency_intent

Evidence = dict[str, Any]

_DIMENSIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "official",
        "name": "官方/一手口径",
        "roles": {"official_primary", "company_primary", "database_official", "publisher_guideline", "standard_original"},
        "source_keywords": ("政府", "部委", "党央媒", "公司一手", "官方", "学术"),
    },
    {
        "id": "media_industry",
        "name": "媒体/产业叙事",
        "roles": {"authoritative_report", "industry_report", "vertical_report", "market_news", "company_context"},
        "source_keywords": ("媒体", "产业", "商业", "财经", "电商"),
    },
    {
        "id": "user_sample",
        "name": "用户样本/社区反馈",
        "roles": {"user_sample", "community_discussion", "developer_discussion", "review"},
        "source_keywords": ("社交", "社区", "开发者", "内容平台", "评价"),
    },
    {
        "id": "recent",
        "name": "近期动态/时间线",
        "roles": {"fresh_news", "public_discussion", "fresh_trend_signal"},
        "source_keywords": ("热榜", "资讯", "快讯", "RSS"),
        "prefer_dated": True,
    },
    {
        "id": "risk",
        "name": "风险/边界",
        "roles": {"risk", "case_record", "clinical_guideline", "statute_original"},
        "source_keywords": ("法律", "医疗", "财经", "风险"),
        "fallback": "看 source_diagnostics、risk_tags、advisor 和证据审计提示。",
    },
)

_BUCKETS: tuple[dict[str, Any], ...] = (
    {"id": "official", "name": "官方/一手来源", "roles": _DIMENSIONS[0]["roles"], "keywords": _DIMENSIONS[0]["source_keywords"]},
    {"id": "media", "name": "媒体/产业材料", "roles": _DIMENSIONS[1]["roles"], "keywords": _DIMENSIONS[1]["source_keywords"]},
    {"id": "sample", "name": "用户/社区样本", "roles": _DIMENSIONS[2]["roles"], "keywords": _DIMENSIONS[2]["source_keywords"]},
    {"id": "recent", "name": "近期动态", "roles": _DIMENSIONS[3]["roles"], "keywords": _DIMENSIONS[3]["source_keywords"]},
)


def build_compare_report(
    subjects: list[str],
    *,
    focus: str = "",
    preset: str = "general",
    profile: str | None = "china",
    limit: int = DEFAULT_RESEARCH_LIMIT,
    read_top: int = 0,
    search_backend: str = "auto",
    read_backend: str = "auto",
    max_read_chars: int | None = None,
    select_top: int = 6,
) -> dict[str, Any]:
    """Compare multiple subjects by building one evidence packet per subject."""
    clean_subjects = [_collapse_ws(subject) for subject in subjects if _collapse_ws(subject)]
    if len(clean_subjects) < 2:
        raise ValueError("compare requires at least two subjects")
    packets: list[dict[str, Any]] = []
    for subject in clean_subjects:
        query = _subject_query(subject, focus)
        packets.append(
            build_research_packet(
                query,
                preset=preset,
                profile=profile,
                limit=max(limit, 1),
                read_top=max(read_top, 0),
                search_backend=search_backend,
                read_backend=read_backend,
                max_read_chars=max_read_chars,
                advisor=False,
                select_top=max(select_top, 1),
            )
        )
    internal_reports = [_subject_report(subject, packet, select_top=select_top) for subject, packet in zip(clean_subjects, packets)]
    subject_reports = [_strip_internal_packet(report) for report in internal_reports]
    diversity_guard = _compare_source_diversity_guard(internal_reports, focus=focus, preset=preset, profile=profile or "china")
    suggested_next = _compare_next_steps(clean_subjects, focus=focus, preset=preset, profile=profile or "china")
    suggested_next = _unique(suggested_next + list(diversity_guard.get("followup_commands") or []))
    return {
        "mode": "compare",
        "subjects": clean_subjects,
        "focus": _collapse_ws(focus),
        "preset": preset,
        "profile": profile or "",
        "limit": max(limit, 1),
        "read_top": max(read_top, 0),
        "subject_reports": subject_reports,
        "comparison_table": _comparison_table(internal_reports),
        "shared_caveats": _shared_caveats(internal_reports),
        "source_diversity_guard": diversity_guard,
        "suggested_next": suggested_next,
        "boundary": "compare 基于每个对象各自的公开证据包做对照，不代表穷尽事实；结论应回到来源链接继续核验。",
    }


def build_timeline_report(
    query: str,
    *,
    preset: str = "general",
    profile: str | None = "china",
    limit: int = 80,
    read_top: int = 0,
    search_backend: str = "auto",
    read_backend: str = "auto",
    max_read_chars: int | None = None,
    max_events: int = 20,
    order: str = "desc",
) -> dict[str, Any]:
    """Build an event timeline from a Guanlan research packet."""
    clean_query = _collapse_ws(query)
    if not clean_query:
        raise ValueError("query is required")
    packet = build_research_packet(
        clean_query,
        preset=preset,
        profile=profile,
        limit=max(limit, 1),
        read_top=max(read_top, 0),
        search_backend=search_backend,
        read_backend=read_backend,
        max_read_chars=max_read_chars,
        advisor=False,
        select_top=10,
    )
    raw_events, undated = _timeline_from_packet(packet, max_events=max(max_events, 1) * 2, order=order)
    timeline_filter = _timeline_window_filter(clean_query, raw_events, max_events=max(max_events, 1), order=order)
    events = timeline_filter["events"]
    return {
        "mode": "timeline",
        "query": clean_query,
        "preset": preset,
        "profile": profile or "",
        "limit": max(limit, 1),
        "event_count": len(events),
        "events": events,
        "background_events": timeline_filter["background_events"],
        "low_relevance_events": timeline_filter["low_relevance_events"],
        "timeline_quality": timeline_filter["timeline_quality"],
        "undated_evidence": undated[:8],
        "source_diagnostics": packet.get("source_diagnostics", {}),
        "route_plan": packet.get("route_plan", {}),
        "evidence_audit": packet.get("evidence_audit", {}),
        "boundary": "timeline 只抽取公开材料中可见的日期线索；日期新不等于事实更真，缺日期的关键证据会放入 undated_evidence。",
    }


def build_dossier_report(
    entity: str,
    *,
    focus: str = "",
    preset: str = "general",
    profile: str | None = "china",
    limit: int = 80,
    read_top: int = 2,
    search_backend: str = "auto",
    read_backend: str = "auto",
    max_read_chars: int | None = 2400,
    select_top: int = 10,
) -> dict[str, Any]:
    """Build a structured dossier for one company, product, policy, or event."""
    clean_entity = _collapse_ws(entity)
    if not clean_entity:
        raise ValueError("entity is required")
    query = _subject_query(clean_entity, focus)
    packet = build_research_packet(
        query,
        preset=preset,
        profile=profile,
        limit=max(limit, 1),
        read_top=max(read_top, 0),
        search_backend=search_backend,
        read_backend=read_backend,
        max_read_chars=max_read_chars,
        advisor=True,
        advisor_style="brief",
        select_top=max(select_top, 1),
    )
    events, undated = _timeline_from_packet(packet, max_events=10, order="desc")
    sections = _dossier_sections(packet)
    return {
        "mode": "dossier",
        "entity": clean_entity,
        "focus": _collapse_ws(focus),
        "query": query,
        "preset": preset,
        "profile": profile or "",
        "result_count": packet.get("result_count", 0),
        "source_mix": packet.get("source_mix", {}),
        "source_diagnostics": packet.get("source_diagnostics", {}),
        "route_plan": packet.get("route_plan", {}),
        "read_quality_summary": packet.get("read_quality_summary", {}),
        "sections": sections,
        "timeline": events,
        "undated_evidence": undated[:6],
        "evidence_audit": packet.get("evidence_audit", {}),
        "advisor": packet.get("advisor", {}),
        "open_questions": _dossier_open_questions(packet, sections),
        "suggested_next": _dossier_next_steps(clean_entity, focus=focus, preset=preset, profile=profile or "china"),
        "boundary": "dossier 是一份可继续研究的档案骨架，不是最终结论；请保留来源差异并对关键事实回读原文。",
    }


def format_compare_markdown(report: dict[str, Any]) -> str:
    """Render a compare report as Markdown."""
    subjects = [str(item) for item in report.get("subjects") or []]
    lines = ["# 观澜对比研究", "", f"- 对象: {', '.join(subjects)}"]
    if report.get("focus"):
        lines.append(f"- 关注点: {report['focus']}")
    lines.extend([f"- 边界: {report.get('boundary', '')}", "", "## 对比表", ""])
    header = "维度 | " + " | ".join(_pipe_safe(subject) for subject in subjects)
    lines.append(header)
    lines.append("--- | " + " | ".join("---" for _ in subjects))
    for row in report.get("comparison_table") or []:
        values = row.get("values") or {}
        lines.append(
            f"{_pipe_safe(str(row.get('name') or row.get('id') or '维度'))} | "
            + " | ".join(_pipe_safe(str(values.get(subject) or "证据不足")) for subject in subjects)
        )
    lines.extend(["", "## 各对象代表证据"])
    for subject_report in report.get("subject_reports") or []:
        lines.extend(["", f"### {subject_report.get('subject')}"])
        lines.append(f"- 结果数: {subject_report.get('result_count', 0)}")
        source_mix = subject_report.get("source_mix") or {}
        diversity_guard = subject_report.get("source_diversity_guard") or {}
        if source_mix:
            lines.append("- 信源: " + "；".join(f"{key}: {value}" for key, value in list(source_mix.items())[:5]))
        if isinstance(diversity_guard, dict) and diversity_guard.get("status") == "warn":
            lines.append(f"- 信源护栏: {diversity_guard.get('message', '')}")
        for item in subject_report.get("top_evidence") or []:
            lines.append(f"- {item.get('evidence_role') or 'evidence'} | {item.get('title')} | {item.get('url')}")
    caveats = report.get("shared_caveats") or []
    if caveats:
        lines.extend(["", "## 共同边界"])
        lines.extend(f"- {item}" for item in caveats)
    lines.extend(["", "## 建议下一步"])
    lines.extend(f"- `{item}`" for item in report.get("suggested_next") or [])
    return "\n".join(lines)


def format_timeline_markdown(report: dict[str, Any]) -> str:
    """Render a timeline report as Markdown."""
    lines = [f"# 观澜时间线 / {report.get('query', '')}", "", f"- 边界: {report.get('boundary', '')}"]
    diagnostics = report.get("source_diagnostics") or {}
    if diagnostics:
        lines.append(
            "- 信源概览: "
            f"source_type={diagnostics.get('source_type_count', 0)} "
            f"domain={diagnostics.get('domain_count', 0)} "
            f"freshness={diagnostics.get('freshness_avg', 0)}"
        )
    timeline_quality = report.get("timeline_quality") or {}
    if timeline_quality:
        lines.append(
            "- 时间窗质量: "
            f"status={timeline_quality.get('status', '')} "
            f"in_window={timeline_quality.get('in_window_count', 0)} "
            f"background={timeline_quality.get('background_count', 0)}"
        )
    events = report.get("events") or []
    lines.extend(["", "## 时间线"])
    if not events:
        lines.append("暂无可抽取日期的证据；请扩大结果池或补充带日期的一手来源。")
    for item in events:
        lines.append(f"- {item.get('date')} | {item.get('title')} | {item.get('url')}")
        if item.get("snippet"):
            lines.append(f"  - 摘要: {item.get('snippet')}")
        lines.append(f"  - 来源类型: {item.get('source_type', '通用网页')} / 证据角色: {item.get('evidence_role', '')}")
    undated = report.get("undated_evidence") or []
    if undated:
        lines.extend(["", "## 无日期但可能重要的证据"])
        for item in undated[:6]:
            lines.append(f"- {item.get('title')} | {item.get('url')}")
    return "\n".join(lines)


def format_dossier_markdown(report: dict[str, Any]) -> str:
    """Render a dossier report as Markdown."""
    lines = [f"# 观澜研究档案 / {report.get('entity', '')}", "", f"- Query: {report.get('query', '')}", f"- 边界: {report.get('boundary', '')}"]
    source_mix = report.get("source_mix") or {}
    if source_mix:
        lines.append("- 信源: " + "；".join(f"{key}: {value}" for key, value in list(source_mix.items())[:6]))
    read_quality = report.get("read_quality_summary") or {}
    if read_quality:
        lines.append(
            "- 阅读质量: "
            f"usable={read_quality.get('usable_count', 0)}/{read_quality.get('count', 0)} "
            f"avg={read_quality.get('avg_score', 0)}"
        )
    for section in report.get("sections") or []:
        lines.extend(["", f"## {section.get('name')}"])
        if section.get("boundary"):
            lines.append(f"- 边界: {section['boundary']}")
        items = section.get("items") or []
        if not items:
            lines.append("- 暂无足够证据。")
            continue
        for item in items:
            lines.append(f"- {item.get('title')} | {item.get('url')}")
            if item.get("snippet"):
                lines.append(f"  - {item.get('snippet')}")
            lines.append(f"  - {item.get('source_type', '通用网页')} / {item.get('evidence_role', '')}")
    if report.get("timeline"):
        lines.extend(["", "## 近期时间线"])
        for item in report["timeline"][:8]:
            lines.append(f"- {item.get('date')} | {item.get('title')} | {item.get('url')}")
    questions = report.get("open_questions") or []
    if questions:
        lines.extend(["", "## 待核验问题"])
        lines.extend(f"- {item}" for item in questions)
    lines.extend(["", "## 建议下一步"])
    lines.extend(f"- `{item}`" for item in report.get("suggested_next") or [])
    return "\n".join(lines)


def format_workflow_context(report: dict[str, Any], title: str = "观澜研究上下文") -> str:
    """Render a compact context form for agents."""
    mode = str(report.get("mode") or "workflow")
    if mode == "compare":
        return format_compare_markdown(report)
    if mode == "timeline":
        return format_timeline_markdown(report)
    if mode == "dossier":
        return format_dossier_markdown(report)
    return f"# {title}\n\n{report}"


def _subject_query(subject: str, focus: str) -> str:
    return _collapse_ws(f"{subject} {focus}" if focus else subject)


def _subject_report(subject: str, packet: dict[str, Any], *, select_top: int) -> dict[str, Any]:
    evidence = list(packet.get("selected_evidence") or packet.get("results") or [])
    return {
        "subject": subject,
        "query": packet.get("query", subject),
        "result_count": packet.get("result_count", len(packet.get("results") or [])),
        "source_mix": packet.get("source_mix", {}),
        "source_diagnostics": packet.get("source_diagnostics", {}),
        "read_quality_summary": packet.get("read_quality_summary", {}),
        "role_counts": _role_counts(evidence),
        "source_diversity_guard": _subject_source_diversity_guard(subject, evidence, packet),
        "top_evidence": _compact_evidence(evidence, limit=max(select_top, 1)),
        "packet": packet,
    }


def _strip_internal_packet(report: dict[str, Any]) -> dict[str, Any]:
    """Drop the heavy raw packet from public workflow output."""
    return {key: value for key, value in report.items() if key != "packet"}


def _comparison_table(subject_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension in _DIMENSIONS:
        values = {}
        for subject_report in subject_reports:
            values[str(subject_report["subject"])] = _dimension_summary(subject_report, dimension)
        rows.append({"id": dimension["id"], "name": dimension["name"], "values": values})
    return rows


def _dimension_summary(subject_report: dict[str, Any], dimension: dict[str, Any]) -> str:
    packet = subject_report.get("packet") or {}
    evidence = list(packet.get("selected_evidence") or packet.get("results") or [])
    matched = [item for item in evidence if _matches_dimension(item, dimension)]
    if dimension.get("prefer_dated"):
        matched = [item for item in matched if _extract_date(_evidence_text(item))] or matched
    if matched:
        item = matched[0]
        return _collapse_ws(f"{item.get('title', '')}（{item.get('source_type', '通用网页')}）")[:96]
    fallback = str(dimension.get("fallback") or "")
    if fallback:
        return fallback
    diagnostics = subject_report.get("source_diagnostics") or {}
    warnings = diagnostics.get("warnings") or []
    if warnings:
        return str(warnings[0])[:96]
    return "证据不足，需补搜该维度。"


def _matches_dimension(item: Evidence, dimension: dict[str, Any]) -> bool:
    role = str(item.get("evidence_role") or "")
    source_type = str(item.get("source_type") or "")
    if role in set(dimension.get("roles") or set()):
        return True
    return any(keyword in source_type for keyword in dimension.get("source_keywords") or [])


def _shared_caveats(subject_reports: list[dict[str, Any]]) -> list[str]:
    caveats = [
        "不同对象的公开资料密度可能不同，结果数量不等于真实市场声量。",
        "用户样本和社区讨论只代表公开样本，不代表总体民意。",
    ]
    for report in subject_reports:
        diagnostics = report.get("source_diagnostics") or {}
        for warning in diagnostics.get("warnings") or []:
            text = str(warning)
            if text not in caveats:
                caveats.append(text)
    return caveats[:6]


def _compare_next_steps(subjects: list[str], *, focus: str, preset: str, profile: str) -> list[str]:
    joined = " ".join(subjects)
    focus_arg = f" --focus {focus!r}" if focus else ""
    timeline_query = _subject_query(joined, focus)
    return [
        f"guanlan compare {' '.join(repr(subject) for subject in subjects)}{focus_arg} --preset {preset} --profile {profile} --limit 80",
        f"guanlan timeline {timeline_query!r} --profile {profile} --limit 80",
        f"guanlan dossier {repr(subjects[0])} --profile {profile} --limit 80",
    ]


def _subject_source_diversity_guard(subject: str, evidence: list[Evidence], packet: dict[str, Any]) -> dict[str, Any]:
    domains = [str(item.get("domain") or _domain(str(item.get("url") or ""))) for item in evidence if item.get("url")]
    source_types = [str(item.get("source_type") or "") for item in evidence if item.get("source_type")]
    domain_counts = _counts(domains)
    type_counts = _counts(source_types)
    total = max(len(evidence), 1)
    top_domain, top_domain_count = _top_count(domain_counts)
    top_type, top_type_count = _top_count(type_counts)
    warnings: list[str] = []
    if top_domain_count >= 3 and top_domain_count / total >= 0.6:
        warnings.append(f"{subject} 证据被 `{top_domain}` 高度支配，可能只有单站样本。")
    if top_type_count >= 4 and top_type_count / total >= 0.75:
        warnings.append(f"{subject} 证据主要来自 `{top_type}`，缺少对照来源。")
    diagnostics = packet.get("source_diagnostics") or {}
    for warning in diagnostics.get("warnings") or []:
        text = str(warning)
        if "域名集中" in text or "来源类型" in text:
            warnings.append(text)
    status = "warn" if warnings else "ok"
    return {
        "status": status,
        "domain_count": len(domain_counts),
        "source_type_count": len(type_counts),
        "top_domain": top_domain,
        "top_domain_ratio": round(top_domain_count / total, 3),
        "top_source_type": top_type,
        "top_source_type_ratio": round(top_type_count / total, 3),
        "warnings": _unique(warnings),
        "message": "；".join(_unique(warnings)[:2]) if warnings else "信源分布可用。",
    }


def _compare_source_diversity_guard(
    subject_reports: list[dict[str, Any]],
    *,
    focus: str,
    preset: str,
    profile: str,
) -> dict[str, Any]:
    weak_subjects = [
        str(report.get("subject") or "")
        for report in subject_reports
        if (report.get("source_diversity_guard") or {}).get("status") == "warn"
    ]
    if not weak_subjects:
        return {"status": "ok", "weak_subjects": [], "followup_commands": []}
    followups: list[str] = []
    for subject in weak_subjects[:3]:
        query = _subject_query(subject, focus)
        followups.extend(
            [
                f"guanlan dossier {query!r} --profile {profile} --limit 80 --format context",
                f"guanlan research {query!r} --preset company --profile {profile} --limit 80 --read-top 2",
                f"guanlan search {query!r} --scope company_primary --profile {profile} --limit 80 --trace",
            ]
        )
        if preset in {"tech", "general"}:
            followups.append(f"guanlan search {query!r} --scope tech_dev --profile {profile} --limit 80 --trace")
    return {
        "status": "warn",
        "weak_subjects": weak_subjects,
        "message": "部分对象证据被单一域名或单一来源类型支配，需要补公司一手、垂直媒体或社区样本。",
        "followup_commands": _unique(followups)[:8],
    }


def _timeline_from_packet(packet: dict[str, Any], *, max_events: int, order: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence = _packet_evidence(packet)
    events: list[dict[str, Any]] = []
    undated: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in evidence:
        text = _evidence_text(item)
        date_value = _extract_date(text)
        compact = _compact_item(item)
        if not date_value:
            undated.append(compact)
            continue
        key = (date_value, str(item.get("url") or item.get("title") or ""))
        if key in seen:
            continue
        seen.add(key)
        events.append({"date": date_value, **compact})
    reverse = order != "asc"
    events = sorted(events, key=lambda item: item.get("date", ""), reverse=reverse)[:max_events]
    return events, undated


def _timeline_window_filter(query: str, events: list[dict[str, Any]], *, max_events: int, order: str) -> dict[str, Any]:
    recency = detect_recency_intent(query)
    if not recency.get("enabled"):
        selected = events[:max_events]
        return {
            "events": selected,
            "background_events": [],
            "low_relevance_events": [],
            "timeline_quality": {
                "status": "ok" if selected else "warn",
                "time_window_enabled": False,
                "in_window_count": len(selected),
                "background_count": 0,
                "low_relevance_count": 0,
                "message": "未检测到显式时间窗；按证据日期排序。",
            },
        }
    start = _safe_iso_date(str(recency.get("start_date") or ""))
    end = _safe_iso_date(str(recency.get("end_date") or ""))
    query_terms = _timeline_query_terms(query)
    in_window: list[dict[str, Any]] = []
    background: list[dict[str, Any]] = []
    low_relevance: list[dict[str, Any]] = []
    for item in events:
        event_date = _safe_iso_date(str(item.get("date") or ""))
        if not _timeline_item_relevant(item, query_terms):
            low_relevance.append(item)
            continue
        if start and end and event_date and start <= event_date <= end:
            in_window.append(item)
        else:
            background.append(item)
    reverse = order != "asc"
    in_window = sorted(in_window, key=lambda item: item.get("date", ""), reverse=reverse)[:max_events]
    status = "ok" if in_window else "warn"
    return {
        "events": in_window,
        "background_events": sorted(background, key=lambda item: item.get("date", ""), reverse=reverse)[:8],
        "low_relevance_events": low_relevance[:8],
        "timeline_quality": {
            "status": status,
            "time_window_enabled": True,
            "label": recency.get("label") or "",
            "start_date": recency.get("start_date") or "",
            "end_date": recency.get("end_date") or "",
            "in_window_count": len(in_window),
            "background_count": len(background),
            "low_relevance_count": len(low_relevance),
            "message": (
                "主时间线已按显式时间窗收束；窗口外事件只作背景。"
                if in_window
                else "未抽到窗口内事件；不要把窗口外事件写成主线进展。"
            ),
        },
    }


def _packet_evidence(packet: dict[str, Any]) -> list[Evidence]:
    rows: list[Evidence] = []
    seen_urls: set[str] = set()
    for item in list(packet.get("selected_evidence") or []) + list(packet.get("results") or []) + list(packet.get("readings") or []):
        url = str(item.get("url") or "")
        key = url or str(item.get("title") or "")
        if key in seen_urls:
            continue
        seen_urls.add(key)
        rows.append(item)
    return rows


def _dossier_sections(packet: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = list(packet.get("selected_evidence") or packet.get("results") or [])
    sections = []
    for bucket in _BUCKETS:
        items = [item for item in evidence if _bucket_match(item, bucket)]
        sections.append(
            {
                "id": bucket["id"],
                "name": bucket["name"],
                "items": _compact_evidence(items[:6], limit=6),
                "boundary": _bucket_boundary(bucket["id"]),
            }
        )
    sections.append(
        {
            "id": "selected",
            "name": "综合代表证据",
            "items": _compact_evidence(evidence[:8], limit=8),
            "boundary": "用于快速把握材料面，不替代逐条回读。",
        }
    )
    return sections


def _bucket_match(item: Evidence, bucket: dict[str, Any]) -> bool:
    role = str(item.get("evidence_role") or "")
    source_type = str(item.get("source_type") or "")
    if role in set(bucket.get("roles") or set()):
        return True
    return any(keyword in source_type for keyword in bucket.get("keywords") or [])


def _bucket_boundary(bucket_id: str) -> str:
    return {
        "official": "优先作为事实口径，但仍需注意发布时间和适用范围。",
        "media": "适合背景和产业叙事，不等同于官方结论。",
        "sample": "公开样本有平台偏差，不能写成总体民意。",
        "recent": "新材料可能修正旧材料，但日期新不代表事实更真。",
    }.get(bucket_id, "作为补充证据使用。")


def _dossier_open_questions(packet: dict[str, Any], sections: list[dict[str, Any]]) -> list[str]:
    questions: list[str] = []
    missing = [section["name"] for section in sections if section.get("id") != "selected" and not section.get("items")]
    if missing:
        questions.append("缺少这些证据面：" + "、".join(missing[:4]) + "。")
    diagnostics = packet.get("source_diagnostics") or {}
    questions.extend(str(item) for item in diagnostics.get("warnings") or [])
    audit = packet.get("evidence_audit") or {}
    questions.extend(str(item) for item in audit.get("warnings") or [])
    if not questions:
        questions.append("继续核验关键数字、发布时间、官方原文和不同平台样本偏差。")
    return _unique(questions)[:8]


def _dossier_next_steps(entity: str, *, focus: str, preset: str, profile: str) -> list[str]:
    query = _subject_query(entity, focus)
    return [
        f"guanlan timeline {query!r} --profile {profile} --limit 80",
        f"guanlan research {query!r} --preset {preset} --profile {profile} --limit 80 --advisor",
        f"guanlan archive ingest-research {query!r} --limit 80 --select-top 8",
    ]


def _role_counts(evidence: list[Evidence]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in evidence:
        role = str(item.get("evidence_role") or "unknown")
        counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items(), key=lambda row: (-row[1], row[0])))


def _compact_evidence(items: list[Evidence], *, limit: int) -> list[dict[str, Any]]:
    return [_compact_item(item) for item in items[:limit]]


def _compact_item(item: Evidence) -> dict[str, Any]:
    return {
        "title": _collapse_ws(str(item.get("title") or ""))[:140],
        "url": str(item.get("url") or ""),
        "domain": str(item.get("domain") or ""),
        "snippet": _collapse_ws(str(item.get("snippet") or item.get("content") or ""))[:220],
        "source_type": str(item.get("source_type") or "通用网页"),
        "evidence_role": str(item.get("evidence_role") or ""),
        "score": item.get("score", 0),
    }


def _evidence_text(item: Evidence) -> str:
    return _collapse_ws(
        " ".join(
            str(item.get(key) or "")
            for key in ("published_at", "date", "updated_at", "title", "snippet", "summary", "content")
        )
    )


def _extract_date(text: str) -> str:
    text = text or ""
    patterns = (
        r"(?P<year>20\d{2})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})",
        r"(?P<year>20\d{2})年\s*(?P<month>\d{1,2})月\s*(?P<day>\d{1,2})日?",
        r"(?P<year>20\d{2})[-/.](?P<month>\d{1,2})",
        r"(?P<year>20\d{2})年\s*(?P<month>\d{1,2})月",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.groupdict().get("day") or 1)
        try:
            return dt.date(year, month, day).isoformat()
        except ValueError:
            continue
    return ""


def _timeline_query_terms(query: str) -> list[str]:
    stop = {"最新", "近期", "最近", "时间线", "进展", "动态", "today", "latest", "news"}
    terms = []
    for term in re.findall(r"[\u4e00-\u9fffA-Za-z0-9_+-]{2,}", query):
        if term in stop or re.fullmatch(r"20\d{2}", term):
            continue
        terms.append(term.lower())
    return _unique(terms)[:12]


def _timeline_item_relevant(item: dict[str, Any], terms: list[str]) -> bool:
    if not terms:
        return True
    text = _collapse_ws(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('url', '')}").lower()
    return any(term in text for term in terms[:8])


def _safe_iso_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", url or "", flags=re.I)
    if not match:
        return ""
    host = match.group(1).lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _counts(items: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not item:
            continue
        counts[item] = counts.get(item, 0) + 1
    return counts


def _top_count(counts: dict[str, int]) -> tuple[str, int]:
    if not counts:
        return "", 0
    return sorted(counts.items(), key=lambda row: (-row[1], row[0]))[0]


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _pipe_safe(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        clean = _collapse_ws(item)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        output.append(clean)
    return output
