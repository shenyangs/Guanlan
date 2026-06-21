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
    when_to_use: tuple[str, ...] = ()
    avoid_when: tuple[str, ...] = ()
    default_limit: int = 0
    timeout_budget_seconds: int = 90
    timeout_budget_ms: int = 90000
    success_signals: tuple[str, ...] = ()
    repair_signals: tuple[str, ...] = ()
    requires_user_authorization: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["request_schema"] = self.request_schema or {"type": "object", "properties": {}}
        payload["mcp_description"] = self.mcp_description or self.role
        payload["cli_handler"] = self.cli_handler or _DEFAULT_CLI_HANDLERS.get(self.name, "")
        payload["service_entrypoint"] = self.service_entrypoint or _DEFAULT_SERVICE_ENTRYPOINTS.get(self.name, "")
        payload["default_limit"] = self.default_limit or self.min_default_limit
        payload["tool_policy"] = {
            "when_to_use": list(self.when_to_use),
            "avoid_when": list(self.avoid_when),
            "default_limit": payload["default_limit"],
            "timeout_budget_seconds": self.timeout_budget_seconds,
            "timeout_budget_ms": self.timeout_budget_ms,
            "success_signals": list(self.success_signals),
            "repair_signals": list(self.repair_signals),
            "requires_user_authorization": self.requires_user_authorization,
        }
        return payload


