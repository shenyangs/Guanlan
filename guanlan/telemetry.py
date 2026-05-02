# -*- coding: utf-8 -*-
"""Privacy-preserving anonymous usage telemetry for Guanlan.

Telemetry is intentionally tiny: it reports command/tool lifecycle metadata
only, never queries, URLs, cookies, result content, local paths, or config
values. Network failures are non-fatal and must not affect Guanlan itself.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Iterator
from urllib import request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from guanlan import __version__
from guanlan.config import Config

DEFAULT_TIMEOUT_SECONDS = 0.35
DEFAULT_SCHEMA_VERSION = 1
_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class TelemetrySettings:
    endpoint: str
    install_id: str
    enabled: bool
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


def _normalized_bool(value: object) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in _TRUTHY:
        return True
    if text in _FALSY:
        return False
    return None


def _env_flag(name: str) -> bool | None:
    return _normalized_bool(os.environ.get(name))


def _timeout_seconds() -> float:
    raw = os.environ.get("GUANLAN_TELEMETRY_TIMEOUT", "")
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return max(0.05, min(value, 2.0))


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
    """Return a stable anonymous agent id.

    GUANLAN_AGENT_ID lets an agent host provide a stable per-agent identifier.
    We hash it before sending so the collector only receives an anonymous id.
    Without that, fall back to one agent instance per install_id + agent_kind.
    """
    explicit = os.environ.get("GUANLAN_AGENT_ID", "").strip()
    seed = explicit if explicit else f"{install_id}|{agent_kind}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


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


def load_settings(config: Config | None = None) -> TelemetrySettings | None:
    """Return telemetry settings, or None when telemetry should not run."""
    env_enabled = _env_flag("GUANLAN_TELEMETRY")
    if env_enabled is False:
        return None

    cfg = config or Config()
    config_enabled = _normalized_bool(cfg.get("telemetry_enabled", True))
    if config_enabled is False:
        return None

    # CI is noisy and usually not representative of real agent use. Allow an
    # explicit GUANLAN_TELEMETRY=1 override for release smoke tests if needed.
    if env_enabled is not True and _env_flag("CI") is True:
        return None
    if env_enabled is not True and os.environ.get("PYTEST_CURRENT_TEST"):
        return None

    endpoint = (
        os.environ.get("GUANLAN_TELEMETRY_ENDPOINT")
        or str(cfg.get("telemetry_endpoint") or "")
    ).strip()
    if not endpoint:
        return None

    return TelemetrySettings(
        endpoint=endpoint.rstrip("/"),
        install_id=_get_or_create_install_id(cfg),
        enabled=True,
        timeout_seconds=_timeout_seconds(),
    )


def telemetry_status(config: Config | None = None) -> dict[str, object]:
    """Return a display-safe telemetry status summary."""
    cfg = config or Config()
    env_enabled = _env_flag("GUANLAN_TELEMETRY")
    config_enabled = _normalized_bool(cfg.get("telemetry_enabled", True))
    endpoint = (
        os.environ.get("GUANLAN_TELEMETRY_ENDPOINT")
        or str(cfg.get("telemetry_endpoint") or "")
    ).strip()
    active = load_settings(cfg) is not None
    return {
        "enabled": active,
        "configured": bool(endpoint),
        "endpoint": _display_endpoint(endpoint),
        "env_override": env_enabled,
        "config_enabled": config_enabled is not False,
    }


def _display_endpoint(endpoint: str) -> str:
    """Redact secret-bearing query parameters before showing an endpoint."""
    if not endpoint:
        return ""
    try:
        parts = urlsplit(endpoint)
        redacted = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key.lower() in {"token", "key", "secret", "api_key", "apikey"}:
                redacted.append((key, "***"))
            else:
                redacted.append((key, value))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted), parts.fragment))
    except Exception:
        return endpoint


def _payload(
    event: str,
    *,
    command: str,
    surface: str,
    session_id: str,
    invocation_id: str,
    install_id: str,
    status: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "schema": DEFAULT_SCHEMA_VERSION,
        "event": event,
        "install_id": install_id,
        "session_id": session_id,
        "invocation_id": invocation_id,
        "surface": surface,
        "command": command,
        "version": __version__,
        "platform": platform.system().lower() or "unknown",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "ts": int(time.time() * 1000),
    }
    agent_kind = _agent_kind()
    data["agent_kind"] = agent_kind
    data["agent_id"] = _agent_id(install_id, agent_kind)
    if status:
        data["status"] = status
    if duration_ms is not None:
        data["duration_ms"] = max(duration_ms, 0)
    return data


def emit(settings: TelemetrySettings, payload: dict[str, object]) -> None:
    """Best-effort POST. Exceptions are swallowed by design."""
    try:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            settings.endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": f"guanlan/{__version__}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=settings.timeout_seconds) as resp:
            resp.read(1)
    except Exception:
        return


@contextlib.contextmanager
def telemetry_span(
    command: str,
    *,
    surface: str = "cli",
    config: Config | None = None,
) -> Iterator[None]:
    """Report a start/end pair around a CLI command or MCP tool call."""
    settings = load_settings(config)
    if settings is None:
        yield
        return

    session_id = os.environ.get("GUANLAN_SESSION_ID", "").strip() or str(uuid.uuid4())
    invocation_id = str(uuid.uuid4())
    started = time.monotonic()
    emit(
        settings,
        _payload(
            "invocation_start",
            command=command,
            surface=surface,
            session_id=session_id,
            invocation_id=invocation_id,
            install_id=settings.install_id,
        ),
    )
    status = "ok"
    try:
        yield
    except SystemExit as exc:
        if exc.code not in (None, 0):
            status = "error"
        raise
    except BaseException:
        status = "error"
        raise
    finally:
        duration_ms = int((time.monotonic() - started) * 1000)
        emit(
            settings,
            _payload(
                "invocation_end",
                command=command,
                surface=surface,
                session_id=session_id,
                invocation_id=invocation_id,
                install_id=settings.install_id,
                status=status,
                duration_ms=duration_ms,
            ),
        )
