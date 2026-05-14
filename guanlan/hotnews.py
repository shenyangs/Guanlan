# -*- coding: utf-8 -*-
"""Native hotnews sources and formatters for Guanlan.

The first native sources intentionally use public, read-only endpoints. They do
not require cookies, browser access, or Keychain integration.
"""

from __future__ import annotations

import html
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from guanlan.limits import DEFAULT_HOTNEWS_LIMIT, MAX_HOTNEWS_PER_SOURCE_LIMIT
from guanlan.source_registry import (
    get_source_metadata,
    list_hotnews_sources,
    list_optional_backend_sources,
    resolve_source_id,
)
from guanlan.source_taxonomy import source_card_for_domain

_UA = "Mozilla/5.0"
_TIMEOUT = 12
DEFAULT_NEWSNOW_BASE_URL = "https://newsnow.busiyi.world"
VVHAN_HOTLIST_BASE_URL = "https://hot-api.vhan.eu.org/v2"
UAPI_HOTBOARD_BASE_URL = "https://uapis.cn"
TOPHUB_BASE_URL = "https://tophub.today"
EXTERNAL_HOTNEWS_BACKENDS = {"newsnow", "vvhan", "uapis", "tophub", "hotboard", "ebrun"}
EXTERNAL_HOTNEWS_RISK_TAGS = ("external_backend", "third_party_aggregation", "provider_volatility")
HOTNEWS_CACHE_VERSION = 1
HOTNEWS_CACHE_MAX_AGE_SECONDS = 900
HOTNEWS_STALE_CACHE_SECONDS = 7 * 24 * 60 * 60
UAPI_HOTBOARD_PLATFORMS: tuple[str, ...] = (
    "36kr", "51cto", "52pojie", "acfun", "baidu", "bilibili", "coolapk", "csdn",
    "douban-group", "douban-movie", "douyin", "earthquake", "genshin", "guokr",
    "hellogithub", "history", "honkai", "hostloc", "hupu", "huxiu", "ifanr",
    "ithome", "ithome-xijiayi", "jianshu", "juejin", "kuaishou", "lol",
    "netease-music", "netease-news", "ngabbs", "nodeseek", "qq-music", "qq-news",
    "sina", "sina-news", "sspai", "starrail", "thepaper", "tieba", "toutiao",
    "v2ex", "weatheralarm", "weibo", "weread", "zhihu", "zhihu-daily",
)
TOPHUB_CATEGORY_IDS: tuple[str, ...] = (
    "news", "tech", "ent", "community", "shopping", "finance", "developer", "brief", "ai",
    "epaper", "design", "university", "organization", "blog", "wxmp",
)
TOPHUB_SOURCE_ALIASES: dict[str, str] = {
    "weibo": "KqndgxeLl9",
    "zhihu": "mproPpoq6O",
}
VVHAN_TYPE_ALIASES: dict[str, str] = {
    "all": "all",
    "weibo": "wbHot",
    "wbhot": "wbHot",
    "zhihu": "zhihuHot",
    "baidu": "baiduRD",
    "douyin": "douyinHot",
    "toutiao": "toutiao",
    "thepaper": "pengPai",
    "qq-news": "qqNews",
    "netease-news": "wyNews",
    "36kr": "36Ke",
    "ithome": "itNews",
    "huxiu": "huXiu",
}
YOUTUBE_AI_CHANNELS: tuple[tuple[str, str], ...] = (
    ("Peter Yang", "UCnpBg7yqNauHtlNSpOl5-cg"),
    ("Lenny's Podcast", "UC6t1O76G0jYXOAoYCm153dA"),
    ("20VC", "UCf0PBRjhf0rF8fWBIxTuoWA"),
)


@dataclass
class HotNewsItem:
    """Unified hotnews item consumed by agents and formatters."""

    platform: str
    source_id: str
    category: str
    title: str
    url: str = ""
    mobile_url: str = ""
    published_at: str = ""
    summary: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = ""
    source_confidence: str = "medium"
    rank: int = 0
    evidence_role: str = ""
    source_card: dict[str, Any] = field(default_factory=dict)
    risk_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SOURCE_CATALOG: dict[str, dict[str, Any]] = {
    source_id: meta
    for source_id, meta in list_hotnews_sources().items()
    if meta.get("backend") == "native"
}
NEWSNOW_RECOMMENDED_SOURCES: dict[str, dict[str, Any]] = list_optional_backend_sources("newsnow")


