# -*- coding: utf-8 -*-
"""Tests for agent-facing search and read primitives."""

import builtins
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from guanlan import webtools
from guanlan.limits import DEFAULT_READ_FALLBACK_LIMIT, DEFAULT_RESEARCH_LIMIT, DEFAULT_SEARCH_LIMIT
from guanlan.source_seeds import direct_source_seeds, is_finance_lookup, is_live_sports_lookup


class _FakeResponse:
    def __init__(self, text: str, content_type: str = "text/html"):
        self._text = text
        self.headers = {"content-type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        return self._text.encode()


def test_search_web_parses_duckduckgo_html(monkeypatch):
    html = """
    <html>
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Example A</a>
      <a class="result__snippet">First snippet</a>
      <a class="result__a" href="https://example.com/b">Example B</a>
    </html>
    """

    seen_timeouts = []

    def fake_urlopen(req, timeout=None):
        seen_timeouts.append(timeout)
        return _FakeResponse(html)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    results = webtools.search_web("agent search", backend="duckduckgo", limit=5)

    assert len(results) == 2
    assert results[0]["title"] == "Example A"
    assert results[0]["url"] == "https://example.com/a"
    assert results[0]["snippet"] == "First snippet"
    assert results[0]["rank"] == 1
    assert results[0]["domain"] == "example.com"
    assert results[0]["source_type"] == "通用网页"
    assert results[0]["score"] > 0
    assert seen_timeouts == [webtools._SEARCH_TIMEOUT]


def test_search_web_trace_keeps_score_parts(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(title="Agent search result", url="https://example.com/a")
        ],
    )

    results = webtools.search_web("agent search", backend="duckduckgo", trace=True)

    assert "score_parts" in results[0]
    assert results[0]["score_parts"]["keyword_match"] > 0
    assert results[0]["trace"]["cache"] == "disabled"


def test_search_quality_profile_detects_policy_intent():
    quality = webtools.detect_search_quality_profile("人工智能 政策 最新", profile="china")

    assert quality["intent"] == "policy"
    assert "gov" in quality["preferred_scopes"]
    assert "政府/部委" in quality["preferred_source_types"]


def test_search_quality_profile_detects_academic_intent():
    quality = webtools.detect_search_quality_profile("EI会议 投稿 检索 要求", profile="china")

    assert quality["intent"] == "academic"
    assert "academic" in quality["preferred_scopes"]
    assert "学术/论文检索" in quality["preferred_source_types"]


def test_search_quality_profile_detects_university_admissions_intent():
    quality = webtools.detect_search_quality_profile("清华大学计算机系研究生招生 导师名单", profile="china")

    assert quality["intent"] == "university_admissions"
    assert "university" in quality["preferred_scopes"]
    assert "高校/院系官网" in quality["preferred_source_types"]
    assert "院系官网" in quality["guidance"]


def test_search_quality_profile_detects_entertainment_intent():
    quality = webtools.detect_search_quality_profile("哪吒2 票房 豆瓣评分 最近热议", profile="china")

    assert quality["intent"] == "entertainment"
    assert "entertainment" in quality["preferred_scopes"]
    assert "文娱/内容平台" in quality["preferred_source_types"]
    assert "单平台热度" in quality["guidance"]


def test_search_quality_profile_routes_magic_school_manga_to_entertainment():
    quality = webtools.detect_search_quality_profile("魔法学院日常漫画 治愈系 魔女", profile="china")

    assert quality["intent"] == "entertainment"
    assert "entertainment" in quality["preferred_scopes"]
    assert "漫画" in quality["matched_terms"]
    assert any("acg_disambiguation" in reason for reason in quality["reasons"])


def test_search_quality_profile_keeps_real_school_queries_in_university_lane():
    quality = webtools.detect_search_quality_profile("南京师范大学中北学院 计算机 导师 招生", profile="china")

    assert quality["intent"] == "university_admissions"
    assert "university" in quality["preferred_scopes"]
    assert any(term in {"导师", "招生"} for term in quality["matched_terms"])


def test_search_quality_profile_detects_global_entertainment_intent():
    quality = webtools.detect_search_quality_profile("Taylor Swift latest album tour", profile="english")

    assert quality["intent"] == "global_entertainment"
    assert "global_entertainment" in quality["preferred_scopes"]
    assert "欧美文娱/音乐产业" in quality["preferred_source_types"]


def test_search_quality_profile_detects_jp_kr_entertainment_intent():
    quality = webtools.detect_search_quality_profile("BLACKPINK K-pop comeback Soompi", profile="hybrid")

    assert quality["intent"] == "jp_kr_entertainment"
    assert "jp_kr_entertainment" in quality["preferred_scopes"]
    assert "日韩文娱/K-pop/J-pop" in quality["preferred_source_types"]


def test_search_quality_profile_detects_new_route_intents():
    cases = [
        ("OpenSSL CVE 最新 漏洞 影响 版本 修复", "cybersecurity", "网络安全/漏洞/反诈"),
        ("台风 路径 最新 中央气象台 日本气象厅", "weather_disaster", "天气/灾害/预警"),
        ("梅西 今天比赛 数据 伤病 最新", "sports", "体育/赛事/转会"),
        ("詹姆斯韦伯 发现 外星生命 真的假的 NASA", "science", "科学机构/科研新闻"),
        ("字节 AI 产品经理 校招 薪资 面经", "career", "招聘/职场/薪资"),
        ("最近 有哪些讲 AI 创业 的中文播客 小宇宙", "podcast", "播客/音频/RSS"),
        ("雅思 口语 2026 题库 机经 靠谱吗", "test_prep", "考试/培训/备考"),
        ("宁德时代 股价 财报 公告 最近风险", "finance", "财经/公告披露"),
    ]

    for query, intent, source_type in cases:
        quality = webtools.detect_search_quality_profile(query, profile="china")
        assert quality["intent"] == intent
        assert source_type in quality["preferred_source_types"]


def test_direct_source_seeds_cover_vertical_lookups_without_treating_dev_tasks_as_scores():
    nba_seeds = direct_source_seeds(
        "NBA季后赛2026年首轮战绩比分",
        intents=["sports"],
        scopes=["sports"],
    )
    weather_seeds = direct_source_seeds("台风 路径 最新 中央气象台 日本气象厅", intents=["weather_disaster"])
    security_seeds = direct_source_seeds("CVE-2026-12345 OpenSSL 漏洞 影响版本", intents=["cybersecurity"])

    assert any("espn.com/nba/story" in item["url"] for item in nba_seeds)
    assert any("nmc.cn" in item["url"] for item in weather_seeds)
    assert any("CVE-2026-12345" in item["url"] for item in security_seeds)
    assert is_live_sports_lookup("NBA季后赛2026年首轮战绩比分", intents=["sports"])
    assert not is_live_sports_lookup("NBA API 开源项目 教程", intents=["tech", "sports"])


def test_direct_source_seeds_cover_acg_entrypoints():
    seeds = direct_source_seeds(
        "魔法学院日常漫画 治愈系 魔女",
        intents=["entertainment"],
        scopes=["entertainment"],
    )

    urls = {item["url"] for item in seeds}
    assert any("bgm.tv/subject_search" in url for url in urls)
    assert any("pixiv.net/tags/" in url for url in urls)
    assert any("mangapedia.com" in url for url in urls)


def test_direct_source_seeds_cover_finance_layers():
    seeds = direct_source_seeds(
        "贵州茅台 600519 股价 财报 公告 雪球",
        intents=["finance"],
        scopes=["finance"],
        limit=8,
    )

    assert is_finance_lookup("贵州茅台 600519 股价 财报 公告 雪球", intents=["finance"])
    assert any(item["matched_scope"] == "finance_quote" and "quote.eastmoney.com/sh600519" in item["url"] for item in seeds)
    assert any(item["matched_scope"] == "finance_disclosure" and "cninfo.com.cn" in item["url"] for item in seeds)
    assert any(item["matched_scope"] == "finance_sentiment" and "xueqiu.com" in item["url"] for item in seeds)
    assert any(item["evidence_role"] == "company_filing" for item in seeds)


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

    assert len(results) == 1
    assert captured_queries[0].startswith("(")
    assert captured_queries[1].startswith("OpenSSL CVE latest affected versions")
    assert "retried the original query" in results[0]["trace"]["backend_diagnostics"][0]["note"]


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
    assert any("limit 10" in warning for warning in results[0]["trace"]["quality_summary"]["warnings"])


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

    assert "technical_primary" in {item["role"] for item in tech["variants"]}
    assert "review" in {item["role"] for item in ecommerce["variants"]}
    finance_roles = {item["role"] for item in finance["variants"]}
    assert "company_filing" in finance_roles
    assert "regulatory_notice" in finance_roles
    assert "market_news" in finance_roles


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


def test_search_ranking_penalizes_non_chinese_drift_for_chinese_reputation_query():
    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="Leo Jiménez Stats, Height, Weight, Position",
                url="https://www.baseball-reference.com/players/j/jimenle01.shtml",
                snippet="Baseball player statistics",
                source="fixture",
                rank=1,
            ),
            webtools.SearchResult(
                title="国产新能源车到底值不值得买？用了3年，谈谈我的使用感受",
                url="https://zhuanlan.zhihu.com/p/123",
                snippet="车主评价、体验、优缺点和购买建议",
                source="fixture",
                rank=2,
            ),
        ],
        query="某新能源车 用户评价 值不值得买",
    )

    assert ranked[0].domain == "zhuanlan.zhihu.com"
    assert ranked[1].score_parts["language_mismatch_penalty"] < 0


def test_search_web_cache_ttl_reuses_results(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(webtools, "cache_dir", lambda: tmp_path / "cache")

    def fake_search(query, limit=10):
        calls.append(query)
        return [webtools.SearchResult(title="Cached", url="https://example.com/cache")]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    first = webtools.search_web("cache query", backend="duckduckgo", cache_ttl=3600, trace=True)
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: (_ for _ in ()).throw(RuntimeError("network should not run")),
    )
    second = webtools.search_web("cache query", backend="duckduckgo", cache_ttl=3600, trace=True)

    assert len(calls) == 1
    assert first[0]["title"] == "Cached"
    assert second[0]["title"] == "Cached"
    assert second[0]["trace"]["cache"] == "hit"


def test_search_web_plugin_backend(tmp_path):
    plugin = tmp_path / "plugin_backend.py"
    plugin.write_text(
        "import json, sys\n"
        "query = sys.argv[1]\n"
        "print(json.dumps([{'title': 'Plugin ' + query, 'url': 'https://internal.example/a', 'snippet': 'S'}]))\n",
        encoding="utf-8",
    )

    results = webtools.search_web("knowledge", backend=f"plugin:{plugin}", limit=1)

    assert results[0]["title"] == "Plugin knowledge"
    assert results[0]["source"].startswith("plugin:")


def test_search_web_uses_china_backend_order():
    assert webtools.backend_order("auto", "china") == ["baidu", "bing", "duckduckgo"]


def test_bing_cjk_drift_cooldown_lowers_auto_priority(monkeypatch):
    monkeypatch.setattr(webtools, "_BING_CJK_DRIFT_UNTIL", 9999999999.0)

    assert webtools.backend_order("auto", "china", query="固态电池量产时间表") == [
        "baidu",
        "duckduckgo",
        "bing",
    ]
    assert webtools.backend_order("auto", "china") == ["baidu", "bing", "duckduckgo"]


