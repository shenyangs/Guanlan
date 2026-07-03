# -*- coding: utf-8 -*-
"""Tests for search quality routing and direct source seeds."""
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
    wps_office_needs_open_web,
)
from tests.support.webtools_helpers import _FakeResponse


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
    assert seen_timeouts == [webtools._DUCKDUCKGO_SEARCH_TIMEOUT]


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
        ("WPS AI PPT Agent 办公选题 最近热点", "wps_office", "办公软件/AI Office/SaaS"),
    ]

    for query, intent, source_type in cases:
        quality = webtools.detect_search_quality_profile(query, profile="china")
        assert quality["intent"] == intent
        assert source_type in quality["preferred_source_types"]


def test_short_wps_brand_query_expands_to_market_radar_terms():
    route_plan = webtools.build_route_plan("WPS AI", scope="wps_office").to_dict()
    quality = webtools.detect_search_quality_profile("WPS AI", scope="wps_office", profile="china")
    shape = webtools._analyze_search_query_shape(
        "WPS AI",
        effective_scope="wps_office",
        quality=quality,
        route_plan=route_plan,
    )

    assert shape["rewritten"]
    assert "AI PPT" in shape["backend_query"]
    assert "职场效率" in shape["backend_query"]
    assert "表格分析" in shape["backend_query"]


def test_wps_semantic_quality_profile_catches_adjacent_office_but_not_generic_ai():
    adjacent = webtools.detect_search_quality_profile("AI 笔记 知识库 Agent", profile="china")
    generic = webtools.detect_search_quality_profile("Python token skill", profile="china")

    assert adjacent["intent"] == "wps_office"
    assert "ai_office_adjacent" in adjacent["wps_lanes"]
    assert "claw_agent" in adjacent["wps_lanes"]
    assert generic["intent"] != "wps_office"


def test_search_quality_profile_generalizes_stress_report_fragile_queries():
    cases = [
        ("设备更新万亿", "policy"),
        ("数据出境安全评估", "standards_compliance"),
        ("劳动法新规灵活用工", "policy"),
        ("医保谈判2025", "medical_health"),
        ("台积电亚利桑那", "company"),
        ("酱香拿铁营销", "industry"),
        ("胖东来模式", "industry"),
        ("chiikawa", "entertainment"),
        ("CAR-T疗法", "medical_health"),
        ("向量数据库", "tech"),
        ("图神经网络", "tech"),
        ("Prompt Engineering", "tech"),
    ]

    for query, intent in cases:
        quality = webtools.detect_search_quality_profile(query, profile="china")
        assert quality["intent"] == intent
        assert any(reason.startswith("semantic:") for reason in quality["reasons"])


def test_search_query_shape_rewrites_fragile_compounds_and_proper_nouns():
    cases = {
        "设备更新万亿": ("大规模设备更新", "工信部"),
        "数据出境安全评估": ("网信办", "申报"),
        "台积电亚利桑那": ("TSMC", "Arizona fab"),
        "酱香拿铁营销": ("瑞幸", "茅台"),
        "胖东来模式": ("零售模式", "商超"),
        "医保谈判2025": ("国家医保局", "药品目录"),
        "chiikawa": ("吉伊卡哇", "ちいかわ"),
        "CAR-T疗法": ("NMPA", "CDE"),
        "向量数据库": ("Milvus", "Qdrant"),
        "Prompt Engineering": ("OpenAI", "Anthropic"),
    }

    for query, needles in cases.items():
        shape = webtools._analyze_search_query_shape(query, quality=webtools.detect_search_quality_profile(query, profile="china"))
        assert shape["rewritten"] is True
        assert "semantic_compound" in shape["rewrite_reasons"]
        assert all(needle in shape["backend_query"] for needle in needles)


def test_direct_source_seeds_cover_medical_and_health_policy_queries():
    car_t = direct_source_seeds("CAR-T疗法", intents=["medical_health"], scopes=["medical_health"])
    insurance = direct_source_seeds("医保谈判2025", intents=["medical_health", "policy"], scopes=["medical_health"])

    assert any("nmpa.gov.cn" in item["url"] for item in car_t)
    assert any("cde.org.cn" in item["url"] for item in car_t)
    assert any("clinicaltrials.gov" in item["url"] for item in car_t)
    assert any("nhsa.gov.cn" in item["url"] for item in insurance)


def test_direct_source_seeds_cover_vertical_lookups_without_treating_dev_tasks_as_scores():
    nba_seeds = direct_source_seeds(
        "NBA季后赛2026年首轮战绩比分",
        intents=["sports"],
        scopes=["sports"],
    )
    worldcup_seeds = direct_source_seeds(
        "2026年美加墨世界杯接下来3天 6月30日-7月3日 淘汰赛赛程 比赛城市 球场",
        intents=["sports"],
        scopes=["sports"],
    )
    weather_seeds = direct_source_seeds("台风 路径 最新 中央气象台 日本气象厅", intents=["weather_disaster"])
    security_seeds = direct_source_seeds("CVE-2026-12345 OpenSSL 漏洞 影响版本", intents=["cybersecurity"])
    wps_seeds = direct_source_seeds("WPS AI 官网 下载", intents=["wps_office"], scopes=["wps_office"])
    wps_open_seeds = direct_source_seeds("WPS AI PPT Agent 办公选题", intents=["wps_office"], scopes=["wps_office"])

    assert any("espn.com/nba/story" in item["url"] for item in nba_seeds)
    assert any("fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures" in item["url"] for item in worldcup_seeds)
    assert any("espn.com/soccer/schedule/_/league/fifa.world" in item["url"] for item in worldcup_seeds)
    assert any("foxsports.com/soccer/fifa-world-cup-men/scores" in item["url"] for item in worldcup_seeds)
    assert any("olympics.com/en/football/fifa-world-cup/schedule-results" in item["url"] for item in worldcup_seeds)
    assert not any("uefa.com/uefachampionsleague" in item["url"] for item in worldcup_seeds)
    assert any("nmc.cn" in item["url"] for item in weather_seeds)
    assert any("CVE-2026-12345" in item["url"] for item in security_seeds)
    assert any("wps.cn" in item["url"] for item in wps_seeds)
    assert wps_open_seeds == []
    assert any("365.wps.cn" in item["url"] for item in wps_seeds)
    assert any("lingxi.wps.cn" in item["url"] for item in wps_seeds)
    assert is_live_sports_lookup("NBA季后赛2026年首轮战绩比分", intents=["sports"])
    assert not is_live_sports_lookup("NBA API 开源项目 教程", intents=["tech", "sports"])
    assert is_wps_office_lookup("WPS AI PPT Agent 办公选题", intents=["wps_office"])
    assert is_wps_office_lookup("AI PPT 工具 横评", intents=[])
    assert not is_wps_office_lookup("Python token skill", intents=[])


def test_direct_source_seeds_include_arxiv_for_academic_preprint_queries():
    seeds = direct_source_seeds("AI Agent browser assist arxiv 论文", intents=["academic"], scopes=["academic"])

    assert seeds[0]["seed_id"] == "academic:arxiv_api"
    assert seeds[0]["evidence_role"] == "preprint_record"


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
