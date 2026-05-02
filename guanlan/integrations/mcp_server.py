# -*- coding: utf-8 -*-
"""观澜 / Guanlan MCP Server.

Run: python -m guanlan.integrations.mcp_server

The MCP surface is intentionally read-first: it exposes search, read, research,
hotnews, and status tools for AI agents without adding write/social actions.
"""

import asyncio
import json
import sys

from guanlan.config import Config
from guanlan.core import Guanlan
from guanlan.limits import (
    DEFAULT_ARCHIVE_SEARCH_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_PULSE_LIMIT,
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    MAX_ARCHIVE_SEARCH_LIMIT,
    MAX_HOTNEWS_LIMIT,
    MAX_PULSE_LIMIT,
    MAX_READ_FALLBACK_LIMIT,
    MAX_RESEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


def _tool_definitions() -> list[dict]:
    """Return MCP tool definitions as plain dictionaries for easy testing."""
    return [
        {
            "name": "guanlan_status",
            "description": "Get Guanlan channel status and health summary.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "guanlan_search",
            "description": (
                "Search public web sources with Guanlan's China-aware ranking layer. "
                "For agent research, prefer a broad limit such as 50-100 and filter after retrieval."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": DEFAULT_SEARCH_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_SEARCH_LIMIT,
                    },
                    "site": {"type": "string"},
                    "scope": {"type": "string"},
                    "backend": {"type": "string", "default": "auto"},
                    "profile": {"type": "string", "enum": ["global", "china", "hybrid"]},
                    "format": {"type": "string", "enum": ["markdown", "context", "prompt", "json"], "default": "context"},
                    "trace": {"type": "boolean", "default": False},
                    "cache_ttl": {"type": "integer", "default": 0, "minimum": 0},
                },
            },
        },
        {
            "name": "guanlan_route",
            "description": (
                "Explain Guanlan's source and demand routing plan before searching. Use this when the "
                "agent needs to understand which source pools, sites, evidence roles, warnings, and "
                "fallbacks fit a Chinese web research request."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "preset": {"type": "string", "default": "general"},
                    "scope": {"type": "string"},
                    "site": {"type": "string"},
                    "sites": {"type": "array", "items": {"type": "string"}},
                    "profile": {"type": "string", "enum": ["global", "china", "hybrid"], "default": "china"},
                    "limit": {
                        "type": "integer",
                        "default": DEFAULT_RESEARCH_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_RESEARCH_LIMIT,
                    },
                    "read_top": {"type": "integer", "minimum": 0, "maximum": 10},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                },
            },
        },
        {
            "name": "guanlan_read",
            "description": "Read a public URL into Markdown with Jina/direct/search fallbacks.",
            "inputSchema": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 1},
                    "backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                    "fallback_search": {"type": "boolean", "default": True},
                    "fallback_limit": {
                        "type": "integer",
                        "default": DEFAULT_READ_FALLBACK_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_READ_FALLBACK_LIMIT,
                    },
                    "profile": {"type": "string", "enum": ["global", "china", "hybrid"], "default": "china"},
                    "cache_ttl": {"type": "integer", "default": 0, "minimum": 0},
                },
            },
        },
        {
            "name": "guanlan_research",
            "description": (
                "Build an agent-ready research evidence packet. Prefer a broad limit such as 50-100 for "
                "serious research. Set advisor=true when the user wants advice, next steps, implications, "
                "risk reminders, or cautious hypotheses about why they may be searching; the advisor block "
                "returns evidence-bound writing rules for the agent, not final advice or the user's true intent."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "preset": {"type": "string", "default": "general"},
                    "limit": {
                        "type": "integer",
                        "default": DEFAULT_RESEARCH_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_RESEARCH_LIMIT,
                    },
                    "site": {"type": "string"},
                    "sites": {"type": "array", "items": {"type": "string"}},
                    "scope": {"type": "string"},
                    "search_backend": {"type": "string", "default": "auto"},
                    "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                    "read_top": {"type": "integer", "minimum": 0, "maximum": 10},
                    "max_read_chars": {"type": "integer", "minimum": 1},
                    "profile": {"type": "string", "enum": ["global", "china", "hybrid"]},
                    "format": {"type": "string", "enum": ["markdown", "context", "prompt", "json"], "default": "markdown"},
                    "advisor": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Append 助理视角规则: evidence limits, synthesis rules, and response boundaries. "
                            "Use them to write natural advice; do not mechanically repeat the block."
                        ),
                    },
                },
            },
        },
        {
            "name": "guanlan_hotnews",
            "description": (
                "Fetch Chinese hotnews/trend lists from public endpoints. "
                "Prefer 50+ items when the agent needs a real sense of the day's flow."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "default": "today"},
                    "limit": {
                        "type": "integer",
                        "default": DEFAULT_HOTNEWS_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_HOTNEWS_LIMIT,
                    },
                    "backend": {"type": "string", "enum": ["auto", "native", "newsnow"], "default": "auto"},
                    "newsnow_base_url": {"type": "string"},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                },
            },
        },
        {
            "name": "guanlan_pulse",
            "description": (
                "Analyze topic echo from public samples with explicit caveats. "
                "Use a broad sample, usually 50-100, before summarizing tendency."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": DEFAULT_PULSE_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_PULSE_LIMIT,
                    },
                    "site": {"type": "string"},
                    "sites": {"type": "array", "items": {"type": "string"}},
                    "scope": {"type": "string"},
                    "backend": {"type": "string", "default": "auto"},
                    "profile": {"type": "string", "enum": ["global", "china", "hybrid"], "default": "china"},
                    "read_top": {"type": "integer", "default": 0, "minimum": 0, "maximum": 5},
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
                },
            },
        },
        {
            "name": "guanlan_archive_search",
            "description": (
                "Search Guanlan's local Markdown archive. "
                "Prefer a broad limit for agent context, then select the strongest evidence."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": DEFAULT_ARCHIVE_SEARCH_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_ARCHIVE_SEARCH_LIMIT,
                    },
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
                },
            },
        },
    ]


