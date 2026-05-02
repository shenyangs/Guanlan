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
    assert "uv tool install --force guanlan" in notice
    assert "brew update" in notice


def test_doctor_prints_update_notice_when_newer_version_available(capsys):
    import guanlan.cli as cli

    with patch(
        "guanlan.cli._print_update_notice_if_available",
        wraps=cli._print_update_notice_if_available,
    ), patch("guanlan.update_check.get_update_info", return_value=UpdateInfo("0.1.14", "0.2.4")):
        cli._print_update_notice_if_available()

    captured = capsys.readouterr()
    assert "版本提醒" in captured.out
    assert "uv tool install --force guanlan" in captured.out


def test_check_update_uses_pypi_without_github_repo(capsys, monkeypatch):
    import guanlan.cli as cli

    monkeypatch.delenv("GUANLAN_UPDATE_REPO", raising=False)
    with patch("guanlan.update_check.get_update_info", return_value=UpdateInfo("0.1.14", "0.2.4")):
        result = cli._cmd_check_update()

    captured = capsys.readouterr()
    assert result == "update_available"
    assert "版本提醒" in captured.out
