# -*- coding: utf-8 -*-
"""Shared, low-impact public-network execution diagnostics.

This module is deliberately small.  It gives every public HTTP adapter the
same failure vocabulary without changing its timeout, retry, cache, or
fallback policy.  Individual adapters retain ownership of those choices so a
new shared layer cannot quietly increase latency or error rates.
"""

from __future__ import annotations

import ssl
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from guanlan.errors import error_diagnostics

T = TypeVar("T")

NETWORK_DIAGNOSTIC_SCHEMA_VERSION = "network_diagnostic_v1"


@dataclass(frozen=True)
class NetworkExecutionResult:
    """Outcome envelope for one adapter-owned public network operation."""

    value: Any = None
    error: BaseException | None = None
    diagnostic: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class PublicUrlPayload:
    """Response bytes plus the small charset hint adapters already relied on."""

    body: bytes
    charset: str = ""


def diagnose_network_error(
    exc: BaseException,
    *,
    source: str,
    operation: str,
) -> dict[str, Any]:
    """Return a safe, stable network diagnostic without raw exception text."""

    diagnostics = error_diagnostics(exc)
    category = str(diagnostics["error_type"])
    return {
        "schema_version": NETWORK_DIAGNOSTIC_SCHEMA_VERSION,
        "source": str(source or "public_source"),
        "operation": str(operation or "request"),
        "status": "error",
        "category": category,
        "retryable": bool(diagnostics["retryable"]),
        "safe_message": str(diagnostics["message"]),
        "next_decision": str(diagnostics["next_decision"]),
        "evidence_boundary": str(diagnostics["evidence_boundary"]),
    }


def diagnostic_label(diagnostic: dict[str, Any] | None, *, fallback: str = "network_error") -> str:
    """Return a compact trace-safe label for legacy list-style error fields."""

    category = str((diagnostic or {}).get("category") or fallback)
    return category or fallback


def run_public_operation(
    operation: Callable[[], T],
    *,
    source: str,
    operation_name: str,
) -> NetworkExecutionResult:
    """Run one adapter operation once and capture a safe failure envelope.

    The helper never retries.  Retry and stale-cache decisions stay local to
    the calling Adapter, which preserves existing latency and reliability
    behavior while making failures comparable across surfaces.
    """

    try:
        return NetworkExecutionResult(value=operation())
    except Exception as exc:  # exact public-network failures vary by platform.
        return NetworkExecutionResult(
            error=exc,
            diagnostic=diagnose_network_error(exc, source=source, operation=operation_name),
        )


def read_url_payload(
    request: urllib.request.Request,
    *,
    timeout: int | float,
    ssl_context: ssl.SSLContext | None = None,
    max_bytes: int | None = None,
    public_url_policy: bool = False,
) -> PublicUrlPayload:
    """Read one public URL while retaining compatibility with simple test fakes.

    ``max_bytes`` is adapter-owned: discovery callers that previously bounded a
    response can retain that memory and latency boundary after adopting the
    shared execution layer.
    """

    def _payload(response: Any) -> PublicUrlPayload:
        if public_url_policy:
            from guanlan.url_policy import validate_public_response
            validate_public_response(str(request.full_url), response)
        headers = getattr(response, "headers", None)
        get_charset = getattr(headers, "get_content_charset", None)
        charset = str(get_charset() or "") if callable(get_charset) else ""
        size = max(int(max_bytes or 0), 0)
        return PublicUrlPayload(body=response.read(size) if size else response.read(), charset=charset)

    if ssl_context is None:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - caller owns public URL policy.
            return _payload(response)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context) as response:  # nosec B310 - caller owns public URL policy.
            return _payload(response)
    except TypeError:
        # Some host integrations and deterministic test fakes do not accept
        # ``context``. This mirrors the prior adapter behavior exactly.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - caller owns public URL policy.
            return _payload(response)


def read_url_bytes(
    request: urllib.request.Request,
    *,
    timeout: int | float,
    ssl_context: ssl.SSLContext | None = None,
    max_bytes: int | None = None,
) -> bytes:
    """Return only bytes for adapters that do not need response metadata."""

    return read_url_payload(request, timeout=timeout, ssl_context=ssl_context, max_bytes=max_bytes).body
