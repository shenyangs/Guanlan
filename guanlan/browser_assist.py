# -*- coding: utf-8 -*-
"""Browser-assisted evidence planning for Guanlan.

This module only describes a read-only, user-authorized handoff for host
agents that already have a browser. It never reads browser state, cookies, or
local credential stores.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from typing import Any
from urllib.parse import urlparse

ALLOWED_BROWSER_ASSIST_ACTIONS = [
    "open_target_page",
    "read_visible_text",
    "scroll_visible_page",
    "copy_visible_url_title_time_author",
]

FORBIDDEN_BROWSER_ASSIST_ACTIONS = [
    "read_cookies",
    "read_tokens",
    "read_keychain",
    "read_browser_profile",
    "read_browser_storage",
    "read_private_messages",
    "read_orders",
    "read_admin_pages",
    "post",
    "like",
    "comment",
    "follow",
    "message",
    "purchase",
    "submit_forms",
]

FORBIDDEN_BROWSER_ASSIST_IMPLEMENTATIONS = [
    "install_playwright_or_browser_runtime",
    "launch_new_playwright_chromium_for_user_session",
    "use_playwright_persistent_context_with_user_profile",
    "read_browser_user_data_dir",
    "read_or_export_cookies_without_separate_cookie_authorization",
    "use_browser_cookie3_or_cookie_extractor",
    "copy_local_storage_or_session_storage",
    "read_browser_database_or_keychain",
]

PLATFORM_HINTS: dict[str, str] = {
    "xiaohongshu.com": "xiaohongshu",
    "xhslink.com": "xiaohongshu",
    "weixin.qq.com": "wechat",
    "mp.weixin.qq.com": "wechat",
    "zhihu.com": "zhihu",
    "weibo.com": "weibo",
    "m.weibo.cn": "weibo",
    "bilibili.com": "bilibili",
    "douban.com": "douban",
    "linkedin.com": "linkedin",
}

BROWSER_ASSIST_TRIGGER_PLATFORMS = {
    "xiaohongshu",
    "wechat",
    "zhihu",
    "weibo",
    "bilibili",
    "douban",
    "linkedin",
}

BROWSER_ASSIST_ADAPTERS: dict[str, dict[str, Any]] = {
    "host-browser": {
        "id": "host-browser",
        "aliases": ["host", "browser", "agent-browser"],
        "kind": "host_agent_browser",
        "stability": "stable",
        "description": "宿主 Agent 已有浏览器/Computer Use/WebView；观澜只生成任务契约，由宿主 Agent 读取可见页。",
        "executable": "",
        "env_command": "",
        "supports_platforms": ["*"],
        "can_extract": True,
        "can_open": True,
        "requires_execute": False,
        "privacy_boundary": "visible_page_only_by_default",
    },
    "open-cli": {
        "id": "open-cli",
        "aliases": ["open", "system-open", "browser-open"],
        "kind": "system_open",
        "stability": "best-effort",
        "description": "调用系统 open/xdg-open/start 打开目标 URL；只负责打开页面，正文仍由宿主 Agent 可见页读取。",
        "executable": "open",
        "env_command": "GUANLAN_BROWSER_ASSIST_OPEN_CLI_COMMAND",
        "supports_platforms": ["*"],
        "can_extract": False,
        "can_open": True,
        "requires_execute": True,
        "privacy_boundary": "opens_visible_page_only",
    },
    "xhs-cli": {
        "id": "xhs-cli",
        "aliases": ["xiaohongshu-cli", "xiaohongshu", "xhs"],
        "kind": "external_platform_cli",
        "stability": "experimental",
        "description": "小红书外部 CLI 适配入口；需要用户已安装并配置外部 CLI，推荐用命令模板显式声明参数。",
        "executable": "xhs-cli",
        "env_command": "GUANLAN_BROWSER_ASSIST_XHS_CLI_COMMAND",
        "supports_platforms": ["xiaohongshu"],
        "can_extract": True,
        "can_open": True,
        "requires_execute": True,
        "privacy_boundary": "external_cli_user_authorized_visible_or_cookie_flow",
    },
}

SENSITIVE_PAYLOAD_KEYS = {
    "cookie",
    "cookies",
    "token",
    "tokens",
    "authorization",
    "password",
    "passwd",
    "secret",
    "keychain",
    "localstorage",
    "sessionstorage",
    "private_messages",
    "orders",
}


def build_browser_assist_plan(
    url: str,
    *,
    page_type: str = "",
    signals: list[str] | None = None,
    candidate_urls: list[str] | None = None,
    force: bool = False,
    max_pages: int = 3,
    max_chars_per_page: int = 3000,
    task_goal: str = "",
) -> dict[str, Any]:
    """Return a stable browser-assist plan for Agent-facing diagnostics."""

    normalized_url = str(url or "").strip()
    signal_set = set(signals or [])
    platform = platform_hint(normalized_url)
    reasons = _reasons(page_type=page_type, signals=signal_set, platform=platform)
    recommended = bool(force or reasons)
    status = "suggested" if recommended else "not_needed"
    urls = _unique([*(candidate_urls or []), normalized_url])
    user_prompt = (
        "公开搜索和普通网页读取目前不足。你当前浏览器可能已经登录或通过验证，能看到目标页面内容。"
        "是否允许我使用当前 Agent 平台已经提供的浏览器/Computer Use/WebView 打开目标链接，并只读取浏览器中可见的目标页面内容用于补充证据？"
        "如果页面需要登录或验证，请你自己在可见浏览器里完成。"
        "本次可见页补证不会读取 Cookie、浏览器数据库、密码、钥匙串、私信、订单、后台信息，也不会点赞、评论、关注、发帖或发送消息。"
        "如果后续确实需要 Cookie，我会单独说明平台、用途和风险，再征求一次明确授权。"
    )
    task = build_browser_assist_task(
        urls,
        platform=platform,
        evidence_role="user_visible_sample" if recommended else "",
        max_pages=max_pages,
        max_chars_per_page=max_chars_per_page,
        task_goal=task_goal,
    )
    return {
        "recommended": recommended,
        "status": status,
        "reason": "；".join(reasons) if reasons else "当前页面可走普通公开读取，不建议升级到浏览器辅助补证。",
        "platform": platform,
        "evidence_role": "user_visible_sample" if recommended else "",
        "candidate_urls": urls,
        "allowed_actions": ALLOWED_BROWSER_ASSIST_ACTIONS,
        "forbidden_actions": FORBIDDEN_BROWSER_ASSIST_ACTIONS,
        "forbidden_implementations": FORBIDDEN_BROWSER_ASSIST_IMPLEMENTATIONS,
        "browser_assist_task": task,
        "user_prompt": user_prompt,
        "agent_execution_rule": (
            "Use only the host Agent's already-available browser/computer-use/webview tool. "
            "For this visible-page evidence task, do not install Playwright, do not launch a separate browser profile, "
            "and do not read browser cookies/profile/storage. If Cookie access is truly needed, stop and request a separate, "
            "explicit Cookie authorization for the target platform. If no host browser tool exists, stop and use the manual fallback."
        ),
        "cookie_access_policy": _cookie_access_policy(platform),
        "boundaries": [
            "浏览器辅助补证必须由用户明确授权。",
            "只使用宿主 Agent 已有的浏览器/Computer Use/WebView 工具，不安装 Playwright，不启动独立浏览器 profile。",
            "默认只读取目标页面可见内容，不读取 Cookie、Token、浏览器 profile、浏览器数据库、localStorage、sessionStorage、钥匙串。",
            "如确实需要 Cookie，必须暂停当前任务，单独征求用户对具体平台和用途的明确授权。",
            "不执行点赞、评论、关注、发帖、私信、下单、提交表单等写操作。",
            "补证内容可能依赖用户当前浏览器状态，应标注 browser_assisted 和 visible_page_only。",
        ],
        "archive_next_step": "guanlan archive add-browser-note --from-json browser-notes.jsonl",
        "manual_fallback_next_step": 'guanlan archive add-browser-note --url "URL" --text-file notes.md',
    }


def list_browser_assist_adapters(
    *,
    check: bool = False,
    platform: str = "",
    dry_run_url: str = "https://example.com/article",
) -> list[dict[str, Any]]:
    """Return adapter descriptors for Agent-facing capability discovery."""

    adapters = []
    for adapter_id in BROWSER_ASSIST_ADAPTERS:
        contract = build_browser_assist_adapter_contract(adapter_id, platform=platform)
        if check:
            contract["check"] = check_browser_assist_adapter(
                adapter_id,
                platform=platform,
                dry_run_url=dry_run_url,
            )
        adapters.append(contract)
    return adapters


def build_browser_assist_adapter_contract(adapter: str = "host-browser", *, platform: str = "") -> dict[str, Any]:
    """Return a stable contract for a browser-assist adapter."""

    adapter_id = resolve_browser_assist_adapter(adapter)
    spec = dict(BROWSER_ASSIST_ADAPTERS[adapter_id])
    executable = str(spec.get("executable") or "")
    command_env = str(spec.get("env_command") or "")
    command_template = os.environ.get(command_env, "").strip() if command_env else ""
    executable_path = _resolve_adapter_executable(adapter_id, executable)
    platform_ok = _adapter_supports_platform(spec, platform)
    return {
        **spec,
        "id": adapter_id,
        "available": bool(adapter_id == "host-browser" or executable_path or command_template),
        "executable_path": executable_path,
        "command_template_env": command_env,
        "command_template_configured": bool(command_template),
        "platform": platform,
        "platform_supported": platform_ok,
        "output_schema": build_browser_assist_task(
            ["https://example.com/article"],
            platform=platform,
            max_pages=1,
            max_chars_per_page=3000,
        )["output_schema"],
        "archive_next_step": "guanlan archive add-browser-note --from-json browser-notes.jsonl",
        "safety": {
            "read_only": True,
            "visible_page_only_by_default": True,
            "cookie_access_requires_separate_explicit_authorization": True,
            "forbidden_actions": FORBIDDEN_BROWSER_ASSIST_ACTIONS,
            "forbidden_implementations": FORBIDDEN_BROWSER_ASSIST_IMPLEMENTATIONS,
        },
    }


def check_browser_assist_adapter(
    adapter: str = "host-browser",
    *,
    platform: str = "",
    dry_run_url: str = "https://example.com/article",
) -> dict[str, Any]:
    """Return a read-only readiness check for one browser-assist adapter."""

    adapter_id = resolve_browser_assist_adapter(adapter)
    contract = build_browser_assist_adapter_contract(adapter_id, platform=platform)
    checks: list[dict[str, Any]] = []
    hints: list[str] = []
    dry_run_command: list[str] = []

    def add(name: str, status: str, message: str, **extra: Any) -> None:
        checks.append({"name": name, "status": status, "message": message, **extra})

    platform_supported = bool(contract.get("platform_supported", True))
    if platform and not platform_supported:
        add("platform", "fail", f"{adapter_id} 不支持平台 {platform}")
        hints.append("改用 host-browser，或选择匹配该平台的外部适配器。")
    elif platform:
        add("platform", "ok", f"{adapter_id} 支持平台 {platform}")
    else:
        add("platform", "ok", "未指定平台；按适配器声明能力检查。")

    if adapter_id == "host-browser":
        add("host_browser_contract", "ok", "宿主浏览器路径只生成任务契约，不需要本机可执行文件。")
        add("dry_run", "ok", "dry-run 可用：返回 host Agent 可执行契约，不读取浏览器状态。")
        return {
            "status": "ok" if platform_supported else "fail",
            "ready": platform_supported,
            "checks": checks,
            "dry_run_available": platform_supported,
            "dry_run_mode": "contract_only",
            "repair_hints": hints,
        }

    executable_path = str(contract.get("executable_path") or "")
    command_env = str(contract.get("command_template_env") or "")
    template_configured = bool(contract.get("command_template_configured"))
    if executable_path:
        add("executable", "ok", "已找到可执行文件。", path=executable_path)
    else:
        add("executable", "warn", "未在 PATH 中找到默认可执行文件。")

    if command_env:
        if template_configured:
            add("command_template", "ok", f"已配置 {command_env}。")
        else:
            template_status = "warn" if adapter_id == "open-cli" else "fail"
            add("command_template", template_status, f"未配置 {command_env}。")
            if adapter_id == "xhs-cli":
                hints.append(f"设置 {command_env}，命令模板需包含 {{url}}，可选包含 {{output}}。")

    if adapter_id == "open-cli":
        dry_run_command = _open_cli_command(dry_run_url)
    else:
        dry_run_command = _external_adapter_command(adapter_id, dry_run_url, output_path="")
    executable_ok = _command_executable_available(dry_run_command)
    if dry_run_command and executable_ok:
        add("dry_run", "ok", "dry-run 命令可构造，入口可执行；未实际打开或抓取页面。")
    elif dry_run_command:
        add("dry_run", "fail", f"dry-run 命令入口不可执行：{dry_run_command[0]}")
        hints.append("确认命令模板中的第一个命令在 PATH 中，或改用绝对路径。")
    else:
        add("dry_run", "fail", "dry-run 命令不可构造。")

    ready = bool(platform_supported and dry_run_command and executable_ok)
    status = "ok" if ready else ("fail" if adapter_id != "xhs-cli" else "warn")
    if adapter_id == "open-cli" and not ready:
        hints.append("安装系统打开命令，或配置 GUANLAN_BROWSER_ASSIST_OPEN_CLI_COMMAND。")
    if adapter_id == "xhs-cli" and not executable_path:
        hints.append("如需小红书外部适配器，先安装并配置 xhs-cli；否则继续使用 host-browser 稳定路径。")

    return {
        "status": status,
        "ready": ready,
        "checks": checks,
        "dry_run_available": ready,
        "dry_run_mode": "command_template" if template_configured else ("builtin_open" if adapter_id == "open-cli" else ""),
        "command_preview": _safe_command_preview(dry_run_command) if dry_run_command else [],
        "repair_hints": _unique(hints),
    }


def resolve_browser_assist_adapter(adapter: str = "host-browser") -> str:
    """Resolve adapter aliases to canonical IDs."""

    value = str(adapter or "host-browser").strip().lower().replace("_", "-")
    if value in BROWSER_ASSIST_ADAPTERS:
        return value
    for adapter_id, spec in BROWSER_ASSIST_ADAPTERS.items():
        aliases = {str(item).lower().replace("_", "-") for item in spec.get("aliases", [])}
        if value in aliases:
            return adapter_id
    return "host-browser"


def run_browser_assist_adapter(
    url: str,
    *,
    adapter: str = "host-browser",
    execute: bool = False,
    command_template: str = "",
    timeout: int = 90,
    output_path: str = "",
    page_type: str = "access_gate",
    signals: list[str] | None = None,
    platform: str = "",
    max_pages: int = 3,
    max_chars_per_page: int = 3000,
    task_goal: str = "",
) -> dict[str, Any]:
    """Build or execute a browser-assist adapter bridge.

    External adapters are intentionally opt-in and command-template driven. This
    keeps Guanlan stable while letting host environments plug in xhs-cli/open-cli
    style tools when they exist.
    """

    normalized_url = str(url or "").strip()
    adapter_id = resolve_browser_assist_adapter(adapter)
    inferred_platform = platform or platform_hint(normalized_url)
    contract = build_browser_assist_adapter_contract(adapter_id, platform=inferred_platform)
    plan = build_browser_assist_plan(
        normalized_url,
        page_type=page_type,
        signals=signals or [],
        force=True,
        max_pages=max(max_pages, 1),
        max_chars_per_page=max(max_chars_per_page, 1),
        task_goal=task_goal,
    )
    if inferred_platform:
        plan["platform"] = inferred_platform
        if isinstance(plan.get("browser_assist_task"), dict):
            plan["browser_assist_task"]["platform"] = inferred_platform

    response: dict[str, Any] = {
        "adapter": adapter_id,
        "status": "planned",
        "execute": bool(execute),
        "url": normalized_url,
        "platform": inferred_platform,
        "contract": contract,
        "plan": plan,
        "payloads": [],
        "archive_next_step": "guanlan archive add-browser-note --from-json browser-notes.jsonl",
        "agent_instruction": (
            "Guanlan planned the browser-assisted route. Use this adapter only after user authorization; "
            "do not read cookies unless the user separately authorizes Cookie access for the target platform."
        ),
    }
    if not normalized_url:
        response.update({"status": "error", "error": "url_required"})
        return response
    if not contract.get("platform_supported", True):
        response.update(
            {
                "status": "adapter_not_recommended_for_platform",
                "error": f"{adapter_id} does not support platform {inferred_platform}",
            }
        )
        return response
    if adapter_id == "host-browser":
        response["status"] = "requires_host_browser_execution"
        response["execution_boundary"] = "host_agent_must_open_and_read_visible_page"
        return response

    if adapter_id == "open-cli":
        command = _open_cli_command(normalized_url, command_template=command_template)
        response["command"] = command
        if not execute:
            response["status"] = "ready_to_open"
            response["next_step"] = "Run with --execute, then let the host Agent read visible page content."
            return response
        return _execute_adapter_command(
            response,
            command,
            timeout=timeout,
            output_path=output_path,
            parse_stdout=False,
            post_status="opened_requires_host_extraction",
        )

    command = _external_adapter_command(
        adapter_id,
        normalized_url,
        command_template=command_template,
        output_path=output_path,
    )
    response["command"] = command
    if not command:
        env_name = str(contract.get("command_template_env") or "")
        response.update(
            {
                "status": "adapter_config_required",
                "error": "external_cli_command_template_required",
                "setup_hint": (
                    f"设置 {env_name}，例如包含 {{url}} 和可选 {{output}} 的只读命令模板；"
                    "或者传入 --command-template。"
                ),
            }
        )
        return response
    if not execute:
        response["status"] = "ready_to_execute_external_cli"
        response["next_step"] = "确认用户授权和外部 CLI 配置后，加 --execute 执行；输出应为 Guanlan browser-visible JSON/JSONL。"
        return response
    return _execute_adapter_command(
        response,
        command,
        timeout=timeout,
        output_path=output_path,
        parse_stdout=True,
        post_status="executed",
    )


def format_browser_assist_adapters_markdown(adapters: list[dict[str, Any]]) -> str:
    """Render adapter registry in compact Markdown."""

    lines = ["# 观澜浏览器辅助补证适配器", ""]
    for item in adapters:
        lines.append(f"## {item.get('id')}")
        lines.append(f"- 类型: {item.get('kind')}")
        lines.append(f"- 稳定性: {item.get('stability')}")
        lines.append(f"- 可用: {'是' if item.get('available') else '否'}")
        lines.append(f"- 支持平台: {', '.join(item.get('supports_platforms') or [])}")
        lines.append(f"- 说明: {item.get('description')}")
        if item.get("command_template_env"):
            lines.append(f"- 命令模板环境变量: `{item.get('command_template_env')}`")
        check = item.get("check") or {}
        if check:
            lines.append(f"- 自检状态: {check.get('status')} / ready={bool(check.get('ready'))}")
            if check.get("dry_run_available"):
                lines.append(f"- Dry-run: 可用（{check.get('dry_run_mode') or 'command'}）")
            else:
                lines.append("- Dry-run: 不可用")
            for hint in check.get("repair_hints") or []:
                lines.append(f"- 修复提示: {hint}")
        lines.append(f"- 入库: `{item.get('archive_next_step')}`")
        lines.append("")
    return "\n".join(lines).strip()


def format_browser_assist_run_markdown(result: dict[str, Any]) -> str:
    """Render adapter run/plan result."""

    lines = [
        "# 观澜浏览器辅助补证运行计划",
        "",
        f"- 适配器: {result.get('adapter')}",
        f"- 状态: {result.get('status')}",
        f"- URL: {result.get('url')}",
        f"- 平台: {result.get('platform') or '-'}",
        f"- 是否执行: {'是' if result.get('execute') else '否'}",
        f"- 入库: `{result.get('archive_next_step', '')}`",
    ]
    if result.get("command"):
        lines.append("- 命令: `" + " ".join(shlex.quote(str(part)) for part in result.get("command") or []) + "`")
    if result.get("setup_hint"):
        lines.append(f"- 配置提示: {result.get('setup_hint')}")
    if result.get("next_step"):
        lines.append(f"- 下一步: {result.get('next_step')}")
    if result.get("error"):
        lines.append(f"- 错误: {result.get('error')}")
    payloads = result.get("payloads") or []
    if payloads:
        lines.append(f"- 已提取 payload: {len(payloads)} 条")
    plan = result.get("plan") or {}
    task = plan.get("browser_assist_task") or {}
    steps = task.get("collection_steps") or []
    if steps:
        lines.append("")
        lines.append("## 执行边界")
        lines.extend(f"- {item}" for item in steps[:6])
    return "\n".join(lines)


def build_browser_assist_task(
    urls: list[str],
    *,
    platform: str = "",
    evidence_role: str = "user_visible_sample",
    max_pages: int = 3,
    max_chars_per_page: int = 3000,
    task_goal: str = "",
) -> dict[str, Any]:
    """Build the host-browser task description for Agent platforms.

    The task is declarative: Guanlan asks the host Agent to read visible page
    content only after user permission. Guanlan itself does not automate the
    browser or access a browser session.
    """

    clean_urls = _unique(urls)
    max_pages = max(max_pages, 1)
    max_chars_per_page = max(max_chars_per_page, 1)
    return {
        "task_type": "open_and_read_visible_page",
        "status": "requires_user_approval",
        "read_only": True,
        "platform": platform,
        "evidence_role": evidence_role,
        "task_goal": task_goal or "补充公开读取不足的目标页面可见证据；只取可见页，不扩大到账号隐私区。",
        "urls": clean_urls[:max_pages],
        "max_pages": max_pages,
        "max_chars_per_page": max_chars_per_page,
        "collection_steps": [
            "先向用户复述授权话术，获得明确允许后再继续。",
            "确认当前 Agent 平台已经提供浏览器/Computer Use/WebView 工具；如果没有，不要安装 Playwright 或自建浏览器，直接走手动兜底。",
            "使用宿主 Agent 已有浏览器能力打开任务 urls；如果用户需要登录、验证或切换账号，请让用户在可见浏览器里完成。",
            "只读取任务目标页的浏览器可见内容；如需滚动，只为读取目标页可见正文或公开评论摘要。",
            "每页提取标题、URL、可见正文、作者/账号、发布时间、采集时间和可见上下文说明。",
            "如果页面要求登录但浏览器已可见，只读取当前页面可见内容；不要在本任务里读取 Cookie、Token、浏览器 profile、localStorage、sessionStorage、钥匙串、浏览器数据库或无关个人资料。",
            "如果仅靠可见浏览器仍无法访问，停止并向用户说明：下一步需要单独 Cookie 授权；用户未明确同意前不要尝试提取 Cookie。",
            "遇到私信、订单、后台、账号设置、支付、发布框或表单，立即跳过并在输出中标记 skipped_reason。",
        ],
        "extract_fields": [
            "url",
            "title",
            "visible_text",
            "author",
            "published_at",
            "captured_at",
            "visible_context",
            "skipped_reason",
        ],
        "output_schema": {
            "url": "string",
            "title": "string",
            "visible_text": "string",
            "author": "string",
            "published_at": "string",
            "captured_at": "unix_timestamp_or_iso8601",
            "visible_context": "string",
            "platform": "string",
            "user_authorized": True,
            "visible_page_only": True,
        },
        "archive_commands": [
            "guanlan archive add-browser-note --from-json browser-notes.jsonl",
            'guanlan archive add-browser-note --url "URL" --text-file notes.md  # fallback only',
        ],
        "host_browser_contract": {
            "requires_host_browser_tool": True,
            "uses_existing_browser_session": True,
            "user_may_login_or_verify_in_browser": True,
            "agent_may_read_visible_dom_text": True,
            "agent_must_not_install_or_launch_own_browser": True,
            "agent_must_not_use_local_browser_profile": True,
            "agent_must_not_extract_credentials_or_storage_without_separate_authorization": True,
            "cookie_access_requires_separate_explicit_authorization": True,
            "manual_copy_is_fallback_only": True,
        },
        "if_no_host_browser_tool": {
            "action": "stop_and_ask_user_for_manual_visible_text",
            "reason": "浏览器辅助补证依赖宿主 Agent 的浏览器能力；没有该能力时，不应通过读取本机 profile/Cookie 来模拟登录态。",
            "fallback_command": 'guanlan archive add-browser-note --url "URL" --text-file notes.md',
        },
        "quality_checks": [
            "visible_text 不应为空，建议至少 80 个中文字符或等价信息量。",
            "url 必须是目标页或同一任务候选页，不要把推荐流无关页面混入。",
            "如果只能看到登录提示、验证码或空壳，应输出 skipped_reason，而不是伪造成正文证据。",
            "补证材料必须标注 browser_assisted / visible_page_only / user_authorized / session_dependent。",
        ],
        "allowed_actions": ALLOWED_BROWSER_ASSIST_ACTIONS,
        "forbidden_actions": FORBIDDEN_BROWSER_ASSIST_ACTIONS,
        "forbidden_implementations": FORBIDDEN_BROWSER_ASSIST_IMPLEMENTATIONS,
        "must_not_access": [
            "cookies_without_separate_explicit_authorization",
            "tokens",
            "keychain",
            "passwords",
            "browser_profile",
            "browser_user_data_dir",
            "local_storage",
            "session_storage",
            "browser_databases",
            "private_messages",
            "orders",
            "admin_pages",
            "unrelated_personal_data",
        ],
        "conditional_access": {
            "cookies": "allowed_only_after_separate_explicit_user_authorization",
            "tokens": "forbidden",
            "keychain": "forbidden",
            "passwords": "forbidden",
            "browser_profile": "forbidden_unless_using_official_user_approved_auth_flow",
        },
        "output_contract": {
            "source_mode": "browser_visible",
            "browser_assisted": True,
            "visible_page_only": True,
            "user_authorized": True,
            "reproducibility": "session_dependent",
        },
    }


def format_browser_assist_markdown(plan: dict[str, Any]) -> str:
    """Render a browser-assist plan in compact Markdown."""

    if not plan or not plan.get("recommended"):
        return ""
    lines = [
        "## 浏览器辅助补证",
        f"- 建议: {'是' if plan.get('recommended') else '否'}",
        f"- 原因: {plan.get('reason', '')}",
        f"- 证据角色: {plan.get('evidence_role', '')}",
        f"- 平台提示: {plan.get('platform') or '-'}",
        "- 给用户的授权话术:",
        f"  {plan.get('user_prompt', '')}",
        "- 允许动作: " + ", ".join(plan.get("allowed_actions") or []),
        "- 禁止动作: " + ", ".join(plan.get("forbidden_actions") or []),
        "- 禁止实现: " + ", ".join(plan.get("forbidden_implementations") or []),
        f"- Agent 执行规则: {plan.get('agent_execution_rule', '')}",
        f"- 补证入库: `{plan.get('archive_next_step', '')}`",
        f"- 手动兜底: `{plan.get('manual_fallback_next_step', '')}`",
    ]
    boundaries = plan.get("boundaries") or []
    if boundaries:
        lines.append("- 边界:")
        lines.extend(f"  - {item}" for item in boundaries)
    cookie_policy = plan.get("cookie_access_policy") or {}
    if cookie_policy:
        lines.append("- Cookie 授权边界:")
        lines.append(f"  - 默认: {cookie_policy.get('default', '')}")
        lines.append(f"  - 可升级: {cookie_policy.get('can_escalate', '')}")
        lines.append(f"  - 授权话术: {cookie_policy.get('authorization_prompt', '')}")
    task = plan.get("browser_assist_task") or {}
    steps = task.get("collection_steps") or []
    if steps:
        lines.append("- 执行步骤:")
        lines.extend(f"  - {item}" for item in steps[:5])
    archive_commands = task.get("archive_commands") or []
    if archive_commands:
        lines.append("- 可用入库命令:")
        lines.extend(f"  - `{item}`" for item in archive_commands)
    return "\n".join(lines)


def browser_visible_metadata(
    *,
    url: str,
    platform: str = "",
    author: str = "",
    published_at: str = "",
    captured_at: float | None = None,
    quality_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Metadata used when a user-authorized visible browser note is archived."""

    return {
        "source_mode": "browser_visible",
        "browser_assisted": True,
        "visible_page_only": True,
        "user_authorized": True,
        "reproducibility": "session_dependent",
        "evidence_role": "user_visible_sample",
        "platform": platform or platform_hint(url),
        "author": author,
        "published_at": published_at,
        "captured_at": captured_at or time.time(),
        "browser_visible_quality": quality_report or {},
        "evidence_chain": {
            "planned_by": "guanlan_browser_assist",
            "collected_by": "host_agent_browser_visible_page",
            "archive_command": "guanlan archive add-browser-note",
            "boundary": "visible_page_only_user_authorized",
        },
        "safety_boundary": {
            "read_only": True,
            "allowed_actions": ALLOWED_BROWSER_ASSIST_ACTIONS,
            "forbidden_actions": FORBIDDEN_BROWSER_ASSIST_ACTIONS,
            "credential_access": "forbidden",
        },
    }


