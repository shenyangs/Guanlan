# -*- coding: utf-8 -*-
"""RSS and OPML content discovery helpers for Guanlan."""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

from guanlan.limits import DEFAULT_FEEDS_LIMIT
from guanlan.source_registry import get_source_metadata
from guanlan.source_registry import list_feed_sources as list_feed_source_metadata
from guanlan.source_taxonomy import source_card_for_domain

_UA = "Mozilla/5.0"
_TIMEOUT = 15

_CURATED_HOST = "best" + "blogs"
_CURATED_OPML_OWNER = "gino" + "befun"
_CURATED_DOMAIN = _CURATED_HOST + ".dev"
_CURATED_HIDDEN_DOMAINS = {
    _CURATED_DOMAIN,
    "www." + _CURATED_DOMAIN,
    "api." + _CURATED_DOMAIN,
    "rsshub." + _CURATED_DOMAIN,
    "wechat2rss." + _CURATED_DOMAIN,
}
CURATED_OPML_URL = (
    "https://raw.githubusercontent.com/"
    + _CURATED_OPML_OWNER
    + "/"
    + "Best"
    + "Blogs"
    + "/main/"
    + "Best"
    + "Blogs"
    + "_RSS_ALL.opml"
)
CURATED_RSS_BASE = "https://www." + _CURATED_DOMAIN + "/{language}/feeds/rss"
AISHORT_BAIDU_RSS_URL = "https://rss.aishort.top/?type=baidu"
AISHORT_WECHAT_RSS_URL = "https://rss.aishort.top/?type=wasi"


@dataclass
class FeedItem:
    """A normalized RSS item for agent discovery."""

    title: str
    url: str
    source_id: str = "rss"
    source_title: str = ""
    category: str = "reading"
    content_direction: str = ""
    published_at: str = ""
    author: str = ""
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    rank: int = 0
    source_confidence: str = "medium"
    evidence_role: str = "reading_signal"
    source_card: dict[str, Any] = field(default_factory=dict)
    freshness: str = ""
    fetched_at: str = ""
    risk_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FeedSource:
    """A source entry from an OPML catalog."""

    title: str
    url: str
    source_id: str = "rss"
    html_url: str = ""
    category: str = ""
    content_direction: str = ""
    rank: int = 0
    source_confidence: str = "medium"
    evidence_role: str = "source_catalog_entry"
    source_card: dict[str, Any] = field(default_factory=dict)
    risk_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FEED_SOURCE_CATALOG: dict[str, dict[str, Any]] = list_feed_source_metadata()

_SOURCE_ALIASES = {
    "quality": "curated",
    "reading": "curated",
    "curated-rss": "curated",
    "tech-rss": "curated",
    "sources": "curated-sources",
    "source-catalog": "curated-sources",
    "opml": "curated-sources",
    "baidu-hot": "baidu-rss",
    "baidu": "baidu-rss",
    "wechat": "wechat-rss",
    "wechat-hot": "wechat-rss",
    "wasi": "wechat-rss",
}


def list_feed_sources() -> dict[str, dict[str, Any]]:
    """Return curated RSS source metadata for routing and UX."""
    return list_feed_source_metadata()


def resolve_feed_source(source: str) -> str:
    """Resolve a feed source id or alias."""
    key = (source or "curated").strip().lower()
    return _SOURCE_ALIASES.get(key, key)


def recommend_feed_sources(query: str) -> list[str]:
    """Return soft source recommendations for a user request."""
    text = (query or "").lower()
    recommendations: list[str] = []
    if any(term in text for term in ("微信", "公众号", "微信热文", "公众号热文")):
        recommendations.append("wechat-rss")
    if any(term in text for term in ("热点", "热搜", "今天", "今日", "实时", "突发")):
        recommendations.append("baidu-rss")
    if any(term in text for term in ("技术文章", "技术博客", "ai", "人工智能", "agent", "产品设计", "商业科技", "值得读", "好文章")):
        recommendations.append("curated")
    if any(term in text for term in ("源", "订阅", "rss", "opml", "目录", "信源")):
        recommendations.append("curated-sources")
    return _unique(recommendations)


def _read_bytes(url: str, timeout: int = _TIMEOUT) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _clean_text(value: Any, max_chars: int = 0) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?，。；：！？])", r"\1", text)
    if max_chars and len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "..."
    return text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain_from_url(url: Any) -> str:
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except Exception:
        return ""
    return (parsed.netloc or "").lower().removeprefix("www.")


