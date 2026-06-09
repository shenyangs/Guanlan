# -*- coding: utf-8 -*-
"""Browser-assisted evidence planning for Guanlan.

This module describes a read-only, user-authorized handoff for host agents
that already have a browser or a browser bridge. It never treats credential
material such as browser state, cookies, tokens, storage, keychains, or local
credential stores as evidence.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from guanlan.social_evidence import (
    build_social_evidence_protocol,
    infer_social_platform,
    normalize_social_evidence_payload,
    social_browser_assist_template,
    social_visible_output_schema,
)

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
    "read_passwords",
    "read_browser_profile",
    "read_browser_storage",
    "read_unrelated_private_messages",
    "read_unrelated_orders",
    "read_unrelated_admin_pages",
    "post",
    "like",
    "comment",
    "follow",
    "message",
    "purchase",
    "submit_forms",
]

CONDITIONAL_BROWSER_ASSIST_ACTIONS = [
    "read_target_private_account_visible_page_after_explicit_authorization",
    "read_target_order_or_admin_visible_page_after_explicit_authorization",
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
    "rednote.com": "rednote",
    "weixin.qq.com": "wechat",
    "mp.weixin.qq.com": "wechat",
    "zhihu.com": "zhihu",
    "weibo.com": "weibo",
    "m.weibo.cn": "weibo",
    "s.weibo.com": "weibo",
    "bilibili.com": "bilibili",
    "b23.tv": "bilibili",
    "space.bilibili.com": "bilibili",
    "m.bilibili.com": "bilibili",
    "douyin.com": "douyin",
    "iesdouyin.com": "douyin",
    "v.douyin.com": "douyin",
    "kuaishou.com": "kuaishou",
    "v.kuaishou.com": "kuaishou",
    "tieba.baidu.com": "tieba",
    "douban.com": "douban",
    "linkedin.com": "linkedin",
}

OPENCLI_NPM_PACKAGE = "@jackwener/opencli"
OPENCLI_CHROME_WEBSTORE_URL = "https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk"
OPENCLI_RELEASES_URL = "https://github.com/jackwener/opencli/releases"
OPENGUANLAN_EXTENSION_NAME = "OpenGuanlan Browser Bridge"

BROWSER_ASSIST_TRIGGER_PLATFORMS = {
    "xiaohongshu",
    "rednote",
    "wechat",
    "zhihu",
    "weibo",
    "bilibili",
    "douyin",
    "kuaishou",
    "tieba",
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
        "can_reuse_existing_session": True,
        "adapter_role": "extractor",
        "risk_level": "low",
        "requires_execute": False,
        "privacy_boundary": "visible_page_only_by_default",
    },
    "openguanlan": {
        "id": "openguanlan",
        "aliases": ["open-guanlan", "guanlan-browser-assist", "browser-assist-layer"],
        "kind": "guanlan_browser_assist_layer",
        "stability": "stable",
        "description": "OpenGuanlan 是观澜浏览器补证总层：默认生成宿主浏览器可见页契约，不要求安装扩展或 daemon。",
        "executable": "",
        "env_command": "GUANLAN_BROWSER_ASSIST_OPENGUANLAN_COMMAND",
        "supports_platforms": ["*"],
        "can_extract": True,
        "can_open": True,
        "can_reuse_existing_session": True,
        "adapter_role": "extractor",
        "risk_level": "low",
        "requires_execute": False,
        "privacy_boundary": "guanlan_native_user_authorized_visible_or_private_account_page_only",
    },
    "openguanlan-bridge": {
        "id": "openguanlan-bridge",
        "aliases": ["guanlan-browser-bridge", "guanlan-bridge", "open-guanlan-bridge", "openguanlan-daemon"],
        "kind": "guanlan_optional_browser_bridge",
        "stability": "experimental",
        "description": "OpenGuanlan 可选扩展桥：通过 openguanlan daemon 和用户手动启用的 Chrome/Chromium 扩展输出可见页 JSON/JSONL。",
        "executable": "openguanlan",
        "env_command": "GUANLAN_BROWSER_ASSIST_OPENGUANLAN_COMMAND",
        "supports_platforms": ["*"],
        "can_extract": True,
        "can_open": True,
        "can_reuse_existing_session": True,
        "adapter_role": "extractor",
        "risk_level": "low",
        "requires_execute": True,
        "privacy_boundary": "optional_bridge_user_authorized_visible_or_private_account_page_only",
    },
    "open-cli": {
        "id": "open-cli",
        "aliases": ["open", "system-open", "browser-open", "opencli", "opencli-browser", "open-cli-browser"],
        "kind": "system_open",
        "stability": "best-effort",
        "description": "默认调用系统 open/xdg-open/start 打开目标 URL；若检测到 OpenCLI 浏览器桥或命令模板，则升级为可见页 extractor。",
        "executable": "open",
        "env_command": "GUANLAN_BROWSER_ASSIST_OPEN_CLI_COMMAND",
        "supports_platforms": ["*"],
        "can_extract": False,
        "can_open": True,
        "can_reuse_existing_session": True,
        "adapter_role": "opener",
        "risk_level": "low",
        "requires_execute": True,
        "privacy_boundary": "opens_visible_page_only",
    },
    "browser-use": {
        "id": "browser-use",
        "aliases": ["browseruse", "browser_use", "bu", "browser-use-cli"],
        "kind": "external_browser_cli",
        "stability": "best-effort",
        "description": "Browser Use CLI 适配入口；默认只用于打开目标页，正文仍由宿主 Agent 按可见页契约提取。",
        "executable": "browser-use",
        "env_command": "GUANLAN_BROWSER_ASSIST_BROWSER_USE_COMMAND",
        "supports_platforms": ["*"],
        "can_extract": False,
        "can_open": True,
        "can_reuse_existing_session": False,
        "adapter_role": "opener",
        "risk_level": "medium",
        "requires_execute": True,
        "privacy_boundary": "open_or_connect_visible_page_only",
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
        "can_reuse_existing_session": False,
        "adapter_role": "extractor",
        "risk_level": "medium",
        "requires_execute": True,
        "privacy_boundary": "external_cli_user_authorized_visible_or_cookie_flow",
    },
}

BROWSER_ASSIST_PLATFORM_TEMPLATES: dict[str, dict[str, Any]] = {
    "xiaohongshu": {
        "name": "小红书可见笔记",
        "evidence_role": "user_visible_sample",
        "extract_fields": [
            "url",
            "title",
            "visible_text",
            "author",
            "published_at",
            "engagement_summary",
            "visible_comment_summary",
            "captured_at",
            "visible_context",
            "skipped_reason",
        ],
        "field_hints": [
            "正文优先于推荐流、页脚和登录提示。",
            "评论只取当前页面可见摘要，不翻私信、不扩大到无关页面。",
            "互动数仅作为样本语境，不写成平台全量结论。",
        ],
        "quality_checks": [
            "visible_text 至少包含标题或正文之一。",
            "如果只能看到登录/扫码/验证码，填写 skipped_reason=needs_login_or_verification。",
            "作者、发布时间缺失时保留空值，不编造。",
        ],
    },
    "rednote": {
        "name": "Rednote 可见笔记",
        "evidence_role": "user_visible_sample",
        "extract_fields": [
            "url",
            "title",
            "visible_text",
            "author",
            "published_at",
            "engagement_summary",
            "visible_comment_summary",
            "captured_at",
            "visible_context",
            "skipped_reason",
        ],
        "field_hints": [
            "按小红书同类公开笔记处理，但保留 rednote 平台标签。",
            "正文优先于推荐流、页脚和登录提示。",
            "互动数仅作为样本语境，不写成平台全量结论。",
        ],
        "quality_checks": [
            "visible_text 至少包含标题或正文之一。",
            "如果只能看到登录/扫码/验证码，填写 skipped_reason=needs_login_or_verification。",
            "作者、发布时间缺失时保留空值，不编造。",
        ],
    },
    "zhihu": {
        "name": "知乎可见问答",
        "evidence_role": "user_visible_answer",
        "extract_fields": [
            "url",
            "title",
            "question",
            "visible_text",
            "author",
            "published_at",
            "engagement_summary",
            "captured_at",
            "visible_context",
            "skipped_reason",
        ],
        "field_hints": [
            "区分问题标题、回答正文和评论区。",
            "赞同数、评论数只作可见页上下文。",
            "不要把推荐回答混入目标 URL 的正文。",
        ],
        "quality_checks": [
            "visible_text 应来自目标回答或目标问题页可见主体。",
            "如果只读到登录弹层或推荐列表，填写 skipped_reason。",
        ],
    },
    "wechat": {
        "name": "公众号可见文章",
        "evidence_role": "user_visible_article",
        "extract_fields": [
            "url",
            "title",
            "visible_text",
            "author",
            "account",
            "published_at",
            "captured_at",
            "visible_context",
            "skipped_reason",
        ],
        "field_hints": [
            "优先提取文章标题、公众号账号、发布时间和正文。",
            "不要采集微信私聊、收藏、通讯录或后台页面。",
            "如果页面需要在微信内打开，说明 access gate，不要绕过。",
        ],
        "quality_checks": [
            "visible_text 应明显多于页脚、二维码和相关推荐。",
            "账号和发布时间能看到就提取，看不到就留空。",
        ],
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
    min_visible_items: int = 0,
    task_goal: str = "",
) -> dict[str, Any]:
    """Return a stable browser-assist plan for Agent-facing diagnostics."""

    normalized_url = str(url or "").strip()
    signal_set = set(signals or [])
    platform = platform_hint(normalized_url)
    template = browser_assist_platform_template(platform)
    reasons = _reasons(page_type=page_type, signals=signal_set, platform=platform)
    recommended = bool(force or reasons)
    status = "suggested" if recommended else "not_needed"
    urls = _unique([*(candidate_urls or []), normalized_url])
    user_prompt = (
        "公开搜索和普通网页读取目前不足。你当前浏览器可能已经登录或通过验证，能看到目标页面内容。"
        "是否允许我使用当前 Agent 平台已经提供的浏览器/Computer Use/WebView 打开目标链接，并只读取浏览器中可见的目标页面内容用于补充证据？"
        "如果页面需要登录或验证，请你自己在可见浏览器里完成。"
        "若目标任务本身就是私信、订单、后台或账号页，也需要你对该目标页和用途单独明确授权；授权后仍只读取目标页可见内容。"
        "本次可见页补证不会读取 Cookie、Token、浏览器数据库、localStorage、sessionStorage、密码、钥匙串或无关个人资料，也不会点赞、评论、关注、发帖或发送消息。"
        "如果后续确实需要 Cookie 或其他凭据材料，我会暂停并说明平台、用途和风险，再征求一次单独授权；普通可见页补证不会碰这些材料。"
    )
    task = build_browser_assist_task(
        urls,
        platform=platform,
        evidence_role="user_visible_sample" if recommended else "",
        max_pages=max_pages,
        max_chars_per_page=max_chars_per_page,
        min_visible_items=min_visible_items,
        task_goal=task_goal,
    )
    recommended_adapter = recommend_browser_assist_adapter(platform=platform, need_extraction=True)
    return {
        "recommended": recommended,
        "status": status,
        "reason": "；".join(reasons) if reasons else "当前页面可走普通公开读取，不建议升级到浏览器辅助补证。",
        "platform": platform,
        "platform_template": template,
        "social_evidence_protocol": build_social_evidence_protocol(platform),
        "evidence_role": template.get("evidence_role") or ("user_visible_sample" if recommended else ""),
        "candidate_urls": urls,
        "allowed_actions": ALLOWED_BROWSER_ASSIST_ACTIONS,
        "conditional_actions": CONDITIONAL_BROWSER_ASSIST_ACTIONS,
        "forbidden_actions": FORBIDDEN_BROWSER_ASSIST_ACTIONS,
        "forbidden_implementations": FORBIDDEN_BROWSER_ASSIST_IMPLEMENTATIONS,
        "browser_assist_task": task,
        "recommended_adapter": recommended_adapter,
        "recommended_commands": [
            "guanlan browser-assist adapters --check",
            f'guanlan browser-assist run "{normalized_url}" --adapter {recommended_adapter}'
            + (f" --min-visible-items {max(int(min_visible_items or 0), 0)}" if int(min_visible_items or 0) > 0 else "")
            + " --json",
            "guanlan archive add-browser-note --from-json browser-notes.jsonl",
        ],
        "failure_taxonomy": browser_assist_failure_taxonomy(),
        "session_contract": build_browser_assist_session_contract(
            normalized_url,
            platform=platform,
            task_goal=task_goal,
            min_visible_items=min_visible_items,
        ),
        "user_prompt": user_prompt,
        "agent_execution_rule": (
            "Use only the host Agent's already-available browser/computer-use/webview tool. "
            "For this visible-page evidence task, do not install Playwright, do not launch a separate browser profile, "
            "and do not read browser cookies/profile/storage. If credential access is truly needed, stop and request a separate, "
            "explicit credential authorization for the target platform and keep credential material out of browser-visible payloads. "
            "If no host browser tool exists, stop and use the manual fallback."
        ),
        "cookie_access_policy": _cookie_access_policy(platform),
        "boundaries": [
            "浏览器辅助补证必须由用户明确授权。",
            "只使用宿主 Agent 已有的浏览器/Computer Use/WebView 工具，不安装 Playwright，不启动独立浏览器 profile。",
            "默认只读取目标页面可见内容，不读取 Cookie、Token、浏览器 profile、浏览器数据库、localStorage、sessionStorage、钥匙串。",
            "私信、订单、后台、账号设置等私域页面只有在任务目标页和用途被用户单独明确授权后，才可作为 private_account_evidence 读取可见内容。",
            "Cookie、Token、localStorage、sessionStorage、浏览器数据库、profile、钥匙串和密码属于凭据材料，不作为浏览器可见页 payload 读取或入库。",
            "不执行点赞、评论、关注、发帖、私信、下单、提交表单等写操作。",
            "补证内容可能依赖用户当前浏览器状态，应标注 browser_assisted 和 visible_page_only。",
            "多步补证要绑定同一目标页会话；页面跳转、登录、SPA 变化后重新确认 URL 和标题，不复用旧快照。",
            "等待动态内容时优先使用可见正文、结果数增长、DOM 变化或网络响应等就绪信号，不用固定 sleep 当作证据充分。",
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


def build_browser_assist_adapter_contract(adapter: str = "openguanlan", *, platform: str = "") -> dict[str, Any]:
    """Return a stable contract for a browser-assist adapter."""

    adapter_id = resolve_browser_assist_adapter(adapter)
    spec = dict(BROWSER_ASSIST_ADAPTERS[adapter_id])
    executable = str(spec.get("executable") or "")
    command_env = str(spec.get("env_command") or "")
    command_template = os.environ.get(command_env, "").strip() if command_env else ""
    executable_path = _resolve_adapter_executable(adapter_id, executable)
    opencli_profile = _opencli_browser_profile(command_template=command_template) if adapter_id == "open-cli" else {}
    if adapter_id == "open-cli" and opencli_profile.get("browser_bridge_available"):
        spec["kind"] = "opencli_browser_bridge"
        spec["description"] = "检测到 OpenCLI 浏览器桥；可打开并按 Guanlan 可见页契约提取目标页正文，默认 OpenGuanlan 主路径仍无需 OpenCLI。"
        spec["can_extract"] = True
        spec["adapter_role"] = "extractor"
        spec["risk_level"] = "medium"
        spec["privacy_boundary"] = "user_authorized_visible_or_private_account_page_only"
        executable_path = str(opencli_profile.get("opencli_path") or executable_path)
    platform_ok = _adapter_supports_platform(spec, platform)
    always_available = adapter_id in {"host-browser", "openguanlan"}
    available = bool(always_available or executable_path or command_template)
    capabilities = _adapter_capabilities(adapter_id, spec, platform_supported=platform_ok, available=available)
    return {
        **spec,
        "id": adapter_id,
        "available": available,
        "capability_layer": capabilities["capability_layer"],
        "capability_score": capabilities["capability_score"],
        "risk_score": capabilities["risk_score"],
        "capabilities": capabilities,
        "executable_path": executable_path,
        "command_template_env": command_env,
        "command_template_configured": bool(command_template),
        "opencli_profile": opencli_profile,
        "openguanlan_profile": _openguanlan_browser_profile(command_template=command_template)
        if adapter_id in {"openguanlan", "openguanlan-bridge"}
        else {},
        "social_evidence_protocol": build_social_evidence_protocol(platform),
        "setup_guidance": _opencli_setup_guidance(opencli_profile) if adapter_id == "open-cli" else {},
        "native_setup_guidance": _openguanlan_setup_guidance()
        if adapter_id in {"openguanlan", "openguanlan-bridge"}
        else {},
        "platform": platform,
        "platform_supported": platform_ok,
        "output_schema": build_browser_assist_task(
            ["https://example.com/article"],
            platform=platform,
            max_pages=1,
            max_chars_per_page=3000,
        )["output_schema"],
        "readiness_contract": browser_assist_readiness_contract(platform=platform),
        "repair_protocol": browser_assist_repair_protocol(adapter_id),
        "archive_next_step": "guanlan archive add-browser-note --from-json browser-notes.jsonl",
        "safety": {
            "read_only": True,
            "visible_page_only_by_default": True,
            "private_account_visible_pages_require_targeted_explicit_authorization": True,
            "credential_material_access_allowed": False,
            "cookie_access_requires_separate_explicit_authorization": True,
            "forbidden_actions": FORBIDDEN_BROWSER_ASSIST_ACTIONS,
            "conditional_actions": CONDITIONAL_BROWSER_ASSIST_ACTIONS,
            "forbidden_implementations": FORBIDDEN_BROWSER_ASSIST_IMPLEMENTATIONS,
        },
    }


def check_browser_assist_adapter(
    adapter: str = "openguanlan",
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

    if adapter_id in {"host-browser", "openguanlan"}:
        if adapter_id == "openguanlan":
            add("openguanlan_contract", "ok", "OpenGuanlan 默认就是浏览器补证契约层；不要求扩展、daemon 或本机可执行文件。")
            add("host_browser_contract", "ok", "执行仍交给宿主 Agent 浏览器读取目标页可见内容。")
            dry_run_mode = "openguanlan_contract"
        else:
            add("host_browser_contract", "ok", "宿主浏览器路径只生成任务契约，不需要本机可执行文件。")
            dry_run_mode = "contract_only"
        add("dry_run", "ok", "dry-run 可用：返回 host Agent 可执行契约，不读取浏览器状态。")
        capabilities = dict(contract.get("capabilities") or {})
        return {
            "status": "ok" if platform_supported else "fail",
            "ready": platform_supported,
            "capability_layer": capabilities.get("capability_layer", "extractor"),
            "capability_score": capabilities.get("capability_score", 0),
            "risk_score": capabilities.get("risk_score", 0),
            "can_open": bool(capabilities.get("can_open")),
            "can_extract_visible_text": bool(capabilities.get("can_extract_visible_text")),
            "can_reuse_existing_session": bool(capabilities.get("can_reuse_existing_session")),
            "can_wait_dynamic_ready": bool(capabilities.get("can_wait_dynamic_ready")),
            "can_scroll_until_min_items": bool(capabilities.get("can_scroll_until_min_items")),
            "can_read_private_account_visible_pages": bool(capabilities.get("can_read_private_account_visible_pages")),
            "credential_material_access_allowed": bool(capabilities.get("credential_material_access_allowed")),
            "cookie_flow_available": bool(capabilities.get("cookie_flow_available")),
            "checks": checks,
            "dry_run_available": platform_supported,
            "dry_run_mode": dry_run_mode,
            "repair_hints": hints,
        }

    executable_path = str(contract.get("executable_path") or "")
    command_env = str(contract.get("command_template_env") or "")
    template_configured = bool(contract.get("command_template_configured"))
    opencli_profile = dict(contract.get("opencli_profile") or {})
    if executable_path:
        add("executable", "ok", "已找到可执行文件。", path=executable_path)
    else:
        add("executable", "warn", "未在 PATH 中找到默认可执行文件。")

    if adapter_id == "open-cli":
        if opencli_profile.get("browser_bridge_available"):
            add("opencli_browser_bridge", "ok", "检测到 OpenCLI 浏览器桥，open-cli 能力层升级为 extractor。")
        else:
            add("opencli_browser_bridge", "warn", "未检测到 OpenCLI 浏览器桥；open-cli 仅作为系统 opener。")

    if command_env:
        if template_configured:
            add("command_template", "ok", f"已配置 {command_env}。")
        else:
            template_status = "warn" if adapter_id == "open-cli" else "fail"
            add("command_template", template_status, f"未配置 {command_env}。")
            if adapter_id == "xhs-cli":
                hints.append(f"设置 {command_env}，命令模板需包含 {{url}}，可选包含 {{output}}。")

    if adapter_id == "open-cli":
        dry_run_command = _opencli_doctor_command(opencli_profile) or _open_cli_command(dry_run_url)
    elif adapter_id == "openguanlan-bridge":
        dry_run_command = _openguanlan_doctor_command() or _external_adapter_command(adapter_id, dry_run_url, output_path="")
    elif adapter_id == "browser-use":
        dry_run_command = _browser_use_doctor_command()
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
    capabilities = _adapter_capabilities(
        adapter_id,
        dict(contract),
        platform_supported=platform_supported,
        available=bool(contract.get("available")),
        executable_ready=executable_ok,
    )
    status = "ok" if ready else ("fail" if adapter_id not in {"xhs-cli", "browser-use", "openguanlan-bridge"} else "warn")
    if adapter_id == "open-cli" and not ready:
        hints.append("安装系统打开命令，或配置 GUANLAN_BROWSER_ASSIST_OPEN_CLI_COMMAND。")
    if adapter_id == "openguanlan-bridge" and not ready:
        hints.append("openguanlan-bridge 是可选扩展桥；无需它也可直接使用 --adapter openguanlan 生成宿主浏览器补证契约。")
    if adapter_id == "xhs-cli" and not executable_path:
        hints.append("如需小红书外部适配器，先安装并配置 xhs-cli；否则继续使用 OpenGuanlan 稳定路径。")
    if adapter_id == "browser-use" and not ready:
        hints.append(
            "如需 browser-use，可安装后再试：`uvx --from 'browser-use[cli]' browser-use doctor`，或配置 "
            "`GUANLAN_BROWSER_ASSIST_BROWSER_USE_COMMAND`。"
        )

    return {
        "status": status,
        "ready": ready,
        "capability_layer": capabilities.get("capability_layer", "opener"),
        "capability_score": capabilities.get("capability_score", 0),
        "risk_score": capabilities.get("risk_score", 0),
        "can_open": bool(capabilities.get("can_open")) and executable_ok,
        "can_extract_visible_text": bool(capabilities.get("can_extract_visible_text")) and executable_ok,
        "can_reuse_existing_session": bool(capabilities.get("can_reuse_existing_session")),
        "can_wait_dynamic_ready": bool(capabilities.get("can_wait_dynamic_ready")) and executable_ok,
        "can_scroll_until_min_items": bool(capabilities.get("can_scroll_until_min_items")) and executable_ok,
        "can_read_private_account_visible_pages": bool(capabilities.get("can_read_private_account_visible_pages")) and executable_ok,
        "credential_material_access_allowed": bool(capabilities.get("credential_material_access_allowed")),
        "cookie_flow_available": bool(capabilities.get("cookie_flow_available")),
        "checks": checks,
        "dry_run_available": ready,
        "dry_run_mode": "command_template"
        if template_configured
        else (
            "opencli_doctor"
            if adapter_id == "open-cli" and opencli_profile.get("browser_bridge_available")
            else (
                "openguanlan_bridge_doctor"
                if adapter_id == "openguanlan-bridge"
                else ("builtin_open" if adapter_id == "open-cli" else ("builtin_doctor" if adapter_id == "browser-use" else ""))
            )
        ),
        "command_preview": _safe_command_preview(dry_run_command) if dry_run_command else [],
        "repair_hints": _unique(hints),
    }


def resolve_browser_assist_adapter(adapter: str = "openguanlan") -> str:
    """Resolve adapter aliases to canonical IDs."""

    value = str(adapter or "openguanlan").strip().lower().replace("_", "-")
    if value in BROWSER_ASSIST_ADAPTERS:
        return value
    for adapter_id, spec in BROWSER_ASSIST_ADAPTERS.items():
        aliases = {str(item).lower().replace("_", "-") for item in spec.get("aliases", [])}
        if value in aliases:
            return adapter_id
    return "openguanlan"


def run_browser_assist_adapter(
    url: str,
    *,
    adapter: str = "openguanlan",
    execute: bool = False,
    command_template: str = "",
    timeout: int = 90,
    output_path: str = "",
    page_type: str = "access_gate",
    signals: list[str] | None = None,
    platform: str = "",
    max_pages: int = 3,
    max_chars_per_page: int = 3000,
    min_visible_items: int = 0,
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
        min_visible_items=max(min_visible_items, 0),
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
            "target private/account pages require separate explicit authorization, and credential material must stay out of browser-visible payloads."
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
    if adapter_id in {"host-browser", "openguanlan"}:
        response["status"] = "requires_host_browser_execution"
        response["execution_boundary"] = (
            "openguanlan_browser_assist_layer_uses_host_agent_visible_page"
            if adapter_id == "openguanlan"
            else "host_agent_must_open_and_read_visible_page"
        )
        if adapter_id == "openguanlan":
            response["native_setup"] = build_openguanlan_browser_bridge_setup_plan()
            response["next_step"] = "用户授权后由宿主 Agent 浏览器读取目标页可见内容；可选 openguanlan-bridge 不是默认前置。"
        return response

    if adapter_id == "openguanlan-bridge":
        command = _openguanlan_command(normalized_url, command_template=command_template, output_path=output_path)
        response["command"] = command
        response["native_setup"] = build_openguanlan_browser_bridge_setup_plan()
        if not command:
            response.update(
                {
                    "status": "optional_bridge_not_installed",
                    "error": "openguanlan_bridge_runtime_not_available",
                    "setup_hint": "openguanlan-bridge 只是可选增强；默认使用 guanlan browser-assist run \"URL\" --adapter openguanlan --json。",
                }
            )
            return response
        if not execute:
            response["status"] = "ready_to_execute_openguanlan_bridge"
            response["next_step"] = "确认用户授权、daemon 和扩展配对后加 --execute；输出必须为 Guanlan browser-visible JSON/JSONL。"
            return response
        return _execute_adapter_command(
            response,
            command,
            timeout=timeout,
            output_path=output_path,
            parse_stdout=True,
            post_status="executed_openguanlan_bridge",
        )

    if adapter_id == "open-cli":
        command = _open_cli_command(normalized_url, command_template=command_template, output_path=output_path)
        response["command"] = command
        capabilities = dict(contract.get("capabilities") or {})
        runtime_extract_capable = bool(
            capabilities.get("can_extract_visible_text")
            or _command_template_uses_opencli(command_template)
            or _open_cli_command_supports_payload(command_template)
        )
        parse_stdout = bool(runtime_extract_capable and _open_cli_command_supports_payload(command_template))
        if not execute:
            response["status"] = "ready_to_extract_with_opencli" if runtime_extract_capable else "ready_to_open"
            response["next_step"] = (
                "检测到 OpenCLI 浏览器桥；如已配置会输出 Guanlan browser-visible JSON/JSONL 的命令模板，可加 --execute 执行。"
                if runtime_extract_capable
                else "Run with --execute, then let the host Agent read visible page content."
            )
            if runtime_extract_capable and not _open_cli_command_supports_payload(command_template):
                response["template_hint"] = (
                    "默认 OpenCLI 命令只负责打开并绑定会话。若要让 Guanlan 自动解析 stdout，请通过 "
                    "GUANLAN_BROWSER_ASSIST_OPEN_CLI_COMMAND 或 --command-template 配置只读提取命令，并输出 browser-visible JSON/JSONL。"
                )
            return response
        return _execute_adapter_command(
            response,
            command,
            timeout=timeout,
            output_path=output_path,
            parse_stdout=parse_stdout,
            post_status="executed_opencli_extractor" if parse_stdout else "opened_requires_host_extraction",
        )
    if adapter_id == "browser-use":
        command = _browser_use_open_command(
            normalized_url,
            command_template=command_template,
            output_path=output_path,
        )
        response["command"] = command
        if not command:
            response.update(
                {
                    "status": "adapter_unavailable",
                    "error": "browser_use_not_installed",
                    "setup_hint": (
                        "先安装 browser-use CLI（例如 `uvx --from 'browser-use[cli]' browser-use doctor`），"
                        "或通过 `GUANLAN_BROWSER_ASSIST_BROWSER_USE_COMMAND` 配置命令模板。"
                    ),
                }
            )
            return response
        if not execute:
            response["status"] = "ready_to_open"
            response["next_step"] = (
                "加 --execute 打开页面；如需使用已有登录态，请在宿主 Agent 的浏览器里完成登录/验证，"
                "并按可见页契约提取正文。"
            )
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
        lines.append(f"- 能力层: {item.get('capability_layer') or item.get('adapter_role') or '-'}")
        lines.append(f"- 稳定性: {item.get('stability')}")
        lines.append(f"- 能力评分: {item.get('capability_score', 0)} / 风险评分: {item.get('risk_score', 0)}")
        lines.append(f"- 可用: {'是' if item.get('available') else '否'}")
        lines.append(f"- 支持平台: {', '.join(item.get('supports_platforms') or [])}")
        lines.append(f"- 说明: {item.get('description')}")
        if item.get("command_template_env"):
            lines.append(f"- 命令模板环境变量: `{item.get('command_template_env')}`")
        check = item.get("check") or {}
        if check:
            lines.append(f"- 自检状态: {check.get('status')} / ready={bool(check.get('ready'))}")
            lines.append(
                "- 自检能力: "
                f"open={bool(check.get('can_open'))}, "
                f"extract={bool(check.get('can_extract_visible_text'))}, "
                f"session={bool(check.get('can_reuse_existing_session'))}, "
                f"cookie_flow={bool(check.get('cookie_flow_available'))}"
            )
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


def build_opencli_browser_bridge_setup_plan(*, execute: bool = False, timeout: int = 180) -> dict[str, Any]:
    """Plan or run the explicit OpenCLI CLI install step for browser bridge use."""

    node_path = shutil.which("node") or ""
    npm_path = shutil.which("npm") or ""
    opencli_path = shutil.which("opencli") or ""
    node_version = _node_version()
    setup: dict[str, Any] = {
        "status": "ready" if opencli_path else "needs_cli_install",
        "execute": bool(execute),
        "opencli_path": opencli_path,
        "node_path": node_path,
        "npm_path": npm_path,
        "node_version": node_version,
        "node_requirement": ">=21.0.0 for the standard npm install path",
        "cli_install_command": ["npm", "install", "-g", f"{OPENCLI_NPM_PACKAGE}@latest"],
        "browser_extension": {
            "manual_user_step_required": True,
            "chrome_webstore_url": OPENCLI_CHROME_WEBSTORE_URL,
            "manual_release_zip_url": OPENCLI_RELEASES_URL,
            "why_manual": "Chrome/Chromium 扩展安装需要用户在浏览器中确认，观澜不会静默安装或启用扩展。",
        },
        "verification_commands": [
            "opencli doctor",
            "opencli profile list",
            "guanlan browser-assist adapters --check --json",
        ],
        "guanlan_next_steps": [
            "确认 opencli doctor 显示 Browser Bridge 已连接。",
            "运行 guanlan browser-assist adapters --check --json，确认 open-cli capability_layer=extractor。",
            "浏览器补证默认使用 OpenGuanlan 契约；只有用户明确选择 open-cli 时才走 OpenCLI bridge。",
        ],
        "safety": {
            "read_only": True,
            "does_not_install_chrome_extension_automatically": True,
            "does_not_read_cookies_tokens_storage_or_profile": True,
            "credential_material_access_allowed": False,
            "write_actions_forbidden": True,
        },
    }
    if opencli_path:
        setup["message"] = "OpenCLI CLI 已安装；下一步让用户安装/启用 Chrome 扩展并运行 opencli doctor。"
        return setup
    if not execute:
        setup["message"] = "OpenCLI CLI 未安装；用户可明确执行安装命令，扩展仍需手动安装。"
        return setup
    if not npm_path:
        setup.update(
            {
                "status": "blocked",
                "error": "npm_not_found",
                "message": "未找到 npm。请先安装 Node.js/npm，再运行 npm install -g @jackwener/opencli@latest。",
            }
        )
        return setup
    command = [npm_path, "install", "-g", f"{OPENCLI_NPM_PACKAGE}@latest"]
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
        setup.update({"status": "timeout", "error": f"opencli_install_timeout_after_{max(timeout, 1)}s", "command": command})
        return setup
    except Exception as exc:
        setup.update({"status": "error", "error": str(exc), "command": command})
        return setup
    opencli_path = shutil.which("opencli") or ""
    setup.update(
        {
            "command": command,
            "returncode": completed.returncode,
            "stdout_preview": (completed.stdout or "")[:800],
            "stderr_preview": (completed.stderr or "")[:800],
            "opencli_path": opencli_path,
            "status": "cli_installed" if completed.returncode == 0 and opencli_path else "cli_install_failed",
        }
    )
    if setup["status"] == "cli_installed":
        setup["message"] = "OpenCLI CLI 已安装；请继续安装/启用 Chrome 扩展，然后运行 opencli doctor。"
    else:
        setup["message"] = "OpenCLI CLI 安装未完成；请查看 stderr_preview，或手动运行 npm install -g @jackwener/opencli@latest。"
    return setup


def build_openguanlan_browser_bridge_setup_plan() -> dict[str, Any]:
    """Return the OpenGuanlan browser-assist definition and optional bridge readiness."""

    openguanlan_path = shutil.which("openguanlan") or ""
    module_path = Path(__file__).resolve().parent / "openguanlan_cli.py"
    extension_path = Path(__file__).resolve().parent / "browser_bridge" / "extension"
    manifest_path = extension_path / "manifest.json"
    runtime_packaged = module_path.exists() and manifest_path.exists()
    bridge_status = (
        "optional_bridge_entrypoint_ready"
        if openguanlan_path and runtime_packaged
        else ("optional_bridge_packaged_needs_install_entrypoint" if runtime_packaged else "optional_bridge_planned")
    )
    return {
        "status": "ready_with_host_browser_contract",
        "adapter": "openguanlan",
        "optional_bridge_adapter": "openguanlan-bridge",
        "openguanlan_path": openguanlan_path,
        "primary_requires_extension": False,
        "primary_requires_daemon": False,
        "primary_execution_contract": "guanlan browser-assist run \"URL\" --adapter openguanlan --json",
        "optional_bridge_status": bridge_status,
        "runtime_packaged": runtime_packaged,
        "module_path": str(module_path),
        "extension_path": str(extension_path),
        "extension_manifest": str(manifest_path),
        "extension_manifest_exists": manifest_path.exists(),
        "principle": "OpenGuanlan 是观澜浏览器补证总层；默认走宿主 Agent 浏览器可见页契约，不要求安装扩展、daemon 或 OpenCLI。",
        "current_default": "openguanlan",
        "host_browser_contract": "included_as_primary_execution_surface",
        "compatibility_fallback": "open-cli adapter remains optional for users who already installed OpenCLI.",
        "components": [
            "OpenGuanlan browser-assist layer: `diagnose page`、`browser-assist plan/sessions/run`、可见页字段契约和 archive 入库边界。",
            "Host Agent browser execution surface: 默认稳定路径，由宿主 Agent 在用户授权后读取目标页可见内容。",
            "openguanlan-bridge optional sidecar: 只有用户明确需要独立 Chrome/Chromium 扩展桥时，才启动 daemon、配对和扩展授权。",
        ],
        "absorbed_opencli_capability_layers": [
            "browser state/snapshot -> browser-assist readiness and visible extraction",
            "open/navigate/wait/scroll -> target-page-only collection steps",
            "find/get/extract/frames/screenshot -> browser-visible evidence helpers",
            "get text/html/title/url/value/attributes -> browser-visible JSON/JSONL payload",
            "tab/session binding -> Guanlan session contract and user-selected browser context",
            "private or logged-in pages -> explicit browser-assist authorization before read",
            "click/type/fill/select/upload/drag/eval/raw network/cookies -> excluded from Guanlan research workflows",
        ],
        "user_install_boundary": [
            "OpenGuanlan 主路径不要求安装浏览器扩展、daemon 或 opencli。",
            "不要求用户安装 opencli。",
            "Chrome/Chromium 扩展只属于 openguanlan-bridge 可选增强；如果使用，仍必须由用户手动安装/启用和配对。",
            "网页读取权限按目标页授权；默认可见页补证由宿主 Agent 浏览器完成。",
            "不读取 Cookie、Token、localStorage、sessionStorage、浏览器数据库、profile、钥匙串或密码。",
            "只读目标页可见内容；私域目标页仍需要单独明确授权并标记 private_account_evidence。",
        ],
        "commands": [
            "guanlan browser-assist adapters --check --json",
            "guanlan browser-assist run \"URL\" --adapter openguanlan --json",
            "guanlan browser-assist sessions \"URL\" --json",
        ],
        "optional_bridge_commands": [
            "guanlan browser-assist run \"URL\" --adapter openguanlan-bridge --json",
            "openguanlan setup --json",
            "openguanlan daemon",
            "openguanlan pair-code --json",
            "openguanlan doctor --json",
            "scripts/build_openguanlan_extension.sh",
        ],
        "chrome_store": {
            "package_command": "scripts/build_openguanlan_extension.sh",
            "privacy_policy": "website/openguanlan-browser-bridge-privacy.html",
            "permission_model": "localhost daemon by default; target sites via optional_host_permissions and popup grant",
            "scope": "optional openguanlan-bridge sidecar, not the definition of OpenGuanlan",
        },
        "next_engineering_step": "把 Agent 文案统一改成：OpenGuanlan 默认是浏览器补证层；插件桥只是可选侧车。",
        "safety": {
            "read_only": True,
            "credential_material_access_allowed": False,
            "extension_install_requires_user_confirmation": False,
            "optional_bridge_extension_install_requires_user_confirmation": True,
            "write_actions_forbidden": True,
        },
    }


def format_opencli_browser_bridge_setup_markdown(setup: dict[str, Any]) -> str:
    """Render OpenCLI browser bridge setup guidance."""

    lines = [
        "# OpenCLI 浏览器桥安装向导",
        "",
        f"- 状态: {setup.get('status')}",
        f"- opencli: {setup.get('opencli_path') or '未找到'}",
        f"- node: {setup.get('node_path') or '未找到'} {setup.get('node_version') or ''}".rstrip(),
        f"- npm: {setup.get('npm_path') or '未找到'}",
        f"- 说明: {setup.get('message') or ''}",
    ]
    command = setup.get("cli_install_command") or []
    if command:
        lines.append("- CLI 安装命令: `" + " ".join(shlex.quote(str(part)) for part in command) + "`")
    extension = setup.get("browser_extension") or {}
    if extension:
        lines.extend(
            [
                "- 浏览器扩展: 用户手动安装/启用",
                f"  - Chrome Web Store: {extension.get('chrome_webstore_url')}",
                f"  - 手动 zip: {extension.get('manual_release_zip_url')}",
            ]
        )
    verification = setup.get("verification_commands") or []
    if verification:
        lines.append("- 验证命令:")
        lines.extend(f"  - `{item}`" for item in verification)
    next_steps = setup.get("guanlan_next_steps") or []
    if next_steps:
        lines.append("- 观澜下一步:")
        lines.extend(f"  - {item}" for item in next_steps)
    if setup.get("error"):
        lines.append(f"- 错误: {setup.get('error')}")
    return "\n".join(lines)


def format_openguanlan_browser_bridge_setup_markdown(setup: dict[str, Any]) -> str:
    lines = [
        "# OpenGuanlan 浏览器补证层",
        "",
        f"- 状态: {setup.get('status')}",
        f"- openguanlan: {setup.get('openguanlan_path') or '未在 PATH 中找到'}",
        f"- 主路径是否需要扩展: {setup.get('primary_requires_extension')}",
        f"- 主路径是否需要 daemon: {setup.get('primary_requires_daemon')}",
        f"- 主路径契约: `{setup.get('primary_execution_contract')}`",
        f"- 可选桥状态: {setup.get('optional_bridge_status')}",
        f"- 默认路径: {setup.get('current_default')}",
        f"- 兼容路径: {setup.get('compatibility_fallback')}",
        f"- 原则: {setup.get('principle')}",
    ]
    components = setup.get("components") or setup.get("planned_components") or []
    if components:
        lines.append("- 组件:")
        lines.extend(f"  - {item}" for item in components)
    layers = setup.get("absorbed_opencli_capability_layers") or []
    if layers:
        lines.append("- 内化能力层:")
        lines.extend(f"  - {item}" for item in layers)
    boundaries = setup.get("user_install_boundary") or []
    if boundaries:
        lines.append("- 安装与安全边界:")
        lines.extend(f"  - {item}" for item in boundaries)
    commands = setup.get("commands") or []
    if commands:
        lines.append("- 命令:")
        lines.extend(f"  - `{item}`" for item in commands)
    optional_commands = setup.get("optional_bridge_commands") or []
    if optional_commands:
        lines.append("- 可选扩展桥命令:")
        lines.extend(f"  - `{item}`" for item in optional_commands)
    lines.append(f"- 下一步工程: {setup.get('next_engineering_step')}")
    return "\n".join(lines)


def build_browser_assist_task(
    urls: list[str],
    *,
    platform: str = "",
    evidence_role: str = "user_visible_sample",
    max_pages: int = 3,
    max_chars_per_page: int = 3000,
    min_visible_items: int = 0,
    task_goal: str = "",
) -> dict[str, Any]:
    """Build the OpenGuanlan visible-page task description for Agent platforms.

    The task is declarative: Guanlan asks the host Agent to read visible page
    content only after user permission. Guanlan itself does not automate the
    browser or access a browser session.
    """

    clean_urls = _unique(urls)
    max_pages = max(max_pages, 1)
    max_chars_per_page = max(max_chars_per_page, 1)
    min_visible_items = max(min_visible_items, 0)
    template = browser_assist_platform_template(platform)
    extract_fields = _unique(
        [*(template.get("extract_fields") or []), "url", "title", "visible_text", "captured_at", "skipped_reason"]
    )
    platform_quality_checks = list(template.get("quality_checks") or [])
    social_protocol = build_social_evidence_protocol(platform)
    output_schema = {
        "url": "string",
        "title": "string",
        "visible_text": "string",
        "author": "string",
        "published_at": "string",
        "captured_at": "unix_timestamp_or_iso8601",
        "visible_context": "string",
        "platform": "string",
        "source_mode": "browser_visible",
        "browser_assisted": True,
        "user_authorized": True,
        "visible_page_only": True,
        "private_account_evidence": False,
        "session_dependent": True,
    }
    if social_protocol.get("enabled"):
        output_schema.update(social_visible_output_schema(platform))
    return {
        "task_type": "open_and_read_visible_page",
        "status": "requires_user_approval",
        "read_only": True,
        "platform": platform,
        "platform_template": template,
        "evidence_role": template.get("evidence_role") or evidence_role,
        "task_goal": task_goal or "补充公开读取不足的目标页面可见证据；只取目标可见页，不扩大到无关账号隐私区。",
        "urls": clean_urls[:max_pages],
        "max_pages": max_pages,
        "max_chars_per_page": max_chars_per_page,
        "collection_steps": [
            "先向用户复述授权话术，获得明确允许后再继续。",
            "确认当前 Agent 平台已经提供浏览器/Computer Use/WebView 工具；如果没有，不要安装 Playwright 或自建浏览器，直接走手动兜底。",
            "使用宿主 Agent 已有浏览器能力打开任务 urls；如果用户需要登录、验证或切换账号，请让用户在可见浏览器里完成。",
            "只读取任务目标页的浏览器可见内容；如需滚动，只为读取目标页可见正文或公开评论摘要。",
            "按 platform_template.extract_fields 提取字段；平台无模板时提取标题、URL、可见正文、作者/账号、发布时间、采集时间和可见上下文说明。",
            "当前浏览器会话可以继续复用已有登录态、Cookie 和浏览历史上下文让目标页可见，但默认不导出这些材料，也不把它们写进 browser-visible payload。",
            "如果页面要求登录但浏览器已可见，只读取当前页面可见内容；不要在本任务里读取 Cookie、Token、浏览器 profile、localStorage、sessionStorage、钥匙串、浏览器数据库或无关个人资料。",
            "如果目标任务就是私信、订单、后台或账号设置页，必须确认用户已对该目标页、用途和只读范围单独授权，并在输出中标记 private_account_evidence=true。",
            "如果私域页不是任务目标，或授权不清楚，立即跳过并在输出中标记 skipped_reason=private_area_not_authorized。",
            "如果仅靠可见浏览器仍无法访问，停止并向用户说明：下一步需要单独凭据授权；用户未明确同意前不要尝试提取 Cookie、Token 或浏览器存储。",
            "遇到支付确认、发布框、提交表单或任何写操作入口，立即跳过并在输出中标记 skipped_reason。",
        ],
        "extract_fields": extract_fields,
        "social_evidence_protocol": social_protocol,
        "output_schema": output_schema,
        "execution_contract": build_browser_assist_execution_contract(
            clean_urls[:max_pages],
            platform=platform,
            extract_fields=extract_fields,
            max_chars_per_page=max_chars_per_page,
            min_visible_items=min_visible_items,
        ),
        "session_contract": build_browser_assist_session_contract(
            clean_urls[0] if clean_urls else "",
            platform=platform,
            task_goal=task_goal,
            min_visible_items=min_visible_items,
        ),
        "readiness_contract": browser_assist_readiness_contract(platform=platform),
        "sufficiency_contract": browser_assist_sufficiency_contract(
            platform=platform,
            min_visible_items=min_visible_items,
        ),
        "archive_commands": [
            "guanlan archive add-browser-note --from-json browser-notes.jsonl",
            'guanlan archive add-browser-note --url "URL" --text-file notes.md  # fallback only',
        ],
        "host_browser_contract": {
            "requires_host_browser_tool": True,
            "uses_existing_browser_session": True,
            "may_reuse_existing_cookie_and_history_context_for_rendering": True,
            "user_may_login_or_verify_in_browser": True,
            "agent_may_read_visible_dom_text": True,
            "agent_must_not_install_or_launch_own_browser": True,
            "agent_must_not_use_local_browser_profile": True,
            "agent_must_not_extract_credentials_or_storage": True,
            "agent_may_read_target_private_account_visible_page_after_explicit_authorization": True,
            "cookie_access_requires_separate_explicit_authorization": True,
            "exporting_cookie_or_history_artifacts_requires_separate_explicit_authorization": True,
            "manual_copy_is_fallback_only": True,
        },
        "if_no_host_browser_tool": {
            "action": "stop_and_ask_user_for_manual_visible_text",
            "reason": "浏览器辅助补证依赖宿主 Agent 的浏览器能力；没有该能力时，不应通过读取本机 profile/Cookie 来模拟登录态。",
            "fallback_command": 'guanlan archive add-browser-note --url "URL" --text-file notes.md',
        },
        "quality_checks": [
            *platform_quality_checks,
            "visible_text 不应为空，建议至少 80 个中文字符或等价信息量。",
            "url 必须是目标页或同一任务候选页，不要把推荐流无关页面混入。",
            "如果只能看到登录提示、验证码或空壳，应输出 skipped_reason，而不是伪造成正文证据。",
            "补证材料必须标注 browser_assisted / visible_page_only / user_authorized / session_dependent。",
            "不要只因为固定等待结束就认为页面已充分加载；必须满足 readiness_contract 或填写 skipped_reason。",
            "列表/评论/搜索页如果设置了 min_visible_items，应滚动到足够条数、连续无增长或达到上限，并输出 collected_count 与 partial_reason。",
            "private_account_evidence=true 只能用于用户明确授权的目标页，不可用于无关私域页面。",
        ],
        "allowed_actions": ALLOWED_BROWSER_ASSIST_ACTIONS,
        "conditional_actions": CONDITIONAL_BROWSER_ASSIST_ACTIONS,
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
            "unrelated_private_messages",
            "unrelated_orders",
            "unrelated_admin_pages",
            "unrelated_personal_data",
        ],
        "conditional_access": {
            "target_private_account_visible_pages": "allowed_only_after_targeted_explicit_user_authorization",
            "cookies": "not_part_of_browser_visible_payload; requires_separate_credential_flow",
            "tokens": "forbidden",
            "keychain": "forbidden",
            "passwords": "forbidden",
            "browser_profile": "forbidden",
            "local_storage": "forbidden",
            "session_storage": "forbidden",
        },
        "output_contract": {
            "source_mode": "browser_visible",
            "browser_assisted": True,
            "visible_page_only": True,
            "user_authorized": True,
            "private_account_evidence": False,
            "session_dependent": True,
            "reproducibility": "session_dependent",
        },
    }


def build_browser_assist_execution_contract(
    urls: list[str],
    *,
    platform: str = "",
    extract_fields: list[str] | None = None,
    max_chars_per_page: int = 3000,
    min_visible_items: int = 0,
) -> dict[str, Any]:
    """Stable instructions that host agents can execute with their own browser tool."""

    fields = _unique(extract_fields or [])
    output_schema = {
        "url": "string",
        "title": "string",
        "visible_text": "string",
        "author": "string",
        "published_at": "string",
        "captured_at": "iso8601_or_unix_timestamp",
        "visible_context": "string",
        "skipped_reason": "string",
        "requested_min_items": "integer",
        "collected_count": "integer",
        "partial_reason": "string",
        "platform": "string",
        "source_mode": "browser_visible",
        "browser_assisted": True,
        "visible_page_only": True,
        "user_authorized": True,
        "private_account_evidence": False,
        "session_dependent": True,
    }
    social_protocol = build_social_evidence_protocol(platform)
    if social_protocol.get("enabled"):
        output_schema.update(social_visible_output_schema(platform))
    return {
        "version": "browser_visible_v2",
        "task": "open_target_urls_and_extract_visible_page_only",
        "platform": platform,
        "urls": _unique(urls),
        "extract_fields": fields,
        "max_chars_per_page": max(max_chars_per_page, 1),
        "min_visible_items": max(min_visible_items, 0),
        "readiness_contract": browser_assist_readiness_contract(platform=platform),
        "sufficiency_contract": browser_assist_sufficiency_contract(
            platform=platform,
            min_visible_items=min_visible_items,
        ),
        "wait_for_user_steps": [
            "login",
            "verification",
            "account_switch",
        ],
        "success_criteria": [
            "url matches the target page or task candidate page",
            "visible_text or skipped_reason is present",
            "if min_visible_items > 0, collected_count or partial_reason is present",
            "browser_assisted=true, visible_page_only=true, user_authorized=true, session_dependent=true",
            "private_account_evidence is true only for target private/account pages with explicit authorization",
        ],
        "failure_reasons": list(browser_assist_failure_taxonomy().keys()),
        "social_evidence_protocol": social_protocol,
        "output_schema": output_schema,
    }


def browser_assist_platform_template(platform: str = "") -> dict[str, Any]:
    """Return a platform-specific visible-page extraction template."""

    normalized = str(platform or "").strip().lower()
    social_template = dict(social_browser_assist_template(normalized) or {})
    template = dict(BROWSER_ASSIST_PLATFORM_TEMPLATES.get(normalized) or {})
    if social_template:
        merged = dict(social_template)
        for key, value in template.items():
            if key in {"extract_fields", "field_hints", "quality_checks", "risk_tags", "content_types"}:
                merged[key] = _unique([*(merged.get(key) or []), *(value or [])])
            elif key == "session_policy":
                session_policy = dict(merged.get("session_policy") or {})
                session_policy.update(dict(value or {}))
                merged[key] = session_policy
            elif key == "supported_capabilities":
                capabilities = dict(merged.get("supported_capabilities") or {})
                capabilities.update(dict(value or {}))
                merged[key] = capabilities
            else:
                merged[key] = value
        return merged
    if not template:
        return {
            "name": "通用可见页",
            "evidence_role": "user_visible_sample",
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
            "field_hints": ["只读取任务目标页可见内容。"],
            "quality_checks": ["visible_text 为空时必须填写 skipped_reason。"],
        }
    return template


def build_browser_assist_session_contract(
    url: str = "",
    *,
    platform: str = "",
    task_goal: str = "",
    min_visible_items: int = 0,
) -> dict[str, Any]:
    """Return a host-agent session contract without touching browser state."""

    normalized_url = str(url or "").strip()
    inferred_platform = platform or platform_hint(normalized_url)
    safe_host = urlparse(normalized_url).netloc.lower().replace(":", "-") or "target"
    session_id = f"guanlan-visible-{safe_host}"[:80]
    return {
        "version": "browser_visible_session_v1",
        "session_id_hint": session_id,
        "platform": inferred_platform,
        "target_url": normalized_url,
        "task_goal": task_goal or "只读补充目标页浏览器可见证据",
        "ownership": "host_agent_existing_browser_only",
        "requires_user_authorization": True,
        "user_may_login_or_verify": True,
        "agent_allowed_to_bind_visible_tab": True,
        "existing_cookie_or_history_context_may_keep_target_page_renderable": True,
        "agent_must_not_create_private_browser_profile": True,
        "agent_must_not_read_browser_profile_or_storage": True,
        "same_session_rules": [
            "同一补证任务使用同一 session_id_hint，避免把多个平台或多个账号的页面混在一起。",
            "每次读取前确认当前 tab 的 URL 与 target_url 或候选 URL 同源/同任务。",
            "登录、验证、SPA 跳转、排序/筛选变化后重新获取标题、URL、正文和结果数，不复用旧快照。",
            "当前浏览器已有 Cookie 和浏览历史上下文只用于保持目标页可见，不导出、不入库。",
            "多 tab 场景必须显式记录读取的是哪个目标页；不读取无关 tab。",
        ],
        "readiness_signals": browser_assist_readiness_contract(platform=inferred_platform),
        "sufficiency_contract": browser_assist_sufficiency_contract(
            platform=inferred_platform,
            min_visible_items=min_visible_items,
        ),
        "timeout_budget_seconds": 90,
        "timeout_budget_ms": 90000,
        "unit_rule": "timeout_budget_seconds 用秒；字段名是 timeout_ms/timeout_milliseconds 时用毫秒，90 秒 = 90000 ms。",
        "release_rule": "完成目标页提取，或遇到未授权 private_area_detected / credential_authorization_required 后结束本次会话，不继续浏览无关页面。",
        "output_boundary": {
            "source_mode": "browser_visible",
            "browser_assisted": True,
            "visible_page_only": True,
            "user_authorized": True,
            "private_account_evidence": False,
            "session_dependent": True,
        },
    }


def browser_assist_readiness_contract(*, platform: str = "") -> dict[str, Any]:
    """Describe robust page-readiness signals for host browser extraction."""

    platform_label = platform or "generic"
    return {
        "platform": platform_label,
        "principle": "优先等待可解释的内容就绪信号；固定 sleep 只能作为最后兜底，不能单独证明页面已加载充分。",
        "preferred_signals": [
            "target_url_or_same_task_candidate_confirmed",
            "title_or_primary_heading_visible",
            "main_visible_text_non_empty",
            "result_count_or_visible_card_count_increased",
            "dom_mutation_plateau_after_scroll",
            "relevant_network_response_seen_if_host_tool_exposes_network",
        ],
        "avoid_as_primary_signal": [
            "fixed_sleep_only",
            "screenshot_only_without_text",
            "localized_aria_label_or_placeholder_only",
            "stale_ref_from_previous_snapshot",
        ],
        "selector_guidance": [
            "aria-label、placeholder、title、alt、按钮可见文案会随语言环境变化；不要把单一中文/英文 UI 文本当稳定锚点。",
            "优先使用稳定 data-*、URL、结构化正文区域、文章/卡片容器、同源网络响应或多语言 fallback。",
            "页面变化后重新定位元素；如果定位不到，输出 skipped_reason=selector_or_locale_mismatch，不要返回空正文假成功。",
        ],
    }


def browser_assist_sufficiency_contract(*, platform: str = "", min_visible_items: int = 0) -> dict[str, Any]:
    """Return collection sufficiency rules for dynamic lists and social pages."""

    target = max(int(min_visible_items or 0), 0)
    platform_label = platform or "generic"
    list_like = platform_label in {"xiaohongshu", "rednote", "zhihu", "weibo", "bilibili", "douban", "linkedin"}
    return {
        "platform": platform_label,
        "requested_min_items": target,
        "applies_to": "list_or_comment_or_search_page" if list_like or target else "article_or_single_page",
        "rules": [
            "单篇文章/笔记页优先保证标题、正文、作者/账号、发布时间和 URL。",
            "列表、评论或搜索页需要结果池时，不要只取首屏；滚动到 requested_min_items、连续两轮无新增、触达平台边界或达到滚动上限后停止。",
            "停止时输出 collected_count；未达到 requested_min_items 时输出 partial_reason，例如 plateaued、login_gate、rate_limited、no_more_results。",
            "不要为了凑数量跳到无关推荐流或私域页面。",
        ],
        "default_scroll_policy": {
            "max_scroll_rounds": 15 if list_like or target else 3,
            "plateau_rounds": 2,
            "wait_after_growth_ms": 200,
            "max_wait_per_scroll_ms": 2500,
        },
    }


def browser_assist_repair_protocol(adapter_id: str = "host-browser") -> dict[str, Any]:
    """Agent-readable failure repair protocol for browser-assist adapters."""

    return {
        "version": "browser_assist_repair_v1",
        "adapter": adapter_id,
        "max_rounds": 3,
        "when_to_use": "适配器打开失败、可见正文为空、结果数明显少于请求、selector/locale 漂移或外部 CLI stdout 无法解析时。",
        "steps": [
            "保留原始任务 URL、平台、adapter、command_preview、status、error、stdout_preview、stderr_preview。",
            "不要立刻扩大权限；先用 adapters --check 或同一 host-browser 会话重新确认平台、URL、可见状态和 readiness 信号。",
            "如果是 selector_or_locale_mismatch，改用稳定结构、URL、data-* 或多语言 fallback；不要把空结果当成功。",
            "如果是 insufficient_visible_items，按 sufficiency_contract 继续滚动或输出 partial_reason。",
            "如果是 auth/login/captcha/rate_limit/private_area，先确认是否是用户明确授权的目标页；不是则停止并说明边界，不改成 Cookie 流。",
            "最多重试 3 轮；仍失败时报告失败类型、已尝试步骤和下一步授权需求。",
        ],
        "never_fix_by": [
            "读取 Cookie/Token/浏览器 profile",
            "安装独立浏览器或 Playwright 来模拟用户登录态",
            "执行点赞、评论、关注、发布、提交表单等写操作",
            "降低字段/数量要求来伪造成功",
        ],
    }


def recommend_browser_assist_adapter(*, platform: str = "", need_extraction: bool = True) -> str:
    """Pick the least surprising adapter for Agent-facing plans."""

    if need_extraction:
        return "openguanlan"
    if platform == "xiaohongshu":
        return "openguanlan"
    return "open-cli"


def browser_assist_failure_taxonomy() -> dict[str, str]:
    """Machine-readable reasons for browser-assist failures."""

    return {
        "needs_login": "目标页要求用户在可见浏览器里登录。",
        "needs_verification": "目标页要求用户完成验证码、安全验证或设备确认。",
        "visible_shell_only": "浏览器里只能看到动态壳、加载页或登录提示。",
        "adapter_can_open_but_cannot_extract": "当前适配器只能打开页面，不能直接产出结构化可见正文。",
        "host_browser_not_available": "宿主 Agent 没有可用浏览器/Computer Use/WebView 提取能力。",
        "target_url_mismatch": "浏览器实际页面不是任务目标 URL 或同一候选页。",
        "private_area_detected": "页面进入私信、订单、后台、账号设置、支付或其他个人区域；只有目标页和用途被单独明确授权时才可读取可见内容。",
        "credential_authorization_required": "仅靠可见页仍不足，下一步需要单独凭据授权；凭据材料不得进入 browser-visible payload。",
        "cookie_authorization_required": "仅靠可见页仍不足，下一步需要单独 Cookie 授权；Cookie 不属于 browser-visible payload。",
        "selector_or_locale_mismatch": "选择器、aria-label、placeholder、title 或可见文案因语言/DOM 漂移失效。",
        "insufficient_visible_items": "列表/评论/搜索页采集条数低于请求数量，且未给出充分 partial_reason。",
        "fixed_sleep_readiness_untrusted": "仅靠固定等待判断页面就绪，缺少正文、结果数、DOM 或网络就绪信号。",
        "session_drift": "多步补证过程中 tab、账号、URL 或目标页发生漂移，需要重新确认会话边界。",
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
        f"- 推荐适配器: {plan.get('recommended_adapter') or '-'}",
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
    template = plan.get("platform_template") or {}
    if template:
        lines.append("- 平台模板:")
        lines.append(f"  - 名称: {template.get('name', '')}")
        lines.append("  - 字段: " + ", ".join(template.get("extract_fields") or []))
    commands = plan.get("recommended_commands") or []
    if commands:
        lines.append("- 推荐命令:")
        lines.extend(f"  - `{item}`" for item in commands)
    failures = plan.get("failure_taxonomy") or {}
    if failures:
        lines.append("- 失败原因枚举: " + ", ".join(list(failures.keys())[:8]))
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
    private_account_evidence: bool = False,
) -> dict[str, Any]:
    """Metadata used when a user-authorized visible browser note is archived."""

    return {
        "schema_version": "browser_visible_v2",
        "source_mode": "browser_visible",
        "browser_assisted": True,
        "visible_page_only": True,
        "private_account_evidence": bool(private_account_evidence),
        "user_authorized": True,
        "session_dependent": True,
        "reproducibility": "session_dependent",
        "evidence_role": "user_visible_sample",
        "platform": platform or platform_hint(url),
        "platform_template": browser_assist_platform_template(platform or platform_hint(url)),
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
            "private_account_visible_page": "allowed_only_for_target_page_after_explicit_authorization",
        },
    }


def browser_visible_quality_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Assess whether a user-authorized visible-page payload is usable."""

    url = str(payload.get("url") or "").strip()
    title = str(payload.get("title") or "").strip()
    visible_text = str(payload.get("visible_text") or payload.get("text") or payload.get("content") or "").strip()
    skipped_reason = str(payload.get("skipped_reason") or "").strip()
    source_mode = str(payload.get("source_mode") or "browser_visible").strip()
    browser_assisted = bool(payload.get("browser_assisted", True))
    visible_page_only = bool(payload.get("visible_page_only", True))
    user_authorized = bool(payload.get("user_authorized", True))
    private_account_evidence = bool(payload.get("private_account_evidence", False))
    sensitive_keys = sorted(_sensitive_keys_in_payload(payload))
    warnings: list[str] = []
    if not url:
        warnings.append("missing_url")
    if not title:
        warnings.append("missing_title")
    if not visible_text and not skipped_reason:
        warnings.append("missing_visible_text")
    if source_mode != "browser_visible":
        warnings.append("invalid_source_mode")
    if not browser_assisted:
        warnings.append("missing_browser_assisted_boundary")
    if not visible_page_only:
        warnings.append("visible_page_only_not_confirmed")
    if not user_authorized:
        warnings.append("user_authorization_not_confirmed")
    if private_account_evidence and not user_authorized:
        warnings.append("private_account_authorization_not_confirmed")
    if 0 < len(visible_text) < 80:
        warnings.append("thin_visible_text")
    if sensitive_keys:
        warnings.append("contains_forbidden_payload_keys")
    usable = bool(url and visible_text and not sensitive_keys and source_mode == "browser_visible" and browser_assisted and visible_page_only and user_authorized)
    return {
        "usable": usable,
        "status": "pass" if usable and len(visible_text) >= 80 else ("skip" if skipped_reason and not visible_text else "warn"),
        "chars": len(visible_text),
        "warnings": warnings,
        "sensitive_keys": sensitive_keys,
        "skipped_reason": skipped_reason,
        "boundary": "browser_visible_user_authorized",
        "private_account_evidence": private_account_evidence,
        "schema_version": "browser_visible_v2",
    }


