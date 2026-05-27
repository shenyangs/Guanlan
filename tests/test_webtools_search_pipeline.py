# -*- coding: utf-8 -*-
"""Tests for search ranking, recovery, and trace behavior."""
# ruff: noqa: F401

import builtins
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from guanlan import webtools
from guanlan.limits import DEFAULT_READ_FALLBACK_LIMIT, DEFAULT_RESEARCH_LIMIT, DEFAULT_SEARCH_LIMIT
from guanlan.source_seeds import (
    direct_source_seeds,
    is_finance_lookup,
    is_live_sports_lookup,
    is_wps_office_lookup,
)
from tests.support.webtools_helpers import _FakeResponse


def test_search_web_adds_direct_sports_seeds_when_search_is_empty(monkeypatch):
    requested = []

    def fake_search(query, limit=10):
        requested.append(query)
        return []

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "NBA季后赛2026年5月战绩 首轮比分",
        backend="duckduckgo",
        profile="china",
        scope="sports",
        limit=5,
        trace=True,
    )

    urls = [item["url"] for item in results]
    assert requested
    assert any("espn.com/nba/story" in url for url in urls)
    assert any("nba.com/games" in url for url in urls)
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert any(item["backend"].startswith("direct:sports") and item["status"] == "ok" for item in diagnostics)
    context = webtools.format_search_context(results)
    assert "高确定性垂直场景" in context


def test_search_web_adds_direct_finance_seeds_even_with_search_results(monkeypatch):
    def fake_search(query, limit=10):
        return [webtools.SearchResult(title="Random generic page", url="https://example.com/random", snippet="noise")]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "贵州茅台 600519 股价 财报 公告",
        backend="duckduckgo",
        profile="china",
        scope="finance",
        limit=8,
        trace=True,
    )

    urls = [item["url"] for item in results]
    assert any("cninfo.com.cn" in url for url in urls)
    assert any("quote.eastmoney.com/sh600519" in url for url in urls)
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert any(item["backend"].startswith("direct:finance") and item["status"] == "ok" for item in diagnostics)


def test_search_web_adds_direct_security_seeds_even_with_search_results(monkeypatch):
    def fake_search(query, limit=10):
        return [
            webtools.SearchResult(
                title="OpenSSL 漏洞讨论",
                url="https://example.com/openssl-note",
                snippet="OpenSSL CVE 最新 漏洞 影响版本",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "OpenSSL CVE 最新 漏洞 影响版本",
        backend="duckduckgo",
        scope="cybersecurity",
        limit=8,
        trace=True,
    )

    urls = [item["url"] for item in results]
    assert any("cisa.gov/known-exploited-vulnerabilities-catalog" in url for url in urls)
    assert any("openssl.org/news/secadv" in url for url in urls)
    assert any(item["evidence_role"] == "vendor_patch" for item in results)
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert any(item["backend"].startswith("direct:cybersecurity") and item["status"] == "ok" for item in diagnostics)


def test_rank_results_maps_security_domains_to_evidence_roles():
    route = webtools.build_route_plan("OpenSSL CVE 最新 漏洞 影响版本", scope="cybersecurity").to_dict()
    quality = webtools.detect_search_quality_profile("OpenSSL CVE 最新 漏洞 影响版本", scope="cybersecurity")
    quality = webtools._quality_with_route_plan(quality, route, explicit_scope="cybersecurity")

    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="国家信息安全漏洞库 CVE-2026-12345",
                url="https://www.cnnvd.org.cn/home/globalSearch?keyword=CVE-2026-12345",
                snippet="OpenSSL 漏洞 影响版本。",
                source="duckduckgo",
            ),
            webtools.SearchResult(
                title="OpenSSL Security Advisories",
                url="https://www.openssl.org/news/secadv/",
                snippet="OpenSSL security advisory and fixed versions.",
                source="direct_source",
            ),
        ],
        query="OpenSSL CVE 最新 漏洞 影响版本",
        preferred_scope="cybersecurity",
        quality=quality,
    )

    roles = {item.domain: item.evidence_role for item in ranked}
    assert roles["cnnvd.org.cn"] == "vulnerability_record"
    assert roles["openssl.org"] == "vendor_patch"


