# -*- coding: utf-8 -*-
"""Canonical request normalization for Guanlan's public tool surfaces.

CLI, MCP, and HTTP intentionally keep their own presentation layers.  This
module gives them one small, explicit place to agree on service kwargs before
they invoke search, read, research, route, or the Agent planner.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from guanlan.limits import (
    DEFAULT_MCP_RESEARCH_READ_TOP,
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    MAX_MCP_RESEARCH_READ_TOP,
    MAX_READ_FALLBACK_LIMIT,
    MAX_RESEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
)


def _text(value: Any, default: str = "") -> str:
    return str(value).strip() if value is not None else default


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _profile(value: Any, default: str | None) -> str | None:
    return _optional_text(value) or default


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _optional_bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    if value is None or value == "":
        return None
    return _bounded_int(value, minimum, minimum, maximum)


def _optional_minimum_int(value: Any, minimum: int) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(int(value), minimum)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str] | None:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        return None
    normalized = [_text(item) for item in values]
    return [item for item in normalized if item] or None


def normalize_search_request(
    payload: Mapping[str, Any], *, default_profile: str | None = "china"
) -> dict[str, Any]:
    """Normalize service kwargs for ``search_web`` without changing defaults."""

    # A number of MCP hosts historically exposed this knob as ``max_results``.
    # Treat it as a compatibility alias, while letting canonical ``limit`` win
    # whenever both are present.
    limit_value = payload.get("limit")
    if limit_value is None:
        limit_value = payload.get("max_results")

    return {
        "query": _text(payload.get("query")),
        "limit": _bounded_int(limit_value, DEFAULT_SEARCH_LIMIT, 1, MAX_SEARCH_LIMIT),
        "site": _optional_text(payload.get("site")),
        "scope": _optional_text(payload.get("scope")),
        "backend": _text(payload.get("backend"), "auto") or "auto",
        "profile": _profile(payload.get("profile"), default_profile),
        "network_mode": _text(payload.get("network_mode", payload.get("network")), "auto") or "auto",
        "trace": _bool(payload.get("trace")),
        "cluster_threshold": _text(payload.get("cluster_threshold"), "conservative") or "conservative",
        "cache_ttl": _bounded_int(payload.get("cache_ttl"), 0, 0, 86_400),
        "use_cache": not _bool(payload.get("no_cache")) if "use_cache" not in payload else _bool(payload.get("use_cache"), True),
        "strict_scope": _bool(payload.get("strict_scope")),
        "evidence_mode": _text(payload.get("evidence_mode"), "shadow") or "shadow",
    }


def normalize_read_request(
    payload: Mapping[str, Any], *, default_profile: str | None = "china"
) -> dict[str, Any]:
    """Normalize service kwargs for ``read_url_with_trace``."""

    no_cache = _bool(payload.get("no_cache"))
    max_chars_value = payload.get("max_chars")
    # The CLI uses 0 to mean "do not truncate". Preserve that public
    # contract when requests pass through the shared CLI/MCP/HTTP normalizer
    # instead of clamping the sentinel to a one-character response.
    if _text(max_chars_value) == "0":
        max_chars_value = None
    return {
        "url": _text(payload.get("url")),
        "max_chars": _optional_bounded_int(max_chars_value, 1, 100_000),
        "backend": _text(payload.get("backend"), "auto") or "auto",
        "fallback_search": _bool(payload.get("fallback_search"), True),
        "fallback_limit": _bounded_int(
            payload.get("fallback_limit"), DEFAULT_READ_FALLBACK_LIMIT, 1, MAX_READ_FALLBACK_LIMIT
        ),
        "profile": _profile(payload.get("profile"), default_profile),
        "cache_ttl": _bounded_int(payload.get("cache_ttl"), 0, 0, 86_400),
        "use_cache": False if no_cache else _bool(payload.get("use_cache"), True),
        "strict": _bool(payload.get("strict")),
        "extract": _text(payload.get("extract"), "article") or "article",
        "upstream_no_cache": no_cache or _bool(payload.get("upstream_no_cache")),
        "jina_engine": _text(payload.get("jina_engine"), "auto") or "auto",
        "jina_format": _text(payload.get("jina_format"), "content") or "content",
        "jina_wait_for": _text(payload.get("jina_wait_for")),
        "jina_target": _text(payload.get("jina_target")),
        "jina_remove": _text(payload.get("jina_remove")),
        "jina_repair": _bool(payload.get("jina_repair"), True),
    }


def normalize_research_request(
    payload: Mapping[str, Any],
    *,
    default_read_top: int | None = DEFAULT_MCP_RESEARCH_READ_TOP,
    max_read_top: int | None = MAX_MCP_RESEARCH_READ_TOP,
    default_max_search_jobs: int | None = 1,
    default_profile: str | None = "china",
) -> dict[str, Any]:
    """Normalize guarded research kwargs shared by CLI, MCP, and HTTP."""

    read_top = (
        _optional_minimum_int(payload.get("read_top"), 0)
        if max_read_top is None
        else _bounded_int(payload.get("read_top"), default_read_top or 0, 0, max_read_top)
    )
    max_search_jobs = (
        _optional_minimum_int(payload.get("max_search_jobs"), 1)
        if default_max_search_jobs is None
        else _bounded_int(payload.get("max_search_jobs"), default_max_search_jobs, 1, 4)
    )
    return {
        "query": _text(payload.get("query")),
        "preset": _text(payload.get("preset"), "general") or "general",
        "limit": _optional_bounded_int(payload.get("limit"), 1, MAX_RESEARCH_LIMIT),
        "site": _optional_text(payload.get("site")),
        "sites": _string_list(payload.get("sites")),
        "scope": _optional_text(payload.get("scope")),
        "search_backend": _text(payload.get("search_backend", payload.get("backend")), "auto") or "auto",
        "profile": _profile(payload.get("profile"), default_profile),
        "read_top": read_top,
        "read_backend": _text(payload.get("read_backend"), "auto") or "auto",
        "max_read_chars": _optional_bounded_int(payload.get("max_read_chars"), 1, 100_000),
        "advisor": _bool(payload.get("advisor")),
        "advisor_style": _text(payload.get("advisor_style"), "brief") or "brief",
        "max_search_jobs": max_search_jobs,
        "select_top": _optional_bounded_int(payload.get("select_top"), 0, 30),
        "cache_ttl": _bounded_int(payload.get("cache_ttl"), 0, 0, 86_400),
    }


def normalize_route_request(
    payload: Mapping[str, Any],
    *,
    max_read_top: int | None = 10,
    default_profile: str | None = "china",
) -> dict[str, Any]:
    """Normalize route and workflow decision kwargs."""

    preset = _text(payload.get("preset"), "general") or "general"
    return {
        "query": _text(payload.get("query")),
        "preset": None if preset == "general" else preset,
        "scope": _optional_text(payload.get("scope")),
        "site": _optional_text(payload.get("site")),
        "sites": _string_list(payload.get("sites")),
        "profile": _profile(payload.get("profile"), default_profile),
        "limit": _bounded_int(payload.get("limit"), DEFAULT_RESEARCH_LIMIT, 1, MAX_RESEARCH_LIMIT),
        "read_top": (
            _optional_minimum_int(payload.get("read_top"), 0)
            if max_read_top is None
            else _optional_bounded_int(payload.get("read_top"), 0, max_read_top)
        ),
    }


def normalize_workflow_request(
    payload: Mapping[str, Any], *, max_read_top: int | None = 10, default_profile: str | None = "china"
) -> dict[str, Any]:
    """Normalize the light/heavy workflow decision contract.

    The CLI names the current command ``workflow_command_context`` while MCP
    uses ``command``.  Keeping that presentation difference here prevents the
    decision service from drifting between the two public surfaces.
    """

    route = normalize_route_request(
        payload,
        max_read_top=max_read_top,
        default_profile=default_profile,
    )
    return {
        **route,
        "command": _text(payload.get("command", payload.get("workflow_command_context")), "search") or "search",
    }


def normalize_map_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize known-site discovery kwargs without narrowing CLI inputs.

    The service itself keeps its established conservative read cap.  This
    normalizer deliberately does not add a new hard cap to ``limit``,
    ``timeout``, or ``max_read_chars`` so existing CLI callers retain the
    behavior they had before the HTTP/MCP surfaces were aligned.
    """

    return {
        "url": _text(payload.get("url")),
        "query": _text(payload.get("query")),
        "limit": _optional_minimum_int(payload.get("limit"), 1) or DEFAULT_SEARCH_LIMIT,
        "include_subdomains": _bool(payload.get("include_subdomains")),
        "sitemap": _text(payload.get("sitemap"), "auto") or "auto",
        "include_patterns": _string_list(payload.get("include_patterns")) or [],
        "exclude_patterns": _string_list(payload.get("exclude_patterns")) or [],
        "timeout": _optional_minimum_int(payload.get("timeout"), 1) or 8,
        "read_top": _bounded_int(payload.get("read_top"), 0, 0, 5),
        "read_backend": _text(payload.get("read_backend"), "auto") or "auto",
        "max_read_chars": _optional_minimum_int(payload.get("max_read_chars"), 1) or 4_000,
    }