def _as_text(result) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result)


def _run_tool(name: str, arguments: dict | None = None):
    from guanlan.telemetry import telemetry_span

    with telemetry_span(name, surface="mcp"):
        return _run_tool_inner(name, arguments)


def _run_tool_inner(name: str, arguments: dict | None = None):
    """Run a Guanlan MCP tool and return text/dict/list output."""
    args = arguments or {}
    if name == "guanlan_status":
        return Guanlan(Config()).doctor_report()

    if name == "guanlan_search":
        from guanlan.webtools import (
            format_search_context,
            format_search_markdown,
            format_search_prompt,
            format_search_trace,
            search_web,
        )

        results = search_web(
            str(args.get("query", "")).strip(),
            limit=int(args.get("limit") or DEFAULT_SEARCH_LIMIT),
            site=args.get("site") or None,
            scope=args.get("scope") or None,
            backend=str(args.get("backend") or "auto"),
            profile=args.get("profile") or None,
            trace=bool(args.get("trace")),
            cache_ttl=int(args.get("cache_ttl") or 0),
        )
        output_format = str(args.get("format") or "context")
        if output_format == "json":
            return results
        if output_format == "markdown":
            text = format_search_markdown(results, title=f"观澜搜索 / {args.get('query', '')}")
            return text + (format_search_trace(results) if args.get("trace") else "")
        if output_format == "prompt":
            return format_search_prompt(results, query=str(args.get("query") or ""))
        return format_search_context(results, title=f"观澜搜索上下文 / {args.get('query', '')}")

    if name == "guanlan_route":
        from guanlan.router import build_route_plan, format_route_plan_markdown

        plan = build_route_plan(
            str(args.get("query", "")).strip(),
            preset=args.get("preset") or "general",
            scope=args.get("scope") or None,
            site=args.get("site") or None,
            sites=args.get("sites") or None,
            profile=args.get("profile") or "china",
            limit=int(args.get("limit") or DEFAULT_RESEARCH_LIMIT),
            read_top=int(args["read_top"]) if args.get("read_top") is not None else None,
        )
        if str(args.get("format") or "markdown") == "json":
            return plan.to_dict()
        return format_route_plan_markdown(plan)

    if name == "guanlan_read":
        from guanlan.webtools import read_url

        return read_url(
            str(args.get("url", "")).strip(),
            max_chars=int(args["max_chars"]) if args.get("max_chars") else None,
            backend=str(args.get("backend") or "auto"),
            fallback_search=bool(args.get("fallback_search", True)),
            fallback_limit=int(args.get("fallback_limit") or DEFAULT_READ_FALLBACK_LIMIT),
            profile=args.get("profile") or "china",
            cache_ttl=int(args.get("cache_ttl") or 0),
        )

    if name == "guanlan_research":
        from guanlan.webtools import (
            build_research_packet,
            format_advisor_context,
            format_research_markdown,
            format_research_prompt,
            format_search_context,
        )

        packet = build_research_packet(
            str(args.get("query", "")).strip(),
            preset=args.get("preset") or "general",
            limit=int(args["limit"]) if args.get("limit") is not None else None,
            site=args.get("site") or None,
            sites=args.get("sites") or None,
            scope=args.get("scope") or None,
            search_backend=str(args.get("search_backend") or "auto"),
            profile=args.get("profile") or None,
            read_top=int(args["read_top"]) if args.get("read_top") is not None else None,
            read_backend=str(args.get("read_backend") or "auto"),
            max_read_chars=int(args["max_read_chars"]) if args.get("max_read_chars") is not None else None,
            advisor=bool(args.get("advisor", False)),
        )
        output_format = str(args.get("format") or "markdown")
        if output_format == "json":
            return packet
        if output_format == "context":
            text = format_search_context(
                packet.get("selected_evidence") or packet.get("results", []),
                title=f"观澜研究上下文 / {args.get('query', '')}",
            )
            if isinstance(packet.get("advisor"), dict):
                text += "\n\n" + format_advisor_context(packet["advisor"])
            return text
        if output_format == "prompt":
            return format_research_prompt(packet)
        return format_research_markdown(packet)

    if name == "guanlan_hotnews":
        from guanlan.hotnews import fetch_hotnews, format_hotnews_markdown

        items = fetch_hotnews(
            str(args.get("source") or "today"),
            limit=int(args.get("limit") or DEFAULT_HOTNEWS_LIMIT),
            backend=str(args.get("backend") or "auto"),
            newsnow_base_url=args.get("newsnow_base_url") or None,
        )
        if str(args.get("format") or "markdown") == "json":
            return items
        return format_hotnews_markdown(items, title=f"观澜热榜 / {args.get('source') or 'today'}")

    if name == "guanlan_pulse":
        from guanlan.pulse import (
            build_pulse_report,
            format_pulse_context,
            format_pulse_markdown,
        )

        report = build_pulse_report(
            str(args.get("query", "")).strip(),
            limit=int(args.get("limit") or DEFAULT_PULSE_LIMIT),
            site=args.get("site") or None,
            sites=args.get("sites") or None,
            scope=args.get("scope") or None,
            backend=str(args.get("backend") or "auto"),
            profile=args.get("profile") or "china",
            read_top=int(args.get("read_top") or 0),
        )
        output_format = str(args.get("format") or "context")
        if output_format == "json":
            return report
        if output_format == "markdown":
            return format_pulse_markdown(report)
        return format_pulse_context(report)

    if name == "guanlan_archive_search":
        from guanlan.archive import (
            format_archive_context,
            format_archive_markdown,
            search_documents,
        )

        records = search_documents(
            str(args.get("query", "")).strip(),
            limit=int(args.get("limit") or DEFAULT_ARCHIVE_SEARCH_LIMIT),
        )
        output_format = str(args.get("format") or "context")
        if output_format == "json":
            return records
        if output_format == "markdown":
            return format_archive_markdown(records, title=f"观澜本地知识库 / {args.get('query', '')}")
        return format_archive_context(records, title=f"观澜本地知识库上下文 / {args.get('query', '')}")

    raise ValueError(f"Unknown tool: {name}")


def create_server():
    if not HAS_MCP:
        print("MCP not installed. Install: pip install guanlan[mcp]", file=sys.stderr)
        sys.exit(1)

    server = Server("guanlan")
    config = Config()
    eyes = Guanlan(config)

    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in _tool_definitions()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            # Keep this alias for local MCP clients that already call it.
            result = eyes.doctor_report() if name == "get_status" else _run_tool(name, arguments)
            return [TextContent(type="text", text=_as_text(result))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    return server


async def main():
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def cli_main():
    """Console entry point for `guanlan-mcp`."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
