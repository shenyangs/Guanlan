# -*- coding: utf-8 -*-
"""Search quality profiling and query strategy for Guanlan web search.

This module owns the search-quality/query-strategy implementation. The legacy
``guanlan.web._impl`` module imports these functions back as compatibility
bindings while the rest of the web stack is being split.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from guanlan.limits import DEFAULT_RESEARCH_LIMIT, DEFAULT_SEARCH_LIMIT
from guanlan.query_semantics import analyze_query_semantics
from guanlan.router import build_route_plan
from guanlan.search_entrypoints import (
    build_search_operator_hints,
    suggest_search_entrypoints,
)
from guanlan.source_seeds import wps_office_needs_open_web
from guanlan.web._search_quality_support import (
    _LONG_QUERY_KEYPHRASE_HINTS,
    _MEANINGLESS_QUERY_ALLOWLIST,
    _QUALITY_INTENT_PROFILES,
    _QUERY_KEYBOARD_RUNS,
    _QUERY_REWRITE_STOPWORDS,
    _RECENCY_DEFAULT_WINDOW_DAYS,
    _collapse_ws,
    _contains_cjk,
    _domain,
    _is_acg_entertainment_query,
    _query_relevance_terms,
    _search_limit_advice,
    _shell_quote_for_command,
    _should_prefer_entertainment_over_university,
    _source_mix,
    _unique_keep_order,
    _wps_office_subroute,
)
from guanlan.wps_semantics import (
    analyze_wps_semantics,
    wps_route_query_variants,
    wps_semantic_summary,
)


def detect_search_quality_profile(
    query: str,
    scope: str | None = None,
    site: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Detect source-quality preferences for a search query.

    This is intentionally advisory: it changes ranking weights and trace output,
    but it does not silently narrow the query to a scope unless the caller asked
    for one.
    """
    text = _collapse_ws(query).lower()
    reasons: list[str] = []
    intent = "general"
    matched_terms: list[str] = []
    wps_analysis = analyze_wps_semantics(query)
    semantic_analysis = analyze_query_semantics(query)
    semantic_quality_intent = str(semantic_analysis.get("quality_intent") or "")

    explicit_scope = (scope or "").strip()
    if explicit_scope:
        try:
            from guanlan.search_sources import resolve_scope

            resolved = resolve_scope(explicit_scope)
            return {
                "intent": f"scope:{resolved.id}",
                "name": f"显式 scope / {resolved.name}",
                "matched_terms": [],
                "preferred_scopes": [resolved.id],
                "preferred_source_types": [resolved.source_type],
                "caution_source_types": [],
                "profile": profile or "",
                "site": site or "",
                "requested_scope": resolved.id,
                "guidance": "用户已指定 scope，优先尊重该信源池。",
                "reasons": [f"requested_scope:{resolved.id}"],
            }
        except Exception:
            reasons.append(f"unknown_scope:{explicit_scope}")

    priority_order = (
        "cybersecurity",
        "weather_disaster",
        "medical_health",
        "legal_judicial",
        "finance",
        "sports",
        "science",
        "podcast",
        "test_prep",
        "career",
        "reading_notes",
        "local_life",
        "design_trend",
        "purchase_advice",
        "wps_office",
        "global_entertainment",
        "jp_kr_entertainment",
    )
    ordered_candidates = list(priority_order) + [
        key for key in _QUALITY_INTENT_PROFILES if key not in priority_order
    ]
    if semantic_quality_intent in _QUALITY_INTENT_PROFILES:
        ordered_candidates = [semantic_quality_intent] + [
            key for key in ordered_candidates if key != semantic_quality_intent
        ]
    for candidate in ordered_candidates:
        data = _QUALITY_INTENT_PROFILES[candidate]
        terms = [term for term in data["terms"] if _quality_term_matches(text, str(term))]
        if candidate == semantic_quality_intent and semantic_analysis.get("matched_rules"):
            terms = list(semantic_analysis.get("matched_terms") or semantic_analysis.get("alias_terms") or terms)
        if candidate == "wps_office" and wps_analysis.get("is_wps_office") and not terms:
            terms = (
                list(wps_analysis.get("brand_terms") or [])
                + list(wps_analysis.get("vertical_terms") or [])
                + list(wps_analysis.get("ambiguous_ai_terms") or [])
                + list(wps_analysis.get("context_terms") or [])
            )
        if terms:
            if candidate == "finance" and _is_industry_funding_context(text):
                reasons.append(f"skip:{candidate}:industry_funding_context")
                continue
            if candidate == "university_admissions" and _should_prefer_entertainment_over_university(text):
                reasons.append(f"skip:{candidate}:acg_disambiguation")
                continue
            intent = candidate
            matched_terms = terms
            reasons.append(f"matched_terms:{','.join(terms[:4])}")
            if semantic_analysis.get("matched_rules"):
                reasons.append(
                    "semantic:" + ",".join(str(item) for item in list(semantic_analysis.get("matched_rules") or [])[:4])
                )
            if candidate == "entertainment" and _is_acg_entertainment_query(text):
                reasons.append("acg_disambiguation:entertainment")
            break

    data = _QUALITY_INTENT_PROFILES.get(intent, {})
    preferred_scopes = list(data.get("preferred_scopes", []))
    preferred_source_types = list(data.get("preferred_source_types", []))
    if profile == "china" and intent == "general":
        reasons.append("profile:china")
    if profile == "english" and intent == "general":
        reasons.append("profile:english")
    if site:
        reasons.append(f"site:{site}")

    return {
        "intent": intent,
        "name": data.get("name", "通用网页研究"),
        "matched_terms": matched_terms,
        "preferred_scopes": preferred_scopes,
        "preferred_source_types": preferred_source_types,
        "caution_source_types": list(data.get("caution_source_types", [])),
        "profile": profile or "",
        "site": site or "",
        "requested_scope": explicit_scope,
        "guidance": data.get("guidance", "先看来源类型、topic 和时效性，再决定是否扩大搜索。"),
        "reasons": reasons,
        "wps_lanes": list(wps_analysis.get("lanes") or []) if intent == "wps_office" else [],
        "wps_semantic_matches": wps_semantic_summary(query) if intent == "wps_office" else {},
    }


def _quality_with_route_plan(
    quality: dict[str, Any],
    route_plan: dict[str, Any],
    explicit_scope: str | None = None,
    site: str | None = None,
) -> dict[str, Any]:
    """Softly enrich quality preferences from the route plan."""
    enriched = dict(quality or {})
    preferred_scopes = list(enriched.get("preferred_scopes") or [])
    preferred_types = list(enriched.get("preferred_source_types") or [])
    if not explicit_scope and not site:
        for scope_id in route_plan.get("preferred_scopes") or []:
            if scope_id not in preferred_scopes:
                preferred_scopes.append(scope_id)
        try:
            from guanlan.search_sources import resolve_scope

            for scope_id in preferred_scopes:
                source_type = resolve_scope(scope_id).source_type
                if source_type not in preferred_types:
                    preferred_types.append(source_type)
        except Exception:
            pass
    enriched["preferred_scopes"] = preferred_scopes
    enriched["preferred_source_types"] = preferred_types
    enriched["route_intents"] = list(route_plan.get("primary_intents") or [])
    enriched["route_evidence_roles"] = list(route_plan.get("evidence_roles") or [])
    enriched["route_warnings"] = list(route_plan.get("warnings") or [])
    enriched["route_query"] = str(route_plan.get("query") or "")
    if enriched.get("intent") == "general" and route_plan.get("primary_intents"):
        enriched["intent"] = "+".join(route_plan.get("primary_intents") or ["general"])
        enriched["name"] = "路由识别 / " + enriched["intent"]
    enriched.setdefault("reasons", [])
    enriched["reasons"] = list(enriched.get("reasons") or []) + [
        f"route:{intent}" for intent in route_plan.get("primary_intents") or [] if intent != "general"
    ]
    return enriched


