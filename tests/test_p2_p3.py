# -*- coding: utf-8 -*-
"""Tests for P2/P3 service, plugin, and evaluation surfaces."""

import json

from guanlan import evaluation, plugins, serve
from guanlan.config import Config


def test_serve_dispatch_health_and_route():
    status, health = serve.dispatch_request("GET", "/health")
    assert status == 200
    assert health["mode"] == "read-only"

    status, plan = serve.dispatch_request("POST", "/route", {"query": "某产品 用户评价 值不值得买"})
    assert status == 200
    assert "reputation" in plan["primary_intents"] + plan["secondary_intents"]

    status, body = serve.dispatch_request("GET", "/sources?surface=hotnews&backend=native")
    assert status == 200
    assert body["sources"]["bilibili-hot-search"]["backend"] == "native"


def test_serve_dispatch_search_uses_webtools(monkeypatch):
    monkeypatch.setattr(
        "guanlan.webtools.search_web",
        lambda *args, **kwargs: [{"title": "A", "url": "https://example.com", "rank": 1}],
    )

    status, body = serve.dispatch_request("POST", "/search", {"query": "A", "limit": 1})

    assert status == 200
    assert body["results"][0]["title"] == "A"


def test_serve_dispatch_feeds_uses_curated(monkeypatch):
    monkeypatch.setattr(
        "guanlan.feeds.fetch_feed_source",
        lambda *_args, **kwargs: [{"title": "A", "url": "https://example.com/a", "limit": kwargs["limit"]}],
    )

    status, body = serve.dispatch_request("GET", "/feeds?source=curated&limit=3&category=ai")

    assert status == 200
    assert body["items"][0]["title"] == "A"
    assert body["items"][0]["limit"] == 3


def test_serve_dispatch_context_returns_prompt(monkeypatch):
    monkeypatch.setattr(
        "guanlan.webtools.build_research_packet",
        lambda *args, **kwargs: {"query": args[0], "results": [], "selected_evidence": [], "readings": [], "guidance": []},
    )

    status, body = serve.dispatch_request("POST", "/context", {"query": "本地模型联网", "read_top": 0})

    assert status == 200
    assert body["format"] == "prompt"
    assert "观澜本地模型联网 Prompt" in body["prompt"]


def test_serve_dispatch_hotnews_compact_brief(monkeypatch):
    monkeypatch.setattr(
        "guanlan.hotnews.fetch_hotnews",
        lambda *_args, **_kwargs: [
            {"rank": 1, "source_id": "baidu", "title": "AI 热点", "url": "https://example.com/a"}
        ],
    )

    status, body = serve.dispatch_request("GET", "/hotnews?source=today&compact=1&brief=1")

    assert status == 200
    assert body["items"][0]["evidence_role"] == "fresh_trend_signal"
    assert body["brief"]["sample_count"] == 1


def test_plugin_registry_registers_readonly_backend(tmp_path):
    config_path = tmp_path / "config.yaml"
    script = tmp_path / "backend.py"
    script.write_text("print('[]')\n", encoding="utf-8")
    config = Config(config_path=config_path)

    registered = plugins.register_plugin("internal", str(script), config=config)
    listed = plugins.list_plugins(config=config)

    assert registered["internal"]["mode"] == "read-only"
    assert listed["internal"]["path"] == str(script)
    assert "Do not write" in plugins.plugin_template("internal")


def test_eval_scenarios_jsonl_is_machine_readable():
    text = evaluation.format_evaluation_jsonl()
    first = json.loads(text.splitlines()[0])

    assert first["id"] == "policy_source_identity"
    assert "checks" in first


def test_eval_benchmark_covers_academic_and_agent_pool():
    report = evaluation.run_benchmark(limit=50)

    ids = {case["id"] for case in report["cases"]}
    assert "academic_indexing" in ids
    assert report["summary"]["fail"] == 0
    assert report["summary"]["score"] >= 80


def test_route_chart_explains_scopes_and_evidence_roles():
    from guanlan.router import build_route_plan, format_route_chart

    plan = build_route_plan("EI会议 投稿 检索 收录 要求", preset="academic", profile="china")
    chart = format_route_chart(plan)

    assert "路由诊断图" in chart
    assert "academic" in chart
    assert "证据角色" in chart
