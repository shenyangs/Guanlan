# -*- coding: utf-8 -*-
"""Safe local PDF ingestion with page and table-cell evidence locators."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from guanlan.evidence_kernel import stable_id

PDF_EVIDENCE_SCHEMA_VERSION = "pdf_evidence_v1"
DEFAULT_MAX_PDF_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_PDF_PAGES = 200


def ingest_pdf(
    path: str | Path,
    *,
    source_url: str = "",
    title: str = "",
    parent_attachment_id: str = "",
    max_bytes: int = DEFAULT_MAX_PDF_BYTES,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Extract a user-selected local PDF and persist immutable evidence."""

    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise ValueError(f"PDF file not found: {path}")
    size = file_path.stat().st_size
    if size <= 0 or size > max(int(max_bytes), 1):
        raise ValueError(f"PDF size outside allowed range: {size} bytes")
    payload = file_path.read_bytes()
    if not payload.startswith(b"%PDF-"):
        raise ValueError("file does not have a PDF signature")

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("PDF support requires pypdf; reinstall Guanlan with PDF dependencies") from exc
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("PDF table support requires pdfplumber; reinstall Guanlan with PDF dependencies") from exc

    reader = PdfReader(file_path, strict=False)
    if reader.is_encrypted and reader.decrypt("") == 0:
        raise ValueError("encrypted PDF requires a password and is not ingested")
    page_count = len(reader.pages)
    if page_count > max(int(max_pages), 1):
        raise ValueError(f"PDF page count exceeds limit: {page_count}")

    binary_hash = hashlib.sha256(payload).hexdigest()
    attachment_id = str(parent_attachment_id or stable_id("att", source_url or file_path.as_uri()))
    page_texts = [str(page.extract_text() or "").strip() for page in reader.pages]
    tables: list[dict[str, Any]] = []
    with pdfplumber.open(file_path) as document:
        for page_number, page in enumerate(document.pages, start=1):
            for table_index, rows in enumerate(page.extract_tables() or [], start=1):
                table_id = stable_id("tbl", binary_hash, page_number, table_index)
                normalized_rows = [
                    [str(cell or "").strip() for cell in row]
                    for row in rows
                    if isinstance(row, list)
                ]
                if normalized_rows:
                    tables.append(
                        {
                            "table_id": table_id,
                            "page_number": page_number,
                            "table_index": table_index,
                            "rows": normalized_rows,
                        }
                    )

    display_title = str(title or reader.metadata.title or file_path.stem).strip()
    markdown_parts = [f"# {display_title}", "", f"PDF-SHA256: `{binary_hash}`"]
    passages: list[dict[str, Any]] = []
    cursor = len("\n".join(markdown_parts)) + 2
    for page_number, text in enumerate(page_texts, start=1):
        page_body = text or "[本页未提取到文本]"
        markdown_parts.extend(["", f"## 第 {page_number} 页", "", page_body])
        passages.append(
            {
                "locator_type": "pdf_page",
                "page_number": page_number,
                "heading_path": [display_title, f"第 {page_number} 页"],
                "char_start": cursor,
                "char_end": cursor + len(page_body),
                "text": page_body,
                "attachment_parent_id": attachment_id,
            }
        )
        cursor += len(page_body) + len(f"\n\n## 第 {page_number} 页\n\n")
    for table in tables:
        markdown_parts.extend(["", f"### 表格 {table['table_index']}（第 {table['page_number']} 页）"])
        for row_index, row in enumerate(table["rows"]):
            markdown_parts.append(" | ".join(row))
            for column_index, value in enumerate(row):
                if not value:
                    continue
                passages.append(
                    {
                        "locator_type": "table_cell",
                        "page_number": table["page_number"],
                        "table_id": table["table_id"],
                        "row_index": row_index,
                        "column_index": column_index,
                        "heading_path": [display_title, f"第 {table['page_number']} 页", f"表格 {table['table_index']}"],
                        "char_start": 0,
                        "char_end": len(value),
                        "text": value,
                        "attachment_parent_id": attachment_id,
                    }
                )
    content = "\n".join(markdown_parts).strip()
    page_cursor = 0
    for passage in passages:
        text = str(passage["text"])
        if passage["locator_type"] == "pdf_page":
            offset = content.find(text, page_cursor)
            if offset >= 0:
                passage["char_start"] = offset
                passage["char_end"] = offset + len(text)
                page_cursor = passage["char_end"]
            continue
        table_marker = f"### 表格 {next(table['table_index'] for table in tables if table['table_id'] == passage['table_id'])}"
        table_start = max(content.find(table_marker), 0)
        offset = content.find(text, table_start)
        if offset >= 0:
            passage["char_start"] = offset
            passage["char_end"] = offset + len(text)
    archive_url = str(source_url or file_path.as_uri())
    metadata = {
        "source_type": "pdf_attachment",
        "mime_type": "application/pdf",
        "binary_sha256": binary_hash,
        "file_size": size,
        "page_count": page_count,
        "table_count": len(tables),
        "attachment_parent_id": attachment_id,
        "local_file_name": file_path.name,
        "security_boundary": "explicit_local_file; no scripts; no external links fetched; encrypted PDFs rejected",
    }
    from guanlan.archive import add_document, replace_snapshot_passages

    record = add_document(archive_url, content, title=display_title, metadata=metadata, db_path=db_path)
    passage_count = replace_snapshot_passages(record["current_snapshot_id"], passages, db_path=db_path)
    return {
        "schema_version": PDF_EVIDENCE_SCHEMA_VERSION,
        **record,
        "binary_sha256": binary_hash,
        "file_size": size,
        "page_count": page_count,
        "table_count": len(tables),
        "cell_count": sum(len(row) for table in tables for row in table["rows"]),
        "attachment_parent_id": attachment_id,
        "passage_count": passage_count,
        "snapshot_resource_uri": f"guanlan://snapshots/{record['current_snapshot_id']}",
        "boundary": metadata["security_boundary"],
    }
