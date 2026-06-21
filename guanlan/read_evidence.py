# -*- coding: utf-8 -*-
"""Canonical read evidence records for Guanlan representative pages."""

from __future__ import annotations

import re
import shlex
import urllib.parse
from typing import Any

READ_EVIDENCE_SCHEMA_VERSION = "read_evidence_v1"
READ_PACK_SCHEMA_VERSION = "representative_read_pack_v1"
DEFAULT_CONTENT_PREVIEW_CHARS = 280


def build_structured_page(
    content: str,
    *,
    url: str = "",
    title: str = "",
    source: str = "",
) -> dict[str, Any]:
    """Extract stable, low-risk structure from already-read public page text."""

    text = str(content or "")
    clean = _collapse_ws(text)
    headings = _extract_headings(text)
    derived_title = title.strip() or _extract_title(text, clean=clean)
    author = _first_regex(
        text,
        [
            r"(?:作者|撰文|编辑|Author|By)\s*[:：]\s*([^\n\r]{2,80})",
            r"\bBy\s+([A-Z][^\n\r]{2,80})",
        ],
    )
    published_at = _first_regex(
        text,
        [
            r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:\s+\d{1,2}:\d{2})?)",
            r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日(?:\s*\d{1,2}:\d{2})?)",
            r"((?:20|19)\d{2}\s*/\s*\d{1,2}\s*/\s*\d{1,2})",
        ],
    )
    links = _extract_links(text)
    list_samples = _extract_list_samples(text)
    table_rows = _extract_table_rows(text)
    language = _detect_language(clean)
    confidence = _structured_confidence(
        title=derived_title,
        published_at=published_at,
        headings=headings,
        links=links,
        content=clean,
    )
    return {
        "title": derived_title,
        "author": _clean_metadata(author),
        "published_at": _clean_metadata(published_at),
        "site_name": source.strip() or _domain(url),
        "language": language,
        "headings": headings[:12],
        "important_links": links[:12],
        "lists": {
            "count": len(list_samples),
            "samples": list_samples[:8],
        },
        "tables": {
            "row_count": len(table_rows),
            "samples": table_rows[:6],
        },
        "confidence": confidence,
    }


def build_read_evidence(
    item: dict[str, Any] | None = None,
    *,
    read_packet: dict[str, Any] | None = None,
    content: str | None = None,
    error: str = "",
    status: str = "",
    source: str = "",
    evidence_role: str = "",
    include_content: bool = True,
    content_preview_chars: int = DEFAULT_CONTENT_PREVIEW_CHARS,
) -> dict[str, Any]:
    """Wrap a read result into the stable ``read_evidence_v1`` shape."""

    item = dict(item or {})
    read_packet = dict(read_packet or {})
    url = str(read_packet.get("url") or item.get("url") or "").strip()
    text = str(content if content is not None else read_packet.get("content") or "")
    trace = dict(read_packet.get("trace") or {})
    quality = dict(read_packet.get("quality") or {})
    quality_report = dict(read_packet.get("quality_report") or {})
    selected_backend = str(trace.get("selected_backend") or trace.get("backend") or "")
    source_value = (
        source
        or item.get("source")
        or item.get("source_name")
        or item.get("origin")
        or item.get("domain")
        or _domain(url)
    )
    source_type = str(item.get("source_type") or item.get("source_tier") or item.get("origin") or "")
    role = evidence_role or item.get("evidence_role") or item.get("role") or ""
    structured = dict(read_packet.get("structured") or {})
    if not structured:
        structured = build_structured_page(
            text,
            url=url,
            title=str(item.get("title") or read_packet.get("title") or ""),
            source=str(source_value or ""),
        )
    title = str(item.get("title") or structured.get("title") or _title_from_url(url)).strip()
    usable = bool(quality_report.get("usable")) and bool(text.strip()) and not error
    normalized_status = _normalize_status(
        status=status,
        usable=usable,
        content=text,
        error=error or str(read_packet.get("error") or ""),
    )
    content_chars = len(_collapse_ws(text))
    preview = _content_preview(text, max_chars=content_preview_chars)
    record: dict[str, Any] = {
        "schema_version": READ_EVIDENCE_SCHEMA_VERSION,
        "url": url,
        "title": title,
        "source": str(source_value or ""),
        "source_type": source_type,
        "domain": _domain(url),
        "evidence_role": str(role or ""),
        "status": normalized_status,
        "read_status": normalized_status,
        "usable": usable,
        "content": text if include_content else "",
        "content_preview": preview,
        "content_chars": content_chars,
        "chars": content_chars,
        "quality_report": quality_report,
        "read_quality": quality,
        "selected_backend": selected_backend,
        "structured": structured,
        "boundary": _evidence_boundary(normalized_status, usable),
    }
    if error or read_packet.get("error"):
        record["error"] = str(error or read_packet.get("error") or "")
    if quality_report:
        record["score"] = int(quality_report.get("score") or 0)
        record["label"] = str(quality_report.get("label") or "")
    return record


