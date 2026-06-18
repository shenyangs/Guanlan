# -*- coding: utf-8 -*-
"""Research and analysis command handlers for Guanlan CLI."""

import json
import sys

from guanlan.commands._feedback import _auto_feedback_for_research
from guanlan.limits import DEFAULT_RESEARCH_LIMIT


def _cmd_research(args):
    """Build an agent-ready research evidence packet."""

    from guanlan.agent_planner import build_agent_followup, format_agent_followup_context
    from guanlan.router import format_route_chart
    from guanlan.web.renderers import (
        format_advisor_context,
        format_claim_ledger_context,
        format_evidence_audit_context,
        format_freshness_guard_markdown,
        format_research_markdown,
        format_research_prompt,
        format_search_context,
        format_source_chart,
        format_source_mix_guard_markdown,
    )
    from guanlan.web.research import (
        build_research_packet,
        list_research_presets,
    )

    if getattr(args, "list_presets", False):
        print(json.dumps(list_research_presets(), ensure_ascii=False, indent=2))
        return
    if not args.query:
        print("Error: query is required unless --list-presets is used", file=sys.stderr)
        sys.exit(2)

    try:
        packet = build_research_packet(
            args.query,
            preset=args.preset,
            limit=max(args.limit, 1) if args.limit is not None else None,
            site=args.site or None,
            sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
            scope=args.scope or None,
            search_backend=args.search_backend,
            profile=args.profile or None,
            read_top=max(args.read_top, 0) if args.read_top is not None else None,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            advisor=args.advisor,
            advisor_style=args.advisor_style,
            select_top=max(args.select_top, 0) if args.select_top is not None else None,
            max_search_jobs=max(args.max_search_jobs, 0) if args.max_search_jobs is not None else None,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    _auto_feedback_for_research(args, packet)
    packet["agent_followup"] = build_agent_followup("guanlan_research", packet, query=args.query)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    elif output_format == "context":
        evidence = packet.get("selected_evidence") or packet.get("results", [])
        print(format_search_context(evidence, title=f"观澜研究上下文 / {args.query}"))
        if isinstance(packet.get("evidence_audit"), dict):
            print()
            print(format_evidence_audit_context(packet["evidence_audit"]))
        if isinstance(packet.get("claim_ledger"), dict):
            print()
            print(format_claim_ledger_context(packet["claim_ledger"]))
        if isinstance(packet.get("freshness_guard"), dict):
            print()
            print(format_freshness_guard_markdown(packet["freshness_guard"]))
        if isinstance(packet.get("source_mix_guard"), dict):
            print()
            print(format_source_mix_guard_markdown(packet["source_mix_guard"]))
        if args.advisor and isinstance(packet.get("advisor"), dict):
            print()
            print(format_advisor_context(packet["advisor"]))
        if args.source_chart:
            print(format_source_chart(packet.get("results", [])))
        if args.route_chart:
            print(format_route_chart(packet.get("route_plan", {})))
        followup_text = format_agent_followup_context(packet.get("agent_followup"))
        if followup_text:
            print()
            print(followup_text)
    elif output_format == "prompt":
        print(format_research_prompt(packet, style=args.prompt_style))
    else:
        print(format_research_markdown(packet))
        if args.source_chart:
            print(format_source_chart(packet.get("results", [])))
        if args.route_chart:
            print(format_route_chart(packet.get("route_plan", {})))

def _cmd_investigate(args):
    """Run an explicit upper-layer investigation workflow."""

    from guanlan.investigation import (
        build_investigation_packet,
        format_investigation_context,
        format_investigation_markdown,
    )

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    try:
        packet = build_investigation_packet(
            args.query,
            preset=args.preset,
            profile=args.profile or None,
            limit=max(args.limit, 1) if args.limit is not None else None,
            read_top=max(args.read_top, 0) if args.read_top is not None else None,
            budget=args.budget,
            dry_run=bool(args.dry_run),
            search_backend=args.search_backend,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            advisor=not bool(args.no_advisor),
            advisor_style=args.advisor_style,
            select_top=max(args.select_top, 0) if args.select_top is not None else None,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_investigation_context(packet))
    else:
        print(format_investigation_markdown(packet))

def _cmd_recipe(args):
    """Render reusable research recipe plans for agents."""

    from guanlan.recipes import (
        build_recipe_plan,
        format_recipe_json,
        format_recipe_list_markdown,
        format_recipe_plan_markdown,
        get_recipe,
        list_recipes,
    )

    command = getattr(args, "recipe_command", None)
    if not command:
        print(format_recipe_list_markdown())
        return
    try:
        if command == "list":
            recipes = list_recipes()
            print(format_recipe_json(recipes) if args.json else format_recipe_list_markdown(recipes))
            return
        if command == "show":
            recipe = get_recipe(args.recipe_id).to_dict()
            print(format_recipe_json(recipe) if args.json else format_recipe_list_markdown([recipe]))
            return
        if command == "run":
            if not args.query:
                print("Error: query is required", file=sys.stderr)
                sys.exit(2)
            plan = build_recipe_plan(
                args.recipe_id,
                args.query,
                profile=args.profile,
                limit=max(args.limit, 1),
                read_top=args.read_top,
            )
            print(format_recipe_json(plan) if args.json else format_recipe_plan_markdown(plan))
            return
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"Error: unknown recipe command: {command}", file=sys.stderr)
    sys.exit(2)

