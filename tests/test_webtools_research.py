# -*- coding: utf-8 -*-
"""Tests for research packet assembly and evidence guards."""
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

    def fake_read(url, **_kwargs):
        content = f"READ {url}"
        return {
            "url": url,
            "content": content,
            "quality": {"score": 80, "chars": len(content), "label": "clean"},
            "quality_report": {"usable": True, "score": 80, "label": "clean"},
            "trace": {"selected_backend": "direct"},
        }

    monkeypatch.setattr("guanlan.web.read.read_url_with_trace", fake_read)

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
    assert packet["readings"][0]["schema_version"] == "read_evidence_v1"
    assert packet["read_pack"]["schema_version"] == "representative_read_pack_v1"
    assert packet["read_pack"]["summary"]["usable_count"] == 2
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


def test_query_for_research_job_prefers_query_rewrite_for_general_job():
    strategy = webtools.build_query_strategy(
        "苹果",
        route_plan=webtools.build_route_plan("苹果", scope="ecommerce").to_dict(),
        quality={"requested_scope": "ecommerce"},
    )

    selected = webtools._query_for_research_job("苹果", "general", "open_web", strategy)

    assert selected != "苹果"
    assert "iPhone" in selected


def test_query_for_research_job_prefers_entity_compare_for_multi_entity_general_job():
    strategy = webtools.build_query_strategy(
        "珠海 澳门 香港 深圳 广州 GDP 对比",
        route_plan=webtools.build_route_plan("珠海 澳门 香港 深圳 广州 GDP 对比").to_dict(),
        quality={},
    )

    selected = webtools._query_for_research_job("珠海 澳门 香港 深圳 广州 GDP 对比", "general", "open_web", strategy)

    assert "对比" in selected
    assert "珠海 澳门 香港 深圳" in selected


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
            "recovery_mode": "off",
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
    ledger = packet["claim_ledger"]
    assert ledger["mode"] == "claim_ledger_v1"
    assert ledger["conflict_count"] >= 3
    assert {"price", "parameter_count", "percentage_metric"} <= set(ledger["category_counts"])
    assert any(claim["conflict_set"] for claim in ledger["claims"] if claim["category"] == "price")
    md = webtools.format_research_markdown(packet)
    assert "结构化事实差异" in md
    assert "## 事实台账" in md
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
