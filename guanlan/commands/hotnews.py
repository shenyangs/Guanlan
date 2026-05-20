# -*- coding: utf-8 -*-
"""Hotnews command handlers for Guanlan CLI."""

import json
import sys


def _cmd_hotnews(args):
    """Fetch Chinese hotnews from native public sources."""

    from guanlan.config import Config
    from guanlan.hotnews import (
        build_hotnews_brief,
        build_hotnews_snapshot_report,
        build_trend_report,
        fetch_hotnews,
        format_hotnews_brief_markdown,
        format_hotnews_markdown,
        format_snapshot_report_markdown,
        format_trend_report_markdown,
        list_sources,
    )

    source = (args.source or "today").lower()
    if source == "list":
        print(json.dumps(list_sources(), ensure_ascii=False, indent=2))
        return
    snapshot_mode = source == "snapshot"
    if snapshot_mode:
        source = (args.snapshot_source or "today").lower()
        args.trends = args.trends or source == "today"

    if source == "zhihu":
        print(
            "[!] zhihu 热榜是 experimental 源，部分环境会 401/403；失败时请用 "
            '`guanlan search "知乎 热榜 关键词" --site zhihu.com --profile china` 兜底。',
            file=sys.stderr,
        )

    try:
        config = Config()
        newsnow_base_url = args.newsnow_base_url or config.get("newsnow_base_url")
        items = fetch_hotnews(
            source=source,
            limit=max(args.limit, 1),
            backend=args.backend,
            newsnow_base_url=newsnow_base_url,
        )
    except Exception as e:
        if source == "zhihu":
            print(
                "Fallback: guanlan search \"知乎 热榜 关键词\" --site zhihu.com --profile china",
                file=sys.stderr,
            )
        if source.startswith("newsnow:") or args.backend == "newsnow":
            print(
                "NewsNow fallback: try another BASE_URL with "
                "`guanlan configure newsnow-base-url https://your-newsnow.example`.",
                file=sys.stderr,
            )
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        payload = {"items": items}
        trend_report = build_trend_report(items) if (args.trends or args.brief) else None
        if args.trends:
            payload["trend_report"] = trend_report
        if args.brief:
            payload["brief"] = build_hotnews_brief(items, trend_report=trend_report)
        if snapshot_mode or args.watch:
            payload["snapshot"] = build_hotnews_snapshot_report(
                source,
                items,
                save=bool(args.watch),
                path=args.snapshot_db or None,
            )
        expanded_payload = bool(args.trends or args.brief or snapshot_mode or args.watch)
        print(json.dumps(payload if expanded_payload else items, ensure_ascii=False, indent=2))
    else:
        print(format_hotnews_markdown(items, title=f"观澜{'信源快照' if snapshot_mode else '热榜'} / {source}"))
        trend_report = build_trend_report(items) if (args.trends or args.brief) else None
        if args.trends:
            print()
            print(format_trend_report_markdown(trend_report or {}, title=f"观澜趋势归并 / {source}"))
        if args.brief:
            print()
            print(format_hotnews_brief_markdown(build_hotnews_brief(items, trend_report=trend_report), title=f"观澜今日水势简报 / {source}"))
        if snapshot_mode or args.watch:
            print()
            print(
                format_snapshot_report_markdown(
                    build_hotnews_snapshot_report(
                        source,
                        items,
                        save=bool(args.watch),
                        path=args.snapshot_db or None,
                    ),
                    title=f"观澜信源快照 / {source}",
                )
            )

__all__ = ['_cmd_hotnews']
