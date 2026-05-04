# -*- coding: utf-8 -*-
"""Local Agent Wiki and archive-to-context helpers.

The wiki layer is deliberately a sidecar over the archive. It reads local
records, writes static Markdown/HTML, and never triggers web search or reads.
"""

from __future__ import annotations

import re
import time
from html import escape
from pathlib import Path
from typing import Any

from guanlan.archive import (
    export_documents,
    format_archive_export_jsonl,
    inspect_document,
)

DEFAULT_WIKI_LIMIT = 200
DEFAULT_CONTEXT_CHARS = 1200


def build_archive_wiki(
    *,
    output_dir: str | Path,
    topic: str = "",
    output_format: str = "html",
    limit: int = DEFAULT_WIKI_LIMIT,
    min_quality: int = 60,
    include_candidates: bool = True,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a static local Agent Wiki from archived documents."""
    records = _select_records(topic=topic, limit=limit, db_path=db_path)
    enriched = [_enrich_wiki_record(record, min_quality=min_quality) for record in records]
    if not include_candidates:
        enriched = [record for record in enriched if record["wiki_status"] == "core"]

    output = Path(output_dir).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    topic_groups = _group_by_topic(enriched)
    files: list[str] = []

    formats = {"markdown", "html"} if output_format == "both" else {output_format}
    if "markdown" in formats:
        index = _render_wiki_markdown(enriched, topic_groups, topic=topic)
        path = output / "index.md"
        path.write_text(index, encoding="utf-8")
        files.append(str(path))
        topics_dir = output / "topics"
        topics_dir.mkdir(exist_ok=True)
        for topic_name, topic_records in topic_groups.items():
            topic_path = topics_dir / f"{_slug(topic_name)}.md"
            topic_path.write_text(_render_topic_markdown(topic_name, topic_records), encoding="utf-8")
            files.append(str(topic_path))
    if "html" in formats:
        index = _render_wiki_html(enriched, topic_groups, topic=topic)
        path = output / "index.html"
        path.write_text(index, encoding="utf-8")
        files.append(str(path))
        topics_dir = output / "topics"
        topics_dir.mkdir(exist_ok=True)
        for topic_name, topic_records in topic_groups.items():
            topic_path = topics_dir / f"{_slug(topic_name)}.html"
            topic_path.write_text(_render_topic_html(topic_name, topic_records), encoding="utf-8")
            files.append(str(topic_path))

    return {
        "status": "ok",
        "output": str(output.resolve()),
        "format": output_format,
        "topic": topic,
        "documents": len(enriched),
        "core_documents": sum(1 for record in enriched if record["wiki_status"] == "core"),
        "candidate_documents": sum(1 for record in enriched if record["wiki_status"] != "core"),
        "topics": len(topic_groups),
        "files": files,
        "boundary": "local-static-wiki; archive-derived; not whole-web knowledge",
    }


def build_archive_wiki_context(
    query: str,
    *,
    limit: int = 20,
    min_quality: int = 0,
    max_chars: int = DEFAULT_CONTEXT_CHARS,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build an evidence-bound local wiki context for an Agent or local model."""
    if not query.strip():
        raise ValueError("query is required")
    from guanlan.archive import search_documents

    hits = search_documents(query, limit=max(limit, 1), trace=True, db_path=db_path)
    records = []
    for hit in hits:
        full = inspect_document(str(hit["id"]), db_path=db_path)
        enriched = _enrich_wiki_record(full, min_quality=min_quality)
        if min_quality and enriched["quality_score"] is not None and enriched["quality_score"] < min_quality:
            enriched["wiki_status"] = "candidate"
        content = str(full.get("content") or "")
        enriched["content_excerpt"] = _compact(content, max_chars)
        enriched["search_trace"] = hit.get("search_trace", {})
        records.append(enriched)
    context = format_archive_wiki_context({"query": query, "records": records})
    return {
        "query": query,
        "records": records,
        "context": context,
        "boundary": "local-archive-context; semantic=not-vector",
    }


def format_archive_wiki_context(payload: dict[str, Any]) -> str:
    """Render local archive context as prompt-ready Markdown."""
    query = str(payload.get("query") or "")
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    lines = [
        f"# Guanlan Local Archive Context / {query}",
        "",
        "Use this as a local evidence pack. It only reflects documents already stored in the Guanlan archive.",
        "Do not treat missing results as proof that the wider web has no evidence.",
        "",
        "来源 | 状态 | 标题 | 摘要",
        "--- | --- | --- | ---",
    ]
    if not records:
        lines.append("无结果 | - | - | 本地 archive 未命中；可先运行 `guanlan archive list` 或联网补搜。")
        return "\n".join(lines)
    for record in records:
        title = _pipe_safe(str(record.get("title", "")))
        url = str(record.get("url", ""))
        domain = _pipe_safe(str(record.get("domain", "")))
        status = _pipe_safe(str(record.get("wiki_status", "")))
        excerpt = _pipe_safe(str(record.get("excerpt") or record.get("content_excerpt") or ""))[:220]
        lines.append(f"{domain} | {status} | [{title}]({url}) | {excerpt}")
    lines.extend(["", "## Evidence Notes"])
    for idx, record in enumerate(records, start=1):
        lines.append(f"### [{idx}] {record.get('title', '')}")
        lines.append(f"- URL: {record.get('url', '')}")
        lines.append(f"- Domain: {record.get('domain', '')}")
        lines.append(f"- Wiki status: {record.get('wiki_status', '')}")
        if record.get("quality_score") is not None:
            lines.append(f"- Read quality: {record.get('quality_score')}")
        matched = ((record.get("search_trace") or {}).get("matched_terms") or [])
        if matched:
            lines.append(f"- Matched terms: {', '.join(matched)}")
        excerpt = str(record.get("content_excerpt") or record.get("excerpt") or "").strip()
        if excerpt:
            lines.append("")
            lines.append(excerpt)
        lines.append("")
    lines.extend(
        [
            "## Answering Rule",
            "- Prefer archive evidence above memory.",
            "- If evidence is thin or candidate-only, say so before giving conclusions.",
            "- For factual claims, cite title/domain or URL in the answer.",
        ]
    )
    return "\n".join(lines).rstrip()


def build_archive_pack(
    query: str,
    *,
    output_path: str | Path | None = None,
    output_format: str = "markdown",
    limit: int = 20,
    max_chars: int = DEFAULT_CONTEXT_CHARS,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Package local archive matches as Markdown or loader-friendly JSONL."""
    context_payload = build_archive_wiki_context(
        query,
        limit=limit,
        max_chars=max_chars,
        db_path=db_path,
    )
    records = context_payload["records"]
    if output_format == "markdown":
        content = context_payload["context"]
    elif output_format in {"jsonl", "rag-jsonl", "llamaindex-jsonl", "langchain-jsonl", "openwebui-jsonl"}:
        content = format_archive_export_jsonl(records, profile=output_format)
    else:
        raise ValueError(f"unsupported archive pack format: {output_format}")

    path_value = ""
    if output_path:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path_value = str(path.resolve())
    return {
        "query": query,
        "format": output_format,
        "records": len(records),
        "content": content,
        "path": path_value,
        "boundary": context_payload["boundary"],
    }


def format_wiki_build_summary(result: dict[str, Any]) -> str:
    """Render wiki build result as Markdown."""
    lines = [
        "# Guanlan Agent Wiki",
        "",
        f"- 状态: {result.get('status', '')}",
        f"- 输出目录: {result.get('output', '')}",
        f"- 格式: {result.get('format', '')}",
        f"- 文档数: {result.get('documents', 0)}",
        f"- Core / Candidate: {result.get('core_documents', 0)} / {result.get('candidate_documents', 0)}",
        f"- Topic 数: {result.get('topics', 0)}",
        f"- 边界: {result.get('boundary', '')}",
        "",
        "## Files",
    ]
    lines.extend(f"- {path}" for path in result.get("files", []))
    lines.extend(
        [
            "",
            "## Agent 提示",
            "- 这个 Wiki 是 archive 的组织层，只代表本地已归档资料，不代表全网知识。",
            "- 回答用户时优先引用页面来源；低质量或 candidate 材料需要提醒用户继续核验。",
            "- 如果用户要给本地模型/RAG 用，下一步可运行 `guanlan archive wiki context \"问题\"` 或 `guanlan archive pack \"问题\" --format langchain-jsonl`。",
        ]
    )
    return "\n".join(lines)


def _select_records(
    *,
    topic: str,
    limit: int,
    db_path: str | Path | None,
) -> list[dict[str, Any]]:
    if topic.strip():
        from guanlan.archive import search_documents

        hits = search_documents(topic, limit=max(limit, 1), db_path=db_path)
        ids = {int(hit["id"]) for hit in hits}
        return [record for record in export_documents(db_path=db_path) if int(record.get("id", -1)) in ids]
    return export_documents(db_path=db_path)[: max(limit, 1)]


def _enrich_wiki_record(record: dict[str, Any], *, min_quality: int) -> dict[str, Any]:
    enriched = dict(record)
    metadata = enriched.get("metadata") if isinstance(enriched.get("metadata"), dict) else {}
    quality = metadata.get("read_quality") if isinstance(metadata.get("read_quality"), dict) else {}
    score = _quality_score(quality)
    content = str(enriched.get("content") or "")
    if not content.strip():
        status = "candidate"
        reasons = ["empty_content"]
    elif score is not None and score < min_quality:
        status = "candidate"
        reasons = ["low_read_quality"]
    else:
        status = "core"
        reasons = []
    enriched["quality_score"] = score
    enriched["wiki_status"] = status
    enriched["wiki_reasons"] = reasons
    enriched["wiki_topic"] = _topic_label(enriched)
    enriched["updated_label"] = _format_time(float(enriched.get("updated_at", 0) or 0))
    return enriched


def _group_by_topic(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        topic = str(record.get("wiki_topic") or "general")
        groups.setdefault(topic, []).append(record)
    return dict(sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])))


def _topic_label(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    for key in ("topic_key", "source_type", "evidence_role"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return str(record.get("domain") or "general")


def _render_wiki_markdown(
    records: list[dict[str, Any]],
    groups: dict[str, list[dict[str, Any]]],
    *,
    topic: str,
) -> str:
    lines = [
        "# Guanlan Agent Wiki",
        "",
        f"Scope: {'topic / ' + topic if topic else 'all local archive documents'}",
        "",
        "This wiki is generated from the local Guanlan archive. It is not a whole-web knowledge base.",
        "",
        f"- Documents: {len(records)}",
        f"- Core: {sum(1 for record in records if record['wiki_status'] == 'core')}",
        f"- Candidate: {sum(1 for record in records if record['wiki_status'] != 'core')}",
        "",
        "## Topics",
    ]
    for topic_name, topic_records in groups.items():
        lines.append(f"- [{topic_name}](topics/{_slug(topic_name)}.md) ({len(topic_records)})")
    lines.extend(["", "## Recent Documents"])
    for record in records[:30]:
        lines.append(f"- [{record.get('title', '')}]({record.get('url', '')}) / {record.get('wiki_status')} / {record.get('domain', '')}")
    return "\n".join(lines)


def _render_topic_markdown(topic_name: str, records: list[dict[str, Any]]) -> str:
    lines = [
        f"# {topic_name}",
        "",
        "Generated from local Guanlan archive. Core items are more suitable for reuse; candidate items need verification.",
        "",
    ]
    for record in records:
        lines.append(f"## {record.get('title', '')}")
        lines.append(f"- URL: {record.get('url', '')}")
        lines.append(f"- Domain: {record.get('domain', '')}")
        lines.append(f"- Status: {record.get('wiki_status', '')}")
        if record.get("quality_score") is not None:
            lines.append(f"- Quality: {record.get('quality_score')}")
        lines.append("")
        lines.append(str(record.get("excerpt", "")))
        lines.append("")
    return "\n".join(lines)


def _render_wiki_html(
    records: list[dict[str, Any]],
    groups: dict[str, list[dict[str, Any]]],
    *,
    topic: str,
) -> str:
    topic_rows = "\n".join(
        f'<a class="topic" href="topics/{escape(_slug(name))}.html"><span>{escape(name)}</span><b>{len(items)}</b></a>'
        for name, items in groups.items()
    )
    cards = "\n".join(_record_card(record) for record in records[:60])
    return _html_page(
        "Guanlan Agent Wiki",
        f"Local archive wiki · {escape(topic or 'all topics')}",
        f"""
        <section class="metrics">
          <div><b>{len(records)}</b><span>Documents</span></div>
          <div><b>{sum(1 for record in records if record['wiki_status'] == 'core')}</b><span>Core</span></div>
          <div><b>{sum(1 for record in records if record['wiki_status'] != 'core')}</b><span>Candidate</span></div>
          <div><b>{len(groups)}</b><span>Topics</span></div>
        </section>
        <section><h2>Topics</h2><div class="topics">{topic_rows}</div></section>
        <section><h2>Recent Evidence</h2><div class="cards">{cards}</div></section>
        """,
    )


def _render_topic_html(topic_name: str, records: list[dict[str, Any]]) -> str:
    cards = "\n".join(_record_card(record) for record in records)
    return _html_page(
        topic_name,
        "Generated from local Guanlan archive. Candidate items need verification.",
        f'<section><h2>Evidence</h2><div class="cards">{cards}</div></section>',
    )


def _record_card(record: dict[str, Any]) -> str:
    status = str(record.get("wiki_status", "candidate"))
    quality = "" if record.get("quality_score") is None else f" · q={record.get('quality_score')}"
    return f"""
    <article class="card {escape(status)}">
      <div class="status">{escape(status)}{escape(quality)}</div>
      <h3><a href="{escape(str(record.get('url', '')), quote=True)}">{escape(str(record.get('title', '')))}</a></h3>
      <p>{escape(str(record.get('excerpt', ''))[:280])}</p>
      <footer>{escape(str(record.get('domain', '')))} · {escape(str(record.get('updated_label', '')))}</footer>
    </article>
    """


def _html_page(title: str, subtitle: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    body {{ margin:0; background:#0a0b10; color:#eef1e8; font-family:"Avenir Next","PingFang SC",sans-serif; }}
    main {{ width:min(1180px, calc(100vw - 36px)); margin:0 auto; padding:42px 0 70px; }}
    header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-end; border-bottom:1px solid rgba(255,255,255,.12); padding-bottom:24px; margin-bottom:26px; }}
    h1 {{ margin:0; font-size:44px; letter-spacing:-.05em; }}
    .sub {{ color:#aeb6c8; max-width:620px; line-height:1.55; }}
    h2 {{ margin-top:34px; color:#f1d07a; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
    .metrics div, .card, .topic {{ border:1px solid rgba(255,255,255,.1); background:rgba(255,255,255,.045); border-radius:18px; padding:18px; }}
    .metrics b {{ display:block; font-size:36px; letter-spacing:-.04em; }}
    .metrics span, footer, .status {{ color:#9da6b8; font-size:13px; }}
    .topics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }}
    .topic {{ display:flex; justify-content:space-between; color:#eef1e8; text-decoration:none; }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; }}
    .card.core {{ border-left:4px solid #72a348; }}
    .card.candidate {{ border-left:4px solid #c78a2f; }}
    h3 {{ margin:8px 0 10px; font-size:18px; }}
    a {{ color:#f5f0dd; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    p {{ color:#c4cad6; line-height:1.55; }}
    footer {{ margin-top:14px; }}
    @media (max-width: 760px) {{ .metrics {{ grid-template-columns:1fr 1fr; }} header {{ display:block; }} h1 {{ font-size:34px; }} }}
  </style>
</head>
<body>
  <main>
    <header><div><h1>{escape(title)}</h1><div class="sub">{escape(subtitle)}</div></div><div class="sub">local · evidence-bound · static</div></header>
    {body}
  </main>
</body>
</html>"""


def _quality_score(quality: dict[str, Any]) -> float | None:
    if not isinstance(quality, dict):
        return None
    for key in ("score", "quality_score", "readability_score"):
        try:
            return float(quality[key])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", value.strip()).strip("-")
    return slug[:80] or "topic"


def _compact(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _pipe_safe(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _format_time(ts: float) -> str:
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
