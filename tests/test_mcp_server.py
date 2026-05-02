# -*- coding: utf-8 -*-
"""Tests for Guanlan's MCP helper surface."""

import json
from unittest.mock import patch

from guanlan import mcp_config
from guanlan.integrations import mcp_server
from guanlan.limits import (
    DEFAULT_ARCHIVE_SEARCH_LIMIT,
    DEFAULT_FEEDS_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_PULSE_LIMIT,
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    MAX_ARCHIVE_SEARCH_LIMIT,
    MAX_FEEDS_LIMIT,
    MAX_HOTNEWS_LIMIT,
    MAX_PULSE_LIMIT,
    MAX_READ_FALLBACK_LIMIT,
    MAX_RESEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
)


def test_mcp_tool_definitions_include_agent_search_tools():
    tools = mcp_server._tool_definitions()
    names = {tool["name"] for tool in tools}

    assert "guanlan_status" in names
    assert "guanlan_capabilities" in names
    assert "guanlan_search" in names
    assert "guanlan_route" in names
    assert "guanlan_read" in names
    assert "guanlan_research" in names
    assert "guanlan_compare" in names
    assert "guanlan_timeline" in names
    assert "guanlan_dossier" in names
    assert "guanlan_hotnews" in names
    assert "guanlan_pulse" in names
    assert "guanlan_feeds" in names
    assert "guanlan_archive_search" in names
    research_tool = next(tool for tool in tools if tool["name"] == "guanlan_research")
    capabilities_tool = next(tool for tool in tools if tool["name"] == "guanlan_capabilities")
    hotnews_tool = next(tool for tool in tools if tool["name"] == "guanlan_hotnews")
    assert "what Guanlan can do" in capabilities_tool["description"]
    assert "format" in capabilities_tool["inputSchema"]["properties"]
    assert "advisor" in research_tool["inputSchema"]["properties"]
    assert "advisor=true" in research_tool["description"]
    assert "writing rules" in research_tool["description"]
    assert "助理视角规则" in research_tool["inputSchema"]["properties"]["advisor"]["description"]
    assert "backend" in hotnews_tool["inputSchema"]["properties"]
    assert "newsnow_base_url" in hotnews_tool["inputSchema"]["properties"]
    search_tool = next(tool for tool in tools if tool["name"] == "guanlan_search")
    route_tool = next(tool for tool in tools if tool["name"] == "guanlan_route")
    assert "evidence roles" in route_tool["description"]
    assert "prompt" in search_tool["inputSchema"]["properties"]["format"]["enum"]
    assert "prompt" in research_tool["inputSchema"]["properties"]["format"]["enum"]
    compare_tool = next(tool for tool in tools if tool["name"] == "guanlan_compare")
    timeline_tool = next(tool for tool in tools if tool["name"] == "guanlan_timeline")
    dossier_tool = next(tool for tool in tools if tool["name"] == "guanlan_dossier")
    assert compare_tool["inputSchema"]["properties"]["subjects"]["minItems"] == 2
    assert "max_events" in timeline_tool["inputSchema"]["properties"]
    assert "source mix" in dossier_tool["description"]


def test_mcp_config_outputs_copyable_server_config():
    config = mcp_config.build_mcp_config(client="claude", command="guanlan-mcp")

    assert config["mcpServers"]["guanlan"]["command"] == "guanlan-mcp"
    assert config["mcpServers"]["guanlan"]["args"] == []
    md = mcp_config.format_mcp_config_markdown(client="codex")
    assert "Guanlan MCP 配置" in md
    assert "guanlan-mcp" in md


def test_mcp_config_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "mcp", "config", "--format", "json"]):
        main()

    captured = capsys.readouterr()
    config = json.loads(captured.out)
    assert config["mcpServers"]["guanlan"]["command"] == "guanlan-mcp"


