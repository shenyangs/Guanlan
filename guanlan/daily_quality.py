# -*- coding: utf-8 -*-
"""Editorial quality helpers for Guanlan daily reports.

Daily reports need a stricter evidence boundary than plain search results:
official/self-owned pages, outside reporting, community samples, and weak SEO
must not be flattened into one list. This module owns those classifications so
the daily workflow does not keep hand-writing source truth.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from guanlan.source_taxonomy import source_card_for_domain

SOURCE_TIER_LABELS = {
    "A": "A 一手/官方/监管",
    "B": "B 媒体/产业/开发者",
    "C": "C 社区/用户样本",
    "D": "D 弱线索/SEO/转载",
}

FRESHNESS_LABELS = {
    "today": "今天",
    "recent_3d": "近 3 天",
    "recent_7d": "近 7 天",
    "background": "背景资料",
    "unknown": "时间未知",
}

VALID_DAILY_TIME_WINDOWS = {"today", "24h", "3d", "7d"}

KNOWN_WPS_OWNED_DOMAINS = (
    "wps.cn",
    "wps.com",
    "kingsoft.com",
    "kdocs.cn",
)
KNOWN_WPS_COMMUNITY_HOSTS = (
    "forum.wps.cn",
    "bbs.wps.cn",
)
SOFT_SEO_DOMAINS = (
    "lnbuy.net",
    "baijiahao.baidu.com",
    "360doc.com",
    "docin.com",
    "jianghu.taobao.com",
    "jsbg-wps.com.cn",
    "pc6.com",
    "onlinedown.net",
    "downza.cn",
    "crsky.com",
)
RECOGNIZED_EXTERNAL_DOMAINS = (
    "ithome.com",
    "36kr.com",
    "huxiu.com",
    "leiphone.com",
    "sspai.com",
    "geekpark.net",
    "ifanr.com",
    "sina.cn",
    "sina.com.cn",
    "new.qq.com",
    "thepaper.cn",
    "jiemian.com",
    "yicai.com",
    "tmtpost.com",
    "cloud.tencent.com",
    "caixin.com",
    "cls.cn",
    "stcn.com",
    "donews.com",
)

OFFICIAL_ROLES = {
    "company_primary",
    "product_primary",
    "official_primary",
    "government",
    "company_filing",
    "security_advisory",
    "authoritative_report",
}
ECOSYSTEM_ROLES = {
    "industry_report",
    "vertical_report",
    "fresh_news",
    "news_signal",
    "tech_news_signal",
    "market_news",
    "market_quote",
    "reading_signal",
    "ai_vertical_discovery_signal",
}
COMMUNITY_ROLES = {
    "community_discussion",
    "developer_discussion",
    "user_sample",
    "review",
    "platform_metric",
}
TRUST_TERMS = (
    "安全",
    "合规",
    "隐私",
    "数据",
    "漏洞",
    "审计",
    "信创",
    "采购",
    "企业信任",
    "security",
    "privacy",
    "compliance",
)
SOFT_TITLE_TERMS = (
    "秘密武器",
    "全解析",
    "告别加班",
    "一键做",
    "小白",
    "保姆级",
    "效率 直接翻倍",
    "效率直接翻倍",
    "塞进",
    "全攻略",
    "领取 ai",
    "激活智能",
    "资源导航站",
    "ai资源导航",
    "官网下载",
    "免费下载安装",
    "破解版",
    "绿色版",
    "安装包",
)


def normalize_daily_time_window(value: str) -> str:
    """Return a supported daily freshness window."""
    clean = str(value or "3d").strip().lower()
    return clean if clean in VALID_DAILY_TIME_WINDOWS else "3d"


def annotate_daily_item(
    item: dict[str, Any],
    *,
    generated_at: str = "",
    time_window: str = "3d",
) -> dict[str, Any]:
    """Return a daily item with source tier and freshness fields attached."""
    row = dict(item)
    profile = classify_daily_source(row)
    freshness = normalize_daily_freshness(
        row.get("published_at") or row.get("date") or "",
        generated_at=generated_at,
        time_window=time_window,
        text=f"{row.get('title') or ''} {row.get('summary') or ''}",
    )
    row["source_profile"] = profile
    row["source_tier"] = profile["source_tier"]
    row["source_tier_label"] = profile["source_tier_label"]
    row["source_section"] = profile["section"]
    row["freshness"] = freshness["freshness"]
    row["freshness_label"] = freshness["freshness_label"]
    row["freshness_days"] = freshness["days"]
    row["freshness_in_window"] = freshness["in_window"]
    row["freshness_evidence"] = freshness["evidence"]
    row["risk_tags"] = _unique_strings(list(row.get("risk_tags") or []) + list(profile.get("risk_tags") or []))
    return row


def annotate_daily_items(
    items: list[dict[str, Any]],
    *,
    generated_at: str = "",
    time_window: str = "3d",
) -> list[dict[str, Any]]:
    return [annotate_daily_item(item, generated_at=generated_at, time_window=time_window) for item in items]


def classify_daily_source(item: dict[str, Any]) -> dict[str, Any]:
    """Classify one candidate into daily source tiers A-D."""
    url = str(item.get("url") or "")
    domain = daily_domain(url)
    card = dict(item.get("source_card") or {})
    if domain and not card:
        card = source_card_for_domain(domain).to_dict()
    role = str(item.get("evidence_role") or "")
    source = str(item.get("source") or "")
    origin = str(item.get("origin") or "")
    title_summary = f"{item.get('title') or ''} {item.get('summary') or ''}"
    risk_tags = _unique_strings(list(item.get("risk_tags") or []) + list(card.get("risk_tags") or []))

    soft = daily_is_soft_seo(item, domain=domain)
    brand_owned = daily_is_brand_owned(item, domain=domain)
    brand_community = daily_is_brand_owned_community(item, domain=domain)
    recognized_external = daily_is_recognized_external(item, domain=domain, source_card=card)
    trust = daily_is_trust_related(item, text=title_summary)

    if soft:
        tier = "D"
        section = "other"
        boundary = "弱 SEO、下载、镜像、标题党或软文聚合，只能作为候补线索。"
    elif trust:
        tier = "A" if role in OFFICIAL_ROLES or float(card.get("authority_score") or 0.0) >= 0.75 else "B"
        section = "trust"
        boundary = "安全、合规、隐私、数据或企业信任相关材料，需要保留风险语境。"
    elif brand_community:
        tier = "C"
        section = "community"
        boundary = "品牌自有社区公开样本，只能观察使用场景，不能外推整体口碑。"
    elif brand_owned or role in {"company_primary", "product_primary", "official_primary"}:
        tier = "A"
        section = "official"
        boundary = "官方或品牌自有口径，适合作为事实锚点，不代表外部评价。"
    elif role in OFFICIAL_ROLES or str(card.get("authority_role") or "") in {"government", "central_media", "local_official_media"}:
        tier = "A"
        section = "official"
        boundary = "一手、监管、官方或权威入口。"
    elif role in COMMUNITY_ROLES or _looks_like_community(domain, source, title_summary):
        tier = "C"
        section = "community"
        boundary = "社区/用户/开发者样本，只能代表局部公开讨论。"
    elif role in ECOSYSTEM_ROLES or origin.startswith("feeds:") or recognized_external:
        tier = "B"
        section = "ecosystem"
        boundary = "外部报道、产业媒体、垂直媒体或开发者材料。"
    else:
        tier = "B" if _looks_like_media_or_industry(source, card) else "D"
        section = "ecosystem" if tier == "B" else "other"
        boundary = "通用公开网页，引用前应回读原文确认。"

    if tier == "D":
        risk_tags = _unique_strings(risk_tags + ["weak_lead"])
    if brand_owned:
        risk_tags = _unique_strings(risk_tags + ["vendor_framing"])
    if brand_community:
        risk_tags = _unique_strings(risk_tags + ["vendor_moderation", "not_representative"])

    return {
        "domain": domain,
        "source_tier": tier,
        "source_tier_label": SOURCE_TIER_LABELS[tier],
        "section": section,
        "section_title": daily_section_title(section),
        "boundary": boundary,
        "is_soft_seo": soft,
        "is_brand_owned": brand_owned,
        "is_brand_owned_community": brand_community,
        "is_recognized_external": recognized_external,
        "is_trust_related": trust,
        "source_card": card,
        "authority_score": float(card.get("authority_score") or 0.0),
        "sample_value": float(card.get("sample_value") or 0.0),
        "freshness_value": float(card.get("freshness_value") or 0.0),
        "risk_tags": risk_tags,
    }


def normalize_daily_freshness(
    value: Any,
    *,
    generated_at: str = "",
    time_window: str = "3d",
    text: str = "",
) -> dict[str, Any]:
    """Normalize raw dates/snippets into daily freshness buckets."""
    window = normalize_daily_time_window(time_window)
    now = _parse_datetime(generated_at) or datetime.now(timezone.utc)
    raw = str(value or "").strip()
    parsed = _parse_datetime(raw) or _parse_datetime_from_text(text)
    evidence = raw
    if not parsed:
        lowered = str(text or "").lower()
        if any(term in lowered for term in ("今天", "今日", "刚刚", "小时前", "分钟前", "today")):
            return _freshness_payload("today", 0, True, evidence or "text:today")
        if any(term in lowered for term in ("昨天", "昨日", "1天前", "2天前", "3天前")):
            days = 1 if "昨天" in lowered or "昨日" in lowered or "1天前" in lowered else 3
            return _freshness_payload("recent_3d", days, _days_in_window(days, window), evidence or "text:recent")
        return _freshness_payload("unknown", None, window != "today", "")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    days = max((now.date() - parsed.astimezone(now.tzinfo or timezone.utc).date()).days, 0)
    if days == 0:
        bucket = "today"
    elif days <= 3:
        bucket = "recent_3d"
    elif days <= 7:
        bucket = "recent_7d"
    else:
        bucket = "background"
    return _freshness_payload(bucket, days, _days_in_window(days, window), evidence or parsed.isoformat())


def build_daily_source_health(
    items: list[dict[str, Any]],
    overflow_items: list[dict[str, Any]] | None = None,
    *,
    time_window: str = "3d",
) -> dict[str, Any]:
    """Summarize evidence quality for editorial self-checks."""
    pool = [dict(row) for row in items]
    overflow = [dict(row) for row in (overflow_items or [])]
    all_rows = pool + overflow
    tier_counts = _count(row.get("source_tier") or classify_daily_source(row)["source_tier"] for row in all_rows)
    main_tier_counts = _count(row.get("source_tier") or classify_daily_source(row)["source_tier"] for row in pool)
    freshness_counts = _count(row.get("freshness") or "unknown" for row in all_rows)
    main_freshness_counts = _count(row.get("freshness") or "unknown" for row in pool)
    section_counts = _count(row.get("source_section") or row.get("section") or daily_section_key(row) for row in pool)
    warnings: list[str] = []
    if main_tier_counts.get("D", 0):
        warnings.append("主正文仍含 D 层弱线索，发布前应降入候补线索池或补强来源。")
    if main_tier_counts.get("A", 0) and not main_tier_counts.get("B", 0):
        warnings.append("主正文缺少 B 层外部媒体/产业/开发者来源，不能代表全网情况。")
    if not main_freshness_counts.get("today", 0) and normalize_daily_time_window(time_window) in {"today", "24h"}:
        warnings.append("当前时间窗要求今天/24h，但主正文缺少明确今日证据。")
    unknown_count = main_freshness_counts.get("unknown", 0)
    if pool and unknown_count / max(len(pool), 1) >= 0.5:
        warnings.append("主正文时间未知占比偏高，避免使用“今天/最新”等强时间表述。")
    return {
        "tier_counts": tier_counts,
        "main_tier_counts": main_tier_counts,
        "freshness_counts": freshness_counts,
        "main_freshness_counts": main_freshness_counts,
        "section_counts": section_counts,
        "time_window": normalize_daily_time_window(time_window),
        "weak_lead_count": tier_counts.get("D", 0),
        "main_weak_lead_count": main_tier_counts.get("D", 0),
        "today_count": main_freshness_counts.get("today", 0),
        "unknown_time_count": unknown_count,
        "warnings": warnings,
    }


def daily_section_key(item: dict[str, Any]) -> str:
    profile = item.get("source_profile") if isinstance(item.get("source_profile"), dict) else {}
    if profile.get("section"):
        return str(profile["section"])
    return str(classify_daily_source(item).get("section") or "other")


def daily_section_title(key: str) -> str:
    return {
        "official": "一手动态",
        "ecosystem": "外部报道与行业观察",
        "community": "社区与样本",
        "trust": "风险与信任",
        "other": "其他线索",
    }.get(str(key or ""), "其他线索")


def daily_is_search_entrypoint(item: dict[str, Any]) -> bool:
    title = _compact_text(str(item.get("title") or ""))
    summary = _compact_text(str(item.get("summary") or ""))
    url = str(item.get("url") or "").lower()
    if "搜索" not in title and "search" not in url:
        return False
    return "入口" in summary or "sousuo" in url or "/search" in url


def daily_is_soft_seo(item: dict[str, Any], *, domain: str | None = None) -> bool:
    profile = item.get("source_profile") if isinstance(item.get("source_profile"), dict) else {}
    if profile.get("is_soft_seo") is True:
        return True
    title = str(item.get("title") or "").lower()
    url = str(item.get("url") or "")
    domain = domain if domain is not None else daily_domain(url)
    if domain and any(domain == blocked or domain.endswith(f".{blocked}") for blocked in SOFT_SEO_DOMAINS):
        return True
    if daily_is_brand_imitating_domain(domain):
        return True
    if daily_is_brand_owned(item, domain=domain):
        return False
    return any(term in title for term in SOFT_TITLE_TERMS)


def daily_is_recognized_external(
    item: dict[str, Any],
    *,
    domain: str | None = None,
    source_card: dict[str, Any] | None = None,
) -> bool:
    profile = item.get("source_profile") if isinstance(item.get("source_profile"), dict) else {}
    if profile.get("is_recognized_external") is True:
        return True
    domain = domain if domain is not None else daily_domain(str(item.get("url") or ""))
    source = str(item.get("source") or "")
    card = dict(source_card or item.get("source_card") or {})
    if domain and any(domain == known or domain.endswith(f".{known}") for known in RECOGNIZED_EXTERNAL_DOMAINS):
        return True
    source_type = str(card.get("source_type") or "")
    return any(term in f"{source} {source_type}" for term in ("科技", "商业", "产业", "媒体", "财经", "新闻", "开发者"))


def daily_is_brand_owned(item: dict[str, Any], *, domain: str | None = None) -> bool:
    profile = item.get("source_profile") if isinstance(item.get("source_profile"), dict) else {}
    if profile.get("is_brand_owned") is True:
        return True
    domain = domain if domain is not None else daily_domain(str(item.get("url") or ""))
    if not domain:
        return False
    return any(domain == known or domain.endswith(f".{known}") for known in KNOWN_WPS_OWNED_DOMAINS)


def daily_is_brand_owned_community(item: dict[str, Any], *, domain: str | None = None) -> bool:
    profile = item.get("source_profile") if isinstance(item.get("source_profile"), dict) else {}
    if profile.get("is_brand_owned_community") is True:
        return True
    domain = domain if domain is not None else daily_domain(str(item.get("url") or ""))
    if not domain:
        return False
    return any(domain == known or domain.endswith(f".{known}") for known in KNOWN_WPS_COMMUNITY_HOSTS)


def daily_is_brand_imitating_domain(domain: str | None) -> bool:
    value = str(domain or "").lower()
    if not value:
        return False
    if any(value == known or value.endswith(f".{known}") for known in KNOWN_WPS_OWNED_DOMAINS):
        return False
    return "wps" in value and any(term in value for term in ("download", "office", "jsbg", "wps"))


def daily_is_trust_related(item: dict[str, Any], *, text: str = "") -> bool:
    role = str(item.get("evidence_role") or "")
    url = str(item.get("url") or "").lower()
    haystack = f"{text} {url} {' '.join(str(tag) for tag in item.get('risk_tags') or [])}".lower()
    return role == "security_advisory" or any(term.lower() in haystack for term in TRUST_TERMS)


def daily_domain(url: str) -> str:
    clean = str(url or "").strip()
    if not clean:
        return ""
    try:
        parsed = urlsplit(clean)
    except ValueError:
        return ""
    return parsed.netloc.lower().split("@")[-1].split(":")[0]


def _freshness_payload(bucket: str, days: int | None, in_window: bool, evidence: str) -> dict[str, Any]:
    return {
        "freshness": bucket,
        "freshness_label": FRESHNESS_LABELS.get(bucket, bucket),
        "days": days,
        "in_window": bool(in_window),
        "evidence": evidence,
    }


def _days_in_window(days: int, window: str) -> bool:
    if window in {"today", "24h"}:
        return days == 0
    if window == "3d":
        return days <= 3
    if window == "7d":
        return days <= 7
    return days <= 3


def _parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    for candidate in (normalized, normalized[:19], normalized[:10]):
        try:
            parsed = datetime.fromisoformat(candidate)
            if len(candidate) == 10:
                parsed = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日", "%m月%d日"):
        try:
            candidate = raw[:10] if pattern in {"%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"} else raw
            parsed = datetime.strptime(candidate, pattern)
            if pattern == "%m月%d日":
                parsed = parsed.replace(year=datetime.now(timezone.utc).year)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return _parse_datetime_from_text(raw)


def _parse_datetime_from_text(text: str) -> datetime | None:
    raw = str(text or "")
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", raw)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None
    match = re.search(r"(\d{1,2})月(\d{1,2})日", raw)
    if match:
        month, day = (int(part) for part in match.groups())
        try:
            return datetime(datetime.now(timezone.utc).year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _looks_like_community(domain: str, source: str, text: str) -> bool:
    haystack = f"{domain} {source} {text}".lower()
    return any(
        term in haystack
        for term in ("zhihu.com", "csdn.net", "github.com", "v2ex.com", "bbs.", "forum.", "知乎", "社交", "社区", "论坛", "评论", "用户反馈")
    )


def _looks_like_media_or_industry(source: str, card: dict[str, Any]) -> bool:
    text = f"{source} {card.get('source_type') or ''} {card.get('authority_role') or ''}"
    return any(term in text for term in ("媒体", "财经", "科技", "商业", "产业", "开发者", "新闻", "研报", "垂类"))


def _count(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _compact_text(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").lower())


def _unique_strings(items: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
