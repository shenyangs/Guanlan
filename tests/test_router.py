# -*- coding: utf-8 -*-
"""Tests for Guanlan demand routing and source taxonomy."""

from unittest.mock import patch

from guanlan.router import build_route_plan, format_route_plan_markdown
from guanlan.source_taxonomy import source_card_for_domain


def test_route_plan_detects_purchase_reputation_need():
    plan = build_route_plan("小米 YU7 用户评价 值不值得买", profile="china")

    assert "reputation" in plan.primary_intents + plan.secondary_intents
    assert "purchase_advice" in plan.primary_intents + plan.secondary_intents
    assert "social_web" in plan.preferred_scopes
    assert "zhihu.com" in plan.target_sites
    assert any("guanlan pulse" in command for command in plan.recommended_commands)
    assert plan.advisor_recommended is True
    assert any("社交" in warning or "购买" in warning for warning in plan.warnings)


def test_route_plan_detects_policy_and_avoids_social_primary():
    plan = build_route_plan("人工智能 监管 政策 最新通知", profile="china")

    assert plan.primary_intents[0] == "policy"
    assert "gov" in plan.preferred_scopes
    assert "party_central" in plan.preferred_scopes
    assert "社交/内容平台" in plan.avoid_as_primary
    assert "baidu-rss" in plan.recommended_feeds
    assert any("--preset policy" in command for command in plan.recommended_commands)
    assert plan.read_top >= 2


def test_route_plan_detects_academic_indexing_need():
    plan = build_route_plan("EI会议的所有标准和要求", profile="china")

    assert "academic" in plan.primary_intents + plan.secondary_intents
    assert "academic" in plan.preferred_scopes
    assert "elsevier.com" in plan.target_sites
    assert any("--preset academic" in command for command in plan.recommended_commands)
    assert any("学术会议" in warning or "检索" in warning for warning in plan.warnings)


def test_route_plan_detects_english_company_primary_need():
    plan = build_route_plan("OpenAI API pricing release notes", profile="english")

    assert plan.primary_intents[0] == "company_primary"
    assert "company_primary" in plan.preferred_scopes
    assert "developer" in plan.preferred_scopes
    assert "company_primary" in plan.evidence_roles
    assert any("--preset company --profile english" in command for command in plan.recommended_commands)


def test_route_plan_keeps_cjk_ai_query_in_china_context_without_explicit_profile():
    plan = build_route_plan("AI 相关内容")

    assert plan.backend_hint == ["baidu", "bing", "duckduckgo"]
    assert any("--profile china" in command for command in plan.recommended_commands)


def test_route_plan_detects_english_policy_need():
    plan = build_route_plan("AI regulation NIST standard policy", profile="english")

    assert "global_policy" in plan.primary_intents + plan.secondary_intents
    assert "global_official" in plan.preferred_scopes
    assert "global_news" in plan.preferred_scopes
    assert any("--preset global_policy --profile english" in command for command in plan.recommended_commands)


def test_route_plan_detects_standards_compliance_need():
    plan = build_route_plan("SOC2 合规认证标准和审计要求", profile="china")

    assert "standards_compliance" in plan.primary_intents + plan.secondary_intents
    assert "global_official" in plan.preferred_scopes
    assert "standard_original" in plan.evidence_roles
    assert "厂商单方合规声明" in plan.avoid_as_primary
    assert any("--scope global_official" in command for command in plan.recommended_commands)


def test_route_plan_detects_medical_health_need():
    plan = build_route_plan("某药品 FDA 临床治疗指南和副作用", profile="china")

    assert "medical_health" in plan.primary_intents + plan.secondary_intents
    assert plan.risk_level == "high"
    assert "clinical_guideline" in plan.evidence_roles
    assert any("医疗健康" in warning for warning in plan.warnings)


def test_route_plan_detects_legal_judicial_need():
    plan = build_route_plan("合同侵权诉讼 判决依据和司法解释", profile="china")

    assert "legal_judicial" in plan.primary_intents + plan.secondary_intents
    assert plan.risk_level == "high"
    assert "statute_original" in plan.evidence_roles
    assert "gov" in plan.preferred_scopes


def test_route_plan_recommends_rss_sources_by_need():
    wechat = build_route_plan("今天微信公众号有什么 AI 热文", profile="china")
    reading = build_route_plan("最近有什么值得读的 Agent 技术文章", profile="china")
    generic = build_route_plan("帮我查一下某公司情况", profile="china")

    assert "wechat-rss" in wechat.recommended_feeds
    assert "baidu-rss" in wechat.recommended_feeds
    assert "curated" in reading.recommended_feeds
    assert generic.recommended_feeds == []
    assert "guanlan feeds wechat-rss --limit 80" in wechat.recommended_commands
    assert any(command.startswith("guanlan feeds curated") for command in reading.recommended_commands)


def test_format_route_plan_markdown_is_agent_readable():
    plan = build_route_plan("Python Agent 框架 对比 github issue")
    text = format_route_plan_markdown(plan)

    assert "# 观澜路由计划" in text
    assert "技术" not in text or "tech" in text
    assert "证据角色" in text
    assert "推荐 RSS" in text
    assert "建议命令" in text
    assert "查询改写" in text


def test_source_card_separates_authority_and_sample_value():
    gov = source_card_for_domain("www.gov.cn")
    zhihu = source_card_for_domain("zhihu.com")

    assert gov.authority_score > zhihu.authority_score
    assert zhihu.sample_value > gov.sample_value
    assert "sample_bias" in zhihu.risk_tags


def test_route_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "route", "某产品 用户评价 值不值得买", "--json"]):
        main()

    captured = capsys.readouterr()
    assert '"primary_intents"' in captured.out
    assert "purchase_advice" in captured.out
