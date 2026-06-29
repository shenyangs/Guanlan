# -*- coding: utf-8 -*-
"""Shared helpers for redacting Guanlan configuration and diagnostic output."""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEY_TERMS: tuple[str, ...] = (
    "key",
    "token",
    "password",
    "passwd",
    "proxy",
    "cookie",
    "cookies",
    "session",
    "sess",
    "sessdata",
    "csrf",
    "auth",
    "ct0",
    "secret",
    "credential",
    "bearer",
)


def is_sensitive_key(key: str) -> bool:
    """Return True when a config key name likely contains credential material."""

    normalized = str(key or "").lower()
    return any(term in normalized for term in SENSITIVE_KEY_TERMS)


def mask_sensitive_value(value: Any) -> str | None:
    """Mask a sensitive config value using Guanlan's existing display style."""

    return f"{str(value)[:8]}..." if value else None


SENSITIVE_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(?:sk|gsk|hf)_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b((?:api[_-]?key|access[_-]?key|secret|token|password|passwd|cookie|session|auth)\s*[:=]\s*)[^\s;&]{6,}"),
    re.compile(r"(?i)([?&](?:token|key|api_key|access_key|secret|password|auth|cookie)=)[^&#\s]+"),
    re.compile(r"https?://([^/\s:@]+):([^@\s/]+)@"),
)


def contains_sensitive_text(value: Any) -> bool:
    """Return True when free text appears to contain credential material."""

    text = str(value or "")
    return any(pattern.search(text) for pattern in SENSITIVE_TEXT_PATTERNS)


def redact_sensitive_text(value: Any, *, marker: str = "[redacted]") -> str:
    """Redact common tokens, cookies, and URL credential fragments from diagnostics."""

    text = str(value or "")
    if not text:
        return ""
    redacted = text
    for pattern in SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(lambda match: _redact_match(match, marker=marker), redacted)
    return redacted


def _redact_match(match: re.Match[str], *, marker: str) -> str:
    if match.re.pattern.startswith("https?://"):
        return f"https://{marker}:{marker}@"
    if match.lastindex:
        prefix = match.group(1)
        if prefix and prefix.lower().startswith("bearer"):
            return f"{prefix}{marker}"
        return f"{prefix}{marker}"
    return marker
