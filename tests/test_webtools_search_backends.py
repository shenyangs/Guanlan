# -*- coding: utf-8 -*-
"""Tests for search backend parsers and backend selection."""
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


def test_search_ranking_promotes_cjk_compound_group_match(monkeypatch):
    def fake_backend(query, limit=10, network_mode="auto"):
        return [
            webtools.SearchResult(
                title="国企风采|2025年5月5日至5月11日回顾",
                url="https://www.zhuhai.gov.cn/gzw/gkmlpt/content/3/3798/post_3798638.html",
                snippet="珠海市国资系统一周工作动态。",
                source="duckduckgo",
                rank=1,
            ),
            webtools.SearchResult(
                title="关于开展横琴粤澳深度合作区2025年上半年跨境电商产业扶持申报工作的通知",
                url="https://www.hengqin.gov.cn/macao_zh_hans/zwgk/tzgg/gg/content/post_3819367.html",
                snippet="跨境电商产业扶持申报指南。",
                source="duckduckgo",
                rank=2,
            ),
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_backend)

    results = webtools.search_web(
        "珠海横琴 跨境电商政策 2025",
        backend="duckduckgo",
        scope="gov",
        profile="china",
        trace=True,
    )

    assert results[0]["url"].startswith("https://www.hengqin.gov.cn/")
    assert results[0]["score_parts"]["cjk_group_fit"] > 0
    assert results[1]["score_parts"]["cjk_group_mismatch_penalty"] < 0


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


