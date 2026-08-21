# -*- coding: utf-8 -*-
"""Read-only registry for Guanlan's agent-facing tool surface.

This is a stability anchor, not a dispatcher. CLI/MCP/HTTP implementations may
remain separate, but tests can use this registry to detect accidental tool
surface drift before release.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

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
    tier: str = "core"
    success_signals: tuple[str, ...] = ()
    repair_signals: tuple[str, ...] = ()
    requires_user_authorization: bool = False
    http_aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["request_schema"] = self.request_schema or {"type": "object", "properties": {}}
        payload["mcp_description"] = self.mcp_description or self.role
        payload["cli_handler"] = self.cli_handler or _DEFAULT_CLI_HANDLERS.get(self.name, "")
        payload["service_entrypoint"] = self.service_entrypoint or _DEFAULT_SERVICE_ENTRYPOINTS.get(self.name, "")
        payload["default_limit"] = self.default_limit or self.min_default_limit
        payload["http_routes"] = [route for route in (self.http_route, *self.http_aliases) if route]
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
    "guanlan_stock": "guanlan.commands.admin._cmd_stock",
    "guanlan_route": "guanlan.commands.search._cmd_route",
    "guanlan_workflow": "guanlan.commands.search._cmd_workflow",
    "guanlan_page_diagnose": "guanlan.commands.read._cmd_diagnose",
    "guanlan_browser_assist_plan": "guanlan.commands.read._cmd_browser_assist",
    "guanlan_browser_assist_run": "guanlan.commands.read._cmd_browser_assist",
    "guanlan_recipe": "guanlan.commands.research._cmd_recipe",
    "guanlan_read": "guanlan.commands.read._cmd_read",
    "guanlan_research": "guanlan.commands.research._cmd_research",
    "guanlan_investigate": "guanlan.commands.research._cmd_investigate",
    "guanlan_compare": "guanlan.commands.research._cmd_compare",
    "guanlan_timeline": "guanlan.commands.research._cmd_timeline",
    "guanlan_dossier": "guanlan.commands.research._cmd_dossier",
    "guanlan_hotnews": "guanlan.commands.hotnews._cmd_hotnews",
    "guanlan_pulse": "guanlan.commands.feeds._cmd_pulse",
    "guanlan_feeds": "guanlan.commands.feeds._cmd_feeds",
    "guanlan_daily": "guanlan.commands.daily._cmd_daily",
    "guanlan_archive_search": "guanlan.commands.admin._cmd_archive",
    "guanlan_archive_context": "guanlan.commands.admin._cmd_archive",
    "guanlan_archive_verify": "guanlan.commands.admin._cmd_archive",
}

_DEFAULT_SERVICE_ENTRYPOINTS = {
    "guanlan_status": "guanlan.doctor.check_all",
    "guanlan_capabilities": "guanlan.capabilities.list_capabilities",
    "guanlan_agent": "guanlan.agent_planner.build_agent_plan_v2",
    "guanlan_search": "guanlan.web.search.search_web",
    "guanlan_map": "guanlan.site_map.build_site_map",
    "guanlan_stock": "guanlan.stockdata",
    "guanlan_route": "guanlan.router.build_route_plan",
    "guanlan_workflow": "guanlan.workflow_decider.decide_workflow",
    "guanlan_page_diagnose": "guanlan.page_diagnosis.diagnose_page",
    "guanlan_browser_assist_plan": "guanlan.browser_assist.build_browser_assist_plan",
    "guanlan_browser_assist_run": "guanlan.browser_assist.run_browser_assist_adapter",
    "guanlan_recipe": "guanlan.recipes.build_recipe_plan",
    "guanlan_read": "guanlan.web.read.read_url_with_trace",
    "guanlan_research": "guanlan.web.research.build_research_packet",
    "guanlan_investigate": "guanlan.investigation.run_investigation",
    "guanlan_compare": "guanlan.research_workflows.build_compare_report",
    "guanlan_timeline": "guanlan.research_workflows.build_timeline_report",
    "guanlan_dossier": "guanlan.research_workflows.build_dossier_report",
    "guanlan_hotnews": "guanlan.hotnews.fetch_hotnews",
    "guanlan_pulse": "guanlan.pulse.build_pulse_report",
    "guanlan_feeds": "guanlan.feeds.fetch_feed_source",
    "guanlan_daily": "guanlan.daily.build_daily_report",
    "guanlan_archive_search": "guanlan.archive.search_documents",
    "guanlan_archive_context": "guanlan.archive.search_documents",
    "guanlan_archive_verify": "guanlan.archive.verify_archive",
}


SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["query"],
    "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer", "default": DEFAULT_SEARCH_LIMIT, "minimum": 1, "maximum": MAX_SEARCH_LIMIT},
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_SEARCH_LIMIT,
            "description": "兼容旧 MCP 客户端的 limit 别名；同时传入时以 limit 为准。",
        },
        "site": {"type": "string"},
        "scope": {"type": "string"},
        "strict_scope": {"type": "boolean", "default": False},
        "backend": {"type": "string", "default": "auto"},
        "network_mode": {"type": "string", "enum": ["auto", "current", "direct", "proxy"], "default": "auto"},
        "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
        "format": {"type": "string", "enum": ["markdown", "context", "prompt", "json"], "default": "context"},
        "trace": {"type": "boolean", "default": False},
        "cache_ttl": {"type": "integer", "default": 0, "minimum": 0},
        "use_cache": {"type": "boolean", "default": True},
        "cluster_threshold": {"type": "string", "enum": ["conservative", "balanced", "loose"], "default": "conservative"},
        "evidence_mode": {"type": "string", "enum": ["off", "shadow", "assist"], "default": "shadow"},
    },
}

ROUTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["query"],
    "properties": {
        "query": {"type": "string"},
        "preset": {"type": "string", "default": "general"},
        "scope": {"type": "string"},
        "site": {"type": "string"},
        "sites": {"type": "array", "items": {"type": "string"}},
        "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
        "limit": {"type": "integer", "default": DEFAULT_RESEARCH_LIMIT, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
        "read_top": {"type": "integer", "minimum": 0, "maximum": 10},
        "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
    },
}

READ_SCHEMA: dict[str, Any] = {
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
        "use_cache": {"type": "boolean", "default": True},
        "no_cache": {"type": "boolean", "default": False},
        "strict": {"type": "boolean", "default": False},
        "extract": {"type": "string", "enum": ["article", "text", "metadata", "links"], "default": "article"},
        "jina_engine": {"type": "string", "enum": ["auto", "browser", "curl"], "default": "auto"},
        "jina_format": {"type": "string", "enum": ["content", "frontmatter"], "default": "content"},
        "jina_wait_for": {"type": "string"},
        "jina_target": {"type": "string"},
        "jina_remove": {"type": "string"},
        "jina_repair": {"type": "boolean", "default": True},
        "format": {"type": "string", "enum": ["raw", "json", "context"], "default": "raw"},
    },
}

RESEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["query"],
    "properties": {
        "query": {"type": "string"},
        "preset": {"type": "string", "default": "general"},
        "limit": {"type": "integer", "default": DEFAULT_RESEARCH_LIMIT, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
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
            "description": "Accepts 0-5. Use 0-2 for normal Agent runs; 3-5 requires a 180-300 second outer timeout.",
        },
        "max_read_chars": {"type": "integer", "minimum": 1},
        "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"]},
        "format": {"type": "string", "enum": ["markdown", "context", "json", "prompt"], "default": "context"},
        "advisor": {
            "type": "boolean",
            "default": False,
            "description": "追加证据约束下的助理视角规则，而不是替用户做最终判断。",
        },
        "advisor_style": {"type": "string", "enum": ["brief", "decision", "risk", "strategy"], "default": "brief"},
        "max_search_jobs": {"type": "integer", "default": 1, "minimum": 1, "maximum": 4},
        "select_top": {"type": "integer", "minimum": 0, "maximum": 30},
        "cache_ttl": {"type": "integer", "default": 0, "minimum": 0},
    },
}

BROWSER_ASSIST_RUN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["url"],
    "properties": {
        "url": {"type": "string"},
        "adapter": {"type": "string", "default": "openguanlan"},
        "timeout": {"type": "integer", "default": 90, "minimum": 1, "maximum": 600},
        "page_type": {"type": "string", "default": "access_gate"},
        "signals": {"type": "array", "items": {"type": "string"}},
        "platform": {"type": "string"},
        "max_pages": {"type": "integer", "default": 3, "minimum": 1, "maximum": 20},
        "max_chars_per_page": {"type": "integer", "default": 3000, "minimum": 1, "maximum": 20000},
        "min_visible_items": {"type": "integer", "default": 0, "minimum": 0, "maximum": 500},
        "task_goal": {"type": "string"},
        "format": {"type": "string", "enum": ["markdown", "json"], "default": "json"},
    },
}

WORKFLOW_SCHEMA: dict[str, Any] = {
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
}


CORE_AGENT_TOOLS: tuple[AgentTool, ...] = (
    AgentTool("guanlan_status", ("cli", "mcp", "http"), "stable", "guanlan status", "install_and_runtime_diagnostics", "/health"),
    AgentTool(
        "guanlan_capabilities",
        ("cli", "mcp"),
        "stable",
        "guanlan capabilities",
        "tool_selection",
        request_schema={
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
    ),
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
                "read_top": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": MAX_AGENT_RESEARCH_READ_TOP,
                    "description": "Accepted 0-5; the Agent Planner still recommends 0-2 for normal runs.",
                },
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
    AgentTool(
        "guanlan_search",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan search",
        "broad_search",
        "/search",
        80,
        request_schema=SEARCH_SCHEMA,
    ),
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
    AgentTool(
        "guanlan_stock",
        ("cli", "mcp"),
        "stable",
        "guanlan stock",
        "structured_finance_data",
        "",
        20,
        request_schema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["plan", "quote", "detail", "fundflow", "news", "plate", "rank", "index", "search"],
                    "default": "quote",
                },
                "target": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                "news_limit": {"type": "integer", "default": 12, "minimum": 1, "maximum": 50},
                "sort": {"type": "string", "default": "turnover"},
                "direct": {"type": "string", "enum": ["down", "up"], "default": "down"},
                "offset": {"type": "integer", "default": 0, "minimum": 0},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
    ),
    AgentTool("guanlan_route", ("cli", "mcp", "http"), "stable", "guanlan route", "source_routing", "/route", 80, request_schema=ROUTE_SCHEMA),
    AgentTool(
        "guanlan_workflow",
        ("cli", "mcp"),
        "stable",
        "guanlan workflow",
        "light_heavy_workflow_decision",
        "",
        80,
        request_schema=WORKFLOW_SCHEMA,
    ),
    AgentTool(
        "guanlan_page_diagnose",
        ("cli", "mcp"),
        "stable",
        "guanlan diagnose page",
        "page_readability_diagnosis",
        "",
        20,
        request_schema={
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
    ),
    AgentTool(
        "guanlan_browser_assist_plan",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan browser-assist plan",
        "browser_visible_evidence_plan",
        "/browser-assist/plan",
        request_schema={
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
                "min_visible_items": {"type": "integer", "default": 0, "minimum": 0, "maximum": 500},
                "task_goal": {"type": "string"},
                "force": {"type": "boolean", "default": True},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "json"},
            },
        },
    ),
    AgentTool(
        "guanlan_browser_assist_run",
        ("cli", "mcp", "http"),
        "experimental",
        "guanlan browser-assist run",
        "browser_visible_evidence_adapter_contract",
        "/browser-assist/run",
        request_schema=BROWSER_ASSIST_RUN_SCHEMA,
        mcp_description=(
            "Return a user-authorized browser-assist execution contract. MCP/HTTP never execute external "
            "adapter commands; execute/command_template/output are CLI-only and fail closed if supplied."
        ),
    ),
    AgentTool(
        "guanlan_recipe",
        ("cli", "mcp"),
        "stable",
        "guanlan recipe",
        "repeatable_research_recipe",
        "",
        80,
        request_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "enum": ["list", "show", "run"], "default": "list"},
                "recipe_id": {"type": "string"},
                "query": {"type": "string"},
                "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                "limit": {"type": "integer", "default": DEFAULT_RESEARCH_LIMIT, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
                "read_top": {"type": "integer", "minimum": 0, "maximum": 10},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
    ),
    AgentTool(
        "guanlan_read",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan read",
        "page_reading",
        "/read",
        20,
        request_schema=READ_SCHEMA,
        when_to_use=("the agent has a target URL and needs page-body evidence",),
        avoid_when=("only URL discovery is needed; use map/search first",),
        success_signals=(
            "read_evidence.usable=true",
            "extract_contract.can_cite_as_page_body=true",
            "quality_report.usable=true",
            "structured extracted",
        ),
        repair_signals=(
            "extract_contract.status=context_only",
            "read_evidence.usable=false",
            "quality_report fallback_only/unusable",
            "dynamic shell",
        ),
    ),
    AgentTool(
        "guanlan_research",
        ("cli", "mcp", "http"),
        "guarded",
        "guanlan research",
        "evidence_packet",
        "/research",
        80,
        http_aliases=("/prompt", "/context"),
        request_schema=RESEARCH_SCHEMA,
        when_to_use=("explicit deep/reusable evidence packet", "search + read still lacks evidence-role coverage"),
        avoid_when=("simple lookup or first-pass search", "outer timeout is below 180 seconds"),
        success_signals=("selected_evidence present", "read_pack usable or read_top=0 by design", "evidence_audit present"),
        repair_signals=("research_failed", "timeout_or_aborted", "read_pack.usable_count=0"),
    ),
    AgentTool(
        "guanlan_investigate",
        ("cli", "mcp"),
        "guarded",
        "guanlan investigate",
        "explicit_upper_layer_investigation",
        "",
        80,
        request_schema={
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
    ),
    AgentTool(
        "guanlan_compare",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan compare",
        "comparative_research",
        "/compare",
        80,
        request_schema={
            "type": "object",
            "required": ["subjects"],
            "properties": {
                "subjects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 4,
                    "description": "Entity names only, for example ['蔚来', '小鹏', '理想']; put dimensions in focus.",
                },
                "focus": {
                    "type": "string",
                    "description": "Shared comparison dimensions and time window; do not repeat them in subjects.",
                },
                "preset": {"type": "string", "default": "general"},
                "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                "limit": {"type": "integer", "default": DEFAULT_RESEARCH_LIMIT, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
                "read_top": {"type": "integer", "default": 0, "minimum": 0, "maximum": 10},
                "search_backend": {"type": "string", "default": "auto"},
                "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                "max_read_chars": {"type": "integer", "minimum": 1},
                "select_top": {"type": "integer", "default": 6, "minimum": 1, "maximum": 20},
                "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
            },
        },
    ),
    AgentTool(
        "guanlan_timeline",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan timeline",
        "event_timeline",
        "/timeline",
        80,
        request_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "preset": {"type": "string", "default": "general"},
                "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                "limit": {"type": "integer", "default": DEFAULT_RESEARCH_LIMIT, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
                "read_top": {"type": "integer", "default": 0, "minimum": 0, "maximum": 10},
                "search_backend": {"type": "string", "default": "auto"},
                "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                "max_read_chars": {"type": "integer", "minimum": 1},
                "max_events": {"type": "integer", "default": 20, "minimum": 1, "maximum": 80},
                "order": {"type": "string", "enum": ["asc", "desc"], "default": "desc"},
                "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
            },
        },
    ),
    AgentTool(
        "guanlan_dossier",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan dossier",
        "entity_dossier",
        "/dossier",
        80,
        request_schema={
            "type": "object",
            "required": ["entity"],
            "properties": {
                "entity": {"type": "string"},
                "focus": {"type": "string"},
                "preset": {"type": "string", "default": "general"},
                "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                "limit": {"type": "integer", "default": DEFAULT_RESEARCH_LIMIT, "minimum": 1, "maximum": MAX_RESEARCH_LIMIT},
                "read_top": {"type": "integer", "default": 2, "minimum": 0, "maximum": 10},
                "search_backend": {"type": "string", "default": "auto"},
                "read_backend": {"type": "string", "enum": ["auto", "jina", "direct"], "default": "auto"},
                "max_read_chars": {"type": "integer", "default": 2400, "minimum": 1},
                "select_top": {"type": "integer", "default": 10, "minimum": 1, "maximum": 30},
                "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
            },
        },
    ),
    AgentTool(
        "guanlan_hotnews",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan hotnews",
        "trend_discovery",
        "/hotnews",
        80,
        request_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string", "default": "today"},
                "limit": {"type": "integer", "default": DEFAULT_HOTNEWS_LIMIT, "minimum": 1, "maximum": MAX_HOTNEWS_LIMIT},
                "backend": {"type": "string", "default": "auto"},
                "trends": {"type": "boolean", "default": False},
                "brief": {"type": "boolean", "default": False},
                "newsnow_base_url": {"type": "string"},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
    ),
    AgentTool(
        "guanlan_pulse",
        ("cli", "mcp"),
        "experimental",
        "guanlan pulse",
        "public_sample_echo_analysis",
        "",
        80,
        request_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": DEFAULT_PULSE_LIMIT, "minimum": 1, "maximum": MAX_PULSE_LIMIT},
                "site": {"type": "string"},
                "sites": {"type": "array", "items": {"type": "string"}},
                "scope": {"type": "string"},
                "backend": {"type": "string", "default": "auto"},
                "profile": {"type": "string", "enum": ["global", "china", "english", "hybrid"], "default": "china"},
                "read_top": {"type": "integer", "default": 0, "minimum": 0, "maximum": 5},
                "format": {"type": "string", "enum": ["markdown", "context", "json"], "default": "context"},
            },
        },
    ),
    AgentTool(
        "guanlan_feeds",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan feeds",
        "rss_discovery",
        "/feeds",
        80,
        request_schema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "default": "curated",
                    "description": "curated, ai-official, ai-media, ai-vertical, arxiv, watchlist, baidu-rss, wechat-rss, curated-sources, list, or a direct RSS/Atom URL",
                },
                "limit": {"type": "integer", "default": DEFAULT_FEEDS_LIMIT, "minimum": 1, "maximum": MAX_FEEDS_LIMIT},
                "language": {"type": "string", "enum": ["zh", "en"], "default": "zh"},
                "category": {"type": "string", "enum": ["programming", "ai", "product", "business"]},
                "resource_type": {"type": "string", "enum": ["article", "podcast", "video", "twitter"]},
                "featured": {"type": "boolean", "default": False},
                "min_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "keyword": {"type": "string"},
                "watchlist": {"type": "string"},
                "watchlist_path": {"type": "string"},
                "time_filter": {"type": "string"},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
    ),
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
    AgentTool(
        "guanlan_archive_search",
        ("cli", "mcp", "http"),
        "stable",
        "guanlan archive search",
        "local_memory_search",
        "/archive/search",
        80,
        request_schema={
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
                "db_path": {"type": "string"},
                "trace": {"type": "boolean", "default": False},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
    ),
    AgentTool(
        "guanlan_archive_context",
        ("cli", "mcp"),
        "stable",
        "guanlan archive context",
        "local_memory_context",
        "",
        20,
        request_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": MAX_ARCHIVE_SEARCH_LIMIT},
                "min_quality": {"type": "integer", "default": 0, "minimum": 0, "maximum": 100},
                "max_chars": {"type": "integer", "default": 1200, "minimum": 120, "maximum": 8000},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
    ),
    AgentTool(
        "guanlan_archive_verify",
        ("cli", "mcp"),
        "stable",
        "guanlan archive verify",
        "local_memory_health_check",
        "",
        20,
        request_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 50},
                "min_quality": {"type": "integer", "default": 60, "minimum": 0, "maximum": 100},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
        },
    ),
)


def core_agent_tool_names() -> set[str]:
    return {tool.name for tool in CORE_AGENT_TOOLS}


def list_agent_tools() -> list[dict[str, object]]:
    return [tool.to_dict() for tool in CORE_AGENT_TOOLS]


def http_routes() -> set[str]:
    return {route for tool in CORE_AGENT_TOOLS for route in (tool.http_route, *tool.http_aliases) if route}


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
            "http_routes": payload["http_routes"],
            "command": payload["command"],
            "service_entrypoint": payload["service_entrypoint"],
            "cli_handler": payload["cli_handler"],
            "request_schema": payload["request_schema"],
        }
    return projections


def mcp_output_contracts() -> dict[str, dict[str, object]]:
    """Describe stable MCP result boundaries without narrowing legacy output."""
    contracts: dict[str, dict[str, object]] = {}
    for tool in CORE_AGENT_TOOLS:
        schema_versions: list[str] = []
        if tool.name == "guanlan_read":
            schema_versions = ["read_evidence_v1", "read_outcome_v1", "jina_read_contract_v1"]
        elif tool.name == "guanlan_research":
            schema_versions = ["evidence_bundle_v1", "claim_ledger_v1"]
        elif tool.name == "guanlan_agent":
            schema_versions = ["agent_plan_v2"]
        contracts[tool.name] = {
            "transport": "text_content", "json_when_requested": True,
            "schema_versions": schema_versions, "additive_fields_only": True,
            "error_transport": "text_content",
        }
    return contracts
