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

from guanlan.query_semantics import semantic_alias_terms, semantic_groups

LOW_RELEVANCE_RESULT_STATUS = "low_relevance"
UNSAFE_RESULT_STATUS = "unsafe_filtered"

KNOWN_LOW_VALUE_DOMAINS = {
    "support.microsoft.com",
}

LOW_VALUE_SAMPLE_DOMAINS = {
    "zhidao.baidu.com",
    "jingyan.baidu.com",
    "wenku.baidu.com",
    "baijiahao.baidu.com",
}

DICTIONARY_DRIFT_DOMAINS = {
    "baike.baidu.com",
    "hanyu.baidu.com",
    "dict.baidu.com",
    "zdic.net",
    "hxdic.net",
    "hanyuguoxue.com",
    "iciba.com",
    "dict.cn",
    "youdao.com",
    "cidian.911cha.com",
}

DICTIONARY_DRIFT_TERMS = (
    "释义",
    "基本解释",
    "详细解释",
    "拼音",
    "部首",
    "组词",
    "词典",
    "汉典",
    "爱词霸",
    "百科",
    "字义",
    "意思",
    "解释",
    "汉字",
    "笔顺",
    "读音",
)

SEO_TITLE_TERMS = (
    "客服电话",
    "24小时",
    "人工服务",
    "号码是多少",
    "联系电话",
    "官网入口",
    "app下载",
)

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
    "跨境电商",
    "跨境电子商务",
    "新质生产力",
    "人工智能",
    "人工智能政策",
    "数据要素",
    "人形机器人",
    "具身智能",
    "宁德时代",
    "珠海",
    "横琴",
    "横琴粤澳深度合作区",
    "量产",
    "时间表",
    "政策",
    "扶持",
    "办法",
    "通知",
    "申报",
    "指南",
    "公示",
    "专项资金",
    "意见",
    "补贴",
    "进展",
    "财报",
    "公告",
    "风险",
    "口碑",
    "评价",
    "导师",
    "招生",
    "研究生招生",
    "官网",
    "小米",
    "小米su7",
    "首销",
    "权益",
    "购车权益",
    "热榜",
    "热点",
)

CJK_RELEVANCE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("zhuhai_hengqin_location", ("珠海", "横琴", "横琴粤澳深度合作区", "广东")),
    ("cross_border_ecommerce", ("跨境电商", "跨境电子商务", "电子商务", "海外仓")),
    ("policy_notice", ("政策", "扶持", "办法", "通知", "申报", "指南", "公示", "专项资金", "意见", "措施", "支持", "奖励", "实施方案", "行动计划")),
    ("ai_policy", ("人工智能", "AI", "智能", "大模型", "算法")),
    ("solid_state_battery", ("固态电池", "全固态电池", "动力电池", "电池量产")),
    ("production_timeline", ("量产", "时间表", "产业化", "进展", "规划")),
    ("university_admission", ("高校", "大学", "学院", "研究生招生", "招生", "导师", "院系", "官网")),
    ("xiaomi_su7_product", ("小米", "小米SU7", "SU7", "汽车", "首销", "权益", "购车权益")),
    ("hara_kenya_design", ("原研哉", "设计哲学", "设计中的设计", "日本设计")),
)

CJK_REQUIRED_TOPIC_GROUPS = {
    "cross_border_ecommerce",
    "solid_state_battery",
    "hara_kenya_design",
}

CJK_COMPOUND_SPLIT_TERMS = (
    "字节跳动",
    "豆包",
    "抖音",
    "飞书",
    "火山引擎",
    "人工智能",
    "大模型",
    "AI",
    "战略",
    "流量",
    "优势",
    "品牌",
    "设计",
    "趋势",
    "房产",
    "加名",
    "婚前财产",
    "财产纠纷",
    "纠纷",
    "法院",
    "司法",
    "政策",
    "规定",
    "通知",
    "公告",
    "攻略",
    "应用",
    "开发",
    "改革",
    "动态",
    "案例",
    "调查",
    "本土化",
)