def _cmd_sources(args):
    """Inspect Guanlan's read-only source registry."""

    from guanlan.source_registry import (
        audit_source_registry,
        explain_sources,
        export_source_registry,
        format_source_audit_markdown,
        format_source_explain_markdown,
        format_source_registry_export_json,
        format_source_show_markdown,
        format_sources_markdown,
        list_source_cards,
        show_source,
    )

    command = getattr(args, "sources_command", None)
    if command == "list":
        rows = list_source_cards(scope=args.scope or None, limit=max(args.limit, 1))
        if args.format == "json":
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            suffix = f" / {args.scope}" if args.scope else ""
            print(format_sources_markdown(rows, title=f"观澜信源矩阵{suffix}"))
        return
    if command == "show":
        payload = show_source(args.target)
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(format_source_show_markdown(payload))
        return
    if command == "explain":
        if not args.query:
            print("Error: query is required", file=sys.stderr)
            sys.exit(2)
        payload = explain_sources(args.query, profile=args.profile or None, limit=max(args.limit, 1))
        if getattr(args, "trace", False):
            payload["trace"] = {
                "adapter": "source-registry-2.0",
                "network": "not_used",
                "boundary": payload.get("boundary", ""),
            }
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(format_source_explain_markdown(payload))
        return
    if command == "audit":
        report = audit_source_registry()
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_source_audit_markdown(report))
        return
    if command == "export":
        print(format_source_registry_export_json(export_source_registry()))
        return
    print("Error: sources command is required: list, show, explain, audit, or export", file=sys.stderr)
    sys.exit(2)

def _cmd_compare(args):
    """Compare multiple subjects through Guanlan evidence packets."""
    from guanlan.research_workflows import (
        build_compare_report,
        format_compare_markdown,
        format_workflow_context,
    )

    try:
        report = build_compare_report(
            list(args.subjects or []),
            focus=args.focus,
            preset=args.preset,
            profile=args.profile,
            limit=max(args.limit, 1),
            read_top=max(args.read_top, 0),
            search_backend=args.search_backend,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            select_top=max(args.select_top, 1),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_workflow_context(report, title="观澜对比研究上下文"))
    else:
        print(format_compare_markdown(report))