def test_entertainment_scopes_use_short_site_expression(monkeypatch):
    captured_queries = []

    def fake_search(query, limit=10):
        captured_queries.append(query)
        return [
            webtools.SearchResult(
                title="Taylor Swift news",
                url="https://www.billboard.com/music/music-news/taylor-swift/",
                snippet="Billboard coverage.",
                source="duckduckgo",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    webtools.search_web(
        "Taylor Swift latest album tour",
        backend="duckduckgo",
        profile="english",
        scope="global_entertainment",
    )

    assert captured_queries
    assert captured_queries[0].count("site:") == 4
    assert "site:billboard.com" in captured_queries[0]
    assert "site:rollingstone.com" not in captured_queries[0]


def test_jp_kr_entertainment_scope_prioritizes_local_sources(monkeypatch):
    captured_queries = []

    def fake_search(query, limit=10):
        captured_queries.append(query)
        return [
            webtools.SearchResult(
                title="BLACKPINK comeback",
                url="https://www.soompi.com/article/1",
                snippet="Soompi coverage.",
                source="duckduckgo",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    webtools.search_web(
        "BLACKPINK K-pop comeback",
        backend="duckduckgo",
        profile="hybrid",
        scope="jp_kr_entertainment",
    )

    assert captured_queries
    assert captured_queries[0].count("site:") == 4
    assert "site:soompi.com" in captured_queries[0]
    assert "site:oricon.co.jp" in captured_queries[0]
    assert "site:natalie.mu" in captured_queries[0]
    assert "site:koreaherald.com" not in captured_queries[0]


def test_scoped_search_retries_open_query_when_site_expression_is_empty(monkeypatch):
    captured_queries = []

    def fake_search(query, limit=10):
        captured_queries.append(query)
        if query.startswith("("):
            return []
        return [
            webtools.SearchResult(
                title="OpenSSL advisory",
                url="https://www.openssl.org/news/secadv/20260503.txt",
                snippet="Security advisory.",
                source="duckduckgo",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "OpenSSL CVE latest affected versions",
        backend="duckduckgo",
        profile="english",
        scope="cybersecurity",
        trace=True,
    )

    assert len(results) >= 1
    assert captured_queries[0].startswith("(")
    assert captured_queries[1].startswith("OpenSSL CVE latest affected versions")
    assert "retried the original query" in results[0]["trace"]["backend_diagnostics"][0]["note"]
    assert any("openssl.org/news/secadv" in item["url"] for item in results)
    assert any(
        item["backend"].startswith("direct:cybersecurity")
        for item in results[0]["trace"]["backend_diagnostics"]
    )


def test_search_quality_profile_detects_english_company_intent():
    quality = webtools.detect_search_quality_profile("OpenAI API pricing release notes", profile="english")

    assert quality["intent"] == "company"
    assert "company_primary" in quality["preferred_scopes"]
    assert "公司一手资料" in quality["preferred_source_types"]


def test_search_web_trace_includes_quality_profile(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(
                title="国务院发布人工智能政策通知",
                url="https://gov.cn/zhengce/ai.htm",
                snippet="2026年5月2日 最新政策",
            )
        ],
    )

    results = webtools.search_web("人工智能 政策 最新", backend="duckduckgo", trace=True)

    assert results[0]["trace"]["query_quality"]["intent"] == "policy"
    assert results[0]["trace"]["quality"]["fit"] is True
    assert results[0]["trace"]["quality_summary"]["preferred_hit_count"] == 1
    assert results[0]["score_parts"]["intent_fit"] > 0
    assert results[0]["trace"]["route_plan"]["primary_intents"][0] == "policy"
    assert "gov" in results[0]["trace"]["route_plan"]["preferred_scopes"]
    assert results[0]["evidence_role"] == "official_primary"


def test_search_web_site_filter_is_hard(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(
                title="知乎政策讨论",
                url="https://www.zhihu.com/question/1",
                snippet="网友讨论。",
                source="duckduckgo",
            ),
            webtools.SearchResult(
                title="国务院政策原文",
                url="https://www.gov.cn/zhengce/ai.htm",
                snippet="2026年政策原文。",
                source="duckduckgo",
            ),
        ],
    )

    results = webtools.search_web("人工智能 政策", backend="duckduckgo", site="gov.cn", trace=True)

    assert len(results) == 1
    assert results[0]["domain"] == "gov.cn"
    assert results[0]["trace"]["site_filter"]["mode"] == "hard"
    assert results[0]["trace"]["site_filter"]["removed"] == 1
    assert results[0]["trace"]["site_filter"]["relaxed"] is False


def test_search_web_site_filter_empty_keeps_diagnostics_and_webfetch_strategy(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(
                title="知乎政策讨论",
                url="https://www.zhihu.com/question/1",
                snippet="网友讨论。",
                source="duckduckgo",
            )
        ],
    )

    results = webtools.search_web("人工智能 政策", backend="duckduckgo", site="gov.cn", trace=True)

    assert results == []
    assert results.diagnostics["site_filter"]["kept"] == 0
    assert results.diagnostics["site_filter"]["relaxed"] is False
    assert results.diagnostics["external_fetch_strategy"]["enabled"] is True
    assert "WebFetch" in results.diagnostics["external_fetch_strategy"]["agent_instruction"]


def test_search_web_small_limit_warns_agent_without_overriding(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(title=f"Result {idx}", url=f"https://example.com/{idx}", source="duckduckgo")
            for idx in range(limit)
        ],
    )

    results = webtools.search_web("人工智能 政策", backend="duckduckgo", limit=10, trace=True)

    assert len(results) == 10
    advice = results[0]["trace"]["agent_limit_advice"]
    assert advice["enabled"] is True
    assert advice["limit"] == 10
    assert advice["recommended_limit"] == DEFAULT_SEARCH_LIMIT
    assert advice["repair_policy"] == "silent_expand_then_summarize"
    assert advice["silent_repair_commands"][0]["command"] == (
        f'guanlan search "人工智能 政策" --profile china --limit {DEFAULT_SEARCH_LIMIT} --trace'
    )
    assert any("limit 10" in warning for warning in results[0]["trace"]["quality_summary"]["warnings"])
    assert results[0]["trace"]["quality_summary"]["silent_repair_commands"] == advice["silent_repair_commands"]


def test_search_web_network_gap_returns_external_fetch_strategy(monkeypatch):
    def fail_search(query, limit=10):
        raise RuntimeError("network_unreachable: offline")

    monkeypatch.setattr(webtools, "_search_duckduckgo", fail_search)

    results = webtools.search_web("OpenSSL CVE 最新", backend="duckduckgo", scope="cybersecurity", trace=True)

    assert results
    assert results[0]["trace"]["external_fetch_strategy"]["enabled"] is True
    assert "backend_unavailable_or_parser_miss" in results[0]["trace"]["external_fetch_strategy"]["reasons"]
    assert "direct_seed_only" in results[0]["trace"]["external_fetch_strategy"]["reasons"]
    assert "WebFetch" in results[0]["trace"]["external_fetch_strategy"]["agent_instruction"]


def test_search_web_rejects_meaningless_query_before_backend(monkeypatch):
    def fail_search(query, limit=10):
        raise AssertionError("backend should not be called")

    monkeypatch.setattr(webtools, "_search_duckduckgo", fail_search)

    results = webtools.search_web("asdfghjk123456789", backend="duckduckgo", trace=True)
    trace = webtools.format_search_trace(results)

    assert results == []
    assert results.diagnostics["query_shape"]["status"] == "rejected"
    assert results.diagnostics["backend_diagnostics"][0]["status"] == "rejected"
    assert "query_shape: status=rejected" in trace


def test_search_web_expands_short_fact_query(monkeypatch):
    captured_queries = []

    def fake_search(query, limit=10):
        captured_queries.append(query)
        return [
            webtools.SearchResult(
                title="澳门统计暨普查局人口数据",
                url="https://www.dsec.gov.mo/zh-MO/Population",
                snippet="澳门人口统计数据。",
                source="duckduckgo",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web("澳门人口多少", backend="duckduckgo", trace=True)

    assert captured_queries
    assert "统计" in captured_queries[0]
    assert "官方" in captured_queries[0]
    assert results[0]["trace"]["query_shape"]["status"] == "rewritten"


def test_search_web_expands_short_ecommerce_query(monkeypatch):
    captured_queries = []

    def fake_search(query, limit=10):
        captured_queries.append(query)
        return [
            webtools.SearchResult(
                title="华为手机用户评价",
                url="https://www.zhihu.com/question/1",
                snippet="购买、续航、拍照和价格讨论。",
                source="duckduckgo",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    webtools.search_web("华为手机", backend="duckduckgo", scope="ecommerce", trace=True)

    assert captured_queries
    assert "价格" in captured_queries[0]
    assert "用户评价" in captured_queries[0]


def test_search_web_compresses_overlong_query(monkeypatch):
    captured_queries = []
    long_query = (
        "我想系统了解具身智能企业在2024到2025年的融资、产品、商业化、政策支持、供应链和主要玩家情况，"
        "包括智元、宇树、傅利叶、银河通用、逐际动力，还想看广东、上海、北京的地方政策以及最新行业趋势、量产、订单、客户落地情况"
    )

    def fake_search(query, limit=10):
        captured_queries.append(query)
        return [
            webtools.SearchResult(
                title="具身智能行业观察",
                url="https://36kr.com/p/robot",
                snippet="融资、产品、商业化和政策趋势。",
                source="duckduckgo",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(long_query, backend="duckduckgo", trace=True)

    assert captured_queries
    assert len(captured_queries[0]) < len(long_query)
    assert "具身智能" in captured_queries[0]
    assert results[0]["trace"]["query_shape"]["overlong_query"] is True
    assert results[0]["trace"]["query_shape"]["rewritten"] is True


def test_search_web_multi_entity_fanout_adds_entity_specific_queries(monkeypatch):
    captured_queries = []

    def fake_search(query, limit=10):
        captured_queries.append(query)
        if "澳门" in query and "珠海 澳门 香港 深圳 广州" not in query:
            return [
                webtools.SearchResult(
                    title="澳门 GDP 统计数据",
                    url="https://www.dsec.gov.mo/gdp",
                    snippet="澳门本地生产总值数据。",
                    source="duckduckgo",
                )
            ]
        return [
            webtools.SearchResult(
                title="珠海 GDP 统计数据",
                url="https://www.zhuhai.gov.cn/gdp",
                snippet="珠海地区生产总值数据。",
                source="duckduckgo",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web("珠海 澳门 香港 深圳 广州 GDP 对比", backend="duckduckgo", trace=True)

    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert len(captured_queries) > 1
    assert any(item["backend"] == "duckduckgo:entity_fanout" for item in diagnostics)
    assert any(item.get("entity") == "澳门" for item in diagnostics)
    assert any(result["title"] == "澳门 GDP 统计数据" for result in results)


def test_search_web_trace_includes_english_source_roles(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(
                title="OpenAI API Pricing",
                url="https://openai.com/api/pricing/",
                snippet="Official pricing information and model rates.",
                source="duckduckgo",
                rank=1,
            ),
            webtools.SearchResult(
                title="OpenAI pricing discussion",
                url="https://www.reddit.com/r/OpenAI/comments/1",
                snippet="Users discuss API pricing.",
                source="duckduckgo",
                rank=2,
            ),
        ],
    )

    results = webtools.search_web("OpenAI API pricing release notes", backend="duckduckgo", profile="english", trace=True)

    assert results[0]["domain"] == "openai.com"
    assert results[0]["source_type"] == "公司一手资料"
    assert results[0]["matched_scope"] == "company_primary"
    assert results[0]["evidence_role"] == "company_primary"
    assert results[0]["trace"]["query_quality"]["intent"] == "company"
    assert results[0]["score_parts"]["intent_fit"] > 0


def test_search_trace_includes_route_plan(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(
                title="用户评价",
                url="https://www.zhihu.com/question/1",
                snippet="值不值得买",
                source="duckduckgo",
                rank=1,
            )
        ],
    )

    results = webtools.search_web("某产品 用户评价 值不值得买", backend="duckduckgo", trace=True)
    trace = webtools.format_search_trace(results)

    assert "route_plan: intents=" in trace
    assert "reputation" in trace
    assert "query_strategy" in trace
    assert results[0]["trace"]["source_card"]["sample_value"] > results[0]["trace"]["source_card"]["authority_score"]
    assert results[0]["evidence_role"] == "user_sample"


def test_rank_results_prefers_company_primary_for_samsung_newsroom():
    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="Samsung Electronics announces Q1 results",
                url="https://news.samsung.com/kr/earnings-q1-2026",
                snippet="Official newsroom release.",
                source="duckduckgo",
            )
        ],
        query="삼성전자 실적",
        backend_order=["duckduckgo"],
    )

    assert ranked[0].source_type == "公司一手资料"
    assert ranked[0].matched_scope == "company_primary"


def test_rank_results_keeps_zhihu_as_social_web_by_default():
    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="一文了解 Transformer 全貌",
                url="https://www.zhihu.com/tardis/zm/art/600773858",
                snippet="详细图解 Encoder、Decoder 和 Attention。",
                source="duckduckgo",
            )
        ],
        query="Transformer架构原理",
        backend_order=["duckduckgo"],
    )

    assert ranked[0].source_type == "社交/内容平台"
    assert ranked[0].matched_scope == "social_web"


def test_rank_results_extracts_date_from_url_when_title_lacks_date():
    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="AI release notes",
                url="https://example.com/2026/05/03/release-notes",
                snippet="Important update.",
                source="duckduckgo",
            )
        ],
        query="OpenAI 最新发布",
        backend_order=["duckduckgo"],
    )

    assert ranked[0].published_at == "2026-05-03"
    assert ranked[0].date_source == "url"