def _raw_domain_from_url(url: Any) -> str:
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except Exception:
        return ""
    return (parsed.netloc or "").lower()


def _is_hidden_curated_url(url: Any) -> bool:
    return _raw_domain_from_url(url) in _CURATED_HIDDEN_DOMAINS


def _is_likely_asset_url(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".avif"))


def _visible_feed_url(url: Any) -> str:
    clean = _clean_text(url)
    return "" if _is_hidden_curated_url(clean) else clean


def _candidate_entry_urls(entry: Any) -> list[str]:
    candidates: list[str] = []
    for link in entry.get("links", []) or []:
        href = link.get("href") if isinstance(link, dict) else getattr(link, "href", "")
        if href:
            candidates.append(str(href))
    for key in ("source", "summary", "description", "content"):
        value = entry.get(key)
        if isinstance(value, list):
            value = " ".join(str(part.get("value", part)) for part in value)
        candidates.extend(re.findall(r"https?://[^\s<>'\"）)]+", str(value or "")))
    return _unique([html.unescape(url).strip() for url in candidates])


def _original_entry_url(entry: Any, fallback: Any) -> str:
    fallback_url = _clean_text(fallback)
    if fallback_url and not _is_hidden_curated_url(fallback_url):
        return fallback_url
    for url in _candidate_entry_urls(entry):
        if not _is_hidden_curated_url(url) and not _is_likely_asset_url(url):
            return url
    return ""


def _source_card_for_feed(url: Any, source_id: str) -> dict[str, Any]:
    domain = _domain_from_url(url)
    if domain:
        return source_card_for_domain(domain).to_dict()
    return {
        "domain": "",
        "source_type": "RSS/OPML",
        "authority_role": "feed_source",
        "content_roles": ["reading_discovery"],
        "risk_tags": ["source_availability"],
        "authority_score": 0.25,
        "sample_value": 0.55,
        "freshness_value": 0.5,
        "stability": "best_effort",
        "notes": f"feed source: {source_id}",
    }


def _feed_evidence_role(source_id: str, category: str) -> str:
    meta = get_source_metadata(source_id)
    if meta.get("evidence_role"):
        return str(meta["evidence_role"])
    if source_id == "baidu-rss":
        return "fresh_trend_signal"
    if source_id == "wechat-rss":
        return "wechat_article_signal"
    if source_id == "curated":
        return "reading_discovery_signal"
    if category == "hotnews":
        return "fresh_trend_signal"
    if category == "source_catalog":
        return "source_catalog_entry"
    return "reading_signal"


def _feed_freshness(source_id: str, published_at: str = "") -> str:
    meta = get_source_metadata(source_id)
    if meta.get("freshness") in {"minutes", "near_realtime"}:
        return "near_realtime"
    if source_id in {"baidu-rss", "wechat-rss"}:
        return "near_realtime"
    if published_at:
        return "dated"
    return "unknown"


def _feed_risk_tags(source_id: str, card: dict[str, Any]) -> list[str]:
    tags = [str(tag) for tag in card.get("risk_tags", []) if tag]
    meta = get_source_metadata(source_id)
    tags.extend(str(tag) for tag in meta.get("risk_tags", []) if tag)
    if source_id == "curated" and not card.get("domain"):
        tags.append("index_link_omitted")
    if meta.get("category") == "source_catalog":
        tags.append("catalog_not_content")
    return _unique(tags)


def _entry_tags(entry: Any) -> list[str]:
    tags = []
    for tag in entry.get("tags", []) or []:
        term = _clean_text(tag.get("term") if isinstance(tag, dict) else getattr(tag, "term", ""))
        if term:
            tags.extend(part.strip() for part in term.split(",") if part.strip())
    return _unique(tags)


def _normalize_hot_title(title: str) -> tuple[str, dict[str, Any]]:
    match = re.search(r"\s*热度[:：]\s*(\d+)\s*$", title)
    if not match:
        return title, {}
    return title[: match.start()].strip(), {"heat": int(match.group(1))}


