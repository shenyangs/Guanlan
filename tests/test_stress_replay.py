# -*- coding: utf-8 -*-
"""Tests for the stress-report replay helper."""

from __future__ import annotations

from guanlan import webtools
from scripts.stress_replay import (
    format_stress_report_markdown,
    load_stress_report_cases,
    replay_stress_report,
)


def test_stress_report_fixture_has_expected_cases():
    cases = load_stress_report_cases()

    assert len(cases) == 20
    assert {case["id"] for case in cases} >= {"stress_001", "stress_010", "stress_020"}


def test_stress_report_replay_summarizes_results(monkeypatch):
    def fake_search_web(query, profile="china", limit=10, trace=True):  # noqa: ARG001
        route_plan = webtools.build_route_plan(query, profile=profile, limit=limit).to_dict()
        quality = webtools.detect_search_quality_profile(query, profile=profile)
        return webtools.SearchResults(
            [
                {
                    "title": f"{query} result",
                    "url": "https://example.com/a",
                    "domain": "example.com",
                    "source_type": "通用网页",
                    "evidence_role": "open_web_context",
                    "trace": {
                        "route_plan": route_plan,
                        "query_quality": quality,
                        "quality_summary": {
                            "quality_status": "needs_more_evidence",
                            "preferred_hit_count": 1,
                            "warnings": [],
                            "source_mix": {"通用网页": 1},
                        },
                        "query_shape": {
                            "backend_query": query,
                            "semantic_rules": [],
                        },
                    },
                }
            ]
        )

    monkeypatch.setattr("scripts.stress_replay.search_api.search_web", fake_search_web)
    report = replay_stress_report(case_ids=["stress_001", "stress_004"])

    assert report["summary"]["total"] == 2
    assert report["summary"]["warn"] == 0
    assert "stress_001" in format_stress_report_markdown(report)