def test_query_strategy_builds_role_specific_variants():
    route = webtools.build_route_plan("某产品 用户评价 值不值得买 最新", profile="china").to_dict()
    recency = webtools.detect_recency_intent("某产品 用户评价 值不值得买 最新")

    strategy = webtools.build_query_strategy(
        "某产品 用户评价 值不值得买 最新",
        route_plan=route,
        recency=recency,
    )

    roles = {item["role"] for item in strategy["variants"]}
    assert "user_sample" in roles
    assert "review" in roles
    assert "fresh_news" in roles
    assert "fresh_user_sample" in roles
    assert strategy["time_window"]["enabled"] is True
    assert strategy["search_quality_v2"]["recency_bounded"] is True
    assert strategy["agent_hint"]


def test_query_strategy_builds_academic_variants():
    route = webtools.build_route_plan("EI会议 投稿 检索 要求", profile="china").to_dict()
    strategy = webtools.build_query_strategy("EI会议 投稿 检索 要求", route_plan=route)

    roles = {item["role"] for item in strategy["variants"]}
    assert "database_official" in roles
    assert "publisher_guideline" in roles
    assert "institution_policy" in roles


def test_query_strategy_distinguishes_vertical_scopes():
    tech = webtools.build_query_strategy(
        "向量数据库 benchmark",
        route_plan=webtools.build_route_plan("向量数据库 benchmark", scope="tech_dev").to_dict(),
        quality={"requested_scope": "tech_dev"},
    )
    ecommerce = webtools.build_query_strategy(
        "咖啡机 用户评价 售后",
        route_plan=webtools.build_route_plan("咖啡机 用户评价 售后", scope="ecommerce").to_dict(),
        quality={"requested_scope": "ecommerce"},
    )
    finance = webtools.build_query_strategy(
        "某公司 业绩 风险",
        route_plan=webtools.build_route_plan("某公司 业绩 风险", scope="finance").to_dict(),
        quality={"requested_scope": "finance"},
    )
    wps = webtools.build_query_strategy(
        "WPS AI PPT Agent 办公选题",
        route_plan=webtools.build_route_plan("WPS AI PPT Agent 办公选题", scope="wps_office").to_dict(),
        quality={"requested_scope": "wps_office"},
    )

    assert "technical_primary" in {item["role"] for item in tech["variants"]}
    assert "review" in {item["role"] for item in ecommerce["variants"]}
    finance_roles = {item["role"] for item in finance["variants"]}
    assert "company_filing" in finance_roles
    assert "regulatory_notice" in finance_roles
    assert "market_news" in finance_roles
    wps_roles = {item["role"] for item in wps["variants"]}
    assert "topic_radar" in wps_roles
    assert "competitive_context" in wps_roles
    assert "scenario_signal" in wps_roles
    assert "company_primary" in wps_roles
    assert "industry_report" in wps_roles
    assert "user_sample" in wps_roles
    assert "developer_discussion" in wps_roles


