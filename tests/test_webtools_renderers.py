# -*- coding: utf-8 -*-
"""Tests for search/read/research renderers."""
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
                            "不要在面向用户的回答里顺嘴写“Guanlan 崩了/抽风了/挂了/炸了/翻车/拉胯/坏了”。",
                            "如果只是目标页公开读取超时或源站响应慢，应表述为“已按 Guanlan 定点补证路线读取目标页并保留来源边界”。",
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
    assert "抽风" in context
    assert "定点补证路线" in context
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
    assert "抽风" in trace
    assert "定点补证路线" in trace
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
