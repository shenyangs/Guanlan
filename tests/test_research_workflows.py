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


def test_timeline_report_keeps_explicit_year_window_as_main_events(monkeypatch):
    def fake_packet(query, **_kwargs):
        return {
            **_packet(query),
            "selected_evidence": [
                {
                    "title": "具身智能 2024年3月1日 产业进展",
                    "url": "https://example.com/2024",
                    "snippet": "具身智能公司发布新产品。",
                    "source_type": "商业/产业媒体",
                    "evidence_role": "fresh_news",
                },
                {
                    "title": "具身智能 2022年1月1日 早期融资",
                    "url": "https://example.com/2022",
                    "snippet": "具身智能早期历史材料。",
                    "source_type": "商业/产业媒体",
                    "evidence_role": "industry_report",
                },
                {
                    "title": "无关公司 2024年4月1日 动态",
                    "url": "https://example.com/noise",
                    "snippet": "无关主题。",
                    "source_type": "通用网页",
                    "evidence_role": "open_web_context",
                },
            ],
            "results": [],
            "readings": [],
        }

    monkeypatch.setattr(research_workflows, "build_research_packet", fake_packet)

    report = research_workflows.build_timeline_report("具身智能 2024", max_events=5)

    assert [item["date"] for item in report["events"]] == ["2024-03-01"]
    assert report["background_events"][0]["date"] == "2022-01-01"
    assert report["low_relevance_events"][0]["url"] == "https://example.com/noise"
    assert report["timeline_quality"]["status"] == "ok"


def test_timeline_report_recent_query_can_fallback_to_background_events(monkeypatch):
    def fake_packet(query, **_kwargs):
        return {
            **_packet(query),
            "selected_evidence": [
                {
                    "title": "具身智能 2026年3月1日 产品更新",
                    "url": "https://example.com/recent-1",
                    "snippet": "具身智能产品进入新阶段。",
                    "source_type": "商业/产业媒体",
                    "evidence_role": "fresh_news",
                },
                {
                    "title": "具身智能 2026年2月15日 行业动向",
                    "url": "https://example.com/recent-2",
                    "snippet": "具身智能行业继续推进。",
                    "source_type": "商业/产业媒体",
                    "evidence_role": "industry_report",
                },
            ],
            "results": [],
            "readings": [],
        }

    monkeypatch.setattr(research_workflows, "build_research_packet", fake_packet)

    report = research_workflows.build_timeline_report("具身智能 最新进展", max_events=2)

    assert [item["date"] for item in report["events"]] == ["2026-03-01", "2026-02-15"]
    assert report["background_events"] == []
    assert report["timeline_quality"]["status"] == "warn"
    assert report["timeline_quality"]["in_window_count"] == 0
    assert report["timeline_quality"]["fallback_count"] == 2
    assert "弱兜底" in report["timeline_quality"]["message"]


def test_dossier_report_groups_evidence_sections(monkeypatch):
    monkeypatch.setattr(research_workflows, "build_research_packet", lambda query, **_kwargs: _packet(query))

    report = research_workflows.build_dossier_report("某公司", focus="业务 风险")

    section_ids = {section["id"] for section in report["sections"]}
    assert {"official", "media", "sample", "selected"} <= section_ids
    assert report["open_questions"]
    assert "观澜研究档案" in research_workflows.format_dossier_markdown(report)


def test_yinshen_report_expands_keyword_into_angles(monkeypatch):
    calls = []

    def fake_build(query, **kwargs):
        calls.append((query, kwargs))
        return _packet(query)

    monkeypatch.setattr(research_workflows, "build_research_packet", fake_build)

    report = research_workflows.build_yinshen_report("AI写代码", angles=5, limit=80, angle_read_top=0)
    rendered = research_workflows.format_yinshen_markdown(report)

    assert report["mode"] == "yinshen"
    assert report["keyword"] == "AI写代码"
    assert len(report["angles"]) == 5
    assert len(calls) == 6
    assert calls[0][0] == "AI写代码"
    assert all("deep_query" in angle for angle in report["angles"])
    assert "观澜引申" in rendered
    assert "引申角度总览" in rendered
    assert "没有搜到" not in rendered


def test_yinshen_plan_only_skips_angle_deep_search(monkeypatch):
    calls = []

    def fake_build(query, **kwargs):
        calls.append((query, kwargs))
        return _packet(query)

    monkeypatch.setattr(research_workflows, "build_research_packet", fake_build)

    report = research_workflows.build_yinshen_report("短剧出海", angles=3, plan_only=True)

    assert report["plan_only"] is True
    assert len(calls) == 1
    assert len(report["angles"]) == 3
    assert all(angle["deep_query"].startswith("短剧出海") for angle in report["angles"])


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


def test_compare_report_flags_single_source_dominance(monkeypatch):
    def fake_packet(query, **_kwargs):
        evidence = [
            {
                "title": f"{query} 用户讨论 {idx}",
                "url": f"https://www.zhihu.com/question/{idx}",
                "domain": "zhihu.com",
                "snippet": "用户样本。",
                "source_type": "社交/内容平台",
                "evidence_role": "user_sample",
                "score": 6.0,
            }
            for idx in range(5)
        ]
        return {
            **_packet(query),
            "selected_evidence": evidence,
            "source_mix": {"社交/内容平台": 5},
            "source_diagnostics": {"source_type_count": 1, "domain_count": 1, "warnings": []},
            "results": [],
            "readings": [],
        }

    monkeypatch.setattr(research_workflows, "build_research_packet", fake_packet)

    report = research_workflows.build_compare_report(["产品A", "产品B"], focus="口碑 风险", limit=80)

    assert report["source_diversity_guard"]["status"] == "warn"
    assert report["subject_reports"][0]["source_diversity_guard"]["status"] == "warn"
    assert any("company_primary" in item for item in report["suggested_next"])
    assert "信源护栏" in research_workflows.format_compare_markdown(report)


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


def test_cli_yinshen_outputs_json(capsys, monkeypatch):
    monkeypatch.setattr(
        "guanlan.research_workflows.build_yinshen_report",
        lambda keyword, **_kwargs: {"mode": "yinshen", "keyword": keyword, "angles": [], "priority_shortlist": []},
    )

    with patch("sys.argv", ["guanlan", "yinshen", "AI写代码", "--json"]):
        main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "yinshen"
    assert payload["keyword"] == "AI写代码"
