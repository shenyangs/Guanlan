# -*- coding: utf-8 -*-
"""Read-only registry for Guanlan's agent-facing tool surface.

This is a stability anchor, not a dispatcher. CLI/MCP/HTTP implementations may
remain separate, but tests can use this registry to detect accidental tool
surface drift before release.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentTool:
    name: str
    surfaces: tuple[str, ...]
    stability: str
    command: str
    role: str
    http_route: str = ""
    min_default_limit: int = 0
    cli_handler: str = ""
    service_entrypoint: str = ""
    request_schema: dict[str, Any] = field(default_factory=dict)
    mcp_description: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["request_schema"] = self.request_schema or {"type": "object", "properties": {}}
        payload["mcp_description"] = self.mcp_description or self.role
        payload["cli_handler"] = self.cli_handler or _DEFAULT_CLI_HANDLERS.get(self.name, "")
        payload["service_entrypoint"] = self.service_entrypoint or _DEFAULT_SERVICE_ENTRYPOINTS.get(self.name, "")
        return payload


_DEFAULT_CLI_HANDLERS = {
    "guanlan_status": "guanlan.commands.admin._cmd_status",
    "guanlan_capabilities": "guanlan.commands.admin._cmd_capabilities",
    "guanlan_agent": "guanlan.commands.search._cmd_agent",
    "guanlan_search": "guanlan.commands.search._cmd_search",
    "guanlan_route": "guanlan.commands.search._cmd_route",
    "guanlan_browser_assist_plan": "guanlan.commands.read._cmd_browser_assist",
    "guanlan_browser_assist_run": "guanlan.commands.read._cmd_browser_assist",
    "guanlan_read": "guanlan.commands.read._cmd_read",
    "guanlan_research": "guanlan.commands.research._cmd_research",
    "guanlan_compare": "guanlan.commands.research._cmd_compare",
    "guanlan_timeline": "guanlan.commands.research._cmd_timeline",
    "guanlan_dossier": "guanlan.commands.research._cmd_dossier",
    "guanlan_hotnews": "guanlan.commands.hotnews._cmd_hotnews",
    "guanlan_feeds": "guanlan.commands.feeds._cmd_feeds",
    "guanlan_daily": "guanlan.commands.daily._cmd_daily",
    "guanlan_archive_search": "guanlan.commands.admin._cmd_archive",
}

_DEFAULT_SERVICE_ENTRYPOINTS = {
    "guanlan_status": "guanlan.doctor.check_all",
    "guanlan_capabilities": "guanlan.capabilities.list_capabilities",
    "guanlan_agent": "guanlan.workflow_decider.build_agent_plan",
    "guanlan_search": "guanlan.web.search.search_web",
    "guanlan_route": "guanlan.router.build_route_plan",
    "guanlan_browser_assist_plan": "guanlan.browser_assist.build_browser_assist_plan",
    "guanlan_browser_assist_run": "guanlan.browser_assist.run_browser_assist_adapter",
    "guanlan_read": "guanlan.web.read.read_url",
    "guanlan_research": "guanlan.web.research.build_research_packet",
    "guanlan_compare": "guanlan.research_workflows.build_compare_report",
    "guanlan_timeline": "guanlan.research_workflows.build_timeline_report",
    "guanlan_dossier": "guanlan.research_workflows.build_dossier_report",
    "guanlan_hotnews": "guanlan.hotnews.fetch_hotnews",
    "guanlan_feeds": "guanlan.feeds.fetch_feed_source",
    "guanlan_daily": "guanlan.daily.build_daily_report",
    "guanlan_archive_search": "guanlan.archive.search_documents",
}


CORE_AGENT_TOOLS: tuple[AgentTool, ...] = (
    AgentTool("guanlan_status", ("cli", "mcp", "http"), "stable", "guanlan status", "install_and_runtime_diagnostics", "/health"),
    AgentTool("guanlan_capabilities", ("cli", "mcp"), "stable", "guanlan capabilities", "tool_selection"),
    AgentTool("guanlan_agent", ("cli", "mcp"), "stable", "guanlan agent", "low_choice_auto_plan"),
    AgentTool("guanlan_search", ("cli", "mcp", "http"), "stable", "guanlan search", "broad_search", "/search", 80),
    AgentTool("guanlan_route", ("cli", "mcp", "http"), "stable", "guanlan route", "source_routing", "/route", 80),
    AgentTool("guanlan_browser_assist_plan", ("cli", "mcp", "http"), "stable", "guanlan browser-assist plan", "browser_visible_evidence_plan", "/browser-assist/plan"),
    AgentTool("guanlan_browser_assist_run", ("cli", "http"), "experimental", "guanlan browser-assist run", "browser_visible_evidence_adapter", "/browser-assist/run"),
    AgentTool("guanlan_read", ("cli", "mcp", "http"), "stable", "guanlan read", "page_reading", "/read", 20),
    AgentTool("guanlan_research", ("cli", "mcp", "http"), "stable", "guanlan research", "evidence_packet", "/research", 80),
    AgentTool("guanlan_compare", ("cli", "mcp", "http"), "stable", "guanlan compare", "comparative_research", "/compare", 80),
    AgentTool("guanlan_timeline", ("cli", "mcp", "http"), "stable", "guanlan timeline", "event_timeline", "/timeline", 80),
    AgentTool("guanlan_dossier", ("cli", "mcp", "http"), "stable", "guanlan dossier", "entity_dossier", "/dossier", 80),
    AgentTool("guanlan_hotnews", ("cli", "mcp", "http"), "stable", "guanlan hotnews", "trend_discovery", "/hotnews", 80),
    AgentTool("guanlan_feeds", ("cli", "mcp", "http"), "stable", "guanlan feeds", "rss_discovery", "/feeds", 80),
    AgentTool(
        "guanlan_daily",
        ("cli", "mcp", "http"),
        "experimental",
        "guanlan daily",
        "daily_brief",
        "/daily",
        20,
        request_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "watch_id": {"type": "string"},
                "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                "time_window": {"type": "string", "enum": ["today", "24h", "3d", "7d"], "default": "3d"},
                "edition": {"type": "string", "enum": ["brand", "market", "reputation", "general"], "default": "brand"},
                "format": {"type": "string", "enum": ["markdown", "context", "json", "html", "im"], "default": "markdown"},
                "record_history": {"type": "boolean", "default": False},
                "history_path": {"type": "string"},
                "compare_days": {"type": "integer", "default": 0},
            },
        },
        mcp_description="Build a multi-source editorial daily brief with storylines, source tiers, freshness, risks, actions, overflow clues, and optional history delta.",
    ),
    AgentTool("guanlan_archive_search", ("cli", "mcp", "http"), "stable", "guanlan archive search", "local_memory_search", "/archive/search", 80),
)


def core_agent_tool_names() -> set[str]:
    return {tool.name for tool in CORE_AGENT_TOOLS}


def list_agent_tools() -> list[dict[str, object]]:
    return [tool.to_dict() for tool in CORE_AGENT_TOOLS]


def http_routes() -> set[str]:
    return {tool.http_route for tool in CORE_AGENT_TOOLS if tool.http_route}


def tool_by_name(name: str) -> AgentTool | None:
    """Return the canonical tool spec by id."""
    return next((tool for tool in CORE_AGENT_TOOLS if tool.name == name), None)


def mcp_projection_defaults() -> dict[str, dict[str, object]]:
    """Project canonical defaults that MCP/HTTP/CLI parity checks can share."""
    projections: dict[str, dict[str, object]] = {}
    for tool in CORE_AGENT_TOOLS:
        payload = tool.to_dict()
        projections[tool.name] = {
            "stability": payload["stability"],
            "default_limit": payload["min_default_limit"],
            "http_route": payload["http_route"],
            "command": payload["command"],
            "service_entrypoint": payload["service_entrypoint"],
            "cli_handler": payload["cli_handler"],
            "request_schema": payload["request_schema"],
        }
    return projections
