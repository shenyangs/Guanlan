#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tiny Guanlan telemetry collector.

This server uses only the Python standard library so it can run on small ECS
instances without a package install step. It stores aggregate-safe lifecycle
metadata in SQLite and exposes a Basic Auth dashboard.
"""

from __future__ import print_function

import base64
import datetime as _dt
import hashlib
import hmac
import html
import json
import os
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

DB_PATH = os.environ.get("GUANLAN_DB", "/var/lib/guanlan-telemetry/events.db")
BIND_HOST = os.environ.get("GUANLAN_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("GUANLAN_PORT", "8080"))
ADMIN_USER = os.environ.get("GUANLAN_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("GUANLAN_ADMIN_PASSWORD", "")
INGEST_TOKEN = os.environ.get("GUANLAN_INGEST_TOKEN", "")
ACTIVE_TTL_SECONDS = int(os.environ.get("GUANLAN_ACTIVE_TTL_SECONDS", "180"))
MAX_BODY_BYTES = 16 * 1024
SYNTHETIC_QUERY_EXACT = set(
    [
        "query",
        "blocked query",
        "test",
        "testing",
        "demo",
        "sample",
        "placeholder",
        "xxx",
        "n/a",
        "na",
    ]
)


def now_ms():
    return int(time.time() * 1000)


def clamp_text(value, limit=160):
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > limit:
        return text[:limit]
    return text


def normalize_query_text(value):
    return str(value or "").strip().lower()


def is_synthetic_feedback_query(query_text):
    normalized = normalize_query_text(query_text)
    if not normalized:
        return False
    if normalized in SYNTHETIC_QUERY_EXACT:
        return True
    return (
        normalized.startswith("test ")
        or normalized.startswith("demo ")
        or normalized.startswith("sample ")
    )


def feedback_real_sql(column="query_text"):
    expr = "LOWER(TRIM(COALESCE(%s, '')))" % column
    return (
        "("
        + expr
        + " NOT IN ('query','blocked query','test','testing','demo','sample','placeholder','xxx','n/a','na') "
        + "AND "
        + expr
        + " NOT LIKE 'test %' "
        + "AND "
        + expr
        + " NOT LIKE 'demo %' "
        + "AND "
        + expr
        + " NOT LIKE 'sample %'"
        + ")"
    )


def db_connect():
    parent = os.path.dirname(DB_PATH)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    conn = db_connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_ms INTEGER NOT NULL,
                received_ms INTEGER NOT NULL,
                event TEXT NOT NULL,
                install_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                invocation_id TEXT NOT NULL,
                surface TEXT NOT NULL,
                command TEXT NOT NULL,
                version TEXT NOT NULL,
                agent_kind TEXT NOT NULL,
                agent_id TEXT NOT NULL DEFAULT '',
                platform TEXT NOT NULL,
                python TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms INTEGER,
                remote_addr TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_received ON events(received_ms);
            CREATE INDEX IF NOT EXISTS idx_events_install ON events(install_id);
            CREATE INDEX IF NOT EXISTS idx_events_invocation ON events(invocation_id);

            CREATE TABLE IF NOT EXISTS active_invocations (
                invocation_id TEXT PRIMARY KEY,
                install_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                surface TEXT NOT NULL,
                command TEXT NOT NULL,
                version TEXT NOT NULL,
                agent_kind TEXT NOT NULL,
                agent_id TEXT NOT NULL DEFAULT '',
                started_ms INTEGER NOT NULL,
                last_seen_ms INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_active_last_seen ON active_invocations(last_seen_ms);

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_ms INTEGER NOT NULL,
                received_ms INTEGER NOT NULL,
                install_id TEXT NOT NULL,
                agent_kind TEXT NOT NULL,
                agent_id TEXT NOT NULL DEFAULT '',
                surface TEXT NOT NULL,
                command TEXT NOT NULL,
                profile TEXT NOT NULL,
                backend TEXT NOT NULL,
                query_text TEXT NOT NULL,
                reason_text TEXT NOT NULL,
                version TEXT NOT NULL,
                platform TEXT NOT NULL,
                python TEXT NOT NULL,
                remote_addr TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_feedback_received ON feedback(received_ms);
            CREATE INDEX IF NOT EXISTS idx_feedback_command ON feedback(command);
            CREATE INDEX IF NOT EXISTS idx_feedback_agent ON feedback(agent_id);
            """
        )
        ensure_column(conn, "events", "agent_id", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "active_invocations", "agent_id", "TEXT NOT NULL DEFAULT ''")
        backfill_agent_ids(conn)
        dedupe_events(conn)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_invocation ON events(event, invocation_id)"
        )
        conn.commit()
    finally:
        conn.close()


def ensure_column(conn, table, column, definition):
    rows = conn.execute("PRAGMA table_info(%s)" % table).fetchall()
    if column in [r["name"] for r in rows]:
        return
    conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, definition))


def fallback_agent_id(install_id, agent_kind):
    seed = "%s|%s" % (install_id or "", agent_kind or "")
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def backfill_agent_ids(conn):
    for table, key in (("events", "id"), ("active_invocations", "invocation_id")):
        rows = conn.execute(
            "SELECT %s, install_id, agent_kind FROM %s WHERE agent_id = '' OR agent_id IS NULL" % (key, table)
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE %s SET agent_id = ? WHERE %s = ?" % (table, key),
                (fallback_agent_id(row["install_id"], row["agent_kind"]), row[key]),
            )