def _normalize_feed_entries(
    parsed: Any,
    source_id: str,
    limit: int,
    category: str = "reading",
    content_direction: str = "",
) -> list[dict[str, Any]]:
    feed_title = _source_title(source_id, _clean_text(parsed.feed.get("title") if hasattr(parsed, "feed") else ""))
    items: list[dict[str, Any]] = []
    for _rank, entry in enumerate(parsed.entries[: max(limit, 1)], 1):
        title = _clean_text(entry.get("title"))
        raw_url = _clean_text(entry.get("link"))
        url = _original_entry_url(entry, raw_url) if source_id == "curated" else _visible_feed_url(raw_url)
        if not title and not url:
            continue
        title, metrics = _normalize_hot_title(title)
        published_at = _clean_text(entry.get("published") or entry.get("updated"))
        source_card = _source_card_for_feed(url, source_id)
        item = FeedItem(
            title=title or url or "Untitled",
            url=url,
            source_id=source_id,
            source_title=feed_title,
            category=category,
            content_direction=content_direction,
            published_at=published_at,
            author=_clean_text(entry.get("author")),
            summary=_clean_text(entry.get("summary") or entry.get("description"), max_chars=900),
            tags=_entry_tags(entry),
            metrics=metrics,
            rank=len(items) + 1,
            source_confidence=str(FEED_SOURCE_CATALOG.get(source_id, {}).get("confidence") or "medium"),
            evidence_role=_feed_evidence_role(source_id, category),
            source_card=source_card,
            freshness=_feed_freshness(source_id, published_at),
            fetched_at=_now_iso(),
            risk_tags=_feed_risk_tags(source_id, source_card),
        )
        items.append(item.to_dict())
    return items


def _source_title(source_id: str, feed_title: str) -> str:
    if source_id == "curated":
        return "精品内容流"
    return feed_title


def fetch_rss_feed(
    url: str,
    limit: int = DEFAULT_FEEDS_LIMIT,
    source_id: str = "rss",
    category: str = "reading",
    content_direction: str = "",
) -> list[dict[str, Any]]:
    """Fetch and normalize one RSS/Atom feed."""
    try:
        import feedparser
    except ImportError as exc:  # pragma: no cover - dependency is declared, message helps external installs.
        raise RuntimeError("RSS support requires feedparser. Install with `pip install feedparser`.") from exc

    raw = _read_bytes(url)
    parsed = feedparser.parse(raw)
    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
        raise RuntimeError(f"Could not parse RSS feed: {getattr(parsed, 'bozo_exception', 'unknown error')}")
    return _normalize_feed_entries(
        parsed,
        source_id=source_id,
        limit=limit,
        category=category,
        content_direction=content_direction,
    )


def build_curated_rss_url(
    language: str = "zh",
    category: str | None = None,
    resource_type: str | None = None,
    featured: bool = False,
    min_score: int | None = None,
    keyword: str | None = None,
    time_filter: str | None = None,
) -> str:
    """Build the public curated RSS URL from supported filters."""
    language = (language or "zh").strip().lower()
    if language not in {"zh", "en"}:
        raise ValueError("Curated RSS language must be zh or en")
    params: dict[str, str] = {}
    if category:
        params["category"] = category.strip()
    if resource_type:
        params["type"] = resource_type.strip()
    if featured:
        params["featured"] = "y"
    if min_score is not None:
        params["minScore"] = str(max(0, min(int(min_score), 100)))
    if keyword:
        params["keyword"] = keyword.strip()
    if time_filter:
        params["timeFilter"] = time_filter.strip()
    base = CURATED_RSS_BASE.format(language=language)
    return base + ("?" + urllib.parse.urlencode(params) if params else "")


