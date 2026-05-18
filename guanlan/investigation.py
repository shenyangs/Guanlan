# -*- coding: utf-8 -*-
"""Explicit upper-layer investigation workflow for Guanlan.

This module composes existing route/research primitives. It deliberately does
not change the default behavior of search/read/hotnews.
"""

from __future__ import annotations

import json
from typing import Any

from guanlan.workflow_decider import decide_workflow, format_workflow_decision_markdown


def build_investigation_packet(
    query: str,
    *,
    preset: str = "general",
    profile: str | None = None,
    limit: int | None = None,
    read_top: int | None = None,
    budget: str = "standard",
    dry_run: bool = False,
    search_backend: str = "auto",
    read_backend: str = "auto",
    max_read_chars: int | None = None,
    advisor: bool = True,
    advisor_style: str = "strategy",
    select_top: int | None = None,
) -> dict[str, Any]:
    """Build a deep investigation packet while reusing the stable research path."""

    from guanlan.webtools import build_research_packet

    budget = _normalize_budget(budget)
    decision = decide_workflow(
        query,
        command="investigate",
        preset=preset,
        profile=profile,
        limit=limit,
        read_top=read_top,
        explicit_deep=True,
    )
    effective_limit = max(limit or decision.recommended_limit, _budget_limit_floor(budget), decision.recommended_limit)
    effective_read_top = _budget_read_top(
        budget,
        requested=read_top,
        recommended=decision.recommended_read_top,
    )
    plan = _execution_plan(decision.to_dict(), budget=budget, read_top=effective_read_top)
    if dry_run:
        return {
            "query": query,
            "workflow_decision": decision.to_dict(),
            "investigation": {
                "stage": "upper_workflow",
                "entrypoint": "investigate",
                "budget": budget,
                "dry_run": True,
                "principle": "dry-run 只解释会跑什么，不发起搜索、阅读或外部网络请求。",
                "executed_steps": [],
                "skipped_steps": plan["skipped_steps"],
                "planned_steps": plan["planned_steps"],
                "limits": {"limit": effective_limit, "read_top": effective_read_top},
                "step_budget": _step_budget(budget),
                "timeout_budget_seconds": _timeout_budget_seconds(budget),
                "fallback_used": False,
                "external_fetch_strategy": _external_fetch_strategy("planned"),
                "network_diagnosis": _network_diagnosis(None),
                "evidence_sufficiency": _evidence_sufficiency(None),
                "next_views": _next_views(decision.to_dict()),
            },
            "open_questions": _open_questions(decision.to_dict()),
            "suggested_next": _suggested_next(decision.to_dict(), budget=budget),
        }
    packet = build_research_packet(
        query,
        preset=preset,
        limit=effective_limit,
        profile=profile,
        read_top=effective_read_top,
        search_backend=search_backend,
        read_backend=read_backend,
        max_read_chars=max_read_chars,
        advisor=advisor,
        advisor_style=advisor_style,
        select_top=select_top,
    )
    packet["workflow_decision"] = decision.to_dict()
    packet["investigation"] = {
        "stage": "upper_workflow",
        "entrypoint": "investigate",
        "budget": budget,
        "dry_run": False,
        "principle": "先用稳定 evidence packet 打底，再组织更高阶的判断；不改变基础 search 的轻路径。",
        "executed_steps": plan["executed_steps"],
        "skipped_steps": plan["skipped_steps"],
        "planned_steps": plan["planned_steps"],
        "limits": {"limit": effective_limit, "read_top": effective_read_top},
        "step_budget": _step_budget(budget),
        "timeout_budget_seconds": _timeout_budget_seconds(budget),
        "fallback_used": _fallback_used(packet),
        "external_fetch_strategy": _external_fetch_strategy("used" if _fallback_used(packet) else "available", packet=packet),
        "network_diagnosis": _network_diagnosis(packet),
        "evidence_sufficiency": _evidence_sufficiency(packet),
        "next_views": _next_views(decision.to_dict()),
    }
    packet["open_questions"] = _open_questions(decision.to_dict(), packet=packet)
    packet["suggested_next"] = _suggested_next(decision.to_dict(), budget=budget)
    packet["final_context"] = _final_context_summary(packet)
    guidance = list(packet.get("guidance") or [])
    guidance.insert(0, "本次使用 investigate：这是显式上层工作流，不代表普通 search 也要这么重。")
    packet["guidance"] = guidance
    return packet


def format_investigation_markdown(packet: dict[str, Any]) -> str:
    """Render an investigation packet as Markdown."""

    from guanlan.webtools import format_research_markdown

    lines = ["# 观澜深查工作流", ""]
    decision = packet.get("workflow_decision")
    if isinstance(decision, dict):
        lines.append(format_workflow_decision_markdown(decision))
        lines.append("")
    investigation = packet.get("investigation") or {}
    if isinstance(investigation, dict):
        lines.extend(["## 深查边界", f"- 原则: {investigation.get('principle', '')}"])
        lines.append(f"- budget: {investigation.get('budget', 'standard')}")
        if investigation.get("dry_run"):
            lines.append("- dry-run: 是，本次没有发起搜索或阅读请求。")
        if investigation.get("executed_steps"):
            lines.append("- 已执行: " + " -> ".join(str(item) for item in investigation.get("executed_steps") or []))
        if investigation.get("planned_steps"):
            lines.append("- 计划: " + " -> ".join(str(item) for item in investigation.get("planned_steps") or []))
        next_views = investigation.get("next_views") or []
        if next_views:
            lines.append("- 后续视图: " + "；".join(str(item) for item in next_views))
        lines.append("")
    lines.append(format_research_markdown(packet))
    return "\n".join(lines).rstrip()


