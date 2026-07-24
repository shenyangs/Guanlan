# -*- coding: utf-8 -*-
"""Tests for deterministic reliability-baseline enforcement."""

from __future__ import annotations

import json

from scripts import reliability_guard as guard


def test_compare_summary_detects_any_failure_warning_or_coverage_drop():
    threshold = {
        "minimum_total": 10,
        "minimum_pass": 10,
        "maximum_warn": 0,
        "maximum_fail": 0,
        "minimum_score": 100,
    }

    regressions = guard.compare_summary({"total": 9, "pass": 8, "warn": 1, "fail": 1, "score": 90}, threshold)

    assert len(regressions) == 5


def test_guard_passes_matching_reports_and_fails_on_quality_drop():
    baseline = {
        "schema_version": "guanlan_reliability_baseline_v1",
        "reference_version": "0.7.9",
        "checks": {
            "benchmark": {
                "minimum_total": 2,
                "minimum_pass": 2,
                "maximum_warn": 0,
                "maximum_fail": 0,
                "minimum_score": 100,
            }
        },
    }

    def passing(_command):
        return {"returncode": 0, "stdout": json.dumps({"summary": {"total": 2, "pass": 2, "warn": 0, "fail": 0, "score": 100}}), "stderr": ""}

    def failing(_command):
        return {"returncode": 0, "stdout": json.dumps({"summary": {"total": 2, "pass": 1, "warn": 1, "fail": 0, "score": 75}}), "stderr": ""}

    assert guard.build_guard_report(baseline=baseline, run=passing)["status"] == "pass"
    report = guard.build_guard_report(baseline=baseline, run=failing)
    assert report["status"] == "fail"
    assert report["checks"][0]["regressions"]
