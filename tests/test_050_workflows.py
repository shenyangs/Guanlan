# -*- coding: utf-8 -*-
"""Tests for 0.5.0-level upper workflow surfaces."""

import json
from pathlib import Path
from unittest.mock import patch

from guanlan import evaluation, source_registry
from guanlan.cli import main
from guanlan.investigation import build_investigation_packet


def test_investigate_dry_run_has_budget_and_no_executed_steps():
    packet = build_investigation_packet("人工智能 政策 最新", budget="deep", dry_run=True)

    assert packet["investigation"]["dry_run"] is True
    assert packet["investigation"]["budget"] == "deep"
    assert packet["investigation"]["executed_steps"] == []
    assert "planned_steps" in packet["investigation"]
    assert packet["investigation"]["limits"]["limit"] >= 80


def test_investigate_budget_uses_research_packet(monkeypatch):
    def fake_research(query, **kwargs):
        return {
            "query": query,
            "result_count": 1,
            "source_mix": {"政府/部委": 1},
            "selected_evidence": [{"title": "政策", "url": "https://gov.cn/a"}],
            "readings": [],
            "guidance": [],
        }

    monkeypatch.setattr("guanlan.web.research.build_research_packet", fake_research)
    packet = build_investigation_packet("人工智能 政策 最新", budget="light")

    assert packet["workflow_decision"]["tier"] in {"guided", "investigate"}
    assert packet["investigation"]["budget"] == "light"
    assert packet["final_context"]["result_count"] == 1
    assert packet["suggested_next"]


def test_source_registry_v2_lists_shows_and_explains():
    rows = source_registry.list_source_cards(scope="gov", limit=2)
    shown = source_registry.show_source("gov.cn")
    explained = source_registry.explain_sources("新质生产力 政策", limit=3)

    assert len(rows) == 2
    assert rows[0]["authority_score"] >= 0.9
    assert shown["domain"] == "gov.cn"
    assert explained["sources"]
    assert "route_plan" in explained


def test_eval_suite_has_100_cases_and_passes():
    report = evaluation.run_eval_suite("chinese-web-v1", limit=80)

    assert report["summary"]["total"] == 100
    assert report["summary"]["fail"] == 0
    assert set(report["category_summary"]) >= {"policy", "finance", "tech", "local_llm"}


def test_eval_suite_html_report(tmp_path):
    report = evaluation.run_eval_suite("chinese-web-v1", limit=80)
    output = tmp_path / "suite.html"

    written = evaluation.write_eval_suite_html(report, str(output))

    assert written == str(output)
    assert "观澜 Eval Suite" in output.read_text(encoding="utf-8")


def test_cli_sources_and_eval_suite(capsys, tmp_path):
    with patch("sys.argv", ["guanlan", "sources", "list", "--scope", "gov", "--limit", "1", "--format", "json"]):
        main()
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["scope_id"] == "gov"

    with patch("sys.argv", ["guanlan", "eval", "suite", "list", "--format", "json"]):
        main()
    suites = json.loads(capsys.readouterr().out)
    assert suites[0]["id"] == "chinese-web-v1"

    output = tmp_path / "report.html"
    with patch("sys.argv", ["guanlan", "eval", "suite", "report", "--output", str(output)]):
        main()
    assert Path(output).exists()
    assert "Eval suite report written" in capsys.readouterr().out


def test_investigate_exposes_budget_fallback_and_sufficiency(monkeypatch):
    def fake_research(query, **kwargs):
        return {
            "query": query,
            "result_count": 0,
            "source_mix": {},
            "selected_evidence": [],
            "results": [],
            "readings": [],
            "guidance": [],
        }

    monkeypatch.setattr("guanlan.web.research.build_research_packet", fake_research)
    packet = build_investigation_packet("某复杂热点", budget="deep")
    investigation = packet["investigation"]

    assert investigation["step_budget"]["max_steps"] >= 8
    assert investigation["timeout_budget_seconds"] >= 300
    assert investigation["external_fetch_strategy"]["recommended"] is True
    assert investigation["network_diagnosis"]["status"] == "warn"
    assert investigation["evidence_sufficiency"]["status"] == "thin"


def test_source_registry_audit_and_export():
    audit = source_registry.audit_source_registry()
    exported = source_registry.export_source_registry()

    assert audit["summary"]["total"] >= 8
    assert "checks" in audit
    assert exported["schema"] == "guanlan-source-registry-2.0"
    assert exported["counts"]["channels"] >= 1


def test_live_eval_suite_has_failure_categories():
    report = evaluation.run_eval_suite("chinese-web-live", mode="live", limit=80)

    assert report["summary"]["total"] == 100
    assert report["summary"]["fail"] == 0
    assert all("failure_category" in case for case in report["cases"])
    assert "network_or_upstream" in report["boundary"]


def test_archive_semantic_sidecar(tmp_path):
    from guanlan.archive import add_document, embed_archive, search_documents

    db = tmp_path / "archive.db"
    add_document("https://example.com/a", "# vLLM 推理框架\n\nKV Cache 和推理吞吐优化。", db_path=db)
    add_document("https://example.com/b", "# 烹饪笔记\n\n番茄鸡蛋做法。", db_path=db)

    result = embed_archive(db_path=db, backend="local")
    records = search_documents("推理 KV Cache", db_path=db, semantic=True, limit=1, trace=True)

    assert result["status"] == "ok"
    assert result["embedded"] == 2
    assert records[0]["retrieval_mode"] == "semantic"
    assert "vLLM" in records[0]["title"]


def test_cli_new_p2_p3_surfaces(capsys, tmp_path):
    from guanlan.archive import add_document

    with patch("sys.argv", ["guanlan", "sources", "audit", "--format", "json"]):
        main()
    audit = json.loads(capsys.readouterr().out)
    assert audit["summary"]["total"] >= 8

    with patch("sys.argv", ["guanlan", "quality", "performance", "--format", "json"]):
        main()
    perf = json.loads(capsys.readouterr().out)
    assert perf["summary"]["fail"] == 0

    db = tmp_path / "archive.db"
    add_document("https://example.com/a", "# AI 政策\n\n人工智能政策原文。", db_path=db)
    with patch("sys.argv", ["guanlan", "archive", "embed", "--db", str(db), "--json"]):
        main()
    embed = json.loads(capsys.readouterr().out)
    assert embed["status"] == "ok"

    with patch("sys.argv", ["guanlan", "archive", "search", "AI 政策", "--semantic", "--db", str(db), "--json"]):
        main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["records"][0]["retrieval_mode"] == "semantic"


def test_channel_runtime_trial_lists_low_risk_adapters():
    from tests.support.channel_runtime_trial import get_runtime, list_runtime_adapters

    adapters = list_runtime_adapters()
    runtime = get_runtime("web")

    assert {item["channel"] for item in adapters} >= {"web", "rss", "github", "v2ex"}
    assert runtime.health().status == "available"
