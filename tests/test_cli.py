# -*- coding: utf-8 -*-
"""Tests for 观澜 / Guanlan CLI."""

import json
from unittest.mock import patch

import pytest
import requests

import guanlan.cli as cli
from guanlan.cli import main
from guanlan.limits import (
    DEFAULT_ARCHIVE_SEARCH_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_SEARCH_LIMIT,
)
from guanlan.update_check import UpdateInfo


class TestCLI:
    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["guanlan", "version"]):
                main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "观澜 / Guanlan v" in captured.out

    def test_no_command_shows_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["guanlan"]):
                main()
        assert exc_info.value.code == 0

    def test_doctor_runs(self, capsys):
        with patch("sys.argv", ["guanlan", "doctor"]), patch("guanlan.cli._install_skill") as install_skill:
            main()
        captured = capsys.readouterr()
        assert "观澜 / Guanlan" in captured.out
        assert "✅" in captured.out
        install_skill.assert_not_called()

    def test_doctor_accepts_profile(self, capsys):
        with patch("sys.argv", ["guanlan", "doctor", "--profile", "china"]):
            main()
        captured = capsys.readouterr()
        assert "观澜 / Guanlan" in captured.out
        assert "中文场景" in captured.out

    def test_doctor_accepts_trace(self, capsys):
        with patch("sys.argv", ["guanlan", "doctor", "--trace"]):
            main()
        captured = capsys.readouterr()
        assert "诊断追踪" in captured.out
        assert "敏感探测: skipped" in captured.out
        assert "readiness=" in captured.out
        assert "verification=" in captured.out

    def test_doctor_accepts_check_config(self, capsys, tmp_path, monkeypatch):
        from guanlan.config import Config

        secret = "ghp_abcdefghijklmnopqrstuvwxyz123456"
        monkeypatch.setattr(Config, "CONFIG_FILE", tmp_path / "config.yaml")
        monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)
        Config().set("github_token", secret)

        with patch("sys.argv", ["guanlan", "doctor", "--check-config"]):
            main()

        captured = capsys.readouterr()
        assert "配置安全扫描" in captured.out
        assert "github_token" in captured.out
        assert secret not in captured.out

    def test_status_runs_with_metadata_and_cache_summary(self, capsys):
        with patch(
            "guanlan.doctor.check_all",
            return_value={
                "web": {
                    "status": "ok",
                    "name": "网页",
                    "message": "ok",
                    "tier": 0,
                    "backends": ["requests"],
                    "readiness": "verified",
                    "verification": "verified",
                    "stability": "stable",
                    "risk_level": "low",
                    "auth": "none",
                    "batch": "allowed",
                }
            },
        ), patch(
            "guanlan.webtools.cache_summary",
            return_value={
                "path": "/tmp/cache",
                "exists": True,
                "kinds": {"search": 2},
                "total_files": 2,
            },
        ), patch("sys.argv", ["guanlan", "status"]):
            main()

        captured = capsys.readouterr()
        assert "状态面板" in captured.out
        assert "verified" in captured.out
        assert "stable" in captured.out
        assert "search: 2" in captured.out

    def test_capabilities_markdown_lists_agent_entrypoints(self, capsys):
        with patch("sys.argv", ["guanlan", "capabilities"]):
            main()

        captured = capsys.readouterr()
        assert "观澜能力地图" in captured.out
        assert "guanlan route" in captured.out
        assert "guanlan research" in captured.out
        assert "助理视角" in captured.out
        assert "财经路由" in captured.out
        assert "查过资料不要丢" in captured.out
        assert "archive context" in captured.out
        assert "Agent 超时预算" in captured.out
        assert "180-300 秒" in captured.out
        assert "timeout_ms" in captured.out
        assert "300000 ms" in captured.out
        assert "裸数字" in captured.out

    def test_capabilities_json_lists_mcp_tools(self, capsys):
        with patch("sys.argv", ["guanlan", "capabilities", "--json"]):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        ids = {item["id"] for item in data}
        assert "discover" in ids
        assert "feeds" in ids
        assert "advisor" in ids
        assert "finance" in ids
        assert "report" in ids
        assert any(item["mcp"] == "guanlan_capabilities" for item in data)


    def test_workflow_command_keeps_simple_lookup_light(self, capsys):
        with patch("sys.argv", ["guanlan", "workflow", "观澜 官网"]):
            main()

        captured = capsys.readouterr()
        assert "观澜工作流分流" in captured.out
        assert "分流层级: direct" in captured.out
        assert "不要过度思考: 是" in captured.out

    def test_route_json_includes_workflow_decision(self, capsys):
        with patch("sys.argv", ["guanlan", "route", "人工智能 政策 最新", "--json"]):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "workflow_decision" in data
        assert data["workflow_decision"]["recommended_limit"] >= 80

    def test_route_json_uses_source_pack_targets_without_explicit_preset(self, capsys):
        with patch("sys.argv", ["guanlan", "route", "OpenAI Claude 模型价格 发布说明", "--json"]):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "company_primary" in data["primary_intents"]
        assert "openai.com" in data["target_sites"]
        assert "anthropic.com" in data["target_sites"]

    def test_investigate_command_uses_upper_workflow(self, capsys):
        packet = {
            "query": "某公司 风险 舆情 档案",
            "results": [],
            "selected_evidence": [],
            "workflow_decision": {"tier": "investigate", "query": "某公司 风险 舆情 档案"},
            "investigation": {"principle": "先取证", "next_views": []},
            "guidance": [],
        }
        with patch("guanlan.investigation.build_investigation_packet", return_value=packet), patch(
            "sys.argv", ["guanlan", "investigate", "某公司 风险 舆情 档案", "--json"]
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["workflow_decision"]["tier"] == "investigate"
        assert data["investigation"]["principle"] == "先取证"

    def test_diagnose_page_command_returns_json(self, capsys):
        with patch(
            "guanlan.page_diagnosis.diagnose_page",
            return_value={
                "url": "https://example.com",
                "page_type": "readable_article",
                "usable_as_evidence": True,
            },
        ), patch("sys.argv", ["guanlan", "diagnose", "page", "https://example.com", "--json"]):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["page_type"] == "readable_article"

    def test_browser_assist_plan_command_returns_task_json(self, capsys):
        with patch(
            "sys.argv",
            [
                "guanlan",
                "browser-assist",
                "plan",
                "https://www.xiaohongshu.com/explore/demo",
                "--json",
            ],
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["recommended"] is True
        assert data["browser_assist_task"]["task_type"] == "open_and_read_visible_page"
        assert data["browser_assist_task"]["status"] == "requires_user_approval"
        assert data["browser_assist_task"]["host_browser_contract"]["uses_existing_browser_session"] is True
        assert data["browser_assist_task"]["host_browser_contract"]["manual_copy_is_fallback_only"] is True
        assert data["browser_assist_task"]["host_browser_contract"]["cookie_access_requires_separate_explicit_authorization"] is True
        assert data["browser_assist_task"]["platform_template"]["name"] == "小红书可见笔记"
        assert "engagement_summary" in data["browser_assist_task"]["extract_fields"]
        assert data["recommended_adapter"] == "host-browser"
        assert data["cookie_access_policy"]["default"] == "forbidden_for_visible_page_task"
        assert "read_cookies" in data["forbidden_actions"]
        assert data["session_contract"]["version"] == "browser_visible_session_v1"
        assert "fixed_sleep_only" in data["browser_assist_task"]["readiness_contract"]["avoid_as_primary_signal"]

    def test_browser_assist_plan_supports_rednote_and_collection_sufficiency(self, capsys):
        with patch(
            "sys.argv",
            [
                "guanlan",
                "browser-assist",
                "plan",
                "https://www.rednote.com/explore/demo",
                "--min-visible-items",
                "30",
                "--json",
            ],
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["platform"] == "rednote"
        task = data["browser_assist_task"]
        assert task["platform_template"]["name"] == "Rednote 可见笔记"
        assert task["sufficiency_contract"]["requested_min_items"] == 30
        assert "collected_count" in task["execution_contract"]["output_schema"]

    def test_browser_assist_adapters_command_lists_host_and_external(self, capsys):
        with patch("sys.argv", ["guanlan", "browser-assist", "adapters", "--json"]):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        ids = {item["id"] for item in data}
        assert {"host-browser", "openguanlan", "open-cli", "browser-use", "xhs-cli"} <= ids
        host = next(item for item in data if item["id"] == "host-browser")
        assert host["available"] is True
        assert host["capability_layer"] == "extractor"
        assert host["capability_score"] >= 90
        assert host["safety"]["cookie_access_requires_separate_explicit_authorization"] is True
        assert "readiness_contract" in host
        assert "repair_protocol" in host

    def test_browser_assist_setup_opencli_command_returns_install_plan(self, capsys, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: None)
        with patch("sys.argv", ["guanlan", "browser-assist", "setup-opencli", "--json"]):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "needs_cli_install"
        assert data["execute"] is False
        assert data["browser_extension"]["manual_user_step_required"] is True
        assert "opencli doctor" in data["verification_commands"]
        assert data["safety"]["credential_material_access_allowed"] is False

    def test_browser_assist_setup_openguanlan_command_returns_native_plan(self, capsys, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: None)
        with patch("sys.argv", ["guanlan", "browser-assist", "setup-openguanlan", "--json"]):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["adapter"] == "openguanlan"
        assert data["status"] == "packaged_needs_install_entrypoint"
        assert data["current_default"] == "host-browser"
        assert data["runtime_packaged"] is True
        assert data["extension_manifest_exists"] is True
        assert any("不要求用户安装 opencli" in item for item in data["user_install_boundary"])
        assert data["safety"]["credential_material_access_allowed"] is False

    def test_browser_assist_sessions_command_returns_contract(self, capsys):
        with patch(
            "sys.argv",
            [
                "guanlan",
                "browser-assist",
                "sessions",
                "https://www.xiaohongshu.com/explore/demo",
                "--min-visible-items",
                "20",
                "--json",
            ],
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["version"] == "browser_visible_session_v1"
        assert data["platform"] == "xiaohongshu"
        assert data["sufficiency_contract"]["requested_min_items"] == 20
        assert data["timeout_budget_ms"] == 90000

    def test_browser_assist_run_browser_use_without_install_is_actionable(self, capsys, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: None)
        with patch(
            "sys.argv",
            [
                "guanlan",
                "browser-assist",
                "run",
                "https://example.com/article",
                "--adapter",
                "browser-use",
                "--json",
            ],
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["adapter"] == "browser-use"
        assert data["status"] == "adapter_unavailable"
        assert data["error"] == "browser_use_not_installed"

    def test_browser_assist_adapters_check_reports_readiness(self, capsys, monkeypatch):
        monkeypatch.delenv("GUANLAN_BROWSER_ASSIST_XHS_CLI_COMMAND", raising=False)
        with patch(
            "sys.argv",
            [
                "guanlan",
                "browser-assist",
                "adapters",
                "--check",
                "--platform",
                "xiaohongshu",
                "--json",
            ],
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        host = next(item for item in data if item["id"] == "host-browser")
        xhs = next(item for item in data if item["id"] == "xhs-cli")
        assert host["check"]["status"] == "ok"
        assert host["check"]["dry_run_available"] is True
        assert host["check"]["can_extract_visible_text"] is True
        assert xhs["check"]["ready"] is False
        assert any(check["name"] == "command_template" for check in xhs["check"]["checks"])

    def test_browser_assist_run_host_browser_returns_execution_contract(self, capsys):
        with patch(
            "sys.argv",
            [
                "guanlan",
                "browser-assist",
                "run",
                "https://www.xiaohongshu.com/explore/demo",
                "--adapter",
                "host-browser",
                "--json",
            ],
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["adapter"] == "host-browser"
        assert data["status"] == "requires_host_browser_execution"
        assert data["contract"]["safety"]["visible_page_only_by_default"] is True
        assert data["contract"]["capabilities"]["can_reuse_existing_session"] is True
        assert data["plan"]["browser_assist_task"]["host_browser_contract"]["uses_existing_browser_session"] is True

    def test_recipe_run_command_returns_plan(self, capsys):
        with patch(
            "sys.argv",
            ["guanlan", "recipe", "run", "finance-risk", "宁德时代 股价 财报", "--json"],
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["recipe"]["id"] == "finance-risk"
        assert any("guanlan stock detail" in command for command in data["commands"])

    def test_feedback_command_submits(self, capsys):
        with patch(
            "guanlan.feedback.submit_feedback",
            return_value={"ok": True, "queued": False, "message": "sent"},
        ) as mocked_submit, patch(
            "sys.argv",
            [
                "guanlan",
                "feedback",
                "人工智能 政策",
                "--reason",
                "结果不够权威",
                "--command",
                "search",
                "--profile",
                "china",
                "--backend",
                "auto",
            ],
        ):
            main()
        captured = capsys.readouterr()
        assert "反馈已提交" in captured.out
        mocked_submit.assert_called_once()

    def test_search_auto_feedback_for_agent_runtime(self, capsys, monkeypatch):
        monkeypatch.setenv("CODEX_HOME", "/tmp/codex")
        mocked_results = [
            {
                "title": "x",
                "url": "https://example.com",
                "snippet": "x",
                "trace": {
                    "quality_summary": {
                        "warnings": ["目标信源覆盖不足"],
                        "preferred_hit_count": 0,
                        "result_count": 1,
                    },
                    "backend_recovery": {"should_warn": True, "issue": "all_primary_failed"},
                },
            }
        ]
        with patch("guanlan.webtools.search_web", return_value=mocked_results), patch(
            "guanlan.webtools.format_search_markdown", return_value="ok"
        ), patch("guanlan.feedback.submit_feedback") as mocked_submit, patch(
            "sys.argv",
            ["guanlan", "search", "AI 政策", "--limit", "5"],
        ):
            main()

        captured = capsys.readouterr()
        assert "ok" in captured.out
        mocked_submit.assert_called_once()

    def test_report_html_cli_writes_sidecar_report(self, capsys, tmp_path):
        input_path = tmp_path / "results.json"
        output_path = tmp_path / "report.html"
        input_path.write_text(
            json.dumps(
                [
                    {
                        "title": "Search result",
                        "url": "https://example.com/a",
                        "source_title": "Example",
                        "snippet": "Useful.",
                        "score": 8,
                    }
                ]
            ),
            encoding="utf-8",
        )

        with patch(
            "sys.argv",
            [
                "guanlan",
                "report",
                "html",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--title",
                "侧边报表",
            ],
        ):
            main()

        captured = capsys.readouterr()
        assert "观澜旁支 HTML 报表" in captured.out
        assert output_path.exists()
        html = output_path.read_text(encoding="utf-8")
        assert "侧边报表" in html
        assert "Search result" in html

    def test_feeds_curated_cli_outputs_json(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "guanlan.feeds.fetch_feed_source",
            lambda *_args, **_kwargs: [{"title": "AI Article", "url": "https://example.com/a"}],
        )

        with patch("sys.argv", ["guanlan", "feeds", "curated", "--json", "--category", "ai", "--limit", "3"]):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data[0]["title"] == "AI Article"

    def test_feeds_curated_sources_cli_outputs_catalog(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "guanlan.feeds.list_curated_sources",
            lambda **_kwargs: [{"title": "LangChain Blog", "url": "https://blog.langchain.dev/rss/"}],
        )

        with patch("sys.argv", ["guanlan", "feeds", "curated-sources", "--keyword", "LangChain"]):
            main()

        captured = capsys.readouterr()
        assert "观澜 RSS 源目录 / 精品源 / LangChain" in captured.out
        assert "LangChain Blog" in captured.out

    def test_feeds_list_cli_outputs_routing_catalog(self, capsys):
        with patch("sys.argv", ["guanlan", "feeds", "list"]):
            main()

        captured = capsys.readouterr()
        assert "观澜 RSS 信源路由" in captured.out
        assert "wechat-rss" in captured.out

    def test_welcome_prints_short_user_guide(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("GUANLAN_ONBOARDING_FILE", str(tmp_path / "onboarding.json"))

        with patch("sys.argv", ["guanlan", "welcome"]):
            main()

        captured = capsys.readouterr()
        assert "观澜已安装完成" in captured.out
        assert "你可以直接这样对 Agent 说" in captured.out
        assert "guanlan capabilities" in captured.out
        assert "Agent Wiki / RAG / 本地模型" in captured.out

    def test_welcome_once_only_prints_first_time(self, capsys, tmp_path, monkeypatch):
        from guanlan.onboarding import show_welcome_once

        monkeypatch.setenv("GUANLAN_ONBOARDING_FILE", str(tmp_path / "onboarding.json"))

        assert show_welcome_once() is True
        first = capsys.readouterr()
        assert "观澜已安装完成" in first.out

        assert show_welcome_once() is False
        second = capsys.readouterr()
        assert second.out == ""

    def test_profile_show(self, capsys, tmp_path, monkeypatch):
        from guanlan.config import Config

        monkeypatch.setattr(Config, "CONFIG_FILE", tmp_path / "config.yaml")
        monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)
        with patch("sys.argv", ["guanlan", "profile", "show"]):
            main()
        captured = capsys.readouterr()
        assert "global" in captured.out

    def test_profile_set(self, capsys, tmp_path, monkeypatch):
        from guanlan.config import Config

        monkeypatch.setattr(Config, "CONFIG_FILE", tmp_path / "config.yaml")
        monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)
        with patch("sys.argv", ["guanlan", "profile", "set", "china"]):
            main()
        captured = capsys.readouterr()
        assert "Profile set to china" in captured.out

    def test_configure_telemetry_endpoint(self, capsys, tmp_path, monkeypatch):
        from guanlan.config import Config

        monkeypatch.setattr(Config, "CONFIG_FILE", tmp_path / "config.yaml")
        monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)

        with patch("sys.argv", ["guanlan", "configure", "telemetry-endpoint", "https://metrics.example/v1/events"]):
            main()

        captured = capsys.readouterr()
        assert "Telemetry endpoint configured" in captured.out
        assert Config().get("telemetry_endpoint") == "https://metrics.example/v1/events"

    def test_configure_telemetry_off(self, capsys, tmp_path, monkeypatch):
        from guanlan.config import Config

        monkeypatch.setattr(Config, "CONFIG_FILE", tmp_path / "config.yaml")
        monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)

        with patch("sys.argv", ["guanlan", "configure", "telemetry", "off"]):
            main()

        captured = capsys.readouterr()
        assert "Anonymous telemetry disabled" in captured.out
        assert Config().get("telemetry_enabled") is False

    def test_setup_does_not_prompt_for_optional_tokens(self, capsys, tmp_path, monkeypatch):
        from guanlan.config import Config

        monkeypatch.setattr(Config, "CONFIG_FILE", tmp_path / "config.yaml")
        monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr("shutil.which", lambda _cmd: None)

        with patch("sys.argv", ["guanlan", "setup"]):
            main()

        captured = capsys.readouterr()
        assert "基础搜索不需要 Token" in captured.out
        assert "GITHUB_TOKEN" not in captured.out
        assert "GROQ_API_KEY" not in captured.out
        assert Config().get("github_token") is None
        assert Config().get("groq_api_key") is None

    def test_parse_twitter_cookie_input_separate_values(self):
        auth_token, ct0 = cli._parse_twitter_cookie_input("token123 ct0abc")
        assert auth_token == "token123"
        assert ct0 == "ct0abc"

    def test_parse_twitter_cookie_input_cookie_header(self):
        auth_token, ct0 = cli._parse_twitter_cookie_input(
            "auth_token=token123; ct0=ct0abc; other=value"
        )
        assert auth_token == "token123"
        assert ct0 == "ct0abc"

    def test_sensitive_access_notice_is_reassuring(self, capsys, monkeypatch):
        monkeypatch.setenv("GUANLAN_NOTICE_DELAY", "0")

        cli._print_sensitive_access_notice("从浏览器读取平台 Cookie", browser="chrome")

        captured = capsys.readouterr()
        assert "观澜安全提示" in captured.out
        assert "不会读取你的系统登录密码" in captured.out
        assert "不会上传任何 Cookie" in captured.out

    def test_search_default_limit_is_expanded(self, capsys, monkeypatch):
        calls = []

        def fake_search_web(*_args, **kwargs):
            calls.append(kwargs)
            return []

        monkeypatch.setattr("guanlan.webtools.search_web", fake_search_web)

        with patch("sys.argv", ["guanlan", "search", "人工智能", "--json"]):
            main()

        capsys.readouterr()
        assert calls[0]["limit"] == DEFAULT_SEARCH_LIMIT

    def test_search_network_option_is_passed_to_webtools(self, capsys, monkeypatch):
        calls = []

        def fake_search_web(*_args, **kwargs):
            calls.append(kwargs)
            return []

        monkeypatch.setattr("guanlan.webtools.search_web", fake_search_web)

        with patch("sys.argv", ["guanlan", "search", "人工智能", "--network", "direct", "--json"]):
            main()

        capsys.readouterr()
        assert calls[0]["network_mode"] == "direct"

    def test_search_strict_scope_option_is_passed_to_webtools(self, capsys, monkeypatch):
        calls = []

        def fake_search_web(*_args, **kwargs):
            calls.append(kwargs)
            return []

        monkeypatch.setattr("guanlan.webtools.search_web", fake_search_web)

        with patch("sys.argv", ["guanlan", "search", "人工智能", "--scope", "tech_dev", "--strict-scope", "--json"]):
            main()

        capsys.readouterr()
        assert calls[0]["scope"] == "tech_dev"
        assert calls[0]["strict_scope"] is True

    def test_search_prints_compact_update_notice_to_stderr_without_polluting_json(self, capsys, monkeypatch):
        def fake_search_web(*_args, **_kwargs):
            return []

        monkeypatch.setattr("guanlan.webtools.search_web", fake_search_web)

        with patch(
            "guanlan.update_check.cached_update_info",
            return_value=UpdateInfo(current="0.4.3", latest="0.4.4"),
        ), patch("sys.argv", ["guanlan", "search", "人工智能", "--json"]):
            main()

        captured = capsys.readouterr()
        assert captured.out.strip() == "[]"
        assert "版本提醒" in captured.err
        assert "uv tool install --force --upgrade guanlan" in captured.err

    def test_hotnews_default_limit_is_expanded(self, capsys, monkeypatch):
        calls = []

        def fake_fetch_hotnews(*_args, **kwargs):
            calls.append(kwargs)
            return []

        monkeypatch.setattr("guanlan.hotnews.fetch_hotnews", fake_fetch_hotnews)

        with patch("sys.argv", ["guanlan", "hotnews", "today", "--json"]):
            main()

        capsys.readouterr()
        assert calls[0]["limit"] == DEFAULT_HOTNEWS_LIMIT

    def test_read_default_fallback_limit_is_expanded(self, capsys, monkeypatch):
        calls = []

        def fake_read_url(*_args, **kwargs):
            calls.append(kwargs)
            return "# Article"

        monkeypatch.setattr("guanlan.webtools.read_url", fake_read_url)

        with patch("sys.argv", ["guanlan", "read", "https://example.com"]):
            main()

        capsys.readouterr()
        assert calls[0]["fallback_limit"] == DEFAULT_READ_FALLBACK_LIMIT

    def test_archive_search_default_limit_is_expanded(self, capsys, monkeypatch):
        calls = []

        def fake_search_documents(*_args, **kwargs):
            calls.append(kwargs)
            return []

        monkeypatch.setattr("guanlan.archive.search_documents", fake_search_documents)

        with patch("sys.argv", ["guanlan", "archive", "search", "材料", "--json"]):
            main()

        capsys.readouterr()
        assert calls[0]["limit"] == DEFAULT_ARCHIVE_SEARCH_LIMIT


class TestCheckUpdateRetry:
    def test_retry_timeout_classification(self):
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)

        with patch("requests.get", side_effect=requests.exceptions.Timeout("timed out")):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                timeout=1,
                retries=3,
                sleeper=fake_sleep,
            )

        assert resp is None
        assert err == "timeout"
        assert attempts == 3
        assert sleeps == [1, 2]

    def test_retry_dns_classification(self):
        error = requests.exceptions.ConnectionError("getaddrinfo failed for api.github.com")
        with patch("requests.get", side_effect=error):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                retries=1,
                sleeper=lambda _x: None,
            )
        assert resp is None
        assert err == "dns"
        assert attempts == 1

    def test_retry_rate_limit_then_success(self):
        sleeps = []

        class R:
            def __init__(self, code, payload=None, headers=None):
                self.status_code = code
                self._payload = payload or {}
                self.headers = headers or {}

            def json(self):
                return self._payload

        sequence = [
            R(429, headers={"Retry-After": "3"}),
            R(200, payload={"tag_name": "v0.1.0"}),
        ]

        with patch("requests.get", side_effect=sequence):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                retries=3,
                sleeper=lambda s: sleeps.append(s),
            )

        assert err is None
        assert resp is not None
        assert resp.status_code == 200
        assert attempts == 2
        assert sleeps == [3.0]

    def test_classify_rate_limit_from_403(self):
        class R:
            status_code = 403
            headers = {"X-RateLimit-Remaining": "0"}

            @staticmethod
            def json():
                return {"message": "API rate limit exceeded"}

        assert cli._classify_github_response_error(R()) == "rate_limit"

    def test_check_update_reports_classified_error(self, capsys, monkeypatch):
        monkeypatch.setenv("GUANLAN_UPDATE_REPO", "example/guanlan")
        with patch("guanlan.cli._github_get_with_retry", return_value=(None, "timeout", 3)):
            result = cli._cmd_check_update()

        captured = capsys.readouterr()
        assert result == "error"
        assert "网络超时" in captured.out
        assert "已重试 3 次" in captured.out

    def test_check_update_uses_pypi_when_no_github_repo(self, capsys, monkeypatch):
        monkeypatch.delenv("GUANLAN_UPDATE_REPO", raising=False)
        with patch("guanlan.update_check.get_update_info", return_value=None):
            result = cli._cmd_check_update()

        captured = capsys.readouterr()
        assert result == "up_to_date"
        assert "已是最新版本" in captured.out
