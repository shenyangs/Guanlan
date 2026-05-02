# -*- coding: utf-8 -*-
"""First-run welcome guidance for Guanlan users."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from guanlan.config import Config


def _state_path() -> Path:
    """Return the onboarding state file path, overridable for tests."""
    override = os.environ.get("GUANLAN_ONBOARDING_FILE")
    if override:
        return Path(override).expanduser()
    return Config.CONFIG_DIR / "onboarding.json"


def _read_state() -> dict[str, Any]:
    path = _state_path()
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return {}


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Onboarding state should never make the CLI fail.
        return


def welcome_was_shown() -> bool:
    """Return whether the first-run welcome card was already shown."""
    return bool(_read_state().get("welcome_shown"))


def mark_welcome_shown() -> None:
    """Persist that the first-run welcome card has been shown."""
    state = _read_state()
    state["welcome_shown"] = True
    _write_state(state)


def format_welcome_card() -> str:
    """Render a compact welcome card for non-technical users."""
    lines = [
        "观澜已安装完成。",
        "",
        "它是给 AI Agent 用的中文互联网检索工具，可以帮 Agent：",
        "1. 搜索中文互联网资料，并区分官方、媒体、社区、电商等信源",
        "2. 阅读网页/文章，把内容整理成 Agent 可用的证据",
        "3. 查看百度、微博、B站、IT之家、V2EX 等热榜",
        "4. 做 research 证据包，需要时给出谨慎的“助理视角”建议",
        "5. 把查过、读过、核验过的资料沉淀到本地 archive，后续接 Agent Wiki / RAG / 本地模型",
        "",
        "你可以直接这样对 Agent 说：",
        "",
        "- 用观澜查一下「低空经济 最新政策」",
        "- 用观澜读这个链接：https://example.com/article",
        "- 用观澜看今天中文互联网热点",
        "- 用观澜查这个产品的用户评价，查完给我建议",
        "- 先用观澜判断这个问题应该查哪些信源",
        "- 用观澜把这次查过的资料存进本地知识库，以后做 Agent Wiki / RAG 可以复用",
        "- 用观澜从本地 archive 里整理一段上下文给 LM Studio",
        "",
        "安全边界：",
        "观澜默认只读公开信息，不会自动读取浏览器 Cookie，不会发帖、点赞、评论或私信。",
        "",
        "想看完整能力：",
        "guanlan capabilities",
    ]
    try:
        from guanlan import __version__
        from guanlan.update_check import format_update_notice, get_update_info

        info = get_update_info(__version__)
        if info:
            lines.extend(["", format_update_notice(info)])
    except Exception:
        pass
    return "\n".join(lines)


def show_welcome_once() -> bool:
    """Print the welcome card once after installation. Return True if printed."""
    if welcome_was_shown():
        return False
    print()
    print(format_welcome_card())
    mark_welcome_shown()
    return True
