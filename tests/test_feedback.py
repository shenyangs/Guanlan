# -*- coding: utf-8 -*-
"""Tests for search dissatisfaction feedback reporting."""

from unittest.mock import patch

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