def test_mcp_tool_definitions_use_expanded_limits():
    tools = {tool["name"]: tool for tool in mcp_server._tool_definitions()}

    search_limit = tools["guanlan_search"]["inputSchema"]["properties"]["limit"]
    read_fallback = tools["guanlan_read"]["inputSchema"]["properties"]["fallback_limit"]
    research_limit = tools["guanlan_research"]["inputSchema"]["properties"]["limit"]
    route_limit = tools["guanlan_route"]["inputSchema"]["properties"]["limit"]
    hotnews_limit = tools["guanlan_hotnews"]["inputSchema"]["properties"]["limit"]
    pulse_limit = tools["guanlan_pulse"]["inputSchema"]["properties"]["limit"]
    feeds_limit = tools["guanlan_feeds"]["inputSchema"]["properties"]["limit"]
    archive_limit = tools["guanlan_archive_search"]["inputSchema"]["properties"]["limit"]
    archive_trace = tools["guanlan_archive_search"]["inputSchema"]["properties"]["trace"]

    assert search_limit == {"type": "integer", "default": DEFAULT_SEARCH_LIMIT, "minimum": 1, "maximum": MAX_SEARCH_LIMIT}
    assert read_fallback == {
        "type": "integer",
        "default": DEFAULT_READ_FALLBACK_LIMIT,
        "minimum": 1,
        "maximum": MAX_READ_FALLBACK_LIMIT,
    }
    assert research_limit == {
        "type": "integer",
        "default": DEFAULT_RESEARCH_LIMIT,
        "minimum": 1,
        "maximum": MAX_RESEARCH_LIMIT,
    }
    assert route_limit == {
        "type": "integer",
        "default": DEFAULT_RESEARCH_LIMIT,
        "minimum": 1,
        "maximum": MAX_RESEARCH_LIMIT,
    }
    assert hotnews_limit == {
        "type": "integer",
        "default": DEFAULT_HOTNEWS_LIMIT,
        "minimum": 1,
        "maximum": MAX_HOTNEWS_LIMIT,
    }
    assert pulse_limit == {
        "type": "integer",
        "default": DEFAULT_PULSE_LIMIT,
        "minimum": 1,
        "maximum": MAX_PULSE_LIMIT,
    }
    assert feeds_limit == {
        "type": "integer",
        "default": DEFAULT_FEEDS_LIMIT,
        "minimum": 1,
        "maximum": MAX_FEEDS_LIMIT,
    }
    assert archive_limit == {
        "type": "integer",
        "default": DEFAULT_ARCHIVE_SEARCH_LIMIT,
        "minimum": 1,
        "maximum": MAX_ARCHIVE_SEARCH_LIMIT,
    }
    assert archive_trace["type"] == "boolean"


def test_mcp_search_context_uses_webtools(monkeypatch):
    calls = []

    def fake_search_web(*_args, **_kwargs):
        calls.append(_kwargs)
        return [
            {
                "title": "政策原文",
                "url": "https://www.gov.cn/a",
                "snippet": "公开来源",
                "source_type": "政府/部委",
                "score": 10.0,
                "topic_key": "policy",
                "topic_role": "single",
            }
        ]

    monkeypatch.setattr("guanlan.webtools.search_web", fake_search_web)

    text = mcp_server._run_tool(
        "guanlan_search",
        {"query": "人工智能 政策", "format": "context", "profile": "china"},
    )

    assert "观澜搜索上下文" in text
    assert "政策原文" in text
    assert calls[0]["limit"] == DEFAULT_SEARCH_LIMIT


def test_mcp_read_uses_webtools(monkeypatch):
    calls = []

    def fake_read_url(*_args, **kwargs):
        calls.append(kwargs)
        return "# Article"

    monkeypatch.setattr("guanlan.webtools.read_url", fake_read_url)

    text = mcp_server._run_tool("guanlan_read", {"url": "https://example.com"})

    assert text == "# Article"
    assert calls[0]["fallback_limit"] == DEFAULT_READ_FALLBACK_LIMIT


def test_mcp_route_explains_source_plan():
    text = mcp_server._run_tool(
        "guanlan_route",
        {"query": "某产品 用户评价 值不值得买", "format": "markdown"},
    )

    assert "观澜路由计划" in text
    assert "reputation" in text
    assert "purchase_advice" in text
    assert "social_web" in text


def test_mcp_capabilities_explains_entrypoints():
    text = mcp_server._run_tool("guanlan_capabilities", {})

    assert "观澜能力地图" in text
    assert "能力发现" in text
    assert "guanlan search" in text
    assert "助理视角" in text


def test_mcp_capabilities_can_return_json():
    payload = mcp_server._run_tool("guanlan_capabilities", {"format": "json"})

    ids = {item["id"] for item in payload}
    assert "discover" in ids
    assert "hotnews" in ids


def test_mcp_archive_search_uses_archive(monkeypatch):
    calls = []

    def fake_search_documents(*_args, **kwargs):
        calls.append(kwargs)
        return [
            {
                "title": "本地材料",
                "url": "https://example.com/a",
                "domain": "example.com",
                "excerpt": "归档正文",
            }
        ]

    monkeypatch.setattr(
        "guanlan.archive.search_documents",
        fake_search_documents,
    )

    text = mcp_server._run_tool("guanlan_archive_search", {"query": "材料", "format": "context", "trace": True})

    assert "观澜本地知识库上下文" in text
    assert "本地材料" in text
    assert calls[0]["limit"] == DEFAULT_ARCHIVE_SEARCH_LIMIT
    assert calls[0]["trace"] is True


