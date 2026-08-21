# -*- coding: utf-8 -*-
"""Read-first local HTTP service for Guanlan.

The service is intentionally local-first and conservative: by default it binds
to 127.0.0.1. Research Case routes only mutate the dedicated local state DB;
they do not add external posting, account or credential actions.
"""

from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from guanlan.errors import error_diagnostics
from guanlan.limits import (
    DEFAULT_ARCHIVE_SEARCH_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
)
from guanlan.tool_invocation import (
    normalize_agent_request,
    normalize_daily_request,
    normalize_map_request,
    normalize_read_request,
    normalize_research_request,
    normalize_route_request,
    normalize_search_request,
)


def declared_http_tool_routes() -> set[str]:
    """Return canonical HTTP tool routes for surface-parity checks.

    `/health`, `/sources`, and `/tools` are service metadata endpoints, not
    task tools.  Every task route is declared by ``tool_registry``.
    """

    from guanlan.tool_registry import http_routes

    return http_routes()


def dispatch_request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    """Dispatch a read-only Guanlan HTTP request for tests and the server."""
    payload = payload or {}
    parsed = urlparse(path)
    route = parsed.path.rstrip("/") or "/"
    query_args = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}

    try:
        if method == "GET" and route == "/health":
            from guanlan import __version__

            return 200, {
                "ok": True,
                "name": "guanlan",
                "version": __version__,
                "mode": "read-only",
                "local_state_writes": ["research_cases"],
            }
        if method == "POST" and route == "/cases":
            from guanlan.research_cases import create_case

            return 201, create_case(
                str(payload.get("query") or ""),
                request=dict(payload.get("request") or {}),
                requirements=dict(payload.get("requirements") or {}),
                budget=dict(payload.get("budget") or {}),
                expires_in=_optional_int(payload.get("expires_in")) or 7 * 24 * 3600,
            )
        if method == "GET" and route == "/cases":
            from guanlan.research_cases import list_cases

            return 200, {"cases": list_cases(state=query_args.get("state") or None, limit=_int(query_args.get("limit"), 50))}
        if route.startswith("/cases/"):
            from guanlan.research_cases import (
                cancel_case,
                get_case,
                pause_case,
                resume_case,
                run_case,
                task_view,
            )

            parts = [item for item in route.split("/") if item]
            if len(parts) not in {2, 3}:
                raise ValueError("invalid Research Case route")
            case_id = parts[1]
            action = parts[2] if len(parts) == 3 else ""
            if method == "GET" and not action:
                return 200, task_view(case_id) if _bool(query_args.get("task")) else get_case(case_id)
            if method == "POST" and action == "run":
                return 200, run_case(case_id)
            if method == "POST" and action == "pause":
                return 200, pause_case(case_id, reason=str(payload.get("reason") or "http_paused"))
            if method == "POST" and action == "resume":
                return 200, resume_case(case_id)
            if method == "POST" and action == "cancel":
                return 200, cancel_case(case_id, reason=str(payload.get("reason") or "http_cancelled"))
            raise ValueError("unsupported Research Case operation")
        if method == "GET" and route == "/sources":
            from guanlan.source_registry import list_sources

            return 200, {
                "sources": list_sources(
                    surface=query_args.get("surface") or None,
                    backend=query_args.get("backend") or None,
                )
            }
        if method == "GET" and route == "/tools":
            from guanlan.tool_registry import list_agent_tools

            return 200, {
                "tools": list_agent_tools(),
                "boundary": "只读工具面登记表；用于 Agent/HTTP/MCP 集成自检，不触发搜索或授权。",
            }
        if method == "POST" and route == "/agent":
            from guanlan.agent_planner import (
                build_agent_plan_v2,
                format_agent_plan_v2_markdown,
                review_agent_observation,
            )

            request = normalize_agent_request(payload)
            common_kwargs = {key: value for key, value in request.items() if key not in {"query", "phase"}}
            if request["phase"] == "review":
                plan = review_agent_observation(
                    request["query"],
                    payload.get("observation") or {},
                    **common_kwargs,
                )
            else:
                plan = build_agent_plan_v2(request["query"], **common_kwargs)
            if str(payload.get("format") or "json").lower() == "markdown":
                plan["rendered"] = format_agent_plan_v2_markdown(plan)
                plan["rendered_format"] = "markdown"
            return 200, plan
        if method == "POST" and route == "/route":
            from guanlan.router import build_route_plan
            from guanlan.workflow_decider import decide_workflow

            request = normalize_route_request(payload)
            plan = build_route_plan(**request)
            workflow_kwargs = {key: value for key, value in request.items() if key != "query"}
            response = plan.to_dict()
            response["workflow_decision"] = decide_workflow(
                request["query"], command="route", route_plan=plan, **workflow_kwargs
            ).to_dict()
            return 200, response
        if method == "POST" and route == "/browser-assist/plan":
            from guanlan.browser_assist import build_browser_assist_plan

            plan = build_browser_assist_plan(
                str(payload.get("url", "")).strip(),
                page_type=str(payload.get("page_type") or "access_gate"),
                signals=[str(item) for item in payload.get("signals", [])] if isinstance(payload.get("signals"), list) else [],
                candidate_urls=[str(item) for item in payload.get("candidate_urls", [])]
                if isinstance(payload.get("candidate_urls"), list)
                else None,
                max_pages=max(_int(payload.get("max_pages"), 3), 1),
                max_chars_per_page=max(_int(payload.get("max_chars_per_page"), 3000), 1),
                min_visible_items=max(_int(payload.get("min_visible_items"), 0), 0),
                task_goal=str(payload.get("task_goal") or ""),
                force=bool(payload.get("force", True)),
            )
            if payload.get("platform"):
                plan["platform"] = str(payload.get("platform"))
                if isinstance(plan.get("browser_assist_task"), dict):
                    plan["browser_assist_task"]["platform"] = str(payload.get("platform"))
            return 200, plan
        if method == "POST" and route == "/browser-assist/run":
            from guanlan.browser_assist import run_browser_assist_adapter

            if _browser_assist_http_execution_requested(payload):
                return 403, {
                    "error": "browser_assist_execution_not_allowed_http",
                    "status": "rejected",
                    "message": (
                        "HTTP /browser-assist/run 只返回浏览器补证执行契约；外部命令执行仅限本地 CLI 显式调用。"
                    ),
                    "boundary": "fail_closed; execute/command_template/output are CLI-only fields",
                }
            return 200, run_browser_assist_adapter(
                str(payload.get("url", "")).strip(),
                adapter=str(payload.get("adapter") or "openguanlan"),
                execute=False,
                command_template="",
                timeout=max(_int(payload.get("timeout"), 90), 1),
                output_path="",
                page_type=str(payload.get("page_type") or "access_gate"),
                signals=[str(item) for item in payload.get("signals", [])] if isinstance(payload.get("signals"), list) else [],
                platform=str(payload.get("platform") or ""),
                max_pages=max(_int(payload.get("max_pages"), 3), 1),
                max_chars_per_page=max(_int(payload.get("max_chars_per_page"), 3000), 1),
                min_visible_items=max(_int(payload.get("min_visible_items"), 0), 0),
                task_goal=str(payload.get("task_goal") or ""),
            )
        if method == "POST" and route == "/search":
            from guanlan.agent_planner import build_agent_followup
            from guanlan.web.search import search_web

            request = normalize_search_request(payload)
            query = request.pop("query")
            results = search_web(query, **request)
            diagnostics = getattr(results, "diagnostics", {}) or {}
            return 200, {
                "results": results,
                "diagnostics": diagnostics,
                "agent_followup": build_agent_followup(
                    "guanlan_search",
                    {
                        "results": results,
                        "limit": request["limit"],
                        "diagnostics": diagnostics,
                    },
                    query=query,
                ),
            }
        if method == "POST" and route == "/map":
            from guanlan.site_map import (
                build_site_map,
                format_site_map_context,
                format_site_map_markdown,
            )

            request = normalize_map_request(payload)
            url = request.pop("url")
            packet = build_site_map(url, **request)
            output_format = str(payload.get("format") or "json").lower()
            if output_format == "markdown":
                packet["rendered"] = format_site_map_markdown(packet)
                packet["rendered_format"] = "markdown"
            elif output_format == "context":
                packet["rendered"] = format_site_map_context(packet)
                packet["rendered_format"] = "context"
            return 200, packet
        if method == "POST" and route == "/research":
            from guanlan.agent_planner import build_agent_followup
            from guanlan.web.research import build_research_packet

            request = normalize_research_request(payload)
            query = request.pop("query")
            packet = build_research_packet(query, **request)
            packet["agent_followup"] = build_agent_followup("guanlan_research", packet, query=query)
            return 200, packet
        if method == "POST" and route == "/compare":
            from guanlan.research_workflows import build_compare_report

            subjects = payload.get("subjects")
            if not isinstance(subjects, list):
                subjects = []
            return 200, build_compare_report(
                [str(item) for item in subjects],
                focus=str(payload.get("focus") or ""),
                preset=str(payload.get("preset") or "general"),
                profile=payload.get("profile") or "china",
                limit=_int(payload.get("limit"), DEFAULT_RESEARCH_LIMIT),
                read_top=_int(payload.get("read_top"), 0),
                search_backend=str(payload.get("search_backend") or "auto"),
                read_backend=str(payload.get("read_backend") or "auto"),
                max_read_chars=_optional_int(payload.get("max_read_chars")),
                select_top=_int(payload.get("select_top"), 6),
            )
        if method == "POST" and route == "/timeline":
            from guanlan.research_workflows import build_timeline_report

            return 200, build_timeline_report(
                str(payload.get("query", "")),
                preset=str(payload.get("preset") or "general"),
                profile=payload.get("profile") or "china",
                limit=_int(payload.get("limit"), 80),
                read_top=_int(payload.get("read_top"), 0),
                search_backend=str(payload.get("search_backend") or "auto"),
                read_backend=str(payload.get("read_backend") or "auto"),
                max_read_chars=_optional_int(payload.get("max_read_chars")),
                max_events=_int(payload.get("max_events"), 20),
                order=str(payload.get("order") or "desc"),
            )
        if method == "POST" and route == "/dossier":
            from guanlan.research_workflows import build_dossier_report

            return 200, build_dossier_report(
                str(payload.get("entity", "")),
                focus=str(payload.get("focus") or ""),
                preset=str(payload.get("preset") or "general"),
                profile=payload.get("profile") or "china",
                limit=_int(payload.get("limit"), 80),
                read_top=_int(payload.get("read_top"), 2),
                search_backend=str(payload.get("search_backend") or "auto"),
                read_backend=str(payload.get("read_backend") or "auto"),
                max_read_chars=_int(payload.get("max_read_chars"), 2400),
                select_top=_int(payload.get("select_top"), 10),
            )
        if method == "POST" and route in {"/prompt", "/context"}:
            from guanlan.web.renderers import format_research_prompt
            from guanlan.web.research import build_research_packet

            prompt_payload = {**payload, "advisor": payload.get("advisor", True)}
            request = normalize_research_request(prompt_payload)
            query = request.pop("query")
            packet = build_research_packet(query, **request)
            return 200, {
                "query": packet.get("query", ""),
                "format": "prompt",
                "prompt": format_research_prompt(packet, style=str(payload.get("style") or "deep")),
            }
        if method == "POST" and route == "/read":
            from guanlan.agent_planner import build_agent_followup
            from guanlan.web.read import read_url_with_trace

            request = normalize_read_request(payload)
            packet = read_url_with_trace(**request)
            packet["agent_followup"] = build_agent_followup("guanlan_read", packet)
            return 200, packet
        if method == "GET" and route == "/hotnews":
            from guanlan.hotnews import (
                build_hotnews_brief,
                build_trend_report,
                compact_hotnews_items,
                fetch_hotnews,
            )

            items = fetch_hotnews(
                str(query_args.get("source") or "today"),
                limit=_int(query_args.get("limit"), DEFAULT_HOTNEWS_LIMIT),
                backend=str(query_args.get("backend") or "auto"),
            )
            compact = _bool(query_args.get("compact"))
            response: dict[str, Any] = {"items": compact_hotnews_items(items) if compact else items}
            trend_report = build_trend_report(items) if (_bool(query_args.get("trends")) or _bool(query_args.get("brief"))) else None
            if _bool(query_args.get("trends")):
                response["trend_report"] = trend_report
            if _bool(query_args.get("brief")):
                response["brief"] = build_hotnews_brief(items, trend_report=trend_report)
            return 200, response
        if method == "GET" and route == "/feeds":
            from guanlan.feeds import (
                compact_feed_items,
                fetch_feed_source,
                list_curated_sources,
                list_feed_sources,
                resolve_feed_source,
            )

            source = resolve_feed_source(str(query_args.get("source") or "curated"))
            limit = _int(query_args.get("limit"), 80)
            if source == "list":
                return 200, {"sources": list_feed_sources()}
            if source == "curated-sources":
                sources = list_curated_sources(limit=limit, query=query_args.get("keyword") or None)
                return 200, {"sources": sources}
            items = fetch_feed_source(
                source,
                limit=limit,
                language=str(query_args.get("language") or "zh"),
                category=query_args.get("category") or None,
                resource_type=query_args.get("type") or query_args.get("resource_type") or None,
                featured=str(query_args.get("featured") or "").lower() in {"1", "true", "yes", "y"},
                min_score=_optional_int(query_args.get("min_score") or query_args.get("minScore")),
                keyword=query_args.get("keyword") or None,
                time_filter=query_args.get("time_filter") or query_args.get("timeFilter") or None,
                watchlist_path=query_args.get("watchlist_path") or query_args.get("watchlist") or None,
            )
            return 200, {"items": compact_feed_items(items) if _bool(query_args.get("compact")) else items}
        if method == "POST" and route == "/daily":
            from guanlan.agent_planner import build_agent_followup
            from guanlan.daily import (
                build_daily_report,
                format_daily_context,
                format_daily_html,
                format_daily_im,
                format_daily_markdown,
            )

            request = normalize_daily_request(payload)
            query = request.pop("query")
            report = build_daily_report(query, **request)
            report["agent_followup"] = build_agent_followup("guanlan_daily", report, query=str(payload.get("query", "")))
            output_format = str(payload.get("format") or "json").lower()
            if output_format == "markdown":
                report["rendered"] = format_daily_markdown(report)
                report["rendered_format"] = "markdown"
            elif output_format == "context":
                report["rendered"] = format_daily_context(report)
                report["rendered_format"] = "context"
            elif output_format == "html":
                report["rendered"] = format_daily_html(report)
                report["rendered_format"] = "html"
            elif output_format == "im":
                report["rendered"] = format_daily_im(report)
                report["rendered_format"] = "im"
            return 200, report
        if method == "POST" and route == "/archive/search":
            from guanlan.archive import search_documents

            records = search_documents(
                str(payload.get("query", "")),
                limit=_int(payload.get("limit"), DEFAULT_ARCHIVE_SEARCH_LIMIT),
                db_path=payload.get("db_path") or None,
            )
            return 200, {"results": records}
        return 404, {"error": "not_found", "message": f"Unknown endpoint: {method} {route}"}
    except Exception as exc:
        diagnostics = error_diagnostics(exc)
        return 400, {"error": "bad_request", **diagnostics}


