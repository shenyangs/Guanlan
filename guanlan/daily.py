# -*- coding: utf-8 -*-
"""Daily brief assembly for Guanlan.

The daily surface is intentionally workflow-first: it reuses Guanlan's
existing route/search/feeds/hotnews/watch layers to produce a compact,
evidence-bound daily brief without introducing a separate AI summarizer stack.
"""

from __future__ import annotations

import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from guanlan.daily_history import build_daily_history_delta, record_daily_history
from guanlan.daily_quality import (
    annotate_daily_items,
    build_daily_source_health,
    daily_domain,
    daily_is_brand_imitating_domain,
    daily_is_brand_owned,
    daily_is_brand_owned_community,
    daily_is_recognized_external,
    daily_is_search_entrypoint,
    daily_is_soft_seo,
    daily_section_key,
    daily_section_title,
    normalize_daily_time_window,
)
from guanlan.daily_renderers import format_daily_html, format_daily_im
from guanlan.daily_storylines import (
    build_daily_editorial_decisions,
    build_daily_storyline_highlights,
    build_daily_storylines,
)
from guanlan.feeds import fetch_feed_source, recommend_feed_sources, resolve_feed_source
from guanlan.hotnews import build_hotnews_brief, build_trend_report, fetch_hotnews
from guanlan.limits import (
    DEFAULT_FEEDS_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_SEARCH_LIMIT,
)
from guanlan.router import build_route_plan
from guanlan.watch import fire_watch_intent
from guanlan.web.search import search_web

DEFAULT_DAILY_LIMIT = 12
MAX_DAILY_LIMIT = 30
DEFAULT_DAILY_OVERFLOW_LIMIT = 20
MAX_DAILY_OVERFLOW_LIMIT = 80


