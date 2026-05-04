# -*- coding: utf-8 -*-
"""Archive CLI command handler.

Kept separate from guanlan.cli so the parser remains stable while command
implementation can be maintained and tested in smaller slices.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def handle_archive_command(args):
    """Manage the local Markdown archive."""

    from guanlan.archive import (
        add_browser_visible_note,
        add_url,
        add_urls,
        archive_quality_summary,
        archive_search_diagnostics,
        archive_stats,
        embed_archive,
        export_documents,
        format_archive_context,
        format_archive_export_jsonl,
        format_archive_markdown,
        format_archive_stats,
        format_archive_verify,
        ingest_search,
        inspect_document,
        list_documents,
        reindex_archive,
        remove_document,
        search_documents,
        verify_archive,
    )
    from guanlan.archive_wiki import (
        build_archive_pack,
        build_archive_wiki,
        build_archive_wiki_context,
        format_wiki_build_summary,
    )

    command = getattr(args, "archive_command", None)
    if not command:
        print("Error: archive command is required: add, add-browser-note, search, context, pack, wiki, embed, ingest-search, ingest-research, list, inspect, remove, reindex, verify, stats, export", file=sys.stderr)
        sys.exit(2)
    db_path = args.db or None

    try:
        if command == "add":
            if args.target == "batch":
                if not args.batch_file:
                    print("Error: archive add batch requires a URL list file", file=sys.stderr)
                    sys.exit(2)
                with open(args.batch_file, "r", encoding="utf-8") as f:
                    urls = [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]
                records = add_urls(
                    urls,
                    max_chars=args.max_chars or None,
                    backend=args.backend,
                    fallback_search=args.fallback_search,
                    fallback_limit=max(args.fallback_limit, 1),
                    profile=args.profile or None,
                    db_path=db_path,
                    concurrency=max(args.concurrency, 1),
                )
            else:
                records = [
                    add_url(
                        args.target,
                        max_chars=args.max_chars or None,
                        backend=args.backend,
                        fallback_search=args.fallback_search,
                        fallback_limit=max(args.fallback_limit, 1),
                        profile=args.profile or None,
                        db_path=db_path,
                    )
                ]
            if args.format == "json":
                print(json.dumps(records, ensure_ascii=False, indent=2))
            else:
                print(_format_archive_add_summary(records))
            return

        if command == "add-browser-note":
            content = str(getattr(args, "text", "") or "")
            if getattr(args, "text_file", ""):
                with open(args.text_file, "r", encoding="utf-8") as f:
                    content = f.read()
            if not content.strip():
                print("Error: --text or --text-file is required for add-browser-note", file=sys.stderr)
                sys.exit(2)
            record = add_browser_visible_note(
                args.url,
                content,
                title=args.title,
                platform=args.platform,
                author=args.author,
                published_at=args.published_at,
                db_path=db_path,
            )
            output_format = "json" if args.json else args.format
            if output_format == "json":
                print(json.dumps(record, ensure_ascii=False, indent=2))
            else:
                print(_format_archive_browser_note_summary(record))
            return

        if command == "search":
            records = search_documents(args.query, limit=max(args.limit, 1), trace=args.trace, semantic=args.semantic, db_path=db_path)
            diagnostics = archive_search_diagnostics(args.query, records=records, semantic=args.semantic, db_path=db_path) if args.trace or args.semantic else None
            output_format = "json" if args.json else args.format
            if output_format == "json":
                print(json.dumps({"records": records, "diagnostics": diagnostics} if diagnostics else records, ensure_ascii=False, indent=2))
            elif output_format == "context":
                print(format_archive_context(records, title=f"观澜本地知识库上下文 / {args.query}"))
                if args.trace:
                    print(_format_archive_search_trace(records, diagnostics=diagnostics))
            else:
                print(format_archive_markdown(records, title=f"观澜本地知识库 / {args.query}"))
                if args.trace:
                    print(_format_archive_search_trace(records, diagnostics=diagnostics))
            return

        if command == "context":
            if args.semantic:
                records = search_documents(args.query, limit=max(args.limit, 1), trace=True, semantic=True, db_path=db_path)
                result = {
                    "query": args.query,
                    "records": records,
                    "context": format_archive_context(records, title=f"观澜本地知识库语义上下文 / {args.query}"),
                    "retrieval_mode": "semantic",
                    "boundary": "显式语义侧车；无 embedding 时自动回退到 FTS/LIKE。",
                }
            else:
                result = build_archive_wiki_context(
                    args.query,
                    limit=max(args.limit, 1),
                    min_quality=max(args.min_quality, 0),
                    max_chars=max(args.max_chars, 1),
                    db_path=db_path,
                )
            output_format = "json" if args.json else args.format
            if output_format == "json":
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(result["context"])
            return

        if command == "embed":
            result = embed_archive(
                backend=args.backend,
                limit=max(args.limit, 1),
                dry_run=args.dry_run,
                db_path=db_path,
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print("# 观澜 Archive 语义侧车")
                print()
                print(f"- 状态: {result.get('status')}")
                print(f"- 后端: {result.get('backend')}")
                print(f"- 文档数: {result.get('documents', 0)}")
                print(f"- 已写入: {result.get('embedded', 0)}")
                print(f"- 边界: {result.get('boundary', '')}")
            return

        if command == "pack":
            result = build_archive_pack(
                args.query,
                output_path=args.output or None,
                output_format=args.format,
                limit=max(args.limit, 1),
                max_chars=max(args.max_chars, 1),
                db_path=db_path,
            )
            if args.output:
                if args.json:
                    print(json.dumps({key: value for key, value in result.items() if key != "content"}, ensure_ascii=False, indent=2))
                else:
                    print("# 观澜 Archive Pack")
                    print()
                    print(f"- 输出: {result.get('path', '')}")
                    print(f"- 格式: {result.get('format', '')}")
                    print(f"- 记录数: {result.get('records', 0)}")
                    print(f"- 边界: {result.get('boundary', '')}")
            else:
                print(result["content"])
            return

        if command == "list":
            records = list_documents(limit=max(args.limit, 1), db_path=db_path)
            output_format = "json" if args.json else args.format
            if output_format == "json":
                print(json.dumps(records, ensure_ascii=False, indent=2))
            elif output_format == "context":
                print(format_archive_context(records))
            else:
                print(format_archive_markdown(records))
            return

        if command == "stats":
            stats = archive_stats(db_path=db_path)
            if args.quality:
                stats["quality"] = archive_quality_summary(
                    db_path=db_path,
                    rag_min_quality=max(args.rag_min_quality, 0),
                )
            if args.json:
                print(json.dumps(stats, ensure_ascii=False, indent=2))
            else:
                print(format_archive_stats(stats))
            return

        if command == "inspect":
            record = inspect_document(args.identifier, db_path=db_path)
            if args.format == "json":
                print(json.dumps(record, ensure_ascii=False, indent=2))
            else:
                print(_format_archive_inspect(record))
            return

        if command == "remove":
            result = remove_document(args.identifier, db_path=db_path)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"已移除: [{result.get('id')}] {result.get('title') or result.get('url')}")
            return

        if command == "reindex":
            result = reindex_archive(db_path=db_path)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print("# 观澜本地知识库重建索引")
                print()
                print(f"- 状态: {result.get('status')}")
                print(f"- 文档数: {result.get('documents')}")
                print(f"- FTS: {result.get('fts')}")
                print(f"- 说明: {result.get('message')}")
            return

        if command == "verify":
            result = verify_archive(
                db_path=db_path,
                limit=max(args.limit, 1),
                min_quality=max(args.min_quality, 0),
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(format_archive_verify(result))
            return

        if command == "export":
            records = export_documents(
                db_path=db_path,
                domain=args.domain or None,
                source_type=args.source_type or None,
                topic=args.topic or None,
                min_quality=args.min_quality,
            )
            if args.format == "markdown":
                for item in records:
                    print(f"# {item.get('title', '')}")
                    print()
                    print(f"URL: {item.get('url', '')}")
                    print(f"Domain: {item.get('domain', '')}")
                    print()
                    print(str(item.get("content", "")).strip())
                    print("\n---\n")
            elif args.format.endswith("-jsonl") or args.format == "jsonl":
                print(format_archive_export_jsonl(records, profile=args.format))
            else:
                for item in records:
                    print(json.dumps(item, ensure_ascii=False, sort_keys=True))
            return

        if command == "wiki":
            wiki_command = getattr(args, "wiki_command", None)
            if wiki_command == "build":
                output_dir = args.output or str(Path.home() / ".guanlan" / "wiki")
                result = build_archive_wiki(
                    output_dir=output_dir,
                    topic=args.topic,
                    output_format=args.format,
                    limit=max(args.limit, 1),
                    min_quality=max(args.min_quality, 0),
                    include_candidates=not args.no_candidates,
                    db_path=db_path,
                )
                if args.json:
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                else:
                    print(format_wiki_build_summary(result))
                return
            if wiki_command == "context":
                result = build_archive_wiki_context(
                    args.query,
                    limit=max(args.limit, 1),
                    min_quality=max(args.min_quality, 0),
                    max_chars=max(args.max_chars, 1),
                    db_path=db_path,
                )
                output_format = "json" if args.json else args.format
                if output_format == "json":
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                else:
                    print(result["context"])
                return
            print("Error: archive wiki command is required: build or context", file=sys.stderr)
            sys.exit(2)

        if command in {"ingest-search", "ingest-research"}:
            def _archive_ingest_progress(event: dict) -> None:
                label = str(event.get("label") or event.get("phase") or "archive")
                detail = str(event.get("detail") or "").strip()
                suffix = f" | {detail}" if detail else ""
                print(f"[archive] {label}{suffix}", file=sys.stderr, flush=True)

            result = ingest_search(
                args.query,
                limit=max(args.limit, 1),
                read_top=max(args.read_top, 0),
                select_top=max(args.select_top, 1),
                preset=args.preset,
                profile=args.profile or None,
                dry_run=args.dry_run,
                db_path=db_path,
                read_backend=args.read_backend,
                read_concurrency=max(args.read_concurrency, 1),
                cache_ttl=max(args.cache_ttl, 0),
                progress_callback=_archive_ingest_progress,
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(_format_archive_ingest_summary(result))
            return
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Error: unknown archive command: {command}", file=sys.stderr)
    sys.exit(2)



def _format_archive_add_summary(records: list[dict]) -> str:
    lines = ["# 观澜本地知识库归档", ""]
    if not records:
        lines.append("暂无 URL。")
        return "\n".join(lines)
    for item in records:
        status = item.get("status", "unknown")
        title = item.get("title") or item.get("url") or "untitled"
        lines.append(f"- [{status}] {title}")
        if item.get("url"):
            lines.append(f"  {item['url']}")
        if item.get("error"):
            lines.append(f"  错误: {item['error']}")
    return "\n".join(lines)


def _format_archive_browser_note_summary(record: dict) -> str:
    lines = [
        "# 观澜浏览器辅助补证入库",
        "",
        f"- 状态: {record.get('status', 'unknown')}",
        f"- 标题: {record.get('title') or record.get('url')}",
        f"- URL: {record.get('url', '')}",
        f"- 平台: {record.get('platform') or '-'}",
        f"- 字符数: {record.get('chars', 0)}",
        "- 证据边界: browser_assisted / visible_page_only / user_authorized",
        f"- 说明: {record.get('boundary', '')}",
    ]
    return "\n".join(lines)


def _format_archive_ingest_summary(result: dict) -> str:
    lines = [
        "# 观澜本地知识库联网研究入库",
        "",
        f"- Query: {result.get('query', '')}",
        "- 行为: 联网 research 后归档精选代表证据；如需搜索已有本地库，请使用 `guanlan archive search`。",
        f"- Dry run: {'是' if result.get('dry_run') else '否'}",
        f"- 模式: {result.get('ingest_mode', 'search-first')}",
        f"- 耗时: {result.get('elapsed_sec', 0)}s",
        f"- 可选深读: read_top={result.get('read_top', 0)} backend={result.get('read_backend', '')} success={result.get('read_success_count', 0)}/{result.get('read_attempted_count', 0)}",
        f"- 搜索结果数: {result.get('packet_result_count', 0)}",
        f"- 精选数: {result.get('selected_count', 0)}",
        f"- 跳过低相关: {result.get('skipped_count', 0)}",
        f"- 已归档: {result.get('archived_count', 0)}",
        f"- 外层 timeout 建议: >= {result.get('timeout_budget_hint_seconds', 120)}s",
    ]
    if result.get("timeout_boundary"):
        lines.append(f"- Timeout 边界: {result.get('timeout_boundary')}")
    audit = result.get("audit_summary") or {}
    if audit:
        lines.extend(
            [
                f"- 审计候选: {audit.get('audited', 0)}",
                f"- 审计保留/跳过: {audit.get('kept', 0)}/{audit.get('skipped', 0)}",
            ]
        )
        reasons = audit.get("reasons") or {}
        if reasons:
            lines.append("- 跳过原因: " + ", ".join(f"{key}={value}" for key, value in sorted(reasons.items())))
    phase_log = result.get("phase_log") or []
    if phase_log:
        compact = " -> ".join(
            f"{item.get('phase', '?')}({item.get('elapsed_sec', 0)}s)"
            for item in phase_log
        )
        lines.append(f"- 阶段轨迹: {compact}")
    next_steps = result.get("next_steps") or []
    if next_steps:
        lines.extend(["", "## 下一步"])
        lines.extend(f"- {step}" for step in next_steps)
    lines.append("")
    for item in result.get("records", []):
        reason = f" ({item.get('reason')})" if item.get("reason") else ""
        lines.append(f"- [{item.get('status', 'unknown')}] {item.get('title') or item.get('url')}{reason}")
    return "\n".join(lines)


def _format_archive_search_trace(records: list[dict], diagnostics: dict | None = None) -> str:
    lines = ["", "## Archive Search Trace"]
    if diagnostics:
        lines.append(f"- documents: {diagnostics.get('documents', 0)}")
        lines.append(f"- query_terms: {', '.join(diagnostics.get('query_terms') or []) or 'none'}")
        index = diagnostics.get("index") if isinstance(diagnostics.get("index"), dict) else {}
        if index:
            lines.append(
                f"- index: {index.get('type', 'sqlite-fts5+like')} / FTS={index.get('fts', '')} / semantic={diagnostics.get('semantic', 'not-vector')}"
            )
    if not records:
        lines.append("- 无命中；请先用 `guanlan archive list` 确认本地库是否已有文档。")
        if diagnostics:
            for step in diagnostics.get("guidance") or []:
                lines.append(f"- 建议: {step}")
        return "\n".join(lines)
    for idx, item in enumerate(records[:10], start=1):
        trace = item.get("search_trace") or {}
        lines.append(f"- {idx}. {item.get('title', '')}")
        lines.append(f"  - score: {trace.get('match_score', item.get('match_score', 0))}")
        lines.append(f"  - matched: {', '.join(trace.get('matched_terms') or []) or 'none'}")
        fields = trace.get("field_hits") or {}
        if fields:
            field_text = "; ".join(f"{key}={','.join(value)}" for key, value in fields.items())
            lines.append(f"  - fields: {field_text}")
    lines.append("- retrieval: sqlite-fts5+like; semantic: not-vector")
    return "\n".join(lines)


def _format_archive_inspect(record: dict) -> str:
    diagnostics = record.get("diagnostics") or {}
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    lines = [
        "# 观澜归档详情",
        "",
        f"- ID: {record.get('id')}",
        f"- 标题: {record.get('title', '')}",
        f"- URL: {record.get('url', '')}",
        f"- Domain: {record.get('domain', '')}",
        f"- 字符数: {diagnostics.get('chars', 0)}",
        f"- 元数据: {', '.join(diagnostics.get('metadata_keys') or []) or '无'}",
        "",
        "## 摘要",
        str(record.get("excerpt", "")),
    ]
    if metadata.get("browser_assisted"):
        lines.extend(
            [
                "",
                "## 浏览器辅助补证边界",
                "- 类型: browser_assisted / visible_page_only / user_authorized",
                f"- 平台: {metadata.get('platform') or '-'}",
                f"- 可复现性: {metadata.get('reproducibility') or 'session_dependent'}",
            ]
        )
        evidence_chain = metadata.get("evidence_chain") if isinstance(metadata.get("evidence_chain"), dict) else {}
        if evidence_chain:
            lines.append(f"- 证据链: {evidence_chain.get('planned_by', '')} -> {evidence_chain.get('collected_by', '')}")
    content = str(record.get("content", ""))
    if content:
        lines.extend(["", "## 正文预览", content[:2000]])
    return "\n".join(lines)