def test_wps_subroute_query_strategy_separates_market_lanes():
    wps_ai = webtools.build_query_strategy(
        "WPS AI",
        route_plan=webtools.build_route_plan("WPS AI", scope="wps_office").to_dict(),
        quality={"requested_scope": "wps_office"},
    )
    lingxi = webtools.build_query_strategy(
        "WPS 灵犀",
        route_plan=webtools.build_route_plan("WPS 灵犀", scope="wps_office").to_dict(),
        quality={"requested_scope": "wps_office"},
    )
    wps365 = webtools.build_query_strategy(
        "WPS 365",
        route_plan=webtools.build_route_plan("WPS 365", scope="wps_office").to_dict(),
        quality={"requested_scope": "wps_office"},
    )
    adjacent = webtools.build_query_strategy(
        "AI知识库 KaaS MonkeyOCR",
        route_plan=webtools.build_route_plan("AI知识库 KaaS MonkeyOCR", scope="wps_office").to_dict(),
        quality={"requested_scope": "wps_office"},
    )

    assert any("AI伴写2.0" in item["query"] for item in wps_ai["variants"])
    assert any("PDF文档问答" in item["query"] for item in wps_ai["variants"])
    assert any("职场效率" in item["query"] for item in wps_ai["variants"])
    assert any("Gamma Canva" in item["query"] for item in wps_ai["variants"])
    assert any("国产 AI PPT 工具 横评" in item["query"] for item in wps_ai["variants"])
    assert any("AI办公全能伙伴" in item["query"] for item in lingxi["variants"])
    assert any("语音文档对话" in item["query"] for item in lingxi["variants"])
    assert any("MCP skill" in item["query"] for item in lingxi["variants"])
    assert any("原生 Office 智能体" in item["query"] for item in lingxi["variants"])
    assert any("Microsoft Copilot" in item["query"] for item in lingxi["variants"])
    assert any("企业大脑" in item["query"] for item in wps365["variants"])
    assert any("Microsoft 365 Copilot" in item["query"] for item in wps365["variants"])
    assert any("AI 笔记 AI 知识库 KaaS" in item["query"] for item in adjacent["variants"])
    assert any("MonkeyOCR" in item["query"] for item in adjacent["variants"])
    assert any("企业大脑" in item["query"] or "AI Docs" in item["query"] for item in adjacent["variants"])


