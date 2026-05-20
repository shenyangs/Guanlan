# -*- coding: utf-8 -*-
"""Shared administrative CLI helpers."""

import os
import sys
import time


def _print_sensitive_access_notice(action: str, browser: str | None = None):
    """Print a reassuring notice before actions that may trigger Keychain prompts."""
    target = f"{browser} 浏览器 Cookie" if browser else "认证/登录态"
    print()
    print("观澜安全提示")
    print("=" * 40)
    print(f"即将进行：{action}")
    print(f"可能出现 macOS 钥匙串弹窗，用于允许读取本机的 {target}。")
    print("这一步不会读取你的系统登录密码，也不会上传任何 Cookie、Token 或个人数据。")
    print("观澜只会在本机提取相关平台的登录态，用于你明确授权的搜索/读取能力。")
    print("如果你不想授权，可以在弹窗中选择拒绝；观澜会继续使用公开搜索、网页阅读和热榜能力。")
    print("=" * 40)
    print()
    sys.stdout.flush()
    try:
        delay = float(os.environ.get("GUANLAN_NOTICE_DELAY", "1.5"))
    except ValueError:
        delay = 1.5
    if delay > 0:
        time.sleep(delay)

def _parse_twitter_cookie_input(value: str):
    """Parse Twitter cookie input from either separate values or a cookie header."""
    auth_token = None
    ct0 = None

    if "auth_token=" in value and "ct0=" in value:
        # Full cookie string — parse it.
        for part in value.replace(";", " ").split():
            if part.startswith("auth_token="):
                auth_token = part.split("=", 1)[1]
            elif part.startswith("ct0="):
                ct0 = part.split("=", 1)[1]
    elif len(value.split()) == 2 and "=" not in value:
        # Two separate values: AUTH_TOKEN CT0.
        parts = value.split()
        auth_token = parts[0]
        ct0 = parts[1]

    return auth_token, ct0

def _classify_update_error(exc):
    """Classify update-check errors for user-friendly diagnostics."""
    import requests

    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        msg = str(exc).lower()
        dns_markers = [
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname",
            "getaddrinfo failed",
            "name resolution",
            "dns",
        ]
        if any(marker in msg for marker in dns_markers):
            return "dns"
        return "connection"
    if isinstance(exc, requests.exceptions.HTTPError):
        return "http"
    return "unknown"

def _update_error_text(kind):
    """Map internal error kinds to user-facing text."""
    mapping = {
        "timeout": "网络超时",
        "dns": "DNS 解析失败",
        "rate_limit": "GitHub API 速率限制",
        "connection": "网络连接失败",
        "server_error": "GitHub 服务暂时不可用",
        "http": "HTTP 请求失败",
        "unknown": "未知网络错误",
    }
    return mapping.get(kind, "请求失败")

def _classify_github_response_error(resp):
    """Classify non-200 GitHub responses that merit special handling."""
    if resp is None:
        return "unknown"
    if resp.status_code == 429:
        return "rate_limit"
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "")
        if remaining == "0":
            return "rate_limit"
        try:
            message = resp.json().get("message", "").lower()
            if "rate limit" in message:
                return "rate_limit"
        except Exception:
            pass
    if 500 <= resp.status_code < 600:
        return "server_error"
    return None

def _github_get_with_retry(url, timeout=10, retries=3, sleeper=time.sleep):
    """GET GitHub API with retry/backoff and basic error classification."""
    import requests

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            if attempt >= retries:
                return None, _classify_update_error(exc), attempt
            sleeper(2 ** (attempt - 1))
            continue

        err_kind = _classify_github_response_error(resp)
        if err_kind in ("rate_limit", "server_error"):
            if attempt >= retries:
                return None, err_kind, attempt
            delay = 2 ** (attempt - 1)
            retry_after = resp.headers.get("Retry-After")
            if err_kind == "rate_limit" and retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except Exception:
                    pass
            sleeper(delay)
            continue

        return resp, None, attempt

    return None, "unknown", retries

def _print_update_notice_if_available(printer=print) -> None:
    """Print a best-effort update notice without affecting command success."""
    try:
        from guanlan import __version__
        from guanlan.update_check import format_update_notice, get_update_info

        info = get_update_info(__version__)
        if info:
            printer("")
            printer(format_update_notice(info))
    except Exception:
        return

def _should_show_background_update_notice(args) -> bool:
    command = str(getattr(args, "command", "") or "")
    return command in {
        "search",
        "read",
        "research",
        "hotnews",
        "route",
        "compare",
        "timeline",
        "dossier",
        "prompt",
        "context",
        "pulse",
        "feeds",
        "status",
    }

def _print_background_update_notice_if_available(args) -> None:
    """Print a compact stderr-only update notice for routine agent commands."""
    if not _should_show_background_update_notice(args):
        return
    try:
        from guanlan import __version__
        from guanlan.update_check import cached_update_info, format_compact_update_notice

        info = cached_update_info(__version__, timeout=0.8)
        if not info:
            return
        print("", file=sys.stderr)
        print(format_compact_update_notice(info), file=sys.stderr)
    except Exception:
        return

__all__ = ['_print_sensitive_access_notice', '_parse_twitter_cookie_input', '_classify_update_error', '_update_error_text', '_classify_github_response_error', '_github_get_with_retry', '_print_update_notice_if_available', '_should_show_background_update_notice', '_print_background_update_notice_if_available']
