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