def format_investigation_context(packet: dict[str, Any]) -> str:
    """Render compact prompt-ready context for an investigation packet."""

    from guanlan.webtools import (
        format_advisor_context,
        format_claim_ledger_context,
        format_evidence_audit_context,
        format_search_context,
    )

    evidence = packet.get("selected_evidence") or packet.get("results") or []
    lines = [format_search_context(evidence, title=f"观澜深查上下文 / {packet.get('query', '')}")]
    if isinstance(packet.get("workflow_decision"), dict):
        lines.append("\n## 工作流分流\n" + json.dumps(packet["workflow_decision"], ensure_ascii=False, indent=2))
    if isinstance(packet.get("evidence_audit"), dict):
        lines.append(format_evidence_audit_context(packet["evidence_audit"]))
    if isinstance(packet.get("claim_ledger"), dict):
        lines.append(format_claim_ledger_context(packet["claim_ledger"]))
    if isinstance(packet.get("advisor"), dict):
        lines.append(format_advisor_context(packet["advisor"]))
    if packet.get("open_questions"):
        lines.append("## 待核验问题\n" + "\n".join(f"- {item}" for item in packet.get("open_questions") or []))
    if packet.get("suggested_next"):
        lines.append("## 建议下一步\n" + "\n".join(f"- `{item}`" for item in packet.get("suggested_next") or []))
    return "\n\n".join(lines).rstrip()


def _next_views(decision: dict[str, Any]) -> list[str]:
    entrypoint = str(decision.get("recommended_entrypoint") or "research")
    query = str(decision.get("query") or "query")
    if entrypoint == "compare":
        return ["如果用户给出两个以上明确对象，继续用 guanlan compare。"]
    if entrypoint == "timeline":
        return [f"guanlan timeline {query!r} --limit 80 --format context"]
    if entrypoint == "dossier":
        return [f"guanlan dossier {query!r} --limit 80 --format context"]
    return ["必要时按证据缺口继续补 compare / timeline / dossier，而不是重复泛搜。"]


def _normalize_budget(budget: str) -> str:
    value = (budget or "standard").strip().lower()
    return value if value in {"light", "standard", "deep"} else "standard"


def _budget_limit_floor(budget: str) -> int:
    return {"light": 80, "standard": 80, "deep": 100}.get(budget, 80)


def _budget_read_top(budget: str, *, requested: int | None, recommended: int) -> int:
    if requested is not None:
        return max(requested, 0)
    if budget == "light":
        return min(max(recommended, 1), 2)
    if budget == "deep":
        return max(recommended, 6)
    return max(recommended, 4)


def _step_budget(budget: str) -> dict[str, int]:
    return {
        "light": {"max_steps": 3, "max_reads": 2, "max_sidecars": 0},
        "standard": {"max_steps": 5, "max_reads": 4, "max_sidecars": 1},
        "deep": {"max_steps": 8, "max_reads": 8, "max_sidecars": 3},
    }.get(budget, {"max_steps": 5, "max_reads": 4, "max_sidecars": 1})


def _timeout_budget_seconds(budget: str) -> int:
    return {"light": 120, "standard": 240, "deep": 420}.get(budget, 240)


def _execution_plan(decision: dict[str, Any], *, budget: str, read_top: int) -> dict[str, list[str]]:
    path = ["workflow", "route", "research"]
    skipped: list[str] = []
    if budget in {"standard", "deep"}:
        path.extend(["scoped search", "read"])
    else:
        skipped.extend(["scoped search", "expanded read"])
    intents = set(decision.get("route_intents") or [])
    if budget == "deep" and ("hot_trend" in intents or decision.get("recommended_entrypoint") == "timeline"):
        path.append("hotnews")
    elif "hot_trend" in intents:
        skipped.append("hotnews unless freshness remains unclear")
    if budget == "deep" and {"tech", "wps_office"} & intents:
        path.append("feeds")
    elif {"tech", "wps_office"} & intents:
        skipped.append("feeds unless tech/WPS evidence is too thin")
    entrypoint = str(decision.get("recommended_entrypoint") or "")
    if budget == "deep" and entrypoint in {"compare", "timeline", "dossier"}:
        path.append(entrypoint)
    elif entrypoint in {"compare", "timeline", "dossier"}:
        skipped.append(f"{entrypoint} view unless user asks for structured output")
    if read_top <= 0:
        skipped.append("read disabled by --read-top 0")
    return {"planned_steps": path, "executed_steps": path, "skipped_steps": skipped}


