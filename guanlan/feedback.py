# -*- coding: utf-8 -*-
"""User feedback reporting for search dissatisfaction diagnostics.

Unlike anonymous lifecycle telemetry, this payload intentionally includes
user-provided query/reason text so operators can improve search quality.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib import request
from urllib.parse import urlsplit, urlunsplit

from guanlan import __version__
from guanlan.config import Config

DEFAULT_TIMEOUT_SECONDS = 1.2
DEFAULT_SCHEMA_VERSION = 1
DEFAULT_ENDPOINT = (
    "https://guanlan.xin/guanlan-telemetry/v1/feedback"
    "?token=2ccdd0259e643de3306e62ee105cecef3daa5da4961b0a57"
)
MAX_QUEUE_ITEMS = 300
MAX_FLUSH_ITEMS = 8
_QUEUE_LOCK = threading.Lock()


@dataclass(frozen=True)
class FeedbackSettings:
    endpoint: str
    install_id: str
    queue_path: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


def _normalized_bool(value: object) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _agent_kind() -> str:
    env = os.environ
    if env.get("CODEX_HOME") or env.get("CODEX_SANDBOX") or env.get("OPENAI_CODEX"):
        return "codex"
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code"
    if env.get("CURSOR_TRACE_ID") or env.get("CURSOR_AGENT"):
        return "cursor"
    if env.get("OPENWEBUI_URL") or env.get("OPEN_WEBUI"):
        return "openwebui"
    return "unknown"


def _agent_id(install_id: str, agent_kind: str) -> str:
    explicit = os.environ.get("GUANLAN_AGENT_ID", "").strip()
    seed = explicit if explicit else f"{install_id}|{agent_kind}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def _clamp(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        return text[:limit]
    return text


def _feedback_from_telemetry(endpoint: str) -> str:
    parts = urlsplit(endpoint.strip())
    path = parts.path or ""
    if path.endswith("/v1/events"):
        path = path[: -len("/v1/events")] + "/v1/feedback"
    elif path.endswith("/events"):
        path = path[: -len("/events")] + "/feedback"
    elif not path.endswith("/v1/feedback"):
        path = path.rstrip("/") + "/v1/feedback"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _timeout_seconds() -> float:
    raw = os.environ.get("GUANLAN_FEEDBACK_TIMEOUT", "")
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return max(0.2, min(value, 4.0))


def _get_or_create_install_id(config: Config) -> str:
    env_install_id = os.environ.get("GUANLAN_INSTALL_ID", "").strip()
    if env_install_id:
        return env_install_id

    install_id = str(config.get("telemetry_install_id") or "").strip()
    if install_id:
        return install_id

    install_id = str(uuid.uuid4())
    config.set("telemetry_install_id", install_id)
    return install_id


def load_feedback_settings(config: Config | None = None) -> FeedbackSettings | None:
    cfg = config or Config()
    if _normalized_bool(os.environ.get("GUANLAN_FEEDBACK")) is False:
        return None

    telemetry_enabled = _normalized_bool(cfg.get("telemetry_enabled", True))
    if telemetry_enabled is False:
        return None

    raw = (
        os.environ.get("GUANLAN_FEEDBACK_ENDPOINT")
        or str(cfg.get("feedback_endpoint") or "").strip()
    )
    if not raw:
        telemetry_ep = (
            os.environ.get("GUANLAN_TELEMETRY_ENDPOINT")
            or str(cfg.get("telemetry_endpoint") or "").strip()
            or DEFAULT_ENDPOINT.replace("/v1/feedback", "/v1/events")
        )
        raw = _feedback_from_telemetry(telemetry_ep)

    if not raw:
        return None

    return FeedbackSettings(
        endpoint=raw.rstrip("/"),
        install_id=_get_or_create_install_id(cfg),
        queue_path=str(cfg.config_dir / "feedback_queue.jsonl"),
        timeout_seconds=_timeout_seconds(),
    )


def _load_queue(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            with contextlib.suppress(Exception):
                items.append(json.loads(line))
    return items


def _save_queue(path: Path, items: list[dict]) -> None:
    if not items:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for item in items[-MAX_QUEUE_ITEMS:]:
            f.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def _post(settings: FeedbackSettings, payload: dict[str, object]) -> bool:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = request.Request(
        settings.endpoint,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": f"guanlan/{__version__}"},
        method="POST",
    )
    try:
        with contextlib.closing(request.urlopen(req, timeout=settings.timeout_seconds)) as resp:
            code = int(getattr(resp, "status", 0) or 0)
            return 200 <= code < 300
    except Exception:
        return False


def _enqueue(settings: FeedbackSettings, payload: dict[str, object]) -> None:
    path = Path(settings.queue_path)
    with _QUEUE_LOCK:
        items = _load_queue(path)
        items.append(payload)
        _save_queue(path, items)


def _flush_queue(settings: FeedbackSettings) -> int:
    path = Path(settings.queue_path)
    with _QUEUE_LOCK:
        items = _load_queue(path)
        if not items:
            return 0
        sent = 0
        keep = list(items)
        for payload in items[:MAX_FLUSH_ITEMS]:
            if not _post(settings, payload):
                break
            sent += 1
            keep.pop(0)
        _save_queue(path, keep)
        return sent


def _payload(
    settings: FeedbackSettings,
    *,
    query_text: str,
    reason_text: str,
    command: str,
    surface: str,
    profile: str,
    backend: str,
) -> dict[str, object]:
    agent_kind = _agent_kind()
    return {
        "schema": DEFAULT_SCHEMA_VERSION,
        "event": "search_feedback",
        "ts": int(time.time() * 1000),
        "install_id": settings.install_id,
        "agent_kind": agent_kind,
        "agent_id": _agent_id(settings.install_id, agent_kind),
        "surface": _clamp(surface or "cli", 32),
        "command": _clamp(command or "search", 40),
        "profile": _clamp(profile, 24),
        "backend": _clamp(backend, 40),
        "query_text": _clamp(query_text, 200),
        "reason_text": _clamp(reason_text, 600),
        "version": __version__,
        "platform": platform.system().lower() or "unknown",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def submit_feedback(
    query_text: str,
    reason_text: str,
    *,
    command: str = "search",
    surface: str = "cli",
    profile: str = "",
    backend: str = "",
    config: Config | None = None,
) -> dict[str, object]:
    query = _clamp(query_text, 200)
    reason = _clamp(reason_text, 600)
    if not query or not reason:
        return {"ok": False, "queued": False, "message": "query/reason required"}

    settings = load_feedback_settings(config)
    if settings is None:
        return {"ok": False, "queued": False, "message": "feedback disabled"}

    payload = _payload(
        settings,
        query_text=query,
        reason_text=reason,
        command=command,
        surface=surface,
        profile=profile,
        backend=backend,
    )
    if _post(settings, payload):
        with contextlib.suppress(Exception):
            _flush_queue(settings)
        return {"ok": True, "queued": False, "message": "sent"}

    _enqueue(settings, payload)
    return {"ok": True, "queued": True, "message": "queued"}
