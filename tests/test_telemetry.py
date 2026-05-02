# -*- coding: utf-8 -*-
"""Tests for privacy-preserving anonymous telemetry."""

from unittest.mock import patch

from guanlan.config import Config
from guanlan.telemetry import _display_endpoint, load_settings, telemetry_span, telemetry_status


def test_telemetry_is_inactive_without_endpoint(tmp_path, monkeypatch):
    monkeypatch.delenv("GUANLAN_TELEMETRY_ENDPOINT", raising=False)
    monkeypatch.delenv("GUANLAN_TELEMETRY", raising=False)
    config = Config(config_path=tmp_path / "config.yaml")

    assert load_settings(config) is None
    status = telemetry_status(config)
    assert status["enabled"] is False
    assert status["configured"] is False


def test_telemetry_can_be_disabled_with_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_TELEMETRY_ENDPOINT", "https://metrics.example/v1/events")
    monkeypatch.setenv("GUANLAN_TELEMETRY", "0")
    config = Config(config_path=tmp_path / "config.yaml")

    assert load_settings(config) is None


def test_telemetry_is_disabled_under_pytest_unless_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_TELEMETRY_ENDPOINT", "https://metrics.example/v1/events")
    monkeypatch.delenv("GUANLAN_TELEMETRY", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_cli.py::test_example")
    config = Config(config_path=tmp_path / "config.yaml")

    assert load_settings(config) is None


def test_telemetry_span_posts_start_and_end_without_sensitive_arguments(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_TELEMETRY_ENDPOINT", "https://metrics.example/v1/events")
    monkeypatch.setenv("GUANLAN_TELEMETRY", "1")
    config = Config(config_path=tmp_path / "config.yaml")
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            return b""

    def fake_urlopen(req, timeout=0):
        calls.append((req, timeout))
        return FakeResponse()

    with patch("guanlan.telemetry.request.urlopen", fake_urlopen):
        with telemetry_span("search", surface="cli", config=config):
            pass

    assert len(calls) == 2
    bodies = [req.data.decode("utf-8") for req, _timeout in calls]
    assert "invocation_start" in bodies[0]
    assert "invocation_end" in bodies[1]
    assert '"command":"search"' in bodies[0]
    assert '"agent_id":"' in bodies[0]
    assert "人工智能" not in "".join(bodies)
    assert "https://example.com" not in "".join(bodies)
    assert config.get("telemetry_install_id")


def test_telemetry_config_off_wins_over_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_TELEMETRY_ENDPOINT", "https://metrics.example/v1/events")
    monkeypatch.delenv("GUANLAN_TELEMETRY", raising=False)
    config = Config(config_path=tmp_path / "config.yaml")
    config.set("telemetry_enabled", False)

    assert load_settings(config) is None


def test_telemetry_status_redacts_endpoint_token():
    endpoint = _display_endpoint("https://metrics.example/v1/events?token=secret&source=test")

    assert endpoint == "https://metrics.example/v1/events?token=%2A%2A%2A&source=test"
    assert "secret" not in endpoint
