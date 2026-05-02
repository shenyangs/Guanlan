# -*- coding: utf-8 -*-
"""Contract documentation guards for agent-facing outputs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_contract_documents_core_surfaces_and_fields():
    text = (ROOT / "docs" / "contract.md").read_text(encoding="utf-8")

    for heading in [
        "Search Result Contract",
        "Research Packet Contract",
        "Archive Contract",
        "Hotnews And Feeds Contract",
        "MCP And HTTP Contract",
    ]:
        assert heading in text
    for field in [
        "source_card",
        "evidence_role",
        "risk_tags",
        "route_plan",
        "query_strategy",
        "ingest_audit",
        "search_trace",
        "feed_status",
        "GUANLAN_SERVE_TOKEN",
    ]:
        assert field in text


def test_readme_links_agent_contract():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_zh = (ROOT / "docs" / "README_zh.md").read_text(encoding="utf-8")

    assert "docs/contract.md" in readme
    assert "contract.md" in docs_zh
