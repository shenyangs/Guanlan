# -*- coding: utf-8 -*-
"""Tests for public site URL discovery."""

from __future__ import annotations

import json
from unittest.mock import patch

from guanlan.site_map import build_site_map, format_site_map_context, format_site_map_markdown


def test_build_site_map_collects_sitemap_and_page_links(monkeypatch):
    pages = {
        "https://example.com/robots.txt": "User-agent: *\nSitemap: https://example.com/sitemap.xml\n",
        "https://example.com/sitemap.xml": """<?xml version="1.0"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://example.com/pricing</loc><lastmod>2026-06-01</lastmod></url>
              <url><loc>https://example.com/docs/api</loc></url>
              <url><loc>https://blog.example.com/docs/post</loc></url>
            </urlset>
        """,
        "https://example.com/": """
            <html><body>
              <a href="/docs">Docs</a>
              <a href="/contact" title="Contact">联系</a>
              <a href="https://outside.example/docs">Outside</a>
            </body></html>
        """,
    }

    def fake_fetch(url: str, *, timeout: int = 8) -> str:
        return pages[url]

    monkeypatch.setattr("guanlan.site_map._fetch_text", fake_fetch)

    packet = build_site_map("example.com", query="docs", limit=10)
    urls = [item["url"] for item in packet["links"]]

    assert packet["schema_version"] == "site_map_v1"
    assert "https://example.com/docs/api" in urls
    assert "https://example.com/docs" in urls
    assert "https://example.com/pricing" not in urls
    assert "https://blog.example.com/docs/post" not in urls
    assert all("guanlan read" in item["read_command"] for item in packet["links"])
    assert packet["agent_followup"]["should_answer"] is False


def test_build_site_map_read_top_adds_quality_readings(monkeypatch):
    pages = {
        "https://example.com/robots.txt": "User-agent: *\nSitemap: https://example.com/sitemap.xml\n",
        "https://example.com/sitemap.xml": """<?xml version="1.0"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://example.com/docs/api</loc></url>
              <url><loc>https://example.com/pricing</loc></url>
            </urlset>
        """,
        "https://example.com/": "<html><body></body></html>",
    }

    def fake_fetch(url: str, *, timeout: int = 8) -> str:
        return pages[url]

    def fake_read(url: str, **kwargs):
        return {
            "url": url,
            "content": f"# {url}\n这是一个可引用的公开页面正文，包含足够连续文本用于站内入口验证。",
            "quality_report": {
                "usable": True,
                "score": 88,
                "label": "clean",
                "chars": 240,
                "selected_backend": kwargs["backend"],
            },
            "trace": {"selected_backend": kwargs["backend"]},
        }

    monkeypatch.setattr("guanlan.site_map._fetch_text", fake_fetch)
    monkeypatch.setattr("guanlan.web.read.read_url_with_trace", fake_read)

    packet = build_site_map(
        "example.com",
        query="docs pricing",
        limit=10,
        read_top=2,
        read_backend="direct",
        max_read_chars=1200,
    )

    assert packet["read_top"] == 2
    assert packet["read_backend"] == "direct"
    assert packet["read_pack"]["schema_version"] == "representative_read_pack_v1"
    assert packet["read_summary"]["attempted"] == 2
    assert packet["read_summary"]["usable_count"] == 2
    assert packet["read_pack"]["usable_count"] == 2
    assert packet["readings"][0]["schema_version"] == "read_evidence_v1"
    assert packet["readings"][0]["usable"] is True
    assert packet["readings"][0]["content"]
    assert packet["agent_followup"]["should_answer"] is True
    assert packet["agent_followup"]["next_decision"] == "answer"


def test_site_map_supports_sitemap_index_and_subdomains(monkeypatch):
    pages = {
        "https://example.com/robots.txt": "",
        "https://example.com/sitemap.xml": """<?xml version="1.0"?>
            <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <sitemap><loc>https://example.com/docs-sitemap.xml</loc></sitemap>
            </sitemapindex>
        """,
        "https://example.com/docs-sitemap.xml": """<?xml version="1.0"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://docs.example.com/api/reference</loc></url>
              <url><loc>https://example.com/blog/ignored</loc></url>
            </urlset>
        """,
    }

    def fake_fetch(url: str, *, timeout: int = 8) -> str:
        return pages[url]

    monkeypatch.setattr("guanlan.site_map._fetch_text", fake_fetch)

    packet = build_site_map(
        "https://example.com",
        sitemap="only",
        include_subdomains=True,
        include_patterns=["api"],
        limit=10,
    )

    assert [item["url"] for item in packet["links"]] == ["https://docs.example.com/api/reference"]
    assert packet["summary"]["source_counts"] == {"sitemap": 1}


