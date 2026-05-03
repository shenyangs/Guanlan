# -*- coding: utf-8 -*-
"""Search backend quality guards shared by search, tests, and release gates.

The functions here are deliberately side-effect free.  They judge whether a
backend batch is safe and relevant enough to stop fallback, but they do not run
network requests or mutate search results.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any, Protocol

LOW_RELEVANCE_RESULT_STATUS = "low_relevance"
UNSAFE_RESULT_STATUS = "unsafe_filtered"

KNOWN_LOW_VALUE_DOMAINS = {
    "support.microsoft.com",
}

UNSAFE_RESULT_DOMAINS = {
    "xnxx.com",
    "xvideos.com",
    "pornhub.com",
    "youporn.com",
    "redtube.com",
}

UNSAFE_RESULT_TERMS = (
    "free porn",
    "porn videos",
    "sex videos",
    "xxx",
    "成人",
    "色情",
)

CJK_RELEVANCE_PHRASES = (
    "固态电池",
    "全固态电池",
    "低空经济",
    "新质生产力",
    "人工智能",
    "数据要素",
    "人形机器人",
    "具身智能",
    "宁德时代",
    "量产",
    "时间表",
    "政策",
    "补贴",
    "进展",
    "财报",
    "公告",
    "风险",
    "口碑",
    "评价",
    "热榜",
    "热点",
)

QUERY_TOKEN_STOPWORDS = {
    "企业",
    "公司",
    "情况",
    "相关",
    "最新",
    "近期",
    "动态",
    "行业",
    "产业",
    "技术",
    "市场",
    "趋势",
    "融资",
}


class SearchResultLike(Protocol):
    title: str
    url: str
    snippet: str
    domain: str


def assess_backend_batch_quality(
    query: str,
    batch: list[SearchResultLike],
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reject obvious backend/parser drift before it can stop fallback.

    This gate is intentionally conservative: it only blocks batches with strong
    signs of being search drift, such as known low-value domains, no overlap with
    requested entities, unsafe single-domain dominance, or missing CJK compound
    terms.
    """
    if not batch:
        return {"usable": False, "reason": "empty", "note": "该后端未产出候选。"}
    quality = quality or {}
    terms = query_relevance_terms(query)
    entity_terms = query_entity_terms(query)
    domains = [_domain(item.url) for item in batch if item.url]
    top_domain = ""
    top_domain_ratio = 0.0
    if domains:
        counts = {domain: domains.count(domain) for domain in set(domains)}
        top_domain, top_count = max(counts.items(), key=lambda row: row[1])
        top_domain_ratio = top_count / max(len(domains), 1)

    matched_terms = {
        term
        for term in terms
        if any(result_text_contains(item, term) for item in batch)
    }
    matched_entities = {
        term
        for term in entity_terms
        if any(result_text_contains(item, term) for item in batch)
    }
    term_coverage = len(matched_terms) / max(len(terms), 1) if terms else 1.0
    entity_coverage = len(matched_entities) / max(len(entity_terms), 1) if entity_terms else 1.0
    reasons: list[str] = []
    if top_domain in KNOWN_LOW_VALUE_DOMAINS and not query_mentions_domain(query, top_domain):
        reasons.append(f"known_low_value_domain:{top_domain}")
    if len(entity_terms) >= 2 and entity_coverage == 0 and (contains_cjk(query) or len(batch) >= 3):
        reasons.append("requested_entities_missing")
    if contains_cjk(query) and len(terms) >= 3 and term_coverage < 0.5 and len(batch) >= 3:
        reasons.append("cjk_compound_terms_missing")
    if len(terms) >= 2 and term_coverage < 0.25 and len(batch) >= 3:
        reasons.append("query_terms_missing")
    if len(terms) >= 3 and term_coverage == 0 and top_domain_ratio >= 0.8 and len(batch) >= 4:
        reasons.append("single_domain_zero_query_overlap")

    if reasons:
        return {
            "usable": False,
            "reason": ",".join(reasons),
            "note": "该后端候选与查询意图明显不匹配，已继续尝试后续后端。",
            "term_coverage": round(term_coverage, 3),
            "entity_coverage": round(entity_coverage, 3),
            "top_domain": top_domain,
            "top_domain_ratio": round(top_domain_ratio, 3),
            "matched_terms": sorted(matched_terms),
            "matched_entities": sorted(matched_entities),
            "quality_intent": quality.get("intent", "general"),
        }
    return {
        "usable": True,
        "reason": "ok",
        "note": "候选批次通过粗粒度相关性门控。",
        "term_coverage": round(term_coverage, 3),
        "entity_coverage": round(entity_coverage, 3),
        "top_domain": top_domain,
        "top_domain_ratio": round(top_domain_ratio, 3),
        "matched_terms": sorted(matched_terms),
        "matched_entities": sorted(matched_entities),
        "quality_intent": quality.get("intent", "general"),
    }


