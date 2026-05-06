# -*- coding: utf-8 -*-
"""Tests for Guanlan's agent timeout unit contract."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_memory_surfaces_warn_about_timeout_units():
    docs = [
        ROOT / "AGENTS.md",
        ROOT / "docs" / "agent-playbook.md",
        ROOT / "docs" / "agent-usage.md",
        ROOT / "docs" / "full-guide.md",
        ROOT / "guanlan" / "skill" / "SKILL.md",
    ]

    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        assert "timeout_ms" in text
        assert "120000" in text
        assert "300000" in text
        assert "裸数字" in text or "bare number" in text
