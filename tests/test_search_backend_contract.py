# -*- coding: utf-8 -*-
"""Backend quality contracts for Guanlan search."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from guanlan import webtools
from guanlan.quality import run_backend_fixture_checks


def _low_relevance_rows(source: str = "bing") -> list[webtools.SearchResult]:
    return [
        webtools.SearchResult(title="什么是固本培元？", url="https://example.com/guben", snippet="中医养生内容", source=source),
        webtools.SearchResult(title="胆固醇 HDL LDL", url="https://health.example.com/a", snippet="健康科普", source=source),
        webtools.SearchResult(title="仆固怀恩传", url="https://history.example.com/a", snippet="历史人物", source=source),
    ]


def _good_rows(source: str = "duckduckgo") -> list[webtools.SearchResult]:
    return [
        webtools.SearchResult(
            title="固态电池量产时间表：产业进展",
            url="https://www.gov.cn/example",
            snippet="固态电池 量产 时间表 政策 进展",
            source=source,
        )
    ]


def test_backend_fixtures_guard_passes():
    report = run_backend_fixture_checks()

    assert report["summary"]["fail"] == 0
    assert {item["id"] for item in report["checks"]} >= {
        "bing_cjk_compound_not_split",
        "unsafe_adult_batch_filtered",
        "good_gov_policy_kept",
    }


def test_explicit_backend_must_return_diagnostics_instead_of_polluted_results(monkeypatch):
    def fake_backend(name, query, *, limit, network_mode="auto", profile=None):
        assert name == "bing"
        return _low_relevance_rows(name), [{"mode": network_mode, "status": "ok"}]

    monkeypatch.setattr(webtools, "_search_backend_with_network", fake_backend)

    results = webtools.search_web("固态电池量产时间表", backend="bing", limit=10, trace=True)

    assert results == []
    diagnostics = results.diagnostics["backend_diagnostics"]
    assert diagnostics[0]["backend"] == "bing"
    assert diagnostics[0]["status"] == "low_relevance"
    assert diagnostics[0]["quality_gate"]["usable"] is False
    assert diagnostics[0]["quality_gate"]["reason"]


def test_auto_backend_falls_through_after_low_relevance(monkeypatch):
    def fake_order(*_args, **_kwargs):
        return ["bing", "duckduckgo"]

    def fake_backend(name, query, *, limit, network_mode="auto", profile=None):
        if name == "bing":
            return _low_relevance_rows(name), [{"mode": network_mode, "status": "ok"}]
        if name == "duckduckgo":
            return _good_rows(name), [{"mode": network_mode, "status": "ok"}]
        raise AssertionError(name)

    monkeypatch.setattr(webtools, "backend_order", fake_order)
    monkeypatch.setattr(webtools, "_search_backend_with_network", fake_backend)

    results = webtools.search_web("固态电池量产时间表", backend="auto", limit=10, trace=True)

    assert len(results) == 1
    assert results[0]["source"] == "duckduckgo"
    diagnostics = results.diagnostics["backend_diagnostics"]
    assert [item["status"] for item in diagnostics[:2]] == ["low_relevance", "ok"]
    assert results.diagnostics["backend_summary"]["fallback_used"] is True


def test_pre_release_status_blocks_dirty_worktree(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "pre_release_status.sh"
    completed = subprocess.run(
        [str(script)],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if completed.returncode == 0:
        pytest.skip("worktree is clean in this checkout; dirty guard is exercised in release gate")
    assert "working tree is dirty" in completed.stderr


def test_pre_release_status_allows_explicit_local_diagnostics():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "pre_release_status.sh"
    completed = subprocess.run(
        [str(script)],
        cwd=root,
        env={**os.environ, "GUANLAN_RELEASE_ALLOW_DIRTY": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0
    assert "pre-release status ok" in completed.stdout
    assert "version=" in completed.stdout


def test_pre_release_status_can_require_homebrew_formula_sync(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "pre_release_status.sh"
    formula = tmp_path / "guanlan.rb"
    formula.write_text('url "https://files.pythonhosted.org/packages/demo/guanlan-0.0.1.tar.gz"\n', encoding="utf-8")

    completed = subprocess.run(
        [str(script)],
        cwd=root,
        env={
            **os.environ,
            "GUANLAN_RELEASE_ALLOW_DIRTY": "1",
            "GUANLAN_RELEASE_REQUIRE_DISTRIBUTIONS": "1",
            "GUANLAN_HOMEBREW_FORMULA": str(formula),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode != 0
    assert "Homebrew formula" in completed.stderr


def test_quality_backend_fixtures_cli_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "quality", "backend-fixtures", "--format", "json"]):
        main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["summary"]["fail"] == 0