def test_wps_ranker_marks_institution_rollout_and_downranks_download_noise():
    quality = {
        "intent": "wps_office",
        "route_intents": ["wps_office"],
        "preferred_scopes": ["wps_office", "university"],
        "preferred_source_types": ["办公软件/AI Office/SaaS", "高校/院系官网", "商业/产业媒体"],
        "route_evidence_roles": ["company_primary", "institution_rollout", "industry_report"],
    }
    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="WPS灵犀 使用说明-西南财经大学-信息化与数据管理处",
                url="https://info.swufe.edu.cn/info/1024/2861.htm",
                snippet="WPS灵犀上线，面向师生提供使用说明。",
                source="fixture",
                rank=1,
            ),
            webtools.SearchResult(
                title="WPS AI 正式版下载 WPS AI V12.1 for Windows 官方最新安装版",
                url="https://www.jb51.net/softs/887904.html",
                snippet="软件下载、安装包、最新版下载。",
                source="fixture",
                rank=2,
            ),
            webtools.SearchResult(
                title="从工具到智能体 WPS 365 公布 AI 协同平台路线图",
                url="https://news.qq.com/rain/a/demo",
                snippet="WPS 365 企业大脑、办公智能体和组织协同平台。",
                source="fixture",
                rank=3,
            ),
            webtools.SearchResult(
                title="2026实测 6款主流 AI 自动生成 PPT 工具横评 职场效率拉满",
                url="https://www.example.com/ai-ppt-roundup",
                snippet="对比 Gamma、Canva、Tome、WPS 等 AI PPT 工具，覆盖汇报和职场效率场景。",
                source="fixture",
                rank=4,
            ),
            webtools.SearchResult(
                title="WPS AI 怎么领取？3步开启智能写作与PDF处理超省力",
                url="https://jianghu.taobao.com/guanglocal/demo",
                snippet="入口打开、怎么领取、怎么设置。",
                source="fixture",
                rank=5,
            ),
        ],
        query="WPS AI",
        backend_order=["fixture"],
        preferred_scope="wps_office",
        quality=quality,
    )

    institution = next(item for item in ranked if "swufe" in item.url)
    download = next(item for item in ranked if "jb51" in item.url)
    industry = next(item for item in ranked if "news.qq.com" in item.url)
    ai_ppt_roundup = next(item for item in ranked if "ai-ppt-roundup" in item.url)
    light_tutorial = next(item for item in ranked if "jianghu.taobao.com" in item.url)
    assert institution.evidence_role == "institution_rollout"
    assert download.evidence_role == "low_value_seo"
    assert industry.evidence_role == "industry_report"
    assert ai_ppt_roundup.evidence_role == "industry_report"
    assert light_tutorial.evidence_role == "low_value_seo"
    assert institution.score > download.score
    assert download.score_parts["semantic_noise_penalty"] <= -1.15
    assert ai_ppt_roundup.score > light_tutorial.score


def test_query_strategy_builds_university_admissions_variants():
    route = webtools.build_route_plan("清华大学计算机系研究生招生 导师名单", profile="china").to_dict()
    strategy = webtools.build_query_strategy("清华大学计算机系研究生招生 导师名单", route_plan=route)

    roles = {item["role"] for item in strategy["variants"]}
    assert "university_official" in roles
    assert "department_page" in roles
    assert "admission_catalog" in roles


def test_academic_query_penalizes_ei_math_noise():
    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="What is operatorname Ei(x)?",
                url="https://math.stackexchange.com/questions/1",
                snippet="Ei is a special function.",
                source="bing",
                rank=1,
            ),
            webtools.SearchResult(
                title="Engineering Village Databases Compendex Elsevier",
                url="https://www.elsevier.com/products/engineering-village/databases/compendex",
                snippet="Compendex is an engineering-focused database.",
                source="duckduckgo",
                rank=2,
            ),
        ],
        query="EI会议 投稿 检索 要求",
        quality=webtools.detect_search_quality_profile("EI会议 投稿 检索 要求", profile="china"),
    )

    assert ranked[0].domain == "elsevier.com"
    assert ranked[-1].score_parts["semantic_noise_penalty"] < 0


def test_university_admissions_query_promotes_named_school_entity():
    quality = webtools.detect_search_quality_profile("北部湾大学 计算机学院 研究生招生 导师", profile="china")
    route = webtools.build_route_plan("北部湾大学 计算机学院 研究生招生 导师", profile="china").to_dict()
    quality = webtools._quality_with_route_plan(quality, route)

    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="2026年计算机学院研究生招生团队及导师目录",
                url="https://scs.bupt.edu.cn/info/1020/3951.htm",
                snippet="计算机学院导师联系方式、研究方向列表。",
                source="duckduckgo",
                rank=1,
            ),
            webtools.SearchResult(
                title="导师队伍-北部湾大学研究生院",
                url="https://yjs.bbgu.edu.cn/pygz/dsdw.htm",
                snippet="北部湾大学研究生导师队伍与招生培养信息。",
                source="duckduckgo",
                rank=2,
            ),
        ],
        query="北部湾大学 计算机学院 研究生招生 导师",
        quality=quality,
    )

    assert ranked[0].domain == "yjs.bbgu.edu.cn"
    assert ranked[0].score_parts["entity_match"] > 0
    assert ranked[1].score_parts["entity_mismatch_penalty"] < 0


def test_university_admissions_penalizes_parent_university_for_affiliated_college():
    quality = webtools.detect_search_quality_profile("南京师范大学中北学院 计算机学院 研究生招生 导师", profile="china")
    route = webtools.build_route_plan("南京师范大学中北学院 计算机学院 研究生招生 导师", profile="china").to_dict()
    quality = webtools._quality_with_route_plan(quality, route)

    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="硕士生导师-南京师范大学计算机与电子信息学院",
                url="https://ceai.njnu.edu.cn/yjsjy/sssds.htm",
                snippet="南京师范大学硕士生导师名单。",
                source="duckduckgo",
                rank=1,
            ),
            webtools.SearchResult(
                title="南京师范大学中北学院",
                url="https://www.nnudy.edu.cn/",
                snippet="南京师范大学中北学院官网。",
                source="duckduckgo",
                rank=2,
            ),
        ],
        query="南京师范大学中北学院 计算机学院 研究生招生 导师",
        quality=quality,
    )

    assert ranked[0].domain == "nnudy.edu.cn"
    assert ranked[1].score_parts["entity_mismatch_penalty"] <= -2.0


def test_format_search_trace_shows_query_quality(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(
                title="国务院发布人工智能政策通知",
                url="https://gov.cn/zhengce/ai.htm",
                snippet="最新政策",
            )
        ],
    )

    results = webtools.search_web("人工智能 政策 最新", backend="duckduckgo", trace=True)
    trace = webtools.format_search_trace(results)

    assert "query_quality: intent=policy" in trace
    assert "quality_fit=True" in trace


