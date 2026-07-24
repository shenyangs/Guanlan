# -*- coding: utf-8 -*-
"""Small error classification helpers for user-facing diagnostics."""

from __future__ import annotations

import json
import re
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

_SAFE_MESSAGES = {
    NETWORK_TIMEOUT: "公开来源响应较慢，当前证据包还需要补证。",
    NETWORK_ERROR: "公开来源暂时不可稳定读取，当前证据包还需要补证。",
    BLOCKED: "目标来源当前有公开访问限制，建议按诊断路线补读。",
    PARSE_ERROR: "请求或上游返回未满足当前读取契约，需要调整输入或更换来源。",
    CONTRACT_ERROR: "请求未满足当前工具契约，需要检查参数后再继续。",
    UPSTREAM_ERROR: "上游服务暂时不可用，建议保留现有证据并稍后补证。",
    UNKNOWN_ERROR: "当前证据链未能完整执行，需要按建议路线补证。",
}

_TOKEN_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(\b(?:token|api[_-]?key|secret|password|passwd|cookie|session(?:id)?|authorization)\b\s*[=:]\s*)[^\s,;&]+"),
    re.compile(r"(?i)([?&](?:token|api[_-]?key|key|secret|signature|sig|authorization)=)[^&#\s]+"),
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


def redact_sensitive_text(text: str) -> str:
    """Remove credential-like fragments from diagnostics before any presentation."""

    redacted = str(text or "")
    for pattern in _TOKEN_PATTERNS:
        redacted = pattern.sub(r"\1[redacted]", redacted)
    return redacted


def error_diagnostics(exc: BaseException) -> dict[str, object]:
    """Return stable, non-sensitive diagnostics for every public surface."""

    category = classify_exception(exc)
    retryable = category in {NETWORK_TIMEOUT, NETWORK_ERROR, BLOCKED, UPSTREAM_ERROR}
    return {
        "error_type": category,
        "message": _SAFE_MESSAGES[category],
        "retryable": retryable,
        "next_decision": "repair" if retryable else "stop",
        "evidence_boundary": "当前输出不能单独作为完整事实依据。",
    }


def format_user_error(exc: BaseException) -> str:
    """Render the same bounded diagnostic for CLI and MCP text surfaces."""

    diagnostics = error_diagnostics(exc)
    return f"{diagnostics['message']}（{diagnostics['error_type']}）"
