# -*- coding: utf-8 -*-
"""Tests for doctor module."""

import os

import pytest

import guanlan.doctor as doctor
from guanlan.config import Config


class _StubChannel:
    def __init__(self, name, description, tier, status, message, backends=None):
        self.name = name
        self.description = description
        self.tier = tier
        self._status = status
        self._message = message
        self.backends = backends or []

    def check(self, config=None):
        return self._status, self._message


@pytest.fixture
def tmp_config(tmp_path):
    return Config(config_path=tmp_path / "config.yaml")


class TestDoctor:
    def test_check_all_collects_channel_results(self, tmp_config, monkeypatch):
        monkeypatch.setattr(
            doctor,
            "get_all_channels",
            lambda profile=None: [
                _StubChannel("web", "网页", 0, "ok", "可抓取网页", ["requests"]),
                _StubChannel("github", "GitHub", 0, "warn", "gh 未安装", ["gh"]),
                _StubChannel("exa_search", "全网语义搜索", 1, "off", "mcporter 未配置", ["Exa"]),
            ],
        )

        results = doctor.check_all(tmp_config)

        assert results == {
            "web": {
                "status": "ok",
                "name": "网页",
                "message": "可抓取网页",
                "tier": 0,
                "backends": ["requests"],
                "readiness": "verified",
                "verification": "verified",
                "stability": "stable",
                "risk_level": "low",
                "auth": "none",
                "batch": "allowed",
                "category": "web",
                "expectation": "",
            },
            "github": {
                "status": "warn",
                "name": "GitHub",
                "message": "gh 未安装",
                "tier": 0,
                "backends": ["gh"],
                "readiness": "best-effort",
                "verification": "verified",
                "stability": "stable",
                "risk_level": "low",
                "auth": "optional",
                "batch": "allowed",
                "category": "dev",
                "expectation": "",
            },
            "exa_search": {
                "status": "off",
                "name": "全网语义搜索",
                "message": "mcporter 未配置",
                "tier": 1,
                "backends": ["Exa"],
                "readiness": "unavailable",
                "verification": "unverified",
                "stability": "opt-in",
                "risk_level": "low",
                "auth": "external",
                "batch": "allowed",
                "category": "search",
                "expectation": "",
            },
        }

    def test_check_all_skips_sensitive_probes_via_env(self, tmp_config, monkeypatch):
        seen = []

        class _EnvChannel(_StubChannel):
            def check(self, config=None):
                seen.append(os.environ.get("GUANLAN_SKIP_SENSITIVE_PROBES"))
                return self._status, self._message

        monkeypatch.delenv("GUANLAN_SKIP_SENSITIVE_PROBES", raising=False)
        monkeypatch.setattr(
            doctor,
            "get_all_channels",
            lambda profile=None: [
                _EnvChannel("github", "GitHub", 0, "ok", "已跳过认证探测", ["gh"]),
            ],
        )

        doctor.check_all(tmp_config, skip_sensitive=True)

        assert seen == ["1"]
        assert os.environ.get("GUANLAN_SKIP_SENSITIVE_PROBES") is None

    def test_format_report(self):
        report = doctor.format_report(
            {
                "web": {
                    "status": "ok",
                    "name": "网页",
                    "message": "可抓取网页",
                    "tier": 0,
                    "backends": ["requests"],
                },
                "exa_search": {
                    "status": "off",
                    "name": "全网语义搜索",
                    "message": "mcporter 未配置",
                    "tier": 1,
                    "backends": ["Exa"],
                },
                "xiaohongshu": {
                    "status": "warn",
                    "name": "小红书",
                    "message": "MCP 已配置，但健康检查超时",
                    "tier": 2,
                    "backends": ["mcporter"],
                },
            }
        )

        # Strip Rich markup tags before checking rendered text.
        import re
        plain = re.sub(r"\[[^\]]*\]", "", report)
        assert "观澜 / Guanlan" in plain
        assert "装好即用：" in plain
        assert "1/3 个渠道可用" in plain
        # Inactive optional channels should be summarized in one line
        assert "可选渠道可以解锁" in plain

    def test_format_report_shows_profile(self):
        report = doctor.format_report(
            {
                "web": {
                    "status": "ok",
                    "name": "网页",
                    "message": "可抓取网页",
                    "tier": 0,
                    "backends": ["requests"],
                },
            },
            profile="china",
        )
        assert "中文场景" in report

    def test_format_trace_shows_sensitive_probe_mode(self):
        trace = doctor.format_trace(
            {
                "github": {
                    "status": "ok",
                    "name": "GitHub",
                    "message": "gh CLI 已安装",
                    "tier": 0,
                    "backends": ["gh"],
                },
            },
            skip_sensitive=True,
        )

        assert "诊断追踪" in trace
        assert "敏感探测: skipped" in trace
        assert "github: status=ok" in trace
        assert "stability=" in trace

    def test_scan_config_detects_plaintext_sensitive_values(self, tmp_config):
        secret = "ghp_abcdefghijklmnopqrstuvwxyz123456"
        tmp_config.set("github_token", secret)
        tmp_config.set("normal_setting", "visible")

        scan = doctor.scan_config(tmp_config)

        assert scan["exists"] is True
        assert len(scan["findings"]) == 1
        assert scan["findings"][0]["path"] == "github_token"
        assert "GitHub token" in " ".join(scan["findings"][0]["reasons"])

        report = doctor.format_config_scan(scan)
        assert "配置安全扫描" in report
        assert "github_token" in report
        assert secret not in report
        assert "normal_setting" not in report

    def test_scan_config_detects_cookie_header_under_plain_key(self, tmp_config):
        cookie = "auth_token=abc123; ct0=def456; other=value"
        tmp_config.set("browser_state", cookie)

        scan = doctor.scan_config(tmp_config)

        assert len(scan["findings"]) == 1
        assert scan["findings"][0]["path"] == "browser_state"
        assert "Cookie header" in " ".join(scan["findings"][0]["reasons"])
        assert cookie not in doctor.format_config_scan(scan)