def browser_visible_quality_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Assess whether a user-authorized visible-page payload is usable."""

    url = str(payload.get("url") or "").strip()
    title = str(payload.get("title") or "").strip()
    visible_text = str(payload.get("visible_text") or payload.get("text") or payload.get("content") or "").strip()
    skipped_reason = str(payload.get("skipped_reason") or "").strip()
    sensitive_keys = sorted(_sensitive_keys_in_payload(payload))
    warnings: list[str] = []
    if not url:
        warnings.append("missing_url")
    if not title:
        warnings.append("missing_title")
    if not visible_text and not skipped_reason:
        warnings.append("missing_visible_text")
    if 0 < len(visible_text) < 80:
        warnings.append("thin_visible_text")
    if sensitive_keys:
        warnings.append("contains_forbidden_payload_keys")
    usable = bool(url and visible_text and not sensitive_keys)
    return {
        "usable": usable,
        "status": "pass" if usable and len(visible_text) >= 80 else ("skip" if skipped_reason and not visible_text else "warn"),
        "chars": len(visible_text),
        "warnings": warnings,
        "sensitive_keys": sensitive_keys,
        "skipped_reason": skipped_reason,
        "boundary": "browser_visible_user_authorized",
    }


def normalize_browser_visible_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize host-browser output before archive ingestion."""

    if not isinstance(payload, dict):
        raise ValueError("browser visible payload must be an object")
    sensitive_keys = _sensitive_keys_in_payload(payload)
    if sensitive_keys:
        raise ValueError("browser visible payload contains forbidden keys: " + ", ".join(sorted(sensitive_keys)))
    visible_text = str(payload.get("visible_text") or payload.get("text") or payload.get("content") or "").strip()
    return {
        "url": str(payload.get("url") or "").strip(),
        "title": str(payload.get("title") or "").strip(),
        "visible_text": visible_text,
        "platform": str(payload.get("platform") or "").strip(),
        "author": str(payload.get("author") or "").strip(),
        "published_at": str(payload.get("published_at") or "").strip(),
        "captured_at": payload.get("captured_at"),
        "visible_context": str(payload.get("visible_context") or "").strip(),
        "skipped_reason": str(payload.get("skipped_reason") or "").strip(),
        "user_authorized": bool(payload.get("user_authorized", True)),
        "visible_page_only": bool(payload.get("visible_page_only", True)),
    }


