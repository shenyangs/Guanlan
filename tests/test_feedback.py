# -*- coding: utf-8 -*-
"""Tests for search dissatisfaction feedback reporting."""

from unittest.mock import patch

from guanlan.commands._feedback import _auto_feedback_enabled, _submit_auto_feedback
from guanlan.config import Config
from guanlan.feedback import load_feedback_settings, submit_feedback


def test_feedback_uses_default_endpoint(tmp_path, monkeypatch):
    monkeypatch.delenv("GUANLAN_FEEDBACK_ENDPOINT", raising=False)
    monkeypatch.setenv("GUANLAN_TELEMETRY", "1")
    config = Config(config_path=tmp_path / "config.yaml")

    settings = load_feedback_settings(config)
    assert settings is not None
    assert "/guanlan-telemetry/v1/feedback" in settings.endpoint


def test_feedback_submit_sends_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_FEEDBACK_ENDPOINT", "https://metrics.example/v1/feedback")
    monkeypatch.setenv("GUANLAN_TELEMETRY", "1")
    config = Config(config_path=tmp_path / "config.yaml")
    calls = []

    class FakeResponse:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            return b""

        def close(self):
            return None

    def fake_urlopen(req, timeout=0):
        calls.append((req, timeout))
        return FakeResponse()

    with patch("guanlan.feedback.request.urlopen", fake_urlopen):
        result = submit_feedback(
            "北京 AI 政策",
            "结果里营销号太多，官方来源太少",
            command="search",
            surface="cli",
            profile="china",
            backend="auto",
            config=config,
        )

    assert result["ok"] is True
    assert result["queued"] is False
    assert calls
    body = calls[0][0].data.decode("utf-8")
    assert '"query_text":"北京 AI 政策"' in body
    assert '"reason_text":"结果里营销号太多，官方来源太少"' in body


def test_auto_feedback_is_opt_in_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("GUANLAN_AUTO_FEEDBACK", raising=False)
    monkeypatch.delenv("GUANLAN_TELEMETRY", raising=False)
    monkeypatch.setattr("guanlan.config.Config.CONFIG_FILE", tmp_path / "config.yaml")

    assert _auto_feedback_enabled() is False


def test_auto_feedback_requires_explicit_flag(monkeypatch):
    monkeypatch.setenv("GUANLAN_AUTO_FEEDBACK", "1")
    calls = []

    def fake_submit(*args, **kwargs):
        calls.append((args, kwargs))

    with patch("guanlan.feedback.submit_feedback", fake_submit):
        _submit_auto_feedback("北京 AI 政策", "结果为空", command="search", profile="china", backend="auto")

    assert calls


def test_auto_feedback_drops_sensitive_text(monkeypatch):
    monkeypatch.setenv("GUANLAN_AUTO_FEEDBACK", "1")
    calls = []

    def fake_submit(*args, **kwargs):
        calls.append((args, kwargs))

    with patch("guanlan.feedback.submit_feedback", fake_submit):
        _submit_auto_feedback(
            "排查 token ghp_abcdefghijklmnopqrstuvwxyz123456",
            "cookie=sessionid=secret123",
            command="search",
            profile="china",
            backend="auto",
        )

    assert calls == []


def test_feedback_submit_rejects_sensitive_text(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_FEEDBACK_ENDPOINT", "https://metrics.example/v1/feedback")
    monkeypatch.setenv("GUANLAN_TELEMETRY", "1")
    config = Config(config_path=tmp_path / "config.yaml")

    result = submit_feedback(
        "排查 ghp_abcdefghijklmnopqrstuvwxyz123456",
        "结果为空",
        command="search",
        config=config,
    )

    assert result["ok"] is False
    assert "sensitive" in result["message"]
    assert not (tmp_path / "feedback_queue.jsonl").exists()


def test_feedback_submit_queues_when_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_FEEDBACK_ENDPOINT", "https://metrics.example/v1/feedback")
    monkeypatch.setenv("GUANLAN_TELEMETRY", "1")
    config = Config(config_path=tmp_path / "config.yaml")

    def fail_urlopen(_req, timeout=0):
        raise TimeoutError("offline")

    with patch("guanlan.feedback.request.urlopen", fail_urlopen):
        result = submit_feedback(
            "人工智能 监管",
            "同质化结果太多",
            command="search",
            config=config,
        )

    assert result["ok"] is True
    assert result["queued"] is True
    queue_path = tmp_path / "feedback_queue.jsonl"
    assert queue_path.exists()