def fetch_curated(
    limit: int = DEFAULT_FEEDS_LIMIT,
    language: str = "zh",
    category: str | None = None,
    resource_type: str | None = None,
    featured: bool = False,
    min_score: int | None = None,
    keyword: str | None = None,
    time_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch the public curated discovery RSS."""
    url = build_curated_rss_url(
        language=language,
        category=category,
        resource_type=resource_type,
        featured=featured,
        min_score=min_score,
        keyword=keyword,
        time_filter=time_filter,
    )
    return fetch_rss_feed(
        url,
        limit=limit,
        source_id="curated",
        category="reading",
        content_direction=FEED_SOURCE_CATALOG["curated"]["content_direction"],
    )


def fetch_baidu_rss(limit: int = DEFAULT_FEEDS_LIMIT) -> list[dict[str, Any]]:
    """Fetch dynamic Baidu hot topics from a public RSS mirror."""
    return fetch_rss_feed(
        AISHORT_BAIDU_RSS_URL,
        limit=limit,
        source_id="baidu-rss",
        category="hotnews",
        content_direction=FEED_SOURCE_CATALOG["baidu-rss"]["content_direction"],
    )


def fetch_wechat_rss(limit: int = DEFAULT_FEEDS_LIMIT) -> list[dict[str, Any]]:
    """Fetch dynamic hot WeChat article signals from a public RSS mirror."""
    return fetch_rss_feed(
        AISHORT_WECHAT_RSS_URL,
        limit=limit,
        source_id="wechat-rss",
        category="wechat",
        content_direction=FEED_SOURCE_CATALOG["wechat-rss"]["content_direction"],
    )


def fetch_feed_source(
    source: str = "curated",
    limit: int = DEFAULT_FEEDS_LIMIT,
    language: str = "zh",
    category: str | None = None,
    resource_type: str | None = None,
    featured: bool = False,
    min_score: int | None = None,
    keyword: str | None = None,
    time_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch one named feed source."""
    resolved = resolve_feed_source(source)
    if resolved == "curated":
        return fetch_curated(
            limit=limit,
            language=language,
            category=category,
            resource_type=resource_type,
            featured=featured,
            min_score=min_score,
            keyword=keyword,
            time_filter=time_filter,
        )
    if resolved == "baidu-rss":
        return fetch_baidu_rss(limit=limit)
    if resolved == "wechat-rss":
        return fetch_wechat_rss(limit=limit)
    if resolved.startswith(("http://", "https://")):
        return fetch_rss_feed(resolved, limit=limit, source_id="rss")
    raise ValueError("feeds source must be curated, baidu-rss, wechat-rss, curated-sources, list, or an RSS/Atom URL")


def list_curated_sources(
    limit: int = DEFAULT_FEEDS_LIMIT,
    query: str | None = None,
    opml_url: str = CURATED_OPML_URL,
) -> list[dict[str, Any]]:
    """Fetch the public OPML catalog and return feed sources."""
    raw = _read_bytes(opml_url)
    root = ElementTree.fromstring(raw)
    query_text = (query or "").strip().lower()
    sources: list[dict[str, Any]] = []
    for outline in root.findall(".//outline"):
        feed_url = outline.get("xmlUrl") or outline.get("xmlurl") or ""
        if not feed_url:
            continue
        title = _clean_text(outline.get("title") or outline.get("text") or feed_url)
        html_url = _clean_text(outline.get("htmlUrl") or outline.get("htmlurl"))
        haystack = f"{title} {feed_url} {html_url}".lower()
        if query_text and query_text not in haystack:
            continue
        visible_url = _visible_feed_url(feed_url)
        visible_html_url = _visible_feed_url(html_url)
        source_card = _source_card_for_feed(visible_url or visible_html_url, "curated:source")
        source = FeedSource(
            title=title,
            url=visible_url,
            source_id="curated:source",
            html_url=visible_html_url,
            category=_source_category(title, feed_url),
            content_direction="长期订阅源候选",
            rank=len(sources) + 1,
            source_confidence="medium",
            source_card=source_card,
            risk_tags=_unique(["catalog_not_content"] + [str(tag) for tag in source_card.get("risk_tags", [])]),
        )
        sources.append(source.to_dict())
        if len(sources) >= max(limit, 1):
            break
    return sources


def format_feed_catalog_markdown(catalog: dict[str, dict[str, Any]] | None = None) -> str:
    """Render source classification and routing guidance."""
    data = catalog or list_feed_sources()
    lines = [
        "# 观澜 RSS 信源路由",
        "",
        "这些入口都只读公开 RSS/OPML。路由原则：实时热点看动态源，深度阅读看精品内容流，长期扩源看源目录。",
        "",
    ]
    for source_id, meta in data.items():
        lines.append(f"## {meta['name']} (`{source_id}`)")
        lines.append(f"- 定位: {meta['content_direction']}")
        lines.append(f"- 分类: {meta['category']}")
        lines.append(f"- 新鲜度: {meta['freshness']}")
        lines.append(f"- 质量口径: {meta['quality']}")
        lines.append(f"- 适用: {meta['route_when']}")
        lines.append(f"- 命令: `{meta['command']}`")
        lines.append(f"- 边界: {meta['caveat']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_feed_items_markdown(items: list[dict[str, Any]], title: str = "观澜内容发现") -> str:
    """Render feed items as compact Markdown."""
    lines = [f"# {title}", ""]
    if not items:
        return "\n".join(lines + ["No items."])
    for idx, item in enumerate(items, 1):
        source = item.get("source_title") or item.get("source_id") or "rss"
        lines.append(f"{idx}. [{source}] {item.get('title', '').strip()}")
        if item.get("url"):
            lines.append(f"   {item['url']}")
        meta = []
        if item.get("published_at"):
            meta.append(str(item["published_at"]))
        if item.get("author"):
            meta.append(f"作者: {item['author']}")
        if item.get("tags"):
            meta.append("标签: " + ", ".join(item["tags"][:6]))
        if item.get("metrics", {}).get("heat") is not None:
            meta.append(f"热度: {item['metrics']['heat']}")
        if item.get("evidence_role"):
            meta.append(f"证据角色: {item['evidence_role']}")
        if meta:
            lines.append("   " + " | ".join(meta))
        if item.get("summary"):
            lines.append(f"   摘要: {item['summary']}")
    return "\n".join(lines).rstrip()


def format_feed_items_context(items: list[dict[str, Any]], title: str = "观澜内容发现上下文") -> str:
    """Render feed items as prompt-friendly context."""
    lines = [
        f"# {title}",
        "",
        "边界：以下内容来自公开 RSS/Atom；它适合做阅读发现和线索筛选，不等同于事实核验或全网热度排名。",
        "",
    ]
    for item in items:
        lines.append(f"- title: {item.get('title', '')}")
        lines.append(f"  url: {item.get('url', '')}")
        lines.append(f"  source: {item.get('source_title') or item.get('source_id', '')}")
        if item.get("category"):
            lines.append(f"  category: {item['category']}")
        if item.get("evidence_role"):
            lines.append(f"  evidence_role: {item['evidence_role']}")
        if item.get("freshness"):
            lines.append(f"  freshness: {item['freshness']}")
        source_card = item.get("source_card") or {}
        if source_card:
            lines.append(f"  source_type: {source_card.get('source_type', '')}")
        if item.get("published_at"):
            lines.append(f"  published_at: {item['published_at']}")
        if item.get("metrics", {}).get("heat") is not None:
            lines.append(f"  heat: {item['metrics']['heat']}")
        if item.get("summary"):
            lines.append(f"  summary: {item['summary']}")
        if item.get("tags"):
            lines.append(f"  tags: {', '.join(item['tags'][:8])}")
    return "\n".join(lines).rstrip()


def format_feed_sources_markdown(sources: list[dict[str, Any]], title: str = "观澜 RSS 源目录") -> str:
    """Render OPML source entries."""
    lines = [f"# {title}", ""]
    if not sources:
        return "\n".join(lines + ["No sources."])
    for idx, source in enumerate(sources, 1):
        lines.append(f"{idx}. {source.get('title', '')}")
        if source.get("url"):
            lines.append(f"   {source.get('url', '')}")
        if source.get("category"):
            lines.append(f"   分类: {source['category']}")
    return "\n".join(lines).rstrip()


def compact_feed_items(items: list[dict[str, Any]], summary_chars: int = 140) -> list[dict[str, Any]]:
    """Return a smaller feed payload while preserving source and evidence hints."""
    compacted: list[dict[str, Any]] = []
    for item in items:
        card = item.get("source_card") or {}
        row: dict[str, Any] = {
            "rank": item.get("rank"),
            "source_id": item.get("source_id"),
            "source_title": item.get("source_title"),
            "title": item.get("title"),
            "url": item.get("url"),
            "published_at": item.get("published_at"),
            "category": item.get("category"),
            "evidence_role": item.get("evidence_role"),
            "freshness": item.get("freshness"),
            "risk_tags": item.get("risk_tags") or [],
        }
        if item.get("summary"):
            row["summary"] = _clean_text(item.get("summary"))[: max(summary_chars, 0)]
        metrics = item.get("metrics") or {}
        if metrics:
            row["metrics"] = {
                key: metrics[key]
                for key in ("heat", "score")
                if key in metrics and metrics[key] not in ("", None)
            }
        if card:
            row["source_card"] = {
                key: card.get(key)
                for key in ("domain", "source_type", "authority_role")
                if card.get(key) not in ("", None)
            }
        compacted.append({key: value for key, value in row.items() if value not in ("", None, [], {})})
    return compacted


def format_json(data: Any) -> str:
    """Pretty JSON helper for CLI output."""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _source_category(title: str, url: str) -> str:
    text = f"{title} {url}".lower()
    if any(term in text for term in ("ai", "人工智能", "machine learning", "deepmind", "openai", "hugging")):
        return "ai"
    if any(term in text for term in ("product", "产品", "ux", "design")):
        return "product"
    if any(term in text for term in ("business", "商业", "创业", "finance")):
        return "business"
    if any(term in text for term in ("podcast", "youtube", "video")):
        return "media"
    return "tech"


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        clean = str(value).strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result
