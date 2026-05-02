# -*- coding: utf-8 -*-
"""Read-only local HTTP service for Guanlan.

The service is intentionally local-first and conservative: by default it binds
to 127.0.0.1 and exposes only search/read/research/hotnews/archive lookup.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


def dispatch_request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    """Dispatch a read-only Guanlan HTTP request for tests and the server."""
    payload = payload or {}
    parsed = urlparse(path)
    route = parsed.path.rstrip("/") or "/"
    query_args = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}

    try:
        if method == "GET" and route == "/health":
            from guanlan import __version__

            return 200, {"ok": True, "name": "guanlan", "version": __version__, "mode": "read-only"}
        if method == "POST" and route == "/route":
            from guanlan.router import build_route_plan

            plan = build_route_plan(
                str(payload.get("query", "")),
                preset=payload.get("preset"),
                scope=payload.get("scope"),
                site=payload.get("site"),
                sites=payload.get("sites") if isinstance(payload.get("sites"), list) else None,
                profile=payload.get("profile") or "china",
                limit=_int(payload.get("limit"), 50),
                read_top=_optional_int(payload.get("read_top")),
            )
            return 200, plan.to_dict()
        if method == "POST" and route == "/search":
            from guanlan.webtools import search_web

            results = search_web(
                str(payload.get("query", "")),
                limit=_int(payload.get("limit"), 50),
                site=payload.get("site") or None,
                scope=payload.get("scope") or None,
                backend=str(payload.get("backend") or "auto"),
                profile=payload.get("profile") or "china",
                trace=bool(payload.get("trace")),
            )
            return 200, {"results": results}
        if method == "POST" and route == "/research":
            from guanlan.webtools import build_research_packet

            packet = build_research_packet(
                str(payload.get("query", "")),
                preset=payload.get("preset") or "general",
                limit=_optional_int(payload.get("limit")),
                site=payload.get("site") or None,
                sites=payload.get("sites") if isinstance(payload.get("sites"), list) else None,
                scope=payload.get("scope") or None,
                search_backend=str(payload.get("search_backend") or "auto"),
                profile=payload.get("profile") or "china",
                read_top=_optional_int(payload.get("read_top")),
                advisor=bool(payload.get("advisor", False)),
            )
            return 200, packet
        if method == "POST" and route == "/read":
            from guanlan.webtools import read_url

            content = read_url(
                str(payload.get("url", "")),
                max_chars=_optional_int(payload.get("max_chars")),
                backend=str(payload.get("backend") or "auto"),
                fallback_search=bool(payload.get("fallback_search", True)),
                profile=payload.get("profile") or "china",
            )
            return 200, {"url": payload.get("url", ""), "content": content}
        if method == "GET" and route == "/hotnews":
            from guanlan.hotnews import build_trend_report, fetch_hotnews

            items = fetch_hotnews(
                str(query_args.get("source") or "today"),
                limit=_int(query_args.get("limit"), 50),
                backend=str(query_args.get("backend") or "auto"),
            )
            response: dict[str, Any] = {"items": items}
            if str(query_args.get("trends") or "").lower() in {"1", "true", "yes"}:
                response["trend_report"] = build_trend_report(items)
            return 200, response
        if method == "POST" and route == "/archive/search":
            from guanlan.archive import search_documents

            records = search_documents(
                str(payload.get("query", "")),
                limit=_int(payload.get("limit"), 50),
                db_path=payload.get("db_path") or None,
            )
            return 200, {"results": records}
        return 404, {"error": "not_found", "message": f"Unknown endpoint: {method} {route}"}
    except Exception as exc:
        return 400, {"error": "bad_request", "message": str(exc)}


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the read-only local HTTP server."""
    server = ThreadingHTTPServer((host, int(port)), _GuanlanHandler)
    print(f"观澜只读服务启动: http://{host}:{port}")
    print("Endpoints: /health, /route, /search, /research, /read, /hotnews, /archive/search")
    server.serve_forever()


class _GuanlanHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        status, body = dispatch_request("GET", self.path)
        self._write_json(status, body)

    def do_POST(self) -> None:  # noqa: N802
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
