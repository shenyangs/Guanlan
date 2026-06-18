# -*- coding: utf-8 -*-
"""Agent-facing task planner and review contracts for Guanlan.

This module wraps the older workflow decider with a richer, still local and
side-effect-free contract.  It deliberately does not execute web requests:
Guanlan tells the host Agent what to run, what to inspect, and when to stop.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from guanlan.limits import DEFAULT_SEARCH_LIMIT
from guanlan.workflow_decider import (
    AgentPlan,
    build_agent_plan,
    format_agent_plan_markdown,
    quote_query,
    timeout_budget_ms,
)

PLAN_SCHEMA_VERSION = "agent_plan_v2"
REVIEW_SCHEMA_VERSION = "agent_review_v1"

NEXT_DECISIONS = {"answer", "continue", "repair", "ask_user", "authorize_browser", "stop"}


def build_agent_plan_v2(
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
) -> dict[str, Any]:
    """Build a v2 Agent decision card while keeping legacy top-level fields."""

    plan = build_agent_plan(
        query,
        mode=mode,
        preset=preset,
        scope=scope,
        site=site,
        sites=sites,
        profile=profile,
        limit=limit,
        read_top=read_top,
        max_commands=max_commands,
    )
    payload = plan.to_dict()
    decision = dict(payload.get("decision") or {})
    route_plan = dict(decision.get("route_plan") or {})
    commands = list(payload.get("agent_next_steps") or [])
    primary_command = str(payload.get("primary_command") or "")

    task_model = _task_model(
        str(payload.get("query") or query or ""),
        decision=decision,
        route_plan=route_plan,
        mode=str(payload.get("mode") or mode or "auto"),
    )
    capability_selection = _capability_selection(
        primary_command,
        commands,
        decision=decision,
        route_plan=route_plan,
        task_model=task_model,
    )
    execution_contract = _execution_contract(
        payload,
        decision=decision,
        capability_selection=capability_selection,
    )
    self_check_contract = _self_check_contract(payload, decision=decision, task_model=task_model)
    boundary = _user_facing_boundary(task_model, decision=decision)

    payload.update(
        {
            "schema_version": PLAN_SCHEMA_VERSION,
            "task_model": task_model,
            "capability_selection": capability_selection,
            "execution_contract": execution_contract,
            "self_check_contract": self_check_contract,
            "user_facing_boundary": boundary,
        }
    )
    payload["agent_plan_v2"] = {
        "task_model": task_model,
        "capability_selection": capability_selection,
        "execution_contract": execution_contract,
        "self_check_contract": self_check_contract,
        "user_facing_boundary": boundary,
    }
    return payload


def review_agent_observation(
    query: str,
    observation: Any,
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
) -> dict[str, Any]:
    """Review a Guanlan observation and return the next Agent decision."""

    plan = build_agent_plan_v2(
        query,
        mode=mode,
        preset=preset,
        scope=scope,
        site=site,
        sites=sites,
        profile=profile,
        limit=limit,
        read_top=read_top,
        max_commands=max_commands,
    )
    normalized = normalize_agent_observation(observation)
    decision, reason = _next_decision(normalized)
    next_commands = _review_next_commands(
        decision,
        reason,
        plan,
        observation=normalized,
        query=str(query or plan.get("query") or ""),
        profile=profile or _profile_from_plan(plan),
    )
    boundary = _review_boundary(decision, reason, normalized)

    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "query": str(query or plan.get("query") or ""),
        "phase": "review",
        "next_decision": decision,
        "status": "needs_followup" if decision in {"continue", "repair", "authorize_browser", "ask_user"} else "ready",
        "reason": reason,
        "signals": normalized.get("signals", []),
        "observation_summary": normalized.get("summary", {}),
        "next_commands": next_commands,
        "must_not": _review_must_not(reason),
        "boundary": boundary,
        "user_facing_boundary": plan.get("user_facing_boundary", {}),
        "plan": plan,
    }


def build_agent_followup(tool_name: str, observation: Any, *, query: str = "") -> dict[str, Any]:
    """Return a tiny follow-up block suitable for search/read/research/daily JSON."""

    normalized = normalize_agent_observation(observation)
    decision, reason = _next_decision(normalized)
    command_seed = _followup_command_seed(tool_name, query, normalized)
    should_answer = decision == "answer"
    if tool_name in {"guanlan_search", "search"} and "small_limit" in normalized.get("signals", []):
        should_answer = False
    return {
        "status": "ready" if should_answer else "needs_followup",
        "should_answer": should_answer,
        "next_decision": decision,
        "reason": reason,
        "next_commands": command_seed,
        "boundary": _review_boundary(decision, reason, normalized),
    }


def format_agent_plan_v2_markdown(payload: dict[str, Any] | AgentPlan) -> str:
    """Render a v2 plan without dropping the familiar old Markdown sections."""

    data = payload.to_dict() if isinstance(payload, AgentPlan) else dict(payload)
    base = format_agent_plan_markdown(data)
    task = dict(data.get("task_model") or {})
    selection = dict(data.get("capability_selection") or {})
    execution = dict(data.get("execution_contract") or {})
    checks = dict(data.get("self_check_contract") or {})
    boundary = dict(data.get("user_facing_boundary") or {})

    lines = [base, "", "## Agent 决策卡 v2"]
    lines.append(f"- 任务类型: `{task.get('task_type') or 'general_search'}`")
    lines.append(f"- 时效性: `{task.get('time_sensitivity') or 'normal'}`")
    lines.append(f"- 风险等级: `{task.get('risk_level') or 'low'}`")
    if task.get("output_expectation"):
        lines.append(f"- 输出期待: {task['output_expectation']}")
    chain = selection.get("recommended_chain") or []
    if chain:
        lines.append(f"- 推荐能力链: {' -> '.join(f'`{item}`' for item in chain)}")
    avoided = selection.get("downranked_capabilities") or []
    if avoided:
        lines.append(f"- 降权能力: {', '.join(f'`{item}`' for item in avoided)}")
    lines.extend(["", "### 执行契约"])
    for item in execution.get("first_steps") or []:
        lines.append(f"- `{item}`")
    for item in execution.get("continue_when") or []:
        lines.append(f"- 继续条件: {item}")
    for item in execution.get("stop_when") or []:
        lines.append(f"- 停止条件: {item}")
    lines.extend(["", "### 自检契约"])
    for item in checks.get("must_check") or []:
        lines.append(f"- {item}")
    preferred = boundary.get("preferred_wording") or ""
    if preferred:
        lines.extend(["", "### 用户表述边界", f"- {preferred}"])
    return "\n".join(lines)


def format_agent_followup_context(followup: dict[str, Any] | None) -> str:
    """Render the small follow-up block for context outputs."""

    if not followup:
        return ""
    lines = ["## Agent Follow-up"]
    lines.append(f"- status: `{followup.get('status') or 'ready'}`")
    lines.append(f"- next_decision: `{followup.get('next_decision') or 'answer'}`")
    if followup.get("reason"):
        lines.append(f"- reason: {followup['reason']}")
    commands = [str(item) for item in followup.get("next_commands") or [] if str(item).strip()]
    if commands:
        lines.append("- next_commands:")
        for command in commands[:3]:
            lines.append(f"  - `{command}`")
    if followup.get("boundary"):
        lines.append(f"- boundary: {followup['boundary']}")
    return "\n".join(lines)


def load_observation_json(value: str | None) -> Any:
    """Load an observation from a JSON string or file path."""

    raw = str(value or "").strip()
    if not raw:
        return {}
    candidate = Path(raw)
    if candidate.exists() and candidate.is_file():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return json.loads(raw)


def normalize_agent_observation(observation: Any) -> dict[str, Any]:
    """Extract reusable quality signals from Guanlan JSON-like outputs."""

    if observation is None:
        observation = {}
    if isinstance(observation, str):
        try:
            observation = json.loads(observation)
        except json.JSONDecodeError:
            observation = {"text": observation}
    if isinstance(observation, list):
        observation = {"results": observation}
    if not isinstance(observation, dict):
        observation = {"value": observation}

    signals: list[str] = []
    summary: dict[str, Any] = {}
    text = json.dumps(observation, ensure_ascii=False, default=str).lower()

    results = observation.get("results")
    if isinstance(results, list):
        summary["result_count"] = len(results)
        if len(results) == 0:
            signals.append("empty_results")
    elif observation.get("result_count") == 0:
        summary["result_count"] = 0
        signals.append("empty_results")

    limit = _find_number(observation, ("limit", "requested_limit", "max_results"))
    if limit:
        summary["limit"] = limit
        if limit < 30:
            signals.append("small_limit")

    diagnostics = observation.get("diagnostics") if isinstance(observation.get("diagnostics"), dict) else {}
    quality_gate = observation.get("quality_gate") if isinstance(observation.get("quality_gate"), dict) else {}
    if "partial_salvage" in text or quality_gate.get("reason") == "partial_salvage":
        signals.append("partial_salvage")
    if "unusable" in text or "兜底状态: unusable" in text:
        signals.append("read_unusable")
    if "dynamic shell" in text or "动态页" in text or "access_gate" in text or "login" in text or "waf" in text:
        signals.append("page_needs_diagnosis_or_browser")
    if "official-only" in text or "official_only" in text or "官网" in text and "外部" in text and "不足" in text:
        signals.append("official_only")
    if "operation was aborted" in text or "timeout" in text or "timed out" in text or "超时" in text:
        signals.append("timeout_or_aborted")
    if "research" in text and ("失败" in text or "error" in text or "aborted" in text):
        signals.append("research_failed")
    if "editorial_health" in observation and isinstance(observation.get("editorial_health"), dict):
        health = observation["editorial_health"]
        summary["editorial_health"] = health.get("status")
        if health.get("status") in {"block", "warn"}:
            signals.append("editorial_health_warn")
    if diagnostics:
        summary["diagnostics"] = diagnostics
    return {"signals": _unique(signals), "summary": summary, "raw": observation}


def _task_model(query: str, *, decision: dict[str, Any], route_plan: dict[str, Any], mode: str) -> dict[str, Any]:
    intents = _unique(
        [str(item) for item in decision.get("route_intents") or []]
        + [str(item) for item in route_plan.get("primary_intents") or []]
        + [str(item) for item in route_plan.get("secondary_intents") or []]
    )
    task_type = _task_type(query, intents, mode)
    return {
        "task_type": task_type,
        "route_intents": intents,
        "time_sensitivity": _time_sensitivity(query, intents, mode),
        "risk_level": decision.get("risk_level") or "low",
        "target_audience": _target_audience(intents),
        "output_expectation": _output_expectation(task_type, query, mode),
        "hard_constraints": _hard_constraints(query, decision=decision),
        "minimum_candidate_pool": max(int(decision.get("recommended_limit") or DEFAULT_SEARCH_LIMIT), DEFAULT_SEARCH_LIMIT),
    }


def _capability_selection(
    primary_command: str,
    commands: list[Any],
    *,
    decision: dict[str, Any],
    route_plan: dict[str, Any],
    task_model: dict[str, Any],
) -> dict[str, Any]:
    chain = _chain_from_commands(commands)
    if not chain and primary_command:
        chain = [_tool_from_command(primary_command)]
    downranked: list[str] = []
    disabled: list[str] = []
    task_type = str(task_model.get("task_type") or "")
    if task_type not in {"deep_research", "comparison", "timeline", "dossier"}:
        downranked.append("research")
    if task_model.get("time_sensitivity") in {"today", "fresh"} and "hotnews" not in chain:
        chain.insert(0, "hotnews")
    if any(intent in {"tech", "wps_office"} for intent in task_model.get("route_intents") or []) and "feeds" not in chain:
        chain.insert(0 if "hotnews" not in chain else 1, "feeds")
    if task_type in {"brand_reputation", "market_daily"} and "daily" not in chain:
        chain.insert(0, "daily")
    return {
        "recommended_chain": _unique(chain),
        "primary_capability": _tool_from_command(primary_command),
        "downranked_capabilities": _unique(downranked),
        "disabled_capabilities": disabled,
        "why": _selection_reason(task_model, decision, route_plan),
    }


def _execution_contract(
    payload: dict[str, Any],
    *,
    decision: dict[str, Any],
    capability_selection: dict[str, Any],
) -> dict[str, Any]:
    timeout_seconds = int(decision.get("timeout_budget_seconds") or 90)
    repairs = [
        item.get("command") if isinstance(item, dict) else str(item)
        for item in payload.get("silent_repair_commands") or []
        if (item.get("command") if isinstance(item, dict) else str(item))
    ]
    commands = [
        item.get("command") if isinstance(item, dict) else str(item)
        for item in payload.get("agent_next_steps") or []
        if (item.get("command") if isinstance(item, dict) else str(item))
    ]
    return {
        "first_steps": commands[:3] or ([payload.get("primary_command")] if payload.get("primary_command") else []),
        "continue_when": [
            "结果池为空、少于 30、或 trace/quality 明确提示证据角色不足。",
            "只得到官方/官网材料，但任务需要全网、媒体、社区或用户样本。",
            "read 返回弱正文、动态页壳、登录/访问门槛或 fallback-only。",
        ],
        "stop_when": [
            "已覆盖任务要求的来源角色，并且代表性 URL 已读过。",
            "明确命中用户给定的 site/year/范围硬约束，没有证据支撑时不要放宽。",
            "review 返回 next_decision=answer 或 stop。",
        ],
        "timeout_budget_seconds": timeout_seconds,
        "timeout_budget_ms": timeout_budget_ms(timeout_seconds),
        "minimum_candidate_pool": int(decision.get("recommended_limit") or DEFAULT_SEARCH_LIMIT),
        "silent_repair_commands": repairs,
        "do_not_run": _execution_do_not_run(capability_selection),
    }


def _self_check_contract(payload: dict[str, Any], *, decision: dict[str, Any], task_model: dict[str, Any]) -> dict[str, Any]:
    tripwires = [item.get("signal", "") for item in payload.get("quality_tripwires") or [] if isinstance(item, dict)]
    must_check = [
        "是否拿到了足够候选池；低于 30 只能算 smoke，不能作研究级结论。",
        "是否至少读过代表性原文 URL，而不是只看搜索摘要。",
        "是否区分官方口径、外部报道、社区/用户样本和背景资料。",
    ]
    if task_model.get("time_sensitivity") in {"today", "fresh"}:
        must_check.append("是否补过 hotnews/时间窗证据，旧材料不能写成今日事实。")
    if any(intent in {"tech", "wps_office"} for intent in task_model.get("route_intents") or []):
        must_check.append("是否补过 feeds/开发者或产业线索，避免只看官网。")
    if decision.get("risk_level") in {"medium", "high"}:
        must_check.append("高影响领域必须保留来源时间、适用边界和非专业建议提醒。")
    return {
        "must_check": _unique(must_check),
        "quality_tripwires": tripwires,
        "review_inputs": [
            "search JSON/trace、read quality packet、research packet、daily editorial_health，或错误摘要。",
            "传给 `guanlan agent --phase review --observation-json ... --json` 获取下一步。",
        ],
    }


def _user_facing_boundary(task_model: dict[str, Any], *, decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "preferred_wording": "当前证据包覆盖不足时，说“需要补证/补读代表性来源”，不要把工具状态当成结论。",
        "avoid_wording": ["Guanlan 崩了", "Guanlan 抽风了", "工具翻车", "搜索没用"],
        "evidence_boundary": _boundary_for_task(task_model, decision),
        "authorization_boundary": "浏览器可见页、私域页、Cookie/Token 访问仍需目标、用途、风险和只读范围的单独授权。",
    }


def _next_decision(observation: dict[str, Any]) -> tuple[str, str]:
    signals = set(observation.get("signals") or [])
    if "page_needs_diagnosis_or_browser" in signals:
        return "authorize_browser", "目标页公开读取不足，先按诊断路线或用户授权的浏览器可见页补证。"
    if "research_failed" in signals or "timeout_or_aborted" in signals:
        return "repair", "重型 research/网络读取未完成，降级为 search + read，不继续加大 read_top。"
    if "empty_results" in signals:
        return "repair", "结果池为空，需要扩大候选池、换 scope 或读取 direct seeds。"
    if "small_limit" in signals:
        return "repair", "当前是小样本 smoke，不足以支撑研究级回答。"
    if "read_unusable" in signals:
        return "repair", "页面正文不可用，先 diagnose page，再换结构化源或浏览器可见页补读。"
    if "official_only" in signals or "editorial_health_warn" in signals:
        return "continue", "来源覆盖不足，需要补外部报道、社区样本或候补线索。"
    if "partial_salvage" in signals:
        return "continue", "已有可用强来源但仍有缺口，读代表性 URL 后再回答。"
    return "answer", "证据边界足够清楚，可以在保留来源边界后回答。"


def _review_next_commands(
    decision: str,
    reason: str,
    plan: dict[str, Any],
    *,
    observation: dict[str, Any],
    query: str,
    profile: str | None,
) -> list[str]:
    if decision == "answer":
        return []
    signals = set(observation.get("signals") or [])
    repairs = [
        item.get("command") if isinstance(item, dict) else str(item)
        for item in plan.get("silent_repair_commands") or []
        if (item.get("command") if isinstance(item, dict) else str(item))
    ]
    next_steps = [
        item.get("command") if isinstance(item, dict) else str(item)
        for item in plan.get("agent_next_steps") or []
        if (item.get("command") if isinstance(item, dict) else str(item))
    ]
    if "small_limit" in signals or "empty_results" in signals:
        return _unique(repairs + next_steps)[:3] or [
            f"guanlan search {quote_query(query)} --profile {profile or 'china'} --limit 80 --trace"
        ]
    if "read_unusable" in signals or "page_needs_diagnosis_or_browser" in signals:
        url = _find_url(observation.get("raw", {}))
        if url:
            return [f"guanlan diagnose page {quote_query(url)} --json"]
        return _unique(next_steps + repairs)[:2]
    if "research_failed" in signals or "timeout_or_aborted" in signals:
        return [
            f"guanlan search {quote_query(query)} --profile {profile or 'china'} --limit 80 --trace",
            "guanlan read <selected_url> --quality-report",
        ]
    return _unique(next_steps + repairs)[:3]


def _review_boundary(decision: str, reason: str, observation: dict[str, Any]) -> str:
    if decision == "answer":
        return "可以回答，但保留来源身份、时间和样本边界。"
    if decision == "authorize_browser":
        return "需要用户明确授权后，只读取目标页可见内容；Cookie/Token/私信/订单等另走单独授权。"
    if "small_limit" in observation.get("signals", []):
        return "低 limit 只能算 smoke，不要当作全网或研究级结论。"
    return reason


def _review_must_not(reason: str) -> list[str]:
    return [
        "不要说 Guanlan 崩了、抽风了、挂了或没用。",
        "不要把空结果、小样本、页面不可读直接写成事实结论。",
        "不要为了避开超时把结果池缩到 30 以下后给强结论。",
    ]


def _followup_command_seed(tool_name: str, query: str, observation: dict[str, Any]) -> list[str]:
    signals = set(observation.get("signals") or [])
    if "small_limit" in signals or "empty_results" in signals:
        if query:
            return [f"guanlan search {quote_query(query)} --limit 80 --trace"]
    if tool_name in {"guanlan_read", "read"} and ("read_unusable" in signals or "page_needs_diagnosis_or_browser" in signals):
        url = _find_url(observation.get("raw", {}))
        if url:
            return [f"guanlan diagnose page {quote_query(url)} --json"]
    if tool_name in {"guanlan_research", "research"} and ("research_failed" in signals or "timeout_or_aborted" in signals):
        if query:
            return [
                f"guanlan search {quote_query(query)} --limit 80 --trace",
                "guanlan read <selected_url> --quality-report",
            ]
    return []


def _task_type(query: str, intents: list[str], mode: str) -> str:
    q = query.lower()
    if mode == "deep" or any(term in query for term in ("深度", "研究", "调研", "证据包", "报告")):
        return "deep_research"
    if any(term in query for term in ("日报", "舆情", "品牌", "公关", "市场")) or any(
        intent in {"reputation", "public_opinion", "crisis_watch", "competitor_watch"} for intent in intents
    ):
        return "brand_reputation"
    if any(term in query for term in ("今天", "今日", "最新", "刚刚", "突发")) or mode == "fresh":
        return "fresh_lookup"
    if any(intent in {"tech", "wps_office"} for intent in intents) or any(term in q for term in ("ai", "wps", "agent")):
        return "tech_tracking"
    if any(term in query for term in ("对比", "比较", "竞品")):
        return "comparison"
    if any(term in query for term in ("时间线", "历程", "演进")):
        return "timeline"
    return "general_search"


def _time_sensitivity(query: str, intents: list[str], mode: str) -> str:
    if mode == "fresh" or any(term in query for term in ("今天", "今日", "最新", "刚刚", "突发", "现在")):
        return "today"
    if any(term in query for term in ("最近", "近期", "本周", "这两天")):
        return "fresh"
    if any(intent in {"finance_quote", "weather_disaster", "sports"} for intent in intents):
        return "fresh"
    return "normal"


def _target_audience(intents: list[str]) -> str:
    if any(intent in {"reputation", "public_opinion", "crisis_watch", "competitor_watch", "review_intel"} for intent in intents):
        return "品牌、公关、市场、舆情团队"
    if any(intent.startswith("finance") for intent in intents):
        return "财经/投研/风控阅读者"
    if "cybersecurity" in intents:
        return "安全/运维/风险团队"
    return "通用 Agent 调研"


def _output_expectation(task_type: str, query: str, mode: str) -> str:
    if task_type == "brand_reputation":
        return "结构化主线、风险等级、行动建议、来源边界。"
    if task_type == "fresh_lookup":
        return "先确认时间窗，再给今天/近期的事实和待核验点。"
    if task_type == "tech_tracking":
        return "官方/开发者/产业/RSS 线索分层，而不是只看官网。"
    if task_type == "deep_research":
        return "可复用证据包；先 search/read，再 guarded research。"
    return "可引用的搜索结果与代表性原文阅读。"


def _hard_constraints(query: str, *, decision: dict[str, Any]) -> list[str]:
    constraints: list[str] = []
    if "--site" in str(decision):
        constraints.append("site 是硬过滤，返回为空也不能擅自放宽到其他域。")
    if any(char.isdigit() for char in query) and any(term in query for term in ("年", "202", "201")):
        constraints.append("显式年份/时间窗是强约束，窗外材料只能作背景。")
    return constraints


def _chain_from_commands(commands: list[Any]) -> list[str]:
    chain: list[str] = []
    for item in commands:
        command = item.get("command") if isinstance(item, dict) else getattr(item, "command", "")
        tool = _tool_from_command(str(command or ""))
        if tool:
            chain.append(tool)
    return _unique(chain)


def _tool_from_command(command: str) -> str:
    command = command.strip()
    if not command.startswith("guanlan"):
        return ""
    parts = command.split()
    if len(parts) < 2:
        return "agent"
    if parts[1] == "browser-assist":
        return "browser_assist"
    return parts[1]


def _selection_reason(task_model: dict[str, Any], decision: dict[str, Any], route_plan: dict[str, Any]) -> str:
    if task_model.get("task_type") == "brand_reputation":
        return "品牌/舆情任务优先日报、脉冲、recipe、search/read；research 只在缺证据角色后启用。"
    if task_model.get("time_sensitivity") in {"today", "fresh"}:
        return "近期任务先补 hotnews/时间窗，再进入 scoped search/read。"
    if any(intent in {"tech", "wps_office"} for intent in task_model.get("route_intents") or []):
        return "技术/AI/WPS 任务需要 feeds/RSS 发现，避免只读官网入口。"
    return "先用轻量 search/read 建证据底座，再根据质量信号继续。"


def _execution_do_not_run(capability_selection: dict[str, Any]) -> list[str]:
    items = ["不要在普通查询首步直接调用 research。", "不要因超时把 limit 缩到 30 以下后给强结论。"]
    if "research" in capability_selection.get("downranked_capabilities", []):
        items.append("除非用户明确要深度证据包，或 search+read 后仍缺关键证据角色，否则不升级 research。")
    return items


def _boundary_for_task(task_model: dict[str, Any], decision: dict[str, Any]) -> str:
    if task_model.get("task_type") == "brand_reputation":
        return "社区/平台线索是公开样本，不代表全网总体口碑。"
    if decision.get("risk_level") in {"medium", "high"}:
        return "高影响任务需要来源时间和适用边界，不输出医疗/法律/投资等专业建议。"
    return "回答必须区分搜索摘要、已读原文和待核验线索。"


def _find_number(payload: Any, keys: tuple[str, ...]) -> int | None:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        for value in payload.values():
            found = _find_number(value, keys)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_number(item, keys)
            if found is not None:
                return found
    return None


def _find_url(payload: Any) -> str:
    if isinstance(payload, dict):
        value = payload.get("url")
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
        for item in payload.values():
            found = _find_url(item)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_url(item)
            if found:
                return found
    return ""


def _profile_from_plan(plan: dict[str, Any]) -> str:
    decision = dict(plan.get("decision") or {})
    route_plan = dict(decision.get("route_plan") or {})
    return str(route_plan.get("profile") or "china")


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        clean = str(item or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


__all__ = [
    "PLAN_SCHEMA_VERSION",
    "REVIEW_SCHEMA_VERSION",
    "build_agent_followup",
    "build_agent_plan_v2",
    "format_agent_followup_context",
    "format_agent_plan_v2_markdown",
    "load_observation_json",
    "normalize_agent_observation",
    "review_agent_observation",
]
