# -*- coding: utf-8 -*-
"""Tests for Guanlan update notices."""

from unittest.mock import patch

import guanlan.update_check as update_check
from guanlan.update_check import UpdateInfo


def test_is_newer_version_compares_semver_parts():
    assert update_check.is_newer_version("0.2.4", "0.1.14") is True
    assert update_check.is_newer_version("0.2.4", "0.2.3") is True
    assert update_check.is_newer_version("0.2.4", "0.2.4") is False
    assert update_check.is_newer_version("0.2.3", "0.2.4") is False


def test_format_update_notice_mentions_safe_upgrade_paths():
    notice = update_check.format_update_notice(UpdateInfo(current="0.1.14", latest="0.2.4"))

    assert "当前 v0.1.14" in notice
    assert "最新 v0.2.4" in notice
    assert "uv tool install --force --upgrade guanlan" in notice
    assert "只有 --force 可能重装旧锁定版本" in notice
    assert "brew update" in notice
    assert "pipx install --force guanlan" in notice
    assert "which -a guanlan" in notice
    assert 'guanlan hotnews today --limit 5 --trends' in notice


def test_format_compact_update_notice_mentions_upgrade_and_install_check():
    notice = update_check.format_compact_update_notice(UpdateInfo(current="0.4.3", latest="0.4.4"))

    assert "当前 v0.4.3" in notice
    assert "最新 v0.4.4" in notice
    assert "uv tool install --force --upgrade guanlan" in notice
    assert "guanlan doctor --install-check" in notice


def test_doctor_prints_update_notice_when_newer_version_available(capsys):
    import guanlan.cli as cli

    with patch(
        "guanlan.cli._print_update_notice_if_available",
        wraps=cli._print_update_notice_if_available,
    ), patch("guanlan.update_check.get_update_info", return_value=UpdateInfo("0.1.14", "0.2.4")):
        cli._print_update_notice_if_available()

    captured = capsys.readouterr()
    assert "版本提醒" in captured.out
    assert "uv tool install --force --upgrade guanlan" in captured.out
    assert "guanlan doctor --trace" in captured.out


def test_check_update_uses_pypi_without_github_repo(capsys, monkeypatch):
    import guanlan.cli as cli

    monkeypatch.delenv("GUANLAN_UPDATE_REPO", raising=False)
    with patch("guanlan.update_check.get_update_info", return_value=UpdateInfo("0.1.14", "0.2.4")):
        result = cli._cmd_check_update()

    captured = capsys.readouterr()
    assert result == "update_available"
    assert "版本提醒" in captured.out


def test_install_check_reports_duplicate_paths_and_stale_version():
    with patch(
        "guanlan.update_check._path_version",
        side_effect=[("0.2.9", ""), ("0.3.0", "")],
    ):
        report = update_check.run_install_check(
            "0.2.9",
            latest="0.3.0",
            command_path="/usr/local/bin/guanlan",
            all_paths=["/usr/local/bin/guanlan", "/opt/homebrew/bin/guanlan"],
        )
    text = update_check.format_install_check(report)

    assert report["status"] == "fail"
    assert report["stale"] is True
    assert report["multiple_paths"] is True
    assert report["path_details"][0]["active"] is True
    assert report["path_details"][0]["version"] == "0.2.9"
    assert "多个 guanlan 路径" in text
    assert "当前优先" in text
    assert "以下路径看起来不是公开最新版本" in text
    assert "uv tool install --force --upgrade guanlan" in text


def test_cached_update_info_reuses_local_cache(tmp_path, monkeypatch):
    cache_path = tmp_path / "update-check.json"
    monkeypatch.setenv("GUANLAN_UPDATE_CHECK", "1")
    monkeypatch.setenv("GUANLAN_UPDATE_CHECK_CACHE", str(cache_path))

    with patch("guanlan.update_check.latest_pypi_version", return_value="0.4.4"):
        info = update_check.cached_update_info("0.4.3", timeout=0.01, ttl_seconds=3600)

    assert info == UpdateInfo(current="0.4.3", latest="0.4.4")
    assert cache_path.exists()

    with patch("guanlan.update_check.latest_pypi_version", side_effect=AssertionError("should use cache")):
        cached = update_check.cached_update_info("0.4.3", timeout=0.01, ttl_seconds=3600)

    assert cached == UpdateInfo(current="0.4.3", latest="0.4.4")


def test_doctor_install_check_cli(capsys):
    import guanlan.cli as cli

    with patch(
        "guanlan.update_check.run_install_check",
        return_value={
            "status": "ok",
            "current_version": "0.3.0",
            "latest_version": "0.3.0",
            "command_path": "/tmp/guanlan",
            "all_paths": ["/tmp/guanlan"],
            "path_count": 1,
            "python": "/tmp/python",
            "stale": False,
            "multiple_paths": False,
            "recommendations": ["可以继续配置 MCP 或 Agent。"],
        },
    ), patch("sys.argv", ["guanlan", "doctor", "--install-check"]):
        cli.main()

    captured = capsys.readouterr()
    assert "观澜安装自检" in captured.out
    assert "/tmp/guanlan" in captured.out
