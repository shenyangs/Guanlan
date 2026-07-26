# -*- coding: utf-8 -*-
"""Tests for the standalone telemetry collector hardening."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "telemetry_collector.py"


def _load_collector(monkeypatch, *, host: str = "127.0.0.1"):
    monkeypatch.setenv("GUANLAN_HOST", host)
    spec = importlib.util.spec_from_file_location("telemetry_collector_test_module", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _insert_event(
    conn,
    *,
    received_ms: int,
    event: str,
    invocation_id: str,
    command: str = "search",
    install_id: str = "install-a",
    agent_id: str = "agent-a",
    session_id: str = "session-a",
    duration_ms: int | None = None,
    status: str = "",
):
    conn.execute(
        """
        INSERT INTO events (
            ts_ms, received_ms, event, install_id, session_id, invocation_id,
            surface, command, version, agent_kind, agent_id, platform, python,
            status, duration_ms, remote_addr
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            received_ms,
            received_ms,
            event,
            install_id,
            session_id,
            invocation_id,
            "cli",
            command,
            "0.7.2",
            "codex",
            agent_id,
            "darwin",
            "3.12",
            status,
            duration_ms,
            "127.0.0.1",
        ),
    )


def test_telemetry_collector_defaults_to_localhost(monkeypatch):
    collector = _load_collector(monkeypatch)

    assert collector.BIND_HOST == "127.0.0.1"
    assert collector.is_local_bind_host(collector.BIND_HOST) is True


def test_telemetry_collector_empty_secrets_do_not_authorize(monkeypatch):
    collector = _load_collector(monkeypatch)
    handler = object.__new__(collector.Handler)
    handler.headers = {}

    assert handler.authorized() is False
    assert handler.ingest_authorized(collector.urlparse("/v1/events")) is False