def list_sources() -> dict[str, dict[str, Any]]:
    """Return supported native hotnews source metadata."""
    sources = dict(list_hotnews_sources())
    try:
        sources.update(list_external_hotnews_catalog())
    except NameError:
        pass
    return sources


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(url: str, timeout: int = _TIMEOUT, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "application/json,text/plain,*/*",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except TypeError:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _read_text(url: str, timeout: int = _TIMEOUT, headers: dict[str, str] | None = None) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except TypeError:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _guanlan_cache_dir() -> Path:
    path = Path.home() / ".guanlan" / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _hotnews_cache_path() -> Path:
    return _guanlan_cache_dir() / "hotnews-providers.json"


def _load_hotnews_cache() -> dict[str, Any]:
    path = _hotnews_cache_path()
    if not path.exists():
        return {"version": HOTNEWS_CACHE_VERSION, "entries": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": HOTNEWS_CACHE_VERSION, "entries": {}}
        data.setdefault("entries", {})
        return data
    except (OSError, json.JSONDecodeError):
        return {"version": HOTNEWS_CACHE_VERSION, "entries": {}}


def _save_hotnews_cache(data: dict[str, Any]) -> None:
    path = _hotnews_cache_path()
    data["version"] = HOTNEWS_CACHE_VERSION
    try:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except OSError:
        return


def _cache_age_seconds(entry: dict[str, Any]) -> float | None:
    fetched_at = entry.get("fetched_at")
    if not fetched_at:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(str(fetched_at))).total_seconds()
    except ValueError:
        return None


def _cache_key(provider: str, source: str) -> str:
    return f"{provider}:{source}".lower()


def _fetch_external_with_cache(provider: str, source: str, fetcher, *, cache_ttl: int = HOTNEWS_CACHE_MAX_AGE_SECONDS) -> list[dict[str, Any]]:
    key = _cache_key(provider, source)
    cache = _load_hotnews_cache()
    entries = cache.setdefault("entries", {})
    cached = entries.get(key) if isinstance(entries, dict) else None
    if isinstance(cached, dict):
        age = _cache_age_seconds(cached)
        if age is not None and age <= cache_ttl and isinstance(cached.get("items"), list):
            return _mark_provider_items(cached["items"], provider, "cache", {"cache_age_seconds": int(age)})

    try:
        items = fetcher()
        if not items:
            raise RuntimeError("provider returned no parseable hotnews rows")
        entries[key] = {"fetched_at": _now_iso(), "items": items}
        _save_hotnews_cache(cache)
        return _mark_provider_items(items, provider, "success")
    except Exception as exc:
        if isinstance(cached, dict) and isinstance(cached.get("items"), list):
            age = _cache_age_seconds(cached)
            if age is not None and age <= HOTNEWS_STALE_CACHE_SECONDS:
                return _mark_provider_items(
                    cached["items"],
                    provider,
                    "stale_cache",
                    {"cache_age_seconds": int(age), "provider_error": str(exc)},
                )
        raise


def _mark_provider_items(
    items: list[dict[str, Any]],
    provider: str,
    status: str,
    extra_metrics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    marked: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        metrics = dict(item.get("metrics") or {})
        metrics["provider"] = provider
        metrics["provider_status"] = status
        if extra_metrics:
            metrics.update(extra_metrics)
        item["metrics"] = metrics
        risk_tags = list(item.get("risk_tags") or [])
        risk_tags.extend(EXTERNAL_HOTNEWS_RISK_TAGS)
        if status == "stale_cache":
            risk_tags.append("stale_cache")
            item.setdefault("source_confidence", "low")
        item["risk_tags"] = _unique(risk_tags)
        marked.append(enrich_hotnews_item(item))
    return marked


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def _strip_html(value: Any) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _pick(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return ""


def _unix_time_iso(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _unique(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _source_meta(source_id: str) -> dict[str, Any]:
    return get_source_metadata(source_id)


def _domain_from_url(url: Any) -> str:
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except Exception:
        return ""
    return (parsed.netloc or "").lower().removeprefix("www.")


def _source_domain(source_id: str, url: Any = "", platform: str | None = None) -> str:
    domain = _domain_from_url(url)
    if domain:
        return domain
    meta = _source_meta(source_id)
    domain = str(meta.get("source_domain") or "")
    if domain:
        return domain
    platform_value = (platform or meta.get("platform") or source_id).strip()
    if "." in platform_value:
        return platform_value.removeprefix("newsnow:")
    return ""


def _source_card_for_hotnews(source_id: str, url: Any = "", platform: str | None = None) -> dict[str, Any]:
    domain = _source_domain(source_id, url=url, platform=platform)
    if not domain:
        return {
            "domain": "",
            "source_type": "热榜/聚合源",
            "authority_role": "trend_signal",
            "content_roles": ["fresh_signal"],
            "risk_tags": ["sample_boundary"],
            "authority_score": 0.2,
            "sample_value": 0.65,
            "freshness_value": 0.85,
            "stability": "best_effort",
        }
    preferred_scope = "ecommerce" if source_id.startswith("ebrun:") else None
    return source_card_for_domain(domain, preferred_scope=preferred_scope).to_dict()


def _default_evidence_role(category: str) -> str:
    mapping = {
        "finance": "market_news_signal",
        "tech": "tech_news_signal",
        "community": "developer_discussion_signal",
        "social": "public_discussion_signal",
        "video": "video_attention_signal",
        "wechat": "article_signal",
        "hotnews": "fresh_trend_signal",
    }
    return mapping.get((category or "").lower(), "open_web_signal")


def _hotnews_risk_tags(source_id: str, source_card: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    meta = _source_meta(source_id)
    tags.extend(str(tag) for tag in meta.get("risk_tags", []) if tag)
    tags.extend(str(tag) for tag in source_card.get("risk_tags", []) if tag)
    if meta.get("backend") == "optional" or meta.get("optional_backend") == "newsnow":
        tags.append("external_backend")
    return _unique(tags)


def enrich_hotnews_item(item: dict[str, Any]) -> dict[str, Any]:
    """Ensure a hotnews row carries Guanlan evidence metadata."""
    row = dict(item)
    source_id = _clean_text(row.get("source_id") or row.get("platform") or "unknown")
    category = _clean_text(row.get("category") or _source_meta(source_id).get("category") or "hotnews")
    platform = _clean_text(row.get("platform") or _source_meta(source_id).get("platform") or source_id)
    row["source_id"] = source_id
    row["platform"] = platform
    row["category"] = category
    row.setdefault("fetched_at", _now_iso())
    row.setdefault("source_confidence", "medium")
    if not row.get("source_card"):
        row["source_card"] = _source_card_for_hotnews(source_id, url=row.get("url", ""), platform=platform)
    if not row.get("evidence_role"):
        row["evidence_role"] = str(_source_meta(source_id).get("evidence_role") or _default_evidence_role(category))
    row["risk_tags"] = _unique(list(row.get("risk_tags") or []) + _hotnews_risk_tags(source_id, row.get("source_card") or {}))
    return row


def _item(
    *,
    source_id: str,
    title: Any,
    url: Any = "",
    mobile_url: Any = "",
    summary: Any = "",
    metrics: dict[str, Any] | None = None,
    rank: int = 0,
    category: str | None = None,
    platform: str | None = None,
    published_at: Any = "",
    confidence: str = "high",
) -> HotNewsItem:
    meta = SOURCE_CATALOG.get(source_id, {})
    source_card = _source_card_for_hotnews(source_id, url=url, platform=platform)
    risk_tags = _hotnews_risk_tags(source_id, source_card)
    return HotNewsItem(
        platform=platform or meta.get("platform", source_id),
        source_id=source_id,
        category=category or meta.get("category", "hotnews"),
        title=_clean_text(title),
        url=_clean_text(url),
        mobile_url=_clean_text(mobile_url),
        published_at=_clean_text(published_at),
        summary=_clean_text(summary),
        metrics=metrics or {},
        fetched_at=_now_iso(),
        source_confidence=confidence,
        rank=rank,
        evidence_role=str(meta.get("evidence_role") or _default_evidence_role(category or meta.get("category", "hotnews"))),
        source_card=source_card,
        risk_tags=risk_tags,
    )


def fetch_baidu(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch Baidu realtime hot search using its public board endpoint."""
    payload = _read_json("https://top.baidu.com/api/board?platform=wise&tab=realtime")
    cards = ((payload.get("data") or {}).get("cards") or []) if isinstance(payload, dict) else []
    content: list[dict[str, Any]] = []
    for card in cards:
        if isinstance(card, dict):
            content = _flatten_baidu_content(card.get("content"))
        if content:
            break

    results: list[HotNewsItem] = []
    for idx, raw in enumerate(content[:limit], start=1):
        title = _pick(raw, "word", "query", "title")
        url = _pick(raw, "url", "rawUrl", "pcUrl")
        if not url and title:
            query = urllib.parse.quote(str(title))
            url = f"https://www.baidu.com/s?wd={query}"
        results.append(
            _item(
                source_id="baidu",
                title=title,
                url=url,
                mobile_url=_pick(raw, "appUrl", "mUrl", "mobileUrl"),
                summary=_pick(raw, "desc", "summary"),
                metrics={
                    "heat": _pick(raw, "hotScore", "hot_score"),
                    "label": _pick(raw, "newHotName", "hotTag", "tag", "label"),
                },
                rank=idx,
            )
        )
    return [item for item in results if item.title]


def _flatten_baidu_content(value: Any) -> list[dict[str, Any]]:
    """Baidu board responses can nest rows under content[].content."""
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        if entry.get("word") or entry.get("title"):
            rows.append(entry)
            continue
        nested = entry.get("content")
        if isinstance(nested, list):
            rows.extend(item for item in nested if isinstance(item, dict))
    return rows


def fetch_weibo(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch Weibo hot searches from a public read-only endpoint."""
    payload = _read_json(
        "https://weibo.com/ajax/side/hotSearch",
        headers={"Referer": "https://weibo.com/"},
    )
    data = payload.get("data") if isinstance(payload, dict) else {}
    rows = data.get("realtime") if isinstance(data, dict) else []

    results: list[HotNewsItem] = []
    for idx, raw in enumerate((rows or [])[:limit], start=1):
        if not isinstance(raw, dict):
            continue
        word = _pick(raw, "word", "note", "small_icon_desc")
        scheme = _pick(raw, "word_scheme")
        query = scheme or word
        url = f"https://s.weibo.com/weibo?q={urllib.parse.quote(str(query))}" if query else ""
        results.append(
            _item(
                source_id="weibo",
                title=word,
                url=url,
                summary=_pick(raw, "note", "category"),
                metrics={
                    "heat": _pick(raw, "num", "raw_hot"),
                    "label": _pick(raw, "flag_desc", "icon_desc", "small_icon_desc"),
                    "category": _pick(raw, "category"),
                },
                rank=idx,
                confidence="medium",
            )
        )
    return [item for item in results if item.title]


def fetch_bilibili(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch Bilibili all-site popular videos from its public ranking API."""
    payload = _read_json("https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all")
    data = payload.get("data") if isinstance(payload, dict) else {}
    rows = data.get("list") if isinstance(data, dict) else []
    if not rows:
        payload = _read_json(f"https://api.bilibili.com/x/web-interface/popular?ps={int(limit)}&pn=1")
        data = payload.get("data") if isinstance(payload, dict) else {}
        rows = data.get("list") if isinstance(data, dict) else []

    results: list[HotNewsItem] = []
    for idx, raw in enumerate((rows or [])[:limit], start=1):
        if not isinstance(raw, dict):
            continue
        owner = raw.get("owner") if isinstance(raw.get("owner"), dict) else {}
        stat = raw.get("stat") if isinstance(raw.get("stat"), dict) else {}
        bvid = _pick(raw, "bvid")
        url = _pick(raw, "short_link_v2", "short_link") or (
            f"https://www.bilibili.com/video/{bvid}" if bvid else ""
        )
        results.append(
            _item(
                source_id="bilibili",
                title=_pick(raw, "title"),
                url=url,
                summary=_pick(raw, "desc"),
                metrics={
                    "heat": _pick(stat, "view"),
                    "views": _pick(stat, "view"),
                    "likes": _pick(stat, "like"),
                    "replies": _pick(stat, "reply"),
                    "owner": _pick(owner, "name"),
                },
                rank=idx,
            )
        )
    return [item for item in results if item.title]


def fetch_bilibili_hot_search(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch Bilibili hot search words from its public hotword endpoint."""
    payload = _read_json("https://s.search.bilibili.com/main/hotword")
    rows = payload.get("list") if isinstance(payload, dict) else []

    results: list[HotNewsItem] = []
    for idx, raw in enumerate((rows or [])[:limit], start=1):
        if not isinstance(raw, dict):
            continue
        keyword = _pick(raw, "show_name", "keyword", "word", "name")
        if not keyword:
            continue
        query = urllib.parse.quote(str(keyword))
        results.append(
            _item(
                source_id="bilibili-hot-search",
                title=keyword,
                url=f"https://search.bilibili.com/all?keyword={query}",
                summary=_pick(raw, "word_type", "label"),
                metrics={
                    "heat": _pick(raw, "heat_score", "heat"),
                    "heat_layer": _pick(raw, "heat_layer"),
                    "position": _pick(raw, "pos", "position"),
                    "label": _pick(raw, "icon", "label"),
                },
                rank=idx,
            )
        )
    return [item for item in results if item.title]


def fetch_ithome(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch IT Home news from its public RSS feed."""
    raw_xml = _read_text("https://www.ithome.com/rss/")
    root = ElementTree.fromstring(raw_xml)
    rows = root.findall(".//item")

    results: list[HotNewsItem] = []
    for idx, row in enumerate(rows[:limit], start=1):
        results.append(
            _item(
                source_id="ithome",
                title=row.findtext("title", default=""),
                url=row.findtext("link", default=""),
                summary=_strip_html(row.findtext("description", default="")),
                published_at=row.findtext("pubDate", default=""),
                rank=idx,
            )
        )
    return [item for item in results if item.title]


def fetch_sspai(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch Sspai articles from its public RSS feed."""
    raw_xml = _read_text("https://sspai.com/feed")
    root = ElementTree.fromstring(raw_xml)
    rows = root.findall(".//item")

    results: list[HotNewsItem] = []
    for idx, row in enumerate(rows[:limit], start=1):
        results.append(
            _item(
                source_id="sspai",
                title=row.findtext("title", default=""),
                url=row.findtext("link", default=""),
                summary=_strip_html(row.findtext("description", default="")),
                published_at=row.findtext("pubDate", default=""),
                rank=idx,
            )
        )
    return [item for item in results if item.title]


def fetch_xinzhiyuan(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch Xinzhiyuan posts from its public WordPress JSON API."""
    page_size = min(max(int(limit), 1), 100)
    payload = _read_json(f"https://aiera.com.cn/wp-json/wp/v2/posts?per_page={page_size}&page=1")
    rows = payload if isinstance(payload, list) else []

    results: list[HotNewsItem] = []
    for idx, raw in enumerate(rows[:limit], start=1):
        if not isinstance(raw, dict):
            continue
        title_obj = raw.get("title") if isinstance(raw.get("title"), dict) else {}
        excerpt_obj = raw.get("excerpt") if isinstance(raw.get("excerpt"), dict) else {}
        title = _strip_html(_pick(title_obj, "rendered") or _pick(raw, "title"))
        url = _pick(raw, "link", "url")
        if not title or not url:
            continue
        results.append(
            _item(
                source_id="xinzhiyuan",
                title=title,
                url=url,
                summary=_strip_html(_pick(excerpt_obj, "rendered")),
                published_at=_pick(raw, "date_gmt", "date", "modified_gmt"),
                metrics={"post_id": _pick(raw, "id")},
                rank=idx,
            )
        )
    return [item for item in results if item.title]


def fetch_youtube_ai_rss(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch a small curated set of public YouTube AI channel RSS feeds."""
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    results: list[HotNewsItem] = []
    per_channel = max(1, min(15, int(limit)))
    for channel_name, channel_id in YOUTUBE_AI_CHANNELS:
        if len(results) >= limit:
            break
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={urllib.parse.quote(channel_id)}"
        try:
            raw_xml = _read_text(feed_url, headers={"Accept": "application/atom+xml,application/xml,text/xml,*/*"})
            root = ElementTree.fromstring(raw_xml)
        except Exception:
            continue
        for entry in root.findall("atom:entry", ns)[:per_channel]:
            if len(results) >= limit:
                break
            link_el = entry.find("atom:link[@rel='alternate']", ns)
            if link_el is None:
                link_el = entry.find("atom:link", ns)
            media_group = entry.find("media:group", ns)
            description = ""
            if media_group is not None:
                description = media_group.findtext("media:description", default="", namespaces=ns)
            video_id = entry.findtext("yt:videoId", default="", namespaces=ns)
            url = link_el.get("href", "") if link_el is not None else (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")
            results.append(
                _item(
                    source_id="youtube-ai-rss",
                    title=entry.findtext("atom:title", default="", namespaces=ns),
                    url=url,
                    summary=_strip_html(description),
                    published_at=entry.findtext("atom:published", default="", namespaces=ns),
                    metrics={"channel": channel_name, "channel_id": channel_id, "video_id": video_id},
                    rank=len(results) + 1,
                    confidence="medium",
                )
            )
    return [item for item in results if item.title]


def fetch_zeli_hn(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch Zeli's public Hacker News 24h selection."""
    payload = _read_json("https://zeli.app/api/hacker-news?type=hot24h")
    rows = payload.get("posts") if isinstance(payload, dict) else []

    results: list[HotNewsItem] = []
    for idx, raw in enumerate((rows or [])[:limit], start=1):
        if not isinstance(raw, dict):
            continue
        results.append(
            _item(
                source_id="zeli-hn",
                title=_pick(raw, "title"),
                url=_pick(raw, "url"),
                published_at=_unix_time_iso(_pick(raw, "time")),
                metrics={"hn_id": _pick(raw, "id")},
                rank=idx,
                confidence="medium",
            )
        )
    return [item for item in results if item.title]


def fetch_buzzing(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch Buzzing's public structured tech link feed."""
    payload = _read_json("https://www.buzzing.cc/feed.json")
    rows = payload.get("items") if isinstance(payload, dict) else []

    results: list[HotNewsItem] = []
    for idx, raw in enumerate((rows or [])[:limit], start=1):
        if not isinstance(raw, dict):
            continue
        source_name = _pick(raw, "source", "site_name", "channel", "category") or _domain_from_url(_pick(raw, "url"))
        results.append(
            _item(
                source_id="buzzing",
                title=_pick(raw, "title"),
                url=_pick(raw, "url"),
                summary=_pick(raw, "summary", "description"),
                published_at=_pick(raw, "date_published", "date_modified", "published_at"),
                metrics={"source": source_name, "category": _pick(raw, "category")},
                rank=idx,
                confidence="medium",
            )
        )
    return [item for item in results if item.title]


def fetch_zhihu(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch Zhihu hot list using its public topstory endpoint."""
    url = (
        "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"
        f"?limit={int(limit)}&desktop=true"
    )
    payload = _read_json(url)
    rows = payload.get("data") if isinstance(payload, dict) else []

    results: list[HotNewsItem] = []
    for idx, raw in enumerate((rows or [])[:limit], start=1):
        target = raw.get("target") if isinstance(raw, dict) else {}
        target = target if isinstance(target, dict) else {}
        link = target.get("link") if isinstance(target.get("link"), dict) else {}
        title_area = target.get("title_area") if isinstance(target.get("title_area"), dict) else {}
        excerpt_area = target.get("excerpt_area") if isinstance(target.get("excerpt_area"), dict) else {}
        metrics_area = target.get("metrics_area") if isinstance(target.get("metrics_area"), dict) else {}

        title = _pick(target, "title", "question", "name") or _pick(title_area, "text")
        item_url = _pick(target, "url") or _pick(link, "url")
        results.append(
            _item(
                source_id="zhihu",
                title=title,
                url=item_url,
                summary=_pick(target, "excerpt", "excerpt_new") or _pick(excerpt_area, "text"),
                metrics={
                    "heat": _pick(raw, "detail_text") or _pick(metrics_area, "text"),
                    "answer_count": _pick(target, "answer_count"),
                },
                rank=idx,
            )
        )
    return [item for item in results if item.title]


def fetch_v2ex(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[HotNewsItem]:
    """Fetch V2EX hot topics and normalize them as hotnews items."""
    from guanlan.channels.v2ex import V2EXChannel

    topics = V2EXChannel().get_hot_topics(limit=limit)
    results = []
    for idx, raw in enumerate(topics[:limit], start=1):
        results.append(
            _item(
                source_id="v2ex",
                title=raw.get("title", ""),
                url=raw.get("url", ""),
                summary=raw.get("content", ""),
                metrics={
                    "replies": raw.get("replies", 0),
                    "node": raw.get("node_title") or raw.get("node_name"),
                },
                rank=idx,
                published_at=raw.get("created", ""),
            )
        )
    return [item for item in results if item.title]


def fetch_today(limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[dict[str, Any]]:
    """Fetch a diverse daily hotnews snapshot without letting one source dominate."""
    limit = max(int(limit), 1)
    source_fetchers = [
        ("baidu", fetch_baidu),
        ("weibo", fetch_weibo),
        ("bilibili-hot-search", fetch_bilibili_hot_search),
        ("ithome", fetch_ithome),
        ("v2ex", fetch_v2ex),
    ]
    per_source = max(3, min(MAX_HOTNEWS_PER_SOURCE_LIMIT, (limit + len(source_fetchers) - 1) // len(source_fetchers) + 2))
    buckets: list[list[dict[str, Any]]] = []
    errors: list[str] = []

    for source_id, fetcher in source_fetchers:
        try:
            bucket = [item.to_dict() for item in fetcher(limit=per_source)]
            if bucket:
                buckets.append(bucket)
        except Exception as exc:  # Keep the aggregate useful even when one public endpoint flakes.
            errors.append(f"{source_id}: {exc}")

    merged: list[dict[str, Any]] = []
    for offset in range(per_source):
        for bucket in buckets:
            if offset >= len(bucket) or len(merged) >= limit:
                continue
            item = dict(bucket[offset])
            item["metrics"] = dict(item.get("metrics") or {})
            item["metrics"].setdefault("source_rank", item.get("rank") or offset + 1)
            item["rank"] = len(merged) + 1
            merged.append(item)

    if not merged and errors:
        raise RuntimeError("All native hotnews sources failed: " + "; ".join(errors))
    return _annotate_trends(merged[:limit])


def fetch_newsnow(
    source: str,
    limit: int = DEFAULT_HOTNEWS_LIMIT,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch NewsNow API source and normalize it into Guanlan hotnews rows."""
    source = source.strip()
    if not source:
        raise ValueError("NewsNow source id is required")
    base = (base_url or DEFAULT_NEWSNOW_BASE_URL).strip().rstrip("/")
    url = f"{base}/api/s?id={urllib.parse.quote(source)}"
    payload = _read_json(url)
    items = normalize_hotnews_payload(payload, source_id=f"newsnow:{source}", platform=source)
    return items[: max(limit, 1)]


def list_external_hotnews_catalog(provider: str | None = None) -> dict[str, dict[str, Any]]:
    """Return catalog rows for external aggregate providers without live crawling them."""
    provider_key = (provider or "").strip().lower()
    catalog: dict[str, dict[str, Any]] = {}
    if provider_key in ("", "vvhan"):
        for alias, provider_source in sorted(VVHAN_TYPE_ALIASES.items()):
            if alias == provider_source.lower():
                continue
            catalog[f"vvhan:{alias}"] = {
                "surface": "hotnews",
                "backend": "optional",
                "optional_backend": "vvhan",
                "provider_source_id": provider_source,
                "status": "optional",
                "evidence_role": "fresh_trend_signal",
                "risk_tags": list(EXTERNAL_HOTNEWS_RISK_TAGS),
                "command": f"guanlan hotnews vvhan:{alias} --limit 80",
            }
    if provider_key in ("", "uapis"):
        for platform in UAPI_HOTBOARD_PLATFORMS:
            catalog[f"uapis:{platform}"] = {
                "surface": "hotnews",
                "backend": "optional",
                "optional_backend": "uapis",
                "provider_source_id": platform,
                "status": "optional",
                "evidence_role": "fresh_trend_signal",
                "source_url": f"{UAPI_HOTBOARD_BASE_URL}/hotboard/{platform}",
                "risk_tags": list(EXTERNAL_HOTNEWS_RISK_TAGS),
                "command": f"guanlan hotnews uapis:{platform} --limit 80",
                "caveat": "UAPI 是外部聚合 API/页面，观澜会校验新鲜度并在失败时使用本地缓存兜底。",
            }
    if provider_key in ("", "tophub"):
        for alias, node_id in sorted(TOPHUB_SOURCE_ALIASES.items()):
            catalog[f"tophub:{alias}"] = {
                "surface": "hotnews",
                "backend": "optional",
                "optional_backend": "tophub",
                "provider_source_id": node_id,
                "status": "optional",
                "evidence_role": "fresh_trend_signal",
                "source_url": f"{TOPHUB_BASE_URL}/n/{node_id}",
                "risk_tags": list(EXTERNAL_HOTNEWS_RISK_TAGS),
                "command": f"guanlan hotnews tophub:{alias} --limit 80",
            }
        for category in TOPHUB_CATEGORY_IDS:
            catalog[f"tophub:catalog:{category}"] = {
                "surface": "hotnews",
                "backend": "optional",
                "optional_backend": "tophub",
                "provider_source_id": category,
                "status": "catalog",
                "evidence_role": "source_catalog_entry",
                "source_url": f"{TOPHUB_BASE_URL}/c/{category}",
                "risk_tags": list(EXTERNAL_HOTNEWS_RISK_TAGS),
                "command": f"guanlan hotnews tophub:catalog:{category} --limit 80",
            }
    if provider_key in ("", "hotboard"):
        catalog["hotboard:catalog"] = {
            "surface": "hotnews",
            "backend": "optional",
            "optional_backend": "hotboard",
            "provider_source_id": "local_nodes_catalog",
            "status": "catalog",
            "evidence_role": "source_catalog_entry",
            "source_url": "packaged:guanlan/data/hotboard_nodes.json",
            "risk_tags": list(EXTERNAL_HOTNEWS_RISK_TAGS) + ["paid_api_optional"],
            "command": "guanlan hotnews hotboard:catalog --limit 100",
            "caveat": "本地目录随包提供；详情 API 需显式配置 key，默认不产生额度消耗。",
        }
        for alias, node_id in sorted(_hotboard_common_aliases().items()):
            catalog[f"hotboard:{alias}"] = {
                "surface": "hotnews",
                "backend": "optional",
                "optional_backend": "hotboard",
                "provider_source_id": node_id,
                "status": "opt-in",
                "evidence_role": "fresh_trend_signal",
                "source_url": "",
                "risk_tags": list(EXTERNAL_HOTNEWS_RISK_TAGS) + ["paid_api_optional", "cost_metered"],
                "command": f"guanlan hotnews hotboard:{alias} --limit 80",
                "caveat": "详情接口约 1u/次，观澜只在显式调用时使用，并带缓存兜底。",
            }
    if provider_key in ("", "ebrun"):
        from guanlan.ebrun_channels import list_ebrun_channels

        for row in list_ebrun_channels():
            source_id = str(row.get("source_id") or "")
            alias = source_id.split(":", 1)[1] if ":" in source_id else source_id
            catalog[source_id] = {
                "surface": "hotnews",
                "backend": "native",
                "optional_backend": "ebrun",
                "provider_source_id": alias,
                "status": "best-effort",
                "evidence_role": row.get("evidence_role") or "ecommerce_vertical_feed",
                "source_url": row.get("api_url") or "https://www.ebrun.com/",
                "risk_tags": ["official_vertical_feed", "server_side_limit_low", "public_json_endpoint"],
                "command": f"guanlan hotnews {source_id} --limit 10",
                "caveat": row.get("server_limit_note") or "",
            }
    return catalog


def _hotboard_common_aliases() -> dict[str, str]:
    try:
        from guanlan.hotboard_catalog import COMMON_ALIASES

        return {
            alias: node_id
            for alias, node_id in COMMON_ALIASES.items()
            if re.fullmatch(r"[a-z0-9_.-]+", alias)
        }
    except Exception:
        return {}


def fetch_vvhan(source: str = "all", limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[dict[str, Any]]:
    """Fetch VVHan/HotList-Web aggregate API and normalize rows with freshness metadata."""
    source_key = (source or "all").strip()
    provider_source = VVHAN_TYPE_ALIASES.get(source_key.lower(), source_key)

    def _fetch() -> list[dict[str, Any]]:
        payload = _read_json(f"{VVHAN_HOTLIST_BASE_URL}?type=all")
        groups = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(groups, list):
            groups = []
        selected: list[dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            rows = group.get("data")
            if not isinstance(rows, list):
                continue
            group_name = _clean_text(group.get("name") or group.get("subtitle") or "")
            group_time = _clean_text(group.get("update_time"))
            if provider_source.lower() != "all":
                matches_group = provider_source.lower() in {
                    _clean_text(group.get("type")).lower(),
                    group_name.lower(),
                    _clean_text(group.get("name")).lower(),
                }
                matches_rows = any(
                    isinstance(row, dict) and _clean_text(row.get("type")).lower() == provider_source.lower()
                    for row in rows
                )
                if not matches_group and not matches_rows:
                    continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                enriched = dict(row)
                enriched.setdefault("source_group", group_name)
                enriched.setdefault("update_time", group_time)
                selected.append(enriched)
                if len(selected) >= limit:
                    break
            if len(selected) >= limit:
                break
        items = _normalize_external_rows(
            selected,
            source_id=f"vvhan:{source_key.lower()}",
            platform=f"vvhan:{provider_source}",
            provider="vvhan",
            url_fallback_base="https://www.vvhan.com",
        )
        return _flag_stale_vvhan_items(items)

    return _fetch_external_with_cache("vvhan", source_key, _fetch)[: max(limit, 1)]


def fetch_uapis(source: str = "weibo", limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[dict[str, Any]]:
    """Fetch UAPI hotboard API/page with cache fallback.

    UAPI currently exposes a rich documented hotboard API, but the exact route is
    served through a Next app and can change. We try documented likely routes
    first, then parse server-rendered rows if present, and report a clear
    provider error instead of returning a misleading empty list.
    """
    source_key = (source or "weibo").strip().lower()
    if source_key in {"catalog", "list"}:
        return _catalog_as_items(list_external_hotnews_catalog("uapis"), "uapis")[: max(limit, 1)]

    def _fetch() -> list[dict[str, Any]]:
        candidate_urls = [
            f"{UAPI_HOTBOARD_BASE_URL}/api/v1/misc/hotboard?type={urllib.parse.quote(source_key)}",
            f"{UAPI_HOTBOARD_BASE_URL}/api/misc/hotboard?type={urllib.parse.quote(source_key)}",
            f"{UAPI_HOTBOARD_BASE_URL}/api/hotboard?type={urllib.parse.quote(source_key)}",
            f"{UAPI_HOTBOARD_BASE_URL}/api/get-misc-hotboard?type={urllib.parse.quote(source_key)}",
        ]
        for url in candidate_urls:
            try:
                payload = _read_json(url)
            except Exception:
                continue
            rows = _extract_rows(payload)
            items = _normalize_external_rows(
                [row for row in rows if isinstance(row, dict)],
                f"uapis:{source_key}",
                f"uapis:{source_key}",
                "uapis",
            )
            if items:
                for item in items:
                    metrics = dict(item.get("metrics") or {})
                    metrics.setdefault("provider_updated_at", _pick(payload, "update_time", "updated_at") if isinstance(payload, dict) else "")
                    item["metrics"] = {key: value for key, value in metrics.items() if value not in ("", None)}
                return items

        page_url = f"{UAPI_HOTBOARD_BASE_URL}/hotboard/{urllib.parse.quote(source_key)}"
        text = _read_text(page_url)
        rows = _parse_generic_hotboard_html(text)
        if rows:
            return _normalize_external_rows(rows, f"uapis:{source_key}", f"uapis:{source_key}", "uapis", source_page=page_url)
        raise RuntimeError(
            "UAPI hotboard endpoint was reachable but no parseable rows were found; "
            f"try `guanlan hotnews uapis:catalog` or another provider for {source_key}."
        )

    return _fetch_external_with_cache("uapis", source_key, _fetch)[: max(limit, 1)]


def fetch_ebrun(source: str = "recommend", limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[dict[str, Any]]:
    """Fetch Ebrun channel JSON as a vertical ecommerce/retail news signal."""
    from guanlan.ebrun_channels import EBRUN_SERVER_LIMIT_NOTE, resolve_ebrun_channel

    channel = resolve_ebrun_channel(source)
    payload = _read_json(channel.api_url)
    rows = [row for row in _extract_rows(payload) if isinstance(row, dict)]
    items: list[dict[str, Any]] = []
    for idx, raw in enumerate(rows[: max(limit, 1)], start=1):
        item = _item(
            source_id=channel.source_id,
            platform="ebrun",
            category="ecommerce",
            title=_pick(raw, "title", "name"),
            url=_pick(raw, "url", "link"),
            summary=_pick(raw, "summary", "desc", "description", "excerpt"),
            published_at=_pick(raw, "publish_time", "published_at", "created_at", "time"),
            metrics={
                "author": _pick(raw, "author"),
                "channel": channel.channel,
                "sub_channel": channel.sub_channel,
                "provider_status": "public_json",
                "server_limit_note": EBRUN_SERVER_LIMIT_NOTE,
                "requested_limit": limit,
                "returned_rows": len(rows),
            },
            rank=idx,
            confidence="medium",
        ).to_dict()
        item["evidence_role"] = channel.evidence_role
        item["risk_tags"] = _unique(
            list(item.get("risk_tags") or [])
            + ["official_vertical_feed", "server_side_limit_low", "public_json_endpoint"]
        )
        items.append(enrich_hotnews_item(item))
    return items


def fetch_tophub(source: str = "weibo", limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[dict[str, Any]]:
    """Fetch TopHub node or category HTML and normalize visible rows."""
    source_key = (source or "weibo").strip()
    if source_key in {"catalog", "list"}:
        source_key = "catalog:news"
    if source_key.startswith("catalog:"):
        category = source_key.split(":", 1)[1] or "news"

        def _fetch_catalog() -> list[dict[str, Any]]:
            text = _read_text(f"{TOPHUB_BASE_URL}/c/{urllib.parse.quote(category)}")
            catalog = _parse_tophub_catalog(text, category=category)
            if not catalog:
                raise RuntimeError(f"TopHub category {category!r} returned no parseable source catalog rows")
            return _catalog_entries_as_items(catalog, provider="tophub", source_id=f"tophub:catalog:{category}")

        return _fetch_external_with_cache("tophub", source_key, _fetch_catalog)[: max(limit, 1)]

    node_id = TOPHUB_SOURCE_ALIASES.get(source_key.lower(), source_key)
    node_id = node_id.removeprefix("/n/").strip()

    def _fetch_node() -> list[dict[str, Any]]:
        text = _read_text(f"{TOPHUB_BASE_URL}/n/{urllib.parse.quote(node_id)}")
        rows = _parse_tophub_rows(text)
        if not rows:
            raise RuntimeError(f"TopHub node {node_id!r} returned no parseable rows")
        return _normalize_external_rows(rows, f"tophub:{source_key.lower()}", f"tophub:{node_id}", "tophub")

    return _fetch_external_with_cache("tophub", source_key, _fetch_node)[: max(limit, 1)]


def fetch_hotboard(source: str = "catalog", limit: int = DEFAULT_HOTNEWS_LIMIT) -> list[dict[str, Any]]:
    """Fetch hotboard catalog/detail/snapshot rows with local-first routing."""
    from guanlan import hotboard_catalog as thd

    source_key = (source or "catalog").strip()
    lower = source_key.lower()
    if lower in {"catalog", "list"} or lower.startswith("catalog:"):
        category = source_key.split(":", 1)[1] if ":" in source_key else ""
        nodes = thd.search_catalog(category=category, limit=max(limit, 1))
        meta = thd.catalog_meta()
        entries = [
            {
                "title": f"{node.get('name')} · {node.get('display')}".strip(" ·"),
                "url": node.get("source_url") or "",
                "node_id": node.get("hashid") or "",
                "category": node.get("category_name") or "",
                "summary": node.get("domain") or "",
                "rank": idx,
            }
            for idx, node in enumerate(nodes, start=1)
        ]
        items = _catalog_entries_as_items(
            entries,
            provider="hotboard",
            source_id=f"hotboard:catalog{':' + category if category else ''}",
        )
        for item in items:
            metrics = dict(item.get("metrics") or {})
            metrics.update(
                {
                    "provider": "hotboard",
                    "provider_status": "local_catalog",
                    "catalog_unique_count": meta.get("unique_count"),
                    "catalog_fetched_at": meta.get("fetched_at"),
                    "cost_u": 0,
                }
            )
            item["metrics"] = {key: value for key, value in metrics.items() if value not in ("", None)}
            item["risk_tags"] = _unique(
                list(item.get("risk_tags") or []) + ["local_catalog", "api_key_not_required"]
            )
        return items[: max(limit, 1)]

    if lower.startswith("snapshots:"):
        node_value = source_key.split(":", 1)[1]
        node = thd.resolve_node(node_value)
        if not node:
            raise ValueError(f"Unknown hotboard node: {node_value}")
        node_id = str(node.get("hashid") or "")

        def _fetch_snapshots() -> list[dict[str, Any]]:
            payload = thd.fetch_node_snapshots(node_id)
            rows = payload.get("data") if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                rows = []
            entries: list[dict[str, Any]] = []
            for idx, row in enumerate(rows[: max(limit, 1)], start=1):
                if not isinstance(row, dict):
                    continue
                timestamp = row.get("timestamp")
                ssid = row.get("ssid")
                entries.append(
                    {
                        "title": f"{node.get('name')} · {node.get('display')} 快照 {idx}",
                        "url": node.get("source_url") or "",
                        "summary": f"ssid={ssid} timestamp={timestamp}",
                        "rank": idx,
                        "time": _unix_time_iso(timestamp),
                        "metric": ssid,
                        "node_id": node_id,
                    }
                )
            items = _normalize_external_rows(
                entries,
                source_id=f"hotboard:snapshots:{node_id}",
                platform=f"hotboard:{node_id}",
                provider="hotboard",
            )
            for item in items:
                metrics = dict(item.get("metrics") or {})
                metrics.update(
                    {
                        "provider_node_name": node.get("name"),
                        "provider_node_display": node.get("display"),
                        "snapshot_only": True,
                        "cost_u": 0,
                        "requires_active_balance": True,
                    }
                )
                item["metrics"] = {key: value for key, value in metrics.items() if value not in ("", None)}
            return items

        return _fetch_external_with_cache(
            "hotboard",
            f"snapshots:{node_id}",
            _fetch_snapshots,
            cache_ttl=600,
        )[: max(limit, 1)]

    node_value = source_key.split(":", 1)[1] if lower.startswith("node:") else source_key
    node = thd.resolve_node(node_value)
    if not node:
        raise ValueError(f"Unknown hotboard node: {node_value}")
    node_id = str(node.get("hashid") or "")

    def _fetch_node_detail() -> list[dict[str, Any]]:
        api_error = ""
        if thd.api_key():
            try:
                payload = thd.fetch_node_detail(node_id)
                data = payload.get("data") if isinstance(payload, dict) else {}
                rows = data.get("items") if isinstance(data, dict) else []
                if not isinstance(rows, list):
                    rows = []
                items = _normalize_external_rows(
                    [row for row in rows if isinstance(row, dict)],
                    source_id=f"hotboard:{source_key.lower()}",
                    platform=f"hotboard:{node_id}",
                    provider="hotboard",
                )
                if not items:
                    raise RuntimeError(f"Hotboard node {node_id!r} returned no detail rows.")
                for item in items:
                    metrics = dict(item.get("metrics") or {})
                    metrics.update(
                        {
                            "provider_node_hashid": node_id,
                            "provider_node_name": node.get("name"),
                            "provider_node_display": node.get("display"),
                            "provider_domain": node.get("domain"),
                            "paid_api": True,
                            "cost_u": 1,
                            "estimated_cost_cny": 0.01,
                        }
                    )
                    item["metrics"] = {
                        key: value for key, value in metrics.items() if value not in ("", None)
                    }
                    item["risk_tags"] = _unique(
                        list(item.get("risk_tags") or []) + ["paid_api_optional", "cost_metered"]
                    )
                return items
            except Exception as exc:
                api_error = str(exc)

        fallback = fetch_tophub(node_id, limit=limit)
        for item in fallback:
            metrics = dict(item.get("metrics") or {})
            metrics.update(
                {
                    "provider": "hotboard",
                    "provider_status": "html_fallback",
                    "provider_node_hashid": node_id,
                    "provider_node_name": node.get("name"),
                    "provider_node_display": node.get("display"),
                    "cost_u": 0,
                    "api_error": api_error,
                    "fallback_provider": "public_html",
                }
            )
            item["metrics"] = {key: value for key, value in metrics.items() if value not in ("", None)}
            item["risk_tags"] = _unique(
                list(item.get("risk_tags") or []) + ["html_fallback", "api_key_not_required"]
            )
        return fallback

    return _fetch_external_with_cache("hotboard", f"node:{node_id}", _fetch_node_detail)[: max(limit, 1)]


def _normalize_external_rows(
    rows: list[dict[str, Any]],
    source_id: str,
    platform: str,
    provider: str,
    url_fallback_base: str = "",
    source_page: str = "",
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(rows, start=1):
        title = _pick(raw, "title", "name", "word", "query", "keyword", "text")
        if not title:
            continue
        url = _pick(raw, "url", "link", "href", "mobile_url", "mobil_url")
        if url and str(url).startswith("/"):
            base = source_page or url_fallback_base
            url = urllib.parse.urljoin(base, str(url))
        metrics = {
            "heat": _pick(raw, "hot", "heat", "hot_value", "hotValue", "hotScore", "hot_score", "index", "views", "metric", "extra"),
            "provider_source": _pick(raw, "type", "source_group", "node_id", "category"),
            "provider_updated_at": _pick(raw, "update_time", "updated_at", "time"),
        }
        item = _item(
            source_id=source_id,
            platform=platform,
            title=title,
            url=url,
            mobile_url=_pick(raw, "mobile_url", "mobileUrl", "mobil_url"),
            summary=_pick(raw, "summary", "desc", "description", "excerpt", "content"),
            metrics={key: value for key, value in metrics.items() if value not in ("", None)},
            rank=int(_pick(raw, "rank", "index", "position") or idx),
            published_at=_pick(raw, "published_at", "created_at", "date", "time", "update_time"),
            confidence="medium",
        ).to_dict()
        item["risk_tags"] = _unique(list(item.get("risk_tags") or []) + list(EXTERNAL_HOTNEWS_RISK_TAGS))
        normalized.append(enrich_hotnews_item(item))
    return normalized


def _flag_stale_vvhan_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stale_cutoff = datetime.now() - timedelta(days=2)
    flagged: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        updated = (row.get("metrics") or {}).get("provider_updated_at") or row.get("published_at")
        is_stale = False
        if updated:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    is_stale = datetime.strptime(str(updated)[:19], fmt) < stale_cutoff
                    break
                except ValueError:
                    continue
        if is_stale:
            row["source_confidence"] = "low"
            row["risk_tags"] = _unique(list(row.get("risk_tags") or []) + ["stale_external_snapshot"])
            metrics = dict(row.get("metrics") or {})
            metrics["provider_status"] = "stale_snapshot"
            row["metrics"] = metrics
        flagged.append(row)
    return flagged


def _parse_tophub_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pattern = re.compile(
        r'<a\s+href="([^"]+)"[^>]*>\s*<div class="cc-cd-cb-ll">\s*'
        r'<span class="s[^"]*">\s*(\d+)\s*</span>\s*'
        r'<span class="t">\s*(.*?)\s*</span>\s*'
        r'(?:<span class="e">\s*(.*?)\s*</span>)?',
        re.S,
    )
    for match in pattern.finditer(text):
        rows.append(
            {
                "url": html.unescape(match.group(1)),
                "rank": match.group(2),
                "title": _strip_html(match.group(3)),
                "heat": _strip_html(match.group(4) or ""),
            }
        )
    if rows:
        return rows
    table_pattern = re.compile(
        r'<td align="center">\s*(\d+)\.?\s*</td>\s*'
        r'<td><a href="([^"]+)"[^>]*>(.*?)</a></td>',
        re.S,
    )
    for match in table_pattern.finditer(text):
        rows.append(
            {
                "rank": match.group(1),
                "url": html.unescape(match.group(2)),
                "title": _strip_html(match.group(3)),
            }
        )
    return rows


def _parse_generic_hotboard_html(text: str) -> list[dict[str, Any]]:
    rows = _parse_tophub_rows(text)
    if rows:
        return rows
    return []


def _parse_tophub_catalog(text: str, category: str = "") -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pattern = re.compile(
        r'<a href="/n/([^"]+)">\s*<div class="cc-cd-lb">.*?</div>\s*</a>.*?'
        r'<span class="cc-cd-sb-st">\s*(.*?)\s*</span>',
        re.S,
    )
    for match in pattern.finditer(text):
        block = match.group(0)
        label_match = re.search(r'onerror="[^"]*">\s*([^<]+?)\s*</div>', block, re.S)
        name = _strip_html(label_match.group(1) if label_match else "")
        board = _strip_html(match.group(2))
        node_id = match.group(1)
        if name or board:
            entries.append(
                {
                    "title": f"{name} · {board}".strip(" ·"),
                    "url": f"{TOPHUB_BASE_URL}/n/{node_id}",
                    "node_id": node_id,
                    "category": category,
                    "rank": len(entries) + 1,
                }
            )
    if entries:
        return entries
    for match in re.finditer(r'<a href="/n/([^"]+)"[^>]*>(.*?)</a>', text, re.S):
        title = _strip_html(match.group(2))
        if title:
            entries.append(
                {
                    "title": title,
                    "url": f"{TOPHUB_BASE_URL}/n/{match.group(1)}",
                    "node_id": match.group(1),
                    "category": category,
                    "rank": len(entries) + 1,
                }
            )
    return entries


def _catalog_as_items(catalog: dict[str, dict[str, Any]], provider: str) -> list[dict[str, Any]]:
    return _catalog_entries_as_items(
        [
            {
                "title": key,
                "url": value.get("source_url") or "",
                "node_id": value.get("provider_source_id") or key,
                "category": value.get("category") or "catalog",
                "rank": idx,
            }
            for idx, (key, value) in enumerate(sorted(catalog.items()), start=1)
        ],
        provider=provider,
        source_id=f"{provider}:catalog",
    )


def _catalog_entries_as_items(entries: list[dict[str, Any]], provider: str, source_id: str) -> list[dict[str, Any]]:
    items = _normalize_external_rows(
        entries,
        source_id=source_id,
        platform=f"{provider}:catalog",
        provider=provider,
    )
    for item in items:
        item["category"] = "source_catalog"
        item["evidence_role"] = "source_catalog_entry"
    return items


def fetch_hotnews(
    source: str = "today",
    limit: int = DEFAULT_HOTNEWS_LIMIT,
    backend: str = "auto",
    newsnow_base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch hotnews and return unified dictionaries."""
    raw_source = (source or "today").strip()
    source = raw_source.lower()
    source = resolve_source_id(source)
    backend = (backend or "auto").lower().strip()
    fetchers = {
        "today": fetch_today,
        "baidu": fetch_baidu,
        "weibo": fetch_weibo,
        "bilibili-hot-search": fetch_bilibili_hot_search,
        "bilibili": fetch_bilibili,
        "ithome": fetch_ithome,
        "sspai": fetch_sspai,
        "xinzhiyuan": fetch_xinzhiyuan,
        "youtube-ai-rss": fetch_youtube_ai_rss,
        "zeli-hn": fetch_zeli_hn,
        "buzzing": fetch_buzzing,
        "zhihu": fetch_zhihu,
        "v2ex": fetch_v2ex,
    }
    raw_external = raw_source.split(":", 1)[1] if ":" in raw_source else ""
    if source.startswith("vvhan:"):
        return fetch_vvhan(raw_external or source.split(":", 1)[1], limit=limit)
    if source.startswith("uapis:"):
        return fetch_uapis(raw_external or source.split(":", 1)[1], limit=limit)
    if source.startswith("tophub:"):
        return fetch_tophub(raw_external or source.split(":", 1)[1], limit=limit)
    if source.startswith("hotboard:"):
        return fetch_hotboard(raw_external or source.split(":", 1)[1], limit=limit)
    if source.startswith("ebrun:"):
        return fetch_ebrun(raw_external or source.split(":", 1)[1], limit=limit)
    if source.startswith("newsnow:"):
        return fetch_newsnow(source.split(":", 1)[1], limit=limit, base_url=newsnow_base_url)
    if backend == "vvhan":
        return fetch_vvhan(source, limit=limit)
    if backend == "uapis":
        return fetch_uapis(source, limit=limit)
    if backend == "tophub":
        return fetch_tophub(source, limit=limit)
    if backend == "hotboard":
        return fetch_hotboard(source, limit=limit)
    if backend == "ebrun":
        return fetch_ebrun(source, limit=limit)
    if backend == "newsnow":
        return fetch_newsnow(source, limit=limit, base_url=newsnow_base_url)
    if backend not in {"auto", "native"}:
        raise ValueError("backend must be one of: auto, native, newsnow, vvhan, uapis, tophub, hotboard, ebrun")
    if source not in fetchers:
        if backend == "auto":
            return fetch_newsnow(source, limit=limit, base_url=newsnow_base_url)
        external = list_external_hotnews_catalog()
        available = ", ".join(
            sorted(fetchers)
            + [f"newsnow:{name}" for name in sorted(NEWSNOW_RECOMMENDED_SOURCES)]
            + sorted(external)[:20]
        )
        raise ValueError(f"Unknown hotnews source: {source}. Available: {available}")
    items = [
        item.to_dict() if hasattr(item, "to_dict") else dict(item)
        for item in fetchers[source](limit=limit)
    ]
    return _annotate_trends(items) if source == "today" else items


def normalize_hotnews_payload(
    payload: Any,
    source_id: str = "unknown",
    platform: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize common hotnews payload shapes into Guanlan items.

    This accepts native output, NewsNow-like JSON, and generic arrays of cards.
    """
    rows = _extract_rows(payload)
    items: list[dict[str, Any]] = []
    for idx, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            continue
        if {"platform", "source_id", "title"}.issubset(raw.keys()):
            item = dict(raw)
            item.setdefault("rank", idx)
            item.setdefault("fetched_at", _now_iso())
            items.append(enrich_hotnews_item(item))
            continue

        title = _pick(raw, "title", "name", "word", "query", "keyword")
        if not title:
            continue
        metrics = {
            "heat": _pick(raw, "hot", "heat", "hot_value", "hotValue", "hotScore", "hot_score", "index", "views"),
            "comments": _pick(raw, "comments", "comment_count", "reply_count"),
        }
        item = _item(
            source_id=source_id,
            platform=platform or source_id,
            title=title,
            url=_pick(raw, "url", "link", "href", "mobile_url"),
            mobile_url=_pick(raw, "mobile_url", "mobileUrl", "appUrl"),
            summary=_pick(raw, "summary", "desc", "description", "excerpt", "content"),
            metrics={k: v for k, v in metrics.items() if v not in ("", None)},
            rank=idx,
            published_at=_pick(raw, "published_at", "created_at", "date", "time"),
            confidence="medium",
        )
        items.append(enrich_hotnews_item(item.to_dict()))
    return items


def _extract_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("items", "list", "news", "content", "result", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return _extract_rows(data)

    return []


def compact_hotnews_items(items: list[dict[str, Any]], summary_chars: int = 120) -> list[dict[str, Any]]:
    """Return a smaller agent/API payload without dropping evidence boundaries."""
    compacted: list[dict[str, Any]] = []
    for raw in items:
        item = enrich_hotnews_item(raw)
        metrics = item.get("metrics") or {}
        card = item.get("source_card") or {}
        row: dict[str, Any] = {
            "rank": item.get("rank"),
            "source_id": item.get("source_id"),
            "title": item.get("title"),
            "url": item.get("url"),
            "evidence_role": item.get("evidence_role"),
            "risk_tags": item.get("risk_tags") or [],
        }
        if item.get("published_at"):
            row["published_at"] = item.get("published_at")
        if item.get("summary"):
            row["summary"] = _clean_text(item.get("summary"))[: max(summary_chars, 0)]
        if metrics:
            row["metrics"] = {
                key: metrics[key]
                for key in ("heat", "source_rank", "replies", "views", "label")
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


def format_hotnews_markdown(items: list[dict[str, Any]], title: str = "观澜热榜") -> str:
    """Render hotnews items as compact Markdown for agent context."""
    lines = [f"# {title}", ""]
    if not items:
        lines.append("暂无可展示条目。")
        return "\n".join(lines)

    for idx, item in enumerate(items, start=1):
        rank = item.get("rank") or idx
        item_title = _clean_text(item.get("title", ""))
        url = _clean_text(item.get("url", ""))
        source = _clean_text(item.get("source_id", "unknown"))
        summary = _clean_text(item.get("summary", ""))
        role = _clean_text(item.get("evidence_role", ""))
        metrics = item.get("metrics") or {}
        heat = metrics.get("heat") or metrics.get("replies") or ""

        line = f"{rank}. [{source}] {item_title}"
        if heat not in ("", None):
            line += f"（热度: {heat}）"
        if role:
            line += f" / {role}"
        if url:
            line += f"\n   {url}"
        if summary:
            line += f"\n   {summary[:180]}"
        lines.append(line)
    return "\n".join(lines)


def build_source_distribution(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize source mix so agents do not overread a narrow sample."""
    source_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    evidence_role_counts: dict[str, int] = {}
    source_type_counts: dict[str, int] = {}
    risk_tag_counts: dict[str, int] = {}
    for raw in items:
        item = enrich_hotnews_item(raw)
        source_id = _clean_text(item.get("source_id") or "unknown")
        category = _clean_text(item.get("category") or "hotnews")
        role = _clean_text(item.get("evidence_role") or "open_web_signal")
        card = item.get("source_card") or {}
        source_type = _clean_text(card.get("source_type") or "热榜/聚合源")
        source_counts[source_id] = source_counts.get(source_id, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
        evidence_role_counts[role] = evidence_role_counts.get(role, 0) + 1
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        for tag in item.get("risk_tags") or []:
            tag = _clean_text(tag)
            if tag:
                risk_tag_counts[tag] = risk_tag_counts.get(tag, 0) + 1
    return {
        "source_counts": dict(sorted(source_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "category_counts": dict(sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "evidence_role_counts": dict(sorted(evidence_role_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "source_type_counts": dict(sorted(source_type_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "risk_tag_counts": dict(sorted(risk_tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def build_sample_boundaries(items: list[dict[str, Any]], distribution: dict[str, Any] | None = None) -> list[str]:
    """Generate conservative caveats for a hotnews sample."""
    distribution = distribution or build_source_distribution(items)
    source_counts = distribution.get("source_counts") or {}
    evidence_counts = distribution.get("evidence_role_counts") or {}
    risk_counts = distribution.get("risk_tag_counts") or {}
    boundaries = [
        "热榜样本只能说明当前公开来源的可见水势，不等同于事实结论或总体比例。",
    ]
    if len(source_counts) <= 1 and len(items) >= 3:
        boundaries.append("当前样本来源单一，应作为单平台快照使用。")
    if evidence_counts and sum(evidence_counts.values()) > 0:
        social_count = sum(
            count for role, count in evidence_counts.items()
            if "discussion" in role or "attention" in role
        )
        if social_count >= max(3, len(items) // 2):
            boundaries.append("社交/社区信号占比较高，适合发现讨论线索，不适合作为权威事实来源。")
    if risk_counts.get("external_backend"):
        boundaries.append("部分条目来自可选外部后端，应保留后端波动和缓存边界。")
    if risk_counts.get("fast_changing"):
        boundaries.append("快变平台热度会迅速变化，引用时应保留抓取时间。")
    return _unique(boundaries)


def build_trend_report(items: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    """Merge cross-source hotnews rows into lightweight trend clusters."""
    clusters: list[dict[str, Any]] = []
    normalized_items = [enrich_hotnews_item(item) for item in items]
    for item in normalized_items:
        title = _clean_text(item.get("title", ""))
        if not title:
            continue
        signature = _trend_signature(title)
        matched = None
        for cluster in clusters:
            similarity = _signature_similarity(signature, set(cluster.get("_signature", [])))
            overlap = len(signature & set(cluster.get("_signature", [])))
            if (
                (similarity >= 0.32 and overlap >= 2)
                or overlap >= 3
                or title in str(cluster.get("title", ""))
                or str(cluster.get("title", "")) in title
            ):
                matched = cluster
                break
        if matched is None:
            matched = {
                "trend_id": f"trend-{len(clusters) + 1}",
                "title": title,
                "sources": [],
                "items": [],
                "_signature": sorted(signature),
            }
            clusters.append(matched)
        matched["items"].append(item)
        source_id = _clean_text(item.get("source_id", "unknown"))
        if source_id and source_id not in matched["sources"]:
            matched["sources"].append(source_id)

    for cluster in clusters:
        items_for_cluster = cluster.get("items", [])
        evidence_roles = _unique([_clean_text(item.get("evidence_role")) for item in items_for_cluster])
        source_types = _unique([
            _clean_text((item.get("source_card") or {}).get("source_type") or "")
            for item in items_for_cluster
        ])
        risk_tags = _unique([
            _clean_text(tag)
            for item in items_for_cluster
            for tag in (item.get("risk_tags") or [])
        ])
        cluster["source_count"] = len(cluster.get("sources", []))
        cluster["item_count"] = len(items_for_cluster)
        cluster["evidence_roles"] = evidence_roles
        cluster["source_types"] = source_types
        cluster["risk_tags"] = risk_tags
        cluster["heat_score"] = _cluster_heat_score(items_for_cluster)
        cluster["resonance"] = _trend_resonance(cluster)
        cluster["island_risk"] = _trend_island_risk(cluster)
        cluster["boundary"] = _trend_boundary(cluster)
        cluster["timeline"] = _trend_timeline(items_for_cluster)
        cluster["research_commands"] = [f'guanlan research "{query}" --profile china --advisor' for query in _trend_research_queries(str(cluster.get("title", "")), list(cluster.get("sources") or []))[:2]]
        cluster.pop("_signature", None)
    clusters.sort(key=lambda row: (-int(row.get("source_count", 0)), -float(row.get("heat_score", 0)), str(row.get("title", ""))))
    distribution = build_source_distribution(normalized_items)
    return {
        "trend_count": len(clusters),
        "sample_count": len(normalized_items),
        "source_distribution": distribution,
        "sample_boundaries": build_sample_boundaries(normalized_items, distribution),
        "trends": clusters[: max(limit, 1)],
    }


def format_trend_report_markdown(report: dict[str, Any], title: str = "观澜趋势归并") -> str:
    """Render cross-source trend clusters as Markdown."""
    lines = [f"# {title}", "", f"- 样本数: {report.get('sample_count', 0)}", f"- 趋势数: {report.get('trend_count', 0)}"]
    distribution = report.get("source_distribution") or {}
    source_counts = distribution.get("source_counts") or {}
    role_counts = distribution.get("evidence_role_counts") or {}
    if source_counts:
        lines.append("- 来源分布: " + "；".join(f"{key}: {value}" for key, value in source_counts.items()))
    if role_counts:
        lines.append("- 证据角色: " + "；".join(f"{key}: {value}" for key, value in role_counts.items()))
    boundaries = report.get("sample_boundaries") or []
    if boundaries:
        lines.extend(["", "## 样本边界"])
        lines.extend(f"- {item}" for item in boundaries)
    trends = report.get("trends") or []
    if not trends:
        lines.append("- 暂无可归并趋势。")
        return "\n".join(lines)
    lines.extend(["", "## 趋势"])
    for idx, trend in enumerate(trends, start=1):
        sources = ", ".join(trend.get("sources") or [])
        lines.append(f"{idx}. {trend.get('title', '')}")
        lines.append(
            f"   来源: {sources or 'unknown'} | 条目: {trend.get('item_count', 0)} | "
            f"热度: {trend.get('heat_score', 0)} | 共振: {trend.get('resonance', 'single-source')}"
        )
        if trend.get("evidence_roles"):
            lines.append("   证据角色: " + ", ".join(trend.get("evidence_roles") or []))
        if trend.get("island_risk"):
            lines.append("   边界: 主要是单平台水花，不应直接写成全网趋势。")
        elif trend.get("boundary"):
            lines.append(f"   边界: {trend.get('boundary')}")
        timeline = trend.get("timeline") or []
        if timeline:
            lines.append("   时间线: " + "；".join(f"{item.get('time')} {item.get('source')}" for item in timeline[:3]))
        for item in (trend.get("items") or [])[:3]:
            source = _clean_text(item.get("source_id", "unknown"))
            url = _clean_text(item.get("url", ""))
            item_title = _clean_text(item.get("title", ""))
            lines.append(f"   - [{source}] {item_title}" + (f" {url}" if url else ""))
        for command in trend.get("research_commands") or []:
            lines.append(f"   继续查: `{command}`")
    return "\n".join(lines)


def build_hotnews_brief(items: list[dict[str, Any]], trend_report: dict[str, Any] | None = None, limit: int = 8) -> dict[str, Any]:
    """Build a lightweight daily brief from hotnews items and trend clusters."""
    trend_report = trend_report or build_trend_report(items, limit=limit)
    distribution = trend_report.get("source_distribution") or build_source_distribution(items)
    platform_counts = dict(distribution.get("source_counts") or {})
    category_counts = dict(distribution.get("category_counts") or {})

    highlights = []
    for trend in (trend_report.get("trends") or [])[: max(limit, 1)]:
        title = _clean_text(trend.get("title"))
        sources = list(trend.get("sources") or [])
        highlights.append(
            {
                "title": title,
                "sources": sources,
                "source_count": int(trend.get("source_count") or 0),
                "item_count": int(trend.get("item_count") or 0),
                "heat_score": trend.get("heat_score", 0),
                "resonance": trend.get("resonance", "single-source"),
                "island_risk": bool(trend.get("island_risk")),
                "evidence_roles": list(trend.get("evidence_roles") or []),
                "source_types": list(trend.get("source_types") or []),
                "boundary": trend.get("boundary", ""),
                "timeline": list(trend.get("timeline") or []),
                "research_queries": _trend_research_queries(title, sources),
            }
        )

    warnings: list[str] = []
    if len(platform_counts) <= 1 and len(items) >= 5:
        warnings.append("当前热榜来源较单一，不能代表整个中文互联网水势。")
    if trend_report.get("trend_count", 0) >= max(len(items) - 2, 1):
        warnings.append("跨源重合度较低，今天更像多主题分散水面；不要强行归并。")

    return {
        "sample_count": len(items),
        "platform_counts": platform_counts,
        "category_counts": category_counts,
        "source_distribution": distribution,
        "sample_boundaries": list(trend_report.get("sample_boundaries") or build_sample_boundaries(items, distribution)),
        "trend_count": int(trend_report.get("trend_count") or 0),
        "highlights": highlights,
        "warnings": warnings,
    }


def format_hotnews_brief_markdown(brief: dict[str, Any], title: str = "观澜今日水势简报") -> str:
    """Render a hotnews brief as compact Markdown."""
    lines = [f"# {title}", ""]
    lines.append(f"- 样本数: {brief.get('sample_count', 0)}")
    lines.append(f"- 趋势数: {brief.get('trend_count', 0)}")
    platform_counts = brief.get("platform_counts") or {}
    if platform_counts:
        lines.append("- 来源分布: " + "；".join(f"{key}: {value}" for key, value in platform_counts.items()))
    role_counts = (brief.get("source_distribution") or {}).get("evidence_role_counts") or {}
    if role_counts:
        lines.append("- 证据角色: " + "；".join(f"{key}: {value}" for key, value in role_counts.items()))
    sample_boundaries = brief.get("sample_boundaries") or []
    if sample_boundaries:
        lines.extend(["", "## 样本边界"])
        lines.extend(f"- {item}" for item in sample_boundaries)
    warnings = brief.get("warnings") or []
    if warnings:
        lines.extend(["", "## 边界提醒"])
        lines.extend(f"- {warning}" for warning in warnings)
    highlights = brief.get("highlights") or []
    if highlights:
        lines.extend(["", "## 值得追踪"])
        for idx, item in enumerate(highlights, start=1):
            sources = ", ".join(item.get("sources") or [])
            lines.append(f"{idx}. {item.get('title', '')}")
            lines.append(
                f"   来源: {sources or 'unknown'} | 条目: {item.get('item_count', 0)} | "
                f"热度: {item.get('heat_score', 0)} | 共振: {item.get('resonance', 'single-source')}"
            )
            if item.get("evidence_roles"):
                lines.append("   证据角色: " + ", ".join(item.get("evidence_roles") or []))
            if item.get("island_risk"):
                lines.append("   边界: 单平台信号，适合追踪，不宜直接定调。")
            elif item.get("boundary"):
                lines.append(f"   边界: {item.get('boundary')}")
            queries = item.get("research_queries") or []
            if queries:
                lines.append("   继续查: " + "；".join(queries[:2]))
    return "\n".join(lines)


def _trend_resonance(cluster: dict[str, Any]) -> str:
    sources = set(cluster.get("sources") or [])
    if len(sources) >= 3:
        return "cross-platform"
    if len(sources) == 2:
        return "two-source"
    return "single-source"


def _trend_island_risk(cluster: dict[str, Any]) -> bool:
    return len(set(cluster.get("sources") or [])) <= 1 and int(cluster.get("item_count") or 0) <= 2


def _trend_boundary(cluster: dict[str, Any]) -> str:
    sources = set(cluster.get("sources") or [])
    roles = set(cluster.get("evidence_roles") or [])
    risk_tags = set(cluster.get("risk_tags") or [])
    if len(sources) <= 1:
        return "单来源信号，适合发现线索，不宜直接外推为全网趋势。"
    if any("discussion" in role or "attention" in role for role in roles):
        return "讨论/注意力信号占比高，需要用新闻、官方或一手资料交叉确认。"
    if "external_backend" in risk_tags:
        return "含可选外部后端信号，需保留抓取时间和后端波动边界。"
    if "sample_boundary" in risk_tags:
        return "聚合样本有来源边界，应结合更多检索再下结论。"
    return ""


def _trend_timeline(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        when = _clean_text(item.get("published_at") or item.get("fetched_at") or "")
        if not when:
            continue
        rows.append(
            {
                "time": when[:16],
                "source": _clean_text(item.get("source_id") or item.get("platform") or "unknown"),
                "title": _clean_text(item.get("title") or "")[:80],
            }
        )
    return sorted(rows, key=lambda row: row["time"])[:5]


def _trend_research_queries(title: str, sources: list[str]) -> list[str]:
    title = _clean_text(title)
    if not title:
        return []
    queries = [f"{title} 原因 进展", f"{title} 官方回应"]
    if any(source in {"weibo", "bilibili", "v2ex"} for source in sources):
        queries.append(f"{title} 网友讨论")
    if any(source in {"baidu", "ithome"} for source in sources):
        queries.append(f"{title} 最新报道")
    return queries[:3]


def _annotate_trends(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    report = build_trend_report(items, limit=len(items) or 1)
    trend_map: dict[str, str] = {}
    for trend in report.get("trends", []):
        for item in trend.get("items", []):
            trend_map[_snapshot_item(item)["key"]] = str(trend.get("trend_id", ""))
    output = []
    for item in items:
        row = enrich_hotnews_item(item)
        key = _snapshot_item(row)["key"]
        if trend_map.get(key):
            row["trend_id"] = trend_map[key]
        output.append(row)
    return output


def _trend_signature(title: str) -> set[str]:
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", title.lower())
    tokens = {token for token in text.split() if len(token) >= 2}
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.update("".join(cjk[idx:idx + 2]) for idx in range(max(len(cjk) - 1, 0)))
    stopwords = {"一个", "如何", "为何", "什么", "最新", "今天", "回应", "官方", "到了", "了一", "一份"}
    return {token for token in tokens if token and token not in stopwords}


def _signature_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _cluster_heat_score(items: list[dict[str, Any]]) -> float:
    score = 0.0
    for item in items:
        rank = int(item.get("rank") or 99)
        score += max(1, 101 - rank)
        metrics = item.get("metrics") or {}
        heat = metrics.get("heat") or metrics.get("views") or metrics.get("replies")
        if isinstance(heat, (int, float)):
            score += min(float(heat) / 10000, 50)
    return round(score, 2)


def hotnews_snapshot_path(path: str | None = None) -> Path:
    """Return the local hotnews snapshot history path."""
    if path:
        return Path(path).expanduser()
    env_path = os.environ.get("GUANLAN_HOTNEWS_SNAPSHOT_FILE", "")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".guanlan" / "hotnews_snapshots.jsonl"


def save_hotnews_snapshot(
    source: str,
    items: list[dict[str, Any]],
    *,
    path: str | None = None,
) -> dict[str, Any]:
    """Append one explicit source snapshot to local history."""
    snapshot = {
        "snapshot_id": _now_iso(),
        "source": (source or "today").strip() or "today",
        "fetched_at": _now_iso(),
        "item_count": len(items),
        "items": [enrich_hotnews_item(item) for item in items],
    }
    target = hotnews_snapshot_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
    return {"path": str(target), **snapshot}


def load_latest_hotnews_snapshot(
    source: str | None = None,
    *,
    path: str | None = None,
) -> dict[str, Any] | None:
    """Load the latest saved snapshot, optionally scoped by source."""
    target = hotnews_snapshot_path(path)
    if not target.exists():
        return None
    wanted = (source or "").strip().lower()
    latest: dict[str, Any] | None = None
    with target.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                snapshot = json.loads(line)
            except json.JSONDecodeError:
                continue
            if wanted and str(snapshot.get("source") or "").lower() != wanted:
                continue
            latest = snapshot
    return latest


def compare_hotnews_snapshots(
    previous_items: list[dict[str, Any]],
    current_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare two explicit snapshots without implying background monitoring."""
    previous = [_snapshot_item(item) for item in previous_items]
    current = [_snapshot_item(item) for item in current_items]
    prev_map = {item["key"]: item for item in previous if item["key"]}
    curr_map = {item["key"]: item for item in current if item["key"]}
    new_keys = [key for key in curr_map if key not in prev_map]
    gone_keys = [key for key in prev_map if key not in curr_map]
    continuing_keys = [key for key in curr_map if key in prev_map]
    rank_changes = []
    for key in continuing_keys:
        before = prev_map[key]
        after = curr_map[key]
        delta = int(before.get("rank") or 0) - int(after.get("rank") or 0)
        if delta:
            rank_changes.append(
                {
                    "title": after["title"],
                    "source_id": after["source_id"],
                    "previous_rank": before.get("rank"),
                    "current_rank": after.get("rank"),
                    "rank_delta": delta,
                    "direction": "up" if delta > 0 else "down",
                    "url": after.get("url", ""),
                }
            )
    rank_changes.sort(key=lambda row: (-abs(int(row.get("rank_delta") or 0)), str(row.get("title") or "")))
    return {
        "previous_count": len(previous),
        "current_count": len(current),
        "new_items": [curr_map[key] for key in new_keys],
        "continuing_items": [curr_map[key] for key in continuing_keys],
        "disappeared_items": [prev_map[key] for key in gone_keys],
        "rank_changes": rank_changes,
        "boundary": "对比只基于本机显式保存的两次快照；没有后台轮询，也不代表完整历史。",
    }


def build_hotnews_snapshot_report(
    source: str,
    items: list[dict[str, Any]],
    *,
    save: bool = False,
    path: str | None = None,
) -> dict[str, Any]:
    """Build a source snapshot report and optionally persist it."""
    previous = load_latest_hotnews_snapshot(source, path=path)
    current_items = [enrich_hotnews_item(item) for item in items]
    comparison = compare_hotnews_snapshots(previous.get("items", []) if previous else [], current_items)
    saved = save_hotnews_snapshot(source, current_items, path=path) if save else None
    return {
        "source": source,
        "fetched_at": _now_iso(),
        "items": current_items,
        "source_distribution": build_source_distribution(current_items),
        "sample_boundaries": build_sample_boundaries(current_items),
        "previous_snapshot": {
            "snapshot_id": previous.get("snapshot_id"),
            "fetched_at": previous.get("fetched_at"),
            "item_count": previous.get("item_count"),
        } if previous else None,
        "comparison": comparison,
        "saved_snapshot": {
            "snapshot_id": saved.get("snapshot_id"),
            "path": saved.get("path"),
        } if saved else None,
    }


def format_snapshot_report_markdown(report: dict[str, Any], title: str = "观澜信源快照") -> str:
    """Render a source snapshot comparison for agent context."""
    lines = [f"# {title}", "", f"- source: {report.get('source', '')}"]
    previous = report.get("previous_snapshot")
    if previous:
        lines.append(f"- 对比基准: {previous.get('fetched_at')} / {previous.get('item_count')} 条")
    else:
        lines.append("- 对比基准: 暂无本地历史")
    saved = report.get("saved_snapshot")
    if saved:
        lines.append(f"- 已保存: {saved.get('path')}")
    comparison = report.get("comparison") or {}
    lines.append(f"- 当前条目: {comparison.get('current_count', 0)}")
    lines.append(f"- 新上榜: {len(comparison.get('new_items') or [])}")
    lines.append(f"- 持续在榜: {len(comparison.get('continuing_items') or [])}")
    lines.append(f"- 消失项: {len(comparison.get('disappeared_items') or [])}")
    if comparison.get("boundary"):
        lines.extend(["", "## 边界", f"- {comparison.get('boundary')}"])
    if comparison.get("new_items"):
        lines.extend(["", "## 新上榜"])
        for item in (comparison.get("new_items") or [])[:10]:
            lines.append(f"- [{item.get('source_id')}] {item.get('title')}" + (f" {item.get('url')}" if item.get("url") else ""))
    if comparison.get("rank_changes"):
        lines.extend(["", "## 排名变化"])
        for item in (comparison.get("rank_changes") or [])[:10]:
            direction = "上升" if item.get("direction") == "up" else "下降"
            lines.append(
                f"- {direction} {abs(int(item.get('rank_delta') or 0))}: "
                f"[{item.get('source_id')}] {item.get('title')} "
                f"{item.get('previous_rank')} -> {item.get('current_rank')}"
            )
    return "\n".join(lines)


def _snapshot_item(item: dict[str, Any]) -> dict[str, Any]:
    row = enrich_hotnews_item(item)
    title = _clean_text(row.get("title"))
    url = _clean_text(row.get("url"))
    source_id = _clean_text(row.get("source_id") or "unknown")
    key_basis = url or title
    return {
        "key": f"{source_id}:{_snapshot_key(key_basis)}",
        "title": title,
        "url": url,
        "source_id": source_id,
        "rank": int(row.get("rank") or 0),
        "evidence_role": row.get("evidence_role", ""),
    }


def _snapshot_key(value: str) -> str:
    text = re.sub(r"\s+", "", (value or "").lower())
    text = re.sub(r"[?&](utm_[^=&]+|spm|from|share)[^&]*", "", text)
    return text[:220]
