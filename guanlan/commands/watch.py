# -*- coding: utf-8 -*-
"""Watch command handlers for Guanlan CLI."""

import json
import sys

from guanlan.commands.admin import _cmd_health_watch


def _cmd_watch_intents(args):
    """Manage standing research intents."""

    from guanlan.watch import (
        build_watch_plan,
        create_watch_intent,
        fire_watch_intent,
        format_watch_fire_markdown,
        format_watch_intent_markdown,
        format_watch_list_markdown,
        format_watch_plan_markdown,
        get_watch_intent,
        list_watch_intents,
        remove_watch_intent,
    )

    command = getattr(args, "watch_command", None)
    if command is None:
        _cmd_health_watch()
        return
    output_format = "json" if getattr(args, "json", False) else getattr(args, "format", "markdown")
    store_path = getattr(args, "store", "") or None
    try:
        if command == "plan":
            payload = build_watch_plan(
                args.query,
                profile=args.profile,
                scope=args.scope or "",
                site=args.site or "",
                preset=args.preset or "",
                feed_source=args.feed_source or "auto",
                watchlist_path=args.watchlist or "",
                lens=args.lens or "",
                schedule=args.schedule or "",
                limit=max(args.limit, 1),
            )
            if output_format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(format_watch_plan_markdown(payload))
            return
        if command == "add":
            payload = create_watch_intent(
                args.query,
                name=args.name or "",
                intent_id=args.intent_id or "",
                profile=args.profile,
                scope=args.scope or "",
                site=args.site or "",
                preset=args.preset or "",
                feed_source=args.feed_source or "auto",
                watchlist_path=args.watchlist or "",
                lens=args.lens or "",
                schedule=args.schedule or "",
                tags=list(args.tag or []),
                store_path=store_path,
            )
            if output_format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(format_watch_intent_markdown(payload))
            return
        if command == "list":
            payload = list_watch_intents(store_path=store_path)
            if output_format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(format_watch_list_markdown(payload))
            return
        if command == "show":
            payload = get_watch_intent(args.identifier, store_path=store_path, include_seen=args.include_seen)
            if output_format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(format_watch_intent_markdown(payload))
            return
        if command == "remove":
            payload = remove_watch_intent(args.identifier, store_path=store_path)
            if output_format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"已移除 watch intent: `{payload.get('id')}` {payload.get('name')}")
            return
        if command == "fire":
            payload = fire_watch_intent(
                args.identifier,
                limit=max(args.limit, 1),
                search_limit=max(args.search_limit, 1) if args.search_limit else None,
                feed_limit=max(args.feed_limit, 1) if args.feed_limit else None,
                search_backend=args.backend or "auto",
                record_seen=bool(args.record_seen),
                store_path=store_path,
                cache_ttl=max(args.cache_ttl, 0),
            )
            if output_format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(format_watch_fire_markdown(payload))
            return
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print("Error: watch command is required: plan, add, list, show, remove, or fire", file=sys.stderr)
    sys.exit(2)

__all__ = ['_cmd_watch_intents']
