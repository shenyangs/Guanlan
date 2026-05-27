# -*- coding: utf-8 -*-
"""Light/heavy workflow decisions for Guanlan agent usage.

The decider is intentionally local and side-effect free. It should help agents
choose the right Guanlan workflow without making basic search commands heavier.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import asdict, dataclass, field
from typing import Any

from guanlan.limits import DEFAULT_RESEARCH_LIMIT, DEFAULT_SEARCH_LIMIT, MAX_AGENT_RESEARCH_READ_TOP
from guanlan.query_semantics import semantic_query_variants
from guanlan.router import RoutePlan, build_route_plan

DIRECT = "direct"
GUIDED = "guided"
INVESTIGATE = "investigate"

_HIGH_IMPACT_INTENTS = {
    "policy",
    "global_policy",
    "standards_compliance",
    "medical_health",
    "legal_judicial",
    "cybersecurity",
    "weather_disaster",
    "finance",
    "finance_quote",
    "finance_company",
    "finance_disclosure",
    "finance_news",
    "finance_macro",
    "finance_sentiment",
    "finance_research",
}

_FINANCE_INTENTS = {
    "finance",
    "finance_quote",
    "finance_company",
    "finance_disclosure",
    "finance_news",
    "finance_macro",
    "finance_sentiment",
    "finance_research",
}

_VERTICAL_INTENTS = {
    "academic",
    "university_admissions",
    "career",
    "transport",
    "local_life",
    "education_learning",
    "education_service",
    "reading_notes",
    "design_trend",
    "science",
    "sports",
    "podcast",
    "test_prep",
    "entertainment",
    "global_entertainment",
    "jp_kr_entertainment",
    "industry",
    "global_industry",
    "ecommerce",
    "reputation",
    "purchase_advice",
    "public_opinion",
    "crisis_watch",
    "competitor_watch",
    "pricing_watch",
    "review_intel",
    "app_review",
    "tech",
    "wps_office",
    "company_primary",
}

_DEEP_TERMS = (
    "研究",
    "调研",
    "报告",
    "证据",
    "论证",
    "判断",
    "分析",
    "风险",
    "方案",
    "复盘",
    "尽调",
    "dossier",
    "investigate",
    "research",
    "evidence",
    "analysis",
    "due diligence",
)

_COMPARE_TERMS = ("对比", "比较", "竞品", "差异", "优劣", "compare", "versus", "vs")
_TIMELINE_TERMS = ("时间线", "脉络", "历程", "进展", "timeline", "history", "roadmap")
_DOSSIER_TERMS = ("档案", "画像", "全貌", "背景", "dossier", "profile", "briefing")
_SIMPLE_LOOKUP_TERMS = ("是什么", "官网", "地址", "电话", "下载", "价格", "版本", "who is", "what is")


@dataclass(frozen=True)
class WorkflowDecision:
    """A stable, JSON-safe workflow decision for agents."""

    query: str
    tier: str
    reason: str
    route_intents: list[str] = field(default_factory=list)
    risk_level: str = "low"
    recommended_entrypoint: str = "search"
    command_path: list[str] = field(default_factory=list)
    minimum_steps: int = 1
    recommended_limit: int = DEFAULT_SEARCH_LIMIT
    recommended_read_top: int = 0
    timeout_budget_seconds: int = 90
    timeout_budget_ms: int = 90000
    do_not_overthink: bool = False
    workflow_contract: list[str] = field(default_factory=list)
    timeout_unit_contract: list[str] = field(default_factory=list)
    fallback_policy: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    route_plan: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentCommand:
    """One executable Guanlan command with enough context for agent runners."""

    role: str
    command: str
    reason: str
    required: bool = True
    timeout_budget_seconds: int = 90
    timeout_budget_ms: int = 90000
    evidence_boundary: str = ""


@dataclass(frozen=True)
class AgentPlan:
    """A low-choice workflow plan for agents that should not browse the command surface."""

    query: str
    mode: str
    summary: str
    primary_command: str
    recommended_commands: list[AgentCommand] = field(default_factory=list)
    agent_next_steps: list[AgentCommand] = field(default_factory=list)
    decision: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    quality_tripwires: list[dict[str, str]] = field(default_factory=list)
    silent_repair_commands: list[AgentCommand] = field(default_factory=list)
    auto_repair_policy: list[str] = field(default_factory=list)
    complexity_rule: str = "先跑 primary_command；检查 trace/quality 跑偏信号；命中后先无感执行 silent_repair_commands，再向用户合并呈现证据。"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_workflow(
    query: str,
    *,
    command: str = "search",
    preset: str | None = None,
    scope: str | None = None,
    site: str | None = None,
    sites: list[str] | None = None,
    profile: str | None = None,
    limit: int | None = None,
    read_top: int | None = None,
    explicit_deep: bool = False,
    route_plan: RoutePlan | dict[str, Any] | None = None,
) -> WorkflowDecision:
    """Decide whether a Guanlan task should stay light or move to a heavier workflow."""

    clean_query = " ".join((query or "").split())
    if isinstance(route_plan, RoutePlan):
        route_data = route_plan.to_dict()
    elif isinstance(route_plan, dict):
        route_data = dict(route_plan)
    else:
        route_data = build_route_plan(
            clean_query,
            preset=preset,
            scope=scope,
            site=site,
            sites=sites,
            profile=profile,
            limit=limit,
            read_top=read_top,
        ).to_dict()
    intents = _unique(list(route_data.get("primary_intents") or []) + list(route_data.get("secondary_intents") or []))
    risk_level = str(route_data.get("risk_level") or "low")
    text = clean_query.lower()
    command = (command or "search").strip().lower()
    requested_limit = max(int(limit or route_data.get("limit") or DEFAULT_SEARCH_LIMIT), 1)
    requested_read_top = max(int(read_top if read_top is not None else route_data.get("read_top") or 0), 0)

    deep_signals = _signals(text, _DEEP_TERMS)
    compare_signals = _signals(text, _COMPARE_TERMS)
    timeline_signals = _signals(text, _TIMELINE_TERMS)
    dossier_signals = _signals(text, _DOSSIER_TERMS)
    simple_lookup = bool(_signals(text, _SIMPLE_LOOKUP_TERMS)) or _is_short_lookup(clean_query)
    freshness = bool(route_data.get("freshness") or "hot_trend" in intents)
    high_impact = risk_level == "high" or bool(set(intents) & _HIGH_IMPACT_INTENTS)
    vertical = bool(set(intents) & _VERTICAL_INTENTS)
    explicit_workflow = command in {"research", "compare", "timeline", "dossier", "investigate"} or explicit_deep
    finance_task = bool(set(intents) & _FINANCE_INTENTS) or str(scope or "").startswith("finance") or str(preset or "") == "finance"

    if command == "compare" or compare_signals:
        return _decision(
            clean_query,
            INVESTIGATE,
            "用户需要比较不同对象，必须分对象取证，不能把所有链接混成一池。",
            intents,
            risk_level,
            "compare",
            ["route", "scoped search per subject", "compare"],
            3,
            max(requested_limit, DEFAULT_RESEARCH_LIMIT),
            0,
            240,
            route_data,
            warnings=list(route_data.get("warnings") or []),
        )
    if command == "timeline" or timeline_signals:
        return _decision(
            clean_query,
            INVESTIGATE,
            "用户需要事件脉络或最新进展，应使用时间线工作流并保留窗口外背景。",
            intents,
            risk_level,
            "timeline",
            ["route", "scoped search", "timeline"],
            3,
            max(requested_limit, DEFAULT_RESEARCH_LIMIT),
            max(requested_read_top, 0),
            240,
            route_data,
            warnings=list(route_data.get("warnings") or []),
        )
    if command == "dossier" or dossier_signals:
        return _decision(
            clean_query,
            INVESTIGATE,
            "用户需要对象档案/画像，应整理来源结构、风险、时间线提示和待核验问题。",
            intents,
            risk_level,
            "dossier",
            ["route", "scoped search", "dossier"],
            3,
            max(requested_limit, DEFAULT_RESEARCH_LIMIT),
            max(requested_read_top, 2),
            300,
            route_data,
            warnings=list(route_data.get("warnings") or []),
        )
    if command == "investigate" or (explicit_workflow and (deep_signals or high_impact)):
        path = ["route", "research", "scoped search"]
        if freshness:
            path.append("hotnews")
        if {"tech", "wps_office"} & set(intents):
            path.append("feeds")
        if finance_task:
            path = ["stock plan", "stock detail/quote", "scoped finance search", "guarded research if evidence packet is required"]
        return _decision(
            clean_query,
            INVESTIGATE,
            "用户要求深查或任务具有高影响风险，应先做证据包，再决定是否补工作流视图。",
            intents,
            risk_level,
            "investigate",
            path,
            len(path),
            max(requested_limit, DEFAULT_RESEARCH_LIMIT),
            max(requested_read_top, 5 if high_impact else 3),
            300,
            route_data,
            warnings=list(route_data.get("warnings") or []),
        )
    if finance_task:
        finance_research_intents = {
            "finance_company",
            "finance_disclosure",
            "finance_news",
            "finance_macro",
            "finance_sentiment",
            "finance_research",
        }
        quote_lookup = "finance_quote" in intents or _signals(text, ("股价", "行情", "指数", "大盘", "代码", "涨跌幅", "资金流向"))
        finance_deep = bool(
            explicit_workflow
            or deep_signals
            or freshness
            or finance_research_intents & set(intents)
            or ("finance" in intents and not quote_lookup)
            or _signals(text, ("财报", "公告", "监管", "风险", "研报", "雪球", "股吧", "宏观", "大跌", "为什么"))
        )
        if not finance_deep:
            return _decision(
                clean_query,
                DIRECT,
                "这是财经行情/代码/指数类查找，先走结构化股票入口，避免把动态财经页当普通网页硬读。",
                intents,
                risk_level,
                "stock",
                ["stock plan", "stock quote", "stock detail optional", "finance search only if more evidence is needed"],
                1,
                max(requested_limit, DEFAULT_SEARCH_LIMIT),
                0,
                90,
                route_data,
                do_not_overthink=True,
                warnings=list(route_data.get("warnings") or []),
            )
        return _decision(
            clean_query,
            GUIDED,
            "这是财经/股票研究任务；先用结构化股票数据拿行情和时间戳，再按公告、宏观、新闻、研报、情绪分层补证。",
            intents,
            risk_level,
            "stock",
            ["stock plan", "stock detail/quote", "scoped finance search", "guarded research if evidence packet is required"],
            3,
            max(requested_limit, DEFAULT_RESEARCH_LIMIT),
            requested_read_top,
            180,
            route_data,
            warnings=list(route_data.get("warnings") or []),
        )
    if high_impact or vertical or freshness or deep_signals:
        if command == "research":
            path = ["route", "guarded research", "scoped search"]
            entrypoint = "research"
            read_top_hint = min(max(requested_read_top, 0), MAX_AGENT_RESEARCH_READ_TOP)
        else:
            path = ["route"]
            if freshness:
                path.append("hotnews")
            path.extend(["scoped search", "read"])
            if {"tech", "wps_office"} & set(intents):
                path.append("feeds")
            entrypoint = "search"
            read_top_hint = 0
        return _decision(
            clean_query,
            GUIDED,
            "任务需要信源分层或时效判断；先用 scoped search/read 取证，research 只作显式深查证据包。",
            intents,
            risk_level,
            entrypoint,
            path,
            len(path),
            max(requested_limit, DEFAULT_RESEARCH_LIMIT),
            read_top_hint,
            180 if not freshness else 240,
            route_data,
            warnings=list(route_data.get("warnings") or []),
        )
    if simple_lookup and command in {"search", "read", "route", ""}:
        return _decision(
            clean_query,
            DIRECT,
            "这是低风险、低歧义的查找任务；不要让 Agent 为基础搜索过度思考。",
            intents,
            risk_level,
            "search",
            ["search", "read optional"],
            1,
            max(requested_limit, DEFAULT_SEARCH_LIMIT),
            min(max(requested_read_top, 0), 1),
            90,
            route_data,
            do_not_overthink=True,
            warnings=list(route_data.get("warnings") or []),
        )
    return _decision(
        clean_query,
        DIRECT,
        "默认保持轻路径：先给足搜索候选池，只有质量信号不足时再升级到 research。",
        intents,
        risk_level,
        "search",
        ["search", "read optional", "research if quality_summary warns"],
        1,
        max(requested_limit, DEFAULT_SEARCH_LIMIT),
        min(max(requested_read_top, 0), 1),
        90,
        route_data,
        do_not_overthink=True,
        warnings=list(route_data.get("warnings") or []),
    )


def format_workflow_decision_markdown(decision: WorkflowDecision | dict[str, Any]) -> str:
    """Render a workflow decision as Markdown for humans and agents."""

    data = decision.to_dict() if isinstance(decision, WorkflowDecision) else dict(decision)
    lines = [f"# 观澜工作流分流 / {data.get('query', '')}", ""]
    lines.extend(
        [
            f"- 分流层级: {data.get('tier')}",
            f"- 推荐入口: `{data.get('recommended_entrypoint')}`",
            f"- 最少步骤: {data.get('minimum_steps')}",
            f"- 建议候选池: {data.get('recommended_limit')}",
            f"- 建议读取数: {data.get('recommended_read_top')}",
            f"- 外层 timeout: {data.get('timeout_budget_seconds')} 秒 / {data.get('timeout_budget_ms')} ms",
            f"- 不要过度思考: {'是' if data.get('do_not_overthink') else '否'}",
            f"- 判断理由: {data.get('reason')}",
            f"- 路由意图: {', '.join(data.get('route_intents') or []) or 'general'}",
            f"- 风险等级: {data.get('risk_level') or 'low'}",
        ]
    )
    lines.extend(["", "## 建议执行链路"])
    for step in data.get("command_path") or []:
        lines.append(f"- {step}")
    lines.extend(["", "## 工作流契约"])
    for item in data.get("workflow_contract") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Timeout 单位契约"])
    for item in data.get("timeout_unit_contract") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## 兜底策略"])
    for item in data.get("fallback_policy") or []:
        lines.append(f"- {item}")
    if data.get("warnings"):
        lines.extend(["", "## 边界提醒"])
        for warning in data.get("warnings") or []:
            lines.append(f"- {warning}")
    return "\n".join(lines)


def workflow_decision_context(decision: WorkflowDecision | dict[str, Any]) -> str:
    data = decision.to_dict() if isinstance(decision, WorkflowDecision) else dict(decision)
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_agent_plan(
    query: str,
    *,
    mode: str = "auto",
    preset: str | None = None,
    scope: str | None = None,
    site: str | None = None,
    sites: list[str] | None = None,
    profile: str | None = None,
    limit: int | None = None,
    read_top: int | None = None,
    max_commands: int = 5,
    route_plan: RoutePlan | dict[str, Any] | None = None,
) -> AgentPlan:
    """Build a compact, executable command shortlist for agent callers.

    This is intentionally side-effect free: it does not search or read the web.
    It collapses route/workflow knowledge into a primary command plus a small
    number of follow-ups so downstream agents do not need to choose from the
    entire Guanlan command surface.
    """

    clean_query = " ".join((query or "").split())
    mode = (mode or "auto").strip().lower()
    if mode not in {"auto", "quick", "deep", "fresh"}:
        mode = "auto"
    effective_profile = _agent_effective_profile(clean_query, profile)

    command_context = "search"
    explicit_deep = False
    effective_read_top = read_top
    if mode == "quick":
        effective_read_top = 0 if read_top is None else min(max(read_top, 0), 1)
    elif mode == "deep":
        command_context = "investigate"
        explicit_deep = True
    elif mode == "fresh":
        command_context = "search"
        explicit_deep = False

    decision = decide_workflow(
        clean_query,
        command=command_context,
        preset=preset,
        scope=scope,
        site=site,
        sites=sites,
        profile=effective_profile,
        limit=limit,
        read_top=effective_read_top,
        explicit_deep=explicit_deep,
        route_plan=route_plan,
    )
    route_data = dict(decision.route_plan or {})
    route_commands = [str(item).strip() for item in route_data.get("recommended_commands") or [] if str(item).strip()]
    primary = _select_primary_agent_command(
        clean_query,
        decision,
        route_commands,
        mode=mode,
        profile=effective_profile,
        scope=scope,
    )
    commands = _build_agent_commands(
        clean_query,
        decision,
        route_commands,
        primary=primary,
        mode=mode,
        profile=effective_profile,
        max_commands=max(max_commands, 1),
    )
    warnings = _unique(list(decision.warnings or []) + list(route_data.get("warnings") or []))
    summary = _agent_plan_summary(decision, mode, primary)
    silent_repairs = _build_silent_repair_commands(
        clean_query,
        decision,
        primary=primary,
        existing_commands=commands,
        profile=effective_profile,
        max_repairs=3,
    )
    return AgentPlan(
        query=clean_query,
        mode=mode,
        summary=summary,
        primary_command=primary,
        recommended_commands=commands,
        agent_next_steps=commands,
        decision=decision.to_dict(),
        warnings=warnings,
        quality_tripwires=_agent_quality_tripwires(clean_query, decision, primary=primary),
        silent_repair_commands=silent_repairs,
        auto_repair_policy=_agent_auto_repair_policy(clean_query, decision, primary=primary),
    )


def format_agent_plan_markdown(plan: AgentPlan | dict[str, Any]) -> str:
    """Render an agent auto-plan as compact Markdown."""

    data = plan.to_dict() if isinstance(plan, AgentPlan) else dict(plan)
    decision = dict(data.get("decision") or {})
    commands = list(data.get("recommended_commands") or [])
    lines = [f"# 观澜 Agent 自动挡 / {data.get('query', '')}", ""]
    lines.extend(
        [
            f"- 模式: `{data.get('mode') or 'auto'}`",
            f"- 主命令: `{data.get('primary_command') or ''}`",
            f"- 决策层级: `{decision.get('tier') or 'direct'}`",
            f"- 推荐入口: `{decision.get('recommended_entrypoint') or 'search'}`",
            f"- 建议候选池: {decision.get('recommended_limit')}",
            f"- 外层 timeout: {decision.get('timeout_budget_seconds')} 秒 / {decision.get('timeout_budget_ms')} ms",
            f"- 复杂度规则: {data.get('complexity_rule')}",
            f"- 摘要: {data.get('summary')}",
        ]
    )
    lines.extend(["", "## 下一步命令"])
    for index, item in enumerate(commands, start=1):
        command = item.get("command") if isinstance(item, dict) else getattr(item, "command", "")
        role = item.get("role") if isinstance(item, dict) else getattr(item, "role", "")
        reason = item.get("reason") if isinstance(item, dict) else getattr(item, "reason", "")
        required = item.get("required") if isinstance(item, dict) else getattr(item, "required", False)
        timeout_seconds = item.get("timeout_budget_seconds") if isinstance(item, dict) else getattr(item, "timeout_budget_seconds", 90)
        timeout_ms = item.get("timeout_budget_ms") if isinstance(item, dict) else getattr(item, "timeout_budget_ms", timeout_budget_ms(timeout_seconds))
        boundary = item.get("evidence_boundary") if isinstance(item, dict) else getattr(item, "evidence_boundary", "")
        must = "必须" if required else "可选"
        lines.append(f"{index}. `{command}`")
        lines.append(f"   - 角色: {role} / {must}")
        lines.append(f"   - 原因: {reason}")
        lines.append(f"   - timeout: {timeout_seconds} 秒 / {timeout_ms} ms")
        if boundary:
            lines.append(f"   - 证据边界: {boundary}")
    tripwires = list(data.get("quality_tripwires") or [])
    repairs = list(data.get("silent_repair_commands") or [])
    policy = list(data.get("auto_repair_policy") or [])
    if tripwires or repairs or policy:
        lines.extend(["", "## 自动补救契约"])
        for item in policy:
            lines.append(f"- {item}")
        if tripwires:
            lines.append("")
            lines.append("### 跑偏触发器")
            for item in tripwires:
                signal = item.get("signal", "")
                repair = item.get("repair", "")
                lines.append(f"- {signal}: {repair}")
        if repairs:
            lines.append("")
            lines.append("### 无感补救命令")
            for item in repairs:
                command = item.get("command") if isinstance(item, dict) else getattr(item, "command", "")
                reason = item.get("reason") if isinstance(item, dict) else getattr(item, "reason", "")
                lines.append(f"- `{command}`")
                if reason:
                    lines.append(f"  - {reason}")
    warnings = data.get("warnings") or []
    if warnings:
        lines.extend(["", "## 边界提醒"])
        for warning in warnings:
            lines.append(f"- {warning}")
    return "\n".join(lines)


def _decision(
    query: str,
    tier: str,
    reason: str,
    intents: list[str],
    risk_level: str,
    entrypoint: str,
    path: list[str],
    minimum_steps: int,
    limit: int,
    read_top: int,
    timeout: int,
    route_data: dict[str, Any],
    *,
    do_not_overthink: bool = False,
    warnings: list[str] | None = None,
) -> WorkflowDecision:
    return WorkflowDecision(
        query=query,
        tier=tier,
        reason=reason,
        route_intents=_unique(intents),
        risk_level=risk_level,
        recommended_entrypoint=entrypoint,
        command_path=path,
        minimum_steps=minimum_steps,
        recommended_limit=limit,
        recommended_read_top=read_top,
        timeout_budget_seconds=timeout,
        timeout_budget_ms=timeout_budget_ms(timeout),
        do_not_overthink=do_not_overthink,
        workflow_contract=_workflow_contract(tier),
        timeout_unit_contract=timeout_unit_contract(timeout),
        fallback_policy=_fallback_policy(tier, intents),
        warnings=_unique(warnings or []),
        route_plan=route_data,
    )


def timeout_budget_ms(seconds: int) -> int:
    """Convert Guanlan's outer timeout budget from seconds to milliseconds."""

    return max(int(seconds or 0), 1) * 1000