def dedupe_events(conn):
    conn.execute(
        """
        DELETE FROM events
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM events
            GROUP BY event, invocation_id
        )
        """
    )


def prune_active(conn, current_ms):
    cutoff = current_ms - ACTIVE_TTL_SECONDS * 1000
    conn.execute("DELETE FROM active_invocations WHERE last_seen_ms < ?", (cutoff,))


def record_event(payload, remote_addr):
    current = now_ms()
    event = clamp_text(payload.get("event"), 64)
    if event not in ("invocation_start", "invocation_heartbeat", "invocation_end"):
        return False

    row = {
        "ts_ms": int(payload.get("ts") or current),
        "received_ms": current,
        "event": event,
        "install_id": clamp_text(payload.get("install_id"), 96),
        "session_id": clamp_text(payload.get("session_id"), 96),
        "invocation_id": clamp_text(payload.get("invocation_id"), 96),
        "surface": clamp_text(payload.get("surface"), 32),
        "command": clamp_text(payload.get("command"), 120),
        "version": clamp_text(payload.get("version"), 40),
        "agent_kind": clamp_text(payload.get("agent_kind"), 40),
        "agent_id": clamp_text(payload.get("agent_id"), 96),
        "platform": clamp_text(payload.get("platform"), 40),
        "python": clamp_text(payload.get("python"), 24),
        "status": clamp_text(payload.get("status"), 24),
        "duration_ms": payload.get("duration_ms"),
        "remote_addr": clamp_text(remote_addr, 80),
    }
    if not row["install_id"] or not row["invocation_id"]:
        return False
    if not row["agent_id"]:
        row["agent_id"] = fallback_agent_id(row["install_id"], row["agent_kind"])
    try:
        row["duration_ms"] = int(row["duration_ms"]) if row["duration_ms"] is not None else None
    except Exception:
        row["duration_ms"] = None

    conn = db_connect()
    try:
        prune_active(conn, current)
        if event == "invocation_heartbeat":
            cursor = conn.execute(
                "UPDATE active_invocations SET last_seen_ms = ? WHERE invocation_id = ?",
                (current, row["invocation_id"]),
            )
            if cursor.rowcount == 0:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO active_invocations (
                        invocation_id, install_id, session_id, surface, command,
                        version, agent_kind, agent_id, started_ms, last_seen_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["invocation_id"],
                        row["install_id"],
                        row["session_id"],
                        row["surface"],
                        row["command"],
                        row["version"],
                        row["agent_kind"],
                        row["agent_id"],
                        current,
                        current,
                    ),
                )
            conn.commit()
            return True

        conn.execute(
            """
            INSERT OR IGNORE INTO events (
                ts_ms, received_ms, event, install_id, session_id, invocation_id,
                surface, command, version, agent_kind, agent_id, platform, python, status,
                duration_ms, remote_addr
            ) VALUES (
                :ts_ms, :received_ms, :event, :install_id, :session_id,
                :invocation_id, :surface, :command, :version, :agent_kind,
                :agent_id, :platform, :python, :status, :duration_ms, :remote_addr
            )
            """,
            row,
        )
        if event == "invocation_start":
            conn.execute(
                """
                INSERT OR REPLACE INTO active_invocations (
                    invocation_id, install_id, session_id, surface, command,
                    version, agent_kind, agent_id, started_ms, last_seen_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["invocation_id"],
                    row["install_id"],
                    row["session_id"],
                    row["surface"],
                    row["command"],
                    row["version"],
                    row["agent_kind"],
                    row["agent_id"],
                    current,
                    current,
                ),
            )
        else:
            conn.execute(
                "DELETE FROM active_invocations WHERE invocation_id = ?",
                (row["invocation_id"],),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def record_feedback(payload, remote_addr):
    current = now_ms()
    row = {
        "ts_ms": int(payload.get("ts") or current),
        "received_ms": current,
        "install_id": clamp_text(payload.get("install_id"), 96),
        "agent_kind": clamp_text(payload.get("agent_kind"), 40),
        "agent_id": clamp_text(payload.get("agent_id"), 96),
        "surface": clamp_text(payload.get("surface"), 32),
        "command": clamp_text(payload.get("command"), 40),
        "profile": clamp_text(payload.get("profile"), 24),
        "backend": clamp_text(payload.get("backend"), 40),
        "query_text": clamp_text(payload.get("query_text"), 200),
        "reason_text": clamp_text(payload.get("reason_text"), 600),
        "version": clamp_text(payload.get("version"), 40),
        "platform": clamp_text(payload.get("platform"), 40),
        "python": clamp_text(payload.get("python"), 24),
        "remote_addr": clamp_text(remote_addr, 80),
    }
    if not row["install_id"] or not row["query_text"] or not row["reason_text"]:
        return False
    if not row["agent_id"]:
        row["agent_id"] = fallback_agent_id(row["install_id"], row["agent_kind"])

    conn = db_connect()
    try:
        conn.execute(
            """
            INSERT INTO feedback (
                ts_ms, received_ms, install_id, agent_kind, agent_id, surface, command,
                profile, backend, query_text, reason_text, version, platform, python, remote_addr
            ) VALUES (
                :ts_ms, :received_ms, :install_id, :agent_kind, :agent_id, :surface, :command,
                :profile, :backend, :query_text, :reason_text, :version, :platform, :python, :remote_addr
            )
            """,
            row,
        )
        conn.commit()
        return True
    finally:
        conn.close()


def query_one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return list(row)[0] if row else 0


def query_groups(conn, column, since_ms, limit=10):
    allowed = set(["surface", "command", "agent_kind", "version", "platform", "status"])
    if column not in allowed:
        return []
    rows = conn.execute(
        """
        SELECT {column} AS key, COUNT(*) AS count
        FROM events
        WHERE received_ms >= ? AND event = 'invocation_start'
        GROUP BY {column}
        ORDER BY count DESC, key ASC
        LIMIT ?
        """.format(column=column),
        (since_ms, limit),
    ).fetchall()
    return [{"key": r["key"] or "unknown", "count": r["count"]} for r in rows]


def query_feedback_groups(conn, column, since_ms, limit=10, real_only=False):
    allowed = set(["command", "profile", "backend", "query_text", "reason_text", "agent_kind"])
    if column not in allowed:
        return []
    where = "received_ms >= ?"
    if real_only:
        where += " AND " + feedback_real_sql("query_text")
    rows = conn.execute(
        """
        SELECT {column} AS key, COUNT(*) AS count
        FROM feedback
        WHERE {where}
        GROUP BY {column}
        ORDER BY count DESC, key ASC
        LIMIT ?
        """.format(column=column, where=where),
        (since_ms, limit),
    ).fetchall()
    return [{"key": r["key"] or "unknown", "count": r["count"]} for r in rows]


def query_platform_unique(conn, field, since_ms=None, limit=10):
    allowed = set(["install_id", "agent_id"])
    if field not in allowed:
        return []
    where = "platform <> '' AND {field} <> ''".format(field=field)
    params = []
    if since_ms is not None:
        where = "received_ms >= ? AND " + where
        params.append(since_ms)
    params.append(limit)
    rows = conn.execute(
        """
        SELECT platform AS key, COUNT(DISTINCT {field}) AS count
        FROM events
        WHERE {where}
        GROUP BY platform
        ORDER BY count DESC, key ASC
        LIMIT ?
        """.format(field=field, where=where),
        tuple(params),
    ).fetchall()
    return [{"key": r["key"] or "unknown", "count": r["count"]} for r in rows]


def query_percentile(values, percentile):
    if not values:
        return 0
    ordered = sorted(int(v) for v in values if v is not None)
    if not ordered:
        return 0
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[max(0, min(index, len(ordered) - 1))]


def query_duration_stats(conn, since_ms):
    rows = conn.execute(
        """
        SELECT duration_ms FROM events
        WHERE received_ms >= ?
          AND event = 'invocation_end'
          AND duration_ms IS NOT NULL
          AND duration_ms >= 0
        """,
        (since_ms,),
    ).fetchall()
    values = [r["duration_ms"] for r in rows]
    if not values:
        return {"avg_ms": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0}
    return {
        "avg_ms": int(sum(values) / len(values)),
        "p50_ms": query_percentile(values, 0.50),
        "p95_ms": query_percentile(values, 0.95),
        "p99_ms": query_percentile(values, 0.99),
    }


def query_session_stats(conn, since_ms):
    rows = conn.execute(
        """
        SELECT session_id,
               MIN(received_ms) AS first_seen,
               MAX(received_ms) AS last_seen,
               COUNT(CASE WHEN event = 'invocation_start' THEN 1 END) AS calls
        FROM events
        WHERE received_ms >= ?
        GROUP BY session_id
        """,
        (since_ms,),
    ).fetchall()
    if not rows:
        return {"count": 0, "avg_duration_ms": 0, "p95_duration_ms": 0, "avg_calls": 0}
    durations = [max(0, r["last_seen"] - r["first_seen"]) for r in rows]
    calls = [int(r["calls"] or 0) for r in rows]
    return {
        "count": len(rows),
        "avg_duration_ms": int(sum(durations) / len(durations)),
        "p95_duration_ms": query_percentile(durations, 0.95),
        "avg_calls": round(float(sum(calls)) / len(calls), 2),
    }


def query_new_installs(conn, since_ms):
    return query_one(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT install_id, MIN(received_ms) AS first_seen
            FROM events
            GROUP BY install_id
            HAVING first_seen >= ?
        )
        """,
        (since_ms,),
    )


