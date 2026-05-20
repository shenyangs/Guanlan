# -*- coding: utf-8 -*-
"""Feeds and pulse command handlers for Guanlan CLI."""

import json
import sys

from guanlan.limits import MAX_FEEDS_LIMIT


def _cmd_pulse(args):
    """Analyze public topic echo with explicit caveats."""

    from guanlan.pulse import (
        build_pulse_report,
        format_pulse_context,
        format_pulse_markdown,
    )

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)

    try:
        report = build_pulse_report(
            args.query,
            limit=max(args.limit, 1),
            site=args.site or None,
            sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
            scope=args.scope or None,
            backend=args.backend,
            profile=args.profile or None,
            read_top=max(args.read_top, 0),
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1),
            cache_ttl=max(args.cache_ttl, 0),
            use_cache=not args.no_cache,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_pulse_context(report))
    else:
        print(format_pulse_markdown(report))

def _cmd_feeds(args):
    """Discover content and source catalogs from public RSS/OPML."""

    from guanlan.feeds import (
        fetch_feed_source,
        format_feed_catalog_markdown,
        format_feed_items_context,
        format_feed_items_markdown,
        format_feed_sources_markdown,
        format_json,
        list_curated_sources,
        list_feed_sources,
        resolve_feed_source,
    )

    source = resolve_feed_source(args.source or "curated")
    limit = min(max(args.limit, 1), MAX_FEEDS_LIMIT)
    output_format = "json" if args.json else args.format

    try:
        if source == "list":
            catalog = list_feed_sources()
            if output_format == "json":
                print(format_json(catalog))
            else:
                print(format_feed_catalog_markdown(catalog))
            return
        if source == "curated-sources":
            sources = list_curated_sources(limit=limit, query=args.keyword or None)
            if output_format == "json":
                print(format_json(sources))
            else:
                suffix = f" / {args.keyword}" if args.keyword else ""
                print(format_feed_sources_markdown(sources, title=f"观澜 RSS 源目录 / 精品源{suffix}"))
            return
        items = fetch_feed_source(
            source,
            limit=limit,
            language=args.language,
            category=args.category or None,
            resource_type=args.resource_type or None,
            featured=args.featured,
            min_score=args.min_score,
            keyword=args.keyword or None,
            time_filter=args.time_filter or None,
            watchlist_path=args.watchlist or None,
        )
        source_titles = {
            "curated": "精品内容流",
            "arxiv": "arXiv 预印本",
            "watchlist": "订阅源观察",
            "baidu-rss": "百度实时热点 RSS",
            "wechat-rss": "微信热门文章 RSS",
        }
        title = f"观澜内容发现 / {source_titles.get(source, 'RSS')}"
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if output_format == "json":
        print(format_json(items))
    elif output_format == "context":
        print(format_feed_items_context(items, title=f"{title} 上下文"))
    else:
        print(format_feed_items_markdown(items, title=title))

__all__ = ['_cmd_pulse', '_cmd_feeds']
