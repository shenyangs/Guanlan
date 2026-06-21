# -*- coding: utf-8 -*-
"""Public site URL discovery for follow-up Guanlan reads.

This module intentionally stays narrow: it discovers candidate URLs from
robots.txt sitemap hints, sitemap XML, and the target page's public links. It
does not execute page actions, crawl at scale, or treat discovered URLs as
evidence until `guanlan read` reads representative pages.
"""

from __future__ import annotations

import fnmatch
import html
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from guanlan.read_evidence import build_representative_read_pack

SCHEMA_VERSION = "site_map_v1"
USER_AGENT = "GuanlanSiteMap/1.0 (+https://guanlan.xin)"
MAX_FETCH_BYTES = 2_000_000
MAX_SITEMAPS = 12
MAX_READ_TOP = 5
DEFAULT_MAX_READ_CHARS = 4000


@dataclass
class _Candidate:
    url: str
    title: str = ""
    description: str = ""
    source: str = "unknown"
    lastmod: str = ""
    order: int = 0


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._current: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = {name.lower(): value or "" for name, value in attrs}
        href = values.get("href", "").strip()
        if not href:
            return
        self._current = {
            "href": href,
            "title": values.get("title", "").strip(),
            "text": [],
        }

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current is None:
            return
        text = _collapse_ws(" ".join(self._current.get("text") or []))
        self.links.append(
            {
                "href": str(self._current.get("href") or ""),
                "title": str(self._current.get("title") or ""),
                "text": text,
            }
        )
        self._current = None


def build_site_map(
    url: str,
    *,
    query: str = "",
    limit: int = 80,
    include_subdomains: bool = False,
    sitemap: str = "auto",
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    timeout: int = 8,
    read_top: int = 0,
    read_backend: str = "auto",
    max_read_chars: int = DEFAULT_MAX_READ_CHARS,
) -> dict[str, Any]:
    """Discover public candidate URLs inside a known site.

    Parameters are deliberately close to agent language. `sitemap` supports:
    `auto` (robots + default sitemap + page links), `only` (sitemaps only), and
    `skip` (page links only).
    """

    normalized_url = _normalize_input_url(url)
    origin = _origin(normalized_url)
    sitemap_mode = sitemap if sitemap in {"auto", "only", "skip"} else "auto"
    source_events: list[dict[str, Any]] = []
    candidates: list[_Candidate] = []

    if sitemap_mode in {"auto", "only"}:
        sitemap_urls = _discover_sitemaps(origin, timeout=timeout, source_events=source_events)
        candidates.extend(
            _collect_sitemap_candidates(
                sitemap_urls,
                timeout=timeout,
                source_events=source_events,
            )
        )

    if sitemap_mode in {"auto", "skip"}:
        candidates.extend(
            _collect_page_link_candidates(
                normalized_url,
                timeout=timeout,
                source_events=source_events,
            )
        )

    base_host = urllib.parse.urlsplit(normalized_url).netloc.lower()
    items = _filter_rank_candidates(
        candidates,
        base_host=base_host,
        query=query,
        limit=max(int(limit or 80), 1),
        include_subdomains=include_subdomains,
        include_patterns=include_patterns or [],
        exclude_patterns=exclude_patterns or [],
    )
    source_counts: dict[str, int] = {}
    for item in items:
        source_counts[item["source"]] = source_counts.get(item["source"], 0) + 1
    read_top_value = _bounded_int(read_top, 0, MAX_READ_TOP)
    max_read_chars_value = _bounded_int(max_read_chars, 1, 20_000)
    read_backend_value = _normalize_read_backend(read_backend)
    read_pack = build_representative_read_pack(
        items,
        read_top=read_top_value,
        read_backend=read_backend_value,
        max_read_chars=max_read_chars_value,
        source="site_map",
        max_read_top=MAX_READ_TOP,
    )
    readings = list(read_pack.get("readings") or [])
    read_summary = dict(read_pack.get("summary") or {})

    return {
        "schema_version": SCHEMA_VERSION,
        "url": normalized_url,
        "origin": origin,
        "query": query,
        "limit": max(int(limit or 80), 1),
        "include_subdomains": include_subdomains,
        "sitemap_mode": sitemap_mode,
        "read_top": read_top_value,
        "read_backend": read_backend_value,
        "max_read_chars": max_read_chars_value,
        "links": items,
        "readings": readings,
        "read_pack": read_pack,
        "summary": {
            "candidate_count": len(candidates),
            "returned_count": len(items),
            "filtered_out_count": max(len(candidates) - len(items), 0),
            "source_counts": source_counts,
        },
        "read_summary": read_summary,
        "sources": source_events,
        "boundary": "站点入口发现只说明这些公开 URL 值得继续读取；它不是正文证据，也不代表已完成全网搜索。",
        "agent_followup": read_pack.get("agent_followup") or {},
    }


