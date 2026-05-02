# -*- coding: utf-8 -*-
"""Search and read primitives for AI agents.

These helpers are deliberately conservative: default search uses public HTML
results and page reading uses Jina Reader. No cookies, browser access, or
Keychain access are involved.
"""

from __future__ import annotations

import base64
import datetime as dt
import difflib
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from guanlan.limits import (
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
)

_UA = "Mozilla/5.0 (compatible; Guanlan/1.4)"
_TIMEOUT = 20
_CACHE_VERSION = 2
_MIN_USEFUL_READ_CHARS = 180
_RECENCY_DEFAULT_WINDOW_DAYS = 30
_WEAK_READ_MARKERS = (
    "captcha",
    "access denied",
    "forbidden",
    "verify you are human",
    "enable javascript",
    "请完成安全验证",
    "访问受限",
    "验证码",
    "登录后查看",
    "请先登录",
)

_QUALITY_INTENT_PROFILES: dict[str, dict[str, Any]] = {
    "policy": {
        "name": "政策/官方口径",
        "terms": ("政策", "监管", "法规", "通知", "意见", "办法", "国务院", "部委", "主管部门", "官方", "解读"),
        "preferred_scopes": ("gov", "party_central"),
        "preferred_source_types": ("政府/部委", "党央媒"),
        "caution_source_types": ("社交/内容平台",),
        "guidance": "优先政府/部委原文和党央媒权威报道，媒体解读只能作为背景。",
    },
    "local": {
        "name": "地方政策/区域研究",
        "terms": ("地方", "城市", "区域", "省", "市", "区县", "产业园", "广东", "上海", "北京", "深圳", "杭州", "成都"),
        "preferred_scopes": ("local_official", "gov", "party_central"),
        "preferred_source_types": ("地方官媒", "政府/部委", "党央媒"),
        "caution_source_types": (),
        "guidance": "优先地方官媒、地方政府和中央口径交叉核验。",
    },
    "ecommerce": {
        "name": "电商/零售/跨境",
        "terms": ("电商", "零售", "跨境", "出海", "品牌", "渠道", "供应链", "产业带", "平台", "新消费"),
        "preferred_scopes": ("ecommerce", "business"),
        "preferred_source_types": ("电商/零售垂类", "商业/产业媒体"),
        "caution_source_types": (),
        "guidance": "优先垂类媒体和产业媒体，注意区分新闻、观点和软文。",
    },
    "finance": {
        "name": "财经/资本市场",
        "terms": ("财经", "股票", "股价", "财报", "融资", "上市", "投资", "基金", "债券", "宏观", "资本市场"),
        "preferred_scopes": ("finance", "business"),
        "preferred_source_types": ("财经/资本市场", "商业/产业媒体"),
        "caution_source_types": ("社交/内容平台",),
        "guidance": "优先公告、财报、财经快讯和权威财经媒体，市场观点不等于建议。",
    },
    "tech": {
        "name": "技术/开发者",
        "terms": ("技术", "开源", "框架", "模型", "api", "sdk", "github", "开发者", "部署", "bug", "benchmark"),
        "preferred_scopes": ("tech_dev",),
        "preferred_source_types": ("科技/开发者社区",),
        "caution_source_types": (),
        "guidance": "优先官方文档、代码仓库、开发者社区和可复现反馈。",
    },
    "reputation": {
        "name": "口碑/公开讨论",
        "terms": ("口碑", "评价", "体验", "吐槽", "避雷", "测评", "推荐", "小红书", "微博", "知乎", "b站", "bilibili"),
        "preferred_scopes": ("social_web", "tech_dev", "business"),
        "preferred_source_types": ("社交/内容平台", "科技/开发者社区", "商业/产业媒体"),
        "caution_source_types": (),
        "guidance": "社交结果适合发现样本线索，不能直接代表总体比例。",
    },
}