def search_quality_summary(
    results: list[dict[str, Any]],
    quality: dict[str, Any] | None = None,
    *,
    limit: int | None = None,
    site_filter: dict[str, Any] | None = None,
    time_constraint: dict[str, Any] | None = None,
    limit_advice: dict[str, Any] | None = None,
    external_fetch_strategy: dict[str, Any] | None = None,
    scope_distinction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize whether a result set matches the query quality profile."""
    quality = quality or {}
    preferred_types = set(quality.get("preferred_source_types") or [])
    preferred_scopes = set(quality.get("preferred_scopes") or [])
    source_mix = _source_mix(results)
    preferred_hits = [
        item
        for item in results
        if item.get("source_type") in preferred_types or item.get("matched_scope") in preferred_scopes
    ]
    domains = {
        str(item.get("domain") or _domain(str(item.get("url", ""))))
        for item in results
        if item.get("url")
    }
    site_filter = site_filter or {"enabled": False}
    site_constrained = bool(site_filter.get("enabled"))
    warnings: list[str] = []
    suggestions: list[str] = []
    if preferred_types and not preferred_hits:
        warnings.append("未命中当前意图偏好的信源类型，需要补充 scope 或站点定向搜索。")
        suggestions.append(_source_gap_suggestion(quality, preferred_types, preferred_scopes))
    if not site_constrained and len(source_mix) <= 1 and len(results) >= 4:
        warnings.append("来源类型较单一，可能需要扩大信源面。")
        suggestions.append("补充开放网页或相邻 scope，避免只看单一信源类型。")
    if not site_constrained and len(domains) <= 1 and len(results) >= 3:
        warnings.append("域名集中度较高，注意同源转载或单站偏差。")
        suggestions.append("补充 2-3 个不同域名结果，尤其是原文、权威报道和社区样本的交叉来源。")
    limit_advice = limit_advice or _search_limit_advice(limit or len(results))
    limit_repairs = list(limit_advice.get("silent_repair_commands") or []) if isinstance(limit_advice, dict) else []
    if limit_advice.get("enabled"):
        warnings.append(str(limit_advice.get("message") or "当前结果池偏小，严肃研究建议扩大到默认结果池。"))
        repair_command = str(limit_advice.get("suggested_command") or "")
        if repair_command:
            suggestions.append(f"先无感补跑 `{repair_command}`，再压缩输出。")
        else:
            suggestions.append(f"补跑 `guanlan search \"问题\" --limit {limit_advice.get('recommended_limit', DEFAULT_SEARCH_LIMIT)} --trace`。")
    if site_filter.get("enabled") and site_filter.get("kept", 0) == 0:
        warnings.append(f"`--site {site_filter.get('site', '')}` 硬过滤后没有站内结果；不要放宽成域外结果。")
        suggestions.append("改用站点入口、站内搜索页或 WebFetch 读取候选原文补证。")
    time_constraint = time_constraint or {"enabled": False}
    if time_constraint.get("enabled") and time_constraint.get("strictness") == "strong":
        suggestions.append("显式年份/年份范围是强约束；窗口外材料只能作为背景，不应写成主线证据。")
    scope_distinction = scope_distinction or {"enabled": False}
    if scope_distinction.get("status") == "warn":
        for warning in scope_distinction.get("warnings") or []:
            warnings.append(str(warning))
        suggestions.append("按 query_strategy 的证据角色 query 或相邻 scope 再补一轮，避免垂直路由被开放网页稀释。")
    external_fetch_strategy = external_fetch_strategy or {"enabled": False}
    if external_fetch_strategy.get("enabled"):
        suggestions.append("如 Guanlan 工作流后仍缺关键原文，可按 external_fetch_strategy 调用 WebFetch 补证。")
    role_counts: dict[str, int] = {}
    for item in results:
        role = str(item.get("evidence_role") or "")
        if role:
            role_counts[role] = role_counts.get(role, 0) + 1
    route_roles = [str(role) for role in quality.get("route_evidence_roles") or [] if str(role)]
    missing_roles = [role for role in route_roles if role not in role_counts]
    for role in missing_roles[:3]:
        suggestions.append(_role_gap_suggestion(role))
    status = "warn" if warnings or missing_roles else "pass"
    strong_primary_evidence = _quality_has_strong_primary_evidence(
        results,
        quality=quality,
        preferred_hits=preferred_hits,
        warnings=warnings,
    )
    quality_status = _quality_status(
        results,
        warnings,
        missing_roles,
        strong_primary_evidence=strong_primary_evidence,
    )
    interpretation = _quality_gap_interpretation(status)
    guanlan_next_steps = _quality_gap_next_steps(quality, warnings, missing_roles)
    reporting_contract = _quality_gap_reporting_contract(status)
    why_cautious = _quality_why_cautious(warnings, missing_roles)
    user_facing_status = _quality_user_facing_status(quality_status, why_cautious)
    followup_actions = _quality_followup_actions(quality, warnings, missing_roles, quality_status)
    workflow_plan = _quality_workflow_plan(quality, warnings, missing_roles, quality_status, followup_actions)
    execution_policy = _quality_execution_policy(quality_status, followup_actions, workflow_plan)
    agent_decision = _quality_agent_decision(
        quality_status,
        workflow_plan=workflow_plan,
        followup_actions=followup_actions,
        warnings=warnings,
        missing_roles=missing_roles,
    )
    browser_assist_suggestion = _browser_assist_suggestion_from_results(results)
    if browser_assist_suggestion.get("enabled"):
        suggestions.append("命中动态/登录态平台页；如公开读取不足，可请求用户授权后用宿主浏览器可见页补证。")

    return {
        "status": status,
        "quality_status": quality_status,
        "intent": quality.get("intent", "general"),
        "preferred_hit_count": len(preferred_hits),
        "result_count": len(results),
        "source_type_count": len(source_mix),
        "domain_count": len(domains),
        "source_mix": source_mix,
        "role_counts": dict(sorted(role_counts.items(), key=lambda row: (-row[1], row[0]))),
        "missing_roles": missing_roles,
        "strong_primary_evidence": strong_primary_evidence,
        "warnings": warnings,
        "site_filter": site_filter,
        "time_constraint": time_constraint,
        "agent_limit_advice": limit_advice,
        "scope_distinction": scope_distinction,
        "external_fetch_strategy": external_fetch_strategy,
        "browser_assist_suggestion": browser_assist_suggestion,
        "interpretation": interpretation,
        "guanlan_next_steps": guanlan_next_steps,
        "agent_reporting_contract": reporting_contract,
        "user_facing_status": user_facing_status,
        "why_cautious": why_cautious,
        "agent_workflow_plan": workflow_plan,
        "agent_decision": agent_decision,
        "followup_actions": followup_actions,
        "recommended_actions": followup_actions,
        "silent_repair_commands": limit_repairs,
        "agent_execution_policy": execution_policy,
        "suggestions": _unique_keep_order([item for item in suggestions if item]),
    }


def _quality_agent_decision(
    quality_status: str,
    *,
    workflow_plan: dict[str, Any],
    followup_actions: list[dict[str, Any]],
    warnings: list[str],
    missing_roles: list[str],
) -> dict[str, Any]:
    tools = [str(item.get("tool") or "") for item in followup_actions if str(item.get("tool") or "")]
    sequence = [str(item) for item in workflow_plan.get("tool_sequence") or [] if str(item)]
    all_tools = _unique_keep_order([*tools, *sequence])
    if quality_status == "ok":
        return {
            "code": "usable",
            "label": "可回答",
            "should_answer": True,
            "next_tool": "read" if "read" in all_tools else "",
            "reason": "结果已通过质量画像。",
        }
    if quality_status == "usable_with_gaps":
        return {
            "code": "usable_with_gaps",
            "label": "可回答但需说明缺口",
            "should_answer": True,
            "next_tool": "read",
            "reason": "已有强一手或偏好信源，但仍有证据角色缺口。",
        }
    if "hotnews" in all_tools:
        code, next_tool = "needs_hotnews", "hotnews"
    elif "feeds" in all_tools:
        code, next_tool = "needs_research", "feeds"
    elif "search" in all_tools or missing_roles:
        code, next_tool = "needs_scope_search", "search"
    elif "research" in all_tools:
        code, next_tool = "needs_research", "research"
    else:
        code, next_tool = "do_not_answer_yet", "route"
    return {
        "code": code,
        "label": "先补证据",
        "should_answer": False,
        "next_tool": next_tool,
        "reason": (warnings[0] if warnings else (f"缺少 {missing_roles[0]} 角色证据。" if missing_roles else "证据面不足。")),
    }


def _browser_assist_suggestion_from_results(results: list[Any]) -> dict[str, Any]:
    try:
        from guanlan.browser_assist import suggest_browser_assist_from_results
    except Exception:
        return {"enabled": False}

    rows: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            rows.append(item)
        elif hasattr(item, "to_dict"):
            rows.append(item.to_dict())
    return suggest_browser_assist_from_results(rows, max_urls=5)


def _quality_status(
    results: list[dict[str, Any]],
    warnings: list[str],
    missing_roles: list[str],
    *,
    strong_primary_evidence: bool = False,
) -> str:
    if not results:
        return "needs_more_evidence"
    if not warnings and not missing_roles:
        return "ok"
    if strong_primary_evidence and not any("未命中" in warning for warning in warnings):
        return "usable_with_gaps"
    if missing_roles or any("未命中" in warning for warning in warnings):
        return "quality_strict"
    return "needs_more_evidence"


def _quality_has_strong_primary_evidence(
    results: list[dict[str, Any]],
    *,
    quality: dict[str, Any],
    preferred_hits: list[dict[str, Any]],
    warnings: list[str],
) -> bool:
    if not results or not preferred_hits:
        return False
    if any("未命中" in warning for warning in warnings):
        return False
    primary_roles = {
        "official_primary",
        "company_primary",
        "technical_primary",
        "security_advisory",
        "weather_primary",
        "science_primary",
        "university_official",
        "database_official",
        "standard_original",
        "statute_original",
        "clinical_guideline",
        "official_stat",
        "sports_report",
        "official_alert",
        "forecast_track",
        "vulnerability_record",
        "security_advisory",
        "institution_primary",
        "chart_metric",
        "market_quote",
        "company_filing",
        "exchange_announcement",
        "regulatory_notice",
        "macro_data",
        "central_bank_notice",
        "statistics_release",
    }
    strong_source_types = {
        "政府/部委",
        "党央媒",
        "公司一手资料",
        "高校/院系官网",
        "英文官方/监管",
        "网络安全/漏洞/反诈",
        "天气/灾害/预警",
        "科学机构/科研新闻",
        "学术/论文检索",
        "标准/合规",
        "法律/司法",
        "医疗/健康",
        "体育/赛事/转会",
        "财经/公告披露",
        "财经/行情数据",
        "财经/宏观数据",
        "财经/新闻报道",
        "办公软件/AI Office/SaaS",
        "文娱/内容平台",
        "欧美文娱/音乐产业",
        "日韩文娱/K-pop/J-pop",
        "考试/培训/备考",
    }
    preferred_scopes = {str(scope) for scope in quality.get("preferred_scopes") or [] if str(scope)}
    preferred_ratio = len(preferred_hits) / max(len(results), 1)
    role_hit = any(str(item.get("evidence_role") or "") in primary_roles for item in preferred_hits)
    scope_hit = any(str(item.get("matched_scope") or "") in preferred_scopes for item in preferred_hits)
    strong_type_hit = any(
        str(item.get("source_type") or "") in strong_source_types
        or int(item.get("trust_level") or 0) >= 4
        for item in preferred_hits
    )
    return strong_type_hit and (role_hit or scope_hit or preferred_ratio >= 0.5)


def _quality_why_cautious(warnings: list[str], missing_roles: list[str]) -> list[str]:
    reasons: list[str] = []
    for warning in warnings:
        reasons.append(warning)
    for role in missing_roles:
        reasons.append(f"缺少 `{role}` 角色证据。")
    return _unique_keep_order(reasons)


def _quality_user_facing_status(quality_status: str, why_cautious: list[str]) -> str:
    if quality_status == "ok":
        return "Guanlan 已返回可用证据；可以继续综合，但仍应保留来源和时效边界。"
    if quality_status == "usable_with_gaps":
        return "Guanlan 已返回强相关的一手/偏好信源；可以继续使用，但最好读取代表原文并说明仍有证据角色缺口。"
    if quality_status == "quality_strict":
        reason = why_cautious[0] if why_cautious else "当前证据包覆盖不足"
        return f"Guanlan 已找到线索，但质量画像提示还不适合直接下结论：{reason} 接下来直接用 Guanlan 补一轮证据。"
    return "Guanlan 已找到部分线索，但当前证据面还不够稳；接下来直接补不同 scope、站点或研究工作流。"


def _quality_followup_actions(
    quality: dict[str, Any],
    warnings: list[str],
    missing_roles: list[str],
    quality_status: str,
) -> list[dict[str, Any]]:
    if quality_status in {"ok", "usable_with_gaps"}:
        return [
            {
                "label": "读取代表原文",
                "command": "guanlan read \"URL\" --quality-report",
                "reason": "证据包可用时，继续摘读关键原文并核对正文质量。",
                "run_policy": "run_when_deepening_answer",
                "tool": "read",
            }
        ]
    query = _shell_quote_for_command(str(quality.get("route_query") or "问题"))
    intent = str(quality.get("intent") or "general")
    route_intents = [str(item) for item in quality.get("route_intents") or [] if str(item)]
    preferred_scopes = [str(item) for item in quality.get("preferred_scopes") or [] if str(item)]
    actions: list[dict[str, str]] = [
        {
            "label": "查看路由计划",
            "command": f"guanlan route {query} --json",
            "reason": "确认 Guanlan 推荐的 source pools、evidence roles 和 caveats。",
            "run_policy": "run_immediately",
            "tool": "route",
        }
    ]
    preset = _quality_followup_preset(intent, route_intents)
    actions.append(
        {
            "label": "跑深度研究",
            "command": f"guanlan research {query} --preset {preset} --advisor",
            "reason": "让 Guanlan 按证据角色重写 query、合并候选并标出补证缺口。",
            "run_policy": "run_immediately",
            "tool": "research",
        }
    )
    if preferred_scopes:
        actions.append(
            {
                "label": f"补 {preferred_scopes[0]} 信源",
                "command": f"guanlan search {query} --scope {preferred_scopes[0]} --limit 80 --trace",
                "reason": "补当前质量画像偏好的垂直信源池，不要只看开放网页 fallback。",
                "run_policy": "run_immediately",
                "tool": "search",
            }
        )
    if any(role in missing_roles for role in ("fresh_news", "public_discussion")) or "hot_trend" in route_intents:
        actions.append(
            {
                "label": "补最新热度",
                "command": "guanlan hotnews today --limit 80 --trends",
                "reason": "近期/热点问题需要热榜或趋势信号交叉确认。",
                "run_policy": "run_immediately",
                "tool": "hotnews",
            }
        )
    if "tech" in route_intents or intent == "tech":
        actions.append(
            {
                "label": "补 AI/RSS 线索",
                "command": "guanlan feeds curated --category ai --limit 80",
                "reason": "技术/AI 问题需要 RSS/精品内容流作为阅读发现线索。",
                "run_policy": "run_immediately",
                "tool": "feeds",
            }
        )
    if any("域名集中" in warning or "来源类型" in warning for warning in warnings):
        actions.append(
            {
                "label": "扩大信源面",
                "command": f"guanlan dossier {query} --limit 80 --format context",
                "reason": "用 dossier/compare/timeline 这类 Guanlan 工作流扩展证据面，而不是立刻切到通用 web_search。",
                "run_policy": "run_immediately",
                "tool": "dossier",
            }
        )
    return actions[:5]


def _quality_execution_policy(
    quality_status: str,
    followup_actions: list[dict[str, Any]],
    workflow_plan: dict[str, Any],
) -> dict[str, Any]:
    run_now = quality_status not in {"ok", "usable_with_gaps"} and bool(followup_actions)
    minimum_tools = int(workflow_plan.get("minimum_guanlan_tools") or 0)
    tool_sequence = [str(item) for item in workflow_plan.get("tool_sequence") or [] if str(item)]
    tool_text = " -> ".join(tool_sequence[:minimum_tools or len(tool_sequence)])
    return {
        "mode": "run_followups_now" if run_now else "continue_or_read",
        "should_run_followups": run_now,
        "instruction": (
            f"不要停在建议；在预算允许且用户未禁止时，直接完成至少 {minimum_tools} 个最适合的 Guanlan 工具步骤"
            f"（{tool_text or 'search -> read'}），再决定是否需要 fallback。"
            if run_now
            else "证据包已可用；需要深化时直接读取代表原文。"
        ),
        "fallback_rule": "只有 Guanlan followup_actions 执行后仍缺关键证据，才切到通用 web_search/web_fetch。",
        "action_count": len(followup_actions),
    }


def _quality_workflow_plan(
    quality: dict[str, Any],
    warnings: list[str],
    missing_roles: list[str],
    quality_status: str,
    followup_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    intent = str(quality.get("intent") or "general")
    route_intents = {str(item) for item in quality.get("route_intents") or [] if str(item)}
    tools = _unique_keep_order(str(action.get("tool") or "") for action in followup_actions if str(action.get("tool") or ""))
    requires_hotnews = (
        any(role in missing_roles for role in ("fresh_news", "public_discussion"))
        or "hot_trend" in route_intents
    )
    requires_feeds = bool({"tech", "wps_office"} & route_intents) or intent in {"tech", "wps_office"}
    requires_breadth = any("域名集中" in warning or "来源类型" in warning for warning in warnings)
    if quality_status in {"ok", "usable_with_gaps"}:
        return {
            "tier": "2-step",
            "minimum_guanlan_tools": 2,
            "planned_tool_count": 2,
            "tool_sequence": ["search", "read"],
            "workflow_kind": "search_then_read",
            "summary": (
                "结果已可用时，先保留搜索证据，再读取代表原文完成核验；"
                "若仍缺角色证据，在回答中说明边界。"
            ),
            "must_finish_before_fallback": False,
        }

    minimum_tools = 3
    workflow_kind = "route_research_scope"
    summary = "默认至少完成 route、research、垂直 search 三步，再判断证据是否够用。"
    if requires_hotnews:
        minimum_tools = 4
        workflow_kind = "route_research_scope_hotnews"
        summary = "涉及实时/热点时，至少完成 route、research、scope search、hotnews 四步交叉补证。"
    elif requires_feeds:
        minimum_tools = 4
        workflow_kind = "route_research_scope_feeds"
        summary = "技术/AI 问题至少完成 route、research、scope search、feeds 四步，补 RSS 发现线索。"
    elif requires_breadth:
        minimum_tools = 4
        workflow_kind = "route_research_scope_breadth"
        summary = "来源过窄时，至少完成 route、research、scope search、dossier 四步扩展证据面。"

    if not tools:
        tools = ["route", "research", "search"]
    return {
        "tier": "4-step" if minimum_tools >= 4 else "3-step",
        "minimum_guanlan_tools": minimum_tools,
        "planned_tool_count": len(tools),
        "tool_sequence": tools,
        "workflow_kind": workflow_kind,
        "summary": summary,
        "must_finish_before_fallback": True,
    }


def _quality_gap_interpretation(status: str) -> str:
    if status != "warn":
        return ""
    return (
        "当前提示是观澜质量画像在提醒“证据包覆盖不足”，不是主题没有资料，也不等于观澜搜索能力失败；"
        "优先继续使用观澜的路由、研究、垂直 scope、feeds/hotnews/read 等能力补证据，再考虑切到通用 web_search/web_fetch。"
    )


def _quality_gap_reporting_contract(status: str) -> list[str]:
    if status != "warn":
        return [
            "可以向使用者说 Guanlan 已返回可用证据；仍需按来源边界引用。",
        ]
    return [
        "不要向 AI 使用者概括为“Guanlan 搜索失败”或“Guanlan 老是失败”。",
        "不要在面向用户的回答里顺嘴写“Guanlan 崩了/抽风了/挂了/炸了/翻车/拉胯/坏了”。",
        "应表述为“当前 Guanlan 证据包未完全通过质量画像，需要继续补证据/换 scope/跑 research”。",
        "如果只是目标页公开读取超时或源站响应慢，应表述为“已按 Guanlan 定点补证路线读取目标页并保留来源边界”。",
        "只有所有 Guanlan 后续能力都尝试后仍无可用证据，才说“本轮 Guanlan 未取得足够证据”。",
        "如果只是 Baidu/Bing/DuckDuckGo 某个后端异常，应说“某后端受限/低相关，Guanlan 已给出恢复路线”。",
    ]


def _quality_gap_next_steps(
    quality: dict[str, Any],
    warnings: list[str],
    missing_roles: list[str],
) -> list[str]:
    if not warnings and not missing_roles:
        return []
    intent = str(quality.get("intent") or "general")
    route_intents = [str(item) for item in quality.get("route_intents") or [] if str(item)]
    preferred_scopes = [str(item) for item in quality.get("preferred_scopes") or [] if str(item)]
    steps = [
        "先运行 `guanlan route \"问题\" --json` 看推荐的 source pools、evidence roles 和 caveats。",
    ]
    preset = _quality_followup_preset(intent, route_intents)
    if preset:
        steps.append(f"再运行 `guanlan research \"问题\" --preset {preset} --advisor`，让观澜按证据角色重写 query 并合并候选。")
    if preferred_scopes:
        steps.append(f"补跑 `guanlan search \"问题\" --scope {preferred_scopes[0]} --limit 80 --trace`，不要只看开放网页 fallback。")
    if any(role in missing_roles for role in ("fresh_news", "public_discussion")) or "hot_trend" in route_intents:
        steps.append("涉及近期/热点时补跑 `guanlan hotnews today --limit 80 --trends` 或对应平台热榜。")
    if "tech" in route_intents or intent == "tech":
        steps.append("技术/AI/开发者问题补跑 `guanlan feeds curated --category ai --limit 80`，RSS 是阅读发现线索。")
    if any("域名集中" in warning or "来源类型" in warning for warning in warnings):
        steps.append("用 Guanlan 的 `--scope`、`--site`、`compare/timeline/dossier` 扩大信源面，而不是立刻切到通用 web_search。")
    steps.append("只有 Guanlan 的多轮补证仍缺关键网页时，再用 web_search/web_fetch 作外部兜底，并保留观澜质量提示。")
    return _unique_keep_order(steps)[:5]


def _analyze_search_query_shape(
    query: str,
    *,
    effective_scope: str | None = None,
    quality: dict[str, Any] | None = None,
    route_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality = quality or {}
    route_plan = route_plan or {}
    clean_query = _collapse_ws(query)
    backend_query = clean_query
    notes: list[str] = []
    reasons: list[str] = []
    relevance_terms = _query_relevance_terms(clean_query)
    semantic_analysis = analyze_query_semantics(clean_query)
    entities = _query_shape_entities(clean_query)
    is_meaningless = _looks_like_meaningless_query(clean_query)
    if is_meaningless:
        return {
            "status": "rejected",
            "rejected": True,
            "reason": "query 近似乱码或低信息量测试串，继续搜索更可能随机返回噪声页面。",
            "backend_query": "",
            "fallback_open_query": "",
            "relevance_terms": relevance_terms,
            "entities": entities,
            "short_query": len(clean_query) <= 8 or len(relevance_terms) <= 1,
            "overlong_query": len(clean_query) >= 100,
            "multi_entity": len(entities) >= 4,
            "rewritten": False,
            "notes": [],
        }

    if len(clean_query) >= 100:
        compressed = _compress_overlong_query(clean_query, route_plan=route_plan)
        if compressed and compressed != backend_query:
            backend_query = compressed
            notes.append("query 过长，已提炼为更可搜索的关键词串。")
            reasons.append("overlong_query")

    expanded = _expand_search_query(
        backend_query,
        effective_scope=effective_scope,
        quality=quality,
        entities=entities,
        semantic_analysis=semantic_analysis,
    )
    if expanded != backend_query:
        backend_query = expanded
        notes.append("query 偏短、偏歧义或缺少任务约束，已自动补充更贴近意图的词。")
        reasons.append("expanded_query")
    if semantic_analysis.get("matched_rules"):
        notes.append("检测到固定短语/品牌/年份事件语义，已补实体别名和高信号限定词。")
        reasons.append("semantic_compound")

    if len(entities) >= 4:
        notes.append("检测到多实体查询；单次搜索只适合先取线索，后续更适合 compare/dossier 分步整理。")
        reasons.append("multi_entity")

    status = "rewritten" if reasons else "ok"
    return {
        "status": status,
        "rejected": False,
        "reason": "",
        "backend_query": backend_query,
        "fallback_open_query": backend_query,
        "relevance_terms": relevance_terms,
        "entities": entities,
        "short_query": len(clean_query) <= 8 or len(relevance_terms) <= 1,
        "overlong_query": len(clean_query) >= 100,
        "multi_entity": len(entities) >= 4,
        "rewritten": bool(reasons),
        "rewrite_reasons": reasons,
        "semantic_rules": list(semantic_analysis.get("matched_rules") or []),
        "notes": notes,
    }


def _compress_overlong_query(query: str, *, route_plan: dict[str, Any] | None = None) -> str:
    route_plan = route_plan or {}
    keywords: list[str] = []
    for hint in _LONG_QUERY_KEYPHRASE_HINTS:
        if hint.lower() in query.lower():
            keywords.append(hint)
    keywords.extend(_query_shape_entities(query))
    keywords.extend(_query_relevance_terms(query))
    keep: list[str] = []
    for token in keywords:
        normalized = token.strip()
        if not normalized or normalized in _QUERY_REWRITE_STOPWORDS:
            continue
        keep.append(normalized)
    keep = _unique_keep_order(keep)
    freshness = str(route_plan.get("freshness") or "")
    if freshness and freshness not in keep:
        keep.append(freshness)
    compact = " ".join(keep[:8]).strip()
    if len(compact) < 8:
        compact = query[:96].strip()
    return compact


def _expand_search_query(
    query: str,
    *,
    effective_scope: str | None = None,
    quality: dict[str, Any] | None = None,
    entities: list[str] | None = None,
    semantic_analysis: dict[str, Any] | None = None,
) -> str:
    quality = quality or {}
    entities = entities or []
    semantic_analysis = semantic_analysis or {}
    normalized = _collapse_ws(query).strip()
    lowered = normalized.lower()
    additions: list[str] = list(semantic_analysis.get("rewrite_terms") or [])
    ai_model_query = _canonical_ai_model_search_query(normalized, quality)
    if ai_model_query and ai_model_query != normalized:
        normalized = ai_model_query
        lowered = normalized.lower()
    intent = str(quality.get("intent") or "")
    is_wps_scope = effective_scope == "wps_office" or intent == "wps_office"
    wps_subroute = _wps_office_subroute(normalized) if is_wps_scope else "general"
    is_short_wps_brand_query = is_wps_scope and (
        len(normalized) <= 16
        or normalized.replace(" ", "").lower() in {"wpsai", "wps灵犀", "wps365"}
    )
    if is_wps_scope and wps_office_needs_open_web(
        normalized,
        intents=[intent] if intent else [],
        scopes=[effective_scope] if effective_scope else [],
    ):
        return normalized
    if normalized == "苹果" and effective_scope in {"ecommerce", "tech_dev", "social_web"}:
        if effective_scope == "ecommerce":
            additions.extend(["iPhone", "手机", "价格", "用户评价"])
        elif effective_scope == "tech_dev":
            additions.extend(["Apple", "iPhone", "芯片", "参数"])
        else:
            additions.extend(["Apple", "iPhone", "知乎", "微博", "评价"])
    if len(normalized) <= 8 or (len(_query_relevance_terms(normalized)) <= 1 and len(normalized) <= 16):
        if any(term in normalized for term in ("人口", "多少")):
            additions.extend(["统计", "数据", "官方"])
        if any(term in normalized for term in ("为什么", "原因")):
            additions.extend(["原因", "调查", "数据", "观点"])
        if effective_scope == "ecommerce":
            additions.extend(["价格", "购买", "评测", "用户评价"])
        elif effective_scope == "tech_dev":
            additions.extend(["官方", "文档", "GitHub"])
        elif effective_scope == "social_web":
            additions.extend(["知乎", "微博", "小红书", "讨论"])
        elif intent == "policy":
            additions.extend(["官方", "原文", "通知"])
        elif intent in {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"} or str(effective_scope or "").startswith("finance"):
            additions.extend(["财报", "公告", "市场"])
        elif intent == "tech":
            additions.extend(["官方", "文档", "benchmark"])
    if is_short_wps_brand_query:
        if wps_subroute == "wps_ai":
            additions.extend(["AI PPT", "职场效率", "文档写作", "表格分析", "选题", "横评", "工具对比"])
        elif wps_subroute == "lingxi":
            additions.extend(["办公智能体", "AI Agent", "对话式办公", "同屏交互", "选题"])
        elif wps_subroute == "wps365":
            additions.extend(["企业大脑", "组织协同", "AI Office", "行业落地", "办公智能体"])
        else:
            additions.extend(["行业热点", "选题", "办公智能体", "AI PPT", "文档协作"])
    if len(normalized) <= 40 and len(entities) >= 4 and not any(term in lowered for term in ("对比", "比较", "排名")):
        additions.extend(["对比", "数据"])
    additions = [item for item in _unique_keep_order(additions) if item and item not in normalized]
    if not additions:
        return normalized
    max_additions = 5 if is_short_wps_brand_query else 4
    if semantic_analysis.get("matched_rules"):
        max_additions = max(max_additions, 6)
    return f"{normalized} {' '.join(additions[:max_additions])}".strip()


_AI_MODEL_QUERY_FAMILY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("GLM", r"\bGLM(?:[-\s]?\d+(?:\.\d+)?)?\b|智谱|zhipu|chatglm|bigmodel"),
    ("Kimi", r"\bKimi(?:[-\s]?K)?(?:[-\s]?\d+(?:\.\d+)?)?\b|moonshot|月之暗面"),
    ("DeepSeek", r"\bDeepSeek(?:[-\s]?[A-Za-z]?\d+(?:\.\d+)?)?\b|深度求索"),
    ("Qwen", r"\bQwen(?:[-\s]?\d+(?:\.\d+)?)?\b|通义|千问"),
    ("Hunyuan", r"\bHunyuan\b|混元"),
    ("Ernie", r"\bErnie\b|文心|ERNIE"),
    ("Doubao", r"\bDoubao(?:[-\s]?\d+(?:\.\d+)?)?\b|豆包|seedance"),
)

_AI_MODEL_QUERY_TASK_TERMS = (
    "版本",
    "发布",
    "声量",
    "热度",
    "能力",
    "强在哪",
    "谁更强",
    "对比",
    "比较",
    "评测",
    "横评",
    "benchmark",
    "code",
    "coding",
    "编程",
    "模型",
)


def _canonical_ai_model_search_query(query: str, quality: dict[str, Any]) -> str:
    route_intents = set(quality.get("route_intents") or [])
    intent = str(quality.get("intent") or "")
    text = _collapse_ws(query)
    lowered = text.lower()
    mentions = _ai_model_query_mentions(text)
    if not mentions:
        return ""
    task_like = (
        len(mentions) >= 2
        or bool(route_intents & {"tech", "public_opinion", "company_primary"})
        or intent in {"tech", "public_opinion"}
        or any(term in lowered or term in text for term in _AI_MODEL_QUERY_TASK_TERMS)
    )
    if not task_like:
        return ""
    terms: list[str] = []
    for mention in mentions:
        label = mention["family"]
        version = mention.get("version") or ""
        terms.append(f"{label} {version}".strip())
    if any(term in lowered for term in ("code", "coding")) or "编程" in text:
        terms.append("Code")
    if len(mentions) >= 2 or any(term in text for term in ("对比", "比较", "比", "谁更强", "强在哪")):
        terms.append("对比")
    if "声量" in text or "热度" in text:
        terms.append("声量")
    if any(term in text for term in ("能力", "强在哪", "谁更强", "亮点", "优势")):
        terms.append("能力")
    if any(term in text for term in ("发布", "版本", "更新")):
        terms.append("发布")
    if intent == "tech" or "tech" in route_intents or any(term in lowered for term in ("code", "coding", "benchmark")):
        terms.append("benchmark")
    canonical = " ".join(_unique_keep_order(terms)).strip()
    return canonical if len(canonical) >= 6 else ""


def _ai_model_query_mentions(query: str) -> list[dict[str, str]]:
    hits: list[tuple[int, str, str]] = []
    for family, pattern in _AI_MODEL_QUERY_FAMILY_PATTERNS:
        for match in re.finditer(pattern, query or "", flags=re.I):
            raw = _collapse_ws(match.group(0))
            version_match = re.search(r"\d+(?:\.\d+)?", raw)
            hits.append((match.start(), family, version_match.group(0) if version_match else ""))
    mentions: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, family, version in sorted(hits, key=lambda item: item[0]):
        if family in seen:
            continue
        seen.add(family)
        mentions.append({"family": family, "version": version})
    return mentions


def _query_shape_entities(query: str, *, semantic_analysis: dict[str, Any] | None = None) -> list[str]:
    tokens = re.split(r"[\s,，。；;、/|()（）]+", _collapse_ws(query))
    entities: list[str] = []
    for token in tokens:
        clean = token.strip()
        lower = clean.lower()
        if not clean or lower in _QUERY_REWRITE_STOPWORDS:
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", clean):
            entities.append(clean)
            continue
        if _contains_cjk(clean):
            if 2 <= len(clean) <= 8 and clean not in {"最新", "最近", "刚刚", "今天", "多少", "怎么申请", "为什么"}:
                entities.append(clean)
                continue
        elif re.search(r"[A-Za-z]", clean) and 2 <= len(clean) <= 20:
            entities.append(clean)
    return _unique_keep_order(entities)


def _looks_like_meaningless_query(query: str) -> bool:
    text = _collapse_ws(query).strip()
    if not text or _contains_cjk(text) or " " in text:
        return False
    lowered = text.lower()
    if any(term in lowered for term in _MEANINGLESS_QUERY_ALLOWLIST):
        return False
    if not re.fullmatch(r"[a-z0-9_-]{10,}", lowered):
        return False
    letters = [char for char in lowered if "a" <= char <= "z"]
    digits = [char for char in lowered if char.isdigit()]
    vowel_count = sum(1 for char in letters if char in "aeiou")
    vowel_ratio = vowel_count / max(len(letters), 1)
    keyboard_run = any(run in lowered for run in _QUERY_KEYBOARD_RUNS)
    return bool(keyboard_run or (digits and vowel_ratio < 0.2))


def _quality_followup_preset(intent: str, route_intents: list[str]) -> str:
    candidates = [intent, *route_intents]
    mapping = {
        "policy": "policy",
        "official_position": "official",
        "local": "local",
        "industry": "industry",
        "global_industry": "global_industry",
        "finance": "finance",
        "finance_quote": "finance",
        "finance_disclosure": "finance",
        "finance_macro": "finance",
        "finance_sentiment": "finance",
        "finance_research": "finance",
        "tech": "tech",
        "wps_office": "wps_office",
        "academic": "academic",
        "university_admissions": "university",
        "reputation": "reputation",
        "purchase_advice": "reputation",
        "global_reputation": "global_reputation",
        "entertainment": "entertainment",
        "global_entertainment": "global_entertainment",
        "jp_kr_entertainment": "jp_kr_entertainment",
        "company_primary": "company",
        "sports": "sports",
        "weather_disaster": "weather_disaster",
        "cybersecurity": "cybersecurity",
        "science": "science",
        "career": "career",
        "podcast": "podcast",
        "test_prep": "test_prep",
    }
    for candidate in candidates:
        clean = str(candidate).split(":", 1)[-1]
        if clean in mapping:
            return mapping[clean]
    return "general"


def _source_gap_suggestion(
    quality: dict[str, Any],
    preferred_types: set[str],
    preferred_scopes: set[str],
) -> str:
    if preferred_scopes:
        scope_hint = ",".join(sorted(preferred_scopes))
        return f"直接补搜 `--scope {scope_hint.split(',')[0]}` 或指定相关官方/垂类站点。"
    if preferred_types:
        return "直接补充 " + "、".join(sorted(preferred_types)[:3]) + " 类型信源。"
    intent = str(quality.get("intent") or "general")
    return f"按 {intent} 意图直接补充更贴近问题的第一手信源。"


def _role_gap_suggestion(role: str) -> str:
    mapping = {
        "official_primary": "缺少官方原文/主管部门口径，直接补搜 `--scope gov`、`--scope party_central` 或 `--scope global_official`。",
        "authoritative_report": "缺少权威报道，直接补搜党央媒或核心地方官媒。",
        "user_sample": "缺少公开用户样本，直接补搜知乎、微博、小红书、B站等公开页，并标明样本偏差。",
        "industry_report": "缺少产业/垂类材料，直接补搜商业媒体、电商垂类或行业报告。",
        "fresh_news": "缺少近期材料，直接加入最近/今日/本周等时效词并开启 trace 核对时间线。",
        "developer_discussion": "缺少开发者实践反馈，直接补搜 GitHub、V2EX、掘金或技术社区。",
        "company_primary": "缺少公司一手资料，直接补搜 `--scope company_primary` 或官方文档/价格/发布说明。",
        "technical_primary": "缺少技术一手资料，直接补搜 `--scope developer`、官方文档、GitHub release 或 issue。",
        "review": "缺少评价样本，直接补搜 Reddit、Hacker News、G2、Trustpilot 等公开样本并说明偏差。",
        "university_official": "缺少高校/院系官网材料，直接补搜 `--scope university` 或指定学校/院系站点。",
        "department_page": "缺少院系官网页面，直接补搜 `--scope university` 或指定院系域名。",
        "faculty_profile": "缺少导师主页/教师列表，直接补搜院系官网的导师、教师、师资队伍页面。",
        "admission_catalog": "缺少招生目录/招生简章，直接补搜研究生招生网或学校研招办页面。",
        "standard_original": "缺少标准原文/标准组织材料，直接补搜 `--scope global_official` 或指定 ISO/IEC/NIST 等站点。",
        "regulator_guidance": "缺少监管解释或主管机构材料，直接补搜 `--scope gov` 或 `--scope global_official`。",
        "clinical_guideline": "缺少临床指南/专业机构材料，直接补搜 WHO、CDC、FDA、卫健委或学术数据库。",
        "statute_original": "缺少法律条文原文，直接补搜 `--scope gov` 或指定人大、法院、司法部等站点。",
        "case_record": "缺少案例/裁判文书材料，直接补搜法院、裁判文书或权威法律数据库。",
        "market_quote": "缺少行情/指数数据入口，直接补搜 `--scope finance_quote`，并标注行情时间和可能延迟。",
        "company_filing": "缺少公告/财报/披露原文，直接补搜 `--scope finance_disclosure` 或指定巨潮、交易所、SEC。",
        "exchange_announcement": "缺少交易所公告入口，直接补搜 `--scope finance_disclosure` 或指定上交所/深交所/HKEXnews。",
        "regulatory_notice": "缺少监管函、问询、处罚或风险提示，直接补搜 `--scope finance_disclosure` 和监管机构站点。",
        "macro_data": "缺少宏观官方数据，直接补搜 `--scope finance_macro` 或指定统计局、央行、FRED。",
        "central_bank_notice": "缺少央行/货币政策口径，直接补搜 `--scope finance_macro` 或指定央行站点。",
        "sentiment_sample": "缺少投资者情绪样本，直接补搜 `--scope finance_sentiment`，但只能作为样本线索。",
        "analyst_opinion": "缺少研报/机构观点，直接补搜 `--scope finance_research`，并和公告财报交叉验证。",
        "market_news": "缺少财经新闻时间线，直接补搜 `--scope finance_news` 或财联社、证券时报、第一财经等站点。",
    }
    return mapping.get(role, f"缺少 `{role}` 角色证据，直接补充对应信源后再下判断。")


def _quality_term_matches(text: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9_+-]+", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", text, flags=re.I))
    return term.lower() in text


def _is_industry_funding_context(text: str) -> bool:
    """Treat financing/valuation as industry unless capital-market terms are explicit."""
    industry_terms = (
        "具身智能",
        "机器人",
        "robotics",
        "robot",
        "企业 融资",
        "企业融资",
        "智元",
        "宇树",
        "傅利叶",
        "市场",
        "行业",
        "产业",
        "创业",
    )
    capital_market_terms = (
        "股票",
        "股价",
        "上市公司",
        "财报",
        "公告",
        "研报",
        "基金",
        "etf",
        "债券",
        "行情",
        "净值",
        "stock",
        "share price",
        "earnings",
        "filing",
    )
    return _quality_term_matches(text, "融资") and any(term in text for term in industry_terms) and not any(term in text for term in capital_market_terms)


def detect_recency_intent(query: str) -> dict[str, Any]:
    """Detect whether a query needs tighter time bounds."""
    text = _collapse_ws(query).lower()
    today = dt.date.today()
    matched_terms: list[str] = []
    window_days = 0
    label = ""

    explicit_windows: tuple[tuple[str, int, tuple[str, ...]], ...] = (
        ("today", 1, ("今天", "今日", "当天", "当日", "刚刚", "实时", "24小时", "近24小时", "now", "today")),
        ("yesterday", 2, ("昨天", "昨日", "48小时", "近48小时")),
        ("week", 7, ("近一周", "最近一周", "过去一周", "一周内", "本周", "这周", "7天", "7日", "七天")),
        (
            "month",
            30,
            ("近一个月", "最近一个月", "过去一个月", "一个月内", "本月", "这个月", "30天", "30日", "三十天"),
        ),
        ("quarter", 90, ("近三个月", "最近三个月", "过去三个月", "一个季度", "本季度", "90天", "90日")),
    )
    for candidate_label, days, terms in explicit_windows:
        found = [term for term in terms if _recency_term_matches(text, term)]
        if found:
            label = candidate_label
            window_days = days
            matched_terms.extend(found)
            break

    if not window_days and _recency_term_matches(text, "今年"):
        label = "year_to_date"
        year_start = dt.date(today.year, 1, 1)
        window_days = max((today - year_start).days + 1, 1)
        matched_terms.append("今年")

    if not window_days:
        explicit_year = _explicit_year_recency(text, today)
        if explicit_year:
            return explicit_year

    if not window_days:
        hot_terms = ("热点", "热搜", "快讯", "突发", "爆发", "热议", "刷屏")
        found_hot = [term for term in hot_terms if _recency_term_matches(text, term)]
        if found_hot:
            label = "hot"
            window_days = 7
            matched_terms.extend(found_hot)

    if not window_days:
        recent_terms = (
            "近期",
            "最近",
            "最新",
            "新近",
            "动态",
            "进展",
            "趋势",
            "舆情",
            "新闻",
            "报道",
            "current",
            "recent",
            "latest",
            "news",
        )
        found_recent = [term for term in recent_terms if _recency_term_matches(text, term)]
        if found_recent:
            label = "recent"
            window_days = _RECENCY_DEFAULT_WINDOW_DAYS
            matched_terms.extend(found_recent)

    if not window_days:
        years = sorted({int(match) for match in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)})
        bounded_years = [year for year in years if 1990 <= year <= today.year + 1]
        if bounded_years:
            start_year = min(bounded_years)
            end_year = max(bounded_years)
            start = dt.date(start_year, 1, 1)
            end = dt.date(end_year, 12, 31)
            if end > today:
                end = today
            window_days = max((end - start).days + 1, 1)
            return {
                "enabled": True,
                "label": "year_range" if len(bounded_years) > 1 else "year",
                "window_days": window_days,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "matched_terms": [str(year) for year in bounded_years],
            }

    if not window_days:
        return {
            "enabled": False,
            "label": "",
            "window_days": 0,
            "start_date": "",
            "end_date": today.isoformat(),
            "matched_terms": [],
        }

    start = today - dt.timedelta(days=max(window_days - 1, 0))
    return {
        "enabled": True,
        "label": label,
        "window_days": window_days,
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "matched_terms": matched_terms,
    }


def _explicit_year_recency(text: str, today: dt.date) -> dict[str, Any] | None:
    years = sorted({int(match) for match in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)})
    bounded_years = [year for year in years if 1990 <= year <= today.year + 1]
    if not bounded_years:
        return None
    start_year = min(bounded_years)
    end_year = max(bounded_years)
    start = dt.date(start_year, 1, 1)
    end = dt.date(end_year, 12, 31)
    if end > today:
        end = today
    window_days = max((end - start).days + 1, 1)
    return {
        "enabled": True,
        "label": "year_range" if len(bounded_years) > 1 else "year",
        "window_days": window_days,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "matched_terms": [str(year) for year in bounded_years],
    }


def build_query_strategy(
    query: str,
    *,
    route_plan: dict[str, Any] | None = None,
    recency: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build query rewrites that preserve source roles instead of one flat query."""
    clean_query = _collapse_ws(query)
    route_plan = route_plan or build_route_plan(clean_query).to_dict()
    recency = recency or detect_recency_intent(clean_query)
    quality = quality or {}
    intents = list(route_plan.get("primary_intents") or []) + list(route_plan.get("secondary_intents") or [])
    roles = list(route_plan.get("evidence_roles") or [])
    variants: list[dict[str, str]] = []
    query_shape = _analyze_search_query_shape(
        clean_query,
        effective_scope=str(quality.get("requested_scope") or "") or None,
        quality=quality,
        route_plan=route_plan,
    )
    rewritten_query = str(query_shape.get("backend_query") or "")
    search_friendly_query = rewritten_query if query_shape.get("rewritten") and rewritten_query else clean_query

    def add(role: str, q: str, reason: str) -> None:
        normalized = _collapse_ws(q)
        if not normalized:
            return
        if any(item["query"] == normalized for item in variants):
            return
        variants.append({"role": role, "query": normalized, "reason": reason})

    add("base", clean_query, "用户原始问题，保留语义中心")
    if query_shape.get("rewritten") and query_shape.get("backend_query"):
        add("query_rewrite", str(query_shape.get("backend_query")), "对过短、过长、歧义或多实体 query 先做搜索友好的重写")
    if {"policy", "official_position", "local"} & set(intents):
        official_terms = "扶持 申报 通知 政策" if any(term in clean_query for term in ("跨境电商", "跨境电子商务", "横琴")) else "官方 原文 通知"
        add("official_primary", f"{clean_query} {official_terms}", "政策/官方问题先找一手口径")
        add("authoritative_report", f"{clean_query} 人民日报 新华社 央视", "补党央媒与权威报道")
    if "global_policy" in intents:
        add("official_primary", f"{clean_query} official regulation standard primary source", "英文政策/监管问题先找官方或标准组织原文")
        add("authoritative_report", f"{clean_query} Reuters AP BBC analysis timeline", "补主流新闻时间线和背景")
    if "company_primary" in intents:
        add("company_primary", f"{clean_query} official docs pricing release notes", "公司/产品问题优先找一手资料")
        add("technical_primary", f"{clean_query} github changelog status documentation", "补开发者文档、release 和状态页")
    if {"reputation", "purchase_advice"} & set(intents):
        add("user_sample", f"{clean_query} 用户评价 吐槽 体验", "口碑问题先找用户样本语言")
        add("review", f"{clean_query} 测评 优缺点 值不值得买", "补评测和购买决策材料")
    if "global_reputation" in intents:
        add("user_sample", f"{clean_query} reddit hacker news user review complaints", "英文口碑问题先找公开社区样本")
        add("review", f"{clean_query} G2 Trustpilot Capterra review", "补评价站点样本并标注偏差")
    if "ecommerce" in intents or str(quality.get("requested_scope") or "") == "ecommerce":
        add("industry_report", f"{clean_query} 电商 零售 行业 数据 案例", "电商问题先看垂类媒体和行业材料")
        add("review", f"{clean_query} 价格 售后 投诉 用户评价 值不值得买", "补购买决策、售后和用户样本")
        try:
            from guanlan.ebrun_channels import ebrun_query_variants

            for variant in ebrun_query_variants(clean_query, limit=2):
                add(
                    str(variant.get("role") or "ecommerce_vertical_feed"),
                    str(variant.get("query") or ""),
                    str(variant.get("reason") or "补亿邦动力垂类频道线索"),
                )
        except Exception:
            pass
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
    requested_scope = str(quality.get("requested_scope") or "")
    if finance_intents & set(intents) or requested_scope.startswith("finance"):
        if "finance_quote" in intents or requested_scope == "finance_quote":
            add("market_quote", f"{clean_query} 行情 股价 涨跌幅 指数 东方财富 新浪财经", "行情问题先找可核验的市场数据入口并标注时间/延迟")
        if "finance_disclosure" in intents or "finance" in intents or requested_scope in {"finance", "finance_disclosure", "finance_company"}:
            add("company_filing", f"{clean_query} 巨潮资讯 交易所 公告 财报", "公司/股票问题先找公告、财报和交易所披露")
            add("regulatory_notice", f"{clean_query} 监管 问询函 处罚 风险提示", "补监管函、问询、处罚和风险披露")
        if "finance_macro" in intents or requested_scope == "finance_macro":
            add("macro_data", f"{clean_query} 央行 统计局 官方 数据", "宏观金融问题先找官方统计和央行口径")
            add("market_expectation", f"{clean_query} FedWatch 利率 预期 市场定价", "市场预期应和政策决定分开")
        if "finance_research" in intents or requested_scope == "finance_research":
            add("analyst_opinion", f"{clean_query} 研报 券商 评级 估值", "研报和评级属于观点层，不能替代披露")
        if "finance_sentiment" in intents or requested_scope == "finance_sentiment":
            add("sentiment_sample", f"{clean_query} 雪球 股吧 热议 情绪", "公开讨论只作情绪样本，不作事实主证据")
        add("market_news", f"{clean_query} 财经 快讯 新闻 事件", "补财经新闻时间线和事件背景")
    elif {"industry"} & set(intents):
        add("industry_report", f"{clean_query} 行业 趋势 公司 案例", "产业/商业问题补行业材料")
    if "wps_office" in intents or requested_scope == "wps_office":
        wps_analysis = analyze_wps_semantics(clean_query)
        wps_lanes = set(wps_analysis.get("lanes") or [])
        for variant in wps_route_query_variants(clean_query)[:5]:
            add("topic_radar", variant, "补 WPS/AI Office 语义 lane 的高信号选题词")
        add("company_primary", f"{clean_query} 金山办公 WPS AI WPS 365 官方 发布 产品 文档", "WPS/AI Office 选题先锚定金山办公和 WPS 一手材料")
        add("industry_report", f"{clean_query} 办公 AI PPT 文档协作 SaaS 信创 行业 趋势 案例 移动办公 平板办公 鸿蒙", "外扩办公 AI、PPT、文档协作、SaaS、信创、移动办公和行业趋势")
        add("user_sample", f"{clean_query} 用户评价 体验 吐槽 知乎 小红书 B站 V2EX", "补公开用户与社区样本，避免只有品牌口径")
        add("developer_discussion", f"{clean_query} Agent API 插件 自动化 文档协作 开发者", "补 Agent、API、插件和自动化开发者视角")
        add("security_advisory", f"{clean_query} 安全 权限 数据合规 信创 等保 国产化", "补政企办公、安全合规和信创约束")
        if "wps_ai" in wps_lanes:
            add("scenario_signal", f"{clean_query} AI伴写2.0 AI写文档 AI润色 AI总结 AI阅读PDF AI处理表格 AIPPT HTML素材", "WPS AI 线补四助手、AIPPT、HTML素材、文档问答和个人办公场景")
            add("competitive_context", f"{clean_query} Gamma Canva Tome Beautiful.ai Adobe Express Microsoft Copilot AI PPT 对比", "补 AI PPT/演示生成竞品和替代工作流")
            add("tool_roundup", f"{clean_query} 国产 AI PPT 工具 HTML素材 代码嵌入 交互式演示 横评 实测 榜单 效率场景", "补非品牌的 AI PPT 工具、交互式演示和可借势热点")
        if {"lingxi", "claw_agent"} & wps_lanes:
            add("agent_radar", f"{clean_query} AI办公全能伙伴 演示智能体 表格智能体 文档智能体 语音文档对话 深度搜索 多文件解读 信息溯源 思维导图", "灵犀/Claw 线补办公智能体、多文件阅读、语音文档和搜索溯源交互")
            add("developer_discussion", f"{clean_query} 灵犀 Claw 数字员工 MCP skill CLI 工具调用 电脑操作 长周期运行 AI记忆 端侧大模型 虚拟机沙箱", "Claw/Agent 线补工具调用、系统操作、长期任务、本地端侧和记忆语境")
            add("pricing_risk", f"{clean_query} AI工时 积分定价 会员套娃 大会员白买 隐私 数据安全 幻觉", "执行型 AI 需要同步观察定价、会员、隐私和幻觉风险")
            add("competitive_context", f"{clean_query} Microsoft 365 Copilot 飞书 钉钉 企业微信 腾讯 WorkBuddy Claude Code GitHub Codex Cursor", "补办公 Agent、协同平台和执行型 AI 竞品叙事")
        if "ai_office_adjacent" in wps_lanes:
            add("scenario_signal", f"{clean_query} AI 笔记 WPS笔记 龙虾直写 AI 知识库 KaaS AI Docs AI Hub Copilot Pro MonkeyOCR", "泛办公线补 AI 笔记、知识库、KaaS、OCR 和企业大脑机会")
            add("platform_signal", f"{clean_query} WPS for Pad iPadOS App Store 国际版 鸿蒙 HarmonyOS 小艺 分布式协同 跨端续写", "补 Pad、鸿蒙、移动端和跨端协同产品线索")
            add("competitive_context", f"{clean_query} Notion AI Mem 飞书知识库 Microsoft Copilot Google Workspace AI Docs 办公 Agent 对比", "补知识库/笔记/协作产品的竞品语境")
        wps_subroute = _wps_office_subroute(clean_query)
        if wps_subroute == "wps365":
            add("topic_radar", f"{clean_query} 企业大脑 组织协同 AI Office 政企 金融 行业落地", "WPS 365 更适合先接企业大脑、组织协同和行业落地选题")
            add("competitive_context", f"{clean_query} Microsoft 365 Copilot Google Workspace 飞书 钉钉 企业微信", "补企业协同和 AI Office 平台竞争")
            add("scenario_signal", f"{clean_query} 办公智能体 知识库 数字资产管理 多维表格 协同平台", "补 ToB 办公平台和组织工作流场景")
        elif not wps_lanes or wps_subroute == "general":
            add("topic_radar", f"{clean_query} 行业热点 选题 办公智能体 AI Agent AI PPT 文档协作", "品牌市场选题要先把 WPS 锚点接到 AI/科技/办公行业热点")
            add("competitive_context", f"{clean_query} Adobe Acrobat PDF Spaces Microsoft Copilot Google Workspace Notion Canva Gamma 飞书 企业微信", "补竞品、替代工作流和横向产品热点，避免只看自身官宣")
            add("scenario_signal", f"{clean_query} 企业 AI 上下文 知识库 多维表格 移动办公 自动化 政务服务 WPS云文档 一键分享", "补企业办公、移动办公、政务民生和可包装的用户问题")
    if "global_industry" in intents:
        add("industry_report", f"{clean_query} market analysis competitive landscape analyst report", "英文产业问题补分析和市场结构材料")
        add("company_context", f"{clean_query} investor relations annual report official", "补公司一手资料和投资者关系材料")
    if "tech" in intents:
        add("technical_primary", f"{search_friendly_query} docs release notes changelog API SDK", "技术问题先找官方文档、发布说明和可复现材料")
        add("developer_discussion", f"{search_friendly_query} github issue benchmark 开源", "技术问题补开发者与可复现线索")
    if "sports" in intents:
        sports_text = clean_query.lower()
        is_world_cup = any(
            term in sports_text
            for term in ("世界杯", "美加墨", "world cup", "fifa world cup")
        )
        if is_world_cup:
            add(
                "official_stat",
                f"{clean_query} FIFA World Cup 2026 official scores fixtures schedule stadium venue",
                "世界杯赛程/城市/球场先锚定 FIFA 官方 scores-fixtures 与 match schedule。",
            )
            add(
                "sports_report",
                f"{clean_query} ESPN FOX Sports Olympics FIFA World Cup schedule results",
                "补 ESPN、FOX Sports、Olympics.com 等可信赛程/赛果视图。",
            )
        else:
            add("official_stat", f"{clean_query} official scoreboard schedule standings", "体育实时问题优先找官方比分、赛程和榜单入口")
            add("sports_report", f"{clean_query} ESPN NBA official scores playoffs schedule", "补可信体育媒体的战报、专题页和实时比分")
    if "university_admissions" in intents:
        add("university_official", f"{clean_query} 官网 研究生招生 导师 招生目录", "高校招生/导师问题先找学校和招生官网")
        add("department_page", f"{clean_query} 院系 导师 研究方向", "补院系官网和导师主页")
        add("admission_catalog", f"{clean_query} 研究生院 招生简章 招生目录 复试 推免", "补招生目录、简章和历史通知")
    if "academic" in intents:
        add("database_official", f"{clean_query} Compendex Engineering Village Elsevier official", "学术检索问题先找数据库/出版商口径")
        add("publisher_guideline", f"{clean_query} CFP author guidelines proceedings", "补会议 CFP、作者指南和论文集要求")
        add("institution_policy", f"{clean_query} 学校 研究生院 认定 要求", "补国内高校或单位认定口径")
    if "standards_compliance" in intents:
        add("standard_original", f"{clean_query} official standard regulator guidance", "标准/合规问题先找标准组织或监管原文")
        add("implementation_context", f"{clean_query} implementation checklist audit requirement", "补实施和审计语境，但不替代原文")
    if "medical_health" in intents:
        add("clinical_guideline", f"{clean_query} clinical guideline regulator official", "医疗健康问题先找指南、监管和专业机构")
        add("peer_review", f"{clean_query} systematic review clinical evidence", "补同行评议或综述证据")
    if "legal_judicial" in intents:
        add("statute_original", f"{clean_query} 法律 条文 司法解释 官方", "法律问题先找条文和司法解释")
        add("case_record", f"{clean_query} 裁判文书 案例 法院", "补裁判文书或案例材料")
    if recency.get("enabled") or "hot_trend" in intents:
        add("fresh_news", _apply_recency_query(f"{clean_query} 最新 进展", recency), "近期/热点问题收束时间窗口")
        if {"policy", "official_position", "local", "company_primary"} & set(intents):
            add("fresh_primary", _apply_recency_query(f"{clean_query} 官方 发布 时间", recency), "近期问题优先补一手发布时间线索")
        if {"reputation", "purchase_advice"} & set(intents):
            add("fresh_user_sample", _apply_recency_query(f"{clean_query} 最新 用户 反馈", recency), "近期口碑需要补新鲜用户样本")
    if query_shape.get("multi_entity"):
        entity_terms = (
            _query_shape_entities(search_friendly_query)
            if search_friendly_query != clean_query
            else [str(item) for item in query_shape.get("entities") or [] if str(item)]
        )
        add("entity_compare", f"{' '.join(entity_terms[:4])} 对比 {search_friendly_query}", "多实体问题先显式保留比较意图和前几个关键实体")
    if roles and len(variants) == 1:
        add(str(roles[0]), f"{clean_query} 依据 来源", "按路由证据角色补充查询")

    time_window = _query_strategy_time_window(recency)
    operator_hints = build_search_operator_hints(
        clean_query,
        recency=recency,
        site=str(quality.get("site") or route_plan.get("site") or ""),
    )
    entrypoint_policy = suggest_search_entrypoints(
        clean_query,
        profile=str(quality.get("profile") or route_plan.get("profile") or ""),
        route_plan=route_plan,
    )
    return {
        "primary_query": variants[0]["query"] if variants else clean_query,
        "recency": recency,
        "time_window": time_window,
        "intent": quality.get("intent") or (intents[0] if intents else "general"),
        "roles": roles,
        "variants": variants[:14],
        "operator_hints": operator_hints,
        "search_entrypoint_policy": entrypoint_policy,
        "search_quality_v2": {
            "prefer_broad_pool": True,
            "minimum_recommended_limit": DEFAULT_RESEARCH_LIMIT,
            "recency_bounded": bool(recency.get("enabled")),
            "source_role_queries": len(variants),
            "operator_hint_count": len(operator_hints),
        },
        "query_shape": query_shape,
        "agent_hint": "不要只用一个宽泛 query；按证据角色分别搜索，再合并去重和标注边界；涉及近期/热点时必须保留时间窗口。",
    }


def _query_strategy_time_window(recency: dict[str, Any]) -> dict[str, Any]:
    if not recency.get("enabled"):
        return {"enabled": False}
    return {
        "enabled": True,
        "label": recency.get("label") or "recent",
        "window_days": recency.get("window_days"),
        "start_date": recency.get("start_date"),
        "end_date": recency.get("end_date"),
        "matched_terms": list(recency.get("matched_terms") or []),
        "instruction": "近期/热点查询应优先使用窗口内结果；窗口外材料只作背景，不应写成最新。",
    }


def _apply_recency_query(query: str, recency: dict[str, Any]) -> str:
    if not recency.get("enabled"):
        return query
    if _query_already_has_absolute_date(query):
        return query
    today = _recency_today(recency)
    window_days = int(recency.get("window_days") or 0)
    suffix = f"{today.year}年{today.month}月 最新"
    if window_days <= 1:
        suffix = f"{today.year}年{today.month}月{today.day}日 最新"
    elif window_days <= 7:
        suffix = f"{today.year}年{today.month}月 近{window_days}天 最新"
    elif recency.get("label") == "year_to_date":
        suffix = f"{today.year}年 最新"
    if suffix in query:
        return query
    return f"{query} {suffix}".strip()


def _query_already_has_absolute_date(query: str) -> bool:
    return bool(
        re.search(r"(?:19|20)\d{2}", query)
        or re.search(r"\d{1,2}\s*月\s*\d{1,2}\s*日", query)
        or re.search(r"\d{4}\s*[-/.]\s*\d{1,2}", query)
    )


def _recency_term_matches(text: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9]+", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", text, flags=re.I))
    return term in text


