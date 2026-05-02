# -*- coding: utf-8 -*-
"""Tests for agent-facing search and read primitives."""

import builtins
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from guanlan import webtools
from guanlan.limits import DEFAULT_READ_FALLBACK_LIMIT, DEFAULT_RESEARCH_LIMIT


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

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(html),
    )

    results = webtools.search_web("agent search", limit=5)

    assert len(results) == 2
    assert results[0]["title"] == "Example A"
    assert results[0]["url"] == "https://example.com/a"
    assert results[0]["snippet"] == "First snippet"
    assert results[0]["rank"] == 1
    assert results[0]["domain"] == "example.com"
    assert results[0]["source_type"] == "通用网页"
    assert results[0]["score"] > 0


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
    assert any("scope gov" in item for item in summary["suggestions"])


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
    assert results[0]["snippet"] == "Bing snippet"


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
    assert "1. [duckduckgo/通用网页" in md
    assert "Result" in md
    assert "https://example.com" in md


def test_search_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("guanlan.webtools.search_web", return_value=[{"title": "A", "url": "https://a"}]):
        with patch("sys.argv", ["guanlan", "search", "query", "--json"]):
            main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)[0]["title"] == "A"


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
    assert packet["read_top"] == 3
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
