# -*- coding: utf-8 -*-
"""Tests for public quality report generation."""

from __future__ import annotations

import json

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
    assert "Legacy Inventory" in markdown


def test_routing_inventory_high_risk_groups_have_positive_and_near_miss():
    inventory = report_gen.build_routing_regression_inventory()

    assert inventory["total_cases"] >= 100
    assert inventory["missing_high_risk_coverage"] == []
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
    assert "待测" not in markdown_path.read_text(encoding="utf-8")


def test_legacy_inventory_classifies_legacy_file():
    inventory = report_gen.build_legacy_inventory()

    assert inventory["file"] == "guanlan/web/_legacy_web_impl.py"
    assert inventory["loc"] > 1000
    assert {"search", "read", "research", "renderers", "compat"} <= set(inventory["buckets"])
