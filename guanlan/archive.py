# -*- coding: utf-8 -*-
"""Local Markdown archive for Guanlan.

The archive is intentionally small and boring: SQLite, local-only storage, and
plain Markdown text. It gives agents a durable Chinese web memory without
requiring a vector database on day one.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from guanlan.evidence_kernel import build_document_snapshot, build_passages
from guanlan.limits import (
    DEFAULT_ARCHIVE_LIST_LIMIT,
    DEFAULT_ARCHIVE_SEARCH_LIMIT,
    DEFAULT_READ_FALLBACK_LIMIT,
)

ARCHIVE_SCHEMA_VERSION = 3
ARCHIVE_MIN_USEFUL_CHARS = 40
ARCHIVE_CONTENT_MODE_RANK = {
    "full_body": 3,
    "partial_body": 2,
    "snippet": 1,
    "unknown": 0,
}
ARCHIVE_TOPIC_KEY_LABELS = {
    "policy": "政策",
    "general": "通用资料",
    "agent": "AI Agent",
    "academic": "学术",
    "finance": "财经",
    "career": "求职职业",
    "entertainment": "文娱",
    "sports": "体育",
    "science": "科学",
    "podcast": "播客",
    "test_prep": "考试备考",
    "reputation": "口碑观察",
    "university": "高校招生",
    "cybersecurity": "网络安全",
    "weather_disaster": "天气灾害",
}


def archive_db_path() -> Path:
    """Return the default local archive database path."""
    return Path.home() / ".guanlan" / "archive.db"


def add_url(
    url: str,
    max_chars: int | None = None,
    backend: str = "auto",
    fallback_search: bool = True,
    fallback_limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read one URL and persist it into the local archive."""
    from guanlan.web.read import read_url

    content = read_url(
        url,
        max_chars=max_chars,
        backend=backend,
        fallback_search=fallback_search,
        fallback_limit=fallback_limit,
        profile=profile,
    )
    return add_document(
        url,
        content,
        metadata={
            "backend": backend,
            "profile": profile or "",
            "fallback_search": fallback_search,
        },
        db_path=db_path,
    )


def add_urls(
    urls: list[str],
    max_chars: int | None = None,
    backend: str = "auto",
    fallback_search: bool = True,
    fallback_limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
    db_path: str | Path | None = None,
    concurrency: int = 1,
) -> list[dict[str, Any]]:
    """Read multiple URLs and persist successful records into the archive."""
    from guanlan.web.read import read_batch

    batch = read_batch(
        urls,
        max_chars=max_chars,
        backend=backend,
        fallback_search=fallback_search,
        fallback_limit=fallback_limit,
        profile=profile,
        concurrency=concurrency,
    )
    records = []
    for item in batch:
        status = str(item.get("status", ""))
        if status != "ok":
            records.append(
                {
                    "url": item.get("url", ""),
                    "status": status or "error",
                    "error": item.get("error", "unknown read error"),
                }
            )
            continue
        records.append(
            add_document(
                str(item.get("url", "")),
                str(item.get("content", "")),
                metadata={"backend": backend, "profile": profile or "", "batch": True},
                db_path=db_path,
            )
        )
    return records