def timeout_unit_contract(seconds: int) -> list[str]:
    """Return agent-facing timeout unit rules for JSON and Markdown contracts."""

    safe_seconds = max(int(seconds or 0), 1)
    safe_ms = timeout_budget_ms(safe_seconds)
    return [
        f"`timeout_budget_seconds={safe_seconds}` 的单位是秒，适合字段名包含 `seconds` 或 `sec` 的宿主工具。",
        f"`timeout_budget_ms={safe_ms}` 的单位是毫秒，适合字段名为 `timeout_ms`、`timeout_milliseconds` 或默认按 ms 解释的平台。",
        "不要把 `timeout=120` 这类裸数字交给下游；必须先确认字段单位，再传 seconds 或 ms。",
    ]


def _workflow_contract(tier: str) -> list[str]:
    if tier == DIRECT:
        return [
            "保持基础命令轻量，不自动扩成长链路。",
            "结果池默认不低于 80，除非用户明确要求小样本。",
            "如果 trace/quality 提示证据不足，先补 scoped search/read；只有 deep 模式或用户明确要证据包时再用 research。",
        ]
    if tier == GUIDED:
        return [
            "先 route 或使用匹配 preset/scope，再 scoped search/read；research 只作显式深查证据包。",
            "保留官方、媒体、社区、用户样本等证据角色差异。",
            "近期/热点任务必须检查时间窗，科技和 WPS/AI Office 任务必须补 RSS discovery。",
        ]
    return [
        "显式进入上层工作流，但不改变 search/read/hotnews 的轻路径默认行为。",
        "自动挡先用 search/read 建立证据底座；deep 模式再组织 compare/timeline/dossier。",
        "高影响领域必须保留边界、时间戳、来源身份和待核验问题。",
    ]