def test_telemetry_collector_nonlocal_bind_requires_secrets(monkeypatch):
    collector = _load_collector(monkeypatch, host="0.0.0.0")
    monkeypatch.setattr(collector, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(collector, "INGEST_TOKEN", "")

    with pytest.raises(SystemExit) as exc:
        collector.validate_bind_security()

    assert exc.value.code == 2


def test_telemetry_collector_nonlocal_bind_accepts_both_secrets(monkeypatch):
    collector = _load_collector(monkeypatch, host="0.0.0.0")
    monkeypatch.setattr(collector, "ADMIN_PASSWORD", "admin-pass")
    monkeypatch.setattr(collector, "INGEST_TOKEN", "ingest-token")

    collector.validate_bind_security()


def test_collector_minimizes_new_network_identifiers(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_DB", str(tmp_path / "events.db"))
    collector = _load_collector(monkeypatch)
    collector.init_db()

    assert collector.record_event(
        {"event": "invocation_start", "install_id": "install", "invocation_id": "call"},
        "203.0.113.9",
    )
    assert collector.record_feedback(
        {"install_id": "install", "query_text": "test query", "reason_text": "test reason"},
        "203.0.113.9",
    )
    assert collector.record_site_visit(
        {"path": "/pricing?email=person@example.test", "referrer": "https://example.test/a?token=secret"},
        "203.0.113.9",
        {"Host": "guanlan.xin", "User-Agent": "Mozilla/5.0 Chrome/120.0"},
    )

    conn = collector.db_connect()
    try:
        assert conn.execute("SELECT remote_addr FROM events").fetchone()[0] == ""
        assert conn.execute("SELECT remote_addr FROM feedback").fetchone()[0] == ""
        visit = conn.execute("SELECT remote_addr, path, referrer, user_agent FROM site_visits").fetchone()
        assert tuple(visit) == ("", "/pricing", "https://example.test", "")
    finally:
        conn.close()


def test_collector_disables_external_geo_lookup_by_default(monkeypatch):
    collector = _load_collector(monkeypatch)

    assert collector.IP_GEO_LOOKUP_ENABLED is False


def test_orphan_breakdown_distinguishes_heartbeat_seen(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_DB", str(tmp_path / "events.db"))
    collector = _load_collector(monkeypatch)
    collector.init_db()
    current_ms = 1_000_000
    cutoff_old = current_ms - collector.ORPHAN_SETTLEMENT_GRACE_SECONDS * 1000 - 1_000
    conn = collector.db_connect()
    try:
        _insert_event(conn, received_ms=cutoff_old, event="invocation_start", invocation_id="no-heartbeat")
        _insert_event(conn, received_ms=cutoff_old, event="invocation_start", invocation_id="with-heartbeat")
        _insert_event(conn, received_ms=cutoff_old + 10, event="invocation_heartbeat", invocation_id="with-heartbeat")
        _insert_event(conn, received_ms=cutoff_old, event="invocation_start", invocation_id="ended")
        _insert_event(conn, received_ms=cutoff_old + 20, event="invocation_end", invocation_id="ended")
        _insert_event(conn, received_ms=cutoff_old, event="invocation_start", invocation_id="still-active")
        conn.execute(
            """
            INSERT INTO active_invocations (
                invocation_id, install_id, session_id, surface, command, version,
                agent_kind, agent_id, started_ms, last_seen_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "still-active",
                "install-a",
                "session-a",
                "cli",
                "search",
                "0.7.2",
                "codex",
                "agent-a",
                cutoff_old,
                current_ms,
            ),
        )
        conn.commit()

        assert collector.query_orphan_starts(conn, 0, current_ms) == 2
        assert collector.query_orphan_breakdown(conn, 0, current_ms) == {
            "with_heartbeat": 1,
            "without_heartbeat": 1,
        }
        rows = collector.query_orphan_sources(conn, 0, current_ms)
    finally:
        conn.close()

    assert rows[0]["orphans"] == 2
    assert rows[0]["with_heartbeat"] == 1
    assert rows[0]["without_heartbeat"] == 1


def test_heartbeat_is_retained_once_for_orphan_diagnosis(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_DB", str(tmp_path / "events.db"))
    collector = _load_collector(monkeypatch)
    collector.init_db()

    payload = {"install_id": "install", "invocation_id": "call", "event": "invocation_start"}
    assert collector.record_event(payload, "203.0.113.9")
    heartbeat = dict(payload, event="invocation_heartbeat")
    assert collector.record_event(heartbeat, "203.0.113.9")
    assert collector.record_event(heartbeat, "203.0.113.9")

    conn = collector.db_connect()
    try:
        heartbeat_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE invocation_id = ? AND event = 'invocation_heartbeat'", ("call",)
        ).fetchone()[0]
        active_count = conn.execute("SELECT COUNT(*) FROM active_invocations WHERE invocation_id = ?", ("call",)).fetchone()[0]
    finally:
        conn.close()

    assert heartbeat_count == 1
    assert active_count == 1


def test_health_error_rate_excludes_explicitly_aborted_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_DB", str(tmp_path / "events.db"))
    collector = _load_collector(monkeypatch)
    collector.init_db()
    current_ms = 4_000_000
    conn = collector.db_connect()
    try:
        for invocation_id, status in (("error", "error"), ("aborted", "aborted"), ("ok", "ok")):
            _insert_event(conn, received_ms=current_ms - 10_000, event="invocation_start", invocation_id=invocation_id)
            _insert_event(
                conn,
                received_ms=current_ms - 9_000,
                event="invocation_end",
                invocation_id=invocation_id,
                status=status,
            )
        conn.commit()
        metrics = collector.query_health_dashboard_metrics(current_ms, 0, 0, 0)
    finally:
        conn.close()

    assert metrics["errors_24h"] == 1
    assert metrics["aborted_24h"] == 1


def test_orphan_rate_waits_for_terminal_event_settlement_window(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_DB", str(tmp_path / "events.db"))
    monkeypatch.setenv("GUANLAN_ORPHAN_SETTLEMENT_GRACE_SECONDS", "600")
    collector = _load_collector(monkeypatch)
    collector.init_db()
    current_ms = 2_000_000
    settled_start = current_ms - collector.ORPHAN_SETTLEMENT_GRACE_SECONDS * 1000 - 10
    recent_start = current_ms - 60_000
    conn = collector.db_connect()
    try:
        _insert_event(conn, received_ms=settled_start, event="invocation_start", invocation_id="old-unclosed")
        _insert_event(conn, received_ms=recent_start, event="invocation_start", invocation_id="awaiting-end")
        conn.commit()

        assert collector.query_settled_starts(conn, 0, current_ms) == 1
        assert collector.query_orphan_starts(conn, 0, current_ms) == 1
    finally:
        conn.close()


def test_blank_session_ids_do_not_merge_unrelated_invocations(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_DB", str(tmp_path / "events.db"))
    collector = _load_collector(monkeypatch)
    collector.init_db()
    conn = collector.db_connect()
    try:
        _insert_event(conn, received_ms=1_000, event="invocation_start", invocation_id="one", session_id="")
        _insert_event(conn, received_ms=1_020, event="invocation_end", invocation_id="one", session_id="")
        _insert_event(conn, received_ms=2_000, event="invocation_start", invocation_id="two", session_id="")
        _insert_event(conn, received_ms=2_040, event="invocation_end", invocation_id="two", session_id="")
        conn.commit()

        stats = collector.query_session_stats(conn, 0)
    finally:
        conn.close()

    assert stats == {"count": 2, "avg_duration_ms": 30, "p95_duration_ms": 40, "avg_calls": 1.0}


def test_dashboard_slow_metrics_wait_for_a_complete_initial_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_DB", str(tmp_path / "events.db"))
    collector = _load_collector(monkeypatch)
    collector.init_db()
    metrics = collector.query_slow_dashboard_metrics_cached(2_000_000, 1_000_000, 0)

    assert metrics["pending"] is False
    assert metrics["session_24h"]["count"] == 0


def test_health_cards_use_one_cached_snapshot_instead_of_mixing_fresh_orphans(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_DB", str(tmp_path / "events.db"))
    collector = _load_collector(monkeypatch)
    collector.init_db()
    current_ms = 10_000_000
    monkeypatch.setattr(collector, "now_ms", lambda: current_ms)
    first_start = current_ms - collector.ORPHAN_SETTLEMENT_GRACE_SECONDS * 1000 - 30_000

    conn = collector.db_connect()
    try:
        _insert_event(conn, received_ms=first_start, event="invocation_start", invocation_id="complete")
        _insert_event(conn, received_ms=first_start + 5_000, event="invocation_end", invocation_id="complete")
        conn.commit()
    finally:
        conn.close()

    first = collector.summary()
    assert first["calls_24h"] == 1
    assert first["session_24h"]["count"] == 1
    assert first["orphan_starts_24h"] == 0

    conn = collector.db_connect()
    try:
        _insert_event(conn, received_ms=first_start, event="invocation_start", invocation_id="new-unclosed")
        conn.commit()
    finally:
        conn.close()

    second = collector.summary()

    # The second response keeps the first complete health snapshot. It must
    # never pair a fresh orphan count with an older session aggregate.
    assert second["health_generated_ms"] == first["health_generated_ms"]
    assert second["calls_24h"] == first["calls_24h"]
    assert second["session_24h"] == first["session_24h"]
    assert second["orphan_starts_24h"] == first["orphan_starts_24h"]
    assert "本组指标同一快照生成于" in collector.render_dashboard()