def test_search_web_rescues_university_scope_with_route_target_site(monkeypatch):
    requested = []

    def fake_search(query, limit=10):
        requested.append(query)
        if query.startswith("site:cs.tsinghua.edu.cn"):
            return [
                webtools.SearchResult(
                    title="清华大学计算机科学与技术系2025年硕士统招生复试录取实施细则",
                    url="https://cs.tsinghua.edu.cn/info/1088/1234.htm",
                    snippet="清华大学计算机科学与技术系 研究生招生 导师 复试 录取。",
                    source="duckduckgo",
                )
            ]
        return [
            webtools.SearchResult(
                title="中国研究生招生信息网",
                url="https://yz.chsi.com.cn/",
                snippet="全国硕士研究生招生考试报名和调剂入口。",
                source="duckduckgo",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "清华大学计算机系研究生招生 导师",
        backend="duckduckgo",
        profile="china",
        scope="university",
        limit=8,
        trace=True,
    )

    assert any("site:cs.tsinghua.edu.cn" in query for query in requested)
    assert any(item["domain"] == "cs.tsinghua.edu.cn" for item in results)
    assert results[0]["source_type"] == "高校/院系官网"
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert any(item["backend"] == "duckduckgo:route_target_site" and item["status"] == "ok" for item in diagnostics)


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

    def fake_ai_vertical(query, **kwargs):
        feed_calls.append(("ai-vertical", kwargs))
        return [
            {
                "title": "AI 垂类精选动态",
                "url": "https://ai.example.com/agent",
                "summary": "来自 AI 垂类精选动态源的线索。",
                "source_id": "ai-vertical",
                "source_title": "AI 垂类精选动态源",
                "evidence_role": "ai_vertical_discovery_signal",
                "source_card": {"domain": "ai.example.com", "source_type": "科技/开发者社区"},
                "feed_status": {"status": "fresh", "source_id": "ai-vertical", "stale": False, "error": ""},
                "risk_tags": ["source_requires_original_verification"],
            }
        ]

    monkeypatch.setattr(webtools, "search_web", fake_search)
    monkeypatch.setattr("guanlan.feeds.fetch_feed_source", fake_feed)
    monkeypatch.setattr("guanlan.feeds.fetch_ai_vertical_signals", fake_ai_vertical)

    packet = webtools.build_research_packet(
        "Python Agent 框架 对比 github issue",
        preset="tech",
        limit=20,
        read_top=0,
    )

    assert search_calls
    assert feed_calls and feed_calls[0][0] == "curated"
    assert feed_calls[0][1]["category"] == "ai"
    assert any(call[0] == "ai-vertical" for call in feed_calls)
    assert any(group["type"] == "feed" and group["forced"] for group in packet["result_groups"])
    assert any(group["label"] == "ai-vertical" for group in packet["result_groups"])
    assert any(item["source"].startswith("feeds:") for item in packet["results"])
    assert any(item["source"] == "feeds:ai-vertical" for item in packet["results"])
    assert any("强制补跑 RSS" in item for item in packet["guidance"])


def test_safety_filter_diagnostics_are_json_safe():
    raw = {
        "kept_results": [
            webtools.SearchResult(
                title="Safe",
                url="https://example.com",
                snippet="ok",
            )
        ],
        "dropped_count": 1,
        "dropped": [{"title": "Bad", "domain": "example.com", "reason": "unsafe"}],
    }

    data = webtools._serializable_safety_filter(raw)

    json.dumps(data)
    assert isinstance(data["kept_results"][0], dict)
    assert raw["kept_results"][0].title == "Safe"


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

    results = webtools.search_web(
        "固态电池量产时间表",
        backend="bing",
        limit=10,
        trace=True,
        cache_ttl=0,
        recovery_mode="off",
    )
    diagnostics = results.diagnostics["backend_diagnostics"]

    assert results == []
    assert diagnostics[0]["status"] == "low_relevance"
    assert "query_terms_missing" in diagnostics[0]["quality_gate"]["reason"]
    assert diagnostics[0]["rejected_samples"][0]["title"] == "什么是固本培元？"

    rendered = webtools.format_search_markdown(results, title="观澜搜索 / 固态电池量产时间表")
    assert "暂无可用搜索结果" in rendered
    assert "bing=low_relevance(3)" in rendered
    assert "候选与查询意图明显不匹配" in rendered
    assert "rejected_sample: 什么是固本培元？" in rendered
    assert "guanlan search \"固态电池量产时间表\" --profile china --limit 80" in rendered


def test_auto_search_keeps_bounded_authoritative_salvage_when_backends_drift(monkeypatch):
    def fake_order(*_args, **_kwargs):
        return ["baidu", "duckduckgo", "bing"]

    def fake_backend(name, query, *, limit, network_mode="auto", profile=None):
        if name == "baidu":
            raise RuntimeError("captcha_or_verification: 百度安全验证")
        if name == "duckduckgo":
            raise webtools.NetworkBackendError(
                "network_unreachable",
                "current=network_unreachable: timed out",
                [{"backend": name, "network_mode": network_mode, "status": "network_unreachable"}],
            )
        if name in {"bing", "bing_generic"}:
            return [
                webtools.SearchResult(
                    title="字节 跳动 - ByteDance",
                    url="https://www.bytedance.com/zh/",
                    snippet="字节跳动旗下产品包括抖音、飞书、豆包等。",
                    source="bing",
                ),
                webtools.SearchResult(
                    title="bit、byte、KB、B、字节之间关系详解",
                    url="https://blog.csdn.net/example",
                    snippet="计算机存储单位教程。",
                    source="bing",
                ),
            ], [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        raise AssertionError(name)

    monkeypatch.setattr(webtools, "backend_order", fake_order)
    monkeypatch.setattr(webtools, "_search_backend_with_network", fake_backend)

    results = webtools.search_web(
        "字节跳动豆包 AI战略 流量优势 2025",
        backend="auto",
        profile="china",
        limit=5,
        trace=True,
    )

    assert [item["domain"] for item in results] == ["bytedance.com"]
    diagnostics = results.diagnostics["backend_diagnostics"]
    assert any(item["backend"] == "quality_salvage" and item["status"] == "ok" for item in diagnostics)
    assert any(item["backend"] == "duckduckgo:recovery" and item["status"] == "skipped" for item in diagnostics)
    assert results[0]["trace"]["quality_salvage"] is True


def test_policy_search_returns_direct_official_entrypoints_when_backends_empty(monkeypatch):
    def fake_order(*_args, **_kwargs):
        return ["baidu", "duckduckgo", "bing"]

    def fake_backend(name, query, *, limit, network_mode="auto", profile=None):
        if name == "baidu":
            raise RuntimeError("captcha_or_verification: 百度安全验证")
        if name == "duckduckgo":
            raise webtools.NetworkBackendError(
                "network_unreachable",
                "current=network_unreachable: timed out",
                [{"backend": name, "network_mode": network_mode, "status": "network_unreachable"}],
            )
        if name in {"bing", "bing_generic"}:
            return [
                webtools.SearchResult(
                    title="横 的解释",
                    url="https://www.zdic.net/hans/%E6%A8%AA",
                    snippet="汉字解释",
                    source="bing",
                )
            ], [{"backend": name, "network_mode": network_mode, "status": "ok"}]
        raise AssertionError(name)

    monkeypatch.setattr(webtools, "backend_order", fake_order)
    monkeypatch.setattr(webtools, "_search_backend_with_network", fake_backend)

    results = webtools.search_web("横琴自贸区最新政策 今天", backend="auto", profile="china", limit=5, trace=True)

    assert results
    assert results[0]["domain"] == "hengqin.gov.cn"
    diagnostics = results[0]["trace"]["backend_diagnostics"]
    assert any(item["backend"].startswith("direct:") and item["status"] == "ok" for item in diagnostics)
    assert all("zdic.net" not in item["url"] for item in results)


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


def test_relative_result_date_ignores_unrealistic_year_offsets():
    import datetime as dt

    assert webtools._extract_relative_result_date("123456年 前的乱序片段", dt.date(2026, 5, 4)) is None
    assert webtools._extract_relative_result_date("101年前", dt.date(2026, 5, 4)) is None
    assert webtools._extract_relative_result_date("3年前", dt.date(2026, 5, 4)) == dt.date(2023, 5, 5)