def test_bing_cjk_drift_cooldown_persists_for_cli_processes(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_TEST_ALLOW_BACKEND_HEALTH", "1")
    monkeypatch.setattr(webtools, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(webtools, "_BING_CJK_DRIFT_UNTIL", 0.0)

    assert webtools._bing_cjk_drift_active() is False
    webtools._record_bing_cjk_drift()

    monkeypatch.setattr(webtools, "_BING_CJK_DRIFT_UNTIL", 0.0)
    assert webtools._bing_cjk_drift_active() is True
    assert webtools.backend_order("auto", "china", query="低空经济政策补贴") == [
        "baidu",
        "duckduckgo",
        "bing",
    ]


def test_search_web_resolves_cjk_ai_query_to_china_profile(monkeypatch):
    requested = []

    def fake_baidu(query, limit=10):
        requested.append(("baidu", query))
        return [webtools.SearchResult(title="AI 中文结果", url="https://example.cn/ai", source="baidu")]

    monkeypatch.setattr(webtools, "_search_baidu", fake_baidu)
    monkeypatch.setattr(webtools, "_search_bing", lambda query, limit=10: [])
    monkeypatch.setattr(webtools, "_search_duckduckgo", lambda query, limit=10: [])

    results = webtools.search_web("AI 相关内容", trace=True)

    assert requested and requested[0][0] == "baidu"
    assert results[0]["trace"]["backend_order"] == ["baidu", "bing", "duckduckgo"]
    assert results[0]["trace"]["query_quality"]["profile"] == "china"


def test_search_web_adds_wechat_sogou_only_for_wechat_site():
    assert webtools.backend_order("auto", "china", site="mp.weixin.qq.com") == [
        "baidu",
        "bing",
        "duckduckgo",
        "wechat-sogou",
    ]
    assert webtools.backend_order("auto", "china", site="zhihu.com") == [
        "baidu",
        "bing",
        "duckduckgo",
    ]


def test_search_web_trace_records_backend_fallback(monkeypatch):
    def parser_miss_baidu(query, limit=10):
        return []

    def blocked_bing(query, limit=10):
        raise RuntimeError("captcha_or_verification: b_captcha")

    def ok_duckduckgo(query, limit=10):
        return [
            webtools.SearchResult(
                title="Fallback result",
                url="https://example.com/a",
                snippet="public result",
                source="duckduckgo",
                rank=1,
            )
        ]

    monkeypatch.setattr(webtools, "_search_baidu", parser_miss_baidu)
    monkeypatch.setattr(webtools, "_search_bing", blocked_bing)
    monkeypatch.setattr(webtools, "_search_duckduckgo", ok_duckduckgo)

    results = webtools.search_web("中文检索", profile="china", trace=True)
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    rendered = webtools.format_search_trace(results)

    assert [item["status"] for item in diagnostics] == ["parser_miss", "blocked", "ok"]
    assert results[0]["trace"]["backend_summary"]["fallback_used"] is True
    recovery = results[0]["trace"]["backend_recovery"]
    assert recovery["status"] == "degraded"
    assert recovery["auto_downgrade"] is True
    assert "duckduckgo" in recovery["active_backends"]
    assert any("--backend duckduckgo" in command for command in recovery["followup_commands"])
    assert "backend_status: baidu=parser_miss, bing=blocked, duckduckgo=ok(1)" in rendered
    assert "backend_recovery: status=degraded" in rendered
    assert "backend_warning" in rendered
    assert "疑似触发验证/反爬" in rendered
    assert "解析器待修而非没有资料" in rendered


def test_search_web_skips_later_backends_when_pool_is_full(monkeypatch):
    def full_baidu(query, limit=10):
        return [
            webtools.SearchResult(
                title=f"Result {idx}",
                url=f"https://example.cn/{idx}",
                snippet="enough candidates",
                source="baidu",
                rank=idx,
            )
            for idx in range(1, limit + 1)
        ]

    def should_skip(query, limit=10):
        raise AssertionError("later backend should be skipped after the pool is full")

    monkeypatch.setattr(webtools, "_search_baidu", full_baidu)
    monkeypatch.setattr(webtools, "_search_bing", should_skip)
    monkeypatch.setattr(webtools, "_search_duckduckgo", should_skip)

    results = webtools.search_web("中文检索", profile="china", limit=DEFAULT_SEARCH_LIMIT, trace=True)
    diagnostics = results[0]["trace"]["backend_diagnostics"]

    assert len(results) == DEFAULT_SEARCH_LIMIT
    assert [item["status"] for item in diagnostics] == ["ok", "skipped", "skipped"]
    assert "避免外层 Agent/MCP 调用超时" in diagnostics[1]["note"]


def test_search_recovery_plan_productizes_baidu_block(monkeypatch):
    def blocked_baidu(query, limit=10):
        raise RuntimeError("captcha_or_verification: 百度安全验证")

    def ok_bing(query, limit=10):
        return [
            webtools.SearchResult(
                title="国务院政策",
                url="https://www.gov.cn/zhengce/a.htm",
                snippet="政策原文",
                source="bing",
                rank=1,
            )
        ]

    monkeypatch.setattr(webtools, "_search_baidu", blocked_baidu)
    monkeypatch.setattr(webtools, "_search_bing", ok_bing)
    monkeypatch.setattr(webtools, "_search_duckduckgo", lambda query, limit=10: [])

    results = webtools.search_web("人工智能 政策", profile="china", trace=True)
    recovery = results[0]["trace"]["backend_recovery"]
    rendered = webtools.format_search_trace(results)

    assert recovery["blocked_backends"] == ["baidu"]
    assert recovery["active_backends"] == ["bing"]
    assert any("不要自动重试" in item for item in recovery["guidance"])
    assert any("--backend bing" in command for command in recovery["followup_commands"])
    assert any("--scope gov" in command for command in recovery["followup_commands"])
    assert "backend_status: baidu=blocked, bing=ok(1), duckduckgo=no_results_or_parser_miss" in rendered
    assert "Baidu 当前被安全验证/反爬拦截" in rendered


def test_search_web_scope_lite_recovers_after_blocked_scoped_query(monkeypatch):
    requested = []

    def blocked_baidu(query, limit=10):
        raise RuntimeError("captcha_or_verification: 百度安全验证")

    def blocked_bing(query, limit=10):
        raise RuntimeError("captcha_or_verification: b_captcha")

    def duckduckgo(query, limit=10):
        requested.append(query)
        if query.startswith("site:gov.cn "):
            return [
                webtools.SearchResult(
                    title="数据要素市场化配置改革政策",
                    url="https://www.gov.cn/zhengce/a.htm",
                    snippet="数据要素 市场化 配置 改革 政策",
                    source="duckduckgo",
                    rank=1,
                )
            ]
        return []

    monkeypatch.setattr(webtools, "_search_baidu", blocked_baidu)
    monkeypatch.setattr(webtools, "_search_bing", blocked_bing)
    monkeypatch.setattr(webtools, "_search_duckduckgo", duckduckgo)

    results = webtools.search_web("数据要素市场化配置改革 最新政策", profile="china", scope="gov", trace=True)
    diagnostics = results[0]["trace"]["backend_diagnostics"]

    assert results[0]["domain"] == "gov.cn"
    assert any(query.startswith("site:gov.cn ") for query in requested)
    assert any(item["backend"] == "duckduckgo:scope_lite" and item["status"] == "ok" for item in diagnostics)


def test_search_web_query_variant_recovers_special_character_query(monkeypatch):
    requested = []

    def duckduckgo(query, limit=10):
        requested.append(query)
        if query == "C++ programming language":
            return [
                webtools.SearchResult(
                    title="C++ programming language",
                    url="https://isocpp.org/",
                    snippet="C++ programming language standard resources",
                    source="duckduckgo",
                    rank=1,
                )
            ]
        return []

    monkeypatch.setattr(webtools, "_search_duckduckgo", duckduckgo)

    results = webtools.search_web("C++", backend="duckduckgo", trace=True)
    diagnostics = results[0]["trace"]["backend_diagnostics"]

    assert "C++ programming language" in requested
    assert results[0]["domain"] == "isocpp.org"
    assert any(item["backend"] == "duckduckgo:query_variant" and item["status"] == "ok" for item in diagnostics)


def test_search_web_continues_after_low_relevance_bing_batch(monkeypatch):
    def blocked_baidu(query, limit=10):
        raise RuntimeError("captcha_or_verification: 百度安全验证")

    def noisy_bing(query, limit=10):
        return [
            webtools.SearchResult(
                title=f"Microsoft Support {idx}",
                url=f"https://support.microsoft.com/en-us/help/{idx}",
                snippet="Contact Microsoft Support and find account help.",
                source="bing",
                rank=idx,
            )
            for idx in range(1, limit + 1)
        ]

    def useful_duckduckgo(query, limit=10):
        return [
            webtools.SearchResult(
                title="智元机器人完成新一轮融资",
                url="https://36kr.com/p/robot",
                snippet="具身智能企业智元、宇树、傅利叶融资和产品动态。",
                source="duckduckgo",
                rank=1,
            )
        ]

    monkeypatch.setattr(webtools, "_search_baidu", blocked_baidu)
    monkeypatch.setattr(webtools, "_search_bing", noisy_bing)
    monkeypatch.setattr(webtools, "_search_bing_generic", lambda query, limit=10: [])
    monkeypatch.setattr(webtools, "_search_duckduckgo", useful_duckduckgo)

    results = webtools.search_web(
        "具身智能 企业 融资 2024 2025 智元 宇树 傅利叶",
        profile="china",
        limit=10,
        trace=True,
    )
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    rendered = webtools.format_search_trace(results)

    assert results[0]["source"] == "duckduckgo"
    assert [item["status"] for item in diagnostics] == ["blocked", "low_relevance", "ok"]
    assert diagnostics[1]["quality_gate"]["reason"]
    assert "support.microsoft.com" in diagnostics[1]["quality_gate"]["top_domain"]
    assert diagnostics[1]["rejected_samples"][0]["domain"] == "support.microsoft.com"
    assert "backend_status: baidu=blocked, bing=low_relevance(10), duckduckgo=ok(1)" in rendered
    assert "相关性门控未通过" in rendered
    assert "rejected_sample:bing => Microsoft Support 1 (support.microsoft.com)" in rendered


def test_search_quality_gate_keeps_official_cjk_compound_results():
    batch = [
        webtools.SearchResult(
            title="关于开展横琴粤澳深度合作区2025年下半年跨境电商产业扶持申报工作的通知",
            url="https://www.hengqin.gov.cn/macao_zh_hans/zwgk/tzgg/gg/content/post_3871318.html",
            snippet="促进跨境电商产业高质量发展扶持办法 申报指南",
            source="baidu",
            rank=1,
        ),
        webtools.SearchResult(
            title="珠海政务-2025跨境电商年会（珠海—横琴）开幕",
            url="https://www.zhuhai.gov.cn/sjb/xw/yw/content/post_3838670.html",
            snippet="珠海跨境电商进出口规模年均增长超100%",
            source="duckduckgo",
            rank=2,
        ),
    ]

    gate = webtools._assess_backend_batch_quality(
        "珠海横琴 跨境电商政策 2025",
        batch,
        {"intent": "scope:gov", "requested_scope": "gov"},
    )

    assert gate["usable"] is True
    assert gate["group_coverage"] >= 0.66
    assert "cross_border_ecommerce" in gate["matched_groups"]


def test_search_quality_gate_still_rejects_cjk_drift():
    batch = [
        webtools.SearchResult(
            title="珠海这座城市怎么样？ - 知乎",
            url=f"https://www.zhihu.com/question/{idx}",
            snippet="珠海生活、旅游、城市体验讨论",
            source="bing",
            rank=idx,
        )
        for idx in range(1, 5)
    ]

    gate = webtools._assess_backend_batch_quality(
        "珠海横琴 跨境电商政策 2025",
        batch,
        {"intent": "scope:gov", "requested_scope": "gov"},
    )

    assert gate["usable"] is False
    assert "cjk_compound_terms_missing" in gate["reason"]


def test_search_quality_profile_treats_robotics_funding_as_industry():
    quality = webtools.detect_search_quality_profile(
        "具身智能 企业 融资 2024 2025 智元 宇树 傅利叶",
        profile="china",
    )

    assert quality["intent"] == "industry"
    assert "business" in quality["preferred_scopes"]


def test_recency_detects_explicit_year_range():
    recency = webtools.detect_recency_intent("具身智能 企业 融资 2024 2025 智元 宇树 傅利叶")

    assert recency["enabled"] is True
    assert recency["label"] == "year_range"
    assert recency["start_date"] == "2024-01-01"
    assert recency["matched_terms"] == ["2024", "2025"]


def test_search_block_detector_marks_captcha_pages():
    with pytest.raises(RuntimeError, match="captcha_or_verification"):
        webtools._raise_for_search_block("<html>百度安全验证 请输入验证码</html>", "baidu")


def test_search_web_applies_scope(monkeypatch):
    requested = []

    def fake_search(query, limit=10):
        requested.append(query)
        return [webtools.SearchResult(title="A", url="https://people.com.cn/a")]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "人工智能",
        backend="duckduckgo",
        scope="party_central",
        limit=1,
    )

    assert "site:people.com.cn" in requested[0]
    assert results[0]["title"] == "A"
    assert results[0]["source_type"] == "党央媒"
    assert results[0]["matched_scope"] == "party_central"


def test_search_web_rewrites_academic_scope_for_university_admissions(monkeypatch):
    requested = []

    def fake_search(query, limit=10):
        requested.append(query)
        return [webtools.SearchResult(title="清华计算机系导师", url="https://cs.tsinghua.edu.cn/faculty")]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "清华大学计算机系研究生招生 导师名单",
        backend="duckduckgo",
        scope="academic",
        limit=1,
        trace=True,
    )

    assert "site:edu.cn" in requested[0]
    assert "engineeringvillage.com" not in requested[0]
    assert results[0]["matched_scope"] == "university"
    assert results[0]["trace"]["requested_scope"] == "academic"
    assert results[0]["trace"]["effective_scope"] == "university"
    assert results[0]["trace"]["scope_rewrite"] == "academic->university"


