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
    search_backend: str = "auto",
    read_backend: str = "auto",
    max_read_chars: int | None = None,
    advisor: bool = True,
    advisor_style: str = "strategy",
    select_top: int | None = None,
) -> dict[str, Any]:
    """Build a deep investigation packet while reusing the stable research path."""

    from guanlan.webtools import build_research_packet

    decision = decide_workflow(
        query,
        command="investigate",
        preset=preset,
        profile=profile,
        limit=limit,
        read_top=read_top,
        explicit_deep=True,
    )
    effective_limit = max(limit or decision.recommended_limit, decision.recommended_limit)
    effective_read_top = max(read_top if read_top is not None else decision.recommended_read_top, 0)
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
        "principle": "先用稳定 evidence packet 打底，再组织更高阶的判断；不改变基础 search 的轻路径。",
        "next_views": _next_views(decision.to_dict()),
    }
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
        format_evidence_audit_context,
        format_search_context,
    )

    evidence = packet.get("selected_evidence") or packet.get("results") or []
    lines = [format_search_context(evidence, title=f"观澜深查上下文 / {packet.get('query', '')}")]
    if isinstance(packet.get("workflow_decision"), dict):
        lines.append("\n## 工作流分流\n" + json.dumps(packet["workflow_decision"], ensure_ascii=False, indent=2))
    if isinstance(packet.get("evidence_audit"), dict):
        lines.append(format_evidence_audit_context(packet["evidence_audit"]))
    if isinstance(packet.get("advisor"), dict):
        lines.append(format_advisor_context(packet["advisor"]))
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