def build_daily_report(
    query: str = "",
    *,
    watch_id: str = "",
    profile: str = "china",
    scope: str = "",
    site: str = "",
    preset: str = "",
    lens: str = "",
    feed_source: str = "auto",
    watchlist_path: str = "",
    hotnews_source: str = "today",
    search_backend: str = "auto",
    limit: int = DEFAULT_DAILY_LIMIT,
    search_limit: int = DEFAULT_SEARCH_LIMIT,
    feeds_limit: int = 20,
    hotnews_limit: int = 20,
    include_search: bool = True,
    include_feeds: bool = True,
    include_hotnews: bool = True,
    cache_ttl: int = 0,
    store_path: str | None = None,
    read_top: int = 0,
    read_backend: str = "auto",
    max_read_chars: int = 1800,
    overflow_limit: int = DEFAULT_DAILY_OVERFLOW_LIMIT,
    time_window: str = "3d",
    edition: str = "brand",
    record_history: bool = False,
    history_path: str = "",
    compare_days: int = 0,
) -> dict[str, Any]:
    """Build a Guanlan-native daily brief.

    The result favors reproducible evidence entrypoints over prose. It is meant
    to be readable by both humans and agents, then deepened via `read`,
    `research`, or `watch fire --record-seen`.
    """
    clean_query = str(query or "").strip()
    watch_id = str(watch_id or "").strip()
    effective_limit = min(max(int(limit or DEFAULT_DAILY_LIMIT), 1), MAX_DAILY_LIMIT)
    effective_search_limit = max(int(search_limit or DEFAULT_SEARCH_LIMIT), 1)
    effective_feeds_limit = max(int(feeds_limit or DEFAULT_FEEDS_LIMIT), 1)
    effective_hotnews_limit = max(int(hotnews_limit or DEFAULT_HOTNEWS_LIMIT), 1)
    effective_overflow_limit = min(max(int(overflow_limit or 0), 0), MAX_DAILY_OVERFLOW_LIMIT)
    effective_time_window = normalize_daily_time_window(time_window)
    effective_edition = str(edition or "brand").strip().lower()
    if effective_edition not in {"brand", "market", "reputation", "general"}:
        effective_edition = "brand"

    diagnostics: dict[str, Any] = {
        "search": {"status": "skipped", "count": 0, "error": "", "limit": effective_search_limit},
        "feeds": {"status": "skipped", "count": 0, "error": "", "limit": effective_feeds_limit, "source": ""},
        "hotnews": {"status": "skipped", "count": 0, "error": "", "limit": effective_hotnews_limit, "source": hotnews_source},
        "watch": {"status": "skipped", "count": 0, "error": ""},
        "read": {"status": "skipped", "count": 0, "error": "", "limit": max(int(read_top or 0), 0)},
    }
    now_iso = _now_iso()
    route_plan: dict[str, Any] = {}
    report_query = clean_query
    report_title = clean_query or "中文互联网"
    mode = "overview_daily"
    raw_items: list[dict[str, Any]] = []

    if watch_id:
        watch_report = fire_watch_intent(
            watch_id,
            limit=max(effective_limit * 3, 20),
            search_limit=effective_search_limit,
            feed_limit=effective_feeds_limit,
            search_backend=search_backend,
            record_seen=False,
            store_path=store_path,
            cache_ttl=cache_ttl,
        )
        route_plan = dict(watch_report.get("route_plan") or {})
        watch_intent = dict(watch_report.get("intent") or {})
        report_query = str(watch_intent.get("query") or clean_query)
        report_title = str(watch_intent.get("name") or report_query or "长期关注")
        mode = "watch_daily"
        diagnostics["watch"] = {
            "status": "ok",
            "count": len(watch_report.get("items") or []),
            "error": "",
            "intent_id": watch_intent.get("id", ""),
        }
        diagnostics["search"] = dict((watch_report.get("diagnostics") or {}).get("search") or diagnostics["search"])
        diagnostics["feeds"] = dict((watch_report.get("diagnostics") or {}).get("feeds") or diagnostics["feeds"])
        raw_items.extend(_normalize_watch_items(watch_report.get("items") or []))
    elif clean_query:
        route_plan = build_route_plan(
            clean_query,
            preset=preset or "general",
            scope=scope or None,
            site=site or None,
            profile=profile or "china",
            limit=effective_search_limit,
        ).to_dict()
        report_title = clean_query
        mode = "query_daily"
    else:
        route_plan = {
            "query": "",
            "primary_intents": ["hot_trend", "general"],
            "secondary_intents": [],
            "preferred_scopes": [],
            "warnings": ["未提供 query；本日报只做热点与公开订阅发现，不替代定向搜索。"],
        }

    route_intents = [str(item) for item in (route_plan.get("primary_intents") or []) + (route_plan.get("secondary_intents") or []) if str(item)]
    resolved_feed_source = _resolve_daily_feed_source(
        feed_source=feed_source,
        query=report_query,
        route_intents=route_intents,
        preset=preset,
    )
    diagnostics["feeds"]["source"] = resolved_feed_source

    if include_search and clean_query and not watch_id:
        try:
            search_rows = search_web(
                clean_query,
                limit=effective_search_limit,
                site=site or None,
                scope=scope or None,
                backend=search_backend or "auto",
                profile=profile or "china",
                cache_ttl=max(int(cache_ttl or 0), 0),
                recovery_mode="lite",
            )
            raw_items.extend(_normalize_search_items(search_rows))
            diagnostics["search"] = {
                "status": "ok",
                "count": len(search_rows),
                "error": "",
                "limit": effective_search_limit,
                "backend": search_backend or "auto",
            }
        except Exception as exc:
            diagnostics["search"] = {
                "status": "error",
                "count": 0,
                "error": str(exc),
                "limit": effective_search_limit,
                "backend": search_backend or "auto",
            }
        lane_reports = _run_daily_lane_searches(
            clean_query,
            route_intents=route_intents,
            profile=profile or "china",
            backend=search_backend or "auto",
            cache_ttl=max(int(cache_ttl or 0), 0),
            limit=min(max(effective_limit, 6), 8),
            base_scope=scope or "",
            route_plan=route_plan,
        )
        diagnostics["search"]["lanes"] = lane_reports["diagnostics"]
        raw_items.extend(lane_reports["items"])

    if include_feeds:
        try:
            feed_rows = fetch_feed_source(
                resolved_feed_source,
                limit=effective_feeds_limit,
                language="zh" if profile != "english" else "en",
                category=_daily_feed_category(route_intents, preset=preset),
                keyword=_daily_feed_keyword(resolved_feed_source, report_query),
                watchlist_path=watchlist_path or None,
            )
            raw_items.extend(_normalize_feed_items(feed_rows, source=resolved_feed_source))
            diagnostics["feeds"] = {
                "status": "ok",
                "count": len(feed_rows),
                "error": "",
                "limit": effective_feeds_limit,
                "source": resolved_feed_source,
            }
        except Exception as exc:
            diagnostics["feeds"] = {
                "status": "error",
                "count": 0,
                "error": str(exc),
                "limit": effective_feeds_limit,
                "source": resolved_feed_source,
            }

    hotnews_items: list[dict[str, Any]] = []
    trend_report: dict[str, Any] = {}
    hotnews_brief: dict[str, Any] = {}
    if include_hotnews:
        try:
            hotnews_items = fetch_hotnews(
                source=hotnews_source,
                limit=effective_hotnews_limit,
                backend="auto",
            )
            normalized_hotnews = _normalize_hotnews_items(hotnews_items)
            focused_hotnews = _filter_related_hotnews(normalized_hotnews, query=report_query) if report_query else normalized_hotnews
            raw_items.extend(focused_hotnews)
            trend_report = build_trend_report(
                [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "summary": item.get("summary", ""),
                        "source_id": item.get("source", ""),
                        "evidence_role": item.get("evidence_role", ""),
                        "risk_tags": item.get("risk_tags", []),
                        "source_card": item.get("source_card", {}),
                        "metrics": item.get("metrics", {}),
                        "published_at": item.get("published_at", ""),
                    }
                    for item in focused_hotnews
                ],
                limit=min(10, effective_hotnews_limit),
            ) if focused_hotnews else {"trend_count": 0, "sample_count": 0, "trends": [], "source_distribution": {}, "sample_boundaries": []}
            hotnews_brief = build_hotnews_brief(
                [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "summary": item.get("summary", ""),
                        "source_id": item.get("source", ""),
                        "evidence_role": item.get("evidence_role", ""),
                        "risk_tags": item.get("risk_tags", []),
                        "source_card": item.get("source_card", {}),
                        "metrics": item.get("metrics", {}),
                        "published_at": item.get("published_at", ""),
                    }
                    for item in focused_hotnews
                ],
                trend_report=trend_report,
                limit=min(8, effective_hotnews_limit),
            ) if focused_hotnews else {
                "sample_count": 0,
                "trend_count": 0,
                "sample_boundaries": [],
                "warnings": ["今天未见该主题直接进入公开热榜；这不等于没有进展，只说明公开热度层未形成明显共振。"] if report_query else [],
                "highlights": [],
            }
            diagnostics["hotnews"] = {
                "status": "ok",
                "count": len(focused_hotnews),
                "error": "",
                "limit": effective_hotnews_limit,
                "source": hotnews_source,
            }
        except Exception as exc:
            diagnostics["hotnews"] = {
                "status": "error",
                "count": 0,
                "error": str(exc),
                "limit": effective_hotnews_limit,
                "source": hotnews_source,
            }

    ranked_items = _merge_daily_items(raw_items, query=report_query, route_intents=route_intents)
    if report_query and "hot_trend" not in set(route_intents):
        ranked_items = [
            row
            for row in ranked_items
            if str(row.get("origin") or "") != "hotnews" or float(row.get("query_overlap") or 0.0) >= 0.35
        ]
    ranked_items = annotate_daily_items(
        ranked_items,
        generated_at=now_iso,
        time_window=effective_time_window,
    )
    items = _select_daily_items(ranked_items, limit=effective_limit)
    overflow_items = _build_daily_overflow_items(ranked_items, selected_items=items, limit=effective_overflow_limit, query=report_query)
    read_evidence: list[dict[str, Any]] = []
    read_pack: dict[str, Any] = {}
    if read_top and int(read_top) > 0:
        read_evidence, read_pack = _enrich_daily_reads(
            items,
            read_top=int(read_top),
            read_backend=read_backend,
            max_read_chars=max_read_chars,
            profile=profile or "china",
            cache_ttl=max(int(cache_ttl or 0), 0),
        )
        read_summary = dict(read_pack.get("summary") or {})
        read_errors = [row for row in read_evidence if row.get("status") == "error"]
        read_status = "skipped"
        if read_evidence:
            if read_errors and len(read_errors) == len(read_evidence):
                read_status = "error"
            elif read_errors:
                read_status = "partial"
            else:
                read_status = "ok"
        diagnostics["read"] = {
            "status": read_status,
            "count": int(read_summary.get("usable_count") or 0),
            "error": "; ".join(str(row.get("error") or "") for row in read_errors if row.get("error"))[:500],
            "limit": int(read_summary.get("requested") or read_top),
            "backend": read_backend or "auto",
            "max_chars": max_read_chars,
        }
    source_health = build_daily_source_health(items, overflow_items, time_window=effective_time_window)
    source_mix = _count_values(items, "source")
    origin_mix = _count_values(items, "origin")
    evidence_role_mix = _count_values(items, "evidence_role")
    sections = _build_daily_sections(items)
    storylines = build_daily_storylines(
        items,
        overflow_items,
        query=report_query,
        edition=effective_edition,
        time_window=effective_time_window,
    )
    editorial_decisions = build_daily_editorial_decisions(storylines)
    editorial_health = _build_editorial_health(
        sections=sections,
        diagnostics=diagnostics,
        candidate_count=len(raw_items),
        query=report_query,
        route_intents=route_intents,
        source_health=source_health,
        storylines=storylines,
        time_window=effective_time_window,
    )
    highlights = build_daily_storyline_highlights(storylines, source_health=source_health)
    if not highlights:
        highlights = _build_daily_judgments(sections, route_plan=route_plan, hotnews_brief=hotnews_brief)
    boundaries = _daily_boundaries(
        route_plan=route_plan,
        hotnews_brief=hotnews_brief,
        diagnostics=diagnostics,
        has_query=bool(report_query),
        has_watch=bool(watch_id),
    )
    next_steps = _daily_next_steps(
        query=report_query,
        watch_id=watch_id,
        items=items,
        route_plan=route_plan,
        resolved_feed_source=resolved_feed_source,
    )

    report = {
        "schema_version": "daily_report_v1",
        "title": report_title,
        "query": report_query,
        "watch_id": watch_id,
        "mode": mode,
        "generated_at": now_iso,
        "time_window": effective_time_window,
        "edition": effective_edition,
        "profile": profile or "china",
        "scope": scope or "",
        "site": site or "",
        "preset": preset or "",
        "lens": lens or "",
        "route_plan": route_plan,
        "diagnostics": diagnostics,
        "feed_source": resolved_feed_source,
        "source_mix": source_mix,
        "origin_mix": origin_mix,
        "evidence_role_mix": evidence_role_mix,
        "candidate_count": len(raw_items),
        "item_count": len(items),
        "highlights": highlights,
        "items": items,
        "overflow_items": overflow_items,
        "overflow_count": len(overflow_items),
        "overflow_limit": effective_overflow_limit,
        "storylines": storylines,
        "editorial_decisions": editorial_decisions,
        "source_health": source_health,
        "sections": sections,
        "read_evidence": read_evidence,
        "read_pack": read_pack,
        "editorial_health": editorial_health,
        "hotnews_brief": hotnews_brief,
        "trend_report": trend_report,
        "boundary": (
            "日报是公开信号与证据入口，不是最终判断；热点、RSS、评论和公开网页样本都应在需要时回读原文。"
        ),
        "boundaries": boundaries,
        "next_steps": next_steps,
    }
    report["history_delta"] = build_daily_history_delta(
        report,
        history_path=history_path or None,
        compare_days=max(int(compare_days or 0), 0),
    )
    if record_history:
        path = record_daily_history(report, history_path=history_path or None)
        report["history_recorded"] = True
        report["history_path"] = str(path)
    else:
        report["history_recorded"] = False
        if history_path:
            report["history_path"] = str(Path(history_path).expanduser())
    return report


