# -*- coding: utf-8 -*-
"""Search and routing command handlers for Guanlan CLI."""

import json
import sys

from guanlan.commands._feedback import _auto_feedback_for_search


def _cmd_route(args):
    """Explain the soft routing plan for a query."""

    from guanlan.router import build_route_plan, format_route_plan_markdown
    from guanlan.workflow_decider import decide_workflow, format_workflow_decision_markdown

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    preset_context = None if args.preset in {"", "general"} else args.preset
    plan = build_route_plan(
        args.query,
        preset=preset_context,
        scope=args.scope or None,
        site=args.site or None,
        sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
        profile=args.profile or None,
        limit=max(args.limit, 1),
        read_top=max(args.read_top, 0) if args.read_top is not None else None,
    )
    workflow_decision = decide_workflow(
        args.query,
        command="route",
        preset=preset_context,
        scope=args.scope or None,
        site=args.site or None,
        sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
        profile=args.profile or None,
        limit=max(args.limit, 1),
        read_top=max(args.read_top, 0) if args.read_top is not None else None,
        route_plan=plan,
    )
    if args.json:
        payload = plan.to_dict()
        payload["workflow_decision"] = workflow_decision.to_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_route_plan_markdown(plan))
        print()
        print(format_workflow_decision_markdown(workflow_decision))

def _cmd_workflow(args):
    """Decide whether a task should stay light or use a heavier workflow."""

    from guanlan.workflow_decider import decide_workflow, format_workflow_decision_markdown

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    decision = decide_workflow(
        args.query,
        command=args.workflow_command_context,
        preset=args.preset,
        scope=args.scope or None,
        site=args.site or None,
        sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
        profile=args.profile or None,
        limit=max(args.limit, 1),
        read_top=max(args.read_top, 0) if args.read_top is not None else None,
    )
    if args.json:
        print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_workflow_decision_markdown(decision))

def _cmd_agent(args):
    """Build a compact auto-plan for agent callers."""

    from guanlan.workflow_decider import build_agent_plan, format_agent_plan_markdown

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    preset_context = None if args.preset in {"", "general"} else args.preset
    plan = build_agent_plan(
        args.query,
        mode=args.mode,
        preset=preset_context,
        scope=args.scope or None,
        site=args.site or None,
        sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
        profile=args.profile or None,
        limit=max(args.limit, 1),
        read_top=max(args.read_top, 0) if args.read_top is not None else None,
        max_commands=max(args.max_commands, 1),
    )
    if args.json:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_agent_plan_markdown(plan))

def _cmd_search(args):
    """Search the web and format results for agents."""

    from guanlan.search_sources import list_search_scopes
    from guanlan.web.renderers import (
        format_search_context,
        format_search_markdown,
        format_search_prompt,
        format_search_trace,
        format_source_chart,
    )
    from guanlan.web.search import (
        search_web,
    )

    if getattr(args, "list_scopes", False):
        print(json.dumps(list_search_scopes(), ensure_ascii=False, indent=2))
        return
    if not args.query:
        print("Error: query is required unless --list-scopes is used", file=sys.stderr)
        sys.exit(2)

    try:
        results = search_web(
            args.query,
            limit=max(args.limit, 1),
            site=args.site or None,
            scope=args.scope or None,
            backend=args.backend,
            profile=args.profile or None,
            network_mode=args.network,
            trace=args.trace,
            cluster_threshold=args.cluster_threshold,
            cache_ttl=max(args.cache_ttl, 0),
            use_cache=not args.no_cache,
            strict_scope=args.strict_scope,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    _auto_feedback_for_search(args, results)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        diagnostics = getattr(results, "diagnostics", None)
        if diagnostics and not results:
            print(json.dumps({"results": [], "diagnostics": diagnostics}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(results, ensure_ascii=False, indent=2))
    elif output_format == "context":
        suffix = f" / {args.scope}" if args.scope else ""
        print(format_search_context(results, title=f"观澜搜索上下文{suffix} / {args.query}"))
        if args.source_chart:
            print(format_source_chart(results))
    elif output_format == "prompt":
        suffix = f" / {args.scope}" if args.scope else ""
        print(format_search_prompt(results, query=args.query, title=f"观澜搜索 Prompt{suffix}"))
    else:
        suffix = f" / {args.scope}" if args.scope else ""
        print(format_search_markdown(results, title=f"观澜搜索{suffix} / {args.query}"))
        if args.trace:
            print(format_search_trace(results))
        if args.source_chart:
            print(format_source_chart(results))

__all__ = ['_cmd_route', '_cmd_workflow', '_cmd_agent', '_cmd_search']