def _fallback_policy(tier: str, intents: list[str]) -> list[str]:
    policy = [
        "不要因为一次后端超时就报告没有资料；这只是网络证据。",
        "优先重试、使用缓存、补 scoped search/read；不要先缩小正常候选池。",
    ]
    if tier != DIRECT:
        policy.append("观澜工作流仍缺关键原文时，可让宿主 Agent 用 WebFetch 定点补读，并外显说明这是补证策略。")
    if "tech" in intents:
        policy.append("科技/AI/开发者任务要额外跑 feeds curated 和 scoped search；deep 模式再跑 research --preset tech。")
    if "wps_office" in intents:
        policy.append("WPS/AI Office 选题任务要额外跑 feeds curated、scope wps_office search 和 hotnews/pulse；deep 模式再跑 research。")
    if "hot_trend" in intents:
        policy.append("热点任务要补 hotnews/pulse，看水势后再写判断。")
    return policy


def _signals(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term.lower() in text]


def _is_short_lookup(query: str) -> bool:
    compact = re.sub(r"\s+", "", query or "")
    if not compact:
        return False
    if len(compact) <= 14 and not any(mark in compact for mark in "，。？！,?!；;"):
        return True
    return False


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output


def quote_query(query: str) -> str:
    """Return a shell-safe quoted query for generated command hints."""

    return shlex.quote(query)


