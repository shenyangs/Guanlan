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
