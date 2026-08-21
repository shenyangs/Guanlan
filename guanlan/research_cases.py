# -*- coding: utf-8 -*-
"""Durable, local Research Case state machine.

Cases are explicit checkpoints around existing research calls.  The module is
deliberately scheduler-free: callers create a case and explicitly advance it.
This keeps cancellation and recovery deterministic for CLI, HTTP and MCP.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from guanlan.evidence_kernel import stable_id

CASE_SCHEMA_VERSION = "research_case_v1"
CASE_STORE_SCHEMA_VERSION = 1
CASE_STATES = frozenset({"queued", "running", "paused", "completed", "failed", "cancelled", "expired"})
TERMINAL_CASE_STATES = frozenset({"completed", "cancelled", "expired"})
_TRANSITIONS = {
    "queued": {"running", "paused", "cancelled", "expired"},
    "running": {"paused", "completed", "failed", "cancelled", "expired"},
    "paused": {"queued", "cancelled", "expired"},
    "failed": {"queued", "cancelled", "expired"},
    "completed": set(),
    "cancelled": set(),
    "expired": set(),
}


def research_case_db_path() -> Path:
    return Path.home() / ".guanlan" / "research-cases.db"


def create_case(
    query: str,
    *,
    request: dict[str, Any] | None = None,
    requirements: dict[str, Any] | None = None,
    budget: dict[str, Any] | None = None,
    expires_in: int | None = 7 * 24 * 3600,
    db_path: str | Path | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    value = str(query or "").strip()
    if not value:
        raise ValueError("query is required")
    created_at = float(now if now is not None else time.time())
    expires_at = created_at + max(int(expires_in), 1) if expires_in is not None else None
    case_id = stable_id("case", created_at, value, json.dumps(request or {}, sort_keys=True, ensure_ascii=False))
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO research_cases (
                case_id, query, state, request_json, requirements_json, budget_json,
                checkpoint_json, result_json, error_json, stop_reason, revision,
                created_at, updated_at, expires_at
            ) VALUES (?, ?, 'queued', ?, ?, ?, '{}', '', '', '', 1, ?, ?, ?)
            """,
            (
                case_id,
                value,
                _dumps(request or {}),
                _dumps(requirements or {}),
                _dumps(budget or {}),
                created_at,
                created_at,
                expires_at,
            ),
        )
        _record_event(conn, case_id, "created", "", "queued", {"checkpoint": "created"}, created_at)
        conn.commit()
    return get_case(case_id, db_path=db_path, expire=False)


def get_case(case_id: str, *, db_path: str | Path | None = None, expire: bool = True) -> dict[str, Any]:
    value = str(case_id or "").strip()
    if not value:
        raise ValueError("case_id is required")
    if expire:
        expire_cases(db_path=db_path, case_id=value)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM research_cases WHERE case_id = ?", (value,)).fetchone()
        if not row:
            raise ValueError(f"research case not found: {case_id}")
        events = conn.execute(
            "SELECT * FROM research_case_events WHERE case_id = ? ORDER BY event_id ASC", (value,)
        ).fetchall()
    record = _case_record(row)
    record["events"] = [_event_record(item) for item in events]
    return record


