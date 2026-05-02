# -*- coding: utf-8 -*-
"""Native hotnews sources and formatters for Guanlan.

The first native sources intentionally use public, read-only endpoints. They do
not require cookies, browser access, or Keychain integration.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

from guanlan.limits import DEFAULT_HOTNEWS_LIMIT, MAX_HOTNEWS_PER_SOURCE_LIMIT

_UA = "Mozilla/5.0"
_TIMEOUT = 12
DEFAULT_NEWSNOW_BASE_URL = "https://newsnow.busiyi.world"


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SOURCE_CATALOG: dict[str, dict[str, Any]] = {
    "today": {
        "name": "今日多源热榜",
        "platform": "guanlan",
        "category": "hotnews",
        "risk": "low",
        "backend": "native",
        "status": "stable",
        "notes": "聚合 baidu、weibo、bilibili、ithome、v2ex；单源失败不影响其它来源。",
    },
    "baidu": {
        "name": "百度热搜",
        "platform": "baidu",
        "category": "hotnews",
        "risk": "low",
        "backend": "native",
        "status": "stable",
    },
    "weibo": {
        "name": "微博热搜",
        "platform": "weibo",
        "category": "social",
        "risk": "low",
        "backend": "native",
        "status": "best-effort",
        "notes": "公开只读热搜端点；不读取 Cookie 或登录态，但可能受反爬和地区网络影响。",
    },
    "bilibili": {
        "name": "B站热门视频",
        "platform": "bilibili",
        "category": "video",
        "risk": "low",
        "backend": "native",
        "status": "best-effort",
        "notes": "公开全站热门视频榜，不等同于 B站搜索框热搜；接口偶尔会限流或返回风控码。",
    },
    "ithome": {
        "name": "IT之家资讯",
        "platform": "ithome",
        "category": "tech",
        "risk": "low",
        "backend": "native",
        "status": "stable",
        "notes": "公开 RSS 源，适合作为科技资讯快照。",
    },
    "zhihu": {
        "name": "知乎热榜",
        "platform": "zhihu",
        "category": "hotnews",
        "risk": "low",
        "backend": "native",
        "status": "experimental",
        "verified": False,
        "notes": "实验源：公开接口在部分环境会返回 401/403，不承诺稳定可用。",
        "fallback": 'guanlan search "知乎 热榜 关键词" --site zhihu.com --profile china',
    },
    "v2ex": {
        "name": "V2EX 热门",
        "platform": "v2ex",
        "category": "community",
        "risk": "low",
        "backend": "native",
        "status": "stable",
    },
}


NEWSNOW_RECOMMENDED_SOURCES: dict[str, dict[str, Any]] = {
    "weibo": {"name": "微博热搜", "column": "china", "type": "hottest"},
    "bilibili-hot-search": {"name": "B站热搜", "column": "china", "type": "hottest"},
    "36kr-quick": {"name": "36氪快讯", "column": "tech", "type": "realtime"},
    "ithome": {"name": "IT之家", "column": "tech", "type": "realtime"},
    "juejin": {"name": "掘金热榜", "column": "tech", "type": "hottest"},
    "sspai": {"name": "少数派热榜", "column": "tech", "type": "hottest"},
    "cls-telegraph": {"name": "财联社电报", "column": "finance", "type": "realtime"},
    "wallstreetcn-quick": {"name": "华尔街见闻快讯", "column": "finance", "type": "realtime"},
    "github-trending-today": {"name": "GitHub Trending", "column": "tech", "type": "hottest"},
    "hackernews": {"name": "Hacker News", "column": "tech", "type": "hottest"},
}


def list_sources() -> dict[str, dict[str, Any]]:
    """Return supported native hotnews source metadata."""
    sources = SOURCE_CATALOG.copy()
    for source_id, meta in NEWSNOW_RECOMMENDED_SOURCES.items():
        sources[f"newsnow:{source_id}"] = {
            "name": meta["name"],
            "platform": source_id,
            "category": meta.get("column", "hotnews"),
            "risk": "low",
            "backend": "newsnow",
            "status": "best-effort",
            "verified": False,
            "notes": "可选增强源：稳定性取决于 NewsNow BASE_URL、Cloudflare 和上游抓取状态。",
        }
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
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def _strip_html(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _pick(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return ""


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
        ("bilibili", fetch_bilibili),
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


def fetch_hotnews(
    source: str = "today",
    limit: int = DEFAULT_HOTNEWS_LIMIT,
    backend: str = "auto",
    newsnow_base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch hotnews and return unified dictionaries."""
    source = source.lower().strip()
    backend = (backend or "auto").lower().strip()
    fetchers = {
        "today": fetch_today,
        "baidu": fetch_baidu,
        "weibo": fetch_weibo,
        "bilibili": fetch_bilibili,
        "ithome": fetch_ithome,
        "zhihu": fetch_zhihu,
        "v2ex": fetch_v2ex,
    }
    if source.startswith("newsnow:"):
        return fetch_newsnow(source.split(":", 1)[1], limit=limit, base_url=newsnow_base_url)
    if backend == "newsnow":
        return fetch_newsnow(source, limit=limit, base_url=newsnow_base_url)
    if backend not in {"auto", "native"}:
        raise ValueError("backend must be one of: auto, native, newsnow")
    if source not in fetchers:
        if backend == "auto":
            return fetch_newsnow(source, limit=limit, base_url=newsnow_base_url)
        available = ", ".join(sorted(fetchers) + [f"newsnow:{name}" for name in sorted(NEWSNOW_RECOMMENDED_SOURCES)])
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
            items.append(item)
            continue

        title = _pick(raw, "title", "name", "word", "query", "keyword")
        if not title:
            continue
        metrics = {
            "heat": _pick(raw, "hot", "heat", "hotScore", "hot_score", "index", "views"),
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
        items.append(item.to_dict())
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
        metrics = item.get("metrics") or {}
        heat = metrics.get("heat") or metrics.get("replies") or ""

        line = f"{rank}. [{source}] {item_title}"
        if heat not in ("", None):
            line += f"（热度: {heat}）"
        if url:
            line += f"\n   {url}"
        if summary:
            line += f"\n   {summary[:180]}"
        lines.append(line)
    return "\n".join(lines)


def build_trend_report(items: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    """Merge cross-source hotnews rows into lightweight trend clusters."""
    clusters: list[dict[str, Any]] = []
    for item in items:
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
        cluster["source_count"] = len(cluster.get("sources", []))
        cluster["item_count"] = len(items_for_cluster)
        cluster["heat_score"] = _cluster_heat_score(items_for_cluster)
        cluster.pop("_signature", None)
    clusters.sort(key=lambda row: (-int(row.get("source_count", 0)), -float(row.get("heat_score", 0)), str(row.get("title", ""))))
    return {
        "trend_count": len(clusters),
        "sample_count": len(items),
        "trends": clusters[: max(limit, 1)],
    }


def format_trend_report_markdown(report: dict[str, Any], title: str = "观澜趋势归并") -> str:
    """Render cross-source trend clusters as Markdown."""
    lines = [f"# {title}", "", f"- 样本数: {report.get('sample_count', 0)}", f"- 趋势数: {report.get('trend_count', 0)}"]
    trends = report.get("trends") or []
    if not trends:
        lines.append("- 暂无可归并趋势。")
        return "\n".join(lines)
    lines.extend(["", "## 趋势"])
    for idx, trend in enumerate(trends, start=1):
        sources = ", ".join(trend.get("sources") or [])
        lines.append(f"{idx}. {trend.get('title', '')}")
        lines.append(f"   来源: {sources or 'unknown'} | 条目: {trend.get('item_count', 0)} | 热度: {trend.get('heat_score', 0)}")
        for item in (trend.get("items") or [])[:3]:
            source = _clean_text(item.get("source_id", "unknown"))
            url = _clean_text(item.get("url", ""))
            item_title = _clean_text(item.get("title", ""))
            lines.append(f"   - [{source}] {item_title}" + (f" {url}" if url else ""))
    return "\n".join(lines)


def _annotate_trends(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    report = build_trend_report(items, limit=len(items) or 1)
    trend_map: dict[int, str] = {}
    for trend in report.get("trends", []):
        for item in trend.get("items", []):
            trend_map[id(item)] = str(trend.get("trend_id", ""))
    output = []
    for item in items:
        row = dict(item)
        if trend_map.get(id(item)):
            row["trend_id"] = trend_map[id(item)]
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
