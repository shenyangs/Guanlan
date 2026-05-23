# -*- coding: utf-8 -*-
"""Shadow evidence-selection diagnostics for Guanlan search results.

This module intentionally does not mutate the search output. It mirrors the
candidate-pipeline shape that a future Evidence Mixer can use, while keeping the
current search path fail-open.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

_POSITIVE_SCORE_PARTS = {
    "source_credibility",
    "authority_fit",
    "sample_fit",
    "freshness_fit",
    "intent_fit",
    "source_quality",
    "content_length",
    "keyword_match",
    "backend_priority",
    "recency_boost",
    "time_constraint_fit",
    "entity_match",
    "cjk_group_fit",
}

_PENALTY_SCORE_PARTS = {
    "ad_penalty",
    "intent_mismatch_penalty",
    "language_mismatch_penalty",
    "source_risk_penalty",
    "entity_mismatch_penalty",
    "cjk_group_mismatch_penalty",
    "semantic_noise_penalty",
    "stale_penalty",
    "time_constraint_penalty",
}

_HIGH_RISK_TAGS = {
    "soft_article",
    "sponsored_content",
    "seo_content",
    "commercial_content",
    "login_wall",
}

_VALID_MODES = {"off", "shadow", "assist"}

_STRONG_EVIDENCE_ROLES = {
    "official_primary",
    "official_alert",
    "company_primary",
    "company_filing",
    "database_official",
    "standard_original",
    "security_advisory",
    "vendor_patch",
    "vulnerability_record",
    "forecast_track",
}


@dataclass
class EvidenceCandidate:
    """A compact, serializable view of a search result as evidence."""

    index: int
    rank: int
    title: str
    url: str
    domain: str
    source_type: str
    evidence_role: str
    search_score: float
    evidence_score: float
    reasons: list[str] = field(default_factory=list)
    penalties: list[str] = field(default_factory=list)
    shadow_filter_reasons: list[str] = field(default_factory=list)

    def sample(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "source_type": self.source_type,
            "evidence_role": self.evidence_role,
            "search_score": round(self.search_score, 3),
            "evidence_score": round(self.evidence_score, 3),
            "reasons": list(self.reasons[:4]),
            "penalties": list(self.penalties[:4]),
            "shadow_filter_reasons": list(self.shadow_filter_reasons[:4]),
        }


def build_shadow_evidence_pipeline(
    results: list[dict[str, Any]],
    *,
    query: str,
    route_plan: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
    limit: int = 80,
    site_filter: dict[str, Any] | None = None,
    time_constraint: dict[str, Any] | None = None,
    target_size: int | None = None,
    mode: str = "shadow",
) -> dict[str, Any]:
    """Return fail-open Evidence Mixer diagnostics without changing results."""

    mode = normalize_evidence_mode(mode)
    if mode == "off":
        return build_disabled_evidence_pipeline(query=query, reason="mode_off")
    route_plan = route_plan or {}
    quality = quality or {}
    site_filter = site_filter or {"enabled": False}
    time_constraint = time_constraint or {"enabled": False}
    limit = max(int(limit or 0), 1)
    candidates = _hydrate_candidates(results)
    stage_counts: dict[str, int] = {
        "source": len(results),
        "hydrated": len(candidates),
        "shadow_filtered": 0,
        "selected": 0,
        "overflow": 0,
    }
    if not candidates:
        gain_estimate = _empty_gain_estimate()
        return {
            "enabled": True,
            "mode": mode,
            "fail_open": True,
            "mutates_output": False,
            "status": "empty_input",
            "query": query,
            "candidate_count": 0,
            "selected_count": 0,
            "overflow_count": 0,
            "shadow_filtered_count": 0,
            "fallback_used": False,
            "fallback_reason": "",
            "stage_counts": stage_counts,
            "selected_evidence": [],
            "overflow_candidates": [],
            "shadow_filtered_candidates": [],
            "warnings": [
                "Evidence Mixer shadow mode saw no candidates from the existing search path."
            ],
            "gain_estimate": gain_estimate,
            "agent_guidance": _agent_guidance(
                mode=mode,
                gain=gain_estimate,
                fallback_reason="",
            ),
            "boundary": _boundary(),
        }

    target = _target_size(len(candidates), limit=limit, target_size=target_size)
    selected, overflow, fallback_reason = _select_diverse(
        candidates,
        target=target,
        route_plan=route_plan,
        quality=quality,
    )
    shadow_filtered = [item for item in candidates if item.shadow_filter_reasons]
    stage_counts.update(
        {
            "shadow_filtered": len(shadow_filtered),
            "selected": len(selected),
            "overflow": len(overflow),
        }
    )
    warnings = _pipeline_warnings(
        candidates,
        selected=selected,
        target=target,
        route_plan=route_plan,
        quality=quality,
        site_filter=site_filter,
        time_constraint=time_constraint,
        fallback_reason=fallback_reason,
    )
    gain_estimate = _gain_estimate(
        candidates,
        selected=selected,
        target=target,
        route_plan=route_plan,
        quality=quality,
        fallback_reason=fallback_reason,
    )
    return {
        "enabled": True,
        "mode": mode,
        "fail_open": True,
        "mutates_output": False,
        "status": "ok",
        "query": query,
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "overflow_count": len(overflow),
        "shadow_filtered_count": len(shadow_filtered),
        "target_size": target,
        "fallback_used": bool(fallback_reason),
        "fallback_reason": fallback_reason,
        "selector": {
            "strategy": "score_then_source_role_diversity",
            "max_per_domain_before_fallback": _max_per_domain(target),
            "coverage_floor": _coverage_floor(target, len(candidates)),
        },
        "stage_counts": stage_counts,
        "selected_evidence": [item.sample() for item in selected[:12]],
        "overflow_candidates": [item.sample() for item in overflow[:8]],
        "shadow_filtered_candidates": [item.sample() for item in shadow_filtered[:8]],
        "warnings": warnings,
        "gain_estimate": gain_estimate,
        "agent_guidance": _agent_guidance(
            mode=mode,
            gain=gain_estimate,
            fallback_reason=fallback_reason,
        ),
        "boundary": _boundary(),
    }


def build_disabled_evidence_pipeline(*, query: str = "", reason: str = "disabled") -> dict[str, Any]:
    """Return a compact disabled report for explicit rollback/off mode."""

    return {
        "enabled": False,
        "mode": "off",
        "fail_open": True,
        "mutates_output": False,
        "status": "disabled",
        "query": query,
        "candidate_count": 0,
        "selected_count": 0,
        "overflow_count": 0,
        "shadow_filtered_count": 0,
        "fallback_used": False,
        "fallback_reason": "",
        "disabled_reason": reason,
        "stage_counts": {
            "source": 0,
            "hydrated": 0,
            "shadow_filtered": 0,
            "selected": 0,
            "overflow": 0,
        },
        "selected_evidence": [],
        "overflow_candidates": [],
        "shadow_filtered_candidates": [],
        "warnings": [],
        "gain_estimate": _empty_gain_estimate(label="off", empty_result_risk="not_evaluated"),
        "agent_guidance": [
            "Evidence Mixer is explicitly off; use the original ranked search results."
        ],
        "boundary": _boundary(),
    }


def normalize_evidence_mode(mode: str | None) -> str:
    """Normalize CLI/API evidence-mode values."""

    normalized = str(mode or "shadow").strip().lower().replace("_", "-")
    aliases = {
        "disabled": "off",
        "false": "off",
        "0": "off",
        "true": "shadow",
        "on": "shadow",
        "diagnostic": "shadow",
        "diagnostics": "shadow",
        "advisory": "assist",
        "guide": "assist",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in _VALID_MODES else "shadow"


def _hydrate_candidates(results: list[dict[str, Any]]) -> list[EvidenceCandidate]:
    seen_urls: set[str] = set()
    candidates: list[EvidenceCandidate] = []
    for idx, item in enumerate(results):
        url = str(item.get("url") or "")
        domain = str(item.get("domain") or _domain(url))
        source_card = ((item.get("trace") or {}).get("source_card") or {})
        score_parts = item.get("score_parts") or {}
        search_score = _safe_float(
            item.get("score"),
            default=_safe_float(score_parts.get("total"), default=0.0),
        )
        evidence_score, reasons, penalties = _evidence_score(
            search_score,
            score_parts=score_parts,
            source_card=source_card,
            evidence_role=str(item.get("evidence_role") or ""),
        )
        shadow_filter_reasons: list[str] = []
        if url in seen_urls:
            shadow_filter_reasons.append("duplicate_url")
        seen_urls.add(url)
        if _safe_float(score_parts.get("semantic_noise_penalty"), default=0.0) <= -2.0:
            shadow_filter_reasons.append("severe_semantic_noise")
        risk_tags = set(source_card.get("risk_tags") or [])
        if risk_tags & _HIGH_RISK_TAGS and search_score < 2.0:
            shadow_filter_reasons.append("weak_high_risk_source")
        candidates.append(
            EvidenceCandidate(
                index=idx,
                rank=int(item.get("rank") or idx + 1),
                title=str(item.get("title") or ""),
                url=url,
                domain=domain,
                source_type=str(
                    item.get("source_type") or source_card.get("source_type") or "通用网页"
                ),
                evidence_role=str(item.get("evidence_role") or "open_web_context"),
                search_score=search_score,
                evidence_score=evidence_score,
                reasons=reasons,
                penalties=penalties,
                shadow_filter_reasons=shadow_filter_reasons,
            )
        )
    return candidates


def _evidence_score(
    search_score: float,
    *,
    score_parts: dict[str, Any],
    source_card: dict[str, Any],
    evidence_role: str,
) -> tuple[float, list[str], list[str]]:
    reasons: list[str] = []
    penalties: list[str] = []
    score = search_score
    for key in sorted(_POSITIVE_SCORE_PARTS):
        value = _safe_float(score_parts.get(key), default=0.0)
        if value > 0:
            reasons.append(f"{key}+{round(value, 3)}")
    for key in sorted(_PENALTY_SCORE_PARTS):
        value = _safe_float(score_parts.get(key), default=0.0)
        if value < 0:
            penalties.append(f"{key}{round(value, 3)}")
    authority = _safe_float(source_card.get("authority_score"), default=0.0)
    sample = _safe_float(source_card.get("sample_value"), default=0.0)
    freshness = _safe_float(source_card.get("freshness_value"), default=0.0)
    score += authority * 0.35 + sample * 0.18 + freshness * 0.12
    if authority >= 0.7:
        reasons.append("source_card.authority")
    if sample >= 0.7:
        reasons.append("source_card.sample")
    if freshness >= 0.7:
        reasons.append("source_card.freshness")
    if evidence_role in {
        "official_primary",
        "company_primary",
        "database_official",
        "standard_original",
        "security_advisory",
        "vendor_patch",
    }:
        score += 0.35
        reasons.append(f"role.{evidence_role}")
    risk_tags = set(source_card.get("risk_tags") or [])
    if risk_tags & _HIGH_RISK_TAGS:
        score -= 0.25
        penalties.append("source_card.risk")
    return round(max(score, 0.1), 3), reasons[:8], penalties[:8]


def _select_diverse(
    candidates: list[EvidenceCandidate],
    *,
    target: int,
    route_plan: dict[str, Any],
    quality: dict[str, Any],
) -> tuple[list[EvidenceCandidate], list[EvidenceCandidate], str]:
    target = min(max(target, 1), len(candidates))
    domain_limit = _max_per_domain(target)
    role_limit = max(2, min(4, target // 2 or 1))
    preferred_roles = set(route_plan.get("evidence_roles") or quality.get("route_evidence_roles") or [])
    ordered = sorted(
        candidates,
        key=lambda item: (
            -_selection_score(item, preferred_roles=preferred_roles),
            item.rank,
            item.index,
        ),
    )
    selected: list[EvidenceCandidate] = []
    overflow: list[EvidenceCandidate] = []
    domain_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    for item in ordered:
        if len(selected) >= target:
            overflow.append(item)
            continue
        if item.shadow_filter_reasons and len(candidates) > target:
            overflow.append(item)
            continue
        domain = item.domain or "-"
        role = item.evidence_role or "-"
        if domain_counts[domain] >= domain_limit:
            overflow.append(item)
            continue
        if role_counts[role] >= role_limit and role not in preferred_roles:
            overflow.append(item)
            continue
        selected.append(item)
        domain_counts[domain] += 1
        role_counts[role] += 1

    fallback_reason = ""
    floor = _coverage_floor(target, len(candidates))
    if len(selected) < floor:
        selected_ids = {id(item) for item in selected}
        for item in ordered:
            if len(selected) >= floor:
                break
            if id(item) not in selected_ids:
                selected.append(item)
                selected_ids.add(id(item))
        overflow = [item for item in ordered if id(item) not in selected_ids]
        fallback_reason = "coverage_floor"
    return selected[:target], overflow, fallback_reason


def _selection_score(item: EvidenceCandidate, *, preferred_roles: set[str]) -> float:
    score = item.evidence_score
    if item.evidence_role in preferred_roles:
        score += 0.4
    if item.shadow_filter_reasons:
        score -= 1.5
    return score


def _pipeline_warnings(
    candidates: list[EvidenceCandidate],
    *,
    selected: list[EvidenceCandidate],
    target: int,
    route_plan: dict[str, Any],
    quality: dict[str, Any],
    site_filter: dict[str, Any],
    time_constraint: dict[str, Any],
    fallback_reason: str,
) -> list[str]:
    warnings: list[str] = []
    if fallback_reason:
        warnings.append("coverage fallback used; shadow selector would have selected too few diverse candidates.")
    if selected and len({item.domain for item in selected}) == 1 and len(selected) >= min(3, target):
        warnings.append("selected evidence is dominated by one domain.")
    preferred_roles = set(route_plan.get("evidence_roles") or quality.get("route_evidence_roles") or [])
    selected_roles = {item.evidence_role for item in selected}
    missing_roles = sorted(role for role in preferred_roles if role not in selected_roles)
    if missing_roles:
        warnings.append("missing preferred evidence roles: " + ", ".join(missing_roles[:4]))
    if any(item.shadow_filter_reasons for item in candidates):
        warnings.append("shadow-only filter reasons were detected; existing output remains fail-open.")
    if any(item.shadow_filter_reasons for item in selected):
        warnings.append("selected set includes shadow-flagged candidates only because coverage is protected.")
    if site_filter.get("enabled") and not site_filter.get("kept"):
        warnings.append("site hard filter kept zero candidates before shadow selection.")
    if time_constraint.get("enabled") and str(time_constraint.get("strictness") or "") == "hard":
        warnings.append("time constraint is strict; window-outside materials should stay background only.")
    return warnings[:8]


def _gain_estimate(
    candidates: list[EvidenceCandidate],
    *,
    selected: list[EvidenceCandidate],
    target: int,
    route_plan: dict[str, Any],
    quality: dict[str, Any],
    fallback_reason: str,
) -> dict[str, Any]:
    baseline = sorted(candidates, key=lambda item: (item.rank, item.index))[:target]
    preferred_roles = set(route_plan.get("evidence_roles") or quality.get("route_evidence_roles") or [])
    selected_shadow_flags = sum(1 for item in selected if item.shadow_filter_reasons)
    shadow_flagged = sum(1 for item in candidates if item.shadow_filter_reasons)
    metrics = {
        "selected_count": len(selected),
        "baseline_domain_count": _distinct_count(baseline, "domain"),
        "selected_domain_count": _distinct_count(selected, "domain"),
        "baseline_role_count": _distinct_count(baseline, "evidence_role"),
        "selected_role_count": _distinct_count(selected, "evidence_role"),
        "baseline_preferred_role_count": _role_hit_count(baseline, preferred_roles),
        "selected_preferred_role_count": _role_hit_count(selected, preferred_roles),
        "baseline_strong_source_count": _role_hit_count(baseline, _STRONG_EVIDENCE_ROLES),
        "selected_strong_source_count": _role_hit_count(selected, _STRONG_EVIDENCE_ROLES),
        "selected_shadow_flagged_count": selected_shadow_flags,
        "shadow_flagged_count": shadow_flagged,
    }
    deltas = {
        "domain_diversity_delta": metrics["selected_domain_count"] - metrics["baseline_domain_count"],
        "role_diversity_delta": metrics["selected_role_count"] - metrics["baseline_role_count"],
        "preferred_role_delta": metrics["selected_preferred_role_count"] - metrics["baseline_preferred_role_count"],
        "strong_source_delta": metrics["selected_strong_source_count"] - metrics["baseline_strong_source_count"],
    }
    score_delta = (
        deltas["domain_diversity_delta"] * 5
        + deltas["role_diversity_delta"] * 4
        + deltas["preferred_role_delta"] * 7
        + deltas["strong_source_delta"] * 8
    )
    if fallback_reason:
        score_delta -= 3
    if selected_shadow_flags:
        score_delta -= selected_shadow_flags * 4
    if not selected and candidates:
        label = "risk"
        empty_result_risk = "would_create_empty_if_activated"
    elif selected_shadow_flags:
        label = "watch"
        empty_result_risk = "low"
    elif fallback_reason:
        label = "watch"
        empty_result_risk = "low"
    elif score_delta > 0:
        label = "positive"
        empty_result_risk = "low"
    elif metrics["selected_preferred_role_count"] or metrics["selected_strong_source_count"]:
        label = "positive"
        empty_result_risk = "low"
    else:
        label = "neutral"
        empty_result_risk = "low"
    activation = "assist_ok" if label in {"positive", "neutral"} and not fallback_reason else "keep_shadow"
    if label == "risk":
        activation = "do_not_activate"
    gain_score = _gain_score(metrics, fallback_reason=fallback_reason)
    summary = (
        f"label={label}; score_delta={score_delta}; "
        f"gain_score={gain_score}; "
        f"domains {metrics['baseline_domain_count']}->{metrics['selected_domain_count']}; "
        f"roles {metrics['baseline_role_count']}->{metrics['selected_role_count']}; "
        f"preferred_roles {metrics['baseline_preferred_role_count']}->{metrics['selected_preferred_role_count']}; "
        f"strong_sources {metrics['baseline_strong_source_count']}->{metrics['selected_strong_source_count']}"
    )
    return {
        "label": label,
        "score_delta": score_delta,
        "gain_score": gain_score,
        "activation_recommendation": activation,
        "empty_result_risk": empty_result_risk,
        "baseline_top_count": len(baseline),
        "selected_count": len(selected),
        "preferred_roles": sorted(preferred_roles),
        "metrics": metrics,
        "deltas": deltas,
        "summary": summary,
    }


def _empty_gain_estimate(
    *,
    label: str = "neutral",
    empty_result_risk: str = "existing_empty_input",
) -> dict[str, Any]:
    return {
        "label": label,
        "score_delta": 0,
        "gain_score": 0,
        "activation_recommendation": "keep_shadow",
        "empty_result_risk": empty_result_risk,
        "baseline_top_count": 0,
        "selected_count": 0,
        "preferred_roles": [],
        "metrics": {
            "selected_count": 0,
            "baseline_domain_count": 0,
            "selected_domain_count": 0,
            "baseline_role_count": 0,
            "selected_role_count": 0,
            "baseline_preferred_role_count": 0,
            "selected_preferred_role_count": 0,
            "baseline_strong_source_count": 0,
            "selected_strong_source_count": 0,
            "selected_shadow_flagged_count": 0,
            "shadow_flagged_count": 0,
        },
        "deltas": {
            "domain_diversity_delta": 0,
            "role_diversity_delta": 0,
            "preferred_role_delta": 0,
            "strong_source_delta": 0,
        },
        "summary": "No candidate evidence was available to estimate mixer gain.",
    }


def _agent_guidance(*, mode: str, gain: dict[str, Any], fallback_reason: str) -> list[str]:
    if mode == "assist":
        prefix = "Use selected_evidence as the first-read order"
    else:
        prefix = "Treat selected_evidence as shadow diagnostics"
    guidance = [
        f"{prefix}; keep the original result list as the complete candidate pool.",
        "Do not report filtered-out candidates as removed from Guanlan output; this selector is fail-open.",
    ]
    if gain.get("empty_result_risk") not in {"low", "not_evaluated"}:
        guidance.append("Do not activate filtering: empty-result risk is not acceptable.")
    if fallback_reason:
        guidance.append("Coverage fallback fired, so this query needs broader reading rather than stricter filtering.")
    if gain.get("activation_recommendation") == "assist_ok":
        guidance.append("Assist-mode surfacing is acceptable; result filtering is still not recommended.")
    return guidance


def _gain_score(metrics: dict[str, int], *, fallback_reason: str) -> int:
    score = 50
    if metrics["selected_domain_count"] >= 2:
        score += 10
    if metrics["selected_role_count"] >= 2:
        score += 10
    if metrics["selected_preferred_role_count"]:
        score += 15
    if metrics["selected_strong_source_count"]:
        score += 15
    if metrics["selected_domain_count"] == 1 and metrics["selected_count"] >= 3:
        score -= 8
    if fallback_reason:
        score -= 10
    score -= metrics["selected_shadow_flagged_count"] * 12
    return max(0, min(100, score))


def _distinct_count(items: list[EvidenceCandidate], field_name: str) -> int:
    return len({str(getattr(item, field_name) or "") for item in items if str(getattr(item, field_name) or "")})


def _role_hit_count(items: list[EvidenceCandidate], roles: set[str]) -> int:
    if not roles:
        return 0
    return sum(1 for item in items if item.evidence_role in roles)


def _target_size(candidate_count: int, *, limit: int, target_size: int | None) -> int:
    if target_size is not None:
        return min(max(int(target_size), 1), candidate_count)
    return min(candidate_count, max(5, min(10, limit)))


def _coverage_floor(target: int, candidate_count: int) -> int:
    return min(candidate_count, target, 5)


def _max_per_domain(target: int) -> int:
    return max(2, min(4, (target + 2) // 3))


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _boundary() -> str:
    return (
        "shadow Evidence Mixer only scores and explains candidate selection; "
        "it does not remove or reorder search results, and it falls open when coverage is thin."
    )


__all__ = [
    "build_disabled_evidence_pipeline",
    "build_shadow_evidence_pipeline",
    "normalize_evidence_mode",
]