def _fallback_used(packet: dict[str, Any]) -> bool:
    diagnostics = packet.get("diagnostics") if isinstance(packet.get("diagnostics"), dict) else {}
    backend_trace = packet.get("backend_trace") if isinstance(packet.get("backend_trace"), list) else []
    if diagnostics.get("fallback_used"):
        return True
    return any(str(item).lower().find("fallback") >= 0 for item in backend_trace)


def _external_fetch_strategy(state: str, packet: dict[str, Any] | None = None) -> dict[str, Any]:
    result_count = int((packet or {}).get("result_count") or len((packet or {}).get("results") or []))
    readings = (packet or {}).get("readings") or []
    should_suggest = state == "planned" or result_count == 0 or (packet is not None and not readings)
    return {
        "state": state,
        "suggest_webfetch_when": [
            "Guanlan 工作流已完成但结果池为空或关键来源缺失",
            "实时/热点任务受上游或地区网络影响，需宿主 Agent 临时补一轮 WebFetch",
            "用户所在 Agent 平台本身提供 WebFetch，且需要外显说明补强策略",
        ],
        "message": (
            "如需调用宿主 WebFetch，应说明这是观澜建议的搜索增强策略，"
            "不是静默绕过或证明 Guanlan 脆弱；WebFetch 结果也应保留来源和时间边界。"
        ),
        "recommended": should_suggest,
    }


def _network_diagnosis(packet: dict[str, Any] | None) -> dict[str, Any]:
    if packet is None:
        return {
            "status": "not_run",
            "network_or_upstream": "unknown",
            "message": "dry-run 未发起网络请求。",
        }
    result_count = int(packet.get("result_count") or len(packet.get("results") or []))
    readings = packet.get("readings") or []
    errors = [item for item in readings if item.get("status") not in {None, "", "ok"}]
    if result_count == 0:
        status = "warn"
        message = "搜索候选池为空；应先视为网络/上游/后端证据，不直接断言主题无结果。"
    elif errors:
        status = "partial"
        message = "搜索已有候选，但部分阅读失败；可降低 read_top、启用缓存或回读更稳来源。"
    else:
        status = "ok"
        message = "未观察到明显网络退化信号。"
    return {
        "status": status,
        "result_count": result_count,
        "read_errors": len(errors),
        "network_or_upstream": "possible" if status in {"warn", "partial"} else "not_observed",
        "message": message,
    }


def _evidence_sufficiency(packet: dict[str, Any] | None) -> dict[str, Any]:
    if packet is None:
        return {
            "status": "planned",
            "score": 0,
            "missing": ["not_executed"],
            "message": "dry-run 只规划，不评价证据充分性。",
        }
    results = packet.get("selected_evidence") or packet.get("results") or []
    source_mix = packet.get("source_mix") if isinstance(packet.get("source_mix"), dict) else {}
    readings = packet.get("readings") or []
    score = 0
    missing: list[str] = []
    if len(results) >= 8:
        score += 35
    else:
        missing.append("candidate_pool")
    if len(source_mix) >= 3:
        score += 25
    else:
        missing.append("source_diversity")
    if any(item.get("status") == "ok" for item in readings):
        score += 25
    else:
        missing.append("read_verification")
    if packet.get("evidence_audit") or packet.get("quality_summary"):
        score += 15
    else:
        missing.append("evidence_audit")
    status = "strong" if score >= 80 else "usable" if score >= 55 else "thin"
    return {
        "status": status,
        "score": score,
        "missing": missing,
        "message": "证据包可用但仍需按 missing 字段补证。" if missing else "证据包结构较完整。",
    }


def _open_questions(decision: dict[str, Any], packet: dict[str, Any] | None = None) -> list[str]:
    questions = ["哪些关键事实仍需要回到原文核验？"]
    risk = str(decision.get("risk_level") or "low")
    if risk == "high":
        questions.append("该主题是否涉及法律、医疗、财经、安全或公共安全边界，需要专业来源复核？")
    if packet and not packet.get("readings"):
        questions.append("当前证据包是否缺少原文摘读，需要降低 read_top 以外的补读策略？")
    return questions


def _suggested_next(decision: dict[str, Any], *, budget: str) -> list[str]:
    query = str(decision.get("query") or "query")
    entrypoint = str(decision.get("recommended_entrypoint") or "research")
    if budget == "light":
        return [f"guanlan research {query!r} --limit 80 --read-top 2 --format context"]
    if entrypoint in {"compare", "timeline", "dossier"}:
        return [f"guanlan {entrypoint} {query!r} --limit 80 --format context"]
    return [f"guanlan research {query!r} --limit 80 --advisor", f"guanlan archive ingest-research {query!r} --limit 80 --dry-run"]


def _final_context_summary(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": packet.get("query"),
        "result_count": packet.get("result_count", 0),
        "selected_count": len(packet.get("selected_evidence") or []),
        "read_success": sum(1 for item in packet.get("readings") or [] if item.get("status") == "ok"),
        "source_mix": packet.get("source_mix", {}),
        "boundary": "final_context 是证据包摘要，不替代原文核验。",
    }