def load_browser_visible_payloads(path: str) -> list[dict[str, Any]]:
    """Load one JSON object, a JSON array, or JSONL browser-visible notes."""

    raw = _read_text_path(path)
    stripped = raw.strip()
    if not stripped:
        return []
    if stripped.startswith("[") or stripped.startswith("{"):
        data = json.loads(stripped)
        rows = data if isinstance(data, list) else [data]
    else:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    return [normalize_browser_visible_payload(row) for row in rows if isinstance(row, dict)]


def suggest_browser_assist_from_results(
    results: list[dict[str, Any]],
    *,
    max_urls: int = 5,
    reason: str = "",
) -> dict[str, Any]:
    """Build a lightweight suggestion when search found platform pages that may need host-browser reading."""

    candidates: list[str] = []
    platforms: list[str] = []
    for item in results:
        url = str(item.get("url") or "").strip()
        platform = platform_hint(url)
        if not url or platform not in BROWSER_ASSIST_TRIGGER_PLATFORMS:
            continue
        candidates.append(url)
        platforms.append(platform)
        if len(candidates) >= max(max_urls, 1):
            break
    candidates = _unique(candidates)
    platforms = _unique(platforms)
    if not candidates:
        return {"enabled": False}
    plan = build_browser_assist_plan(
        candidates[0],
        page_type="search_fallback_only",
        candidate_urls=candidates,
        force=True,
        max_pages=min(len(candidates), max(max_urls, 1)),
        task_goal="对搜索命中的平台页做用户授权的浏览器可见页补证；只采集目标页可见内容。",
    )
    return {
        "enabled": True,
        "recommended": True,
        "reason": reason or "结果包含可能需要登录态或动态渲染的平台页，可在用户授权后读取浏览器可见页补证。",
        "platforms": platforms,
        "candidate_urls": candidates,
        "user_prompt": plan.get("user_prompt", ""),
        "browser_assist_task": plan.get("browser_assist_task", {}),
        "archive_next_step": plan.get("archive_jsonl_next_step", plan.get("archive_next_step", "")),
        "reporting_contract": [
            "先说明 Guanlan 已完成公开信源路线判断；浏览器只用于用户授权后的目标页可见内容补证。",
            "不要把浏览器可见页材料伪装成所有人可复现的普通公开网页证据。",
        ],
    }


