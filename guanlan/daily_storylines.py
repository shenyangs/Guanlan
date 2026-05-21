# -*- coding: utf-8 -*-
"""Storyline clustering and editorial decisions for Guanlan daily reports."""

from __future__ import annotations

import re
from typing import Any

from guanlan.daily_quality import daily_domain, daily_section_title

FRESHNESS_RANK = {
    "today": 0,
    "recent_3d": 1,
    "recent_7d": 2,
    "unknown": 3,
    "background": 4,
}

RISK_TERMS = {
    "privacy": ("隐私", "数据", "训练", "权限", "privacy", "data"),
    "security": ("安全", "漏洞", "攻击", "泄露", "security", "cve"),
    "compliance": ("合规", "监管", "版权", "审计", "compliance", "copyright"),
    "trust": ("信任", "采购", "企业", "私有化", "信创", "trust"),
    "reputation": ("投诉", "吐槽", "差评", "争议", "道歉", "舆情"),
}


def build_daily_storylines(
    items: list[dict[str, Any]],
    overflow_items: list[dict[str, Any]] | None = None,
    *,
    query: str = "",
    edition: str = "brand",
    time_window: str = "3d",
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Cluster daily items into event/storyline units."""
    overflow = overflow_items or []
    groups: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}

    for row in items:
        key = _storyline_key(row, query=query)
        group = by_key.get(key)
        if not group:
            group = {"key": key, "items": [], "overflow": []}
            by_key[key] = group
            groups.append(group)
        group["items"].append(dict(row))

    for row in overflow:
        key = _storyline_key(row, query=query)
        group = by_key.get(key)
        if not group:
            group = {"key": key, "items": [], "overflow": []}
            by_key[key] = group
            groups.append(group)
        group["overflow"].append(dict(row))

    storylines: list[dict[str, Any]] = []
    for group in groups:
        primary_items = group["items"] or group["overflow"]
        if not primary_items:
            continue
        evidence_items = _compact_evidence_items(primary_items, max_items=5)
        source_spread = _source_spread(primary_items + group["overflow"])
        section = _dominant_section(primary_items)
        headline = _best_headline(primary_items)
        risk_flags = _risk_flags(primary_items + group["overflow"])
        freshness = _best_freshness(primary_items)
        confidence = _confidence(source_spread, primary_items, freshness=freshness)
        action = _recommended_action(section=section, risk_flags=risk_flags, confidence=confidence, freshness=freshness, edition=edition)
        risk_level = _risk_level(section=section, risk_flags=risk_flags, source_spread=source_spread)
        story_id = _story_id(group["key"], headline)
        storylines.append(
            {
                "id": story_id,
                "cluster_key": group["key"],
                "headline": headline,
                "what_happened": _what_happened(primary_items, section=section),
                "why_it_matters": _why_it_matters(primary_items, section=section, edition=edition),
                "freshness": freshness,
                "freshness_label": _freshness_label(freshness),
                "evidence_items": evidence_items,
                "overflow_items": _compact_evidence_items(group["overflow"], max_items=4),
                "source_spread": source_spread,
                "risk_flags": risk_flags,
                "confidence": confidence,
                "recommended_action": action,
                "risk_level": risk_level,
                "teams": _recommended_teams(section=section, risk_flags=risk_flags, edition=edition),
                "storyline_type": section,
                "storyline_type_label": daily_section_title(section),
                "time_window": time_window,
            }
        )
    storylines.sort(key=_storyline_sort_key)
    return storylines[: max(limit, 1)]


def build_daily_storyline_highlights(storylines: list[dict[str, Any]], *, source_health: dict[str, Any] | None = None) -> list[str]:
    """Build human-readable editorial judgments from storylines."""
    bullets: list[str] = []
    for story in storylines[:4]:
        headline = str(story.get("headline") or "")
        spread = story.get("source_spread") or {}
        tier_counts = spread.get("tier_counts") or {}
        fact_anchor = _first_evidence_title(story)
        boundary = _storyline_boundary(story)
        bullets.append(
            f"{headline}：{fact_anchor}。来源层分布 A/B/C/D={tier_counts.get('A', 0)}/"
            f"{tier_counts.get('B', 0)}/{tier_counts.get('C', 0)}/{tier_counts.get('D', 0)}；{boundary}"
        )
    health = source_health or {}
    for warning in health.get("warnings") or []:
        bullets.append(str(warning))
    return bullets[:5]


def build_daily_editorial_decisions(storylines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return action cards for PR/market/reputation teams."""
    decisions: list[dict[str, Any]] = []
    for story in storylines:
        decisions.append(
            {
                "storyline_id": story.get("id", ""),
                "headline": story.get("headline", ""),
                "recommended_action": story.get("recommended_action", "深写观察"),
                "risk_level": story.get("risk_level", "low"),
                "teams": story.get("teams", []),
                "confidence": story.get("confidence", "medium"),
                "reason": _decision_reason(story),
            }
        )
    return decisions


def _storyline_key(item: dict[str, Any], *, query: str = "") -> str:
    url = str(item.get("url") or "")
    domain = daily_domain(url)
    title = str(item.get("title") or "")
    compact_title = _compact_text(title)
    query_tokens = set(_tokens(query))
    tokens = [
        token
        for token in _tokens(title)
        if token not in query_tokens and token not in {"今天", "今日", "最新", "2025", "2026", "wps", "ai"}
    ]
    if len(tokens) >= 2:
        return "t:" + "-".join(tokens[:4])
    if compact_title:
        return "t:" + compact_title[:32]
    if domain:
        return "d:" + domain
    return "unknown"


def _story_id(key: str, headline: str) -> str:
    base = _compact_text(key or headline)[:40] or "daily-story"
    return f"daily-{base}"


def _compact_evidence_items(items: list[dict[str, Any]], *, max_items: int) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for row in items[:max_items]:
        evidence.append(
            {
                "title": str(row.get("title") or ""),
                "url": str(row.get("url") or ""),
                "source": str(row.get("source") or ""),
                "origin": str(row.get("origin") or ""),
                "source_tier": str(row.get("source_tier") or ""),
                "source_tier_label": str(row.get("source_tier_label") or ""),
                "section": str(row.get("source_section") or row.get("section") or ""),
                "evidence_role": str(row.get("evidence_role") or ""),
                "freshness": str(row.get("freshness") or "unknown"),
                "freshness_label": str(row.get("freshness_label") or ""),
                "summary": str(row.get("summary") or "")[:240],
            }
        )
    return evidence


def _source_spread(items: list[dict[str, Any]]) -> dict[str, Any]:
    domains: dict[str, int] = {}
    tiers: dict[str, int] = {}
    sections: dict[str, int] = {}
    origins: dict[str, int] = {}
    for row in items:
        domain = daily_domain(str(row.get("url") or ""))
        tier = str(row.get("source_tier") or "unknown")
        section = str(row.get("source_section") or row.get("section") or "other")
        origin = str(row.get("origin") or "")
        if domain:
            domains[domain] = domains.get(domain, 0) + 1
        if tier:
            tiers[tier] = tiers.get(tier, 0) + 1
        if section:
            sections[section] = sections.get(section, 0) + 1
        if origin:
            origins[origin] = origins.get(origin, 0) + 1
    return {
        "domain_count": len(domains),
        "domains": dict(sorted(domains.items(), key=lambda item: (-item[1], item[0]))),
        "tier_counts": dict(sorted(tiers.items(), key=lambda item: item[0])),
        "section_counts": dict(sorted(sections.items(), key=lambda item: (-item[1], item[0]))),
        "origin_counts": dict(sorted(origins.items(), key=lambda item: (-item[1], item[0]))),
    }


def _dominant_section(items: list[dict[str, Any]]) -> str:
    order = {"trust": 0, "ecosystem": 1, "community": 2, "official": 3, "other": 4}
    counts: dict[str, int] = {}
    for row in items:
        section = str(row.get("source_section") or row.get("section") or "other")
        counts[section] = counts.get(section, 0) + 1
    if not counts:
        return "other"
    return sorted(counts, key=lambda key: (-counts[key], order.get(key, 9), key))[0]


def _best_headline(items: list[dict[str, Any]]) -> str:
    candidates = sorted(
        items,
        key=lambda row: (
            str(row.get("source_tier") or "D") == "D",
            -float(row.get("daily_score") or 0.0),
            len(str(row.get("title") or "")),
        ),
    )
    return str((candidates[0] if candidates else {}).get("title") or "未命名主线")


def _what_happened(items: list[dict[str, Any]], *, section: str) -> str:
    row = items[0] if items else {}
    summary = str(row.get("summary") or "").strip()
    title = str(row.get("title") or "").strip()
    source = str(row.get("source") or "").strip()
    text = summary if len(summary) > len(title) else title
    text = _shorten(text, 120)
    if source:
        return f"{text}（{source}）"
    return text or daily_section_title(section)


def _why_it_matters(items: list[dict[str, Any]], *, section: str, edition: str) -> str:
    if section == "official":
        return "这是可核验的一手口径，适合先确认发布动作、产品能力和官方边界。"
    if section == "ecosystem":
        return "这是官方之外的媒体、产业或开发者视角，可用于判断外部关注点和行业语境。"
    if section == "community":
        return "这是公开用户/社区样本，适合发现真实使用问题、口碑线索和传播素材，但不能外推总体。"
    if section == "trust":
        return "这条主线涉及安全、合规、隐私、数据或企业采购信任，是品牌和舆情团队需要单独跟进的风险面。"
    if edition == "market":
        return "这条线索可作为市场选题补充，但需要补强来源后再进入正文。"
    return "这是候补线索，适合做后续补证或选题扩展。"


def _best_freshness(items: list[dict[str, Any]]) -> str:
    freshnesses = [str(row.get("freshness") or "unknown") for row in items]
    return sorted(freshnesses or ["unknown"], key=lambda value: FRESHNESS_RANK.get(value, 9))[0]


def _freshness_label(value: str) -> str:
    return {
        "today": "今天",
        "recent_3d": "近 3 天",
        "recent_7d": "近 7 天",
        "background": "背景资料",
        "unknown": "时间未知",
    }.get(value, value)


def _risk_flags(items: list[dict[str, Any]]) -> list[str]:
    parts: list[str] = []
    for row in items:
        parts.extend(
            [
                " ".join(str(tag) for tag in row.get("risk_tags") or []),
                str(row.get("title") or ""),
                str(row.get("summary") or ""),
            ]
        )
    text = " ".join(parts).lower()
    flags: list[str] = []
    for flag, terms in RISK_TERMS.items():
        if any(term.lower() in text for term in terms):
            flags.append(flag)
    if any(str(row.get("source_tier") or "") == "D" for row in items):
        flags.append("weak_lead")
    return _unique(flags)


def _confidence(source_spread: dict[str, Any], items: list[dict[str, Any]], *, freshness: str) -> str:
    tier_counts = source_spread.get("tier_counts") or {}
    strong = int(tier_counts.get("A", 0)) + int(tier_counts.get("B", 0))
    weak = int(tier_counts.get("D", 0))
    if strong >= 2 and weak == 0 and freshness in {"today", "recent_3d", "recent_7d"}:
        return "high"
    if strong >= 1 and weak < max(len(items), 1):
        return "medium"
    return "low"


def _recommended_action(*, section: str, risk_flags: list[str], confidence: str, freshness: str, edition: str) -> str:
    if set(risk_flags) & {"privacy", "security", "compliance", "trust", "reputation"}:
        return "立即跟进" if freshness in {"today", "recent_3d"} else "深写观察"
    if section == "community":
        return "社交传播" if confidence in {"high", "medium"} else "深写观察"
    if section == "ecosystem" and confidence in {"high", "medium"}:
        return "深写观察"
    if section == "official" and edition in {"brand", "market"}:
        return "深写观察"
    return "暂不动作"


def _risk_level(*, section: str, risk_flags: list[str], source_spread: dict[str, Any]) -> str:
    if set(risk_flags) & {"privacy", "security", "compliance", "reputation"}:
        return "high"
    if section == "trust" or source_spread.get("tier_counts", {}).get("D", 0):
        return "medium"
    return "low"


def _recommended_teams(*, section: str, risk_flags: list[str], edition: str) -> list[str]:
    teams = ["PR"]
    if edition == "market" or section in {"ecosystem", "official"}:
        teams.append("市场")
    if section == "community":
        teams.extend(["舆情", "产品市场"])
    if set(risk_flags) & {"privacy", "security", "compliance", "trust", "reputation"} or section == "trust":
        teams.extend(["舆情", "产品市场"])
    if section == "official":
        teams.append("销售支持")
    return _unique(teams)


def _storyline_sort_key(story: dict[str, Any]) -> tuple[int, int, int, str]:
    risk_rank = {"high": 0, "medium": 1, "low": 2}.get(str(story.get("risk_level") or "low"), 2)
    freshness_rank = FRESHNESS_RANK.get(str(story.get("freshness") or "unknown"), 9)
    section_rank = {"trust": 0, "ecosystem": 1, "community": 2, "official": 3, "other": 4}.get(str(story.get("storyline_type") or ""), 9)
    return (risk_rank, freshness_rank, section_rank, str(story.get("headline") or ""))


def _first_evidence_title(story: dict[str, Any]) -> str:
    evidence = story.get("evidence_items") or []
    if not evidence:
        return str(story.get("what_happened") or "")
    row = evidence[0]
    source = str(row.get("source") or "")
    title = _shorten(str(row.get("title") or ""), 72)
    return f"{title}（{source}）" if source else title


def _storyline_boundary(story: dict[str, Any]) -> str:
    confidence = str(story.get("confidence") or "medium")
    freshness = str(story.get("freshness_label") or story.get("freshness") or "时间未知")
    if confidence == "low":
        return f"证据强度偏低，当前只能作为线索；时间层为{freshness}。"
    return f"当前可作为日报主线，但结论需保留来源边界；时间层为{freshness}。"


def _decision_reason(story: dict[str, Any]) -> str:
    action = str(story.get("recommended_action") or "")
    if action == "立即跟进":
        return "涉及风险/信任或高敏感议题，适合当天核验、补证并同步相关团队。"
    if action == "社交传播":
        return "有社区或用户样本，适合提炼使用场景、反馈和传播素材。"
    if action == "深写观察":
        return "已有可用事实锚点，但仍需要代表原文和更多外部来源支撑成稿。"
    return "来源强度或时间证据不足，先保留在观察池。"


def _tokens(text: str) -> list[str]:
    raw = str(text or "")
    parts = re.split(r"[\s/,_:+|｜-]+", raw)
    tokens: list[str] = []
    for part in parts:
        clean = _compact_text(part)
        if len(clean) >= 2:
            tokens.append(clean)
    if not tokens:
        compact = _compact_text(raw)
        tokens = [compact[i : i + 4] for i in range(0, min(len(compact), 24), 4) if len(compact[i : i + 4]) >= 2]
    return _unique(tokens)


def _compact_text(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").lower())


def _shorten(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip(" ，。")
    if len(clean) <= limit:
        return clean
    return clean[: max(limit - 2, 1)].rstrip() + "..."


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
