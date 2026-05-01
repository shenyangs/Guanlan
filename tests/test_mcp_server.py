# -*- coding: utf-8 -*-
"""Tests for Guanlan's MCP helper surface."""

from guanlan.integrations import mcp_server


def test_mcp_tool_definitions_include_agent_search_tools():
    names = {tool["name"] for tool in mcp_server._tool_definitions()}

    assert "guanlan_status" in names
    assert "guanlan_search" in names
    assert "guanlan_read" in names
    assert "guanlan_research" in names
    assert "guanlan_hotnews" in names


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
