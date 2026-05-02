# -*- coding: utf-8 -*-
"""Structured source taxonomy for Guanlan routing.

This module deliberately separates authority, fit, sample value, stability, and
risk. A source can be weak for official facts while still useful as a public
discussion sample.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from guanlan.search_sources import SEARCH_SCOPES, classify_domain


@dataclass(frozen=True)
class SourceCard:
    domain: str
    source_type: str = "通用网页"
    scope_id: str = ""
    authority_role: str = "open_web"
    content_roles: tuple[str, ...] = ("unknown",)
    fit_tags: tuple[str, ...] = ()
    risk_tags: tuple[str, ...] = ()
    access: str = "public_html"
    stability: str = "best_effort"
    authority_score: float = 0.2
    sample_value: float = 0.2
    freshness_value: float = 0.2
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SCOPE_DEFAULTS: dict[str, dict[str, Any]] = {
    "party_central": {
        "authority_role": "central_media",
        "content_roles": ("authoritative_report", "official_narrative"),
        "fit_tags": ("policy", "official", "macro", "news"),
        "risk_tags": ("editorial_framing",),
        "authority_score": 0.88,
        "sample_value": 0.18,
        "freshness_value": 0.62,
        "stability": "stable",
    },
    "gov": {
        "authority_role": "government",
        "content_roles": ("primary_source", "notice", "regulation", "data"),
        "fit_tags": ("policy", "official", "regulation", "data"),
        "risk_tags": ("bureaucratic_language", "slow_update"),
        "authority_score": 0.96,
        "sample_value": 0.05,
        "freshness_value": 0.45,
        "stability": "stable",
    },
    "local_official": {
        "authority_role": "local_official_media",
        "content_roles": ("local_report", "policy_context", "official_narrative"),
        "fit_tags": ("local", "policy", "regional", "news"),
        "risk_tags": ("local_framing",),
        "authority_score": 0.74,
        "sample_value": 0.2,
        "freshness_value": 0.58,
        "stability": "stable",
    },
    "business": {
        "authority_role": "industry_media",
        "content_roles": ("report", "analysis", "interview", "commercial_context"),
        "fit_tags": ("industry", "business", "startup", "company", "commerce"),
        "risk_tags": ("soft_article", "sponsored_content", "source_bias"),
        "authority_score": 0.5,
        "sample_value": 0.35,
        "freshness_value": 0.68,
    },
    "ecommerce": {
        "authority_role": "vertical_media",
        "content_roles": ("vertical_report", "analysis", "case"),
        "fit_tags": ("ecommerce", "retail", "consumer", "cross_border", "brand"),
        "risk_tags": ("vendor_bias", "soft_article"),
        "authority_score": 0.48,
        "sample_value": 0.42,
        "freshness_value": 0.65,
    },
    "tech_dev": {
        "authority_role": "developer_community",
        "content_roles": ("practice", "discussion", "technical_note", "issue"),
        "fit_tags": ("tech", "developer", "opensource", "engineering", "product_feedback"),
        "risk_tags": ("anecdotal", "version_sensitive"),
        "authority_score": 0.44,
        "sample_value": 0.72,
        "freshness_value": 0.62,
    },
    "finance": {
        "authority_role": "finance_media",
        "content_roles": ("market_news", "analysis", "filing_context", "quote"),
        "fit_tags": ("finance", "market", "company", "macro", "investment_risk"),
        "risk_tags": ("market_opinion", "time_sensitive"),
        "authority_score": 0.6,
        "sample_value": 0.28,
        "freshness_value": 0.82,
    },
    "social_web": {
        "authority_role": "social_platform",
        "content_roles": ("user_sample", "public_discussion", "commentary"),
        "fit_tags": ("reputation", "sentiment", "consumer", "social", "purchase_advice"),
        "risk_tags": ("sample_bias", "login_wall", "platform_framing", "not_representative"),
        "authority_score": 0.24,
        "sample_value": 0.92,
        "freshness_value": 0.78,
        "stability": "best_effort",
    },
}


_DOMAIN_OVERRIDES: dict[str, dict[str, Any]] = {
    "github.com": {
        "source_type": "代码/开源平台",
        "scope_id": "tech_dev",
        "authority_role": "code_host",
        "content_roles": ("source_code", "issue", "release", "discussion"),
        "fit_tags": ("tech", "developer", "opensource", "evidence_primary"),
        "risk_tags": ("project_bias", "version_sensitive"),
        "authority_score": 0.7,
        "sample_value": 0.7,
        "freshness_value": 0.7,
        "stability": "stable",
    },
    "zhihu.com": {
        "content_roles": ("question_answer", "public_discussion", "user_sample"),
        "fit_tags": ("reputation", "explanation", "consumer", "decision"),
        "risk_tags": ("sample_bias", "opinionated", "login_wall"),
    },
    "weibo.com": {
        "content_roles": ("social_post", "hot_discussion", "user_sample"),
        "fit_tags": ("hot", "sentiment", "social", "reputation"),
        "risk_tags": ("sample_bias", "platform_framing", "fast_changing"),
    },
    "xiaohongshu.com": {
        "content_roles": ("consumer_note", "lifestyle_review", "user_sample"),
        "fit_tags": ("consumer", "purchase_advice", "reputation", "lifestyle"),
        "risk_tags": ("sample_bias", "commercial_content", "login_wall"),
    },
    "bilibili.com": {
        "content_roles": ("video", "review", "community_discussion"),
        "fit_tags": ("video", "reputation", "tech", "consumer"),
        "risk_tags": ("creator_bias", "sample_bias"),
    },
    "csdn.net": {
        "risk_tags": ("seo_content", "quality_variance", "version_sensitive"),
        "authority_score": 0.32,
    },
    "caixin.com": {
        "authority_score": 0.72,
        "risk_tags": ("paywall", "time_sensitive"),
    },
}


def source_card_for_domain(domain: str, preferred_scope: str | None = None) -> SourceCard:
    """Return a structured source card for a domain."""
    normalized = normalize_domain(domain)
    classified = classify_domain(normalized, preferred_scope=preferred_scope)
    scope_id = str(classified.get("matched_scope") or "")
    defaults = dict(_SCOPE_DEFAULTS.get(scope_id, {}))
    override = _domain_override(normalized)
    merged = {
        "domain": normalized,
        "source_type": classified.get("source_type", "通用网页"),
        "scope_id": scope_id,
        **defaults,
        **override,
    }
    return SourceCard(
        domain=merged["domain"],
        source_type=merged.get("source_type", "通用网页"),
        scope_id=merged.get("scope_id", scope_id),
        authority_role=merged.get("authority_role", "open_web"),
        content_roles=tuple(merged.get("content_roles", ("unknown",))),
        fit_tags=tuple(merged.get("fit_tags", ())),
        risk_tags=tuple(merged.get("risk_tags", ())),
        access=merged.get("access", "public_html"),
        stability=merged.get("stability", "best_effort"),
        authority_score=float(merged.get("authority_score", 0.2)),
        sample_value=float(merged.get("sample_value", 0.2)),
        freshness_value=float(merged.get("freshness_value", 0.2)),
        notes=merged.get("notes", ""),
    )


def scope_source_cards(scope_id: str) -> list[SourceCard]:
    """Return source cards for domains in a scope."""
    scope = SEARCH_SCOPES.get(scope_id)
    if not scope:
        return []
    return [source_card_for_domain(domain, preferred_scope=scope_id) for domain in scope.domains]


def normalize_domain(domain: str) -> str:
    value = (domain or "").strip().lower()
    value = value.removeprefix("https://").removeprefix("http://")
    value = value.removeprefix("www.")
    return value.split("/", 1)[0]


def _domain_override(domain: str) -> dict[str, Any]:
    for candidate, override in _DOMAIN_OVERRIDES.items():
        if domain == candidate or domain.endswith("." + candidate):
            return dict(override)
    return {}