def _adapter_supports_platform(spec: dict[str, Any], platform: str = "") -> bool:
    supported = [str(item) for item in spec.get("supports_platforms") or []]
    return not platform or "*" in supported or platform in supported


def _resolve_adapter_executable(adapter_id: str, executable: str = "") -> str:
    if adapter_id == "host-browser":
        return ""
    if adapter_id == "open-cli":
        for candidate in [executable, "open", "xdg-open", "start"]:
            if not candidate:
                continue
            found = shutil.which(candidate)
            if found:
                return found
        return ""
    if executable:
        return shutil.which(executable) or ""
    return ""


def _open_cli_command(url: str, *, command_template: str = "") -> list[str]:
    template = str(command_template or os.environ.get("GUANLAN_BROWSER_ASSIST_OPEN_CLI_COMMAND") or "").strip()
    if template:
        return _render_command_template(template, url=url, output="")
    executable = _resolve_adapter_executable("open-cli", "open")
    if executable:
        return [executable, url]
    return []


def _external_adapter_command(
    adapter_id: str,
    url: str,
    *,
    command_template: str = "",
    output_path: str = "",
) -> list[str]:
    spec = BROWSER_ASSIST_ADAPTERS.get(adapter_id, {})
    env_name = str(spec.get("env_command") or "")
    template = str(command_template or (os.environ.get(env_name, "") if env_name else "") or "").strip()
    if not template:
        return []
    return _render_command_template(template, url=url, output=output_path)


