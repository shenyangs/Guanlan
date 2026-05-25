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
    DEFAULT_MCP_RESEARCH_READ_TOP,
    DEFAULT_PULSE_LIMIT,
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    MAX_ARCHIVE_SEARCH_LIMIT,
    MAX_FEEDS_LIMIT,
    MAX_HOTNEWS_LIMIT,
    MAX_MCP_RESEARCH_READ_TOP,
    MAX_PULSE_LIMIT,
    MAX_READ_FALLBACK_LIMIT,
    MAX_RESEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
)
from guanlan.tool_registry import core_agent_tool_names


def test_mcp_tool_definitions_include_agent_search_tools():
    tools = mcp_server._tool_definitions()
    names = {tool["name"] for tool in tools}

    assert core_agent_tool_names() <= names
    assert "guanlan_status" in names
    assert "guanlan_capabilities" in names
    assert "guanlan_agent" in names
    assert "guanlan_search" in names
    assert "guanlan_stock" in names
    assert "guanlan_route" in names
    assert "guanlan_workflow" in names
    assert "guanlan_page_diagnose" in names
    assert "guanlan_browser_assist_plan" in names
    assert "guanlan_recipe" in names
    assert "guanlan_read" in names
    assert "guanlan_research" in names
    assert "guanlan_investigate" in names
    assert "guanlan_compare" in names
    assert "guanlan_timeline" in names
    assert "guanlan_dossier" in names
    assert "guanlan_hotnews" in names
    assert "guanlan_pulse" in names
    assert "guanlan_feeds" in names
    assert "guanlan_daily" in names
    assert "guanlan_archive_search" in names
    assert "guanlan_archive_context" in names
    assert "guanlan_archive_verify" in names
    research_tool = next(tool for tool in tools if tool["name"] == "guanlan_research")
    capabilities_tool = next(tool for tool in tools if tool["name"] == "guanlan_capabilities")
    hotnews_tool = next(tool for tool in tools if tool["name"] == "guanlan_hotnews")
    daily_tool = next(tool for tool in tools if tool["name"] == "guanlan_daily")
    assert "what Guanlan can do" in capabilities_tool["description"]
    assert "format" in capabilities_tool["inputSchema"]["properties"]
    assert "advisor" in research_tool["inputSchema"]["properties"]
    assert "advisor=true" in research_tool["description"]
    assert "writing rules" in research_tool["description"]
    assert "180-300 seconds" in research_tool["description"]
    assert "300000 ms" in research_tool["description"]
    assert "助理视角规则" in research_tool["inputSchema"]["properties"]["advisor"]["description"]
    assert "backend" in hotnews_tool["inputSchema"]["properties"]
    assert "newsnow_base_url" in hotnews_tool["inputSchema"]["properties"]
    assert "watch_id" in daily_tool["inputSchema"]["properties"]
    assert "time_window" in daily_tool["inputSchema"]["properties"]
    assert "html" in daily_tool["inputSchema"]["properties"]["format"]["enum"]
    assert "im" in daily_tool["inputSchema"]["properties"]["format"]["enum"]
    assert "daily brief" in daily_tool["description"]
    search_tool = next(tool for tool in tools if tool["name"] == "guanlan_search")
    agent_tool = next(tool for tool in tools if tool["name"] == "guanlan_agent")
    stock_tool = next(tool for tool in tools if tool["name"] == "guanlan_stock")
    route_tool = next(tool for tool in tools if tool["name"] == "guanlan_route")
    workflow_tool = next(tool for tool in tools if tool["name"] == "guanlan_workflow")
    diagnose_tool = next(tool for tool in tools if tool["name"] == "guanlan_page_diagnose")
    browser_assist_tool = next(tool for tool in tools if tool["name"] == "guanlan_browser_assist_plan")
    browser_assist_run_tool = next(tool for tool in tools if tool["name"] == "guanlan_browser_assist_run")
    feeds_tool = next(tool for tool in tools if tool["name"] == "guanlan_feeds")
    recipe_tool = next(tool for tool in tools if tool["name"] == "guanlan_recipe")
    investigate_tool = next(tool for tool in tools if tool["name"] == "guanlan_investigate")
    assert "evidence roles" in route_tool["description"]
    assert "avoid overthinking basic" in workflow_tool["description"]
    assert "dynamic shell" in diagnose_tool["description"]
    assert "OpenGuanlan visible-page evidence task" in browser_assist_tool["description"]
    assert "format" in browser_assist_tool["inputSchema"]["properties"]
    assert "min_visible_items" in browser_assist_tool["inputSchema"]["properties"]
    assert "min_visible_items" in browser_assist_run_tool["inputSchema"]["properties"]
    assert "watchlist" in feeds_tool["inputSchema"]["properties"]
    assert "watchlist_path" in feeds_tool["inputSchema"]["properties"]
    assert "stable multi-step workflow" in recipe_tool["description"]
    assert "workflow_decision" in investigate_tool["description"]
    assert "prompt" in search_tool["inputSchema"]["properties"]["format"]["enum"]
    assert "cache_ttl=3600" in search_tool["description"]
    assert "do not shrink the evidence pool" in search_tool["description"]
    assert "primary_command" in agent_tool["description"]
    assert "mode" in agent_tool["inputSchema"]["properties"]
    assert "dynamic finance pages" in stock_tool["description"]
    assert "stocks" in stock_tool["description"]
    assert "plan" in stock_tool["inputSchema"]["properties"]["command"]["enum"]
    assert "detail" in stock_tool["inputSchema"]["properties"]["command"]["enum"]
    assert "prompt" in research_tool["inputSchema"]["properties"]["format"]["enum"]
    compare_tool = next(tool for tool in tools if tool["name"] == "guanlan_compare")
    timeline_tool = next(tool for tool in tools if tool["name"] == "guanlan_timeline")
    dossier_tool = next(tool for tool in tools if tool["name"] == "guanlan_dossier")
    assert compare_tool["inputSchema"]["properties"]["subjects"]["minItems"] == 2
    assert "max_events" in timeline_tool["inputSchema"]["properties"]
    assert "source mix" in dossier_tool["description"]
    archive_search_tool = next(tool for tool in tools if tool["name"] == "guanlan_archive_search")
    archive_context_tool = next(tool for tool in tools if tool["name"] == "guanlan_archive_context")
    archive_verify_tool = next(tool for tool in tools if tool["name"] == "guanlan_archive_verify")
    assert "local memory layer" in archive_search_tool["description"]
    assert "RAG/local-model/Agent Wiki" in archive_search_tool["description"]
    assert "prompt-ready context" in archive_context_tool["description"]
    assert "sample recall" in archive_verify_tool["description"]


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
    research_read_top = tools["guanlan_research"]["inputSchema"]["properties"]["read_top"]
    route_limit = tools["guanlan_route"]["inputSchema"]["properties"]["limit"]
    hotnews_limit = tools["guanlan_hotnews"]["inputSchema"]["properties"]["limit"]
    pulse_limit = tools["guanlan_pulse"]["inputSchema"]["properties"]["limit"]
    feeds_limit = tools["guanlan_feeds"]["inputSchema"]["properties"]["limit"]
    archive_limit = tools["guanlan_archive_search"]["inputSchema"]["properties"]["limit"]
    archive_trace = tools["guanlan_archive_search"]["inputSchema"]["properties"]["trace"]
    archive_context_limit = tools["guanlan_archive_context"]["inputSchema"]["properties"]["limit"]

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
    assert research_read_top["default"] == DEFAULT_MCP_RESEARCH_READ_TOP
    assert research_read_top["minimum"] == 0
    assert research_read_top["maximum"] == MAX_MCP_RESEARCH_READ_TOP
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
    assert archive_context_limit == {
        "type": "integer",
        "default": 20,
        "minimum": 1,
        "maximum": MAX_ARCHIVE_SEARCH_LIMIT,
    }


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

    monkeypatch.setattr("guanlan.web.search.search_web", fake_search_web)

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

    monkeypatch.setattr("guanlan.web.read.read_url", fake_read_url)

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
    assert "观澜工作流分流" in text