def test_search_web_keeps_unknown_university_scope_broad(monkeypatch):
    requested = []

    def fake_search(query, limit=10):
        requested.append(query)
        return [webtools.SearchResult(title="北部湾大学研究生院", url="https://yjs.bbgu.edu.cn/")]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    webtools.search_web(
        "北部湾大学 计算机学院 研究生招生 导师",
        backend="duckduckgo",
        scope="university",
        limit=1,
    )

    assert requested[0].startswith("site:edu.cn ")
    assert "tsinghua.edu.cn" not in requested[0]
    assert "pku.edu.cn" not in requested[0]


def test_search_web_university_scope_open_fallback_when_site_search_empty(monkeypatch):
    requested = []

    def fake_search(query, limit=10):
        requested.append(query)
        if query.startswith("site:edu.cn"):
            return []
        return [webtools.SearchResult(title="重庆文理学院研究生招生网", url="https://yjszs.cqwu.edu.cn/")]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "重庆文理学院 计算机学院 研究生招生 导师",
        backend="duckduckgo",
        scope="university",
        limit=1,
        trace=True,
    )

    assert requested[0].startswith("site:edu.cn ")
    assert requested[1] == "重庆文理学院 计算机学院 研究生招生 导师"
    assert results[0]["domain"] == "yjszs.cqwu.edu.cn"
    assert any(item["backend"] == "duckduckgo:open_fallback" for item in results[0]["trace"]["backend_diagnostics"])


def test_search_web_university_scope_infers_school_site(monkeypatch):
    requested = []

    def fake_search(query, limit=10):
        requested.append(query)
        if query.startswith("site:cqwu.edu.cn"):
            return [
                webtools.SearchResult(
                    title="重庆文理学院硕士研究生导师名单",
                    url="https://graduate.cqwu.edu.cn/channel_24231.html",
                )
            ]
        return [
            webtools.SearchResult(
                title="重庆文理学院 研究生招生网",
                url="https://yjszs.cqwu.edu.cn/",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "重庆文理学院 计算机学院 研究生招生 导师",
        backend="duckduckgo",
        scope="university",
        limit=5,
        trace=True,
    )

    assert requested[0].startswith("site:edu.cn ")
    assert requested[1].startswith("site:cqwu.edu.cn ")
    assert any(item["backend"] == "duckduckgo:site_inferred" for item in results[0]["trace"]["backend_diagnostics"])
    assert any(item["url"] == "https://graduate.cqwu.edu.cn/channel_24231.html" for item in results)
    context = webtools.format_search_context(results)
    assert "已从结果识别学校主域 `cqwu.edu.cn`" in context


def test_search_web_prefers_requested_scope_for_overlapping_domains(monkeypatch):
    def fake_search(query, limit=10):
        return [webtools.SearchResult(title="亿邦动力", url="https://ebrun.com/article")]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "跨境电商",
        backend="duckduckgo",
        scope="ecommerce",
        limit=1,
    )

    assert results[0]["source_type"] == "电商/零售垂类"
    assert results[0]["matched_scope"] == "ecommerce"


def test_search_web_scope_mixes_open_results_when_scoped_batch_is_weak(monkeypatch):
    requested = []
    original = "AI Agent 发展趋势 2025"

    def fake_search(query, limit=10):
        requested.append(query)
        if query.startswith(original):
            return [
                webtools.SearchResult(
                    title="AI Agent 2025 技术发展趋势深度分析",
                    url="https://qbitai.com/agent-2025",
                    snippet="AI Agent 2025 技术发展趋势、模型调用、工具使用和多智能体架构。",
                    source="duckduckgo",
                )
            ]
        return [
            webtools.SearchResult(
                title=f"如何禁用搜狗输入法旺仔AI {idx}",
                url=f"https://ithome.com/0/{idx}.htm",
                snippet="输入法 AI 功能设置。",
                source="duckduckgo",
            )
            for idx in range(5)
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        original,
        backend="duckduckgo",
        scope="tech_dev",
        limit=6,
        trace=True,
    )

    assert requested[0].startswith("(")
    assert any(query.startswith(original) for query in requested)
    assert any(item["url"] == "https://qbitai.com/agent-2025" for item in results)
    assert any(
        item["backend"] == "duckduckgo:scope_open_mix"
        for item in results[0]["trace"]["backend_diagnostics"]
    )
    assert results[0]["trace"]["scope_mode"] == "soft"


def test_search_web_strict_scope_skips_open_mix(monkeypatch):
    requested = []
    original = "AI Agent 发展趋势 2025"

    def fake_search(query, limit=10):
        requested.append(query)
        return [
            webtools.SearchResult(
                title=f"如何禁用搜狗输入法旺仔AI {idx}",
                url=f"https://ithome.com/0/{idx}.htm",
                snippet="输入法 AI 功能设置。",
                source="duckduckgo",
            )
            for idx in range(5)
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        original,
        backend="duckduckgo",
        scope="tech_dev",
        strict_scope=True,
        limit=5,
        trace=True,
    )

    assert len(requested) == 1
    assert requested[0].startswith("(")
    assert results[0]["trace"]["scope_mode"] == "strict"


def test_research_english_profile_adapts_legacy_tech_preset(monkeypatch):
    def fake_search(query, limit=10, site=None, scope=None, backend="auto", profile=None, **kwargs):
        return [
            {
                "title": f"{scope or site or 'open'} result",
                "url": f"https://{site or 'github.com'}/repo",
                "snippet": query,
                "source": "fixture",
                "rank": 1,
                "domain": site or "github.com",
                "source_type": "英文开发者/开源",
                "matched_scope": scope or "developer",
                "trust_level": 4,
                "evidence_role": "technical_primary",
                "score": 3.0,
                "topic_key": "a",
                "topic_role": "single",
                "topic_size": 1,
                "trace": {},
            }
        ]

    monkeypatch.setattr(webtools, "search_web", fake_search)
    monkeypatch.setattr("guanlan.feeds.fetch_feed_source", lambda *_args, **_kwargs: [])

    packet = webtools.build_research_packet(
        "OpenAI SDK release notes",
        preset="tech",
        profile="english",
        read_top=0,
    )

    assert packet["profile"] == "english"
    assert "developer" in packet["scopes"]
    assert "tech_dev" not in packet["scopes"]
    assert packet["route_plan"]["recommended_commands"]


def test_research_overrides_wrong_tech_preset_for_live_sports_lookup(monkeypatch):
    search_calls = []

    def fake_search(query, **kwargs):
        search_calls.append(kwargs)
        scope = kwargs.get("scope") or ""
        return [
            {
                "title": "ESPN NBA Scoreboard",
                "url": "https://www.espn.com/nba/scoreboard",
                "snippet": "NBA scores schedule standings.",
                "source": "fixture",
                "rank": 1,
                "domain": "espn.com",
                "source_type": "体育/赛事/转会",
                "matched_scope": scope or "sports",
                "trust_level": 4,
                "evidence_role": "official_stat",
                "score": 5.0,
                "topic_key": "nba",
                "topic_role": "single",
                "topic_size": 1,
                "trace": {},
            }
        ]

    monkeypatch.setattr(webtools, "search_web", fake_search)
    monkeypatch.setattr("guanlan.feeds.fetch_feed_source", lambda *_args, **_kwargs: [])

    packet = webtools.build_research_packet(
        "NBA季后赛2026年首轮战绩比分",
        preset="tech",
        profile="china",
        read_top=0,
    )

    assert packet["preset"] == "sports"
    assert packet["preset_override"]["from"] == "tech"
    assert packet["preset_override"]["to"] == "sports"
    assert "sports" in packet["scopes"]
    assert any(call.get("scope") == "sports" for call in search_calls)
    assert not any(group.get("type") == "feed" for group in packet["result_groups"])


def test_research_tech_route_forces_rss_discovery(monkeypatch):
    search_calls = []
    feed_calls = []

    def fake_search(query, **kwargs):
        search_calls.append((query, kwargs))
        label = kwargs.get("scope") or kwargs.get("site") or "open"
        return [
            {
                "title": f"{label} 技术结果",
                "url": f"https://example.com/{label}",
                "snippet": "Python Agent 框架 对比 github issue",
                "source": "fixture",
                "rank": 1,
                "domain": "example.com",
                "source_type": "科技/开发者社区",
                "matched_scope": kwargs.get("scope") or "",
                "trust_level": 3,
                "evidence_role": "developer_discussion",
                "score": 6.0,
                "topic_key": label,
                "topic_role": "single",
            }
        ]

    def fake_feed(source, **kwargs):
        feed_calls.append((source, kwargs))
        return [
            {
                "title": "RSS Agent 深度文章",
                "url": "https://rss.example.com/agent",
                "summary": "来自精品 RSS 的技术阅读线索。",
                "source_id": "curated",
                "source_title": "精品内容流",
                "evidence_role": "reading_discovery_signal",
                "source_card": {"domain": "rss.example.com", "source_type": "RSS/OPML"},
                "feed_status": {"status": "fresh", "source_id": "curated", "stale": False, "error": ""},
                "risk_tags": [],
            }
        ]

    monkeypatch.setattr(webtools, "search_web", fake_search)
    monkeypatch.setattr("guanlan.feeds.fetch_feed_source", fake_feed)

    packet = webtools.build_research_packet(
        "Python Agent 框架 对比 github issue",
        preset="tech",
        limit=20,
        read_top=0,
    )

    assert search_calls
    assert feed_calls and feed_calls[0][0] == "curated"
    assert feed_calls[0][1]["category"] == "ai"
    assert any(group["type"] == "feed" and group["forced"] for group in packet["result_groups"])
    assert any(item["source"].startswith("feeds:") for item in packet["results"])
    assert any("强制补跑 RSS" in item for item in packet["guidance"])


