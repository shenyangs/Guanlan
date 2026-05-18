# -*- coding: utf-8 -*-

import json
from urllib.parse import parse_qs, urlparse

import pytest

from guanlan import wechat_exporter


class _FakeResponse:
    def __init__(self, text: str, content_type: str = "application/json; charset=utf-8"):
        self._text = text
        self.headers = {"content-type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        return self._text.encode("utf-8")


def test_exporter_status_is_safe_without_configuration(monkeypatch):
    monkeypatch.delenv("GUANLAN_WECHAT_EXPORTER_BASE_URL", raising=False)
    monkeypatch.delenv("GUANLAN_WECHAT_EXPORTER_AUTH_KEY", raising=False)

    status = wechat_exporter.exporter_status()

    assert status["status"] == "not_configured"
    assert status["auth_key_value"] == ""
    assert status["safety"]["default_cookie_access"] == "forbidden"
    assert "IndexedDB" in status["boundary"] or "browser" in status["boundary"]


def test_search_accounts_uses_auth_header_and_redacts_payload(monkeypatch):
    monkeypatch.setenv("GUANLAN_WECHAT_EXPORTER_AUTH_KEY", "SECRET-AUTH")
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        return _FakeResponse(
            json.dumps(
                {
                    "base_resp": {"ret": 0, "err_msg": "ok"},
                    "list": [{"fakeid": "abc", "nickname": "测试公众号", "key": "SHOULD_HIDE"}],
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    payload = wechat_exporter.search_accounts("测试", base_url="https://exporter.example", size=50)

    parsed = urlparse(seen["url"])
    assert parsed.path == "/api/public/v1/account"
    query = parse_qs(parsed.query)
    assert query["keyword"] == ["测试"]
    assert query["size"] == ["20"]
    assert seen["headers"]["X-auth-key"] == "SECRET-AUTH"
    assert payload["list"][0]["key"] == "redacted"
    assert payload["boundary"].startswith("wechat_exporter_authorized_account_api")


def test_download_article_requires_explicit_base_url(monkeypatch):
    monkeypatch.delenv("GUANLAN_WECHAT_EXPORTER_BASE_URL", raising=False)

    with pytest.raises(wechat_exporter.WeChatExporterError):
        wechat_exporter.download_article("https://mp.weixin.qq.com/s/example")


def test_download_article_returns_public_markdown(monkeypatch):
    def fake_urlopen(req, timeout=None):
        assert "/api/public/v1/download" in req.full_url
        return _FakeResponse("# 标题\n正文", content_type="text/markdown; charset=utf-8")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    payload = wechat_exporter.download_article(
        "https://mp.weixin.qq.com/s/example",
        base_url="https://exporter.example",
    )

    assert payload["format"] == "markdown"
    assert "正文" in payload["content"]
    assert "no implicit credential" in payload["boundary"]

