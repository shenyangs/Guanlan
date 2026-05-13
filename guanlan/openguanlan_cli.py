# -*- coding: utf-8 -*-
"""OpenGuanlan native browser bridge CLI.

This is Guanlan's read-only browser bridge surface. It absorbs the useful
browser-observation primitives into Guanlan's browser-assist boundary instead
of requiring users to install OpenCLI as a prerequisite.
"""

from __future__ import annotations

import argparse
import base64
import json
import queue
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 19830
SCHEMA_VERSION = "openguanlan_bridge_v1"

READ_ONLY_ACTIONS = {
    "back",
    "bind",
    "extract",
    "find",
    "frames",
    "get_attributes",
    "get_value",
    "open",
    "refresh",
    "screenshot",
    "state",
    "get_text",
    "get_html",
    "get_title",
    "get_url",
    "tab_new",
    "tab_select",
    "wait_text",
    "scroll",
    "tab_list",
    "read_visible",
    "unbind",
}

NAVIGATION_ACTIONS = {"open", "back", "refresh", "tab_new", "tab_select"}

FORBIDDEN_ACTIONS = [
    "read_cookies",
    "read_tokens",
    "read_local_storage",
    "read_session_storage",
    "read_browser_profile",
    "read_browser_database",
    "read_private_api_tokens",
    "network_body_with_credentials",
    "eval_arbitrary_js",
    "read_passwords",
    "read_keychain",
    "click",
    "type",
    "fill",
    "select",
    "upload",
    "drag",
    "post",
    "like",
    "comment",
    "follow",
    "message",
    "purchase",
    "submit_forms",
]


class BridgeState:
    def __init__(self) -> None:
        self.pending: queue.Queue[dict[str, Any]] = queue.Queue()
        self.results: dict[str, dict[str, Any]] = {}
        self.extension_seen_at = 0.0
        self.extension_info: dict[str, Any] = {}