def normalize_browser_visible_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize host-browser output before archive ingestion."""

    if not isinstance(payload, dict):
        raise ValueError("browser visible payload must be an object")
    sensitive_keys = _sensitive_keys_in_payload(payload)
    if sensitive_keys:
        raise ValueError("browser visible payload contains forbidden keys: " + ", ".join(sorted(sensitive_keys)))
    visible_text = str(payload.get("visible_text") or payload.get("text") or payload.get("content") or "").strip()
    inferred_platform = infer_social_platform(str(payload.get("platform") or payload.get("url") or "")) or str(payload.get("platform") or "").strip()
    social_payload = normalize_social_evidence_payload(payload, platform=inferred_platform) if inferred_platform else {}
    return {
        "url": str(payload.get("url") or "").strip(),
        "title": str(payload.get("title") or "").strip(),
        "visible_text": visible_text,
        "platform": inferred_platform,
        "author": str(payload.get("author") or "").strip(),
        "published_at": str(payload.get("published_at") or "").strip(),
        "captured_at": payload.get("captured_at"),
        "visible_context": str(payload.get("visible_context") or "").strip(),
        "skipped_reason": str(payload.get("skipped_reason") or "").strip(),
        "content_type": str(social_payload.get("content_type") or payload.get("content_type") or "").strip(),
        "content_id": str(social_payload.get("content_id") or payload.get("content_id") or "").strip(),
        "engagement_summary": str(payload.get("engagement_summary") or "").strip(),
        "visible_comment_summary": str(payload.get("visible_comment_summary") or "").strip(),
        "creator_profile_summary": str(social_payload.get("creator_profile_summary") or payload.get("creator_profile_summary") or "").strip(),
        "creator_profile": dict(social_payload.get("creator_profile") or {}),
        "metric_snapshots": list(social_payload.get("metric_snapshots") or []),
        "comment_samples": list(social_payload.get("comment_samples") or []),
        "requested_min_items": int(payload.get("requested_min_items") or 0),
        "collected_count": int(payload.get("collected_count") or 0),
        "partial_reason": str(payload.get("partial_reason") or "").strip(),
        "question": str(payload.get("question") or "").strip(),
        "account": str(payload.get("account") or "").strip(),
        "source_mode": str(payload.get("source_mode") or "browser_visible").strip(),
        "browser_assisted": bool(payload.get("browser_assisted", True)),
        "user_authorized": bool(payload.get("user_authorized", True)),
        "visible_page_only": bool(payload.get("visible_page_only", True)),
        "private_account_evidence": bool(payload.get("private_account_evidence", False)),
        "session_dependent": bool(payload.get("session_dependent", True)),
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


def _adapter_capabilities(
    adapter_id: str,
    spec: dict[str, Any],
    *,
    platform_supported: bool,
    available: bool,
    executable_ready: bool | None = None,
) -> dict[str, Any]:
    can_open = bool(spec.get("can_open"))
    can_extract = bool(spec.get("can_extract"))
    can_reuse_existing_session = bool(spec.get("can_reuse_existing_session"))
    cookie_flow_available = adapter_id == "xhs-cli"
    native_visible_adapters = {"host-browser", "openguanlan", "openguanlan-bridge", "open-cli", "xhs-cli"}
    can_wait_dynamic_ready = bool(can_extract and adapter_id in native_visible_adapters)
    can_scroll_until_min_items = bool(can_extract and adapter_id in native_visible_adapters)
    can_read_private_account_visible_pages = bool(can_extract and adapter_id in {"host-browser", "openguanlan", "openguanlan-bridge", "open-cli"})
    executable_ok = available if executable_ready is None else executable_ready
    capability_layer = "extractor" if can_extract else "opener" if can_open else "planner"
    score = 0
    if platform_supported:
        score += 20
    if available:
        score += 20
    if can_open and (adapter_id in {"host-browser", "openguanlan"} or executable_ok):
        score += 20
    if can_extract:
        score += 25
    if can_reuse_existing_session:
        score += 10
    if cookie_flow_available:
        score += 5
    risk_level = str(spec.get("risk_level") or "medium")
    risk_score = {"low": 1, "medium": 2, "high": 3}.get(risk_level, 2)
    return {
        "adapter_id": adapter_id,
        "capability_layer": capability_layer,
        "capability_score": min(score, 100),
        "risk_level": risk_level,
        "risk_score": risk_score,
        "can_open": can_open,
        "can_extract_visible_text": can_extract,
        "can_reuse_existing_session": can_reuse_existing_session,
        "can_wait_dynamic_ready": can_wait_dynamic_ready,
        "can_scroll_until_min_items": can_scroll_until_min_items,
        "can_read_private_account_visible_pages": can_read_private_account_visible_pages,
        "credential_material_access_allowed": False,
        "cookie_flow_available": cookie_flow_available,
        "platform_supported": platform_supported,
        "available": available,
        "executable_ready": executable_ok,
    }


def _resolve_adapter_executable(adapter_id: str, executable: str = "") -> str:
    if adapter_id in {"host-browser", "openguanlan"}:
        return ""
    if adapter_id == "open-cli":
        for candidate in ["opencli", executable, "open", "xdg-open", "start"]:
            if not candidate:
                continue
            found = shutil.which(candidate)
            if found:
                return found
        return ""
    if executable:
        return shutil.which(executable) or ""
    return ""


def _opencli_browser_profile(*, command_template: str = "") -> dict[str, Any]:
    template = str(command_template or os.environ.get("GUANLAN_BROWSER_ASSIST_OPEN_CLI_COMMAND") or "").strip()
    opencli_path = shutil.which("opencli") or ""
    template_uses_opencli = _command_template_uses_opencli(template)
    browser_bridge_available = bool(opencli_path or template_uses_opencli)
    return {
        "browser_bridge_available": browser_bridge_available,
        "opencli_path": opencli_path,
        "template_uses_opencli": template_uses_opencli,
        "template_outputs_payload": _open_cli_command_supports_payload(template),
        "mode": "opencli_browser_bridge" if browser_bridge_available else "system_open",
        "read_only_commands": [
            "opencli browser --session guanlan-visible open {url}",
            "opencli browser --session guanlan-visible wait text <ready-text> --timeout 90000",
            "opencli browser --session guanlan-visible state",
            "opencli browser --session guanlan-visible get text body",
        ],
        "forbidden_opencli_patterns": [
            "commands that export cookies/tokens/storage/profile data",
            "write commands such as click-to-submit, fill, upload, post, like, follow, purchase",
        ],
    }


def _openguanlan_browser_profile(*, command_template: str = "") -> dict[str, Any]:
    template = str(command_template or os.environ.get("GUANLAN_BROWSER_ASSIST_OPENGUANLAN_COMMAND") or "").strip()
    openguanlan_path = shutil.which("openguanlan") or ""
    extension_path = Path(__file__).resolve().parent / "browser_bridge" / "extension"
    return {
        "primary_layer_available": True,
        "primary_layer_requires_extension": False,
        "optional_bridge_available": bool(openguanlan_path or template),
        "native_bridge_available": bool(openguanlan_path or template),
        "openguanlan_path": openguanlan_path,
        "extension_path": str(extension_path),
        "extension_manifest_exists": (extension_path / "manifest.json").exists(),
        "template_configured": bool(template),
        "mode": "openguanlan_browser_assist_layer",
        "optional_bridge_mode": "openguanlan_native_bridge" if openguanlan_path or template else "packaged_needs_install_entrypoint",
        "template_outputs_payload": bool(template and _open_cli_command_supports_payload(template)),
    }


def _opencli_setup_guidance(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    opencli_ready = bool((profile or {}).get("browser_bridge_available"))
    return {
        "needed": not opencli_ready,
        "cli_install_command": f"npm install -g {OPENCLI_NPM_PACKAGE}@latest",
        "extension_url": OPENCLI_CHROME_WEBSTORE_URL,
        "manual_release_zip_url": OPENCLI_RELEASES_URL,
        "verify_commands": [
            "opencli doctor",
            "opencli profile list",
            "guanlan browser-assist adapters --check --json",
        ],
        "guanlan_command": "guanlan browser-assist setup-opencli --json",
        "execute_command": "guanlan browser-assist setup-opencli --execute --json",
        "boundary": "CLI 可由用户明确安装；Chrome 扩展需要用户在浏览器中手动确认；观澜不读取凭据材料。",
    }


def _openguanlan_setup_guidance() -> dict[str, Any]:
    return {
        "guanlan_command": "guanlan browser-assist setup-openguanlan --json",
        "primary_command": "guanlan browser-assist run \"URL\" --adapter openguanlan --json",
        "optional_bridge_adapter": "openguanlan-bridge",
        "doctor_command": "openguanlan doctor --json",
        "daemon_command": "openguanlan daemon",
        "extension_path_command": "openguanlan extension path",
        "package_command": "scripts/build_openguanlan_extension.sh",
        "boundary": "OpenGuanlan is the Guanlan browser-assist layer; extension/daemon bridge is optional.",
        "default_adapter": "openguanlan",
    }


def _node_version() -> str:
    node = shutil.which("node")
    if not node:
        return ""
    try:
        completed = subprocess.run(
            [node, "--version"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    return (completed.stdout or completed.stderr or "").strip()


def _command_template_uses_opencli(template: str = "") -> bool:
    if not template:
        return False
    try:
        first = shlex.split(template)[0]
    except Exception:
        return "opencli" in template
    return os.path.basename(first).lower() == "opencli"


def _open_cli_command_supports_payload(command_template: str = "") -> bool:
    template = str(command_template or os.environ.get("GUANLAN_BROWSER_ASSIST_OPEN_CLI_COMMAND") or "").strip().lower()
    if not template:
        return False
    return any(marker in template for marker in ["{output}", "--output", "--jsonl", "jsonl", "browser-visible", "browser_visible", "guanlan-visible"])


def _opencli_doctor_command(profile: dict[str, Any] | None = None) -> list[str]:
    opencli_path = str((profile or {}).get("opencli_path") or shutil.which("opencli") or "")
    if opencli_path:
        return [opencli_path, "doctor"]
    return []


def _openguanlan_doctor_command() -> list[str]:
    executable = shutil.which("openguanlan") or ""
    if executable:
        return [executable, "doctor"]
    return []


def _openguanlan_command(url: str, *, command_template: str = "", output_path: str = "") -> list[str]:
    template = str(command_template or os.environ.get("GUANLAN_BROWSER_ASSIST_OPENGUANLAN_COMMAND") or "").strip()
    if template:
        return _render_command_template(template, url=url, output=output_path)
    executable = shutil.which("openguanlan") or ""
    if executable:
        return [executable, "read-visible", url, "--output", output_path or "-"]
    return []


def _open_cli_command(url: str, *, command_template: str = "", output_path: str = "") -> list[str]:
    template = str(command_template or os.environ.get("GUANLAN_BROWSER_ASSIST_OPEN_CLI_COMMAND") or "").strip()
    if template:
        return _render_command_template(template, url=url, output=output_path)
    opencli_path = shutil.which("opencli") or ""
    if opencli_path:
        return [opencli_path, "browser", "--session", "guanlan-visible", "open", url]
    executable = _resolve_adapter_executable("open-cli", "open")
    if executable:
        return [executable, url]
    return []


def _browser_use_doctor_command() -> list[str]:
    executable = _resolve_adapter_executable("browser-use", "browser-use")
    if executable:
        return [executable, "doctor"]
    return []


def _browser_use_open_command(url: str, *, command_template: str = "", output_path: str = "") -> list[str]:
    template = str(command_template or os.environ.get("GUANLAN_BROWSER_ASSIST_BROWSER_USE_COMMAND") or "").strip()
    if template:
        return _render_command_template(template, url=url, output=output_path)
    executable = _resolve_adapter_executable("browser-use", "browser-use")
    if executable:
        return [executable, "open", url]
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

    social_platform = infer_social_platform(url)
    if social_platform:
        return social_platform
    host = urlparse(str(url or "")).netloc.lower()
    for suffix, label in PLATFORM_HINTS.items():
        if host == suffix or host.endswith("." + suffix):
            return label
    return ""


def _cookie_access_policy(platform: str = "") -> dict[str, Any]:
    platform_label = platform or "target_platform"
    return {
        "default": "forbidden_for_visible_page_task",
        "existing_browser_session_context": "current browser session may keep the target page logged in or warm; Cookie/history artifacts still stay outside payload by default",
        "can_escalate": "yes_but_only_after_separate_explicit_credential_authorization",
        "required_before_cookie_access": [
            "说明需要哪个平台的 Cookie",
            "说明为什么仅靠公开读取和浏览器可见页仍不足",
            "说明 Cookie 只用于当前目标平台的只读检索/读取",
            "说明 Cookie/凭据材料不会进入 browser-visible payload 或 archive 正文",
            "说明不会读取密码、Token、钥匙串、无关私域页面或无关个人资料",
            "获得用户明确同意，例如：我同意读取小红书 Cookie 用于这次只读检索",
        ],
        "authorization_prompt": (
            f"公开读取和浏览器可见页仍不足。是否允许我读取 {platform_label} 的 Cookie，"
            "仅用于本次只读检索/读取目标页面？Cookie 不会进入可见页 payload 或 archive 正文；我不会读取密码、Token、钥匙串、无关私域页面或无关个人资料，"
            "也不会执行点赞、评论、关注、发帖、私信、下单或提交表单。"
        ),
        "preferred_flow": "use Guanlan's explicit auth/config command or a user-approved host credential connector; do not ad-hoc scrape browser profiles.",
    }


def _sensitive_keys_in_payload(payload: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    stack: list[tuple[str, Any]] = [("", payload)]
    while stack:
        prefix, current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                normalized = str(key or "").strip().lower().replace("-", "_")
                full_key = f"{prefix}.{key}" if prefix else str(key)
                if normalized in SENSITIVE_PAYLOAD_KEYS:
                    found.add(full_key)
                stack.append((full_key, value))
        elif isinstance(current, list):
            for index, value in enumerate(current):
                list_key = f"{prefix}[{index}]" if prefix else f"[{index}]"
                stack.append((list_key, value))
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
