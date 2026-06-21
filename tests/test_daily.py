# -*- coding: utf-8 -*-
"""Tests for Guanlan daily briefs."""

import json
from pathlib import Path
from unittest.mock import patch

from guanlan.daily import (
    _daily_is_soft_seo,
    _daily_section_key,
    _resolve_daily_feed_source,
    build_daily_report,
    format_daily_context,
    format_daily_html,
    format_daily_im,
    format_daily_markdown,
    save_daily_output,
)
from guanlan.daily_history import build_daily_history_delta, record_daily_history
from guanlan.daily_quality import classify_daily_source, normalize_daily_freshness
from guanlan.daily_storylines import build_daily_storylines


class _Plan:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


def test_build_daily_report_combines_query_layers(monkeypatch):
    monkeypatch.setattr(
        "guanlan.daily.build_route_plan",
        lambda *args, **kwargs: _Plan(
            {
                "query": args[0],
                "primary_intents": ["tech", "wps_office"],
                "secondary_intents": ["hot_trend"],
                "preferred_scopes": ["tech_dev", "company_primary"],
                "warnings": ["技术类日报应继续回读官方原文。"],
            }
        ),
    )
    monkeypatch.setattr(
        "guanlan.daily.search_web",
        lambda *_args, **_kwargs: [
            {
                "title": "WPS AI 办公智能体发布说明",
                "url": "https://www.wps.cn/ai/launch",
                "snippet": "WPS AI Agent 新能力。",
                "source_type": "公司一手资料",
                "evidence_role": "company_primary",
                "source_card": {"authority_score": 0.82},
            }
        ],
    )
    monkeypatch.setattr(
        "guanlan.daily.fetch_feed_source",
        lambda source, **_kwargs: [
            {
                "title": "WPS AI 办公智能体发布说明",
                "url": "https://www.wps.cn/ai/launch",
                "summary": "来自 RSS 的同一条发布说明。",
                "source_title": "AI HOT",
                "evidence_role": "reading_signal",
                "source_card": {"authority_score": 0.66},
            },
            {
                "title": "AI Office 新趋势观察",
                "url": "https://example.com/ai-office-trend",
                "summary": "办公智能体行业趋势。",
                "source_title": "AI HOT",
                "evidence_role": "industry_report",
            },
        ],
    )
    monkeypatch.setattr(
        "guanlan.daily.fetch_hotnews",
        lambda **_kwargs: [
            {
                "title": "办公智能体成热议方向",
                "url": "https://hot.example.com/a",
                "source_id": "weibo",
                "evidence_role": "fresh_trend_signal",
                "metrics": {"heat": 900000},
            }
        ],
    )
    monkeypatch.setattr(
        "guanlan.daily.build_trend_report",
        lambda *_args, **_kwargs: {"trend_count": 1, "sample_count": 1, "trends": [], "source_distribution": {}, "sample_boundaries": []},
    )
    monkeypatch.setattr(
        "guanlan.daily.build_hotnews_brief",
        lambda *_args, **_kwargs: {
            "sample_count": 1,
            "trend_count": 1,
            "sample_boundaries": ["热榜样本只能说明当前公开来源的可见水势。"],
            "warnings": [],
            "highlights": [{"title": "办公智能体成热议方向", "sources": ["weibo"], "resonance": "single-source", "boundary": ""}],
        },
    )

    report = build_daily_report(
        "WPS AI 办公智能体",
        profile="china",
        limit=5,
        search_limit=20,
        feeds_limit=10,
        hotnews_limit=5,
    )

    assert report["mode"] == "query_daily"
    assert report["schema_version"] == "daily_report_v1"
    assert report["feed_source"] == "ai-vertical"
    assert report["candidate_count"] >= 4
    assert report["item_count"] >= 2
    assert report["storylines"]
    assert report["editorial_decisions"]
    assert report["source_health"]["main_tier_counts"].get("D", 0) == 0
    launch_item = next(item for item in report["items"] if item["title"] == "WPS AI 办公智能体发布说明")
    assert "feeds:ai-vertical" in set(launch_item["merged_from"])
    assert any(item.startswith("search") for item in launch_item["merged_from"])
    assert report["editorial_health"]["status"] in {"ok", "warn"}
    assert report["editorial_health"]["coverage"]["ecosystem"] >= 1
    assert any("回读官方原文" in item for item in report["boundaries"])
    assert report["hotnews_brief"]["sample_count"] in {0, 1}


