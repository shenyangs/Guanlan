# -*- coding: utf-8 -*-
"""Tests for Guanlan's MCP helper surface."""

from guanlan.integrations import mcp_server


def test_mcp_tool_definitions_include_agent_search_tools():
    tools = mcp_server._tool_definitions()
    names = {tool["name"] for tool in tools}

    assert "guanlan_status" in names
    assert "guanlan_search" in names
    assert "guanlan_read" in names
    assert "guanlan_research" in names
    assert "guanlan_hotnews" in names
    assert "guanlan_pulse" in names
    assert "guanlan_archive_search" in names
    research_tool = next(tool for tool in tools if tool["name"] == "guanlan_research")
    hotnews_tool = next(tool for tool in tools if tool["name"] == "guanlan_hotnews")
    assert "advisor" in research_tool["inputSchema"]["properties"]
    assert "backend" in hotnews_tool["inputSchema"]["properties"]
    assert "newsnow_base_url" in hotnews_tool["inputSchema"]["properties"]


def test_mcp_search_context_uses_webtools(monkeypatch):
    def fake_search_web(*_args, **_kwargs):
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


def test_mcp_read_uses_webtools(monkeypatch):
    monkeypatch.setattr("guanlan.webtools.read_url", lambda *_args, **_kwargs: "# Article")

    text = mcp_server._run_tool("guanlan_read", {"url": "https://example.com"})

    assert text == "# Article"


def test_mcp_archive_search_uses_archive(monkeypatch):
    monkeypatch.setattr(
        "guanlan.archive.search_documents",
        lambda *_args, **_kwargs: [
            {
                "title": "本地材料",
                "url": "https://example.com/a",
                "domain": "example.com",
                "excerpt": "归档正文",
            }
        ],
    )

    text = mcp_server._run_tool("guanlan_archive_search", {"query": "材料", "format": "context"})

    assert "观澜本地知识库上下文" in text
    assert "本地材料" in text


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
