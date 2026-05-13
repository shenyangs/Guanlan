# -*- coding: utf-8 -*-
"""Tests for reusable recipes and page diagnosis."""

from guanlan.browser_assist import (
    build_browser_assist_adapter_contract,
    build_opencli_browser_bridge_setup_plan,
    build_openguanlan_browser_bridge_setup_plan,
    check_browser_assist_adapter,
    normalize_browser_visible_payload,
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


def test_recipe_plan_builds_wps_office_radar_workflow():
    plan = build_recipe_plan("wps-office-radar", "WPS AI PPT Agent 办公选题 最近热点")
    rendered = format_recipe_plan_markdown(plan)

    assert plan["recipe"]["id"] == "wps-office-radar"
    assert plan["read_top"] == 5
    assert plan["timeout_budget_seconds"] == 240
    assert "AI/科技媒体和 RSS" in plan["recipe"]["evidence_layers"]
    assert any("--preset wps_office" in command for command in plan["commands"])
    assert any("--scope wps_office" in command for command in plan["commands"])
    assert any("feeds curated" in command for command in plan["commands"])
    assert any("hotnews today" in command for command in plan["commands"])
    assert "不要把任务缩成品牌稿检索" in rendered
    assert suggest_recipe("WPS AI PPT Agent 办公选题 最近热点").id == "wps-office-radar"


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
    assert plan["cookie_access_policy"]["can_escalate"] == "yes_but_only_after_separate_explicit_credential_authorization"
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


def test_browser_assist_open_cli_upgrades_when_opencli_bridge_exists(monkeypatch):
    def fake_which(name: str) -> str | None:
        if name == "opencli":
            return "/bin/echo"
        if name == "open":
            return "/usr/bin/open"
        return None

    monkeypatch.setattr("shutil.which", fake_which)

    contract = build_browser_assist_adapter_contract("opencli", platform="zhihu")
    check = check_browser_assist_adapter("open-cli", platform="zhihu")

    assert contract["id"] == "open-cli"
    assert contract["kind"] == "opencli_browser_bridge"
    assert contract["capability_layer"] == "extractor"
    assert contract["capabilities"]["can_extract_visible_text"] is True
    assert contract["capabilities"]["can_wait_dynamic_ready"] is True
    assert contract["capabilities"]["can_scroll_until_min_items"] is True
    assert contract["capabilities"]["can_read_private_account_visible_pages"] is True
    assert contract["capabilities"]["credential_material_access_allowed"] is False
    assert contract["opencli_profile"]["browser_bridge_available"] is True
    assert check["ready"] is True
    assert check["dry_run_mode"] == "opencli_doctor"
    assert check["can_extract_visible_text"] is True


def test_browser_assist_open_cli_stays_opener_without_opencli(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/open" if name == "open" else None)

    contract = build_browser_assist_adapter_contract("open-cli")

    assert contract["kind"] == "system_open"
    assert contract["capability_layer"] == "opener"
    assert contract["capabilities"]["can_extract_visible_text"] is False
    assert contract["opencli_profile"]["browser_bridge_available"] is False


def test_browser_assist_openguanlan_is_native_planned_adapter(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)

    contract = build_browser_assist_adapter_contract("openguanlan")

    assert contract["id"] == "openguanlan"
    assert contract["kind"] == "guanlan_native_browser_bridge"
    assert contract["capability_layer"] == "extractor"
    assert contract["available"] is False
    assert contract["native_setup_guidance"]["guanlan_command"] == "guanlan browser-assist setup-openguanlan --json"


def test_openguanlan_browser_bridge_setup_plan_does_not_require_opencli(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)

    plan = build_openguanlan_browser_bridge_setup_plan()

    assert plan["adapter"] == "openguanlan"
    assert plan["status"] == "packaged_needs_install_entrypoint"
    assert plan["current_default"] == "host-browser"
    assert plan["runtime_packaged"] is True
    assert plan["extension_manifest_exists"] is True
    assert "opencli" in plan["user_install_boundary"][0]
    assert plan["safety"]["credential_material_access_allowed"] is False


def test_opencli_browser_bridge_setup_plan_is_explicit_and_manual(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)

    plan = build_opencli_browser_bridge_setup_plan()

    assert plan["status"] == "needs_cli_install"
    assert plan["execute"] is False
    assert plan["cli_install_command"] == ["npm", "install", "-g", "@jackwener/opencli@latest"]
    assert plan["browser_extension"]["manual_user_step_required"] is True
    assert plan["safety"]["does_not_install_chrome_extension_automatically"] is True
    assert plan["safety"]["credential_material_access_allowed"] is False


def test_browser_visible_payload_allows_target_private_account_boundary():
    payload = normalize_browser_visible_payload(
        {
            "url": "https://example.com/account/orders/123",
            "title": "目标订单页",
            "visible_text": "用户明确授权读取的目标订单页可见内容。" * 4,
            "source_mode": "browser_visible",
            "browser_assisted": True,
            "user_authorized": True,
            "visible_page_only": True,
            "private_account_evidence": True,
        }
    )

    assert payload["private_account_evidence"] is True


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