def normalize_daily_request(
    payload: Mapping[str, Any], *, default_profile: str | None = "china"
) -> dict[str, Any]:
    """Normalize editorial daily kwargs shared by CLI, MCP, and HTTP.

    ``build_daily_report`` remains the owner of final editorial limits.  The
    public surfaces only agree on defaults, aliases, and boolean intent here.
    """

    no_search = _bool(payload.get("no_search"))
    no_feeds = _bool(payload.get("no_feeds"))
    no_hotnews = _bool(payload.get("no_hotnews"))
    overflow_limit = _optional_minimum_int(payload.get("overflow_limit"), 0)
    return {
        "query": _text(payload.get("query")),
        "watch_id": _text(payload.get("watch_id")),
        "profile": _profile(payload.get("profile"), default_profile) or "china",
        "scope": _text(payload.get("scope")),
        "site": _text(payload.get("site")),
        "preset": _text(payload.get("preset")),
        "lens": _text(payload.get("lens")),
        "feed_source": _text(payload.get("feed_source"), "auto") or "auto",
        "watchlist_path": _text(payload.get("watchlist_path", payload.get("watchlist"))),
        "hotnews_source": _text(payload.get("hotnews_source"), "today") or "today",
        "search_backend": _text(payload.get("search_backend", payload.get("backend")), "auto") or "auto",
        "limit": _optional_minimum_int(payload.get("limit"), 1) or 12,
        "search_limit": _optional_minimum_int(payload.get("search_limit"), 1) or DEFAULT_SEARCH_LIMIT,
        "feeds_limit": _optional_minimum_int(payload.get("feeds_limit"), 1) or 20,
        "hotnews_limit": _optional_minimum_int(payload.get("hotnews_limit"), 1) or 20,
        "include_search": _bool(payload.get("include_search"), not no_search),
        "include_feeds": _bool(payload.get("include_feeds"), not no_feeds),
        "include_hotnews": _bool(payload.get("include_hotnews"), not no_hotnews),
        "cache_ttl": _bounded_int(payload.get("cache_ttl"), 0, 0, 86_400),
        "store_path": _optional_text(payload.get("store_path", payload.get("store"))),
        "read_top": _bounded_int(payload.get("read_top"), 3, 0, 3),
        "read_backend": _text(payload.get("read_backend"), "auto") or "auto",
        "max_read_chars": _optional_minimum_int(payload.get("max_read_chars"), 1) or 1_800,
        "overflow_limit": 20 if overflow_limit is None else overflow_limit,
        "time_window": _text(payload.get("time_window"), "3d") or "3d",
        "edition": _text(payload.get("edition"), "brand") or "brand",
        "record_history": _bool(payload.get("record_history")),
        "history_path": _text(payload.get("history_path")),
        "compare_days": _optional_minimum_int(payload.get("compare_days"), 0) or 0,
    }


def normalize_agent_request(
    payload: Mapping[str, Any], *, default_profile: str | None = "china"
) -> dict[str, Any]:
    """Normalize the small decision-card contract consumed by the Agent planner."""

    route = normalize_route_request(
        payload,
        max_read_top=MAX_MCP_RESEARCH_READ_TOP,
        default_profile=default_profile,
    )
    return {
        **route,
        "mode": _text(payload.get("mode"), "auto") or "auto",
        "max_commands": _bounded_int(payload.get("max_commands"), 5, 1, 12),
        "phase": _text(payload.get("phase"), "plan") or "plan",
    }
