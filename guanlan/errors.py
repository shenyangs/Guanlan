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