def list_cases(
    *,
    state: str | None = None,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    expire_cases(db_path=db_path)
    normalized = str(state or "").strip().lower()
    if normalized and normalized not in CASE_STATES:
        raise ValueError(f"invalid case state: {state}")
    with _connect(db_path) as conn:
        if normalized:
            rows = conn.execute(
                "SELECT * FROM research_cases WHERE state = ? ORDER BY updated_at DESC LIMIT ?",
                (normalized, max(int(limit), 1)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM research_cases ORDER BY updated_at DESC LIMIT ?", (max(int(limit), 1),)
            ).fetchall()
    return [_case_record(row) for row in rows]


def run_case(
    case_id: str,
    *,
    executor: Callable[[str, dict[str, Any], Callable[[], bool]], dict[str, Any]] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Advance one queued case; late results never overwrite pause/cancel."""

    case = get_case(case_id, db_path=db_path)
    if case["state"] != "queued":
        raise ValueError(f"case must be queued before run; current state is {case['state']}")
    running = _transition(
        case_id,
        "running",
        event="run_started",
        checkpoint={"phase": "research", "attempt": int(case.get("attempts") or 0) + 1},
        db_path=db_path,
        expected_revision=int(case["revision"]),
        increment_attempts=True,
    )
    run_revision = int(running["revision"])

    def cancelled() -> bool:
        current = get_case(case_id, db_path=db_path, expire=False)
        return current["state"] != "running" or int(current["revision"]) != run_revision

    if executor is None:
        executor = _default_executor
    try:
        result = executor(str(running["query"]), dict(running["request"]), cancelled)
    except Exception as exc:
        if cancelled():
            return get_case(case_id, db_path=db_path, expire=False)
        return _transition(
            case_id,
            "failed",
            event="run_failed",
            error={"type": type(exc).__name__, "message": str(exc)},
            stop_reason="executor_error",
            db_path=db_path,
            expected_revision=run_revision,
        )
    if cancelled():
        return get_case(case_id, db_path=db_path, expire=False)
    return _transition(
        case_id,
        "completed",
        event="run_completed",
        result=result,
        checkpoint={"phase": "completed"},
        stop_reason="completed",
        db_path=db_path,
        expected_revision=run_revision,
    )


def pause_case(case_id: str, *, reason: str = "user_paused", db_path: str | Path | None = None) -> dict[str, Any]:
    case = get_case(case_id, db_path=db_path)
    return _transition(
        case_id,
        "paused",
        event="paused",
        stop_reason=reason,
        db_path=db_path,
        expected_revision=int(case["revision"]),
    )


def resume_case(case_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    case = get_case(case_id, db_path=db_path)
    return _transition(
        case_id,
        "queued",
        event="resumed",
        stop_reason="",
        error={},
        db_path=db_path,
        expected_revision=int(case["revision"]),
    )


def cancel_case(case_id: str, *, reason: str = "user_cancelled", db_path: str | Path | None = None) -> dict[str, Any]:
    case = get_case(case_id, db_path=db_path)
    return _transition(
        case_id,
        "cancelled",
        event="cancelled",
        stop_reason=reason,
        db_path=db_path,
        expected_revision=int(case["revision"]),
    )


def expire_cases(
    *, db_path: str | Path | None = None, case_id: str | None = None, now: float | None = None
) -> int:
    timestamp = float(now if now is not None else time.time())
    with _connect(db_path) as conn:
        sql = (
            "SELECT case_id, state, revision FROM research_cases "
            "WHERE expires_at IS NOT NULL AND expires_at <= ? AND state NOT IN ('completed','cancelled','expired')"
        )
        params: list[Any] = [timestamp]
        if case_id:
            sql += " AND case_id = ?"
            params.append(str(case_id))
        rows = conn.execute(sql, params).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE research_cases SET state='expired', stop_reason='expired', revision=revision+1, updated_at=? "
                "WHERE case_id=? AND revision=?",
                (timestamp, row["case_id"], row["revision"]),
            )
            _record_event(conn, str(row["case_id"]), "expired", str(row["state"]), "expired", {}, timestamp)
        conn.commit()
    return len(rows)


def case_resource(case_id: str, *, include_result: bool = True, db_path: str | Path | None = None) -> dict[str, Any]:
    case = get_case(case_id, db_path=db_path)
    if not include_result:
        case.pop("result", None)
    case["resource_uri"] = f"guanlan://cases/{case_id}"
    case["result_resource_uri"] = f"guanlan://cases/{case_id}/result" if case.get("result") else ""
    return case


def task_view(case_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    case = get_case(case_id, db_path=db_path)
    status = {
        "queued": "working",
        "running": "working",
        "paused": "input_required",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
        "expired": "cancelled",
    }[str(case["state"])]
    payload = {
        "taskId": case["case_id"],
        "status": status,
        "statusMessage": case.get("stop_reason") or case.get("error", {}).get("message") or "",
        "createdAt": _rfc3339(case["created_at"]),
        "lastUpdatedAt": _rfc3339(case["updated_at"]),
        "ttl": max(int(float(case["expires_at"]) - time.time()), 0) if case.get("expires_at") else None,
        "meta": {"guanlanCaseState": case["state"], "revision": case["revision"]},
    }
    if status == "completed":
        payload["result"] = case.get("result") or {}
    return payload


def recover_interrupted_cases(*, db_path: str | Path | None = None) -> int:
    """Move process-interrupted running cases to paused so they can resume."""
    timestamp = time.time()
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT case_id FROM research_cases WHERE state='running'").fetchall()
        for row in rows:
            case_id = str(row["case_id"])
            conn.execute(
                "UPDATE research_cases SET state='paused', stop_reason='process_interrupted', "
                "revision=revision+1, updated_at=? WHERE case_id=? AND state='running'",
                (timestamp, case_id),
            )
            _record_event(conn, case_id, "process_interrupted", "running", "paused", {}, timestamp)
        conn.commit()
    return len(rows)


def _transition(
    case_id: str,
    target: str,
    *,
    event: str,
    db_path: str | Path | None,
    expected_revision: int,
    checkpoint: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    stop_reason: str | None = None,
    increment_attempts: bool = False,
) -> dict[str, Any]:
    if target not in CASE_STATES:
        raise ValueError(f"invalid target state: {target}")
    timestamp = time.time()
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM research_cases WHERE case_id = ?", (case_id,)).fetchone()
        if not row:
            raise ValueError(f"research case not found: {case_id}")
        source = str(row["state"])
        if target not in _TRANSITIONS[source]:
            raise ValueError(f"invalid research case transition: {source} -> {target}")
        if int(row["revision"]) != int(expected_revision):
            raise RuntimeError("research case changed concurrently; reload before retrying")
        fields = ["state = ?", "revision = revision + 1", "updated_at = ?"]
        values: list[Any] = [target, timestamp]
        if checkpoint is not None:
            fields.append("checkpoint_json = ?")
            values.append(_dumps(checkpoint))
        if result is not None:
            fields.append("result_json = ?")
            values.append(_dumps(result))
        if error is not None:
            fields.append("error_json = ?")
            values.append(_dumps(error))
        if stop_reason is not None:
            fields.append("stop_reason = ?")
            values.append(stop_reason)
        if increment_attempts:
            fields.append("attempts = attempts + 1")
        values.extend([case_id, expected_revision])
        cursor = conn.execute(
            f"UPDATE research_cases SET {', '.join(fields)} WHERE case_id = ? AND revision = ?", values
        )
        if cursor.rowcount != 1:
            raise RuntimeError("research case changed concurrently; reload before retrying")
        _record_event(conn, case_id, event, source, target, checkpoint or {}, timestamp)
        conn.commit()
    return get_case(case_id, db_path=db_path, expire=False)


def _default_executor(query: str, request: dict[str, Any], cancelled: Callable[[], bool]) -> dict[str, Any]:
    if cancelled():
        return {}
    from guanlan.tool_invocation import normalize_research_request
    from guanlan.web.research import build_research_packet

    normalized = normalize_research_request({"query": query, **request})
    value = normalized.pop("query")
    return build_research_packet(value, **normalized)


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path).expanduser() if db_path else research_case_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_cases (
            case_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            state TEXT NOT NULL,
            request_json TEXT NOT NULL DEFAULT '{}',
            requirements_json TEXT NOT NULL DEFAULT '{}',
            budget_json TEXT NOT NULL DEFAULT '{}',
            checkpoint_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '',
            error_json TEXT NOT NULL DEFAULT '',
            stop_reason TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            expires_at REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_case_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            event TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            FOREIGN KEY(case_id) REFERENCES research_cases(case_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_cases_state_updated ON research_cases(state, updated_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_case_events_case ON research_case_events(case_id, event_id)")
    conn.execute(f"PRAGMA user_version = {CASE_STORE_SCHEMA_VERSION}")
    conn.commit()


def _record_event(
    conn: sqlite3.Connection,
    case_id: str,
    event: str,
    source: str,
    target: str,
    detail: dict[str, Any],
    created_at: float,
) -> None:
    conn.execute(
        "INSERT INTO research_case_events (case_id,event,from_state,to_state,detail_json,created_at) VALUES (?,?,?,?,?,?)",
        (case_id, event, source, target, _dumps(detail), created_at),
    )


def _case_record(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    return {
        "schema_version": CASE_SCHEMA_VERSION,
        "case_id": data["case_id"],
        "query": data["query"],
        "state": data["state"],
        "request": _loads(data.get("request_json")),
        "requirements": _loads(data.get("requirements_json")),
        "budget": _loads(data.get("budget_json")),
        "checkpoint": _loads(data.get("checkpoint_json")),
        "result": _loads(data.get("result_json")),
        "error": _loads(data.get("error_json")),
        "stop_reason": data.get("stop_reason") or "",
        "attempts": int(data.get("attempts") or 0),
        "revision": int(data.get("revision") or 0),
        "created_at": float(data["created_at"]),
        "updated_at": float(data["updated_at"]),
        "expires_at": float(data["expires_at"]) if data.get("expires_at") is not None else None,
    }


def _event_record(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    return {
        "event_id": int(data["event_id"]),
        "event": data["event"],
        "from_state": data["from_state"],
        "to_state": data["to_state"],
        "detail": _loads(data.get("detail_json")),
        "created_at": float(data["created_at"]),
    }


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _rfc3339(timestamp: float) -> str:
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat().replace("+00:00", "Z")