RESEARCH_PRESETS: dict[str, dict[str, Any]] = {
    "general": {
        "name": "通用研究",
        "description": "适合一般资料检索与多来源核验。",
        "profile": "china",
        "scope": "",
        "scopes": [],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 2,
        "max_read_chars": 2400,
        "guidance": ["先看不同 topic 和 source_type，再组织结论。"],
    },
    "policy": {
        "name": "政策研究",
        "description": "优先政府/部委信源，适合政策原文、通知、法规和监管口径。",
        "profile": "china",
        "scope": "gov",
        "scopes": ["gov", "party_central"],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 3200,
        "guidance": ["优先引用政策原文、主管部门通知和官方公告，不要用媒体解读替代原文。"],
    },
    "official": {
        "name": "官方表述",
        "description": "优先党央媒与中央重点媒体，适合宏观叙事和权威报道。",
        "profile": "china",
        "scope": "party_central",
        "scopes": ["party_central", "gov"],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 3000,
        "guidance": ["区分官方原文、权威报道和二次解读，保留措辞差异。"],
    },
    "industry": {
        "name": "产业研究",
        "description": "优先商业与产业媒体，适合公司动态、商业模式和行业趋势。",
        "profile": "china",
        "scope": "business",
        "scopes": ["business", "ecommerce", "finance"],
        "sites": ["36kr.com", "huxiu.com", "yicai.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": ["注意区分新闻事实、商业观点和软文营销。"],
    },
    "ecommerce": {
        "name": "电商零售",
        "description": "优先电商/零售垂类媒体，适合跨境、品牌、渠道和产业带研究。",
        "profile": "china",
        "scope": "ecommerce",
        "scopes": ["ecommerce", "business"],
        "sites": ["ebrun.com", "100ec.cn", "cifnews.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": ["优先关注平台、品牌、渠道、供应链和交易场景。"],
    },
    "reputation": {
        "name": "产品口碑",
        "description": "优先社交与内容平台公开页，适合用户评价、讨论和体验线索。",
        "profile": "china",
        "scope": "social_web",
        "scopes": ["social_web", "tech_dev", "business"],
        "sites": ["zhihu.com", "weibo.com", "xiaohongshu.com", "bilibili.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 2,
        "max_read_chars": 2400,
        "guidance": ["口碑材料偏样本线索，不要直接当作总体结论。"],
    },
    "tech": {
        "name": "技术选型",
        "description": "优先科技与开发者社区，适合工程实践、技术反馈和开发者讨论。",
        "profile": "china",
        "scope": "tech_dev",
        "scopes": ["tech_dev", "social_web"],
        "sites": ["v2ex.com", "juejin.cn", "segmentfault.com", "github.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": ["优先提取版本、限制、真实使用反馈和可复现依据。"],
    },
    "finance": {
        "name": "财经研究",
        "description": "优先财经与资本市场信源，适合公司、股票、市场和宏观金融。",
        "profile": "china",
        "scope": "finance",
        "scopes": ["finance", "business"],
        "sites": ["cls.cn", "eastmoney.com", "xueqiu.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": ["财经内容注意时效性和风险，不把市场观点当作投资建议。"],
    },
    "local": {
        "name": "地方研究",
        "description": "优先核心地方官媒，适合区域政策、城市治理和地方产业。",
        "profile": "china",
        "scope": "local_official",
        "scopes": ["local_official", "gov", "party_central"],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": ["注意地方口径、区域边界和政策适用范围。"],
    },
}


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source: str = "duckduckgo"
    rank: int = 0
    domain: str = ""
    source_type: str = "通用网页"
    matched_scope: str = ""
    trust_level: int = 1
    score: float = 0.0
    score_parts: dict[str, float] = field(default_factory=dict)
    topic_key: str = ""
    topic_size: int = 1
    topic_role: str = "single"
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _DuckDuckGoHTMLParser(HTMLParser):
    """Small parser for DuckDuckGo's no-JS HTML results."""

    def __init__(self):
        super().__init__()
        self.results: list[SearchResult] = []
        self._in_title = False
        self._in_snippet = False
        self._current_href = ""
        self._current_title: list[str] = []
        self._last_result: SearchResult | None = None
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attrs_dict = {k: v or "" for k, v in attrs}
        classes = set(attrs_dict.get("class", "").split())
        if tag == "a" and "result__a" in classes:
            self._in_title = True
            self._current_href = attrs_dict.get("href", "")
            self._current_title = []
        elif tag in {"a", "td"} and "result-link" in classes:
            self._in_title = True
            self._current_href = attrs_dict.get("href", "")
            self._current_title = []
        elif "result__snippet" in classes:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag: str):
        if tag == "a" and self._in_title:
            title = _collapse_ws("".join(self._current_title))
            url = _normalize_ddg_url(self._current_href)
            if title and url and not _is_duckduckgo_noise(url):
                result = SearchResult(
                    title=title,
                    url=url,
                    rank=len(self.results) + 1,
                )
                self.results.append(result)
                self._last_result = result
            self._in_title = False
            self._current_href = ""
            self._current_title = []
        elif self._in_snippet and tag in {"a", "td", "div"}:
            snippet = _collapse_ws("".join(self._snippet_parts))
            if self._last_result and snippet and not self._last_result.snippet:
                self._last_result.snippet = snippet
            self._in_snippet = False
            self._snippet_parts = []

    def handle_data(self, data: str):
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._snippet_parts.append(data)


_WECHAT_SOGOU_BACKENDS = {"wechat-sogou", "wechat_sogou", "sogou-wechat", "sogou_wechat"}


def backend_order(
    backend: str = "auto",
    profile: str | None = None,
    site: str | None = None,
    query: str | None = None,
) -> list[str]:
    """Return search backend order for a profile."""
    backend = (backend or "auto").lower()
    if backend in _WECHAT_SOGOU_BACKENDS:
        return ["wechat-sogou"]
    if backend != "auto":
        return [backend]
    if profile == "china":
        order = ["baidu", "bing", "duckduckgo"]
    else:
        order = ["duckduckgo", "bing"]
    if _is_wechat_search_intent(site=site, query=query):
        order.append("wechat-sogou")
    return order


def cache_dir() -> Path:
    """Return the Guanlan cache directory."""
    return Path.home() / ".guanlan" / "cache"


def _cache_key(kind: str, payload: dict[str, Any]) -> str:
    raw = json.dumps({"kind": kind, "v": _CACHE_VERSION, **payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(kind: str, key: str) -> Path:
    return cache_dir() / kind / f"{key}.json"


def _cache_get(kind: str, key: str, ttl: int) -> dict[str, Any] | None:
    path = _cache_path(kind, key)
    if ttl <= 0 or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    created_at = float(data.get("created_at", 0) or 0)
    if time.time() - created_at > ttl:
        return None
    payload = data.get("payload")
    return payload if isinstance(payload, dict) else None


def _cache_set(kind: str, key: str, payload: dict[str, Any]) -> None:
    path = _cache_path(kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": _CACHE_VERSION, "created_at": time.time(), "kind": kind, "payload": payload}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cache_summary() -> dict[str, Any]:
    """Return lightweight local cache stats for status output."""
    root = cache_dir()
    summary: dict[str, Any] = {"path": str(root), "exists": root.exists(), "kinds": {}, "total_files": 0}
    if not root.exists():
        return summary
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        files = list(child.glob("*.json"))
        summary["kinds"][child.name] = len(files)
        summary["total_files"] += len(files)
    return summary


def search_web(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    site: str | None = None,
    scope: str | None = None,
    backend: str = "auto",
    profile: str | None = None,
    trace: bool = False,
    cluster_threshold: str = "conservative",
    cache_ttl: int = 0,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Search the web and return normalized result dictionaries."""
    original_query = query.strip()
    query = original_query
    if not original_query:
        raise ValueError("query is required")
    recency = detect_recency_intent(original_query)
    quality = detect_search_quality_profile(original_query, scope=scope, site=site, profile=profile)
    if scope:
        from guanlan.search_sources import resolve_scope, scoped_query

        domains = list(resolve_scope(scope).domains)
        if site:
            domains.insert(0, site.strip())
        query = scoped_query(query, domains)
    elif site:
        query = f"site:{site.strip()} {query}"
    query = _apply_recency_query(query, recency)

    cache_meta = {
        "enabled": bool(cache_ttl and cache_ttl > 0 and use_cache),
        "status": "disabled",
        "ttl": max(cache_ttl, 0),
    }
    cache_key = ""
    if cache_meta["enabled"]:
        cache_key = _cache_key(
            "search",
            {
                "query": original_query,
                "effective_query": query,
                "limit": max(limit, 1),
                "site": site or "",
                "scope": scope or "",
                "backend": backend,
                "profile": profile or "",
                "cluster_threshold": cluster_threshold,
                "recency": {
                    "enabled": recency["enabled"],
                    "window_days": recency["window_days"],
                    "start_date": recency["start_date"],
                    "end_date": recency["end_date"],
                },
                "quality_intent": quality["intent"],
            },
        )
        cached = _cache_get("search", cache_key, ttl=cache_ttl)
        if cached is not None:
            results = [dict(item) for item in cached.get("results", [])]
            for item in results:
                item.setdefault("trace", {})
                item["trace"]["cache"] = "hit"
                item["trace"]["cache_key"] = cache_key
                if not trace:
                    item.pop("score_parts", None)
            return results[:limit]
        cache_meta["status"] = "miss"

    errors: list[str] = []
    results: list[SearchResult] = []
    order = backend_order(backend, profile, site=site, query=original_query)
    for name in order:
        try:
            if name == "duckduckgo":
                results.extend(_search_duckduckgo(query, limit=limit))
            elif name == "bing":
                results.extend(_search_bing(query, limit=limit))
            elif name == "baidu":
                results.extend(_search_baidu(query, limit=limit))
            elif name == "wechat-sogou":
                if backend == "auto" and len(_dedupe_results(results)) >= limit:
                    continue
                results.extend(_search_wechat_sogou(original_query, limit=limit))
            elif name.startswith("plugin:"):
                results.extend(_search_plugin_backend(name, query, limit=limit))
            else:
                raise ValueError(f"unknown backend: {name}")
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue

    if not results and errors:
        fatal_errors = [
            error
            for error in errors
            if not (backend == "auto" and error.startswith("wechat-sogou:"))
        ]
        if fatal_errors:
            raise RuntimeError("; ".join(fatal_errors))
    ranked = rank_results(
        results,
        query=original_query,
        backend_order=order,
        preferred_scope=scope,
        cluster_threshold=cluster_threshold,
        recency=recency,
        quality=quality,
    )
    output_full = [r.to_dict() for r in ranked[:limit]]
    quality_summary = search_quality_summary(output_full, quality=quality)
    for item in output_full:
        item.setdefault("trace", {})
        item["trace"].update(
            {
                "effective_query": query,
                "backend_order": order,
                "cache": cache_meta["status"],
                "cache_key": cache_key,
                "cluster_threshold": cluster_threshold,
                "query_recency": recency,
                "query_quality": quality,
                "quality_summary": quality_summary,
                "errors": list(errors),
            }
        )
    if cache_meta["enabled"]:
        _cache_set("search", cache_key, {"results": output_full})
    output = [dict(item) for item in output_full]
    if not trace:
        for item in output:
            item.pop("score_parts", None)
    return output


def rank_results(
    results: list[SearchResult],
    query: str = "",
    backend_order: list[str] | None = None,
    preferred_scope: str | None = None,
    cluster_threshold: str = "conservative",
    recency: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
) -> list[SearchResult]:
    """Normalize, dedupe, classify, and score search results."""
    backend_order = backend_order or []
    quality = quality or detect_search_quality_profile(query, scope=preferred_scope)
    deduped = _dedupe_results(results)
    for item in deduped:
        item.domain = _domain(item.url)
        try:
            from guanlan.search_sources import classify_domain

            meta = classify_domain(item.domain, preferred_scope=preferred_scope)
        except Exception:
            meta = {"source_type": "通用网页", "matched_scope": "", "trust_level": 1}
        item.source_type = meta["source_type"]
        item.matched_scope = meta["matched_scope"]
        item.trust_level = meta["trust_level"]
        item.score_parts = _score_result_parts(
            item,
            query=query,
            backend_order=backend_order,
            recency=recency,
            quality=quality,
        )
        item.score = item.score_parts["total"]
        item.trace["recency"] = _result_recency_trace(item, recency)
        item.trace["quality"] = _result_quality_trace(item, quality)
    ranked = sorted(deduped, key=lambda r: (-r.score, r.rank))
    _assign_topic_clusters(ranked, threshold=cluster_threshold)
    ranked = _order_topic_representatives_first(ranked)
    for idx, item in enumerate(ranked, start=1):
        item.rank = idx
    return ranked


def _search_duckduckgo(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        page = resp.read().decode("utf-8", errors="replace")

    parser = _DuckDuckGoHTMLParser()
    parser.feed(page)
    return _dedupe_results(parser.results)[:limit]


def _search_bing(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "count": min(max(limit, 1), 50)})
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        page = resp.read().decode("utf-8", errors="replace")

    results: list[SearchResult] = []
    for block in re.findall(r'<li class="b_algo".*?</li>', page, flags=re.S):
        match = re.search(r"<h2[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.S)
        if not match:
            continue
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        title = _strip_tags(match.group(2))
        url = _normalize_bing_url(match.group(1))
        snippet = _strip_tags(snippet_match.group(1)) if snippet_match else ""
        if title and url:
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source="bing",
                    rank=len(results) + 1,
                )
            )
        if len(results) >= limit:
            break
    return results


def _search_baidu(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    # Baidu redirects HTTPS to HTTP for classic result HTML in some regions.
    url = "http://www.baidu.com/s?" + urllib.parse.urlencode({"wd": query, "rn": min(max(limit, 1), 50)})
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        page = resp.read().decode("utf-8", errors="replace")

    results: list[SearchResult] = []
    blocks = re.findall(r'<div class="result c-container.*?(?=<div class="result c-container|\Z)', page, flags=re.S)
    for block in blocks:
        title_match = re.search(r"<h3[^>]*>.*?<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.S)
        if not title_match:
            continue
        title = _strip_tags(title_match.group(2))
        href = html.unescape(title_match.group(1))
        mu_match = re.search(r'\bmu="([^"]+)"', block)
        url = html.unescape(mu_match.group(1)) if mu_match else href
        snippet = _strip_tags(_best_baidu_snippet(block))
        if title and url:
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source="baidu",
                    rank=len(results) + 1,
                )
            )
        if len(results) >= limit:
            break
    return results


def _search_wechat_sogou(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    api = _build_wechat_sogou_api()
    safe_query = _strip_site_filters(query)
    results: list[SearchResult] = []

    def reject_captcha(*_args, **_kwargs):
        raise RuntimeError("Sogou WeChat captcha required")

    pages = max(1, min(5, (max(limit, 1) + 9) // 10))
    for page in range(1, pages + 1):
        rows = api.search_article(
            safe_query,
            page=page,
            identify_image_callback=reject_captcha,
            decode_url=True,
        )
        for row in rows:
            item = _wechat_sogou_result(row, rank=len(results) + 1)
            if item:
                results.append(item)
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return results


def _build_wechat_sogou_api():
    try:
        import wechatsogou
    except ImportError as e:
        raise RuntimeError(
            "wechat-sogou backend requires optional dependency: "
            "install with `pip install 'guanlan[wechat]'` or "
            "`uv pip install 'guanlan[wechat]'`"
        ) from e
    return wechatsogou.WechatSogouAPI(captcha_break_time=1, timeout=min(_TIMEOUT, 10))


def _wechat_sogou_result(row: Any, rank: int) -> SearchResult | None:
    if not isinstance(row, dict):
        return None
    article = row.get("article")
    gzh = row.get("gzh")
    if not isinstance(article, dict):
        return None
    if not isinstance(gzh, dict):
        gzh = {}
    title = _collapse_ws(str(article.get("title") or ""))
    url = str(article.get("url") or article.get("content_url") or "").strip()
    if not title or not url.startswith(("http://", "https://")):
        return None

    abstract = _collapse_ws(str(article.get("abstract") or ""))
    wechat_name = _collapse_ws(str(gzh.get("wechat_name") or ""))
    published = _format_unix_date(article.get("time") or article.get("datetime"))
    snippet_parts = [part for part in (abstract, f"公众号: {wechat_name}" if wechat_name else "", f"发布: {published}" if published else "") if part]
    return SearchResult(
        title=title,
        url=url,
        snippet=" | ".join(snippet_parts),
        source="wechat_sogou",
        rank=rank,
    )


def _search_plugin_backend(backend: str, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    plugin_ref = backend.split(":", 1)[1].strip()
    if not plugin_ref:
        raise ValueError("plugin backend requires plugin:name or plugin:/path/to/script.py")
    script_path = _resolve_plugin_backend_path(plugin_ref)
    proc = subprocess.run(
        [sys.executable, str(script_path), query, str(limit)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"plugin backend exited {proc.returncode}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"plugin backend returned invalid JSON: {e}") from e
    rows = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise RuntimeError("plugin backend must return a JSON array or {'results': [...]}")
    results: list[SearchResult] = []
    for idx, row in enumerate(rows[:limit], start=1):
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", "")).strip()
        url = str(row.get("url", "")).strip()
        if not title or not url:
            continue
        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=str(row.get("snippet", "")).strip(),
                source=f"plugin:{plugin_ref}",
                rank=idx,
            )
        )
    return results


def _resolve_plugin_backend_path(plugin_ref: str) -> Path:
    candidate = Path(plugin_ref).expanduser()
    if candidate.is_file():
        return candidate
    from guanlan.config import Config

    backends = Config().get("backends", {}) or {}
    config = backends.get(plugin_ref) if isinstance(backends, dict) else None
    if not isinstance(config, dict) or config.get("type") != "plugin":
        raise ValueError(f"unknown plugin backend: {plugin_ref}")
    path = Path(str(config.get("path", ""))).expanduser()
    if not path.is_file():
        raise ValueError(f"plugin backend path does not exist: {path}")
    return path


def _is_wechat_search_intent(site: str | None = None, query: str | None = None) -> bool:
    text = f"{site or ''} {query or ''}".lower()
    return "mp.weixin.qq.com" in text or "weixin.qq.com" in text


def _strip_site_filters(query: str) -> str:
    cleaned = re.sub(r"\bsite:\s*[\w.-]+", " ", query or "", flags=re.I)
    return _collapse_ws(cleaned) or query.strip()


def _format_unix_date(value: Any) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    try:
        return dt.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""


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
) -> str:
    """Read a URL with Jina/direct fallbacks and optional search context."""
    url = url.strip()
    if not url:
        raise ValueError("url is required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    cache_key = ""
    if cache_ttl and cache_ttl > 0 and use_cache and not watch:
        cache_key = _cache_key(
            "read",
            {
                "url": url,
                "max_chars": max_chars or 0,
                "backend": backend,
                "fallback_search": fallback_search,
                "fallback_limit": fallback_limit,
                "profile": profile or "",
            },
        )
        cached = _cache_get("read", cache_key, ttl=cache_ttl)
        if cached is not None:
            return str(cached.get("text", ""))

    backend = (backend or "auto").lower()
    errors: list[str] = []
    text = ""
    weak_text = ""
    if backend in ("auto", "jina"):
        try:
            candidate = _read_with_jina(url)
            if backend == "auto" and _is_weak_read(candidate):
                errors.append("jina: weak or blocked content")
                weak_text = weak_text or candidate
            else:
                text = candidate
        except Exception as e:
            errors.append(f"jina: {e}")
            if backend == "jina":
                raise
    if not text and backend in ("auto", "direct"):
        try:
            candidate = _read_direct(url)
            if backend == "auto" and _is_weak_read(candidate):
                errors.append("direct: weak or blocked content")
                weak_text = weak_text or candidate
            else:
                text = candidate
        except Exception as e:
            errors.append(f"direct: {e}")
            if backend == "direct":
                raise
    if not text and fallback_search and backend == "auto":
        try:
            text = _read_search_context(url, errors=errors, limit=fallback_limit, profile=profile)
        except Exception as e:
            errors.append(f"search_context: {e}")
    if not text and weak_text:
        text = weak_text
    if not text and errors:
        raise RuntimeError("; ".join(errors))
    if max_chars and max_chars > 0:
        text = text[:max_chars]
    if watch:
        return _format_read_watch(url, text)
    if cache_key:
        _cache_set("read", cache_key, {"text": text})
    return text


def read_batch(
    urls: list[str],
    max_chars: int | None = None,
    backend: str = "auto",
    fallback_search: bool = True,
    fallback_limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
    cache_ttl: int = 0,
) -> list[dict[str, Any]]:
    """Read multiple URLs with per-item errors kept in the result list."""
    records: list[dict[str, Any]] = []
    for idx, url in enumerate(urls, start=1):
        clean_url = url.strip()
        if not clean_url:
            continue
        blocked_reason = _batch_block_reason(clean_url)
        if blocked_reason:
            records.append({"rank": idx, "url": clean_url, "status": "blocked", "error": blocked_reason})
            continue
        try:
            content = read_url(
                clean_url,
                max_chars=max_chars,
                backend=backend,
                fallback_search=fallback_search,
                fallback_limit=fallback_limit,
                profile=profile,
                cache_ttl=cache_ttl,
            )
            records.append({"rank": idx, "url": clean_url, "status": "ok", "content": content})
        except Exception as e:
            records.append({"rank": idx, "url": clean_url, "status": "error", "error": str(e)})
    return records


def _batch_block_reason(url: str) -> str:
    domain = _domain(url if url.startswith(("http://", "https://")) else "https://" + url)
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
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    query = _query_from_url(url)
    results = search_web(
        query,
        limit=max(limit, 1),
        site=domain or None,
        profile=profile,
    )
    if not results and domain:
        results = search_web(f"{domain} {query}", limit=max(limit, 1), profile=profile)

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
    lines.extend(["", format_search_markdown(results, title=f"观澜搜索兜底 / {query}")])
    return "\n".join(lines)


def _snapshot_path(url: str) -> Path:
    key = _cache_key("snapshot", {"url": url})
    return cache_dir() / "snapshots" / f"{key}.json"


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


def list_research_presets() -> dict[str, dict[str, Any]]:
    """Return available research presets."""
    return {key: dict(value) for key, value in RESEARCH_PRESETS.items()}


def resolve_research_preset(preset: str | None) -> dict[str, Any]:
    key = (preset or "general").strip().lower()
    if key not in RESEARCH_PRESETS:
        available = ", ".join(sorted(RESEARCH_PRESETS))
        raise ValueError(f"Unknown research preset: {preset}. Available: {available}")
    resolved = dict(RESEARCH_PRESETS[key])
    resolved["id"] = key
    return resolved


def build_research_packet(
    query: str,
    limit: int | None = None,
    site: str | None = None,
    sites: list[str] | None = None,
    scope: str | None = None,
    search_backend: str = "auto",
    profile: str | None = None,
    read_top: int | None = None,
    read_backend: str = "auto",
    max_read_chars: int | None = None,
    preset: str | None = "general",
    advisor: bool = False,
) -> dict[str, Any]:
    """Build an agent-ready evidence packet from search + selected reads."""
    preset_config = resolve_research_preset(preset)
    effective_limit = max(limit if limit is not None else preset_config["limit"], 1)
    effective_profile = profile or preset_config["profile"]
    explicit_scope = scope if scope not in (None, "") else None
    effective_scope = explicit_scope if explicit_scope is not None else preset_config["scope"]
    effective_sites = _research_sites(preset_config, site=site, sites=sites, explicit_scope=explicit_scope)
    effective_scopes = _research_scopes(
        preset_config,
        explicit_scope=explicit_scope,
        explicit_sites=effective_sites,
        site=site,
    )
    effective_read_top = max(read_top if read_top is not None else preset_config["read_top"], 0)
    effective_max_read_chars = max(
        max_read_chars if max_read_chars is not None else preset_config["max_read_chars"],
        1,
    )
    results, search_errors, result_groups = _research_search(
        query,
        limit=effective_limit,
        sites=effective_sites,
        scopes=effective_scopes,
        search_backend=search_backend,
        profile=effective_profile,
    )
    readings: list[dict[str, Any]] = []
    for item in _select_reading_candidates(results, effective_read_top):
        try:
            content = read_url(
                item["url"],
                max_chars=effective_max_read_chars,
                backend=read_backend,
                fallback_search=True,
                fallback_limit=DEFAULT_READ_FALLBACK_LIMIT,
                profile=effective_profile,
            )
            readings.append(_reading_record(item, status="ok", content=content))
        except Exception as e:
            readings.append(_reading_record(item, status="error", error=str(e)))

    packet = {
        "query": query,
        "preset": preset_config["id"],
        "preset_name": preset_config["name"],
        "profile": effective_profile or "",
        "site": site or "",
        "sites": effective_sites,
        "scope": effective_scope or "",
        "scopes": effective_scopes,
        "search_backend": search_backend,
        "read_backend": read_backend,
        "read_top": effective_read_top,
        "result_count": len(results),
        "source_mix": _source_mix(results),
        "topic_count": len({item.get("topic_key") for item in results if item.get("topic_key")}),
        "search_errors": search_errors,
        "result_groups": result_groups,
        "results": results,
        "readings": readings,
        "guidance": list(preset_config.get("guidance", [])) + [
            "这是一份证据上下文，不是最终结论。",
            "优先使用不同 topic、不同 source_type 的材料交叉验证。",
            "topic=related 的结果可作为补充线索，不要当成独立证据重复计数。",
            "阅读兜底内容只代表公开搜索线索，不等同于原文全文。",
        ],
    }
    if advisor:
        packet["advisor"] = build_advisor_view(packet)
    return packet


def format_research_markdown(packet: dict[str, Any]) -> str:
    """Render a research packet as compact Markdown for agents."""
    query = str(packet.get("query", "")).strip()
    lines = [f"# 观澜研究证据包 / {query}", ""]
    lines.append("## 使用说明")
    for note in packet.get("guidance", []):
        lines.append(f"- {note}")

    lines.extend(["", "## 信源概览"])
    lines.append(f"- 结果数: {packet.get('result_count', 0)}")
    lines.append(f"- Topic 数: {packet.get('topic_count', 0)}")
    source_mix = packet.get("source_mix", {})
    if source_mix:
        mix = "；".join(f"{key}: {value}" for key, value in source_mix.items())
        lines.append(f"- 信源类型: {mix}")
    if packet.get("scope"):
        lines.append(f"- Scope: {packet['scope']}")
    if packet.get("scopes"):
        lines.append(f"- Scopes: {', '.join(packet['scopes'])}")
    if packet.get("site"):
        lines.append(f"- Site: {packet['site']}")
    if packet.get("sites"):
        lines.append(f"- Sites: {', '.join(packet['sites'])}")
    if packet.get("preset"):
        lines.append(f"- Preset: {packet.get('preset')} / {packet.get('preset_name', '')}")
    if packet.get("search_errors"):
        lines.append(f"- 部分搜索失败: {'；'.join(packet['search_errors'])}")

    advisor = packet.get("advisor")
    if isinstance(advisor, dict):
        lines.extend(["", format_advisor_markdown(advisor)])

    groups = packet.get("result_groups", [])
    if groups:
        lines.extend(["", "## 子证据块"])
        for group in groups:
            label = str(group.get("label", ""))
            group_type = str(group.get("type", ""))
            count = group.get("result_count", 0)
            lines.extend(["", f"### {group_type}: {label}", f"- 结果数: {count}"])
            if group.get("error"):
                lines.append(f"- 错误: {group['error']}")
            group_results = group.get("results", [])
            if group_results:
                lines.extend(["", format_search_markdown(group_results[:3], title=f"{group_type} / {label}")])

    lines.extend(["", "## 搜索证据", ""])
    lines.append(format_search_markdown(packet.get("results", []), title="搜索结果"))

    readings = packet.get("readings", [])
    if readings:
        lines.extend(["", "## 原文摘读"])
        for item in readings:
            title = _collapse_ws(str(item.get("title", "")))
            url = str(item.get("url", ""))
            status = str(item.get("status", ""))
            source_type = str(item.get("source_type", "通用网页"))
            lines.extend(["", f"### [{status}] {title}", f"- URL: {url}", f"- 信源类型: {source_type}"])
            if item.get("error"):
                lines.append(f"- 读取错误: {item['error']}")
            content = str(item.get("content", "")).strip()
            if content:
                lines.extend(["", content])
    return "\n".join(lines)


def _research_scopes(
    preset_config: dict[str, Any],
    explicit_scope: str | None = None,
    explicit_sites: list[str] | None = None,
    site: str | None = None,
) -> list[str]:
    if explicit_scope:
        return [explicit_scope]
    # A caller-provided site request should stay narrowly site-bound unless the
    # caller also provides an explicit scope. Preset sites can still coexist
    # with preset scopes.
    if site and explicit_sites:
        return []
    scopes = [scope for scope in preset_config.get("scopes", []) if scope]
    if scopes:
        return scopes
    primary = preset_config.get("scope", "")
    return [primary] if primary else []


def _research_sites(
    preset_config: dict[str, Any],
    site: str | None = None,
    sites: list[str] | None = None,
    explicit_scope: str | None = None,
) -> list[str]:
    explicit = _normalize_sites(([site] if site else []) + (sites or []))
    if explicit:
        return explicit
    if explicit_scope:
        return []
    return _normalize_sites(preset_config.get("sites", []))


def _normalize_sites(sites: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for site in sites:
        value = (site or "").strip().lower()
        if not value:
            continue
        value = value.removeprefix("https://").removeprefix("http://").removeprefix("www.")
        value = value.split("/", 1)[0]
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized


def _research_search(
    query: str,
    limit: int,
    sites: list[str],
    scopes: list[str],
    search_backend: str,
    profile: str | None,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    groups: list[dict[str, Any]] = []
    jobs: list[tuple[str, str]] = [("scope", scope_id) for scope_id in scopes]
    jobs.extend(("site", site_id) for site_id in sites)
    if not jobs:
        results = search_web(query, limit=limit, backend=search_backend, profile=profile)
        return results, errors, [{"type": "general", "label": "web", "result_count": len(results), "results": results}]

    combined: list[dict[str, Any]] = []
    per_job_limit = max(3, min(limit, (limit // max(len(jobs), 1)) + 2))
    for job_type, target in jobs:
        try:
            result = search_web(
                query,
                limit=per_job_limit,
                site=target if job_type == "site" else None,
                scope=target if job_type == "scope" else None,
                backend=search_backend,
                profile=profile,
            )
            combined.extend(result)
            groups.append({"type": job_type, "label": target, "result_count": len(result), "results": result})
        except Exception as e:
            message = f"{job_type}:{target}: {e}"
            errors.append(message)
            groups.append({"type": job_type, "label": target, "result_count": 0, "results": [], "error": str(e)})
    if not combined and errors:
        raise RuntimeError("; ".join(errors))
    return _merge_ranked_result_dicts(combined, limit=limit), errors, groups


def _merge_ranked_result_dicts(results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    candidates = [_result_from_dict(item) for item in results if item.get("url")]
    candidates.sort(key=lambda item: (-item.score, item.rank))
    deduped = _dedupe_results(candidates)
    ranked = sorted(deduped, key=lambda item: (-item.score, item.rank))
    _assign_topic_clusters(ranked)
    ranked = _order_topic_representatives_first(ranked)
    for idx, item in enumerate(ranked, start=1):
        item.rank = idx
    return [item.to_dict() for item in ranked[:limit]]


def _result_from_dict(item: dict[str, Any]) -> SearchResult:
    return SearchResult(
        title=str(item.get("title", "")),
        url=str(item.get("url", "")),
        snippet=str(item.get("snippet", "")),
        source=str(item.get("source", "search")),
        rank=int(item.get("rank") or 0),
        domain=str(item.get("domain", "")),
        source_type=str(item.get("source_type", "通用网页")),
        matched_scope=str(item.get("matched_scope", "")),
        trust_level=int(item.get("trust_level") or 1),
        score=float(item.get("score") or 0),
        score_parts=dict(item.get("score_parts") or {}),
        topic_key=str(item.get("topic_key", "")),
        topic_size=int(item.get("topic_size") or 1),
        topic_role=str(item.get("topic_role", "single")),
        trace=dict(item.get("trace") or {}),
    )


def _select_reading_candidates(results: list[dict[str, Any]], read_top: int) -> list[dict[str, Any]]:
    if read_top <= 0:
        return []
    candidates = [item for item in results if item.get("topic_role") != "related"]
    if len(candidates) < read_top:
        seen = {item.get("url") for item in candidates}
        candidates.extend(item for item in results if item.get("url") not in seen)
    return candidates[:read_top]


def _reading_record(
    item: dict[str, Any],
    status: str,
    content: str = "",
    error: str = "",
) -> dict[str, Any]:
    return {
        "rank": item.get("rank", 0),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "source_type": item.get("source_type", "通用网页"),
        "topic_key": item.get("topic_key", ""),
        "topic_role": item.get("topic_role", ""),
        "status": status,
        "content": content,
        "error": error,
    }


def build_advisor_view(packet: dict[str, Any]) -> dict[str, Any]:
    """Build evidence-bound guidance that helps an agent write its own advice."""
    query = str(packet.get("query", "")).strip()
    preset = str(packet.get("preset", "general")).strip() or "general"
    results = list(packet.get("results") or [])
    readings = list(packet.get("readings") or [])
    source_mix = dict(packet.get("source_mix") or _source_mix(results))
    topic_count = int(packet.get("topic_count") or 0)
    result_count = int(packet.get("result_count") or len(results))
    read_top = int(packet.get("read_top") or 0)

    intents = _advisor_intents(query, preset, packet, source_mix)
    supports = _advisor_supports(source_mix, topic_count, result_count, readings)
    limits = _advisor_limits(packet, source_mix, topic_count, result_count, readings, read_top)
    next_steps = _advisor_next_steps(query, preset, source_mix, limits)

    return {
        "title": "助理视角规则",
        "mode": "agent_guidance",
        "stance": "以下内容用于指导 Agent 生成建议：它只约束如何基于当前证据思考，不代表用户真实目的，也不构成最终结论。",
        "synthesis_rules": _advisor_synthesis_rules(preset, query, source_mix),
        "suggested_angles": intents,
        "possible_intents": intents,
        "evidence_supports": supports,
        "evidence_limits": limits,
        "scenario_advice": _advisor_scenario_advice(preset, query, source_mix),
        "next_steps": next_steps,
        "response_contract": _advisor_response_contract(packet, limits),
    }


def format_advisor_markdown(advisor: dict[str, Any]) -> str:
    """Render advisor output as a compact, caveated Markdown block."""
    lines = [f"## {advisor.get('title') or '助理视角'}"]
    stance = str(advisor.get("stance") or "").strip()
    if stance:
        lines.extend(["", stance])
    sections = [
        ("给 Agent 的写作规则", advisor.get("synthesis_rules") or []),
        ("可展开的判断方向", advisor.get("suggested_angles") or advisor.get("possible_intents") or []),
        ("当前证据能支持", advisor.get("evidence_supports") or []),
        ("当前证据边界", advisor.get("evidence_limits") or []),
        ("不同场景的展开方式", advisor.get("scenario_advice") or []),
        ("输出时必须避免", advisor.get("response_contract") or []),
        ("建议补充", advisor.get("next_steps") or []),
    ]
    for title, items in sections:
        if not items:
            continue
        lines.extend(["", f"### {title}"])
        for item in items:
            lines.append(f"- {item}")
    return "\n".join(lines)


def format_advisor_context(advisor: dict[str, Any]) -> str:
    """Render advisor output for compact LLM context mode."""
    lines = [f"# {advisor.get('title') or '助理视角'}"]
    stance = str(advisor.get("stance") or "").strip()
    if stance:
        lines.append(stance)
    for key, title in (
        ("synthesis_rules", "写作规则"),
        ("suggested_angles", "可展开方向"),
        ("evidence_supports", "适合支持"),
        ("evidence_limits", "不适合支持"),
        ("scenario_advice", "下一步"),
        ("response_contract", "输出边界"),
    ):
        items = [str(item) for item in advisor.get(key, []) if str(item).strip()]
        if items:
            lines.append(f"{title}: " + "；".join(items[:3]))
    return "\n".join(lines)


def _advisor_synthesis_rules(
    preset: str,
    query: str,
    source_mix: dict[str, int],
) -> list[str]:
    rules = [
        "先用证据回答用户真正要解决的问题，再说明不确定性和需要补证的地方",
        "把建议写成可执行的下一步，而不是复述搜索结果或固定模板",
        "明确区分事实、推断、风险提醒和行动建议",
    ]
    if preset in {"policy", "official", "local"} or _contains_any(query, ["政策", "监管", "通知", "官方"]):
        rules.append("涉及政策或官方口径时，优先引用原文和发文主体，再解释影响")
    if preset in {"reputation", "ecommerce"} or _contains_any(query, ["口碑", "评价", "购买", "产品"]):
        rules.append("涉及口碑时，提炼高频场景和用户原话，不把样本热度写成总体比例")
    if any(_source_has(key, ["社交", "内容平台"]) for key in source_mix):
        rules.append("社交材料只能支持线索和表达，不直接支持总体判断")
    if _high_stakes_query(query):
        rules.append("涉及医疗、法律、金融或重大决策时，只给研究路线和风险提示")
    return _unique_keep_order(rules)[:5]


def _advisor_intents(
    query: str,
    preset: str,
    packet: dict[str, Any],
    source_mix: dict[str, int],
) -> list[str]:
    text = query.lower()
    sites = " ".join(str(site).lower() for site in packet.get("sites", []) or [])
    site = str(packet.get("site", "")).lower()
    scope = str(packet.get("scope", "")).lower()
    haystack = " ".join([text, sites, site, scope, preset])
    intents: list[str] = []

    if preset in {"policy", "official", "local"} or _contains_any(haystack, ["政策", "监管", "通知", "法规", "官方", "gov", "party_central"]):
        intents.extend(["寻找可引用的官方依据或政策口径", "判断某项政策、监管或公共议题对业务/研究的影响"])
    if preset in {"reputation", "ecommerce"} or _contains_any(haystack, ["评价", "口碑", "吐槽", "小红书", "知乎", "微博", "购买", "产品"]):
        intents.extend(["判断产品、品牌或服务的真实口碑线索", "为购买、选型、运营或竞品分析寻找用户语言"])
    if preset in {"industry", "finance"} or _contains_any(haystack, ["融资", "裁员", "财报", "股价", "行业", "商业化", "公司"]):
        intents.extend(["评估公司、行业或商业趋势是否值得继续关注", "识别合作、求职、投资或供应链相关风险"])
    if preset == "tech" or _contains_any(haystack, ["框架", "开源", "github", "技术", "开发者", "选型", "api"]):
        intents.extend(["做技术选型或工程调研", "寻找真实使用反馈、限制和可复现线索"])
    if any("社交" in key or "内容平台" in key for key in source_mix):
        intents.append("观察公开讨论中的情绪、痛点和高频表达")

    intents.append("快速判断这个主题是否值得进入更深一轮核验")
    return _unique_keep_order(intents)[:4]


def _advisor_supports(
    source_mix: dict[str, int],
    topic_count: int,
    result_count: int,
    readings: list[dict[str, Any]],
) -> list[str]:
    supports: list[str] = []
    source_keys = list(source_mix)
    if any(_source_has(key, ["政府", "部委", "党央媒", "官方"]) for key in source_keys):
        supports.append("判断官方口径、政策表述或权威报道中的主要说法")
    if any(_source_has(key, ["商业", "产业", "财经", "电商"]) for key in source_keys):
        supports.append("梳理商业媒体、产业媒体或财经来源中的趋势线索")
    if any(_source_has(key, ["社交", "内容平台", "开发者", "社区"]) for key in source_keys):
        supports.append("发现公开讨论里的用户语言、痛点、情绪和使用场景")
    if topic_count >= 3:
        supports.append("从多个 topic 中挑出不同角度，避免只围绕同一篇转载反复计数")
    elif result_count > 0:
        supports.append("形成初步线索清单，适合决定下一步读哪些原文")
    if any(item.get("status") == "ok" and str(item.get("content", "")).strip() for item in readings):
        supports.append("基于已读取原文片段做更稳的摘要和引用")
    return supports or ["形成初步搜索线索，但更适合继续核验而不是直接下结论"]


def _advisor_limits(
    packet: dict[str, Any],
    source_mix: dict[str, int],
    topic_count: int,
    result_count: int,
    readings: list[dict[str, Any]],
    read_top: int,
) -> list[str]:
    limits: list[str] = []
    source_keys = list(source_mix)
    successful_reads = [
        item for item in readings if item.get("status") == "ok" and str(item.get("content", "")).strip()
    ]
    if result_count < 3:
        limits.append("结果数量偏少，暂时不适合做强结论")
    if len(source_mix) <= 1 and result_count >= 3:
        limits.append("来源类型较单一，容易放大单一圈层或单一媒体视角")
    if topic_count <= 1 and result_count >= 3:
        limits.append("同题聚类较集中，可能存在转载或同源重复")
    if read_top == 0 or not successful_reads:
        limits.append("目前主要依赖搜索摘要，缺少原文级核验")
    if any(_source_has(key, ["社交", "内容平台"]) for key in source_keys):
        limits.append("社交平台材料适合发现样本线索，不适合直接代表总体口碑")
    if packet.get("search_errors"):
        limits.append("部分搜索后端失败，结果覆盖面可能不完整")
    if _high_stakes_query(str(packet.get("query", ""))):
        limits.append("这个查询可能涉及高影响决策，建议把当前输出只当作研究线索")
    return _unique_keep_order(limits)


def _advisor_scenario_advice(
    preset: str,
    query: str,
    source_mix: dict[str, int],
) -> list[str]:
    advice: list[str] = []
    text = query.lower()
    if preset in {"policy", "official", "local"}:
        advice.append("如果你是为了写材料或引用依据：优先读取政府/部委原文，再用媒体解读补背景")
        advice.append("如果你是为了判断影响：把政策原文、实施地区、适用对象和时间节点分开核对")
    if preset in {"reputation", "ecommerce"} or _contains_any(text, ["评价", "口碑", "购买", "产品"]):
        advice.append("如果你是为了购买或采用：先看负面反馈是否集中在同一版本、渠道或使用场景")
        advice.append("如果你是为了竞品/运营：提取用户原话和高频痛点，但不要用热门样本估算总体比例")
    if preset in {"industry", "finance"}:
        advice.append("如果你是为了商业判断：把事实报道、市场观点和公司宣传分开看")
        advice.append("如果你是为了风险判断：优先补官方公告、财报或一手披露材料")
    if preset == "tech":
        advice.append("如果你是为了技术选型：优先补版本、维护活跃度、真实限制和失败案例")
        advice.append("如果你是为了写方案：把社区反馈和官方文档分别引用")
    if any(_source_has(key, ["社交", "内容平台"]) for key in source_mix):
        advice.append("如果你是为了舆情观察：关注重复出现的表达和场景，不要只看单条高互动内容")
    if not advice:
        advice.append("如果你是为了快速了解：先读不同 source_type 的代表结果，再决定是否扩大搜索范围")
        advice.append("如果你是为了做判断：先补一手来源或原文摘读，再把当前结果当作辅助材料")
    return _unique_keep_order(advice)[:4]


def _advisor_next_steps(
    query: str,
    preset: str,
    source_mix: dict[str, int],
    limits: list[str],
) -> list[str]:
    steps: list[str] = []
    if any("原文" in item or "摘要" in item for item in limits):
        steps.append("读取 2-3 条不同 topic、不同 source_type 的代表原文")
    if any("来源类型较单一" in item for item in limits):
        steps.append("补一个不同信源池，例如官方、产业媒体或社交公开页")
    if any("社交平台" in item for item in limits):
        steps.append("把社交样本当作痛点池，再用官方说明或第三方评测交叉验证")
    if preset in {"policy", "official", "local"} and not any(_source_has(key, ["政府", "部委"]) for key in source_mix):
        steps.append("增加 gov 或 party_central scope，优先找原文")
    if preset in {"reputation", "ecommerce"} and not any(_source_has(key, ["社交", "内容平台"]) for key in source_mix):
        steps.append("补充知乎、微博、小红书、B站等公开页搜索，但注意登录态和样本偏差")
    if _high_stakes_query(query):
        steps.append("涉及重大决策时，补充权威来源或专业意见后再行动")
    steps.append("把当前建议视为下一步研究路线，而不是最终判断")
    return _unique_keep_order(steps)[:4]


def _advisor_response_contract(packet: dict[str, Any], limits: list[str]) -> list[str]:
    contract = [
        "不要声称已经知道用户真实动机，只能说“可能在关心”",
        "不要把当前搜索样本写成全网结论",
        "不要省略来源、证据边界和失败后端带来的覆盖缺口",
    ]
    if any("高影响决策" in item for item in limits) or _high_stakes_query(str(packet.get("query", ""))):
        contract.append("不要给医疗、法律、金融等高风险事项的最终建议")
    if packet.get("read_top") == 0:
        contract.append("没有原文摘读时，不要写成已经完成深度阅读")
    return contract


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle.lower() in text for needle in needles)


def _source_has(source_type: str, needles: list[str]) -> bool:
    return any(needle in source_type for needle in needles)


def _unique_keep_order(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _collapse_ws(str(item))
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


def _high_stakes_query(query: str) -> bool:
    return _contains_any(
        query.lower(),
        ["投资", "股票", "股价", "医疗", "诊断", "药", "法律", "诉讼", "裁员", "offer", "入职", "合规"],
    )


def _source_mix(results: list[dict[str, Any]]) -> dict[str, int]:
    mix: dict[str, int] = {}
    for item in results:
        key = str(item.get("source_type") or "通用网页")
        mix[key] = mix.get(key, 0) + 1
    return dict(sorted(mix.items(), key=lambda item: (-item[1], item[0])))


def source_distribution(results: list[dict[str, Any]], field: str = "source_type") -> list[dict[str, Any]]:
    """Return count/percent rows for source diagnostics."""
    counts: dict[str, int] = {}
    for item in results:
        if field == "domain":
            key = str(item.get("domain") or _domain(str(item.get("url", ""))) or "unknown")
        elif field == "source":
            key = str(item.get("source") or "search")
        else:
            key = str(item.get("source_type") or "通用网页")
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values())
    rows = []
    for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        rows.append(
            {
                "label": label,
                "count": count,
                "percent": (count / total * 100) if total else 0.0,
            }
        )
    return rows


def format_source_chart(
    results: list[dict[str, Any]],
    title: str = "来源分布",
    width: int = 24,
) -> str:
    """Render an ASCII source distribution chart for CLI diagnostics."""
    lines = ["", f"## {title}"]
    if not results:
        lines.append("- 暂无可统计结果。")
        return "\n".join(lines)

    sections = [
        ("信源类型", source_distribution(results, "source_type")),
        ("域名/平台", source_distribution(results, "domain")),
    ]
    for section_title, rows in sections:
        lines.extend(["", f"### {section_title}"])
        lines.extend(_format_chart_rows(rows, width=width))
    return "\n".join(lines)


def _format_chart_rows(rows: list[dict[str, Any]], width: int = 24) -> list[str]:
    if not rows:
        return ["- 暂无数据。"]
    max_count = max(int(row.get("count", 0)) for row in rows) or 1
    max_label = max(len(str(row.get("label", ""))) for row in rows)
    lines = []
    for row in rows:
        label = str(row.get("label", "unknown"))
        count = int(row.get("count", 0))
        percent = float(row.get("percent", 0.0))
        bar_len = max(1, round(count / max_count * width)) if count else 0
        bar = "#" * bar_len
        lines.append(f"- {label.ljust(max_label)} {bar.ljust(width)} {percent:5.1f}% ({count})")
    return lines


def format_search_markdown(results: list[dict[str, Any]], title: str = "观澜搜索") -> str:
    """Render search results as compact Markdown for agent context."""
    lines = [f"# {title}", ""]
    if not results:
        lines.append("暂无搜索结果。")
        return "\n".join(lines)

    for idx, item in enumerate(results, start=1):
        rank = item.get("rank") or idx
        item_title = _collapse_ws(str(item.get("title", "")))
        url = str(item.get("url", "")).strip()
        snippet = _collapse_ws(str(item.get("snippet", "")))
        source = str(item.get("source", "search")).strip()
        source_type = str(item.get("source_type", "通用网页")).strip()
        score = item.get("score", 0)
        score_label = f" score={score:.2f}" if isinstance(score, (int, float)) and score else ""
        topic_size = item.get("topic_size", 1)
        topic_role = str(item.get("topic_role", "single"))
        topic_label = ""
        if isinstance(topic_size, int) and topic_size > 1:
            topic_label = f" topic={topic_role}/{topic_size}"
        lines.append(f"{rank}. [{source}/{source_type}{score_label}{topic_label}] {item_title}")
        if url:
            lines.append(f"   {url}")
        if snippet:
            lines.append(f"   {snippet[:240]}")
    return "\n".join(lines)


def format_search_context(results: list[dict[str, Any]], title: str = "观澜搜索上下文") -> str:
    """Render compact LLM-friendly search context."""
    lines = [f"# {title}", "", "来源 | 标题 | 摘要 | 可信度 | Topic", "--- | --- | --- | --- | ---"]
    if not results:
        lines.append("无结果 | - | - | - | -")
        return "\n".join(lines)
    for idx, item in enumerate(results, start=1):
        source = _pipe_safe(str(item.get("source_type") or item.get("source") or "web"))
        title_text = _pipe_safe(_collapse_ws(str(item.get("title", ""))))
        snippet = _pipe_safe(_collapse_ws(str(item.get("snippet", "")))[:140])
        score = item.get("score", 0)
        score_text = f"{score:.2f}" if isinstance(score, (int, float)) else str(score or "")
        topic = str(item.get("topic_key") or f"result-{idx}")
        role = str(item.get("topic_role") or "single")
        url = str(item.get("url") or "")
        lines.append(f"{source} | [{title_text}]({url}) | {snippet} | {score_text} | {topic}/{role}")
    return "\n".join(lines)


def format_search_trace(results: list[dict[str, Any]]) -> str:
    """Render score and routing trace for search results."""
    lines = ["", "## 搜索 Trace"]
    if not results:
        lines.append("- 无结果。")
        return "\n".join(lines)
    query_quality = (results[0].get("trace") or {}).get("query_quality") or {}
    quality_summary = (results[0].get("trace") or {}).get("quality_summary") or {}
    if query_quality:
        preferred = ",".join(query_quality.get("preferred_source_types") or []) or "none"
        lines.append(
            "- query_quality: "
            f"intent={query_quality.get('intent', 'general')} "
            f"preferred={preferred} "
            f"hits={quality_summary.get('preferred_hit_count', 0)}/{quality_summary.get('result_count', 0)}"
        )
        for warning in quality_summary.get("warnings", []):
            lines.append(f"  warning: {warning}")
    for idx, item in enumerate(results, start=1):
        title = _collapse_ws(str(item.get("title", "")))
        parts = item.get("score_parts") or {}
        trace = item.get("trace") or {}
        recency = trace.get("recency") or {}
        quality = trace.get("quality") or {}
        part_text = ", ".join(
            f"{key}={value}" for key, value in parts.items() if key != "total"
        )
        recency_text = ""
        if recency.get("enabled"):
            result_date = recency.get("result_date") or "unknown"
            age_days = recency.get("age_days")
            in_window = recency.get("in_window")
            recency_text = (
                f"; recency={recency.get('window_days')}d "
                f"date={result_date} age={age_days} in_window={in_window}"
            )
        quality_text = ""
        if quality:
            quality_text = (
                f"; quality_fit={quality.get('fit')} "
                f"matched={quality.get('matched_reason', '')}"
            )
        lines.append(
            f"- result {idx}: score={item.get('score', 0)} ({part_text}); "
            f"topic={item.get('topic_key', '')}/{item.get('topic_role', '')}; "
            f"cache={trace.get('cache', 'disabled')}{recency_text}{quality_text}; title={title}"
        )
    return "\n".join(lines)


def format_read_batch_markdown(records: list[dict[str, Any]]) -> str:
    """Render batch read records as Markdown."""
    lines = ["# 观澜批量阅读", ""]
    if not records:
        lines.append("暂无 URL。")
        return "\n".join(lines)
    for item in records:
        status = str(item.get("status", ""))
        url = str(item.get("url", ""))
        lines.extend(["", f"## [{status}] {item.get('rank', '')}. {url}"])
        if item.get("error"):
            lines.append(f"读取错误: {item['error']}")
        content = str(item.get("content", "")).strip()
        if content:
            lines.extend(["", content])
    return "\n".join(lines)


def format_read_batch_context(records: list[dict[str, Any]]) -> str:
    """Render batch read records as compact prompt context."""
    lines = ["# 观澜批量阅读上下文", ""]
    for item in records:
        url = str(item.get("url", ""))
        status = str(item.get("status", ""))
        content = _collapse_ws(str(item.get("content") or item.get("error") or ""))
        lines.append(f"[{item.get('rank', '')}] {status} | {url} | {content[:500]}")
    return "\n".join(lines)


def _pipe_safe(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def detect_search_quality_profile(
    query: str,
    scope: str | None = None,
    site: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Detect source-quality preferences for a search query.

    This is intentionally advisory: it changes ranking weights and trace output,
    but it does not silently narrow the query to a scope unless the caller asked
    for one.
    """
    text = _collapse_ws(query).lower()
    reasons: list[str] = []
    intent = "general"
    matched_terms: list[str] = []

    explicit_scope = (scope or "").strip()
    if explicit_scope:
        try:
            from guanlan.search_sources import resolve_scope

            resolved = resolve_scope(explicit_scope)
            return {
                "intent": f"scope:{resolved.id}",
                "name": f"显式 scope / {resolved.name}",
                "matched_terms": [],
                "preferred_scopes": [resolved.id],
                "preferred_source_types": [resolved.source_type],
                "caution_source_types": [],
                "profile": profile or "",
                "site": site or "",
                "requested_scope": resolved.id,
                "guidance": "用户已指定 scope，优先尊重该信源池。",
                "reasons": [f"requested_scope:{resolved.id}"],
            }
        except Exception:
            reasons.append(f"unknown_scope:{explicit_scope}")

    for candidate, data in _QUALITY_INTENT_PROFILES.items():
        terms = [term for term in data["terms"] if _quality_term_matches(text, str(term))]
        if terms:
            intent = candidate
            matched_terms = terms
            reasons.append(f"matched_terms:{','.join(terms[:4])}")
            break

    data = _QUALITY_INTENT_PROFILES.get(intent, {})
    preferred_scopes = list(data.get("preferred_scopes", []))
    preferred_source_types = list(data.get("preferred_source_types", []))
    if profile == "china" and intent == "general":
        reasons.append("profile:china")
    if site:
        reasons.append(f"site:{site}")

    return {
        "intent": intent,
        "name": data.get("name", "通用网页研究"),
        "matched_terms": matched_terms,
        "preferred_scopes": preferred_scopes,
        "preferred_source_types": preferred_source_types,
        "caution_source_types": list(data.get("caution_source_types", [])),
        "profile": profile or "",
        "site": site or "",
        "requested_scope": explicit_scope,
        "guidance": data.get("guidance", "先看来源类型、topic 和时效性，再决定是否扩大搜索。"),
        "reasons": reasons,
    }


def search_quality_summary(
    results: list[dict[str, Any]],
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize whether a result set matches the query quality profile."""
    quality = quality or {}
    preferred_types = set(quality.get("preferred_source_types") or [])
    preferred_scopes = set(quality.get("preferred_scopes") or [])
    source_mix = _source_mix(results)
    preferred_hits = [
        item
        for item in results
        if item.get("source_type") in preferred_types or item.get("matched_scope") in preferred_scopes
    ]
    domains = {
        str(item.get("domain") or _domain(str(item.get("url", ""))))
        for item in results
        if item.get("url")
    }
    warnings: list[str] = []
    if preferred_types and not preferred_hits:
        warnings.append("未命中当前意图偏好的信源类型，建议补充 scope 或站点定向搜索。")
    if len(source_mix) <= 1 and len(results) >= 4:
        warnings.append("来源类型较单一，可能需要扩大信源面。")
    if len(domains) <= 1 and len(results) >= 3:
        warnings.append("域名集中度较高，注意同源转载或单站偏差。")

    return {
        "intent": quality.get("intent", "general"),
        "preferred_hit_count": len(preferred_hits),
        "result_count": len(results),
        "source_type_count": len(source_mix),
        "domain_count": len(domains),
        "source_mix": source_mix,
        "warnings": warnings,
    }


def _quality_term_matches(text: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9_+-]+", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", text, flags=re.I))
    return term.lower() in text


def detect_recency_intent(query: str) -> dict[str, Any]:
    """Detect whether a query needs tighter time bounds."""
    text = _collapse_ws(query).lower()
    today = dt.date.today()
    matched_terms: list[str] = []
    window_days = 0
    label = ""

    explicit_windows: tuple[tuple[str, int, tuple[str, ...]], ...] = (
        ("today", 1, ("今天", "今日", "当天", "当日", "刚刚", "实时", "24小时", "近24小时", "now", "today")),
        ("yesterday", 2, ("昨天", "昨日", "48小时", "近48小时")),
        ("week", 7, ("近一周", "最近一周", "过去一周", "一周内", "本周", "这周", "7天", "7日", "七天")),
        (
            "month",
            30,
            ("近一个月", "最近一个月", "过去一个月", "一个月内", "本月", "这个月", "30天", "30日", "三十天"),
        ),
        ("quarter", 90, ("近三个月", "最近三个月", "过去三个月", "一个季度", "本季度", "90天", "90日")),
    )
    for candidate_label, days, terms in explicit_windows:
        found = [term for term in terms if _recency_term_matches(text, term)]
        if found:
            label = candidate_label
            window_days = days
            matched_terms.extend(found)
            break

    if not window_days and _recency_term_matches(text, "今年"):
        label = "year_to_date"
        year_start = dt.date(today.year, 1, 1)
        window_days = max((today - year_start).days + 1, 1)
        matched_terms.append("今年")

    if not window_days:
        hot_terms = ("热点", "热搜", "快讯", "突发", "爆发", "热议", "刷屏")
        found_hot = [term for term in hot_terms if _recency_term_matches(text, term)]
        if found_hot:
            label = "hot"
            window_days = 7
            matched_terms.extend(found_hot)

    if not window_days:
        recent_terms = (
            "近期",
            "最近",
            "最新",
            "新近",
            "动态",
            "进展",
            "趋势",
            "舆情",
            "新闻",
            "报道",
            "current",
            "recent",
            "latest",
            "news",
        )
        found_recent = [term for term in recent_terms if _recency_term_matches(text, term)]
        if found_recent:
            label = "recent"
            window_days = _RECENCY_DEFAULT_WINDOW_DAYS
            matched_terms.extend(found_recent)

    if not window_days:
        return {
            "enabled": False,
            "label": "",
            "window_days": 0,
            "start_date": "",
            "end_date": today.isoformat(),
            "matched_terms": [],
        }

    start = today - dt.timedelta(days=max(window_days - 1, 0))
    return {
        "enabled": True,
        "label": label,
        "window_days": window_days,
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "matched_terms": matched_terms,
    }


def _apply_recency_query(query: str, recency: dict[str, Any]) -> str:
    if not recency.get("enabled"):
        return query
    if _query_already_has_absolute_date(query):
        return query
    today = _recency_today(recency)
    window_days = int(recency.get("window_days") or 0)
    suffix = f"{today.year}年{today.month}月 最新"
    if window_days <= 1:
        suffix = f"{today.year}年{today.month}月{today.day}日 最新"
    elif window_days <= 7:
        suffix = f"{today.year}年{today.month}月 近{window_days}天 最新"
    elif recency.get("label") == "year_to_date":
        suffix = f"{today.year}年 最新"
    if suffix in query:
        return query
    return f"{query} {suffix}".strip()


def _query_already_has_absolute_date(query: str) -> bool:
    return bool(
        re.search(r"(?:19|20)\d{2}", query)
        or re.search(r"\d{1,2}\s*月\s*\d{1,2}\s*日", query)
        or re.search(r"\d{4}\s*[-/.]\s*\d{1,2}", query)
    )


def _recency_term_matches(text: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9]+", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", text, flags=re.I))
    return term in text


def _recency_today(recency: dict[str, Any] | None = None) -> dt.date:
    if recency:
        try:
            end_date = str(recency.get("end_date") or "")
            if end_date:
                return dt.date.fromisoformat(end_date)
        except ValueError:
            pass
    return dt.date.today()


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: dict[str, SearchResult] = {}
    deduped: list[SearchResult] = []
    for item in results:
        key = _canonical_url(item.url)
        if not key:
            continue
        if key in seen:
            existing = seen[key]
            if len(item.snippet) > len(existing.snippet):
                existing.snippet = item.snippet
            if item.source not in existing.source.split("+"):
                existing.source = existing.source + "+" + item.source
            continue
        seen[key] = item
        item.rank = len(deduped) + 1
        deduped.append(item)
    return deduped


def _result_recency_trace(item: SearchResult, recency: dict[str, Any] | None = None) -> dict[str, Any]:
    metrics = _result_recency_metrics(item, recency)
    if not metrics["enabled"]:
        return {"enabled": False}
    result_date = metrics.get("result_date")
    return {
        "enabled": True,
        "window_days": metrics["window_days"],
        "start_date": metrics["start_date"],
        "end_date": metrics["end_date"],
        "matched_terms": metrics["matched_terms"],
        "result_date": result_date.isoformat() if isinstance(result_date, dt.date) else "",
        "age_days": metrics.get("age_days"),
        "in_window": metrics["in_window"],
    }


def _result_quality_trace(item: SearchResult, quality: dict[str, Any] | None = None) -> dict[str, Any]:
    quality = quality or {}
    preferred_types = set(quality.get("preferred_source_types") or [])
    preferred_scopes = set(quality.get("preferred_scopes") or [])
    matched_reason = ""
    if item.matched_scope and item.matched_scope in preferred_scopes:
        matched_reason = f"scope:{item.matched_scope}"
    elif item.source_type and item.source_type in preferred_types:
        matched_reason = f"source_type:{item.source_type}"
    elif quality.get("requested_scope") and item.matched_scope == quality.get("requested_scope"):
        matched_reason = f"requested_scope:{item.matched_scope}"
    return {
        "intent": quality.get("intent", "general"),
        "name": quality.get("name", ""),
        "fit": bool(matched_reason),
        "matched_reason": matched_reason,
        "preferred_scopes": list(preferred_scopes),
        "preferred_source_types": list(preferred_types),
        "guidance": quality.get("guidance", ""),
    }


def _result_recency_metrics(item: SearchResult, recency: dict[str, Any] | None = None) -> dict[str, Any]:
    recency = recency or {}
    enabled = bool(recency.get("enabled"))
    today = _recency_today(recency)
    window_days = int(recency.get("window_days") or 0)
    start_date = str(recency.get("start_date") or "")
    result_date = _extract_result_date(item, today=today) if enabled else None
    age_days = (today - result_date).days if result_date else None
    return {
        "enabled": enabled,
        "window_days": window_days,
        "start_date": start_date,
        "end_date": today.isoformat(),
        "matched_terms": list(recency.get("matched_terms") or []),
        "result_date": result_date,
        "age_days": age_days,
        "in_window": bool(result_date and age_days is not None and age_days <= max(window_days, 0)),
        "has_freshness_words": _has_freshness_words(item),
    }


def _extract_result_date(item: SearchResult, today: dt.date | None = None) -> dt.date | None:
    today = today or dt.date.today()
    text = _collapse_ws(f"{item.title} {item.snippet}")
    if not text:
        return None

    relative = _extract_relative_result_date(text, today)
    if relative:
        return relative

    patterns = (
        r"((?:19|20)\d{2})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})\s*日?",
        r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3)) if len(match.groups()) >= 3 and match.group(3) else 1
        parsed = _safe_date(year, month, day)
        if parsed:
            return parsed

    match = re.search(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if match:
        parsed = _safe_date(today.year, int(match.group(1)), int(match.group(2)))
        if parsed and parsed > today + dt.timedelta(days=7):
            parsed = _safe_date(today.year - 1, int(match.group(1)), int(match.group(2)))
        return parsed

    return None


def _extract_relative_result_date(text: str, today: dt.date) -> dt.date | None:
    if any(marker in text for marker in ("刚刚", "今天", "今日", "分钟前", "小时前")):
        return today
    if "昨天" in text:
        return today - dt.timedelta(days=1)
    if "前天" in text:
        return today - dt.timedelta(days=2)

    day_match = re.search(r"(\d+)\s*(?:天|日)\s*前", text)
    if day_match:
        return today - dt.timedelta(days=int(day_match.group(1)))
    week_match = re.search(r"(\d+)\s*(?:周|星期|礼拜)\s*前", text)
    if week_match:
        return today - dt.timedelta(days=int(week_match.group(1)) * 7)
    month_match = re.search(r"(\d+)\s*(?:个)?月\s*前", text)
    if month_match:
        return today - dt.timedelta(days=int(month_match.group(1)) * 30)
    year_match = re.search(r"(\d+)\s*年\s*前", text)
    if year_match:
        return today - dt.timedelta(days=int(year_match.group(1)) * 365)
    return None


def _safe_date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _has_freshness_words(item: SearchResult) -> bool:
    text = f"{item.title} {item.snippet}".lower()
    markers = (
        "今天",
        "今日",
        "刚刚",
        "最新",
        "热点",
        "热搜",
        "快讯",
        "突发",
        "实时",
        "进展",
        "latest",
        "breaking",
        "today",
    )
    return any(marker in text for marker in markers)


def _score_result_parts(
    item: SearchResult,
    query: str = "",
    backend_order: list[str] | None = None,
    recency: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
) -> dict[str, float]:
    backend_order = backend_order or []
    quality = quality or {}
    parts: dict[str, float] = {
        "base": 1.0,
        "source_credibility": min(item.trust_level, 5) * 0.25,
        "intent_fit": 0.0,
        "source_quality": _source_quality_weight(item.source_type),
        "content_length": 0.2 if item.snippet else 0.0,
        "keyword_match": 0.0,
        "backend_priority": 0.0,
        "recency_boost": 0.0,
        "ad_penalty": 0.0,
        "intent_mismatch_penalty": 0.0,
        "stale_penalty": 0.0,
    }
    title_text = (item.title + " " + item.snippet).lower()
    terms = [t.lower() for t in re.split(r"\s+", query) if t and not t.startswith("site:")]
    if terms:
        matched = sum(1 for term in terms if term in title_text)
        parts["keyword_match"] = min(matched / max(len(terms), 1), 1.0) * 0.8
    first_backend = (item.source.split("+")[0] or "").strip()
    if first_backend in backend_order:
        parts["backend_priority"] = max(0, len(backend_order) - backend_order.index(first_backend)) * 0.05
    preferred_scopes = set(quality.get("preferred_scopes") or [])
    preferred_source_types = set(quality.get("preferred_source_types") or [])
    caution_source_types = set(quality.get("caution_source_types") or [])
    if item.matched_scope and item.matched_scope in preferred_scopes:
        parts["intent_fit"] = 0.65
    elif item.source_type and item.source_type in preferred_source_types:
        parts["intent_fit"] = 0.48
    if item.source_type and item.source_type in caution_source_types:
        parts["intent_mismatch_penalty"] = -0.35
    if recency and recency.get("enabled"):
        metrics = _result_recency_metrics(item, recency)
        if metrics["result_date"] and metrics["age_days"] is not None:
            age_days = max(int(metrics["age_days"]), 0)
            window_days = max(int(metrics["window_days"] or 1), 1)
            if metrics["in_window"]:
                freshness = max((window_days - age_days) / window_days, 0)
                parts["recency_boost"] = 0.35 + freshness * 0.75
            else:
                overdue = max(age_days - window_days, 0)
                parts["stale_penalty"] = -min(2.4, 0.45 + overdue / window_days)
        else:
            parts["stale_penalty"] = -0.12
        if metrics["has_freshness_words"]:
            parts["recency_boost"] += 0.15
    if _looks_like_ad(item):
        parts["ad_penalty"] = -0.8
    total = sum(parts.values())
    parts["total"] = round(max(total, 0.1), 3)
    return {key: round(value, 3) for key, value in parts.items()}


def _source_quality_weight(source_type: str) -> float:
    weights = {
        "政府/部委": 0.35,
        "党央媒": 0.35,
        "地方官媒": 0.24,
        "财经/资本市场": 0.2,
        "电商/零售垂类": 0.16,
        "商业/产业媒体": 0.14,
        "科技/开发者社区": 0.12,
        "社交/内容平台": 0.04,
        "通用网页": 0.0,
    }
    return weights.get(source_type or "通用网页", 0.0)


def _assign_topic_clusters(results: list[SearchResult], threshold: str = "conservative") -> None:
    """Mark near-duplicate search results that discuss the same topic."""
    clusters: list[dict[str, Any]] = []
    for item in results:
        tokens = _topic_tokens(item.title)
        normalized = _normalize_topic_text(item.title)
        matched: dict[str, Any] | None = None
        for cluster in clusters:
            if _same_topic(normalized, tokens, cluster["normalized"], cluster["tokens"], threshold=threshold):
                matched = cluster
                break
        if matched is None:
            matched = {
                "key": f"topic-{len(clusters) + 1}",
                "normalized": normalized,
                "tokens": tokens,
                "items": [],
            }
            clusters.append(matched)
        item.topic_key = matched["key"]
        matched["items"].append(item)

    for cluster in clusters:
        items = cluster["items"]
        size = len(items)
        for idx, item in enumerate(items):
            item.topic_size = size
            item.topic_role = "single" if size == 1 else ("representative" if idx == 0 else "related")


def _order_topic_representatives_first(results: list[SearchResult]) -> list[SearchResult]:
    representatives = [item for item in results if item.topic_role != "related"]
    related = [item for item in results if item.topic_role == "related"]
    return _interleave_by_source_type(representatives) + related


def _interleave_by_source_type(results: list[SearchResult]) -> list[SearchResult]:
    """Prefer source-type diversity among already-ranked representative items."""
    buckets: dict[str, list[SearchResult]] = {}
    for item in results:
        key = item.source_type or "通用网页"
        buckets.setdefault(key, []).append(item)

    ordered: list[SearchResult] = []
    while buckets:
        for key in list(buckets):
            bucket = buckets[key]
            if bucket:
                ordered.append(bucket.pop(0))
            if not bucket:
                del buckets[key]
    return ordered


def _same_topic(
    left_text: str,
    left_tokens: set[str],
    right_text: str,
    right_tokens: set[str],
    threshold: str = "conservative",
) -> bool:
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    if min(len(left_text), len(right_text)) >= 12 and (left_text in right_text or right_text in left_text):
        return True
    if len(left_tokens) < 4 or len(right_tokens) < 4:
        return False
    overlap = left_tokens & right_tokens
    union = left_tokens | right_tokens
    min_overlap, ratio = {
        "conservative": (4, 0.42),
        "balanced": (3, 0.34),
        "loose": (3, 0.26),
    }.get((threshold or "conservative").lower(), (4, 0.42))
    return len(overlap) >= min_overlap and len(overlap) / max(len(union), 1) >= ratio


def _normalize_topic_text(text: str) -> str:
    text = _collapse_ws(text).lower()
    text = re.sub(r"[【\[].*?[】\]]", " ", text)
    text = re.sub(
        r"[\s\-_—|]+.{0,18}(?:网|新闻|客户端|频道|日报|时报|周刊|央视|人民网|新华网|新浪|搜狐|腾讯|网易|百家号)$",
        " ",
        text,
    )
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text


def _topic_tokens(text: str) -> set[str]:
    normalized = _collapse_ws(text).lower()
    tokens: set[str] = set()
    for segment in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", normalized):
        if re.fullmatch(r"[\u4e00-\u9fff]+", segment):
            for size in (2, 3):
                if len(segment) >= size:
                    tokens.update(segment[i : i + size] for i in range(len(segment) - size + 1))
        elif segment not in {"http", "https", "html", "www", "com", "cn"}:
            tokens.add(segment)
    return {token for token in tokens if token not in _TOPIC_STOP_TOKENS}


_TOPIC_STOP_TOKENS = {
    "中国",
    "我国",
    "进行",
    "相关",
    "最新",
    "消息",
    "新闻",
    "报道",
    "发布",
    "表示",
    "关于",
    "如何",
    "什么",
}


def _canonical_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        return url.strip()
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [
        (k, v)
        for k, v in query
        if not (k.lower().startswith("utm_") or k.lower() in {"spm", "from", "wfr", "for"})
    ]
    return urllib.parse.urlunparse(
        (
            parsed.scheme.lower() or "https",
            parsed.netloc.lower().removeprefix("www."),
            parsed.path.rstrip("/") or "/",
            "",
            urllib.parse.urlencode(filtered),
            "",
        )
    )


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _looks_like_ad(item: SearchResult) -> bool:
    text = f"{item.title} {item.snippet}".lower()
    return any(marker in text for marker in ("广告", "推广", "sponsored", "ad "))


def _is_weak_read(text: str) -> bool:
    normalized = _collapse_ws(text)
    if len(normalized) < _MIN_USEFUL_READ_CHARS:
        return True
    lowered = normalized.lower()
    return any(marker in lowered for marker in _WEAK_READ_MARKERS)


def _query_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    path = urllib.parse.unquote(parsed.path or "")
    stem = re.sub(r"\.[a-zA-Z0-9]{1,8}$", " ", path)
    stem = re.sub(r"[/_\-+]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    if stem:
        return stem[:120]
    return domain or url


def _read_with_jina(url: str) -> str:
    jina_url = f"https://r.jina.ai/{url}"
    req = urllib.request.Request(
        jina_url,
        headers={"User-Agent": _UA, "Accept": "text/plain"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _read_direct(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,text/plain",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        content_type = resp.headers.get("content-type", "")
    if "text/plain" in content_type:
        return raw
    return _html_to_markdownish(raw, url=url)


def _html_to_markdownish(raw: str, url: str = "") -> str:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    title = _strip_tags(title_match.group(1)) if title_match else ""
    text = _extract_article_text(raw)
    lines = []
    if title:
        lines.extend([f"Title: {title}", ""])
    if url:
        lines.extend([f"URL Source: {url}", ""])
    lines.append("Markdown Content:")
    lines.append(text)
    return "\n".join(lines)


def _extract_article_text(raw: str) -> str:
    """Extract readable article text while filtering common page chrome."""
    body = re.sub(r"<!--.*?-->", " ", raw or "", flags=re.S)
    body = re.sub(r"<(script|style|noscript|svg|canvas|iframe)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    body = re.sub(
        r"<(header|footer|nav|aside|form|button|select|option)[^>]*>.*?</\1>",
        " ",
        body,
        flags=re.S | re.I,
    )
    body = _prefer_main_content(body)
    body = re.sub(r"</?(?:p|div|section|article|main|h[1-6]|li|blockquote|tr|br)[^>]*>", "\n", body, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body or ""))
    raw_lines = [line.strip(" \t\r\n-•·|") for line in text.splitlines()]
    lines: list[str] = []
    seen: set[str] = set()
    for line in raw_lines:
        line = _collapse_ws(line)
        if _is_noise_content_line(line):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    if not lines:
        return _strip_tags(raw)
    return "\n\n".join(lines)


def _prefer_main_content(body: str) -> str:
    candidates = _content_candidates(body)
    if not candidates:
        return body
    best = max(candidates, key=_content_score)
    return best if _content_score(best) >= 120 else body


def _content_candidates(body: str) -> list[str]:
    candidates: list[str] = []
    attr_pattern = (
        r"(?:article|content|main|正文|post|entry|detail|news|rich_media_content|"
        r"article-content|article_body|articleBody)"
    )
    for pattern in (
        r"<article\b[^>]*>(.*?)</article>",
        r"<main\b[^>]*>(.*?)</main>",
        rf"<div\b[^>]*(?:id|class)=['\"][^'\"]*{attr_pattern}[^'\"]*['\"][^>]*>(.*?)</div>",
        rf"<section\b[^>]*(?:id|class)=['\"][^'\"]*{attr_pattern}[^'\"]*['\"][^>]*>(.*?)</section>",
    ):
        candidates.extend(match.group(1) for match in re.finditer(pattern, body, flags=re.S | re.I))
    return candidates


def _content_score(html_fragment: str) -> int:
    text = _strip_tags(html_fragment)
    if not text:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    paragraphs = len(re.findall(r"</p>|<br\b|</h[1-6]>", html_fragment, flags=re.I))
    link_text = "".join(re.findall(r"<a\b[^>]*>(.*?)</a>", html_fragment, flags=re.S | re.I))
    link_len = len(_strip_tags(link_text))
    return len(text) + cjk * 2 + paragraphs * 40 - link_len * 2


def _is_noise_content_line(line: str) -> bool:
    if not line:
        return True
    if len(line) <= 1:
        return True
    lowered = line.lower()
    noise_markers = (
        "登录",
        "注册",
        "分享",
        "收藏",
        "点赞",
        "评论",
        "发表评论",
        "下载app",
        "下载 app",
        "客户端",
        "扫码",
        "二维码",
        "广告",
        "推荐阅读",
        "相关阅读",
        "热门推荐",
        "返回首页",
        "首页",
        "导航",
        "菜单",
        "上一页",
        "下一页",
        "上一篇",
        "下一篇",
        "版权所有",
        "copyright",
        "icp",
        "京公网安备",
        "联系我们",
        "关于我们",
    )
    if len(line) <= 28 and any(marker in lowered for marker in noise_markers):
        return True
    if re.fullmatch(r"[\W_]+", line):
        return True
    if len(line) <= 18 and re.search(r"(首页|新闻|财经|科技|娱乐|体育|视频|图片|专题|登录|注册)", line):
        return True
    return False


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def _strip_tags(text: str) -> str:
    return _collapse_ws(re.sub(r"<[^>]+>", " ", text or ""))


def _best_baidu_snippet(block: str) -> str:
    # Prefer common abstract/summary containers, then fall back to visible text.
    for pattern in (
        r'<span[^>]+class="[^"]*(?:content-right|content|abstract)[^"]*"[^>]*>(.*?)</span>',
        r'<div[^>]+class="[^"]*(?:c-abstract|abstract|content)[^"]*"[^>]*>(.*?)</div>',
    ):
        match = re.search(pattern, block, re.S)
        if match:
            return match.group(1)
    return ""


def _normalize_ddg_url(url: str) -> str:
    url = html.unescape(url or "").strip()
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if parsed.path == "/l/":
        params = urllib.parse.parse_qs(parsed.query)
        uddg = params.get("uddg", [""])[0]
        if uddg:
            return urllib.parse.unquote(uddg)
    if url.startswith("//"):
        return "https:" + url
    return url


def _normalize_bing_url(url: str) -> str:
    url = html.unescape(url or "").strip()
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    encoded = params.get("u", [""])[0]
    if encoded.startswith("a1"):
        encoded = encoded[2:]
        padding = "=" * (-len(encoded) % 4)
        try:
            return base64.urlsafe_b64decode(encoded + padding).decode("utf-8", errors="replace")
        except Exception:
            return url
    return url


def _is_duckduckgo_noise(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host.endswith("duckduckgo.com")
