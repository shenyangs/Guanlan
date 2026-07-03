# -*- coding: utf-8 -*-
"""Read implementation for Guanlan web primitives.

This module owns the public read entrypoints while reusing the lower-level
network, cache, and parser helpers that still live in ``guanlan.web._impl``.
The import of ``_impl`` is lazy to keep module initialization acyclic.
"""

from __future__ import annotations

import concurrent.futures
import difflib
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

from guanlan.limits import DEFAULT_READ_FALLBACK_LIMIT


def _base():
    from guanlan.web import _impl

    return _impl


def read_url(
    url: str,
    max_chars: int | None = None,
    backend: str = "auto",
    fallback_search: bool = False,
    fallback_limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
    cache_ttl: int = 0,
    use_cache: bool = True,
    watch: bool = False,
    strict: bool = False,
    extract: str = "article",
) -> str:
    """Read a URL with Jina/direct fallbacks and optional search context."""
    return str(
        read_url_with_trace(
            url,
            max_chars=max_chars,
            backend=backend,
            fallback_search=fallback_search,
            fallback_limit=fallback_limit,
            profile=profile,
            cache_ttl=cache_ttl,
            use_cache=use_cache,
            watch=watch,
            strict=strict,
            extract=extract,
        )["content"]
    )


def read_url_with_trace(
    url: str,
    max_chars: int | None = None,
    backend: str = "auto",
    fallback_search: bool = False,
    fallback_limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
    cache_ttl: int = 0,
    use_cache: bool = True,
    watch: bool = False,
    strict: bool = False,
    extract: str = "article",
) -> dict[str, Any]:
    """Read a URL and return content plus backend/quality trace."""
    base = _base()
    url = url.strip()
    if not url:
        raise ValueError("url is required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    original_url = url
    request_url = _request_safe_url(url)

    cache_key = ""
    extract = (extract or "article").lower()
    if extract not in {"article", "text", "metadata", "links"}:
        raise ValueError("extract must be one of: article, text, metadata, links")

    if cache_ttl and cache_ttl > 0 and use_cache and not watch:
        cache_key = base._cache_key(
            "read",
            {
                "url": request_url,
                "max_chars": max_chars or 0,
                "backend": backend,
                "fallback_search": fallback_search,
                "fallback_limit": fallback_limit,
                "profile": profile or "",
                "strict": strict,
                "extract": extract,
            },
        )
        cached = base._cache_get("read", cache_key, ttl=cache_ttl)
        if cached is not None:
            text = str(cached.get("text", ""))
            quality = assess_read_quality(text)
            packet = {
                "url": url,
                "content": text,
                "quality": quality,
                "trace": {
                    "backend": backend,
                    "selected_backend": str(cached.get("selected_backend") or "cache"),
                    "strict": bool(strict),
                    "extract": extract,
                    "cache": "hit",
                    "cache_key": cache_key,
                    "attempts": list(cached.get("attempts") or []),
                    "fallback_search": False,
                    "source_chars": int(cached.get("source_chars") or len(text)),
                    "returned_chars": len(text),
                    "max_chars": int(max_chars or 0),
                    "content_truncated": bool(cached.get("content_truncated")),
                },
            }
            packet["quality_report"] = build_read_quality_report(
                text,
                url=url,
                quality=quality,
                trace=packet["trace"],
            )
            return _attach_read_evidence(packet)

    backend = (backend or "auto").lower()
    errors: list[str] = []
    attempts: list[dict[str, Any]] = []
    text = ""
    weak_text = ""
    selected_backend = ""
    prefer_direct = extract in {"metadata", "links"}
    if backend in ("auto", "direct") and extract in {"article", "text"} and base._is_wechat_article_url(request_url):
        try:
            candidate = base._read_wechat_article(request_url)
            candidate_quality = assess_read_quality(candidate)
            if backend == "auto" and base._read_should_fallback(candidate_quality, strict=strict):
                errors.append("wechat_article: weak or blocked content")
                weak_text = weak_text or candidate
                attempts.append(
                    {
                        "backend": "wechat_article",
                        "status": "weak",
                        "chars": len(candidate),
                        "quality": candidate_quality,
                    }
                )
            else:
                text = candidate
                selected_backend = "wechat_article"
                attempts.append(
                    {
                        "backend": "wechat_article",
                        "status": "ok",
                        "chars": len(candidate),
                        "quality": candidate_quality,
                    }
                )
        except Exception as e:
            errors.append(f"wechat_article: {e}")
            attempts.append({"backend": "wechat_article", "status": "error", "error": str(e)})
            if backend == "direct":
                raise
    if not text and backend in ("auto", "jina") and not prefer_direct:
        try:
            candidate = base._read_with_jina(request_url)
            candidate_quality = assess_read_quality(candidate)
            if backend == "auto" and base._read_should_fallback(candidate_quality, strict=strict):
                errors.append("jina: weak or blocked content")
                weak_text = weak_text or candidate
                attempts.append(
                    {"backend": "jina", "status": "weak", "chars": len(candidate), "quality": candidate_quality}
                )
            else:
                text = candidate
                selected_backend = "jina"
                attempts.append(
                    {"backend": "jina", "status": "ok", "chars": len(candidate), "quality": candidate_quality}
                )
        except Exception as e:
            errors.append(f"jina: {e}")
            attempts.append({"backend": "jina", "status": "error", "error": str(e)})
            if backend == "jina":
                raise
    if not text and backend in ("auto", "direct"):
        try:
            candidate = base._call_read_direct(request_url, extract=extract)
            candidate_quality = assess_read_quality(candidate)
            if backend == "auto" and base._read_should_fallback(candidate_quality, strict=strict):
                errors.append("direct: weak or blocked content")
                weak_text = weak_text or candidate
                attempts.append(
                    {"backend": "direct", "status": "weak", "chars": len(candidate), "quality": candidate_quality}
                )
            else:
                text = candidate
                selected_backend = "direct"
                attempts.append(
                    {"backend": "direct", "status": "ok", "chars": len(candidate), "quality": candidate_quality}
                )
        except Exception as e:
            errors.append(f"direct: {e}")
            attempts.append({"backend": "direct", "status": "error", "error": str(e)})
            if backend == "direct":
                raise
    fallback_used = False
    if not text and fallback_search and backend == "auto" and not strict:
        try:
            text = _read_search_context(original_url, errors=errors, limit=fallback_limit, profile=profile)
            selected_backend = "search_fallback"
            fallback_used = True
            attempts.append(
                {
                    "backend": "search_fallback",
                    "status": "ok",
                    "chars": len(text),
                    "quality": assess_read_quality(text),
                }
            )
        except Exception as e:
            errors.append(f"search_context: {e}")
            attempts.append({"backend": "search_fallback", "status": "error", "error": str(e)})
    if not text and weak_text:
        text = weak_text
        selected_backend = selected_backend or "weak_fallback"
    if not text and errors:
        raise RuntimeError("; ".join(errors))
    source_chars = len(text)
    content_truncated = bool(max_chars and max_chars > 0 and source_chars > max_chars)
    if content_truncated:
        text = text[:max_chars]
    if watch:
        text = _format_read_watch(url, text)
        selected_backend = "watch"
    quality = assess_read_quality(text)
    trace_payload = {
        "backend": backend,
        "selected_backend": selected_backend or backend,
        "strict": bool(strict),
        "extract": extract,
        "cache": "miss" if cache_key else "disabled",
        "cache_key": cache_key,
        "attempts": attempts,
        "errors": errors,
        "fallback_search": fallback_used,
        "source_chars": source_chars,
        "returned_chars": len(text),
        "max_chars": int(max_chars or 0),
        "content_truncated": content_truncated,
    }
    if request_url != original_url:
        trace_payload["request_url"] = request_url
    if cache_key:
        base._cache_set(
            "read",
            cache_key,
            {
                "text": text,
                "selected_backend": selected_backend or backend,
                "attempts": attempts,
                "source_chars": source_chars,
                "content_truncated": content_truncated,
            },
        )
    packet = {"url": original_url, "content": text, "quality": quality, "trace": trace_payload}
    packet["quality_report"] = build_read_quality_report(text, url=original_url, quality=quality, trace=trace_payload)
    return _attach_read_evidence(packet)


def _attach_read_evidence(packet: dict[str, Any]) -> dict[str, Any]:
    from guanlan.read_evidence import build_read_evidence, build_structured_page
    from guanlan.web_backend_contract import attach_read_contract

    content = str(packet.get("content") or "")
    structured = build_structured_page(content, url=str(packet.get("url") or ""))
    packet["structured"] = structured
    attach_read_contract(packet)
    packet["read_evidence"] = build_read_evidence(read_packet=packet, content=content)
    return packet


def assess_read_quality(text: str) -> dict[str, Any]:
    """Return a lightweight readability/noise score for extracted content."""
    base = _base()
    normalized = base._collapse_ws(text or "")
    noise_terms = (
        "登录",
        "注册",
        "广告",
        "客户端下载",
        "打开APP",
        "推荐阅读",
        "相关阅读",
        "上一篇",
        "下一篇",
        "发表评论",
        "版权声明",
        "行情中心",
        "数据加载中",
        "自选股",
        "沪深京",
        "客户端下载",
    )
    noise_hits = [term for term in noise_terms if term.lower() in normalized.lower()]
    cjk_chars = sum(1 for char in normalized if "\u4e00" <= char <= "\u9fff")
    mojibake = base._looks_mojibake(normalized)
    fallback = normalized.startswith("# 观澜阅读兜底")
    line_count = len([line for line in (text or "").splitlines() if line.strip()])
    avg_line_len = round(len(normalized) / max(line_count, 1), 1)
    noise_ratio = round(len(noise_hits) / max(line_count, 1), 3)
    weak = (
        len(normalized) < base._MIN_USEFUL_READ_CHARS
        or mojibake
        or any(marker in normalized.lower() for marker in base._WEAK_READ_MARKERS)
    )
    score = 100
    if fallback:
        score -= 25
    if weak:
        score -= 45
    if mojibake:
        score -= 35
    score -= min(len(noise_hits) * 8, 32)
    if cjk_chars < 80 and _contains_cjk(normalized):
        score -= 12
    score = max(score, 0)
    if fallback:
        label = "fallback"
    elif weak:
        label = "weak"
    elif noise_hits:
        label = "noisy"
    else:
        label = "clean"
    strict_pass = bool(
        label == "clean" and score >= 70
        or (
            label == "noisy"
            and score >= 70
            and len(normalized) >= 500
            and noise_ratio <= 0.15
            and not mojibake
        )
    )
    return {
        "label": label,
        "score": score,
        "chars": len(normalized),
        "cjk_chars": cjk_chars,
        "noise_hits": noise_hits,
        "mojibake": mojibake,
        "weak": weak,
        "fallback": fallback,
        "line_count": line_count,
        "avg_line_len": avg_line_len,
        "noise_ratio": noise_ratio,
        "strict_pass": strict_pass,
    }


def build_read_quality_report(
    text: str,
    *,
    url: str = "",
    quality: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable read-quality payload for CLI, research, and archive."""
    base = _base()
    quality = dict(quality or assess_read_quality(text))
    trace = dict(trace or {})
    normalized = text or ""
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    short_lines = sum(1 for line in lines if len(base._collapse_ws(line)) <= 18)
    link_like_lines = sum(
        1 for line in lines if re.search(r"https?://|阅读原文|点击|打开APP|下载", line, flags=re.I)
    )
    body_ratio = round(
        max(0.0, 1.0 - min(quality.get("noise_ratio", 0) * 3 + link_like_lines / max(len(lines), 1), 0.95)),
        3,
    )
    blocked_markers = [marker for marker in base._WEAK_READ_MARKERS if marker in base._collapse_ws(normalized).lower()]
    dynamic_shell = _looks_like_dynamic_finance_shell(
        normalized,
        url=url,
        quality=quality,
        body_ratio=body_ratio,
    )
    fallback = bool(quality.get("fallback"))
    usable = bool(
        quality.get("score", 0) >= 55
        and quality.get("chars", 0) >= 160
        and not blocked_markers
        and not dynamic_shell
        and not fallback
    )
    recommendations: list[str] = []
    if quality.get("fallback"):
        recommendations.append("当前内容来自搜索兜底，只能作为线索，建议补读原文或更稳定转载页。")
    if blocked_markers:
        recommendations.append("疑似登录墙/安全验证/访问限制，建议改用公开转载、官方来源或人工授权后的平台能力。")
    if quality.get("noise_hits"):
        recommendations.append("正文中仍有导航、登录或推荐阅读噪音，回答时优先引用连续正文段落。")
    if dynamic_shell:
        recommendations.append(
            "疑似动态财经页壳或行情入口，正文不可直接作为事实证据；建议改用 `guanlan stock ...` "
            "结构化行情、公告/监管源或可导出的数据页补证。"
        )
    if quality.get("chars", 0) < 500:
        recommendations.append("正文较短，可能只读到摘要或页面片段，建议扩大 read 或补充 search/research。")
    if not recommendations:
        recommendations.append("正文可用度较好，可作为证据摘读；仍建议和搜索结果中的来源身份交叉验证。")
    return {
        "url": url,
        "label": quality.get("label", "unknown"),
        "score": quality.get("score", 0),
        "usable": usable,
        "fallback": fallback,
        "body_ratio": body_ratio,
        "chars": quality.get("chars", 0),
        "cjk_chars": quality.get("cjk_chars", 0),
        "line_count": quality.get("line_count", 0),
        "avg_line_len": quality.get("avg_line_len", 0),
        "short_line_count": short_lines,
        "link_like_line_count": link_like_lines,
        "noise_hits": quality.get("noise_hits", []),
        "blocked_markers": blocked_markers,
        "dynamic_shell": dynamic_shell,
        "selected_backend": trace.get("selected_backend", ""),
        "cache": trace.get("cache", "disabled"),
        "recommendations": recommendations,
    }


def format_read_quality_report(report_or_packet: dict[str, Any]) -> str:
    """Render a read quality report as compact Markdown."""
    report = dict(report_or_packet.get("quality_report") or report_or_packet)
    lines = [
        "## 阅读质量报告",
        f"- label: {report.get('label', 'unknown')} score={report.get('score', 0)} usable={report.get('usable', False)}",
        f"- chars: {report.get('chars', 0)} cjk={report.get('cjk_chars', 0)} lines={report.get('line_count', 0)} body_ratio={report.get('body_ratio', 0)}",
        f"- backend/cache: {report.get('selected_backend', '') or '-'} / {report.get('cache', 'disabled')}",
    ]
    noise = report.get("noise_hits") or []
    if noise:
        lines.append(f"- noise: {', '.join(str(item) for item in noise)}")
    blocked = report.get("blocked_markers") or []
    if blocked:
        lines.append(f"- blocked_markers: {', '.join(str(item) for item in blocked)}")
    if report.get("dynamic_shell"):
        lines.append("- dynamic_shell: true")
    if report.get("fallback"):
        lines.append("- fallback: search_context_only")
    recommendations = report.get("recommendations") or []
    if recommendations:
        lines.append("- 建议:")
        lines.extend(f"  - {item}" for item in recommendations[:4])
    return "\n".join(lines)


def _looks_like_dynamic_finance_shell(
    text: str,
    *,
    url: str,
    quality: dict[str, Any],
    body_ratio: float,
) -> bool:
    base = _base()
    domain = base._domain(url)
    if domain not in {
        "quote.eastmoney.com",
        "eastmoney.com",
        "finance.sina.com.cn",
        "xueqiu.com",
        "guba.eastmoney.com",
        "10jqka.com.cn",
        "cn.investing.com",
        "finance.yahoo.com",
        "nasdaq.com",
    }:
        return False
    normalized = base._collapse_ws(text).lower()
    markers = (
        "行情中心",
        "自选股",
        "沪深京",
        "数据加载中",
        "客户端下载",
        "打开app",
        "stock quote",
        "market activity",
        "portfolio",
        "系统检测到您的ip",
        "访问过于频繁",
        "请验证以继续访问",
        "upgrade_browser",
        "window.location.href",
        "galileotelemetry",
        "new aegis",
        "公司概况",
        "股权信息",
        "股票交易",
    )
    marker_hits = sum(1 for marker in markers if marker.lower() in normalized)
    if domain == "xueqiu.com" and any(marker.lower() in normalized for marker in ("访问过于频繁", "请验证以继续访问")):
        return True
    if any(marker in normalized for marker in ("upgrade_browser", "galileotelemetry", "window.location.href")):
        return True
    weak_size = int(quality.get("chars") or 0) < 900
    noisy_shape = body_ratio < 0.45 or int(quality.get("line_count") or 0) < 8
    return bool(marker_hits >= 2 and (weak_size or noisy_shape))


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text or "")


def _request_safe_url(url: str) -> str:
    """Percent-encode non-ASCII URL parts before urllib sees the request."""

    parsed = urllib.parse.urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    try:
        host = parsed.hostname.encode("idna").decode("ascii") if parsed.hostname else ""
    except UnicodeError:
        host = parsed.hostname or ""
    auth = ""
    if parsed.username:
        auth = urllib.parse.quote(parsed.username, safe="")
        if parsed.password:
            auth += ":" + urllib.parse.quote(parsed.password, safe="")
        auth += "@"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{auth}{host}{port}"
    path = urllib.parse.quote(parsed.path or "", safe="/%:@!$&'()*+,;=")
    query = urllib.parse.quote(parsed.query or "", safe="/%:@!$&'()*+,;=?")
    fragment = urllib.parse.quote(parsed.fragment or "", safe="/%:@!$&'()*+,;=?")
    return urllib.parse.urlunsplit((parsed.scheme, netloc, path, query, fragment))


def read_batch(
    urls: list[str],
    max_chars: int | None = None,
    backend: str = "auto",
    fallback_search: bool = True,
    fallback_limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
    cache_ttl: int = 0,
    strict: bool = False,
    extract: str = "article",
    concurrency: int = 1,
) -> list[dict[str, Any]]:
    """Read multiple URLs with per-item errors kept in the result list."""
    records: list[dict[str, Any]] = []
    jobs: list[tuple[int, str]] = []
    for idx, url in enumerate(urls, start=1):
        clean_url = url.strip()
        if not clean_url:
            continue
        blocked_reason = _batch_block_reason(clean_url)
        if blocked_reason:
            records.append({"rank": idx, "url": clean_url, "status": "blocked", "error": blocked_reason})
            continue
        jobs.append((idx, clean_url))

    def read_one(job: tuple[int, str]) -> dict[str, Any]:
        idx, clean_url = job
        try:
            content = _base().read_url(
                clean_url,
                max_chars=max_chars,
                backend=backend,
                fallback_search=fallback_search,
                fallback_limit=fallback_limit,
                profile=profile,
                cache_ttl=cache_ttl,
                strict=strict,
                extract=extract,
            )
            return {"rank": idx, "url": clean_url, "status": "ok", "content": content}
        except Exception as e:
            return {"rank": idx, "url": clean_url, "status": "error", "error": str(e)}

    workers = max(1, min(int(concurrency or 1), 8))
    if workers == 1 or len(jobs) <= 1:
        records.extend(read_one(job) for job in jobs)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            records.extend(executor.map(read_one, jobs))
        for item in records:
            item["concurrency"] = workers
    records.sort(key=lambda item: int(item.get("rank") or 0))
    return records


def _batch_block_reason(url: str) -> str:
    base = _base()
    domain = base._domain(url if url.startswith(("http://", "https://")) else "https://" + url)
    blocked_domains = {
        "xiaohongshu.com": "xiaohongshu",
        "xhslink.com": "xiaohongshu",
        "weibo.com": "weibo",
        "m.weibo.cn": "weibo",
        "twitter.com": "twitter",
        "x.com": "twitter",
        "linkedin.com": "linkedin",
        "douyin.com": "douyin",
    }
    for suffix, channel in blocked_domains.items():
        if domain == suffix or domain.endswith("." + suffix):
            return (
                f"batch read is disabled for {channel}; use explicit single reads or platform tools "
                "after user authorization"
            )
    return ""


def _read_search_context(
    url: str,
    errors: list[str] | None = None,
    limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
) -> str:
    """Build a search-based context packet when direct reading fails."""
    base = _base()
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    query = base._query_from_url(url)
    raw_results = base.search_web(
        query,
        limit=max(limit, 1),
        site=domain or None,
        profile=profile,
    )
    results = _filter_read_fallback_results(raw_results, url)
    if not results and domain:
        raw_results = base.search_web(f"{domain} {query}", limit=max(limit, 1), profile=profile)
        results = _filter_read_fallback_results(raw_results, url)

    lines = [
        "# 观澜阅读兜底",
        "",
        f"原始 URL: {url}",
        "",
        "说明: 原文读取失败或正文疑似不完整，以下内容来自公开搜索结果，适合作为继续核验的线索，不等同于原文全文。",
    ]
    if errors:
        lines.extend(["", "读取问题:"])
        lines.extend(f"- {err}" for err in errors)
    if base._url_path_is_weak_identity(url) and not results:
        lines.extend(
            [
                "",
                "兜底状态: unusable",
                "原因: URL 只有数字路径或弱身份信息，公开搜索未能确认同一页面；为避免把无关结果包装成原文上下文，本次不输出搜索兜底结果。",
                "给 Agent: 不要引用本页搜索兜底作为证据。请改用 `guanlan diagnose page \"URL\"`、站内结构化入口，或按 external_fetch_strategy 使用宿主 WebFetch 定点读取该 URL。",
            ]
        )
        return "\n".join(lines)
    lines.extend(["", base.format_search_markdown(results, title=f"观澜搜索兜底 / {query}")])
    return "\n".join(lines)


def _filter_read_fallback_results(results: list[dict[str, Any]], url: str) -> list[dict[str, Any]]:
    """Keep fallback search context only when it can identify the target page."""
    base = _base()
    if not base._url_path_is_weak_identity(url):
        return list(results)
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    identity = base._url_identity_parts(url)
    target_path = identity.get("path", "")
    compact = identity.get("compact", "")
    tail = identity.get("tail", "")
    kept: list[dict[str, Any]] = []
    for item in results:
        item_url = str(item.get("url") or "")
        item_domain = base._domain(item_url)
        if domain and item_domain != domain:
            continue
        normalized_url = urllib.parse.unquote(item_url).lower()
        if target_path and target_path.lower() in normalized_url:
            kept.append(item)
            continue
        if compact and compact in re.sub(r"\D+", "", normalized_url):
            kept.append(item)
            continue
        if tail and re.search(rf"(?:/|-|_){re.escape(tail)}(?:\\.|/|$)", normalized_url):
            kept.append(item)
    return kept


def _snapshot_path(url: str) -> Path:
    base = _base()
    key = base._cache_key("snapshot", {"url": url})
    return base.cache_dir() / "snapshots" / f"{key}.json"


def _format_read_watch(url: str, text: str) -> str:
    """Compare current read content with the saved local snapshot."""
    path = _snapshot_path(url)
    saved_text = ""
    if path.exists():
        try:
            saved_text = str(json.loads(path.read_text(encoding="utf-8")).get("text", ""))
        except Exception:
            saved_text = ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"url": url, "updated_at": time.time(), "text": text}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not saved_text:
        return "\n".join(
            [
                "# 观澜内容追踪",
                "",
                f"URL: {url}",
                "状态: 已保存首次快照，后续再次运行会输出 diff。",
                "",
                text,
            ]
        )
    if saved_text == text:
        return "\n".join(["# 观澜内容追踪", "", f"URL: {url}", "状态: 未发现内容变化。"])
    diff = difflib.unified_diff(
        saved_text.splitlines(),
        text.splitlines(),
        fromfile="saved",
        tofile="current",
        lineterm="",
    )
    return "\n".join(["# 观澜内容追踪", "", f"URL: {url}", "状态: 发现内容变化。", "", "```diff", *diff, "```"])


__all__ = [
    "assess_read_quality",
    "build_read_quality_report",
    "format_read_quality_report",
    "read_batch",
    "read_url",
    "read_url_with_trace",
]
