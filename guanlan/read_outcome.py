# -*- coding: utf-8 -*-
"""Canonical outcome state for a single public-page read attempt.

The read stack already exposes quality and extraction contracts. This module
compresses those compatible signals into one stable Agent-facing state without
changing the underlying reader or its fallback behavior.
"""

from __future__ import annotations

from typing import Any

READ_OUTCOME_SCHEMA_VERSION = "read_outcome_v1"


def build_read_outcome(packet: dict[str, Any]) -> dict[str, Any]:
    """Return one citation-oriented outcome for a read packet."""

    source = dict(packet or {})
    contract = dict(source.get("extract_contract") or {})
    quality = dict(source.get("quality_report") or {})
    trace = dict(source.get("trace") or {})
    content = str(source.get("content") or "")
    raw_status = str(contract.get("status") or "").strip().lower()
    selected_backend = str(
        contract.get("selected_backend") or trace.get("selected_backend") or trace.get("backend") or "unknown"
    )
    citation_allowed = bool(contract.get("can_cite_as_page_body"))

    if raw_status == "context_only" or quality.get("fallback") or selected_backend == "search_fallback":
        state = "context_only"
    elif citation_allowed:
        state = "page_body"
    elif content.strip():
        state = "weak_body"
    else:
        state = "unavailable"

    if state == "page_body":
        boundary = "该页是可引用的公开正文；仍应保留来源和时间边界。"
    elif state == "context_only":
        boundary = "当前只是搜索上下文线索，不是目标页正文；不能作为正文事实引用。"
    elif state == "weak_body":
        boundary = "当前只获得弱正文片段；可作为线索，但引用前需要补读或诊断。"
    else:
        boundary = "当前没有可引用的公开正文；需要诊断页面或改读代表来源。"

    truncation = contract.get("truncation") if isinstance(contract.get("truncation"), dict) else {}
    return {
        "schema_version": READ_OUTCOME_SCHEMA_VERSION,
        "state": state,
        "citation_allowed": citation_allowed,
        "selected_backend": selected_backend,
        "quality_label": str(quality.get("label") or ""),
        "next_decision": "answer" if state == "page_body" else "repair",
        "next_actions": list(contract.get("recommended_next_actions") or []),
        "content_truncated": bool(truncation.get("content_truncated")),
        "boundary": boundary,
    }


def attach_read_outcome(packet: dict[str, Any]) -> dict[str, Any]:
    """Attach ``read_outcome_v1`` in-place and return the packet."""

    packet["read_outcome"] = build_read_outcome(packet)
    return packet


__all__ = ["READ_OUTCOME_SCHEMA_VERSION", "attach_read_outcome", "build_read_outcome"]
