# -*- coding: utf-8 -*-
"""Deterministic, conservative provenance records for Guanlan evidence.

This module is deliberately free of network access and ranking decisions.  It
turns already-read page bodies into stable identities, snapshots, passages and
strict claim mentions.  It never decides whether a claim is true.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import Any

EVIDENCE_BUNDLE_SCHEMA_VERSION = "evidence_bundle_v1"
DOCUMENT_SNAPSHOT_SCHEMA_VERSION = "document_snapshot_v1"
PASSAGE_SCHEMA_VERSION = "passage_v1"
CLAIM_CANDIDATE_SCHEMA_VERSION = "claim_candidate_v1"
EVIDENCE_LINK_SCHEMA_VERSION = "evidence_link_v1"

_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "model_version",
        re.compile(
            r"\b(?:GPT|Claude|GLM|Qwen|Gemini|DeepSeek)[-\s]?[A-Za-z]*(?:\s+)?\d+(?:\.\d+)?\b", re.I
        ),
    ),
    ("price", re.compile(r"(?:[$¥￥]\s?\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:元|美元|人民币))", re.I)),
    (
        "parameter_count",
        re.compile(
            r"\b\d+(?:\.\d+)?\s*(?:B|M|K|T)\s*(?:parameters?|params?)?\b|\d+(?:\.\d+)?\s*(?:万亿|千亿|百亿|亿|万)\s*参数",
            re.I,
        ),
    ),
    ("percentage_metric", re.compile(r"\b\d+(?:\.\d+)?\s?%")),
    ("date", re.compile(r"\b20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?\b")),
)


def stable_id(prefix: str, *parts: object) -> str:
    """Return a readable deterministic identifier over canonical string parts."""

    payload = "\x1f".join(str(part or "").strip() for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def normalize_url(url: str) -> str:
    """Normalize a web URL for identity purposes without fetching it."""

    value = str(url or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    if not parsed.scheme and not parsed.netloc:
        parsed = urllib.parse.urlsplit("https://" + value)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    if not scheme or not host:
        return value
    port = parsed.port
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    return urllib.parse.urlunsplit((scheme, netloc, path, parsed.query, ""))


def build_source_identity(item: dict[str, Any]) -> dict[str, Any]:
    url = normalize_url(str(item.get("url") or ""))
    domain = (urllib.parse.urlsplit(url).hostname or str(item.get("domain") or "")).lower()
    source_name = str(item.get("source") or item.get("source_name") or domain).strip()
    return {
        "schema_version": "source_identity_v1",
        "source_id": stable_id("src", domain, source_name),
        "name": source_name,
        "domain": domain,
        "source_type": str(item.get("source_type") or ""),
        "evidence_role": str(item.get("evidence_role") or ""),
        "url": url,
    }


def build_document_snapshot(
    *,
    url: str,
    content: str,
    title: str = "",
    metadata: dict[str, Any] | None = None,
    observed_at: float | None = None,
    previous_snapshot_id: str = "",
) -> dict[str, Any]:
    """Build a content-addressed snapshot from an already-read page body."""

    normalized_url = normalize_url(url)
    body = str(content or "")
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    snapshot_id = stable_id("snap", normalized_url, content_hash)
    return {
        "schema_version": DOCUMENT_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "url": normalized_url,
        "title": str(title or "").strip(),
        "content_hash": content_hash,
        "content_chars": len(body),
        "observed_at": observed_at,
        "previous_snapshot_id": str(previous_snapshot_id or ""),
        "metadata": dict(metadata or {}),
    }


def build_passages(
    snapshot: dict[str, Any],
    content: str,
    *,
    max_passages: int = 96,
) -> list[dict[str, Any]]:
    """Split Markdown/plain text into offset-addressable paragraph passages."""

    body = str(content or "")
    snapshot_id = str(snapshot.get("snapshot_id") or "")
    headings: list[str] = []
    passages: list[dict[str, Any]] = []
    for match in re.finditer(r"(?ms)(?:^|(?<=\n\n))[^\s].*?(?=\n\s*\n|\Z)", body):
        raw = match.group(0)
        text = raw.strip()
        if not text:
            continue
        leading = len(raw) - len(raw.lstrip())
        start = match.start() + leading
        end = start + len(text)
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", text)
        if heading:
            level = len(heading.group(1))
            headings = headings[: level - 1]
            headings.append(heading.group(2).strip())
        ordinal = len(passages)
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        passages.append(
            {
                "schema_version": PASSAGE_SCHEMA_VERSION,
                "passage_id": stable_id("psg", snapshot_id, ordinal, text_hash),
                "snapshot_id": snapshot_id,
                "ordinal": ordinal,
                "heading_path": list(headings),
                "char_start": start,
                "char_end": end,
                "text": text,
                "text_hash": text_hash,
            }
        )
        if len(passages) >= max(max_passages, 1):
            break
    return passages


def extract_claim_candidates(
    passages: list[dict[str, Any]],
    *,
    max_claims: int = 48,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract exact token mentions; relations are intentionally non-judgmental."""

    claims: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for passage in passages:
        text = str(passage.get("text") or "")
        for category, pattern in _CLAIM_PATTERNS:
            for match in pattern.finditer(text):
                value = " ".join(match.group(0).split())
                key = (str(passage.get("passage_id") or ""), category, value.lower())
                if key in seen:
                    continue
                seen.add(key)
                claim_id = stable_id("clm", *key)
                claim = {
                    "schema_version": CLAIM_CANDIDATE_SCHEMA_VERSION,
                    "claim_id": claim_id,
                    "category": category,
                    "value": value,
                    "passage_id": passage.get("passage_id", ""),
                    "char_start": int(passage.get("char_start") or 0) + match.start(),
                    "char_end": int(passage.get("char_start") or 0) + match.end(),
                    "confidence": 1.0,
                    "status": "candidate",
                }
                link = {
                    "schema_version": EVIDENCE_LINK_SCHEMA_VERSION,
                    "link_id": stable_id("lnk", claim_id, passage.get("passage_id", "")),
                    "claim_id": claim_id,
                    "passage_id": passage.get("passage_id", ""),
                    "relation": "mentions",
                    "confidence": 1.0,
                }
                claims.append(claim)
                links.append(link)
                if len(claims) >= max(max_claims, 1):
                    return claims, links
    return claims, links


