# -*- coding: utf-8 -*-
"""Tests for reusable recipes and page diagnosis."""

from guanlan.page_diagnosis import diagnose_page, format_page_diagnosis_markdown
from guanlan.recipes import (
    build_recipe_plan,
    format_recipe_plan_markdown,
    list_recipes,
    suggest_recipe,
)


def test_recipe_plan_builds_finance_workflow():
    plan = build_recipe_plan("finance-risk", "宁德时代 股价 财报 公告 最近风险")

    assert plan["recipe"]["id"] == "finance-risk"
    assert any("guanlan stock detail" in command for command in plan["commands"])
    assert any("--scope finance_disclosure" in command for command in plan["commands"])
    assert "不输出买入、卖出或持有建议。" in plan["boundaries"]
    assert "结构化行情" in format_recipe_plan_markdown(plan)


def test_recipe_list_and_suggestion_cover_university():
    recipes = list_recipes()
    ids = {item["id"] for item in recipes}

    assert "university-advisor" in ids
    assert suggest_recipe("南京师范大学中北学院 计算机 导师 招生").id == "university-advisor"


def test_page_diagnosis_marks_dynamic_shell_without_network():
    payload = diagnose_page(
        "https://xueqiu.com/snowman/provider/zz/gp_detail?symbol=SH600519",
        fetch=False,
        content=(
            "window.location.href='//finance.qq.com/gsfinance/upgrade_browser.htm'; "
            "var url='https://galileotelemetry.tencent.com/collect';"
        ),
    )

    assert payload["page_type"] == "dynamic_shell"
    assert payload["usable_as_evidence"] is False
    assert "script_or_app_shell" in payload["signals"]
    assert any("guanlan stock detail" in command for command in payload["recommended_commands"])
    assert "页面诊断" in format_page_diagnosis_markdown(payload)


def test_page_diagnosis_marks_readable_article_without_network():
    payload = diagnose_page(
        "https://example.com/article",
        fetch=False,
        content="这是一段可读正文，包含清楚的事实信息、来源说明和上下文。" * 20,
    )

    assert payload["page_type"] == "readable_article"
    assert payload["usable_as_evidence"] is True
    assert any("archive add" in command for command in payload["recommended_commands"])
