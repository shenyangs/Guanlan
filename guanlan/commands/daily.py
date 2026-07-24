# -*- coding: utf-8 -*-
"""Daily brief command handlers for Guanlan CLI."""

import json
import sys

from guanlan.errors import format_user_error
from guanlan.tool_invocation import normalize_daily_request


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
        request = normalize_daily_request(vars(args))
        query = request.pop("query")
        report = build_daily_report(query, **request)
    except Exception as exc:
        print(f"Error: {format_user_error(exc)}", file=sys.stderr)
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
