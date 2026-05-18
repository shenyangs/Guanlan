# -*- coding: utf-8 -*-
"""Lightweight claim ledger for Guanlan evidence packets.

The ledger is intentionally conservative. It extracts common fact-like tokens
from search/read evidence and keeps provenance next to every value, but it does
not decide which value is true.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import Any

_CLAIM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("model_version", r"\b(?:GPT|Claude|GLM|Qwen|Gemini|DeepSeek)[-\s]?[A-Za-z]*(?:\s+)?\d+(?:\.\d+)?\b"),
    (
        "price",
        r"(?:[$¥￥]\s?\d+(?:\.\d+)?(?:\s*(?:/|per|每)\s*(?:1m|million|百万|千|k|tokens?|token))?|(?:\d+(?:\.\d+)?\s*(?:元|美元|人民币)(?:\s*(?:/|每)\s*(?:百万|千|tokens?|token|次))?))",
    ),
    (
        "parameter_count",
        r"\b\d+(?:\.\d+)?\s*(?:B|M|K|T)\s*(?:parameters?|params?)?\b|(?:\d+(?:\.\d+)?\s*(?:万亿|千亿|百亿|亿|万)\s*参数)",
    ),
    ("percentage_metric", r"\b\d+(?:\.\d+)?\s?%"),
    ("date", r"\b20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?\b"),
)

_CONFLICT_CATEGORIES = {"model_version", "price", "parameter_count", "percentage_metric"}

_STRONG_ROLES = {
    "official_primary",
    "company_primary",
    "technical_primary",
    "vendor_patch",
    "regulator_notice",
    "database_official",
    "publisher_guideline",
    "market_quote",
    "company_filing",
}
_MEDIUM_ROLES = {
    "authoritative_report",
    "industry_report",
    "vertical_report",
    "technical_note",
    "developer_discussion",
    "research_primary",
    "preprint_record",
}
_SAMPLE_ROLES = {
    "user_sample",
    "community_discussion",
    "public_discussion",
    "social_signal",
    "sentiment_sample",
    "user_visible_sample",
}


def build_claim_ledger(packet: dict[str, Any], *, limit: int = 48) -> dict[str, Any]:
    """Extract an agent-facing, provenance-preserving claim ledger."""

    query = str(packet.get("query") or "").strip()
    claims: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in _candidate_evidence(packet):
        text = _evidence_text(item)
        if not text:
            continue
        for extracted in _extract_claims(text):
            url = str(item.get("url") or "")
            key = (
                str(extracted.get("category") or ""),
                str(extracted.get("normalized_value") or ""),
                url,
                str(item.get("evidence_kind") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            claim = _claim_record(query=query, item=item, extracted=extracted, ordinal=len(claims) + 1)
            claims.append(claim)
            if len(claims) >= max(limit, 1):
                break
        if len(claims) >= max(limit, 1):
            break

    conflict_sets = _build_conflict_sets(claims)
    _attach_conflict_sets(claims, conflict_sets)
    for claim in claims:
        claim["needs_verification"] = bool(claim.get("conflict_set") or float(claim.get("confidence", 0)) < 0.6)

    warnings: list[str] = []
    if conflict_sets:
        warnings.append("事实台账检测到同类事实有多个候选值；回答时要保留来源、时间和证据角色差异。")
    if any(claim.get("source_mode") == "browser_visible" for claim in claims):
        warnings.append("台账包含浏览器可见页补证；这些材料依赖用户授权和当前会话，不能写成普通公开网页证据。")
    if claims and not conflict_sets:
        warnings.append("事实台账未发现明显候选值冲突；仍需回到原文确认上下文、口径和日期。")

    return {
        "title": "事实台账",
        "mode": "claim_ledger_v1",
        "query": query,
        "claim_count": len(claims),
        "conflict_count": len(conflict_sets),
        "category_counts": _count_by(claims, "category"),
        "role_counts": _count_by(claims, "evidence_role"),
        "source_type_counts": _count_by(claims, "source_type"),
        "claims": claims,
        "conflict_sets": conflict_sets,
        "warnings": warnings,
        "verification_steps": [
            "把同一 category 的多个值当作待核验候选，不要自动平均、合并或择新。",
            "优先查看 official/company/technical 等强证据角色，再用媒体、社区和可见页样本补充语境。",
            "引用 claim 时同时带上 source_title、url、date、evidence_role 和 confidence。",
        ],
        "boundary": "事实台账是证据整理层，不是事实裁决层；它只保留可追溯候选值和冲突信号。",
    }


def format_claim_ledger_markdown(ledger: dict[str, Any]) -> str:
    """Render a compact Markdown claim ledger."""

    lines = [f"## {ledger.get('title') or '事实台账'}"]
    if ledger.get("boundary"):
        lines.append(f"- 边界: {ledger['boundary']}")
    lines.append(
        f"- 抽取 claim: {int(ledger.get('claim_count') or 0)}；冲突组: {int(ledger.get('conflict_count') or 0)}"
    )
    for warning in list(ledger.get("warnings") or [])[:3]:
        lines.append(f"- 提醒: {warning}")
    conflict_sets = list(ledger.get("conflict_sets") or [])
    if conflict_sets:
        lines.append("- 候选值冲突:")
        for conflict in conflict_sets[:5]:
            values = " / ".join(str(item) for item in conflict.get("values", [])[:6])
            lines.append(f"  - {conflict.get('conflict_set')}: {conflict.get('category')} -> {values}")
            for source in list(conflict.get("sources") or [])[:4]:
                lines.append(
                    f"    - {source.get('value')} | {source.get('evidence_role') or '-'} | "
                    f"{source.get('source_title') or ''} | {source.get('url') or ''}"
                )
    claims = list(ledger.get("claims") or [])
    if claims:
        lines.append("- 代表 claim:")
        for claim in claims[:10]:
            source = _trim(str(claim.get("source_title") or ""), 70)
            lines.append(
                f"  - {claim.get('claim_id')}: [{claim.get('category')}] {claim.get('value')} | "
                f"{claim.get('evidence_role') or claim.get('source_type') or '-'} | "
                f"confidence={claim.get('confidence')} | {source} | {claim.get('url') or ''}"
            )
    return "\n".join(lines)


def format_claim_ledger_context(ledger: dict[str, Any]) -> str:
    """Render claim ledger hints for prompt/context modes."""

    lines = [f"# {ledger.get('title') or '事实台账'}"]
    if ledger.get("boundary"):
        lines.append(f"边界: {ledger['boundary']}")
    lines.append(f"claims={ledger.get('claim_count', 0)} conflicts={ledger.get('conflict_count', 0)}")
    for conflict in list(ledger.get("conflict_sets") or [])[:5]:
        values = " / ".join(str(item) for item in conflict.get("values", [])[:6])
        lines.append(f"- 冲突组 {conflict.get('conflict_set')}: {conflict.get('category')} -> {values}")
    for claim in list(ledger.get("claims") or [])[:12]:
        lines.append(
            f"- {claim.get('claim_id')} [{claim.get('category')}] {claim.get('value')} | "
            f"{claim.get('evidence_role') or claim.get('source_type') or '-'} | "
            f"confidence={claim.get('confidence')} | {claim.get('source_title') or ''} | {claim.get('url') or ''}"
        )
    return "\n".join(lines)


def _candidate_evidence(packet: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_search_urls: set[str] = set()
    for item in list(packet.get("selected_evidence") or []) + list(packet.get("results") or []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        if url and url in seen_search_urls:
            continue
        if url:
            seen_search_urls.add(url)
        row = dict(item)
        row["evidence_kind"] = "search"
        candidates.append(row)
    for item in list(packet.get("readings") or []):
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["evidence_kind"] = "read"
        candidates.append(row)
    return candidates


def _evidence_text(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("title") or ""),
        str(item.get("snippet") or ""),
        str(item.get("content") or ""),
        str(item.get("summary") or ""),
        str(item.get("error") or ""),
    ]
    return _collapse_ws(" ".join(part for part in parts if part))[:6000]


def _extract_claims(text: str) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for category, pattern in _CLAIM_PATTERNS:
        for match in re.finditer(pattern, text or "", flags=re.I):
            raw = _collapse_ws(match.group(0))
            value = _normalize_value(category, raw)
            if not value:
                continue
            key = (category, value.lower())
            if key in seen:
                continue
            seen.add(key)
            claims.append(
                {
                    "category": category,
                    "value": value,
                    "normalized_value": _normalized_key(category, value),
                    "raw": raw,
                }
            )
    return claims


def _claim_record(query: str, item: dict[str, Any], extracted: dict[str, str], ordinal: int) -> dict[str, Any]:
    url = str(item.get("url") or "")
    domain = str(item.get("domain") or _domain(url))
    evidence_role = str(item.get("evidence_role") or "")
    source_type = str(item.get("source_type") or "")
    evidence_kind = str(item.get("evidence_kind") or "search")
    confidence = _claim_confidence(evidence_role=evidence_role, source_type=source_type, evidence_kind=evidence_kind)
    claim_id = _claim_id(ordinal, url, extracted)
    return {
        "claim_id": claim_id,
        "category": extracted["category"],
        "value": extracted["value"],
        "normalized_value": extracted["normalized_value"],
        "subject": _subject(query=query, item=item),
        "source_title": _collapse_ws(str(item.get("title") or "")),
        "url": url,
        "domain": domain,
        "source_type": source_type or "通用网页",
        "evidence_role": evidence_role,
        "evidence_kind": evidence_kind,
        "source_mode": str(item.get("source_mode") or ""),
        "date": _date_from_item(item),
        "confidence": confidence,
        "conflict_set": "",
        "needs_verification": False,
    }


def _build_conflict_sets(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_category: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for claim in claims:
        category = str(claim.get("category") or "")
        value = str(claim.get("normalized_value") or "")
        if category not in _CONFLICT_CATEGORIES or not value:
            continue
        by_category.setdefault(category, {}).setdefault(value, []).append(claim)

    conflict_sets: list[dict[str, Any]] = []
    for category, values in by_category.items():
        if len(values) < 2:
            continue
        source_urls = {str(claim.get("url") or "") for group in values.values() for claim in group if claim.get("url")}
        if len(source_urls) < 2:
            continue
        conflict_id = f"CLF-{len(conflict_sets) + 1:03d}"
        sources: list[dict[str, Any]] = []
        for value, group in list(values.items())[:8]:
            for claim in group[:2]:
                sources.append(
                    {
                        "claim_id": claim.get("claim_id"),
                        "value": claim.get("value"),
                        "source_title": claim.get("source_title"),
                        "url": claim.get("url"),
                        "date": claim.get("date"),
                        "evidence_role": claim.get("evidence_role"),
                        "source_type": claim.get("source_type"),
                        "confidence": claim.get("confidence"),
                    }
                )
        conflict_sets.append(
            {
                "conflict_set": conflict_id,
                "category": category,
                "values": [group[0].get("value") for group in values.values() if group],
                "claim_ids": [claim.get("claim_id") for group in values.values() for claim in group],
                "sources": sources,
                "severity": "needs_review",
            }
        )
    return conflict_sets


def _attach_conflict_sets(claims: list[dict[str, Any]], conflict_sets: list[dict[str, Any]]) -> None:
    claim_to_conflict: dict[str, str] = {}
    for conflict in conflict_sets:
        conflict_id = str(conflict.get("conflict_set") or "")
        for claim_id in conflict.get("claim_ids") or []:
            claim_to_conflict[str(claim_id)] = conflict_id
    for claim in claims:
        claim["conflict_set"] = claim_to_conflict.get(str(claim.get("claim_id") or ""), "")


def _claim_confidence(*, evidence_role: str, source_type: str, evidence_kind: str) -> float:
    role = evidence_role.strip()
    source = source_type.strip()
    if role in _STRONG_ROLES:
        base = 0.82
    elif role in _MEDIUM_ROLES:
        base = 0.62
    elif role in _SAMPLE_ROLES:
        base = 0.38
    elif "官方" in source or "政府" in source:
        base = 0.78
    elif "媒体" in source or "产业" in source:
        base = 0.55
    elif "社交" in source or "社区" in source:
        base = 0.36
    else:
        base = 0.46
    if evidence_kind == "read":
        base += 0.05
    return round(min(max(base, 0.05), 0.95), 2)


def _normalize_value(category: str, value: str) -> str:
    normalized = _collapse_ws(value).replace("￥", "¥")
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if category == "date":
        normalized = normalized.replace("年", "-").replace("月", "-").replace("日", "")
        normalized = normalized.replace("/", "-").replace(".", "-")
        parts = [part for part in normalized.split("-") if part]
        if len(parts) >= 2 and all(part.isdigit() for part in parts[:2]):
            year = parts[0]
            month = parts[1].zfill(2)
            day = parts[2].zfill(2) if len(parts) >= 3 and parts[2].isdigit() else ""
            return "-".join(part for part in (year, month, day) if part)
    return normalized


def _normalized_key(category: str, value: str) -> str:
    value = _normalize_value(category, value)
    if category in {"model_version", "parameter_count"}:
        return re.sub(r"\s+", "", value).lower()
    if category == "price":
        return value.replace(" ", "").lower()
    if category == "percentage_metric":
        return value.replace(" ", "")
    return value.lower()


def _claim_id(ordinal: int, url: str, extracted: dict[str, str]) -> str:
    seed = "|".join([url, extracted.get("category", ""), extracted.get("normalized_value", ""), str(ordinal)])
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6].upper()
    return f"CLM-{ordinal:03d}-{digest}"


def _subject(*, query: str, item: dict[str, Any]) -> str:
    title = _collapse_ws(str(item.get("title") or ""))
    if title:
        return _trim(title, 90)
    return _trim(query, 90) or "unknown"


def _date_from_item(item: dict[str, Any]) -> str:
    for key in ("published_at", "date", "updated_at", "captured_at"):
        value = str(item.get(key) or "").strip()
        if value:
            return value[:32]
    trace = item.get("trace") if isinstance(item.get("trace"), dict) else {}
    recency = trace.get("recency") if isinstance(trace.get("recency"), dict) else {}
    return str(recency.get("result_date") or "")[:32]


def _count_by(claims: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for claim in claims:
        value = str(claim.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda row: (-row[1], row[0])))


def _domain(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _trim(text: str, limit: int) -> str:
    text = _collapse_ws(text)
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "…"