def test_search_web_parses_bing_html(monkeypatch):
    html = """
    <ol id="b_results">
      <li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9h">Bing A</a></h2>
      <p>Bing snippet</p></li>
    </ol>
    """

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(html),
    )

    results = webtools.search_web("agent search", backend="bing", limit=5)

    assert results[0]["source"] == "bing"
    assert results[0]["title"] == "Bing A"
    assert results[0]["url"] == "https://example.com/a"


def test_bing_backend_uses_locale_and_safe_search(monkeypatch):
    html = """
    <ol id="b_results">
      <li class="b_algo"><h2><a href="https://example.com/a">固态电池量产时间表</a></h2>
      <p>固态电池 量产 时间表</p></li>
    </ol>
    """
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["accept_language"] = req.headers.get("Accept-language") or req.headers.get("Accept-Language")
        return _FakeResponse(html)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    results = webtools.search_web("固态电池量产时间表", backend="bing", limit=5)

    assert results[0]["title"] == "固态电池量产时间表"
    assert "safeSearch=Strict" in seen["url"]
    assert "mkt=zh-CN" in seen["url"]
    assert "setLang=zh-Hans" in seen["url"]
    assert "cc=CN" in seen["url"]
    assert "zh-CN" in seen["accept_language"]


def test_explicit_bing_low_relevance_batch_is_not_returned(monkeypatch):
    monkeypatch.setattr(webtools, "_BING_CJK_DRIFT_UNTIL", 0.0)

    def noisy_bing(query, limit=10):
        return [
            webtools.SearchResult(
                title="什么是固本培元？",
                url="https://example.com/guben",
                snippet="中医养生内容",
                source="bing",
            ),
            webtools.SearchResult(
                title="胆固醇 HDL LDL 都是什么？",
                url="https://health.example.com/cholesterol",
                snippet="胆固醇 健康科普",
                source="bing",
            ),
            webtools.SearchResult(
                title="如何评价仆固怀恩？",
                url="https://history.example.com/pugu",
                snippet="历史人物介绍",
                source="bing",
            ),
        ]

    monkeypatch.setattr(webtools, "_search_bing", noisy_bing)

    results = webtools.search_web("固态电池量产时间表", backend="bing", limit=10, trace=True)
    diagnostics = results.diagnostics["backend_diagnostics"]

    assert results == []
    assert diagnostics[0]["status"] == "low_relevance"
    assert "query_terms_missing" in diagnostics[0]["quality_gate"]["reason"]
    assert diagnostics[0]["rejected_samples"][0]["title"] == "什么是固本培元？"

    rendered = webtools.format_search_markdown(results, title="观澜搜索 / 固态电池量产时间表")
    assert "暂无可用搜索结果" in rendered
    assert "bing=low_relevance(3)" in rendered
    assert "不是观澜质量门槛过紧" in rendered
    assert "rejected_sample: 什么是固本培元？" in rendered
    assert "guanlan search \"固态电池量产时间表\" --profile china --limit 80" in rendered