STATE = BridgeState()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="openguanlan",
        description="Guanlan-native read-only browser bridge",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bridge daemon host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bridge daemon port")
    parser.add_argument("--json", action="store_true", help="Print JSON where supported")
    sub = parser.add_subparsers(dest="command")

    p_doctor = sub.add_parser("doctor", help="Check daemon/extension readiness")
    _add_daemon_args(p_doctor)
    _add_json_arg(p_doctor)
    p_capabilities = sub.add_parser("capabilities", help="List read-only bridge primitives")
    _add_json_arg(p_capabilities)
    p_setup = sub.add_parser("setup", help="Show extension install path and setup steps")
    _add_json_arg(p_setup)

    p_extension = sub.add_parser("extension", help="Show browser extension information")
    p_extension.add_argument("extension_command", choices=["path", "manifest"], nargs="?", default="path")
    _add_json_arg(p_extension)

    p_daemon = sub.add_parser("daemon", help="Run local OpenGuanlan bridge daemon")
    _add_daemon_args(p_daemon)
    p_daemon.add_argument("--once", action="store_true", help="Handle one HTTP request then exit")

    p_open = sub.add_parser("open", help="Open a URL in the user browser through the bridge")
    p_open.add_argument("url")
    _add_common_task_args(p_open)

    p_read = sub.add_parser("read-visible", help="Read target page visible content as Guanlan browser-visible JSON")
    p_read.add_argument("url")
    p_read.add_argument("--output", default="-", help="Output JSONL path, or - for stdout")
    p_read.add_argument("--max-chars", type=int, default=3000)
    p_read.add_argument("--min-visible-items", type=int, default=0)
    p_read.add_argument("--private-account-evidence", action="store_true")
    _add_common_task_args(p_read)

    p_state = sub.add_parser("state", help="Get active page URL/title/text snapshot")
    p_state.add_argument("--max-chars", type=int, default=3000)
    p_state.add_argument("--include-items", action="store_true")
    _add_common_task_args(p_state)

    p_get = sub.add_parser("get", help="Get active page property")
    p_get.add_argument("field", choices=["text", "html", "title", "url", "value", "attributes"])
    p_get.add_argument("--selector", default="")
    p_get.add_argument("--target", default="")
    p_get.add_argument("--max-chars", type=int, default=3000)
    _add_common_task_args(p_get)

    p_find = sub.add_parser("find", help="Find visible elements by CSS/text/role/name")
    p_find.add_argument("--css", default="")
    p_find.add_argument("--text", default="")
    p_find.add_argument("--role", default="")
    p_find.add_argument("--name", default="")
    p_find.add_argument("--limit", type=int, default=20)
    p_find.add_argument("--max-chars", type=int, default=240)
    _add_common_task_args(p_find)

    p_extract = sub.add_parser("extract", help="Extract long-form visible content with chunk cursor")
    p_extract.add_argument("--selector", default="")
    p_extract.add_argument("--chunk-size", type=int, default=6000)
    p_extract.add_argument("--start", type=int, default=0)
    _add_common_task_args(p_extract)

    p_frames = sub.add_parser("frames", help="List iframe/source hints without reading credentials")
    _add_common_task_args(p_frames)

    p_screenshot = sub.add_parser("screenshot", help="Capture the visible viewport")
    p_screenshot.add_argument("output", nargs="?", default="-", help="PNG/JPEG path, or - for JSON data URL")
    p_screenshot.add_argument("--format", choices=["png", "jpeg"], default="png")
    _add_common_task_args(p_screenshot)

    p_back = sub.add_parser("back", help="Navigate active tab back")
    _add_common_task_args(p_back)

    p_refresh = sub.add_parser("refresh", help="Refresh active tab")
    _add_common_task_args(p_refresh)

    p_wait = sub.add_parser("wait", help="Wait for target page readiness signal")
    p_wait.add_argument("kind", choices=["text"])
    p_wait.add_argument("value")
    p_wait.add_argument("--timeout-ms", type=int, default=0, help="Wait timeout in milliseconds")
    _add_common_task_args(p_wait)

    p_scroll = sub.add_parser("scroll", help="Scroll target page")
    p_scroll.add_argument("direction", choices=["up", "down"])
    p_scroll.add_argument("--amount", type=int, default=800)
    _add_common_task_args(p_scroll)

    p_tab = sub.add_parser("tab", help="Tab/session helpers")
    p_tab.add_argument("tab_command", choices=["list", "new", "select"])
    p_tab.add_argument("target", nargs="?", default="")
    p_tab.add_argument("--url", default="")
    _add_common_task_args(p_tab)

    p_bind = sub.add_parser("bind", help="Bind the current visible tab to a logical session")
    _add_common_task_args(p_bind)

    p_unbind = sub.add_parser("unbind", help="Release a logical session binding")
    _add_common_task_args(p_unbind)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    if args.command == "doctor":
        return _print_payload(_doctor(args.host, args.port), as_json=args.json)
    if args.command == "capabilities":
        return _print_payload(_capabilities(), as_json=args.json)
    if args.command == "setup":
        return _print_payload(_setup_payload(), as_json=args.json)
    if args.command == "extension":
        payload = _extension_payload()
        if args.extension_command == "path":
            print(payload["path"])
            return 0
        return _print_payload(payload, as_json=True)
    if args.command == "daemon":
        return _run_daemon(args.host, args.port, once=bool(args.once))
    return _run_task_command(args)


def _add_common_task_args(parser: argparse.ArgumentParser) -> None:
    _add_daemon_args(parser)
    _add_json_arg(parser)
    parser.add_argument("--timeout", type=float, default=90.0, help="Timeout seconds")
    parser.add_argument("--session", default="guanlan-visible", help="Logical browser bridge session")


def _add_daemon_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bridge daemon host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bridge daemon port")


def _add_json_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Print JSON output")