def build_representative_read_pack(
    items: list[dict[str, Any]],
    *,
    read_top: int,
    read_backend: str = "auto",
    max_read_chars: int = 4000,
    profile: str = "china",
    cache_ttl: int = 0,
    fallback_search: bool = False,
    source: str = "",
    max_read_top: int = 5,
    include_content: bool = True,
    content_preview_chars: int = DEFAULT_CONTENT_PREVIEW_CHARS,
) -> dict[str, Any]:
    """Read a small, representative URL set and return a canonical pack."""

    requested = _bounded_int(read_top, 0, max_read_top)
    max_chars = _bounded_int(max_read_chars, 1, 50_000)
    candidates = select_representative_read_candidates(items, requested)
    readings: list[dict[str, Any]] = []
    if requested > 0:
        from guanlan.web.read import read_url_with_trace

        for item in candidates[:requested]:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            try:
                packet = read_url_with_trace(
                    url,
                    max_chars=max_chars,
                    backend=read_backend or "auto",
                    fallback_search=fallback_search,
                    profile=profile or "china",
                    cache_ttl=max(int(cache_ttl or 0), 0),
                    use_cache=bool(cache_ttl and cache_ttl > 0),
                )
                readings.append(
                    build_read_evidence(
                        item,
                        read_packet=packet,
                        source=str(item.get("source") or source or ""),
                        include_content=include_content,
                        content_preview_chars=content_preview_chars,
                    )
                )
            except Exception as exc:  # pragma: no cover - network failures vary
                readings.append(
                    build_read_evidence(
                        item,
                        content="",
                        error=_short_error(exc),
                        status="error",
                        source=str(item.get("source") or source or ""),
                        include_content=include_content,
                        content_preview_chars=content_preview_chars,
                    )
                )
    summary = summarize_read_evidence(readings, requested=requested)
    next_commands = _next_read_commands(items, skip_urls={row.get("url", "") for row in readings}, limit=3)
    summary["next_read_commands"] = next_commands
    pack = {
        "schema_version": READ_PACK_SCHEMA_VERSION,
        "source": source or "",
        "requested": requested,
        "attempted": len(readings),
        "read_backend": read_backend or "auto",
        "max_read_chars": max_chars,
        "profile": profile or "china",
        "readings": readings,
        "summary": summary,
        "usable_count": summary["usable_count"],
        "weak_count": summary["weak_count"],
        "error_count": summary["error_count"],
        "next_read_commands": next_commands,
        "boundary": (
            "代表页证据包只把 usable=true 的已读正文作为可引用事实；未读 URL 仍只是入口线索。"
        ),
    }
    pack["agent_followup"] = build_read_pack_agent_followup(pack)
    return pack


