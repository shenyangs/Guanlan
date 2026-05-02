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
        "verification": "unverified",
        "auth": "none",
        "batch": "allowed",
        "recommended_backend": "open-webSearch MCP",
        "expectation": "公开搜索后端可用不等于所有查询都稳定返回。",
    },
    "hotnews": {
        "region": "china",
        "category": "hotnews",
        "risk_level": "low",
        "stability": "best-effort",
        "verification": "unverified",
        "auth": "none",
        "batch": "limited",
        "recommended_backend": "native public endpoints",
        "fallback_backends": ["mcp-hotnews-server"],
        "expectation": "稳定源优先使用 baidu/v2ex；zhihu 为实验源，失败时改用搜索 fallback。",
    },
    "web": {
        "region": "global",
        "category": "web",
        "risk_level": "low",
        "stability": "stable",
        "verification": "verified",
        "auth": "none",
        "batch": "allowed",
    },
    "rss": {
        "region": "global",
        "category": "rss",
        "risk_level": "low",
        "stability": "stable",
        "verification": "verified",
        "auth": "none",
        "batch": "allowed",
    },
    "github": {
        "region": "global",
        "category": "dev",
        "risk_level": "low",
        "stability": "stable",
        "verification": "verified",
        "auth": "optional",
        "batch": "allowed",
    },
    "youtube": {
        "region": "global",
        "category": "video",
        "risk_level": "low",
        "stability": "best-effort",
        "verification": "unverified",
        "auth": "optional",
        "batch": "limited",
    },
    "wechat": {
        "region": "china",
        "category": "web",
        "risk_level": "medium",
        "stability": "best-effort",
        "verification": "unverified",
        "auth": "none",
        "batch": "limited",
        "expectation": "后端就绪只代表具备搜索/阅读路径，不代表公众号端到端稳定可用。",
    },
    "weibo": {
        "region": "china",
        "category": "social",
        "risk_level": "medium",
        "stability": "best-effort",
        "verification": "unverified",
        "auth": "optional",
        "batch": "blocked",
        "expectation": "公开网页线索可用性波动较大，必要时需要授权或降级为普通搜索。",
    },
    "xiaohongshu": {
        "region": "china",
        "category": "social",
        "risk_level": "high",
        "stability": "opt-in",
        "verification": "unverified",
        "auth": "required",
        "batch": "blocked",
        "expectation": "强依赖外部后端与登录态，适合按需启用，不适合默认批量读取。",
    },
    "douyin": {
        "region": "china",
        "category": "video",
        "risk_level": "high",
        "stability": "opt-in",
        "verification": "unverified",
        "auth": "external",
        "batch": "blocked",
    },
    "bilibili": {
        "region": "china",
        "category": "video",
        "risk_level": "medium",
        "stability": "best-effort",
        "verification": "unverified",
        "auth": "optional",
        "batch": "limited",
    },
    "twitter": {
        "region": "global",
        "category": "social",
        "risk_level": "high",
        "stability": "opt-in",
        "verification": "unverified",
        "auth": "required",
        "batch": "blocked",
    },
    "reddit": {
        "region": "global",
        "category": "social",
        "risk_level": "medium",
        "stability": "opt-in",
        "verification": "unverified",
        "auth": "optional",
        "batch": "limited",
    },
    "linkedin": {
        "region": "global",
        "category": "career",
        "risk_level": "high",
        "stability": "opt-in",
        "verification": "unverified",
        "auth": "required",
        "batch": "blocked",
    },
    "v2ex": {
        "region": "china",
        "category": "community",
        "risk_level": "low",
        "stability": "stable",
        "verification": "verified",
        "auth": "none",
        "batch": "allowed",
    },
    "xueqiu": {
        "region": "china",
        "category": "finance",
        "risk_level": "medium",
        "stability": "best-effort",
        "verification": "unverified",
        "auth": "optional",
        "batch": "limited",
    },
    "xiaoyuzhou": {
        "region": "china",
        "category": "audio",
        "risk_level": "low",
        "stability": "opt-in",
        "verification": "unverified",
        "auth": "api-key",
        "batch": "limited",
    },
    "exa_search": {
        "region": "global",
        "category": "search",
        "risk_level": "low",
        "stability": "opt-in",
        "verification": "unverified",
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
    "english": [
        "github",
        "web",
        "rss",
        "exa_search",
        "reddit",
        "youtube",
        "twitter",
        "linkedin",
        "open_websearch",
        "hotnews",
        "v2ex",
        "wechat",
        "weibo",
        "bilibili",
        "xiaohongshu",
        "douyin",
        "xueqiu",
        "xiaoyuzhou",
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
        "verification": "unverified",
        "auth": "unknown",
        "batch": "limited",
    }
    return {**defaults, **CHANNEL_CATALOG.get(name, {})}
