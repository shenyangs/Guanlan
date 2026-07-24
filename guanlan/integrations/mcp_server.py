# -*- coding: utf-8 -*-
"""观澜 / Guanlan MCP Server.

Run: python -m guanlan.integrations.mcp_server

The MCP surface is intentionally read-first: it exposes search, read, research,
hotnews, and status tools for AI agents without adding write/social actions.
"""

import asyncio
import json
import sys

from guanlan.errors import format_user_error
from guanlan.limits import (
    DEFAULT_ARCHIVE_SEARCH_LIMIT,
    DEFAULT_FEEDS_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_MCP_RESEARCH_READ_TOP,
    DEFAULT_PULSE_LIMIT,
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    MAX_AGENT_RESEARCH_READ_TOP,
    MAX_ARCHIVE_SEARCH_LIMIT,
    MAX_FEEDS_LIMIT,
    MAX_HOTNEWS_LIMIT,
    MAX_MCP_RESEARCH_READ_TOP,
    MAX_PULSE_LIMIT,
    MAX_READ_FALLBACK_LIMIT,
    MAX_RESEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
)
from guanlan.tool_invocation import (
    normalize_agent_request,
    normalize_daily_request,
    normalize_map_request,
    normalize_read_request,
    normalize_research_request,
    normalize_route_request,
    normalize_search_request,
    normalize_workflow_request,
)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


def _doctor_report() -> str:
    from guanlan.config import Config
    from guanlan.doctor import check_all, format_report

    config = Config()
    return format_report(check_all(config))


