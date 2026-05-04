# -*- coding: utf-8 -*-
"""Browser-assisted evidence planning for Guanlan.

This module only describes a read-only, user-authorized handoff for host
agents that already have a browser. It never reads browser state, cookies, or
local credential stores.
"""

from __future__ import annotations

import json
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