def select_representative_read_candidates(
    items: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Select high-quality, domain-diverse candidate pages for representative reads."""

    if limit <= 0:
        return []
    scored: list[tuple[float, int, dict[str, Any]]] = []
    seen_urls: set[str] = set()
    for order, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        score = _candidate_score(item, order=order)
        scored.append((score, order, item))
    scored.sort(key=lambda row: (-row[0], row[1], str(row[2].get("url") or "")))
    selected: list[dict[str, Any]] = []
    seen_domains: set[str] = set()
    for _score, _order, item in scored:
        domain = _domain(str(item.get("url") or ""))
        if domain and domain in seen_domains and len(scored) > limit:
            continue
        selected.append(item)
        if domain:
            seen_domains.add(domain)
        if len(selected) >= limit:
            return selected
    for _score, _order, item in scored:
        url = str(item.get("url") or "")
        if any(str(row.get("url") or "") == url for row in selected):
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def summarize_read_evidence(readings: list[dict[str, Any]], *, requested: int | None = None) -> dict[str, Any]:
    """Return a compact status summary for read evidence rows."""

    status_counts: dict[str, int] = {}
    for row in readings:
        status = str(row.get("status") or row.get("read_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    usable_count = sum(1 for row in readings if row.get("usable"))
    error_count = status_counts.get("error", 0)
    weak_count = sum(1 for row in readings if not row.get("usable") and str(row.get("status")) != "error")
    return {
        "requested": len(readings) if requested is None else requested,
        "attempted": len(readings),
        "usable_count": usable_count,
        "weak_count": weak_count,
        "error_count": error_count,
        "status_counts": status_counts,
    }


def build_read_pack_agent_followup(pack: dict[str, Any]) -> dict[str, Any]:
    """Create the short agent follow-up contract for a read pack."""

    summary = dict(pack.get("summary") or {})
    attempted = int(summary.get("attempted") or pack.get("attempted") or 0)
    usable_count = int(summary.get("usable_count") or pack.get("usable_count") or 0)
    commands = [str(item) for item in pack.get("next_read_commands") or [] if str(item).strip()]
    if attempted and usable_count:
        return {
            "status": "ready_with_readings",
            "should_answer": True,
            "next_decision": "answer",
            "next_commands": commands[:3],
            "boundary": "只引用 read_pack.readings 中 usable=true 的已读正文；未读 URL 仍只是线索。",
        }
    if attempted:
        return {
            "status": "needs_followup",
            "should_answer": False,
            "next_decision": "repair",
            "next_commands": commands[:3],
            "boundary": "代表页读取不足，需要换代表页、诊断页面或补结构化来源后再引用事实。",
        }
    return {
        "status": "ready" if commands else "idle",
        "should_answer": False,
        "next_decision": "continue" if commands else "stop",
        "next_commands": commands[:3],
        "boundary": "当前只有 URL 入口；先读取代表页，usable=true 后才作为正文证据。",
    }


def _candidate_score(item: dict[str, Any], *, order: int) -> float:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("title", "url", "source", "source_type", "source_tier", "evidence_role", "origin", "topic_role")
    ).lower()
    score = 1000.0 - order
    if "representative" in text:
        score += 120
    if any(token in text for token in ("official", "官网", "公告", "gov", "regulator", "一手", "source_original")):
        score += 80
    if any(token in text for token in ("党央媒", "政府", "部委", "监管")):
        score += 55
    if any(token in text for token in ("vertical", "media", "新闻", "报道", "产业", "developer", "feed")):
        score += 45
    if any(token in text for token in ("community", "社区", "forum", "知乎", "微博", "bilibili")):
        score += 15
    if any(token in text for token in ("seo", "download", "mirror", "下载站", "镜像", "软文", "聚合")):
        score -= 180
    try:
        score += min(float(item.get("daily_score") or item.get("score") or 0.0), 100.0)
    except (TypeError, ValueError):
        pass
    return score


def _normalize_status(*, status: str, usable: bool, content: str, error: str) -> str:
    raw = str(status or "").strip().lower()
    if raw in {"ok", "weak", "error", "unusable", "skipped"}:
        return "ok" if raw == "ok" and usable else raw
    if error:
        return "error"
    if usable:
        return "ok"
    if content.strip():
        return "weak"
    return "unusable"


def _evidence_boundary(status: str, usable: bool) -> str:
    if usable and status == "ok":
        return "该页正文质量可用，可作为代表页证据引用。"
    if status == "error":
        return "该页读取出错，只能作为待补读入口，不能作为事实证据。"
    return "该页正文质量不足或信息不完整，只能作为弱线索，引用前需补证。"


def _next_read_commands(items: list[dict[str, Any]], *, skip_urls: set[str], limit: int) -> list[str]:
    commands: list[str] = []
    for item in items:
        url = str(item.get("url") or "").strip()
        if not url or url in skip_urls:
            continue
        commands.append(str(item.get("read_command") or f"guanlan read {shlex.quote(url)} --quality-report"))
        if len(commands) >= limit:
            break
    return commands


def _extract_title(text: str, *, clean: str) -> str:
    for line in text.splitlines()[:30]:
        value = line.strip()
        if not value:
            continue
        if value.lower().startswith(("title:", "# ")):
            return _clean_metadata(value.split(":", 1)[-1] if ":" in value else value.lstrip("# "))
        if len(value) <= 120 and not value.startswith(("-", "*", "|")):
            return _clean_metadata(value)
    return clean[:80].strip()


def _extract_headings(text: str) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append({"level": len(match.group(1)), "text": _clean_metadata(match.group(2))})
    return headings


def _extract_links(text: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for label, url in re.findall(r"\[([^\]]{0,120})]\((https?://[^)\s]+)\)", text):
        clean_url = url.strip()
        if clean_url in seen:
            continue
        seen.add(clean_url)
        links.append({"title": _clean_metadata(label), "url": clean_url})
    for url in re.findall(r"(?<!\()https?://[^\s)>\]]+", text):
        clean_url = url.rstrip("。,.，)")
        if clean_url in seen:
            continue
        seen.add(clean_url)
        links.append({"title": _title_from_url(clean_url), "url": clean_url})
    return links


def _extract_list_samples(text: str) -> list[str]:
    samples: list[str] = []
    for line in text.splitlines():
        value = line.strip()
        if re.match(r"^([-*+]|\d+[.)、])\s+", value):
            value = re.sub(r"^([-*+]|\d+[.)、])\s+", "", value).strip()
            if 4 <= len(value) <= 160:
                samples.append(_clean_metadata(value))
    return samples


def _extract_table_rows(text: str) -> list[str]:
    rows: list[str] = []
    for line in text.splitlines():
        value = line.strip()
        if value.count("|") >= 2 and not re.fullmatch(r"[-:\s|]+", value):
            rows.append(_clean_metadata(value))
    return rows


def _structured_confidence(
    *,
    title: str,
    published_at: str,
    headings: list[dict[str, Any]],
    links: list[dict[str, str]],
    content: str,
) -> str:
    score = 0
    if title:
        score += 1
    if published_at:
        score += 1
    if headings:
        score += 1
    if links:
        score += 1
    if len(content) >= 300:
        score += 1
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _first_regex(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _detect_language(text: str) -> str:
    if not text:
        return "unknown"
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk >= max(8, latin // 3):
        return "zh"
    if latin >= 20:
        return "en"
    return "unknown"


def _clean_metadata(value: str) -> str:
    return _collapse_ws(value).strip(" -_|#*：:")


def _content_preview(text: str, *, max_chars: int = DEFAULT_CONTENT_PREVIEW_CHARS) -> str:
    clean = _collapse_ws(str(text or ""))
    if len(clean) <= max_chars:
        return clean
    return clean[: max(0, max_chars - 3)].rstrip() + "..."


def _title_from_url(url: str) -> str:
    path = urllib.parse.urlsplit(url).path.strip("/")
    if not path:
        return _domain(url) or url
    tail = path.rsplit("/", 1)[-1]
    tail = urllib.parse.unquote(tail)
    return tail.replace("-", " ").replace("_", " ")[:80] or url


def _domain(url: str) -> str:
    return urllib.parse.urlsplit(str(url or "")).netloc.lower()


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _bounded_int(value: Any, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = low
    return min(max(number, low), high)


def _short_error(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:500]
