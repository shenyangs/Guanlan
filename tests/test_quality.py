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
