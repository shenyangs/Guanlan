# -*- coding: utf-8 -*-
"""Contract tests for shared CLI/MCP/HTTP request normalization."""

from guanlan.limits import DEFAULT_READ_FALLBACK_LIMIT, MAX_MCP_RESEARCH_READ_TOP
from guanlan.tool_invocation import (
    normalize_agent_request,
    normalize_daily_request,
    normalize_map_request,
    normalize_read_request,
    normalize_research_request,
    normalize_route_request,
    normalize_search_request,
    normalize_workflow_request,
)


def test_search_normalization_preserves_quality_and_cache_controls():
    request = normalize_search_request(
        {
            "query": "WPS AI",
            "strict_scope": True,
            "cache_ttl": "3600",
            "network": "direct",
            "no_cache": True,
        }
    )

    assert request["strict_scope"] is True
    assert request["cache_ttl"] == 3600
    assert request["network_mode"] == "direct"
    assert request["use_cache"] is False


def test_search_normalization_accepts_max_results_compatibility_alias():
    alias_only = normalize_search_request({"query": "WPS AI", "max_results": 8})
    canonical_wins = normalize_search_request({"query": "WPS AI", "limit": 12, "max_results": 8})

    assert alias_only["limit"] == 8
    assert canonical_wins["limit"] == 12


def test_read_normalization_keeps_fallback_and_cache_contract():
    request = normalize_read_request(
        {"url": "https://example.com", "fallback_limit": "999", "cache_ttl": "60", "strict": True}
    )

    assert request["fallback_limit"] == DEFAULT_READ_FALLBACK_LIMIT
    assert request["cache_ttl"] == 60
    assert request["strict"] is True


def test_read_normalization_keeps_jina_controls_opt_in_and_bounded():
    default_request = normalize_read_request({"url": "https://example.com"})
    controlled = normalize_read_request(
        {
            "url": "https://example.com",
            "no_cache": True,
            "jina_engine": "browser",
            "jina_format": "frontmatter",
            "jina_wait_for": "article",
            "jina_target": "article",
            "jina_remove": "nav, footer",
            "jina_repair": False,
        }
    )

    assert default_request["upstream_no_cache"] is False
    assert default_request["jina_engine"] == "auto"
    assert default_request["jina_format"] == "content"
    assert default_request["jina_repair"] is True
    assert controlled["use_cache"] is False
    assert controlled["upstream_no_cache"] is True
    assert controlled["jina_engine"] == "browser"
    assert controlled["jina_format"] == "frontmatter"
    assert controlled["jina_wait_for"] == "article"
    assert controlled["jina_repair"] is False


def test_read_no_cache_overrides_conflicting_cache_flags():
    request = normalize_read_request(
        {
            "url": "https://example.com",
            "no_cache": True,
            "use_cache": True,
            "upstream_no_cache": False,
        }
    )

    assert request["use_cache"] is False
    assert request["upstream_no_cache"] is True


def test_research_normalization_guards_heavy_knobs_without_dropping_options():
    request = normalize_research_request(
        {
            "query": "政策差异",
            "read_top": 99,
            "max_search_jobs": 3,
            "advisor_style": "risk",
            "select_top": 8,
            "cache_ttl": 600,
        }
    )

    assert request["read_top"] == MAX_MCP_RESEARCH_READ_TOP
    assert request["max_search_jobs"] == 3
    assert request["advisor_style"] == "risk"
    assert request["select_top"] == 8
    assert request["cache_ttl"] == 600


def test_research_normalization_accepts_explicit_read_top_above_agent_default():
    request = normalize_research_request({"query": "三家车企对比", "read_top": 3})

    assert request["read_top"] == 3


def test_route_and_agent_normalization_share_site_and_preset_rules():
    route = normalize_route_request({"query": "AI", "preset": "general", "sites": "gov.cn, cas.cn"})
    agent = normalize_agent_request({"query": "AI", "preset": "general", "sites": "gov.cn, cas.cn"})

    assert route["preset"] is None
    assert route["sites"] == ["gov.cn", "cas.cn"]
    assert agent["sites"] == route["sites"]


def test_workflow_normalization_unifies_cli_and_mcp_command_names():
    cli = normalize_workflow_request(
        {"query": "WPS AI", "workflow_command_context": "research", "read_top": 99}
    )
    mcp = normalize_workflow_request({"query": "WPS AI", "command": "research", "read_top": 99})

    assert cli == mcp
    assert cli["command"] == "research"
    assert cli["read_top"] == 10


def test_workflow_cli_can_preserve_an_explicit_read_count_without_mcp_capping():
    request = normalize_workflow_request(
        {"query": "WPS AI", "workflow_command_context": "research", "read_top": 15},
        max_read_top=None,
    )

    assert request["read_top"] == 15


def test_map_normalization_preserves_repeated_patterns_and_read_cap():
    request = normalize_map_request(
        {
            "url": "https://example.com",
            "include_patterns": ["/docs", "api"],
            "exclude_patterns": "login,preview",
            "read_top": 99,
        }
    )

    assert request["include_patterns"] == ["/docs", "api"]
    assert request["exclude_patterns"] == ["login", "preview"]
    assert request["read_top"] == 5


def test_daily_normalization_keeps_explicit_skip_and_history_contracts():
    request = normalize_daily_request(
        {
            "query": "WPS AI",
            "no_feeds": True,
            "include_hotnews": False,
            "watchlist": "daily.json",
            "read_top": 99,
            "compare_days": "7",
        }
    )

    assert request["include_search"] is True
    assert request["include_feeds"] is False
    assert request["include_hotnews"] is False
    assert request["watchlist_path"] == "daily.json"
    assert request["read_top"] == 3
    assert request["compare_days"] == 7
