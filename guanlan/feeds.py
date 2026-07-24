# -*- coding: utf-8 -*-
"""RSS and OPML content discovery helpers for Guanlan."""

from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from guanlan import __version__
from guanlan.limits import DEFAULT_FEEDS_LIMIT
from guanlan.network_execution import diagnose_network_error, read_url_bytes
from guanlan.source_registry import get_source_metadata
from guanlan.source_registry import list_feed_sources as list_feed_source_metadata
from guanlan.source_taxonomy import source_card_for_domain

_UA = "Mozilla/5.0"
_TIMEOUT = 15
_CACHE_VERSION = 1
FEEDS_CACHE_TTL_SECONDS = 24 * 60 * 60

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
ARXIV_API_URL = "https://export.arxiv.org/api/query"
AI_VERTICAL_ITEMS_URL = "https://aihot.virxact.com/api/public/items"
AI_OFFICIAL_FEEDS: tuple[dict[str, Any], ...] = (
    {
        "title": "OpenAI News",
        "xml_url": "https://openai.com/news/rss.xml",
        "html_url": "https://openai.com/news",
        "max_entries": 12,
    },
    {
        "title": "Google DeepMind Blog",
        "xml_url": "https://deepmind.google/blog/rss.xml",
        "html_url": "https://deepmind.google/discover/blog/",
        "max_entries": 12,
    },
    {
        "title": "Google AI Blog",
        "xml_url": "https://blog.google/technology/ai/rss/",
        "html_url": "https://blog.google/technology/ai/",
        "max_entries": 10,
    },
    {
        "title": "Hugging Face Blog",
        "xml_url": "https://huggingface.co/blog/feed.xml",
        "html_url": "https://huggingface.co/blog",
        "max_entries": 10,
    },
    {
        "title": "GitHub AI & ML",
        "xml_url": "https://github.blog/ai-and-ml/feed/",
        "html_url": "https://github.blog/ai-and-ml/",
        "max_entries": 10,
    },
    {
        "title": "GitHub Changelog",
        "xml_url": "https://github.blog/changelog/feed/",
        "html_url": "https://github.blog/changelog/",
        "include_keywords": "ai,artificial intelligence,copilot,github models,agent,agents,claude,gpt,gemini,model,mcp",
        "max_entries": 6,
    },
    {
        "title": "Microsoft AI Blog",
        "xml_url": "https://news.microsoft.com/source/topics/ai/feed/",
        "html_url": "https://news.microsoft.com/source/topics/ai/",
        "max_entries": 10,
    },
    {
        "title": "NVIDIA Generative AI Blog",
        "xml_url": "https://developer.nvidia.com/blog/category/generative-ai/feed/",
        "html_url": "https://developer.nvidia.com/blog/category/generative-ai/",
        "max_entries": 8,
    },
)
AI_MEDIA_FEEDS: tuple[dict[str, Any], ...] = (
    {
        "title": "The Decoder AI News",
        "xml_url": "https://the-decoder.com/feed/",
        "html_url": "https://the-decoder.com/",
        "max_entries": 8,
    },
    {
        "title": "TechCrunch AI",
        "xml_url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "html_url": "https://techcrunch.com/category/artificial-intelligence/",
        "max_entries": 8,
    },
    {
        "title": "VentureBeat AI",
        "xml_url": "https://venturebeat.com/category/ai/feed",
        "html_url": "https://venturebeat.com/category/ai/",
        "max_entries": 8,
    },
    {
        "title": "Artificial Intelligence News",
        "xml_url": "https://www.artificialintelligence-news.com/feed/",
        "html_url": "https://www.artificialintelligence-news.com/",
        "max_entries": 8,
    },
    {
        "title": "Wired AI",
        "xml_url": "https://www.wired.com/feed/tag/ai/latest/rss",
        "html_url": "https://www.wired.com/tag/artificial-intelligence/",
        "max_entries": 6,
    },
    {
        "title": "The Verge",
        "xml_url": "https://www.theverge.com/rss/index.xml",
        "html_url": "https://www.theverge.com/ai-artificial-intelligence",
        "include_keywords": "ai,artificial intelligence,openai,anthropic,claude,chatgpt,gpt,gemini,llm,agent,copilot",
        "max_entries": 6,
        "strict_title_filter": True,
    },
    {
        "title": "MarkTechPost Research",
        "xml_url": "https://www.marktechpost.com/feed/",
        "html_url": "https://www.marktechpost.com/",
        "include_keywords": "paper,research,arxiv,benchmark,dataset,model,llm,agent,diffusion,transformer,multimodal,reasoning,inference,training,open-source",
        "max_entries": 6,
        "strict_title_filter": True,
    },
)
AI_VERTICAL_CATEGORY_ALIASES = {
    "model": "ai-models",
    "models": "ai-models",
    "ai-models": "ai-models",
    "模型": "ai-models",
    "产品": "ai-products",
    "product": "ai-products",
    "products": "ai-products",
    "ai-products": "ai-products",
    "industry": "industry",
    "行业": "industry",
    "paper": "paper",
    "papers": "paper",
    "论文": "paper",
    "research": "paper",
    "tip": "tip",
    "tips": "tip",
    "技巧": "tip",
    "观点": "tip",
}
DEFAULT_FEED_WATCHLIST_PATH = Path.home() / ".guanlan" / "feeds-watchlist.json"


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
    feed_status: dict[str, Any] = field(default_factory=dict)

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
    "preprint": "arxiv",
    "paper": "arxiv",
    "aihot": "ai-vertical",
    "ai-hot": "ai-vertical",
    "ai": "ai-vertical",
    "official-ai": "ai-official",
    "ai-official-rss": "ai-official",
    "ai-news-official": "ai-official",
    "curated-ai-media": "ai-media",
    "ai-news-media": "ai-media",
    "ai-media-rss": "ai-media",
    "watch": "watchlist",
    "feeds-watch": "watchlist",
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
    if any(
        term in text
        for term in (
            "人工智能",
            "大模型",
            "agent",
            "智能体",
            "openai",
            "anthropic",
            "claude",
            "gemini",
            "wps ai",
            "ai office",
            "office ai",
            "ai ppt",
        )
    ):
        recommendations.append("ai-official")
        recommendations.append("ai-media")
        recommendations.append("ai-vertical")
    if any(term in text for term in ("arxiv", "预印本", "preprint", "论文", "paper")):
        recommendations.append("arxiv")
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
    return read_url_bytes(req, timeout=timeout)


