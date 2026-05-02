# -*- coding: utf-8 -*-
"""Tests for Guanlan local archive."""

import json
from unittest.mock import patch

from guanlan import archive


def test_archive_add_document_and_search(tmp_path):
    db = tmp_path / "archive.db"

    record = archive.add_document(
        "example.com/policy",
        "# 人工智能政策\n\n这是一份关于人工智能政策和治理的材料。",
        db_path=db,
    )
    results = archive.search_documents("人工智能", db_path=db)

    assert record["status"] == "created"
    assert record["title"] == "人工智能政策"
    assert results[0]["title"] == "人工智能政策"
    assert "人工智能" in results[0]["excerpt"]
    assert results[0]["metadata"]["source_card"]["domain"] == "example.com"
    assert results[0]["metadata"]["read_quality"]["chars"] > 0


def test_archive_updates_existing_url(tmp_path):
    db = tmp_path / "archive.db"

    first = archive.add_document("https://example.com/a", "# 旧标题\n旧内容", db_path=db)
    second = archive.add_document("https://example.com/a", "# 新标题\n新内容", db_path=db)
    docs = archive.list_documents(db_path=db)

    assert first["status"] == "created"
    assert second["status"] == "updated"
    assert len(docs) == 1
    assert docs[0]["title"] == "新标题"


def test_archive_add_url_uses_reader(tmp_path, monkeypatch):
    from guanlan import webtools

    db = tmp_path / "archive.db"
    monkeypatch.setattr(webtools, "read_url", lambda url, **kwargs: "# 标题\n正文")

    record = archive.add_url("https://example.com/article", db_path=db)

    assert record["status"] == "created"
    assert record["title"] == "标题"


def test_archive_format_context(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document("https://example.com/a", "# 标题\n正文包含跨境电商。", db_path=db)

    context = archive.format_archive_context(archive.search_documents("跨境电商", db_path=db))

    assert "来源 | 标题 | 摘要 | 时间" in context
    assert "[标题](https://example.com/a)" in context


def test_archive_cli_search_outputs_json(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    archive.add_document("https://example.com/a", "# 标题\n正文包含政策。", db_path=db)

    with patch("sys.argv", ["guanlan", "archive", "search", "政策", "--db", str(db), "--json"]):
        main()
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert payload[0]["title"] == "标题"


def test_archive_cli_add_batch_respects_blocked_records(tmp_path, capsys, monkeypatch):
    from guanlan import webtools
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    urls = tmp_path / "urls.txt"
    urls.write_text("https://www.xiaohongshu.com/explore/1\nhttps://example.com/a\n", encoding="utf-8")
    monkeypatch.setattr(webtools, "read_url", lambda url, **kwargs: "# 标题\n正文")

    with patch("sys.argv", ["guanlan", "archive", "add", "batch", str(urls), "--db", str(db), "--format", "json"]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload[0]["status"] == "blocked"
    assert payload[1]["status"] == "created"


def test_archive_export_filters_and_adds_rag_fields(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document(
        "https://gov.cn/a",
        "# 政策原文\n正文",
        metadata={"source_type": "政府/部委", "topic_key": "policy"},
        db_path=db,
    )
    archive.add_document(
        "https://example.com/b",
        "# 普通文章\n正文",
        metadata={"source_type": "通用网页", "topic_key": "general"},
        db_path=db,
    )

    records = archive.export_documents(db_path=db, source_type="政府", topic="policy")

    assert len(records) == 1
    assert records[0]["domain"] == "gov.cn"
    assert records[0]["rag"]["source_type"] == "政府/部委"
    assert records[0]["rag"]["topic"] == "policy"


def test_archive_cli_export_rag_jsonl(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    archive.add_document(
        "https://gov.cn/a",
        "# 政策原文\n正文",
        metadata={"source_type": "政府/部委", "topic_key": "policy"},
        db_path=db,
    )

    with patch("sys.argv", ["guanlan", "archive", "export", "--format", "rag-jsonl", "--db", str(db)]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["id"].startswith("guanlan-")
    assert payload["source"] == "https://gov.cn/a"
    assert payload["text"].startswith("# 政策原文")


def test_archive_ingest_search_persists_representative_evidence(tmp_path, monkeypatch):
    db = tmp_path / "archive.db"

    monkeypatch.setattr(
        "guanlan.webtools.build_research_packet",
        lambda *args, **kwargs: {
            "result_count": 1,
            "preset": "general",
            "route_plan": {"primary_intents": ["policy"]},
            "selected_evidence": [
                {
                    "title": "政策原文",
                    "url": "https://gov.cn/a",
                    "snippet": "政策正文摘要",
                    "source_type": "政府/部委",
                    "topic_key": "policy",
                    "topic_role": "single",
                    "rank": 1,
                    "score": 9.0,
                }
            ],
            "readings": [{"url": "https://gov.cn/a", "status": "ok", "content": "# 政策原文\n全文"}],
        },
    )

    result = archive.ingest_search("人工智能 政策", db_path=db)
    records = archive.search_documents("全文", db_path=db)

    assert result["archived_count"] == 1
    assert records[0]["title"] == "政策原文"
    assert records[0]["metadata"]["source_type"] == "政府/部委"
    assert records[0]["metadata"]["route_plan"]["primary_intents"] == ["policy"]
    assert records[0]["metadata"]["read_quality"]["chars"] > 0
    assert records[0]["metadata"]["source_card"]["domain"] == "gov.cn"


def test_archive_cli_ingest_research_alias(tmp_path, capsys, monkeypatch):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    monkeypatch.setattr(
        "guanlan.webtools.build_research_packet",
        lambda *args, **kwargs: {
            "result_count": 1,
            "preset": "academic",
            "route_plan": {"primary_intents": ["academic"]},
            "selected_evidence": [
                {
                    "title": "EI 检索说明",
                    "url": "https://example.com/ei",
                    "snippet": "EI 检索要求",
                    "source_type": "学术/论文检索",
                }
            ],
            "readings": [],
        },
    )

    with patch("sys.argv", ["guanlan", "archive", "ingest-research", "EI检索", "--db", str(db)]):
        main()
    captured = capsys.readouterr()

    assert "已归档: 1" in captured.out
