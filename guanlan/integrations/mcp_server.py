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
            "description": "Search public web sources with Guanlan's China-aware ranking layer.",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 20},
                    "site": {"type": "string"},
                    "scope": {"type": "string"},
                    "backend": {"type": "string", "default": "auto"},
                    "profile": {"type": "string", "enum": ["global", "china", "hybrid"]},
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
                    "trace": {"type": "boolean", "default": False},
                    "cache_ttl": {"type": "integer", "default": 0, "minimum": 0},
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
                    "fallback_limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
                    "profile": {"type": "string", "enum": ["global", "china", "hybrid"], "default": "china"},
                    "cache_ttl": {"type": "integer", "default": 0, "minimum": 0},
                },
            },
        },
        {
            "name": "guanlan_research",
            "description": "Build an agent-ready research evidence packet.",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "preset": {"type": "string", "default": "general"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    "site": {"type": "string"},
                    "sites": {"type": "array", "items": {"type": "string"}},
                    "scope": {"type": "string"},
                    "search_backend": {"type": "string", "default": "auto"},
                    "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                    "read_top": {"type": "integer", "minimum": 0, "maximum": 10},
                    "max_read_chars": {"type": "integer", "minimum": 1},
                    "profile": {"type": "string", "enum": ["global", "china", "hybrid"]},
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "markdown"},
                },
            },
        },
        {
            "name": "guanlan_hotnews",
            "description": "Fetch Chinese hotnews/trend lists from public endpoints.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "default": "baidu"},
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                },
            },
        },
    ]


def _as_text(result) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result)


def _run_tool(name: str, arguments: dict | None = None):
    """Run a Guanlan MCP tool and return text/dict/list output."""
    args = arguments or {}
    if name == "guanlan_status":
        return Guanlan(Config()).doctor_report()

    if name == "guanlan_search":
        from guanlan.webtools import (
            format_search_context,
            format_search_markdown,
            format_search_trace,
            search_web,
        )

        results = search_web(
            str(args.get("query", "")).strip(),
            limit=int(args.get("limit") or 8),
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
        return format_search_context(results, title=f"观澜搜索上下文 / {args.get('query', '')}")

    if name == "guanlan_read":
        from guanlan.webtools import read_url

        return read_url(
            str(args.get("url", "")).strip(),
            max_chars=int(args["max_chars"]) if args.get("max_chars") else None,
            backend=str(args.get("backend") or "auto"),
            fallback_search=bool(args.get("fallback_search", True)),
            fallback_limit=int(args.get("fallback_limit") or 5),
            profile=args.get("profile") or "china",
            cache_ttl=int(args.get("cache_ttl") or 0),
        )

    if name == "guanlan_research":
        from guanlan.webtools import (
            build_research_packet,
            format_research_markdown,
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
        )
        output_format = str(args.get("format") or "markdown")
        if output_format == "json":
            return packet
        if output_format == "context":
            return format_search_context(packet.get("results", []), title=f"观澜研究上下文 / {args.get('query', '')}")
        return format_research_markdown(packet)

    if name == "guanlan_hotnews":
        from guanlan.hotnews import fetch_hotnews, format_hotnews_markdown

        items = fetch_hotnews(str(args.get("source") or "baidu"), limit=int(args.get("limit") or 10))
        if str(args.get("format") or "markdown") == "json":
            return items
        return format_hotnews_markdown(items, title=f"观澜热榜 / {args.get('source') or 'baidu'}")

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
