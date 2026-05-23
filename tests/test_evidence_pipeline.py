# -*- coding: utf-8 -*-
"""Tests for the shadow Evidence Mixer diagnostics."""

from guanlan import webtools
from guanlan.web.evidence_pipeline import build_shadow_evidence_pipeline


def _same_domain_result(idx: int) -> dict:
    return {
        "rank": idx,
        "title": f"同域名证据 {idx}",
        "url": f"https://example.com/items/{idx}",
        "domain": "example.com",
        "source_type": "社交/内容平台",
        "evidence_role": "user_sample",
        "score": 4.5 - idx * 0.1,
        "score_parts": {
            "total": 4.5 - idx * 0.1,
            "keyword_match": 0.8,
            "sample_fit": 0.3,
        },
        "trace": {
            "source_card": {
                "source_type": "社交/内容平台",
                "sample_value": 0.8,
                "authority_score": 0.2,
                "freshness_value": 0.2,
            }
        },
    }


def test_shadow_evidence_mixer_fails_open_when_diversity_would_underselect():
    rows = [_same_domain_result(idx) for idx in range(1, 7)]

    report = build_shadow_evidence_pipeline(
        rows,
        query="某产品 用户评价",
        route_plan={"evidence_roles": ["user_sample", "authoritative_report"]},
        quality={"route_evidence_roles": ["user_sample", "authoritative_report"]},
        limit=6,
        target_size=6,
    )

    assert report["mode"] == "shadow"
    assert report["fail_open"] is True
    assert report["mutates_output"] is False
    assert report["candidate_count"] == 6
    assert report["fallback_used"] is True
    assert report["fallback_reason"] == "coverage_floor"
    assert report["selected_count"] >= 5
    assert report["gain_estimate"]["empty_result_risk"] == "low"
    assert report["gain_estimate"]["activation_recommendation"] == "keep_shadow"
    assert any("coverage fallback" in warning for warning in report["warnings"])


def test_search_web_attaches_shadow_mixer_without_reordering_results(monkeypatch):
    def fake_search(query, limit=10):
        return [
            webtools.SearchResult(
                title=f"同域名证据 {idx}",
                url=f"https://example.com/items/{idx}",
                snippet="某产品 用户评价 体验",
                source="duckduckgo",
                rank=idx,
            )
            for idx in range(1, 7)
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web("某产品 用户评价", backend="duckduckgo", limit=6, trace=True)

    assert [item["url"] for item in results] == [f"https://example.com/items/{idx}" for idx in range(1, 7)]
    mixer = results[0]["trace"]["evidence_mixer_shadow"]
    assert mixer["mode"] == "shadow"
    assert mixer["candidate_count"] == len(results)
    assert mixer["selected_count"] >= 5
    assert "gain_estimate" in mixer
    assert mixer["mutates_output"] is False
    assert "evidence_mixer_shadow" in webtools.format_search_trace(results)
    assert "Evidence Mixer" in webtools.format_search_context(results)


def test_search_web_evidence_assist_keeps_order_and_surfaces_first_read_guidance(monkeypatch):
    def fake_search(query, limit=10):
        return [
            webtools.SearchResult(
                title="社区讨论",
                url="https://zhihu.com/question/product",
                snippet="某产品 用户评价 体验",
                source="duckduckgo",
                rank=1,
            ),
            webtools.SearchResult(
                title="官方参数",
                url="https://example.gov.cn/product",
                snippet="某产品 官方 参数",
                source="duckduckgo",
                rank=2,
            ),
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    shadow_results = webtools.search_web(
        "某产品 用户评价 官方参数",
        backend="duckduckgo",
        limit=2,
        trace=True,
        evidence_mode="shadow",
    )
    results = webtools.search_web(
        "某产品 用户评价 官方参数",
        backend="duckduckgo",
        limit=2,
        trace=True,
        evidence_mode="assist",
    )

    assert [item["url"] for item in results] == [item["url"] for item in shadow_results]
    mixer = results[0]["trace"]["evidence_mixer_shadow"]
    assert mixer["mode"] == "assist"
    assert mixer["mutates_output"] is False
    context = webtools.format_search_context(results)
    assert "Evidence Mixer 优先阅读" in context


def test_search_web_evidence_mode_off_disables_report(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(title="结果", url="https://example.com/a", snippet="摘要")
        ],
    )

    results = webtools.search_web(
        "普通查询",
        backend="duckduckgo",
        limit=1,
        trace=True,
        evidence_mode="off",
    )

    mixer = results[0]["trace"]["evidence_mixer_shadow"]
    assert mixer["enabled"] is False
    assert mixer["mode"] == "off"
    assert "Evidence Mixer" not in webtools.format_search_context(results)


def test_search_web_empty_results_keep_fail_open_shadow_diagnostics(monkeypatch):
    monkeypatch.setattr(webtools, "_search_duckduckgo", lambda query, limit=10: [])

    results = webtools.search_web("冷门不存在查询样本", backend="duckduckgo", limit=6, trace=True)

    assert list(results) == []
    mixer = results.diagnostics["evidence_mixer_shadow"]
    assert mixer["mode"] == "shadow"
    assert mixer["fail_open"] is True
    assert mixer["candidate_count"] == 0
    assert mixer["selected_count"] == 0
    assert mixer["fallback_used"] is False
    assert mixer["gain_estimate"]["empty_result_risk"] == "existing_empty_input"