def _read_json(url: str, timeout: int = _TIMEOUT, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
            f"guanlan/{__version__} ai-vertical-source"
        ),
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    raw = read_url_bytes(req, timeout=timeout).decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def feed_cache_dir() -> Path:
    """Return the local cache directory for public RSS/OPML discovery."""
    return Path.home() / ".guanlan" / "cache" / "feeds"


def _feed_cache_key(kind: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(
        {"kind": kind, "version": _CACHE_VERSION, "app": __version__, **payload},
        sort_keys=True,
        ensure_ascii=False,
    )
    import hashlib

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _feed_cache_path(kind: str, key: str) -> Path:
    return feed_cache_dir() / kind / f"{key}.json"


def _feed_cache_get(kind: str, key: str, ttl: int = FEEDS_CACHE_TTL_SECONDS) -> dict[str, Any] | None:
    path = _feed_cache_path(kind, key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    created_at = float(data.get("created_at", 0) or 0)
    if ttl > 0 and time.time() - created_at > ttl:
        return None
    payload = data.get("payload")
    return payload if isinstance(payload, dict) else None


def _feed_cache_get_any(kind: str, key: str) -> dict[str, Any] | None:
    return _feed_cache_get(kind, key, ttl=0)


def _feed_cache_set(kind: str, key: str, payload: dict[str, Any]) -> None:
    path = _feed_cache_path(kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": _CACHE_VERSION,
        "created_at": time.time(),
        "kind": kind,
        "payload": payload,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _annotate_feed_status(
    rows: list[dict[str, Any]],
    status: str,
    *,
    source_id: str,
    error: str = "",
    network_diagnostic: dict[str, Any] | None = None,
    stale: bool = False,
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for rank, item in enumerate(rows, 1):
        row = dict(item)
        row["rank"] = rank
        row["feed_status"] = {
            "status": status,
            "source_id": source_id,
            "stale": bool(stale),
            "error": error,
        }
        if network_diagnostic:
            row["feed_status"]["network_diagnostic"] = dict(network_diagnostic)
        if stale:
            risk_tags = [str(tag) for tag in row.get("risk_tags", []) if tag]
            if "stale_cache" not in risk_tags:
                risk_tags.append("stale_cache")
            row["risk_tags"] = risk_tags
            row.setdefault("freshness", "cached")
        annotated.append(row)
    return annotated


def _feed_failure_item(
    *,
    url: str,
    source_id: str,
    category: str,
    content_direction: str,
    error: str,
    network_diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a diagnostic row when a public feed is unavailable on cold start."""
    source_card = _source_card_for_feed(url, source_id)
    item = FeedItem(
        title=f"{_source_title(source_id, source_id)} 暂时不可用",
        url=url,
        source_id=source_id,
        source_title=_source_title(source_id, source_id),
        category=category or "source_status",
        content_direction=content_direction,
        summary="公开 RSS/OPML 源本次请求失败，且本机还没有最近成功缓存。请稍后重试，或改用 search/research/hotnews 兜底。",
        rank=1,
        source_confidence=str(FEED_SOURCE_CATALOG.get(source_id, {}).get("confidence") or "low"),
        evidence_role="source_availability_signal",
        source_card=source_card,
        freshness="unavailable",
        fetched_at=_now_iso(),
        risk_tags=_unique(_feed_risk_tags(source_id, source_card) + ["source_unavailable", "no_cache"]),
        feed_status={
            "status": "error",
            "source_id": source_id,
            "stale": False,
            "error": error,
            **({"network_diagnostic": dict(network_diagnostic)} if network_diagnostic else {}),
        },
    )
    return item.to_dict()


def _feed_error_details(exc: BaseException, *, source_id: str, operation: str) -> tuple[str, dict[str, Any]]:
    """Return the public-safe status and structured diagnostic for one feed."""

    diagnostic = diagnose_network_error(exc, source=source_id, operation=operation)
    return str(diagnostic["category"]), diagnostic


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
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if host.endswith(("qlogo.cn", "qpic.cn", "mmbiz.qpic.cn", "wx.qlogo.cn")):
        return True
    if re.search(r"/(?:avatar|image|img|logo|icon|cover|thumb|thumbnail)/", path):
        return True
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
    if fallback_url and not _is_hidden_curated_url(fallback_url) and not _is_likely_asset_url(fallback_url):
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


def infer_ai_vertical_category(query: str = "", category: str | None = None) -> str | None:
    """Map Guanlan route hints to the AI vertical API categories."""
    explicit = (category or "").strip().lower()
    if explicit:
        return AI_VERTICAL_CATEGORY_ALIASES.get(explicit, explicit if explicit in set(AI_VERTICAL_CATEGORY_ALIASES.values()) else None)
    text = (query or "").lower()
    compact = re.sub(r"\s+", "", text)
    if any(term in compact for term in ("模型", "大模型", "llm", "gpt", "claude", "gemini", "qwen", "glm")):
        return "ai-models"
    if any(term in compact for term in ("产品", "发布", "工具", "agent", "智能体", "wps", "office", "ppt", "应用")):
        return "ai-products"
    if any(term in compact for term in ("论文", "paper", "arxiv", "研究", "benchmark", "评测")):
        return "paper"
    if any(term in compact for term in ("技巧", "观点", "实践", "经验", "教程", "方法")):
        return "tip"
    if any(term in compact for term in ("行业", "融资", "公司", "商业化", "监管", "市场")):
        return "industry"
    return None


def build_ai_vertical_items_url(
    *,
    mode: str = "selected",
    category: str | None = None,
    keyword: str | None = None,
    since: str | None = None,
    take: int = DEFAULT_FEEDS_LIMIT,
    cursor: str | None = None,
) -> str:
    """Build the read-only AI vertical source URL used internally by routing."""
    clean_mode = "all" if (mode or "").strip().lower() == "all" else "selected"
    params: dict[str, str] = {"mode": clean_mode, "take": str(max(1, min(int(take), 100)))}
    clean_category = infer_ai_vertical_category(category=category)
    if clean_category:
        params["category"] = clean_category
    clean_keyword = (keyword or "").strip()
    if len(clean_keyword) >= 2:
        params["q"] = clean_keyword[:200]
    if since:
        params["since"] = since
    if cursor:
        params["cursor"] = cursor
    return AI_VERTICAL_ITEMS_URL + "?" + urllib.parse.urlencode(params)


def _normalize_ai_vertical_items(data: dict[str, Any], *, source_url: str, limit: int) -> list[dict[str, Any]]:
    rows = data.get("items") if isinstance(data.get("items"), list) else []
    items: list[dict[str, Any]] = []
    for row in rows[: max(limit, 1)]:
        if not isinstance(row, dict):
            continue
        url = _clean_text(row.get("url"))
        title = _clean_text(row.get("title") or row.get("title_en") or url)
        if not title and not url:
            continue
        source_card = _source_card_for_feed(url, "ai-vertical")
        category = _clean_text(row.get("category")) or "ai"
        item = FeedItem(
            title=title or url,
            url=url,
            source_id="ai-vertical",
            source_title="AI 垂类精选动态源",
            category=category,
            content_direction=FEED_SOURCE_CATALOG["ai-vertical"]["content_direction"],
            published_at=_clean_text(row.get("publishedAt")),
            author=_clean_text(row.get("source")),
            summary=_clean_text(row.get("summary"), max_chars=900),
            tags=_unique(["ai", category]),
            metrics={"item_id": _clean_text(row.get("id"))} if row.get("id") else {},
            rank=len(items) + 1,
            source_confidence=str(FEED_SOURCE_CATALOG["ai-vertical"].get("confidence") or "medium"),
            evidence_role=_feed_evidence_role("ai-vertical", "ai"),
            source_card=source_card,
            freshness=_feed_freshness("ai-vertical", _clean_text(row.get("publishedAt"))),
            fetched_at=_now_iso(),
            risk_tags=_unique(_feed_risk_tags("ai-vertical", source_card)),
            feed_status={"status": "fresh", "source_id": "ai-vertical", "stale": False, "error": "", "url": source_url},
        )
        items.append(item.to_dict())
    return items


def fetch_ai_vertical_signals(
    query: str = "",
    *,
    limit: int = DEFAULT_FEEDS_LIMIT,
    category: str | None = None,
    mode: str = "selected",
    keyword: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch the internal AI vertical discovery source for AI/WPS routing."""
    inferred_category = infer_ai_vertical_category(query, category)
    query_keyword = keyword if keyword is not None else ""
    url = build_ai_vertical_items_url(
        mode=mode,
        category=inferred_category,
        keyword=query_keyword,
        since=since,
        take=min(max(limit, 1), 100),
    )
    cache_key = _feed_cache_key(
        "ai-vertical",
        {
            "url": url,
            "query": query,
            "category": inferred_category or "",
            "keyword": query_keyword,
            "mode": mode,
            "since": since or "",
        },
    )
    try:
        data = _read_json(url)
        items = _normalize_ai_vertical_items(data, source_url=url, limit=limit)
        items = _annotate_feed_status(items, "fresh", source_id="ai-vertical")
        _feed_cache_set("ai-vertical", cache_key, {"items": items, "url": url, "source_id": "ai-vertical"})
        return items[: max(limit, 1)]
    except Exception as exc:
        error, diagnostic = _feed_error_details(exc, source_id="ai-vertical", operation="fetch_feed")
        cached = _feed_cache_get_any("ai-vertical", cache_key)
        if cached and isinstance(cached.get("items"), list):
            return _annotate_feed_status(
                [dict(item) for item in cached["items"][: max(limit, 1)]],
                "stale_cache",
                source_id="ai-vertical",
                error=error,
                network_diagnostic=diagnostic,
                stale=True,
            )
        return [
            _feed_failure_item(
                url=url,
                source_id="ai-vertical",
                category="ai",
                content_direction=FEED_SOURCE_CATALOG["ai-vertical"]["content_direction"],
                error=error,
                network_diagnostic=diagnostic,
            )
        ]


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
            feed_status={"status": "fresh", "source_id": source_id, "stale": False, "error": ""},
        )
        items.append(item.to_dict())
    return items


def _source_title(source_id: str, feed_title: str) -> str:
    if source_id == "curated":
        return "精品内容流"
    if source_id == "ai-official":
        return "AI 官方更新流"
    if source_id == "ai-media":
        return "AI 媒体观察流"
    if source_id == "arxiv":
        return "arXiv"
    if source_id == "watchlist":
        return "订阅源观察"
    return feed_title


def _first_xml_text(node: ElementTree.Element, names: tuple[str, ...]) -> str:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag in names:
            return _clean_text(child.text)
    return ""


def _first_xml_link(node: ElementTree.Element) -> str:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag != "link":
            continue
        attrs = {key.lower(): value for key, value in child.attrib.items()}
        rel = attrs.get("rel", "alternate")
        href = attrs.get("href", "")
        if href and rel in {"alternate", ""}:
            return _clean_text(href)
    return ""


def fetch_arxiv(
    query: str,
    limit: int = DEFAULT_FEEDS_LIMIT,
    sort_by: str = "submittedDate",
    sort_order: str = "descending",
) -> list[dict[str, Any]]:
    """Fetch arXiv public API results as academic feed items."""
    clean_query = (query or "").strip()
    if not clean_query:
        return [
            _feed_failure_item(
                url=ARXIV_API_URL,
                source_id="arxiv",
                category="academic",
                content_direction=FEED_SOURCE_CATALOG["arxiv"]["content_direction"],
                error="arXiv 查询需要通过 --keyword 提供关键词。",
            )
        ]
    search_query = clean_query if ":" in clean_query else f"all:{clean_query}"
    params = {
        "search_query": search_query,
        "start": "0",
        "max_results": str(max(limit, 1)),
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    url = ARXIV_API_URL + "?" + urllib.parse.urlencode(params)
    cache_key = _feed_cache_key("arxiv", {"query": clean_query, "sort_by": sort_by, "sort_order": sort_order})
    try:
        raw = _read_bytes(url)
        root = ElementTree.fromstring(raw)
        items: list[dict[str, Any]] = []
        for entry in [node for node in list(root) if node.tag.rsplit("}", 1)[-1].lower() == "entry"][: max(limit, 1)]:
            title = _first_xml_text(entry, ("title",))
            entry_url = _first_xml_link(entry) or _first_xml_text(entry, ("id",))
            published_at = _first_xml_text(entry, ("published", "updated"))
            authors = [
                _first_xml_text(author, ("name",))
                for author in list(entry)
                if author.tag.rsplit("}", 1)[-1].lower() == "author"
            ]
            source_card = _source_card_for_feed(entry_url, "arxiv")
            item = FeedItem(
                title=title or entry_url or "Untitled arXiv result",
                url=entry_url,
                source_id="arxiv",
                source_title="arXiv",
                category="academic",
                content_direction=FEED_SOURCE_CATALOG["arxiv"]["content_direction"],
                published_at=published_at,
                author=", ".join([author for author in authors if author][:4]),
                summary=_first_xml_text(entry, ("summary",))[:1200],
                tags=["preprint"],
                metrics={},
                rank=len(items) + 1,
                source_confidence=str(FEED_SOURCE_CATALOG["arxiv"].get("confidence") or "medium"),
                evidence_role=_feed_evidence_role("arxiv", "academic"),
                source_card=source_card,
                freshness=_feed_freshness("arxiv", published_at),
                fetched_at=_now_iso(),
                risk_tags=_feed_risk_tags("arxiv", source_card),
                feed_status={"status": "fresh", "source_id": "arxiv", "stale": False, "error": ""},
            )
            items.append(item.to_dict())
        items = _annotate_feed_status(items, "fresh", source_id="arxiv")
        _feed_cache_set("arxiv", cache_key, {"items": items, "url": url, "source_id": "arxiv"})
        return items[: max(limit, 1)]
    except Exception as exc:
        error, diagnostic = _feed_error_details(exc, source_id="arxiv", operation="fetch_feed")
        cached = _feed_cache_get_any("arxiv", cache_key)
        if cached and isinstance(cached.get("items"), list):
            return _annotate_feed_status(
                [dict(item) for item in cached["items"][: max(limit, 1)]],
                "stale_cache",
                source_id="arxiv",
                error=error,
                network_diagnostic=diagnostic,
                stale=True,
            )
        return [
            _arxiv_search_entrypoint(clean_query, error=error, network_diagnostic=diagnostic),
            _feed_failure_item(
                url=url,
                source_id="arxiv",
                category="academic",
                content_direction=FEED_SOURCE_CATALOG["arxiv"]["content_direction"],
                error=error,
                network_diagnostic=diagnostic,
            ),
        ]


def _arxiv_search_entrypoint(
    query: str,
    *,
    error: str = "",
    network_diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = "https://arxiv.org/search/?" + urllib.parse.urlencode(
        {"query": query, "searchtype": "all", "abstracts": "show", "order": "-announced_date_first", "size": "50"}
    )
    source_card = _source_card_for_feed(url, "arxiv")
    item = FeedItem(
        title=f"arXiv 搜索入口：{query}",
        url=url,
        source_id="arxiv",
        source_title="arXiv",
        category="academic",
        content_direction=FEED_SOURCE_CATALOG["arxiv"]["content_direction"],
        summary="arXiv API 本次不可用时的公开网页检索入口；可继续用 read/search 定点补证。",
        rank=1,
        source_confidence=str(FEED_SOURCE_CATALOG["arxiv"].get("confidence") or "medium"),
        evidence_role="preprint_search_entrypoint",
        source_card=source_card,
        freshness="entrypoint",
        fetched_at=_now_iso(),
        risk_tags=_unique(_feed_risk_tags("arxiv", source_card) + ["api_unavailable"]),
        feed_status={
            "status": "fallback_entrypoint",
            "source_id": "arxiv",
            "stale": False,
            "error": error,
            **({"network_diagnostic": dict(network_diagnostic)} if network_diagnostic else {}),
        },
    )
    return item.to_dict()


def fetch_rss_feed(
    url: str,
    limit: int = DEFAULT_FEEDS_LIMIT,
    source_id: str = "rss",
    category: str = "reading",
    content_direction: str = "",
) -> list[dict[str, Any]]:
    """Fetch and normalize one RSS/Atom feed."""
    cache_key = _feed_cache_key(
        "rss",
        {
            "url": url,
            "source_id": source_id,
            "category": category,
            "content_direction": content_direction,
        },
    )
    try:
        import feedparser
    except ImportError as exc:  # pragma: no cover - dependency is declared, message helps external installs.
        raise RuntimeError("RSS support requires feedparser. Install with `pip install feedparser`.") from exc

    try:
        raw = _read_bytes(url)
        parsed = feedparser.parse(raw)
        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
            raise RuntimeError(f"Could not parse RSS feed: {getattr(parsed, 'bozo_exception', 'unknown error')}")
        rows = _normalize_feed_entries(
            parsed,
            source_id=source_id,
            limit=max(limit, DEFAULT_FEEDS_LIMIT),
            category=category,
            content_direction=content_direction,
        )
        rows = _annotate_feed_status(rows, "fresh", source_id=source_id)
        _feed_cache_set("rss", cache_key, {"items": rows, "url": url, "source_id": source_id})
        return rows[: max(limit, 1)]
    except Exception as exc:
        error, diagnostic = _feed_error_details(exc, source_id=source_id, operation="fetch_feed")
        cached = _feed_cache_get_any("rss", cache_key)
        if cached and isinstance(cached.get("items"), list):
            return _annotate_feed_status(
                [dict(item) for item in cached["items"][: max(limit, 1)]],
                "stale_cache",
                source_id=source_id,
                error=error,
                network_diagnostic=diagnostic,
                stale=True,
            )
        return [
            _feed_failure_item(
                url=url,
                source_id=source_id,
                category=category,
                content_direction=content_direction,
                error=error,
                network_diagnostic=diagnostic,
            )
        ]


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


def _split_keywords(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = ",".join(str(item) for item in value)
    else:
        raw = str(value)
    return [part.strip().lower() for part in re.split(r"[,，|/]", raw) if part.strip()]


def _feed_item_matches_terms(item: dict[str, Any], terms: list[str], *, strict_title: bool = False) -> bool:
    if not terms:
        return True
    title = str(item.get("title") or "").lower()
    if strict_title:
        return any(term in title for term in terms)
    haystack = " ".join(
        [
            title,
            str(item.get("summary") or "").lower(),
            " ".join(str(tag).lower() for tag in item.get("tags") or []),
        ]
    )
    return any(term in haystack for term in terms)


def _feed_sort_value(item: dict[str, Any]) -> float:
    raw = str(item.get("published_at") or "").strip()
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:
        pass
    try:
        return parsedate_to_datetime(raw).timestamp()
    except Exception:
        return 0.0


def fetch_feed_bundle(
    source_id: str,
    feed_entries: tuple[dict[str, Any], ...],
    *,
    limit: int = DEFAULT_FEEDS_LIMIT,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch a small named bundle of public RSS/Atom feeds with boundaries."""
    meta = FEED_SOURCE_CATALOG[source_id]
    per_source_limit = max(3, min(12, (max(limit, 1) + max(len(feed_entries), 1) - 1) // max(len(feed_entries), 1) + 2))
    items: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    keyword_terms = _split_keywords(keyword)
    for feed in feed_entries:
        feed_limit = max(per_source_limit, int(feed.get("max_entries") or per_source_limit))
        rows = fetch_rss_feed(
            str(feed["xml_url"]),
            limit=feed_limit,
            source_id=source_id,
            category=str(meta.get("category") or "ai"),
            content_direction=str(meta.get("content_direction") or ""),
        )
        include_terms = _split_keywords(feed.get("include_keywords"))
        strict_title = bool(feed.get("strict_title_filter", False))
        for row in rows:
            status = (row.get("feed_status") or {}).get("status")
            if status == "error":
                failures.append(row)
                continue
            if not _feed_item_matches_terms(row, include_terms, strict_title=strict_title):
                continue
            if keyword_terms and not _feed_item_matches_terms(row, keyword_terms):
                continue
            item = dict(row)
            item["feed_source"] = {
                "title": str(feed.get("title") or ""),
                "xml_url": str(feed.get("xml_url") or ""),
                "html_url": str(feed.get("html_url") or ""),
            }
            if feed.get("html_url"):
                item.setdefault("source_home", str(feed["html_url"]))
            risk_tags = [str(tag) for tag in item.get("risk_tags", []) if tag]
            if "source_requires_original_verification" not in risk_tags:
                risk_tags.append("source_requires_original_verification")
            item["risk_tags"] = _unique(risk_tags)
            items.append(item)
    items.sort(key=_feed_sort_value, reverse=True)
    for rank, item in enumerate(items[: max(limit, 1)], 1):
        item["rank"] = rank
    if items:
        return items[: max(limit, 1)]
    return failures[: max(limit, 1)] or [
        _feed_failure_item(
            url=", ".join(str(feed.get("xml_url") or "") for feed in feed_entries[:3]),
            source_id=source_id,
            category=str(meta.get("category") or "ai"),
            content_direction=str(meta.get("content_direction") or ""),
            error="命名 RSS 源包本次没有可用条目；可稍后重试或改用 ai-vertical/curated/search。",
        )
    ]


def fetch_ai_official_updates(limit: int = DEFAULT_FEEDS_LIMIT, keyword: str | None = None) -> list[dict[str, Any]]:
    """Fetch first-party AI company and platform update feeds."""
    return fetch_feed_bundle("ai-official", AI_OFFICIAL_FEEDS, limit=limit, keyword=keyword)


def fetch_ai_media_signals(limit: int = DEFAULT_FEEDS_LIMIT, keyword: str | None = None) -> list[dict[str, Any]]:
    """Fetch curated AI media RSS signals with source-level filters."""
    return fetch_feed_bundle("ai-media", AI_MEDIA_FEEDS, limit=limit, keyword=keyword)


def load_watchlist(path: str | Path | None = None) -> list[dict[str, str]]:
    """Load explicit RSS/Atom watchlist entries from JSON, JSONL, or plain text."""
    watchlist_path = Path(path).expanduser() if path else DEFAULT_FEED_WATCHLIST_PATH
    if not watchlist_path.exists():
        return []
    raw = watchlist_path.read_text(encoding="utf-8")
    entries: list[dict[str, str]] = []
    try:
        data = json.loads(raw)
        rows = data.get("feeds") if isinstance(data, dict) else data
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, str):
                    entries.append({"url": row, "title": ""})
                elif isinstance(row, dict):
                    entries.append(
                        {
                            "url": str(row.get("url") or row.get("feed_url") or row.get("xmlUrl") or "").strip(),
                            "title": str(row.get("title") or row.get("name") or "").strip(),
                            "category": str(row.get("category") or "").strip(),
                        }
                    )
            return [entry for entry in entries if entry.get("url")]
    except Exception:
        pass
    for line in raw.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        if clean.startswith("{"):
            try:
                row = json.loads(clean)
            except Exception:
                row = {}
            if isinstance(row, dict):
                url = str(row.get("url") or row.get("feed_url") or "").strip()
                if url:
                    entries.append({"url": url, "title": str(row.get("title") or row.get("name") or "").strip()})
            continue
        parts = [part.strip() for part in clean.split("\t")]
        if parts:
            entries.append({"url": parts[0], "title": parts[1] if len(parts) > 1 else ""})
    return [entry for entry in entries if entry.get("url")]


def fetch_watchlist(
    limit: int = DEFAULT_FEEDS_LIMIT,
    path: str | Path | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch a local explicit RSS watchlist.

    This internalizes the reliable part of blogwatcher-style workflows: explicit
    feed URLs first, cached/stale status visible, no external binary dependency.
    """
    entries = load_watchlist(path)
    if keyword:
        needle = keyword.strip().lower()
        entries = [
            entry
            for entry in entries
            if needle in f"{entry.get('title', '')} {entry.get('url', '')} {entry.get('category', '')}".lower()
        ]
    if not entries:
        return [
            _feed_failure_item(
                url=str(Path(path).expanduser() if path else DEFAULT_FEED_WATCHLIST_PATH),
                source_id="watchlist",
                category="source_status",
                content_direction=FEED_SOURCE_CATALOG["watchlist"]["content_direction"],
                error="未找到本地订阅源清单；支持 JSON、JSONL 或每行一个 RSS/Atom URL。",
            )
        ]
    per_source_limit = max(1, min(max(limit, 1), max(5, (max(limit, 1) + len(entries) - 1) // len(entries))))
    items: list[dict[str, Any]] = []
    for entry in entries:
        source_items = fetch_rss_feed(
            entry["url"],
            limit=per_source_limit,
            source_id="watchlist",
            category=entry.get("category") or "reading",
            content_direction=FEED_SOURCE_CATALOG["watchlist"]["content_direction"],
        )
        for item in source_items:
            row = dict(item)
            if entry.get("title") and row.get("source_title") in {"订阅源观察", "watchlist", ""}:
                row["source_title"] = entry["title"]
            row["watchlist_source"] = {
                "title": entry.get("title", ""),
                "url": entry.get("url", ""),
                "path": str(Path(path).expanduser() if path else DEFAULT_FEED_WATCHLIST_PATH),
            }
            if row.get("evidence_role") == "reading_signal":
                row["evidence_role"] = "watchlist_update_signal"
            risk_tags = [str(tag) for tag in row.get("risk_tags", []) if tag]
            if "user_watchlist" not in risk_tags:
                risk_tags.append("user_watchlist")
            row["risk_tags"] = risk_tags
            items.append(row)
    items.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)
    for rank, item in enumerate(items[: max(limit, 1)], 1):
        item["rank"] = rank
    return items[: max(limit, 1)]


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
    watchlist_path: str | Path | None = None,
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
    if resolved == "arxiv":
        return fetch_arxiv(keyword or "", limit=limit)
    if resolved == "ai-vertical":
        return fetch_ai_vertical_signals(
            keyword or "",
            limit=limit,
            category=category,
            keyword=keyword,
        )
    if resolved == "ai-official":
        return fetch_ai_official_updates(limit=limit, keyword=keyword)
    if resolved == "ai-media":
        return fetch_ai_media_signals(limit=limit, keyword=keyword)
    if resolved == "watchlist":
        return fetch_watchlist(limit=limit, path=watchlist_path, keyword=keyword)
    if resolved.startswith(("http://", "https://")):
        return fetch_rss_feed(resolved, limit=limit, source_id="rss")
    raise ValueError("feeds source must be curated, ai-vertical, ai-official, ai-media, arxiv, watchlist, baidu-rss, wechat-rss, curated-sources, list, or an RSS/Atom URL")


def list_curated_sources(
    limit: int = DEFAULT_FEEDS_LIMIT,
    query: str | None = None,
    opml_url: str = CURATED_OPML_URL,
) -> list[dict[str, Any]]:
    """Fetch the public OPML catalog and return feed sources."""
    cache_key = _feed_cache_key("opml", {"opml_url": opml_url, "query": query or ""})
    try:
        raw = _read_bytes(opml_url)
        root = ElementTree.fromstring(raw)
    except Exception as exc:
        error, diagnostic = _feed_error_details(exc, source_id="curated:source", operation="fetch_opml")
        cached = _feed_cache_get_any("opml", cache_key)
        if cached and isinstance(cached.get("sources"), list):
            sources = [dict(item) for item in cached["sources"][: max(limit, 1)]]
            for source in sources:
                risk_tags = [str(tag) for tag in source.get("risk_tags", []) if tag]
                if "stale_cache" not in risk_tags:
                    risk_tags.append("stale_cache")
                source["risk_tags"] = risk_tags
                source["feed_status"] = {
                    "status": "stale_cache",
                    "source_id": "curated:source",
                    "stale": True,
                    "error": error,
                    "network_diagnostic": diagnostic,
                }
            return sources
        return [
            FeedSource(
                title="精品 RSS 源目录暂时不可用",
                url=opml_url,
                source_id="curated:source",
                category="source_status",
                content_direction="公开 OPML 源本次请求失败，且本机还没有最近成功缓存。",
                rank=1,
                source_confidence="low",
                risk_tags=["source_unavailable", "no_cache"],
            ).to_dict()
        ]
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
    _feed_cache_set("opml", cache_key, {"sources": sources, "opml_url": opml_url, "query": query or ""})
    return sources


def format_feed_catalog_markdown(catalog: dict[str, dict[str, Any]] | None = None) -> str:
    """Render source classification and routing guidance."""
    data = catalog or list_feed_sources()
    lines = [
        "# 观澜 RSS 信源路由",
        "",
        "这些入口都只读公开 RSS/OPML/API。路由原则：实时热点看动态源，深度阅读看精品内容流，AI/WPS 研究看垂类精选动态源，长期扩源看源目录。",
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
        feed_status = item.get("feed_status") or {}
        if feed_status.get("status") == "stale_cache":
            meta.append("缓存兜底: 是")
        elif feed_status.get("status") == "error":
            meta.append("信源状态: 暂不可用")
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
        feed_status = item.get("feed_status") or {}
        if feed_status:
            lines.append(f"  feed_status: {feed_status.get('status', '')}")
            if feed_status.get("stale"):
                lines.append("  boundary: 当前条目来自最近成功缓存，外部 RSS 源本次请求失败。")
            elif feed_status.get("status") == "error":
                lines.append("  boundary: 外部 RSS 源本次请求失败，且本机没有可用缓存。")
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
            "feed_status": item.get("feed_status") or {},
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