def test_mcp_workflow_keeps_basic_search_light():
    payload = mcp_server._run_tool("guanlan_workflow", {"query": "观澜 官网", "format": "json"})

    assert payload["tier"] == "direct"
    assert payload["recommended_entrypoint"] == "search"
    assert payload["do_not_overthink"] is True


def test_mcp_agent_returns_low_choice_plan():
    payload = mcp_server._run_tool(
        "guanlan_agent",
        {"query": "WPS AI 灵犀 最近热点", "mode": "fresh", "format": "json"},
    )
    commands = [item["command"] for item in payload["agent_next_steps"]]

    assert payload["primary_command"] == "guanlan hotnews today --limit 80 --trends"
    assert "guanlan hotnews today --limit 80 --trends" in commands
    assert "guanlan feeds curated --category ai --limit 80" in commands
    assert any("--scope wps_office" in command for command in commands)
    assert not any(command.startswith("guanlan research") for command in commands)


def test_mcp_research_is_guarded_and_clamps_heavy_knobs(monkeypatch):
    calls = []

    def fake_build_research_packet(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"query": args[0], "results": [], "readings": []}

    monkeypatch.setattr("guanlan.web.research.build_research_packet", fake_build_research_packet)

    payload = mcp_server._run_tool(
        "guanlan_research",
        {"query": "政策差异", "read_top": 8, "format": "json"},
    )

    assert payload["query"] == "政策差异"
    assert calls[0]["kwargs"]["read_top"] == MAX_MCP_RESEARCH_READ_TOP
    assert calls[0]["kwargs"]["max_search_jobs"] == 1


