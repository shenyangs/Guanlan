# -*- coding: utf-8 -*-
"""Tests for high-level Guanlan research workflows."""

import json
from unittest.mock import patch

from guanlan import research_workflows
from guanlan.cli import main


def _packet(query: str) -> dict:
    return {
        "query": query,
        "result_count": 3,
        "source_mix": {"政府/部委": 1, "社交/内容平台": 1, "商业/产业媒体": 1},
        "source_diagnostics": {"source_type_count": 3, "domain_count": 3, "freshness_avg": 0.7},
        "route_plan": {"primary_intents": ["policy"], "evidence_roles": ["official_primary"]},
        "read_quality_summary": {"count": 1, "usable_count": 1, "avg_score": 82},
        "evidence_audit": {"warnings": ["核验发布日期"]},
        "advisor": {"briefing": "基于公开证据谨慎整理"},
        "selected_evidence": [
            {
                "title": f"2026年5月2日 {query} 官方发布",
                "url": "https://www.gov.cn/a",
                "domain": "gov.cn",
                "snippet": "官方原文与发布时间",
                "source_type": "政府/部委",
                "evidence_role": "official_primary",
                "score": 9.5,
            },
            {
                "title": f"{query} 用户反馈",
                "url": "https://www.zhihu.com/question/1",
                "domain": "zhihu.com",
                "snippet": "公开用户样本",
                "source_type": "社交/内容平台",
                "evidence_role": "user_sample",
                "score": 7.1,
            },
            {
                "title": f"{query} 产业观察",
                "url": "https://www.ebrun.com/a",
                "domain": "ebrun.com",
                "snippet": "行业案例",
                "source_type": "电商/零售垂类",
                "evidence_role": "industry_report",
                "score": 6.4,
            },
        ],
        "results": [],
        "readings": [],
    }


def test_compare_report_keeps_public_payload_compact(monkeypatch):
    calls = []

    def fake_build(query, **kwargs):
        calls.append((query, kwargs))
        return _packet(query)

    monkeypatch.setattr(research_workflows, "build_research_packet", fake_build)

    report = research_workflows.build_compare_report(["产品A", "产品B"], focus="价格 口碑", limit=80)

    assert report["mode"] == "compare"
    assert len(report["comparison_table"]) >= 3
    assert "packet" not in report["subject_reports"][0]
    assert calls[0][1]["limit"] == 80
    assert "产品A" in research_workflows.format_compare_markdown(report)


def test_timeline_report_extracts_dated_events(monkeypatch):
    monkeypatch.setattr(research_workflows, "build_research_packet", lambda query, **_kwargs: _packet(query))

    report = research_workflows.build_timeline_report("低空经济 最新政策", max_events=5)

    assert report["mode"] == "timeline"
    assert report["events"][0]["date"] == "2026-05-02"
    assert "观澜时间线" in research_workflows.format_timeline_markdown(report)


def test_dossier_report_groups_evidence_sections(monkeypatch):
    monkeypatch.setattr(research_workflows, "build_research_packet", lambda query, **_kwargs: _packet(query))

    report = research_workflows.build_dossier_report("某公司", focus="业务 风险")

    section_ids = {section["id"] for section in report["sections"]}
    assert {"official", "media", "sample", "selected"} <= section_ids
    assert report["open_questions"]
    assert "观澜研究档案" in research_workflows.format_dossier_markdown(report)


def test_cli_compare_outputs_json(capsys, monkeypatch):
    monkeypatch.setattr(
        "guanlan.research_workflows.build_compare_report",
        lambda subjects, **_kwargs: {"mode": "compare", "subjects": subjects, "comparison_table": []},
    )

    with patch("sys.argv", ["guanlan", "compare", "A", "B", "--json"]):
        main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "compare"
    assert payload["subjects"] == ["A", "B"]


def test_cli_timeline_and_dossier_markdown(capsys, monkeypatch):
    monkeypatch.setattr(
        "guanlan.research_workflows.build_timeline_report",
        lambda query, **_kwargs: {"mode": "timeline", "query": query, "events": [], "boundary": "边界"},
    )
    monkeypatch.setattr(
        "guanlan.research_workflows.build_dossier_report",
        lambda entity, **_kwargs: {
            "mode": "dossier",
            "entity": entity,
            "query": entity,
            "sections": [],
            "suggested_next": [],
            "boundary": "边界",
        },
    )

    with patch("sys.argv", ["guanlan", "timeline", "AI 眼镜"]):
        main()
    assert "观澜时间线" in capsys.readouterr().out

    with patch("sys.argv", ["guanlan", "dossier", "某公司"]):
        main()
    assert "观澜研究档案" in capsys.readouterr().out