def _agent_query_for_commands(query: str) -> str:
    variants = semantic_query_variants(query, limit=1)
    return variants[0] if variants else query


def _select_primary_agent_command(
    query: str,
    decision: WorkflowDecision,
    route_commands: list[str],
    *,
    mode: str,
    profile: str | None,
    scope: str | None,
) -> str:
    url = _extract_url_from_query(query)
    if url:
        return f"guanlan read {quote_query(url)} --max-chars 12000 --quality-report --trace"
    if _is_archive_query(query):
        return f"guanlan archive context {quote_query(query)} --semantic --limit 20"
    site_operator = _extract_site_operator(query)
    if site_operator and mode != "deep":
        return f"guanlan search {quote_query(query)} --site {site_operator} --profile {profile or 'china'} --limit {max(decision.recommended_limit, DEFAULT_SEARCH_LIMIT)} --trace"
    if _is_secondhand_market_query(query):
        return f"guanlan search {quote_query(query)} --profile {profile or 'china'} --scope ecommerce --limit {max(decision.recommended_limit, DEFAULT_SEARCH_LIMIT)} --trace"
    if _is_social_style_query(query):
        return f"guanlan search {quote_query(query)} --profile {profile or 'china'} --scope social_web --limit {max(decision.recommended_limit, DEFAULT_SEARCH_LIMIT)} --trace"
    if mode == "deep":
        return f"guanlan investigate {quote_query(query)} --limit {max(decision.recommended_limit, DEFAULT_RESEARCH_LIMIT)} --format context"
    if mode == "fresh":
        if _needs_agent_freshness(decision, mode):
            return "guanlan hotnews today --limit 80 --trends"
        if _needs_agent_feeds(decision):
            return "guanlan feeds curated --category ai --limit 80"
        search = _first_command(route_commands, "search")
        if search:
            return search
        return _generated_search_command(query, decision, profile=profile, scope=scope)
    if mode == "quick" and decision.tier != INVESTIGATE:
        search = _first_command(route_commands, "search")
        if search:
            return search
        return _generated_search_command(query, decision, profile=profile, scope=scope)

    entrypoint = decision.recommended_entrypoint
    if entrypoint == "stock":
        if _is_index_or_futures_quote_query(query):
            return _generated_search_command(query, decision, profile=profile, scope="finance_quote")
        if _is_macro_finance_query(query, decision):
            return _generated_search_command(query, decision, profile=profile, scope="finance_macro")
        if _is_generic_finance_product_query(query):
            return _generated_search_command(query, decision, profile=profile, scope="finance_research")
        stock = _first_command(route_commands, "stock")
        if stock:
            return stock
        return f"guanlan stock plan {quote_query(query)}"
    if entrypoint == "compare":
        return _generated_search_command(query, decision, profile=profile, scope=scope)
    if entrypoint == "timeline":
        return _generated_search_command(query, decision, profile=profile, scope=scope)
    if entrypoint == "dossier":
        return _generated_search_command(query, decision, profile=profile, scope=scope)
    if entrypoint == "investigate":
        return _generated_search_command(query, decision, profile=profile, scope=scope)
    if entrypoint == "research":
        if "podcast" in decision.route_intents:
            search = _first_command(route_commands, "search")
            if search:
                return search
        return _generated_search_command(query, decision, profile=profile, scope=scope)
    if entrypoint in {"search", "hotnews"}:
        return _generated_search_command(query, decision, profile=profile, scope=scope)

    if _is_ai_discovery_query(query, decision) and mode != "quick":
        return _generated_search_command(query, decision, profile=profile, scope="tech_dev")

    search = _first_command(route_commands, "search")
    if search:
        return search
    return _generated_search_command(query, decision, profile=profile, scope=scope)


def _build_agent_commands(
    query: str,
    decision: WorkflowDecision,
    route_commands: list[str],
    *,
    primary: str,
    mode: str,
    profile: str | None,
    max_commands: int,
) -> list[AgentCommand]:
    commands: list[AgentCommand] = []
    commands.append(
        _agent_command(
            "primary",
            primary,
            _primary_reason(decision, mode),
            required=True,
            evidence_boundary="主证据入口；执行后先看 quality/trace/advisor，再决定是否补跑后续。",
        )
    )
    if _command_kind(primary) == "archive":
        if len(commands) < max_commands:
            commands.append(
                _agent_command(
                    "archive_verify",
                    "guanlan archive verify",
                    "依赖本地 archive/RAG 前先确认索引、正文质量和样本召回边界。",
                    required=False,
                    evidence_boundary="只检查本地归档状态，不代表全网证据。",
                )
            )
        return commands[:max_commands]

    if _extract_site_operator(query):
        if len(commands) < max_commands:
            commands.append(
                _agent_command(
                    "read_optional",
                    "guanlan read \"URL\" --quality-report --trace",
                    "用户显式指定 `site:`，后续只读取该站点搜索结果里的代表原文，不自动放宽到跨站 feeds/research。",
                    required=False,
                    evidence_boundary="把站内搜索结果中的目标 URL 替换进去；`--site` 是硬约束，不能用跨站来源替代。",
                )
            )
        return commands[:max_commands]

    if _needs_agent_freshness(decision, mode) and not _has_kind(commands, "hotnews") and len(commands) < max_commands:
        commands.append(
            _agent_command(
                "freshness",
                "guanlan hotnews today --limit 80 --trends",
                "需求带近期/热点/新鲜度要求，补一层热榜水势，不能只看静态网页结果。",
                required=True,
            )
        )
    if _needs_agent_feeds(decision) and not _has_kind(commands, "feeds") and len(commands) < max_commands:
        commands.append(
            _agent_command(
                "rss_discovery",
                "guanlan feeds curated --category ai --limit 80",
                "科技、AI、WPS/AI Office 任务需要 RSS/精品内容流发现新线索。",
                required=False,
            )
        )
    if (
        _agent_allows_research_command(decision, mode)
        and _needs_agent_feeds(decision)
        and not _has_kind(commands, "research")
        and len(commands) < max_commands
    ):
        commands.append(
            _agent_command(
                "evidence_packet",
                _generated_tech_research_command(query, decision, profile=profile)
                if _is_ai_discovery_query(query, decision)
                else _generated_research_command(query, decision, profile=profile),
                "科技、AI、WPS/AI Office 任务需要配套证据包，不能只看热榜或 RSS 线索。",
                required=False,
            )
        )
    if (
        _agent_allows_research_command(decision, mode)
        and _needs_finance_research(decision)
        and not _has_kind(commands, "research")
        and len(commands) < max_commands
    ):
        commands.append(
            _agent_command(
                "evidence_packet",
                _generated_research_command(query, decision, profile=profile),
                "金融/股票风险任务不能只看行情入口，还要补公告、新闻、研报和情绪分层证据包。",
                required=True,
            )
        )
    if _is_generic_finance_product_query(query) and len(commands) < max_commands:
        commands.append(
            _agent_command(
                "scoped_search",
                f"guanlan search {quote_query(query)} --profile {profile or 'china'} --scope finance_research --limit 80 --trace",
                "银行理财/保险/贷款等金融产品风险更适合研报、监管和产品信息检索，不应只走股票公告入口。",
                required=False,
            )
        )
    if _is_macro_finance_query(query, decision) and not any("--scope finance_macro" in item.command for item in commands) and len(commands) < max_commands:
        commands.append(
            _agent_command(
                "scoped_search",
                f"guanlan search {quote_query(query)} --profile {profile or 'china'} --scope finance_macro --limit 80 --trace",
                "宏观金融问题要补央行/统计/宏观数据线索，不应落到股票行情入口。",
                required=False,
            )
        )
    fallback_search = _agent_scoped_search_fallback(query, decision, profile=profile)
    if fallback_search and not _has_kind(commands, "search") and len(commands) < max_commands:
        commands.append(
            _agent_command(
                "scoped_search",
                fallback_search,
                "补一轮语义 scope 搜索，避免把自动档锁死在某个未被用户点名的官网或社区站点。",
                required=False,
            )
        )

    for command in _prioritized_agent_route_commands(route_commands, decision, mode):
        if command == primary or len(commands) >= max_commands:
            continue
        kind = _command_kind(command)
        if _should_skip_agent_route_command(command, decision, query):
            continue
        if kind == "hotnews" and not _needs_agent_freshness(decision, mode):
            continue
        if kind == "feeds" and not (_needs_agent_feeds(decision) or "podcast" in decision.route_intents):
            continue
        if kind == "research" and not _agent_allows_research_command(decision, mode):
            continue
        if kind in {"search", "research"} and _has_kind(commands, kind):
            continue
        if kind in {"pulse", "hotnews", "feeds"} and _has_kind(commands, kind):
            continue
        if mode == "fresh" and kind == "hotnews" and "--trends" not in command:
            command = command.replace("guanlan hotnews today --limit 80", "guanlan hotnews today --limit 80 --trends")
        commands.append(_agent_command(_role_for_kind(kind), command, _reason_for_kind(kind, decision), required=False))
    if (
        decision.tier == DIRECT
        and "read optional" in decision.command_path
        and not _has_kind(commands, "read")
        and _command_kind(primary) != "archive"
        and len(commands) < max_commands
    ):
        commands.append(
            _agent_command(
                "read_optional",
                "guanlan read \"URL\" --quality-report --trace",
                "搜索结果足够明确后，读取一到两个代表性原文确认正文质量。",
                required=False,
                evidence_boundary="把搜索结果中的目标 URL 替换进去；不要把兜底搜索上下文当原文。",
            )
        )
    return commands[:max_commands]