def _tool_definitions() -> list[dict]:
    """Return MCP tool definitions as plain dictionaries for easy testing."""
    return _apply_registry_tool_definitions([
        {
            "name": "guanlan_status",
            "description": (
                "Get Guanlan channel status and health summary. If the user asks what Guanlan can do, "
                "call guanlan_capabilities instead."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "guanlan_capabilities",
            "description": (
                "Show Guanlan's capability map: when to use search, route, read, research, advisor, "
                "hotnews, pulse, archive, local-LLM prompt, agent auto-plan, status, and their safety boundaries. "
                "Call this first when the user asks what Guanlan can do or which Guanlan tool to use."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                },
            },
        },
        {
            "name": "guanlan_agent",
            "description": (
                "Auto-plan or review the smallest safe Guanlan command chain for an agent. Use phase=plan "
                "when the agent is unsure which Guanlan tool to run; use phase=review after a Guanlan result "
                "to return next_decision=answer/continue/repair/authorize_browser without saying the tool failed."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "phase": {"type": "string", "enum": ["plan", "review"], "default": "plan"},
                    "observation": {
                        "type": "object",
                        "description": "Structured Guanlan result/error summary for phase=review.",
                    },
                    "mode": {"type": "string", "enum": ["auto", "quick", "deep", "fresh"], "default": "auto"},
                    "preset": {"type": "string", "default": "general"},
                    "scope": {"type": "string"},
                    "site": {"type": "string"},
                    "sites": {"type": "array", "items": {"type": "string"}},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                    "limit": {"type": "integer", "default": DEFAULT_SEARCH_LIMIT, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
                    "read_top": {"type": "integer", "minimum": 0, "maximum": MAX_AGENT_RESEARCH_READ_TOP},
                    "max_commands": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "json"},
                },
            },
        },
        {
            "name": "guanlan_search",
            "description": (
                "Search public web sources with Guanlan's China-aware ranking layer. "
                "For agent research, prefer a broad limit such as 80-100 and filter after retrieval. "
                "If an MCP client aborts the call, retry once with cache_ttl=3600 or a single backend; "
                "do not shrink the evidence pool first."
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
                    "strict_scope": {"type": "boolean", "default": False},
                    "backend": {"type": "string", "default": "auto"},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"]},
                    "format": {"type": "string", "enum": ["markdown", "context", "prompt", "json"], "default": "context"},
                    "trace": {"type": "boolean", "default": False},
                    "cache_ttl": {"type": "integer", "default": 0, "minimum": 0},
                },
            },
        },
        {
            "name": "guanlan_map",
            "description": (
                "Discover public candidate URLs inside a known site using robots.txt sitemap hints, sitemap XML, "
                "and page links. Use this before guanlan_read when the user knows a site/domain and needs docs, "
                "pricing, announcements, contact pages, or other site-local entrypoints. This is URL discovery, "
                "not whole-web search; set read_top=1-5 to read representative pages with quality reports."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {"type": "string"},
                    "query": {"type": "string", "default": ""},
                    "limit": {
                        "type": "integer",
                        "default": DEFAULT_SEARCH_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_SEARCH_LIMIT,
                    },
                    "include_subdomains": {"type": "boolean", "default": False},
                    "sitemap": {"type": "string", "enum": ["auto", "only", "skip"], "default": "auto"},
                    "include_patterns": {"type": "array", "items": {"type": "string"}},
                    "exclude_patterns": {"type": "array", "items": {"type": "string"}},
                    "timeout": {"type": "integer", "default": 8, "minimum": 1, "maximum": 30},
                    "read_top": {"type": "integer", "default": 0, "minimum": 0, "maximum": 5},
                    "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                    "max_read_chars": {"type": "integer", "default": 4000, "minimum": 1, "maximum": 20000},
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
                },
            },
        },
        {
            "name": "guanlan_stock",
            "description": (
                "Fetch structured public stock, ETF, fund, and market data without reading dynamic finance pages: quote/NAV, detail, "
                "fundflow, news, plate, rank, index, search, or plan. Use this first whenever users ask "
                "about stocks, ETFs, funds, NAV, stock prices, market indices, fund flow, disclosures, Xueqiu/Guba sentiment, "
                "or capital-market risk; do not start by reading dynamic finance pages. Output is evidence "
                "data, not investment advice."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["plan", "quote", "detail", "fundflow", "news", "plate", "rank", "index", "search"],
                        "default": "quote",
                    },
                    "target": {"type": "string", "description": "Stock code/name/ticker, e.g. 600519, 贵州茅台, NVDA"},
                    "query": {"type": "string", "description": "Stock search keyword or noisy finance query"},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                    "news_limit": {"type": "integer", "default": 12, "minimum": 1, "maximum": 50},
                    "sort": {"type": "string", "default": "turnover"},
                    "direct": {"type": "string", "enum": ["down", "up"], "default": "down"},
                    "offset": {"type": "integer", "default": 0, "minimum": 0},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
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
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
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
            "name": "guanlan_workflow",
            "description": (
                "Decide whether a user request should stay on a light search/read path or move to "
                "research/compare/timeline/dossier/investigate. Use this to avoid overthinking basic "
                "search while still escalating serious research."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "command": {
                        "type": "string",
                        "enum": ["search", "read", "route", "research", "compare", "timeline", "dossier", "investigate"],
                        "default": "search",
                    },
                    "preset": {"type": "string", "default": "general"},
                    "scope": {"type": "string"},
                    "site": {"type": "string"},
                    "sites": {"type": "array", "items": {"type": "string"}},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                    "limit": {"type": "integer", "default": DEFAULT_SEARCH_LIMIT, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
                    "read_top": {"type": "integer", "minimum": 0, "maximum": 10},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                },
            },
        },
        {
            "name": "guanlan_page_diagnose",
            "description": (
                "Diagnose whether a public page is readable evidence, a dynamic shell, an access gate, "
                "or search-fallback-only context. Use this before repeatedly calling read on weak pages."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 4000, "minimum": 1},
                    "backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                    "fallback_search": {"type": "boolean", "default": True},
                    "fallback_limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                    "strict": {"type": "boolean", "default": False},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                },
            },
        },
        {
            "name": "guanlan_browser_assist_plan",
            "description": (
                "Build a read-only OpenGuanlan visible-page evidence task after Guanlan finds that public "
                "reading is weak, blocked, dynamic, or search-fallback-only. The tool only returns a plan; "
                "the Agent must ask the user before reading browser-visible content. Target private/account "
                "pages require separate explicit authorization; cookies, tokens, keychain/storage/profile "
                "credential material must not enter the browser-visible payload, and write actions are forbidden."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {"type": "string"},
                    "page_type": {"type": "string", "default": "access_gate"},
                    "signals": {"type": "array", "items": {"type": "string"}},
                    "candidate_urls": {"type": "array", "items": {"type": "string"}},
                    "platform": {"type": "string"},
                    "max_pages": {"type": "integer", "default": 3, "minimum": 1, "maximum": 20},
                    "max_chars_per_page": {"type": "integer", "default": 3000, "minimum": 1, "maximum": 20000},
                    "min_visible_items": {
                        "type": "integer",
                        "default": 0,
                        "minimum": 0,
                        "maximum": 500,
                        "description": "Minimum visible list/comment/search items the host Agent should try to collect before marking partial.",
                    },
                    "task_goal": {"type": "string"},
                    "force": {"type": "boolean", "default": True},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "json"},
                },
            },
        },
        {
            "name": "guanlan_browser_assist_run",
            "description": (
                "Prepare or run a user-authorized OpenGuanlan browser-assist task. Default openguanlan mode "
                "returns the host Agent browser visible-page execution contract without requiring an extension "
                "or daemon; openguanlan-bridge and open-cli remain explicit opt-in sidecar/compatibility flows. "
                "Credential material is outside the payload boundary."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {"type": "string"},
                    "adapter": {"type": "string", "default": "openguanlan"},
                    "execute": {"type": "boolean", "default": False},
                    "command_template": {"type": "string"},
                    "timeout": {"type": "integer", "default": 90, "minimum": 1, "maximum": 600},
                    "output": {"type": "string"},
                    "page_type": {"type": "string", "default": "access_gate"},
                    "signals": {"type": "array", "items": {"type": "string"}},
                    "platform": {"type": "string"},
                    "max_pages": {"type": "integer", "default": 3, "minimum": 1, "maximum": 20},
                    "max_chars_per_page": {"type": "integer", "default": 3000, "minimum": 1, "maximum": 20000},
                    "min_visible_items": {
                        "type": "integer",
                        "default": 0,
                        "minimum": 0,
                        "maximum": 500,
                        "description": "Minimum visible list/comment/search items the host Agent should try to collect before marking partial.",
                    },
                    "task_goal": {"type": "string"},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "json"},
                },
            },
        },
        {
            "name": "guanlan_recipe",
            "description": (
                "List or render reusable Guanlan research recipes, such as university advisor lookup, "
                "finance risk, product reputation, entertainment pulse, security advisory, tech radar, and WPS/AI Office radar. "
                "Use recipes when the agent needs a stable multi-step workflow instead of one generic search."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "enum": ["list", "show", "run"], "default": "list"},
                    "recipe_id": {"type": "string", "description": "Recipe id, e.g. finance-risk"},
                    "query": {"type": "string", "description": "Research query for command=run"},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                    "limit": {"type": "integer", "default": DEFAULT_RESEARCH_LIMIT, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
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
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                    "cache_ttl": {"type": "integer", "default": 0, "minimum": 0},
                    "format": {"type": "string", "enum": ["raw", "json", "context"], "default": "raw"},
                },
            },
        },
        {
            "name": "guanlan_research",
            "description": (
                "Guarded/heavy evidence-packet tool. Do not use as the first step for ordinary lookups; "
                "prefer guanlan_search plus guanlan_read, or guanlan_agent to plan a safe chain. Use this "
                "only when the user explicitly needs a reusable research packet, deep synthesis, or when a "
                "prior search/read pass still lacks source-role coverage. Prefer a broad limit such as 80-100 "
                "for serious research, but keep read_top low on MCP clients and follow with guanlan_read for "
                "specific URLs. Set advisor=true when the user wants advice, next steps, implications, "
                "risk reminders, or cautious hypotheses about why they may be searching; the advisor block "
                "returns evidence-bound writing rules for the agent, not final advice or the user's true intent. "
                "Use an outer timeout budget of 180-300 seconds for research; if the host field is named "
                "timeout_ms or timeout_milliseconds, convert explicitly, for example 300 seconds = 300000 ms. "
                "On timeout, retry once with cache_ttl=3600 where available or run guanlan_search/guanlan_read "
                "instead of increasing read_top."
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
                    "read_top": {
                        "type": "integer",
                        "default": DEFAULT_MCP_RESEARCH_READ_TOP,
                        "minimum": 0,
                        "maximum": MAX_MCP_RESEARCH_READ_TOP,
                        "description": "MCP guarded default is 0; use guanlan_read for selected URLs instead of making research read many pages.",
                    },
                    "max_read_chars": {"type": "integer", "minimum": 1},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"]},
                    "format": {"type": "string", "enum": ["markdown", "context", "prompt", "json"], "default": "markdown"},
                    "advisor": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Append 助理视角规则: evidence limits, synthesis rules, and response boundaries. "
                            "Use them to write natural advice; do not mechanically repeat the block."
                        ),
                    },
                    "advisor_style": {
                        "type": "string",
                        "enum": ["brief", "decision", "risk", "strategy"],
                        "default": "brief",
                        "description": "Style for advisor guidance when advisor=true.",
                    },
                },
            },
        },
        {
            "name": "guanlan_investigate",
            "description": (
                "Run Guanlan's explicit upper-layer investigation workflow. This composes route + "
                "research evidence packets and returns workflow_decision metadata; it does not change "
                "the lightweight behavior of guanlan_search."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "preset": {"type": "string", "default": "general"},
                    "limit": {"type": "integer", "default": DEFAULT_RESEARCH_LIMIT, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
                    "read_top": {"type": "integer", "minimum": 0, "maximum": 10},
                    "search_backend": {"type": "string", "default": "auto"},
                    "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                    "max_read_chars": {"type": "integer", "minimum": 1},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"]},
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
                    "advisor": {"type": "boolean", "default": True},
                    "advisor_style": {"type": "string", "enum": ["brief", "decision", "risk", "strategy"], "default": "strategy"},
                },
            },
        },
        {
            "name": "guanlan_compare",
            "description": (
                "Compare two or more subjects through separate Guanlan evidence packets. Use this when the "
                "user asks for 对比, compare, 竞品, alternatives, or pros/cons with source boundaries."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["subjects"],
                "properties": {
                    "subjects": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                    "focus": {"type": "string"},
                    "preset": {"type": "string", "default": "general"},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                    "limit": {
                        "type": "integer",
                        "default": DEFAULT_RESEARCH_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_RESEARCH_LIMIT,
                    },
                    "read_top": {"type": "integer", "default": 0, "minimum": 0, "maximum": 10},
                    "search_backend": {"type": "string", "default": "auto"},
                    "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                    "max_read_chars": {"type": "integer", "minimum": 1},
                    "select_top": {"type": "integer", "default": 6, "minimum": 1, "maximum": 20},
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
                },
            },
        },
        {
            "name": "guanlan_timeline",
            "description": (
                "Extract a dated timeline from a broad Guanlan evidence packet. Use this for 发展历程, "
                "事件脉络, 最近进展, release history, or when recency matters."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "preset": {"type": "string", "default": "general"},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                    "limit": {"type": "integer", "default": 80, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
                    "read_top": {"type": "integer", "default": 0, "minimum": 0, "maximum": 10},
                    "search_backend": {"type": "string", "default": "auto"},
                    "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                    "max_read_chars": {"type": "integer", "minimum": 1},
                    "max_events": {"type": "integer", "default": 20, "minimum": 1, "maximum": 50},
                    "order": {"type": "string", "enum": ["desc", "asc"], "default": "desc"},
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
                },
            },
        },
        {
            "name": "guanlan_dossier",
            "description": (
                "Build a structured dossier for one entity or issue: source mix, official/material/sample "
                "sections, timeline hints, open questions, and next commands."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["entity"],
                "properties": {
                    "entity": {"type": "string"},
                    "focus": {"type": "string"},
                    "preset": {"type": "string", "default": "general"},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                    "limit": {"type": "integer", "default": 80, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
                    "read_top": {"type": "integer", "default": 2, "minimum": 0, "maximum": 10},
                    "search_backend": {"type": "string", "default": "auto"},
                    "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                    "max_read_chars": {"type": "integer", "default": 2400, "minimum": 1},
                    "select_top": {"type": "integer", "default": 10, "minimum": 1, "maximum": 20},
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
                },
            },
        },
        {
            "name": "guanlan_hotnews",
            "description": (
                "Fetch Chinese hotnews/trend lists from public endpoints. "
                "Prefer 80+ items when the agent needs a real sense of the day's flow."
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
                    "backend": {"type": "string", "enum": ["auto", "native", "newsnow", "vvhan", "uapis", "tophub"], "default": "auto"},
                    "newsnow_base_url": {"type": "string"},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                    "trends": {"type": "boolean", "default": False},
                    "brief": {"type": "boolean", "default": False},
                    "compact": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return a smaller JSON payload while keeping evidence_role, source_card, and risk_tags.",
                    },
                },
            },
        },
        {
            "name": "guanlan_pulse",
            "description": (
                "Analyze topic echo from public samples with explicit caveats. "
                "Use a broad sample, usually 80-100, before summarizing tendency."
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
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                    "read_top": {"type": "integer", "default": 0, "minimum": 0, "maximum": 5},
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
                },
            },
        },
        {
            "name": "guanlan_feeds",
            "description": (
                "Discover high-quality public RSS content and source catalogs. "
                "Use source=curated for curated reading RSS, curated-sources for the OPML catalog, "
                "baidu-rss for dynamic Baidu hot topics, wechat-rss for dynamic WeChat hot articles, "
                "list for source routing metadata, or pass a direct RSS/Atom URL. Prefer 80 items for discovery."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "default": "curated"},
                    "limit": {
                        "type": "integer",
                        "default": DEFAULT_FEEDS_LIMIT,
                        "minimum": 1,
                        "maximum": MAX_FEEDS_LIMIT,
                    },
                    "language": {"type": "string", "enum": ["zh", "en"], "default": "zh"},
                    "category": {"type": "string", "enum": ["programming", "ai", "product", "business"]},
                    "resource_type": {"type": "string", "enum": ["article", "podcast", "video", "twitter"]},
                    "featured": {"type": "boolean", "default": False},
                    "min_score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "keyword": {"type": "string"},
                    "watchlist": {
                        "type": "string",
                        "description": "Optional JSON/JSONL/plain-text RSS watchlist path for source=watchlist.",
                    },
                    "watchlist_path": {
                        "type": "string",
                        "description": "Alias for watchlist; kept for MCP clients that prefer explicit *_path names.",
                    },
                    "time_filter": {"type": "string", "enum": ["1d", "3d", "1w", "1m", "3m"]},
                    "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
                    "compact": {
                        "type": "boolean",
                        "default": False,
                        "description": "For JSON output, return compact rows with source/evidence metadata.",
                    },
                },
            },
        },
        {
            "name": "guanlan_daily",
            "description": (
                "Build a Guanlan-native daily brief by combining route/search or watch, RSS discovery, "
                "and hotnews trend signals into one evidence-bound report. Use this for daily industry, "
                "brand, AI, PR, or public-web briefings instead of assembling separate hotnews/feeds/search "
                "calls by hand."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional daily topic; omit for a broader public brief."},
                    "watch_id": {"type": "string", "description": "Optional saved watch intent id to reuse as the daily subject."},
                    "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                    "scope": {"type": "string"},
                    "site": {"type": "string"},
                    "preset": {"type": "string", "default": "general"},
                    "lens": {"type": "string"},
                    "feed_source": {"type": "string", "default": "auto"},
                    "watchlist": {"type": "string"},
                    "watchlist_path": {"type": "string"},
                    "hotnews_source": {"type": "string", "default": "today"},
                    "backend": {"type": "string", "default": "auto"},
                    "limit": {"type": "integer", "default": 12, "minimum": 1, "maximum": 30},
                    "search_limit": {"type": "integer", "default": DEFAULT_SEARCH_LIMIT, "minimum": 1, "maximum": MAX_SEARCH_LIMIT},
                    "feeds_limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": MAX_FEEDS_LIMIT},
                    "hotnews_limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": MAX_HOTNEWS_LIMIT},
                    "read_top": {"type": "integer", "default": 3, "minimum": 0, "maximum": 8},
                    "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                    "max_read_chars": {"type": "integer", "default": 1800, "minimum": 300, "maximum": 8000},
                    "overflow_limit": {"type": "integer", "default": 20, "minimum": 0, "maximum": 80},
                    "time_window": {"type": "string", "enum": ["today", "24h", "3d", "7d"], "default": "3d"},
                    "edition": {"type": "string", "enum": ["brand", "market", "reputation", "general"], "default": "brand"},
                    "record_history": {"type": "boolean", "default": False},
                    "history_path": {"type": "string"},
                    "compare_days": {"type": "integer", "default": 0, "minimum": 0, "maximum": 365},
                    "cache_ttl": {"type": "integer", "default": 0, "minimum": 0},
                    "no_search": {"type": "boolean", "default": False},
                    "no_feeds": {"type": "boolean", "default": False},
                    "no_hotnews": {"type": "boolean", "default": False},
                    "store": {"type": "string"},
                    "format": {"type": "string", "enum": ["markdown", "context", "json", "html", "im"], "default": "markdown"},
                },
            },
        },
        {
            "name": "guanlan_archive_search",
            "description": (
                "Search Guanlan's local Markdown archive. This is Guanlan's local memory layer, not web search. "
                "Prefer a broad limit for agent context, then select the strongest evidence. "
                "If the user asks for RAG/local-model/Agent Wiki context, use guanlan_archive_context. "
                "Before relying on archive as long-term memory, call guanlan_archive_verify."
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
                    "trace": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include matched terms, fields, and retrieval boundary for archive search.",
                    },
                },
            },
        },
        {
            "name": "guanlan_archive_context",
            "description": (
                "Build prompt-ready context from Guanlan's local archive for an Agent, LM Studio/Ollama, "
                "RAG, or AI Agent Wiki workflow. Only uses already archived local documents; missing results "
                "do not mean the wider web has no evidence."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "minimum": 1,
                        "maximum": MAX_ARCHIVE_SEARCH_LIMIT,
                    },
                    "min_quality": {"type": "integer", "default": 0, "minimum": 0, "maximum": 100},
                    "max_chars": {"type": "integer", "default": 1200, "minimum": 120, "maximum": 8000},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                },
            },
        },
        {
            "name": "guanlan_archive_verify",
            "description": (
                "Verify Guanlan archive health before using it as Agent memory, AI Agent Wiki, or RAG input. "
                "Checks index consistency, empty content, sample recall, and RAG/Wiki readiness."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 50},
                    "min_quality": {"type": "integer", "default": 60, "minimum": 0, "maximum": 100},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                },
            },
        },
    ])


