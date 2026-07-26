# -*- coding: utf-8 -*-
"""Tests for public quality report generation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts import generate_quality_report as report_gen


def test_quality_report_contains_required_blocks():
    report = report_gen.build_quality_report(include_distribution=False)

    assert report["schema_version"] == "guanlan_quality_report_v1"
    for key in (
        "benchmark",
        "eval_suite",
        "routing_regression",
        "live_smoke",
        "quality_signals",
        "reliability_baseline",
        "distribution",
        "legacy_inventory",
    ):
        assert key in report


def test_quality_report_markdown_has_concrete_conclusions():
    report = report_gen.build_quality_report(include_distribution=False)
    markdown = report_gen.render_markdown(report)

    assert "待测" not in markdown
    assert "Deterministic Benchmark" in markdown
    assert "Routing Regression Inventory" in markdown
    assert "Deterministic Reliability Baseline" in markdown
    assert "Legacy Inventory" in markdown


def test_quality_report_exposes_deterministic_no_regression_baseline():
    report = report_gen.build_quality_report(include_distribution=False)

    baseline = report["reliability_baseline"]
    assert baseline["status"] == "configured"
    assert baseline["reference_version"] == "0.7.9"
    assert {"benchmark", "eval_suite", "quality_regression", "quality_robustness"} <= set(baseline["checks"])


def test_routing_inventory_high_risk_groups_have_positive_and_near_miss():
    inventory = report_gen.build_routing_regression_inventory()

    assert inventory["total_cases"] >= 100
    assert inventory["missing_high_risk_coverage"] == []
    assert inventory["rule_inventory"]["scope_rules"]["tech_dev"] >= 1
    assert inventory["rule_inventory"]["scope_rules"]["!sports"] >= 1
    for group in report_gen.HIGH_RISK_ROUTING_GROUPS:
        assert inventory["high_risk_coverage"][group]["coverage_floor"] == "pass"


def test_quality_report_write_outputs_json_and_markdown(tmp_path):
    markdown_path = tmp_path / "benchmark-report.md"
    json_path = tmp_path / "latest-quality.json"

    report = report_gen.write_report(markdown_output=markdown_path, json_output=json_path)

    assert markdown_path.exists()
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["version"] == report["version"]
    assert payload["routing_regression"]["total_cases"] >= 100
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "待测" not in markdown
    assert "规则索引: intents=" in markdown


def test_quality_report_direct_script_entrypoint(tmp_path):
    markdown_path = tmp_path / "benchmark-report.md"
    json_path = tmp_path / "latest-quality.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/generate_quality_report.py",
            "--output",
            str(markdown_path),
            "--json-output",
            str(json_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(json_path.read_text(encoding="utf-8"))["version"] == report_gen.__version__


def test_legacy_inventory_classifies_legacy_file():
    inventory = report_gen.build_legacy_inventory()

    assert inventory["file"] == "guanlan/web/_legacy_web_impl.py"
    assert inventory["loc"] > 1000
    assert {"search", "read", "research", "renderers", "compat"} <= set(inventory["buckets"])
    seams = inventory["compatibility_seams"]
    assert seams["module"] == "guanlan/web/_impl.py"
    assert seams["sync_function"] == "_sync_legacy_overrides"
    assert "search_web" in seams["entrypoints"]


def test_quality_report_redacts_home_directory_from_default_live_history_path(monkeypatch):
    monkeypatch.setattr(report_gen, "DEFAULT_LIVE_SMOKE_HISTORY_PATH", Path.home() / ".guanlan" / "smoke.jsonl")

    payload = report_gen.build_live_smoke_section()

    assert payload["history_path"].startswith("~/.guanlan/")
    assert str(Path.home()) not in payload["history_path"]
