# -*- coding: utf-8 -*-
"""Agent-facing web backend capability and extraction contracts."""

from __future__ import annotations

from typing import Any

BACKEND_CAPABILITY_SCHEMA_VERSION = "web_backend_capability_v1"
EXTRACT_CONTRACT_SCHEMA_VERSION = "read_extract_contract_v1"


def attach_read_contract(packet: dict[str, Any]) -> dict[str, Any]:
    """Attach backend capability and extraction contract to a read packet."""

    packet["backend_capability"] = build_backend_capability(packet)
    packet["extract_contract"] = build_extract_contract(packet)
    return packet


def build_backend_capability(packet: dict[str, Any]) -> dict[str, Any]:
    """Describe what the selected read backend can and cannot prove."""

    trace = dict(packet.get("trace") or {})
    selected = str(trace.get("selected_backend") or trace.get("backend") or "").strip() or "unknown"
    requested = str(trace.get("backend") or "").strip() or "auto"
    quality_report = dict(packet.get("quality_report") or {})
    fallback = bool(quality_report.get("fallback")) or selected == "search_fallback"
    weak_fragment = selected in {"weak_fallback", "unknown"} and bool(packet.get("content")) and not quality_report.get("usable")

    if fallback:
        provider_class = "search_context"
        trust_model = "search_context_only"
        can_extract_page_body = False
        boundary = "该结果来自搜索候选/摘要兜底，不等于目标 URL 的正文。"
    elif weak_fragment:
        provider_class = "reader"
        trust_model = "weak_public_page_fragment"
        can_extract_page_body = True
        boundary = "该后端只拿到弱正文片段，引用前需要补读或诊断。"
    elif selected == "cache":
        provider_class = "cache"
        trust_model = "cached_public_page_extraction"
        can_extract_page_body = True
        boundary = "该结果来自本地缓存的公开正文读取，仍以 quality_report.usable 为引用边界。"
    elif selected in {"jina", "direct", "wechat_article", "watch"}:
        provider_class = "reader"
        trust_model = "public_page_extraction"
        can_extract_page_body = True
        boundary = "该后端尝试读取目标 URL 的公开正文，能否引用取决于 quality_report.usable。"
    else:
        provider_class = "unknown"
        trust_model = "unknown_backend"
        can_extract_page_body = False
        boundary = "后端能力未知，先按线索处理并补读代表页。"

    return {
        "schema_version": BACKEND_CAPABILITY_SCHEMA_VERSION,
        "backend": selected,
        "requested_backend": requested,
        "provider_class": provider_class,
        "trust_model": trust_model,
        "can_search": fallback,
        "can_extract_page_body": can_extract_page_body,
        "can_extract_metadata": selected in {"direct", "wechat_article", "cache", "jina"},
        "can_cite_as_page_body": bool(quality_report.get("usable")) and can_extract_page_body and not fallback,
        "result_boundary": boundary,
        "quiet_user_facing": True,
    }


def build_extract_contract(packet: dict[str, Any]) -> dict[str, Any]:
    """Build a compact contract for Agent review after a read attempt."""

    trace = dict(packet.get("trace") or {})
    quality_report = dict(packet.get("quality_report") or {})
    capability = dict(packet.get("backend_capability") or build_backend_capability(packet))
    content = str(packet.get("content") or "")
    selected = str(capability.get("backend") or "")
    content_truncated = bool(trace.get("content_truncated"))
    can_cite = bool(capability.get("can_cite_as_page_body"))
    status = _contract_status(
        content=content,
        can_cite=can_cite,
        selected_backend=selected,
        quality_report=quality_report,
    )
    next_actions = _recommended_next_actions(status=status, selected_backend=selected, content_truncated=content_truncated)

    return {
        "schema_version": EXTRACT_CONTRACT_SCHEMA_VERSION,
        "status": status,
        "extract": str(trace.get("extract") or "article"),
        "selected_backend": selected,
        "can_cite_as_page_body": can_cite,
        "requires_followup": not can_cite,
        "recommended_next_actions": next_actions,
        "agent_instruction": _agent_instruction(status, content_truncated=content_truncated),
        "user_facing_boundary": _user_facing_boundary(status),
        "avoid_user_facing_error": True,
        "truncation": {
            "content_truncated": content_truncated,
            "returned_chars": len(content),
            "source_chars": int(trace.get("source_chars") or len(content)),
            "max_chars": int(trace.get("max_chars") or 0),
            "advice": "需要完整长文时提高 --max-chars 或改读更聚焦的代表页。" if content_truncated else "",
        },
    }


def _contract_status(
    *,
    content: str,
    can_cite: bool,
    selected_backend: str,
    quality_report: dict[str, Any],
) -> str:
    if selected_backend == "search_fallback" or quality_report.get("fallback"):
        return "context_only"
    if can_cite:
        return "usable"
    if content.strip():
        return "weak"
    return "unavailable"


def _recommended_next_actions(*, status: str, selected_backend: str, content_truncated: bool) -> list[str]:
    actions: list[str] = []
    if status == "context_only":
        actions.extend(["read_original_url", "diagnose_page", "read_representative_candidate"])
    elif status in {"weak", "unavailable"}:
        actions.extend(["diagnose_page", "read_backend_direct", "use_external_fetch_strategy_if_available"])
    if content_truncated:
        actions.append("increase_max_chars_or_choose_focused_url")
    return actions


def _agent_instruction(status: str, *, content_truncated: bool) -> str:
    if status == "usable":
        if content_truncated:
            return "可引用已返回正文，但这是截断读页；若结论依赖后半部分，继续提高 max_chars 或换更聚焦 URL。"
        return "可把该页作为代表页正文证据引用，同时保留来源和时间边界。"
    if status == "context_only":
        return "当前只有搜索上下文，不能当目标页正文；先按 next_actions 补读原文或代表页。"
    if status == "weak":
        return "当前正文较弱，只作线索；先诊断页面或补读结构化/代表来源。"
    return "当前没有可引用正文；按诊断、direct read 或外部定点补证路线继续。"


def _user_facing_boundary(status: str) -> str:
    if status == "usable":
        return "直接引用证据即可，不需要向用户额外解释后端状态。"
    if status == "context_only":
        return "对用户说“当前只是线索，需要补读原文”，不要说工具失败。"
    return "对用户说“公开正文覆盖不足，需要补证”，不要把后端状态包装成结论。"
