# -*- coding: utf-8 -*-
"""Tests for optional AnySearch routing."""

from guanlan import webtools
from guanlan.anysearch import (
    anysearch_activation_plan,
    anysearch_anonymous_auto_allowed,
    anysearch_auto_mode,
)
from guanlan.config import Config


def test_anysearch_auto_mode_defaults_to_anonymous_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("GUANLAN_ANYSEARCH_AUTO", raising=False)
    monkeypatch.delenv("GUANLAN_ANYSEARCH_ANONYMOUS_AUTO", raising=False)
    config = Config(config_path=tmp_path / "config.yaml")

    assert anysearch_auto_mode(config) == "fallback"
    assert anysearch_anonymous_auto_allowed(config) is True


def test_backend_order_adds_anysearch_by_default_for_strong_fit(monkeypatch):
    monkeypatch.setenv("GUANLAN_ANYSEARCH_AUTO", "fallback")
    monkeypatch.delenv("ANYSEARCH_API_KEY", raising=False)
    monkeypatch.delenv("GUANLAN_ANYSEARCH_ANONYMOUS_AUTO", raising=False)

    assert webtools.backend_order("auto", "english", query="OpenAI API release notes") == [
        "bing",
        "anysearch",
        "duckduckgo",
    ]


def test_backend_order_keeps_anysearch_off_without_opt_in(monkeypatch):
    monkeypatch.setenv("GUANLAN_ANYSEARCH_AUTO", "off")

    assert webtools.backend_order("auto", "english", query="OpenAI API release notes") == [
        "duckduckgo",
        "bing",
    ]


def test_backend_order_respects_anonymous_auto_off(monkeypatch):
    monkeypatch.setenv("GUANLAN_ANYSEARCH_AUTO", "fallback")
    monkeypatch.setenv("GUANLAN_ANYSEARCH_ANONYMOUS_AUTO", "off")
    monkeypatch.delenv("ANYSEARCH_API_KEY", raising=False)

    assert webtools.backend_order("auto", "english", query="OpenAI API release notes") == [
        "duckduckgo",
        "bing",
    ]


def test_auto_anysearch_skips_late_duckduckgo_when_pool_is_satisfied(monkeypatch):
    monkeypatch.setenv("GUANLAN_ANYSEARCH_AUTO", "fallback")
    monkeypatch.delenv("GUANLAN_ANYSEARCH_ANONYMOUS_AUTO", raising=False)
    calls = []

    def fake_backend(name, query, limit=10, **_kwargs):
        calls.append(name)
        if name == "bing":
            return (
                [
                    webtools.SearchResult(
                        title=f"OpenAI API release notes changelog {idx}",
                        url=f"https://developers.openai.com/api/docs/changelog/{idx}",
                        snippet="OpenAI API release notes changelog documentation.",
                        source="bing",
                    )
                    for idx in range(8)
                ],
                [{"network_mode": "direct", "status": "ok"}],
            )
        if name == "duckduckgo":
            return (
                [
                    webtools.SearchResult(
                        title="DuckDuckGo should not be needed",
                        url="https://example.com/ddg",
                        snippet="Should be skipped.",
                        source="duckduckgo",
                    )
                ],
                [{"network_mode": "direct", "status": "ok"}],
            )
        return [], []

    def fake_anysearch(query, **_kwargs):
        return {
            "results": [
                {
                    "title": f"OpenAI API release notes AnySearch {idx}",
                    "url": f"https://example.com/any/{idx}",
                    "description": "OpenAI API release notes structured result.",
                    "quality_score": 80,
                }
                for idx in range(10)
            ],
            "metadata": {"credential_mode": "anonymous"},
        }

    monkeypatch.setattr(webtools, "_search_backend_with_network", fake_backend)
    monkeypatch.setattr(webtools, "search_anysearch", fake_anysearch)

    results = webtools.search_web(
        "OpenAI API release notes",
        profile="english",
        limit=30,
        trace=True,
    )

    assert calls == ["bing"]
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert [item["backend"] for item in diagnostics[:3]] == ["bing", "anysearch", "duckduckgo"]
    assert diagnostics[2]["status"] == "skipped"
    assert "AnySearch 自动兜底" in diagnostics[2]["note"]


def test_search_web_anysearch_backend_maps_results(monkeypatch):
    monkeypatch.setattr(webtools, "anysearch_api_key", lambda: "")

    def fake_search_anysearch(query, **kwargs):
        assert query == "Guanlan API"
        assert kwargs["api_key"] == ""
        return {
            "results": [
                {
                    "title": "Guanlan v0.5.9",
                    "url": "https://pypi.org/project/guanlan/",
                    "description": "China-aware source router",
                    "source": "web",
                    "score": 76.0,
                    "quality_score": 80.0,
                }
            ],
            "metadata": {
                "credential_mode": "anonymous",
                "request_id": "req_test",
                "rate_limit_remaining": "99",
            },
        }

    monkeypatch.setattr(webtools, "search_anysearch", fake_search_anysearch)

    results = webtools.search_web("Guanlan API", backend="anysearch", limit=1, trace=True)

    assert results[0]["source"] == "anysearch"
    assert results[0]["title"] == "Guanlan v0.5.9"
    assert results[0]["trace"]["backend_order"] == ["anysearch"]
    assert results[0]["trace"]["anysearch_activation"]["status"] == "active"


def test_anysearch_activation_plan_suggests_without_silent_key_access(tmp_path):
    config = Config(config_path=tmp_path / "config.yaml")

    plan = anysearch_activation_plan(
        "OpenSSL CVE latest vendor advisory",
        profile="english",
        scope="cybersecurity",
        backend="auto",
        backend_summary={"blocked": ["bing"]},
        result_count=1,
        config=config,
    )

    assert plan["status"] == "auto_fallback"
    assert plan["next_action"] == "use_anysearch"
    assert "query_matches_anysearch_strength" in plan["reasons"]
    assert "不要读取浏览器 Cookie" in plan["credential_boundary"]


def test_anysearch_activation_plan_ignores_non_fit_backend_gaps(tmp_path):
    config = Config(config_path=tmp_path / "config.yaml")

    plan = anysearch_activation_plan(
        "横琴封关政策 2025 最新",
        profile="china",
        scope="party_central",
        backend="auto",
        backend_summary={"blocked": ["bing"], "parser_miss": ["duckduckgo"]},
        result_count=1,
        config=config,
    )

    assert plan["status"] == "inactive"
    assert plan["enabled"] is False
    assert "query_matches_anysearch_strength" not in plan["reasons"]
