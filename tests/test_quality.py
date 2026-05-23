# -*- coding: utf-8 -*-
"""Tests for Guanlan quality gate."""

import json
from unittest.mock import patch

import pytest

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
    assert any(item["dimension"] == "evidence_mixer" for item in report["checks"])
    assert "feed_status" in quality.format_regression_report(report)
    assert "evidence_mixer_shadow" in quality.format_regression_report(report)


def test_quality_cli_regression_outputs_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "quality", "regression", "--format", "json"]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["mode"] == "quick"
    assert payload["summary"]["fail"] == 0
    assert "minimum_pool" in payload["contract"]


def test_evidence_mixer_guard_checks_shadow_contract():
    report = quality.run_evidence_mixer_checks()

    assert report["summary"]["fail"] == 0
    assert report["gain_summary"]["positive"] >= 1
    assert report["gain_summary"]["fallback_count"] >= 1
    assert report["gain_summary"]["average_gain_score"] > 0
    assert report["gain_summary"]["activation_empty_risk_count"] == 0
    assert any(item["id"] == "evidence_mixer_policy_keeps_official_primary" for item in report["checks"])
    assert any(
        item["id"] == "evidence_mixer_reputation_fails_open_on_single_domain"
        and item["shadow_report"]["fallback_reason"] == "coverage_floor"
        for item in report["checks"]
    )
    assert all("gain_estimate" in item for item in report["checks"])
    assert "Evidence Mixer Guard" in quality.format_evidence_mixer_report(report)
    assert "增益估计" in quality.format_evidence_mixer_report(report)


def test_quality_cli_evidence_mixer_outputs_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "quality", "evidence-mixer", "--format", "json"]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["mode"] == "quick"
    assert payload["summary"]["fail"] == 0
    assert payload["contract"]["fixture_count"] >= 5
    assert "gain_summary" in payload


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
        with patch("sys.argv", ["guanlan", "quality", "live-smoke", "--format", "json", "--timeout-budget", "180"]):
            main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["mode"] == "live"
    assert payload["contract"]["blocking"] is False
    assert payload["contract"]["timeout_budget_seconds"] == 180
    assert payload["contract"]["timeout_budget_ms"] == 180000
    assert any("timeout_ms" in item for item in payload["contract"]["timeout_unit_contract"])
    assert payload["live_trend_report"]["runs_considered"] == 1
    assert payload["live_trend_report"]["blocking"] is False
    assert payload["summary"]["fail"] == 1


def test_live_smoke_contract_exposes_scenario_groups():
    fake_report = {
        "mode": "live",
        "summary": {"total": 4, "pass": 3, "warn": 1, "fail": 0, "score": 87.5},
        "checks": [
            {"id": "a", "scenario_group": "policy", "status": "pass"},
            {"id": "b", "scenario_group": "finance", "status": "warn"},
            {"id": "c", "scenario_group": "university", "status": "pass"},
            {"id": "d", "scenario_group": "reputation", "status": "pass"},
        ],
    }
    with patch("guanlan.quality.run_quality_checks", return_value=fake_report):
        report = quality.run_live_smoke_checks(limit=3, timeout_budget=180, profile="china")

    assert "scenario_groups" in report["network_summary"]
    groups = report["network_summary"]["scenario_groups"]
    assert {"policy", "finance", "university", "reputation"} <= set(groups)


def test_live_smoke_history_records_and_summarizes_trends(tmp_path):
    history_path = tmp_path / "live-smoke-history.jsonl"

    reports = [
        {
            "mode": "live",
            "summary": {"total": 2, "pass": 1, "warn": 1, "fail": 0, "score": 75},
            "checks": [
                {"id": "live_policy", "scenario_group": "policy", "status": "warn", "message": "upstream timeout"},
                {"id": "live_feeds", "scenario_group": "feeds", "status": "pass", "message": "ok"},
            ],
        },
        {
            "mode": "live",
            "summary": {"total": 2, "pass": 1, "warn": 1, "fail": 0, "score": 75},
            "checks": [
                {"id": "live_policy", "scenario_group": "policy", "status": "pass", "message": "ok"},
                {"id": "live_feeds", "scenario_group": "feeds", "status": "warn", "message": "backend cache stale"},
            ],
        },
    ]

    with patch("guanlan.quality.run_quality_checks", side_effect=[dict(item) for item in reports]):
        quality.run_live_smoke_checks(history_path=history_path, record_history=True)
        report = quality.run_live_smoke_checks(history_path=history_path, record_history=True)

    trend = report["live_trend_report"]
    assert history_path.exists()
    assert len(history_path.read_text(encoding="utf-8").splitlines()) == 2
    assert trend["runs_considered"] == 2
    assert trend["new_failures"] == ["live_feeds"]
    assert trend["recovered"] == ["live_policy"]
    assert trend["likely_network_or_upstream"] == 1
    assert "live smoke 趋势" in quality.format_quality_report(report)


def test_quality_cli_live_smoke_records_history_without_changing_strict_exit(tmp_path, capsys):
    from guanlan.cli import main

    history_path = tmp_path / "history.jsonl"
    fake_report = {
        "mode": "live",
        "summary": {"total": 1, "pass": 0, "warn": 0, "fail": 1, "score": 0},
        "checks": [{"id": "live_timeout", "scenario_group": "policy", "status": "fail", "message": "network timeout"}],
    }
    argv = [
        "guanlan",
        "quality",
        "live-smoke",
        "--format",
        "json",
        "--strict",
        "--record-history",
        "--history-path",
        str(history_path),
    ]
    with patch("guanlan.quality.run_quality_checks", return_value=fake_report):
        with patch("sys.argv", argv):
            with pytest.raises(SystemExit) as exc:
                main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exc.value.code == 1
    assert history_path.exists()
    assert payload["contract"]["blocking"] is True
    assert payload["live_trend_report"]["recorded"] is True
