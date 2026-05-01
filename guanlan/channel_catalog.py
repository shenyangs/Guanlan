# -*- coding: utf-8 -*-
"""Central channel metadata used by profile-aware UX.

This catalog is intentionally lightweight for now. Existing channel classes
remain the source of health-check behavior; the catalog gives doctor/install
surfaces a stable place to learn regional ordering and future channel metadata.
"""

from __future__ import annotations

from typing import Iterable, List

CHANNEL_CATALOG = {
    "open_websearch": {
        "region": "china",
        "category": "search",
        "risk_level": "low",
        "stability": "best-effort",
        "auth": "none",
        "batch": "allowed",
        "recommended_backend": "open-webSearch MCP",
    },
    "hotnews": {
        "region": "china",
        "category": "hotnews",
        "risk_level": "low",
        "stability": "best-effort",
        "auth": "none",
        "batch": "limited",
        "recommended_backend": "native public endpoints",
        "fallback_backends": ["mcp-hotnews-server"],
    },
    "web": {
        "region": "global",
        "category": "web",
        "risk_level": "low",
        "stability": "stable",
        "auth": "none",
        "batch": "allowed",
    },
    "rss": {
        "region": "global",
        "category": "rss",
        "risk_level": "low",
        "stability": "stable",
        "auth": "none",
        "batch": "allowed",
    },
    "github": {
        "region": "global",
        "category": "dev",
        "risk_level": "low",
        "stability": "stable",
        "auth": "optional",
        "batch": "allowed",
    },
    "youtube": {
        "region": "global",
        "category": "video",
        "risk_level": "low",
        "stability": "best-effort",
        "auth": "optional",
        "batch": "limited",
    },
    "wechat": {
        "region": "china",
        "category": "web",
        "risk_level": "medium",
        "stability": "best-effort",
        "auth": "none",
        "batch": "limited",
    },
    "weibo": {
        "region": "china",
        "category": "social",
        "risk_level": "medium",
        "stability": "best-effort",
        "auth": "optional",
        "batch": "blocked",
    },
    "xiaohongshu": {
        "region": "china",
        "category": "social",
        "risk_level": "high",
        "stability": "opt-in",
        "auth": "required",
        "batch": "blocked",
    },
    "douyin": {
        "region": "china",
        "category": "video",
        "risk_level": "high",
        "stability": "opt-in",
        "auth": "external",
        "batch": "blocked",
    },
    "bilibili": {
        "region": "china",
        "category": "video",
        "risk_level": "medium",
        "stability": "best-effort",
        "auth": "optional",
        "batch": "limited",
    },
    "twitter": {
        "region": "global",
        "category": "social",
        "risk_level": "high",
        "stability": "opt-in",
        "auth": "required",
        "batch": "blocked",
    },
    "reddit": {
        "region": "global",
        "category": "social",
        "risk_level": "medium",
        "stability": "opt-in",
        "auth": "optional",
        "batch": "limited",
    },
    "linkedin": {
        "region": "global",
        "category": "career",
        "risk_level": "high",
        "stability": "opt-in",
        "auth": "required",
        "batch": "blocked",
    },
    "v2ex": {
        "region": "china",
        "category": "community",
        "risk_level": "low",
        "stability": "stable",
        "auth": "none",
        "batch": "allowed",
    },
    "xueqiu": {
        "region": "china",
        "category": "finance",
        "risk_level": "medium",
        "stability": "best-effort",
        "auth": "optional",
        "batch": "limited",
    },
    "xiaoyuzhou": {
        "region": "china",
        "category": "audio",
        "risk_level": "low",
        "stability": "opt-in",
        "auth": "api-key",
        "batch": "limited",
    },
    "exa_search": {
        "region": "global",
        "category": "search",
        "risk_level": "low",
        "stability": "opt-in",
        "auth": "external",
        "batch": "allowed",
    },
}


PROFILE_CHANNEL_ORDER = {
    "china": [
        "open_websearch",
        "hotnews",
        "wechat",
        "weibo",
        "xiaohongshu",
        "douyin",
        "bilibili",
        "v2ex",
        "xueqiu",
        "xiaoyuzhou",
        "rss",
        "web",
        "github",
        "exa_search",
        "youtube",
        "twitter",
        "reddit",
        "linkedin",
    ],
    "hybrid": [
        "github",
        "open_websearch",
        "exa_search",
        "hotnews",
        "web",
        "rss",
        "wechat",
        "weibo",
        "xiaohongshu",
        "douyin",
        "bilibili",
        "youtube",
        "twitter",
        "reddit",
        "v2ex",
        "xiaoyuzhou",
        "linkedin",
    ],
}


def order_channel_names(names: Iterable[str], profile: str | None = None) -> List[str]:
    """Order channel names for a profile while preserving unknown channels."""
    name_list = list(names)
    preferred = PROFILE_CHANNEL_ORDER.get(profile or "")
    if not preferred:
        return name_list

    preferred_rank = {name: idx for idx, name in enumerate(preferred)}
    original_rank = {name: idx for idx, name in enumerate(name_list)}

    return sorted(
        name_list,
        key=lambda name: (
            preferred_rank.get(name, len(preferred_rank) + original_rank[name]),
            original_rank[name],
        ),
    )


def get_channel_metadata(name: str) -> dict:
    """Return conservative metadata defaults for a channel."""
    defaults = {
        "region": "global",
        "category": "misc",
        "risk_level": "medium",
        "stability": "best-effort",
        "auth": "unknown",
        "batch": "limited",
    }
    return {**defaults, **CHANNEL_CATALOG.get(name, {})}