def test_search_quality_summary_suggests_missing_roles():
    summary = webtools.search_quality_summary(
        [
            {
                "title": "通用网页",
                "url": "https://example.com/a",
                "source_type": "通用网页",
                "domain": "example.com",
                "evidence_role": "open_web_context",
            }
        ],
        quality={
            "preferred_source_types": ["政府/部委"],
            "preferred_scopes": ["gov"],
            "route_evidence_roles": ["official_primary"],
        },
    )

    assert summary["missing_roles"] == ["official_primary"]
    assert summary["status"] == "warn"
    assert summary["quality_status"] == "quality_strict"
    assert "Guanlan 已找到线索" in summary["user_facing_status"]
    assert "缺少 `official_primary`" in "；".join(summary["why_cautious"])
    assert summary["agent_workflow_plan"]["tier"] == "3-step"
    assert summary["agent_workflow_plan"]["minimum_guanlan_tools"] == 3
    assert summary["agent_workflow_plan"]["tool_sequence"][:3] == ["route", "research", "search"]
    assert summary["agent_execution_policy"]["should_run_followups"] is True
    assert summary["agent_execution_policy"]["mode"] == "run_followups_now"
    assert "不要停在建议" in summary["agent_execution_policy"]["instruction"]
    assert "至少 3 个最适合的 Guanlan 工具步骤" in summary["agent_execution_policy"]["instruction"]
    assert any(action["label"] == "查看路由计划" for action in summary["followup_actions"])
    assert all(action["run_policy"] == "run_immediately" for action in summary["followup_actions"])
    assert any("guanlan research" in action["command"] for action in summary["followup_actions"])
    assert "质量画像" in summary["interpretation"]
    assert any("guanlan route" in item for item in summary["guanlan_next_steps"])
    assert any("不要只看开放网页" in item for item in summary["guanlan_next_steps"])
    assert any("不要向 AI 使用者概括为" in item for item in summary["agent_reporting_contract"])
    assert any("抽风" in item and "崩了" in item for item in summary["agent_reporting_contract"])
    assert any("定点补证路线" in item for item in summary["agent_reporting_contract"])
    assert any("未完全通过质量画像" in item for item in summary["agent_reporting_contract"])
    assert any("scope gov" in item for item in summary["suggestions"])
    assert summary["agent_decision"]["code"] == "needs_scope_search"
    assert summary["agent_decision"]["should_answer"] is False


def test_search_quality_summary_treats_strong_primary_evidence_as_usable_with_gaps():
    summary = webtools.search_quality_summary(
        [
            {
                "title": "国务院人工智能政策通知",
                "url": "https://www.gov.cn/zhengce/ai.htm",
                "source_type": "政府/部委",
                "matched_scope": "gov",
                "domain": "gov.cn",
                "evidence_role": "official_primary",
                "trust_level": 5,
            }
        ],
        quality={
            "intent": "policy",
            "preferred_source_types": ["政府/部委"],
            "preferred_scopes": ["gov"],
            "route_evidence_roles": ["official_primary", "authoritative_report", "public_discussion"],
        },
    )

    assert summary["missing_roles"] == ["authoritative_report", "public_discussion"]
    assert summary["strong_primary_evidence"] is True
    assert summary["quality_status"] == "usable_with_gaps"
    assert summary["agent_workflow_plan"]["tier"] == "2-step"
    assert summary["agent_execution_policy"]["mode"] == "continue_or_read"
    assert summary["agent_execution_policy"]["should_run_followups"] is False
    assert summary["followup_actions"][0]["tool"] == "read"
    assert summary["agent_decision"]["code"] == "usable_with_gaps"
    assert summary["agent_decision"]["should_answer"] is True


def test_search_quality_gate_detects_low_value_baidu_pollution():
    batch = [
        webtools.SearchResult(
            title="苹果客服电话24小时人工服务热线是多少？_百度知道",
            url="https://zhidao.baidu.com/question/1120136526299781379.html",
            snippet="客服电话、人工服务、号码是多少",
            source="bing",
            rank=1,
        ),
        webtools.SearchResult(
            title="苹果售后人工服务号码是多少？",
            url="https://jingyan.baidu.com/article/demo.html",
            snippet="24小时 电话 客服",
            source="bing",
            rank=2,
        ),
        webtools.SearchResult(
            title="苹果手机使用经验",
            url="https://baijiahao.baidu.com/s?id=demo",
            snippet="客服电话 官网入口",
            source="bing",
            rank=3,
        ),
    ]

    gate = webtools._assess_backend_batch_quality("人工智能 政策", batch, {"intent": "policy"})

    assert gate["usable"] is False
    assert "low_value_domain_pollution" in gate["reason"]
    assert gate["pollution"]["severity"] == "high"
    assert gate["pollution"]["polluted_count"] == 3


def test_search_quality_gate_detects_dictionary_definition_drift():
    batch = [
        webtools.SearchResult(
            title="胖_百度百科",
            url="https://baike.baidu.com/item/%E8%83%96/1",
            snippet="胖，汉语一级字，基本解释为人体脂肪多。",
            source="bing",
            rank=1,
        ),
        webtools.SearchResult(
            title="酱_汉典",
            url="https://www.hydcd.com/zidian/hz/12345.htm",
            snippet="酱的拼音、部首、组词和详细解释。",
            source="bing",
            rank=2,
        ),
        webtools.SearchResult(
            title="劳动_爱词霸",
            url="https://www.iciba.com/word?w=%E5%8A%B3%E5%8A%A8",
            snippet="劳动的意思、读音、用法和英译。",
            source="bing",
            rank=3,
        ),
    ]

    gate = webtools._assess_backend_batch_quality("胖东来模式", batch, {"intent": "industry"})

    assert gate["usable"] is False
    assert "low_value_domain_pollution" in gate["reason"]
    assert gate["pollution"]["severity"] == "high"
    assert gate["pollution"]["polluted_count"] == 3


