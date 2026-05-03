# -*- coding: utf-8 -*-
"""Error classification smoke tests."""

from __future__ import annotations

import json
import subprocess
import urllib.error

from guanlan.errors import BLOCKED, NETWORK_ERROR, NETWORK_TIMEOUT, PARSE_ERROR, classify_exception


def test_classify_timeout_and_url_errors():
    assert classify_exception(TimeoutError("timed out")) == NETWORK_TIMEOUT
    assert classify_exception(subprocess.TimeoutExpired("cmd", 1)) == NETWORK_TIMEOUT
    assert classify_exception(urllib.error.URLError("network unreachable")) == NETWORK_ERROR


def test_classify_blocked_and_parse_errors():
    assert classify_exception(urllib.error.HTTPError("https://x", 403, "Forbidden", {}, None)) == BLOCKED
    assert classify_exception(json.JSONDecodeError("bad", "{", 0)) == PARSE_ERROR
    assert classify_exception(RuntimeError("captcha required")) == BLOCKED