def build_evidence_bundle(packet: dict[str, Any]) -> dict[str, Any]:
    """Build the additive v1 provenance bundle without changing packet results."""

    source_identities: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    candidates = (
        list(packet.get("results") or [])
        + list(packet.get("selected_evidence") or [])
        + list(packet.get("readings") or [])
    )
    for item in candidates:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        source = build_source_identity(item)
        key = str(source.get("url") or source.get("source_id") or "")
        if key in seen_sources:
            continue
        seen_sources.add(key)
        source_identities.append(source)

    snapshots: list[dict[str, Any]] = []
    passages: list[dict[str, Any]] = []
    for reading in list(packet.get("readings") or []):
        if not isinstance(reading, dict) or not _is_citable_reading(reading):
            continue
        content = str(reading.get("content") or "")
        snapshot = build_document_snapshot(
            url=str(reading.get("url") or ""),
            content=content,
            title=str(reading.get("title") or ""),
            metadata={
                "source": str(reading.get("source") or ""),
                "source_type": str(reading.get("source_type") or ""),
                "evidence_role": str(reading.get("evidence_role") or ""),
                "boundary": str(reading.get("boundary") or ""),
            },
        )
        snapshots.append(snapshot)
        remaining = max(0, 96 - len(passages))
        if remaining:
            passages.extend(build_passages(snapshot, content, max_passages=remaining))
        if len(passages) >= 96:
            break
    claims, links = extract_claim_candidates(passages, max_claims=48)
    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION,
        "query": str(packet.get("query") or ""),
        "source_identities": source_identities,
        "document_snapshots": snapshots,
        "passages": passages,
        "claim_candidates": claims,
        "evidence_links": links,
        "coverage": {
            "source_count": len(source_identities),
            "snapshot_count": len(snapshots),
            "passage_count": len(passages),
            "claim_candidate_count": len(claims),
            "citable_page_count": len(snapshots),
        },
        "experimental": ["claim_candidate_v1", "evidence_link_v1"],
        "boundary": (
            "只从 can_cite_as_page_body=true 的已读正文生成快照和段落；claim 是精确字符串候选，"
            "relation=mentions 不代表支持、反驳或事实为真。"
        ),
    }


def _is_citable_reading(reading: dict[str, Any]) -> bool:
    contract = reading.get("extract_contract")
    return bool(
        reading.get("usable")
        and isinstance(contract, dict)
        and contract.get("can_cite_as_page_body") is True
        and str(reading.get("content") or "").strip()
    )


__all__ = [
    "CLAIM_CANDIDATE_SCHEMA_VERSION",
    "DOCUMENT_SNAPSHOT_SCHEMA_VERSION",
    "EVIDENCE_BUNDLE_SCHEMA_VERSION",
    "EVIDENCE_LINK_SCHEMA_VERSION",
    "PASSAGE_SCHEMA_VERSION",
    "build_document_snapshot",
    "build_evidence_bundle",
    "build_passages",
    "build_source_identity",
    "extract_claim_candidates",
    "normalize_url",
    "stable_id",
]