def format_daily_markdown(report: dict[str, Any]) -> str:
    """Render a daily report as an editorial daily brief."""
    title = str(report.get("title") or report.get("query") or "中文互联网")
    sample_count = int(report.get("candidate_count") or 0)
    item_count = int(report.get("item_count") or 0)
    lines = [
        f"# 观澜日报 / {title}",
        "",
        f"> 从 {sample_count} 条公开线索里，筛出 {item_count} 条值得继续跟进的内容。",
        "",
        f"- 生成时间: {report.get('generated_at', '')}",
        f"- 模式: {report.get('mode', '')}",
        f"- feed_source: {report.get('feed_source', '') or 'none'}",
    ]
    if report.get("query"):
        lines.append(f"- 主题: {report.get('query', '')}")
    if report.get("lens"):
        lines.append(f"- lens: {report.get('lens', '')}")
    route_plan = report.get("route_plan") or {}
    route_intents = list(route_plan.get("primary_intents") or []) + list(route_plan.get("secondary_intents") or [])
    if route_intents:
        lines.append("- 路由意图: " + ", ".join(route_intents))
    if route_plan.get("preferred_scopes"):
        lines.append("- 推荐 scopes: " + ", ".join(route_plan.get("preferred_scopes") or []))
    if report.get("source_mix"):
        lines.append("- 来源分布: " + "；".join(f"{key}: {value}" for key, value in (report.get("source_mix") or {}).items()))
    source_health = report.get("source_health") or {}
    if source_health.get("main_tier_counts"):
        lines.append(
            "- 来源层级: "
            + "；".join(f"{key}: {value}" for key, value in (source_health.get("main_tier_counts") or {}).items())
        )

    highlights = report.get("highlights") or []
    if highlights:
        lines.extend(["", "## 今日摘要"])
        lines.extend(f"- {item}" for item in highlights)

    storylines = report.get("storylines") or []
    if storylines:
        lines.extend(["", "## 今日主线"])
        for idx, story in enumerate(storylines, start=1):
            lines.append("")
            lines.append(f"### {idx}. {story.get('headline', '')}")
            lines.append(
                f"- 时间: {story.get('freshness_label') or story.get('freshness', 'unknown')}；"
                f"风险等级: {story.get('risk_level', 'low')}；"
                f"动作建议: {story.get('recommended_action', '')}；"
                f"适合团队: {'、'.join(story.get('teams') or [])}；"
                f"信心: {story.get('confidence', '')}"
            )
            lines.append(f"- 发生了什么: {story.get('what_happened', '')}")
            lines.append(f"- 为什么重要: {story.get('why_it_matters', '')}")
            spread = story.get("source_spread") or {}
            tier_counts = spread.get("tier_counts") or {}
            if tier_counts:
                lines.append("- 来源层: " + "；".join(f"{key}: {value}" for key, value in tier_counts.items()))
            evidence = story.get("evidence_items") or []
            if evidence:
                lines.append("- 证据锚点:")
                for row in evidence:
                    title_text = str(row.get("title") or "")
                    url = str(row.get("url") or "")
                    meta = " · ".join(
                        part
                        for part in [
                            str(row.get("source_tier_label") or row.get("source_tier") or ""),
                            str(row.get("source") or ""),
                            str(row.get("freshness_label") or row.get("freshness") or ""),
                        ]
                        if part
                    )
                    line = f"  - [{title_text}]({url})" if url else f"  - {title_text}"
                    if meta:
                        line += f" · {meta}"
                    lines.append(line)

        lines.extend(["", "## 关键事实"])
        facts = [
            row
            for story in storylines
            for row in story.get("evidence_items") or []
            if str(row.get("source_tier") or "") in {"A", "B"}
        ]
        if facts:
            for row in facts[:8]:
                title_text = str(row.get("title") or "")
                source = str(row.get("source") or "")
                lines.append(f"- {title_text}" + (f"（{source}）" if source else ""))
        else:
            lines.append("- 目前缺少 A/B 层事实锚点，不能当成成品日报。")

        read_rows = report.get("read_evidence") or []
        if read_rows:
            lines.extend(["", "## 原文回读"])
            for row in read_rows[:6]:
                status = str(row.get("status") or "")
                summary = str(row.get("summary") or "")
                title_text = str(row.get("title") or "")
                if row.get("usable"):
                    lines.append(f"- {title_text}（{status}）: {summary}")
                else:
                    lines.append(f"- {title_text}（{status}，弱线索）: {summary or '正文不足，需补读。'}")

        lines.extend(["", "## 风险与争议"])
        risk_stories = [
            story
            for story in storylines
            if story.get("risk_level") in {"high", "medium"} or story.get("risk_flags")
        ]
        if risk_stories:
            for story in risk_stories:
                flags = "、".join(story.get("risk_flags") or []) or "风险待核验"
                lines.append(f"- {story.get('headline', '')}: {flags}；动作建议 {story.get('recommended_action', '')}")
        else:
            lines.append("- 未形成高风险主线；仍需持续留意隐私、数据、合规、安全和品牌信任信号。")

        lines.extend(["", "## 社区与用户样本"])
        community_rows = [
            row
            for story in storylines
            for row in story.get("evidence_items") or []
            if str(row.get("section") or "") == "community" or str(row.get("source_tier") or "") == "C"
        ]
        if community_rows:
            for row in community_rows[:6]:
                lines.append(f"- {row.get('title', '')}（样本，不外推总体口碑）")
        else:
            lines.append("- 社区与用户样本不足；今天不能下总体口碑结论。")

        lines.extend(["", "## 竞品/行业参照"])
        industry_rows = [
            row
            for story in storylines
            for row in story.get("evidence_items") or []
            if str(row.get("section") or "") == "ecosystem" or str(row.get("source_tier") or "") == "B"
        ]
        if industry_rows:
            for row in industry_rows[:6]:
                lines.append(f"- {row.get('title', '')}")
        else:
            lines.append("- 外部行业参照不足；不宜把品牌自述写成全网判断。")

        decisions = report.get("editorial_decisions") or []
        lines.extend(["", "## 可行动作"])
        if decisions:
            for row in decisions[:8]:
                teams = "、".join(row.get("teams") or [])
                lines.append(
                    f"- {row.get('recommended_action', '')}: {row.get('headline', '')}"
                    f"（团队: {teams or '待定'}；风险: {row.get('risk_level', 'low')}）"
                )
        else:
            lines.append("- 暂无动作建议。")

    history_delta = report.get("history_delta") or {}
    if history_delta.get("enabled"):
        lines.extend(["", "## 历史对比"])
        new_count = len(history_delta.get("new_storylines") or [])
        continued_count = len(history_delta.get("continued_storylines") or [])
        cooled_count = len(history_delta.get("cooled_storylines") or [])
        lines.append(
            f"- 新增主线: {new_count}；延续主线: {continued_count}；降温/消失主线: {cooled_count}；"
            f"对比窗口: {history_delta.get('compare_days', 0)} 天"
        )
        for label, key in (("今日新增", "new_storylines"), ("延续观察", "continued_storylines"), ("降温/消失", "cooled_storylines")):
            rows = history_delta.get(key) or []
            if rows:
                lines.append(f"- {label}: " + "；".join(str(row.get("headline") or "") for row in rows[:5]))

    items = report.get("items") or []
    sections = report.get("sections") or _build_daily_sections(items)
    if items and not storylines:
        lines.extend(["", "## 快速导航"])
        for section in sections:
            lines.append(f"- {section.get('title', '')}")
            for item in section.get("items") or []:
                title_text = str(item.get("title") or "")
                source = str(item.get("source") or "")
                role = str(item.get("evidence_role") or "")
                lines.append(f"  - [{title_text}](#item-{item.get('_daily_anchor')})" + (f" · {source}" if source else "") + (f" · {role}" if role else ""))

        lines.extend(["", "## 今日重点"])
        for section in sections:
            lines.extend(["", f"### {section.get('title', '')}"])
            if section.get("summary"):
                lines.append("")
                lines.append(section.get("summary", ""))
            for item in section.get("items") or []:
                lines.append("")
                lines.append(f'<a id="item-{item.get("_daily_anchor")}"></a>')
                lines.append(f"#### [{item.get('title', '')}]({item.get('url')})" if item.get("url") else f"#### {item.get('title', '')}")
                meta = _daily_story_meta(item)
                if meta:
                    lines.append("")
                    lines.append(meta)
                if item.get("summary"):
                    lines.append("")
                    lines.append(f"**事实锚点**：{item.get('summary')}")
                read_evidence = item.get("read_evidence") or {}
                if read_evidence.get("usable") and read_evidence.get("summary"):
                    lines.append("")
                    lines.append(f"**原文回读**：{read_evidence.get('summary')}")
                why = _daily_story_why_it_matters(item)
                if why:
                    lines.append("")
                    lines.append(f"**观察价值**：{why}")
                boundary = _daily_story_boundary(item)
                if boundary:
                    lines.append("")
                    lines.append(f"**今天的边界**：{boundary}")
                followups = _daily_story_followups(item)
                if followups:
                    lines.append("")
                    lines.append("**继续跟进**：")
                    lines.extend(f"- `{command}`" for command in followups)
                if item.get("merged_from"):
                    lines.append("")
                    lines.append("**线索来源**：" + "、".join(item.get("merged_from") or []))

    hotnews_brief = report.get("hotnews_brief") or {}
    if hotnews_brief.get("highlights") or hotnews_brief.get("warnings"):
        lines.extend(["", "## 热点水势"])
        if hotnews_brief.get("highlights"):
            lines.append(f"- 样本数: {hotnews_brief.get('sample_count', 0)}")
            lines.append(f"- 趋势数: {hotnews_brief.get('trend_count', 0)}")
            for idx, item in enumerate((hotnews_brief.get("highlights") or [])[:3], start=1):
                lines.append(
                    f"{idx}. {item.get('title', '')} | 来源: {', '.join(item.get('sources') or []) or 'unknown'} | 共振: {item.get('resonance', 'single-source')}"
                )
                if item.get("boundary"):
                    lines.append(f"   边界: {item.get('boundary')}")
        else:
            lines.extend(f"- {warning}" for warning in hotnews_brief.get("warnings") or [])

    overflow_items = report.get("overflow_items") or []
    if overflow_items:
        lines.extend(["", "## 候补线索池"])
        lines.append("这些线索没有进入今日重点，但仍保留给后续补证、改稿或扩展选题使用。")
        for idx, item in enumerate(overflow_items, start=1):
            title_text = str(item.get("title") or "")
            url = str(item.get("url") or "")
            meta = " · ".join(
                part
                for part in [
                    str(item.get("section_title") or ""),
                    str(item.get("source") or ""),
                    str(item.get("evidence_role") or ""),
                    str(item.get("overflow_note") or ""),
                ]
                if part
            )
            line = f"{idx}. [{title_text}]({url})" if url else f"{idx}. {title_text}"
            if meta:
                line += f" · {meta}"
            lines.append(line)

    editorial_health = report.get("editorial_health") or {}
    if editorial_health:
        status = str(editorial_health.get("status") or "unknown")
        coverage = editorial_health.get("coverage") or {}
        lines.extend(["", "## 采编自检"])
        lines.append(f"- 状态: {status}")
        if coverage:
            lines.append("- 覆盖: " + "；".join(f"{key}: {value}" for key, value in coverage.items()))
        source_health = report.get("source_health") or {}
        if source_health.get("main_freshness_counts"):
            lines.append(
                "- 时间健康度: "
                + "；".join(f"{key}: {value}" for key, value in (source_health.get("main_freshness_counts") or {}).items())
            )
        for warning in editorial_health.get("warnings") or []:
            lines.append(f"- {warning}")

    boundaries = report.get("boundaries") or []
    if boundaries:
        lines.extend(["", "## 边界提醒"])
        lines.extend(f"- {item}" for item in boundaries)

    next_steps = report.get("next_steps") or []
    if next_steps:
        lines.extend(["", "## 下一步"])
        lines.extend(f"- {item}" for item in next_steps)

    return "\n".join(lines)


