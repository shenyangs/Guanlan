# -*- coding: utf-8 -*-
"""Regression tests for shared public-network execution diagnostics."""

from guanlan.network_execution import diagnostic_label, read_url_payload, run_public_operation


def test_network_operation_keeps_original_error_but_exposes_safe_diagnostic():
    def fail():
        raise TimeoutError("https://example.com/?token=secret timed out")

    result = run_public_operation(fail, source="rss", operation_name="fetch")

    assert result.ok is False
    assert isinstance(result.error, TimeoutError)
    assert result.diagnostic["category"] == "network_timeout"
    assert "secret" not in result.diagnostic["safe_message"]
    assert diagnostic_label(result.diagnostic) == "network_timeout"


def test_public_url_payload_preserves_adapter_byte_cap(monkeypatch):
    class Headers:
        def get_content_charset(self):
            return "utf-8"

    class Response:
        headers = Headers()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size=None):
            assert size == 4
            return b"abcd"

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())

    payload = read_url_payload(object(), timeout=2, max_bytes=4)

    assert payload.body == b"abcd"
    assert payload.charset == "utf-8"
