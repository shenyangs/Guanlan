# -*- coding: utf-8 -*-
"""Tests for the read-only search entrypoint catalog."""

from guanlan.search_entrypoints import (
    build_search_operator_hints,
    get_search_engine_entrypoint,
    list_search_engine_entrypoints,
    suggest_search_entrypoints,
)


def test_search_entrypoints_catalog_internalizes_skill_without_runtime_claims():
    rows = list_search_engine_entrypoints()

    assert len(rows) == 17
    assert rows["baidu-web"]["integration"] == "guanlan_native_backend"
    assert rows["bing-cn"]["integration"] == "guanlan_native_backend"
    assert rows["duckduckgo-html"]["integration"] == "guanlan_native_backend"
    assert rows["toutiao-search"]["integration"] == "catalog_only"
    assert rows["jisilu-search"]["status"] == "experimental"
    assert "not_investment_advice" in rows["jisilu-search"]["risk_tags"]
    assert rows["wolframalpha"]["evidence_role"] == "computational_knowledge_reference"


def test_search_entrypoint_alias_resolution():
    assert get_search_engine_entrypoint("duckduckgo")["id"] == "duckduckgo-html"
    assert get_search_engine_entrypoint("google_hk")["id"] == "google-hk"
    assert get_search_engine_entrypoint("not-a-search-engine") == {}


def test_search_entrypoint_suggestions_are_catalog_only():
    policy = suggest_search_entrypoints(
        "宁德时代 可转债 风险",
        route_plan={"primary_intents": ["finance"], "preferred_scopes": ["finance_sentiment"]},
    )

    ids = [item["id"] for item in policy["selected"]]
    assert "baidu-web" in ids
    assert "jisilu-search" in ids
    assert policy["policy"] == "catalog_only_not_default_backend"
    assert any("不要让 Agent 逐个裸抓" in item for item in policy["avoid"])


def test_search_operator_hints_preserve_site_and_recency_boundaries():
    hints = build_search_operator_hints(
        "site:gov.cn 横琴封关政策 最新",
        recency={"enabled": True, "window_days": 7},
    )

    by_operator = {item["operator"]: item for item in hints}
    assert by_operator["site:"]["status"] == "hard_filter"
    assert "不能放宽到域外" in by_operator["site:"]["boundary"]
    assert by_operator["time_filter"]["status"] == "suggested"
    assert "不可跨后端通用" in by_operator["time_filter"]["boundary"]


def test_search_operator_hints_suggest_exact_phrase_and_filetype():
    hints = build_search_operator_hints("WPS AI 白皮书")

    operators = {item["operator"] for item in hints}
    assert "exact_phrase" in operators
    assert "filetype:" in operators
