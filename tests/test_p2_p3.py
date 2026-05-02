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


def test_serve_dispatch_search_uses_webtools(monkeypatch):
    monkeypatch.setattr(
        "guanlan.webtools.search_web",
        lambda *args, **kwargs: [{"title": "A", "url": "https://example.com", "rank": 1}],
    )

    status, body = serve.dispatch_request("POST", "/search", {"query": "A", "limit": 1})

    assert status == 200
    assert body["results"][0]["title"] == "A"


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
