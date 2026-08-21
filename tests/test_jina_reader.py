# -*- coding: utf-8 -*-
"""Contract tests for Guanlan's bounded Jina Reader integration."""

from __future__ import annotations

import urllib.error

import pytest

from guanlan.jina_reader import (
    diagnose_jina_error,
    normalize_jina_options,
    should_attempt_safe_repair,
)


def test_jina_options_preserve_legacy_defaults():
    options = normalize_jina_options()

    assert options.request_headers() == {"Accept": "text/plain"}
    assert options.contract()["wire_defaults_preserved"] is True
    assert options.contract()["mode"] == "compatibility"


def test_jina_options_reject_unsafe_or_unknown_controls():
    with pytest.raises(ValueError, match="jina_engine"):
        normalize_jina_options(engine="remote-browser")
    with pytest.raises(ValueError, match="jina_format"):
        normalize_jina_options(response_format="markdown+frontmatter")
    with pytest.raises(ValueError, match="jina_wait_for"):
        normalize_jina_options(wait_for="article\nX-Set-Cookie: secret")


def test_jina_error_diagnosis_distinguishes_rate_limit_and_quota():
    rate_limited = urllib.error.HTTPError(
        "https://r.jina.ai/https://example.com",
        429,
        "Too Many Requests",
        {"Retry-After": "12"},
        None,
    )
    quota = urllib.error.HTTPError(
        "https://r.jina.ai/https://example.com",
        402,
        "Payment Required",
        {},
        None,
    )

    rate_diagnostic = diagnose_jina_error(rate_limited)
    quota_diagnostic = diagnose_jina_error(quota)

    assert rate_diagnostic["category"] == "rate_limited"
    assert rate_diagnostic["retryable"] is True
    assert rate_diagnostic["retry_after_seconds"] == 12
    assert quota_diagnostic["category"] == "quota_exhausted"
    assert quota_diagnostic["retryable"] is False


def test_no_cache_remains_compatible_with_bounded_safe_repair():
    options = normalize_jina_options(no_cache=True)

    assert should_attempt_safe_repair(
        "https://example.com/app",
        jina_text="Please enable JavaScript to continue",
        direct_text='<main id="__next">内容加载中</main>',
        options=options,
    )


def test_safe_repair_requires_dynamic_shell_evidence_from_both_paths():
    options = normalize_jina_options()

    assert not should_attempt_safe_repair(
        "https://example.com/app",
        jina_text="Please enable JavaScript to continue",
        direct_text="A short but ordinary server-rendered page",
        options=options,
    )
