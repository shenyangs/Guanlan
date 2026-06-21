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

    from guanlan.agent_planner import (
        build_agent_plan_v2,
        format_agent_plan_v2_markdown,
        load_observation_json,
        review_agent_observation,
    )

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    preset_context = None if args.preset in {"", "general"} else args.preset
    common_kwargs = {
        "mode": args.mode,
        "preset": preset_context,
        "scope": args.scope or None,
        "site": args.site or None,
        "sites": [s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
        "profile": args.profile or None,
        "limit": max(args.limit, 1),
        "read_top": max(args.read_top, 0) if args.read_top is not None else None,
        "max_commands": max(args.max_commands, 1),
    }
    if getattr(args, "phase", "plan") == "review":
        try:
            observation = load_observation_json(getattr(args, "observation_json", ""))
        except Exception as exc:
            print(f"Error: invalid observation JSON: {exc}", file=sys.stderr)
            sys.exit(2)
        plan = review_agent_observation(args.query, observation, **common_kwargs)
    else:
        plan = build_agent_plan_v2(args.query, **common_kwargs)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print(format_agent_plan_v2_markdown(plan))

def _cmd_search(args):
    """Search the web and format results for agents."""

    from guanlan.agent_planner import build_agent_followup, format_agent_followup_context
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
            evidence_mode=getattr(args, "evidence_mode", "shadow"),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    _auto_feedback_for_search(args, results)
    followup = build_agent_followup(
        "guanlan_search",
        {"results": results, "limit": max(args.limit, 1), "diagnostics": getattr(results, "diagnostics", {})},
        query=args.query,
    )

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
        followup_text = format_agent_followup_context(followup)
        if followup_text:
            print()
            print(followup_text)
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


def _cmd_map(args):
    """Discover public URLs inside a known site for follow-up reads."""

    from guanlan.site_map import build_site_map, format_site_map_context, format_site_map_markdown

    if not args.url:
        print("Error: url is required", file=sys.stderr)
        sys.exit(2)
    try:
        packet = build_site_map(
            args.url,
            query=args.query or "",
            limit=max(args.limit, 1),
            include_subdomains=bool(args.include_subdomains),
            sitemap=args.sitemap,
            include_patterns=list(args.include_patterns or []),
            exclude_patterns=list(args.exclude_patterns or []),
            timeout=max(args.timeout, 1),
            read_top=max(min(int(args.read_top or 0), 5), 0),
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_site_map_context(packet))
    else:
        print(format_site_map_markdown(packet))


__all__ = ['_cmd_route', '_cmd_workflow', '_cmd_agent', '_cmd_search', '_cmd_map']