def _render_command_template(template: str, *, url: str, output: str = "") -> list[str]:
    rendered = template.format(url=url, output=output)
    return shlex.split(rendered)


def _command_executable_available(command: list[str]) -> bool:
    if not command:
        return False
    executable = str(command[0] or "")
    return bool(shutil.which(executable) or (os.path.isabs(executable) and os.path.exists(executable)))


def _safe_command_preview(command: list[str]) -> list[str]:
    if not command:
        return []
    preview = [str(part) for part in command[:3]]
    if len(command) > 3:
        preview.append("...")
    return preview


def _execute_adapter_command(
    response: dict[str, Any],
    command: list[str],
    *,
    timeout: int,
    output_path: str,
    parse_stdout: bool,
    post_status: str,
) -> dict[str, Any]:
    if not command:
        response.update({"status": "adapter_unavailable", "error": "command_not_found"})
        return response
    executable = shutil.which(command[0]) or (command[0] if os.path.isabs(command[0]) else "")
    if not executable:
        response.update({"status": "adapter_unavailable", "error": f"executable_not_found: {command[0]}"})
        return response
    command = [executable, *command[1:]]
    response["command"] = command
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(timeout, 1),
            check=False,
        )
    except subprocess.TimeoutExpired:
        response.update({"status": "timeout", "error": f"adapter_timeout_after_{max(timeout, 1)}s"})
        return response
    except Exception as exc:
        response.update({"status": "error", "error": str(exc)})
        return response
    response["returncode"] = completed.returncode
    response["stdout_preview"] = (completed.stdout or "")[:800]
    response["stderr_preview"] = (completed.stderr or "")[:800]
    if completed.returncode != 0:
        response.update({"status": "adapter_failed", "error": completed.stderr.strip() or f"exit={completed.returncode}"})
        return response
    payloads: list[dict[str, Any]] = []
    if parse_stdout and completed.stdout.strip():
        try:
            payloads = _parse_visible_payload_text(completed.stdout)
        except Exception as exc:
            response["parse_error"] = str(exc)
    response["payloads"] = payloads
    if payloads and output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            for item in payloads:
                f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
        response["output_path"] = output_path
        response["archive_command"] = f"guanlan archive add-browser-note --from-json {output_path}"
    response["status"] = post_status
    if parse_stdout and not payloads:
        response["status"] = "executed_no_parseable_payload"
        response["next_step"] = "外部 CLI 已执行，但 stdout 不是 Guanlan browser-visible JSON/JSONL；请检查命令模板或手动转换。"
    return response


