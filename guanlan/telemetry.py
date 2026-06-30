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
import signal
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib import request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from guanlan import __version__
from guanlan.config import Config

DEFAULT_TIMEOUT_SECONDS = 0.35
DEFAULT_HEARTBEAT_SECONDS = 30.0
DEFAULT_SCHEMA_VERSION = 1
DEFAULT_ENDPOINT = (
    "https://guanlan.xin/guanlan-telemetry/v1/events"
    "?token=2ccdd0259e643de3306e62ee105cecef3daa5da4961b0a57"
)
MAX_QUEUE_EVENTS = 2000
MAX_FLUSH_EVENTS = 5
END_EVENT_RETRY = 3
END_EVENT_RETRY_DELAY_SECONDS = 0.05
_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}
_QUEUE_LOCK = threading.Lock()


@dataclass(frozen=True)
class TelemetrySettings:
    endpoint: str
    install_id: str
    enabled: bool
    queue_path: str
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


def _heartbeat_seconds() -> float:
    raw = os.environ.get("GUANLAN_TELEMETRY_HEARTBEAT", "")
    if not raw:
        return DEFAULT_HEARTBEAT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_HEARTBEAT_SECONDS
    return max(5.0, min(value, 300.0))


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
        or DEFAULT_ENDPOINT
    ).strip()
    if not endpoint:
        return None

    return TelemetrySettings(
        endpoint=endpoint.rstrip("/"),
        install_id=_get_or_create_install_id(cfg),
        enabled=True,
        queue_path=str(cfg.config_dir / "telemetry_queue.jsonl"),
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
        or DEFAULT_ENDPOINT
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


def emit(settings: TelemetrySettings, payload: dict[str, object], retries: int = 0) -> None:
    """Best-effort POST with local durable queue on failure."""
    attempts = max(1, 1 + int(retries or 0))
    for index in range(attempts):
        if _post(settings, payload):
            return
        if index + 1 < attempts:
            time.sleep(END_EVENT_RETRY_DELAY_SECONDS)
    _enqueue(settings, payload)


def emit_transient(settings: TelemetrySettings, payload: dict[str, object]) -> None:
    """Best-effort POST without queueing, used for heartbeat noise."""
    _post(settings, payload)


def _post(settings: TelemetrySettings, payload: dict[str, object]) -> bool:
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
        return True
    except Exception:
        return False


def _queue_limit() -> int:
    raw = os.environ.get("GUANLAN_TELEMETRY_QUEUE_LIMIT", "")
    if not raw:
        return MAX_QUEUE_EVENTS
    try:
        return max(0, min(int(raw), 10000))
    except ValueError:
        return MAX_QUEUE_EVENTS


def _flush_limit() -> int:
    raw = os.environ.get("GUANLAN_TELEMETRY_FLUSH_LIMIT", "")
    if not raw:
        return MAX_FLUSH_EVENTS
    try:
        return max(0, min(int(raw), 100))
    except ValueError:
        return MAX_FLUSH_EVENTS


def _read_queue(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    items = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    items.append(payload)
    except OSError:
        return []
    return items


def _write_queue(path: Path, items: list[dict[str, object]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        tmp.replace(path)
    except OSError:
        return


def _enqueue(settings: TelemetrySettings, payload: dict[str, object]) -> None:
    limit = _queue_limit()
    if limit <= 0:
        return
    path = Path(settings.queue_path)
    queued = dict(payload)
    queued["queued_ms"] = int(time.time() * 1000)
    with _QUEUE_LOCK:
        items = _read_queue(path)
        items.append(queued)
        if len(items) > limit:
            items = items[-limit:]
        _write_queue(path, items)


def flush_queue(settings: TelemetrySettings) -> int:
    """Flush a small number of queued events. Returns sent count."""
    limit = _flush_limit()
    if limit <= 0:
        return 0
    path = Path(settings.queue_path)
    with _QUEUE_LOCK:
        items = _read_queue(path)
        if not items:
            return 0
        sent = 0
        remaining = []
        for index, item in enumerate(items):
            if sent >= limit:
                remaining.extend(items[index:])
                break
            if _post(settings, item):
                sent += 1
            else:
                remaining.extend(items[index:])
                break
        if remaining:
            _write_queue(path, remaining)
        else:
            try:
                path.unlink()
            except OSError:
                pass
        return sent


def _start_heartbeat(
    settings: TelemetrySettings,
    *,
    command: str,
    surface: str,
    session_id: str,
    invocation_id: str,
) -> tuple[threading.Event, threading.Thread]:
    stop = threading.Event()
    interval = _heartbeat_seconds()

    def run():
        while not stop.wait(interval):
            emit_transient(
                settings,
                _payload(
                    "invocation_heartbeat",
                    command=command,
                    surface=surface,
                    session_id=session_id,
                    invocation_id=invocation_id,
                    install_id=settings.install_id,
                ),
            )

    thread = threading.Thread(target=run, name="guanlan-telemetry-heartbeat", daemon=True)
    thread.start()
    return stop, thread


def _install_termination_handlers(handler) -> dict[int, object]:
    """Install temporary handlers so host timeouts can still emit an end event."""
    if threading.current_thread() is not threading.main_thread():
        return {}
    previous: dict[int, object] = {}
    signals = [signal.SIGINT]
    for name in ("SIGTERM", "SIGHUP"):
        signum = getattr(signal, name, None)
        if signum is not None:
            signals.append(signum)
    for signum in signals:
        try:
            previous[int(signum)] = signal.getsignal(signum)
            signal.signal(signum, handler)
        except (OSError, RuntimeError, ValueError):
            continue
    return previous


def _restore_termination_handlers(previous: dict[int, object]) -> None:
    for signum, handler in previous.items():
        try:
            signal.signal(signum, handler)
        except (OSError, RuntimeError, ValueError):
            continue


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
    flush_queue(settings)
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
    heartbeat_stop, heartbeat_thread = _start_heartbeat(
        settings,
        command=command,
        surface=surface,
        session_id=session_id,
        invocation_id=invocation_id,
    )
    status = "ok"
    ended = False
    end_lock = threading.Lock()

    def finish(final_status: str) -> None:
        nonlocal ended
        with end_lock:
            if ended:
                return
            ended = True
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=0.1)
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
                status=final_status,
                duration_ms=duration_ms,
            ),
            retries=END_EVENT_RETRY,
        )
        # Push tail events opportunistically; still non-fatal on network failure.
        flush_queue(settings)

    def handle_termination(signum, _frame):
        finish("error")
        if int(signum) == int(signal.SIGINT):
            raise KeyboardInterrupt
        raise SystemExit(128 + int(signum))

    previous_handlers = _install_termination_handlers(handle_termination)
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
        _restore_termination_handlers(previous_handlers)
        finish(status)
