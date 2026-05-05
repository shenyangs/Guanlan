# -*- coding: utf-8 -*-
"""Read-only registry for Guanlan's agent-facing tool surface.

This is a stability anchor, not a dispatcher. CLI/MCP/HTTP implementations may
remain separate, but tests can use this registry to detect accidental tool
surface drift before release.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AgentTool:
    name: str
    surfaces: tuple[str, ...]
    stability: str
    command: str
    role: str
    http_route: str = ""
    min_default_limit: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


CORE_AGENT_TOOLS: tuple[AgentTool, ...] = (
    AgentTool("guanlan_status", ("cli", "mcp", "http"), "stable", "guanlan status", "install_and_runtime_diagnostics", "/health"),
    AgentTool("guanlan_capabilities", ("cli", "mcp"), "stable", "guanlan capabilities", "tool_selection"),
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
    AgentTool("guanlan_archive_search", ("cli", "mcp", "http"), "stable", "guanlan archive search", "local_memory_search", "/archive/search", 80),
)


def core_agent_tool_names() -> set[str]:
    return {tool.name for tool in CORE_AGENT_TOOLS}


def list_agent_tools() -> list[dict[str, object]]:
    return [tool.to_dict() for tool in CORE_AGENT_TOOLS]


def http_routes() -> set[str]:
    return {tool.http_route for tool in CORE_AGENT_TOOLS if tool.http_route}