def format_daily_context(report: dict[str, Any]) -> str:
    """Render a prompt-friendly daily context block."""
    lines = [
        f"# 观澜日报上下文 / {report.get('title') or report.get('query') or '中文互联网'}",
        "",
        f"- mode: {report.get('mode', '')}",
        f"- generated_at: {report.get('generated_at', '')}",
        f"- candidate_count: {report.get('candidate_count', 0)}",
        f"- item_count: {report.get('item_count', 0)}",
        f"- feed_source: {report.get('feed_source', '') or 'none'}",
    ]
    route_plan = report.get("route_plan") or {}
    route_intents = list(route_plan.get("primary_intents") or []) + list(route_plan.get("secondary_intents") or [])
    if route_intents:
        lines.append("- intents: " + ", ".join(route_intents))
    if route_plan.get("warnings"):
        lines.extend(f"- route_warning: {item}" for item in route_plan.get("warnings") or [])
    editorial_health = report.get("editorial_health") or {}
    if editorial_health:
        lines.append(f"- editorial_health: {editorial_health.get('status', 'unknown')}")
        coverage = editorial_health.get("coverage") or {}
        if coverage:
            lines.append("- editorial_coverage: " + ", ".join(f"{key}={value}" for key, value in coverage.items()))
        for warning in editorial_health.get("warnings") or []:
            lines.append(f"- editorial_warning: {warning}")
    for item in report.get("highlights") or []:
        lines.append(f"- highlight: {item}")
    for story in report.get("storylines") or []:
        lines.append(
            "- storyline: "
            f"id={story.get('id', '')} freshness={story.get('freshness', '')} "
            f"risk={story.get('risk_level', '')} action={story.get('recommended_action', '')} "
            f"confidence={story.get('confidence', '')} title={story.get('headline', '')}"
        )
        if story.get("what_happened"):
            lines.append(f"  what_happened={story.get('what_happened')}")
        if story.get("why_it_matters"):
            lines.append(f"  why_it_matters={story.get('why_it_matters')}")
        for row in story.get("evidence_items") or []:
            lines.append(
                "  - evidence: "
                f"tier={row.get('source_tier', '')} source={row.get('source', '')} "
                f"freshness={row.get('freshness', '')} title={row.get('title', '')}"
            )
            if row.get("url"):
                lines.append(f"    url={row.get('url')}")
    sections = report.get("sections") or _build_daily_sections(report.get("items") or [])
    for section in sections:
        lines.append(f"- section: {section.get('title', '')}")
        if section.get("summary"):
            lines.append(f"  summary={section.get('summary')}")
        for row in section.get("items") or []:
            lines.append(
                "  - item: "
                f"origin={row.get('origin', '')} source={row.get('source', '')} role={row.get('evidence_role', '')} "
                f"title={row.get('title', '')}"
            )
            if row.get("url"):
                lines.append(f"    url={row.get('url')}")
            if row.get("summary"):
                lines.append(f"    summary={row.get('summary')}")
            read_evidence = row.get("read_evidence") or {}
            if read_evidence.get("usable") and read_evidence.get("summary"):
                lines.append(f"    read_summary={read_evidence.get('summary')}")
            if read_evidence.get("status"):
                lines.append(
                    "    read_status="
                    f"{read_evidence.get('status')} score={read_evidence.get('score', 0)} "
                    f"backend={read_evidence.get('selected_backend', '')}"
                )
    overflow_items = report.get("overflow_items") or []
    if overflow_items:
        lines.append("- overflow_items:")
        for row in overflow_items:
            lines.append(
                "  - overflow: "
                f"section={row.get('section_title', '')} source={row.get('source', '')} "
                f"role={row.get('evidence_role', '')} title={row.get('title', '')}"
            )
            if row.get("url"):
                lines.append(f"    url={row.get('url')}")
            if row.get("overflow_note"):
                lines.append(f"    note={row.get('overflow_note')}")
    for item in report.get("boundaries") or []:
        lines.append(f"- boundary: {item}")
    for item in report.get("next_steps") or []:
        lines.append(f"- next: {item}")
    return "\n".join(lines)


def save_daily_output(report: dict[str, Any], path: str, *, output_format: str = "markdown") -> Path:
    """Save a daily report to a local file."""
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        payload = json.dumps(report, ensure_ascii=False, indent=2)
    elif output_format == "context":
        payload = format_daily_context(report)
    elif output_format == "html":
        payload = format_daily_html(report)
    elif output_format == "im":
        payload = format_daily_im(report)
    else:
        payload = format_daily_markdown(report)
    output_path.write_text(payload, encoding="utf-8")
    return output_path


def _normalize_search_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        trace = row.get("trace") if isinstance(row.get("trace"), dict) else {}
        source_card = dict(row.get("source_card") or trace.get("source_card") or {})
        items.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or row.get("href") or "").strip(),
                "summary": str(row.get("snippet") or "").strip()[:500],
                "source": str(row.get("source_type") or row.get("domain") or row.get("source") or "search"),
                "origin": "search",
                "evidence_role": str(row.get("evidence_role") or row.get("source_type") or "open_web_context"),
                "published_at": str(row.get("published_at") or row.get("date") or ""),
                "source_card": source_card,
                "risk_tags": _unique_list(list(row.get("risk_tags") or []) + list(source_card.get("risk_tags") or [])),
                "metrics": {"score": row.get("score", 0)},
            }
        )
    return [item for item in items if item.get("title") and item.get("url")]


def _normalize_search_items_with_origin(rows: list[dict[str, Any]], *, origin: str) -> list[dict[str, Any]]:
    items = _normalize_search_items(rows)
    for item in items:
        item["origin"] = origin
    return items


def _normalize_feed_items(rows: list[dict[str, Any]], *, source: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "summary": str(row.get("summary") or "").strip()[:500],
                "source": str(row.get("source_title") or row.get("source_id") or source),
                "origin": f"feeds:{source}",
                "evidence_role": str(row.get("evidence_role") or "reading_signal"),
                "published_at": str(row.get("published_at") or ""),
                "source_card": dict(row.get("source_card") or {}),
                "risk_tags": list(row.get("risk_tags") or []),
                "metrics": dict(row.get("metrics") or {}),
            }
        )
    return [item for item in items if item.get("title")]


def _normalize_hotnews_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "summary": str(row.get("summary") or "").strip()[:500],
                "source": str(row.get("source_id") or row.get("platform") or "hotnews"),
                "origin": "hotnews",
                "evidence_role": str(row.get("evidence_role") or "fresh_trend_signal"),
                "published_at": str(row.get("published_at") or ""),
                "source_card": dict(row.get("source_card") or {}),
                "risk_tags": list(row.get("risk_tags") or []),
                "metrics": dict(row.get("metrics") or {}),
            }
        )
    return [item for item in items if item.get("title")]


def _normalize_watch_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        origin = str(row.get("origin") or "watch")
        items.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "summary": str(row.get("summary") or "").strip()[:500],
                "source": str(row.get("source") or origin),
                "origin": "watch" if origin.startswith("search") or origin.startswith("feeds:") else origin,
                "evidence_role": str(row.get("evidence_role") or "watch_signal"),
                "published_at": str(row.get("published_at") or ""),
                "source_card": dict(row.get("source_card") or {}),
                "risk_tags": list(row.get("risk_tags") or []),
                "metrics": dict(row.get("metrics") or {}),
                "is_new": bool(row.get("is_new")),
                "watch_origin": origin,
            }
        )
    return [item for item in items if item.get("title")]