def test_mcp_investigate_uses_investigation_module(monkeypatch):
    monkeypatch.setattr(
        "guanlan.investigation.build_investigation_packet",
        lambda query, **_kwargs: {
            "query": query,
            "selected_evidence": [],
            "workflow_decision": {"tier": "investigate", "query": query},
            "investigation": {"principle": "先取证", "next_views": []},
        },
    )

    payload = mcp_server._run_tool("guanlan_investigate", {"query": "某公司 风险", "format": "json"})

    assert payload["workflow_decision"]["tier"] == "investigate"


def test_mcp_page_diagnose_uses_diagnosis_module(monkeypatch):
    monkeypatch.setattr(
        "guanlan.page_diagnosis.diagnose_page",
        lambda url, **_kwargs: {
            "url": url,
            "page_type": "dynamic_shell",
            "usable_as_evidence": False,
        },
    )

    payload = mcp_server._run_tool("guanlan_page_diagnose", {"url": "https://example.com", "format": "json"})

    assert payload["page_type"] == "dynamic_shell"


def test_mcp_browser_assist_plan_returns_task():
    payload = mcp_server._run_tool(
        "guanlan_browser_assist_plan",
        {
            "url": "https://www.xiaohongshu.com/explore/demo",
            "signals": ["access_gate"],
            "min_visible_items": 12,
            "format": "json",
        },
    )

    assert payload["recommended"] is True
    assert payload["browser_assist_task"]["read_only"] is True
    assert payload["browser_assist_task"]["status"] == "requires_user_approval"
    assert payload["browser_assist_task"]["host_browser_contract"]["uses_existing_browser_session"] is True
    assert payload["browser_assist_task"]["sufficiency_contract"]["requested_min_items"] == 12
    assert "read_cookies" in payload["browser_assist_task"]["forbidden_actions"]