def _recency_today(recency: dict[str, Any] | None = None) -> dt.date:
    if recency:
        try:
            end_date = str(recency.get("end_date") or "")
            if end_date:
                return dt.date.fromisoformat(end_date)
        except ValueError:
            pass
    return dt.date.today()




_OWNED_EXPORTS = ['detect_search_quality_profile', '_quality_with_route_plan', 'search_quality_summary', '_quality_agent_decision', '_browser_assist_suggestion_from_results', '_quality_status', '_quality_has_strong_primary_evidence', '_quality_why_cautious', '_quality_user_facing_status', '_quality_followup_actions', '_quality_execution_policy', '_quality_workflow_plan', '_quality_gap_interpretation', '_quality_gap_reporting_contract', '_quality_gap_next_steps', '_analyze_search_query_shape', '_compress_overlong_query', '_expand_search_query', '_query_shape_entities', '_looks_like_meaningless_query', '_quality_followup_preset', '_source_gap_suggestion', '_role_gap_suggestion', '_quality_term_matches', 'detect_recency_intent', '_explicit_year_recency', 'build_query_strategy', '_query_strategy_time_window', '_apply_recency_query', '_query_already_has_absolute_date', '_recency_term_matches', '_recency_today']

__all__ = sorted(_OWNED_EXPORTS)