CJK_GENERIC_ENTITY_TERMS = {
    "AI",
    "战略",
    "流量",
    "优势",
    "品牌",
    "设计",
    "趋势",
    "房产",
    "加名",
    "纠纷",
    "政策",
    "规定",
    "通知",
    "公告",
    "攻略",
    "应用",
    "开发",
    "改革",
    "动态",
    "案例",
    "调查",
    "本土化",
}

OFFICIAL_DOMAIN_SUFFIXES = (
    "gov.cn",
    "hengqin.gov.cn",
    "zhuhai.gov.cn",
    "gd.gov.cn",
    "mofcom.gov.cn",
    "ndrc.gov.cn",
    "customs.gov.cn",
)

QUERY_TOKEN_STOPWORDS = {
    "企业",
    "公司",
    "情况",
    "相关",
    "最新",
    "近期",
    "今天",
    "今日",
    "刚刚",
    "昨天",
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
    groups = query_relevance_groups(query)
    matched_groups = matched_relevance_groups(batch, groups)
    group_coverage = len(matched_groups) / max(len(groups), 1) if groups else 1.0
    official_salvage = official_salvage_summary(batch, groups, quality)
    pollution = backend_pollution_summary(query, batch)
    pollution_reasons = " ".join(str(sample.get("reason") or "") for sample in pollution.get("samples") or [])
    requested_required_groups = {
        str(group.get("name"))
        for group in groups
        if str(group.get("name")) in CJK_REQUIRED_TOPIC_GROUPS
    }
    missing_required_groups = requested_required_groups - matched_groups
    reasons: list[str] = []
    if top_domain in KNOWN_LOW_VALUE_DOMAINS and not query_mentions_domain(query, top_domain):
        reasons.append(f"known_low_value_domain:{top_domain}")
    if len(entity_terms) >= 2 and entity_coverage == 0 and (contains_cjk(query) or len(batch) >= 3):
        reasons.append("requested_entities_missing")
    if missing_required_groups and len(batch) >= 3:
        reasons.append("required_topic_group_missing:" + "|".join(sorted(missing_required_groups)))
    if (
        contains_cjk(query)
        and len(terms) >= 3
        and term_coverage < 0.5
        and group_coverage < 0.5
        and len(batch) >= 3
    ):
        reasons.append("cjk_compound_terms_missing")
    if len(terms) >= 2 and term_coverage < 0.25 and group_coverage < 0.5 and len(batch) >= 3:
        reasons.append("query_terms_missing")
    if (
        contains_cjk(query)
        and len(terms) >= 5
        and term_coverage < 0.35
        and entity_coverage < 0.5
        and len(batch) >= 2
    ):
        reasons.append("cjk_multi_entity_sparse_coverage")
    if len(terms) >= 3 and term_coverage == 0 and top_domain_ratio >= 0.8 and len(batch) >= 4:
        reasons.append("single_domain_zero_query_overlap")
    if pollution["severity"] == "high" and "dictionary_definition_drift" in pollution_reasons:
        reasons.append("dictionary_definition_drift")
    if (
        pollution["severity"] == "high"
        and (len(batch) >= 3 or pollution.get("critical_count", 0))
        and not official_salvage["salvaged_count"]
    ):
        reasons.append("low_value_domain_pollution")

    if reasons:
        hard_reasons = [reason for reason in reasons if reason.startswith("known_low_value_domain")]
        if official_salvage["salvaged_count"] and not hard_reasons:
            return {
                "usable": True,
                "reason": "partial_salvage",
                "note": "该后端存在覆盖缺口，但已命中强官方/垂直信源；保留为可用线索并建议继续读取原文核验。",
                "term_coverage": round(term_coverage, 3),
                "entity_coverage": round(entity_coverage, 3),
                "group_coverage": round(group_coverage, 3),
                "top_domain": top_domain,
                "top_domain_ratio": round(top_domain_ratio, 3),
                "matched_terms": sorted(matched_terms),
                "matched_entities": sorted(matched_entities),
                "matched_groups": sorted(matched_groups),
                "missing_required_groups": sorted(missing_required_groups),
                "quality_intent": quality.get("intent", "general"),
                "pollution": pollution,
                "salvage": official_salvage,
                "suppressed_reasons": reasons,
            }
        return {
            "usable": False,
            "reason": ",".join(reasons),
            "note": "该后端候选与查询意图明显不匹配，已继续尝试后续后端。",
            "term_coverage": round(term_coverage, 3),
            "entity_coverage": round(entity_coverage, 3),
            "group_coverage": round(group_coverage, 3),
            "top_domain": top_domain,
            "top_domain_ratio": round(top_domain_ratio, 3),
            "matched_terms": sorted(matched_terms),
            "matched_entities": sorted(matched_entities),
            "matched_groups": sorted(matched_groups),
            "missing_required_groups": sorted(missing_required_groups),
            "quality_intent": quality.get("intent", "general"),
            "pollution": pollution,
        }
    return {
        "usable": True,
        "reason": "ok",
        "note": "候选批次通过粗粒度相关性门控。",
        "term_coverage": round(term_coverage, 3),
        "entity_coverage": round(entity_coverage, 3),
        "group_coverage": round(group_coverage, 3),
        "top_domain": top_domain,
        "top_domain_ratio": round(top_domain_ratio, 3),
        "matched_terms": sorted(matched_terms),
        "matched_entities": sorted(matched_entities),
        "matched_groups": sorted(matched_groups),
        "missing_required_groups": sorted(missing_required_groups),
        "quality_intent": quality.get("intent", "general"),
        "pollution": pollution,
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
    terms.extend(semantic_alias_terms(query))
    return unique_keep_order(terms)


def expand_relevance_term(term: str) -> list[str]:
    if not contains_cjk(term):
        return [term]
    expanded = [phrase for phrase in CJK_RELEVANCE_PHRASES if phrase in term]
    lowered = term.lower()
    expanded.extend(phrase for phrase in CJK_COMPOUND_SPLIT_TERMS if phrase.lower() in lowered)
    expanded.extend(cjk_compound_windows(term))
    if expanded:
        # Keep the original term when it is short enough to be a meaningful
        # compound, but avoid making a long unsplit Chinese sentence the only
        # relevance key.
        if len(term) <= 8:
            expanded.insert(0, term)
        return unique_keep_order(expanded)
    return [term]


def cjk_compound_windows(term: str) -> list[str]:
    """Extract stable CJK compound windows without exploding into every bigram."""
    if not contains_cjk(term):
        return []
    chunks = re.findall(r"[\u4e00-\u9fffA-Za-z0-9+._-]+", term)
    compounds: list[str] = []
    for chunk in chunks:
        if not contains_cjk(chunk):
            continue
        if 2 <= len(chunk) <= 8:
            compounds.append(chunk)
        if len(chunk) <= 4:
            continue
        for idx in range(0, max(0, len(chunk) - 4 + 1)):
            window = chunk[idx : idx + 4]
            if any(phrase in window for phrase in CJK_RELEVANCE_PHRASES if len(phrase) >= 3):
                compounds.append(window)
    return unique_keep_order(compounds)


def query_entity_terms(query: str) -> list[str]:
    terms = []
    for term in query_relevance_terms(query):
        if term in QUERY_TOKEN_STOPWORDS:
            continue
        if term in {"人形机器人", "机器人", "具身智能", "人工智能", "大模型"}:
            continue
        if term in CJK_GENERIC_ENTITY_TERMS:
            continue
        if len(term) >= 2:
            terms.append(term)
    return unique_keep_order(terms)


def query_relevance_groups(query: str) -> list[dict[str, Any]]:
    """Return soft semantic groups for CJK queries.

    Flat token coverage is brittle for Chinese policy and local-government
    searches because titles often rewrite "跨境电商政策" as "扶持申报通知".
    Groups let the gate distinguish "same task, different wording" from true
    retrieval drift.
    """
    if not contains_cjk(query):
        return []
    text = collapse_ws(query).lower()
    groups: list[dict[str, Any]] = []
    for name, aliases in CJK_RELEVANCE_GROUPS:
        if any(alias.lower() in text for alias in aliases):
            groups.append({"name": name, "aliases": list(aliases)})
    groups.extend(semantic_groups(query))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        name = str(group.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(
            {
                "name": name,
                "aliases": unique_keep_order([str(alias) for alias in group.get("aliases", []) if str(alias)]),
                "required": bool(group.get("required", False)),
            }
        )
    return deduped


def matched_relevance_groups(batch: list[SearchResultLike], groups: list[dict[str, Any]]) -> set[str]:
    matched: set[str] = set()
    for group in groups:
        aliases = [str(alias) for alias in group.get("aliases", []) if str(alias)]
        if any(any(result_text_contains(item, alias) for alias in aliases) for item in batch):
            matched.add(str(group.get("name") or ""))
    matched.discard("")
    return matched


def official_salvage_summary(
    batch: list[SearchResultLike],
    groups: list[dict[str, Any]],
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality = quality or {}
    intent = str(quality.get("intent") or "")
    requested_scope = str(quality.get("requested_scope") or "")
    route_intents = {str(item) for item in quality.get("route_intents", []) if str(item)}
    policy_like = (
        intent in {"policy", "local", "official_position", "standards_compliance", "legal_judicial", "medical_health"}
        or intent.startswith("scope:gov")
        or requested_scope in {"gov", "party_central", "local_official"}
        or bool({"policy", "official_position", "local", "ecommerce", "standards_compliance", "legal_judicial", "medical_health"} & route_intents)
    )
    if not policy_like or not groups:
        return {"salvaged_count": 0, "items": [], "reason": ""}
    items: list[dict[str, Any]] = []
    for item in batch:
        domain = (getattr(item, "domain", "") or _domain(getattr(item, "url", ""))).lower().removeprefix("www.")
        if not is_official_domain(domain):
            continue
        matched = matched_relevance_groups([item], groups)
        requested_required = {
            str(group.get("name"))
            for group in groups
            if bool(group.get("required", False)) or str(group.get("name")) in CJK_REQUIRED_TOPIC_GROUPS
        }
        if requested_required and not requested_required <= matched:
            continue
        if len(matched) < 2:
            continue
        items.append(
            {
                "title": getattr(item, "title", ""),
                "domain": domain,
                "url": getattr(item, "url", ""),
                "matched_groups": sorted(matched),
            }
        )
    return {
        "salvaged_count": len(items),
        "items": items[:5],
        "reason": "official_domain_with_semantic_group_match" if items else "",
    }


def is_official_domain(domain: str) -> bool:
    normalized = (domain or "").lower().removeprefix("www.")
    return any(normalized == suffix or normalized.endswith("." + suffix) for suffix in OFFICIAL_DOMAIN_SUFFIXES)


def result_text_contains(item: SearchResultLike, term: str) -> bool:
    haystack = collapse_ws(f"{item.title} {item.snippet} {item.url}").lower()
    needle = collapse_ws(term).lower()
    if not needle:
        return False
    if needle in haystack:
        return True
    return compact_relevance_text(needle) in compact_relevance_text(haystack)


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


def backend_pollution_summary(query: str, batch: list[SearchResultLike]) -> dict[str, Any]:
    """Detect low-value Q&A/SEO pollution without treating it as final truth."""
    if not batch:
        return {"enabled": False, "severity": "none", "polluted_count": 0, "ratio": 0.0}
    semantic_aliases = [alias.lower() for alias in semantic_alias_terms(query)]
    requested_versions = _model_version_mentions(query)
    samples: list[dict[str, str]] = []
    polluted_count = 0
    critical_count = 0
    for item in batch:
        domain = (getattr(item, "domain", "") or _domain(getattr(item, "url", ""))).lower().removeprefix("www.")
        title = collapse_ws(getattr(item, "title", ""))
        title_compact = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", title)
        text = collapse_ws(f"{title} {getattr(item, 'snippet', '')}").lower()
        reasons: list[str] = []
        if domain in LOW_VALUE_SAMPLE_DOMAINS:
            reasons.append(f"low_value_domain:{domain}")
        mismatch = _requested_model_version_mismatch(requested_versions, text)
        if mismatch and domain in LOW_VALUE_SAMPLE_DOMAINS:
            reasons.append(f"model_version_mismatch:{mismatch}")
            critical_count += 1
        if any(term.lower() in text for term in SEO_TITLE_TERMS):
            reasons.append("seo_or_service_phone_title")
        if domain in DICTIONARY_DRIFT_DOMAINS or any(term.lower() in text for term in DICTIONARY_DRIFT_TERMS):
            dictionary_title = any(term in title_compact for term in ("解释", "意思", "拼音", "笔顺", "汉字", "读音"))
            if len(collapse_ws(query)) >= 4 and (len(title_compact) <= 3 or dictionary_title):
                reasons.append("dictionary_definition_drift")
            elif semantic_aliases and not any(alias in text for alias in semantic_aliases):
                reasons.append("dictionary_definition_drift")
        if reasons:
            polluted_count += 1
            if len(samples) < 5:
                samples.append(
                    {
                        "title": collapse_ws(getattr(item, "title", ""))[:120],
                        "domain": domain,
                        "url": getattr(item, "url", ""),
                        "reason": ",".join(reasons),
                    }
                )
    ratio = polluted_count / max(len(batch), 1)
    severity = "high" if ratio >= 0.5 else ("medium" if ratio >= 0.25 else ("low" if polluted_count else "none"))
    return {
        "enabled": bool(polluted_count),
        "severity": severity,
        "polluted_count": polluted_count,
        "critical_count": critical_count,
        "total": len(batch),
        "ratio": round(ratio, 3),
        "samples": samples,
        "agent_note": (
            "候选里出现百度知道/经验/文库、百家号或客服号码类 SEO 污染；"
            "应降权并补官方、垂直或 scope 搜索，不要把这类样本当主证据。"
            if polluted_count
            else ""
        ),
    }


def _model_version_mentions(text: str) -> list[dict[str, str]]:
    patterns = (
        ("GLM", r"\bGLM[-\s]?\d+(?:\.\d+)?\b"),
        ("Kimi", r"\bKimi[-\s]?\d+(?:\.\d+)?\b"),
        ("Qwen", r"\bQwen[-\s]?\d+(?:\.\d+)?\b"),
        ("DeepSeek", r"\bDeepSeek[-\s]?[A-Za-z]?\d+(?:\.\d+)?\b"),
        ("Doubao", r"\bDoubao[-\s]?\d+(?:\.\d+)?\b"),
    )
    mentions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for family, pattern in patterns:
        for match in re.finditer(pattern, text or "", flags=re.I):
            raw = collapse_ws(match.group(0))
            normalized = re.sub(r"[-_\s]+", " ", raw).strip()
            version = normalized.split(maxsplit=1)[1] if len(normalized.split(maxsplit=1)) > 1 else ""
            canonical = f"{family} {version}".strip()
            key = (family, canonical.lower())
            if key in seen:
                continue
            seen.add(key)
            mentions.append({"family": family, "mention": canonical})
    return mentions


def _requested_model_version_mismatch(requested_versions: list[dict[str, str]], result_text: str) -> str:
    if not requested_versions:
        return ""
    result_versions = _model_version_mentions(result_text)
    if not result_versions:
        return ""
    result_by_family: dict[str, set[str]] = {}
    for mention in result_versions:
        result_by_family.setdefault(mention["family"], set()).add(mention["mention"].lower())
    for requested in requested_versions:
        family = requested["family"]
        wanted = requested["mention"].lower()
        observed = result_by_family.get(family, set())
        if observed and wanted not in observed:
            return requested["mention"]
    return ""


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


def compact_relevance_text(text: str) -> str:
    """Normalize display text for CJK/ASCII mixed relevance matching."""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", collapse_ws(text).lower())


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
