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
from pathlib import Path
from typing import Any

ARCHIVE_SCHEMA_VERSION = 1


def archive_db_path() -> Path:
    """Return the default local archive database path."""
    return Path.home() / ".guanlan" / "archive.db"


def add_url(
    url: str,
    max_chars: int | None = None,
    backend: str = "auto",
    fallback_search: bool = True,
    fallback_limit: int = 5,
    profile: str | None = "china",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read one URL and persist it into the local archive."""
    from guanlan.webtools import read_url

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
    fallback_limit: int = 5,
    profile: str | None = "china",
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Read multiple URLs and persist successful records into the archive."""
    from guanlan.webtools import read_batch

    batch = read_batch(
        urls,
        max_chars=max_chars,
        backend=backend,
        fallback_search=fallback_search,
        fallback_limit=fallback_limit,
        profile=profile,
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

    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id, content_hash FROM documents WHERE url = ?",
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
    }


def search_documents(
    query: str,
    limit: int = 10,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Search the local archive with FTS when available and LIKE fallback."""
    query = query.strip()
    if not query:
        raise ValueError("query is required")
    limit = max(limit, 1)
    with _connect(db_path) as conn:
        rows: list[sqlite3.Row] = []
        seen: set[int] = set()
        for row in _search_fts(conn, query, limit):
            seen.add(int(row["id"]))
            rows.append(row)
        if len(rows) < limit:
            for row in _search_like(conn, query, limit * 2):
                row_id = int(row["id"])
                if row_id in seen:
                    continue
                seen.add(row_id)
                rows.append(row)
                if len(rows) >= limit:
                    break
    return [_row_to_record(row, query=query) for row in rows[:limit]]


def list_documents(limit: int = 20, db_path: str | Path | None = None) -> list[dict[str, Any]]:
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


def export_documents(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return all archive documents for JSONL/Markdown export."""
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY updated_at DESC, id DESC").fetchall()
    return [_row_to_record(row, include_content=True) for row in rows]


def archive_stats(db_path: str | Path | None = None) -> dict[str, Any]:
    """Return archive counts and domain distribution."""
    path = _db_path(db_path)
    if not path.exists():
        return {"path": str(path), "exists": False, "documents": 0, "domains": []}
    with _connect(path) as conn:
        count = int(conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"])
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
        "domains": [{"domain": row["domain"], "count": int(row["count"])} for row in domains],
    }


def format_archive_markdown(records: list[dict[str, Any]], title: str = "观澜本地知识库") -> str:
    """Render archive records as Markdown."""
    lines = [f"# {title}", ""]
    if not records:
        lines.append("暂无本地归档结果。")
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
    lines = [f"# {title}", "", "来源 | 标题 | 摘要 | 时间", "--- | --- | --- | ---"]
    if not records:
        lines.append("无结果 | - | - | -")
        return "\n".join(lines)
    for item in records:
        domain = _pipe_safe(str(item.get("domain", "unknown")))
        title_text = _pipe_safe(_collapse_ws(str(item.get("title", ""))))
        excerpt = _pipe_safe(_collapse_ws(str(item.get("excerpt", "")))[:160])
        updated = _format_time(float(item.get("updated_at", 0) or 0))
        url = str(item.get("url", ""))
        lines.append(f"{domain} | [{title_text}]({url}) | {excerpt} | {updated}")
    return "\n".join(lines)


def format_archive_stats(stats: dict[str, Any]) -> str:
    """Render archive stats as Markdown."""
    lines = ["# 观澜本地知识库状态", "", f"- 路径: {stats.get('path', '')}", f"- 文档数: {stats.get('documents', 0)}"]
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
            updated_at REAL NOT NULL
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


def _has_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM archive_meta WHERE key = 'fts'").fetchone()
    return bool(row and row["value"] == "1")


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
    terms = _query_terms(query)
    clauses = []
    params: list[str] = []
    for term in terms:
        clauses.append("(title LIKE ? OR content LIKE ? OR url LIKE ? OR domain LIKE ?)")
        like = f"%{term}%"
        params.extend([like, like, like, like])
    where = " AND ".join(clauses) if clauses else "1 = 1"
    params.append(str(max(limit, 1)))
    return conn.execute(
        f"""
        SELECT *
        FROM documents
        WHERE {where}
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()


def _row_to_record(row: sqlite3.Row, query: str = "", include_content: bool = False) -> dict[str, Any]:
    data = dict(row)
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
        "excerpt": _snippet(str(data.get("content", "")), query) if query else data.get("excerpt", ""),
        "content_hash": data.get("content_hash", ""),
        "added_at": data.get("added_at", 0),
        "updated_at": data.get("updated_at", 0),
        "metadata": metadata,
    }
    if include_content:
        record["content"] = data.get("content", "")
    return record


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
    terms = [term.strip() for term in re.split(r"\s+", query) if term.strip()]
    return terms or [query.strip()]


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
