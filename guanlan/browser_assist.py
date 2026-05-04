# -*- coding: utf-8 -*-
"""Browser-assisted evidence planning for Guanlan.

This module only describes a read-only, user-authorized handoff for host
agents that already have a browser. It never reads browser state, cookies, or
local credential stores.
"""

from __future__ import annotations

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


def build_browser_assist_plan(
    url: str,
    *,
    page_type: str = "",
    signals: list[str] | None = None,
    candidate_urls: list[str] | None = None,
    force: bool = False,
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
        "公开搜索和普通网页读取目前不足。你当前浏览器可能能看到更多目标页面内容。"
        "是否允许我只读取浏览器中可见的目标页面内容，用于补充证据？"
        "我不会读取 Cookie、密码、钥匙串、私信、订单、后台信息，也不会点赞、评论、关注、发帖或发送消息。"
    )
    task = build_browser_assist_task(
        urls,
        platform=platform,
        evidence_role="user_visible_sample" if recommended else "",
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
        "browser_assist_task": task,
        "user_prompt": user_prompt,
        "boundaries": [
            "浏览器辅助补证必须由用户明确授权。",
            "只读取目标页面可见内容，不读取 Cookie、Token、钥匙串或浏览器数据库。",
            "不执行点赞、评论、关注、发帖、私信、下单、提交表单等写操作。",
            "补证内容可能依赖用户当前浏览器状态，应标注 browser_assisted 和 visible_page_only。",
        ],
        "archive_next_step": 'guanlan archive add-browser-note --url "URL" --text-file notes.md',
    }


def build_browser_assist_task(
    urls: list[str],
    *,
    platform: str = "",
    evidence_role: str = "user_visible_sample",
    max_pages: int = 3,
    max_chars_per_page: int = 3000,
) -> dict[str, Any]:
    """Build the host-browser task description for Agent platforms.

    The task is declarative: Guanlan asks the host Agent to read visible page
    content only after user permission. Guanlan itself does not automate the
    browser or access a browser session.
    """

    clean_urls = _unique(urls)
    return {
        "task_type": "open_and_read_visible_page",
        "status": "requires_user_approval",
        "read_only": True,
        "platform": platform,
        "evidence_role": evidence_role,
        "urls": clean_urls[: max(max_pages, 1)],
        "max_pages": max(max_pages, 1),
        "max_chars_per_page": max(max_chars_per_page, 1),
        "extract_fields": [
            "url",
            "title",
            "visible_text",
            "author",
            "published_at",
            "captured_at",
        ],
        "allowed_actions": ALLOWED_BROWSER_ASSIST_ACTIONS,
        "forbidden_actions": FORBIDDEN_BROWSER_ASSIST_ACTIONS,
        "must_not_access": [
            "cookies",
            "tokens",
            "keychain",
            "passwords",
            "private_messages",
            "orders",
            "admin_pages",
            "unrelated_personal_data",
        ],
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
        f"- 补证入库: `{plan.get('archive_next_step', '')}`",
    ]
    boundaries = plan.get("boundaries") or []
    if boundaries:
        lines.append("- 边界:")
        lines.extend(f"  - {item}" for item in boundaries)
    return "\n".join(lines)


def browser_visible_metadata(
    *,
    url: str,
    platform: str = "",
    author: str = "",
    published_at: str = "",
    captured_at: float | None = None,
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


def platform_hint(url: str) -> str:
    """Return a coarse platform label from URL host."""

    host = urlparse(str(url or "")).netloc.lower()
    for suffix, label in PLATFORM_HINTS.items():
        if host == suffix or host.endswith("." + suffix):
            return label
    return ""


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
