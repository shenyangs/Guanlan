# -*- coding: utf-8 -*-
"""Packaged hotboard catalog and optional detail API helpers.

The catalog is shipped as a local routing table. Live detail calls are opt-in
and require a user-provided key.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from functools import lru_cache
from importlib import resources
from typing import Any

API_BASE_URL = "https://api.tophubdata.com"
CATALOG_RESOURCE = "data/hotboard_nodes.json"

CATEGORY_NAMES: dict[int, str] = {
    1: "综合",
    2: "科技",
    3: "娱乐",
    4: "社区",
    5: "购物",
    6: "财经",
    7: "开发",
    8: "高校",
    9: "机构",
    10: "博客",
    12: "电子报",
    13: "设计",
}

CATEGORY_ALIASES: dict[str, set[int]] = {
    "all": set(CATEGORY_NAMES),
    "catalog": set(CATEGORY_NAMES),
    "综合": {1},
    "news": {1},
    "hot": {1},
    "科技": {2},
    "tech": {2, 7},
    "ai": {2, 7},
    "娱乐": {3},
    "ent": {3},
    "entertainment": {3},
    "社区": {4},
    "community": {4},
    "购物": {5},
    "shopping": {5},
    "ecommerce": {5},
    "财经": {6},
    "finance": {6},
    "开发": {7},
    "developer": {7},
    "高校": {8},
    "university": {8},
    "机构": {9},
    "official": {9},
    "gov": {9},
    "policy": {9},
    "博客": {10},
    "blog": {10},
    "电子报": {12},
    "epaper": {12},
    "设计": {13},
    "design": {13},
}

COMMON_ALIASES: dict[str, str] = {
    "weibo": "KqndgxeLl9",
    "微博": "KqndgxeLl9",
    "zhihu": "mproPpoq6O",
    "知乎": "mproPpoq6O",
    "baidu": "Jb0vmloB1G",
    "百度": "Jb0vmloB1G",
    "toutiao": "x9ozB4KoXb",
    "今日头条": "x9ozB4KoXb",
    "thepaper": "wWmoO5Rd4E",
    "澎湃": "wWmoO5Rd4E",
    "wechat": "WnBe01o371",
    "微信": "WnBe01o371",
    "douyin": "DpQvNABoNE",
    "抖音": "DpQvNABoNE",
    "xiaohongshu": "L4MdA5ldxD",
    "xhs": "L4MdA5ldxD",
    "小红书": "L4MdA5ldxD",
    "bilibili": "VaobLKGdAj",
    "b站": "VaobLKGdAj",
    "哔哩哔哩": "VaobLKGdAj",
    "ithome": "74Kvx59dkx",
    "it之家": "74Kvx59dkx",
    "v2ex": "KGoRAN1el6",
    "github": "rYqoXQ8vOD",
    "36kr": "Q1Vd5Ko85R",
    "36氪": "Q1Vd5Ko85R",
    "yicai": "0MdKam4ow1",
    "第一财经": "0MdKam4ow1",
    "xueqiu": "X12owXzvNV",
    "雪球": "X12owXzvNV",
    "gov": "47o8ELqvMm",
    "gov.cn": "47o8ELqvMm",
    "中国政府网": "47o8ELqvMm",
}

ROUTE_CATEGORY_BY_INTENT: dict[str, str] = {
    "policy": "policy",
    "official_position": "policy",
    "industry": "finance",
    "ecommerce": "ecommerce",
    "tech": "tech",
    "wps_office": "tech",
    "science": "tech",
    "entertainment": "entertainment",
    "reputation": "community",
    "purchase_advice": "shopping",
    "finance": "finance",
    "finance_quote": "finance",
    "finance_disclosure": "finance",
    "finance_macro": "finance",
    "finance_sentiment": "finance",
    "finance_research": "finance",
    "career": "community",
    "podcast": "tech",
    "university_admissions": "university",
}


def api_key() -> str:
    """Return the configured hotboard API key without logging it."""
    return (
        os.environ.get("GUANLAN_HOTBOARD_API_KEY")
        or os.environ.get("HOTBOARD_API_KEY")
        or ""
    ).strip()


@lru_cache(maxsize=1)
def load_catalog_payload() -> dict[str, Any]:
    """Load the packaged hotboard node table."""
    path = resources.files("guanlan")
    for part in CATALOG_RESOURCE.split("/"):
        path = path.joinpath(part)
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        return {"meta": {}, "nodes": []}
    return payload


def catalog_meta() -> dict[str, Any]:
    return dict(load_catalog_payload().get("meta") or {})


def catalog_nodes() -> list[dict[str, Any]]:
    return [dict(item) for item in load_catalog_payload().get("nodes") or [] if isinstance(item, dict)]


def category_name(cid: Any) -> str:
    try:
        return CATEGORY_NAMES.get(int(cid), str(cid or ""))
    except (TypeError, ValueError):
        return str(cid or "")


def normalize_category(value: str | None) -> set[int]:
    key = (value or "").strip().lower()
    if not key:
        return set()
    return set(CATEGORY_ALIASES.get(key, set()))


def search_catalog(
    *,
    query: str = "",
    category: str = "",
    domain: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Search the local hotboard node table for routing and catalog output."""
    terms = _terms(query)
    category_ids = normalize_category(category)
    domain = domain.strip().lower().removeprefix("www.")
    scored: list[tuple[int, dict[str, Any]]] = []
    for node in catalog_nodes():
        if category_ids and _safe_int(node.get("cid")) not in category_ids:
            continue
        node_domain = str(node.get("domain") or "").lower().removeprefix("www.")
        if domain and domain not in node_domain:
            continue
        haystack = " ".join(
            str(node.get(key) or "")
            for key in ("name", "display", "domain", "hashid")
        ).lower()
        if terms and not any(term in haystack for term in terms):
            continue
        score = _node_score(node, terms=terms, domain=domain)
        enriched = enrich_node(node)
        enriched["route_score"] = score
        scored.append((score, enriched))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("name") or ""), str(item[1].get("display") or "")))
    return [item for _, item in scored[: max(limit, 1)]]


