# -*- coding: utf-8 -*-
"""Tests for local Agent Wiki sidecar generation."""

import json
from unittest.mock import patch

from guanlan import archive
from guanlan.archive_wiki import (
    build_archive_pack,
    build_archive_wiki,
    build_archive_wiki_context,
)


def test_archive_wiki_builds_static_html_and_markdown(tmp_path):
    db = tmp_path / "archive.db"
    output = tmp_path / "wiki"
    archive.add_document(
        "https://example.com/agent",
        "# AI Agent Wiki\n\nAgent Wiki 可以把资料组织成本地知识页面。",
        metadata={"topic_key": "AI Agent", "read_quality": {"score": 86}},
        db_path=db,
    )

    result = build_archive_wiki(output_dir=output, output_format="both", db_path=db)

    assert result["documents"] == 1
    assert result["core_documents"] == 1
    assert (output / "index.html").exists()
    assert (output / "index.md").exists()
    assert any("topics" in path for path in result["files"])
    assert "AI Agent" in (output / "index.md").read_text(encoding="utf-8")


def test_archive_wiki_context_is_prompt_ready(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document(
        "https://example.com/kv",
        "# KV Cache\n\nKIVI 和 KVQuant 都是 KV Cache 量化相关方法。",
        metadata={"topic_key": "KV Cache", "read_quality": {"score": 82}},
        db_path=db,
    )

    payload = build_archive_wiki_context("KV Cache 量化 KIVI", db_path=db)

    assert payload["records"]
    assert "Answering Rule" in payload["context"]
    assert "KIVI" in payload["context"]


def test_archive_pack_can_write_loader_jsonl(tmp_path):
    db = tmp_path / "archive.db"
    output = tmp_path / "pack.jsonl"
    archive.add_document(
        "https://example.com/agent",
        "# Agent 资料\n\n本地模型可以读取这段资料。",
        metadata={"topic_key": "agent", "read_quality": {"score": 90}},
        db_path=db,
    )

    result = build_archive_pack(
        "Agent 资料",
        output_path=output,
        output_format="langchain-jsonl",
        db_path=db,
    )

    assert result["path"] == str(output)
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["page_content"].startswith("# Agent 资料")
    assert row["metadata"]["tool"] == "guanlan"


def test_archive_wiki_cli_builds_summary(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    output = tmp_path / "wiki"
    archive.add_document("https://example.com/a", "# AI Agent\n正文", db_path=db)

    with patch(
        "sys.argv",
        ["guanlan", "archive", "wiki", "build", "--db", str(db), "--output", str(output)],
    ):
        main()

    captured = capsys.readouterr()
    assert "Guanlan Agent Wiki" in captured.out
    assert (output / "index.html").exists()
