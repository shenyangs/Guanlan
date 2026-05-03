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
    "academic": {
        "authority_role": "academic_index_or_publisher",
        "content_roles": ("publisher_guideline", "index_database", "scholarly_context"),
        "fit_tags": ("academic", "paper", "conference", "indexing", "publisher"),
        "risk_tags": ("paywall", "metadata_only", "version_sensitive"),
        "authority_score": 0.78,
        "sample_value": 0.22,
        "freshness_value": 0.46,
        "stability": "best_effort",
    },
    "university": {
        "authority_role": "university_official",
        "content_roles": ("faculty_profile", "admission_catalog", "department_page", "official_notice"),
        "fit_tags": ("university", "admission", "faculty", "advisor", "department", "program"),
        "risk_tags": ("page_fragmentation", "annual_policy_change", "site_search_needed"),
        "authority_score": 0.88,
        "sample_value": 0.12,
        "freshness_value": 0.5,
        "stability": "stable",
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
    "entertainment": {
        "authority_role": "culture_entertainment_source",
        "content_roles": ("platform_metric", "rating", "review", "box_office", "public_discussion"),
        "fit_tags": ("entertainment", "culture", "film", "music", "game", "reputation"),
        "risk_tags": ("promotion_bias", "fanwar_bias", "platform_framing", "not_representative"),
        "authority_score": 0.42,
        "sample_value": 0.78,
        "freshness_value": 0.75,
        "stability": "best_effort",
    },
    "global_entertainment": {
        "authority_role": "entertainment_trade_media",
        "content_roles": ("trade_report", "music_chart", "review", "celebrity_news", "public_context"),
        "fit_tags": ("entertainment", "hollywood", "music", "celebrity", "awards", "fresh"),
        "risk_tags": ("promotion_bias", "tabloid_rumor", "paywall", "source_bias"),
        "authority_score": 0.56,
        "sample_value": 0.42,
        "freshness_value": 0.84,
        "stability": "best_effort",
    },
    "jp_kr_entertainment": {
        "authority_role": "japan_korea_entertainment_source",
        "content_roles": ("translation_report", "chart_metric", "agency_context", "celebrity_news", "fan_discussion"),
        "fit_tags": ("entertainment", "kpop", "jpop", "kdrama", "jdrama", "anime", "fresh"),
        "risk_tags": ("translation_loss", "agency_framing", "rumor_tabloid", "fanwar_bias"),
        "authority_score": 0.5,
        "sample_value": 0.55,
        "freshness_value": 0.82,
        "stability": "best_effort",
    },
    "cybersecurity": {
        "authority_role": "security_authority",
        "content_roles": ("vulnerability_record", "security_advisory", "vendor_patch", "official_warning"),
        "fit_tags": ("security", "cve", "vulnerability", "fraud", "official", "fresh"),
        "risk_tags": ("time_sensitive", "exploit_risk", "vendor_scope"),
        "authority_score": 0.86,
        "sample_value": 0.28,
        "freshness_value": 0.9,
        "stability": "stable",
    },
    "sports": {
        "authority_role": "sports_source",
        "content_roles": ("official_stat", "sports_report", "transfer_report", "fan_discussion"),
        "fit_tags": ("sports", "match", "injury", "transfer", "fresh"),
        "risk_tags": ("rumor", "fan_bias", "time_sensitive"),
        "authority_score": 0.48,
        "sample_value": 0.58,
        "freshness_value": 0.88,
    },
    "weather_disaster": {
        "authority_role": "weather_disaster_authority",
        "content_roles": ("official_alert", "forecast_track", "disaster_notice", "public_safety"),
        "fit_tags": ("weather", "disaster", "alert", "official", "fresh"),
        "risk_tags": ("time_sensitive", "location_sensitive", "outdated_alert"),
        "authority_score": 0.92,
        "sample_value": 0.1,
        "freshness_value": 0.95,
        "stability": "stable",
    },
    "science": {
        "authority_role": "science_institution",
        "content_roles": ("institution_primary", "peer_review", "preprint", "science_news"),
        "fit_tags": ("science", "research", "space", "paper", "official"),
        "risk_tags": ("headline_hype", "preprint_uncertainty", "translation_loss"),
        "authority_score": 0.82,
        "sample_value": 0.18,
        "freshness_value": 0.62,
        "stability": "stable",
    },
    "career": {
        "authority_role": "career_market_source",
        "content_roles": ("job_posting", "salary_sample", "interview_sample", "company_context"),
        "fit_tags": ("career", "salary", "interview", "recruiting", "sample"),
        "risk_tags": ("sample_bias", "outdated_compensation", "self_selection"),
        "authority_score": 0.38,
        "sample_value": 0.8,
        "freshness_value": 0.7,
    },
    "podcast": {
        "authority_role": "podcast_catalog",
        "content_roles": ("episode_catalog", "show_metadata", "rss_feed", "listener_sample"),
        "fit_tags": ("podcast", "audio", "rss", "content_discovery"),
        "risk_tags": ("catalog_gap", "ranking_bias", "transcript_gap"),
        "authority_score": 0.42,
        "sample_value": 0.62,
        "freshness_value": 0.7,
    },
    "test_prep": {
        "authority_role": "exam_prep_source",
        "content_roles": ("exam_official", "prep_material", "candidate_sample", "training_context"),
        "fit_tags": ("education", "exam", "test_prep", "official", "sample"),
        "risk_tags": ("training_marketing", "leaked_material_claim", "outdated_policy"),
        "authority_score": 0.52,
        "sample_value": 0.55,
        "freshness_value": 0.6,
    },
    "global_official": {
        "authority_role": "public_institution",
        "content_roles": ("primary_source", "regulation", "standard", "public_data"),
        "fit_tags": ("policy", "regulation", "official", "data", "standards"),
        "risk_tags": ("legalese", "slow_update"),
        "authority_score": 0.94,
        "sample_value": 0.05,
        "freshness_value": 0.48,
        "stability": "stable",
    },
    "company_primary": {
        "authority_role": "company_primary",
        "content_roles": ("official_specs", "release_note", "pricing", "status", "company_statement"),
        "fit_tags": ("company", "product", "pricing", "release", "official", "tech"),
        "risk_tags": ("vendor_framing", "marketing_language"),
        "authority_score": 0.78,
        "sample_value": 0.12,
        "freshness_value": 0.72,
        "stability": "stable",
    },
    "developer": {
        "authority_role": "developer_source",
        "content_roles": ("source_code", "documentation", "issue", "release", "developer_discussion"),
        "fit_tags": ("tech", "developer", "opensource", "evidence_primary", "product_feedback"),
        "risk_tags": ("version_sensitive", "project_bias"),
        "authority_score": 0.66,
        "sample_value": 0.72,
        "freshness_value": 0.68,
        "stability": "stable",
    },
    "global_news": {
        "authority_role": "news_media",
        "content_roles": ("report", "timeline", "interview", "public_context"),
        "fit_tags": ("news", "industry", "policy", "company", "fresh"),
        "risk_tags": ("editorial_framing", "paywall", "source_bias"),
        "authority_score": 0.62,
        "sample_value": 0.24,
        "freshness_value": 0.82,
        "stability": "stable",
    },
    "industry_analysis": {
        "authority_role": "industry_analysis",
        "content_roles": ("analysis", "market_context", "forecast", "thesis"),
        "fit_tags": ("industry", "business", "strategy", "market", "company"),
        "risk_tags": ("opinionated", "paywall", "methodology_gap"),
        "authority_score": 0.5,
        "sample_value": 0.32,
        "freshness_value": 0.58,
    },
    "community_sample": {
        "authority_role": "community_platform",
        "content_roles": ("user_sample", "public_discussion", "developer_discussion", "commentary"),
        "fit_tags": ("reputation", "developer", "social", "sentiment", "product_feedback"),
        "risk_tags": ("sample_bias", "not_representative", "platform_framing"),
        "authority_score": 0.22,
        "sample_value": 0.9,
        "freshness_value": 0.78,
    },
    "market_review": {
        "authority_role": "review_platform",
        "content_roles": ("user_sample", "review", "buyer_feedback", "rating"),
        "fit_tags": ("reputation", "consumer", "saas", "purchase_advice", "product_feedback"),
        "risk_tags": ("sample_bias", "commercial_incentive", "review_manipulation"),
        "authority_score": 0.24,
        "sample_value": 0.82,
        "freshness_value": 0.62,
    },
}