def format_site_map_markdown(packet: dict[str, Any]) -> str:
    """Render a site map packet for humans and agents."""

    lines = [
        f"# 观澜站点入口 / {packet.get('url', '')}",
        "",
        f"> {packet.get('boundary', '')}",
        "",
    ]
    query = str(packet.get("query") or "")
    if query:
        lines.append(f"- 站内筛选词: `{query}`")
    lines.append(f"- 返回入口: {len(packet.get('links') or [])}")
    lines.append(f"- sitemap 模式: `{packet.get('sitemap_mode') or 'auto'}`")
    read_summary = dict(packet.get("read_summary") or {})
    if read_summary.get("attempted"):
        lines.append(
            f"- 已读代表页: {read_summary.get('usable_count', 0)}/{read_summary.get('attempted', 0)} 可用"
        )
    lines.append("")
    links = list(packet.get("links") or [])
    if not links:
        lines.append("未发现可用入口。可以换用 `--sitemap skip` 只看首页链接，或用 `guanlan search --site ...` 补公开搜索。")
        return "\n".join(lines)
    lines.append("## 候选入口")
    for idx, item in enumerate(links[: int(packet.get("limit") or 80)], start=1):
        title = item.get("title") or item.get("url") or "Untitled"
        lines.append(f"{idx}. [{title}]({item.get('url', '')})")
        details = [f"source={item.get('source')}", f"score={item.get('score')}"]
        if item.get("lastmod"):
            details.append(f"lastmod={item['lastmod']}")
        lines.append(f"   - {', '.join(str(part) for part in details if part)}")
        if item.get("description"):
            lines.append(f"   - {item['description']}")
        lines.append(f"   - read: `{item.get('read_command')}`")
    readings = list(packet.get("readings") or [])
    if readings:
        lines.extend(["", "## 已读代表页"])
        for idx, reading in enumerate(readings, start=1):
            title = reading.get("title") or reading.get("url") or "Untitled"
            lines.append(f"{idx}. [{title}]({reading.get('url', '')})")
            lines.append(
                "   - "
                + ", ".join(
                    [
                        f"status={reading.get('read_status')}",
                        f"usable={reading.get('usable')}",
                        f"backend={reading.get('selected_backend') or '-'}",
                        f"chars={reading.get('content_chars', 0)}",
                    ]
                )
            )
            if reading.get("error"):
                lines.append(f"   - error: {reading['error']}")
            preview = str(reading.get("content_preview") or "").strip()
            if preview:
                lines.append(f"   - 摘录: {preview}")
    followup = dict(packet.get("agent_followup") or {})
    commands = [str(item) for item in followup.get("next_commands") or [] if str(item).strip()]
    if commands:
        lines.extend(["", "## 下一步"])
        for command in commands:
            lines.append(f"- `{command}`")
    return "\n".join(lines)


def format_site_map_context(packet: dict[str, Any]) -> str:
    """Render a compact context block for downstream agents."""

    lines = [
        f"# 观澜站点入口上下文 / {packet.get('url', '')}",
        "",
        f"边界: {packet.get('boundary', '')}",
        "",
    ]
    for item in list(packet.get("links") or [])[: int(packet.get("limit") or 80)]:
        lines.append(f"- title: {item.get('title') or item.get('url')}")
        lines.append(f"  url: {item.get('url')}")
        lines.append(f"  source: {item.get('source')}")
        lines.append(f"  read_command: {item.get('read_command')}")
        if item.get("description"):
            lines.append(f"  note: {item.get('description')}")
    readings = list(packet.get("readings") or [])
    if readings:
        lines.extend(["", "## 已读代表页"])
        for reading in readings:
            lines.append(f"- title: {reading.get('title') or reading.get('url')}")
            lines.append(f"  url: {reading.get('url')}")
            lines.append(f"  usable: {reading.get('usable')}")
            lines.append(f"  read_status: {reading.get('read_status')}")
            lines.append(f"  selected_backend: {reading.get('selected_backend') or ''}")
            if reading.get("error"):
                lines.append(f"  error: {reading.get('error')}")
            preview = str(reading.get("content_preview") or "").strip()
            if preview:
                lines.append(f"  excerpt: {preview}")
    return "\n".join(lines)