def test_mcp_recipe_renders_plan():
    payload = mcp_server._run_tool(
        "guanlan_recipe",
        {"command": "run", "recipe_id": "finance-risk", "query": "宁德时代 股价 财报", "format": "json"},
    )

    assert payload["recipe"]["id"] == "finance-risk"
    assert any("guanlan stock detail" in command for command in payload["commands"])


def test_mcp_capabilities_explains_entrypoints():
    text = mcp_server._run_tool("guanlan_capabilities", {})

    assert "观澜能力地图" in text
    assert "能力发现" in text
    assert "guanlan search" in text
    assert "助理视角" in text
    assert "页面诊断" in text


def test_mcp_capabilities_can_return_json():
    payload = mcp_server._run_tool("guanlan_capabilities", {"format": "json"})

    ids = {item["id"] for item in payload}
    assert "discover" in ids
    assert "hotnews" in ids
    assert "daily" in ids


def test_mcp_daily_runs_report(monkeypatch):
    monkeypatch.setattr(
        "guanlan.daily.build_daily_report",
        lambda *args, **kwargs: {"title": "测试日报", "items": [], "candidate_count": 0, "item_count": 0},
    )

    payload = mcp_server._run_tool("guanlan_daily", {"query": "AI 行业", "format": "json"})

    assert payload["title"] == "测试日报"


def test_mcp_stock_tool_returns_markdown(monkeypatch):
    monkeypatch.setattr(
        "guanlan.stock_cli.run_stock_tool",
        lambda args: "# 观澜行情\n\n- 名称: 贵州茅台",
    )

    text = mcp_server._run_tool("guanlan_stock", {"command": "quote", "target": "600519"})

    assert "观澜行情" in text
    assert "贵州茅台" in text


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


def test_mcp_archive_context_guides_local_model(monkeypatch):
    calls = []

    def fake_context(*_args, **kwargs):
        calls.append(kwargs)
        return {"context": "# Guanlan Local Archive Context\n\nAgent Wiki", "records": []}

    monkeypatch.setattr("guanlan.archive_wiki.build_archive_wiki_context", fake_context)

    text = mcp_server._run_tool("guanlan_archive_context", {"query": "Agent Wiki", "limit": 20})

    assert "Local Archive Context" in text
    assert calls[0]["limit"] == 20


def test_mcp_archive_verify_explains_memory_readiness(monkeypatch):
    monkeypatch.setattr(
        "guanlan.archive.verify_archive",
        lambda **_kwargs: {
            "status": "ok",
            "path": "/tmp/archive.db",
            "documents": 1,
            "issues": [],
            "checks": {"sample_recall": "ok"},
            "quality": {"rag_ready": 1, "documents": 1, "average_read_quality": 80, "low_quality": 0},
            "next_steps": ["Archive 基础检索和导出状态正常。"],
        },
    )

    text = mcp_server._run_tool("guanlan_archive_verify", {})

    assert "本地知识库体检" in text
    assert "Agent 提示" in text


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
    seen = {}

    def fake_fetch(*_args, **kwargs):
        seen.update(kwargs)
        return [
            {
                "title": "高分 AI 文章",
                "url": "https://example.com/a",
                "source_id": "curated",
                "source_title": "精品内容流",
                "summary": "值得读",
                "evidence_role": "reading_discovery_signal",
            }
        ]

    monkeypatch.setattr(
        "guanlan.feeds.fetch_feed_source",
        fake_fetch,
    )

    payload = mcp_server._run_tool(
        "guanlan_feeds",
        {
            "source": "curated",
            "format": "json",
            "compact": True,
            "watchlist_path": "/tmp/feeds.json",
        },
    )

    assert payload[0]["title"] == "高分 AI 文章"
    assert payload[0]["evidence_role"] == "reading_discovery_signal"
    assert seen["watchlist_path"] == "/tmp/feeds.json"


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
