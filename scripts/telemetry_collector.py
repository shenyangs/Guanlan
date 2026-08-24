#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tiny Guanlan telemetry collector.

This server uses only the Python standard library so it can run on small ECS
instances without a package install step. It stores minimal lifecycle metadata
in SQLite and exposes a Basic Auth dashboard.
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
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlencode, urlparse

DB_PATH = os.environ.get("GUANLAN_DB", "/var/lib/guanlan-telemetry/events.db")
BIND_HOST = os.environ.get("GUANLAN_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("GUANLAN_PORT", "8080"))
ADMIN_USER = os.environ.get("GUANLAN_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("GUANLAN_ADMIN_PASSWORD", "")
INGEST_TOKEN = os.environ.get("GUANLAN_INGEST_TOKEN", "")
ACTIVE_TTL_SECONDS = int(os.environ.get("GUANLAN_ACTIVE_TTL_SECONDS", "180"))
# Do not classify a just-started invocation as unclosed while its terminal
# event can still be waiting in a local durable queue or crossing the network.
ORPHAN_SETTLEMENT_GRACE_SECONDS = max(
    ACTIVE_TTL_SECONDS,
    int(os.environ.get("GUANLAN_ORPHAN_SETTLEMENT_GRACE_SECONDS", "600")),
)
# A client event timestamp is the semantic time for health metrics.  Received
# time is retained separately for delivery-lag diagnostics and must not make a
# week-old local queue replay look like fresh product activity.
EVENT_TIME_FUTURE_SKEW_SECONDS = max(
    0,
    int(os.environ.get("GUANLAN_EVENT_TIME_FUTURE_SKEW_SECONDS", "300")),
)
INGEST_EVENT_MAX_AGE_SECONDS = max(
    3600,
    int(os.environ.get("GUANLAN_INGEST_EVENT_MAX_AGE_SECONDS", str(7 * 24 * 3600))),
)
MAX_BODY_BYTES = 16 * 1024
IP_GEO_LOOKUP_ENABLED = os.environ.get("GUANLAN_IP_GEO_LOOKUP", "0") == "1"
IP_GEO_CACHE_TTL_SECONDS = int(os.environ.get("GUANLAN_IP_GEO_CACHE_TTL_SECONDS", str(7 * 24 * 3600)))
SITE_VISIT_ALLOWED_HOSTS = set(
    host.strip().lower()
    for host in os.environ.get(
        "GUANLAN_SITE_VISIT_ALLOWED_HOSTS",
        "guanlan.xin,www.guanlan.xin,101.37.70.222",
    ).split(",")
    if host.strip()
)
DASHBOARD_CACHE_TTL_SECONDS = max(
    1,
    int(os.environ.get("GUANLAN_DASHBOARD_CACHE_TTL_SECONDS", "30")),
)
DASHBOARD_REFRESH_STUCK_SECONDS = max(
    30,
    int(os.environ.get("GUANLAN_DASHBOARD_REFRESH_STUCK_SECONDS", "180")),
)
RETENTION_CACHE_TTL_SECONDS = max(
    300,
    int(os.environ.get("GUANLAN_RETENTION_CACHE_TTL_SECONDS", str(6 * 3600))),
)
SLOW_METRICS_CACHE_TTL_SECONDS = max(
    60,
    int(os.environ.get("GUANLAN_SLOW_METRICS_CACHE_TTL_SECONDS", "300")),
)
HEALTH_METRICS_CACHE_TTL_SECONDS = max(
    1,
    int(os.environ.get("GUANLAN_HEALTH_METRICS_CACHE_TTL_SECONDS", "30")),
)
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
_DASHBOARD_CACHE_LOCK = threading.Lock()
_DASHBOARD_CACHE = {"built_ms": 0, "html": "", "refreshing": False, "refresh_started_ms": 0}
_ASYNC_STATS_CACHE_LOCK = threading.Lock()
_ASYNC_STATS_CACHE = {}
_HEAVY_STATS_LOCK = threading.Lock()


def now_ms():
    return int(time.time() * 1000)


def event_time_upper_bound(current_ms):
    """Allow a small client clock lead without admitting unbounded future data."""
    return current_ms + EVENT_TIME_FUTURE_SKEW_SECONDS * 1000


def event_time_is_acceptable(event_ms, current_ms):
    """Return whether an event is recent enough to retain as telemetry."""
    return (
        current_ms - INGEST_EVENT_MAX_AGE_SECONDS * 1000 <= int(event_ms) <= event_time_upper_bound(current_ms)
    )


def log_info(message):
    sys.stderr.write("[guanlan-telemetry] %s\n" % message)


def clamp_text(value, limit=160):
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > limit:
        return text[:limit]
    return text


def sanitize_site_path(value):
    """Keep a page path for aggregate site metrics, never its query string."""
    text = clamp_text(value, 240)
    if not text:
        return "/"
    try:
        path = urlparse(text).path or "/"
    except Exception:
        path = text.split("?", 1)[0].split("#", 1)[0] or "/"
    return clamp_text(path, 240)


def sanitize_referrer(value):
    """Retain only a referrer's origin; paths can contain private context."""
    text = clamp_text(value, 240)
    if not text:
        return ""
    try:
        parsed = urlparse(text)
        if parsed.scheme and parsed.netloc:
            return "%s://%s" % (parsed.scheme, parsed.netloc)
    except Exception:
        pass
    return ""


def normalize_query_text(value):
    return str(value or "").strip().lower()


def normalize_cluster_text(value):
    text = " ".join(str(value or "").strip().lower().split())
    return text[:320]


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


def retention_placeholder(offsets=(1, 3, 7, 14, 30)):
    return [
        {
            "offset": offset,
            "cohort": 0,
            "retained": 0,
            "rate": 0,
            "pending": True,
        }
        for offset in offsets
    ]


def _async_cache_snapshot(name, default_value):
    with _ASYNC_STATS_CACHE_LOCK:
        entry = _ASYNC_STATS_CACHE.get(name)
        if entry is None:
            entry = {
                "value": default_value,
                "built_ms": 0,
                "refreshing": False,
                "refresh_started_ms": 0,
            }
            _ASYNC_STATS_CACHE[name] = entry
        return dict(entry)


def _async_cache_store(name, value):
    with _ASYNC_STATS_CACHE_LOCK:
        entry = _ASYNC_STATS_CACHE.setdefault(name, {})
        entry["value"] = value
        entry["built_ms"] = now_ms()
        entry["refreshing"] = False
        entry["refresh_started_ms"] = 0


def _async_cache_finish(name, keep_value=False):
    with _ASYNC_STATS_CACHE_LOCK:
        entry = _ASYNC_STATS_CACHE.setdefault(name, {})
        entry["refreshing"] = False
        entry["refresh_started_ms"] = 0
        if keep_value and "value" not in entry:
            entry["value"] = None


def _async_cache_worker(name, builder, heavy=False):
    started = time.time()
    try:
        if heavy:
            # Retention/all-time scans share one SQLite database with ingest.
            # A single-flight queue is slower for a stale secondary panel, but
            # prevents dashboard requests from multiplying full-table scans.
            with _HEAVY_STATS_LOCK:
                value = builder()
        else:
            value = builder()
        _async_cache_store(name, value)
        elapsed = time.time() - started
        if elapsed >= 1.0:
            log_info("async cache refreshed %s in %.2fs" % (name, elapsed))
    except Exception as exc:
        _async_cache_finish(name, keep_value=True)
        log_info("async cache refresh failed for %s: %s" % (name, exc))


def ensure_async_cache_refresh(name, builder, default_value=None, *, heavy=False):
    current = now_ms()
    with _ASYNC_STATS_CACHE_LOCK:
        entry = _ASYNC_STATS_CACHE.setdefault(
            name,
            {
                "value": default_value,
                "built_ms": 0,
                "refreshing": False,
                "refresh_started_ms": 0,
            },
        )
        refresh_started_ms = int(entry.get("refresh_started_ms") or 0)
        if entry.get("refreshing"):
            if refresh_started_ms and current - refresh_started_ms > DASHBOARD_REFRESH_STUCK_SECONDS * 1000:
                log_info("async cache refresh remains single-flight after timeout: %s" % name)
            return False
        entry["refreshing"] = True
        entry["refresh_started_ms"] = current
    thread = threading.Thread(
        target=_async_cache_worker,
        args=(name, builder, heavy),
        name="guanlan-async-cache-%s" % name,
        daemon=True,
    )
    thread.start()
    return True


def get_async_cached_value(
    name,
    ttl_seconds,
    builder,
    default_value=None,
    *,
    wait_for_initial=False,
    heavy=False,
):
    current = now_ms()
    snapshot = _async_cache_snapshot(name, default_value)
    built_ms = int(snapshot.get("built_ms") or 0)
    value = snapshot.get("value", default_value)
    if built_ms and current - built_ms < ttl_seconds * 1000:
        return value
    if wait_for_initial and not built_ms:
        # A zero-valued placeholder is fine for a background API response, but
        # it is misleading in a human-facing health panel. The first dashboard
        # render waits for a coherent baseline; later refreshes keep the last
        # complete value while a new one is built asynchronously.
        value = builder()
        _async_cache_store(name, value)
        return value
    ensure_async_cache_refresh(name, builder, default_value, heavy=heavy)
    return value


def hash_site_ip(remote_addr):
    ip = str(remote_addr or "").strip()
    if not ip:
        return ""
    return hashlib.sha256(("guanlan-site-ip-v1|" + ip).encode("utf-8")).hexdigest()[:32]


def parse_user_agent(user_agent):
    ua = str(user_agent or "")
    lowered = ua.lower()
    if "micromessenger" in lowered:
        browser = "WeChat"
    elif "edg/" in lowered:
        browser = "Edge"
    elif "chrome/" in lowered or "crios/" in lowered:
        browser = "Chrome"
    elif "safari/" in lowered and "chrome/" not in lowered and "crios/" not in lowered:
        browser = "Safari"
    elif "firefox/" in lowered or "fxios/" in lowered:
        browser = "Firefox"
    elif "curl/" in lowered:
        browser = "curl"
    else:
        browser = "unknown"

    if "iphone" in lowered or "ipad" in lowered or "ios" in lowered:
        os_name = "iOS"
    elif "android" in lowered:
        os_name = "Android"
    elif "mac os x" in lowered or "macintosh" in lowered:
        os_name = "macOS"
    elif "windows" in lowered:
        os_name = "Windows"
    elif "linux" in lowered:
        os_name = "Linux"
    else:
        os_name = "unknown"

    if "bot" in lowered or "spider" in lowered or "crawler" in lowered:
        device_type = "bot"
    elif "ipad" in lowered or "tablet" in lowered:
        device_type = "tablet"
    elif "mobile" in lowered or "iphone" in lowered or "android" in lowered:
        device_type = "mobile"
    elif browser == "curl":
        device_type = "script"
    else:
        device_type = "desktop"

    return {"browser": browser, "os": os_name, "device_type": device_type}


def is_public_ip(remote_addr):
    ip = str(remote_addr or "").strip()
    if not ip:
        return False
    if ":" in ip and ip.count(":") == 1 and ip.rsplit(":", 1)[1].isdigit():
        ip = ip.rsplit(":", 1)[0]
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        first = int(parts[0])
        second = int(parts[1])
        if first == 10 or first == 127:
            return False
        if first == 172 and 16 <= second <= 31:
            return False
        if first == 192 and second == 168:
            return False
        if first == 169 and second == 254:
            return False
        return True
    except Exception:
        return False


def fetch_ip_geo(remote_addr):
    if not IP_GEO_LOOKUP_ENABLED or not is_public_ip(remote_addr):
        return {}
    url = (
        "http://ip-api.com/json/%s?fields=status,country,regionName,city,isp,org,as,query"
        % str(remote_addr).strip()
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "guanlan-telemetry/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            payload = json.loads(resp.read(8192).decode("utf-8"))
    except Exception:
        return {}
    if payload.get("status") != "success":
        return {}
    return {
        "country": clamp_text(payload.get("country"), 80),
        "region": clamp_text(payload.get("regionName"), 80),
        "city": clamp_text(payload.get("city"), 80),
        "isp": clamp_text(payload.get("isp"), 160),
        "org": clamp_text(payload.get("org"), 160),
        "asn": clamp_text(payload.get("as"), 120),
    }


def get_ip_geo(conn, remote_addr, allow_fetch=True):
    ip_hash = hash_site_ip(remote_addr)
    if not ip_hash:
        return {}
    current = now_ms()
    row = conn.execute(
        "SELECT country, region, city, isp, org, asn, updated_ms FROM ip_geo_cache WHERE ip_hash = ?",
        (ip_hash,),
    ).fetchone()
    if row and current - int(row["updated_ms"] or 0) < IP_GEO_CACHE_TTL_SECONDS * 1000:
        return dict(row)
    if not allow_fetch:
        return dict(row) if row else {}
    geo = fetch_ip_geo(remote_addr)
    if not geo:
        if row:
            return dict(row)
        return {}
    conn.execute(
        """
        INSERT OR REPLACE INTO ip_geo_cache (
            ip_hash, remote_addr, country, region, city, isp, org, asn, updated_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ip_hash,
            clamp_text(remote_addr, 80),
            geo["country"],
            geo["region"],
            geo["city"],
            geo["isp"],
            geo["org"],
            geo["asn"],
            current,
        ),
    )
    conn.commit()
    geo["updated_ms"] = current
    return geo


def db_connect():
    parent = os.path.dirname(DB_PATH)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    conn = db_connect()
    try:
        # Configure journal mode once at service start. Reissuing this pragma
        # for every ingest connection contends with readers under dashboard
        # load and amplifies write latency.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
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
            CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_id);
            CREATE INDEX IF NOT EXISTS idx_events_invocation ON events(invocation_id);
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_event_received ON events(event, received_ms);
            CREATE INDEX IF NOT EXISTS idx_events_event_ts ON events(event, ts_ms);

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
            CREATE INDEX IF NOT EXISTS idx_feedback_install ON feedback(install_id);

            CREATE TABLE IF NOT EXISTS site_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_ms INTEGER NOT NULL,
                ip_hash TEXT NOT NULL,
                remote_addr TEXT NOT NULL DEFAULT '',
                host TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL,
                referrer TEXT NOT NULL,
                user_agent TEXT NOT NULL,
                browser TEXT NOT NULL DEFAULT '',
                os TEXT NOT NULL DEFAULT '',
                device_type TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                languages TEXT NOT NULL DEFAULT '',
                timezone TEXT NOT NULL DEFAULT '',
                screen TEXT NOT NULL DEFAULT '',
                viewport TEXT NOT NULL DEFAULT '',
                device_pixel_ratio TEXT NOT NULL DEFAULT '',
                network_effective_type TEXT NOT NULL DEFAULT '',
                network_downlink TEXT NOT NULL DEFAULT '',
                network_rtt TEXT NOT NULL DEFAULT '',
                network_save_data TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_site_visits_received ON site_visits(received_ms);
            CREATE INDEX IF NOT EXISTS idx_site_visits_ip ON site_visits(ip_hash);

            CREATE TABLE IF NOT EXISTS ip_geo_cache (
                ip_hash TEXT PRIMARY KEY,
                remote_addr TEXT NOT NULL,
                country TEXT NOT NULL DEFAULT '',
                region TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                isp TEXT NOT NULL DEFAULT '',
                org TEXT NOT NULL DEFAULT '',
                asn TEXT NOT NULL DEFAULT '',
                updated_ms INTEGER NOT NULL
            );
            """
        )
        ensure_column(conn, "events", "agent_id", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "active_invocations", "agent_id", "TEXT NOT NULL DEFAULT ''")
        for column, definition in (
            ("remote_addr", "TEXT NOT NULL DEFAULT ''"),
            ("host", "TEXT NOT NULL DEFAULT ''"),
            ("browser", "TEXT NOT NULL DEFAULT ''"),
            ("os", "TEXT NOT NULL DEFAULT ''"),
            ("device_type", "TEXT NOT NULL DEFAULT ''"),
            ("language", "TEXT NOT NULL DEFAULT ''"),
            ("languages", "TEXT NOT NULL DEFAULT ''"),
            ("timezone", "TEXT NOT NULL DEFAULT ''"),
            ("screen", "TEXT NOT NULL DEFAULT ''"),
            ("viewport", "TEXT NOT NULL DEFAULT ''"),
            ("device_pixel_ratio", "TEXT NOT NULL DEFAULT ''"),
            ("network_effective_type", "TEXT NOT NULL DEFAULT ''"),
            ("network_downlink", "TEXT NOT NULL DEFAULT ''"),
            ("network_rtt", "TEXT NOT NULL DEFAULT ''"),
            ("network_save_data", "TEXT NOT NULL DEFAULT ''"),
        ):
            ensure_column(conn, "site_visits", column, definition)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_site_visits_remote ON site_visits(remote_addr)")
        # Old collectors need one migration to fill legacy agent ids and
        # remove duplicate lifecycle rows before the uniqueness guard exists.
        # Re-running those full-table writes at every restart made a large
        # collector unavailable for minutes, so their completed index is the
        # durable migration marker.
        has_lifecycle_unique_index = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            ("idx_events_event_invocation",),
        ).fetchone()
        if not has_lifecycle_unique_index:
            backfill_agent_ids(conn)
            dedupe_events(conn)
            conn.execute(
                "CREATE UNIQUE INDEX idx_events_event_invocation ON events(event, invocation_id)"
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
        # Invocation lifecycle analytics does not need a network address.
        "remote_addr": "",
    }
    if not row["install_id"] or not row["invocation_id"]:
        return False
    if not row["agent_id"]:
        row["agent_id"] = fallback_agent_id(row["install_id"], row["agent_kind"])
    try:
        row["duration_ms"] = int(row["duration_ms"]) if row["duration_ms"] is not None else None
    except Exception:
        row["duration_ms"] = None
    if not event_time_is_acceptable(row["ts_ms"], current):
        # Acknowledge stale local-queue telemetry so legacy clients stop
        # retrying it. This is observability data, not product state.
        return True

    conn = db_connect()
    try:
        prune_active(conn, current)
        # Retain one heartbeat event per invocation. The unique index keeps the
        # table bounded while giving orphan diagnostics evidence that a client
        # was alive even if its terminal event never reached the collector.
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
        # Feedback is already user-provided content; avoid adding network
        # identifiers to that record.
        "remote_addr": "",
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


def record_site_visit(payload, remote_addr, headers):
    ip_hash = hash_site_ip(remote_addr)
    if not ip_hash:
        return False
    path = sanitize_site_path(payload.get("path") or "/")
    if path.startswith("/guanlan-telemetry") or path.startswith("/telemetry"):
        return False
    ua_info = parse_user_agent(clamp_text(headers.get("User-Agent", ""), 240))
    row = {
        "received_ms": now_ms(),
        "ip_hash": ip_hash,
        # ip_hash supports anonymous visit counting. Do not retain raw IPs.
        "remote_addr": "",
        "host": clamp_text(headers.get("Host", ""), 120),
        "path": path,
        "referrer": sanitize_referrer(payload.get("referrer")),
        # Parsed categories below are enough for dashboard segmentation.
        "user_agent": "",
        "browser": ua_info["browser"],
        "os": ua_info["os"],
        "device_type": ua_info["device_type"],
        "language": clamp_text(payload.get("language"), 80),
        "languages": clamp_text(payload.get("languages"), 160),
        "timezone": clamp_text(payload.get("timezone"), 80),
        "screen": clamp_text(payload.get("screen"), 40),
        "viewport": clamp_text(payload.get("viewport"), 40),
        "device_pixel_ratio": clamp_text(payload.get("device_pixel_ratio"), 20),
        "network_effective_type": clamp_text(payload.get("network_effective_type"), 24),
        "network_downlink": clamp_text(payload.get("network_downlink"), 24),
        "network_rtt": clamp_text(payload.get("network_rtt"), 24),
        "network_save_data": clamp_text(payload.get("network_save_data"), 12),
    }
    conn = db_connect()
    try:
        conn.execute(
            """
            INSERT INTO site_visits (
                received_ms, ip_hash, remote_addr, host, path, referrer, user_agent,
                browser, os, device_type, language, languages, timezone, screen, viewport,
                device_pixel_ratio, network_effective_type, network_downlink, network_rtt,
                network_save_data
            ) VALUES (
                :received_ms, :ip_hash, :remote_addr, :host, :path, :referrer, :user_agent,
                :browser, :os, :device_type, :language, :languages, :timezone, :screen, :viewport,
                :device_pixel_ratio, :network_effective_type, :network_downlink, :network_rtt,
                :network_save_data
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


def query_platform_unique(conn, field, since_ms=None, limit=10, current_ms=None):
    allowed = set(["install_id", "agent_id"])
    if field not in allowed:
        return []
    where = "platform <> '' AND {field} <> ''".format(field=field)
    params = []
    if since_ms is not None:
        if current_ms is not None:
            where = "ts_ms >= ? AND ts_ms < ? AND " + where
            params.extend([since_ms, event_time_upper_bound(current_ms)])
        else:
            where = "ts_ms >= ? AND " + where
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


def query_duration_stats(conn, since_ms, current_ms=None):
    params = [since_ms]
    upper_clause = ""
    if current_ms is not None:
        upper_clause = " AND ts_ms < ?"
        params.append(event_time_upper_bound(current_ms))
    rows = conn.execute(
        """
        SELECT duration_ms FROM events
        WHERE ts_ms >= ?
        {upper_clause}
          AND event = 'invocation_end'
          AND duration_ms IS NOT NULL
          AND duration_ms >= 0
        """.format(upper_clause=upper_clause),
        tuple(params),
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


def query_session_stats(conn, since_ms, current_ms=None):
    params = [since_ms]
    upper_clause = ""
    if current_ms is not None:
        upper_clause = " AND ts_ms < ?"
        params.append(event_time_upper_bound(current_ms))
    rows = conn.execute(
        """
        SELECT install_id,
               agent_id,
               CASE
                   WHEN TRIM(COALESCE(session_id, '')) <> '' THEN session_id
                   ELSE 'invocation:' || invocation_id
               END AS effective_session_id,
               MIN(ts_ms) AS first_seen,
               MAX(ts_ms) AS last_seen,
               COUNT(CASE WHEN event = 'invocation_start' THEN 1 END) AS calls
        FROM events
        WHERE ts_ms >= ?
          {upper_clause}
          AND event IN ('invocation_start', 'invocation_end')
        GROUP BY install_id, agent_id, effective_session_id
        """.format(upper_clause=upper_clause),
        tuple(params),
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
            SELECT install_id, MIN(ts_ms) AS first_seen
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
            SELECT install_id, MIN(ts_ms) AS first_seen
            FROM events
            GROUP BY install_id
        ) firsts ON firsts.install_id = e.install_id
        WHERE e.ts_ms >= ?
          AND firsts.first_seen < ?
        """,
        (since_ms, since_ms),
    )


def query_retention_stats(conn, field, offsets=(1, 3, 7, 14, 30)):
    allowed = set(["install_id", "agent_id"])
    if field not in allowed:
        return []
    current_date = (_dt.datetime.utcfromtimestamp(now_ms() / 1000.0) + _dt.timedelta(hours=8)).date()
    stats = []
    for offset in offsets:
        cutoff_date = (current_date - _dt.timedelta(days=offset)).isoformat()
        row = conn.execute(
            """
            WITH firsts AS (
                SELECT {field} AS entity,
                       MIN(date(received_ms / 1000, 'unixepoch', '+8 hours')) AS first_date
                FROM events
                WHERE event = 'invocation_start'
                  AND {field} <> ''
                GROUP BY {field}
            ),
            eligible AS (
                SELECT entity, first_date
                FROM firsts
                WHERE first_date <= ?
            )
            SELECT COUNT(DISTINCT eligible.entity) AS cohort,
                   COUNT(DISTINCT events.{field}) AS retained
            FROM eligible
            LEFT JOIN events
              ON events.{field} = eligible.entity
             AND events.event = 'invocation_start'
             AND date(events.received_ms / 1000, 'unixepoch', '+8 hours') =
                 date(eligible.first_date, '+' || ? || ' days')
            """.format(field=field),
            (cutoff_date, offset),
        ).fetchone()
        cohort = int(row["cohort"] or 0) if row else 0
        retained = int(row["retained"] or 0) if row else 0
        stats.append(
            {
                "offset": offset,
                "cohort": cohort,
                "retained": retained,
                "rate": round(100.0 * retained / cohort, 1) if cohort else 0,
            }
        )
    return stats


def query_retention_stats_cached(field, offsets=(1, 3, 7, 14, 30)):
    default_rows = retention_placeholder(offsets)

    def builder():
        conn = db_connect()
        try:
            return query_retention_stats(conn, field, offsets)
        finally:
            conn.close()

    return get_async_cached_value(
        "retention:%s" % field,
        RETENTION_CACHE_TTL_SECONDS,
        builder,
        default_rows,
        heavy=True,
    )


def query_orphan_starts(conn, since_ms, current_ms):
    active_cutoff = current_ms - ACTIVE_TTL_SECONDS * 1000
    settled_cutoff = current_ms - ORPHAN_SETTLEMENT_GRACE_SECONDS * 1000
    return query_one(
        conn,
        """
        SELECT COUNT(*)
        FROM events starts
        WHERE starts.event = 'invocation_start'
          AND starts.ts_ms >= ?
          AND starts.ts_ms < ?
          AND NOT EXISTS (
              SELECT 1 FROM events ends
              WHERE ends.invocation_id = starts.invocation_id
                AND ends.event = 'invocation_end'
          )
          AND NOT EXISTS (
              SELECT 1 FROM active_invocations active
              WHERE active.invocation_id = starts.invocation_id
                AND active.last_seen_ms >= ?
          )
        """,
        (since_ms, settled_cutoff, active_cutoff),
    )


def query_settled_starts(conn, since_ms, current_ms):
    """Count starts old enough that a terminal event should have arrived.

    This is deliberately the denominator for the unclosed-invocation rate. A
    newly started call is neither a successful completion nor an abnormal end.
    """
    settled_cutoff = current_ms - ORPHAN_SETTLEMENT_GRACE_SECONDS * 1000
    return query_one(
        conn,
        """
        SELECT COUNT(*)
        FROM events
        WHERE event = 'invocation_start'
          AND ts_ms >= ?
          AND ts_ms < ?
        """,
        (since_ms, settled_cutoff),
    )


def query_orphan_breakdown(conn, since_ms, current_ms):
    active_cutoff = current_ms - ACTIVE_TTL_SECONDS * 1000
    settled_cutoff = current_ms - ORPHAN_SETTLEMENT_GRACE_SECONDS * 1000
    row = conn.execute(
        """
        WITH starts AS (
            SELECT invocation_id
            FROM events
            WHERE event = 'invocation_start'
              AND ts_ms >= ?
              AND ts_ms < ?
        )
        SELECT
            SUM(CASE
                WHEN NOT EXISTS (
                    SELECT 1 FROM events ended
                    WHERE ended.invocation_id = starts.invocation_id
                      AND ended.event = 'invocation_end'
                )
                 AND NOT EXISTS (
                    SELECT 1 FROM active_invocations active
                    WHERE active.invocation_id = starts.invocation_id
                      AND active.last_seen_ms >= ?
                )
                 AND EXISTS (
                    SELECT 1 FROM events heartbeats
                    WHERE heartbeats.invocation_id = starts.invocation_id
                      AND heartbeats.event = 'invocation_heartbeat'
                )
                THEN 1 ELSE 0 END) AS with_heartbeat,
            SUM(CASE
                WHEN NOT EXISTS (
                    SELECT 1 FROM events ended
                    WHERE ended.invocation_id = starts.invocation_id
                      AND ended.event = 'invocation_end'
                )
                 AND NOT EXISTS (
                    SELECT 1 FROM active_invocations active
                    WHERE active.invocation_id = starts.invocation_id
                      AND active.last_seen_ms >= ?
                )
                 AND NOT EXISTS (
                    SELECT 1 FROM events heartbeats
                    WHERE heartbeats.invocation_id = starts.invocation_id
                      AND heartbeats.event = 'invocation_heartbeat'
                )
                THEN 1 ELSE 0 END) AS without_heartbeat
        FROM starts
        """,
        (since_ms, settled_cutoff, active_cutoff, active_cutoff),
    ).fetchone()
    return {
        "with_heartbeat": int((row and row["with_heartbeat"]) or 0),
        "without_heartbeat": int((row and row["without_heartbeat"]) or 0),
    }


def query_orphan_sources(conn, since_ms, current_ms, limit=12):
    active_cutoff = current_ms - ACTIVE_TTL_SECONDS * 1000
    settled_cutoff = current_ms - ORPHAN_SETTLEMENT_GRACE_SECONDS * 1000
    rows = conn.execute(
        """
        WITH starts AS (
            SELECT invocation_id, command, agent_kind, version, platform
            FROM events
            WHERE event = 'invocation_start'
              AND ts_ms >= ?
              AND ts_ms < ?
        )
        SELECT starts.command AS command,
               starts.agent_kind AS agent_kind,
               starts.version AS version,
               starts.platform AS platform,
               COUNT(*) AS starts,
               SUM(CASE
                   WHEN NOT EXISTS (
                       SELECT 1 FROM events ended
                       WHERE ended.invocation_id = starts.invocation_id
                         AND ended.event = 'invocation_end'
                   )
                    AND NOT EXISTS (
                        SELECT 1 FROM active_invocations active
                        WHERE active.invocation_id = starts.invocation_id
                          AND active.last_seen_ms >= ?
                    )
                   THEN 1 ELSE 0 END) AS orphans,
               SUM(CASE
                   WHEN NOT EXISTS (
                       SELECT 1 FROM events ended
                       WHERE ended.invocation_id = starts.invocation_id
                         AND ended.event = 'invocation_end'
                   )
                    AND NOT EXISTS (
                        SELECT 1 FROM active_invocations active
                        WHERE active.invocation_id = starts.invocation_id
                          AND active.last_seen_ms >= ?
                    )
                    AND EXISTS (
                        SELECT 1 FROM events heartbeats
                        WHERE heartbeats.invocation_id = starts.invocation_id
                          AND heartbeats.event = 'invocation_heartbeat'
                    )
                   THEN 1 ELSE 0 END) AS with_heartbeat,
               SUM(CASE
                   WHEN NOT EXISTS (
                       SELECT 1 FROM events ended
                       WHERE ended.invocation_id = starts.invocation_id
                         AND ended.event = 'invocation_end'
                   )
                    AND NOT EXISTS (
                        SELECT 1 FROM active_invocations active
                        WHERE active.invocation_id = starts.invocation_id
                          AND active.last_seen_ms >= ?
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM events heartbeats
                        WHERE heartbeats.invocation_id = starts.invocation_id
                          AND heartbeats.event = 'invocation_heartbeat'
                    )
                   THEN 1 ELSE 0 END) AS without_heartbeat
        FROM starts
        GROUP BY starts.command, starts.agent_kind, starts.version, starts.platform
        HAVING orphans > 0
        ORDER BY orphans DESC, starts DESC
        LIMIT ?
        """,
        (since_ms, settled_cutoff, active_cutoff, active_cutoff, active_cutoff, limit),
    ).fetchall()
    items = []
    for row in rows:
        starts = int(row["starts"] or 0)
        orphans = int(row["orphans"] or 0)
        items.append(
            {
                "command": row["command"] or "unknown",
                "agent_kind": row["agent_kind"] or "unknown",
                "version": row["version"] or "unknown",
                "platform": row["platform"] or "unknown",
                "starts": starts,
                "orphans": orphans,
                "with_heartbeat": int(row["with_heartbeat"] or 0),
                "without_heartbeat": int(row["without_heartbeat"] or 0),
                "rate": fmt_rate(orphans, starts),
            }
        )
    return items


def slow_dashboard_metrics_placeholder():
    return {
        "pending": True,
        "all_time_unique_installs": "...",
        "all_time_unique_agents": "...",
        "new_installs_24h": "...",
        "new_installs_7d": "...",
        "returning_installs_24h": "...",
        "task_duration_7d": {"avg_ms": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0},
        "session_24h": {"count": 0, "avg_duration_ms": 0, "p95_duration_ms": 0, "avg_calls": 0},
        "session_7d": {"count": 0, "avg_duration_ms": 0, "p95_duration_ms": 0, "avg_calls": 0},
        "platform_unique_devices": [],
        "platform_unique_agents": [],
        "platform_unique_devices_all": [],
        "platform_unique_agents_all": [],
        "orphan_sources_24h": [],
        "feedback_commands": [],
        "feedback_queries": [],
        "feedback_reasons": [],
    }


def health_metrics_placeholder():
    """Return a schema-complete value without ever presenting it as live data."""
    return {
        "pending": True,
        "generated_ms": 0,
        "active_now": 0,
        "last_event_age_ms": 0,
        "calls_24h": 0,
        "calls_7d": 0,
        "calls_30d": 0,
        "active_installs_24h": 0,
        "active_installs_7d": 0,
        "unique_agents_24h": 0,
        "unique_agents_7d": 0,
        "errors_24h": 0,
        "aborted_24h": 0,
        "task_duration_24h": {"avg_ms": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0},
        "session_24h": {"count": 0, "avg_duration_ms": 0, "p95_duration_ms": 0, "avg_calls": 0},
        "orphan_starts_24h": 0,
        "settled_calls_24h": 0,
        "orphan_with_heartbeat_24h": 0,
        "orphan_without_heartbeat_24h": 0,
    }


def query_slow_dashboard_metrics(current_ms, day_ms, week_ms):
    conn = db_connect()
    try:
        return {
            "pending": False,
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
            "new_installs_24h": query_new_installs(conn, day_ms),
            "new_installs_7d": query_new_installs(conn, week_ms),
            "returning_installs_24h": query_returning_installs(conn, day_ms),
            "task_duration_7d": query_duration_stats(conn, week_ms, current_ms),
            "session_24h": query_session_stats(conn, day_ms, current_ms),
            "session_7d": query_session_stats(conn, week_ms, current_ms),
            "platform_unique_devices": query_platform_unique(conn, "install_id", week_ms, current_ms=current_ms),
            "platform_unique_agents": query_platform_unique(conn, "agent_id", week_ms, current_ms=current_ms),
            "platform_unique_devices_all": query_platform_unique(conn, "install_id"),
            "platform_unique_agents_all": query_platform_unique(conn, "agent_id"),
            "orphan_sources_24h": query_orphan_sources(conn, day_ms, current_ms),
            "feedback_commands": query_feedback_groups(conn, "command", week_ms, 12, real_only=True),
            "feedback_queries": query_feedback_groups(conn, "query_text", week_ms, 12, real_only=True),
            "feedback_reasons": query_feedback_groups(conn, "reason_text", week_ms, 12, real_only=True),
        }
    finally:
        conn.close()


def query_health_dashboard_metrics(current_ms, day_ms, week_ms, month_ms):
    """Build the health cards from one database snapshot.

    Session, error, and settled-unclosed numbers are interpreted together by
    humans.  Keeping them in one short-lived snapshot prevents a fresh orphan
    rate from being rendered next to an older session aggregate.
    """
    conn = db_connect()
    try:
        prune_active(conn, current_ms)
        conn.commit()
        calls_24h = query_one(
            conn,
            "SELECT COUNT(*) FROM events WHERE ts_ms >= ? AND ts_ms < ? AND event = 'invocation_start'",
            (day_ms, event_time_upper_bound(current_ms)),
        )
        calls_7d = query_one(
            conn,
            "SELECT COUNT(*) FROM events WHERE ts_ms >= ? AND ts_ms < ? AND event = 'invocation_start'",
            (week_ms, event_time_upper_bound(current_ms)),
        )
        calls_30d = query_one(
            conn,
            "SELECT COUNT(*) FROM events WHERE ts_ms >= ? AND ts_ms < ? AND event = 'invocation_start'",
            (month_ms, event_time_upper_bound(current_ms)),
        )
        orphan_breakdown = query_orphan_breakdown(conn, day_ms, current_ms)
        last_event_ms = query_one(conn, "SELECT MAX(received_ms) FROM events") or current_ms
        return {
            "pending": False,
            "generated_ms": current_ms,
            "active_now": query_one(conn, "SELECT COUNT(*) FROM active_invocations"),
            "last_event_age_ms": max(0, current_ms - last_event_ms),
            "calls_24h": calls_24h,
            "calls_7d": calls_7d,
            "calls_30d": calls_30d,
            "active_installs_24h": query_one(
                conn,
                "SELECT COUNT(DISTINCT install_id) FROM events WHERE ts_ms >= ? AND ts_ms < ?",
                (day_ms, event_time_upper_bound(current_ms)),
            ),
            "active_installs_7d": query_one(
                conn,
                "SELECT COUNT(DISTINCT install_id) FROM events WHERE ts_ms >= ? AND ts_ms < ?",
                (week_ms, event_time_upper_bound(current_ms)),
            ),
            "unique_agents_24h": query_one(
                conn,
                "SELECT COUNT(DISTINCT agent_id) FROM events WHERE ts_ms >= ? AND ts_ms < ?",
                (day_ms, event_time_upper_bound(current_ms)),
            ),
            "unique_agents_7d": query_one(
                conn,
                "SELECT COUNT(DISTINCT agent_id) FROM events WHERE ts_ms >= ? AND ts_ms < ?",
                (week_ms, event_time_upper_bound(current_ms)),
            ),
            "errors_24h": query_one(
                conn,
                "SELECT COUNT(*) FROM events WHERE ts_ms >= ? AND ts_ms < ? AND event = 'invocation_end' AND status = 'error'",
                (day_ms, event_time_upper_bound(current_ms)),
            ),
            "aborted_24h": query_one(
                conn,
                "SELECT COUNT(*) FROM events WHERE ts_ms >= ? AND ts_ms < ? AND event = 'invocation_end' AND status = 'aborted'",
                (day_ms, event_time_upper_bound(current_ms)),
            ),
            "task_duration_24h": query_duration_stats(conn, day_ms, current_ms),
            "session_24h": query_session_stats(conn, day_ms, current_ms),
            "orphan_starts_24h": query_orphan_starts(conn, day_ms, current_ms),
            "settled_calls_24h": query_settled_starts(conn, day_ms, current_ms),
            "orphan_with_heartbeat_24h": orphan_breakdown["with_heartbeat"],
            "orphan_without_heartbeat_24h": orphan_breakdown["without_heartbeat"],
        }
    finally:
        conn.close()


def query_slow_dashboard_metrics_cached(current_ms, day_ms, week_ms):
    return get_async_cached_value(
        "dashboard_slow_metrics",
        SLOW_METRICS_CACHE_TTL_SECONDS,
        lambda: query_slow_dashboard_metrics(current_ms, day_ms, week_ms),
        slow_dashboard_metrics_placeholder(),
        heavy=True,
    )


def query_health_dashboard_metrics_cached(current_ms, day_ms, week_ms, month_ms):
    return get_async_cached_value(
        "dashboard_health_metrics",
        HEALTH_METRICS_CACHE_TTL_SECONDS,
        lambda: query_health_dashboard_metrics(current_ms, day_ms, week_ms, month_ms),
        health_metrics_placeholder(),
        wait_for_initial=True,
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


def parse_rate_value(rate_text):
    text = str(rate_text or "").strip()
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except Exception:
        return 0.0


def metric_text(value, default="0"):
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return text


def tone_by_threshold(value, good_max, warn_max):
    number = float(value or 0)
    if number <= good_max:
        return "good"
    if number <= warn_max:
        return "warn"
    return "bad"


def summary():
    started = time.time()
    current = now_ms()
    day = current - 24 * 3600 * 1000
    week = current - 7 * 24 * 3600 * 1000
    month = current - 30 * 24 * 3600 * 1000
    slow_metrics = query_slow_dashboard_metrics_cached(current, day, week)
    health_metrics = query_health_dashboard_metrics_cached(current, day, week, month)
    conn = db_connect()
    try:
        calls_24h = health_metrics["calls_24h"]
        calls_7d = health_metrics["calls_7d"]
        calls_30d = health_metrics["calls_30d"]
        unique_agents_24h = health_metrics["unique_agents_24h"]
        active_installs_24h = health_metrics["active_installs_24h"]
        errors_24h = health_metrics["errors_24h"]
        aborted_24h = health_metrics["aborted_24h"]
        orphan_starts_24h = health_metrics["orphan_starts_24h"]
        settled_calls_24h = health_metrics["settled_calls_24h"]
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
            "health_generated_ms": health_metrics["generated_ms"],
            "health_metrics_pending": bool(health_metrics.get("pending")),
            "slow_metrics_pending": bool(slow_metrics.get("pending")),
            "last_event_age_ms": health_metrics["last_event_age_ms"],
            "active_now": health_metrics["active_now"],
            "all_time_unique_installs": slow_metrics["all_time_unique_installs"],
            "all_time_unique_agents": slow_metrics["all_time_unique_agents"],
            "calls_24h": calls_24h,
            "calls_7d": calls_7d,
            "calls_30d": calls_30d,
            "active_installs_24h": active_installs_24h,
            "active_installs_7d": health_metrics["active_installs_7d"],
            "unique_agents_24h": unique_agents_24h,
            "unique_agents_7d": health_metrics["unique_agents_7d"],
            "new_installs_24h": slow_metrics["new_installs_24h"],
            "new_installs_7d": slow_metrics["new_installs_7d"],
            "returning_installs_24h": slow_metrics["returning_installs_24h"],
            "error_24h": errors_24h,
            "aborted_24h": aborted_24h,
            "error_rate_24h": fmt_rate(errors_24h, calls_24h),
            "orphan_starts_24h": orphan_starts_24h,
            "settled_calls_24h": settled_calls_24h,
            "orphan_rate_24h": fmt_rate(orphan_starts_24h, settled_calls_24h),
            "orphan_with_heartbeat_24h": health_metrics["orphan_with_heartbeat_24h"],
            "orphan_without_heartbeat_24h": health_metrics["orphan_without_heartbeat_24h"],
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
            "site_unique_ips_all": query_one(
                conn,
                "SELECT COUNT(DISTINCT ip_hash) FROM site_visits WHERE ip_hash <> ''",
            ),
            "site_unique_ips_24h": query_one(
                conn,
                "SELECT COUNT(DISTINCT ip_hash) FROM site_visits WHERE received_ms >= ? AND ip_hash <> ''",
                (day,),
            ),
            "site_unique_ips_7d": query_one(
                conn,
                "SELECT COUNT(DISTINCT ip_hash) FROM site_visits WHERE received_ms >= ? AND ip_hash <> ''",
                (week,),
            ),
            "site_visits_24h": query_one(
                conn,
                "SELECT COUNT(*) FROM site_visits WHERE received_ms >= ?",
                (day,),
            ),
            "site_visits_7d": query_one(
                conn,
                "SELECT COUNT(*) FROM site_visits WHERE received_ms >= ?",
                (week,),
            ),
            "calls_per_agent_24h": round(float(calls_24h) / unique_agents_24h, 2)
            if unique_agents_24h
            else 0,
            "calls_per_device_24h": round(float(calls_24h) / active_installs_24h, 2)
            if active_installs_24h
            else 0,
            "task_duration_24h": health_metrics["task_duration_24h"],
            "task_duration_7d": slow_metrics["task_duration_7d"],
            "session_24h": health_metrics["session_24h"],
            "session_7d": slow_metrics["session_7d"],
            "surface": query_groups(conn, "surface", week),
            "commands": query_groups(conn, "command", week, 12),
            "agents": query_groups(conn, "agent_kind", week),
            "versions": query_groups(conn, "version", week),
            "platforms": query_groups(conn, "platform", week),
            "platform_unique_devices": slow_metrics["platform_unique_devices"],
            "platform_unique_agents": slow_metrics["platform_unique_agents"],
            "platform_unique_devices_all": slow_metrics["platform_unique_devices_all"],
            "platform_unique_agents_all": slow_metrics["platform_unique_agents_all"],
            "retention_devices": query_retention_stats_cached("install_id"),
            "retention_agents": query_retention_stats_cached("agent_id"),
            "orphan_sources_24h": slow_metrics["orphan_sources_24h"],
            "feedback_commands": slow_metrics["feedback_commands"],
            "feedback_queries": slow_metrics["feedback_queries"],
            "feedback_reasons": slow_metrics["feedback_reasons"],
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
        elapsed = time.time() - started
        if elapsed >= 2.0:
            log_info("summary built in %.2fs" % elapsed)


def format_time(ms):
    try:
        dt = _dt.datetime.utcfromtimestamp(int(ms) / 1000.0) + _dt.timedelta(hours=8)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def render_group(title, rows):
    compact = "Platform Unique Devices (All-time)" in title or "Platform Unique Agents (All-time)" in title
    items = []
    for row in rows:
        key = html.escape(str(row["key"] or "unknown"))
        count = int(row["count"])
        if compact:
            items.append(
                "<li><span>{}</span><strong>{}</strong></li>".format(
                    key, count
                )
            )
        else:
            items.append("<tr><td>{}</td><td>{}</td></tr>".format(key, count))
    if not items:
        if compact:
            items.append("<li><span>暂无数据 / No data yet</span><strong>0</strong></li>")
        else:
            items.append("<tr><td colspan='2'>暂无数据 / No data yet</td></tr>")
    if compact:
        return "<section class='panel core-sidecard'><h2>{}</h2><ul>{}</ul></section>".format(
            html.escape(title), "\n".join(items)
        )
    return "<section class='panel data-panel'><h2>{}</h2><table><tbody>{}</tbody></table></section>".format(
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
    return "<section class='panel data-panel'><h2>{}</h2><table><tbody>{}</tbody></table></section>".format(
        html.escape(title), "\n".join(items)
    )


def render_retention_panel(device_rows, agent_rows):
    def cards(rows, prefix):
        items = []
        for row in rows:
            offset = int(row.get("offset") or 0)
            label = "D{} {}".format(offset, prefix)
            pending = bool(row.get("pending"))
            rate_text = "..." if pending else "{}%".format(html.escape(str(row.get("rate") or 0)))
            retained_text = "... / ..." if pending else "{}/{} retained".format(
                html.escape(str(row.get("retained") or 0)),
                html.escape(str(row.get("cohort") or 0)),
            )
            items.append(
                """
<div class="retention-card">
  <strong>{rate_text}</strong>
  <span>{label}</span>
  <em>{retained_text}</em>
</div>
                """.strip().format(
                    rate_text=rate_text,
                    label=html.escape(label),
                    retained_text=retained_text,
                )
            )
        return "\n".join(items)

    pending = any(bool(row.get("pending")) for row in list(device_rows) + list(agent_rows))

    return """
<section class="panel retention-panel">
  <div class="retention-heading">
    <div>
      <h2>留存分析 / Retention</h2>
      <p>按首次激活日期分群；D1 / D3 / D7 / D14 / D30 表示首次激活后第 N 天是否再次调用 Guanlan。历史不足 N 天的 cohort 不进入分母。</p>
      {pending_note}
    </div>
  </div>
  <h3>独立设备留存 / Unique Device Retention</h3>
  <div class="retention-grid">{device_cards}</div>
  <h3>独立 Agent 留存 / Unique Agent Retention</h3>
  <div class="retention-grid">{agent_cards}</div>
</section>
    """.strip().format(
        pending_note="<p class='panel-note'>留存卡片正在后台刷新，主看板和反馈列表不会再被它拖住。</p>" if pending else "",
        device_cards=cards(device_rows, "设备 / Devices"),
        agent_cards=cards(agent_rows, "Agent"),
    )


def render_orphan_sources_panel(rows):
    items = []
    for row in rows:
        items.append(
            "<tr><td>{command}</td><td>{agent_kind}</td><td>{version}</td><td>{platform}</td><td>{starts}</td><td>{orphans}</td><td>{with_heartbeat}</td><td>{without_heartbeat}</td><td>{rate}</td></tr>".format(
                command=html.escape(str(row.get("command") or "")),
                agent_kind=html.escape(str(row.get("agent_kind") or "")),
                version=html.escape(str(row.get("version") or "")),
                platform=html.escape(str(row.get("platform") or "")),
                starts=html.escape(str(row.get("starts") or 0)),
                orphans=html.escape(str(row.get("orphans") or 0)),
                with_heartbeat=html.escape(str(row.get("with_heartbeat") or 0)),
                without_heartbeat=html.escape(str(row.get("without_heartbeat") or 0)),
                rate=html.escape(str(row.get("rate") or "0%")),
            )
        )
    if not items:
        items.append("<tr><td colspan='9'>暂无异常来源 / No orphan sources</td></tr>")
    return """
<section class="panel data-panel">
  <h2>异常来源 Top / Top Orphan Sources (24h)</h2>
  <p class="panel-note">见过心跳通常代表任务运行过一段时间后失去结束事件；无心跳更常见于宿主超时、进程被终止或结束事件未发出。</p>
  <table>
    <thead>
      <tr><th>命令 / Command</th><th>Agent</th><th>版本 / Version</th><th>平台 / Platform</th><th>启动 / Starts</th><th>异常 / Orphans</th><th>见过心跳</th><th>无心跳</th><th>异常率 / Rate</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</section>
    """.strip().format(rows="\n".join(items))


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
    return "<section id='feedback-inbox' class='panel recent feedback-inbox'><h2>反馈明细面板 / Feedback Inbox <a class='section-link' href='./feedback-archive'>全量归档 / Archive</a></h2>{}</section>".format(
        "\n".join(items)
    )


def clamp_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except Exception:
        number = default
    return max(minimum, min(maximum, number))


def first_param(params, key, default=""):
    values = params.get(key) or []
    if not values:
        return default
    return str(values[0]).strip()


def query_distinct(conn, column, limit=80):
    allowed = set(["command", "profile", "backend", "agent_kind", "version", "platform"])
    if column not in allowed:
        return []
    rows = conn.execute(
        """
        SELECT DISTINCT {column} AS value
        FROM feedback
        WHERE {column} <> ''
        ORDER BY value ASC
        LIMIT ?
        """.format(column=column),
        (limit,),
    ).fetchall()
    return [r["value"] for r in rows]


def build_archive_where(filters):
    current = now_ms()
    where = []
    args = []
    window = filters["window"]
    if window == "24h":
        where.append("received_ms >= ?")
        args.append(current - 24 * 3600 * 1000)
    elif window == "7d":
        where.append("received_ms >= ?")
        args.append(current - 7 * 24 * 3600 * 1000)
    elif window == "30d":
        where.append("received_ms >= ?")
        args.append(current - 30 * 24 * 3600 * 1000)

    kind = filters["kind"]
    real_sql = feedback_real_sql("query_text")
    if kind == "real":
        where.append(real_sql)
    elif kind == "synthetic":
        where.append("NOT " + real_sql)

    for column in ("command", "profile", "backend", "agent_kind", "version", "platform"):
        value = filters.get(column) or ""
        if value:
            where.append(column + " = ?")
            args.append(value)

    keyword = filters["q"]
    if keyword:
        like = "%" + keyword + "%"
        where.append("(query_text LIKE ? OR reason_text LIKE ?)")
        args.extend([like, like])

    return (" AND ".join(where) if where else "1=1"), args


def query_feedback_archive(params):
    raw_window = first_param(params, "window", "all")
    window = raw_window if raw_window in ("24h", "7d", "30d", "all") else "all"
    raw_kind = first_param(params, "kind", "all")
    kind = raw_kind if raw_kind in ("all", "real", "synthetic") else "all"
    raw_view = first_param(params, "view", "clusters")
    view = raw_view if raw_view in ("clusters", "raw") else "clusters"
    filters = {
        "window": window,
        "kind": kind,
        "view": view,
        "q": clamp_text(first_param(params, "q", ""), 160),
        "command": clamp_text(first_param(params, "command", ""), 40),
        "profile": clamp_text(first_param(params, "profile", ""), 24),
        "backend": clamp_text(first_param(params, "backend", ""), 40),
        "agent_kind": clamp_text(first_param(params, "agent_kind", ""), 40),
        "version": clamp_text(first_param(params, "version", ""), 40),
        "platform": clamp_text(first_param(params, "platform", ""), 40),
    }
    page = clamp_int(first_param(params, "page", "1"), 1, 1, 1000000)
    per_page = clamp_int(first_param(params, "per_page", "100"), 100, 20, 200)

    conn = db_connect()
    try:
        where, args = build_archive_where(filters)
        total = int(query_one(conn, "SELECT COUNT(*) FROM feedback WHERE " + where, tuple(args)) or 0)
        pages = max(1, int((total + per_page - 1) // per_page))
        page = min(page, pages)
        offset = (page - 1) * per_page
        rows = conn.execute(
            """
            SELECT id, received_ms, query_text, reason_text, command, profile, backend,
                   agent_kind, agent_id, install_id, version, platform, python, remote_addr
            FROM feedback
            WHERE {where}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """.format(where=where),
            tuple(args + [per_page, offset]),
        ).fetchall()
        return {
            "filters": filters,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "total": total,
            "rows": [dict(r) for r in rows],
            "options": {
                "command": query_distinct(conn, "command"),
                "profile": query_distinct(conn, "profile"),
                "backend": query_distinct(conn, "backend"),
                "agent_kind": query_distinct(conn, "agent_kind"),
                "version": query_distinct(conn, "version"),
                "platform": query_distinct(conn, "platform"),
            },
        }
    finally:
        conn.close()


def query_feedback_clusters(params):
    data = query_feedback_archive(params)
    filters = data["filters"]
    conn = db_connect()
    try:
        where, args = build_archive_where(filters)
        rows = conn.execute(
            """
            SELECT received_ms, query_text, reason_text, command, profile, backend,
                   agent_kind, agent_id, install_id, version, platform
            FROM feedback
            WHERE {where}
            ORDER BY id DESC
            """.format(where=where),
            tuple(args),
        ).fetchall()
        clusters = {}
        for row in rows:
            command = row["command"] or "unknown-command"
            profile = row["profile"] or "unknown-profile"
            backend = row["backend"] or "unknown-backend"
            reason_text = row["reason_text"] or ""
            cluster_key = "||".join(
                [
                    command,
                    profile,
                    backend,
                    normalize_cluster_text(reason_text),
                ]
            )
            item = clusters.get(cluster_key)
            if item is None:
                item = {
                    "command": command,
                    "profile": profile,
                    "backend": backend,
                    "reason_text": reason_text,
                    "sample_query": row["query_text"] or "",
                    "count": 0,
                    "latest_ms": int(row["received_ms"] or 0),
                    "unique_agents": set(),
                    "unique_installs": set(),
                    "versions": set(),
                    "platforms": set(),
                }
                clusters[cluster_key] = item
            item["count"] += 1
            item["latest_ms"] = max(item["latest_ms"], int(row["received_ms"] or 0))
            if row["agent_id"]:
                item["unique_agents"].add(row["agent_id"])
            if row["install_id"]:
                item["unique_installs"].add(row["install_id"])
            if row["version"]:
                item["versions"].add(row["version"])
            if row["platform"]:
                item["platforms"].add(row["platform"])
        ordered = sorted(
            clusters.values(),
            key=lambda x: (-int(x["count"]), -int(x["latest_ms"])),
        )
        page = data["page"]
        per_page = data["per_page"]
        total = len(ordered)
        pages = max(1, int((total + per_page - 1) // per_page))
        page = min(page, pages)
        offset = (page - 1) * per_page
        page_rows = ordered[offset : offset + per_page]
        items = []
        for item in page_rows:
            items.append(
                {
                    "command": item["command"],
                    "profile": item["profile"],
                    "backend": item["backend"],
                    "reason_text": item["reason_text"],
                    "sample_query": item["sample_query"],
                    "count": item["count"],
                    "latest_ms": item["latest_ms"],
                    "unique_agents": len(item["unique_agents"]),
                    "unique_installs": len(item["unique_installs"]),
                    "versions": sorted(item["versions"]),
                    "platforms": sorted(item["platforms"]),
                }
            )
        data["page"] = page
        data["pages"] = pages
        data["total"] = total
        data["clusters"] = items
        return data
    finally:
        conn.close()


def archive_url(filters, page, per_page):
    query = {"page": page, "per_page": per_page}
    for key, value in filters.items():
        if value:
            query[key] = value
    return "./feedback-archive?" + urlencode(query)


def archive_view_url(filters, view):
    next_filters = dict(filters)
    next_filters["view"] = view
    return archive_url(next_filters, 1, 100)


def render_select(name, label, current, options, include_all=True):
    items = []
    if include_all:
        selected = " selected" if not current else ""
        items.append("<option value=''{}>全部 / All</option>".format(selected))
    for option in options:
        value = html.escape(str(option))
        selected = " selected" if str(option) == str(current) else ""
        items.append("<option value=\"{}\"{}>{}</option>".format(value, selected, value))
    return """
<label>
  <span>{label}</span>
  <select name="{name}">{options}</select>
</label>
    """.strip().format(
        label=html.escape(label),
        name=html.escape(name),
        options="\n".join(items),
    )


def render_feedback_archive(params):
    base = query_feedback_archive(params)
    if base["filters"].get("view") == "clusters":
        data = query_feedback_clusters(params)
    else:
        data = base
    filters = data["filters"]
    rows = []
    if filters.get("view") == "clusters":
        for index, row in enumerate(data.get("clusters") or [], 1):
            version_text = html.escape(", ".join(row.get("versions") or []) or "unknown")
            platform_text = html.escape(", ".join(row.get("platforms") or []) or "unknown")
            rows.append(
                """
<details class="archive-item cluster-item">
  <summary>
    <span class="archive-row cluster-row">
      <span class="archive-id">#{index}</span>
      <span class="archive-time">{time}</span>
      <span class="archive-query">{query}</span>
      <span class="archive-reason">{reason_preview}</span>
      <span class="archive-meta">{meta}</span>
      <span class="archive-version">{count} 次</span>
      <span class="kind-real">{agents} Agent</span>
      <span class="archive-action">展开 / Open</span>
    </span>
  </summary>
  <div class="archive-body">
    <p><strong>代表搜索词 / Representative Query</strong></p>
    <p class="full-text">{query_full}</p>
    <p><strong>聚类原因 / Clustered Reason</strong></p>
    <p class="full-text">{reason}</p>
    <div class="detail-grid">
      <p><strong>命令 / Command</strong><br>{command}</p>
      <p><strong>Profile</strong><br>{profile}</p>
      <p><strong>Backend</strong><br>{backend}</p>
      <p><strong>最近出现 / Latest Seen</strong><br>{time}</p>
      <p><strong>出现次数 / Total Count</strong><br>{count}</p>
      <p><strong>影响 Agent / Unique Agents</strong><br>{agents}</p>
      <p><strong>影响设备 / Unique Devices</strong><br>{installs}</p>
      <p><strong>版本分布 / Versions</strong><br>{versions}</p>
      <p><strong>平台分布 / Platforms</strong><br>{platforms}</p>
    </div>
  </div>
</details>
                """.strip().format(
                    index=index,
                    time=html.escape(format_time(row.get("latest_ms"))),
                    query=html.escape(clamp_text(row.get("sample_query") or "", 72)) or "(empty query)",
                    query_full=html.escape(row.get("sample_query") or "(empty query)"),
                    reason_preview=html.escape(clamp_text(row.get("reason_text") or "", 88)) or "(empty reason)",
                    reason=html.escape(row.get("reason_text") or "(empty reason)"),
                    meta=html.escape(
                        " · ".join(
                            [
                                row.get("command") or "unknown-command",
                                row.get("profile") or "unknown-profile",
                                row.get("backend") or "unknown-backend",
                            ]
                        )
                    ),
                    command=html.escape(row.get("command") or ""),
                    profile=html.escape(row.get("profile") or ""),
                    backend=html.escape(row.get("backend") or ""),
                    count=html.escape(str(row.get("count") or 0)),
                    agents=html.escape(str(row.get("unique_agents") or 0)),
                    installs=html.escape(str(row.get("unique_installs") or 0)),
                    versions=version_text,
                    platforms=platform_text,
                )
            )
    else:
        for row in data["rows"]:
            synthetic = is_synthetic_feedback_query(row.get("query_text"))
            kind_class = "kind-synthetic" if synthetic else "kind-real"
            kind_text = "测试流量 / Synthetic" if synthetic else "真实反馈 / Real"
            query_text = html.escape(row.get("query_text") or "")
            reason_text = html.escape(row.get("reason_text") or "")
            meta = " · ".join(
                [
                    row.get("command") or "unknown-command",
                    row.get("profile") or "unknown-profile",
                    row.get("backend") or "unknown-backend",
                    row.get("agent_kind") or "unknown-agent",
                    row.get("platform") or "unknown-platform",
                ]
            )
            rows.append(
                """
<details class="archive-item">
  <summary>
    <span class="archive-row">
      <span class="archive-id">#{id}</span>
      <span class="archive-time">{time}</span>
      <span class="archive-query">{query}</span>
      <span class="archive-reason">{reason_preview}</span>
      <span class="archive-meta">{meta}</span>
      <span class="archive-version">v{version}</span>
      <span class="{kind_class}">{kind_text}</span>
      <span class="archive-action">展开 / Open</span>
    </span>
  </summary>
  <div class="archive-body">
    <p><strong>搜索词 / Query</strong></p>
    <p class="full-text">{query_full}</p>
    <p><strong>原因 / Reason</strong></p>
    <p class="full-text">{reason}</p>
    <div class="detail-grid">
      <p><strong>命令 / Command</strong><br>{command}</p>
      <p><strong>Profile</strong><br>{profile}</p>
      <p><strong>Backend</strong><br>{backend}</p>
      <p><strong>Agent</strong><br>{agent_kind}</p>
      <p><strong>版本 / Version</strong><br>{version}</p>
      <p><strong>平台 / Platform</strong><br>{platform}</p>
      <p><strong>Python</strong><br>{python}</p>
      <p><strong>Install ID</strong><br>{install_id}</p>
      <p><strong>Agent ID</strong><br>{agent_id}</p>
      <p><strong>Remote</strong><br>{remote_addr}</p>
    </div>
  </div>
</details>
                """.strip().format(
                    id=int(row.get("id") or 0),
                    time=html.escape(format_time(row.get("received_ms"))),
                    query=query_text or "(empty query)",
                    query_full=query_text or "(empty query)",
                    reason_preview=html.escape(clamp_text(row.get("reason_text") or "", 72)) or "(empty reason)",
                    reason=reason_text or "(empty reason)",
                    meta=html.escape(meta),
                    command=html.escape(row.get("command") or ""),
                    profile=html.escape(row.get("profile") or ""),
                    backend=html.escape(row.get("backend") or ""),
                    agent_kind=html.escape(row.get("agent_kind") or ""),
                    version=html.escape(row.get("version") or "unknown"),
                    platform=html.escape(row.get("platform") or ""),
                    python=html.escape(row.get("python") or ""),
                    install_id=html.escape(row.get("install_id") or ""),
                    agent_id=html.escape(row.get("agent_id") or ""),
                    remote_addr=html.escape(row.get("remote_addr") or ""),
                    kind_class=kind_class,
                    kind_text=kind_text,
                )
            )
    if not rows:
        rows.append(
            "<p class='empty'>没有匹配的{} / No matching {}.</p>".format(
                "问题簇" if filters.get("view") == "clusters" else "反馈明细",
                "clusters" if filters.get("view") == "clusters" else "feedback rows",
            )
        )

    page = data["page"]
    pages = data["pages"]
    per_page = data["per_page"]
    prev_link = (
        "<a href='{}'>上一页 / Previous</a>".format(
            html.escape(archive_url(filters, page - 1, per_page))
        )
        if page > 1
        else "<span>上一页 / Previous</span>"
    )
    next_link = (
        "<a href='{}'>下一页 / Next</a>".format(
            html.escape(archive_url(filters, page + 1, per_page))
        )
        if page < pages
        else "<span>下一页 / Next</span>"
    )

    filter_options = data["options"]
    cluster_view_active = " is-active" if filters.get("view") == "clusters" else ""
    raw_view_active = " is-active" if filters.get("view") == "raw" else ""
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Guanlan Feedback Archive</title>
  <link rel="icon" href="/assets/guanlan-logo.svg" type="image/svg+xml">
  <style>
    :root {{ --bg:#f5f5f7; --card:#fff; --border:#e7e7ec; --text:#1d1d1f; --muted:#6e6e73; --blue:#2563eb; }}
    body {{ margin:0; font:14px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
    header {{ position:sticky; top:0; z-index:10; padding:14px 24px; background:rgba(255,255,255,.86); border-bottom:1px solid var(--border); backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px); }}
    .topbar {{ max-width:1280px; margin:0 auto; display:flex; align-items:center; justify-content:space-between; gap:16px; }}
    .brand {{ display:flex; align-items:center; gap:12px; }}
    .brand img {{ width:38px; height:38px; border-radius:8px; }}
    .brand strong {{ display:block; font-size:20px; }}
    .brand span {{ display:block; color:var(--muted); font-size:12px; }}
    .nav a {{ color:var(--blue); text-decoration:none; font-weight:600; }}
    main {{ max-width:1280px; margin:0 auto; padding:18px 24px 36px; }}
    .panel {{ background:var(--card); border:1px solid var(--border); border-radius:8px; box-shadow:0 6px 18px rgba(15,23,42,.06); }}
    .view-tabs {{ display:flex; gap:10px; margin:0 0 14px; }}
    .view-tab {{ display:inline-flex; align-items:center; justify-content:center; padding:10px 14px; border:1px solid var(--border); border-radius:999px; background:#fff; color:var(--muted); text-decoration:none; font-weight:700; }}
    .view-tab.is-active {{ background:#1d1d1f; color:#fff; border-color:#1d1d1f; }}
    .filters {{ padding:14px; display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; align-items:end; }}
    label span {{ display:block; color:var(--muted); font-size:12px; margin-bottom:4px; }}
    input, select {{ width:100%; box-sizing:border-box; border:1px solid #d8d8de; border-radius:8px; padding:9px 10px; background:#fff; color:var(--text); font:inherit; }}
    button {{ border:0; border-radius:8px; padding:10px 14px; background:#1d1d1f; color:#fff; font-weight:700; cursor:pointer; }}
    .summary {{ margin:14px 0; display:flex; align-items:center; justify-content:space-between; gap:12px; color:var(--muted); }}
    .summary strong {{ color:var(--text); font-size:20px; }}
    .pager {{ display:flex; gap:10px; align-items:center; }}
    .pager a, .pager span {{ padding:8px 11px; border:1px solid var(--border); border-radius:8px; background:#fff; color:var(--blue); text-decoration:none; }}
    .pager span {{ color:var(--muted); }}
    .archive-list {{ padding:10px; }}
    .archive-item {{ border:1px solid #ececf2; border-radius:8px; margin-bottom:10px; background:#fff; overflow:hidden; }}
    .archive-item summary {{ cursor:pointer; list-style:none; padding:10px 12px; }}
    .archive-item summary::-webkit-details-marker {{ display:none; }}
    .archive-row {{ display:grid; grid-template-columns:72px 170px minmax(240px,1.25fr) minmax(260px,1.3fr) minmax(220px,1fr) 80px 150px 100px; gap:10px; align-items:start; }}
    .archive-id {{ font-weight:700; color:#4b5563; }}
    .archive-time, .archive-meta {{ color:var(--muted); font-size:12px; }}
    .archive-query {{ font-weight:600; white-space:normal; word-break:break-word; }}
    .archive-reason {{ color:#3f3f46; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .archive-meta {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .archive-version {{ color:#0f172a; font-size:12px; font-weight:800; white-space:nowrap; }}
    .kind-real {{ color:#0f766e; font-weight:700; white-space:nowrap; }}
    .kind-synthetic {{ color:#b45309; font-weight:700; white-space:nowrap; }}
    .archive-action {{ color:var(--blue); justify-self:end; white-space:nowrap; }}
    .archive-body {{ border-top:1px solid #ececf2; padding:12px; }}
    .archive-body p {{ margin:0 0 10px; }}
    .full-text {{ white-space:pre-wrap; word-break:break-word; }}
    .cluster-row {{ grid-template-columns:72px 170px minmax(220px,1fr) minmax(280px,1.35fr) minmax(200px,1fr) 90px 110px 100px; }}
    .detail-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; color:var(--muted); }}
    .detail-grid strong {{ color:var(--text); }}
    .empty {{ color:var(--muted); margin:8px 4px; }}
    @media (max-width: 900px) {{
      header {{ position:static; }}
      .topbar, .summary {{ align-items:flex-start; flex-direction:column; }}
      .archive-row {{ grid-template-columns:1fr; gap:4px; }}
      .archive-action {{ justify-self:start; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div class="brand">
        <img src="/assets/guanlan-logo.svg" alt="">
        <div>
          <strong>反馈归档 / Feedback Archive</strong>
          <span>全量反馈分页查看，不影响主面板刷新</span>
        </div>
      </div>
      <div class="nav"><a href="./">返回遥测面板 / Back to Dashboard</a></div>
    </div>
  </header>
  <main>
    <div class="view-tabs">
      <a class="view-tab{cluster_view_active}" href="{clusters_href}">问题簇 / Clusters</a>
      <a class="view-tab{raw_view_active}" href="{raw_href}">原始明细 / Raw</a>
    </div>
    <form class="panel filters" method="get" action="">
      <label><span>关键词 / Keyword</span><input name="q" value="{q}" placeholder="搜索 query 或 reason"></label>
      {window_select}
      {kind_select}
      {version_select}
      {platform_select}
      {agent_select}
      {command_select}
      {profile_select}
      {backend_select}
      <label><span>每页 / Per Page</span><select name="per_page">
        <option value="50"{pp50}>50</option>
        <option value="100"{pp100}>100</option>
        <option value="200"{pp200}>200</option>
      </select></label>
      <button type="submit">筛选 / Filter</button>
    </form>
    <div class="summary">
      <div><strong>{total}</strong> {summary_label} · 第 {page}/{pages} 页 · 每页 {per_page}</div>
      <div class="pager">{prev_link}{next_link}</div>
    </div>
    <section class="panel archive-list">{rows}</section>
  </main>
</body>
</html>""".format(
        cluster_view_active=cluster_view_active,
        raw_view_active=raw_view_active,
        clusters_href=html.escape(archive_view_url(filters, "clusters")),
        raw_href=html.escape(archive_view_url(filters, "raw")),
        q=html.escape(filters["q"]),
        window_select=render_select(
            "window",
            "时间 / Window",
            filters["window"],
            [("24h"), ("7d"), ("30d"), ("all")],
            include_all=False,
        ),
        kind_select=render_select(
            "kind",
            "类型 / Kind",
            filters["kind"],
            [("all"), ("real"), ("synthetic")],
            include_all=False,
        ),
        version_select=render_select("version", "版本 / Version", filters["version"], filter_options["version"]),
        platform_select=render_select("platform", "平台 / Platform", filters["platform"], filter_options["platform"]),
        agent_select=render_select("agent_kind", "Agent 类型 / Agent", filters["agent_kind"], filter_options["agent_kind"]),
        command_select=render_select("command", "命令 / Command", filters["command"], filter_options["command"]),
        profile_select=render_select("profile", "Profile", filters["profile"], filter_options["profile"]),
        backend_select=render_select("backend", "Backend", filters["backend"], filter_options["backend"]),
        pp50=" selected" if per_page == 50 else "",
        pp100=" selected" if per_page == 100 else "",
        pp200=" selected" if per_page == 200 else "",
        total=data["total"],
        summary_label="个问题簇 / clusters" if filters.get("view") == "clusters" else "条反馈 / feedback",
        page=page,
        pages=pages,
        per_page=per_page,
        prev_link=prev_link,
        next_link=next_link,
        rows="\n".join(rows),
    )


def query_site_visit_options(conn, column, limit=80):
    allowed = set(["browser", "os", "device_type", "network_effective_type"])
    if column not in allowed:
        return []
    rows = conn.execute(
        """
        SELECT DISTINCT {column} AS value
        FROM site_visits
        WHERE {column} <> ''
        ORDER BY value ASC
        LIMIT ?
        """.format(column=column),
        (limit,),
    ).fetchall()
    return [r["value"] for r in rows]


def build_site_visit_where(filters):
    current = now_ms()
    where = []
    args = []
    window = filters["window"]
    if window == "24h":
        where.append("received_ms >= ?")
        args.append(current - 24 * 3600 * 1000)
    elif window == "7d":
        where.append("received_ms >= ?")
        args.append(current - 7 * 24 * 3600 * 1000)
    elif window == "30d":
        where.append("received_ms >= ?")
        args.append(current - 30 * 24 * 3600 * 1000)

    for column in ("browser", "os", "device_type", "network_effective_type"):
        value = filters.get(column) or ""
        if value:
            where.append(column + " = ?")
            args.append(value)

    keyword = filters["q"]
    if keyword:
        like = "%" + keyword + "%"
        where.append(
            """
            (
                remote_addr LIKE ? OR path LIKE ? OR referrer LIKE ? OR user_agent LIKE ?
                OR language LIKE ? OR timezone LIKE ? OR host LIKE ?
            )
            """
        )
        args.extend([like, like, like, like, like, like, like])

    return (" AND ".join(where) if where else "1=1"), args


def query_site_visit_archive(params):
    raw_window = first_param(params, "window", "24h")
    window = raw_window if raw_window in ("24h", "7d", "30d", "all") else "24h"
    filters = {
        "window": window,
        "q": clamp_text(first_param(params, "q", ""), 160),
        "browser": clamp_text(first_param(params, "browser", ""), 40),
        "os": clamp_text(first_param(params, "os", ""), 40),
        "device_type": clamp_text(first_param(params, "device_type", ""), 40),
        "network_effective_type": clamp_text(first_param(params, "network_effective_type", ""), 24),
    }
    page = clamp_int(first_param(params, "page", "1"), 1, 1, 1000000)
    per_page = clamp_int(first_param(params, "per_page", "100"), 100, 20, 200)
    conn = db_connect()
    try:
        where, args = build_site_visit_where(filters)
        total = int(query_one(conn, "SELECT COUNT(*) FROM site_visits WHERE " + where, tuple(args)) or 0)
        pages = max(1, int((total + per_page - 1) // per_page))
        page = min(page, pages)
        offset = (page - 1) * per_page
        rows = conn.execute(
            """
            SELECT id, received_ms, remote_addr, host, path, referrer, user_agent,
                   browser, os, device_type, language, languages, timezone, screen,
                   viewport, device_pixel_ratio, network_effective_type, network_downlink,
                   network_rtt, network_save_data
            FROM site_visits
            WHERE {where}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """.format(where=where),
            tuple(args + [per_page, offset]),
        ).fetchall()
        enriched = []
        geo_fetches = 0
        for row in rows:
            item = dict(row)
            allow_fetch = geo_fetches < 8
            item["geo"] = get_ip_geo(conn, item.get("remote_addr"), allow_fetch=allow_fetch)
            if allow_fetch and item["geo"]:
                geo_fetches += 1
            enriched.append(item)
        return {
            "filters": filters,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "total": total,
            "rows": enriched,
            "options": {
                "browser": query_site_visit_options(conn, "browser"),
                "os": query_site_visit_options(conn, "os"),
                "device_type": query_site_visit_options(conn, "device_type"),
                "network_effective_type": query_site_visit_options(conn, "network_effective_type"),
            },
        }
    finally:
        conn.close()


def site_visit_url(filters, page, per_page):
    query = {"page": page, "per_page": per_page}
    for key, value in filters.items():
        if value:
            query[key] = value
    return "./site-visits?" + urlencode(query)


def format_geo(geo):
    if not geo:
        return "未知 / Unknown"
    parts = [geo.get("country"), geo.get("region"), geo.get("city")]
    location = " / ".join([p for p in parts if p])
    isp = geo.get("isp") or geo.get("org") or ""
    if location and isp:
        return "%s · %s" % (location, isp)
    return location or isp or "未知 / Unknown"


def render_site_visits(params):
    data = query_site_visit_archive(params)
    filters = data["filters"]
    rows = []
    for row in data["rows"]:
        geo = row.get("geo") or {}
        location = format_geo(geo)
        network_bits = []
        if row.get("network_effective_type"):
            network_bits.append(row["network_effective_type"])
        if row.get("network_downlink"):
            network_bits.append(str(row["network_downlink"]) + "Mbps")
        if row.get("network_rtt"):
            network_bits.append(str(row["network_rtt"]) + "ms")
        if row.get("network_save_data"):
            network_bits.append("saveData=" + str(row["network_save_data"]))
        network = " · ".join(network_bits) if network_bits else "浏览器未提供 / Not provided"
        device = " · ".join(
            [
                item
                for item in (row.get("device_type"), row.get("os"), row.get("browser"))
                if item
            ]
        ) or "unknown"
        rows.append(
            """
<details class="visit-item">
  <summary>
    <span class="visit-row">
      <span class="visit-id">#{id}</span>
      <span class="visit-time">{time}</span>
      <span class="visit-ip">{ip}</span>
      <span class="visit-location">{location}</span>
      <span class="visit-device">{device}</span>
      <span class="visit-path">{path}</span>
      <span class="visit-action">展开 / Open</span>
    </span>
  </summary>
  <div class="visit-body">
    <div class="detail-grid">
      <p><strong>IP</strong><br>{ip}</p>
      <p><strong>IP 归属 / Location</strong><br>{location}</p>
      <p><strong>ISP / Org / ASN</strong><br>{isp}<br>{org}<br>{asn}</p>
      <p><strong>设备 / Device</strong><br>{device}</p>
      <p><strong>网络 / Network</strong><br>{network}</p>
      <p><strong>语言 / Language</strong><br>{language}<br>{languages}</p>
      <p><strong>时区 / Timezone</strong><br>{timezone}</p>
      <p><strong>屏幕 / Screen</strong><br>{screen} · viewport {viewport} · DPR {dpr}</p>
      <p><strong>Host</strong><br>{host}</p>
      <p><strong>Path</strong><br>{path}</p>
      <p><strong>Referrer</strong><br>{referrer}</p>
      <p><strong>User-Agent</strong><br>{ua}</p>
    </div>
  </div>
</details>
            """.strip().format(
                id=int(row.get("id") or 0),
                time=html.escape(format_time(row.get("received_ms"))),
                ip=html.escape(row.get("remote_addr") or "(historical hash only)"),
                location=html.escape(location),
                device=html.escape(device),
                path=html.escape(row.get("path") or ""),
                isp=html.escape(geo.get("isp") or ""),
                org=html.escape(geo.get("org") or ""),
                asn=html.escape(geo.get("asn") or ""),
                network=html.escape(network),
                language=html.escape(row.get("language") or ""),
                languages=html.escape(row.get("languages") or ""),
                timezone=html.escape(row.get("timezone") or ""),
                screen=html.escape(row.get("screen") or ""),
                viewport=html.escape(row.get("viewport") or ""),
                dpr=html.escape(row.get("device_pixel_ratio") or ""),
                host=html.escape(row.get("host") or ""),
                referrer=html.escape(row.get("referrer") or ""),
                ua=html.escape(row.get("user_agent") or ""),
            )
        )
    if not rows:
        rows.append("<p class='empty'>没有匹配的访问记录 / No matching visits.</p>")
    else:
        rows.insert(
            0,
            """
<div class="visit-row visit-head">
  <span>ID</span>
  <span>时间 / Time</span>
  <span>IP</span>
  <span>IP 归属 / Location</span>
  <span>设备 / Device</span>
  <span>路径 / Path</span>
  <span>详情 / Detail</span>
</div>
            """.strip(),
        )

    page = data["page"]
    pages = data["pages"]
    per_page = data["per_page"]
    prev_link = (
        "<a href='{}'>上一页 / Previous</a>".format(
            html.escape(site_visit_url(filters, page - 1, per_page))
        )
        if page > 1
        else "<span>上一页 / Previous</span>"
    )
    next_link = (
        "<a href='{}'>下一页 / Next</a>".format(
            html.escape(site_visit_url(filters, page + 1, per_page))
        )
        if page < pages
        else "<span>下一页 / Next</span>"
    )
    options = data["options"]
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Guanlan Website Visits</title>
  <link rel="icon" href="/assets/guanlan-logo.svg" type="image/svg+xml">
  <style>
    :root {{ --bg:#f5f5f7; --card:#fff; --border:#e7e7ec; --text:#1d1d1f; --muted:#6e6e73; --blue:#2563eb; }}
    body {{ margin:0; font:14px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
    header {{ position:sticky; top:0; z-index:10; padding:14px 24px; background:rgba(255,255,255,.86); border-bottom:1px solid var(--border); backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px); }}
    .topbar {{ max-width:1280px; margin:0 auto; display:flex; align-items:center; justify-content:space-between; gap:16px; }}
    .brand {{ display:flex; align-items:center; gap:12px; }}
    .brand img {{ width:38px; height:38px; border-radius:8px; }}
    .brand strong {{ display:block; font-size:20px; }}
    .brand span {{ display:block; color:var(--muted); font-size:12px; }}
    .nav a {{ color:var(--blue); text-decoration:none; font-weight:600; }}
    main {{ max-width:1280px; margin:0 auto; padding:18px 24px 36px; }}
    .panel {{ background:var(--card); border:1px solid var(--border); border-radius:8px; box-shadow:0 6px 18px rgba(15,23,42,.06); }}
    .filters {{ padding:14px; display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; align-items:end; }}
    label span {{ display:block; color:var(--muted); font-size:12px; margin-bottom:4px; }}
    input, select {{ width:100%; box-sizing:border-box; border:1px solid #d8d8de; border-radius:8px; padding:9px 10px; background:#fff; color:var(--text); font:inherit; }}
    button {{ border:0; border-radius:8px; padding:10px 14px; background:#1d1d1f; color:#fff; font-weight:700; cursor:pointer; }}
    .explain {{ margin:14px 0; padding:12px 14px; color:#3f3f46; }}
    .explain strong {{ color:var(--text); }}
    .explain p {{ margin:0 0 6px; }}
    .explain p:last-child {{ margin-bottom:0; }}
    .summary {{ margin:14px 0; display:flex; align-items:center; justify-content:space-between; gap:12px; color:var(--muted); }}
    .summary strong {{ color:var(--text); font-size:20px; }}
    .pager {{ display:flex; gap:10px; align-items:center; }}
    .pager a, .pager span {{ padding:8px 11px; border:1px solid var(--border); border-radius:8px; background:#fff; color:var(--blue); text-decoration:none; }}
    .pager span {{ color:var(--muted); }}
    .visit-list {{ padding:10px; }}
    .visit-head {{ padding:8px 12px; color:var(--muted); font-size:12px; font-weight:700; border-bottom:1px solid #ececf2; margin-bottom:8px; }}
    .visit-item {{ border:1px solid #ececf2; border-radius:8px; margin-bottom:10px; background:#fff; overflow:hidden; }}
    .visit-item summary {{ cursor:pointer; list-style:none; padding:10px 12px; }}
    .visit-item summary::-webkit-details-marker {{ display:none; }}
    .visit-row {{ display:grid; grid-template-columns:70px 170px 130px minmax(220px,1.2fr) minmax(170px,.9fr) minmax(220px,1fr) 100px; gap:10px; align-items:start; }}
    .visit-id {{ font-weight:700; color:#4b5563; }}
    .visit-time {{ color:var(--muted); font-size:12px; }}
    .visit-ip {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
    .visit-location, .visit-device, .visit-path {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .visit-action {{ color:var(--blue); justify-self:end; white-space:nowrap; }}
    .visit-body {{ border-top:1px solid #ececf2; padding:12px; }}
    .detail-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; color:var(--muted); }}
    .detail-grid strong {{ color:var(--text); }}
    .detail-grid p {{ margin:0; word-break:break-word; }}
    .empty {{ color:var(--muted); margin:8px 4px; }}
    @media (max-width: 900px) {{
      header {{ position:static; }}
      .topbar, .summary {{ align-items:flex-start; flex-direction:column; }}
      .visit-head {{ display:none; }}
      .visit-row {{ grid-template-columns:1fr; gap:4px; }}
      .visit-action {{ justify-self:start; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div class="brand">
        <img src="/assets/guanlan-logo.svg" alt="">
        <div>
          <strong>官网访问明细 / Website Visits</strong>
          <span>IP、归属地、设备、网络与访问上下文</span>
        </div>
      </div>
      <div class="nav"><a href="./">返回遥测面板 / Back to Dashboard</a></div>
    </div>
  </header>
  <main>
    <form class="panel filters" method="get" action="">
      <label><span>关键词 / Keyword</span><input name="q" value="{q}" placeholder="IP / path / UA / referrer"></label>
      {window_select}
      {device_select}
      {os_select}
      {browser_select}
      {network_select}
      <label><span>每页 / Per Page</span><select name="per_page">
        <option value="50"{pp50}>50</option>
        <option value="100"{pp100}>100</option>
        <option value="200"{pp200}>200</option>
      </select></label>
      <button type="submit">筛选 / Filter</button>
    </form>
    <section class="panel explain">
      <p><strong>下面是官网页面访问记录 / Website page visits.</strong></p>
      <p>新官网脚本会记录 IP、访问路径、来源页、User-Agent、语言、时区、屏幕和浏览器可提供的网络信息；历史日志回填只包含 Nginx 当时留下的 IP、路径、来源页和 User-Agent。</p>
      <p>如果显示未知，通常是浏览器没有提供该字段、User-Agent 无法识别、或历史记录早于新版官网 beacon。</p>
    </section>
    <div class="summary">
      <div><strong>{total}</strong> 条访问 / visits · 第 {page}/{pages} 页 · 每页 {per_page}</div>
      <div class="pager">{prev_link}{next_link}</div>
    </div>
    <section class="panel visit-list">{rows}</section>
  </main>
</body>
</html>""".format(
        q=html.escape(filters["q"]),
        window_select=render_select("window", "时间 / Window", filters["window"], ["24h", "7d", "30d", "all"], include_all=False),
        device_select=render_select("device_type", "设备 / Device", filters["device_type"], options["device_type"]),
        os_select=render_select("os", "系统 / OS", filters["os"], options["os"]),
        browser_select=render_select("browser", "浏览器 / Browser", filters["browser"], options["browser"]),
        network_select=render_select("network_effective_type", "网络 / Network", filters["network_effective_type"], options["network_effective_type"]),
        pp50=" selected" if per_page == 50 else "",
        pp100=" selected" if per_page == 100 else "",
        pp200=" selected" if per_page == 200 else "",
        total=data["total"],
        page=page,
        pages=pages,
        per_page=per_page,
        prev_link=prev_link,
        next_link=next_link,
        rows="\n".join(rows),
    )


def render_dashboard():
    data = summary()
    task_24h = data["task_duration_24h"]
    session_24h = data["session_24h"]
    generated_at = format_time(data["generated_ms"])
    health_generated_at = format_time(data["health_generated_ms"] or data["generated_ms"])
    slow_metrics_note = (
        "<p class='panel-note'>部分历史/诊断指标正在后台刷新，反馈明细和实时调用已经是最新数据。</p>"
        if data.get("slow_metrics_pending")
        else ""
    )
    health_snapshot_note = (
        "<p class='panel-note'>健康指标正在生成完整快照；暂不把占位值当作当前异常率。</p>"
        if data.get("health_metrics_pending")
        else "<p class='panel-note'>本组指标同一快照生成于：%s。24h 使用客户端事件发生时间；延迟补传仅计入投递健康，不混入当前使用健康。</p>"
        % html.escape(health_generated_at)
    )

    core_cards = [
        {"label": "全部独立设备 / All-time Unique Devices", "value": data["all_time_unique_installs"]},
        {"label": "全部独立 Agent / All-time Unique Agents", "value": data["all_time_unique_agents"]},
        {"label": "24h 独立 Agent / 24h Unique Agents", "value": data["unique_agents_24h"]},
        {"label": "24h 独立设备 / 24h Unique Devices", "value": data["active_installs_24h"]},
        {"label": "24h 新增设备 / 24h New Devices", "value": data["new_installs_24h"]},
        {"label": "24h 有效反馈 / 24h Real Feedback", "value": data["feedback_24h"], "href": "./feedback-archive?window=24h&kind=real"},
        {
            "label": "官网全部独立 IP / All-time Website Unique IPs",
            "value": data["site_unique_ips_all"],
            "href": "./site-visits?window=all",
            "hint": "打开访问明细",
        },
        {
            "label": "24h 官网独立 IP / 24h Website Unique IPs",
            "value": data["site_unique_ips_24h"],
            "href": "./site-visits?window=24h",
            "hint": "打开访问明细",
        },
    ]
    error_rate_value = parse_rate_value(data["error_rate_24h"])
    orphan_rate_value = parse_rate_value(data["orphan_rate_24h"])
    operational_cards = [
        {"label": "当前并发 / Active Concurrency", "value": metric_text(data["active_now"]), "tone": "neutral"},
        {"label": "最近事件 / Last Event", "value": fmt_ms(data["last_event_age_ms"]) + " 前", "tone": "neutral"},
        {"label": "24h 调用 / 24h Calls", "value": data["calls_24h"], "tone": "neutral"},
        {"label": "30d 调用 / 30d Calls", "value": data["calls_30d"], "tone": "neutral"},
        {"label": "7d 官网独立 IP / 7d Website Unique IPs", "value": data["site_unique_ips_7d"], "tone": "neutral"},
        {"label": "24h 官网访问 / 24h Website Visits", "value": data["site_visits_24h"], "tone": "neutral"},
        {"label": "7d 官网访问 / 7d Website Visits", "value": data["site_visits_7d"], "tone": "neutral"},
        {"label": "7d 反馈 / 7d Feedback", "value": data["feedback_7d"], "tone": "good"},
    ]
    growth_cards = [
        {"label": "24h 反馈总量 / 24h Feedback Total", "value": data["feedback_24h_total"], "tone": "good"},
        {"label": "24h 测试反馈 / 24h Synthetic Feedback", "value": metric_text(data["feedback_24h_synthetic"]), "tone": "neutral"},
        {"label": "7d 测试反馈 / 7d Synthetic Feedback", "value": data["feedback_7d_synthetic"], "tone": "neutral"},
        {"label": "7d 反馈 Agent / 7d Feedback Agents", "value": data["feedback_unique_agents_7d"], "tone": "good"},
        {"label": "7d 反馈 Agent 总量 / 7d Feedback Agents Total", "value": data["feedback_unique_agents_7d_total"], "tone": "good"},
        {"label": "7d 独立 Agent / 7d Unique Agents", "value": data["unique_agents_7d"], "tone": "neutral"},
        {"label": "7d 独立设备 / 7d Unique Devices", "value": data["active_installs_7d"], "tone": "neutral"},
        {"label": "24h 回访设备 / 24h Returning Devices", "value": data["returning_installs_24h"], "tone": "good"},
    ]
    performance_cards = [
        {"label": "Agent 日均调用 / Daily Calls per Agent", "value": data["calls_per_agent_24h"], "tone": "neutral"},
        {"label": "设备日均调用 / Daily Calls per Device", "value": data["calls_per_device_24h"], "tone": "neutral"},
        {"label": "任务平均时长 / Avg Task Duration", "value": fmt_ms(task_24h["avg_ms"]), "tone": "neutral"},
        {"label": "任务 P95 时长 / P95 Task Duration", "value": fmt_ms(task_24h["p95_ms"]), "tone": "neutral"},
        {"label": "Session 平均时长 / Avg Session Duration", "value": fmt_ms(session_24h["avg_duration_ms"]), "tone": "neutral"},
        {"label": "Session P95 时长 / P95 Session Duration", "value": fmt_ms(session_24h["p95_duration_ms"]), "tone": "neutral"},
        {
            "label": "24h 错误率 / 24h Error Rate",
            "value": data["error_rate_24h"],
            "tone": tone_by_threshold(error_rate_value, 1.0, 3.0),
        },
        {
            "label": "24h 未闭环率 / 24h Settled Unclosed Rate",
            "value": data["orphan_rate_24h"],
            "tone": tone_by_threshold(orphan_rate_value, 5.0, 12.0),
        },
    ]
    core_card_html = "\n".join(
        (
            "<a class='core-card core-card-link' href='{href}'><span>{label}</span><strong>{value}</strong><em>{hint}</em></a>".format(
                href=html.escape(str(card.get("href") or "")),
                label=html.escape(str(card.get("label") or "")),
                value=html.escape(metric_text(card.get("value"), default="—")),
                hint=html.escape(str(card.get("hint") or "打开逐条反馈")),
            )
            if card.get("href")
            else "<div class='core-card'><span>{label}</span><strong>{value}</strong></div>".format(
                label=html.escape(str(card.get("label") or "")),
                value=html.escape(metric_text(card.get("value"), default="—")),
            )
        )
        for card in core_cards
    )
    def render_stat_cards(cards):
        return "\n".join(
            "<div class='card card-{tone}'><span>{label}</span><strong>{value}</strong></div>".format(
                tone=html.escape(str(card.get("tone") or "neutral")),
                label=html.escape(str(card.get("label") or "")),
                value=html.escape(str(card.get("value") or "")),
            )
            for card in cards
        )

    operational_card_html = render_stat_cards(operational_cards)
    growth_card_html = render_stat_cards(growth_cards)
    performance_card_html = render_stat_cards(performance_cards)
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
            ("24h 中止 / 24h Aborted", data["aborted_24h"]),
            ("24h 错误率 / 24h Error Rate", data["error_rate_24h"]),
            ("24h 已结算调用 / 24h Settled Calls", data["settled_calls_24h"]),
            ("24h 未闭环调用 / 24h Unclosed Starts", data["orphan_starts_24h"]),
            ("24h 未闭环率 / 24h Settled Unclosed Rate", data["orphan_rate_24h"]),
            ("24h 未闭环中见过心跳 / Unclosed With Heartbeat", data["orphan_with_heartbeat_24h"]),
            ("24h 未闭环中无心跳 / Unclosed Without Heartbeat", data["orphan_without_heartbeat_24h"]),
            ("24h 新增设备 / 24h New Devices", data["new_installs_24h"]),
            ("7d 新增设备 / 7d New Devices", data["new_installs_7d"]),
            ("24h 回访设备 / 24h Returning Devices", data["returning_installs_24h"]),
        ],
    )
    retention_panel = render_retention_panel(data["retention_devices"], data["retention_agents"])
    orphan_sources_panel = render_orphan_sources_panel(data["orphan_sources_24h"])

    countdown_seconds = 30
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Guanlan Telemetry</title>
  <link rel="icon" href="/assets/guanlan-logo.svg" type="image/svg+xml">
  <style>
    :root {{
      --bg: #f3f4f6;
      --card: #ffffff;
      --card-border: #e5e7eb;
      --text: #1d1d1f;
      --muted: #6e6e73;
      --panel-bg: linear-gradient(180deg, rgba(255,255,255,0.94), rgba(255,255,255,0.88));
      --shadow: 0 14px 40px rgba(15, 23, 42, 0.06);
      --blue: #2563eb;
      --green: #10b981;
      --amber: #f59e0b;
      --red: #ef4444;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font:14px/1.6 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif; background:radial-gradient(circle at top, rgba(37,99,235,0.06), transparent 28%), var(--bg); color:var(--text); }}
    header {{ background:rgba(255,255,255,0.82); border-bottom:1px solid #e8e8ee; backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px); padding:18px 28px; position:sticky; top:0; z-index:10; }}
    .brand {{ display:flex; align-items:center; gap:12px; }}
    .brand img {{ width:42px; height:42px; border-radius:10px; box-shadow:0 8px 18px rgba(185,28,28,0.08); }}
    .brand-title {{ display:flex; flex-direction:column; }}
    .brand-title strong {{ font-size:22px; letter-spacing:0; }}
    .brand-title span {{ color:var(--muted); font-size:12px; }}
    main {{ padding:28px 28px 48px; max-width:1480px; margin:0 auto; }}
    .dashboard-block {{ margin-top:22px; }}
    .dashboard-block:first-child {{ margin-top:0; }}
    .block-heading {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; margin-bottom:16px; }}
    .block-heading h1, .block-heading h2 {{ margin:0; }}
    .block-heading h1 {{ font-size:30px; line-height:1.05; }}
    .block-heading h2 {{ font-size:22px; line-height:1.1; }}
    .block-heading p {{ margin:8px 0 0; color:var(--muted); max-width:760px; }}
    .eyebrow {{ margin:0 0 6px; color:#475569; font-size:12px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; }}
    .block-meta {{ display:flex; flex-wrap:wrap; justify-content:flex-end; gap:10px; min-width:280px; }}
    .meta-pill {{ padding:10px 14px; border:1px solid var(--card-border); border-radius:999px; background:rgba(255,255,255,0.7); color:#475569; font-size:12px; white-space:nowrap; }}
    .hero-cards {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; }}
    .hero-grid {{ display:grid; grid-template-columns:minmax(0,2.1fr) minmax(260px,1fr) minmax(260px,1fr); gap:16px; align-items:stretch; }}
    .stats-cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; }}
    .triple-stack {{ display:grid; gap:14px; }}
    .panel {{ background:var(--panel-bg); border:1px solid var(--card-border); border-radius:18px; box-shadow:var(--shadow); }}
    .core-card, .card {{ background:var(--panel-bg); border:1px solid var(--card-border); border-radius:18px; box-shadow:var(--shadow); }}
    .overview-shell {{ padding:18px; }}
    .core-card {{ padding:18px 18px 20px; min-height:122px; }}
    .core-card span {{ display:block; color:var(--muted); font-size:12px; line-height:1.45; }}
    .core-card strong {{ display:block; margin-top:10px; font-size:40px; line-height:1; color:var(--green); }}
    .core-card-link {{ display:flex; flex-direction:column; align-items:flex-start; text-decoration:none; color:inherit; }}
    .core-card-link:hover {{ border-color:#c8c9d4; box-shadow:0 18px 44px rgba(15,23,42,0.1); transform:translateY(-1px); }}
    .core-card-link em {{ margin-top:auto; padding-top:10px; color:var(--blue); font-style:normal; font-size:12px; line-height:1.35; white-space:normal; word-break:break-word; }}
    .core-sidecard {{ padding:18px 20px; display:flex; flex-direction:column; }}
    .core-sidecard h2 {{ margin:0 0 18px; font-size:16px; line-height:1.35; }}
    .core-sidecard ul {{ list-style:none; margin:0; padding:0; display:grid; gap:0; }}
    .core-sidecard li {{ display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 0; border-bottom:1px solid #eef0f3; }}
    .core-sidecard li:last-child {{ border-bottom:0; }}
    .core-sidecard li span {{ color:#475569; font-size:18px; line-height:1.35; }}
    .core-sidecard li strong {{ color:#1d1d1f; font-size:20px; line-height:1; font-weight:700; }}
    .card {{ padding:16px 18px; min-height:106px; }}
    .card span {{ display:block; color:var(--muted); font-size:12px; line-height:1.45; }}
    .card strong {{ display:block; margin-top:10px; font-size:30px; line-height:1.05; color:#1d1d1f; }}
    .card strong:empty::before {{ content:"0"; color:#1d1d1f; }}
    .card.card-good strong {{ color:var(--green); }}
    .card.card-warn strong {{ color:var(--amber); }}
    .card.card-bad strong {{ color:var(--red); }}
    .split-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); gap:14px; }}
    section {{ padding:18px 20px; overflow:auto; }}
    h2 {{ margin:0 0 12px; font-size:16px; }}
    .section-link {{ float:right; color:var(--blue); text-decoration:none; font-size:12px; font-weight:600; }}
    .retention-panel {{ margin-top:22px; }}
    .retention-heading {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:8px; }}
    .retention-heading p {{ margin:0 0 8px; color:var(--muted); max-width:880px; }}
    .retention-panel h3 {{ margin:16px 0 10px; font-size:13px; color:#3f3f46; }}
    .retention-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }}
    .retention-card {{ border:1px solid #ececf2; border-radius:16px; padding:18px 14px; background:#fff; text-align:center; }}
    .retention-card strong {{ display:block; color:var(--green); font-size:34px; line-height:1; }}
    .retention-card span {{ display:block; margin-top:10px; color:#4b5563; font-weight:700; }}
    .retention-card em {{ display:block; margin-top:6px; color:var(--muted); font-size:12px; font-style:normal; }}
    .data-panel table td:first-child {{ color:#475569; width:58%; }}
    table {{ width:100%; border-collapse:collapse; }}
    td, th {{ padding:10px 6px; border-bottom:1px solid #eef0f3; text-align:left; white-space:nowrap; }}
    th {{ color:var(--muted); font-size:12px; }}
    .recent {{ margin-top:22px; }}
    .feedback-item {{ border:1px solid #ececf2; border-radius:16px; margin-bottom:12px; background:#fff; overflow:hidden; }}
    .feedback-item summary {{ cursor:pointer; list-style:none; padding:14px 16px; }}
    .feedback-item summary::-webkit-details-marker {{ display:none; }}
    .feedback-row {{ display:grid; grid-template-columns:70px 170px minmax(260px,1.2fr) minmax(260px,1.25fr) 1.1fr 90px 180px 130px; gap:12px; align-items:start; }}
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
    .feedback-body {{ border-top:1px solid #ececf2; padding:14px 16px 16px; }}
    .feedback-body p {{ margin:0 0 8px; }}
    .feedback-query-full {{ white-space:pre-wrap; word-break:break-word; }}
    .feedback-reason {{ white-space:pre-wrap; word-break:break-word; }}
    .feedback-meta {{ color:#6e6e73; font-size:12px; }}
    .feedback-empty {{ color:#6e6e73; margin:4px 0; }}
    .recent-table table td:first-child, .recent-table table th:first-child {{ white-space:nowrap; }}
    .panel-note {{ margin-top:6px; color:var(--muted); font-size:12px; }}
    @media (max-width: 1100px) {{
      .hero-grid, .split-grid {{ grid-template-columns:1fr; }}
      .hero-cards {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
      .block-meta {{ justify-content:flex-start; min-width:0; }}
    }}
    @media (max-width: 780px) {{
      header {{ padding:16px 18px; }}
      main {{ padding:20px 16px 36px; }}
      .block-heading {{ flex-direction:column; }}
      .hero-cards, .stats-cards, .grid, .retention-grid {{ grid-template-columns:1fr; }}
      .feedback-row {{ grid-template-columns:1fr; gap:4px; }}
      .feedback-expand-hint {{ justify-self:start; }}
      .core-card strong {{ font-size:34px; }}
      .card strong {{ font-size:28px; }}
      .core-sidecard li span {{ font-size:16px; }}
      .core-sidecard li strong {{ font-size:18px; }}
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
    <section class="dashboard-block overview-block">
      <div class="block-heading">
        <div>
          <p class="eyebrow">Overview</p>
          <h1>核心看板 / Core Metrics</h1>
          <p>把增长、官网访问、反馈信号和使用健康度拆开看，第一眼先判断规模，第二眼再看问题在哪。</p>
        </div>
        <div class="block-meta">
          <span class="meta-pill">自动刷新倒计时 / Refresh in <strong id="refresh-countdown">{countdown_seconds}</strong>s</span>
          <span class="meta-pill">生成时间 / Generated: {generated_at}</span>
        </div>
      </div>
      <div class="overview-shell panel">
        {slow_metrics_note}
        <div class="hero-grid">
          <div class="hero-cards">{core_cards}</div>
          {core_platform_devices}
          {core_platform_agents}
        </div>
      </div>
    </section>
    <section class="dashboard-block">
      <div class="block-heading">
        <div>
          <p class="eyebrow">Operations</p>
          <h2>运行与增长 / Operations & Growth</h2>
          <p>把调用、官网访问、反馈数量、留存相关指标拆成两组，避免一大片卡片挤在一起。</p>
        </div>
      </div>
      <div class="split-grid">
        <div class="triple-stack">
          <section class="panel">
            <h2>运行态 / Runtime</h2>
            <div class="stats-cards">{operational_cards}</div>
          </section>
        </div>
        <div class="triple-stack">
          <section class="panel">
            <h2>增长与反馈 / Growth & Feedback</h2>
            <div class="stats-cards">{growth_cards}</div>
          </section>
        </div>
      </div>
    </section>
    <section class="dashboard-block">
      <div class="block-heading">
        <div>
          <p class="eyebrow">Performance</p>
          <h2>健康度与深度 / Health & Depth</h2>
          <p>把效率、时长、错误和未闭环调用单独放一屏，颜色更聚焦，读起来不会和增长指标混在一起。</p>
          {health_snapshot_note}
        </div>
      </div>
      <section class="panel">
        <div class="stats-cards">{performance_cards}</div>
      </section>
    </section>
    {retention}
    {feedback_inbox}
    <section class="dashboard-block">
      <div class="block-heading">
        <div>
          <p class="eyebrow">Breakdown</p>
          <h2>结构拆解 / Distribution & Diagnostics</h2>
          <p>这里是解释层：大家都在用什么命令、什么平台、什么版本，异常主要集中在哪些来源。</p>
        </div>
      </div>
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
        {orphan_sources}
      </div>
    </section>
    <section class="panel recent recent-table">
      <h2>最近事件 / Recent Events</h2>
      <p class="panel-note">按时间倒序显示最近调用生命周期，适合快速确认新版本是否真的在进来。</p>
      <table>
        <thead><tr><th>时间 / Time (CST)</th><th>事件 / Event</th><th>入口 / Surface</th><th>命令 / Command</th><th>Agent</th><th>版本 / Version</th><th>状态 / Status</th><th>耗时 / Duration (ms)</th></tr></thead>
        <tbody>{recent}</tbody>
      </table>
    </section>
  </main>
  <script>
    (function () {{
      var countdown = {countdown_seconds};
      var el = document.getElementById("refresh-countdown");
      var reloading = false;
      if (!el) return;
      function tick() {{
        if (reloading) return;
        el.textContent = Math.max(0, countdown);
        if (countdown <= 0) {{
          reloading = true;
          window.location.reload();
          return;
        }}
        countdown -= 1;
      }}
      tick();
      window.setInterval(tick, 1000);
    }})();
  </script>
</body>
</html>""".format(
        core_cards=core_card_html,
        countdown_seconds=countdown_seconds,
        generated_at=generated_at,
        slow_metrics_note=slow_metrics_note,
        health_snapshot_note=health_snapshot_note,
        operational_cards=operational_card_html,
        growth_cards=growth_card_html,
        performance_cards=performance_card_html,
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
        orphan_sources=orphan_sources_panel,
        retention=retention_panel,
        recent="\n".join(recent_rows),
        feedback_inbox=render_feedback_inbox(data["recent_feedback"]),
    )


def render_dashboard_loading():
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Guanlan Telemetry</title>
  <link rel="icon" href="/assets/guanlan-logo.svg" type="image/svg+xml">
  <style>
    body { margin:0; font:14px/1.6 -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif; background:#f3f4f6; color:#1d1d1f; }
    main { min-height:100vh; display:grid; place-items:center; padding:24px; }
    .panel { width:min(560px, 100%); padding:28px 30px; border:1px solid #e5e7eb; border-radius:20px; background:rgba(255,255,255,0.92); box-shadow:0 14px 40px rgba(15, 23, 42, 0.06); }
    h1 { margin:0 0 8px; font-size:24px; }
    p { margin:0; color:#6e6e73; }
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>遥测面板正在刷新 / Telemetry is refreshing</h1>
      <p>缓存正在后台重建，几秒后自动再试。</p>
    </section>
  </main>
  <script>
    window.setTimeout(function () {
      window.location.reload();
    }, 4000);
  </script>
</body>
</html>"""


def _build_dashboard_html():
    html_text = render_dashboard()
    with _DASHBOARD_CACHE_LOCK:
        _DASHBOARD_CACHE["html"] = html_text
        _DASHBOARD_CACHE["built_ms"] = now_ms()
        _DASHBOARD_CACHE["refreshing"] = False
        _DASHBOARD_CACHE["refresh_started_ms"] = 0
    return html_text


def _dashboard_refresh_worker():
    started = time.time()
    try:
        _build_dashboard_html()
        elapsed = time.time() - started
        if elapsed >= 1.0:
            log_info("dashboard cache refreshed in %.2fs" % elapsed)
    except Exception:
        with _DASHBOARD_CACHE_LOCK:
            _DASHBOARD_CACHE["refreshing"] = False
            _DASHBOARD_CACHE["refresh_started_ms"] = 0


def ensure_dashboard_refresh():
    current = now_ms()
    with _DASHBOARD_CACHE_LOCK:
        refresh_started_ms = int(_DASHBOARD_CACHE.get("refresh_started_ms") or 0)
        if _DASHBOARD_CACHE.get("refreshing"):
            if refresh_started_ms and current - refresh_started_ms > DASHBOARD_REFRESH_STUCK_SECONDS * 1000:
                log_info("dashboard cache refresh remains single-flight after timeout")
            return False
        _DASHBOARD_CACHE["refreshing"] = True
        _DASHBOARD_CACHE["refresh_started_ms"] = current
    thread = threading.Thread(
        target=_dashboard_refresh_worker,
        name="guanlan-dashboard-refresh",
        daemon=True,
    )
    thread.start()
    return True


def render_dashboard_cached(force_refresh=False):
    current = now_ms()
    with _DASHBOARD_CACHE_LOCK:
        html_text = _DASHBOARD_CACHE.get("html") or ""
        built_ms = int(_DASHBOARD_CACHE.get("built_ms") or 0)
        refreshing = bool(_DASHBOARD_CACHE.get("refreshing"))
    if force_refresh:
        if not refreshing:
            return _build_dashboard_html()
        return html_text or render_dashboard_loading()
    if html_text and current - built_ms < DASHBOARD_CACHE_TTL_SECONDS * 1000:
        return html_text
    if html_text:
        if not refreshing:
            ensure_dashboard_refresh()
        return html_text
    if not refreshing:
        ensure_dashboard_refresh()
    return render_dashboard_loading()


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
        try:
            self.wfile.write(body)
        except OSError:
            # Client may disconnect when upstream/proxy timeout is reached.
            return

    def authorized(self):
        if not ADMIN_PASSWORD:
            return False
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
            return False
        token = self.headers.get("X-Guanlan-Token", "")
        if not token:
            token = (parse_qs(parsed.query).get("token") or [""])[0]
        return hmac.compare_digest(token, INGEST_TOKEN)

    def client_ip(self):
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return clamp_text(forwarded.split(",", 1)[0], 80)
        real_ip = self.headers.get("X-Real-IP", "")
        if real_ip:
            return clamp_text(real_ip, 80)
        return clamp_text(self.client_address[0], 80)

    def site_visit_authorized(self):
        if not SITE_VISIT_ALLOWED_HOSTS:
            return True
        candidates = []
        host = (self.headers.get("Host") or "").split(":", 1)[0].lower()
        if host:
            candidates.append(host)
        for header_name in ("Origin", "Referer"):
            value = self.headers.get(header_name, "")
            if value:
                parsed = urlparse(value)
                if parsed.hostname:
                    candidates.append(parsed.hostname.lower())
        return any(item in SITE_VISIT_ALLOWED_HOSTS for item in candidates)

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
            self.send_text(200, render_dashboard_cached(), "text/html; charset=utf-8")
            return
        if parsed.path in ("/feedback-archive", "/feedback-archive/"):
            if not self.require_auth():
                return
            self.send_text(200, render_feedback_archive(parse_qs(parsed.query)), "text/html; charset=utf-8")
            return
        if parsed.path in ("/site-visits", "/site-visits/"):
            if not self.require_auth():
                return
            self.send_text(200, render_site_visits(parse_qs(parsed.query)), "text/html; charset=utf-8")
            return
        self.send_text(404, "not found\n")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in ("/v1/events", "/v1/feedback", "/v1/site-visits"):
            self.send_text(404, "not found\n")
            return
        if parsed.path == "/v1/site-visits":
            if not self.site_visit_authorized():
                self.send_text(401, "unauthorized\n")
                return
        elif not self.ingest_authorized(parsed):
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
            ok = record_event(payload, self.client_ip())
        elif parsed.path == "/v1/feedback":
            ok = record_feedback(payload, self.client_ip())
        else:
            ok = record_site_visit(payload, self.client_ip(), self.headers)
        if not ok:
            self.send_text(400, "ignored\n")
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    validate_bind_security()
    init_db()
    ensure_dashboard_refresh()
    httpd = ThreadedHTTPServer((BIND_HOST, BIND_PORT), Handler)
    print("Guanlan telemetry collector listening on %s:%s" % (BIND_HOST, BIND_PORT))
    httpd.serve_forever()


def validate_bind_security():
    if is_local_bind_host(BIND_HOST):
        return
    missing = []
    if not ADMIN_PASSWORD:
        missing.append("GUANLAN_ADMIN_PASSWORD")
    if not INGEST_TOKEN:
        missing.append("GUANLAN_INGEST_TOKEN")
    if missing:
        sys.stderr.write(
            "telemetry collector refused non-local bind without secrets: %s\n"
            % ", ".join(missing)
        )
        sys.exit(2)


def is_local_bind_host(host):
    return str(host or "").strip().lower() in {"127.0.0.1", "localhost", "::1"}


if __name__ == "__main__":
    main()