def test_mcp_pulse_uses_pulse(monkeypatch):
    monkeypatch.setattr(
        "guanlan.pulse.build_pulse_report",
        lambda *_args, **_kwargs: {
            "query": "某产品",
            "tendency": "偏负向",
            "confidence": "低",
            "sample_count": 1,
            "read_success": 0,
            "positive_terms": [],
            "negative_terms": [{"term": "吐槽", "count": 1}],
            "controversy_terms": [{"term": "争议", "count": 1}],
            "samples": [
                {
                    "source_type": "社交/内容平台",
                    "title": "用户吐槽",
                    "url": "https://example.com/a",
                    "snippet": "争议",
                    "stance": "negative",
                }
            ],
        },
    )

    text = mcp_server._run_tool("guanlan_pulse", {"query": "某产品", "format": "context"})

    assert "观澜回响上下文" in text
    assert "偏负向" in text


def test_mcp_research_workflow_tools(monkeypatch):
    monkeypatch.setattr(
        "guanlan.research_workflows.build_compare_report",
        lambda subjects, **_kwargs: {"mode": "compare", "subjects": subjects, "comparison_table": []},
    )
    monkeypatch.setattr(
        "guanlan.research_workflows.build_timeline_report",
        lambda query, **_kwargs: {"mode": "timeline", "query": query, "events": [], "boundary": "边界"},
    )
    monkeypatch.setattr(
        "guanlan.research_workflows.build_dossier_report",
        lambda entity, **_kwargs: {
            "mode": "dossier",
            "entity": entity,
            "query": entity,
            "sections": [],
            "suggested_next": [],
            "boundary": "边界",
        },
    )

    compare = mcp_server._run_tool("guanlan_compare", {"subjects": ["A", "B"], "format": "json"})
    timeline = mcp_server._run_tool("guanlan_timeline", {"query": "AI 眼镜", "format": "markdown"})
    dossier = mcp_server._run_tool("guanlan_dossier", {"entity": "某公司", "format": "context"})

    assert compare["subjects"] == ["A", "B"]
    assert "观澜时间线" in timeline
    assert "观澜研究档案" in dossier


def test_mcp_feeds_uses_curated(monkeypatch):
    monkeypatch.setattr(
        "guanlan.feeds.fetch_feed_source",
        lambda *_args, **_kwargs: [
            {
                "title": "高分 AI 文章",
                "url": "https://example.com/a",
                "source_title": "精品内容流",
                "summary": "值得读",
            }
        ],
    )

    text = mcp_server._run_tool(
        "guanlan_feeds",
        {"source": "curated", "category": "ai", "format": "context"},
    )

    assert "观澜内容发现 / 精品内容流 上下文" in text
    assert "高分 AI 文章" in text


def test_mcp_hotnews_json_can_return_compact_brief(monkeypatch):
    monkeypatch.setattr(
        "guanlan.hotnews.fetch_hotnews",
        lambda *_args, **_kwargs: [
            {"rank": 1, "source_id": "baidu", "title": "AI 热点", "url": "https://example.com/a"}
        ],
    )

    payload = mcp_server._run_tool(
        "guanlan_hotnews",
        {"source": "today", "format": "json", "compact": True, "brief": True},
    )

    assert set(payload) == {"items", "brief"}
    assert payload["items"][0]["evidence_role"] == "fresh_trend_signal"
    assert payload["brief"]["sample_count"] == 1


def test_mcp_feeds_json_can_return_compact_rows(monkeypatch):
    monkeypatch.setattr(
        "guanlan.feeds.fetch_feed_source",
        lambda *_args, **_kwargs: [
            {
                "title": "高分 AI 文章",
                "url": "https://example.com/a",
                "source_id": "curated",
                "source_title": "精品内容流",
                "summary": "值得读",
                "evidence_role": "reading_discovery_signal",
            }
        ],
    )

    payload = mcp_server._run_tool("guanlan_feeds", {"source": "curated", "format": "json", "compact": True})

    assert payload[0]["title"] == "高分 AI 文章"
    assert payload[0]["evidence_role"] == "reading_discovery_signal"


def test_mcp_feeds_lists_curated_sources(monkeypatch):
    monkeypatch.setattr(
        "guanlan.feeds.list_curated_sources",
        lambda **_kwargs: [{"title": "LangChain Blog", "url": "https://blog.langchain.dev/rss/"}],
    )

    text = mcp_server._run_tool("guanlan_feeds", {"source": "curated-sources"})

    assert "观澜 RSS 源目录 / 精品源" in text
    assert "LangChain Blog" in text


def test_mcp_feeds_lists_source_routing():
    text = mcp_server._run_tool("guanlan_feeds", {"source": "list"})

    assert "观澜 RSS 信源路由" in text
    assert "baidu-rss" in text
