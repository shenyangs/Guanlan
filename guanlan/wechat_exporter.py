# -*- coding: utf-8 -*-
"""Optional WeChat article exporter adapter.

This module talks to a user-configured wechat-article-exporter deployment. It
never reads browser cookies, local credentials, or IndexedDB by itself; the
caller must provide a base URL and, for account/history APIs, an auth key via an
environment variable.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL_ENV = "GUANLAN_WECHAT_EXPORTER_BASE_URL"
DEFAULT_AUTH_KEY_ENV = "GUANLAN_WECHAT_EXPORTER_AUTH_KEY"
DEFAULT_TIMEOUT = 25
DOWNLOAD_FORMATS = {"html", "markdown", "text", "json"}


class WeChatExporterError(RuntimeError):
    """Raised when the optional exporter adapter is not configured or fails."""


def exporter_status(
    *,
    base_url: str | None = None,
    auth_key_env: str = DEFAULT_AUTH_KEY_ENV,
    probe: bool = False,
) -> dict[str, Any]:
    resolved_base = _resolve_base_url(base_url, required=False)
    auth_key = _resolve_auth_key(auth_key_env, required=False)
    payload: dict[str, Any] = {
        "adapter": "wechat_exporter",
        "status": "configured" if resolved_base else "not_configured",
        "base_url": resolved_base,
        "base_url_env": DEFAULT_BASE_URL_ENV,
        "auth_key_env": auth_key_env,
        "auth_key_configured": bool(auth_key),
        "auth_key_value": "redacted" if auth_key else "",
        "capabilities": [
            "download_public_article",
            "search_account_with_user_auth_key",
            "list_account_articles_with_user_auth_key",
            "account_by_article_url_with_user_auth_key",
        ],
        "safety": {
            "default_cookie_access": "forbidden",
            "credential_material_access": "env_auth_key_only",
            "browser_storage_access": "forbidden",
            "credentials_not_logged": True,
            "requires_user_configured_exporter": True,
        },
        "boundary": "optional_user_configured_wechat_exporter; account APIs require X-Auth-Key from env; no browser cookie/profile/IndexedDB reads",
        "setup": [
            f"export {DEFAULT_BASE_URL_ENV}=https://your-private-exporter.example",
            f"export {auth_key_env}=<wechat_exporter_auth_key>",
            "guanlan wechat-exporter status --probe",
        ],
    }
    if probe and resolved_base:
        try:
            probe_payload = _request_json("/api/public/v1/authkey", base_url=resolved_base, auth_key=auth_key, require_auth=False)
            base_resp = probe_payload.get("base_resp") if isinstance(probe_payload, dict) else None
            payload["probe"] = {
                "status": "ok" if isinstance(base_resp, dict) and base_resp.get("ret") == 0 else "warn",
                "response": _redact_payload(probe_payload),
            }
        except Exception as exc:
            payload["probe"] = {"status": "error", "error": str(exc)}
    return payload


def search_accounts(
    keyword: str,
    *,
    begin: int = 0,
    size: int = 20,
    base_url: str | None = None,
    auth_key_env: str = DEFAULT_AUTH_KEY_ENV,
) -> dict[str, Any]:
    if not keyword.strip():
        raise WeChatExporterError("keyword is required")
    payload = _request_json(
        "/api/public/v1/account",
        base_url=_resolve_base_url(base_url),
        auth_key=_resolve_auth_key(auth_key_env),
        params={"keyword": keyword.strip(), "begin": max(begin, 0), "size": _clamp_size(size)},
    )
    return _with_boundary(payload, operation="account_search")


def account_by_url(
    url: str,
    *,
    base_url: str | None = None,
    auth_key_env: str = DEFAULT_AUTH_KEY_ENV,
) -> dict[str, Any]:
    _require_wechat_article_url(url)
    payload = _request_json(
        "/api/public/v1/accountbyurl",
        base_url=_resolve_base_url(base_url),
        auth_key=_resolve_auth_key(auth_key_env),
        params={"url": url},
    )
    return _with_boundary(payload, operation="account_by_url")


def list_articles(
    fakeid: str,
    *,
    begin: int = 0,
    size: int = 20,
    keyword: str = "",
    base_url: str | None = None,
    auth_key_env: str = DEFAULT_AUTH_KEY_ENV,
) -> dict[str, Any]:
    if not fakeid.strip():
        raise WeChatExporterError("fakeid is required")
    params: dict[str, Any] = {"fakeid": fakeid.strip(), "begin": max(begin, 0), "size": _clamp_size(size)}
    if keyword.strip():
        params["keyword"] = keyword.strip()
    payload = _request_json(
        "/api/public/v1/article",
        base_url=_resolve_base_url(base_url),
        auth_key=_resolve_auth_key(auth_key_env),
        params=params,
    )
    return _with_boundary(payload, operation="article_list")


def download_article(
    url: str,
    *,
    output_format: str = "markdown",
    base_url: str | None = None,
    auth_key_env: str = DEFAULT_AUTH_KEY_ENV,
) -> dict[str, Any]:
    _require_wechat_article_url(url)
    fmt = (output_format or "markdown").lower()
    if fmt not in DOWNLOAD_FORMATS:
        raise WeChatExporterError(f"unsupported format: {output_format}")
    content = _request_text(
        "/api/public/v1/download",
        base_url=_resolve_base_url(base_url),
        auth_key=_resolve_auth_key(auth_key_env, required=False),
        params={"url": url, "format": fmt},
        require_auth=False,
        accept="application/json,text/markdown,text/plain,text/html",
    )
    parsed: Any = None
    if fmt == "json":
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"raw": content}
    return {
        "operation": "download_article",
        "url": url,
        "format": fmt,
        "content": parsed if fmt == "json" else content,
        "boundary": "wechat_exporter_download; user_configured_base_url; no implicit credential or browser storage access",
    }


def _request_json(
    path: str,
    *,
    base_url: str,
    auth_key: str | None,
    params: dict[str, Any] | None = None,
    require_auth: bool = True,
) -> dict[str, Any]:
    raw = _request_text(path, base_url=base_url, auth_key=auth_key, params=params, require_auth=require_auth)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WeChatExporterError("wechat exporter returned non-json response") from exc
    if not isinstance(data, dict):
        raise WeChatExporterError("wechat exporter returned unexpected json shape")
    return data


def _request_text(
    path: str,
    *,
    base_url: str,
    auth_key: str | None,
    params: dict[str, Any] | None = None,
    require_auth: bool = True,
    accept: str = "application/json",
) -> str:
    if require_auth and not auth_key:
        raise WeChatExporterError(f"missing auth key; set {DEFAULT_AUTH_KEY_ENV} or pass --auth-env")
    query = urllib.parse.urlencode(params or {})
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    if query:
        url = f"{url}?{query}"
    headers = {
        "Accept": accept,
        "User-Agent": "Guanlan-WeChatExporter/1.0",
    }
    if auth_key:
        headers["X-Auth-Key"] = auth_key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            raw = resp.read()
            content_type = resp.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        raise WeChatExporterError(f"wechat exporter http {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise WeChatExporterError(f"wechat exporter unavailable: {exc.reason}") from exc
    encoding = "utf-8"
    match = "charset="
    if match in content_type.lower():
        encoding = content_type.lower().split(match, 1)[1].split(";", 1)[0].strip() or "utf-8"
    return raw.decode(encoding, errors="replace")


def _resolve_base_url(base_url: str | None, *, required: bool = True) -> str:
    value = (base_url or os.environ.get(DEFAULT_BASE_URL_ENV) or "").strip().rstrip("/")
    if value and not re_url(value):
        raise WeChatExporterError("wechat exporter base url must start with http:// or https://")
    if required and not value:
        raise WeChatExporterError(f"wechat exporter base url is required; set {DEFAULT_BASE_URL_ENV} or pass --base-url")
    return value


def _resolve_auth_key(auth_key_env: str, *, required: bool = True) -> str:
    env_name = auth_key_env or DEFAULT_AUTH_KEY_ENV
    value = (os.environ.get(env_name) or "").strip()
    if required and not value:
        raise WeChatExporterError(f"wechat exporter auth key is required; set {env_name}")
    return value


def _with_boundary(payload: dict[str, Any], *, operation: str) -> dict[str, Any]:
    result = dict(payload)
    result["operation"] = operation
    result["boundary"] = "wechat_exporter_authorized_account_api; X-Auth-Key from env; no cookie/token/logged credential output"
    return _redact_payload(result)


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"cookie", "cookies", "token", "auth_key", "authkey", "key", "pass_ticket", "uin", "wap_sid2"}:
                redacted[key] = "redacted"
            else:
                redacted[key] = _redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def _clamp_size(size: int) -> int:
    return min(max(int(size or 20), 1), 20)


def _require_wechat_article_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.netloc.lower() != "mp.weixin.qq.com":
        raise WeChatExporterError("only mp.weixin.qq.com article URLs are supported")


def re_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