def _agent_quality_tripwires(query: str, decision: WorkflowDecision, *, primary: str) -> list[dict[str, str]]:
    """Return trace/result signals that mean the auto route needs silent repair."""
    tripwires: list[dict[str, str]] = [
        {
            "signal": "`result_count==0`、输出 `[]`、或 `quality_gate.reason=empty`",
            "repair": "不要向用户说没资料；先执行 `silent_repair_commands` 的第一条补证命令。",
        },
        {
            "signal": "`quality_summary.preferred_hit_count==0` 且查询命中明确 preset/scope/site",
            "repair": "说明主路由覆盖不足，先补语义 scope/open search，再合并证据。",
        },
        {
            "signal": "`backend_recovery.should_warn=true`、`all_primary_failed`、`network_unreachable` 或后端全部超时",
            "repair": "把它当网络证据，不当空结果；重试或执行补救命令，必要时使用 planned WebFetch 定点补读。",
        },
        {
            "signal": "`quality_gate.reason=partial_salvage` 或 `quality_summary.agent_decision.code=usable_with_gaps`",
            "repair": "可用但有缺口；读取强来源原文或补第二条命令，不要写成失败。",
        },
    ]
    if _extract_site_operator(query) or "--site " in primary:
        tripwires.append(
            {
                "signal": "`site_filter.mode=hard` 后站内结果为空或 `site_filter.removed` 很高",
                "repair": "`--site` 是硬约束，不自动放宽到跨站结果；只读取站内结果或说明站内未命中。",
            }
        )
    if _needs_agent_freshness(decision, "auto") or "hot_trend" in decision.route_intents:
        tripwires.append(
            {
                "signal": "`recency.enabled=true` 但 `in_window=false` 占多数，或结果日期超出用户时间窗",
                "repair": "补 `hotnews`/fresh search；窗口外材料只作背景，不写成最新。",
            }
        )
    if _command_kind(primary) == "read":
        tripwires.append(
            {
                "signal": "`read_quality.status=unusable`、`selected_backend=search_fallback`、动态壳/登录墙/WAF",
                "repair": "先跑 `diagnose page`；只有诊断建议且用户授权后，才用浏览器可见页补证。",
            }
        )
    if "tech" in decision.route_intents or "wps_office" in decision.route_intents:
        tripwires.append(
            {
                "signal": "科技/AI/WPS 结果只有通用网页或 SEO 文章，缺 RSS/垂类/官方/社区角色",
                "repair": "先补 scoped search 和 curated feeds；只有 deep 模式或用户明确要证据包时才升级 research。",
            }
        )
    return tripwires


def _agent_auto_repair_policy(query: str, decision: WorkflowDecision, *, primary: str) -> list[str]:
    policy = [
        "自动挡默认先自救：命中跑偏触发器时，Agent 应先执行 `silent_repair_commands`，再决定是否需要告诉用户证据边界。",
        "用户面前不要说 Guanlan 崩了、坏了、没搜到；表述为“我补了一轮定向/开放信源核验，下面按可用证据说”。",
        "如果补救后仍缺关键事实，只报告证据边界和下一步授权/读取需求，不把网络超时或弱页面说成没有资料。",
    ]
    if _extract_site_operator(query) or "--site " in primary:
        policy.append("显式 `--site`/`site:` 不能无感放宽；补救只限站内结果读取、页面诊断或说明硬约束下未命中。")
    if decision.risk_level == "high":
        policy.append("高影响任务补救后仍必须保留时间戳、来源身份和非专业建议边界。")
    return policy


def _agent_allows_research_command(decision: WorkflowDecision, mode: str) -> bool:
    """Keep research out of ordinary Agent auto plans unless the user opts into deep mode."""
    return mode == "deep"


def _build_silent_repair_commands(
    query: str,
    decision: WorkflowDecision,
    *,
    primary: str,
    existing_commands: list[AgentCommand],
    profile: str | None,
    max_repairs: int,
) -> list[AgentCommand]:
    repairs: list[AgentCommand] = []
    def add(command: str, reason: str, *, boundary: str = "") -> None:
        if not command or command == primary or any(item.command == command for item in repairs):
            return
        if len(repairs) >= max_repairs:
            return
        repairs.append(
            _agent_command(
                "silent_repair",
                command,
                reason,
                required=False,
                evidence_boundary=boundary,
            )
        )

    url = _extract_url_from_query(query)
    site_operator = _extract_site_operator(query)
    if url and _command_kind(primary) == "read":
        add(
            f"guanlan diagnose page {quote_query(url)}",
            "目标页正文弱、动态壳、登录墙或 WAF 时，先做只读页面诊断，不重复硬读。",
            boundary="诊断只说明页面可读性和下一步路线，不读取 Cookie 或账号数据。",
        )
        return repairs
    if site_operator:
        add(
            "guanlan read \"URL\" --quality-report --trace",
            "站内搜索有代表 URL 后，只读取该站点内原文确认正文质量。",
            boundary="`site:` 是硬约束；不要自动放宽到跨站搜索。",
        )
        return repairs

    scoped_fallback = _agent_scoped_search_fallback(query, decision, profile=profile)
    if scoped_fallback:
        add(
            scoped_fallback,
            "主命令结果为空、preferred_hit_count 为 0 或来源角色过窄时，补一轮语义 scope 搜索。",
        )
    if _command_kind(primary) == "search" and "--scope " in primary:
        add(
            _generated_open_search_command(query, decision, profile=profile),
            "scope 结果为空、偏窄或 preferred_hit_count 为 0 时，补一轮开放搜索保底。",
        )
    elif _command_kind(primary) != "search":
        add(
            _generated_open_search_command(query, decision, profile=profile),
            "preset/scope 明显跑偏或过窄时，补一轮开放搜索保底，但仍保留来源角色差异。",
        )
    if _needs_agent_freshness(decision, "auto"):
        add(
            "guanlan hotnews today --limit 80 --trends",
            "最新/热点任务发现结果不在时间窗内时，补热榜水势和近期线索。",
        )
    if _needs_agent_feeds(decision):
        add(
            "guanlan feeds curated --category ai --limit 80",
            "科技/AI/WPS 结果缺少 RSS/垂类动态时，补精选内容流作为发现层。",
        )
    return repairs


