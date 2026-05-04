# -*- coding: utf-8 -*-
"""Read-quality and page-access diagnosis for Guanlan.

This module is deliberately read-only. It explains why a page is or is not a
usable evidence source, then points agents back to Guanlan's stable search,
structured-data, and archive workflows.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class PageDiagnosis:
    """Stable page diagnosis payload for CLI/MCP agents."""

    url: str
    page_type: str
    usable_as_evidence: bool
    confidence: float
    selected_backend: str = ""
    read_label: str = "unknown"
    read_score: int = 0
    signals: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    quality_report: dict[str, Any] = field(default_factory=dict)
    recommended_commands: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    authorization_policy: list[str] = field(default_factory=list)
    browser_assist: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def diagnose_page(
    url: str,
    *,
    max_chars: int | None = 4000,
    backend: str = "auto",
    fallback_search: bool = True,
    fallback_limit: int = 5,
    profile: str | None = "china",
    strict: bool = False,
    fetch: bool = True,
    content: str | None = None,
) -> dict[str, Any]:
    """Diagnose a URL or supplied page text without changing browser state."""

    from guanlan.webtools import assess_read_quality, build_read_quality_report, read_url_with_trace

    normalized_url = _normalize_url(url)
    packet: dict[str, Any]
    errors: list[str] = []
    if fetch:
        try:
            packet = read_url_with_trace(
                normalized_url,
                max_chars=max_chars,
                backend=backend,
                fallback_search=fallback_search,
                fallback_limit=max(fallback_limit, 1),
                profile=profile,
                strict=strict,
            )
        except Exception as exc:
            packet = {
                "url": normalized_url,
                "content": "",
                "quality": {},
                "quality_report": {
                    "usable": False,
                    "label": "error",
                    "score": 0,
                    "recommendations": ["读取失败，建议检查网络、站点可用性或改用搜索/垂直源补证。"],
                },
                "trace": {"selected_backend": "", "attempts": [], "errors": [str(exc)]},
            }
            errors.append(str(exc))
    else:
        text = content or ""
        quality = assess_read_quality(text)
        trace = {"selected_backend": "provided_text", "attempts": [], "errors": []}
        packet = {
            "url": normalized_url,
            "content": text,
            "quality": quality,
            "quality_report": build_read_quality_report(text, url=normalized_url, quality=quality, trace=trace),
            "trace": trace,
        }
    diagnosis = _diagnose_packet(packet, errors=errors)
    return diagnosis.to_dict()


def format_page_diagnosis_markdown(payload: PageDiagnosis | dict[str, Any]) -> str:
    """Render page diagnosis as compact Markdown."""

    data = payload.to_dict() if isinstance(payload, PageDiagnosis) else dict(payload)
    lines = [
        f"# 观澜页面诊断 / {data.get('url', '')}",
        "",
        f"- 页面类型: {data.get('page_type')}",
        f"- 可作为正文证据: {'是' if data.get('usable_as_evidence') else '否'}",
        f"- 置信度: {data.get('confidence')}",
        f"- 读取后端: {data.get('selected_backend') or '-'}",
        f"- 阅读质量: {data.get('read_label')} / {data.get('read_score')}",
    ]
    signals = data.get("signals") or []
    if signals:
        lines.extend(["", "## 诊断信号"])
        lines.extend(f"- {item}" for item in signals)
    attempts = data.get("attempts") or []
    if attempts:
        lines.extend(["", "## 读取尝试"])
        for item in attempts:
            label = str(item.get("backend") or "unknown")
            status = str(item.get("status") or "unknown")
            detail = f"{label}: {status}"
            if item.get("chars") is not None:
                detail += f" chars={item.get('chars')}"
            if item.get("error"):
                detail += f" error={item.get('error')}"
            lines.append(f"- {detail}")
    commands = data.get("recommended_commands") or []
    if commands:
        lines.extend(["", "## 推荐下一步"])
        lines.extend(f"- `{item}`" for item in commands)
    boundaries = data.get("boundaries") or []
    if boundaries:
        lines.extend(["", "## 边界"])
        lines.extend(f"- {item}" for item in boundaries)
    auth = data.get("authorization_policy") or []
    if auth:
        lines.extend(["", "## 授权策略"])
        lines.extend(f"- {item}" for item in auth)
    browser_assist = data.get("browser_assist") if isinstance(data.get("browser_assist"), dict) else {}
    if browser_assist and browser_assist.get("recommended"):
        from guanlan.browser_assist import format_browser_assist_markdown

        lines.extend(["", format_browser_assist_markdown(browser_assist)])
    return "\n".join(lines).rstrip()


def format_page_diagnosis_json(payload: PageDiagnosis | dict[str, Any]) -> str:
    data = payload.to_dict() if isinstance(payload, PageDiagnosis) else dict(payload)
    return json.dumps(data, ensure_ascii=False, indent=2)


def _diagnose_packet(packet: dict[str, Any], *, errors: list[str]) -> PageDiagnosis:
    url = str(packet.get("url") or "")
    trace = dict(packet.get("trace") or {})
    quality_report = dict(packet.get("quality_report") or {})
    attempts = list(trace.get("attempts") or [])
    selected_backend = str(trace.get("selected_backend") or "")
    content = str(packet.get("content") or "")
    signals = _signals(url, content, quality_report, trace, errors)
    page_type, confidence = _page_type(quality_report, signals, errors)
    usable = bool(quality_report.get("usable")) and page_type == "readable_article"
    commands = _recommended_commands(url, page_type, signals)
    boundaries = _boundaries(page_type)
    from guanlan.browser_assist import build_browser_assist_plan

    return PageDiagnosis(
        url=url,
        page_type=page_type,
        usable_as_evidence=usable,
        confidence=confidence,
        selected_backend=selected_backend,
        read_label=str(quality_report.get("label") or "unknown"),
        read_score=int(quality_report.get("score") or 0),
        signals=signals,
        attempts=attempts,
        quality_report=quality_report,
        recommended_commands=commands,
        boundaries=boundaries,
        authorization_policy=_authorization_policy(page_type),
        browser_assist=build_browser_assist_plan(url, page_type=page_type, signals=signals),
    )


def _signals(
    url: str,
    content: str,
    quality_report: dict[str, Any],
    trace: dict[str, Any],
    errors: list[str],
) -> list[str]:
    output: list[str] = []
    selected = str(trace.get("selected_backend") or "")
    if quality_report.get("usable"):
        output.append("readable_body")
    if quality_report.get("dynamic_shell"):
        output.append("dynamic_shell")
    if quality_report.get("fallback") or selected == "search_fallback":
        output.append("search_fallback_only")
    if quality_report.get("blocked_markers"):
        output.append("blocked_or_login_marker")
    if errors or trace.get("errors"):
        output.append("read_errors")
    if "xueqiu.com" in urlparse(url).netloc:
        output.append("finance_social_page")
    if _looks_finance_url(url):
        output.append("finance_dynamic_candidate")
    lowered = (content or "").lower()
    if any(item in lowered for item in ("验证码", "访问受限", "access denied", "captcha", "请先登录", "login")):
        output.append("access_gate")
    if any(item in lowered for item in ("window.location.href", "upgrade_browser", "galileotelemetry", "数据加载中")):
        output.append("script_or_app_shell")
    if int(quality_report.get("chars") or 0) < 500 and not quality_report.get("usable"):
        output.append("thin_body")
    return _unique(output)


def _page_type(quality_report: dict[str, Any], signals: list[str], errors: list[str]) -> tuple[str, float]:
    signal_set = set(signals)
    if errors and not quality_report.get("usable"):
        return "network_or_fetch_error", 0.72
    if "dynamic_shell" in signal_set or "script_or_app_shell" in signal_set:
        return "dynamic_shell", 0.88
    if "access_gate" in signal_set or "blocked_or_login_marker" in signal_set:
        return "access_gate", 0.9
    if "search_fallback_only" in signal_set:
        return "search_fallback_only", 0.86
    if quality_report.get("usable"):
        return "readable_article", 0.84
    if "thin_body" in signal_set:
        return "thin_or_noisy_body", 0.68
    return "unknown_weak_page", 0.55


def _recommended_commands(url: str, page_type: str, signals: list[str]) -> list[str]:
    domain = urlparse(url).netloc.lower()
    commands: list[str] = []
    symbol = _extract_stock_symbol(url)
    if "finance_dynamic_candidate" in signals or "finance_social_page" in signals:
        if symbol:
            commands.append(f'guanlan stock detail "{symbol}"')
            commands.append(f'guanlan stock fundflow "{symbol}"')
        commands.append('guanlan search "公司 公告 财报 风险" --scope finance_disclosure --limit 80 --trace')
    if page_type in {"dynamic_shell", "access_gate", "search_fallback_only", "network_or_fetch_error"}:
        if domain:
            commands.append(f'guanlan search "关键词" --site {domain} --limit 80 --trace')
        commands.append(f'guanlan read "{url}" --backend direct --extract metadata')
        commands.append('guanlan route "原始研究问题" --json')
    elif page_type == "readable_article":
        commands.append(f'guanlan read "{url}" --quality-report')
        commands.append(f'guanlan archive add "{url}"')
    else:
        commands.append(f'guanlan read "{url}" --strict --trace')
        commands.append('guanlan research "原始研究问题" --limit 80 --read-top 3')
    return _unique(commands)[:6]


def _boundaries(page_type: str) -> list[str]:
    common = ["页面诊断只判断当前读取样本，不代表站点整体可用性。"]
    if page_type == "readable_article":
        return common + ["当前正文可作为证据摘读，但仍应核对来源身份、时间戳和上下文。"]
    if page_type == "search_fallback_only":
        return common + ["搜索兜底只能作为继续核验线索，不能冒充原网页正文。"]
    if page_type in {"dynamic_shell", "access_gate"}:
        return common + ["不要反复重试动态页或登录墙；优先改用结构化数据、官方披露源或垂直入口。"]
    return common + ["如果仍需该页正文，应先说明缺口，再考虑用户显式授权的只读辅助读取。"]


def _authorization_policy(page_type: str) -> list[str]:
    if page_type in {"dynamic_shell", "access_gate"}:
        return [
            "默认不读取 Cookie、钥匙串或浏览器登录态。",
            "如必须使用浏览器辅助，只能在用户显式授权后进行只读读取。",
            "遇到登录、验证码、支付、私信、交易或写操作入口时停止。",
        ]
    return ["默认只读；不执行发布、评论、点赞、私信、交易等写操作。"]


def _looks_finance_url(url: str) -> bool:
    domain = urlparse(url).netloc.lower()
    return any(
        item in domain
        for item in (
            "xueqiu.com",
            "eastmoney.com",
            "finance.sina.com.cn",
            "10jqka.com.cn",
            "quote.",
            "finance.qq.com",
        )
    )


def _extract_stock_symbol(url: str) -> str:
    match = re.search(r"\b(?:SH|SZ|BJ|sh|sz|bj)?(\d{6})\b", url)
    if not match:
        return ""
    code = match.group(1)
    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}{code}"


def _normalize_url(url: str) -> str:
    clean = str(url or "").strip()
    if clean and not clean.startswith(("http://", "https://")):
        return "https://" + clean
    return clean


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output