def _parse_visible_payload_text(raw: str) -> list[dict[str, Any]]:
    stripped = str(raw or "").strip()
    if not stripped:
        return []
    if stripped.startswith("{") or stripped.startswith("["):
        data = json.loads(stripped)
        rows = data if isinstance(data, list) else [data]
    else:
        rows = [json.loads(line) for line in stripped.splitlines() if line.strip()]
    return [normalize_browser_visible_payload(row) for row in rows if isinstance(row, dict)]


def platform_hint(url: str) -> str:
    """Return a coarse platform label from URL host."""

    host = urlparse(str(url or "")).netloc.lower()
    for suffix, label in PLATFORM_HINTS.items():
        if host == suffix or host.endswith("." + suffix):
            return label
    return ""


def _cookie_access_policy(platform: str = "") -> dict[str, Any]:
    platform_label = platform or "target_platform"
    return {
        "default": "forbidden_for_visible_page_task",
        "can_escalate": "yes_but_only_after_separate_explicit_user_authorization",
        "required_before_cookie_access": [
            "说明需要哪个平台的 Cookie",
            "说明为什么仅靠公开读取和浏览器可见页仍不足",
            "说明 Cookie 只用于当前目标平台的只读检索/读取",
            "说明不会读取密码、Token、钥匙串、私信、订单、后台或无关个人资料",
            "获得用户明确同意，例如：我同意读取小红书 Cookie 用于这次只读检索",
        ],
        "authorization_prompt": (
            f"公开读取和浏览器可见页仍不足。是否允许我读取 {platform_label} 的 Cookie，"
            "仅用于本次只读检索/读取目标页面？我不会读取密码、Token、钥匙串、私信、订单、后台或无关个人资料，"
            "也不会执行点赞、评论、关注、发帖、私信、下单或提交表单。"
        ),
        "preferred_flow": "use Guanlan's explicit auth/config command or a user-approved host credential connector; do not ad-hoc scrape browser profiles.",
    }


def _sensitive_keys_in_payload(payload: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for key in payload.keys():
        normalized = str(key or "").strip().lower().replace("-", "_")
        if normalized in SENSITIVE_PAYLOAD_KEYS:
            found.add(str(key))
    return found


def _read_text_path(path: str) -> str:
    if str(path or "").strip() == "-":
        import sys

        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _reasons(*, page_type: str, signals: set[str], platform: str) -> list[str]:
    reasons: list[str] = []
    if page_type in {"dynamic_shell", "access_gate", "search_fallback_only"}:
        reasons.append("页面直连读取不足，适合在用户授权后读取浏览器可见页补证")
    if page_type == "network_or_fetch_error" and platform:
        reasons.append("目标平台可能存在访问门槛，公开读取失败后可请求浏览器可见页补证")
    if signals & {"dynamic_shell", "script_or_app_shell", "access_gate", "blocked_or_login_marker"}:
        reasons.append("诊断信号显示动态壳、访问门槛或登录提示")
    if signals & {"search_fallback_only", "thin_body"} and platform:
        reasons.append("当前正文较弱，但平台内容对问题可能有样本价值")
    return _unique(reasons)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