def test_bing_cjk_low_relevance_tries_disambiguation_variant(monkeypatch):
    calls = []

    def fake_backend(name, query, *, limit, network_mode="auto", profile=None):
        calls.append((name, query))
        if len(calls) == 1:
            return [
                webtools.SearchResult(
                    title="2026 固态硬盘选购指南",
                    url="https://www.zhihu.com/ssd",
                    snippet="SSD NVMe 固态硬盘 推荐",
                    source="bing",
                )
            ], [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        if name == "bing_generic":
            return [], [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        return [
            webtools.SearchResult(
                title="固态电池量产时间表：动力电池产业化进展",
                url="https://example.com/solid-battery",
                snippet="固态电池 量产 时间表 动力电池 汽车 企业 产业化",
                source="bing",
            )
        ], [{"backend": name, "network_mode": network_mode, "status": "ok"}]

    monkeypatch.setattr(webtools, "_search_backend_with_network", fake_backend)

    results = webtools.search_web("固态电池量产时间表", backend="bing", limit=5, trace=True)

    assert len(results) == 1
    assert results[0]["source"] == "bing"
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert diagnostics[0]["status"] == "ok"
    assert diagnostics[0]["bing_generic_recovery"]["status"] == "not_recovered"
    assert diagnostics[0]["bing_cjk_recovery"]["status"] == "recovered"
    assert calls[0] == ("bing", "固态电池量产时间表")
    assert calls[1] == ("bing_generic", "固态电池量产时间表")
    assert calls[2][0] == "bing"
    assert calls[2][1] != "固态电池量产时间表"


def test_bing_cjk_low_relevance_uses_generic_before_disambiguation(monkeypatch):
    calls = []

    def fake_backend(name, query, *, limit, network_mode="auto", profile=None):
        calls.append((name, query))
        if name == "bing" and len(calls) == 1:
            return [
                webtools.SearchResult(
                    title="如何评价《原神》兹白角色PV？",
                    url="https://www.zhihu.com/genshin",
                    snippet="原神 游戏 角色 PV",
                    source="bing",
                )
            ], [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        if name == "bing_generic":
            return [
                webtools.SearchResult(
                    title="原研哉设计哲学：从无到有",
                    url="https://example.com/hara-design",
                    snippet="原研哉 设计 哲学 日本 设计师",
                    source="bing_generic",
                )
            ], [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        raise AssertionError("generic recovery should stop before disambiguation")

    monkeypatch.setattr(webtools, "_search_backend_with_network", fake_backend)

    results = webtools.search_web("原研哉 设计哲学", backend="bing", limit=5, trace=True)

    assert len(results) == 1
    assert results[0]["source"] == "bing"
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert diagnostics[0]["status"] == "ok"
    assert diagnostics[0]["bing_generic_recovery"]["status"] == "recovered"
    assert diagnostics[0]["bing_generic_recovery"]["strategy"] == "bing_generic"
    assert results[0]["trace"]["backend_entrypoint"] == "bing_generic"
    assert calls == [("bing", "原研哉 设计哲学"), ("bing_generic", "原研哉 设计哲学")]


def test_bing_parser_miss_tries_generic_fallback(monkeypatch):
    calls = []

    def fake_backend(name, query, *, limit, network_mode="auto", profile=None):
        calls.append((name, query))
        if name == "bing":
            return [], [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        if name == "bing_generic":
            return [
                webtools.SearchResult(
                    title="低空经济政策补贴官方汇总",
                    url="https://example.gov.cn/low-altitude",
                    snippet="低空经济 政策 补贴 政府 通知",
                    source="bing_generic",
                )
            ], [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        raise AssertionError(name)

    monkeypatch.setattr(webtools, "_search_backend_with_network", fake_backend)

    results = webtools.search_web("低空经济政策补贴", backend="bing", limit=5, trace=True)

    assert len(results) == 1
    assert results[0]["source"] == "bing"
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert diagnostics[0]["status"] == "ok"
    assert diagnostics[0]["bing_generic_recovery"]["status"] == "recovered"
    assert "Bing generic" in diagnostics[0]["note"]
    assert calls[0][0] == "bing"
    assert "低空经济政策补贴" in calls[0][1]
    assert calls[1] == ("bing_generic", "低空经济政策补贴")


def test_explicit_bing_unsafe_batch_is_filtered(monkeypatch):
    def unsafe_bing(query, limit=10):
        return [
            webtools.SearchResult(
                title="Today's selection - XNXX.COM",
                url="https://www.xnxx.com/",
                snippet="Free Porn, Sex, Tube Videos, XXX Pics",
                source="bing",
            )
        ]

    monkeypatch.setattr(webtools, "_search_bing", unsafe_bing)

    results = webtools.search_web("宁德时代 固态电池 进展", backend="bing", limit=5, trace=True)
    diagnostics = results.diagnostics["backend_diagnostics"]

    assert results == []
    assert diagnostics[0]["status"] == "unsafe_filtered"
    assert diagnostics[0]["safety_filter"]["dropped_count"] == 1


def test_search_web_parses_bing_html_with_extra_li_attributes(monkeypatch):
    html = """
    <ol id="b_results">
      <li class="b_algo" data-id="SERP.1234" iid="SERP.5678">
        <h2><a href="https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9i">Bing B</a></h2>
        <p>Bing snippet with new li attributes</p>
      </li>
    </ol>
    """

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(html),
    )

    results = webtools.search_web("agent search", backend="bing", limit=5)

    assert results[0]["source"] == "bing"
    assert results[0]["title"] == "Bing B"
    assert results[0]["url"] == "https://example.com/b"
    assert results[0]["snippet"] == "Bing snippet with new li attributes"


def test_search_web_parses_bing_html_when_class_attribute_is_not_first(monkeypatch):
    html = """
    <ol id="b_results">
      <li data-id="SERP.1234" iid="SERP.5678" class='b_algo b_algoBorder'>
        <h2><a href="https://example.com/c">Bing C</a></h2>
        <p>Bing snippet with reordered li attributes</p>
      </li>
    </ol>
    """

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(html),
    )

    results = webtools.search_web("agent search", backend="bing", limit=5)

    assert results[0]["source"] == "bing"
    assert results[0]["title"] == "Bing C"
    assert results[0]["url"] == "https://example.com/c"
    assert results[0]["snippet"] == "Bing snippet with reordered li attributes"


def test_search_web_parses_baidu_html(monkeypatch):
    html = """
    <div class="result c-container" mu="https://example.cn/a">
      <h3 class="t"><a href="http://www.baidu.com/link?url=abc">百度结果</a></h3>
      <div class="c-abstract">百度摘要</div>
    </div>
    """

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(html),
    )

    results = webtools.search_web("agent search", backend="baidu", limit=5)

    assert results[0]["source"] == "baidu"
    assert results[0]["title"] == "百度结果"
    assert results[0]["url"] == "https://example.cn/a"
    assert results[0]["snippet"] == "百度摘要"


def test_search_web_explicit_wechat_sogou_backend(monkeypatch):
    class FakeWechatSogouAPI:
        def search_article(self, query, page=1, identify_image_callback=None, decode_url=True):
            assert query == "人工智能"
            assert page == 1
            assert callable(identify_image_callback)
            assert decode_url is True
            yield {
                "article": {
                    "title": "AI 微信文章",
                    "url": "https://mp.weixin.qq.com/s/example",
                    "abstract": "文章摘要",
                    "time": 1714521600,
                },
                "gzh": {"wechat_name": "测试公众号"},
            }

    monkeypatch.setattr(webtools, "_build_wechat_sogou_api", lambda: FakeWechatSogouAPI())

    results = webtools.search_web("人工智能", backend="wechat-sogou", limit=5)

    assert results[0]["source"] == "wechat_sogou"
    assert results[0]["title"] == "AI 微信文章"
    assert results[0]["url"] == "https://mp.weixin.qq.com/s/example"
    assert "公众号: 测试公众号" in results[0]["snippet"]
    assert "发布: 2024-05-01" in results[0]["snippet"]


def test_search_web_auto_skips_wechat_sogou_when_public_results_are_enough(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_baidu",
        lambda query, limit=10: [
            webtools.SearchResult(title="百度微信结果", url="https://mp.weixin.qq.com/s/public")
        ],
    )
    monkeypatch.setattr(webtools, "_search_bing", lambda query, limit=10: [])
    monkeypatch.setattr(webtools, "_search_duckduckgo", lambda query, limit=10: [])
    monkeypatch.setattr(
        webtools,
        "_search_wechat_sogou",
        lambda query, limit=10: (_ for _ in ()).throw(RuntimeError("should not run")),
    )

    results = webtools.search_web(
        "人工智能",
        site="mp.weixin.qq.com",
        profile="china",
        limit=1,
    )

    assert results[0]["title"] == "百度微信结果"


def test_search_web_auto_uses_wechat_sogou_when_public_results_are_insufficient(monkeypatch):
    monkeypatch.setattr(webtools, "_search_baidu", lambda query, limit=10: [])
    monkeypatch.setattr(webtools, "_search_bing", lambda query, limit=10: [])
    monkeypatch.setattr(webtools, "_search_bing_generic", lambda query, limit=10: [])
    monkeypatch.setattr(webtools, "_search_duckduckgo", lambda query, limit=10: [])
    monkeypatch.setattr(
        webtools,
        "_search_wechat_sogou",
        lambda query, limit=10: [
            webtools.SearchResult(
                title="搜狗微信结果",
                url="https://mp.weixin.qq.com/s/sogou",
                source="wechat_sogou",
            )
        ],
    )

    results = webtools.search_web(
        "site:mp.weixin.qq.com 人工智能",
        profile="china",
        limit=3,
    )

    assert results[0]["source"] == "wechat_sogou"
    assert results[0]["title"] == "搜狗微信结果"


def test_search_web_auto_treats_wechat_sogou_as_non_fatal_backup(monkeypatch):
    monkeypatch.setattr(webtools, "_search_baidu", lambda query, limit=10: [])
    monkeypatch.setattr(webtools, "_search_bing", lambda query, limit=10: [])
    monkeypatch.setattr(webtools, "_search_bing_generic", lambda query, limit=10: [])
    monkeypatch.setattr(webtools, "_search_duckduckgo", lambda query, limit=10: [])
    monkeypatch.setattr(
        webtools,
        "_search_wechat_sogou",
        lambda query, limit=10: (_ for _ in ()).throw(RuntimeError("captcha")),
    )

    results = webtools.search_web(
        "人工智能",
        site="mp.weixin.qq.com",
        profile="china",
        limit=3,
    )

    assert results == []


def test_wechat_sogou_optional_dependency_message(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "wechatsogou":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="wechat-sogou backend requires optional dependency"):
        webtools._build_wechat_sogou_api()


def test_read_url_uses_jina_reader(monkeypatch):
    requested = []

    def fake_urlopen(req, timeout=None):
        requested.append(req.full_url)
        return _FakeResponse("# Title\nContent")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    text = webtools.read_url("example.com/article", max_chars=8, backend="jina")

    assert requested == ["https://r.jina.ai/https://example.com/article"]
    assert text == "# Title\n"


def test_read_url_falls_back_to_direct_when_jina_fails(monkeypatch):
    requested = []

    def fake_urlopen(req, timeout=None):
        requested.append(req.full_url)
        if req.full_url.startswith("https://r.jina.ai/"):
            raise OSError("jina timeout")
        return _FakeResponse("<html><title>原网页</title><body><script>x</script>正文</body></html>")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    text = webtools.read_url("https://example.cn/article")

    assert requested == [
        "https://r.jina.ai/https://example.cn/article",
        "https://example.cn/article",
    ]
    assert "Title: 原网页" in text
    assert "正文" in text
    assert "script" not in text


def test_direct_html_reader_filters_navigation_and_footer_noise(monkeypatch):
    html = """
    <html>
      <head><title>测试新闻</title></head>
      <body>
        <nav>首页 新闻 财经 科技 登录 注册</nav>
        <header>下载APP 分享 收藏</header>
        <main class="article-content">
          <h1>测试新闻标题</h1>
          <p>这是第一段正文，包含足够多的中文内容，用来验证正文抽取是否保留核心信息。</p>
          <p>这是第二段正文，继续说明事件背景、公开资料和可验证线索。</p>
        </main>
        <footer>版权所有 ICP 备案 联系我们</footer>
      </body>
    </html>
    """
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(html))

    text = webtools.read_url("https://example.cn/article", backend="direct")

    assert "这是第一段正文" in text
    assert "这是第二段正文" in text
    assert "首页 新闻 财经" not in text
    assert "版权所有" not in text
    assert "登录 注册" not in text


def test_direct_html_reader_drops_related_login_and_app_noise(monkeypatch):
    html = """
    <html>
      <head><title>深度文章</title></head>
      <body>
        <div class="login-panel">登录后查看更多 打开APP</div>
        <article>
          <h1>产业观察</h1>
          <p>第一段正文说明产业变化、企业反馈和公开数据，足够长以成为有效正文。</p>
          <p>第二段正文继续补充政策背景、市场反应和后续观察重点。</p>
        </article>
        <div class="related-news">相关阅读 热门推荐 下一篇</div>
      </body>
    </html>
    """
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(html))

    text = webtools.read_url("https://example.cn/deep", backend="direct")

    assert "第一段正文说明产业变化" in text
    assert "第二段正文继续补充政策背景" in text
    assert "登录后查看更多" not in text
    assert "相关阅读" not in text


def test_direct_html_reader_decodes_gbk_charset(monkeypatch):
    html = """
    <html>
      <head><meta charset="gb2312"><title>联商测试</title></head>
      <body><article><p>即时零售行业进入质量深耕阶段，平台融合和供给效率成为重点。</p></article></body>
    </html>
    """.encode("gb18030")

    class GbkResponse:
        headers = {"content-type": "text/html; charset=gb2312"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            return html

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: GbkResponse())

    text = webtools.read_url("https://example.cn/gbk", backend="direct")

    assert "联商测试" in text
    assert "即时零售行业进入质量深耕阶段" in text
    assert "�" not in text


def test_read_url_treats_mojibake_jina_as_weak_and_falls_back(monkeypatch):
    requested = []

    def fake_urlopen(req, timeout=None):
        requested.append(req.full_url)
        if req.full_url.startswith("https://r.jina.ai/"):
            return _FakeResponse("Title: ��������\nMarkdown Content:\n������������������������")
        return _FakeResponse(
            "<html><title>正文</title><body><article>"
            "<p>这是干净的中文正文，说明降级读取成功，并且保留了足够多的上下文。</p>"
            "<p>第二段继续补充事件背景、来源说明、公开信息和可验证线索，避免被判定为弱读取。</p>"
            "<p>第三段提供更多正文长度，用于模拟真实新闻页面中的主体内容，而不是导航栏或登录提示。</p>"
            "</article></body></html>"
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    text = webtools.read_url("https://example.cn/article", backend="auto")

    assert requested == [
        "https://r.jina.ai/https://example.cn/article",
        "https://example.cn/article",
    ]
    assert "这是干净的中文正文" in text
    assert "����" not in text


def test_read_url_uses_search_context_when_reading_is_blocked(monkeypatch):
    monkeypatch.setattr(webtools, "_read_with_jina", lambda url: "请先登录后查看")
    monkeypatch.setattr(webtools, "_read_direct", lambda url: "访问受限，请完成安全验证")
    monkeypatch.setattr(
        webtools,
        "search_web",
        lambda query, limit=5, site=None, profile=None: [
            {
                "rank": 1,
                "source": "duckduckgo",
                "source_type": "通用网页",
                "title": "替代来源",
                "url": "https://example.com/mirror",
                "snippet": "公开搜索摘要",
                "score": 1.2,
            }
        ],
    )

    text = webtools.read_url(
        "https://example.com/articles/ai-report",
        fallback_search=True,
        fallback_limit=3,
    )

    assert "# 观澜阅读兜底" in text
    assert "原始 URL: https://example.com/articles/ai-report" in text
    assert "替代来源" in text
    assert "jina: weak or blocked content" in text
    assert "direct: weak or blocked content" in text


def test_read_url_does_not_emit_unverified_numeric_path_fallback(monkeypatch):
    monkeypatch.setattr(webtools, "_read_with_jina", lambda url: "请先登录后查看")
    monkeypatch.setattr(webtools, "_read_direct", lambda url: "访问受限，请完成安全验证")
    monkeypatch.setattr(
        webtools,
        "search_web",
        lambda query, limit=5, site=None, profile=None: [
            {
                "rank": 1,
                "source": "duckduckgo",
                "source_type": "通用网页",
                "title": "IT之家首页",
                "url": "https://www.ithome.com/",
                "snippet": "首页内容",
                "score": 1.2,
            },
            {
                "rank": 2,
                "source": "duckduckgo",
                "source_type": "通用网页",
                "title": "台湾 iThome 250",
                "url": "https://www.ithome.com.tw/news/250",
                "snippet": "不同站点内容",
                "score": 1.0,
            },
        ],
    )

    text = webtools.read_url(
        "https://www.ithome.com/0/946/250.htm",
        fallback_search=True,
        fallback_limit=3,
    )

    assert "兜底状态: unusable" in text
    assert "不要引用本页搜索兜底作为证据" in text
    assert "台湾 iThome" not in text


def test_read_batch_keeps_per_url_status(monkeypatch):
    def fake_read(url, **kwargs):
        if "bad" in url:
            raise RuntimeError("blocked")
        return f"READ {url}"

    monkeypatch.setattr(webtools, "read_url", fake_read)

    records = webtools.read_batch(["https://good.example", "https://bad.example"])

    assert records[0]["status"] == "ok"
    assert records[0]["content"] == "READ https://good.example"
    assert records[1]["status"] == "error"
    assert records[1]["error"] == "blocked"


def test_read_batch_blocks_high_risk_social_domains(monkeypatch):
    called = []
    monkeypatch.setattr(webtools, "read_url", lambda url, **kwargs: called.append(url) or "content")

    records = webtools.read_batch(["https://www.xiaohongshu.com/explore/1", "https://example.com/a"])

    assert records[0]["status"] == "blocked"
    assert "authorization" in records[0]["error"]
    assert records[1]["status"] == "ok"
    assert called == ["https://example.com/a"]


def test_format_search_markdown():
    md = webtools.format_search_markdown(
        [
            {
                "rank": 1,
                "source": "duckduckgo",
                "title": "Result",
                "url": "https://example.com",
                "snippet": "Snippet",
            }
        ]
    )

    assert "# 观澜搜索" in md
    assert "1. [通用网页" in md
    assert "duckduckgo/通用网页" not in md
    assert "Result" in md
    assert "https://example.com" in md


def test_search_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("guanlan.webtools.search_web", return_value=[{"title": "A", "url": "https://a"}]):
        with patch("sys.argv", ["guanlan", "search", "query", "--json"]):
            main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)[0]["title"] == "A"


def test_search_cli_outputs_empty_diagnostics_json(capsys):
    from guanlan.cli import main

    empty = webtools.SearchResults(
        [],
        diagnostics={
            "query": "blocked query",
            "backend_diagnostics": [{"backend": "baidu", "status": "blocked"}],
            "backend_recovery": {"status": "failed"},
        },
    )
    with patch("guanlan.webtools.search_web", return_value=empty):
        with patch("sys.argv", ["guanlan", "search", "blocked query", "--json"]):
            main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["results"] == []
    assert payload["diagnostics"]["backend_diagnostics"][0]["status"] == "blocked"


def test_search_cli_outputs_context(capsys):
    from guanlan.cli import main

    with patch(
        "guanlan.webtools.search_web",
        return_value=[
            {
                "title": "A",
                "url": "https://a.example",
                "snippet": "S",
                "source_type": "通用网页",
                "score": 1.0,
            }
        ],
    ):
        with patch("sys.argv", ["guanlan", "search", "query", "--format", "context"]):
            main()
    captured = capsys.readouterr()
    assert "观澜搜索上下文" in captured.out
    assert "[A](https://a.example)" in captured.out


def test_search_cli_outputs_prompt(capsys):
    from guanlan.cli import main

    with patch(
        "guanlan.webtools.search_web",
        return_value=[
            {
                "title": "A",
                "url": "https://a.example",
                "snippet": "S",
                "source_type": "通用网页",
                "score": 1.0,
            }
        ],
    ):
        with patch("sys.argv", ["guanlan", "search", "query", "--format", "prompt"]):
            main()
    captured = capsys.readouterr()
    assert "观澜搜索 Prompt" in captured.out
    assert "## 用户问题" in captured.out
    assert "query" in captured.out


def test_research_cli_outputs_json(capsys):
    from guanlan.cli import main

    packet = {"query": "query", "results": [], "readings": []}
    with patch("guanlan.webtools.build_research_packet", return_value=packet):
        with patch("sys.argv", ["guanlan", "research", "query", "--json", "--read-top", "0"]):
            main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)["query"] == "query"