def query_relevance_terms(query: str) -> list[str]:
    terms: list[str] = []
    for raw in re.findall(r"[\u4e00-\u9fffA-Za-z0-9+._-]+", collapse_ws(query)):
        term = raw.strip().lower()
        if not term or term in QUERY_TOKEN_STOPWORDS:
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", term):
            continue
        if re.fullmatch(r"\d+", term):
            continue
        if len(term) < 2:
            continue
        terms.extend(expand_relevance_term(term))
    return unique_keep_order(terms)


def expand_relevance_term(term: str) -> list[str]:
    if not contains_cjk(term):
        return [term]
    expanded = [phrase for phrase in CJK_RELEVANCE_PHRASES if phrase in term]
    if expanded:
        # Keep the original term when it is short enough to be a meaningful
        # compound, but avoid making a long unsplit Chinese sentence the only
        # relevance key.
        if len(term) <= 8:
            expanded.insert(0, term)
        return unique_keep_order(expanded)
    return [term]


def query_entity_terms(query: str) -> list[str]:
    terms = []
    for term in query_relevance_terms(query):
        if term in QUERY_TOKEN_STOPWORDS:
            continue
        if term in {"人形机器人", "机器人", "具身智能", "人工智能", "大模型"}:
            continue
        if len(term) >= 2:
            terms.append(term)
    return unique_keep_order(terms)


def result_text_contains(item: SearchResultLike, term: str) -> bool:
    haystack = collapse_ws(f"{item.title} {item.snippet} {item.url}").lower()
    return term.lower() in haystack


def filter_unsafe_search_results(batch: list[SearchResultLike]) -> dict[str, Any]:
    kept: list[SearchResultLike] = []
    dropped: list[dict[str, str]] = []
    for item in batch:
        reason = unsafe_search_result_reason(item)
        if reason:
            dropped.append(
                {
                    "title": item.title,
                    "domain": item.domain or _domain(item.url),
                    "reason": reason,
                }
            )
            continue
        kept.append(item)
    return {
        "kept_results": kept,
        "dropped_count": len(dropped),
        "dropped": dropped[:5],
        "policy": "adult_or_unsafe_search_result_filter",
    }


def unsafe_search_result_reason(item: SearchResultLike) -> str:
    domain = (item.domain or _domain(item.url)).lower().removeprefix("www.")
    if any(domain == unsafe or domain.endswith("." + unsafe) for unsafe in UNSAFE_RESULT_DOMAINS):
        return f"unsafe_domain:{domain}"
    text = collapse_ws(f"{item.title} {item.snippet} {item.url}").lower()
    for term in UNSAFE_RESULT_TERMS:
        if term in text:
            return f"unsafe_term:{term}"
    return ""


def query_mentions_domain(query: str, domain: str) -> bool:
    text = query.lower()
    root = domain.removeprefix("www.").split(".", 1)[0]
    return domain.lower() in text or root in text


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text or "")


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def unique_keep_order(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = collapse_ws(str(item))
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