def _prioritized_agent_route_commands(commands: list[str], decision: WorkflowDecision, mode: str) -> list[str]:
    if decision.recommended_entrypoint == "stock":
        priority = ["stock", "research", "search", "read", "pulse", "feeds", "hotnews", "other"]
    elif decision.tier == INVESTIGATE and _needs_agent_freshness(decision, mode):
        priority = ["hotnews", "feeds", "research", "search", "pulse", "read", "stock", "dossier", "timeline", "compare", "other"]
    elif decision.tier == INVESTIGATE:
        priority = ["research", "search", "feeds", "pulse", "hotnews", "read", "stock", "dossier", "timeline", "compare", "other"]
    elif _needs_agent_freshness(decision, mode):
        priority = ["hotnews", "feeds", "search", "pulse", "read", "research", "stock", "other"]
    elif _needs_agent_feeds(decision):
        priority = ["feeds", "search", "pulse", "read", "research", "hotnews", "stock", "other"]
    else:
        priority = ["search", "read", "research", "pulse", "feeds", "hotnews", "stock", "other"]
    output: list[str] = []
    seen: set[str] = set()
    for kind in priority:
        for command in commands:
            if command in seen:
                continue
            if _command_kind(command) == kind or (kind == "other" and _command_kind(command) not in priority):
                seen.add(command)
                output.append(command)
    for command in commands:
        if command not in seen:
            output.append(command)
    return output


def _agent_command(
    role: str,
    command: str,
    reason: str,
    *,
    required: bool,
    evidence_boundary: str = "",
) -> AgentCommand:
    seconds = _timeout_for_command(command)
    return AgentCommand(
        role=role,
        command=command,
        reason=reason,
        required=required,
        timeout_budget_seconds=seconds,
        timeout_budget_ms=timeout_budget_ms(seconds),
        evidence_boundary=evidence_boundary,
    )


def _should_skip_agent_route_command(command: str, decision: WorkflowDecision, query: str) -> bool:
    kind = _command_kind(command)
    text = command.lower()
    intents = set(decision.route_intents)
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
    site = _extract_site_from_command(command)
    if _is_generic_finance_product_query(query) and kind == "stock":
        return True
    if _is_index_or_futures_quote_query(query) and kind == "stock":
        return True
    if _is_generic_finance_product_query(query) and "finance_disclosure" in text:
        return True
    if _is_generic_finance_product_query(query) and kind == "read" and any(
        domain in text for domain in ("cninfo.com.cn", "sse.com.cn", "szse.cn")
    ):
        return True
    if not finance_intents & intents and kind == "read" and any(
        domain in text for domain in ("cninfo.com.cn", "sse.com.cn", "szse.cn", "eastmoney.com")
    ):
        return True
    if kind in {"read", "search"} and any(
        domain in text for domain in ("cninfo.com.cn", "sse.com.cn", "szse.cn", "eastmoney.com", "stats.gov.cn", "pbc.gov.cn", "safe.gov.cn")
    ):
        if _query_prefers_global_finance(query) and not _query_mentions_china_market(query):
            return True
    if site and _should_skip_unrequested_site(site, query, intents):
        return True
    if "cybersecurity" in intents and kind == "read" and any(
        domain in text for domain in ("cisa.gov/known-exploited", "openssl.org/news/secadv", "msrc.microsoft.com/update-guide")
    ):
        query_text = query.lower()
        if any(term in query_text for term in ("骗局", "诈骗", "反诈", "短信", "钓鱼", "etc")) and not any(term in query_text for term in ("cve", "漏洞", "补丁", "openssl", "log4j")):
            return True
    return False


def _agent_scoped_search_fallback(query: str, decision: WorkflowDecision, *, profile: str | None) -> str:
    if _extract_site_operator(query):
        return ""
    text_profile = profile or "china"
    intents = set(decision.route_intents)
    if _is_secondhand_market_query(query):
        scope = "ecommerce"
    elif _is_social_style_query(query):
        scope = "social_web"
    elif "finance_macro" in intents:
        scope = "finance_macro"
    elif "finance_quote" in intents:
        scope = "finance_quote"
    elif "finance_disclosure" in intents:
        scope = "finance_disclosure"
    elif "global_policy" in intents:
        scope = "global_official"
    elif "policy" in intents or "official_position" in intents:
        scope = "gov"
    elif "standards_compliance" in intents:
        scope = "global_official"
    elif "transport" in intents:
        scope = "local_official"
    elif {"local_life", "education_service", "reading_notes", "design_trend"} & intents:
        scope = "social_web"
    elif "education_learning" in intents:
        scope = "test_prep"
    elif "company_primary" in intents:
        scope = "company_primary"
    elif "global_industry" in intents:
        scope = "industry_analysis"
    elif "industry" in intents:
        scope = "industry_analysis"
    elif "tech" in intents or _is_ai_discovery_query(query, decision):
        scope = "tech_dev"
    else:
        return ""
    return f"guanlan search {quote_query(query)} --profile {text_profile} --scope {scope} --limit 80 --trace"


def _generated_research_command(query: str, decision: WorkflowDecision, *, profile: str | None) -> str:
    effective_query = _agent_query_for_commands(query)
    profile_part = f" --profile {profile}" if profile in {"china", "english", "hybrid"} else ""
    preset = _preset_from_intents(decision.route_intents)
    preset_part = f" --preset {preset}" if preset else ""
    advisor = " --advisor" if decision.risk_level != "low" or {"wps_office", "reputation", "purchase_advice"} & set(decision.route_intents) else ""
    read_top = _agent_research_read_top(decision)
    return (
        f"guanlan research {quote_query(effective_query)}{preset_part}{profile_part} "
        f"--limit {max(decision.recommended_limit, DEFAULT_RESEARCH_LIMIT)} "
        f"--read-top {read_top} --max-search-jobs 2{advisor}"
    )


def _generated_tech_research_command(query: str, decision: WorkflowDecision, *, profile: str | None) -> str:
    effective_query = _agent_query_for_commands(query)
    profile_part = f" --profile {profile}" if profile in {"china", "english", "hybrid"} else ""
    advisor = " --advisor" if decision.risk_level != "low" else ""
    return (
        f"guanlan research {quote_query(effective_query)} --preset tech{profile_part} "
        f"--limit {max(decision.recommended_limit, DEFAULT_RESEARCH_LIMIT)} "
        f"--read-top {_agent_research_read_top(decision)} --max-search-jobs 2{advisor}"
    )


def _agent_research_read_top(decision: WorkflowDecision) -> int:
    if decision.tier == INVESTIGATE or decision.risk_level == "high":
        return min(max(decision.recommended_read_top, 1), MAX_AGENT_RESEARCH_READ_TOP)
    return 0


def _generated_search_command(query: str, decision: WorkflowDecision, *, profile: str | None, scope: str | None) -> str:
    effective_query = _agent_query_for_commands(query)
    scope_hint = scope or _scope_from_intents(decision.route_intents)
    effective_profile = _profile_for_scope(profile, scope_hint)
    profile_part = f" --profile {effective_profile}" if effective_profile in {"china", "english", "hybrid"} else ""
    scope_part = f" --scope {scope_hint}" if scope_hint else ""
    return f"guanlan search {quote_query(effective_query)}{profile_part}{scope_part} --limit {max(decision.recommended_limit, DEFAULT_SEARCH_LIMIT)} --trace"


def _generated_open_search_command(query: str, decision: WorkflowDecision, *, profile: str | None) -> str:
    effective_query = _agent_query_for_commands(query)
    profile_part = f" --profile {profile}" if profile in {"china", "english", "hybrid"} else ""
    return f"guanlan search {quote_query(effective_query)}{profile_part} --limit {max(decision.recommended_limit, DEFAULT_SEARCH_LIMIT)} --trace"


def _profile_for_scope(profile: str | None, scope: str | None) -> str | None:
    if scope == "global_entertainment":
        return "english"
    if scope == "jp_kr_entertainment":
        return "hybrid"
    return profile


def _first_command(commands: list[str], kind: str) -> str:
    for command in commands:
        if _command_kind(command) == kind:
            return command
    return ""


def _command_kind(command: str) -> str:
    text = f" {command.strip()} "
    if " guanlan stock " in text or text.startswith(" guanlan-stock "):
        return "stock"
    if " guanlan archive " in text:
        return "archive"
    for kind in ("investigate", "compare", "timeline", "dossier", "research", "search", "read", "hotnews", "feeds", "pulse", "route"):
        if f" {kind} " in text:
            return kind
    return "other"


