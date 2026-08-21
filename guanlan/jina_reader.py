# -*- coding: utf-8 -*-
"""Bounded, compatibility-first controls for the hosted Jina Reader API.

The default request deliberately matches Guanlan's historical wire contract.
New upstream controls are opt-in, except for one internal browser repair that
is allowed only after the existing Jina and direct paths both return a clear
dynamic application shell.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
from dataclasses import dataclass, replace
from typing import Any

from guanlan.network_execution import diagnose_network_error

JINA_READ_CONTRACT_SCHEMA_VERSION = "jina_read_contract_v1"

_VALID_ENGINES = {"auto", "browser", "curl"}
_VALID_FORMATS = {"content", "frontmatter"}
_MAX_SELECTOR_CHARS = 512
_DYNAMIC_SHELL_MARKERS = (
    "enable javascript",
    "javascript is required",
    "please enable javascript",
    "数据加载中",
    "内容加载中",
    "window.location.href",
    "upgrade_browser",
    "galileotelemetry",
    "__next_data__",
    'id="__next"',
)
_ACCESS_GATE_MARKERS = (
    "captcha",
    "verify you are human",
    "access denied",
    "forbidden",
    "验证码",
    "安全验证",
    "访问受限",
    "访问过于频繁",
    "请验证以继续访问",
    "请先登录",
    "登录后查看",
)
_STRUCTURED_FINANCE_DOMAINS = {
    "quote.eastmoney.com",
    "eastmoney.com",
    "finance.sina.com.cn",
    "xueqiu.com",
    "guba.eastmoney.com",
    "10jqka.com.cn",
    "cn.investing.com",
    "finance.yahoo.com",
    "nasdaq.com",
}


@dataclass(frozen=True)
class JinaReadOptions:
    """Safe subset of Jina controls supported by Guanlan read."""

    engine: str = "auto"
    response_format: str = "content"
    wait_for: str = ""
    target: str = ""
    remove: str = ""
    no_cache: bool = False
    respond_timing: str = ""

    @property
    def explicit_controls(self) -> bool:
        return bool(
            self.engine != "auto"
            or self.response_format != "content"
            or self.wait_for
            or self.target
            or self.remove
            or self.no_cache
            or self.respond_timing
        )

    def request_headers(self) -> dict[str, str]:
        """Build headers while preserving the old default request exactly."""

        headers = {"Accept": "text/plain"}
        if self.engine != "auto":
            headers["X-Engine"] = self.engine
        if self.response_format != "content":
            headers["X-Respond-With"] = self.response_format
        if self.wait_for:
            headers["X-Wait-For-Selector"] = self.wait_for
        if self.target:
            headers["X-Target-Selector"] = self.target
        if self.remove:
            headers["X-Remove-Selector"] = self.remove
        if self.no_cache:
            headers["X-No-Cache"] = "true"
        if self.respond_timing:
            headers["X-Respond-Timing"] = self.respond_timing
        return headers

    def contract(self, *, repair_enabled: bool = True, repair_used: bool = False) -> dict[str, Any]:
        """Return an additive, credential-free trace contract."""

        return {
            "schema_version": JINA_READ_CONTRACT_SCHEMA_VERSION,
            "mode": "compatibility",
            "wire_defaults_preserved": not self.explicit_controls,
            "engine": self.engine,
            "response_format": self.response_format,
            "upstream_cache": "bypass" if self.no_cache else "default",
            "explicit_controls": self.explicit_controls,
            "selectors": {
                "wait_for": self.wait_for,
                "target": self.target,
                "remove": self.remove,
            },
            "safe_repair": {
                "enabled": bool(repair_enabled),
                "used": bool(repair_used),
                "trigger": "confirmed_dynamic_shell_after_jina_and_direct",
            },
            "credential_material_access_allowed": False,
            "cookie_forwarding_allowed": False,
            "proxy_credentials_allowed": False,
        }

    def for_safe_browser_repair(self) -> "JinaReadOptions":
        """Return the one bounded internal repair profile."""

        return replace(
            self,
            engine="browser",
            no_cache=True,
            respond_timing="mutation-idle",
        )


def normalize_jina_options(
    *,
    engine: str = "auto",
    response_format: str = "content",
    wait_for: str = "",
    target: str = "",
    remove: str = "",
    no_cache: bool = False,
) -> JinaReadOptions:
    """Validate the deliberately small public Jina option surface."""

    normalized_engine = str(engine or "auto").strip().lower()
    if normalized_engine not in _VALID_ENGINES:
        raise ValueError("jina_engine must be one of: auto, browser, curl")
    normalized_format = str(response_format or "content").strip().lower()
    if normalized_format not in _VALID_FORMATS:
        raise ValueError("jina_format must be one of: content, frontmatter")
    return JinaReadOptions(
        engine=normalized_engine,
        response_format=normalized_format,
        wait_for=_safe_selector("jina_wait_for", wait_for),
        target=_safe_selector("jina_target", target),
        remove=_safe_selector("jina_remove", remove),
        no_cache=bool(no_cache),
    )


def should_attempt_safe_repair(
    url: str,
    *,
    jina_text: str,
    direct_text: str,
    options: JinaReadOptions,
    enabled: bool = True,
) -> bool:
    """Allow browser repair only for a confirmed public dynamic-page shell."""

    # ``no_cache`` is compatible with the bounded repair: the repair already
    # bypasses upstream cache. Other explicit extraction controls indicate the
    # caller chose a specific Jina behavior, so do not silently replace it.
    caller_selected_behavior = bool(
        options.engine != "auto"
        or options.response_format != "content"
        or options.wait_for
        or options.target
        or options.remove
        or options.respond_timing
    )
    if not enabled or caller_selected_behavior:
        return False
    host = urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    if any(host == domain or host.endswith(f".{domain}") for domain in _STRUCTURED_FINANCE_DOMAINS):
        return False
    jina_lower = jina_text.lower()
    direct_lower = direct_text.lower()
    combined = f"{jina_lower}\n{direct_lower}"
    if any(marker in combined for marker in _ACCESS_GATE_MARKERS):
        return False
    return any(marker in jina_lower for marker in _DYNAMIC_SHELL_MARKERS) and any(
        marker in direct_lower for marker in _DYNAMIC_SHELL_MARKERS
    )


def diagnose_jina_error(exc: BaseException) -> dict[str, Any]:
    """Add rate/quota detail without exposing upstream response bodies."""

    diagnostic = diagnose_network_error(exc, source="jina", operation="read_page")
    if not isinstance(exc, urllib.error.HTTPError):
        return diagnostic
    diagnostic["http_status"] = int(exc.code)
    if exc.code == 429:
        diagnostic.update(
            {
                "category": "rate_limited",
                "retryable": True,
                "safe_message": "Jina Reader 当前请求频率受限，观澜将继续既有降级路线。",
                "next_decision": "repair",
            }
        )
        retry_after = _retry_after_seconds(exc)
        if retry_after is not None:
            diagnostic["retry_after_seconds"] = retry_after
    elif exc.code == 402:
        diagnostic.update(
            {
                "category": "quota_exhausted",
                "retryable": False,
                "safe_message": "Jina Reader 当前额度不可用，观澜将继续既有降级路线。",
                "next_decision": "continue",
            }
        )
    return diagnostic


def _safe_selector(name: str, value: Any) -> str:
    selector = str(value or "").strip()
    if any(char in selector for char in ("\r", "\n", "\x00")):
        raise ValueError(f"{name} must be a single safe header value")
    if len(selector) > _MAX_SELECTOR_CHARS:
        raise ValueError(f"{name} must be at most {_MAX_SELECTOR_CHARS} characters")
    return selector


def _retry_after_seconds(exc: urllib.error.HTTPError) -> int | None:
    headers = getattr(exc, "headers", None)
    value = headers.get("Retry-After") if headers is not None and hasattr(headers, "get") else None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return max(parsed, 0)


__all__ = [
    "JINA_READ_CONTRACT_SCHEMA_VERSION",
    "JinaReadOptions",
    "diagnose_jina_error",
    "normalize_jina_options",
    "should_attempt_safe_repair",
]
