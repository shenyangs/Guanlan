# -*- coding: utf-8 -*-
"""Daily brief command handlers for Guanlan CLI."""

import json
import sys


def _cmd_daily(args):
    """Build a Guanlan-native daily brief."""
    from guanlan.agent_planner import build_agent_followup
    from guanlan.daily import (
        build_daily_report,
        format_daily_context,
        format_daily_html,
        format_daily_im,
        format_daily_markdown,
        save_daily_output,
    )

    output_format = "json" if getattr(args, "json", False) else str(getattr(args, "format", "markdown") or "markdown")
    try:
        report = build_daily_report(
            str(getattr(args, "query", "") or ""),
            watch_id=str(getattr(args, "watch_id", "") or ""),
            profile=str(getattr(args, "profile", "china") or "china"),
            scope=str(getattr(args, "scope", "") or ""),
            site=str(getattr(args, "site", "") or ""),
            preset=str(getattr(args, "preset", "") or ""),
            lens=str(getattr(args, "lens", "") or ""),
            feed_source=str(getattr(args, "feed_source", "auto") or "auto"),
            watchlist_path=str(getattr(args, "watchlist", "") or ""),
            hotnews_source=str(getattr(args, "hotnews_source", "today") or "today"),
            search_backend=str(getattr(args, "backend", "auto") or "auto"),
            limit=int(getattr(args, "limit", 12) or 12),
            search_limit=int(getattr(args, "search_limit", 80) or 80),
            feeds_limit=int(getattr(args, "feeds_limit", 20) or 20),
            hotnews_limit=int(getattr(args, "hotnews_limit", 20) or 20),
            include_search=not bool(getattr(args, "no_search", False)),
            include_feeds=not bool(getattr(args, "no_feeds", False)),
            include_hotnews=not bool(getattr(args, "no_hotnews", False)),
            cache_ttl=int(getattr(args, "cache_ttl", 0) or 0),
            store_path=str(getattr(args, "store", "") or "") or None,
            read_top=int(getattr(args, "read_top", 3) or 0),
            read_backend=str(getattr(args, "read_backend", "auto") or "auto"),
            max_read_chars=int(getattr(args, "max_read_chars", 1800) or 1800),
            overflow_limit=int(getattr(args, "overflow_limit", 20) or 0),
            time_window=str(getattr(args, "time_window", "3d") or "3d"),
            edition=str(getattr(args, "edition", "brand") or "brand"),
            record_history=bool(getattr(args, "record_history", False)),
            history_path=str(getattr(args, "history_path", "") or ""),
            compare_days=int(getattr(args, "compare_days", 0) or 0),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    report["agent_followup"] = build_agent_followup(
        "guanlan_daily",
        report,
        query=str(getattr(args, "query", "") or ""),
    )

    if output_format == "json":
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
    elif output_format == "context":
        from guanlan.agent_planner import format_agent_followup_context

        rendered = format_daily_context(report)
        followup_text = format_agent_followup_context(report.get("agent_followup"))
        if followup_text:
            rendered = f"{rendered}\n\n{followup_text}"
    elif output_format == "html":
        rendered = format_daily_html(report)
    elif output_format == "im":
        rendered = format_daily_im(report)
    else:
        rendered = format_daily_markdown(report)

    output_path = str(getattr(args, "output", "") or "").strip()
    if output_path:
        save_daily_output(report, output_path, output_format=output_format)

    print(rendered)


__all__ = ["_cmd_daily"]