def _merge_daily_items(items: list[dict[str, Any]], *, query: str, route_intents: list[str]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in items:
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        key = _daily_fingerprint(title=title, url=url, source=str(row.get("source") or ""))
        if not title or not key:
            continue
        score = _daily_score(row, query=query, route_intents=route_intents)
        overlap = _query_overlap_score(query, f"{title} {row.get('summary') or ''}")
        if key not in merged:
            item = dict(row)
            item["daily_score"] = round(score, 3)
            item["query_overlap"] = round(overlap, 3)
            item["merged_from"] = [str(row.get("origin") or "")]
            merged[key] = item
            continue
        current = merged[key]
        current["daily_score"] = round(max(float(current.get("daily_score") or 0.0), score), 3)
        current["query_overlap"] = round(max(float(current.get("query_overlap") or 0.0), overlap), 3)
        current["merged_from"] = _unique_list(list(current.get("merged_from") or []) + [str(row.get("origin") or "")])
        current["risk_tags"] = _unique_list(list(current.get("risk_tags") or []) + list(row.get("risk_tags") or []))
        if not current.get("summary") and row.get("summary"):
            current["summary"] = row.get("summary")
        if not current.get("published_at") and row.get("published_at"):
            current["published_at"] = row.get("published_at")
        if len(str(row.get("summary") or "")) > len(str(current.get("summary") or "")):
            current["summary"] = row.get("summary")
    ordered = sorted(
        merged.values(),
        key=lambda row: (
            -float(row.get("daily_score") or 0.0),
            _origin_priority(str(row.get("origin") or "")),
            str(row.get("title") or ""),
        ),
    )
    return ordered


def _select_daily_items(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not items:
        return []
    if limit <= 2:
        return items[:limit]

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    section_order = ("ecosystem", "community", "trust", "official", "other")
    section_caps = _daily_section_caps(limit)

    def add(row: dict[str, Any], *, allow_soft: bool = False) -> bool:
        if _daily_is_search_entrypoint(row):
            return False
        if str(row.get("source_tier") or "") == "D":
            return False
        if _daily_is_soft_seo(row) and not allow_soft:
            return False
        key = _daily_fingerprint(
            title=str(row.get("title") or ""),
            url=str(row.get("url") or ""),
            source=str(row.get("source") or ""),
        )
        if not key or key in selected_ids:
            return False
        section_key = _daily_section_key(row)
        if _section_count(selected, section_key) >= section_caps.get(section_key, limit):
            return False
        selected.append(row)
        selected_ids.add(key)
        return True

    # First pass: force a minimum editorial spread when matching evidence exists.
    for section_key in section_order:
        for row in items:
            if _daily_section_key(row) == section_key and add(row):
                break
        if len(selected) >= limit:
            return selected[:limit]

    # Second pass: keep source modality diversity inside each section.
    for origin_group in ("watch", "feeds:", "search:", "search", "hotnews"):
        for row in items:
            origin = str(row.get("origin") or "")
            if origin == origin_group or (origin_group.endswith(":") and origin.startswith(origin_group)):
                add(row)
            if len(selected) >= limit:
                return selected[:limit]

    for row in items:
        add(row)
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        for row in items:
            add(row, allow_soft=True)
            if len(selected) >= limit:
                break
    return selected[:limit]


def _build_daily_overflow_items(
    ranked_items: list[dict[str, Any]],
    *,
    selected_items: list[dict[str, Any]],
    limit: int,
    query: str,
) -> list[dict[str, Any]]:
    """Keep a compact trail of useful candidates that did not make the lead brief."""
    if limit <= 0:
        return []
    selected_keys = {
        _daily_fingerprint(
            title=str(item.get("title") or ""),
            url=str(item.get("url") or ""),
            source=str(item.get("source") or ""),
        )
        for item in selected_items
    }
    selected_keys.discard("")
    overflow: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in ranked_items:
        if not _daily_overflow_is_relevant(row, query=query):
            continue
        key = _daily_fingerprint(
            title=str(row.get("title") or ""),
            url=str(row.get("url") or ""),
            source=str(row.get("source") or ""),
        )
        if not key or key in selected_keys or key in seen or _daily_is_search_entrypoint(row):
            continue
        seen.add(key)
        section_key = _daily_section_key(row)
        overflow.append(
            {
                "title": str(row.get("title") or ""),
                "url": str(row.get("url") or ""),
                "summary": str(row.get("summary") or "")[:240],
                "source": str(row.get("source") or ""),
                "origin": str(row.get("origin") or ""),
                "evidence_role": str(row.get("evidence_role") or ""),
                "published_at": str(row.get("published_at") or ""),
                "source_tier": str(row.get("source_tier") or ""),
                "source_tier_label": str(row.get("source_tier_label") or ""),
                "freshness": str(row.get("freshness") or ""),
                "freshness_label": str(row.get("freshness_label") or ""),
                "freshness_in_window": bool(row.get("freshness_in_window", False)),
                "section": section_key,
                "section_title": _daily_section_title(section_key),
                "daily_score": row.get("daily_score", 0),
                "overflow_note": _daily_overflow_note(row),
            }
        )
        if len(overflow) >= limit:
            break
    return overflow


def _daily_overflow_is_relevant(row: dict[str, Any], *, query: str) -> bool:
    """Keep bottom candidate trails useful, not every weak fanout hit."""
    if not query:
        return True
    text = f"{row.get('title') or ''} {row.get('summary') or ''}"
    if _topic_match_strict(query, text, min_ratio=0.5):
        return True
    overlap = float(row.get("query_overlap") or 0.0)
    if overlap >= 0.7:
        return True
    if _daily_is_brand_owned(row):
        return True
    if _daily_is_soft_seo(row):
        return overlap >= 0.35
    return False


def _daily_section_caps(limit: int) -> dict[str, int]:
    official_cap = 2 if limit <= 15 else 3
    return {
        "official": official_cap,
        "ecosystem": max(2, limit // 3),
        "community": max(2, limit // 4),
        "trust": 2,
        "other": max(1, limit // 6),
    }


def _section_count(items: list[dict[str, Any]], section_key: str) -> int:
    return sum(1 for row in items if _daily_section_key(row) == section_key)


def _build_daily_sections(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[tuple[str, str, str]] = [
        ("official", "一手动态", "今天能直接核验的官方产品与服务入口。"),
        ("ecosystem", "外部报道与行业观察", "第三方媒体、RSS 和开放网页里更接近行业观察的部分。"),
        ("community", "社区与样本", "用户、社区、开发者或官方社区中的公开样本，更适合看使用感受和话题方向。"),
        ("trust", "风险与信任", "安全、合规、企业信任与采购侧相关入口。"),
        ("other", "其他线索", "今天仍值得保留、但不属于上面几类的线索。"),
    ]
    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key, _, _ in groups}
    for row in items:
        buckets[_daily_section_key(row)].append(dict(row))

    sections: list[dict[str, Any]] = []
    anchor_idx = 1
    for key, title, fallback_summary in groups:
        rows = buckets.get(key) or []
        if not rows:
            continue
        for row in rows:
            row["_daily_anchor"] = anchor_idx
            anchor_idx += 1
        sections.append(
            {
                "key": key,
                "title": title,
                "summary": _daily_section_summary(key, rows) or fallback_summary,
                "items": rows,
            }
        )
    return sections


def _daily_section_title(key: str) -> str:
    return daily_section_title(key)


def _daily_score(row: dict[str, Any], *, query: str, route_intents: list[str]) -> float:
    origin = str(row.get("origin") or "")
    evidence_role = str(row.get("evidence_role") or "")
    source_card = row.get("source_card") or {}
    authority_score = float(source_card.get("authority_score") or 0.0)
    risk_tags = {str(tag) for tag in row.get("risk_tags") or [] if str(tag)}
    metrics = row.get("metrics") or {}

    score = 0.0
    if origin == "watch":
        score += 4.6
    elif origin == "search":
        score += 4.2
    elif origin.startswith("feeds:"):
        score += 3.2
    elif origin == "hotnews":
        score += 2.5
    else:
        score += 2.0

    if evidence_role in {
        "official_primary",
        "authoritative_report",
        "company_primary",
        "security_advisory",
        "company_filing",
        "government",
    }:
        score += 1.2
    if authority_score:
        score += min(authority_score * 1.1, 1.0)
    if row.get("is_new"):
        score += 0.6

    title = str(row.get("title") or "")
    summary = str(row.get("summary") or "")
    overlap_score = _query_overlap_score(query, f"{title} {summary}")
    score += overlap_score

    if "hot_trend" in set(route_intents) and origin == "hotnews":
        score += 0.5
    elif query and origin == "hotnews" and overlap_score == 0:
        score -= 1.4
    heat = metrics.get("heat") or metrics.get("views") or metrics.get("hot")
    score += min(_to_float(heat) / 1000000.0, 0.9)

    if risk_tags & {"sample_bias", "not_representative", "external_backend"}:
        score -= 0.2
    if risk_tags & {"seo_content", "commercial_content", "soft_article"}:
        score -= 0.5
    if risk_tags & {"vendor_framing", "marketing_language"} and origin == "search":
        score -= 0.2
    if _daily_is_soft_seo(row):
        score -= 3.0
    if _daily_is_brand_owned(row) and _daily_section_key(row) == "community":
        score -= 0.4
    if _daily_is_recognized_external(row):
        score += 0.9
    if _daily_is_search_entrypoint(row):
        score -= 2.0
    return score


def _resolve_daily_feed_source(*, feed_source: str, query: str, route_intents: list[str], preset: str) -> str:
    requested = resolve_feed_source(feed_source or "auto")
    if requested != "auto":
        return requested
    recommendations = recommend_feed_sources(query)
    rec_set = set(recommendations)
    intent_set = set(route_intents)
    preset = str(preset or "").strip().lower()
    query_lower = str(query or "").lower()
    if "academic" in intent_set or preset == "academic":
        return "arxiv"
    if any(term in query_lower for term in (" ai ", "ai ", " ai", "人工智能", "大模型", "智能体", "openai", "claude", "gemini", "豆包", "office ai", "ai office", "ai ppt", "wps ai")):
        return "ai-vertical"
    if "ai-vertical" in rec_set or intent_set & {"tech", "wps_office", "company_primary"}:
        return "ai-vertical"
    if "baidu-rss" in rec_set and not query:
        return "baidu-rss"
    return "curated"


def _daily_feed_keyword(source: str, query: str) -> str | None:
    if not query:
        return None
    if source in {"curated", "curated-sources", "arxiv", "ai-vertical"}:
        return query
    return None


def _daily_feed_category(route_intents: list[str], *, preset: str) -> str | None:
    intent_set = set(route_intents)
    preset = str(preset or "").strip().lower()
    if intent_set & {"tech", "wps_office", "company_primary"} or preset in {"tech", "wps_office", "company"}:
        return "ai"
    return None


def _build_highlights(items: list[dict[str, Any]]) -> list[str]:
    highlights: list[str] = []
    for row in items[:5]:
        lead = str(row.get("title") or "")
        why = _daily_story_why_it_matters(row)
        if why:
            highlights.append(f"{lead}：{why}")
        else:
            highlights.append(lead)
    return highlights


def _daily_boundaries(
    *,
    route_plan: dict[str, Any],
    hotnews_brief: dict[str, Any],
    diagnostics: dict[str, Any],
    has_query: bool,
    has_watch: bool,
) -> list[str]:
    boundaries: list[str] = []
    boundaries.extend(str(item) for item in route_plan.get("warnings") or [] if str(item))
    boundaries.extend(str(item) for item in hotnews_brief.get("sample_boundaries") or [] if str(item))
    boundaries.extend(str(item) for item in hotnews_brief.get("warnings") or [] if str(item))
    if has_watch:
        boundaries.append("watch 模式默认不写 seen 状态；若要把今天已见线索记入本地去重，请显式运行 `watch fire --record-seen`。")
    if has_query:
        boundaries.append("日报里的搜索、RSS 和热榜线索适合做选题入口；正式结论仍应回读代表原文。")
    if diagnostics.get("search", {}).get("status") == "error":
        boundaries.append("本轮搜索入口有后端受限或上游偏慢；日报仍保留了其他公开来源线索。")
    return _unique_list(boundaries)


def _daily_next_steps(
    *,
    query: str,
    watch_id: str,
    items: list[dict[str, Any]],
    route_plan: dict[str, Any],
    resolved_feed_source: str,
) -> list[str]:
    steps: list[str] = []
    if watch_id:
        steps.append(f"guanlan watch fire {shlex.quote(watch_id)} --record-seen --limit 30")
    elif query:
        preset = _daily_research_preset(route_plan)
        command = ["guanlan", "research", query, "--limit", "80", "--read-top", "3"]
        if preset:
            command.extend(["--preset", preset])
        steps.append(_shell_join(command))
    if resolved_feed_source:
        display_feed_source = "curated" if resolved_feed_source == "ai-vertical" else resolved_feed_source
        feed_command = ["guanlan", "feeds", display_feed_source, "--limit", "80"]
        if display_feed_source == "curated" and resolved_feed_source == "ai-vertical":
            feed_command.extend(["--category", "ai"])
        if query and display_feed_source in {"curated", "curated-sources", "arxiv"}:
            feed_command.extend(["--keyword", query])
        steps.append(_shell_join(feed_command))
    for row in items[:3]:
        if row.get("url"):
            steps.append(f'guanlan read {shlex.quote(str(row.get("url")))} --quality-report')
    return _unique_list(steps)


def _daily_story_meta(item: dict[str, Any]) -> str:
    parts: list[str] = []
    source = str(item.get("source") or "")
    origin = str(item.get("origin") or "")
    role = str(item.get("evidence_role") or "")
    published_at = str(item.get("published_at") or "")
    if source:
        parts.append(source)
    if origin:
        parts.append(origin)
    if role:
        parts.append(role)
    if published_at:
        parts.append(published_at)
    return " · ".join(parts)


def _daily_story_why_it_matters(item: dict[str, Any]) -> str:
    key = _daily_section_key(item)
    title_summary = _short_daily_claim(item)
    if key == "official":
        return f"把它放在一手层，是为了先确认可公开核验的事实锚点：{title_summary}。"
    if key == "ecosystem":
        return f"它来自官方以外的内容层，可用于补媒体、行业或订阅源视角：{title_summary}。"
    if key == "community":
        if _daily_is_brand_owned_community(item):
            return f"它来自品牌自有社区，只能当公开使用样本看，不能当独立口碑结论：{title_summary}。"
        return f"它能补用户、社区或开发者如何理解和使用该主题：{title_summary}。"
    if key == "trust":
        return f"它把安全、合规、企业信任或采购侧边界纳入日报：{title_summary}。"
    return f"它扩展了今天的观察面，后续应回读原文确认价值：{title_summary}。"


def _daily_story_boundary(item: dict[str, Any]) -> str:
    origin = str(item.get("origin") or "")
    risk_tags = {str(tag) for tag in item.get("risk_tags") or [] if str(tag)}
    if origin == "hotnews":
        return "单条热度只能说明公开平台的当下注意力，不应直接写成行业事实。"
    if _daily_is_soft_seo(item):
        return "这条更像搜索噪声、下载页或软性 SEO，只能作为弱线索，不能进入核心判断。"
    if _daily_is_brand_owned_community(item):
        return "这是品牌自有社区里的公开样本，能看使用场景，但仍不等同于独立第三方评价。"
    if risk_tags & {"sample_bias", "not_representative"}:
        return "这类样本更像局部信号，适合发现线索，不适合外推总体判断。"
    if risk_tags & {"external_backend"}:
        return "该线索经过外部聚合后端，引用时应保留缓存和上游波动边界。"
    if risk_tags & {"vendor_framing", "marketing_language"}:
        return "这条内容带有品牌自述或营销表达，适合先当一手入口，再补外部佐证。"
    return ""


def _daily_overflow_note(item: dict[str, Any]) -> str:
    if _daily_is_soft_seo(item):
        return "弱线索"
    if _daily_is_brand_owned_community(item):
        return "品牌自有社区"
    origin = str(item.get("origin") or "")
    if origin.startswith("feeds:"):
        return "订阅发现"
    if origin == "hotnews":
        return "热度样本"
    section = _daily_section_key(item)
    if section == "official":
        return "一手入口"
    if section == "ecosystem":
        return "外部材料"
    if section == "community":
        return "公开样本"
    if section == "trust":
        return "信任边界"
    return ""


def _daily_story_followups(item: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    url = str(item.get("url") or "")
    if url:
        commands.append(f"guanlan read {shlex.quote(url)} --quality-report")
    title = str(item.get("title") or "")
    if title and str(item.get("origin") or "") == "hotnews":
        commands.append(f"guanlan research {shlex.quote(title)} --profile china --limit 80 --read-top 3")
    return commands[:2]


def _daily_research_preset(route_plan: dict[str, Any]) -> str:
    intents = [str(item) for item in (route_plan.get("primary_intents") or []) + (route_plan.get("secondary_intents") or [])]
    mapping = {
        "policy": "policy",
        "local": "policy",
        "tech": "tech",
        "wps_office": "wps_office",
        "academic": "academic",
        "company_primary": "company",
        "global_entertainment": "global_entertainment",
        "jp_kr_entertainment": "jp_kr_entertainment",
        "entertainment": "entertainment",
        "reputation": "reputation",
        "finance": "finance",
        "career": "career",
        "sports": "sports",
        "science": "science",
        "cybersecurity": "cybersecurity",
    }
    for intent in intents:
        if intent in mapping:
            return mapping[intent]
    return "general"


def _run_daily_lane_searches(
    query: str,
    *,
    route_intents: list[str],
    profile: str,
    backend: str,
    cache_ttl: int,
    limit: int,
    base_scope: str,
    route_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    specs = _daily_scope_fanout_specs(
        query,
        route_intents=route_intents,
        base_scope=base_scope,
        route_plan=route_plan or {},
    )
    for spec in specs:
        scope = spec["scope"]
        lane_query = spec["query"]
        try:
            rows = search_web(
                lane_query,
                limit=max(limit, 1),
                scope=scope,
                backend=backend,
                profile=profile,
                cache_ttl=max(cache_ttl, 0),
                recovery_mode="lite",
            )
            items.extend(_normalize_search_items_with_origin(rows, origin=f"search:{scope}"))
            diagnostics.append({"scope": scope, "query": lane_query, "status": "ok", "count": len(rows)})
        except Exception as exc:
            diagnostics.append({"scope": scope, "query": lane_query, "status": "error", "count": 0, "error": str(exc)})
    return {"items": items, "diagnostics": diagnostics}


def _daily_scope_fanout_specs(
    query: str,
    *,
    route_intents: list[str],
    base_scope: str,
    route_plan: dict[str, Any],
) -> list[dict[str, str]]:
    intent_set = set(route_intents)
    specs: list[dict[str, str]] = []
    if "wps_office" in intent_set:
        specs.extend(
            [
                {"scope": "tech_dev", "query": f"{query} 金山办公 媒体 报道 行业观察 -site:wps.cn -site:wps.com"},
                {"scope": "business", "query": f"{query} 金山办公 商业化 财报 竞品 对比 办公AI"},
                {"scope": "social_web", "query": f"{query} 用户 反馈 实测 吐槽 体验"},
                {"scope": "cybersecurity", "query": f"{query} 安全 合规 数据 隐私"},
            ]
        )
    elif intent_set & {"tech", "company_primary"}:
        specs.extend(
            [
                {"scope": "tech_dev", "query": query},
                {"scope": "social_web", "query": f"{query} 用户 讨论 评测"},
            ]
        )
    elif intent_set & {"reputation", "industry", "business"}:
        specs.extend(
            [
                {"scope": "business", "query": query},
                {"scope": "social_web", "query": f"{query} 评价 反馈"},
            ]
        )
    for variant in route_plan.get("query_variants") or []:
        variant_text = str(variant or "").strip()
        if not variant_text or variant_text == query:
            continue
        if len(specs) >= 4:
            break
        specs.append({"scope": "tech_dev" if intent_set & {"wps_office", "tech"} else "business", "query": variant_text})
    if base_scope:
        specs = [spec for spec in specs if spec["scope"] != base_scope]
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for spec in specs:
        key = (spec["scope"], spec["query"])
        if key in seen:
            continue
        seen.add(key)
        result.append(spec)
    return result[:4]


def _filter_related_hotnews(items: list[dict[str, Any]], *, query: str) -> list[dict[str, Any]]:
    if not query:
        return items
    filtered = [
        item
        for item in items
        if _topic_match_strict(query, f"{item.get('title') or ''} {item.get('summary') or ''}", min_ratio=0.66)
    ]
    return filtered


def _topic_match_strict(query: str, text: str, *, min_ratio: float = 0.5) -> bool:
    tokens = _query_tokens(query)
    if not tokens:
        return True
    important = [token for token in tokens if _compact_text(token) not in {"今天", "今日", "最新", "2025", "2026"}]
    check_tokens = important or tokens
    haystack = _compact_text(text)
    matched = sum(1 for token in check_tokens if _compact_text(token) in haystack)
    if not check_tokens:
        return True
    if len(check_tokens) <= 2:
        return matched == len(check_tokens)
    return matched / len(check_tokens) >= min_ratio


def _daily_section_key(item: dict[str, Any]) -> str:
    return daily_section_key(item)


def _daily_is_search_entrypoint(item: dict[str, Any]) -> bool:
    return daily_is_search_entrypoint(item)


def _daily_is_soft_seo(item: dict[str, Any]) -> bool:
    return daily_is_soft_seo(item)


def _daily_is_recognized_external(item: dict[str, Any]) -> bool:
    return daily_is_recognized_external(item)


def _daily_section_summary(key: str, rows: list[dict[str, Any]]) -> str:
    if key == "official":
        return "这一栏只放可直接核验的一手入口，用来确认产品能力、版本入口和官方表述边界。"
    if key == "ecosystem":
        return "这一栏用第三方报道、订阅源和行业内容补外部事实，避免日报退化成品牌自述。"
    if key == "community":
        return "这一栏看用户、社区和开发者样本，适合判断真实使用感受和话题走向。"
    if key == "trust":
        return "这一栏专门补安全、合规和企业信任面，避免日报只剩功能宣传。"
    return "这一栏保留今天仍值得记录但暂时不方便归类的线索。"


def _build_daily_judgments(
    sections: list[dict[str, Any]],
    *,
    route_plan: dict[str, Any],
    hotnews_brief: dict[str, Any],
) -> list[str]:
    bullets: list[str] = []
    section_map = {str(section.get("key") or ""): section for section in sections}
    official_item = _first_section_item(section_map, "official")
    ecosystem_item = _first_section_item(section_map, "ecosystem")
    community_item = _first_section_item(section_map, "community")
    trust_item = _first_section_item(section_map, "trust")
    if official_item:
        bullets.append(f"一手层可核验：{_short_daily_claim(official_item)}。这只能代表官方公开口径，不代表外部评价。")
    if ecosystem_item:
        bullets.append(f"外部层可核验：{_short_daily_claim(ecosystem_item)}。这类线索应优先回读原文，补足媒体和行业视角。")
    else:
        bullets.append("外部报道与行业观察层仍偏薄；今天不能把官网信息写成“全网情况”。")
    if community_item:
        bullets.append(f"社区层可核验：{_short_daily_claim(community_item)}。它是公开样本，适合看使用场景和问题线索，不适合外推总体口碑。")
    else:
        bullets.append("社区与用户样本不足；今天还缺真实使用者和开发者反馈。")
    if trust_item:
        bullets.append(f"信任层可核验：{_short_daily_claim(trust_item)}。这部分用于补安全、合规和企业采购边界。")
    elif "wps_office" in {str(item) for item in (route_plan.get("primary_intents") or []) + (route_plan.get("secondary_intents") or [])}:
        bullets.append("像 WPS AI 这样的办公产品日报，必须单独留出安全、合规和企业信任这一栏，不能只谈功能。")
    if hotnews_brief.get("highlights"):
        bullets.append("主题相关热度信号已单独放在热度层，只能说明公开注意力，不替代事实核验。")
    else:
        bullets.append("今天没有看到主题直接进入公开热榜，说明“注意力爆点”不是当前主叙事，日报应更多依赖事实与材料层。")
    return bullets[:5]


def _first_section_item(section_map: dict[str, dict[str, Any]], key: str) -> dict[str, Any] | None:
    rows = (section_map.get(key) or {}).get("items") or []
    first = rows[0] if rows else None
    return dict(first) if isinstance(first, dict) else None


def _short_daily_claim(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "").strip()
    summary = str(item.get("summary") or "").strip()
    source = str(item.get("source") or "").strip()
    text = summary if summary and len(summary) > len(title) else title
    text = re.sub(r"\s+", " ", text).strip(" ，。")
    if len(text) > 86:
        text = text[:84].rstrip() + "..."
    if source:
        return f"{text}（{source}）"
    return text


def _enrich_daily_reads(
    items: list[dict[str, Any]],
    *,
    read_top: int,
    read_backend: str,
    max_read_chars: int,
    profile: str,
    cache_ttl: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read a small representative set of daily URLs and attach summaries."""
    from guanlan.read_evidence import build_representative_read_pack

    candidates = _daily_read_candidates(items, limit=max(int(read_top or 0), 0))
    by_key = {
        _daily_fingerprint(
            title=str(item.get("title") or ""),
            url=str(item.get("url") or ""),
            source=str(item.get("source") or ""),
        ): item
        for item in items
    }
    read_pack = build_representative_read_pack(
        candidates,
        read_top=max(int(read_top or 0), 0),
        read_backend=read_backend or "auto",
        max_read_chars=max(int(max_read_chars or 1800), 300),
        profile=profile or "china",
        cache_ttl=max(int(cache_ttl or 0), 0),
        fallback_search=False,
        source="daily",
        max_read_top=3,
    )
    evidence: list[dict[str, Any]] = []
    for row in list(read_pack.get("readings") or []):
        url = str(row.get("url") or "")
        key = _daily_fingerprint(title=str(row.get("title") or ""), url=url, source=str(row.get("source") or ""))
        record = dict(row)
        record["summary"] = _daily_read_summary(str(row.get("content") or ""), title=str(row.get("title") or ""))
        record["chars"] = int(row.get("content_chars") or 0)
        record["score"] = int((row.get("quality_report") or {}).get("score") or row.get("score") or 0)
        record["label"] = str((row.get("quality_report") or {}).get("label") or row.get("label") or "")
        evidence.append(record)
        if key and key in by_key:
            by_key[key]["read_evidence"] = record
    return evidence, read_pack


def _daily_read_candidates(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    sections = _build_daily_sections(items)
    section_order = ("ecosystem", "official", "community", "trust", "other")
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(row: dict[str, Any]) -> bool:
        url = str(row.get("url") or "")
        key = _daily_fingerprint(title=str(row.get("title") or ""), url=url, source=str(row.get("source") or ""))
        if not url or not key or key in seen or _daily_is_search_entrypoint(row):
            return False
        seen.add(key)
        selected.append(row)
        return True

    for section_key in section_order:
        rows = []
        for section in sections:
            if section.get("key") == section_key:
                rows = [dict(row) for row in section.get("items") or [] if isinstance(row, dict)]
                break
        for row in sorted(rows, key=_daily_read_priority):
            if add(row):
                break
        if len(selected) >= limit:
            return selected[:limit]

    for row in sorted((dict(item) for item in items), key=_daily_read_priority):
        add(row)
        if len(selected) >= limit:
            break
    return selected[:limit]


def _daily_read_priority(row: dict[str, Any]) -> tuple[int, float, str]:
    section = _daily_section_key(row)
    section_rank = {"ecosystem": 0, "official": 1, "community": 2, "trust": 3, "other": 4}.get(section, 9)
    penalty = 0
    if _daily_is_soft_seo(row):
        penalty += 4
    if _daily_is_recognized_external(row):
        penalty -= 2
    if str(row.get("origin") or "").startswith("feeds:"):
        penalty -= 1
    return (section_rank + penalty, -float(row.get("daily_score") or 0.0), str(row.get("title") or ""))


def _daily_read_summary(text: str, *, title: str = "") -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return ""
    clean = re.sub(r"^Title:\s*", "", clean, flags=re.IGNORECASE)
    if "Markdown Content:" in clean:
        clean = clean.split("Markdown Content:", 1)[1].strip()
    clean = re.sub(r"\bURL Source:\s*\S+", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"\bAuthor:\s*[^。！？!?]{0,80}", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"!\[[^\]]*]\([^)]+\)", "", clean).strip()
    clean = re.sub(r"\[[^\]]*]\(https?://[^)]+\)", "", clean).strip()
    title_compact = _compact_text(title)
    chunks = re.split(r"(?<=[。！？!?])\s+|[\r\n]+", clean)
    picked: list[str] = []
    for chunk in chunks:
        value = chunk.strip(" -_*#\t")
        if len(value) < 24:
            continue
        if title_compact and _compact_text(value) == title_compact:
            continue
        if any(marker in value.lower() for marker in ("javascript", "cookie", "copyright", "all rights reserved")):
            continue
        picked.append(value)
        if len("".join(picked)) >= 180 or len(picked) >= 2:
            break
    if not picked:
        picked = [clean[:220]]
    summary = " ".join(picked)
    if len(summary) > 260:
        summary = summary[:258].rstrip() + "..."
    return summary


def _build_editorial_health(
    *,
    sections: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    candidate_count: int,
    query: str,
    route_intents: list[str],
    source_health: dict[str, Any] | None = None,
    storylines: list[dict[str, Any]] | None = None,
    time_window: str = "3d",
) -> dict[str, Any]:
    coverage = {str(section.get("key") or ""): len(section.get("items") or []) for section in sections}
    warnings: list[str] = []
    status = "ok"
    if candidate_count < 12:
        warnings.append("候选池偏小，日报只能当轻量线索，不适合写强判断。")
    if coverage.get("official", 0) and not coverage.get("ecosystem", 0):
        warnings.append("一手来源已经出现，但外部报道与行业观察不足，不能代表全网。")
    ecosystem_rows = [
        row
        for section in sections
        if section.get("key") == "ecosystem"
        for row in section.get("items") or []
        if isinstance(row, dict)
    ]
    if ecosystem_rows and not any(_daily_is_recognized_external(row) or str(row.get("origin") or "").startswith("feeds:") for row in ecosystem_rows):
        warnings.append("外部层目前以通用网页或弱垂类线索为主，仍需补行业媒体、RSS 或第三方原文。")
    if ecosystem_rows and all(_daily_is_soft_seo(row) for row in ecosystem_rows):
        warnings.append("外部层全是弱 SEO/转载线索，不能当作客观新闻事实层。")
    community_rows = [
        row
        for section in sections
        if section.get("key") == "community"
        for row in section.get("items") or []
        if isinstance(row, dict)
    ]
    if community_rows and all(_daily_is_brand_owned_community(row) for row in community_rows):
        warnings.append("社区层目前主要来自品牌自有社区，还缺独立用户社区或开发者社区样本。")
    if query and not coverage.get("community", 0):
        warnings.append("社区与用户样本不足，缺少真实使用反馈层。")
    if "wps_office" in set(route_intents) and not coverage.get("trust", 0):
        warnings.append("WPS/AI Office 日报缺少安全、合规或企业信任层。")
    if diagnostics.get("feeds", {}).get("status") == "error":
        warnings.append("订阅/垂类动态层未成功进入候选池，需要补抓或读取缓存。")
    if set(route_intents) & {"wps_office", "tech"} and int(diagnostics.get("feeds", {}).get("count") or 0) == 0:
        warnings.append("AI/WPS 主题的订阅或垂类动态层没有命中，日报不能宣称覆盖了今日 AI 圈动态。")
    if diagnostics.get("hotnews", {}).get("status") == "error":
        warnings.append("热度层本轮不可用，不能判断今天是否形成公开水势。")
    if diagnostics.get("read", {}).get("status") in {"error", "partial"}:
        warnings.append("代表原文回读不完整；已保留可读条目的边界，弱读页面需要后续 `read --quality-report` 或页面诊断。")
    source_health = source_health or {}
    warnings.extend(str(item) for item in source_health.get("warnings") or [] if str(item))
    freshness_counts = source_health.get("main_freshness_counts") or {}
    if normalize_daily_time_window(time_window) in {"today", "24h"} and not freshness_counts.get("today", 0):
        warnings.append("本日报时间窗要求今天/24h，但主正文缺少明确今日证据，不能使用“今日最新事实”口径。")
    if not storylines:
        warnings.append("还没有形成稳定主线，当前只能作为线索池。")
    if warnings:
        status = "warn"
    if coverage.get("official", 0) and sum(value for key, value in coverage.items() if key != "official") == 0:
        status = "block"
        warnings.insert(0, "题池只有官方/一手来源，禁止把它写成日报正文。")
    return {
        "status": status,
        "candidate_count": candidate_count,
        "coverage": coverage,
        "warnings": _unique_list(warnings),
    }


def _query_overlap_score(query: str, text: str) -> float:
    tokens = _query_tokens(query)
    if not tokens:
        return 0.0
    haystack = _compact_text(text)
    matched = sum(1 for token in tokens if _compact_text(token) and _compact_text(token) in haystack)
    return min(matched * 0.35, 2.1)


def _query_tokens(query: str) -> list[str]:
    compact = str(query or "").strip()
    if not compact:
        return []
    tokens = re.split(r"[\s/,_:+-]+", compact)
    results = []
    for token in tokens:
        token = token.strip()
        if not token or len(token) < 2:
            continue
        results.append(token)
    return _unique_list(results)[:16]


def _daily_fingerprint(*, title: str, url: str, source: str) -> str:
    canonical = _canonical_url(url)
    if canonical:
        return canonical
    compact = _compact_text(title)
    return f"{source}:{compact}" if compact else ""


def _canonical_url(url: str) -> str:
    clean = str(url or "").strip()
    if not clean:
        return ""
    try:
        parsed = urlsplit(clean)
    except ValueError:
        return clean
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    query = parsed.query
    fragment = ""
    return urlunsplit((scheme, netloc, path, query, fragment))


def _daily_domain(url: str) -> str:
    return daily_domain(url)


def _daily_is_brand_owned(item: dict[str, Any]) -> bool:
    return daily_is_brand_owned(item)


def _daily_is_brand_owned_community(item: dict[str, Any]) -> bool:
    return daily_is_brand_owned_community(item)


def _daily_is_brand_imitating_domain(domain: str) -> bool:
    return daily_is_brand_imitating_domain(domain)


def _origin_priority(origin: str) -> int:
    if origin == "watch":
        return 0
    if origin == "search":
        return 1
    if origin.startswith("feeds:"):
        return 2
    if origin == "hotnews":
        return 3
    return 9


def _count_values(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in items:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _compact_text(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").lower())


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique_list(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts if str(part))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
