# -*- coding: utf-8 -*-
"""Optional AnySearch integration and activation policy.

AnySearch is an external search provider. Guanlan enables anonymous fallback by
default for strong-fit agent search routes, while keeping explicit opt-out
switches for users who do not want external AnySearch calls.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from guanlan.config import Config

ANYSEARCH_API_BASE = "https://api.anysearch.com"
ANYSEARCH_SEARCH_ENDPOINT = f"{ANYSEARCH_API_BASE}/v1/search"
ANYSEARCH_CONSOLE_URL = "https://www.anysearch.com/console/api-keys"
ANYSEARCH_AUTO_MODES = {"off", "fallback", "preferred"}

_AUTO_FIT_PROFILES = {"english", "global", "hybrid"}
_AUTO_FIT_SCOPES = {
    "academic",
    "cybersecurity",
    "finance",
    "finance_disclosure",
    "finance_macro",
    "finance_quote",
    "finance_research",
    "global_industry",
    "global_official",
    "global_reputation",
    "industry_analysis",
    "science",
    "tech",
}
_AUTO_FIT_INTENTS = {
    "academic",
    "company_primary",
    "cybersecurity",
    "finance",
    "global_policy",
    "science",
    "tech",
}
_AUTO_FIT_QUERY_TERMS = (
    "api",
    "mcp",
    "sdk",
    "github",
    "cve",
    "arxiv",
    "doi",
    "paper",
    "pricing",
    "benchmark",
    "release notes",
    "security advisory",
    "vulnerability",
    "agent",
)


@dataclass
class AnySearchAPIError(RuntimeError):
    """External AnySearch API error with redacted diagnostic metadata."""

    status_code: int
    error_code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return f"AnySearch API error {self.status_code}: {self.error_code or self.message}"


def anysearch_api_key(config: Config | None = None) -> str:
    """Return the configured AnySearch key without printing or logging it."""
    cfg = config or Config()
    return str(cfg.get("anysearch_api_key") or "").strip()


def anysearch_has_api_key(config: Config | None = None) -> bool:
    return bool(anysearch_api_key(config))


def anysearch_auto_mode(config: Config | None = None) -> str:
    """Return automatic routing mode: fallback by default, or off/preferred."""
    cfg = config or Config()
    raw = (
        os.environ.get("GUANLAN_ANYSEARCH_AUTO")
        or str(cfg.get("anysearch_auto") or "")
        or "fallback"
    )
    mode = str(raw).strip().lower()
    return mode if mode in ANYSEARCH_AUTO_MODES else "fallback"


def anysearch_anonymous_auto_allowed(config: Config | None = None) -> bool:
    """Whether auto mode may use AnySearch without a user API key.

    Explicit `--backend anysearch` is always allowed to use anonymous quota. This
    flag only controls automatic insertion into the normal backend chain. The
    default is on so Guanlan can use public anonymous quota on routed fit.
    """
    cfg = config or Config()
    env_raw = os.environ.get("GUANLAN_ANYSEARCH_ANONYMOUS_AUTO")
    raw = env_raw if env_raw is not None else cfg.get("anysearch_anonymous_auto", None)
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def anysearch_auto_backend_order(
    base_order: list[str],
    *,
    query: str | None = None,
    profile: str | None = None,
    scope: str | None = None,
    site: str | None = None,
    config: Config | None = None,
) -> list[str]:
    """Insert AnySearch into an auto backend order when the user opted in."""
    cfg = config or Config()
    mode = anysearch_auto_mode(cfg)
    if mode == "off" or "anysearch" in base_order:
        return base_order
    if site:
        return base_order
    has_key = anysearch_has_api_key(cfg)
    if not has_key and not anysearch_anonymous_auto_allowed(cfg):
        return base_order
    if not _query_fits_anysearch(query=query, profile=profile, scope=scope, route_plan=None):
        return base_order
    if mode == "preferred":
        if profile == "china":
            return _unique_keep_order([base_order[0], "anysearch", *base_order[1:]]) if base_order else ["anysearch"]
        return _unique_keep_order(["anysearch", *base_order])
    if profile == "china":
        # Keep China-native sources first, but avoid spending the final slot on a
        # slow open-web HTML fallback before the structured AnySearch fallback.
        if "duckduckgo" in base_order:
            idx = base_order.index("duckduckgo")
            return _unique_keep_order([*base_order[:idx], "anysearch", *base_order[idx:]])
        return _unique_keep_order([*base_order, "anysearch"])
    # For non-China strong-fit routes, Bing gives a quick public baseline,
    # AnySearch expands structured coverage, and DuckDuckGo stays as a late HTML
    # fallback only when the first two are insufficient.
    return _unique_keep_order(["bing", "anysearch", *base_order])


def anysearch_activation_plan(
    query: str,
    *,
    profile: str | None = None,
    scope: str | None = None,
    backend: str = "auto",
    route_plan: dict[str, Any] | None = None,
    backend_summary: dict[str, Any] | None = None,
    result_count: int | None = None,
    config: Config | None = None,
) -> dict[str, Any]:
    """Explain when Guanlan should activate AnySearch for a user.

    Default automatic use is anonymous fallback for strong-fit routes. Guanlan
    still never persists credentials or reads browser state without user action.
    """
    cfg = config or Config()
    mode = anysearch_auto_mode(cfg)
    has_key = anysearch_has_api_key(cfg)
    anonymous_auto = anysearch_anonymous_auto_allowed(cfg)
    normalized_backend = (backend or "auto").lower()
    summary = backend_summary or {}
    reasons: list[str] = []

    explicit = normalized_backend == "anysearch"
    route_fit = _query_fits_anysearch(query=query, profile=profile, scope=scope, route_plan=route_plan)
    if explicit:
        reasons.append("explicit_backend")
    if route_fit:
        reasons.append("query_matches_anysearch_strength")
    if result_count is not None and result_count < 3:
        reasons.append("low_result_count")
    if any(summary.get(key) for key in ("errors", "blocked", "parser_miss", "zero_results")):
        reasons.append("search_backend_needs_supplement")

    eligible = explicit or route_fit
    can_auto = explicit or (
        mode != "off"
        and eligible
        and (has_key or anonymous_auto)
    )
    if can_auto:
        status = "active" if explicit else f"auto_{mode}"
        next_action = "use_anysearch"
    elif eligible:
        status = "suggest"
        next_action = "ask_user_or_configure"
    else:
        status = "inactive"
        next_action = "keep_default_backends"

    return {
        "enabled": status != "inactive",
        "status": status,
        "next_action": next_action,
        "auto_mode": mode,
        "has_api_key": has_key,
        "anonymous_auto_allowed": anonymous_auto,
        "reasons": _unique_keep_order(reasons),
        "recommended_commands": [] if can_auto else _activation_commands(has_key=has_key, eligible=eligible),
        "credential_boundary": (
            "不要读取浏览器 Cookie、Token、密码或控制台页面来获取 AnySearch key；"
            "只允许用户显式配置 key，或在 AnySearch 返回自动注册 key 后经用户确认再保存。"
        ),
        "privacy_boundary": (
            "AnySearch 是外部搜索后端；启用后查询和待提取 URL 会发送到 api.anysearch.com。"
        ),
    }


def search_anysearch(
    query: str,
    *,
    limit: int = 10,
    api_key: str | None = None,
    zone: str | None = None,
    language: str | None = None,
    timeout: float = 12,
) -> dict[str, Any]:
    """Call AnySearch's REST search API and return normalized raw payload."""
    payload: dict[str, Any] = {
        "query": query,
        "max_results": max(1, min(int(limit or 10), 100)),
    }
    if zone:
        payload["zone"] = zone
    if language:
        payload["language"] = language
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    credential_mode = "anonymous"
    key = (api_key or anysearch_api_key() or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
        credential_mode = "api_key"
    request = urllib.request.Request(
        ANYSEARCH_SEARCH_ENDPOINT,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = int(getattr(response, "status", 200) or 200)
            headers_map = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        details = _parse_error_details(raw)
        raise AnySearchAPIError(
            status_code=exc.code,
            error_code=str(details.get("error_code") or details.get("code") or ""),
            message=str(details.get("message") or exc.reason or "request failed"),
            details=_redact_error_details(details),
        ) from exc
    except urllib.error.URLError as exc:
        raise AnySearchAPIError(
            status_code=0,
            error_code="network_error",
            message=str(exc.reason or exc),
            details={"status": "network_error"},
        ) from exc

    data = json.loads(raw)
    if isinstance(data, dict) and data.get("code") not in (None, 0, "0", "success"):
        raise AnySearchAPIError(
            status_code=status_code,
            error_code=str(data.get("code") or ""),
            message=str(data.get("message") or "request failed"),
            details=_redact_error_details(data),
        )
    normalized = _normalize_success_payload(data)
    normalized.setdefault("metadata", {})
    normalized["metadata"].update(
        {
            "credential_mode": credential_mode,
            "request_id": normalized["metadata"].get("request_id") or headers_map.get("x-request-id", ""),
            "rate_limit_limit": headers_map.get("x-ratelimit-limit", ""),
            "rate_limit_remaining": headers_map.get("x-ratelimit-remaining", ""),
            "rate_limit_reset": headers_map.get("x-ratelimit-reset", ""),
        }
    )
    return normalized


def _query_fits_anysearch(
    *,
    query: str | None,
    profile: str | None,
    scope: str | None,
    route_plan: dict[str, Any] | None,
) -> bool:
    normalized_query = str(query or "").lower()
    if (profile or "").lower() in _AUTO_FIT_PROFILES:
        return True
    if (scope or "").lower() in _AUTO_FIT_SCOPES:
        return True
    intents = set(str(item).lower() for item in (route_plan or {}).get("primary_intents") or [])
    intents.update(str(item).lower() for item in (route_plan or {}).get("secondary_intents") or [])
    if intents & _AUTO_FIT_INTENTS:
        return True
    return any(term in normalized_query for term in _AUTO_FIT_QUERY_TERMS)


def _activation_commands(*, has_key: bool, eligible: bool) -> list[str]:
    if not eligible:
        return []
    commands = ['guanlan search "关键词" --backend anysearch --limit 80 --trace']
    if not has_key:
        commands.extend(
            [
                "guanlan configure anysearch-key <YOUR_ANYSEARCH_API_KEY>",
                "guanlan configure anysearch-auto fallback",
            ]
        )
    else:
        commands.append("guanlan configure anysearch-auto fallback")
    return commands


def _normalize_success_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"results": [], "metadata": {}}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return {
        "results": data.get("results") if isinstance(data.get("results"), list) else [],
        "metadata": data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
    }


def _parse_error_details(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"message": raw[:200]}
    return payload if isinstance(payload, dict) else {"message": str(payload)[:200]}


def _redact_error_details(details: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in details.items():
        normalized = str(key).lower()
        if normalized in {"api_key", "password", "username"}:
            redacted[f"{normalized}_available"] = bool(value)
        elif isinstance(value, dict):
            redacted[key] = _redact_error_details(value)
        else:
            redacted[key] = value
    if redacted.get("api_key_available"):
        redacted["requires_user_confirmation_to_persist"] = True
    return redacted


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
