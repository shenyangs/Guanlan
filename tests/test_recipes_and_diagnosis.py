# -*- coding: utf-8 -*-
"""Tests for reusable recipes and page diagnosis."""

from guanlan.browser_assist import (
    build_browser_assist_adapter_contract,
    check_browser_assist_adapter,
    run_browser_assist_adapter,
)
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


def test_recipe_plan_builds_trajectory_map_workflow():
    plan = build_recipe_plan("trajectory-map", "Cursor 发展历程 竞品格局")
    rendered = format_recipe_plan_markdown(plan)

    assert plan["recipe"]["id"] == "trajectory-map"
    assert "起源与关键节点" in plan["recipe"]["evidence_layers"]
    assert any("guanlan timeline" in command for command in plan["commands"])
    assert any("guanlan dossier" in command for command in plan["commands"])
    assert any("guanlan compare" in command for command in plan["commands"])
    assert any("guanlan sources explain" in command for command in plan["commands"])
    assert plan["timeout_budget_seconds"] == 300
    assert plan["timeout_budget_ms"] == 300000
    assert any("timeout_ms" in item for item in plan["timeout_unit_contract"])
    assert "300000 ms" in rendered
    assert "不要凭印象编造竞品清单" in rendered
    assert suggest_recipe("帮我搞懂 Manus Agent 的来龙去脉和竞品格局").id == "trajectory-map"


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
    assert payload["browser_assist"]["recommended"] is True
    assert "read_cookies" in payload["browser_assist"]["forbidden_actions"]
    assert payload["browser_assist"]["browser_assist_task"]["status"] == "requires_user_approval"
    assert any("browser-assist run" in command for command in payload["recommended_commands"])
    assert any("guanlan stock detail" in command for command in payload["recommended_commands"])
    rendered = format_page_diagnosis_markdown(payload)
    assert "页面诊断" in rendered
    assert "浏览器辅助补证" in rendered


def test_page_diagnosis_marks_readable_article_without_network():
    payload = diagnose_page(
        "https://example.com/article",
        fetch=False,
        content="这是一段可读正文，包含清楚的事实信息、来源说明和上下文。" * 20,
    )

    assert payload["page_type"] == "readable_article"
    assert payload["usable_as_evidence"] is True
    assert payload["browser_assist"]["recommended"] is False
    assert any("archive add" in command for command in payload["recommended_commands"])


def test_browser_assist_plan_is_read_only_and_user_authorized():
    payload = diagnose_page(
        "https://www.xiaohongshu.com/explore/example",
        fetch=False,
        content="请先登录后查看完整内容",
    )

    plan = payload["browser_assist"]
    assert plan["recommended"] is True
    assert plan["evidence_role"] == "user_visible_sample"
    assert "read_visible_text" in plan["allowed_actions"]
    assert "post" in plan["forbidden_actions"]
    assert plan["browser_assist_task"]["output_contract"]["visible_page_only"] is True
    assert plan["browser_assist_task"]["output_contract"]["session_dependent"] is True
    assert plan["browser_assist_task"]["execution_contract"]["version"] == "browser_visible_v2"
    assert "visible_comment_summary" in plan["browser_assist_task"]["extract_fields"]
    assert plan["browser_assist_task"]["host_browser_contract"]["uses_existing_browser_session"] is True
    assert plan["browser_assist_task"]["host_browser_contract"]["manual_copy_is_fallback_only"] is True
    assert plan["browser_assist_task"]["host_browser_contract"]["cookie_access_requires_separate_explicit_authorization"] is True
    assert plan["cookie_access_policy"]["can_escalate"] == "yes_but_only_after_separate_explicit_user_authorization"
    assert "Cookie" in plan["user_prompt"]


def test_browser_assist_adapter_contract_keeps_xhs_optional_and_explicit():
    contract = build_browser_assist_adapter_contract("xhs-cli", platform="xiaohongshu")

    assert contract["id"] == "xhs-cli"
    assert contract["stability"] == "experimental"
    assert contract["capability_layer"] == "extractor"
    assert contract["platform_supported"] is True
    assert contract["safety"]["cookie_access_requires_separate_explicit_authorization"] is True


def test_browser_assist_adapter_contract_exposes_browser_use():
    contract = build_browser_assist_adapter_contract("browser-use", platform="xiaohongshu")

    assert contract["id"] == "browser-use"
    assert contract["stability"] == "best-effort"
    assert contract["capability_layer"] == "opener"
    assert contract["platform_supported"] is True
    assert contract["safety"]["cookie_access_requires_separate_explicit_authorization"] is True


def test_browser_assist_adapter_check_is_read_only_and_actionable(monkeypatch):
    monkeypatch.delenv("GUANLAN_BROWSER_ASSIST_XHS_CLI_COMMAND", raising=False)

    result = check_browser_assist_adapter("xhs-cli", platform="xiaohongshu")

    assert result["status"] == "warn"
    assert result["ready"] is False
    assert result["dry_run_available"] is False
    assert any("GUANLAN_BROWSER_ASSIST_XHS_CLI_COMMAND" in hint for hint in result["repair_hints"])


def test_browser_assist_external_adapter_requires_template_before_execution(monkeypatch):
    monkeypatch.delenv("GUANLAN_BROWSER_ASSIST_XHS_CLI_COMMAND", raising=False)

    result = run_browser_assist_adapter(
        "https://www.xiaohongshu.com/explore/demo",
        adapter="xhs-cli",
        execute=True,
    )

    assert result["adapter"] == "xhs-cli"
    assert result["status"] == "adapter_config_required"
    assert "GUANLAN_BROWSER_ASSIST_XHS_CLI_COMMAND" in result["setup_hint"]