def query_returning_installs(conn, since_ms):
    return query_one(
        conn,
        """
        SELECT COUNT(DISTINCT e.install_id)
        FROM events e
        JOIN (
            SELECT install_id, MIN(received_ms) AS first_seen
            FROM events
            GROUP BY install_id
        ) firsts ON firsts.install_id = e.install_id
        WHERE e.received_ms >= ?
          AND firsts.first_seen < ?
        """,
        (since_ms, since_ms),
    )


def query_orphan_starts(conn, since_ms, current_ms):
    cutoff = current_ms - ACTIVE_TTL_SECONDS * 1000
    return query_one(
        conn,
        """
        SELECT COUNT(*)
        FROM events starts
        LEFT JOIN events ends
          ON ends.invocation_id = starts.invocation_id
         AND ends.event = 'invocation_end'
        WHERE starts.event = 'invocation_start'
          AND starts.received_ms >= ?
          AND starts.received_ms < ?
          AND ends.id IS NULL
        """,
        (since_ms, cutoff),
    )


def fmt_ms(ms):
    ms = int(ms or 0)
    if ms <= 0:
        return "0s"
    seconds = ms / 1000.0
    if seconds < 60:
        return "%.1fs" % seconds
    minutes = int(seconds // 60)
    rest = int(seconds % 60)
    if minutes < 60:
        return "%dm %02ds" % (minutes, rest)
    hours = int(minutes // 60)
    minutes = minutes % 60
    return "%dh %02dm" % (hours, minutes)


def fmt_rate(numerator, denominator):
    if not denominator:
        return "0%"
    return "%.1f%%" % (100.0 * float(numerator) / float(denominator))


def summary():
    current = now_ms()
    day = current - 24 * 3600 * 1000
    week = current - 7 * 24 * 3600 * 1000
    conn = db_connect()
    try:
        prune_active(conn, current)
        conn.commit()
        calls_24h = query_one(
            conn,
            "SELECT COUNT(*) FROM events WHERE received_ms >= ? AND event = 'invocation_start'",
            (day,),
        )
        calls_7d = query_one(
            conn,
            "SELECT COUNT(*) FROM events WHERE received_ms >= ? AND event = 'invocation_start'",
            (week,),
        )
        unique_agents_24h = query_one(
            conn,
            "SELECT COUNT(DISTINCT agent_id) FROM events WHERE received_ms >= ?",
            (day,),
        )
        active_installs_24h = query_one(
            conn,
            "SELECT COUNT(DISTINCT install_id) FROM events WHERE received_ms >= ?",
            (day,),
        )
        errors_24h = query_one(
            conn,
            "SELECT COUNT(*) FROM events WHERE received_ms >= ? AND event = 'invocation_end' AND status = 'error'",
            (day,),
        )
        orphan_starts_24h = query_orphan_starts(conn, day, current)
        feedback_24h_total = query_one(
            conn,
            "SELECT COUNT(*) FROM feedback WHERE received_ms >= ?",
            (day,),
        )
        feedback_7d_total = query_one(
            conn,
            "SELECT COUNT(*) FROM feedback WHERE received_ms >= ?",
            (week,),
        )
        real_feedback_where = feedback_real_sql("query_text")
        feedback_24h = query_one(
            conn,
            "SELECT COUNT(*) FROM feedback WHERE received_ms >= ? AND " + real_feedback_where,
            (day,),
        )
        feedback_7d = query_one(
            conn,
            "SELECT COUNT(*) FROM feedback WHERE received_ms >= ? AND " + real_feedback_where,
            (week,),
        )
        data = {
            "generated_ms": current,
            "last_event_age_ms": max(
                0,
                current - (query_one(conn, "SELECT MAX(received_ms) FROM events") or current),
            ),
            "active_now": query_one(conn, "SELECT COUNT(*) FROM active_invocations"),
            "all_time_unique_installs": query_one(
                conn,
                """
                SELECT COUNT(DISTINCT install_id) FROM (
                    SELECT install_id FROM events WHERE install_id <> ''
                    UNION
                    SELECT install_id FROM feedback WHERE install_id <> ''
                )
                """,
            ),
            "all_time_unique_agents": query_one(
                conn,
                """
                SELECT COUNT(DISTINCT agent_id) FROM (
                    SELECT agent_id FROM events WHERE agent_id <> ''
                    UNION
                    SELECT agent_id FROM feedback WHERE agent_id <> ''
                )
                """,
            ),
            "calls_24h": calls_24h,
            "calls_7d": calls_7d,
            "active_installs_24h": active_installs_24h,
            "active_installs_7d": query_one(
                conn,
                "SELECT COUNT(DISTINCT install_id) FROM events WHERE received_ms >= ?",
                (week,),
            ),
            "unique_agents_24h": unique_agents_24h,
            "unique_agents_7d": query_one(
                conn,
                "SELECT COUNT(DISTINCT agent_id) FROM events WHERE received_ms >= ?",
                (week,),
            ),
            "new_installs_24h": query_new_installs(conn, day),
            "new_installs_7d": query_new_installs(conn, week),
            "returning_installs_24h": query_returning_installs(conn, day),
            "error_24h": errors_24h,
            "error_rate_24h": fmt_rate(errors_24h, calls_24h),
            "orphan_starts_24h": orphan_starts_24h,
            "orphan_rate_24h": fmt_rate(orphan_starts_24h, calls_24h),
            "feedback_24h": feedback_24h,
            "feedback_7d": feedback_7d,
            "feedback_24h_total": feedback_24h_total,
            "feedback_7d_total": feedback_7d_total,
            "feedback_24h_synthetic": max(0, int(feedback_24h_total) - int(feedback_24h)),
            "feedback_7d_synthetic": max(0, int(feedback_7d_total) - int(feedback_7d)),
            "feedback_unique_agents_7d": query_one(
                conn,
                "SELECT COUNT(DISTINCT agent_id) FROM feedback WHERE received_ms >= ? AND " + real_feedback_where,
                (week,),
            ),
            "feedback_unique_agents_7d_total": query_one(
                conn,
                "SELECT COUNT(DISTINCT agent_id) FROM feedback WHERE received_ms >= ?",
                (week,),
            ),
            "calls_per_agent_24h": round(float(calls_24h) / unique_agents_24h, 2)
            if unique_agents_24h
            else 0,
            "calls_per_device_24h": round(float(calls_24h) / active_installs_24h, 2)
            if active_installs_24h
            else 0,
            "task_duration_24h": query_duration_stats(conn, day),
            "task_duration_7d": query_duration_stats(conn, week),
            "session_24h": query_session_stats(conn, day),
            "session_7d": query_session_stats(conn, week),
            "surface": query_groups(conn, "surface", week),
            "commands": query_groups(conn, "command", week, 12),
            "agents": query_groups(conn, "agent_kind", week),
            "versions": query_groups(conn, "version", week),
            "platforms": query_groups(conn, "platform", week),
            "platform_unique_devices": query_platform_unique(conn, "install_id", week),
            "platform_unique_agents": query_platform_unique(conn, "agent_id", week),
            "platform_unique_devices_all": query_platform_unique(conn, "install_id"),
            "platform_unique_agents_all": query_platform_unique(conn, "agent_id"),
            "feedback_commands": query_feedback_groups(conn, "command", week, 12, real_only=True),
            "feedback_queries": query_feedback_groups(conn, "query_text", week, 12, real_only=True),
            "feedback_reasons": query_feedback_groups(conn, "reason_text", week, 12, real_only=True),
            "recent": [],
            "recent_feedback": [],
        }
        rows = conn.execute(
            """
            SELECT received_ms, event, surface, command, version, agent_kind, status, duration_ms
            FROM events
            ORDER BY id DESC
            LIMIT 40
            """
        ).fetchall()
        for r in rows:
            data["recent"].append(dict(r))
        feedback_rows = conn.execute(
            """
            SELECT received_ms, query_text, reason_text, command, profile, backend, agent_kind, version
            FROM feedback
            ORDER BY id DESC
            LIMIT 80
            """
        ).fetchall()
        for r in feedback_rows:
            item = dict(r)
            item["synthetic"] = bool(is_synthetic_feedback_query(item.get("query_text")))
            data["recent_feedback"].append(item)
        return data
    finally:
        conn.close()


def format_time(ms):
    try:
        dt = _dt.datetime.utcfromtimestamp(int(ms) / 1000.0) + _dt.timedelta(hours=8)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def render_group(title, rows):
    items = []
    for row in rows:
        key = html.escape(str(row["key"] or "unknown"))
        count = int(row["count"])
        items.append("<tr><td>{}</td><td>{}</td></tr>".format(key, count))
    if not items:
        items.append("<tr><td colspan='2'>暂无数据 / No data yet</td></tr>")
    return "<section><h2>{}</h2><table><tbody>{}</tbody></table></section>".format(
        html.escape(title), "\n".join(items)
    )


def render_key_values(title, rows):
    items = []
    for label, value in rows:
        items.append(
            "<tr><td>{}</td><td>{}</td></tr>".format(
                html.escape(str(label)), html.escape(str(value))
            )
        )
    return "<section><h2>{}</h2><table><tbody>{}</tbody></table></section>".format(
        html.escape(title), "\n".join(items)
    )


def render_feedback_inbox(rows):
    items = []
    for index, row in enumerate(rows, 1):
        received = format_time(row.get("received_ms"))
        query_text = html.escape(row.get("query_text") or "")
        reason_text = html.escape(row.get("reason_text") or "")
        command = html.escape(row.get("command") or "")
        profile = html.escape(row.get("profile") or "")
        backend = html.escape(row.get("backend") or "")
        agent_kind = html.escape(row.get("agent_kind") or "")
        version = html.escape(row.get("version") or "")
        synthetic = bool(row.get("synthetic"))
        items.append(
            """
<details class="feedback-item">
  <summary>
    <span class="feedback-row">
      <span class="feedback-index">#{index}</span>
      <span class="feedback-time">{received}</span>
      <span class="feedback-query" title="{query_title}">{query}</span>
      <span class="feedback-reason-preview">{reason_preview}</span>
      <span class="feedback-inline-meta">{command} · {profile} · {backend} · {agent_kind}</span>
      <span class="feedback-version">v{version}</span>
      <span class="feedback-kind {kind_class}">{kind_text}</span>
      <span class="feedback-expand-hint">点击展开详情</span>
    </span>
  </summary>
  <div class="feedback-body">
    <p><strong>搜索词 / Query</strong></p>
    <p class="feedback-query-full">{query_full}</p>
    <p><strong>原因 / Reason</strong></p>
    <p class="feedback-reason">{reason}</p>
    <p class="feedback-meta">{command} · {profile} · {backend} · {agent_kind} · {version}</p>
  </div>
</details>
            """.strip().format(
                index=index,
                received=received,
                query=query_text or "(empty query)",
                query_title=query_text or "(empty query)",
                query_full=query_text or "(empty query)",
                reason_preview=((reason_text[:80] + "...") if len(reason_text) > 80 else reason_text) or "(empty reason)",
                reason=reason_text or "(empty reason)",
                command=command or "unknown-command",
                profile=profile or "unknown-profile",
                backend=backend or "unknown-backend",
                agent_kind=agent_kind or "unknown-agent",
                version=version or "unknown",
                kind_class="feedback-kind-synthetic" if synthetic else "feedback-kind-real",
                kind_text="测试流量 / Synthetic" if synthetic else "真实反馈 / Real",
            )
        )
    if not items:
        items.append("<p class='feedback-empty'>暂无反馈 / No feedback yet</p>")
    return "<section id='feedback-inbox' class='recent'><h2>反馈明细面板 / Feedback Inbox</h2>{}</section>".format(
        "\n".join(items)
    )


def render_dashboard():
    data = summary()
    task_24h = data["task_duration_24h"]
    session_24h = data["session_24h"]

    core_cards = [
        {"label": "全部独立设备 / All-time Unique Devices", "value": data["all_time_unique_installs"]},
        {"label": "全部独立 Agent / All-time Unique Agents", "value": data["all_time_unique_agents"]},
        {"label": "24h 独立 Agent / 24h Unique Agents", "value": data["unique_agents_24h"]},
        {"label": "24h 独立设备 / 24h Unique Devices", "value": data["active_installs_24h"]},
        {"label": "24h 新增设备 / 24h New Devices", "value": data["new_installs_24h"]},
        {"label": "24h 有效反馈 / 24h Real Feedback", "value": data["feedback_24h"], "href": "#feedback-inbox"},
    ]
    secondary_cards = [
        ("当前并发 / Active Concurrency", data["active_now"]),
        ("最近事件 / Last Event", fmt_ms(data["last_event_age_ms"]) + " 前"),
        ("24h 调用 / 24h Calls", data["calls_24h"]),
        ("7d 调用 / 7d Calls", data["calls_7d"]),
        ("7d 反馈 / 7d Feedback", data["feedback_7d"]),
        ("24h 反馈总量 / 24h Feedback Total", data["feedback_24h_total"]),
        ("24h 测试反馈 / 24h Synthetic Feedback", data["feedback_24h_synthetic"]),
        ("7d 测试反馈 / 7d Synthetic Feedback", data["feedback_7d_synthetic"]),
        ("7d 反馈 Agent / 7d Feedback Agents", data["feedback_unique_agents_7d"]),
        ("7d 反馈 Agent 总量 / 7d Feedback Agents Total", data["feedback_unique_agents_7d_total"]),
        ("7d 独立 Agent / 7d Unique Agents", data["unique_agents_7d"]),
        ("7d 独立设备 / 7d Unique Devices", data["active_installs_7d"]),
        ("24h 回访设备 / 24h Returning Devices", data["returning_installs_24h"]),
        ("Agent 日均调用 / Daily Calls per Agent", data["calls_per_agent_24h"]),
        ("设备日均调用 / Daily Calls per Device", data["calls_per_device_24h"]),
        ("任务平均时长 / Avg Task Duration", fmt_ms(task_24h["avg_ms"])),
        ("任务 P95 时长 / P95 Task Duration", fmt_ms(task_24h["p95_ms"])),
        ("Session 平均时长 / Avg Session Duration", fmt_ms(session_24h["avg_duration_ms"])),
        ("Session P95 时长 / P95 Session Duration", fmt_ms(session_24h["p95_duration_ms"])),
        ("24h 错误率 / 24h Error Rate", data["error_rate_24h"]),
        ("24h 异常结束率 / 24h Orphan Rate", data["orphan_rate_24h"]),
    ]
    core_card_html = "\n".join(
        (
            "<a class='core-card core-card-link' href='{href}'><span>{label}</span><strong>{value}</strong><em>打开逐条反馈</em></a>".format(
                href=html.escape(str(card.get("href") or "")),
                label=html.escape(str(card.get("label") or "")),
                value=html.escape(str(card.get("value") or "")),
            )
            if card.get("href")
            else "<div class='core-card'><span>{label}</span><strong>{value}</strong></div>".format(
                label=html.escape(str(card.get("label") or "")),
                value=html.escape(str(card.get("value") or "")),
            )
        )
        for card in core_cards
    )
    secondary_card_html = "\n".join(
        "<div class='card'><span>{}</span><strong>{}</strong></div>".format(label, value)
        for label, value in secondary_cards
    )
    recent_rows = []
    for row in data["recent"]:
        recent_rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(format_time(row["received_ms"])),
                html.escape(row["event"] or ""),
                html.escape(row["surface"] or ""),
                html.escape(row["command"] or ""),
                html.escape(row["agent_kind"] or ""),
                html.escape(row["version"] or ""),
                html.escape(row["status"] or ""),
                "" if row["duration_ms"] is None else int(row["duration_ms"]),
            )
        )
    if not recent_rows:
        recent_rows.append("<tr><td colspan='8'>暂无事件 / No events yet</td></tr>")

    depth_panel = render_key_values(
        "使用深度 / Usage Depth",
        [
            ("24h 单任务平均 / 24h Avg Task", fmt_ms(task_24h["avg_ms"])),
            ("24h 单任务 P50 / 24h P50 Task", fmt_ms(task_24h["p50_ms"])),
            ("24h 单任务 P95 / 24h P95 Task", fmt_ms(task_24h["p95_ms"])),
            ("7d 单任务 P95 / 7d P95 Task", fmt_ms(data["task_duration_7d"]["p95_ms"])),
            ("24h Session 数 / 24h Sessions", data["session_24h"]["count"]),
            ("24h Session 平均 / 24h Avg Session", fmt_ms(session_24h["avg_duration_ms"])),
            ("24h Session 平均调用 / 24h Avg Calls per Session", data["session_24h"]["avg_calls"]),
        ],
    )
    quality_panel = render_key_values(
        "质量与留存 / Quality & Retention",
        [
            ("24h 错误 / 24h Errors", data["error_24h"]),
            ("24h 错误率 / 24h Error Rate", data["error_rate_24h"]),
            ("24h 异常结束 / 24h Orphan Starts", data["orphan_starts_24h"]),
            ("24h 异常结束率 / 24h Orphan Rate", data["orphan_rate_24h"]),
            ("24h 新增设备 / 24h New Devices", data["new_installs_24h"]),
            ("7d 新增设备 / 7d New Devices", data["new_installs_7d"]),
            ("24h 回访设备 / 24h Returning Devices", data["returning_installs_24h"]),
        ],
    )

    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>Guanlan Telemetry</title>
  <link rel="icon" href="/assets/guanlan-logo.svg" type="image/svg+xml">
  <style>
    :root {{
      --bg: #f5f5f7;
      --card: #ffffff;
      --card-border: #e7e7ec;
      --text: #1d1d1f;
      --muted: #6e6e73;
      --shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
    }}
    body {{ margin:0; font:14px/1.5 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif; background:var(--bg); color:var(--text); }}
    header {{ background:rgba(255,255,255,0.86); border-bottom:1px solid #e8e8ee; backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); padding:14px 24px; position:sticky; top:0; z-index:10; }}
    .brand {{ display:flex; align-items:center; gap:12px; }}
    .brand img {{ width:38px; height:38px; border-radius:8px; }}
    .brand-title {{ display:flex; flex-direction:column; }}
    .brand-title strong {{ font-size:20px; letter-spacing:0; }}
    .brand-title span {{ color:var(--muted); font-size:12px; }}
    main {{ padding:20px 24px 36px; max-width:1240px; margin:0 auto; }}
    .hero-cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
    .hero-grid {{ display:grid; grid-template-columns:2fr 1fr 1fr; gap:12px; align-items:stretch; margin-top:10px; }}
    .stats-cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-top:14px; }}
    .core-card, .card, section {{ background:var(--card); border:1px solid var(--card-border); border-radius:8px; box-shadow:var(--shadow); }}
    .core-card {{ padding:14px 16px; min-height:96px; }}
    .core-card span {{ display:block; color:var(--muted); font-size:12px; }}
    .core-card strong {{ display:block; margin-top:8px; font-size:36px; line-height:1; }}
    .core-card-link {{ text-decoration:none; color:inherit; position:relative; }}
    .core-card-link:hover {{ border-color:#c8c9d4; box-shadow:0 8px 24px rgba(15,23,42,0.1); }}
    .core-card-link em {{ position:absolute; right:14px; bottom:12px; color:#2563eb; font-style:normal; font-size:12px; }}
    .card {{ padding:14px 16px; }}
    .card span {{ display:block; color:var(--muted); font-size:12px; }}
    .card strong {{ display:block; margin-top:6px; font-size:26px; line-height:1.1; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:14px; margin-top:16px; }}
    section {{ padding:14px 16px; overflow:auto; }}
    h2 {{ margin:0 0 10px; font-size:15px; }}
    table {{ width:100%; border-collapse:collapse; }}
    td, th {{ padding:8px 6px; border-bottom:1px solid #eef0f3; text-align:left; white-space:nowrap; }}
    th {{ color:var(--muted); font-size:12px; }}
    .recent {{ margin-top:16px; }}
    .feedback-item {{ border:1px solid #ececf2; border-radius:8px; margin-bottom:10px; background:#fff; }}
    .feedback-item summary {{ cursor:pointer; list-style:none; padding:10px 12px; }}
    .feedback-item summary::-webkit-details-marker {{ display:none; }}
    .feedback-row {{ display:grid; grid-template-columns:70px 170px minmax(220px,1.15fr) minmax(240px,1.2fr) 1.05fr 80px 180px 130px; gap:10px; align-items:start; }}
    .feedback-index {{ font-weight:600; color:#4b5563; }}
    .feedback-time {{ color:#6e6e73; font-size:12px; }}
    .feedback-query {{ white-space:normal; overflow:visible; text-overflow:clip; word-break:break-word; line-height:1.35; }}
    .feedback-reason-preview {{ color:#3f3f46; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .feedback-inline-meta {{ color:#6e6e73; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .feedback-version {{ color:#0f172a; font-size:12px; font-weight:700; white-space:nowrap; }}
    .feedback-kind {{ font-size:12px; font-weight:600; white-space:nowrap; }}
    .feedback-kind-real {{ color:#0f766e; }}
    .feedback-kind-synthetic {{ color:#b45309; }}
    .feedback-expand-hint {{ justify-self:end; color:#2563eb; font-size:12px; }}
    .feedback-item[open] .feedback-expand-hint {{ color:#4b5563; }}
    .feedback-item[open] .feedback-expand-hint::after {{ content:"（已展开）"; }}
    .feedback-body {{ border-top:1px solid #ececf2; padding:10px 12px 12px; }}
    .feedback-body p {{ margin:0 0 8px; }}
    .feedback-query-full {{ white-space:pre-wrap; word-break:break-word; }}
    .feedback-reason {{ white-space:pre-wrap; word-break:break-word; }}
    .feedback-meta {{ color:#6e6e73; font-size:12px; }}
    .feedback-empty {{ color:#6e6e73; margin:4px 0; }}
    @media (max-width: 1100px) {{
      .hero-grid {{ grid-template-columns:1fr; }}
    }}
    @media (max-width: 780px) {{
      .feedback-row {{ grid-template-columns:1fr; gap:4px; }}
      .feedback-expand-hint {{ justify-self:start; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <img src="/assets/guanlan-logo.svg" alt="">
      <div class="brand-title">
        <strong>观澜遥测面板 / Guanlan Telemetry</strong>
        <span>Guanlan Telemetry</span>
      </div>
    </div>
  </header>
  <main>
    <div class="hero-grid">
      <div class="hero-cards">{core_cards}</div>
      {core_platform_devices}
      {core_platform_agents}
    </div>
    <div class="stats-cards">{secondary_cards}</div>
    <div class="grid">
      {surface}
      {commands}
      {agents}
      {versions}
      {platforms}
      {platform_devices}
      {platform_agents}
      {feedback_commands}
      {feedback_queries}
      {feedback_reasons}
      {depth}
      {quality}
    </div>
    {feedback_inbox}
    <section class="recent">
      <h2>最近事件 / Recent Events</h2>
      <table>
        <thead><tr><th>时间 / Time (CST)</th><th>事件 / Event</th><th>入口 / Surface</th><th>命令 / Command</th><th>Agent</th><th>版本 / Version</th><th>状态 / Status</th><th>耗时 / Duration (ms)</th></tr></thead>
        <tbody>{recent}</tbody>
      </table>
    </section>
  </main>
</body>
</html>""".format(
        core_cards=core_card_html,
        secondary_cards=secondary_card_html,
        core_platform_devices=render_group("平台独立设备 / Platform Unique Devices (All-time)", data["platform_unique_devices_all"]),
        core_platform_agents=render_group("平台独立 Agent / Platform Unique Agents (All-time)", data["platform_unique_agents_all"]),
        surface=render_group("入口分布 / Surface", data["surface"]),
        commands=render_group("命令分布 / Commands", data["commands"]),
        agents=render_group("Agent 类型 / Agent Types", data["agents"]),
        versions=render_group("版本分布 / Versions", data["versions"]),
        platforms=render_group("平台调用分布 / Platform Calls", data["platforms"]),
        platform_devices=render_group("平台独立设备 / Platform Unique Devices", data["platform_unique_devices"]),
        platform_agents=render_group("平台独立 Agent / Platform Unique Agents", data["platform_unique_agents"]),
        feedback_commands=render_group("有效反馈命令 / Real Feedback Commands", data["feedback_commands"]),
        feedback_queries=render_group("有效高频问题词 / Real Top Problem Queries", data["feedback_queries"]),
        feedback_reasons=render_group("有效问题原因 / Real Pain Reasons", data["feedback_reasons"]),
        depth=depth_panel,
        quality=quality_panel,
        recent="\n".join(recent_rows),
        feedback_inbox=render_feedback_inbox(data["recent_feedback"]),
    )


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    server_version = "GuanlanTelemetry/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def send_text(self, status, text, content_type="text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        if not ADMIN_PASSWORD:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        except Exception:
            return False
        user, _, password = raw.partition(":")
        return hmac.compare_digest(user, ADMIN_USER) and hmac.compare_digest(password, ADMIN_PASSWORD)

    def require_auth(self):
        if self.authorized():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Guanlan Telemetry"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def ingest_authorized(self, parsed):
        if not INGEST_TOKEN:
            return True
        token = self.headers.get("X-Guanlan-Token", "")
        if not token:
            token = (parse_qs(parsed.query).get("token") or [""])[0]
        return hmac.compare_digest(token, INGEST_TOKEN)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self.send_text(200, "ok\n")
            return
        if parsed.path == "/api/summary":
            if not self.require_auth():
                return
            self.send_text(200, json.dumps(summary(), ensure_ascii=False), "application/json; charset=utf-8")
            return
        if parsed.path in ("/", "/dashboard"):
            if not self.require_auth():
                return
            self.send_text(200, render_dashboard(), "text/html; charset=utf-8")
            return
        self.send_text(404, "not found\n")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in ("/v1/events", "/v1/feedback"):
            self.send_text(404, "not found\n")
            return
        if not self.ingest_authorized(parsed):
            self.send_text(401, "unauthorized\n")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self.send_text(413, "bad body\n")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_text(400, "bad json\n")
            return
        if not isinstance(payload, dict):
            self.send_text(400, "bad payload\n")
            return
        if parsed.path == "/v1/events":
            ok = record_event(payload, self.client_address[0])
        else:
            ok = record_feedback(payload, self.client_address[0])
        if not ok:
            self.send_text(400, "ignored\n")
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    init_db()
    httpd = ThreadedHTTPServer((BIND_HOST, BIND_PORT), Handler)
    print("Guanlan telemetry collector listening on %s:%s" % (BIND_HOST, BIND_PORT))
    httpd.serve_forever()


if __name__ == "__main__":
    main()
