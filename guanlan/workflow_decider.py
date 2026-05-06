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

from guanlan.limits import DEFAULT_RESEARCH_LIMIT, DEFAULT_SEARCH_LIMIT
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

_VERTICAL_INTENTS = {
    "academic",
    "university_admissions",
    "career",
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
    "tech",
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

    if command == "compare" or compare_signals:
        return _decision(
            clean_query,
            INVESTIGATE,
            "用户需要比较不同对象，必须分对象取证，不能把所有链接混成一池。",
            intents,
            risk_level,
            "compare",
            ["route", "research", "compare"],
            3,
            max(requested_limit, DEFAULT_RESEARCH_LIMIT),
            max(requested_read_top, 0),
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
            ["route", "research", "timeline"],
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
            ["route", "research", "dossier"],
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
        if "tech" in intents:
            path.append("feeds")
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
    if high_impact or vertical or freshness or deep_signals:
        path = ["route", "research", "scoped search"]
        if freshness:
            path.append("hotnews")
        if "tech" in intents:
            path.append("feeds")
        return _decision(
            clean_query,
            GUIDED,
            "任务需要信源分层或时效判断；保持较大候选池，先取证再下结论。",
            intents,
            risk_level,
            "research",
            path,
            len(path),
            max(requested_limit, DEFAULT_RESEARCH_LIMIT),
            max(requested_read_top, 5 if high_impact else requested_read_top),
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
            "如果 trace/quality 提示证据不足，再升级到 research。",
        ]
    if tier == GUIDED:
        return [
            "先 route 或使用匹配 preset/scope，再 research/scoped search。",
            "保留官方、媒体、社区、用户样本等证据角色差异。",
            "近期/热点任务必须检查时间窗，科技任务必须补 RSS discovery。",
        ]
    return [
        "显式进入上层工作流，但不改变 search/read/hotnews 的轻路径默认行为。",
        "以证据包为底座，再组织 compare/timeline/dossier，而不是直接写结论。",
        "高影响领域必须保留边界、时间戳、来源身份和待核验问题。",
    ]


def _fallback_policy(tier: str, intents: list[str]) -> list[str]:
    policy = [
        "不要因为一次后端超时就报告没有资料；这只是网络证据。",
        "优先重试、使用缓存或降低 read_top，不要先缩小正常候选池。",
    ]
    if tier != DIRECT:
        policy.append("观澜工作流仍缺关键原文时，可让宿主 Agent 用 WebFetch 定点补读，并外显说明这是补证策略。")
    if "tech" in intents:
        policy.append("科技/AI/开发者任务要额外跑 feeds curated 或 research --preset tech 的 RSS 发现。")
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