def _apply_registry_tool_definitions(tools: list[dict]) -> list[dict]:
    """Project canonical registry descriptions/schemas onto MCP definitions."""

    try:
        from guanlan.tool_registry import tool_by_name
    except Exception:  # pragma: no cover - defensive fallback for broken installs
        return tools

    projected: list[dict] = []
    for tool in tools:
        spec = tool_by_name(str(tool.get("name") or ""))
        if spec is None:
            projected.append(tool)
            continue
        payload = spec.to_dict()
        next_tool = dict(tool)
        next_tool["description"] = str(spec.mcp_description or tool.get("description") or payload.get("mcp_description") or "")
        next_tool["inputSchema"] = spec.request_schema or tool.get("inputSchema") or {"type": "object", "properties": {}}
        projected.append(next_tool)
    return projected


def _as_text(result) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result)


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _browser_assist_mcp_execution_requested(args: dict) -> bool:
    if _truthy(args.get("execute")):
        return True
    for key in ("command_template", "output"):
        if str(args.get(key) or "").strip():
            return True
    return False


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def _run_tool(name: str, arguments: dict | None = None):
    from guanlan.telemetry import telemetry_span

    with telemetry_span(name, surface="mcp"):
        return _run_tool_inner(name, arguments)


def _run_tool_inner(name: str, arguments: dict | None = None):
    """Run a Guanlan MCP tool and return text/dict/list output."""
    args = arguments or {}
    if name == "guanlan_status":
        return _doctor_report()

    if name == "guanlan_capabilities":
        from guanlan.capabilities import format_capabilities_markdown, list_capabilities

        if str(args.get("format") or "markdown") == "json":
            return list_capabilities()
        return format_capabilities_markdown()

    if name == "guanlan_agent":
        from guanlan.agent_planner import (
            build_agent_plan_v2,
            format_agent_plan_v2_markdown,
            review_agent_observation,
        )

        request = normalize_agent_request(args)
        common_kwargs = {key: value for key, value in request.items() if key not in {"query", "phase"}}
        if request["phase"] == "review":
            plan = review_agent_observation(
                request["query"],
                args.get("observation") or {},
                **common_kwargs,
            )
        else:
            plan = build_agent_plan_v2(
                request["query"],
                **common_kwargs,
            )
        if str(args.get("format") or "json") == "markdown":
            return format_agent_plan_v2_markdown(plan)
        return plan

    if name == "guanlan_search":
        from guanlan.agent_planner import build_agent_followup, format_agent_followup_context
        from guanlan.web.renderers import (
            format_search_context,
            format_search_markdown,
            format_search_prompt,
            format_search_trace,
        )
        from guanlan.web.search import (
            search_web,
        )

        request = normalize_search_request(args)
        query = request.pop("query")
        results = search_web(query, **request)
        diagnostics = getattr(results, "diagnostics", {}) or {}
        followup = build_agent_followup(
            "guanlan_search",
            {
                "results": results,
                "limit": request["limit"],
                "diagnostics": diagnostics,
            },
            query=query,
        )
        output_format = str(args.get("format") or "context")
        if output_format == "json":
            return {"results": results, "diagnostics": diagnostics, "agent_followup": followup}
        if output_format == "markdown":
            text = format_search_markdown(results, title=f"观澜搜索 / {args.get('query', '')}")
            return text + (format_search_trace(results) if args.get("trace") else "")
        if output_format == "prompt":
            return format_search_prompt(results, query=str(args.get("query") or ""))
        followup_text = format_agent_followup_context(followup)
        text = format_search_context(results, title=f"观澜搜索上下文 / {args.get('query', '')}")
        return text + (f"\n\n{followup_text}" if followup_text else "")

    if name == "guanlan_map":
        from guanlan.site_map import (
            build_site_map,
            format_site_map_context,
            format_site_map_markdown,
        )

        request = normalize_map_request(args)
        url = request.pop("url")
        packet = build_site_map(url, **request)
        output_format = str(args.get("format") or "context")
        if output_format == "json":
            return packet
        if output_format == "markdown":
            return format_site_map_markdown(packet)
        return format_site_map_context(packet)

    if name == "guanlan_stock":
        from guanlan.stock_cli import run_stock_tool

        return run_stock_tool(args)

    if name == "guanlan_route":
        from guanlan.router import build_route_plan, format_route_plan_markdown
        from guanlan.workflow_decider import decide_workflow, format_workflow_decision_markdown

        request = normalize_route_request(args)
        plan = build_route_plan(**request)
        workflow_kwargs = {key: value for key, value in request.items() if key != "query"}
        decision = decide_workflow(
            request["query"],
            command="route",
            **workflow_kwargs,
            route_plan=plan,
        )
        if str(args.get("format") or "markdown") == "json":
            payload = plan.to_dict()
            payload["workflow_decision"] = decision.to_dict()
            return payload
        return format_route_plan_markdown(plan) + "\n\n" + format_workflow_decision_markdown(decision)

    if name == "guanlan_workflow":
        from guanlan.workflow_decider import decide_workflow, format_workflow_decision_markdown

        request = normalize_workflow_request(args)
        query = request.pop("query")
        decision = decide_workflow(query, **request)
        if str(args.get("format") or "markdown") == "json":
            return decision.to_dict()
        return format_workflow_decision_markdown(decision)

    if name == "guanlan_page_diagnose":
        from guanlan.page_diagnosis import diagnose_page, format_page_diagnosis_markdown

        payload = diagnose_page(
            str(args.get("url", "")).strip(),
            max_chars=int(args.get("max_chars") or 4000),
            backend=str(args.get("backend") or "auto"),
            fallback_search=bool(args.get("fallback_search", True)),
            fallback_limit=int(args.get("fallback_limit") or 5),
            profile=args.get("profile") or "china",
            strict=bool(args.get("strict", False)),
        )
        if str(args.get("format") or "markdown") == "json":
            return payload
        return format_page_diagnosis_markdown(payload)

    if name == "guanlan_browser_assist_plan":
        from guanlan.browser_assist import build_browser_assist_plan, format_browser_assist_markdown

        payload = build_browser_assist_plan(
            str(args.get("url", "")).strip(),
            page_type=str(args.get("page_type") or "access_gate"),
            signals=[str(item) for item in args.get("signals", [])] if isinstance(args.get("signals"), list) else [],
            candidate_urls=[str(item) for item in args.get("candidate_urls", [])]
            if isinstance(args.get("candidate_urls"), list)
            else None,
            max_pages=max(int(args.get("max_pages") or 3), 1),
            max_chars_per_page=max(int(args.get("max_chars_per_page") or 3000), 1),
            min_visible_items=max(int(args.get("min_visible_items") or 0), 0),
            task_goal=str(args.get("task_goal") or ""),
            force=bool(args.get("force", True)),
        )
        if args.get("platform"):
            payload["platform"] = str(args.get("platform"))
            if isinstance(payload.get("browser_assist_task"), dict):
                payload["browser_assist_task"]["platform"] = str(args.get("platform"))
        if str(args.get("format") or "json") == "json":
            return payload
        return format_browser_assist_markdown(payload)

    if name == "guanlan_browser_assist_run":
        from guanlan.browser_assist import (
            format_browser_assist_run_markdown,
            run_browser_assist_adapter,
        )

        if _browser_assist_mcp_execution_requested(args):
            payload = {
                "error": "browser_assist_execution_not_allowed_mcp",
                "status": "rejected",
                "message": (
                    "MCP guanlan_browser_assist_run 只返回浏览器补证执行契约；外部命令执行仅限本地 CLI 显式调用。"
                ),
                "boundary": "fail_closed; execute/command_template/output are CLI-only fields",
            }
            if str(args.get("format") or "json") == "json":
                return payload
            return format_browser_assist_run_markdown(payload)
        payload = run_browser_assist_adapter(
            str(args.get("url", "")).strip(),
            adapter=str(args.get("adapter") or "openguanlan"),
            execute=False,
            command_template="",
            timeout=max(int(args.get("timeout") or 90), 1),
            output_path="",
            page_type=str(args.get("page_type") or "access_gate"),
            signals=[str(item) for item in args.get("signals", [])] if isinstance(args.get("signals"), list) else [],
            platform=str(args.get("platform") or ""),
            max_pages=max(int(args.get("max_pages") or 3), 1),
            max_chars_per_page=max(int(args.get("max_chars_per_page") or 3000), 1),
            min_visible_items=max(int(args.get("min_visible_items") or 0), 0),
            task_goal=str(args.get("task_goal") or ""),
        )
        if str(args.get("format") or "json") == "json":
            return payload
        return format_browser_assist_run_markdown(payload)

    if name == "guanlan_recipe":
        from guanlan.recipes import (
            build_recipe_plan,
            format_recipe_list_markdown,
            format_recipe_plan_markdown,
            get_recipe,
            list_recipes,
        )

        command = str(args.get("command") or "list")
        output_format = str(args.get("format") or "markdown")
        if command == "list":
            recipes = list_recipes()
            return recipes if output_format == "json" else format_recipe_list_markdown(recipes)
        if command == "show":
            recipe = get_recipe(str(args.get("recipe_id") or "")).to_dict()
            return recipe if output_format == "json" else format_recipe_list_markdown([recipe])
        if command == "run":
            plan = build_recipe_plan(
                str(args.get("recipe_id") or ""),
                str(args.get("query") or "").strip(),
                profile=str(args.get("profile") or "china"),
                limit=int(args.get("limit") or DEFAULT_RESEARCH_LIMIT),
                read_top=int(args["read_top"]) if args.get("read_top") is not None else None,
            )
            return plan if output_format == "json" else format_recipe_plan_markdown(plan)
        raise ValueError(f"unknown recipe command: {command}")

    if name == "guanlan_read":
        from guanlan.agent_planner import build_agent_followup, format_agent_followup_context
        from guanlan.web.read import read_url, read_url_with_trace

        request = normalize_read_request(args)
        if str(args.get("format") or "raw") == "json":
            packet = read_url_with_trace(**request)
            packet["agent_followup"] = build_agent_followup("guanlan_read", packet)
            return packet
        content = read_url(**request)
        followup = build_agent_followup("guanlan_read", {"url": request["url"], "content": content})
        if str(args.get("format") or "raw") == "context":
            followup_text = format_agent_followup_context(followup)
            return content + (f"\n\n{followup_text}" if followup_text else "")
        return content

    if name == "guanlan_research":
        from guanlan.agent_planner import build_agent_followup, format_agent_followup_context
        from guanlan.web.renderers import (
            format_advisor_context,
            format_claim_ledger_context,
            format_evidence_audit_context,
            format_research_markdown,
            format_research_prompt,
            format_search_context,
        )
        from guanlan.web.research import build_research_packet

        request = normalize_research_request(args)
        query = request.pop("query")
        packet = build_research_packet(query, **request)
        packet["agent_followup"] = build_agent_followup("guanlan_research", packet, query=query)
        output_format = str(args.get("format") or "markdown")
        if output_format == "json":
            return packet
        if output_format == "context":
            text = format_search_context(
                packet.get("selected_evidence") or packet.get("results", []),
                title=f"观澜研究上下文 / {args.get('query', '')}",
            )
            if isinstance(packet.get("evidence_audit"), dict):
                text += "\n\n" + format_evidence_audit_context(packet["evidence_audit"])
            if isinstance(packet.get("claim_ledger"), dict):
                text += "\n\n" + format_claim_ledger_context(packet["claim_ledger"])
            if isinstance(packet.get("advisor"), dict):
                text += "\n\n" + format_advisor_context(packet["advisor"])
            followup_text = format_agent_followup_context(packet.get("agent_followup"))
            if followup_text:
                text += "\n\n" + followup_text
            return text
        if output_format == "prompt":
            return format_research_prompt(packet)
        return format_research_markdown(packet)

    if name == "guanlan_investigate":
        from guanlan.investigation import (
            build_investigation_packet,
            format_investigation_context,
            format_investigation_markdown,
        )

        packet = build_investigation_packet(
            str(args.get("query", "")).strip(),
            preset=str(args.get("preset") or "general"),
            limit=int(args["limit"]) if args.get("limit") is not None else None,
            read_top=int(args["read_top"]) if args.get("read_top") is not None else None,
            search_backend=str(args.get("search_backend") or "auto"),
            read_backend=str(args.get("read_backend") or "auto"),
            max_read_chars=int(args["max_read_chars"]) if args.get("max_read_chars") is not None else None,
            profile=args.get("profile") or None,
            advisor=bool(args.get("advisor", True)),
            advisor_style=str(args.get("advisor_style") or "strategy"),
        )
        output_format = str(args.get("format") or "context")
        if output_format == "json":
            return packet
        if output_format == "markdown":
            return format_investigation_markdown(packet)
        return format_investigation_context(packet)

    if name == "guanlan_compare":
        from guanlan.research_workflows import (
            build_compare_report,
            format_compare_markdown,
            format_workflow_context,
        )

        subjects = args.get("subjects") if isinstance(args.get("subjects"), list) else []
        report = build_compare_report(
            [str(item) for item in subjects],
            focus=str(args.get("focus") or ""),
            preset=str(args.get("preset") or "general"),
            profile=args.get("profile") or "china",
            limit=int(args.get("limit") or DEFAULT_RESEARCH_LIMIT),
            read_top=int(args.get("read_top") or 0),
            search_backend=str(args.get("search_backend") or "auto"),
            read_backend=str(args.get("read_backend") or "auto"),
            max_read_chars=int(args["max_read_chars"]) if args.get("max_read_chars") is not None else None,
            select_top=int(args.get("select_top") or 6),
        )
        output_format = str(args.get("format") or "context")
        if output_format == "json":
            return report
        if output_format == "markdown":
            return format_compare_markdown(report)
        return format_workflow_context(report, title="观澜对比研究上下文")

    if name == "guanlan_timeline":
        from guanlan.research_workflows import (
            build_timeline_report,
            format_timeline_markdown,
            format_workflow_context,
        )

        report = build_timeline_report(
            str(args.get("query", "")).strip(),
            preset=str(args.get("preset") or "general"),
            profile=args.get("profile") or "china",
            limit=int(args.get("limit") or 80),
            read_top=int(args.get("read_top") or 0),
            search_backend=str(args.get("search_backend") or "auto"),
            read_backend=str(args.get("read_backend") or "auto"),
            max_read_chars=int(args["max_read_chars"]) if args.get("max_read_chars") is not None else None,
            max_events=int(args.get("max_events") or 20),
            order=str(args.get("order") or "desc"),
        )
        output_format = str(args.get("format") or "context")
        if output_format == "json":
            return report
        if output_format == "markdown":
            return format_timeline_markdown(report)
        return format_workflow_context(report, title="观澜时间线上下文")

    if name == "guanlan_dossier":
        from guanlan.research_workflows import (
            build_dossier_report,
            format_dossier_markdown,
            format_workflow_context,
        )

        report = build_dossier_report(
            str(args.get("entity", "")).strip(),
            focus=str(args.get("focus") or ""),
            preset=str(args.get("preset") or "general"),
            profile=args.get("profile") or "china",
            limit=int(args.get("limit") or 80),
            read_top=int(args.get("read_top") or 2),
            search_backend=str(args.get("search_backend") or "auto"),
            read_backend=str(args.get("read_backend") or "auto"),
            max_read_chars=int(args.get("max_read_chars") or 2400),
            select_top=int(args.get("select_top") or 10),
        )
        output_format = str(args.get("format") or "context")
        if output_format == "json":
            return report
        if output_format == "markdown":
            return format_dossier_markdown(report)
        return format_workflow_context(report, title="观澜研究档案上下文")

    if name == "guanlan_hotnews":
        from guanlan.hotnews import (
            build_hotnews_brief,
            build_trend_report,
            compact_hotnews_items,
            fetch_hotnews,
            format_hotnews_brief_markdown,
            format_hotnews_markdown,
            format_trend_report_markdown,
        )

        items = fetch_hotnews(
            str(args.get("source") or "today"),
            limit=int(args.get("limit") or DEFAULT_HOTNEWS_LIMIT),
            backend=str(args.get("backend") or "auto"),
            newsnow_base_url=args.get("newsnow_base_url") or None,
        )
        output_format = str(args.get("format") or "markdown")
        trend_report = build_trend_report(items) if (args.get("trends") or args.get("brief")) else None
        if output_format == "json":
            rows = compact_hotnews_items(items) if args.get("compact") else items
            if args.get("trends") or args.get("brief") or args.get("compact"):
                payload = {"items": rows}
                if args.get("trends"):
                    payload["trend_report"] = trend_report
                if args.get("brief"):
                    payload["brief"] = build_hotnews_brief(items, trend_report=trend_report)
                return payload
            return rows
        text = format_hotnews_markdown(items, title=f"观澜热榜 / {args.get('source') or 'today'}")
        if args.get("trends"):
            text += "\n\n" + format_trend_report_markdown(trend_report or {}, title=f"观澜趋势归并 / {args.get('source') or 'today'}")
        if args.get("brief"):
            text += "\n\n" + format_hotnews_brief_markdown(build_hotnews_brief(items, trend_report=trend_report), title=f"观澜今日水势简报 / {args.get('source') or 'today'}")
        return text

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

    if name == "guanlan_feeds":
        from guanlan.feeds import (
            compact_feed_items,
            fetch_feed_source,
            format_feed_catalog_markdown,
            format_feed_items_context,
            format_feed_items_markdown,
            format_feed_sources_markdown,
            list_curated_sources,
            list_feed_sources,
            resolve_feed_source,
        )

        source = resolve_feed_source(str(args.get("source") or "curated"))
        limit = min(max(int(args.get("limit") or DEFAULT_FEEDS_LIMIT), 1), MAX_FEEDS_LIMIT)
        output_format = str(args.get("format") or "context")
        if source == "list":
            catalog = list_feed_sources()
            if output_format == "json":
                return catalog
            return format_feed_catalog_markdown(catalog)
        if source == "curated-sources":
            sources = list_curated_sources(limit=limit, query=args.get("keyword") or None)
            if output_format == "json":
                return sources
            return format_feed_sources_markdown(sources, title="观澜 RSS 源目录 / 精品源")
        items = fetch_feed_source(
            source,
            limit=limit,
            language=str(args.get("language") or "zh"),
            category=args.get("category") or None,
            resource_type=args.get("resource_type") or None,
            featured=bool(args.get("featured", False)),
            min_score=int(args["min_score"]) if args.get("min_score") is not None else None,
            keyword=args.get("keyword") or None,
            time_filter=args.get("time_filter") or None,
            watchlist_path=args.get("watchlist_path") or args.get("watchlist") or None,
        )
        source_titles = {
            "curated": "精品内容流",
            "ai-official": "AI 官方更新流",
            "ai-media": "AI 媒体观察流",
            "ai-vertical": "AI 垂类精选动态源",
            "arxiv": "arXiv 预印本",
            "watchlist": "订阅源观察",
            "baidu-rss": "百度实时热点 RSS",
            "wechat-rss": "微信热门文章 RSS",
        }
        title = f"观澜内容发现 / {source_titles.get(source, 'RSS')}"
        if output_format == "json":
            return compact_feed_items(items) if args.get("compact") else items
        if output_format == "markdown":
            return format_feed_items_markdown(items, title=title)
        return format_feed_items_context(items, title=f"{title} 上下文")

    if name == "guanlan_daily":
        from guanlan.agent_planner import build_agent_followup, format_agent_followup_context
        from guanlan.daily import (
            build_daily_report,
            format_daily_context,
            format_daily_html,
            format_daily_im,
            format_daily_markdown,
        )

        request = normalize_daily_request(args)
        query = request.pop("query")
        report = build_daily_report(query, **request)
        report["agent_followup"] = build_agent_followup("guanlan_daily", report, query=str(args.get("query", "")).strip())
        output_format = str(args.get("format") or "markdown")
        if output_format == "json":
            return report
        if output_format == "context":
            text = format_daily_context(report)
            followup_text = format_agent_followup_context(report.get("agent_followup"))
            return text + (f"\n\n{followup_text}" if followup_text else "")
        if output_format == "html":
            return format_daily_html(report)
        if output_format == "im":
            return format_daily_im(report)
        return format_daily_markdown(report)

    if name == "guanlan_archive_search":
        from guanlan.archive import (
            archive_search_diagnostics,
            format_archive_context,
            format_archive_markdown,
            search_documents,
        )

        records = search_documents(
            str(args.get("query", "")).strip(),
            limit=int(args.get("limit") or DEFAULT_ARCHIVE_SEARCH_LIMIT),
            trace=bool(args.get("trace", False)),
        )
        output_format = str(args.get("format") or "context")
        diagnostics = archive_search_diagnostics(str(args.get("query", "")).strip(), records=records) if args.get("trace") else None
        if output_format == "json":
            return {"records": records, "diagnostics": diagnostics} if diagnostics else records
        if output_format == "markdown":
            return format_archive_markdown(records, title=f"观澜本地知识库 / {args.get('query', '')}")
        return format_archive_context(records, title=f"观澜本地知识库上下文 / {args.get('query', '')}")

    if name == "guanlan_archive_context":
        from guanlan.archive_wiki import build_archive_wiki_context

        result = build_archive_wiki_context(
            str(args.get("query", "")).strip(),
            limit=int(args.get("limit") or 20),
            min_quality=int(args.get("min_quality") or 0),
            max_chars=int(args.get("max_chars") or 1200),
        )
        if str(args.get("format") or "markdown") == "json":
            return result
        return result["context"]

    if name == "guanlan_archive_verify":
        from guanlan.archive import format_archive_verify, verify_archive

        result = verify_archive(
            limit=int(args.get("limit") or 8),
            min_quality=int(args.get("min_quality") if args.get("min_quality") is not None else 60),
        )
        if str(args.get("format") or "markdown") == "json":
            return result
        return format_archive_verify(result)

    raise ValueError(f"Unknown tool: {name}")


def create_server():
    if not HAS_MCP:
        print("MCP not installed. Install: pip install guanlan[mcp]", file=sys.stderr)
        sys.exit(1)

    server = Server("guanlan")

    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in _tool_definitions()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            # Keep this alias for local MCP clients that already call it.
            result = _doctor_report() if name == "get_status" else _run_tool(name, arguments)
            return [TextContent(type="text", text=_as_text(result))]
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {format_user_error(exc)}")]

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
