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
    assert payload["contract"]["search_min"] == 80
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


def test_robustness_guard_checks_messy_agent_workflows():
    report = quality.run_robustness_checks(mode="quick")

    assert report["summary"]["fail"] == 0
    assert any(item["id"] == "robustness_archive_ingest_audits_noise_before_write" for item in report["checks"])
    assert any(item["id"] == "robustness_release_gate_runs_full_local_checks" for item in report["checks"])
    assert "Robustness Guard" in quality.format_robustness_report(report)


def test_quality_cli_robustness_outputs_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "quality", "robustness", "--format", "json"]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["mode"] == "quick"
    assert payload["summary"]["fail"] == 0
    assert "must_explain" in payload["contract"]


def test_quality_cli_live_smoke_is_non_blocking_by_default(capsys):
    from guanlan.cli import main

    fake_report = {
        "mode": "live",
        "summary": {"total": 1, "pass": 0, "warn": 0, "fail": 1, "score": 0},
        "checks": [{"id": "live_timeout", "status": "fail", "message": "upstream timeout"}],
    }
    with patch("guanlan.quality.run_quality_checks", return_value=fake_report):
        with patch("sys.argv", ["guanlan", "quality", "live-smoke", "--format", "json"]):
            main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["mode"] == "live"
    assert payload["contract"]["blocking"] is False
    assert payload["summary"]["fail"] == 1