_DEFAULT_CLI_HANDLERS = {
    "guanlan_status": "guanlan.commands.admin._cmd_status",
    "guanlan_capabilities": "guanlan.commands.admin._cmd_capabilities",
    "guanlan_agent": "guanlan.commands.search._cmd_agent",
    "guanlan_search": "guanlan.commands.search._cmd_search",
    "guanlan_map": "guanlan.commands.search._cmd_map",
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
    "guanlan_agent": "guanlan.agent_planner.build_agent_plan_v2",
    "guanlan_search": "guanlan.web.search.search_web",
    "guanlan_map": "guanlan.site_map.build_site_map",
    "guanlan_route": "guanlan.router.build_route_plan",
    "guanlan_browser_assist_plan": "guanlan.browser_assist.build_browser_assist_plan",
    "guanlan_browser_assist_run": "guanlan.browser_assist.run_browser_assist_adapter",
    "guanlan_read": "guanlan.web.read.read_url_with_trace",
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
    AgentTool(
        "guanlan_agent",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan agent",
        "low_choice_auto_plan_and_review",
        "/agent",
        request_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "phase": {"type": "string", "enum": ["plan", "review"], "default": "plan"},
                "observation": {"type": "object"},
                "mode": {"type": "string", "enum": ["auto", "quick", "deep", "fresh"], "default": "auto"},
                "preset": {"type": "string", "default": "general"},
                "scope": {"type": "string"},
                "site": {"type": "string"},
                "sites": {"type": "array", "items": {"type": "string"}},
                "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                "limit": {"type": "integer", "default": 80},
                "read_top": {"type": "integer", "minimum": 0, "maximum": 2},
                "max_commands": {"type": "integer", "default": 5},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "json"},
            },
        },
        mcp_description=(
            "Return an Agent Planner v2 decision card, or review a Guanlan observation and return "
            "next_decision=answer|continue|repair|ask_user|authorize_browser|stop."
        ),
        when_to_use=("unsure which Guanlan capability to run", "after a Guanlan result needs quality review"),
        avoid_when=("simple known command path is obvious",),
        success_signals=("primary_command present", "next_decision=answer in review"),
        repair_signals=(
            "empty_results",
            "small_limit",
            "read_unusable",
            "read_pack_unusable",
            "research_failed",
            "official_only",
        ),
    ),
    AgentTool("guanlan_search", ("cli", "mcp", "http"), "stable", "guanlan search", "broad_search", "/search", 80),
    AgentTool(
        "guanlan_map",
        ("cli", "mcp", "http"),
        "experimental",
        "guanlan map",
        "site_url_discovery",
        "/map",
        80,
        request_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "query": {"type": "string", "default": ""},
                "limit": {"type": "integer", "default": 80, "minimum": 1},
                "include_subdomains": {"type": "boolean", "default": False},
                "sitemap": {"type": "string", "enum": ["auto", "only", "skip"], "default": "auto"},
                "include_patterns": {"type": "array", "items": {"type": "string"}},
                "exclude_patterns": {"type": "array", "items": {"type": "string"}},
                "timeout": {"type": "integer", "default": 8, "minimum": 1},
                "read_top": {"type": "integer", "default": 0, "minimum": 0, "maximum": 5},
                "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                "max_read_chars": {"type": "integer", "default": 4000, "minimum": 1, "maximum": 20000},
                "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "markdown"},
            },
        },
        mcp_description=(
            "Discover public candidate URLs inside a known site using robots.txt sitemap hints, "
            "sitemap XML, and page links. Use before read when the user knows a site/domain and "
            "needs docs, pricing, announcements, contact pages, or other site-local entrypoints. "
            "This is URL discovery by default; set read_top=1-5 to read representative pages with quality reports."
        ),
        when_to_use=("known site/domain entrypoint discovery", "find docs/pricing/announcement/contact pages inside one site"),
        avoid_when=("whole-web search is needed", "the agent already has a specific URL to read"),
        success_signals=(
            "links returned",
            "read_pack.usable_count>0 when read_top>0",
            "agent_followup contains read commands",
        ),
        repair_signals=("no links", "read_pack.usable_count=0", "robots/sitemap/page_links source errors"),
    ),
    AgentTool("guanlan_route", ("cli", "mcp", "http"), "stable", "guanlan route", "source_routing", "/route", 80),
    AgentTool("guanlan_browser_assist_plan", ("cli", "mcp", "http"), "stable", "guanlan browser-assist plan", "browser_visible_evidence_plan", "/browser-assist/plan"),
    AgentTool("guanlan_browser_assist_run", ("cli", "http"), "experimental", "guanlan browser-assist run", "browser_visible_evidence_adapter", "/browser-assist/run"),
    AgentTool(
        "guanlan_read",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan read",
        "page_reading",
        "/read",
        20,
        when_to_use=("the agent has a target URL and needs page-body evidence",),
        avoid_when=("only URL discovery is needed; use map/search first",),
        success_signals=("read_evidence.usable=true", "quality_report.usable=true", "structured extracted"),
        repair_signals=("read_evidence.usable=false", "quality_report fallback_only/unusable", "dynamic shell"),
    ),
    AgentTool(
        "guanlan_research",
        ("cli", "mcp", "http"),
        "guarded",
        "guanlan research",
        "evidence_packet",
        "/research",
        80,
        when_to_use=("explicit deep/reusable evidence packet", "search + read still lacks evidence-role coverage"),
        avoid_when=("simple lookup or first-pass search", "outer timeout is below 180 seconds"),
        success_signals=("selected_evidence present", "read_pack usable or read_top=0 by design", "evidence_audit present"),
        repair_signals=("research_failed", "timeout_or_aborted", "read_pack.usable_count=0"),
    ),
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
                "read_top": {"type": "integer", "default": 3, "minimum": 0, "maximum": 3},
                "record_history": {"type": "boolean", "default": False},
                "history_path": {"type": "string"},
                "compare_days": {"type": "integer", "default": 0},
            },
        },
        mcp_description="Build a multi-source editorial daily brief with storylines, source tiers, freshness, risks, actions, overflow clues, and optional history delta.",
        when_to_use=("brand/market/reputation daily brief", "today/fresh editorial summary"),
        avoid_when=("single page reading or one-off site URL discovery"),
        success_signals=("storylines present", "read_pack usable when read_top>0", "editorial_health not block"),
        repair_signals=("editorial_health block/warn", "official-only", "read_pack.usable_count=0"),
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