def _has_kind(commands: list[AgentCommand], kind: str) -> bool:
    return any(_command_kind(command.command) == kind for command in commands)


def _role_for_kind(kind: str) -> str:
    return {
        "search": "scoped_search",
        "research": "evidence_packet",
        "read": "source_read",
        "hotnews": "freshness",
        "feeds": "rss_discovery",
        "pulse": "community_signal",
        "stock": "structured_data",
        "archive": "local_archive",
        "compare": "structured_compare",
        "timeline": "structured_timeline",
        "dossier": "structured_dossier",
    }.get(kind, "follow_up")


def _reason_for_kind(kind: str, decision: WorkflowDecision) -> str:
    if kind == "search":
        return "补一轮 scope/site 定向搜索，扩大候选池并查看 trace 质量信号。"
    if kind == "research":
        return "生成证据包，分清官方、媒体、社区和风险样本。"
    if kind == "hotnews":
        return "补热点/近期水势，避免只看静态网页。"
    if kind == "feeds":
        return "补 RSS/精品内容流，适合 AI、科技、WPS/AI Office 和开发者趋势发现。"
    if kind == "pulse":
        return "补公开社区样本，只作为情绪/语言信号，不替代主证据。"
    if kind == "stock":
        return "先取结构化行情、公告或财务入口，避免硬读动态财经页。"
    if kind == "read":
        return "读取代表原文，确认页面正文质量和来源时间戳。"
    if kind == "archive":
        return "用户要查本地 archive/RAG/知识库，先走本地记忆上下文，不把本地问题误送全网搜索。"
    if kind in {"compare", "timeline", "dossier"}:
        return f"当前任务适合 {decision.recommended_entrypoint} 结构化视图，建立可复用证据上下文。"
    return "作为质量不足时的补证步骤。"


def _primary_reason(decision: WorkflowDecision, mode: str) -> str:
    if mode == "quick":
        return "快速模式优先轻路径；先拿足候选池，不展开复杂工作流。"
    if mode == "deep":
        return "深查模式直接生成可复用证据包，适合高影响、对比、档案或复杂研究。"
    if mode == "fresh":
        return "新鲜度模式优先跑 hotnews/feeds/search，先拿近期线索，再决定是否需要深查。"
    if decision.do_not_overthink:
        return "这是低歧义任务；直接执行主命令，不要先浏览完整能力列表。"
    return decision.reason or "按本地路由和轻重分流选择的主证据入口。"


def _agent_plan_summary(decision: WorkflowDecision, mode: str, primary: str) -> str:
    if decision.do_not_overthink and mode == "auto":
        return f"这类任务不要过度规划，先跑 `{primary}`。"
    if mode == "quick":
        return f"快速拿线索，先跑 `{primary}`；除非质量提示不足，否则不升级。"
    if mode == "deep":
        return f"直接进入深查工作流，先跑 `{primary}`。"
    if mode == "fresh":
        return f"按最新/热点任务处理，先跑 `{primary}`，再补 hotnews/feeds。"
    return f"先跑 `{primary}`，再按质量信号补 scoped search、hotnews 或 feeds。"


def _needs_agent_freshness(decision: WorkflowDecision, mode: str) -> bool:
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
    if mode == "fresh" or "hotnews" in decision.command_path:
        return True
    if "hot_trend" in decision.route_intents and not finance_intents & set(decision.route_intents):
        return True
    return False


def _needs_agent_feeds(decision: WorkflowDecision) -> bool:
    route_data = dict(decision.route_plan or {})
    domains = set(route_data.get("domains") or [])
    feeds = set(route_data.get("recommended_feeds") or [])
    if "podcast" in decision.route_intents and not {"tech", "wps_office"} & set(decision.route_intents):
        return False
    return (
        "feeds" in decision.command_path
        or bool({"tech", "wps_office"} & set(decision.route_intents))
        or ("ai" in domains and bool(feeds))
    )