def _discover_sitemaps(origin: str, *, timeout: int, source_events: list[dict[str, Any]]) -> list[str]:
    robots_url = urllib.parse.urljoin(origin, "/robots.txt")
    sitemap_urls: list[str] = []
    try:
        robots = _fetch_text(robots_url, timeout=timeout)
        source_events.append({"url": robots_url, "source": "robots", "status": "ok"})
        for line in robots.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                if sitemap_url:
                    sitemap_urls.append(sitemap_url)
    except Exception as exc:  # pragma: no cover - exact network exceptions vary
        source_events.append({"url": robots_url, "source": "robots", "status": "error", "error": _short_error(exc)})
    sitemap_urls.append(urllib.parse.urljoin(origin, "/sitemap.xml"))
    return _unique(sitemap_urls)


def _collect_sitemap_candidates(
    sitemap_urls: list[str],
    *,
    timeout: int,
    source_events: list[dict[str, Any]],
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    queue = list(sitemap_urls)
    seen: set[str] = set()
    order = 0
    while queue and len(seen) < MAX_SITEMAPS:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen:
            continue
        seen.add(sitemap_url)
        try:
            xml_text = _fetch_text(sitemap_url, timeout=timeout)
            root = ET.fromstring(xml_text)
            source_events.append({"url": sitemap_url, "source": "sitemap", "status": "ok"})
        except Exception as exc:  # pragma: no cover - exact network exceptions vary
            source_events.append({"url": sitemap_url, "source": "sitemap", "status": "error", "error": _short_error(exc)})
            continue
        for child in list(root):
            tag = _local_name(child.tag)
            if tag == "sitemap":
                loc = _child_text(child, "loc")
                if loc and loc not in seen and len(seen) + len(queue) < MAX_SITEMAPS:
                    queue.append(loc)
                continue
            if tag != "url":
                continue
            loc = _child_text(child, "loc")
            if not loc:
                continue
            lastmod = _child_text(child, "lastmod")
            order += 1
            candidates.append(
                _Candidate(
                    url=loc,
                    title=_title_from_url(loc),
                    source="sitemap",
                    lastmod=lastmod,
                    order=order,
                )
            )
    return candidates


def _collect_page_link_candidates(
    url: str,
    *,
    timeout: int,
    source_events: list[dict[str, Any]],
) -> list[_Candidate]:
    try:
        html_text = _fetch_text(url, timeout=timeout)
        source_events.append({"url": url, "source": "page_links", "status": "ok"})
    except Exception as exc:  # pragma: no cover - exact network exceptions vary
        source_events.append({"url": url, "source": "page_links", "status": "error", "error": _short_error(exc)})
        return []
    parser = _LinkParser()
    parser.feed(html_text)
    candidates: list[_Candidate] = []
    for order, link in enumerate(parser.links, start=1):
        href = urllib.parse.urljoin(url, link.get("href") or "")
        title = _collapse_ws(link.get("text") or link.get("title") or _title_from_url(href))
        description = _collapse_ws(link.get("title") or "")
        candidates.append(_Candidate(url=href, title=title, description=description, source="page_link", order=order))
    return candidates


def _filter_rank_candidates(
    candidates: list[_Candidate],
    *,
    base_host: str,
    query: str,
    limit: int,
    include_subdomains: bool,
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    terms = _query_terms(query)
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for candidate in candidates:
        canonical = _canonical_url(candidate.url)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        if not _host_allowed(canonical, base_host=base_host, include_subdomains=include_subdomains):
            continue
        if include_patterns and not _matches_any(canonical, include_patterns):
            continue
        if exclude_patterns and _matches_any(canonical, exclude_patterns):
            continue
        score, matched_terms = _score_candidate(candidate, canonical, terms)
        if terms and score <= 0:
            continue
        item = {
            "url": canonical,
            "title": candidate.title or _title_from_url(canonical),
            "description": candidate.description,
            "source": candidate.source,
            "score": round(score, 3),
            "lastmod": candidate.lastmod,
            "matched_terms": matched_terms,
            "read_command": f"guanlan read {quote_query(canonical)} --quality-report",
        }
        ranked.append((score, candidate.order, item))
    ranked.sort(key=lambda entry: (-entry[0], entry[1], entry[2]["url"]))
    return [item for _, _, item in ranked[:limit]]


def _score_candidate(candidate: _Candidate, canonical_url: str, terms: list[str]) -> tuple[float, list[str]]:
    if not terms:
        source_bonus = 1.2 if candidate.source == "sitemap" else 1.0
        return source_bonus, []
    haystack = " ".join(
        [
            canonical_url.lower(),
            candidate.title.lower(),
            candidate.description.lower(),
        ]
    )
    score = 0.0
    matched: list[str] = []
    for term in terms:
        lowered = term.lower()
        if lowered and lowered in haystack:
            matched.append(term)
            score += 1.0
            if lowered in candidate.title.lower():
                score += 2.0
            if lowered in canonical_url.lower():
                score += 1.0
    if matched and candidate.source == "sitemap":
        score += 0.2
    return score, matched


def _fetch_text(url: str, *, timeout: int = 8) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310 - public user-provided URL fetch is the tool purpose.
        raw = response.read(MAX_FETCH_BYTES)
        encoding = response.headers.get_content_charset() or "utf-8"
    return raw.decode(encoding, errors="replace")


def _normalize_input_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("url is required")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = "https://" + raw
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"unsupported site URL: {value}")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _origin(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def _canonical_url(url: str) -> str:
    raw, _fragment = urllib.parse.urldefrag(str(url or "").strip())
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.lower(), path, parsed.query, ""))