def test_build_daily_report_can_reuse_watch_intent(monkeypatch):
    monkeypatch.setattr(
        "guanlan.daily.fire_watch_intent",
        lambda *_args, **_kwargs: {
            "intent": {"id": "openai-api", "name": "OpenAI API 更新", "query": "OpenAI API release notes"},
            "route_plan": {"primary_intents": ["tech"], "secondary_intents": [], "preferred_scopes": ["tech_dev"]},
            "diagnostics": {
                "search": {"status": "ok", "count": 2, "error": ""},
                "feeds": {"status": "ok", "count": 1, "error": "", "source": "curated"},
            },
            "items": [
                {
                    "title": "OpenAI API changelog",
                    "url": "https://platform.openai.com/docs/changelog",
                    "summary": "新版本说明。",
                    "source": "company_primary",
                    "origin": "search",
                    "evidence_role": "company_primary",
                    "is_new": True,
                }
            ],
        },
    )
    monkeypatch.setattr("guanlan.daily.fetch_feed_source", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("guanlan.daily.fetch_hotnews", lambda **_kwargs: [])
    monkeypatch.setattr("guanlan.daily.build_trend_report", lambda *_args, **_kwargs: {"trend_count": 0, "sample_count": 0, "trends": [], "source_distribution": {}, "sample_boundaries": []})
    monkeypatch.setattr("guanlan.daily.build_hotnews_brief", lambda *_args, **_kwargs: {"sample_count": 0, "trend_count": 0, "sample_boundaries": [], "warnings": [], "highlights": []})

    report = build_daily_report("", watch_id="openai-api", limit=5)

    assert report["mode"] == "watch_daily"
    assert report["watch_id"] == "openai-api"
    assert report["diagnostics"]["watch"]["status"] == "ok"
    assert report["items"][0]["title"] == "OpenAI API changelog"
    assert any("watch fire openai-api --record-seen" in item for item in report["next_steps"])


def test_build_daily_report_can_read_representative_urls(monkeypatch):
    monkeypatch.setattr(
        "guanlan.daily.build_route_plan",
        lambda *args, **kwargs: _Plan(
            {
                "query": args[0],
                "primary_intents": ["wps_office"],
                "secondary_intents": [],
                "preferred_scopes": ["wps_office", "tech_dev"],
                "warnings": [],
            }
        ),
    )
    monkeypatch.setattr(
        "guanlan.daily.search_web",
        lambda *_args, **_kwargs: [
            {
                "title": "WPS AI 官方入口",
                "url": "https://www.wps.cn/ai",
                "snippet": "官方说明。",
                "source_type": "办公软件/AI Office/SaaS",
                "evidence_role": "company_primary",
            },
            {
                "title": "WPS AI 外部评测",
                "url": "https://media.example.com/wps-ai-review",
                "snippet": "外部评测。",
                "source_type": "科技/开发者社区",
                "evidence_role": "fresh_news",
            },
        ],
    )
    monkeypatch.setattr("guanlan.daily.fetch_feed_source", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("guanlan.daily.fetch_hotnews", lambda **_kwargs: [])
    monkeypatch.setattr("guanlan.daily.build_trend_report", lambda *_args, **_kwargs: {"trend_count": 0, "sample_count": 0, "trends": [], "source_distribution": {}, "sample_boundaries": []})
    monkeypatch.setattr("guanlan.daily.build_hotnews_brief", lambda *_args, **_kwargs: {"sample_count": 0, "trend_count": 0, "sample_boundaries": [], "warnings": [], "highlights": []})
    monkeypatch.setattr(
        "guanlan.web.read.read_url_with_trace",
        lambda url, **_kwargs: {
            "url": url,
            "content": "这是一段来自原文的事实摘要。WPS AI 文章讨论了办公文档、PPT 和表格场景，并给出实际使用边界。",
            "trace": {"selected_backend": "direct"},
            "quality_report": {"score": 80, "label": "usable", "usable": True},
        },
    )

    report = build_daily_report("WPS AI", profile="china", limit=4, read_top=2)

    assert report["diagnostics"]["read"]["status"] == "ok"
    assert report["read_pack"]["schema_version"] == "representative_read_pack_v1"
    assert report["read_pack"]["summary"]["usable_count"] == 2
    assert len(report["read_evidence"]) == 2
    assert report["read_evidence"][0]["schema_version"] == "read_evidence_v1"
    assert any(item.get("read_evidence", {}).get("summary") for item in report["items"])
    markdown = format_daily_markdown(report)
    assert "原文回读" in markdown


def test_daily_prefers_ai_vertical_for_plain_ai_queries():
    assert _resolve_daily_feed_source(feed_source="auto", query="AI 行业", route_intents=["industry"], preset="") == "ai-vertical"


def test_daily_keeps_brand_owned_community_and_seo_boundaries():
    community = {
        "title": "WPS AI 用户实测",
        "url": "https://forum.wps.cn/topic/123",
        "source": "办公软件/AI Office/SaaS",
        "origin": "search",
        "evidence_role": "company_primary",
    }
    seo = {
        "title": "WPS 怎么领取 AI 功能 3步激活智能助手",
        "url": "https://jsbg-wps.com.cn/a",
        "source": "通用网页",
        "origin": "search",
        "evidence_role": "fresh_news",
    }
    nav_site = {
        "title": "Wps Ai_ppt一键生成 | Ai写作文档 | Ai表格处理 -ai资源导航站",
        "url": "https://web-note.cn/article/ai-ppt/424.html",
        "source": "通用网页",
        "origin": "search",
        "evidence_role": "fresh_news",
    }

    assert _daily_section_key(community) == "community"
    assert not _daily_is_soft_seo(community)
    assert _daily_is_soft_seo(seo)
    assert _daily_is_soft_seo(nav_site)
    assert _daily_section_key(seo) == "other"


def test_daily_source_tiers_and_freshness_are_editorial_boundaries():
    official = classify_daily_source(
        {
            "title": "WPS AI 官方发布",
            "url": "https://www.wps.cn/ai",
            "evidence_role": "company_primary",
        }
    )
    community = classify_daily_source(
        {
            "title": "WPS AI 用户反馈",
            "url": "https://forum.wps.cn/topic/1",
            "evidence_role": "company_primary",
        }
    )
    weak = classify_daily_source(
        {
            "title": "WPS Office 官网下载 免费下载安装",
            "url": "https://wpsworks.cn/",
            "evidence_role": "fresh_news",
        }
    )
    today = normalize_daily_freshness("2026-05-21", generated_at="2026-05-21T10:00:00+00:00", time_window="today")
    old = normalize_daily_freshness("2026-05-01", generated_at="2026-05-21T10:00:00+00:00", time_window="3d")

    assert official["source_tier"] == "A"
    assert community["source_tier"] == "C"
    assert weak["source_tier"] == "D"
    assert today["freshness"] == "today"
    assert today["in_window"] is True
    assert old["freshness"] == "background"
    assert old["in_window"] is False


def test_daily_storylines_cluster_related_evidence_and_actions():
    items = [
        {
            "title": "WPS AI 发布智能办公新能力",
            "url": "https://www.wps.cn/ai/new",
            "summary": "官方发布智能办公新能力。",
            "source": "WPS",
            "source_tier": "A",
            "source_tier_label": "A 一手/官方/监管",
            "source_section": "official",
            "freshness": "today",
            "freshness_label": "今天",
            "evidence_role": "company_primary",
        },
        {
            "title": "WPS AI 发布智能办公新能力 媒体观察",
            "url": "https://36kr.com/p/wps-ai-new",
            "summary": "外部媒体观察办公 AI 商业化。",
            "source": "36氪",
            "source_tier": "B",
            "source_tier_label": "B 媒体/产业/开发者",
            "source_section": "ecosystem",
            "freshness": "today",
            "freshness_label": "今天",
            "evidence_role": "industry_report",
        },
    ]

    storylines = build_daily_storylines(items, query="WPS AI", edition="brand", time_window="today")

    assert storylines
    assert storylines[0]["freshness"] == "today"
    assert storylines[0]["recommended_action"] in {"深写观察", "立即跟进"}
    assert any((story["source_spread"]["tier_counts"].get("A", 0) >= 1) for story in storylines)


def test_daily_selection_prefers_stronger_items_over_soft_seo(monkeypatch):
    monkeypatch.setattr(
        "guanlan.daily.build_route_plan",
        lambda *args, **kwargs: _Plan(
            {
                "query": args[0],
                "primary_intents": ["wps_office"],
                "secondary_intents": [],
                "preferred_scopes": ["wps_office", "business", "tech_dev"],
                "warnings": [],
            }
        ),
    )
    rows = [
        {
            "title": "WPS 怎么领取 AI 功能 3步激活智能助手",
            "url": "https://jsbg-wps.com.cn/a",
            "snippet": "领取 AI 功能。",
            "source_type": "通用网页",
            "evidence_role": "fresh_news",
        },
        {
            "title": "WPS AI 外部观察",
            "url": "https://cloud.tencent.com/developer/article/1",
            "snippet": "第三方开发者社区讨论 WPS AI 办公体验。",
            "source_type": "科技/开发者社区",
            "evidence_role": "fresh_news",
        },
        {
            "title": "WPS AI 官方入口",
            "url": "https://ai.wps.cn/",
            "snippet": "官方产品入口。",
            "source_type": "办公软件/AI Office/SaaS",
            "evidence_role": "company_primary",
        },
        {
            "title": "WPS AI 社区讨论",
            "url": "https://forum.wps.cn/topic/1",
            "snippet": "用户公开讨论。",
            "source_type": "办公软件/AI Office/SaaS",
            "evidence_role": "company_primary",
        },
    ]
    monkeypatch.setattr("guanlan.daily.search_web", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr("guanlan.daily.fetch_feed_source", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("guanlan.daily.fetch_hotnews", lambda **_kwargs: [])
    monkeypatch.setattr("guanlan.daily.build_trend_report", lambda *_args, **_kwargs: {"trend_count": 0, "sample_count": 0, "trends": [], "source_distribution": {}, "sample_boundaries": []})
    monkeypatch.setattr("guanlan.daily.build_hotnews_brief", lambda *_args, **_kwargs: {"sample_count": 0, "trend_count": 0, "sample_boundaries": [], "warnings": [], "highlights": []})

    report = build_daily_report("WPS AI", profile="china", limit=3, search_limit=10)

    titles = {item["title"] for item in report["items"]}
    assert "WPS AI 外部观察" in titles
    assert "WPS 怎么领取 AI 功能 3步激活智能助手" not in titles


def test_daily_renders_overflow_candidate_pool(monkeypatch):
    monkeypatch.setattr(
        "guanlan.daily.build_route_plan",
        lambda *args, **kwargs: _Plan(
            {
                "query": args[0],
                "primary_intents": ["wps_office"],
                "secondary_intents": [],
                "preferred_scopes": ["wps_office", "business"],
                "warnings": [],
            }
        ),
    )
    rows = [
        {
            "title": "WPS AI 外部报道",
            "url": "https://cloud.tencent.com/developer/article/1",
            "snippet": "第三方报道。",
            "source_type": "科技/开发者社区",
            "evidence_role": "fresh_news",
        },
        {
            "title": "WPS AI 官方入口",
            "url": "https://ai.wps.cn/",
            "snippet": "官方入口。",
            "source_type": "办公软件/AI Office/SaaS",
            "evidence_role": "company_primary",
        },
        {
            "title": "WPS AI 社区吐槽",
            "url": "https://forum.wps.cn/topic/2",
            "snippet": "用户样本。",
            "source_type": "办公软件/AI Office/SaaS",
            "evidence_role": "company_primary",
        },
        {
            "title": "WPS AI 安全合规",
            "url": "https://security.wps.cn/",
            "snippet": "安全入口。",
            "source_type": "办公软件/AI Office/SaaS",
            "evidence_role": "security_advisory",
        },
        {
            "title": "WPS Office官网下载 免费下载安装",
            "url": "https://wpsworks.cn/",
            "snippet": "下载页。",
            "source_type": "通用网页",
            "evidence_role": "low_value_seo",
        },
        {
            "title": "合规性与数据隐私 - Power Platform",
            "url": "https://learn.microsoft.com/zh-cn/power-platform/admin/wp-compliance-data-privacy",
            "snippet": "企业合规文档。",
            "source_type": "公司一手资料",
            "evidence_role": "company_primary",
        },
    ]
    monkeypatch.setattr("guanlan.daily.search_web", lambda *_args, **_kwargs: rows)

    report = build_daily_report(
        "WPS AI",
        profile="china",
        limit=2,
        search_limit=10,
        include_feeds=False,
        include_hotnews=False,
        overflow_limit=3,
    )

    assert report["overflow_count"] == 3
    overflow_titles = {item["title"] for item in report["overflow_items"]}
    assert "WPS AI 社区吐槽" in overflow_titles
    assert "合规性与数据隐私 - Power Platform" not in overflow_titles
    markdown = format_daily_markdown(report)
    context = format_daily_context(report)
    assert "## 候补线索池" in markdown
    assert "WPS AI 社区吐槽" in markdown
    assert "overflow_items" in context


def test_daily_formatters_and_save_output(tmp_path: Path):
    report = {
        "title": "测试日报",
        "query": "测试主题",
        "mode": "query_daily",
        "generated_at": "2026-05-21T10:00:00+00:00",
        "candidate_count": 3,
        "item_count": 1,
        "feed_source": "curated",
        "boundary": "日报是公开信号与证据入口。",
        "route_plan": {"primary_intents": ["tech"], "secondary_intents": [], "warnings": []},
        "source_mix": {"company_primary": 1},
        "highlights": ["[search] 测试标题 (company_primary / official_primary)"],
        "items": [
            {
                "origin": "search",
                "source": "company_primary",
                "evidence_role": "official_primary",
                "title": "测试标题",
                "url": "https://example.com/a",
                "summary": "测试摘要",
                "merged_from": ["search"],
            }
        ],
        "sections": [
            {
                "key": "official",
                "title": "一手动态",
                "summary": "这一栏主要回答官方今天对外说了什么。",
                "items": [
                    {
                        "origin": "search",
                        "source": "company_primary",
                        "evidence_role": "official_primary",
                        "title": "测试标题",
                        "url": "https://example.com/a",
                        "summary": "测试摘要",
                        "merged_from": ["search"],
                        "_daily_anchor": 1,
                    }
                ],
            }
        ],
        "hotnews_brief": {"highlights": []},
        "boundaries": ["需要回读原文。"],
        "next_steps": ["guanlan read 'https://example.com/a' --quality-report"],
    }

    markdown = format_daily_markdown(report)
    context = format_daily_context(report)

    assert "观澜日报 / 测试日报" in markdown
    assert "今日重点" in markdown
    assert "观察价值" in markdown
    assert "观澜日报上下文 / 测试日报" in context

    output = tmp_path / "daily.json"
    saved = save_daily_output(report, str(output), output_format="json")
    assert saved == output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["title"] == "测试日报"


def test_daily_history_delta_and_record(tmp_path: Path):
    history = tmp_path / "history.jsonl"
    previous = {
        "title": "WPS AI",
        "query": "WPS AI",
        "generated_at": "2026-05-20T10:00:00+00:00",
        "storylines": [
            {
                "id": "daily-old",
                "headline": "旧主线",
                "risk_level": "medium",
                "recommended_action": "深写观察",
                "confidence": "medium",
            },
            {
                "id": "daily-continued",
                "headline": "延续主线",
                "risk_level": "high",
                "recommended_action": "立即跟进",
                "confidence": "high",
            },
        ],
    }
    record_daily_history(previous, history_path=str(history))
    current = {
        "title": "WPS AI",
        "query": "WPS AI",
        "generated_at": "2026-05-21T10:00:00+00:00",
        "storylines": [
            {
                "id": "daily-new",
                "headline": "新增主线",
                "risk_level": "low",
                "recommended_action": "深写观察",
                "confidence": "medium",
            },
            {
                "id": "daily-continued",
                "headline": "延续主线",
                "risk_level": "high",
                "recommended_action": "立即跟进",
                "confidence": "high",
            },
        ],
    }

    delta = build_daily_history_delta(current, history_path=str(history), compare_days=3)

    assert delta["enabled"] is True
    assert {row["headline"] for row in delta["new_storylines"]} == {"新增主线"}
    assert {row["headline"] for row in delta["continued_storylines"]} == {"延续主线"}
    assert {row["headline"] for row in delta["cooled_storylines"]} == {"旧主线"}
    assert delta["persistent_risks"][0]["headline"] == "延续主线"


def test_daily_html_and_im_renderers_keep_source_boundaries(tmp_path: Path):
    report = {
        "schema_version": "daily_report_v1",
        "title": "WPS AI",
        "query": "WPS AI",
        "mode": "query_daily",
        "generated_at": "2026-05-21T10:00:00+00:00",
        "time_window": "3d",
        "candidate_count": 2,
        "storylines": [
            {
                "id": "daily-wps",
                "headline": "WPS AI 外部观察",
                "what_happened": "外部媒体观察 WPS AI。",
                "why_it_matters": "补足官方之外的行业语境。",
                "freshness": "today",
                "freshness_label": "今天",
                "risk_level": "medium",
                "recommended_action": "深写观察",
                "confidence": "medium",
                "teams": ["PR", "市场"],
                "evidence_items": [
                    {
                        "title": "WPS AI 外部观察",
                        "url": "https://36kr.com/p/wps-ai",
                        "source": "36氪",
                        "source_tier": "B",
                    }
                ],
            }
        ],
        "editorial_decisions": [
            {
                "headline": "WPS AI 外部观察",
                "recommended_action": "深写观察",
                "teams": ["PR", "市场"],
                "risk_level": "medium",
            }
        ],
        "source_health": {"today_count": 1, "main_weak_lead_count": 0},
        "editorial_health": {"status": "warn", "warnings": ["外部报道仍需回读原文。"]},
        "overflow_items": [],
        "highlights": ["外部层可核验。"],
        "boundaries": ["社区样本不能外推总体。"],
    }

    html = format_daily_html(report)
    im = format_daily_im(report)
    html_path = tmp_path / "daily.html"
    im_path = tmp_path / "daily.im.txt"

    save_daily_output(report, str(html_path), output_format="html")
    save_daily_output(report, str(im_path), output_format="im")

    assert "<!doctype html>" in html
    assert "WPS AI 外部观察" in html
    assert "【观澜日报】WPS AI" in im
    assert "风险 medium" in im
    assert "36氪" in html_path.read_text(encoding="utf-8")
    assert "深写观察" in im_path.read_text(encoding="utf-8")


def test_daily_cli_can_return_json(capsys):
    from guanlan.cli import main

    payload = {
        "title": "测试日报",
        "items": [],
        "candidate_count": 0,
        "item_count": 0,
        "feed_source": "curated",
        "mode": "query_daily",
        "generated_at": "2026-05-21T10:00:00+00:00",
        "boundary": "日报是公开信号与证据入口。",
        "route_plan": {},
        "source_mix": {},
        "highlights": [],
        "hotnews_brief": {},
        "boundaries": [],
        "next_steps": [],
    }
    with patch("guanlan.daily.build_daily_report", return_value=payload), patch("sys.argv", ["guanlan", "daily", "AI 行业", "--json"]):
        main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["title"] == "测试日报"
