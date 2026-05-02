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


def now_ms():
    return int(time.time() * 1000)


def clamp_text(value, limit=160):
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > limit:
        return text[:limit]
    return text


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
        data = {
            "generated_ms": current,
            "last_event_age_ms": max(
                0,
                current - (query_one(conn, "SELECT MAX(received_ms) FROM events") or current),
            ),
            "active_now": query_one(conn, "SELECT COUNT(*) FROM active_invocations"),
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
            "recent": [],
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
        items.append("<tr><td colspan='2'>No data yet</td></tr>")
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


def render_dashboard():
    data = summary()
    task_24h = data["task_duration_24h"]
    session_24h = data["session_24h"]
    cards = [
        ("当前并发", data["active_now"]),
        ("最近事件", fmt_ms(data["last_event_age_ms"]) + " 前"),
        ("24h 调用", data["calls_24h"]),
        ("7d 调用", data["calls_7d"]),
        ("24h 独立 Agent", data["unique_agents_24h"]),
        ("7d 独立 Agent", data["unique_agents_7d"]),
        ("24h 独立设备", data["active_installs_24h"]),
        ("7d 独立设备", data["active_installs_7d"]),
        ("24h 新增设备", data["new_installs_24h"]),
        ("24h 回访设备", data["returning_installs_24h"]),
        ("Agent 日均调用", data["calls_per_agent_24h"]),
        ("设备日均调用", data["calls_per_device_24h"]),
        ("任务平均时长", fmt_ms(task_24h["avg_ms"])),
        ("任务 P95 时长", fmt_ms(task_24h["p95_ms"])),
        ("Session 平均时长", fmt_ms(session_24h["avg_duration_ms"])),
        ("Session P95 时长", fmt_ms(session_24h["p95_duration_ms"])),
        ("24h 错误率", data["error_rate_24h"]),
        ("24h 异常结束率", data["orphan_rate_24h"]),
    ]
    card_html = "\n".join(
        "<div class='card'><span>{}</span><strong>{}</strong></div>".format(label, value)
        for label, value in cards
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
        recent_rows.append("<tr><td colspan='8'>No events yet</td></tr>")

    depth_panel = render_key_values(
        "使用深度",
        [
            ("24h 单任务平均", fmt_ms(task_24h["avg_ms"])),
            ("24h 单任务 P50", fmt_ms(task_24h["p50_ms"])),
            ("24h 单任务 P95", fmt_ms(task_24h["p95_ms"])),
            ("7d 单任务 P95", fmt_ms(data["task_duration_7d"]["p95_ms"])),
            ("24h Session 数", data["session_24h"]["count"]),
            ("24h Session 平均", fmt_ms(session_24h["avg_duration_ms"])),
            ("24h Session 平均调用", data["session_24h"]["avg_calls"]),
        ],
    )
    quality_panel = render_key_values(
        "质量与留存",
        [
            ("24h 错误", data["error_24h"]),
            ("24h 错误率", data["error_rate_24h"]),
            ("24h 异常结束", data["orphan_starts_24h"]),
            ("24h 异常结束率", data["orphan_rate_24h"]),
            ("24h 新增设备", data["new_installs_24h"]),
            ("7d 新增设备", data["new_installs_7d"]),
            ("24h 回访设备", data["returning_installs_24h"]),
        ],
    )

    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="5">
  <title>Guanlan Telemetry</title>
  <link rel="icon" href="/assets/guanlan-logo.svg" type="image/svg+xml">
  <style>
    body {{ margin:0; font:14px/1.5 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif; background:#f6f7f9; color:#20242a; }}
    header {{ background:#111827; color:white; padding:18px 28px; }}
    .brand {{ display:flex; align-items:center; gap:12px; }}
    .brand img {{ width:38px; height:38px; border-radius:8px; }}
    .brand-title {{ display:flex; flex-direction:column; }}
    .brand-title strong {{ font-size:20px; letter-spacing:0; }}
    .brand-title span {{ color:#b8c2d6; font-size:12px; }}
    main {{ padding:22px 28px 40px; max-width:1180px; margin:0 auto; }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }}
    .card, section {{ background:white; border:1px solid #e5e7eb; border-radius:8px; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
    .card {{ padding:14px 16px; }}
    .card span {{ display:block; color:#667085; font-size:12px; }}
    .card strong {{ display:block; margin-top:6px; font-size:28px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:14px; margin-top:16px; }}
    section {{ padding:14px 16px; overflow:auto; }}
    h2 {{ margin:0 0 10px; font-size:15px; }}
    table {{ width:100%; border-collapse:collapse; }}
    td, th {{ padding:8px 6px; border-bottom:1px solid #eef0f3; text-align:left; white-space:nowrap; }}
    th {{ color:#667085; font-size:12px; }}
    .recent {{ margin-top:16px; }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <img src="/assets/guanlan-logo.svg" alt="">
      <div class="brand-title">
        <strong>观澜遥测面板</strong>
        <span>Guanlan Telemetry</span>
      </div>
    </div>
  </header>
  <main>
    <div class="cards">{cards}</div>
    <div class="grid">
      {surface}
      {commands}
      {agents}
      {versions}
      {platforms}
      {depth}
      {quality}
    </div>
    <section class="recent">
      <h2>Recent events</h2>
      <table>
        <thead><tr><th>Time CST</th><th>Event</th><th>Surface</th><th>Command</th><th>Agent</th><th>Version</th><th>Status</th><th>Duration ms</th></tr></thead>
        <tbody>{recent}</tbody>
      </table>
    </section>
  </main>
</body>
</html>""".format(
        cards=card_html,
        surface=render_group("Surface", data["surface"]),
        commands=render_group("Commands", data["commands"]),
        agents=render_group("Agents", data["agents"]),
        versions=render_group("Versions", data["versions"]),
        platforms=render_group("Platforms", data["platforms"]),
        depth=depth_panel,
        quality=quality_panel,
        recent="\n".join(recent_rows),
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
        if parsed.path != "/v1/events":
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
        ok = record_event(payload, self.client_address[0])
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