def test_research_cli_lists_presets(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "research", "--list-presets"]):
        main()
    captured = capsys.readouterr()
    presets = json.loads(captured.out)
    assert "policy" in presets
    assert presets["policy"]["scope"] == "gov"
    assert "entertainment" in presets
    assert presets["entertainment"]["scope"] == "entertainment"
    assert presets["global_entertainment"]["scope"] == "global_entertainment"
    assert presets["jp_kr_entertainment"]["scope"] == "jp_kr_entertainment"
    assert presets["cybersecurity"]["scope"] == "cybersecurity"
    assert presets["sports"]["scope"] == "sports"
    assert presets["weather_disaster"]["scope"] == "weather_disaster"
    assert presets["science"]["scope"] == "science"
    assert presets["career"]["scope"] == "career"
    assert presets["podcast"]["scope"] == "podcast"
    assert presets["test_prep"]["scope"] == "test_prep"
    assert presets["finance"]["scope"] == "finance"
    assert "finance_disclosure" in presets["finance"]["scopes"]
    assert "finance_quote" in presets["finance"]["scopes"]
    assert "university" in presets
    assert presets["university"]["scope"] == "university"


def test_search_cli_lists_scopes(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "search", "--list-scopes"]):
        main()
    captured = capsys.readouterr()
    scopes = json.loads(captured.out)
    assert "party_central" in scopes
    assert "ecommerce" in scopes


def test_prompt_cli_builds_local_llm_prompt(capsys):
    from guanlan.cli import main

    packet = {
        "query": "本地模型联网",
        "results": [],
        "selected_evidence": [],
        "readings": [],
        "guidance": ["保留来源"],
    }
    with patch("guanlan.webtools.build_research_packet", return_value=packet) as mocked:
        with patch("sys.argv", ["guanlan", "prompt", "本地模型联网", "--limit", "80"]):
            main()
    captured = capsys.readouterr()
    assert "观澜本地模型联网 Prompt" in captured.out
    assert "本地模型联网" in captured.out
    assert mocked.call_args.kwargs["limit"] == 80
    assert mocked.call_args.kwargs["advisor"] is True


def test_prompt_cli_passes_prompt_style(capsys):
    from guanlan.cli import main

    packet = {
        "query": "本地模型联网",
        "results": [],
        "selected_evidence": [],
        "readings": [],
        "guidance": [],
    }
    with patch("guanlan.webtools.build_research_packet", return_value=packet):
        with patch("sys.argv", ["guanlan", "prompt", "本地模型联网", "--style", "decision", "--read-top", "0"]):
            main()
    captured = capsys.readouterr()
    assert "当前输出风格: decision" in captured.out


def test_context_cli_alias_builds_local_llm_prompt(capsys):
    from guanlan.cli import main

    packet = {
        "query": "本地模型联网",
        "results": [],
        "selected_evidence": [],
        "readings": [],
        "guidance": [],
    }
    with patch("guanlan.webtools.build_research_packet", return_value=packet) as mocked:
        with patch("sys.argv", ["guanlan", "context", "本地模型联网", "--read-top", "0"]):
            main()
    captured = capsys.readouterr()

    assert "观澜本地模型联网 Prompt" in captured.out
    assert mocked.call_args.kwargs["read_top"] == 0


def test_read_cli_outputs_text(capsys):
    from guanlan.cli import main

    with patch("guanlan.webtools.read_url", return_value="content"):
        with patch("sys.argv", ["guanlan", "read", "https://example.com"]):
            main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "content"


def test_read_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("guanlan.webtools.read_url", return_value="content"):
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--format", "json"]):
            main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["url"] == "https://example.com"
    assert payload["content"] == "content"


def test_read_cli_outputs_context(capsys):
    from guanlan.cli import main

    with patch("guanlan.webtools.read_url", return_value="content"):
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--format", "context"]):
            main()
    captured = capsys.readouterr()
    assert "# 观澜阅读上下文" in captured.out
    assert "URL: https://example.com" in captured.out
    assert "content" in captured.out


def test_read_cli_outputs_trace_json(capsys):
    from guanlan.cli import main

    packet = {
        "url": "https://example.com",
        "content": "content",
        "quality": {"label": "clean", "score": 100},
        "trace": {"selected_backend": "direct", "attempts": []},
    }
    with patch("guanlan.webtools.read_url_with_trace", return_value=packet):
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--format", "json", "--trace"]):
            main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["quality"]["label"] == "clean"
    assert payload["trace"]["selected_backend"] == "direct"


def test_read_url_extracts_metadata_with_direct_backend(monkeypatch):
    html = """
    <html><head>
      <title>测试标题</title>
      <meta name="description" content="测试摘要">
      <meta property="article:published_time" content="2026-05-02">
    </head><body><article>正文</article></body></html>
    """

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(html))

    packet = webtools.read_url_with_trace(
        "https://example.com/a",
        backend="direct",
        extract="metadata",
    )

    assert "测试标题" in packet["content"]
    assert "article:published_time" in packet["content"]
    assert packet["trace"]["extract"] == "metadata"


def test_format_research_prompt_accepts_decision_style():
    packet = {
        "query": "本地模型联网",
        "guidance": [],
        "route_plan": {},
        "selected_evidence": [],
        "results": [],
        "readings": [],
    }

    prompt = webtools.format_research_prompt(packet, style="decision")

    assert "当前输出风格: decision" in prompt
    assert "可行动建议" in prompt


def test_read_cli_batch_outputs_json(capsys, tmp_path):
    from guanlan.cli import main

    url_file = tmp_path / "urls.txt"
    url_file.write_text("https://example.com/a\nhttps://example.com/b\n", encoding="utf-8")
    records = [{"rank": 1, "url": "https://example.com/a", "status": "ok", "content": "A"}]
    with patch("guanlan.webtools.read_batch", return_value=records):
        with patch("sys.argv", ["guanlan", "read", "batch", str(url_file), "--format", "json"]):
            main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)[0]["content"] == "A"


def test_read_cli_passes_backend():
    from guanlan.cli import main

    with patch("guanlan.webtools.read_url", return_value="content") as mocked:
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--backend", "direct"]):
            main()

    mocked.assert_called_once_with(
        "https://example.com",
        max_chars=None,
        backend="direct",
        fallback_search=True,
        fallback_limit=DEFAULT_READ_FALLBACK_LIMIT,
        profile="china",
        cache_ttl=0,
        use_cache=True,
        watch=False,
    )


def test_read_cli_quality_report_uses_trace_packet(capsys):
    from guanlan.cli import main

    packet = {
        "url": "https://example.com",
        "content": "这是正文内容。" * 30,
        "quality": webtools.assess_read_quality("这是正文内容。" * 30),
        "trace": {"selected_backend": "direct", "cache": "disabled"},
    }
    packet["quality_report"] = webtools.build_read_quality_report(
        packet["content"],
        url=packet["url"],
        quality=packet["quality"],
        trace=packet["trace"],
    )
    with patch("guanlan.webtools.read_url_with_trace", return_value=packet):
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--quality-report"]):
            main()
    captured = capsys.readouterr()

    assert "阅读质量报告" in captured.out
    assert "阅读 Trace" not in captured.out


def test_read_quality_report_flags_dynamic_finance_shell():
    text = "\n".join(
        [
            "东方财富行情中心",
            "沪深京 自选股 登录 注册",
            "数据加载中 请下载客户端 打开APP",
            "行情 板块 排名",
        ]
    )

    report = webtools.build_read_quality_report(
        text,
        url="https://quote.eastmoney.com/sh600519.html",
        quality=webtools.assess_read_quality(text),
    )

    assert report["dynamic_shell"] is True
    assert report["usable"] is False
    assert any("动态财经页壳" in item for item in report["recommendations"])
    rendered = webtools.format_read_quality_report(report)
    assert "dynamic_shell: true" in rendered


def test_read_quality_report_flags_xueqiu_waf_as_unusable():
    text = "\n".join(
        [
            "雪球-聪明的投资者都在这里",
            "登录 下载App",
            "系统检测到您的IP最近访问过于频繁，请验证以继续访问",
            "点击按钮进行验证 请点击重试",
        ]
    )

    report = webtools.build_read_quality_report(
        text,
        url="https://xueqiu.com/snowman/provider/zz/gp_detail?symbol=SH600519",
        quality=webtools.assess_read_quality(text),
    )

    assert report["usable"] is False
    assert report["dynamic_shell"] is True


def test_read_quality_report_flags_finance_upgrade_browser_shell():
    text = (
        "window.location.href='//finance.qq.com/gsfinance/upgrade_browser.htm' "
        "var url = 'https://galileotelemetry.tencent.com/collect'; "
        "window.AegisV2 = new Aegis({ id: 'SDK-demo' });"
    )

    report = webtools.build_read_quality_report(
        text,
        url="https://xueqiu.com/snowman/provider/zz/gp_detail?symbol=SH600519",
        quality=webtools.assess_read_quality(text),
    )

    assert report["usable"] is False
    assert report["dynamic_shell"] is True
    assert "upgrade_browser" in report["blocked_markers"]


def test_read_quality_report_marks_search_fallback_as_context_only():
    text = "# 观澜阅读兜底\n\n1. 搜索结果摘要，可作为继续核验线索。" + "补充内容" * 80

    report = webtools.build_read_quality_report(
        text,
        url="https://example.com/noisy",
        quality=webtools.assess_read_quality(text),
        trace={"selected_backend": "search_fallback"},
    )

    assert report["fallback"] is True
    assert report["usable"] is False
    assert webtools.format_read_quality_report(report).find("fallback: search_context_only") >= 0
    assert any("搜索兜底" in item for item in report["recommendations"])


def test_direct_article_extractor_uses_paragraph_density_when_container_is_noisy():
    raw = """
    <html><body>
      <div class="nav">首页 登录 注册 推荐阅读</div>
      <div class="layout"><div class="left">热门推荐 打开APP</div>
      <div class="weird-box">
        <p>第一段正文介绍政策背景，包含发布主体、适用范围和执行目标。</p>
        <p>第二段正文继续说明产业影响、地方落实路径和企业需要关注的事项。</p>
        <p>第三段正文给出后续安排，强调公开信息、权威来源和时间节点。</p>
      </div></div>
      <div class="footer">版权声明 联系我们</div>
    </body></html>
    """

    text = webtools._extract_article_text(raw)

    assert "第一段正文" in text
    assert "地方落实路径" in text
    assert "登录 注册" not in text
    assert "版权声明" not in text


def test_rank_results_merges_duplicate_sources():
    results = webtools.rank_results(
        [
            webtools.SearchResult(title="A", url="https://example.com/a?utm_source=x", source="bing"),
            webtools.SearchResult(title="A", url="https://www.example.com/a", source="duckduckgo"),
        ],
        query="A",
        backend_order=["bing", "duckduckgo"],
    )

    assert len(results) == 1
    assert results[0].source == "bing+duckduckgo"


def test_rank_results_clusters_same_topic_and_promotes_diversity():
    results = webtools.rank_results(
        [
            webtools.SearchResult(
                title="央行发布人工智能金融服务新规",
                url="https://example.com/a",
                source="bing",
                rank=1,
            ),
            webtools.SearchResult(
                title="人民银行发布人工智能金融服务新规 解读",
                url="https://example.cn/b",
                source="duckduckgo",
                rank=2,
            ),
            webtools.SearchResult(
                title="跨境电商平台推出新功能",
                url="https://example.org/c",
                source="baidu",
                rank=3,
            ),
        ],
        query="人工智能 金融",
        backend_order=["bing", "duckduckgo", "baidu"],
    )

    assert results[0].topic_role == "representative"
    assert results[0].topic_size == 2
    assert results[1].topic_role == "single"
    assert results[2].topic_role == "related"
    assert results[2].topic_key == results[0].topic_key


