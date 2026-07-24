# -*- coding: utf-8 -*-
"""Search and routing command handlers for Guanlan CLI."""

import json
import sys

from guanlan.commands._feedback import _auto_feedback_for_search
from guanlan.errors import format_user_error
from guanlan.tool_invocation import (
    normalize_agent_request,
    normalize_map_request,
    normalize_route_request,
    normalize_search_request,
    normalize_workflow_request,
)


def _cmd_route(args):
    """Explain the soft routing plan for a query."""

    from guanlan.router import build_route_plan, format_route_plan_markdown
    from guanlan.workflow_decider import decide_workflow, format_workflow_decision_markdown

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    request = normalize_route_request(vars(args), max_read_top=None, default_profile=None)
    plan = build_route_plan(**request)
    workflow_kwargs = {key: value for key, value in request.items() if key != "query"}
    workflow_decision = decide_workflow(
        request["query"],
        command="route",
        **workflow_kwargs,
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
    request = normalize_workflow_request(vars(args), max_read_top=None, default_profile=None)
    query = request.pop("query")
    decision = decide_workflow(query, **request)
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
    request = normalize_agent_request(vars(args), default_profile=None)
    common_kwargs = {key: value for key, value in request.items() if key not in {"query", "phase"}}
    if request["phase"] == "review":
        try:
            observation = load_observation_json(getattr(args, "observation_json", ""))
        except Exception as exc:
            print(f"Error: invalid observation JSON: {exc}", file=sys.stderr)
            sys.exit(2)
        plan = review_agent_observation(request["query"], observation, **common_kwargs)
    else:
        plan = build_agent_plan_v2(request["query"], **common_kwargs)
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
        request = normalize_search_request(vars(args), default_profile=None)
        query = request.pop("query")
        results = search_web(query, **request)
    except Exception as exc:
        print(f"Error: {format_user_error(exc)}", file=sys.stderr)
        sys.exit(1)

    _auto_feedback_for_search(args, results)
    followup = build_agent_followup(
        "guanlan_search",
        {"results": results, "limit": request["limit"], "diagnostics": getattr(results, "diagnostics", {})},
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
        request = normalize_map_request(vars(args))
        url = request.pop("url")
        packet = build_site_map(url, **request)
    except Exception as exc:
        print(f"Error: {format_user_error(exc)}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_site_map_context(packet))
    else:
        print(format_site_map_markdown(packet))


__all__ = ['_cmd_route', '_cmd_workflow', '_cmd_agent', '_cmd_search', '_cmd_map']
