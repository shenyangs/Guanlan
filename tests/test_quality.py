# -*- coding: utf-8 -*-
"""Tests for Guanlan quality gate."""

import json
from unittest.mock import patch

from guanlan import quality


def test_quality_quick_run_passes_core_checks():
    report = quality.run_quality_checks(mode="quick")

    assert report["summary"]["fail"] == 0
    assert report["summary"]["pass"] >= 6
    assert any(item["id"] == "reputation_avoids_english_drift" for item in report["checks"])
    assert "policy_source_identity" in quality.format_quality_report(report)


def test_quality_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "quality", "run", "--format", "json"]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["mode"] == "quick"
    assert payload["summary"]["fail"] == 0


def test_coverage_guard_checks_default_contract():
    report = quality.run_coverage_checks(mode="quick")

    assert report["summary"]["fail"] == 0
    assert any(item["id"] == "coverage_search_default_limit" for item in report["checks"])
    assert any(item["id"] == "coverage_feeds_default_limit" for item in report["checks"])
    assert "不得让 Agent" in quality.format_coverage_report(report)


def test_quality_cli_coverage_outputs_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "quality", "coverage", "--format", "json"]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["mode"] == "quick"
    assert payload["contract"]["search_min"] == 50
    assert payload["contract"]["feeds_min"] == 80
    assert payload["summary"]["fail"] == 0


def test_regression_guard_checks_agent_visible_depth():
    report = quality.run_regression_checks(mode="quick")

    assert report["summary"]["fail"] == 0
    assert any(item["id"] == "regression_feeds_can_mark_stale_cache" for item in report["checks"])
    assert "feed_status" in quality.format_regression_report(report)


def test_quality_cli_regression_outputs_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "quality", "regression", "--format", "json"]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["mode"] == "quick"
    assert payload["summary"]["fail"] == 0
    assert "minimum_pool" in payload["contract"]