def test_search_trace_exposes_pollution_and_agent_decision(monkeypatch):
    def polluted_bing(query, limit=10):
        return [
            webtools.SearchResult(
                title="苹果客服电话24小时人工服务热线是多少？_百度知道",
                url="https://zhidao.baidu.com/question/1120136526299781379.html",
                snippet="客服电话、人工服务、号码是多少",
                source="bing",
                rank=1,
            ),
            webtools.SearchResult(
                title="苹果售后人工服务号码是多少？",
                url="https://jingyan.baidu.com/article/demo.html",
                snippet="24小时 电话 客服",
                source="bing",
                rank=2,
            ),
            webtools.SearchResult(
                title="苹果手机使用经验",
                url="https://baijiahao.baidu.com/s?id=demo",
                snippet="客服电话 官网入口",
                source="bing",
                rank=3,
            ),
        ]

    def official_duckduckgo(query, limit=10):
        return [
            webtools.SearchResult(
                title="国务院关于人工智能政策的通知",
                url="https://www.gov.cn/zhengce/ai.htm",
                snippet="人工智能 政策 官方 原文 通知",
                source="duckduckgo",
                rank=1,
            )
        ]

    def fake_backend(name, query, *, limit, network_mode="auto", profile=None):
        if name == "bing":
            return polluted_bing(query, limit=limit), [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        if name == "bing_generic":
            return [], [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        if name == "duckduckgo":
            return official_duckduckgo(query, limit=limit), [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        raise AssertionError(name)

    monkeypatch.setattr(webtools, "backend_order", lambda *_args, **_kwargs: ["bing", "duckduckgo"])
    monkeypatch.setattr(webtools, "_search_backend_with_network", fake_backend)

    results = webtools.search_web("人工智能 政策", backend="auto", profile="china", trace=True)
    rendered = webtools.format_search_trace(results)

    assert results[0]["trace"]["backend_diagnostics"][0]["quality_gate"]["pollution"]["severity"] == "high"
    assert results[0]["trace"]["quality_summary"]["agent_decision"]["code"] == "usable_with_gaps"
    assert "backend_pollution:bing" in rendered
    assert "agent_decision: code=usable_with_gaps" in rendered


def test_cjk_compound_terms_keep_chinese_search_intent():
    terms = webtools._query_relevance_terms("人工智能政策")

    assert "人工智能" in terms
    assert "人工智能政策" in terms


def test_cjk_relevance_terms_split_compounds_but_ignore_recency_words():
    terms = webtools._query_relevance_terms("品牌设计趋势 2025 今天")

    assert {"品牌", "设计", "趋势"} <= set(terms)
    assert "今天" not in terms


def test_search_quality_summary_upgrades_tech_queries_to_four_step_workflow():
    summary = webtools.search_quality_summary(
        [
            {
                "title": "开发者博客",
                "url": "https://example.com/a",
                "source_type": "通用网页",
                "domain": "example.com",
                "evidence_role": "open_web_context",
            }
        ],
        quality={
            "intent": "tech",
            "route_intents": ["tech"],
            "preferred_source_types": ["开发者社区/技术博客"],
            "preferred_scopes": ["tech_dev"],
            "route_evidence_roles": ["developer_discussion"],
        },
    )

    assert summary["agent_workflow_plan"]["tier"] == "4-step"
    assert summary["agent_workflow_plan"]["minimum_guanlan_tools"] == 4
    assert "feeds" in summary["agent_workflow_plan"]["tool_sequence"]
    assert any(action["tool"] == "feeds" for action in summary["followup_actions"])
    assert "至少 4 个最适合的 Guanlan 工具步骤" in summary["agent_execution_policy"]["instruction"]


def test_search_web_detects_recency_intent():
    intent = webtools.detect_recency_intent("最近 AI 热点")

    assert intent["enabled"] is True
    assert intent["window_days"] <= 30
    assert set(intent["matched_terms"]) & {"最近", "热点"}
    assert intent["start_date"]
    assert intent["end_date"]


def test_search_web_detects_year_to_date_recency():
    intent = webtools.detect_recency_intent("今年 跨境电商 趋势")

    assert intent["enabled"] is True
    assert intent["label"] == "year_to_date"
    assert intent["start_date"].endswith("-01-01")


def test_search_web_recency_intent_does_not_match_english_substrings():
    intent = webtools.detect_recency_intent("knowledge graph")

    assert intent["enabled"] is False


def test_search_web_recency_augments_query_and_trace(monkeypatch):
    requested = []
    today = webtools.dt.date.today()

    def fake_search(query, limit=10):
        requested.append(query)
        return [
            webtools.SearchResult(
                title=f"AI 热点 {today.year}年{today.month}月{today.day}日",
                url="https://example.com/fresh",
                snippet="今日最新进展",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web("最近 AI 热点", backend="duckduckgo", trace=True)

    assert str(today.year) in requested[0]
    assert "最新" in requested[0]
    assert results[0]["trace"]["recency"]["enabled"] is True
    assert results[0]["trace"]["recency"]["in_window"] is True
    assert results[0]["score_parts"]["recency_boost"] > 0


def test_rank_results_penalizes_stale_results_for_recent_query():
    today = webtools.dt.date.today()
    fresh_date = f"{today.year}年{today.month}月{today.day}日"
    recency = webtools.detect_recency_intent("最新 AI 进展")

    results = webtools.rank_results(
        [
            webtools.SearchResult(
                title="AI 进展 2021年1月1日",
                url="https://example.com/old",
                source="bing",
                rank=1,
            ),
            webtools.SearchResult(
                title=f"AI 进展 {fresh_date}",
                url="https://example.com/new",
                source="duckduckgo",
                rank=2,
            ),
        ],
        query="最新 AI 进展",
        backend_order=["bing", "duckduckgo"],
        recency=recency,
    )

    assert results[0].url == "https://example.com/new"
    assert results[0].score_parts["recency_boost"] > 0
    assert results[1].score_parts["stale_penalty"] < 0
    assert results[1].trace["recency"]["in_window"] is False


def test_rank_results_strongly_prefers_explicit_year_window():
    recency = webtools.detect_recency_intent("具身智能 2024 进展")
    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="具身智能 2022年旧闻",
                url="https://example.com/2022/old",
                snippet="历史报道。",
                source="duckduckgo",
                rank=1,
            ),
            webtools.SearchResult(
                title="具身智能 2024年进展",
                url="https://example.com/2024/new",
                snippet="年度进展。",
                source="bing",
                rank=2,
            ),
        ],
        query="具身智能 2024 进展",
        recency=recency,
    )

    assert ranked[0].url == "https://example.com/2024/new"
    assert ranked[0].score_parts["time_constraint_fit"] > 0
    assert ranked[1].score_parts["time_constraint_penalty"] < 0
    assert ranked[0].trace["recency"]["in_window"] is True


def test_rank_results_promotes_quality_fit_for_policy_query():
    results = webtools.rank_results(
        [
            webtools.SearchResult(
                title="知乎热议人工智能政策",
                url="https://zhihu.com/question/ai-policy",
                snippet="网友讨论人工智能政策最新影响",
                source="duckduckgo",
                rank=1,
            ),
            webtools.SearchResult(
                title="国务院发布人工智能政策通知",
                url="https://www.gov.cn/zhengce/ai.htm",
                snippet="国务院发布人工智能相关政策通知",
                source="bing",
                rank=2,
            ),
        ],
        query="人工智能 政策 最新",
        backend_order=["duckduckgo", "bing"],
    )

    assert results[0].domain == "gov.cn"
    assert results[0].score_parts["intent_fit"] > 0
    assert results[0].trace["quality"]["matched_reason"] == "scope:gov"


def test_search_quality_fixture_rankings():
    fixture_path = Path(__file__).parent / "fixtures" / "search_quality" / "scenarios.json"
    scenarios = json.loads(fixture_path.read_text(encoding="utf-8"))

    for scenario in scenarios:
        ranked = webtools.rank_results(
            [
                webtools.SearchResult(
                    title=row["title"],
                    url=row["url"],
                    snippet=row.get("snippet", ""),
                    source=row.get("source", "fixture"),
                    rank=row.get("rank", idx),
                )
                for idx, row in enumerate(scenario["results"], start=1)
            ],
            query=scenario["query"],
        )
        assert ranked[0].domain == scenario["expected_first_domain"], scenario["name"]


def test_search_auto_network_falls_back_to_proxy_and_redacts_credentials(monkeypatch):
    monkeypatch.setenv("GUANLAN_PROXY_URL", "http://user:pass@127.0.0.1:7890")
    monkeypatch.setattr(webtools, "_NETWORK_HEALTH_CACHE", {})
    seen_modes = []

    def fake_bing(query, limit=10, network_mode="current"):
        seen_modes.append(network_mode)
        if network_mode != "proxy":
            raise TimeoutError("timed out")
        return [
            webtools.SearchResult(
                title="Agent search result",
                url="https://example.com/network",
                snippet="agent search result",
                source="bing",
            )
        ]

    monkeypatch.setattr(webtools, "_search_bing", fake_bing)

    results = webtools.search_web("agent search", backend="bing", profile="english", trace=True)

    assert seen_modes == ["current", "proxy"]
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert diagnostics[0]["status"] == "ok"
    assert diagnostics[0]["network_mode"] == "proxy"
    assert diagnostics[0]["network_attempts"][0]["status"] == "network_unreachable"
    assert diagnostics[0]["network_attempts"][1]["status"] == "ok"
    network_profile = results[0]["trace"]["network_profile"]
    assert network_profile["proxy_detected"] is True
    assert network_profile["proxy"] == "http://***@127.0.0.1:7890"
    assert "user:pass" not in json.dumps(network_profile)


def test_search_direct_network_bypasses_proxy_auto_fallback(monkeypatch):
    monkeypatch.setenv("GUANLAN_PROXY_URL", "http://127.0.0.1:7890")
    seen_modes = []

    def fake_duckduckgo(query, limit=10, network_mode="current"):
        seen_modes.append(network_mode)
        return [
            webtools.SearchResult(
                title="Direct network result",
                url="https://example.com/direct",
                snippet="direct network result",
                source="duckduckgo",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_duckduckgo)

    results = webtools.search_web(
        "direct network result",
        backend="duckduckgo",
        network_mode="direct",
        trace=True,
    )

    assert seen_modes == ["direct"]
    assert results[0]["trace"]["backend_diagnostics"][0]["network_mode"] == "direct"


def test_search_trace_marks_network_failure_as_not_empty_evidence(monkeypatch):
    monkeypatch.delenv("GUANLAN_PROXY_URL", raising=False)
    monkeypatch.setattr(webtools, "_NETWORK_HEALTH_CACHE", {})

    def fake_duckduckgo(query, limit=10, network_mode="current"):
        raise TimeoutError("timed out")

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_duckduckgo)

    results = webtools.search_web("network failure", backend="duckduckgo", trace=True)
    trace = webtools.format_search_trace(results)

    assert not results
    assert results.diagnostics["backend_diagnostics"][0]["status"] == "network_unreachable"
    assert "network_unreachable" in trace
    assert "不要汇报为无资料" in trace


def test_research_uses_role_specific_query_variants(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append((query, kwargs))
        return [
            {
                "title": query,
                "url": f"https://example.com/{len(calls)}",
                "source_type": "通用网页",
                "score": 1.0,
            }
        ]

    monkeypatch.setattr(webtools, "search_web", fake_search)

    webtools.build_research_packet("人工智能监管 政策 最新", preset="policy", limit=12, read_top=0)

    queries = [query for query, _kwargs in calls]
    assert any("官方 原文 通知" in query for query in queries)
    assert any("最新" in query for query in queries)


def test_research_search_uses_light_recovery_for_subroutes(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(webtools, "search_web", fake_search)

    webtools.build_research_packet("人工智能监管", preset="policy", read_top=0)

    assert [call["scope"] for call in calls] == ["gov", "party_central", None]
    assert [call["recovery_mode"] for call in calls] == ["lite", "lite", "auto"]


def test_rank_results_downranks_calendar_noise_for_ai_release_query():
    results = webtools.rank_results(
        [
            webtools.SearchResult(
                title="April 2026 Calendar",
                url="https://www.timeanddate.com/calendar/monthly.html?year=2026&month=4",
                snippet="Calendar for April 2026 with holidays and moon phases.",
                source="duckduckgo",
                rank=1,
            ),
            webtools.SearchResult(
                title="April 2026 LLM model release roundup: GPT and Claude updates",
                url="https://example.com/llm-release",
                snippet="Analysis of AI model release notes.",
                source="duckduckgo",
                rank=2,
            ),
        ],
        query="2026 April LLM release global AI model",
        backend_order=["duckduckgo"],
    )

    assert results[0].url == "https://example.com/llm-release"
    calendar = next(item for item in results if "timeanddate" in item.url)
    assert calendar.score_parts["semantic_noise_penalty"] < 0
