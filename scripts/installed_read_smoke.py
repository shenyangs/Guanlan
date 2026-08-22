# -*- coding: utf-8 -*-
"""Deterministic installed-package smoke for MCP read under proxy fake-IP DNS."""

from __future__ import annotations

from unittest.mock import patch


class _Response:
    def __init__(self, url: str, body: str) -> None:
        self._url = url
        self._body = body.encode("utf-8")
        self.headers = {"content-type": "text/html; charset=utf-8"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self) -> str:
        return self._url

    def read(self) -> bytes:
        return self._body


def main() -> None:
    from guanlan.integrations.mcp_server import _run_tool
    from guanlan.url_policy import URLPolicyError, validate_public_url

    url = "https://mp.weixin.qq.com/s/installed-read-smoke"
    body = "观澜安装包微信正文读取验证。" * 40
    html = (
        "<html><head>"
        '<meta property="og:title" content="观澜安装包读取验证">'
        '<meta name="author" content="Guanlan">'
        "</head><body>"
        f'<div id="js_content"><p>{body}</p></div>'
        "</body></html>"
    )

    def fake_open(request, timeout=None, **_kwargs):
        del timeout
        return _Response(request.full_url, html)

    scenarios = (
        ("normal_public_dns", ("93.184.216.34",), False, "dns"),
        ("loopback_proxy_fake_ip", ("198.18.0.96", "::ffff:198.18.0.96"), True, "loopback_proxy_fake_ip"),
        ("loopback_proxy_mixed_dns", ("93.184.216.34", "198.18.0.96"), True, "loopback_proxy_mixed_dns"),
        ("loopback_proxy_remote_dns", OSError("local DNS unavailable"), True, "loopback_proxy_remote_dns"),
    )
    completed: list[str] = []
    for name, resolver_result, proxy_enabled, expected_mode in scenarios:
        resolver_patch = (
            patch("guanlan.url_policy._resolve_host", side_effect=resolver_result)
            if isinstance(resolver_result, BaseException)
            else patch("guanlan.url_policy._resolve_host", return_value=resolver_result)
        )
        with (
            resolver_patch,
            patch("guanlan.url_policy._loopback_proxy_handles_host", return_value=proxy_enabled),
            patch("urllib.request.urlopen", side_effect=fake_open),
        ):
            packet = _run_tool(
                "guanlan_read",
                {"url": url, "format": "json", "fallback_search": False, "max_chars": 12000},
            )
            assert packet["trace"]["selected_backend"] == "wechat_article"
            assert packet["trace"]["public_url_policy"]["resolution_mode"] == expected_mode
            assert packet["extract_contract"]["can_cite_as_page_body"] is True
            assert "观澜安装包微信正文读取验证" in packet["content"]
            completed.append(name)

    for blocked in ("http://127.0.0.1/admin", "http://198.18.0.96/admin", "http://10.0.0.1/a"):
        try:
            validate_public_url(blocked)
        except URLPolicyError:
            continue
        raise AssertionError(f"unsafe literal unexpectedly allowed: {blocked}")

    print(f"installed MCP read network matrix passed: {', '.join(completed)} + private literal rejection")


if __name__ == "__main__":
    main()