def add_document(
    url: str,
    content: str,
    title: str = "",
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Persist a Markdown document into the local archive."""
    normalized_url = _normalize_url(url)
    if not normalized_url:
        raise ValueError("url is required")
    content = content.strip()
    if not content:
        raise ValueError("content is required")
    title = (title or _title_from_markdown(content) or _domain(normalized_url) or normalized_url).strip()
    now = time.time()
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    url_hash = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
    metadata = dict(metadata or {})
    domain = _domain(normalized_url)
    _enrich_archive_metadata(metadata, domain=domain, content=content)

    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id, content_hash, current_snapshot_id FROM documents WHERE url = ?",
            (normalized_url,),
        ).fetchone()
        status = "created"
        if existing:
            doc_id = int(existing["id"])
            status = "unchanged" if existing["content_hash"] == content_hash else "updated"
            conn.execute(
                """
                UPDATE documents
                SET title = ?, domain = ?, content = ?, excerpt = ?, content_hash = ?,
                    metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title,
                    domain,
                    content,
                    _excerpt(content),
                    content_hash,
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    now,
                    doc_id,
                ),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO documents (
                    url, url_hash, title, domain, content, excerpt, content_hash,
                    metadata_json, added_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_url,
                    url_hash,
                    title,
                    domain,
                    content,
                    _excerpt(content),
                    content_hash,
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
            doc_id = int(cursor.lastrowid)
        snapshot_id, snapshot_status, passage_count = _ensure_document_snapshot(
            conn,
            document_id=doc_id,
            url=normalized_url,
            title=title,
            content=content,
            content_hash=content_hash,
            metadata=metadata,
            observed_at=now,
            previous_snapshot_id=str(existing["current_snapshot_id"] or "") if existing else "",
        )
        if status == "updated" and existing and str(existing["current_snapshot_id"] or "") != snapshot_id:
            _ensure_change_event(
                conn,
                document_id=doc_id,
                before_snapshot_id=str(existing["current_snapshot_id"] or ""),
                after_snapshot_id=snapshot_id,
                created_at=now,
            )
        conn.execute("UPDATE documents SET current_snapshot_id = ? WHERE id = ?", (snapshot_id, doc_id))
        _upsert_fts(conn, doc_id, title=title, content=content, url=normalized_url, domain=domain)
        conn.commit()

    return {
        "id": doc_id,
        "status": status,
        "url": normalized_url,
        "title": title,
        "domain": domain,
        "chars": len(content),
        "content_hash": content_hash,
        "current_snapshot_id": snapshot_id,
        "snapshot_status": snapshot_status,
        "passage_count": passage_count,
    }


def add_browser_visible_note(
    url: str,
    content: str,
    *,
    title: str = "",
    platform: str = "",
    author: str = "",
    published_at: str = "",
    captured_at: float | None = None,
    visible_context: str = "",
    skipped_reason: str = "",
    private_account_evidence: bool = False,
    extra_metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Persist user-authorized visible browser content with explicit boundaries."""

    normalized_url = _normalize_url(url)
    text = str(content or "").strip()
    if not normalized_url:
        raise ValueError("url is required")
    if not text and not skipped_reason:
        raise ValueError("content is required")
    from guanlan.browser_assist import browser_visible_metadata, browser_visible_quality_report

    quality_report = browser_visible_quality_report(
        {
            "url": normalized_url,
            "title": title,
            "visible_text": text,
            "platform": platform,
            "author": author,
            "published_at": published_at,
            "captured_at": captured_at,
            "visible_context": visible_context,
            "skipped_reason": skipped_reason,
            "private_account_evidence": private_account_evidence,
        }
    )
    metadata = browser_visible_metadata(
        url=normalized_url,
        platform=platform,
        author=author,
        published_at=published_at,
        captured_at=captured_at,
        quality_report=quality_report,
        private_account_evidence=private_account_evidence,
    )
    if visible_context:
        metadata["visible_context"] = visible_context
    if skipped_reason:
        metadata["skipped_reason"] = skipped_reason
    if extra_metadata:
        metadata["browser_visible_fields"] = dict(extra_metadata)
    if not text and skipped_reason:
        text = f"浏览器可见页未入正文：{skipped_reason}"
    if title and not text.lstrip().startswith("#"):
        text = f"# {title.strip()}\n\n{text}"
    record = add_document(
        normalized_url,
        text,
        title=title,
        metadata=metadata,
        db_path=db_path,
    )
    record.update(
        {
            "source_mode": "browser_visible",
            "browser_assisted": True,
            "visible_page_only": True,
            "private_account_evidence": bool(private_account_evidence),
            "platform": metadata.get("platform", ""),
            "browser_visible_quality": quality_report,
            "boundary": "用户授权的浏览器可见页补证；不可伪装成所有人可复现的普通公开网页证据。",
        }
    )
    return record


def add_browser_visible_payload(
    payload: dict[str, Any],
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Persist one normalized host-browser visible-page payload."""

    from guanlan.browser_assist import normalize_browser_visible_payload

    row = normalize_browser_visible_payload(payload)
    if (
        row.get("source_mode") != "browser_visible"
        or not row.get("browser_assisted", True)
        or not row.get("user_authorized", True)
        or not row.get("visible_page_only", True)
    ):
        raise ValueError("browser visible payload must declare browser_visible/browser_assisted/user_authorized/visible_page_only")
    return add_browser_visible_note(
        row["url"],
        row["visible_text"],
        title=row.get("title", ""),
        platform=row.get("platform", ""),
        author=row.get("author", ""),
        published_at=row.get("published_at", ""),
        captured_at=_coerce_timestamp(row.get("captured_at")),
        visible_context=row.get("visible_context", ""),
        skipped_reason=row.get("skipped_reason", ""),
        private_account_evidence=bool(row.get("private_account_evidence", False)),
        extra_metadata={
            key: row.get(key, "")
            for key in (
                "content_type",
                "content_id",
                "engagement_summary",
                "visible_comment_summary",
                "creator_profile_summary",
                "creator_profile",
                "metric_snapshots",
                "comment_samples",
                "question",
                "account",
                "session_dependent",
                "private_account_evidence",
            )
            if row.get(key, "") not in ("", None)
        },
        db_path=db_path,
    )


def add_browser_visible_payloads(
    payloads: list[dict[str, Any]],
    *,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Persist multiple browser-visible payloads while keeping per-row errors."""

    records: list[dict[str, Any]] = []
    for payload in payloads:
        try:
            records.append(add_browser_visible_payload(payload, db_path=db_path))
        except Exception as exc:
            records.append(
                {
                    "status": "error",
                    "url": str(payload.get("url") or "") if isinstance(payload, dict) else "",
                    "error": str(exc),
                    "source_mode": "browser_visible",
                    "browser_assisted": True,
                    "visible_page_only": True,
                }
            )
    return records


def _coerce_timestamp(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def ingest_search(
    query: str,
    *,
    limit: int = 50,
    read_top: int = 0,
    select_top: int = 8,
    preset: str = "general",
    profile: str | None = "china",
    dry_run: bool = False,
    db_path: str | Path | None = None,
    read_backend: str = "direct",
    read_concurrency: int = 3,
    cache_ttl: int = 3600,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run Guanlan research and persist representative evidence into the archive."""
    started_at = time.time()
    from guanlan.web.read import read_batch
    from guanlan.web.research import build_research_packet

    phase_log: list[dict[str, Any]] = []

    def emit_progress(phase: str, label: str, detail: str = "", **extra: Any) -> None:
        event = {
            "phase": phase,
            "label": label,
            "detail": detail,
            "elapsed_sec": round(time.time() - started_at, 3),
        }
        for key, value in extra.items():
            if value is not None:
                event[key] = value
        phase_log.append(event)
        if progress_callback:
            try:
                progress_callback(event)
            except Exception:
                pass

    emit_progress(
        "research_start",
        "搜索/研究候选中",
        f"query={query!r} limit={max(limit, 1)} preset={preset} profile={profile or 'auto'}",
    )

    packet = build_research_packet(
        query,
        limit=max(limit, 1),
        # Archive ingest must return predictably. We collect candidates first,
        # then perform bounded reads ourselves only when the user asks for them.
        read_top=0,
        select_top=max(select_top, 1),
        preset=preset,
        profile=profile,
        cache_ttl=max(cache_ttl, 0),
    )
    selected_items = list(packet.get("selected_evidence") or packet.get("results", [])[:select_top])
    topic_labels = _build_topic_labels(query, selected_items)
    emit_progress(
        "research_done",
        "候选已就绪",
        f"packet_results={packet.get('result_count', 0)} selected={len(selected_items)}",
        packet_result_count=packet.get("result_count", 0),
        selected_count=len(selected_items),
    )
    read_attempted = max(read_top, 0)
    selected_urls = [str(item.get("url", "")).strip() for item in selected_items if str(item.get("url", "")).strip()]
    readings = list(packet.get("readings", []))
    if read_attempted > 0 and selected_urls:
        emit_progress(
            "read_start",
            "代表页面读取中",
            f"read_top={read_attempted} backend={read_backend} concurrency={max(read_concurrency, 1)}",
            read_attempted_count=min(read_attempted, len(selected_urls)),
        )
        batch = read_batch(
            selected_urls[:read_attempted],
            max_chars=6000,
            backend=read_backend,
            fallback_search=False,
            profile=profile,
            cache_ttl=max(cache_ttl, 0),
            concurrency=max(read_concurrency, 1),
        )
        readings.extend(
            {
                "url": item.get("url", ""),
                "title": "",
                "status": item.get("status", "error"),
                "content": item.get("content", ""),
                "error": item.get("error", ""),
            }
            for item in batch
        )
        emit_progress(
            "read_done",
            "代表页面读取完成",
            f"success={sum(1 for item in batch if item.get('status') == 'ok')}/{len(batch)}",
            read_success_count=sum(1 for item in batch if item.get("status") == "ok"),
            read_attempted_count=len(batch),
        )
    readings_by_url = {
        str(item.get("url", "")): item
        for item in readings
        if item.get("status") == "ok"
    }
    records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    emit_progress(
        "archive_start",
        "审计/入库中",
        f"selected={len(selected_items)} dry_run={'yes' if dry_run else 'no'}",
        selected_count=len(selected_items),
        dry_run=dry_run,
    )
    for item in selected_items:
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        reading = readings_by_url.get(url)
        if reading and reading.get("content"):
            content = str(reading.get("content", ""))
        else:
            title = str(item.get("title") or url)
            snippet = str(item.get("snippet") or "")
            content = f"# {title}\n\nURL: {url}\n\n{snippet}".strip()
        audit = audit_ingest_candidate(query, item, content=content, existing_urls=seen_urls)
        if audit.get("decision") == "skip":
            records.append(
                {
                    "url": url,
                    "title": str(item.get("title") or url),
                    "status": "skipped",
                    "reason": ",".join(audit.get("reasons") or ["low_quality_candidate"]),
                    "audit": audit,
                }
            )
            continue
        seen_urls.add(_normalize_url(url))
        read_quality = reading.get("read_quality", {}) if isinstance(reading, dict) else {}
        quality_report = reading.get("quality_report", {}) if isinstance(reading, dict) else {}
        topic_key = str(item.get("topic_key") or "").strip()
        metadata = {
            "ingest_query": query,
            "ingest_type": "research",
            "preset": packet.get("preset", preset),
            "source_type": item.get("source_type", ""),
            "source": item.get("source", ""),
            "evidence_role": item.get("evidence_role", ""),
            "topic_key": topic_key,
            "topic_label": topic_labels.get(topic_key or url, ""),
            "topic_role": item.get("topic_role", ""),
            "rank": item.get("rank", 0),
            "score": item.get("score", 0),
            "route_plan": packet.get("route_plan", {}),
            "query_strategy": packet.get("query_strategy", {}),
            "source_card": (item.get("trace") or {}).get("source_card", {}),
            "read_quality": read_quality,
            "quality_report": quality_report,
            "content_mode": _infer_content_mode(
                content,
                quality=read_quality,
                quality_report=quality_report,
                explicit_hint="partial_body" if reading else "snippet",
            ),
            "content_chars": len(_collapse_ws(content)),
            "ingest_audit": audit,
        }
        if dry_run:
            records.append(
                {
                    "url": url,
                    "title": str(item.get("title", "")),
                    "domain": _domain(url),
                    "status": "preview",
                    "chars": len(content),
                    "source_type": item.get("source_type", ""),
                    "evidence_role": item.get("evidence_role", ""),
                    "snippet": _excerpt(content, max_chars=180),
                    "audit": audit,
                }
            )
            continue
        try:
            record = add_document(url, content, title=str(item.get("title", "")), metadata=metadata, db_path=db_path)
            record["audit"] = audit
            records.append(record)
        except Exception as exc:
            records.append({"url": url, "status": "error", "error": str(exc)})
    archived_count = sum(1 for item in records if item.get("status") in {"created", "updated", "unchanged"})
    skipped_count = sum(1 for item in records if item.get("status") == "skipped")
    read_success_count = len(readings_by_url)
    timeout_budget_hint_seconds = 240 if read_attempted > 0 else 120
    timeout_recommendation = {
        "outer_timeout_seconds": timeout_budget_hint_seconds,
        "patient_wait_seconds": timeout_budget_hint_seconds,
        "retry_timeout_seconds": 300 if read_attempted > 0 else 180,
        "agent_instruction": (
            "archive ingest 是搜索、候选审计、可选读取和写库的长链路；"
            "看到 phase_log 持续推进时不要过早判定卡死。若外层超时，请先用 --dry-run 预览，"
            "或降低 --read-top，但不要把 --limit 降到 30 以下来牺牲证据池。"
        ),
        "safe_speedup": [
            "先运行 --dry-run 查看候选和审计。",
            "保持 --limit 80，必要时把 --read-top 设为 0-2。",
            "保留 --cache-ttl 3600 以减少重复请求。",
        ],
    }
    timeout_boundary = (
        "默认 search-first ingest 建议给外层 120 秒；如果开启 --read-top，或网络较弱/上游较慢，"
        "建议放宽到 180-300 秒。"
    )
    next_steps = _archive_ingest_next_steps(
        query,
        dry_run=dry_run,
        archived_count=archived_count,
        skipped_count=skipped_count,
        read_attempted=read_attempted,
        read_success_count=read_success_count,
    )
    emit_progress(
        "archive_done",
        "入库完成",
        f"archived={archived_count} skipped={skipped_count} elapsed={round(time.time() - started_at, 3)}s",
        archived_count=archived_count,
        skipped_count=skipped_count,
        read_success_count=read_success_count,
    )
    return {
        "query": query,
        "dry_run": dry_run,
        "ingest_mode": "search-first",
        "read_top": read_attempted,
        "read_backend": read_backend,
        "read_concurrency": max(read_concurrency, 1),
        "cache_ttl": max(cache_ttl, 0),
        "elapsed_sec": round(time.time() - started_at, 3),
        "packet_result_count": packet.get("result_count", 0),
        "selected_count": len(selected_items),
        "read_attempted_count": min(read_attempted, len(selected_urls)),
        "read_success_count": read_success_count,
        "skipped_count": skipped_count,
        "archived_count": archived_count,
        "audit_summary": _summarize_ingest_audits(records),
        "phase_log": phase_log,
        "timeout_budget_hint_seconds": timeout_budget_hint_seconds,
        "timeout_recommendation": timeout_recommendation,
        "timeout_boundary": timeout_boundary,
        "next_steps": next_steps,
        "records": records,
    }


def _archive_ingest_next_steps(
    query: str,
    *,
    dry_run: bool,
    archived_count: int,
    skipped_count: int,
    read_attempted: int,
    read_success_count: int,
) -> list[str]:
    """Suggest the next best action after an ingest-search run."""
    query = str(query or "").strip()
    if dry_run:
        return [
            f"预览没问题后可运行 `guanlan archive ingest-research {query!r} --limit 80` 正式写入。",
            "如果外层 Agent/MCP 容易超时，默认给 120 秒；开启 `--read-top` 时建议放宽到 180-300 秒。",
        ]
    steps: list[str] = []
    if archived_count == 0:
        steps.append("这次没有成功写入；先改用 `guanlan archive ingest-research ... --dry-run` 看候选和审计结果。")
    if skipped_count > 0:
        steps.append("若觉得跳过太多，可先复查 query/preset，或单独 `guanlan read URL --quality-report` 验证代表页面。")
    if read_attempted > 0 and read_success_count == 0:
        steps.append("代表页面读取全部失败；先 `guanlan diagnose page \"URL\"`，再决定是否改用 scoped search / structured source。")
    if not steps:
        steps.append("可继续用 `guanlan archive search` / `archive context` / `archive wiki build` 复用刚写入的资料。")
    steps.append("如果运行在外层 Agent/MCP 平台，请把这个命令的 timeout 预算显式设为 120-300 秒。")
    return steps


def audit_ingest_candidate(
    query: str,
    item: dict[str, Any],
    *,
    content: str = "",
    existing_urls: set[str] | None = None,
) -> dict[str, Any]:
    """Score one research result before it is written into the local archive.

    The audit is deliberately conservative and explainable. It should reject
    obvious drift, platform homepages, duplicate candidates, and very thin
    content, while keeping technical English terms that match a Chinese query
    (for example vLLM/SGLang in KV Cache research).
    """
    title = _collapse_ws(str(item.get("title") or ""))
    url = str(item.get("url") or "")
    snippet = _collapse_ws(str(item.get("snippet") or ""))
    normalized = _normalize_url(url)
    combined = _collapse_ws(f"{title} {url} {snippet} {content}")
    combined_lower = combined.lower()
    terms = _meaningful_query_terms(query)
    matched = _unique_terms([term for term in terms if term.lower() in combined_lower])
    reasons: list[str] = []
    score = 100

    if not normalized:
        reasons.append("missing_url")
        score -= 100
    if existing_urls and normalized in existing_urls:
        reasons.append("duplicate_candidate")
        score -= 70
    if _looks_like_platform_homepage(title, url, snippet):
        reasons.append("platform_homepage")
        score -= 80
    if len(terms) >= 3 and not matched:
        reasons.append("low_query_overlap")
        score -= 60
    if _contains_cjk(query) and not _contains_cjk(combined) and not matched:
        reasons.append("english_drift")
        score -= 45
    if content and len(_collapse_ws(content)) < ARCHIVE_MIN_USEFUL_CHARS:
        reasons.append("thin_content")
        score -= 25

    decision = "skip" if any(reason in reasons for reason in {"missing_url", "duplicate_candidate", "platform_homepage"}) else "keep"
    if score < 45:
        decision = "skip"
    return {
        "decision": decision,
        "quality_score": max(score, 0),
        "reasons": reasons,
        "query_terms": terms,
        "matched_terms": matched,
        "domain": _domain(normalized),
        "content_chars": len(content),
        "retrieval_boundary": "research-ingest-audit",
    }


def _enrich_archive_metadata(metadata: dict[str, Any], *, domain: str, content: str) -> None:
    """Attach stable source/read metadata without changing the SQLite schema."""
    try:
        from guanlan.source_taxonomy import source_card_for_domain

        if not metadata.get("source_card"):
            metadata["source_card"] = source_card_for_domain(domain).to_dict()
    except Exception:
        if not metadata.get("source_card"):
            metadata["source_card"] = {"domain": domain}
    try:
        from guanlan.web.read import assess_read_quality, build_read_quality_report

        quality = metadata.get("read_quality") if isinstance(metadata.get("read_quality"), dict) else {}
        if not quality:
            quality = assess_read_quality(content)
            metadata["read_quality"] = quality
        if not metadata.get("quality_report"):
            metadata["quality_report"] = build_read_quality_report(content, url="", quality=quality)
    except Exception:
        metadata.setdefault("read_quality", {})
        metadata.setdefault("quality_report", {})
    metadata["content_chars"] = len(_collapse_ws(content))
    metadata["content_mode"] = _infer_content_mode(
        content,
        quality=metadata.get("read_quality") if isinstance(metadata.get("read_quality"), dict) else {},
        quality_report=metadata.get("quality_report") if isinstance(metadata.get("quality_report"), dict) else {},
        explicit_hint=str(metadata.get("content_mode") or ""),
    )
    if not str(metadata.get("topic_label") or "").strip():
        metadata["topic_label"] = _derive_topic_label(
            str(metadata.get("ingest_query") or ""),
            title=_title_from_markdown(content),
            snippet=_excerpt(content, max_chars=220),
            topic_key=str(metadata.get("topic_key") or ""),
        )


def _build_topic_labels(query: str, items: list[dict[str, Any]]) -> dict[str, str]:
    """Infer human-readable topic labels for grouped ingest candidates."""
    labels: dict[str, str] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for idx, item in enumerate(items):
        raw_key = str(item.get("topic_key") or "").strip()
        group_key = raw_key or f"item-{idx}"
        grouped.setdefault(group_key, []).append(item)
    for group_key, bucket in grouped.items():
        if not _is_generic_topic_key(group_key):
            labels[group_key] = _humanize_topic_key(group_key)
            continue
        texts = " ".join(
            _collapse_ws(
                f"{item.get('title') or ''} {item.get('snippet') or ''} {item.get('source_type') or ''}"
            )
            for item in bucket
        )
        representative = bucket[0] if bucket else {}
        labels[group_key] = _derive_topic_label(
            query,
            title=str(representative.get("title") or ""),
            snippet=texts,
            topic_key=group_key,
        )
    return labels


def _is_generic_topic_key(value: str) -> bool:
    key = str(value or "").strip().lower()
    return (not key) or bool(re.fullmatch(r"topic[-_ ]?\d+", key))


def _humanize_topic_key(value: str) -> str:
    key = str(value or "").strip()
    if not key:
        return ""
    mapped = ARCHIVE_TOPIC_KEY_LABELS.get(key.lower())
    if mapped:
        return mapped
    return re.sub(r"[-_]+", " ", key).strip()


def _derive_topic_label(query: str, *, title: str = "", snippet: str = "", topic_key: str = "") -> str:
    """Choose a readable topic label instead of generic topic-N placeholders."""
    topic_key = str(topic_key or "").strip()
    if topic_key and not _is_generic_topic_key(topic_key):
        return _humanize_topic_key(topic_key)
    title_candidate = _best_topic_segment(title)
    meaningful_terms = _meaningful_query_terms(query)
    combined_lower = _collapse_ws(f"{title} {snippet}").lower()
    matched_terms = [term for term in meaningful_terms if term.lower() in combined_lower][:4]
    if matched_terms:
        joined = " ".join(matched_terms)
        if _contains_cjk(joined):
            return joined[:24].strip()
    if title_candidate:
        return title_candidate
    compact_query = " ".join(meaningful_terms[:4]).strip() or _collapse_ws(query)[:24]
    return compact_query[:24].strip() or "通用资料"


def _best_topic_segment(title: str) -> str:
    text = _collapse_ws(str(title or ""))
    if not text:
        return ""
    segments = re.split(r"[|｜\-—·•:：/]", text)
    candidates = [segment.strip(" []【】()（）") for segment in segments if segment.strip()]
    generic = {"首页", "正文", "全文", "详情", "通用网页", "官方网站"}
    for candidate in candidates:
        if candidate in generic or len(candidate) < 2:
            continue
        return candidate[:24]
    return text[:24]


def _infer_content_mode(
    content: str,
    *,
    quality: dict[str, Any] | None = None,
    quality_report: dict[str, Any] | None = None,
    explicit_hint: str = "",
) -> str:
    """Classify archive content depth for downstream context/wiki/RAG ranking."""
    hint = str(explicit_hint or "").strip().lower()
    if hint in ARCHIVE_CONTENT_MODE_RANK:
        return hint
    text = _collapse_ws(content)
    chars = len(text)
    quality = quality if isinstance(quality, dict) else {}
    quality_report = quality_report if isinstance(quality_report, dict) else {}
    usable = bool(quality_report.get("usable")) if quality_report else False
    fallback = bool(quality_report.get("fallback")) if quality_report else False
    score = _quality_score(quality) or 0
    has_markdown_heading = content.lstrip().startswith("#")
    if fallback:
        if score >= 70 and chars >= 12:
            return "partial_body"
        return "snippet"
    if chars <= 260:
        if has_markdown_heading or score >= 70 or chars >= ARCHIVE_MIN_USEFUL_CHARS:
            return "partial_body"
        return "snippet"
    if usable and (chars >= 1200 or score >= 80):
        return "full_body"
    if usable or chars >= 420:
        return "partial_body"
    return "snippet"


def search_documents(
    query: str,
    limit: int = DEFAULT_ARCHIVE_SEARCH_LIMIT,
    trace: bool = False,
    semantic: bool = False,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Search the local archive with FTS when available and LIKE fallback."""
    query = query.strip()
    if not query:
        raise ValueError("query is required")
    limit = max(limit, 1)
    with _connect(db_path) as conn:
        if semantic:
            semantic_records = _search_semantic(conn, query, limit)
            if semantic_records:
                return semantic_records
        rows: list[sqlite3.Row] = []
        seen: set[int] = set()
        for row in _search_fts(conn, query, limit):
            seen.add(int(row["id"]))
            rows.append(row)
        if len(rows) < limit:
            for row in _search_like(conn, query, limit * 4):
                row_id = int(row["id"])
                if row_id in seen:
                    continue
                seen.add(row_id)
                rows.append(row)
                if len(rows) >= limit:
                    break
    return [_row_to_record(row, query=query, trace=trace) for row in rows[:limit]]


def archive_search_diagnostics(
    query: str,
    *,
    records: list[dict[str, Any]] | None = None,
    semantic: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return retrieval diagnostics for local archive search."""
    stats = archive_stats(db_path=db_path)
    query_terms = _query_terms(query)[:16]
    record_count = len(records or [])
    index = stats.get("index") if isinstance(stats.get("index"), dict) else {}
    guidance = []
    if not stats.get("exists") or not stats.get("documents"):
        guidance.append("本地库为空；先运行 `guanlan archive add URL` 或 `guanlan archive ingest-research \"关键词\"`。")
    elif record_count == 0:
        guidance.append("本地库有文档但本次无命中；可运行 `guanlan archive list` 看已有主题，或改用更短关键词。")
        guidance.append("如怀疑索引异常，运行 `guanlan archive verify` 或 `guanlan archive reindex`。")
    return {
        "query": query,
        "query_terms": query_terms,
        "documents": stats.get("documents", 0),
        "content_chars": stats.get("content_chars", 0),
        "index": index,
        "results": record_count,
        "retrieval": "semantic+sqlite-fts5+like" if semantic else "sqlite-fts5+like",
        "retrieval_mode": "semantic" if semantic else "fts",
        "semantic": index.get("semantic", "not-vector"),
        "guidance": guidance,
    }


def embed_archive(
    *,
    backend: str = "local",
    db_path: str | Path | None = None,
    limit: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Build an explicit local semantic sidecar over existing archive rows."""

    backend = (backend or "local").strip().lower()
    if backend not in {"local", "ollama", "openai"}:
        backend = "local"
    if backend in {"ollama", "openai"}:
        return {
            "status": "planned",
            "backend": backend,
            "embedded": 0,
            "boundary": "外部 embedding 后端尚未默认启用；请先用 backend=local 建本地轻量索引，或后续配置专用 provider。",
            "next_steps": ["guanlan archive embed --backend local"],
        }
    path = _db_path(db_path)
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT id, title, content, url, domain, content_hash FROM documents ORDER BY updated_at DESC LIMIT ?",
            (max(limit, 1),),
        ).fetchall()
        if dry_run:
            return {
                "status": "preview",
                "backend": backend,
                "documents": len(rows),
                "embedded": 0,
                "path": str(path),
                "boundary": "dry-run 未写入 archive_embeddings。",
            }
        embedded = 0
        for row in rows:
            vector = _local_embedding(" ".join([str(row["title"]), str(row["domain"]), str(row["content"])]))
            conn.execute(
                """
                INSERT OR REPLACE INTO archive_embeddings
                    (document_id, backend, model, vector_json, content_hash, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["id"]),
                    backend,
                    "guanlan-local-lexical-v1",
                    json.dumps(vector, ensure_ascii=False),
                    str(row["content_hash"]),
                    time.time(),
                ),
            )
            embedded += 1
        conn.execute("INSERT OR REPLACE INTO archive_meta (key, value) VALUES ('semantic', 'local')")
        conn.commit()
    return {
        "status": "ok",
        "backend": backend,
        "model": "guanlan-local-lexical-v1",
        "documents": len(rows),
        "embedded": embedded,
        "path": str(path),
        "boundary": "显式本地轻量语义侧车；不联网、不替代 FTS，search/context 仍保留来源和质量元数据。",
    }


def list_documents(limit: int = DEFAULT_ARCHIVE_LIST_LIMIT, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """List recently updated archive documents."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM documents
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (max(limit, 1),),
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def inspect_document(identifier: str, db_path: str | Path | None = None) -> dict[str, Any]:
    """Return one archived document by id or URL, including content and diagnostics."""
    value = str(identifier or "").strip()
    if not value:
        raise ValueError("identifier is required")
    with _connect(db_path) as conn:
        if value.isdigit():
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (int(value),)).fetchone()
        else:
            normalized = _normalize_url(value)
            row = conn.execute(
                "SELECT * FROM documents WHERE url = ? OR url_hash = ?",
                (normalized, hashlib.sha256(normalized.encode("utf-8")).hexdigest()),
            ).fetchone()
        snapshot_count = 0
        passage_count = 0
        if row:
            snapshot_count = int(conn.execute(
                "SELECT COUNT(*) AS count FROM document_snapshots WHERE document_id = ?", (int(row["id"]),)
            ).fetchone()["count"])
            current_snapshot_id = str(row["current_snapshot_id"] or "")
            if current_snapshot_id:
                passage_count = int(conn.execute(
                    "SELECT COUNT(*) AS count FROM passages WHERE snapshot_id = ?", (current_snapshot_id,)
                ).fetchone()["count"])
    if not row:
        raise ValueError(f"archive document not found: {identifier}")
    record = _row_to_record(row, include_content=True, rag=True)
    content = str(record.get("content") or "")
    record["diagnostics"] = {
        "chars": len(content),
        "content_hash": record.get("content_hash", ""),
        "has_content": bool(content.strip()),
        "metadata_keys": sorted((record.get("metadata") or {}).keys()),
        "snapshot_count": snapshot_count,
        "passage_count": passage_count,
    }
    record["snapshot_count"] = snapshot_count
    record["passage_count"] = passage_count
    return record


def list_document_snapshots(identifier: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """List append-only snapshots for one archive document, newest first."""
    document = inspect_document(identifier, db_path=db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT s.*, COUNT(p.passage_id) AS passage_count
            FROM document_snapshots s
            LEFT JOIN passages p ON p.snapshot_id = s.snapshot_id
            WHERE s.document_id = ?
            GROUP BY s.snapshot_id
            ORDER BY s.observed_at DESC, s.created_at DESC
            """, (int(document["id"]),),
        ).fetchall()
    return [_snapshot_row_to_record(row) for row in rows]


def inspect_snapshot(snapshot_id: str, db_path: str | Path | None = None) -> dict[str, Any]:
    """Return one immutable archive snapshot including its stored body."""
    value = str(snapshot_id or "").strip()
    if not value:
        raise ValueError("snapshot_id is required")
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT s.*, d.url, COUNT(p.passage_id) AS passage_count
            FROM document_snapshots s
            JOIN documents d ON d.id = s.document_id
            LEFT JOIN passages p ON p.snapshot_id = s.snapshot_id
            WHERE s.snapshot_id = ?
            GROUP BY s.snapshot_id
            """, (value,),
        ).fetchone()
    if not row:
        raise ValueError(f"archive snapshot not found: {snapshot_id}")
    return _snapshot_row_to_record(row, include_content=True)


def list_snapshot_passages(snapshot_id: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return stable, offset-addressable passages for one snapshot."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM passages WHERE snapshot_id = ? ORDER BY ordinal ASC",
            (str(snapshot_id or "").strip(),),
        ).fetchall()
    return [_passage_row_to_record(row) for row in rows]


def compare_snapshots(
    before_snapshot_id: str,
    after_snapshot_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return deterministic text and conservative claim changes for two snapshots."""
    from guanlan.temporal import build_claim_delta, build_snapshot_diff

    before = inspect_snapshot(before_snapshot_id, db_path=db_path)
    after = inspect_snapshot(after_snapshot_id, db_path=db_path)
    return {
        "schema_version": "snapshot_comparison_v1",
        "snapshot_diff": build_snapshot_diff(before, after),
        "claim_delta": build_claim_delta(before, after),
    }


def list_change_events(
    *,
    identifier: str | None = None,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List append-only snapshot change events, newest first."""
    document_id: int | None = None
    if identifier:
        document_id = int(inspect_document(identifier, db_path=db_path)["id"])
    with _connect(db_path) as conn:
        if document_id is None:
            rows = conn.execute(
                "SELECT * FROM change_events ORDER BY created_at DESC, event_id DESC LIMIT ?",
                (max(int(limit), 1),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM change_events WHERE document_id=? ORDER BY created_at DESC, event_id DESC LIMIT ?",
                (document_id, max(int(limit), 1)),
            ).fetchall()
    return [_change_event_record(row) for row in rows]


def replace_snapshot_passages(
    snapshot_id: str,
    passages: list[dict[str, Any]],
    *,
    db_path: str | Path | None = None,
) -> int:
    """Replace passages for a newly-created attachment snapshot.

    This is intentionally strict: an immutable snapshot that already has
    non-generic locators cannot be rewritten.
    """
    value = str(snapshot_id or "").strip()
    if not value:
        raise ValueError("snapshot_id is required")
    with _connect(db_path) as conn:
        exists = conn.execute(
            "SELECT snapshot_id FROM document_snapshots WHERE snapshot_id=?", (value,)
        ).fetchone()
        if not exists:
            raise ValueError(f"archive snapshot not found: {snapshot_id}")
        specialized = conn.execute(
            "SELECT COUNT(*) AS count FROM passages WHERE snapshot_id=? AND locator_type!='text'", (value,)
        ).fetchone()
        if specialized and int(specialized["count"]) > 0:
            return int(conn.execute(
                "SELECT COUNT(*) AS count FROM passages WHERE snapshot_id=?", (value,)
            ).fetchone()["count"])
        conn.execute("DELETE FROM passages WHERE snapshot_id=?", (value,))
        for ordinal, passage in enumerate(passages):
            text = str(passage.get("text") or "").strip()
            if not text:
                continue
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            passage_id = str(passage.get("passage_id") or "")
            if not passage_id:
                from guanlan.evidence_kernel import stable_id

                passage_id = stable_id(
                    "psg", value, passage.get("locator_type"), passage.get("page_number"),
                    passage.get("table_id"), passage.get("row_index"), passage.get("column_index"), text_hash,
                )
            conn.execute(
                """
                INSERT INTO passages (
                    passage_id,snapshot_id,ordinal,heading_path_json,char_start,char_end,text,text_hash,
                    locator_type,page_number,table_id,row_index,column_index,attachment_parent_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    passage_id, value, ordinal, json.dumps(passage.get("heading_path") or [], ensure_ascii=False),
                    int(passage.get("char_start") or 0), int(passage.get("char_end") or len(text)), text,
                    text_hash, str(passage.get("locator_type") or "text"), passage.get("page_number"),
                    str(passage.get("table_id") or ""), passage.get("row_index"), passage.get("column_index"),
                    str(passage.get("attachment_parent_id") or ""),
                ),
            )
        conn.commit()
        row = conn.execute("SELECT COUNT(*) AS count FROM passages WHERE snapshot_id=?", (value,)).fetchone()
    return int(row["count"])


def remove_document(identifier: str, db_path: str | Path | None = None) -> dict[str, Any]:
    """Remove one archived document by id or URL."""
    record = inspect_document(identifier, db_path=db_path)
    doc_id = int(record["id"])
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        if _has_fts(conn):
            try:
                conn.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
            except sqlite3.OperationalError:
                conn.execute("INSERT OR REPLACE INTO archive_meta (key, value) VALUES ('fts', '0')")
        conn.commit()
    return {"id": doc_id, "status": "removed", "url": record.get("url", ""), "title": record.get("title", "")}


def reindex_archive(db_path: str | Path | None = None) -> dict[str, Any]:
    """Rebuild the SQLite FTS index from stored documents."""
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT id, title, content, url, domain FROM documents ORDER BY id ASC").fetchall()
        fts_available = _has_fts(conn)
        if fts_available:
            conn.execute("DELETE FROM documents_fts")
            for row in rows:
                conn.execute(
                    "INSERT INTO documents_fts (rowid, title, content, url, domain) VALUES (?, ?, ?, ?, ?)",
                    (int(row["id"]), row["title"], row["content"], row["url"], row["domain"]),
                )
            conn.execute("INSERT OR REPLACE INTO archive_meta (key, value) VALUES ('fts', '1')")
            conn.commit()
    return {
        "status": "ok" if fts_available else "warn",
        "documents": len(rows),
        "fts": "enabled" if fts_available else "unavailable",
        "message": "FTS index rebuilt" if fts_available else "SQLite FTS5 unavailable; LIKE fallback will be used",
    }


def verify_archive(
    *,
    db_path: str | Path | None = None,
    limit: int = 8,
    min_quality: int = 60,
) -> dict[str, Any]:
    """Verify archive index health, content quality, and basic recall."""
    stats = archive_stats(db_path=db_path)
    quality = archive_quality_summary(db_path=db_path, rag_min_quality=min_quality)
    path = _db_path(db_path)
    if not stats.get("exists") or not stats.get("documents"):
        return {
            "status": "empty",
            "path": str(path),
            "documents": 0,
            "issues": ["archive_empty"],
            "checks": {
                "index_consistency": "skipped",
                "content_presence": "skipped",
                "sample_recall": "skipped",
            },
            "quality": quality,
            "recall_samples": [],
            "next_steps": ["用 `guanlan archive add URL` 或 `guanlan archive ingest-research \"关键词\"` 添加资料。"],
        }

    with _connect(db_path) as conn:
        document_count = int(conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"])
        empty_content = int(
            conn.execute("SELECT COUNT(*) AS count FROM documents WHERE TRIM(content) = ''").fetchone()["count"]
        )
        fts_enabled = _has_fts(conn)
        fts_count = 0
        if fts_enabled:
            try:
                fts_count = int(conn.execute("SELECT COUNT(*) AS count FROM documents_fts").fetchone()["count"])
            except sqlite3.OperationalError:
                fts_count = -1
        rows = conn.execute(
            """
            SELECT id, title, content, url, domain
            FROM documents
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (max(limit, 1),),
        ).fetchall()

    recall_samples = []
    recall_failures = 0
    for row in rows:
        probes = _verification_probe_terms(str(row["title"] or ""), str(row["content"] or ""))
        if not probes:
            recall_samples.append({"id": row["id"], "title": row["title"], "status": "skipped", "probes": []})
            continue
        recalled = False
        for probe in probes:
            hits = search_documents(probe, limit=10, db_path=db_path)
            if any(int(hit.get("id", -1)) == int(row["id"]) for hit in hits):
                recalled = True
                break
        if not recalled:
            recall_failures += 1
        recall_samples.append(
            {
                "id": row["id"],
                "title": row["title"],
                "status": "ok" if recalled else "fail",
                "probes": probes,
            }
        )

    issues = []
    if fts_enabled and fts_count != document_count:
        issues.append("fts_document_count_mismatch")
    if empty_content:
        issues.append("empty_content")
    if recall_failures:
        issues.append("sample_recall_failed")
    if quality.get("low_quality", 0):
        issues.append("low_quality_documents")

    critical = {"fts_document_count_mismatch", "empty_content", "sample_recall_failed"}
    status = "fail" if critical & set(issues) else "warn" if issues else "ok"
    next_steps = []
    if "fts_document_count_mismatch" in issues or "sample_recall_failed" in issues:
        next_steps.append("运行 `guanlan archive reindex` 后再执行 `guanlan archive verify`。")
    if "low_quality_documents" in issues:
        next_steps.append("导出 RAG/Wiki 时使用 `--min-quality`，或重新读取低质量页面。")
    if not next_steps:
        next_steps.append("Archive 基础检索和导出状态正常。")

    return {
        "status": status,
        "path": str(path),
        "documents": document_count,
        "issues": issues,
        "checks": {
            "index_consistency": "ok" if not (fts_enabled and fts_count != document_count) else "fail",
            "content_presence": "ok" if empty_content == 0 else "fail",
            "sample_recall": "ok" if recall_failures == 0 else "fail",
        },
        "index": {
            "fts": "enabled" if fts_enabled else "unavailable",
            "fts_documents": fts_count,
            "documents": document_count,
            "semantic": "not-vector",
        },
        "quality": quality,
        "recall_samples": recall_samples,
        "next_steps": next_steps,
    }


def format_archive_verify(report: dict[str, Any]) -> str:
    """Render archive verification as Markdown."""
    lines = [
        "# 观澜本地知识库体检",
        "",
        f"- 状态: {report.get('status', '')}",
        f"- 路径: {report.get('path', '')}",
        f"- 文档数: {report.get('documents', 0)}",
    ]
    issues = report.get("issues") or []
    lines.append("- 问题: " + (", ".join(issues) if issues else "无"))
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    if checks:
        lines.extend(["", "## 检查项"])
        for key, value in checks.items():
            lines.append(f"- {key}: {value}")
    index = report.get("index") if isinstance(report.get("index"), dict) else {}
    if index:
        lines.extend(
            [
                "",
                "## 索引",
                f"- FTS: {index.get('fts', '')}",
                f"- FTS 文档数: {index.get('fts_documents', 0)} / {index.get('documents', 0)}",
                f"- 语义边界: {index.get('semantic', 'not-vector')}",
            ]
        )
    quality = report.get("quality") if isinstance(report.get("quality"), dict) else {}
    if quality:
        lines.extend(
            [
                "",
                "## RAG / Wiki 就绪",
                f"- RAG-ready: {quality.get('rag_ready', 0)} / {quality.get('documents', 0)}",
                f"- 平均阅读质量: {quality.get('average_read_quality', 0)}",
                f"- 低质量文档: {quality.get('low_quality', 0)}",
            ]
        )
    samples = report.get("recall_samples") or []
    if samples:
        lines.extend(["", "## 召回样本"])
        for item in samples[:12]:
            probes = ", ".join(item.get("probes") or [])
            lines.append(f"- [{item.get('status')}] #{item.get('id')} {item.get('title')} / probes: {probes}")
    next_steps = report.get("next_steps") or []
    if next_steps:
        lines.extend(["", "## 下一步"])
        lines.extend(f"- {step}" for step in next_steps)
    lines.extend(
        [
            "",
            "## Agent 提示",
            "- 如果用户要长期记忆、AI Agent Wiki、RAG 或本地模型上下文，先确认本体检结果，再用 `archive context`、`archive wiki context` 或 `archive pack`。",
            "- Archive/Wiki 只基于本地已归档材料；不要把无命中解释为全网没有证据。",
        ]
    )
    return "\n".join(lines)


def export_documents(
    db_path: str | Path | None = None,
    *,
    domain: str | None = None,
    source_type: str | None = None,
    topic: str | None = None,
    min_quality: int | None = None,
) -> list[dict[str, Any]]:
    """Return all archive documents for JSONL/Markdown export."""
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY updated_at DESC, id DESC").fetchall()
    records = [_row_to_record(row, include_content=True, rag=True) for row in rows]
    filtered = [
        record for record in records
        if _export_filter(
            record,
            domain=domain,
            source_type=source_type,
            topic=topic,
            min_quality=min_quality,
        )
    ]
    return sorted(filtered, key=_archive_record_priority, reverse=True)


def export_record_for_profile(record: dict[str, Any], profile: str = "jsonl") -> dict[str, Any]:
    """Map one archive record to a common RAG/loader JSONL profile."""
    normalized = (profile or "jsonl").lower()
    metadata = _rag_metadata(record)
    content = str(record.get("content") or "")
    if normalized == "rag-jsonl":
        return dict(record.get("rag") or {})
    if normalized == "llamaindex-jsonl":
        return {"text": content, "metadata": metadata}
    if normalized == "langchain-jsonl":
        return {"page_content": content, "metadata": metadata}
    if normalized == "openwebui-jsonl":
        return {
            "content": content,
            "title": record.get("title", ""),
            "source": record.get("url", ""),
            "metadata": metadata,
        }
    return record


def format_archive_export_jsonl(records: list[dict[str, Any]], profile: str = "jsonl") -> str:
    """Render archive records as one JSON object per line."""
    return "\n".join(
        json.dumps(export_record_for_profile(record, profile), ensure_ascii=False, sort_keys=True)
        for record in records
    )


def archive_stats(db_path: str | Path | None = None) -> dict[str, Any]:
    """Return archive counts and domain distribution."""
    path = _db_path(db_path)
    if not path.exists():
        return {"path": str(path), "exists": False, "documents": 0, "domains": []}
    with _connect(path) as conn:
        count = int(conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"])
        content_chars = int(conn.execute("SELECT COALESCE(SUM(LENGTH(content)), 0) AS chars FROM documents").fetchone()["chars"])
        schema_row = conn.execute("SELECT value FROM archive_meta WHERE key = 'schema_version'").fetchone()
        fts_enabled = _has_fts(conn)
        fts_count = 0
        if fts_enabled:
            try:
                fts_count = int(conn.execute("SELECT COUNT(*) AS count FROM documents_fts").fetchone()["count"])
            except sqlite3.OperationalError:
                fts_count = 0
        semantic_count = int(conn.execute("SELECT COUNT(*) AS count FROM archive_embeddings").fetchone()["count"])
        semantic_row = conn.execute("SELECT value FROM archive_meta WHERE key = 'semantic'").fetchone()
        domains = conn.execute(
            """
            SELECT domain, COUNT(*) AS count
            FROM documents
            GROUP BY domain
            ORDER BY count DESC, domain ASC
            LIMIT 20
            """
        ).fetchall()
    return {
        "path": str(path),
        "exists": path.exists(),
        "documents": count,
        "content_chars": content_chars,
        "schema_version": schema_row["value"] if schema_row else "",
        "index": {
            "type": "sqlite-fts5+like",
            "fts": "enabled" if fts_enabled else "unavailable",
            "fts_documents": fts_count,
            "fallback": "LIKE",
            "semantic": semantic_row["value"] if semantic_row else "not-vector",
            "semantic_documents": semantic_count,
        },
        "domains": [{"domain": row["domain"], "count": int(row["count"])} for row in domains],
    }


def archive_quality_summary(
    db_path: str | Path | None = None,
    *,
    rag_min_quality: int = 60,
) -> dict[str, Any]:
    """Summarize archive read quality and RAG readiness without changing schema."""
    records = export_documents(db_path=db_path)
    labels: dict[str, int] = {}
    scores: list[float] = []
    with_quality = 0
    with_ingest_audit = 0
    low_quality = 0
    rag_ready = 0
    for record in records:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        quality = metadata.get("read_quality") if isinstance(metadata.get("read_quality"), dict) else {}
        audit = metadata.get("ingest_audit") if isinstance(metadata.get("ingest_audit"), dict) else {}
        score = _quality_score(quality)
        if quality:
            with_quality += 1
            label = str(quality.get("label") or quality.get("status") or "unknown")
            labels[label] = labels.get(label, 0) + 1
        if audit:
            with_ingest_audit += 1
        if score is not None:
            scores.append(score)
            if score < rag_min_quality:
                low_quality += 1
        content = str(record.get("content") or "")
        if content.strip() and record.get("url") and (score is None or score >= rag_min_quality):
            rag_ready += 1
    average = round(sum(scores) / len(scores), 1) if scores else 0
    return {
        "documents": len(records),
        "with_read_quality": with_quality,
        "with_ingest_audit": with_ingest_audit,
        "average_read_quality": average,
        "labels": labels,
        "low_quality": low_quality,
        "rag_ready": rag_ready,
        "rag_min_quality": rag_min_quality,
        "principle": "Archive 先保留来源身份和正文质量，再进入 RAG；低分材料不默认丢弃，但可在导出时过滤。",
    }


def format_archive_markdown(records: list[dict[str, Any]], title: str = "观澜本地知识库") -> str:
    """Render archive records as Markdown."""
    lines = [f"# {title}", ""]
    if not records:
        lines.append("暂无本地归档结果。")
        lines.append("可以先用 `guanlan archive list` 确认已有文档，或用 `guanlan archive ingest-research \"关键词\"` 联网研究并入库。")
        return "\n".join(lines)
    for idx, item in enumerate(records, start=1):
        item_title = _collapse_ws(str(item.get("title", "")))
        lines.append(f"{idx}. [{item.get('domain', 'unknown')}] {item_title}")
        lines.append(f"   {item.get('url', '')}")
        excerpt = _collapse_ws(str(item.get("excerpt", "")))
        if excerpt:
            lines.append(f"   {excerpt[:240]}")
    return "\n".join(lines)


def format_archive_context(records: list[dict[str, Any]], title: str = "观澜本地知识库上下文") -> str:
    """Render archive records as compact prompt context."""
    lines = [
        f"# {title}",
        "",
        "Agent 提示：这是本地 archive 记忆层，只反映已归档资料；给本地模型/RAG/Wiki 用时，先说明这个边界。",
        "",
        "来源 | 主题 | 内容层级 | 标题 | 摘要 | 时间",
        "--- | --- | --- | --- | --- | ---",
    ]
    if not records:
        lines.append("无结果 | - | - | - | 可先运行 `guanlan archive list` 确认本地库，或用 `guanlan archive ingest-research` 联网研究并入库。 | -")
        return "\n".join(lines)
    for item in records:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        domain = _pipe_safe(str(item.get("domain", "unknown")))
        topic_label = _pipe_safe(str(item.get("topic_label") or metadata.get("topic_label") or metadata.get("topic_key") or "-"))
        content_mode = _pipe_safe(str(item.get("content_mode") or metadata.get("content_mode") or "unknown"))
        title_text = _pipe_safe(_collapse_ws(str(item.get("title", ""))))
        excerpt = _pipe_safe(_collapse_ws(str(item.get("excerpt", "")))[:160])
        updated = _format_time(float(item.get("updated_at", 0) or 0))
        url = str(item.get("url", ""))
        lines.append(f"{domain} | {topic_label} | {content_mode} | [{title_text}]({url}) | {excerpt} | {updated}")
    return "\n".join(lines)


def format_archive_stats(stats: dict[str, Any]) -> str:
    """Render archive stats as Markdown."""
    lines = ["# 观澜本地知识库状态", "", f"- 路径: {stats.get('path', '')}", f"- 文档数: {stats.get('documents', 0)}"]
    index = stats.get("index") or {}
    if index:
        lines.extend(
            [
                f"- 正文字符数: {stats.get('content_chars', 0)}",
                f"- 索引: {index.get('type', '')} / FTS={index.get('fts', '')} / fallback={index.get('fallback', '')}",
                f"- 语义边界: {index.get('semantic', '')}",
            ]
        )
    quality = stats.get("quality") if isinstance(stats.get("quality"), dict) else {}
    if quality:
        lines.extend(
            [
                "",
                "## 质量概览",
                f"- 有阅读质量元数据: {quality.get('with_read_quality', 0)} / {quality.get('documents', 0)}",
                f"- 平均阅读质量: {quality.get('average_read_quality', 0)}",
                f"- RAG-ready 文档: {quality.get('rag_ready', 0)}",
                f"- 低于导出阈值: {quality.get('low_quality', 0)}",
                f"- 原则: {quality.get('principle', '')}",
            ]
        )
        labels = quality.get("labels") if isinstance(quality.get("labels"), dict) else {}
        if labels:
            lines.append("- 质量标签: " + ", ".join(f"{key}={value}" for key, value in sorted(labels.items())))
    domains = stats.get("domains", [])
    if domains:
        lines.extend(["", "## 域名分布"])
        max_count = max(int(item.get("count", 0)) for item in domains) or 1
        for item in domains:
            count = int(item.get("count", 0))
            bar = "#" * max(1, round(count / max_count * 24))
            lines.append(f"- {item.get('domain', 'unknown')} {bar} ({count})")
    return "\n".join(lines)


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_schema(conn)
    return conn


def _db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path).expanduser() if db_path else archive_db_path()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS archive_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            url_hash TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            domain TEXT NOT NULL,
            content TEXT NOT NULL,
            excerpt TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            added_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            current_snapshot_id TEXT
        )
        """
    )
    columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "current_snapshot_id" not in columns:
        conn.execute("ALTER TABLE documents ADD COLUMN current_snapshot_id TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            document_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            observed_at REAL NOT NULL,
            last_observed_at REAL NOT NULL,
            created_at REAL NOT NULL,
            previous_snapshot_id TEXT NOT NULL DEFAULT '',
            UNIQUE(document_id, content_hash),
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS passages (
            passage_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            heading_path_json TEXT NOT NULL DEFAULT '[]',
            char_start INTEGER NOT NULL,
            char_end INTEGER NOT NULL,
            text TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            locator_type TEXT NOT NULL DEFAULT 'text',
            page_number INTEGER,
            table_id TEXT NOT NULL DEFAULT '',
            row_index INTEGER,
            column_index INTEGER,
            attachment_parent_id TEXT NOT NULL DEFAULT '',
            UNIQUE(snapshot_id, ordinal),
            FOREIGN KEY(snapshot_id) REFERENCES document_snapshots(snapshot_id) ON DELETE CASCADE
        )
        """
    )
    passage_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(passages)").fetchall()}
    for name, definition in (
        ("locator_type", "TEXT NOT NULL DEFAULT 'text'"),
        ("page_number", "INTEGER"),
        ("table_id", "TEXT NOT NULL DEFAULT ''"),
        ("row_index", "INTEGER"),
        ("column_index", "INTEGER"),
        ("attachment_parent_id", "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in passage_columns:
            conn.execute(f"ALTER TABLE passages ADD COLUMN {name} {definition}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_document_snapshots_document ON document_snapshots(document_id, observed_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_passages_snapshot ON passages(snapshot_id, ordinal)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_passages_locator ON passages(snapshot_id, locator_type, page_number)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS change_events (
            event_id TEXT PRIMARY KEY,
            document_id INTEGER NOT NULL,
            before_snapshot_id TEXT NOT NULL,
            after_snapshot_id TEXT NOT NULL,
            summary_json TEXT NOT NULL DEFAULT '{}',
            claim_delta_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            UNIQUE(before_snapshot_id, after_snapshot_id),
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY(before_snapshot_id) REFERENCES document_snapshots(snapshot_id) ON DELETE CASCADE,
            FOREIGN KEY(after_snapshot_id) REFERENCES document_snapshots(snapshot_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_change_events_document ON change_events(document_id, created_at DESC)")
    _migrate_legacy_snapshots(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS archive_embeddings (
            document_id INTEGER PRIMARY KEY,
            backend TEXT NOT NULL,
            model TEXT NOT NULL,
            vector_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
        """
    )
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
            USING fts5(title, content, url, domain)
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO archive_meta (key, value) VALUES ('fts', '1')"
        )
    except sqlite3.OperationalError:
        conn.execute(
            "INSERT OR REPLACE INTO archive_meta (key, value) VALUES ('fts', '0')"
        )
    conn.execute(
        "INSERT OR REPLACE INTO archive_meta (key, value) VALUES ('schema_version', ?)",
        (str(ARCHIVE_SCHEMA_VERSION),),
    )
    conn.commit()


def _upsert_fts(conn: sqlite3.Connection, doc_id: int, title: str, content: str, url: str, domain: str) -> None:
    if not _has_fts(conn):
        return
    try:
        conn.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
        conn.execute(
            "INSERT INTO documents_fts (rowid, title, content, url, domain) VALUES (?, ?, ?, ?, ?)",
            (doc_id, title, content, url, domain),
        )
    except sqlite3.OperationalError:
        conn.execute("INSERT OR REPLACE INTO archive_meta (key, value) VALUES ('fts', '0')")


def _migrate_legacy_snapshots(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT * FROM documents WHERE current_snapshot_id IS NULL OR current_snapshot_id = '' ORDER BY id ASC"
    ).fetchall()
    for row in rows:
        try:
            metadata = json.loads(str(row["metadata_json"] or "{}"))
        except json.JSONDecodeError:
            metadata = {}
        snapshot_id, _, _ = _ensure_document_snapshot(
            conn,
            document_id=int(row["id"]), url=str(row["url"]), title=str(row["title"]),
            content=str(row["content"]), content_hash=str(row["content_hash"]), metadata=metadata,
            observed_at=float(row["added_at"]), last_observed_at=float(row["updated_at"]),
        )
        conn.execute("UPDATE documents SET current_snapshot_id = ? WHERE id = ?", (snapshot_id, int(row["id"])))


def _ensure_document_snapshot(
    conn: sqlite3.Connection, *, document_id: int, url: str, title: str, content: str,
    content_hash: str, metadata: dict[str, Any], observed_at: float,
    last_observed_at: float | None = None, previous_snapshot_id: str = "",
) -> tuple[str, str, int]:
    snapshot = build_document_snapshot(
        url=url, content=content, title=title, metadata=metadata,
        observed_at=observed_at, previous_snapshot_id=previous_snapshot_id,
    )
    snapshot_id = str(snapshot["snapshot_id"])
    existing = conn.execute(
        "SELECT snapshot_id FROM document_snapshots WHERE document_id = ? AND content_hash = ?",
        (document_id, content_hash),
    ).fetchone()
    if existing:
        snapshot_id = str(existing["snapshot_id"])
        conn.execute("UPDATE document_snapshots SET last_observed_at = ? WHERE snapshot_id = ?",
                     (float(last_observed_at or observed_at), snapshot_id))
        status = "unchanged"
    else:
        conn.execute(
            """
            INSERT INTO document_snapshots (
                snapshot_id, document_id, title, content, content_hash, metadata_json,
                observed_at, last_observed_at, created_at, previous_snapshot_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (snapshot_id, document_id, title, content, content_hash,
             json.dumps(metadata, ensure_ascii=False, sort_keys=True), float(observed_at),
             float(last_observed_at or observed_at), time.time(), previous_snapshot_id),
        )
        status = "created"
    passage_count = int(conn.execute(
        "SELECT COUNT(*) AS count FROM passages WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()["count"])
    if passage_count == 0:
        for passage in build_passages({"snapshot_id": snapshot_id}, content):
            conn.execute(
                """
                INSERT OR IGNORE INTO passages (
                    passage_id, snapshot_id, ordinal, heading_path_json,
                    char_start, char_end, text, text_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (passage["passage_id"], snapshot_id, passage["ordinal"],
                 json.dumps(passage["heading_path"], ensure_ascii=False), passage["char_start"],
                 passage["char_end"], passage["text"], passage["text_hash"]),
            )
        passage_count = int(conn.execute(
            "SELECT COUNT(*) AS count FROM passages WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()["count"])
    return snapshot_id, status, passage_count


def _ensure_change_event(
    conn: sqlite3.Connection,
    *,
    document_id: int,
    before_snapshot_id: str,
    after_snapshot_id: str,
    created_at: float,
) -> None:
    if not before_snapshot_id or not after_snapshot_id or before_snapshot_id == after_snapshot_id:
        return
    from guanlan.evidence_kernel import stable_id
    from guanlan.temporal import build_claim_delta, build_snapshot_diff

    before = conn.execute("SELECT * FROM document_snapshots WHERE snapshot_id=?", (before_snapshot_id,)).fetchone()
    after = conn.execute("SELECT * FROM document_snapshots WHERE snapshot_id=?", (after_snapshot_id,)).fetchone()
    if not before or not after:
        return
    before_record = _snapshot_row_to_record(before, include_content=True)
    after_record = _snapshot_row_to_record(after, include_content=True)
    diff = build_snapshot_diff(before_record, after_record)
    claim_delta = build_claim_delta(before_record, after_record)
    conn.execute(
        """
        INSERT OR IGNORE INTO change_events (
            event_id,document_id,before_snapshot_id,after_snapshot_id,summary_json,claim_delta_json,created_at
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (
            stable_id("evt", document_id, before_snapshot_id, after_snapshot_id), document_id,
            before_snapshot_id, after_snapshot_id, json.dumps(diff, ensure_ascii=False, sort_keys=True),
            json.dumps(claim_delta, ensure_ascii=False, sort_keys=True), created_at,
        ),
    )


def _has_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM archive_meta WHERE key = 'fts'").fetchone()
    return bool(row and row["value"] == "1")


def _has_semantic(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) AS count FROM archive_embeddings").fetchone()
    return bool(row and int(row["count"]) > 0)


def _search_semantic(conn: sqlite3.Connection, query: str, limit: int) -> list[dict[str, Any]]:
    if not _has_semantic(conn):
        return []
    query_vec = _local_embedding(query)
    rows = conn.execute(
        """
        SELECT d.*, e.vector_json, e.backend, e.model
        FROM archive_embeddings e
        JOIN documents d ON d.id = e.document_id
        ORDER BY d.updated_at DESC
        LIMIT 1000
        """
    ).fetchall()
    scored: list[tuple[float, sqlite3.Row]] = []
    for row in rows:
        try:
            vector = [float(item) for item in json.loads(str(row["vector_json"]))]
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        score = _cosine_similarity(query_vec, vector)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    records: list[dict[str, Any]] = []
    for score, row in scored[: max(limit, 1)]:
        record = _row_to_record(row, query=query, trace=True)
        record["semantic_score"] = round(score, 4)
        record["retrieval_mode"] = "semantic"
        trace = record.get("search_trace") if isinstance(record.get("search_trace"), dict) else {}
        trace["semantic"] = "local-lexical"
        trace["retrieval"] = "semantic+sqlite-fts5+like"
        record["search_trace"] = trace
        records.append(record)
    return records


def _search_fts(conn: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    if not _has_fts(conn):
        return []
    fts_query = _fts_query(query)
    if not fts_query:
        return []
    try:
        return conn.execute(
            """
            SELECT d.*, bm25(documents_fts) AS rank
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ?
            ORDER BY rank ASC, d.updated_at DESC
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def _search_like(conn: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    terms = _query_terms(query)[:16]
    if not terms:
        return []
    clauses = []
    where_params: list[str] = []
    score_parts = []
    score_params: list[str] = []
    for term in terms:
        like = f"%{term}%"
        clauses.append("(title LIKE ? OR content LIKE ? OR url LIKE ? OR domain LIKE ?)")
        where_params.extend([like, like, like, like])
        # Keep local search broad enough for Chinese phrases and technical
        # terms, but rank title/domain hits above body-only incidental mentions.
        for column, weight in (("title", 8), ("domain", 2), ("url", 2), ("content", 3)):
            score_parts.append(f"CASE WHEN {column} LIKE ? THEN {weight} ELSE 0 END")
            score_params.append(like)
    where = " OR ".join(clauses)
    score_expr = " + ".join(score_parts) or "0"
    params = score_params + where_params + [str(max(limit, 1))]
    return conn.execute(
        f"""
        SELECT *, ({score_expr}) AS match_score
        FROM documents
        WHERE {where}
        ORDER BY match_score DESC, updated_at DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def _local_embedding(text: str, dims: int = 64) -> list[float]:
    vector = [0.0] * dims
    for term in _query_terms(text)[:512]:
        digest = hashlib.sha256(term.lower().encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % dims
        weight = 1.0 + min(len(term), 12) / 12
        vector[idx] += weight
    norm = sum(value * value for value in vector) ** 0.5
    if not norm:
        return vector
    return [round(value / norm, 6) for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(left[idx] * right[idx] for idx in range(size))


def _is_low_value_ingest_candidate(query: str, item: dict[str, Any]) -> bool:
    """Avoid auto-archiving obvious drift or platform homepages."""
    return audit_ingest_candidate(query, item).get("decision") == "skip"


def _summarize_ingest_audits(records: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    audited = 0
    kept = 0
    skipped = 0
    for record in records:
        audit = record.get("audit")
        if not isinstance(audit, dict):
            audit = (record.get("metadata") or {}).get("ingest_audit") if isinstance(record.get("metadata"), dict) else {}
        if not isinstance(audit, dict) or not audit:
            continue
        audited += 1
        if audit.get("decision") == "skip":
            skipped += 1
        else:
            kept += 1
        for reason in audit.get("reasons") or []:
            reasons[str(reason)] = reasons.get(str(reason), 0) + 1
    return {
        "audited": audited,
        "kept": kept,
        "skipped": skipped,
        "reasons": reasons,
        "principle": "入库前先审计相关性、重复、平台首页、正文厚度和漂移风险。",
    }


def _looks_like_platform_homepage(title: str, url: str, snippet: str) -> bool:
    title_lower = title.strip().lower()
    homepage_titles = {
        "sciencedirect.com",
        "ieee xplore",
        "engineering village - quick search",
        "engineering village | search and discovery platform",
        "engineering village | search and discovery platform to ... - elsevier",
    }
    homepage_markers = ("quick search", "search and discovery platform")
    if (title_lower in homepage_titles or any(marker in title_lower for marker in homepage_markers)) and len(snippet.strip()) < 160:
        return True
    parsed = urllib.parse.urlparse(url)
    path = (parsed.path or "").strip("/")
    return bool(path == "" and title.strip().lower() in {parsed.netloc.lower(), parsed.netloc.lower().removeprefix("www.")})


def _meaningful_query_terms(query: str) -> list[str]:
    stopwords = {
        "这些",
        "文章",
        "提到",
        "所有",
        "具体",
        "方法",
        "名称",
        "哪些",
        "什么",
        "相关",
        "介绍",
        "对比",
    }
    terms = []
    for term in _query_terms(query):
        if term in stopwords:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]{2}", term) and term in {"这些", "文章", "提到", "所有", "具体", "方法"}:
            continue
        terms.append(term)
    return terms[:12]


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _match_trace(query: str, fields: dict[str, str], *, match_score: float = 0.0) -> dict[str, Any]:
    terms = _query_terms(query)[:16]
    field_hits: dict[str, list[str]] = {}
    for field, value in fields.items():
        lower = str(value or "").lower()
        hits = [term for term in terms if term.lower() in lower]
        if hits:
            field_hits[field] = hits
    return {
        "query_terms": terms,
        "matched_terms": _unique_terms([term for hits in field_hits.values() for term in hits]),
        "field_hits": field_hits,
        "match_score": match_score,
        "retrieval": "sqlite-fts5+like",
        "semantic": "not-vector",
    }


def _row_to_record(
    row: sqlite3.Row,
    query: str = "",
    include_content: bool = False,
    rag: bool = False,
    trace: bool = False,
) -> dict[str, Any]:
    data = dict(row)
    content = str(data.get("content", ""))
    metadata_raw = data.pop("metadata_json", "{}")
    try:
        metadata = json.loads(metadata_raw)
    except json.JSONDecodeError:
        metadata = {}
    record = {
        "id": data.get("id"),
        "url": data.get("url", ""),
        "title": data.get("title", ""),
        "domain": data.get("domain", ""),
        "excerpt": _snippet(content, query) if query else data.get("excerpt", ""),
        "content_hash": data.get("content_hash", ""),
        "current_snapshot_id": data.get("current_snapshot_id", ""),
        "added_at": data.get("added_at", 0),
        "updated_at": data.get("updated_at", 0),
        "metadata": metadata,
    }
    record["topic_label"] = str(metadata.get("topic_label") or _derive_topic_label("", title=str(record.get("title", "")), topic_key=str(metadata.get("topic_key") or "")))
    record["content_mode"] = str(metadata.get("content_mode") or _infer_content_mode(content, quality=metadata.get("read_quality"), quality_report=metadata.get("quality_report")))
    record["content_chars"] = int(metadata.get("content_chars") or len(_collapse_ws(content)))
    record["quality_score"] = _quality_score(metadata.get("read_quality") if isinstance(metadata.get("read_quality"), dict) else {})
    if "match_score" in data:
        record["match_score"] = data.get("match_score", 0)
    if "rank" in data:
        record["rank_score"] = data.get("rank", 0)
    if include_content:
        record["content"] = content
    if rag:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        record["rag"] = {
            "id": f"guanlan-{record.get('id')}",
            "text": data.get("content", ""),
            "source": record.get("url", ""),
            "title": record.get("title", ""),
            "domain": record.get("domain", ""),
            "source_type": metadata.get("source_type", ""),
            "topic": metadata.get("topic_key", ""),
            "topic_label": record.get("topic_label", ""),
            "updated_at": record.get("updated_at", 0),
        }
    if trace and query:
        record["search_trace"] = _match_trace(
            query,
            {
                "title": str(record.get("title", "")),
                "domain": str(record.get("domain", "")),
                "url": str(record.get("url", "")),
                "content": content,
            },
            match_score=float(record.get("match_score", 0) or 0),
        )
    return record


def _snapshot_row_to_record(row: sqlite3.Row, *, include_content: bool = False) -> dict[str, Any]:
    data = dict(row)
    try:
        metadata = json.loads(str(data.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        metadata = {}
    record = {
        "schema_version": "document_snapshot_v1",
        "snapshot_id": data.get("snapshot_id", ""), "document_id": data.get("document_id"),
        "url": data.get("url", ""), "title": data.get("title", ""),
        "content_hash": data.get("content_hash", ""), "observed_at": data.get("observed_at", 0),
        "last_observed_at": data.get("last_observed_at", 0), "created_at": data.get("created_at", 0),
        "previous_snapshot_id": data.get("previous_snapshot_id", ""),
        "passage_count": int(data.get("passage_count") or 0), "metadata": metadata,
    }
    if include_content:
        record["content"] = str(data.get("content") or "")
        record["content_chars"] = len(record["content"])
    return record


def _passage_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    try:
        heading_path = json.loads(str(data.get("heading_path_json") or "[]"))
    except json.JSONDecodeError:
        heading_path = []
    record = {
        "schema_version": "passage_v1", "passage_id": data.get("passage_id", ""),
        "snapshot_id": data.get("snapshot_id", ""), "ordinal": int(data.get("ordinal") or 0),
        "heading_path": heading_path if isinstance(heading_path, list) else [],
        "char_start": int(data.get("char_start") or 0), "char_end": int(data.get("char_end") or 0),
        "text": str(data.get("text") or ""), "text_hash": data.get("text_hash", ""),
    }
    record.update(
        {
            "locator_type": str(data.get("locator_type") or "text"),
            "page_number": data.get("page_number"),
            "table_id": str(data.get("table_id") or ""),
            "row_index": data.get("row_index"),
            "column_index": data.get("column_index"),
            "attachment_parent_id": str(data.get("attachment_parent_id") or ""),
        }
    )
    return record


def _change_event_record(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    try:
        summary = json.loads(str(data.get("summary_json") or "{}"))
    except json.JSONDecodeError:
        summary = {}
    try:
        claim_delta = json.loads(str(data.get("claim_delta_json") or "{}"))
    except json.JSONDecodeError:
        claim_delta = {}
    return {
        "schema_version": "change_event_v1",
        "event_id": data.get("event_id", ""),
        "document_id": data.get("document_id"),
        "before_snapshot_id": data.get("before_snapshot_id", ""),
        "after_snapshot_id": data.get("after_snapshot_id", ""),
        "snapshot_diff": summary,
        "claim_delta": claim_delta,
        "created_at": data.get("created_at", 0),
    }


def _export_filter(
    record: dict[str, Any],
    *,
    domain: str | None = None,
    source_type: str | None = None,
    topic: str | None = None,
    min_quality: int | None = None,
) -> bool:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    if domain and domain.lower() not in str(record.get("domain", "")).lower():
        return False
    if source_type and source_type.lower() not in str(metadata.get("source_type", "")).lower():
        return False
    if topic and topic.lower() not in str(metadata.get("topic_key", "")).lower():
        topic_label = str(metadata.get("topic_label", "")).lower()
        if topic.lower() not in topic_label:
            return False
    if min_quality is not None:
        quality = metadata.get("read_quality") if isinstance(metadata.get("read_quality"), dict) else {}
        score = _quality_score(quality)
        if score is None or score < max(min_quality, 0):
            return False
    return True


def _quality_score(quality: dict[str, Any]) -> float | None:
    if not isinstance(quality, dict):
        return None
    for key in ("score", "quality_score", "readability_score"):
        if key not in quality:
            continue
        try:
            return float(quality[key])
        except (TypeError, ValueError):
            continue
    return None


def _rag_metadata(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    quality = metadata.get("read_quality") if isinstance(metadata.get("read_quality"), dict) else {}
    return {
        "id": f"guanlan-{record.get('id')}",
        "source": record.get("url", ""),
        "title": record.get("title", ""),
        "domain": record.get("domain", ""),
        "source_type": metadata.get("source_type", ""),
        "topic": metadata.get("topic_key", ""),
        "topic_label": metadata.get("topic_label", "") or record.get("topic_label", ""),
        "evidence_role": metadata.get("evidence_role", ""),
        "content_mode": metadata.get("content_mode", "") or record.get("content_mode", ""),
        "content_chars": metadata.get("content_chars", 0) or record.get("content_chars", 0),
        "read_quality_score": _quality_score(quality),
        "updated_at": record.get("updated_at", 0),
        "content_hash": record.get("content_hash", ""),
        "tool": "guanlan",
    }


def _archive_record_priority(record: dict[str, Any]) -> tuple[float, ...]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    quality = metadata.get("read_quality") if isinstance(metadata.get("read_quality"), dict) else {}
    audit = metadata.get("ingest_audit") if isinstance(metadata.get("ingest_audit"), dict) else {}
    quality_score = _quality_score(quality) or 0.0
    content_mode = str(metadata.get("content_mode") or record.get("content_mode") or "unknown")
    content_rank = ARCHIVE_CONTENT_MODE_RANK.get(content_mode, 0)
    content_chars = int(metadata.get("content_chars") or record.get("content_chars") or 0)
    keep_bonus = 1 if audit.get("decision") == "keep" else 0
    return (
        keep_bonus,
        content_rank,
        quality_score,
        min(content_chars, 12000),
        float(record.get("updated_at", 0) or 0),
        float(record.get("id", 0) or 0),
    )


def _verification_probe_terms(title: str, content: str) -> list[str]:
    """Choose stable probe terms that should recall the document itself."""
    stopwords = {
        "正文",
        "内容",
        "标题",
        "关于",
        "本文",
        "介绍",
        "材料",
        "来源",
        "https",
        "http",
    }
    candidates = _query_terms(f"{title} {content[:1200]}")[:24]
    output = []
    for term in candidates:
        if term.lower() in stopwords or term in stopwords:
            continue
        if len(term.strip()) < 2:
            continue
        output.append(term)
        if len(output) >= 3:
            break
    return output


def _normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    if not parsed.netloc:
        return value
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = parsed.query
    return urllib.parse.urlunparse((scheme, netloc, path, "", query, ""))


def _domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def _title_from_markdown(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if stripped:
            return _collapse_ws(stripped)[:80]
    return ""


def _excerpt(content: str, max_chars: int = 260) -> str:
    text = _collapse_ws(re.sub(r"`{3}.*?`{3}", " ", content, flags=re.S))
    return text[:max_chars]


def _snippet(content: str, query: str, radius: int = 100) -> str:
    text = _collapse_ws(content)
    for term in _query_terms(query):
        idx = text.lower().find(term.lower())
        if idx >= 0:
            start = max(idx - radius, 0)
            end = min(idx + len(term) + radius, len(text))
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(text) else ""
            return prefix + text[start:end] + suffix
    return text[:240]


def _query_terms(query: str) -> list[str]:
    raw_terms = re.findall(
        r"[A-Za-z][A-Za-z0-9_.+-]*|\d+(?:\.\d+)?|[\u4e00-\u9fff]{2,}",
        query or "",
        flags=re.I,
    )
    terms: list[str] = []
    for raw in raw_terms:
        term = raw.strip()
        if not term:
            continue
        terms.append(term)
        if re.fullmatch(r"[\u4e00-\u9fff]{4,}", term):
            terms.extend(_cjk_chunks(term))
    return _unique_terms(terms) or [query.strip()]


def _cjk_chunks(value: str) -> list[str]:
    """Split long Chinese phrases into recall terms for SQLite search."""
    text = value.strip()
    chunks: list[str] = []
    idx = 0
    while idx < len(text):
        chunk = text[idx:idx + 2]
        if len(chunk) == 2:
            chunks.append(chunk)
        idx += 2
    if len(text) >= 5 and len(text) % 2 == 1:
        chunks.append(text[-3:])
    return chunks


def _unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(term)
    return output


def _fts_query(query: str) -> str:
    terms = [term.replace('"', '""') for term in _query_terms(query)]
    return " AND ".join(f'"{term}"' for term in terms if term)


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _pipe_safe(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _format_time(ts: float) -> str:
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