def _host_allowed(url: str, *, base_host: str, include_subdomains: bool) -> bool:
    host = urllib.parse.urlsplit(url).netloc.lower()
    if not host:
        return False
    base = _strip_www(base_host)
    current = _strip_www(host)
    if current == base:
        return True
    return include_subdomains and current.endswith("." + base)


def _matches_any(url: str, patterns: list[str]) -> bool:
    path = urllib.parse.urlsplit(url).path
    for pattern in patterns:
        raw = str(pattern or "").strip()
        if not raw:
            continue
        has_wildcard = any(char in raw for char in "*?[]")
        if has_wildcard and (fnmatch.fnmatch(url, raw) or fnmatch.fnmatch(path, raw)):
            return True
        if not has_wildcard and (raw in url or raw in path):
            return True
    return False


def _query_terms(query: str) -> list[str]:
    raw = _collapse_ws(query)
    if not raw:
        return []
    terms = re.findall(r"[A-Za-z0-9_.-]+|[\u4e00-\u9fff]{2,}", raw)
    if not terms:
        terms = [raw]
    if raw not in terms and len(raw) >= 2:
        terms.append(raw)
    return _unique(terms)


def _child_text(node: ET.Element, local_name: str) -> str:
    for child in list(node):
        if _local_name(child.tag) == local_name:
            return _collapse_ws(child.text or "")
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _title_from_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path.strip("/")
    if not path:
        return parsed.netloc
    tail = path.split("/")[-1] or path
    tail = re.sub(r"[-_]+", " ", tail)
    return html.unescape(_collapse_ws(tail)) or parsed.netloc


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _content_preview(value: str, *, limit: int = 280) -> str:
    text = _collapse_ws(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(min(parsed, maximum), minimum)


def _normalize_read_backend(value: str) -> str:
    backend = str(value or "auto").strip().lower()
    return backend if backend in {"auto", "jina", "direct"} else "auto"


def _strip_www(host: str) -> str:
    return str(host or "").lower().removeprefix("www.")


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _short_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return str(exc.reason)
    if isinstance(exc, socket.timeout):
        return "timeout"
    return str(exc).splitlines()[0][:160]


def quote_query(value: str) -> str:
    """Quote a value for copyable shell commands."""

    text = str(value or "")
    if not text:
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,-]+", text):
        return text
    return json_safe_shell_quote(text)


def json_safe_shell_quote(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
