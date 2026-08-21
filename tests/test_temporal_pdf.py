# -*- coding: utf-8 -*-
"""Snapshot delta and PDF/table evidence regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from guanlan import archive
from guanlan.pdf_evidence import ingest_pdf
from guanlan.temporal import build_claim_delta, build_snapshot_diff

FIXTURE = Path(__file__).parent / "fixtures" / "pdf_evidence_sample.pdf"


def test_snapshot_diff_and_claim_delta_are_conservative():
    before = {"snapshot_id": "a", "content": "# 指标\n\n成功率为 91%。"}
    after = {"snapshot_id": "b", "content": "# 指标\n\n成功率为 99.5%。\n\n新增说明。"}

    diff = build_snapshot_diff(before, after)
    delta = build_claim_delta(before, after)

    assert diff["changed"] is True
    assert diff["summary"]["change_blocks"] >= 1
    assert delta["summary"] == {"value_changed": 1}
    assert delta["deltas"][0]["before"]["value"] == "91%"
    assert delta["deltas"][0]["after"]["value"] == "99.5%"
    assert "refuting_evidence" not in delta["supported_change_types"]


def test_archive_update_persists_one_change_event_and_diff(tmp_path):
    db = tmp_path / "archive.db"
    first = archive.add_document("https://example.com/version", "版本成功率为 91%。", db_path=db)
    second = archive.add_document("https://example.com/version", "版本成功率为 99.5%。", db_path=db)
    archive.add_document("https://example.com/version", "版本成功率为 99.5%。", db_path=db)

    events = archive.list_change_events(identifier="https://example.com/version", db_path=db)
    comparison = archive.compare_snapshots(first["current_snapshot_id"], second["current_snapshot_id"], db_path=db)
    assert len(events) == 1
    assert events[0]["claim_delta"]["summary"] == {"value_changed": 1}
    assert comparison["snapshot_diff"]["changed"] is True


def test_pdf_ingest_addresses_pages_tables_and_parent_attachment(tmp_path):
    db = tmp_path / "archive.db"
    record = ingest_pdf(FIXTURE, source_url="https://example.com/report.pdf", db_path=db)
    passages = archive.list_snapshot_passages(record["current_snapshot_id"], db_path=db)

    assert record["page_count"] == 2
    assert record["table_count"] >= 1
    assert {item["page_number"] for item in passages if item["locator_type"] == "pdf_page"} == {1, 2}
    cells = [item for item in passages if item["locator_type"] == "table_cell"]
    assert any(item["text"] == "99.5%" for item in cells)
    assert all(item["table_id"] for item in cells)
    assert all(item["attachment_parent_id"] == record["attachment_parent_id"] for item in passages)
    snapshot = archive.inspect_snapshot(record["current_snapshot_id"], db_path=db)
    assert all(
        snapshot["content"][item["char_start"] : item["char_end"]] == item["text"]
        for item in passages
    )


def test_pdf_binary_update_creates_new_snapshot_even_if_visible_text_is_same(tmp_path):
    db = tmp_path / "archive.db"
    changed = tmp_path / "report.pdf"
    changed.write_bytes(FIXTURE.read_bytes())
    first = ingest_pdf(changed, source_url="https://example.com/report.pdf", db_path=db)
    changed.write_bytes(changed.read_bytes() + b"\n% changed-container-metadata\n")
    second = ingest_pdf(changed, source_url="https://example.com/report.pdf", db_path=db)

    assert second["status"] == "updated"
    assert first["current_snapshot_id"] != second["current_snapshot_id"]
    assert len(archive.list_document_snapshots("https://example.com/report.pdf", db_path=db)) == 2


def test_pdf_rejects_non_pdf_signature(tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(ValueError, match="PDF signature"):
        ingest_pdf(path, db_path=tmp_path / "archive.db")