def _run_task_command(args: argparse.Namespace) -> int:
    action = _action_from_args(args)
    task = _task_from_args(args, action)
    result = _submit_task(args.host, args.port, task, timeout=max(float(args.timeout or 1), 0.1))
    if args.command == "read-visible" and result.get("ok"):
        payload = _normalize_visible_result(result, task)
        output = str(getattr(args, "output", "-") or "-")
        if output == "-":
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            with open(output, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return 0
    if args.command == "screenshot" and result.get("ok") and getattr(args, "output", "-") != "-":
        _write_screenshot_file(result, str(args.output), str(getattr(args, "format", "png") or "png"))
        print(json.dumps({"ok": True, "output": str(args.output)}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 69


def _action_from_args(args: argparse.Namespace) -> str:
    if args.command == "get":
        return f"get_{args.field}"
    if args.command == "wait":
        return "wait_text"
    if args.command == "tab":
        return f"tab_{args.tab_command}"
    return str(args.command).replace("-", "_")


def _task_from_args(args: argparse.Namespace, action: str) -> dict[str, Any]:
    if action not in READ_ONLY_ACTIONS:
        raise SystemExit(f"unsupported read-only action: {action}")
    task = {
        "id": uuid.uuid4().hex,
        "schema_version": SCHEMA_VERSION,
        "action": action,
        "session": str(getattr(args, "session", "guanlan-visible") or "guanlan-visible"),
        "created_at": time.time(),
        "read_only": True,
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "credential_material_access_allowed": False,
    }
    for key in (
        "url",
        "selector",
        "target",
        "value",
        "direction",
        "amount",
        "max_chars",
        "min_visible_items",
        "private_account_evidence",
        "include_items",
        "css",
        "text",
        "role",
        "name",
        "limit",
        "chunk_size",
        "start",
        "format",
        "timeout_ms",
        "target",
    ):
        if hasattr(args, key):
            task[key] = getattr(args, key)
    if hasattr(args, "tab_command"):
        task["tab_command"] = args.tab_command
    if hasattr(args, "target") and getattr(args, "target"):
        task["target"] = getattr(args, "target")
    if hasattr(args, "field"):
        task["field"] = getattr(args, "field")
    return task


def _submit_task(host: str, port: int, task: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    try:
        _request_json(host, port, "/tasks", method="POST", payload=task, timeout=3)
    except Exception as exc:
        return {
            "ok": False,
            "status": "bridge_unavailable",
            "error": str(exc),
            "setup": _setup_payload(),
        }
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = _request_json(host, port, f"/results/{task['id']}", timeout=3)
        except Exception as exc:
            return {"ok": False, "status": "bridge_result_error", "error": str(exc)}
        if result.get("ready"):
            return dict(result.get("result") or {})
        time.sleep(0.25)
    return {"ok": False, "status": "timeout", "error": f"openguanlan_timeout_after_{timeout:g}s"}


def _normalize_visible_result(result: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    data = dict(result.get("data") or result)
    visible_text = str(data.get("visible_text") or data.get("text") or "").strip()
    max_chars = max(int(task.get("max_chars") or 3000), 1)
    if len(visible_text) > max_chars:
        visible_text = visible_text[:max_chars]
    return {
        "url": str(data.get("url") or task.get("url") or "").strip(),
        "title": str(data.get("title") or "").strip(),
        "visible_text": visible_text,
        "items": data.get("items") or [],
        "collected_count": int(data.get("collected_count") or len(data.get("items") or [])),
        "requested_min_items": int(task.get("min_visible_items") or 0),
        "partial_reason": data.get("partial_reason") or "",
        "captured_at": data.get("captured_at") or time.time(),
        "visible_context": "openguanlan native browser bridge",
        "source_mode": "browser_visible",
        "browser_assisted": True,
        "user_authorized": True,
        "visible_page_only": True,
        "private_account_evidence": bool(task.get("private_account_evidence", False)),
        "session_dependent": True,
        "openguanlan": {
            "schema_version": SCHEMA_VERSION,
            "action": task.get("action"),
            "session": task.get("session"),
            "credential_material_access_allowed": False,
        },
    }


def _doctor(host: str, port: int) -> dict[str, Any]:
    status: dict[str, Any]
    try:
        status = _request_json(host, port, "/status", timeout=2)
        daemon_ok = True
    except Exception as exc:
        status = {"error": str(exc)}
        daemon_ok = False
    extension = _extension_payload()
    extension_seen = bool(status.get("extension_connected")) if daemon_ok else False
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if daemon_ok and extension_seen else ("daemon_ready" if daemon_ok else "needs_daemon"),
        "daemon": {
            "ok": daemon_ok,
            "host": host,
            "port": port,
            **status,
        },
        "extension": extension,
        "capabilities": _capabilities(),
        "safety": {
            "read_only": True,
            "credential_material_access_allowed": False,
            "forbidden_actions": FORBIDDEN_ACTIONS,
        },
        "next_steps": _setup_payload()["steps"],
    }


def _capabilities() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": "OpenGuanlan Browser Bridge",
        "absorbed_opencli_primitives": sorted(READ_ONLY_ACTIONS),
        "navigation_primitives": sorted(NAVIGATION_ACTIONS),
        "browser_visible_primitives": [
            "state",
            "find",
            "get text/html/title/url/value/attributes",
            "extract",
            "frames",
            "screenshot",
            "wait text",
            "scroll",
            "tab list/new/select",
        ],
        "excluded_opencli_primitives": [
            "click/type/fill/select/keys/upload/drag write actions",
            "cookie/token/localStorage/sessionStorage/browser profile export",
            "generic eval arbitrary JavaScript",
            "raw network bodies that may contain credential material",
            "generic external CLI auto-install hub",
            "platform private API calls outside browser-assist authorization",
        ],
        "output_schema": "Guanlan browser_visible JSON/JSONL",
        "privacy_boundary": "browser-assist user-authorized target visible page only",
    }


def _setup_payload() -> dict[str, Any]:
    extension = _extension_payload()
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "manual_extension_step_required",
        "path": extension["path"],
        "steps": [
            "Run `openguanlan daemon` in a local terminal.",
            f"Open chrome://extensions and load the unpacked extension directory: {extension['path']}",
            "Click the OpenGuanlan extension popup on the target tab and grant the current site.",
            "Run `openguanlan doctor --json` until daemon and extension are connected.",
            "Use `guanlan browser-assist run \"URL\" --adapter openguanlan --json` after user authorization.",
        ],
        "safety": {
            "extension_install_requires_user_confirmation": True,
            "site_permission_requires_user_confirmation": True,
            "read_only": True,
            "credential_material_access_allowed": False,
            "navigation_requires_browser_assist_authorization": True,
        },
        "chrome_store": {
            "package_command": "scripts/build_openguanlan_extension.sh",
            "privacy_policy": "website/openguanlan-browser-bridge-privacy.html",
            "default_host_permissions": ["http://127.0.0.1:19830/*", "http://localhost:19830/*"],
            "optional_host_permissions": ["<all_urls>"],
        },
    }


def _extension_payload() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "browser_bridge" / "extension"
    return {
        "name": "OpenGuanlan Browser Bridge",
        "path": str(path),
        "manifest": str(path / "manifest.json"),
        "exists": (path / "manifest.json").exists(),
        "manual_user_step_required": True,
        "popup": str(path / "popup.html"),
        "icons": {
            "16": str(path / "icons" / "icon-16.png"),
            "32": str(path / "icons" / "icon-32.png"),
            "48": str(path / "icons" / "icon-48.png"),
            "128": str(path / "icons" / "icon-128.png"),
        },
        "chrome_store_ready_assets": all(
            (path / rel).exists()
            for rel in [
                "manifest.json",
                "background.js",
                "popup.html",
                "popup.css",
                "popup.js",
                "icons/icon-16.png",
                "icons/icon-32.png",
                "icons/icon-48.png",
                "icons/icon-128.png",
            ]
        ),
    }


def _run_daemon(host: str, port: int, *, once: bool = False) -> int:
    class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True

    server = _ReusableThreadingHTTPServer((host, port), _BridgeHandler)
    print(json.dumps({"status": "listening", "host": host, "port": port, "schema_version": SCHEMA_VERSION}, ensure_ascii=False))
    if once:
        server.handle_request()
    else:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


class _BridgeHandler(BaseHTTPRequestHandler):
    server_version = "OpenGuanlanBridge/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/ping":
            self._write_json({"ok": True, "schema_version": SCHEMA_VERSION})
            return
        if self.path == "/status":
            self._write_json(
                {
                    "ok": True,
                    "schema_version": SCHEMA_VERSION,
                    "pending": STATE.pending.qsize(),
                    "extension_connected": time.time() - STATE.extension_seen_at < 10,
                    "extension_seen_at": STATE.extension_seen_at,
                    "extension_info": STATE.extension_info,
                }
            )
            return
        if self.path == "/extension/task":
            STATE.extension_seen_at = time.time()
            try:
                task = STATE.pending.get_nowait()
            except queue.Empty:
                self._write_json({"ok": True, "task": None})
            else:
                self._write_json({"ok": True, "task": task})
            return
        if self.path.startswith("/results/"):
            task_id = self.path.rsplit("/", 1)[-1]
            if task_id in STATE.results:
                self._write_json({"ok": True, "ready": True, "result": STATE.results.pop(task_id)})
            else:
                self._write_json({"ok": True, "ready": False})
            return
        self._write_json({"ok": False, "error": "not_found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        payload = self._read_json()
        if self.path == "/tasks":
            if payload.get("action") not in READ_ONLY_ACTIONS:
                self._write_json({"ok": False, "error": "unsupported_action"}, status=400)
                return
            STATE.pending.put(payload)
            self._write_json({"ok": True, "task_id": payload.get("id")})
            return
        if self.path == "/extension/hello":
            STATE.extension_seen_at = time.time()
            STATE.extension_info = dict(payload)
            self._write_json({"ok": True})
            return
        if self.path == "/extension/result":
            task_id = str(payload.get("task_id") or "")
            if not task_id:
                self._write_json({"ok": False, "error": "task_id_required"}, status=400)
                return
            STATE.results[task_id] = dict(payload.get("result") or {})
            STATE.extension_seen_at = time.time()
            self._write_json({"ok": True})
            return
        self._write_json({"ok": False, "error": "not_found"}, status=404)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-headers", "content-type")
        self.send_header("access-control-allow-methods", "GET,POST,OPTIONS")
        self.end_headers()

    def log_message(self, _format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace") if length else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-headers", "content-type")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _write_screenshot_file(result: dict[str, Any], output_path: str, image_format: str) -> None:
    data = dict(result.get("data") or result)
    data_url = str(data.get("data_url") or "")
    marker = ";base64,"
    if marker not in data_url:
        raise RuntimeError("screenshot_result_missing_data_url")
    encoded = data_url.split(marker, 1)[1]
    raw = base64.b64decode(encoded)
    path = Path(output_path)
    if not path.suffix:
        path = path.with_suffix(".jpg" if image_format == "jpeg" else ".png")
    path.write_bytes(raw)


def _request_json(
    host: str,
    port: int,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 5,
) -> dict[str, Any]:
    url = f"http://{host}:{port}{path}"
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if method == "POST" else None
    request = Request(url, data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc
    parsed = json.loads(raw or "{}")
    return parsed if isinstance(parsed, dict) else {}


def _print_payload(payload: dict[str, Any], *, as_json: bool = False) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