def recommend_nodes_for_route(
    query: str,
    *,
    intents: list[str],
    domains: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return local hotboard nodes that fit a route plan."""
    categories = [ROUTE_CATEGORY_BY_INTENT[intent] for intent in intents if intent in ROUTE_CATEGORY_BY_INTENT]
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for category in categories[:3]:
        nodes = search_catalog(query=query, category=category, limit=max(limit * 2, 8))
        if not nodes:
            nodes = search_catalog(category=category, limit=max(limit * 2, 8))
        for node in nodes:
            hashid = str(node.get("hashid") or "")
            if hashid and hashid not in seen:
                seen.add(hashid)
                candidates.append(node)
            if len(candidates) >= limit:
                return candidates
    for domain in domains or []:
        for node in search_catalog(domain=domain, limit=3):
            hashid = str(node.get("hashid") or "")
            if hashid and hashid not in seen:
                seen.add(hashid)
                candidates.append(node)
            if len(candidates) >= limit:
                return candidates
    return candidates[:limit]


def resolve_node(value: str) -> dict[str, Any] | None:
    """Resolve an alias, hashid, name, display, or domain to a local node."""
    raw = (value or "").strip()
    if not raw:
        return None
    key = raw.lower().removeprefix("node:").strip()
    alias = COMMON_ALIASES.get(key) or COMMON_ALIASES.get(raw)
    nodes = catalog_nodes()
    if alias:
        key = alias
    for node in nodes:
        if str(node.get("hashid") or "") == key:
            return enrich_node(node)
    matches = search_catalog(query=raw, limit=1)
    return matches[0] if matches else None


def enrich_node(node: dict[str, Any]) -> dict[str, Any]:
    data = dict(node)
    data["category_name"] = category_name(data.get("cid"))
    data["source_url"] = ""
    data["command"] = f"guanlan hotnews hotboard:node:{data.get('hashid')} --limit 80"
    return data


def fetch_api_json(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call the optional hotboard API endpoint with a configured key."""
    key = api_key()
    if not key:
        raise RuntimeError("Hotboard API key is not configured; set GUANLAN_HOTBOARD_API_KEY.")
    path = path if path.startswith("/") else "/" + path
    url = API_BASE_URL.rstrip("/") + path
    if params:
        clean = {k: v for k, v in params.items() if v not in ("", None)}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "guanlan/0.1",
            "Accept": "application/json",
            "Authorization": key,
        },
    )
    try:
        context = _ssl_context()
        with urllib.request.urlopen(req, timeout=20, context=context) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except TypeError:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise RuntimeError("Hotboard API returned a non-object JSON payload.")
    if payload.get("error"):
        status = payload.get("status")
        msg = payload.get("msg") or "Hotboard API error"
        if status == 100300:
            raise RuntimeError("Hotboard API key is valid but balance is insufficient.")
        raise RuntimeError(f"Hotboard API error {status}: {msg}")
    return payload


def fetch_node_detail(hashid: str) -> dict[str, Any]:
    return fetch_api_json(f"/nodes/{hashid}")


def fetch_node_snapshots(hashid: str, *, date: str = "", details: bool = False) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if date:
        params["date"] = date
    if details:
        params["details"] = 1
    return fetch_api_json(f"/nodes/{hashid}/snapshots", params=params)


def _node_score(node: dict[str, Any], *, terms: list[str], domain: str) -> int:
    score = 0
    name = str(node.get("name") or "").lower()
    display = str(node.get("display") or "").lower()
    node_domain = str(node.get("domain") or "").lower()
    if terms:
        for term in terms:
            if term in name:
                score += 8
            if term in display:
                score += 5
            if term in node_domain:
                score += 4
    if domain and domain in node_domain:
        score += 12
    if any(word in display for word in ("热榜", "热搜", "热门", "排行", "日榜", "今日", "最新")):
        score += 3
    return score


def _terms(query: str) -> list[str]:
    text = (query or "").strip().lower()
    if not text:
        return []
    parts = [part for part in re.split(r"[\s,，/|]+", text) if part]
    if len(text) <= 12 and text not in parts:
        parts.insert(0, text)
    return parts[:8]


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()
