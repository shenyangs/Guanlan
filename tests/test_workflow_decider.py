# -*- coding: utf-8 -*-
"""Tests for Guanlan light/heavy workflow decisions."""

from guanlan.workflow_decider import (
    DIRECT,
    GUIDED,
    INVESTIGATE,
    decide_workflow,
    format_workflow_decision_markdown,
)


def test_simple_lookup_stays_direct_and_light():
    decision = decide_workflow("观澜 官网", command="search", profile="china")

    assert decision.tier == DIRECT
    assert decision.recommended_entrypoint == "search"
    assert decision.do_not_overthink is True
    assert decision.recommended_limit >= 80
    assert "research" not in decision.command_path[:1]


def test_policy_research_uses_guided_workflow():
    decision = decide_workflow("人工智能 监管 政策 最新通知", command="search", profile="china")

    assert decision.tier == GUIDED
    assert decision.recommended_entrypoint == "research"
    assert "route" in decision.command_path
    assert "research" in decision.command_path
    assert decision.recommended_limit >= 80
    assert decision.recommended_read_top >= 5


def test_explicit_compare_uses_investigate_tier():
    decision = decide_workflow("OpenAI Claude Gemini 对比 价格 风险", command="search", profile="china")

    assert decision.tier == INVESTIGATE
    assert decision.recommended_entrypoint == "compare"
    assert decision.minimum_steps >= 3
    assert "WebFetch" in " ".join(decision.fallback_policy)


def test_tech_query_reminds_rss_without_forcing_basic_search_heavy():
    decision = decide_workflow("Python Agent 框架 对比 github issue", command="research", profile="china")

    assert decision.tier in {GUIDED, INVESTIGATE}
    assert "feeds" in decision.command_path or any("RSS" in item for item in decision.fallback_policy)


def test_workflow_markdown_is_agent_readable():
    decision = decide_workflow("某公司 档案 风险 舆情", command="search", profile="china")
    text = format_workflow_decision_markdown(decision)

    assert "观澜工作流分流" in text
    assert "建议执行链路" in text
    assert "不要过度思考" in text
    assert "300000 ms" in text
    assert "Timeout 单位契约" in text
    assert "裸数字" in text


def test_workflow_json_exposes_timeout_seconds_and_ms():
    decision = decide_workflow("某公司 档案 风险 舆情", command="search", profile="china")
    payload = decision.to_dict()

    assert payload["timeout_budget_seconds"] == 300
    assert payload["timeout_budget_ms"] == 300000
    assert any("timeout_ms" in item for item in payload["timeout_unit_contract"])