def test_rank_results_interleaves_source_types_for_better_evidence_mix():
    results = webtools.rank_results(
        [
            webtools.SearchResult(
                title="人工智能产业观察",
                url="https://people.com.cn/a",
                source="bing",
                rank=1,
            ),
            webtools.SearchResult(
                title="人工智能企业案例",
                url="https://xinhuanet.com/b",
                source="bing",
                rank=2,
            ),
            webtools.SearchResult(
                title="人工智能政策通知",
                url="https://gov.cn/c",
                source="bing",
                rank=3,
            ),
        ],
        query="人工智能",
        backend_order=["bing"],
    )

    assert [item.source_type for item in results[:3]] == ["党央媒", "政府/部委", "党央媒"]


def test_format_search_markdown_shows_topic_cluster():
    md = webtools.format_search_markdown(
        [
            {
                "rank": 1,
                "source": "bing",
                "source_type": "通用网页",
                "title": "同题代表",
                "url": "https://example.com/a",
                "topic_role": "representative",
                "topic_size": 2,
            }
        ]
    )

    assert "topic=representative/2" in md


def test_format_search_context_is_compact_table():
    context = webtools.format_search_context(
        [
            {
                "rank": 1,
                "source_type": "党央媒",
                "title": "结果",
                "url": "https://example.com/a",
                "snippet": "摘要",
                "score": 1.5,
                "topic_key": "topic-1",
                "topic_role": "single",
            }
        ]
    )

    assert "来源 | 标题 | 摘要 | 可信度 | Topic" in context
    assert "[结果](https://example.com/a)" in context


def test_format_search_context_surfaces_quality_guidance_before_web_fallback():
    context = webtools.format_search_context(
        [
            {
                "rank": 1,
                "source_type": "通用网页",
                "title": "普通结果",
                "url": "https://example.com/a",
                "snippet": "摘要",
                "trace": {
                    "quality_summary": {
                        "quality_status": "quality_strict",
                        "user_facing_status": "Guanlan 已找到线索，但质量画像提示还不适合直接下结论。",
                        "interpretation": "当前提示是观澜质量画像在提醒“证据包覆盖不足”，不是主题没有资料。",
                        "why_cautious": ["未命中当前意图偏好的信源类型。"],
                        "agent_workflow_plan": {
                            "tier": "4-step",
                            "minimum_guanlan_tools": 4,
                            "workflow_kind": "route_research_scope_hotnews",
                            "summary": "涉及实时/热点时，至少完成 route、research、scope search、hotnews 四步交叉补证。",
                            "tool_sequence": ["route", "research", "search", "hotnews"],
                        },
                        "guanlan_next_steps": [
                            "先运行 `guanlan route \"问题\" --json` 看推荐的 source pools。",
                            "只有 Guanlan 的多轮补证仍缺关键网页时，再用 web_search/web_fetch 作外部兜底。",
                        ],
                        "agent_execution_policy": {
                            "mode": "run_followups_now",
                            "should_run_followups": True,
                            "instruction": "不要停在建议；直接按 followup_actions 顺序继续运行 Guanlan 补证。",
                        },
                        "followup_actions": [
                            {
                                "label": "跑深度研究",
                                "command": "guanlan research \"问题\" --preset industry --advisor",
                                "reason": "继续用 Guanlan 补证。",
                                "run_policy": "run_immediately",
                            }
                        ],
                        "agent_reporting_contract": [
                            "不要向 AI 使用者概括为“Guanlan 搜索失败”。",
                        ],
                    }
                },
            }
        ]
    )

    assert "质量画像" in context
    assert "质量状态" in context
    assert "当前进展" in context
    assert "谨慎原因" in context
    assert "工作流档位" in context
    assert "至少 4 个 Guanlan 工具" in context
    assert "工具顺序: route" in context
    assert "执行策略" in context
    assert "执行动作" in context
    assert "run_immediately" in context
    assert "guanlan research" in context
    assert "观澜补证" in context
    assert "汇报约束" in context
    assert "Guanlan 搜索失败" in context
    assert "web_search/web_fetch" in context


def test_format_search_trace_includes_reporting_contract_for_quality_warn(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(
                title="普通网页",
                url="https://example.com/a",
                snippet="泛泛而谈",
                source="duckduckgo",
                rank=1,
            )
        ],
    )

    results = webtools.search_web("人工智能 政策", backend="duckduckgo", trace=True)
    trace = webtools.format_search_trace(results)

    assert "report_as:" in trace
    assert "不要向 AI 使用者概括为" in trace
    assert "未完全通过质量画像" in trace
    assert "quality_status:" in trace
    assert "user_facing_status:" in trace
    assert "why_cautious:" in trace
    assert "workflow_plan:" in trace
    assert "workflow_tool: route" in trace
    assert "execution_policy:" in trace
    assert "run_followups_now" in trace
    assert "run_immediately" in trace
    assert "action:" in trace


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


def test_format_source_chart_shows_type_and_domain_distribution():
    chart = webtools.format_source_chart(
        [
            {
                "source_type": "党央媒",
                "domain": "people.com.cn",
                "url": "https://people.com.cn/a",
            },
            {
                "source_type": "党央媒",
                "domain": "xinhuanet.com",
                "url": "https://xinhuanet.com/b",
            },
            {
                "source_type": "社交/内容平台",
                "domain": "zhihu.com",
                "url": "https://zhihu.com/c",
            },
        ]
    )

    assert "## 来源分布" in chart
    assert "党央媒" in chart
    assert "66.7%" in chart
    assert "people.com.cn" in chart
    assert "#" in chart


def test_search_cli_outputs_source_chart(capsys):
    from guanlan.cli import main

    with patch(
        "guanlan.webtools.search_web",
        return_value=[
            {
                "title": "A",
                "url": "https://people.com.cn/a",
                "domain": "people.com.cn",
                "source_type": "党央媒",
            }
        ],
    ):
        with patch("sys.argv", ["guanlan", "search", "query", "--source-chart"]):
            main()
    captured = capsys.readouterr()
    assert "观澜搜索" in captured.out
    assert "来源分布" in captured.out
    assert "people.com.cn" in captured.out


def test_build_research_packet_reads_representative_results(monkeypatch):
    search_results = [
        {
            "rank": 1,
            "title": "代表结果",
            "url": "https://example.com/a",
            "source_type": "党央媒",
            "topic_key": "topic-1",
            "topic_role": "representative",
        },
        {
            "rank": 2,
            "title": "相关转载",
            "url": "https://example.com/b",
            "source_type": "党央媒",
            "topic_key": "topic-1",
            "topic_role": "related",
        },
        {
            "rank": 3,
            "title": "另一视角",
            "url": "https://gov.cn/c",
            "source_type": "政府/部委",
            "topic_key": "topic-2",
            "topic_role": "single",
        },
    ]

    monkeypatch.setattr(webtools, "search_web", lambda *args, **kwargs: search_results)
    monkeypatch.setattr(webtools, "read_url", lambda url, **kwargs: f"READ {url}")

    packet = webtools.build_research_packet("人工智能", read_top=2)

    assert packet["query"] == "人工智能"
    assert packet["result_count"] == 3
    assert packet["topic_count"] == 2
    assert packet["source_mix"] == {"党央媒": 2, "政府/部委": 1}
    assert [item["url"] for item in packet["readings"]] == [
        "https://example.com/a",
        "https://gov.cn/c",
    ]
    assert [item["url"] for item in packet["selected_evidence"][:2]] == [
        "https://example.com/a",
        "https://gov.cn/c",
    ]
    assert packet["readings"][0]["content"] == "READ https://example.com/a"
    assert packet["readings"][0]["read_quality"]["chars"] > 0
    assert packet["read_quality_summary"]["count"] == 2
    assert "recommendation" in packet["read_quality_summary"]
    assert "status_counts" in packet["read_quality_summary"]


def test_build_research_packet_selects_diverse_representative_evidence(monkeypatch):
    search_results = [
        {
            "rank": 1,
            "title": "同题转载",
            "url": "https://media.example/a",
            "source_type": "商业媒体",
            "domain": "media.example",
            "score": 10,
            "topic_key": "topic-1",
            "topic_role": "related",
        },
        {
            "rank": 2,
            "title": "原文代表",
            "url": "https://gov.cn/policy",
            "source_type": "政府/部委",
            "domain": "gov.cn",
            "score": 8,
            "topic_key": "topic-1",
            "topic_role": "representative",
        },
        {
            "rank": 3,
            "title": "社交反馈",
            "url": "https://weibo.com/a",
            "source_type": "社交/内容平台",
            "domain": "weibo.com",
            "score": 7,
            "topic_key": "topic-2",
            "topic_role": "single",
        },
    ]

    monkeypatch.setattr(webtools, "search_web", lambda *args, **kwargs: search_results)

    packet = webtools.build_research_packet("政策反馈", read_top=0, select_top=2)

    assert [item["url"] for item in packet["selected_evidence"]] == [
        "https://gov.cn/policy",
        "https://weibo.com/a",
    ]


def test_selected_evidence_does_not_promote_low_relevance_representative_noise():
    selected = webtools._select_representative_evidence(
        [
            {
                "rank": 1,
                "title": "EI会议投稿要求",
                "url": "https://example.com/ei",
                "source_type": "通用网页",
                "domain": "example.com",
                "score": 2.5,
                "topic_key": "topic-1",
                "topic_role": "single",
            },
            {
                "rank": 9,
                "title": "Spelling ie or ei",
                "url": "https://usingenglish.com/ei",
                "source_type": "通用网页",
                "domain": "usingenglish.com",
                "score": 0.8,
                "topic_key": "topic-2",
                "topic_role": "representative",
            },
        ],
        select_top=1,
    )

    assert selected[0]["url"] == "https://example.com/ei"