def test_site_map_renderers_keep_boundary(monkeypatch):
    packet = {
        "url": "https://example.com/",
        "query": "docs",
        "limit": 80,
        "sitemap_mode": "auto",
        "boundary": "站点入口发现只说明这些公开 URL 值得继续读取。",
        "links": [
            {
                "title": "Docs",
                "url": "https://example.com/docs",
                "source": "page_link",
                "score": 3.0,
                "description": "",
                "read_command": "guanlan read https://example.com/docs --quality-report",
            }
        ],
        "agent_followup": {"next_commands": ["guanlan read https://example.com/docs --quality-report"]},
    }

    markdown = format_site_map_markdown(packet)
    context = format_site_map_context(packet)

    assert "观澜站点入口" in markdown
    assert "不是正文证据" in markdown or "继续读取" in markdown
    assert "read_command" in context


def _sample_packet() -> dict:
    return {
        "schema_version": "site_map_v1",
        "url": "https://example.com/",
        "origin": "https://example.com/",
        "query": "docs",
        "limit": 80,
        "include_subdomains": False,
        "sitemap_mode": "auto",
        "links": [
            {
                "title": "Docs",
                "url": "https://example.com/docs",
                "source": "page_link",
                "score": 3.0,
                "description": "",
                "lastmod": "",
                "matched_terms": ["docs"],
                "read_command": "guanlan read https://example.com/docs --quality-report",
            }
        ],
        "summary": {"candidate_count": 1, "returned_count": 1, "filtered_out_count": 0, "source_counts": {"page_link": 1}},
        "sources": [],
        "boundary": "站点入口发现只说明这些公开 URL 值得继续读取；它不是正文证据。",
        "agent_followup": {
            "status": "ready",
            "should_answer": False,
            "next_decision": "continue",
            "next_commands": ["guanlan read https://example.com/docs --quality-report"],
            "boundary": "先用 guanlan read 读取代表性 URL。",
        },
    }


def test_map_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("guanlan.site_map.build_site_map", return_value=_sample_packet()):
        with patch("sys.argv", ["guanlan", "map", "example.com", "--query", "docs", "--json"]):
            main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "site_map_v1"
    assert payload["links"][0]["url"] == "https://example.com/docs"


def test_map_cli_passes_read_options(capsys):
    from guanlan.cli import main

    captured = {}

    def fake_build(*args, **kwargs):
        captured.update(kwargs)
        return _sample_packet()

    with patch("guanlan.site_map.build_site_map", side_effect=fake_build):
        with patch(
            "sys.argv",
            [
                "guanlan",
                "map",
                "example.com",
                "--query",
                "docs",
                "--read-top",
                "2",
                "--read-backend",
                "direct",
                "--max-read-chars",
                "1200",
                "--json",
            ],
        ):
            main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "site_map_v1"
    assert captured["read_top"] == 2
    assert captured["read_backend"] == "direct"
    assert captured["max_read_chars"] == 1200


def test_map_http_dispatch_uses_site_map(monkeypatch):
    from guanlan import serve

    captured = {}

    def fake_build(*args, **kwargs):
        captured.update(kwargs)
        return _sample_packet()

    monkeypatch.setattr("guanlan.site_map.build_site_map", fake_build)

    status, body = serve.dispatch_request(
        "POST",
        "/map",
        {"url": "https://example.com", "query": "docs", "read_top": 1, "read_backend": "direct"},
    )

    assert status == 200
    assert body["schema_version"] == "site_map_v1"
    assert body["agent_followup"]["should_answer"] is False
    assert captured["read_top"] == 1
    assert captured["read_backend"] == "direct"


def test_map_mcp_tool_runs_json(monkeypatch):
    from guanlan.integrations import mcp_server

    captured = {}

    def fake_build(*args, **kwargs):
        captured.update(kwargs)
        return _sample_packet()

    monkeypatch.setattr("guanlan.site_map.build_site_map", fake_build)

    payload = mcp_server._run_tool(
        "guanlan_map",
        {"url": "https://example.com", "query": "docs", "read_top": 1, "max_read_chars": 1200, "format": "json"},
    )

    assert payload["schema_version"] == "site_map_v1"
    assert payload["links"][0]["read_command"].startswith("guanlan read")
    assert captured["read_top"] == 1
    assert captured["max_read_chars"] == 1200
