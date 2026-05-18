# -*- coding: utf-8 -*-
"""Shared helpers for redacting Guanlan configuration and diagnostic output."""

from __future__ import annotations

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
