# -*- coding: utf-8 -*-
"""JSONL-driven routing regressions for Guanlan's agent auto mode."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from guanlan.workflow_decider import build_agent_plan

FIXTURE = Path(__file__).parent / "fixtures" / "routing_regression_cases.jsonl"


def _load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            cases.append(json.loads(text))
    return cases


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _commands(payload: dict[str, Any]) -> list[str]:
    commands = [str(payload.get("primary_command") or "")]
    for key in ("recommended_commands", "silent_repair_commands"):
        for item in payload.get(key) or []:
            commands.append(str(item.get("command") or ""))
    return commands


def test_routing_regression_fixture_has_broad_vertical_coverage():
    cases = _load_cases()
    categories = {case["category"] for case in cases}
    case_types = {case["case_type"] for case in cases}

    assert len(cases) >= 18
    assert {"positive", "negative", "near_miss"} <= case_types
    assert {
        "tech",
        "wps_office",
        "finance",
        "policy",
        "ecommerce",
        "university",
        "podcast",
        "cybersecurity",
        "weather",
        "science",
        "entertainment",
    } <= categories


@pytest.mark.parametrize("case", _load_cases(), ids=lambda item: item["id"])
def test_agent_auto_routing_regression_case(case: dict[str, Any]):
    plan = build_agent_plan(
        case["query"],
        mode=case.get("mode", "auto"),
        profile=case.get("profile", "china"),
    )
    payload = plan.to_dict()
    decision = payload["decision"]
    route_plan = decision.get("route_plan") or {}
    intents = set(decision.get("route_intents") or [])
    scopes = set(route_plan.get("preferred_scopes") or []) | set(route_plan.get("fallback_scopes") or [])
    commands = _commands(payload)
    command_blob = "\n".join(commands)

    expected_intents = set(_list(case.get("expected_intents_any")))
    if expected_intents:
        assert intents & expected_intents, f"{case['id']} intents={sorted(intents)}"
    for intent in _list(case.get("forbidden_intents")):
        assert intent not in intents, f"{case['id']} unexpectedly routed to {intent}: {sorted(intents)}"

    expected_scopes = set(_list(case.get("expected_scopes_any")))
    if expected_scopes:
        assert scopes & expected_scopes, f"{case['id']} scopes={sorted(scopes)}"
    for scope in _list(case.get("forbidden_scopes")):
        assert scope not in scopes, f"{case['id']} unexpectedly preferred/fell back to {scope}: {sorted(scopes)}"
    target_sites = set(str(site) for site in route_plan.get("target_sites") or [])
    for site in _list(case.get("expected_sites_contains")):
        assert site in target_sites, f"{case['id']} target_sites={sorted(target_sites)}"

    primary = str(payload.get("primary_command") or "")
    for needle in _list(case.get("expected_primary_contains")):
        assert needle in primary, f"{case['id']} primary={primary}"
    for needle in _list(case.get("expected_command_contains")):
        assert needle in command_blob, f"{case['id']} commands={commands}"
    for needle in _list(case.get("forbidden_command_contains")):
        assert needle not in command_blob, f"{case['id']} commands={commands}"