def _needs_finance_research(decision: WorkflowDecision) -> bool:
    finance_intents = {"finance", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
    return decision.recommended_entrypoint == "stock" and bool(finance_intents & set(decision.route_intents)) and decision.tier != DIRECT


def _is_archive_query(query: str) -> bool:
    text = (query or "").lower()
    return any(term in text for term in ("archive", "rag", "本地知识库", "本地 archive", "向量库", "知识底座", "归档资料"))


def _is_generic_finance_product_query(query: str) -> bool:
    text = (query or "").lower()
    education_service_context = ("夏令营", "冬令营", "研学", "营地", "家长评价", "小学生", "青少年", "户外", "投诉")
    if any(term in text for term in education_service_context):
        return False
    product_terms = ("理财", "银行理财", "存款", "贷款", "车险", "保险", "保费", "利率", "回撤")
    if not any(term in text for term in product_terms):
        return False
    capital_market_terms = ("股票", "股价", "etf", "指数", "行情", "财报", "公告", "雪球", "股吧", "研报", "代码", "ipo")
    return not any(term in text for term in capital_market_terms)


def _is_macro_finance_query(query: str, decision: WorkflowDecision) -> bool:
    text = (query or "").lower()
    macro_terms = ("finance_macro", "gdp", "inflation", "recession", "cpi", "pmi", "fed", "央行", "社融", "通胀", "降息", "宏观")
    return "finance_macro" in decision.route_intents or any(term in text for term in macro_terms)


def _is_index_or_futures_quote_query(query: str) -> bool:
    text = (query or "").lower()
    quote_terms = (
        "富时",
        "a50",
        "期货",
        "标普500",
        "s&p 500",
        "纳指",
        "nasdaq",
        "道指",
        "dow",
        "美股收盘",
        "指数",
    )
    company_terms = ("公司", "集团", "财报", "年报", "公告", "股东", "股票代码")
    return any(term in text for term in quote_terms) and not any(term in text for term in company_terms)


def _is_secondhand_market_query(query: str) -> bool:
    text = (query or "").lower()
    secondhand_terms = ("二手", "闲鱼", "转转", "回收", "旧货", "中古", "second hand", "used price", "resale")
    price_terms = ("价格", "报价", "多少钱", "行情", "回收价", "估价", "price")
    return any(term in text for term in secondhand_terms) and any(term in text for term in price_terms)


def _is_social_style_query(query: str) -> bool:
    text = (query or "").lower()
    if not any(term in text for term in ("小红书", "xiaohongshu", "instagram", "ins", "tiktok", "抖音")):
        return False
    style_terms = ("风格", "穿搭", "妆容", "女生", "可爱", "文艺", "审美", "模板", "灵感", "种草", "标题", "封面")
    if not any(term in text for term in style_terms):
        return False
    reputation_terms = ("评价", "口碑", "投诉", "避雷", "差评", "好评", "风评", "舆情", "被骂")
    return not any(term in text for term in reputation_terms)


def _is_ai_discovery_query(query: str, decision: WorkflowDecision) -> bool:
    text = (query or "").lower()
    route_data = dict(decision.route_plan or {})
    domains = set(route_data.get("domains") or [])
    if "tech" in decision.route_intents or "wps_office" in decision.route_intents:
        return False
    discovery_terms = (
        " ai ",
        "ai ",
        " agent",
        "product hunt",
        "figma",
        "firefly",
        "companion",
        "character.ai",
        "aip",
        "persona",
        "人格化",
        "智能体",
        "ai工具",
    )
    padded = f" {text} "
    return "ai" in domains and any(term in padded for term in discovery_terms)


def _extract_site_from_command(command: str) -> str:
    match = re.search(r"\s--site\s+([^\s]+)", command or "", re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip("\"'").lower()


def _should_skip_unrequested_site(site: str, query: str, intents: set[str]) -> bool:
    normalized = site.lower().removeprefix("www.")
    if _site_is_requested_by_query(normalized, query):
        return False
    generic_ai_company_sites = {
        "openai.com",
        "anthropic.com",
        "deepmind.google",
        "machinelearning.apple.com",
        "research.google",
        "mistral.ai",
        "x.ai",
        "cursor.com",
        "openrouter.ai",
        "runwayml.com",
        "midjourney.com",
    }
    generic_developer_sites = {"github.com", "v2ex.com", "juejin.cn", "segmentfault.com", "csdn.net", "cnblogs.com", "oschina.net"}
    generic_business_sites = {"36kr.com", "huxiu.com", "latepost.com", "leiphone.com", "geekpark.net", "tmtpost.com", "iyiou.com", "ebrun.com"}
    if normalized in generic_ai_company_sites and {"company_primary", "global_industry", "tech"} & intents:
        return True
    if normalized in generic_developer_sites and {"company_primary", "global_industry", "tech"} & intents:
        return not _query_has_developer_site_intent(query)
    if normalized in generic_business_sites and "industry" in intents and _agent_effective_profile(query, None) == "english":
        return True
    return False


def _site_is_requested_by_query(site: str, query: str) -> bool:
    text = (query or "").lower()
    compact_text = re.sub(r"[^a-z0-9]+", "", text)
    compact_site = re.sub(r"[^a-z0-9]+", "", site.lower().removeprefix("www."))
    if compact_site and compact_site in compact_text:
        return True
    labels = [label for label in re.split(r"[.-]+", site.lower()) if label]
    ignored = {"www", "com", "cn", "net", "org", "io", "ai", "co", "app", "google", "research"}
    for label in labels:
        if label in ignored or len(label) <= 2:
            continue
        if label in text or label in compact_text:
            return True
    aliases = {
        "producthunt.com": ("product hunt", "producthunt"),
        "news.ycombinator.com": ("hacker news", "ycombinator", "hn"),
        "finance.yahoo.com": ("yahoo finance", "雅虎财经"),
        "nasdaq.com": ("nasdaq", "纳斯达克"),
        "sec.gov": ("sec", "10-k", "10-q"),
    }
    return any(alias in text or re.sub(r"[^a-z0-9]+", "", alias) in compact_text for alias in aliases.get(site, ()))


def _query_has_developer_site_intent(query: str) -> bool:
    text = (query or "").lower()
    developer_terms = (
        "github",
        "repo",
        "repository",
        "issue",
        "pull request",
        "开源",
        "源码",
        "代码",
        "sdk",
        "api",
        "cli",
        "mcp",
        "部署",
        "框架",
        "bug",
    )
    return any(term in text for term in developer_terms)


def _query_prefers_global_finance(query: str) -> bool:
    text = (query or "").lower()
    english_profile = _agent_effective_profile(query, None) == "english"
    global_terms = ("nasdaq", "nyse", "sec", "10-k", "10-q", "fed", "recession", "inflation", "gdp", "nvidia", "oracle", "salesforce", "paypal")
    return english_profile or any(term in text for term in global_terms)


def _query_mentions_china_market(query: str) -> bool:
    text = (query or "").lower()
    china_terms = (
        "中国",
        "a股",
        "沪深",
        "上证",
        "深交所",
        "港股",
        "社融",
        "人民银行",
        "央行",
        "统计局",
        "证监会",
        "cninfo",
        "sse",
        "szse",
        "eastmoney",
    )
    return any(term in text for term in china_terms)


def _agent_effective_profile(query: str, profile: str | None) -> str | None:
    if profile not in {None, "", "china"}:
        return profile
    cjk_count = sum(1 for char in query or "" if "\u4e00" <= char <= "\u9fff")
    latin_tokens = re.findall(r"[A-Za-z][A-Za-z0-9.+-]*", query or "")
    latin_chars = sum(len(token) for token in latin_tokens)
    if latin_chars >= 16 and cjk_count == 0:
        return "english"
    if latin_chars >= 14 and latin_chars > cjk_count * 2:
        return "english"
    if latin_chars >= 10 and cjk_count > 0:
        return "hybrid"
    return profile or "china"


def _extract_site_operator(query: str) -> str:
    match = re.search(r"\bsite:([A-Za-z0-9.-]+\.[A-Za-z]{2,})", query or "", re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip().lower()


def _extract_url_from_query(query: str) -> str:
    pattern = re.compile(
        r"(https?://[^\s\"'<>]+|(?:www\.|[a-z0-9.-]+\.(?:com|cn|org|net|edu|gov|io|ai|co|jp|tv|fm|me|xyz|app)/)[^\s\"'<>]*)",
        re.IGNORECASE,
    )
    match = pattern.search(query or "")
    if not match:
        return ""
    url = match.group(1).rstrip("，。；;、)）]】>\"'")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _timeout_for_command(command: str) -> int:
    kind = _command_kind(command)
    if kind in {"research", "compare", "timeline", "dossier", "investigate"}:
        return 300 if kind != "research" else 180
    if kind in {"hotnews", "feeds", "pulse"}:
        return 120
    return 90


def _preset_from_intents(intents: list[str]) -> str:
    mapping = {
        "wps_office": "wps_office",
        "tech": "tech",
        "policy": "policy",
        "global_policy": "global_policy",
        "academic": "academic",
        "university_admissions": "university",
        "finance": "finance",
        "cybersecurity": "cybersecurity",
        "sports": "sports",
        "science": "science",
        "career": "career",
        "podcast": "podcast",
        "entertainment": "entertainment",
        "global_entertainment": "global_entertainment",
        "jp_kr_entertainment": "jp_kr_entertainment",
        "reputation": "reputation",
        "purchase_advice": "reputation",
        "industry": "industry",
        "global_industry": "global_industry",
    }
    priority = [
        "wps_office",
        "tech",
        "policy",
        "global_policy",
        "academic",
        "university_admissions",
        "finance",
        "finance_disclosure",
        "finance_macro",
        "finance_sentiment",
        "finance_research",
        "cybersecurity",
        "sports",
        "science",
        "career",
        "podcast",
        "entertainment",
        "global_entertainment",
        "jp_kr_entertainment",
        "industry",
        "global_industry",
        "reputation",
        "purchase_advice",
    ]
    intent_set = set(intents)
    for intent in priority:
        if intent in intent_set and intent in mapping:
            return mapping[intent]
    for intent in intents:
        if intent in mapping:
            return mapping[intent]
    return ""


def _scope_from_intents(intents: list[str]) -> str:
    mapping = {
        "wps_office": "wps_office",
        "ecommerce": "ecommerce",
        "tech": "tech_dev",
        "policy": "gov",
        "official_position": "gov",
        "global_policy": "global_official",
        "standards_compliance": "global_official",
        "legal_judicial": "gov",
        "transport": "local_official",
        "local_life": "social_web",
        "education_learning": "test_prep",
        "education_service": "social_web",
        "reading_notes": "social_web",
        "design_trend": "social_web",
        "academic": "academic",
        "weather_disaster": "weather_disaster",
        "cybersecurity": "cybersecurity",
        "company_primary": "company_primary",
        "finance_quote": "finance_quote",
        "finance_disclosure": "finance_disclosure",
        "finance_macro": "finance_macro",
        "finance_sentiment": "finance_sentiment",
        "finance_research": "finance_research",
        "sports": "sports",
        "science": "science",
        "career": "career",
        "podcast": "podcast",
        "test_prep": "test_prep",
        "university_admissions": "university",
        "entertainment": "entertainment",
        "global_entertainment": "global_entertainment",
        "jp_kr_entertainment": "jp_kr_entertainment",
        "reputation": "social_web",
        "purchase_advice": "social_web",
        "industry": "industry_analysis",
        "global_industry": "industry_analysis",
    }
    priority = [
        "wps_office",
        "company_primary",
        "podcast",
        "global_policy",
        "policy",
        "official_position",
        "legal_judicial",
        "standards_compliance",
        "tech",
        "transport",
        "local_life",
        "education_learning",
        "education_service",
        "reading_notes",
        "design_trend",
        "ecommerce",
        "academic",
        "weather_disaster",
        "cybersecurity",
        "finance_quote",
        "finance_disclosure",
        "finance_macro",
        "finance_sentiment",
        "finance_research",
        "sports",
        "science",
        "career",
        "test_prep",
        "university_admissions",
        "global_entertainment",
        "jp_kr_entertainment",
        "industry",
        "global_industry",
        "entertainment",
        "reputation",
        "purchase_advice",
    ]
    intent_set = set(intents)
    for intent in priority:
        if intent in intent_set and intent in mapping:
            return mapping[intent]
    for intent in intents:
        if intent in mapping:
            return mapping[intent]
    return ""
