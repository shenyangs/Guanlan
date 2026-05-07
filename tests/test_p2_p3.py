# -*- coding: utf-8 -*-
"""Tests for P2/P3 service, plugin, and evaluation surfaces."""

import json
import sys
from unittest.mock import patch

from guanlan import evaluation, plugins, serve
from guanlan.config import Config
from guanlan.limits import (
    DEFAULT_ARCHIVE_SEARCH_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
)


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

    status, tools = serve.dispatch_request("GET", "/tools")
    assert status == 200
    tool_names = {tool["name"] for tool in tools["tools"]}
    assert {"guanlan_search", "guanlan_research", "guanlan_archive_search", "guanlan_browser_assist_plan", "guanlan_browser_assist_run"} <= tool_names
    assert "只读工具面" in tools["boundary"]


def test_serve_dispatch_browser_assist_plan_is_read_only():
    status, body = serve.dispatch_request(
        "POST",
        "/browser-assist/plan",
        {
            "url": "https://www.xiaohongshu.com/explore/demo",
            "signals": ["access_gate"],
        },
    )

    assert status == 200
    assert body["recommended"] is True
    assert body["browser_assist_task"]["task_type"] == "open_and_read_visible_page"
    assert body["browser_assist_task"]["read_only"] is True
    assert body["browser_assist_task"]["host_browser_contract"]["uses_existing_browser_session"] is True
    assert "cookies_without_separate_explicit_authorization" in body["browser_assist_task"]["must_not_access"]
    assert body["browser_assist_task"]["conditional_access"]["cookies"] == "allowed_only_after_separate_explicit_user_authorization"


def test_serve_dispatch_browser_assist_run_returns_adapter_contract():
    status, body = serve.dispatch_request(
        "POST",
        "/browser-assist/run",
        {
            "url": "https://www.xiaohongshu.com/explore/demo",
            "adapter": "host-browser",
        },
    )

    assert status == 200
    assert body["adapter"] == "host-browser"
    assert body["status"] == "requires_host_browser_execution"
    assert body["contract"]["safety"]["cookie_access_requires_separate_explicit_authorization"] is True


def test_serve_dispatch_search_uses_webtools(monkeypatch):
    monkeypatch.setattr(
        "guanlan.webtools.search_web",
        lambda *args, **kwargs: [{"title": "A", "url": "https://example.com", "rank": 1}],
    )

    status, body = serve.dispatch_request("POST", "/search", {"query": "A", "limit": 1})

    assert status == 200
    assert body["results"][0]["title"] == "A"


def test_serve_dispatch_errors_are_classified(monkeypatch):
    def broken_search(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("guanlan.webtools.search_web", broken_search)

    status, body = serve.dispatch_request("POST", "/search", {"query": "A"})

    assert status == 400
    assert body["error_type"] == "network_timeout"


def test_serve_dispatch_defaults_use_expanded_agent_limits(monkeypatch):
    calls = {}

    def fake_search_web(*_args, **kwargs):
        calls["search"] = kwargs["limit"]
        return []

    def fake_fetch_hotnews(*_args, **kwargs):
        calls["hotnews"] = kwargs["limit"]
        return []

    def fake_search_documents(*_args, **kwargs):
        calls["archive"] = kwargs["limit"]
        return []

    def fake_compare_report(*_args, **kwargs):
        calls["compare"] = kwargs["limit"]
        return {"ok": True}

    monkeypatch.setattr("guanlan.webtools.search_web", fake_search_web)
    monkeypatch.setattr("guanlan.hotnews.fetch_hotnews", fake_fetch_hotnews)
    monkeypatch.setattr("guanlan.archive.search_documents", fake_search_documents)
    monkeypatch.setattr("guanlan.research_workflows.build_compare_report", fake_compare_report)

    serve.dispatch_request("POST", "/search", {"query": "A"})
    serve.dispatch_request("GET", "/hotnews")
    serve.dispatch_request("POST", "/archive/search", {"query": "A"})
    serve.dispatch_request("POST", "/compare", {"subjects": ["A", "B"]})

    assert calls["search"] == DEFAULT_SEARCH_LIMIT
    assert calls["hotnews"] == DEFAULT_HOTNEWS_LIMIT
    assert calls["archive"] == DEFAULT_ARCHIVE_SEARCH_LIMIT
    assert calls["compare"] == DEFAULT_RESEARCH_LIMIT


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


def test_serve_dispatch_research_workflows(monkeypatch):
    monkeypatch.setattr(
        "guanlan.research_workflows.build_compare_report",
        lambda subjects, **_kwargs: {"mode": "compare", "subjects": subjects},
    )
    monkeypatch.setattr(
        "guanlan.research_workflows.build_timeline_report",
        lambda query, **_kwargs: {"mode": "timeline", "query": query},
    )
    monkeypatch.setattr(
        "guanlan.research_workflows.build_dossier_report",
        lambda entity, **_kwargs: {"mode": "dossier", "entity": entity},
    )

    status, compare = serve.dispatch_request("POST", "/compare", {"subjects": ["A", "B"]})
    assert status == 200
    assert compare["subjects"] == ["A", "B"]

    status, timeline = serve.dispatch_request("POST", "/timeline", {"query": "AI 眼镜"})
    assert status == 200
    assert timeline["query"] == "AI 眼镜"

    status, dossier = serve.dispatch_request("POST", "/dossier", {"entity": "某公司"})
    assert status == 200
    assert dossier["entity"] == "某公司"


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


def test_serve_token_auth_helper_accepts_header_or_bearer():
    assert serve.is_authorized_request({}, "") is True
    assert serve.is_authorized_request({"X-Guanlan-Token": "secret"}, "secret") is True
    assert serve.is_authorized_request({"Authorization": "Bearer secret"}, "secret") is True
    assert serve.is_authorized_request({"Authorization": "Bearer wrong"}, "secret") is False


def test_serve_cli_can_print_random_token(capsys):
    from guanlan.cli import main

    with patch.object(sys, "argv", ["guanlan", "serve", "--print-token"]):
        main()
    captured = capsys.readouterr()

    assert len(captured.out.strip()) >= 24
    assert not captured.err


def test_benchmark_task_pool_has_realistic_category_coverage():
    tasks = evaluation.list_benchmark_tasks()
    categories = {task["category"] for task in tasks}

    assert len(tasks) >= 40
    assert {"policy", "local", "ecommerce", "tech", "reputation", "hot", "academic", "local_llm"} <= categories
    assert len(evaluation.list_benchmark_tasks(category="policy")) == 5


def test_eval_tasks_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch.object(sys, "argv", ["guanlan", "eval", "tasks", "--category", "policy", "--format", "json"]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert len(payload) == 5
    assert payload[0]["category"] == "policy"


def test_eval_tasks_markdown_uses_shared_formatter(capsys):
    from guanlan.cli import main

    with patch.object(sys, "argv", ["guanlan", "eval", "tasks", "--category", "tech"]):
        main()
    captured = capsys.readouterr()

    assert "观澜真实任务评测池" in captured.out
    assert "## tech" in captured.out


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
    assert "wps_office_market_radar" in ids
    assert report["summary"]["fail"] == 0
    assert report["summary"]["score"] >= 80


def test_route_chart_explains_scopes_and_evidence_roles():
    from guanlan.router import build_route_plan, format_route_chart

    plan = build_route_plan("EI会议 投稿 检索 收录 要求", preset="academic", profile="china")
    chart = format_route_chart(plan)

    assert "路由诊断图" in chart
    assert "academic" in chart
    assert "证据角色" in chart
