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
from guanlan.read_outcome import READ_OUTCOME_SCHEMA_VERSION, build_read_outcome


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


def test_build_read_evidence_attaches_backend_and_extract_contract():
    packet = {
        "url": "https://example.com/news",
        "content": "# 标题\n这是一段足够干净的正文。" * 20,
        "quality_report": {"usable": True, "score": 88, "label": "clean"},
        "quality": {"score": 88, "chars": 500},
        "trace": {"selected_backend": "jina", "backend": "auto", "extract": "article"},
    }

    evidence = build_read_evidence({"title": "新闻"}, read_packet=packet)

    assert evidence["backend_capability"]["schema_version"] == "web_backend_capability_v1"
    assert evidence["backend_capability"]["trust_model"] == "public_page_extraction"
    assert evidence["extract_contract"]["schema_version"] == "read_extract_contract_v1"
    assert evidence["extract_contract"]["status"] == "usable"
    assert evidence["extract_contract"]["can_cite_as_page_body"] is True
    assert evidence["read_outcome"]["state"] == "page_body"
    assert evidence["read_outcome"]["citation_allowed"] is True


def test_build_read_evidence_marks_search_fallback_as_context_only():
    packet = {
        "url": "https://example.com/news",
        "content": "# 观澜阅读兜底\n搜索候选摘要",
        "quality_report": {"usable": False, "score": 40, "label": "fallback", "fallback": True},
        "quality": {"score": 40, "chars": 80, "fallback": True},
        "trace": {"selected_backend": "search_fallback", "backend": "auto"},
    }

    evidence = build_read_evidence({"title": "新闻"}, read_packet=packet)

    assert evidence["backend_capability"]["trust_model"] == "search_context_only"
    assert evidence["extract_contract"]["status"] == "context_only"
    assert evidence["extract_contract"]["can_cite_as_page_body"] is False
    assert "不是目标页正文" in evidence["boundary"]
    assert evidence["read_outcome"]["state"] == "context_only"
    assert evidence["read_outcome"]["citation_allowed"] is False


def test_read_outcome_distinguishes_weak_and_unavailable_pages():
    weak = build_read_outcome(
        {
            "content": "只有一小段可读文字",
            "quality_report": {"usable": False, "label": "weak"},
            "extract_contract": {"status": "weak", "selected_backend": "direct"},
        }
    )
    unavailable = build_read_outcome(
        {
            "content": "",
            "quality_report": {"usable": False, "label": "blocked"},
            "extract_contract": {"status": "unavailable", "selected_backend": "direct"},
        }
    )

    assert weak["schema_version"] == READ_OUTCOME_SCHEMA_VERSION
    assert weak["state"] == "weak_body"
    assert unavailable["state"] == "unavailable"


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
    assert pack["summary"]["context_only_count"] == 0
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
    assert "network timeout" not in pack["readings"][0]["error"]
    assert "network_timeout" in pack["readings"][0]["error"]
    assert pack["agent_followup"]["next_decision"] == "repair"
    assert pack["next_read_commands"][0] == "guanlan diagnose page https://example.com/a --json"
    assert "guanlan read https://example.com/a --quality-report --backend direct" in pack["next_read_commands"]