def test_build_research_packet_applies_preset_defaults(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(webtools, "search_web", fake_search)

    packet = webtools.build_research_packet("人工智能监管", preset="policy")

    assert [call["scope"] for call in calls] == ["gov", "party_central", None]
    assert all(call["limit"] == DEFAULT_RESEARCH_LIMIT // 3 + 2 for call in calls)
    assert packet["preset"] == "policy"
    assert packet["scope"] == "gov"
    assert packet["scopes"] == ["gov", "party_central"]
    assert packet["read_top"] == 5
    assert packet["route_plan"]["primary_intents"][0] == "policy"


def test_build_research_packet_includes_route_plan_and_open_fallback(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        label = kwargs.get("scope") or kwargs.get("site") or "open"
        return [
            {
                "title": f"{label} result",
                "url": f"https://example.com/{label}",
                "snippet": "用户评价 值不值得买",
                "source": "mock",
                "rank": 1,
                "score": 1.0,
                "source_type": "通用网页",
                "matched_scope": kwargs.get("scope") or "",
                "topic_key": label,
                "topic_role": "single",
            }
        ]

    monkeypatch.setattr(webtools, "search_web", fake_search)

    packet = webtools.build_research_packet(
        "某产品 用户评价 值不值得买",
        preset="general",
        limit=12,
        read_top=0,
    )

    assert "reputation" in packet["route_plan"]["primary_intents"] + packet["route_plan"]["secondary_intents"]
    assert "social_web" in packet["scopes"]
    assert any(call["scope"] is None and call["site"] is None for call in calls)
    assert any(group["type"] == "general" for group in packet["result_groups"])
    assert packet["query_strategy"]["variants"]
    assert packet["source_diagnostics"]["result_count"] >= 1


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


def test_source_diagnostics_flags_missing_authority_for_policy():
    diagnostics = webtools.build_source_diagnostics(
        [
            {
                "title": "社交讨论",
                "url": "https://weibo.com/a",
                "domain": "weibo.com",
                "source_type": "社交/内容平台",
            }
        ],
        route_plan={"primary_intents": ["policy"]},
    )

    assert diagnostics["sample_avg"] > diagnostics["authority_avg"]
    assert any("权威来源偏少" in warning for warning in diagnostics["warnings"])


def test_freshness_guard_flags_stale_and_unknown_dates():
    guard = webtools.build_freshness_guard(
        [
            {
                "title": "旧专访",
                "published_at": "2024-06-01",
                "stale_risk": "high",
                "trace": {"recency": {"enabled": True, "result_date": "2024-06-01", "date_source": "title_or_snippet", "in_window": False}},
            },
            {"title": "无日期讨论", "trace": {"recency": {"enabled": True}}},
        ],
        route_plan={"primary_intents": ["hot_trend"], "freshness": "recent"},
        recency={"enabled": True, "window_days": 30},
    )

    assert guard["status"] == "fail"
    assert guard["stale_count"] == 1
    assert guard["unknown_date_count"] == 1
    assert any("旧内容风险" in warning for warning in guard["warnings"])


def test_source_mix_guard_limits_ugc_for_fact_queries():
    guard = webtools.build_source_mix_guard(
        [
            {"title": "知乎讨论", "source_type": "社交/内容平台", "evidence_role": "user_sample", "domain": "zhihu.com"},
            {"title": "微博讨论", "source_type": "社交/内容平台", "evidence_role": "user_sample", "domain": "weibo.com"},
            {"title": "产业报道", "source_type": "商业/产业媒体", "evidence_role": "industry_report", "domain": "36kr.com"},
        ],
        route_plan={"primary_intents": ["policy"]},
    )

    assert guard["status"] == "warn"
    assert guard["ugc_ratio"] > guard["max_recommended_ugc_ratio"]
    assert any("UGC" in warning for warning in guard["warnings"])


def test_build_research_packet_user_scope_overrides_preset(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(webtools, "search_web", fake_search)

    packet = webtools.build_research_packet(
        "人工智能监管",
        preset="policy",
        scope="party_central",
        read_top=0,
    )

    assert [call["scope"] for call in calls] == ["party_central"]
    assert packet["scope"] == "party_central"
    assert packet["scopes"] == ["party_central"]
    assert packet["read_top"] == 0


def test_build_research_packet_site_request_skips_preset_scopes(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(webtools, "search_web", fake_search)

    packet = webtools.build_research_packet(
        "用户评价",
        preset="reputation",
        site="zhihu.com",
    )

    assert calls == [
        {
            "limit": DEFAULT_RESEARCH_LIMIT,
            "site": "zhihu.com",
            "scope": None,
            "backend": "auto",
            "profile": "china",
            "cache_ttl": 0,
        }
    ]
    assert packet["scope"] == "social_web"
    assert packet["scopes"] == []


def test_build_research_packet_preset_adds_site_evidence_groups(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        target = kwargs.get("scope") or kwargs.get("site") or "web"
        return [
            {
                "rank": 1,
                "title": f"{target} result",
                "url": f"https://example.com/{len(calls)}",
                "source_type": "通用网页",
                "score": 1.0,
            }
        ]

    monkeypatch.setattr(webtools, "search_web", fake_search)

    packet = webtools.build_research_packet("产品评价", preset="reputation", read_top=0)

    searched_scopes = [call.get("scope") for call in calls if call.get("scope")]
    searched_sites = [call.get("site") for call in calls if call.get("site")]
    assert searched_scopes == ["social_web", "tech_dev", "business"]
    assert "zhihu.com" in searched_sites
    assert "weibo.com" in searched_sites
    assert packet["sites"][:2] == ["zhihu.com", "weibo.com"]
    assert {group["type"] for group in packet["result_groups"]} == {"scope", "site", "general"}


def test_build_research_packet_adds_cautious_advisor_when_requested(monkeypatch):
    search_results = [
        {
            "rank": 1,
            "title": "产品口碑讨论",
            "url": "https://zhihu.com/a",
            "source_type": "社交/内容平台",
            "topic_key": "topic-1",
            "topic_role": "representative",
        },
        {
            "rank": 2,
            "title": "产品发布报道",
            "url": "https://example.com/b",
            "source_type": "商业/产业媒体",
            "topic_key": "topic-2",
            "topic_role": "single",
        },
    ]

    monkeypatch.setattr(webtools, "search_web", lambda *args, **kwargs: search_results)
    monkeypatch.setattr(webtools, "read_url", lambda url, **kwargs: f"READ {url}")

    plain_packet = webtools.build_research_packet("某产品 用户评价", preset="reputation", read_top=0)
    advisor_packet = webtools.build_research_packet(
        "某产品 用户评价",
        preset="reputation",
        read_top=0,
        advisor=True,
    )

    assert "advisor" not in plain_packet
    assert advisor_packet["advisor"]["title"] == "助理视角规则"
    assert advisor_packet["advisor"]["mode"] == "agent_guidance"
    assert "不代表用户真实目的" in advisor_packet["advisor"]["stance"]
    assert "briefing" in advisor_packet["advisor"]
    assert any("谁在说" in item for item in advisor_packet["advisor"]["answer_frame"])
    assert any("口碑" in item for item in advisor_packet["advisor"]["suggested_angles"])
    assert any("搜索摘要" in item for item in advisor_packet["advisor"]["evidence_limits"])
    assert any("固定模板" in item for item in advisor_packet["advisor"]["synthesis_rules"])
    assert any("用户真实动机" in item for item in advisor_packet["advisor"]["response_contract"])


def test_build_research_packet_adds_evidence_audit_for_version_conflicts(monkeypatch):
    search_results = [
        {
            "rank": 1,
            "title": "2026-04-05 BuildFastWithAI: GPT-5.4 and Claude Opus 4.6 released",
            "url": "https://buildfast.example/llm",
            "snippet": "GLM-5 model summary",
            "source_type": "通用网页",
            "domain": "buildfast.example",
            "score": 5,
        },
        {
            "rank": 2,
            "title": "2026-04-17 Medium: GPT-5.5 and Claude Opus 4.7 update",
            "url": "https://medium.example/llm",
            "snippet": "GLM-5.1 pricing and release notes",
            "source_type": "通用网页",
            "domain": "medium.example",
            "score": 6,
        },
    ]

    monkeypatch.setattr(webtools, "search_web", lambda *args, **kwargs: search_results)

    packet = webtools.build_research_packet("2026 April LLM release global AI model", read_top=0)

    audit = packet["evidence_audit"]
    families = {item["family"] for item in audit["version_conflicts"]}
    assert {"GPT", "Claude", "GLM"} <= families
    assert audit["timeline"][0]["date"] == "2026-04-17"
    md = webtools.format_research_markdown(packet)
    assert "## 证据审计提示" in md
    assert "GPT-5.4" in md
    assert "GPT-5.5" in md
    assert "不能仅凭日期自动判定真伪" in md


def test_evidence_audit_flags_general_structured_claim_differences(monkeypatch):
    search_results = [
        {
            "rank": 1,
            "title": "2026-04-05 Model API pricing and parameter report",
            "url": "https://example.com/a",
            "snippet": "API price $2/million tokens, 参数量 72B parameters, benchmark 83.2%",
            "source_type": "通用网页",
            "domain": "example.com",
            "score": 5,
        },
        {
            "rank": 2,
            "title": "2026-04-17 Updated pricing and benchmark",
            "url": "https://example.org/b",
            "snippet": "API price $3/million tokens, 参数量 70B parameters, benchmark 85%",
            "source_type": "通用网页",
            "domain": "example.org",
            "score": 6,
        },
    ]

    monkeypatch.setattr(webtools, "search_web", lambda *args, **kwargs: search_results)

    packet = webtools.build_research_packet("model API price parameter benchmark", read_top=0)

    categories = {item["category"] for item in packet["evidence_audit"]["claim_differences"]}
    assert {"price", "parameter_count", "percentage_metric"} <= categories
    md = webtools.format_research_markdown(packet)
    assert "结构化事实差异" in md
    assert "$2/million" in md
    assert "$3/million" in md


def test_build_research_packet_accepts_advisor_style(monkeypatch):
    monkeypatch.setattr(webtools, "search_web", lambda *args, **kwargs: [])
    packet = webtools.build_research_packet(
        "某产品 用户评价",
        preset="reputation",
        read_top=0,
        advisor=True,
        advisor_style="risk",
    )

    assert packet["advisor"]["style"] == "risk"
    assert any("风险" in item or "误判" in item for item in packet["advisor"]["answer_frame"])


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


def test_format_research_markdown():
    md = webtools.format_research_markdown(
        {
            "query": "人工智能",
            "result_count": 1,
            "topic_count": 1,
            "source_mix": {"党央媒": 1},
            "guidance": ["优先交叉验证。"],
            "results": [
                {
                    "rank": 1,
                    "source": "bing",
                    "source_type": "党央媒",
                    "title": "结果",
                    "url": "https://example.com/a",
                }
            ],
            "readings": [
                {
                    "title": "结果",
                    "url": "https://example.com/a",
                    "source_type": "党央媒",
                    "status": "ok",
                    "content": "正文摘录",
                }
            ],
        }
    )

    assert "# 观澜研究证据包 / 人工智能" in md
    assert "## 信源概览" in md
    assert "党央媒: 1" in md
    assert "正文摘录" in md


def test_html_to_markdownish_prefers_chinese_article_body():
    html = """
    <html><head><title>标题</title><meta name="source" content="新华社">
    <meta property="article:published_time" content="2026-05-02"></head>
    <body>
      <nav>首页 新闻 财经 科技 登录 注册</nav>
      <div class="side recommend">推荐阅读 登录 下载APP</div>
      <div id="js_content">
        <p>这是第一段正文，介绍政策背景和核心事实。</p>
        <p>这是第二段正文，包含更多连续信息和分析。</p>
      </div>
      <footer>版权所有 联系我们</footer>
    </body></html>
    """
    text = webtools._html_to_markdownish(html, url="https://example.com/a")

    assert "Source: 新华社" in text
    assert "Published: 2026-05-02" in text
    assert "这是第一段正文" in text
    assert "下载APP" not in text


def test_format_research_markdown_includes_advisor_block():
    advisor = webtools.build_advisor_view(
        {
            "query": "人工智能 政策",
            "preset": "policy",
            "result_count": 1,
            "topic_count": 1,
            "source_mix": {"政府/部委": 1},
            "results": [{"source_type": "政府/部委", "title": "通知"}],
            "readings": [],
            "read_top": 0,
        }
    )
    md = webtools.format_research_markdown(
        {
            "query": "人工智能 政策",
            "result_count": 1,
            "topic_count": 1,
            "source_mix": {"政府/部委": 1},
            "guidance": [],
            "results": [],
            "readings": [],
            "advisor": advisor,
        }
    )

    assert "## 助理视角规则" in md
    assert "自然作答骨架" in md
    assert "给 Agent 的写作规则" in md
    assert "当前证据边界" in md


def test_read_watch_outputs_diff(monkeypatch, tmp_path):
    monkeypatch.setattr(webtools, "cache_dir", lambda: tmp_path / "cache")

    first = webtools._format_read_watch("https://example.com/a", "line one")
    second = webtools._format_read_watch("https://example.com/a", "line two")

    assert "首次快照" in first
    assert "发现内容变化" in second
    assert "-line one" in second
    assert "+line two" in second


def test_relative_result_date_ignores_unrealistic_year_offsets():
    import datetime as dt

    assert webtools._extract_relative_result_date("123456年 前的乱序片段", dt.date(2026, 5, 4)) is None
    assert webtools._extract_relative_result_date("101年前", dt.date(2026, 5, 4)) is None
    assert webtools._extract_relative_result_date("3年前", dt.date(2026, 5, 4)) == dt.date(2023, 5, 5)