def _cmd_timeline(args):
    """Build a dated timeline from Guanlan evidence."""
    from guanlan.research_workflows import (
        build_timeline_report,
        format_timeline_markdown,
        format_workflow_context,
    )

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    try:
        report = build_timeline_report(
            args.query,
            preset=args.preset,
            profile=args.profile,
            limit=max(args.limit, 1),
            read_top=max(args.read_top, 0),
            search_backend=args.search_backend,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            max_events=max(args.max_events, 1),
            order=args.order,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_workflow_context(report, title="观澜时间线上下文"))
    else:
        print(format_timeline_markdown(report))

def _cmd_dossier(args):
    """Build a structured Guanlan dossier for one entity."""
    from guanlan.research_workflows import (
        build_dossier_report,
        format_dossier_markdown,
        format_workflow_context,
    )

    if not args.entity:
        print("Error: entity is required", file=sys.stderr)
        sys.exit(2)
    try:
        report = build_dossier_report(
            args.entity,
            focus=args.focus,
            preset=args.preset,
            profile=args.profile,
            limit=max(args.limit, 1),
            read_top=max(args.read_top, 0),
            search_backend=args.search_backend,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            select_top=max(args.select_top, 1),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_workflow_context(report, title="观澜研究档案上下文"))
    else:
        print(format_dossier_markdown(report))

def _cmd_yinshen(args):
    """Expand one keyword into evidence-backed media angles."""
    from guanlan.research_workflows import (
        build_yinshen_report,
        format_workflow_context,
        format_yinshen_markdown,
    )

    if not args.keyword:
        print("Error: keyword is required", file=sys.stderr)
        sys.exit(2)
    try:
        report = build_yinshen_report(
            args.keyword,
            preset=args.preset,
            profile=args.profile,
            limit=max(args.limit, 1),
            read_top=max(args.read_top, 0),
            angle_limit=max(args.angle_limit, 1) if args.angle_limit is not None else None,
            angle_read_top=max(args.angle_read_top, 0),
            angles=max(min(args.angles, 8), 1),
            search_backend=args.search_backend,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            select_top=max(args.select_top, 1),
            plan_only=bool(args.plan_only),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_workflow_context(report, title="观澜引申上下文"))
    else:
        print(format_yinshen_markdown(report))

def _cmd_prompt(args):
    """Build a local-LLM prompt from a broad Guanlan research packet."""

    from guanlan.web.renderers import format_research_prompt
    from guanlan.web.research import build_research_packet

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)

    try:
        packet = build_research_packet(
            args.query,
            preset=args.preset,
            limit=max(args.limit or DEFAULT_RESEARCH_LIMIT, 1),
            site=args.site or None,
            sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
            scope=args.scope or None,
            search_backend=args.search_backend,
            profile=args.profile or None,
            read_top=max(args.read_top, 0),
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1),
            advisor=args.advisor,
            advisor_style=args.advisor_style,
            select_top=max(args.select_top, 1),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(format_research_prompt(packet, style=args.style))

def _cmd_feedback(args):
    """Submit search dissatisfaction feedback for server-side diagnosis."""

    from guanlan.feedback import submit_feedback

    query = str(args.query or "").strip()
    reason = str(args.reason or "").strip()
    if not query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    if not reason:
        print("Error: --reason is required", file=sys.stderr)
        sys.exit(2)

    result = submit_feedback(
        query,
        reason,
        command=args.feedback_command,
        surface="cli",
        profile=args.profile or "",
        backend=args.backend or "",
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if result.get("ok") and result.get("queued"):
        print("✅ 反馈已保存，将在网络恢复后自动上报。")
    elif result.get("ok"):
        print("✅ 反馈已提交，感谢帮助我们改进搜索质量。")
    else:
        print(f"❌ 反馈提交失败: {result.get('message')}", file=sys.stderr)
        sys.exit(1)

__all__ = ['_cmd_research', '_cmd_investigate', '_cmd_recipe', '_cmd_sources', '_cmd_compare', '_cmd_timeline', '_cmd_dossier', '_cmd_yinshen', '_cmd_prompt', '_cmd_feedback']
