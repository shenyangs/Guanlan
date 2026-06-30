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


def _insert_event(conn, *, received_ms: int, event: str, invocation_id: str, command: str = "search"):
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
            "install-a",
            "session-a",
            invocation_id,
            "cli",
            command,
            "0.7.2",
            "codex",
            "agent-a",
            "darwin",
            "3.12",
            "",
            None,
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


def test_orphan_breakdown_distinguishes_heartbeat_seen(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_DB", str(tmp_path / "events.db"))
    collector = _load_collector(monkeypatch)
    collector.init_db()
    current_ms = 1_000_000
    cutoff_old = current_ms - collector.ACTIVE_TTL_SECONDS * 1000 - 1_000
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
