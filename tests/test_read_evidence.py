# -*- coding: utf-8 -*-
"""Tests for canonical representative read evidence."""

from __future__ import annotations

from guanlan.read_evidence import (
    READ_EVIDENCE_SCHEMA_VERSION,
    READ_PACK_SCHEMA_VERSION,
    build_read_evidence,
    build_representative_read_pack,
    build_structured_page,
    select_representative_read_candidates,
)


def test_build_structured_page_extracts_stable_fields():
    structured = build_structured_page(
        """Title: WPS AI 发布说明
作者: 观澜编辑部
2026年06月20日

# WPS AI 发布说明
正文内容。
- PPT Agent
- AI 表格
[官网](https://www.wps.cn/ai)
| 功能 | 状态 |
| PPT | 发布 |
""",
        url="https://www.wps.cn/ai",
    )

    assert structured["title"] == "WPS AI 发布说明"
    assert structured["author"] == "观澜编辑部"
    assert structured["published_at"] == "2026年06月20日"
    assert structured["language"] == "zh"
    assert structured["headings"][0]["text"] == "WPS AI 发布说明"
    assert structured["important_links"][0]["url"] == "https://www.wps.cn/ai"
    assert structured["tables"]["row_count"] >= 1


def test_build_read_evidence_normalizes_usable_and_weak_pages():
    packet = {
        "url": "https://example.com/news",
        "content": "# 标题\n这是一段足够干净的正文。",
        "quality_report": {"usable": True, "score": 82, "label": "clean"},
        "quality": {"score": 82, "chars": 120},
        "trace": {"selected_backend": "direct"},
    }

    evidence = build_read_evidence({"title": "新闻", "source": "媒体"}, read_packet=packet)

    assert evidence["schema_version"] == READ_EVIDENCE_SCHEMA_VERSION
    assert evidence["status"] == "ok"
    assert evidence["usable"] is True
    assert evidence["source"] == "媒体"
    assert evidence["selected_backend"] == "direct"
    assert evidence["structured"]["title"]

    weak = build_read_evidence({"url": "https://example.com"}, content="短正文", status="weak")
    assert weak["usable"] is False
    assert weak["status"] == "weak"


def test_representative_pack_prioritizes_strong_sources_and_summarizes(monkeypatch):
    items = [
        {"title": "下载站镜像", "url": "https://download.example.com/app", "source_type": "SEO 下载站"},
        {"title": "官方公告", "url": "https://brand.example.com/news", "evidence_role": "official"},
        {"title": "媒体报道", "url": "https://media.example.com/report", "source_type": "vertical media"},
    ]

    def fake_read(url: str, **_kwargs):
        return {
            "url": url,
            "content": f"# {url}\n这是代表页正文，信息足够完整，可以作为可引用证据。" * 3,
            "quality_report": {"usable": True, "score": 90, "label": "clean"},
            "quality": {"score": 90, "chars": 300},
            "trace": {"selected_backend": "direct"},
        }

    monkeypatch.setattr("guanlan.web.read.read_url_with_trace", fake_read)

    selected = select_representative_read_candidates(items, 2)
    assert "download" not in selected[0]["url"]

    pack = build_representative_read_pack(items, read_top=2, read_backend="direct")

    assert pack["schema_version"] == READ_PACK_SCHEMA_VERSION
    assert pack["summary"]["attempted"] == 2
    assert pack["summary"]["usable_count"] == 2
    assert pack["agent_followup"]["next_decision"] == "answer"
    assert all(row["usable"] for row in pack["readings"])


def test_representative_pack_repairs_when_all_reads_fail(monkeypatch):
    items = [
        {"title": "入口一", "url": "https://example.com/a"},
        {"title": "入口二", "url": "https://example.com/b"},
    ]

    def fake_read(_url: str, **_kwargs):
        raise RuntimeError("network timeout")

    monkeypatch.setattr("guanlan.web.read.read_url_with_trace", fake_read)

    pack = build_representative_read_pack(items, read_top=1)

    assert pack["summary"]["error_count"] == 1
    assert pack["usable_count"] == 0
    assert pack["agent_followup"]["next_decision"] == "repair"
    assert pack["next_read_commands"]