def run_server(host: str = "127.0.0.1", port: int = 8765, token: str = "") -> None:
    """Run the read-only local HTTP server."""
    resolved_token = token or os.environ.get("GUANLAN_SERVE_TOKEN", "")
    if not _is_local_bind_host(host) and not resolved_token:
        raise SystemExit(
            "非本地监听必须设置 --token 或 GUANLAN_SERVE_TOKEN；已拒绝启动。"
        )
    server = ThreadingHTTPServer((host, int(port)), _GuanlanHandler)
    server.guanlan_token = resolved_token
    print(f"观澜只读服务启动: http://{host}:{port}")
    print("Endpoints: /health, /tools, /sources, /agent, /route, /browser-assist/plan, /search, /map, /research, /compare, /timeline, /dossier, /read, /hotnews, /feeds, /daily, /archive/search")
    if server.guanlan_token:
        print("Access: token required via Authorization: Bearer <token> or X-Guanlan-Token")
    server.serve_forever()


class _GuanlanHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if not self._check_auth():
            return
        status, body = dispatch_request("GET", self.path)
        self._write_json(status, body)

    def do_POST(self) -> None:  # noqa: N802
        if not self._check_auth():
            return
        length = _int(self.headers.get("content-length"), 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace") if length else "{}"
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return
        if not isinstance(payload, dict):
            self._write_json(400, {"error": "invalid_payload"})
            return
        status, body = dispatch_request("POST", self.path, payload)
        self._write_json(status, body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _check_auth(self) -> bool:
        token = str(getattr(self.server, "guanlan_token", "") or "")
        if not token:
            return True
        if is_authorized_request(self.headers, token):
            return True
        self._write_json(
            401,
            {
                "error": "unauthorized",
                "message": "Missing or invalid Guanlan serve token.",
            },
        )
        return False

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return _int(value)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    return min(max(_int(value, default), minimum), maximum)


def _bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _browser_assist_http_execution_requested(payload: dict[str, Any]) -> bool:
    if _bool(payload.get("execute")):
        return True
    for key in ("command_template", "output"):
        if str(payload.get(key) or "").strip():
            return True
    return False


def _is_local_bind_host(host: str) -> bool:
    return str(host or "").strip().lower() in {"127.0.0.1", "localhost", "::1"}


def is_authorized_request(headers: Any, token: str) -> bool:
    """Return whether HTTP headers satisfy the optional serve token."""
    expected = str(token or "")
    if not expected:
        return True
    provided = str(headers.get("x-guanlan-token", "") or headers.get("X-Guanlan-Token", "") or "")
    auth = str(headers.get("authorization", "") or headers.get("Authorization", "") or "")
    if auth.lower().startswith("bearer "):
        provided = auth[7:].strip()
    return bool(provided) and hmac.compare_digest(provided, expected)