_DOMAIN_OVERRIDES: dict[str, dict[str, Any]] = {
    "github.com": {
        "source_type": "英文开发者/开源",
        "scope_id": "developer",
        "authority_role": "code_host",
        "content_roles": ("source_code", "issue", "release", "discussion"),
        "fit_tags": ("tech", "developer", "opensource", "evidence_primary"),
        "risk_tags": ("project_bias", "version_sensitive"),
        "authority_score": 0.7,
        "sample_value": 0.7,
        "freshness_value": 0.7,
        "stability": "stable",
    },
    "docs.github.com": {
        "source_type": "英文开发者/开源",
        "scope_id": "developer",
        "authority_role": "developer_source",
        "content_roles": ("documentation", "official_specs", "technical_note"),
        "fit_tags": ("tech", "developer", "official", "documentation"),
        "authority_score": 0.82,
        "sample_value": 0.32,
        "stability": "stable",
    },
    "sec.gov": {
        "content_roles": ("primary_source", "filing", "regulation", "public_data"),
        "fit_tags": ("official", "finance", "company", "regulation"),
        "authority_score": 0.97,
    },
    "openai.com": {
        "content_roles": ("official_specs", "release_note", "pricing", "documentation", "company_statement"),
        "fit_tags": ("company", "product", "pricing", "release", "ai", "official"),
        "authority_score": 0.84,
        "freshness_value": 0.78,
    },
    "stackoverflow.com": {
        "content_roles": ("developer_discussion", "technical_note", "question_answer"),
        "fit_tags": ("tech", "developer", "practice"),
        "risk_tags": ("version_sensitive", "answer_age", "sample_bias"),
    },
    "reddit.com": {
        "content_roles": ("user_sample", "public_discussion", "commentary"),
        "fit_tags": ("reputation", "social", "consumer", "developer"),
        "risk_tags": ("sample_bias", "not_representative", "platform_framing"),
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
        "fit_tags": ("video", "reputation", "tech", "consumer", "entertainment"),
        "risk_tags": ("creator_bias", "sample_bias"),
    },
    "douban.com": {
        "source_type": "文娱/内容平台",
        "scope_id": "entertainment",
        "authority_role": "culture_entertainment_source",
        "content_roles": ("rating", "review", "user_sample", "catalog_metadata"),
        "fit_tags": ("entertainment", "film", "book", "music", "reputation"),
        "risk_tags": ("sample_bias", "rating_manipulation", "not_representative"),
        "authority_score": 0.36,
        "sample_value": 0.86,
        "freshness_value": 0.62,
    },
    "maoyan.com": {
        "source_type": "文娱/内容平台",
        "scope_id": "entertainment",
        "authority_role": "ticketing_platform",
        "content_roles": ("box_office", "platform_metric", "rating", "release_schedule"),
        "fit_tags": ("entertainment", "film", "box_office", "platform_data"),
        "risk_tags": ("platform_framing", "commercial_incentive", "not_representative"),
        "authority_score": 0.46,
        "sample_value": 0.74,
        "freshness_value": 0.88,
    },
    "piaofang.maoyan.com": {
        "source_type": "文娱/内容平台",
        "scope_id": "entertainment",
        "authority_role": "ticketing_platform",
        "content_roles": ("box_office", "platform_metric", "release_schedule"),
        "fit_tags": ("entertainment", "film", "box_office", "fresh"),
        "risk_tags": ("platform_framing", "commercial_incentive"),
        "authority_score": 0.5,
        "sample_value": 0.68,
        "freshness_value": 0.9,
    },
    "taptap.cn": {
        "source_type": "文娱/内容平台",
        "scope_id": "entertainment",
        "authority_role": "game_platform",
        "content_roles": ("rating", "review", "user_sample", "game_catalog"),
        "fit_tags": ("entertainment", "game", "reputation", "consumer"),
        "risk_tags": ("sample_bias", "platform_framing", "review_manipulation"),
        "authority_score": 0.34,
        "sample_value": 0.82,
        "freshness_value": 0.72,
    },
    "variety.com": {
        "content_roles": ("trade_report", "industry_report", "review", "awards_context"),
        "fit_tags": ("hollywood", "film", "tv", "industry", "awards"),
        "authority_score": 0.64,
        "sample_value": 0.3,
    },
    "deadline.com": {
        "content_roles": ("trade_report", "breaking_news", "box_office", "casting_report"),
        "fit_tags": ("hollywood", "film", "tv", "industry", "fresh"),
        "authority_score": 0.64,
        "sample_value": 0.3,
    },
    "hollywoodreporter.com": {
        "content_roles": ("trade_report", "review", "awards_context", "industry_report"),
        "fit_tags": ("hollywood", "film", "tv", "awards", "industry"),
        "authority_score": 0.62,
        "sample_value": 0.32,
    },
    "billboard.com": {
        "content_roles": ("music_chart", "music_news", "industry_report", "artist_interview"),
        "fit_tags": ("music", "chart", "pop", "kpop", "industry"),
        "authority_score": 0.66,
        "sample_value": 0.34,
    },
    "grammy.com": {
        "content_roles": ("award_primary", "music_news", "artist_profile"),
        "fit_tags": ("music", "awards", "official", "grammy"),
        "authority_score": 0.76,
        "sample_value": 0.18,
    },
    "officialcharts.com": {
        "content_roles": ("chart_metric", "music_chart", "release_context"),
        "fit_tags": ("music", "chart", "uk", "official"),
        "authority_score": 0.74,
        "sample_value": 0.22,
    },
    "soompi.com": {
        "content_roles": ("translation_report", "k_pop_news", "k_drama_news", "celebrity_news"),
        "fit_tags": ("kpop", "kdrama", "korean_entertainment", "translation"),
        "risk_tags": ("translation_layer", "agency_framing", "fanwar_bias"),
        "authority_score": 0.54,
        "sample_value": 0.58,
    },
    "oricon.co.jp": {
        "content_roles": ("chart_metric", "j_pop_news", "celebrity_news", "release_context"),
        "fit_tags": ("jpop", "japan_entertainment", "chart", "official_metric"),
        "authority_score": 0.64,
        "sample_value": 0.38,
    },
    "natalie.mu": {
        "content_roles": ("music_news", "comic_news", "stage_news", "release_context"),
        "fit_tags": ("jpop", "anime", "manga", "stage", "japan_entertainment"),
        "authority_score": 0.58,
        "sample_value": 0.42,
    },
    "allkpop.com": {
        "content_roles": ("k_pop_news", "celebrity_news", "fan_discussion"),
        "risk_tags": ("clickbait", "rumor_tabloid", "translation_layer", "fanwar_bias"),
        "authority_score": 0.34,
        "sample_value": 0.66,
    },
    "koreaboo.com": {
        "content_roles": ("k_pop_news", "celebrity_news", "fan_discussion"),
        "risk_tags": ("clickbait", "rumor_tabloid", "translation_layer", "fanwar_bias"),
        "authority_score": 0.3,
        "sample_value": 0.68,
    },
    "csdn.net": {
        "risk_tags": ("seo_content", "quality_variance", "version_sensitive"),
        "authority_score": 0.32,
    },
    "engineeringvillage.com": {
        "content_roles": ("index_database", "primary_source", "scholarly_context"),
        "fit_tags": ("academic", "ei", "compendex", "indexing", "official"),
        "risk_tags": ("login_wall", "metadata_only"),
        "authority_score": 0.9,
    },
    "elsevier.com": {
        "content_roles": ("publisher_guideline", "index_database", "official_context"),
        "fit_tags": ("academic", "ei", "scopus", "publisher", "official"),
        "authority_score": 0.86,
    },
    "tsinghua.edu.cn": {
        "content_roles": ("department_page", "faculty_profile", "official_notice", "admission_catalog"),
        "fit_tags": ("university", "admission", "faculty", "department", "official"),
        "authority_score": 0.92,
    },
    "cs.tsinghua.edu.cn": {
        "content_roles": ("department_page", "faculty_profile", "program_info"),
        "fit_tags": ("university", "computer_science", "faculty", "department", "official"),
        "authority_score": 0.93,
    },
    "yz.tsinghua.edu.cn": {
        "content_roles": ("admission_catalog", "official_notice", "program_info"),
        "fit_tags": ("university", "graduate_admission", "official"),
        "authority_score": 0.94,
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
    for candidate, override in sorted(_DOMAIN_OVERRIDES.items(), key=lambda row: len(row[0]), reverse=True):
        if domain == candidate or domain.endswith("." + candidate):
            return dict(override)
    return {}
