# -*- coding: utf-8 -*-
"""Small error classification helpers for user-facing diagnostics."""

from __future__ import annotations

import json
import socket
import subprocess
import urllib.error

NETWORK_TIMEOUT = "network_timeout"
NETWORK_ERROR = "network_error"
BLOCKED = "blocked"
PARSE_ERROR = "parse_error"
CONTRACT_ERROR = "contract_error"
UPSTREAM_ERROR = "upstream_error"
UNKNOWN_ERROR = "unknown_error"

_BLOCKED_MARKERS = (
    "captcha",
    "验证码",
    "安全验证",
    "access denied",
    "forbidden",
    "blocked",
    "verify you are human",
    "访问受限",
)


def classify_exception(exc: BaseException) -> str:
    """Classify an exception without leaking sensitive values."""

    if isinstance(exc, (TimeoutError, socket.timeout, subprocess.TimeoutExpired)):
        return NETWORK_TIMEOUT
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in {401, 403, 429, 451}:
            return BLOCKED
        if 500 <= exc.code <= 599:
            return UPSTREAM_ERROR
        return NETWORK_ERROR
    if isinstance(exc, urllib.error.URLError):
        reason = str(getattr(exc, "reason", "") or exc).lower()
        if "timed out" in reason or "timeout" in reason:
            return NETWORK_TIMEOUT
        return NETWORK_ERROR
    if isinstance(exc, (json.JSONDecodeError, ValueError, TypeError)):
        return PARSE_ERROR
    text = str(exc).lower()
    if any(marker in text for marker in _BLOCKED_MARKERS):
        return BLOCKED
    if "timed out" in text or "timeout" in text:
        return NETWORK_TIMEOUT
    if "contract" in text or "schema" in text:
        return CONTRACT_ERROR
    return UNKNOWN_ERROR


def error_diagnostics(exc: BaseException) -> dict[str, str]:
    """Return a compact diagnostic payload suitable for JSON surfaces."""

    category = classify_exception(exc)
    return {
        "error_type": category,
        "message": str(exc),
    }


_FRIENDLY_MESSAGES: dict[str, str] = {         #中文字典补充
    NETWORK_TIMEOUT: "网络连接超时，请检查网络或稍后重试",
    NETWORK_ERROR: "网络连接失败，请检查网络状态",
    BLOCKED: "请求被目标网站拦截（可能触发了验证码或访问限制），请稍后再试",
    PARSE_ERROR: "页面内容解析失败，目标页面格式可能已变更",
    CONTRACT_ERROR: "返回数据格式异常，请联系开发者",
    UPSTREAM_ERROR: "上游服务异常，请稍后再试",
    UNKNOWN_ERROR: "发生未知错误，请查看详细日志",
}

#error友好消息&GET_RET
def user_friendly_message(exc: BaseException) -> str:
    category = classify_exception(exc)
    return _FRIENDLY_MESSAGES.get(category, _FRIENDLY_MESSAGES[UNKNOWN_ERROR])