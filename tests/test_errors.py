# -*- coding: utf-8 -*-
"""Error classification smoke tests."""

from __future__ import annotations

import json
import subprocess
import urllib.error

from guanlan.errors import (
    BLOCKED,
    NETWORK_ERROR,
    NETWORK_TIMEOUT,
    PARSE_ERROR,
    classify_exception,
    error_diagnostics,
    redact_sensitive_text,
)


def test_classify_timeout_and_url_errors():
    assert classify_exception(TimeoutError("timed out")) == NETWORK_TIMEOUT
    assert classify_exception(subprocess.TimeoutExpired("cmd", 1)) == NETWORK_TIMEOUT
    assert classify_exception(urllib.error.URLError("network unreachable")) == NETWORK_ERROR


def test_classify_blocked_and_parse_errors():
    assert classify_exception(urllib.error.HTTPError("https://x", 403, "Forbidden", {}, None)) == BLOCKED
    assert classify_exception(json.JSONDecodeError("bad", "{", 0)) == PARSE_ERROR
    assert classify_exception(RuntimeError("captcha required")) == BLOCKED


def test_public_error_diagnostics_do_not_expose_secret_like_text():
    exc = RuntimeError("request failed https://example.com/?token=abc123 Bearer top-secret")

    diagnostics = error_diagnostics(exc)

    assert diagnostics["error_type"]
    assert "abc123" not in str(diagnostics)
    assert "top-secret" not in str(diagnostics)
    assert diagnostics["next_decision"] == "stop"
    assert "abc123" not in redact_sensitive_text(str(exc))
    assert "top-secret" not in redact_sensitive_text(str(exc))
