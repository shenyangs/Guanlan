# -*- coding: utf-8 -*-
"""Durable Research Case lifecycle and interruption guards."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from guanlan import research_cases


def test_case_completes_with_audited_state_transitions(tmp_path):
    db = tmp_path / "cases.db"
    case = research_cases.create_case("AI 政策", request={"limit": 80}, db_path=db)

    done = research_cases.run_case(
        case["case_id"],
        executor=lambda query, request, cancelled: {
            "query": query,
            "limit": request["limit"],
            "cancelled": cancelled(),
        },
        db_path=db,
    )

    assert done["state"] == "completed"
    assert done["result"]["limit"] == 80
    assert done["attempts"] == 1
    assert [item["event"] for item in done["events"]] == ["created", "run_started", "run_completed"]
    assert research_cases.task_view(case["case_id"], db_path=db)["status"] == "completed"


def test_cancelled_running_case_rejects_late_result(tmp_path):
    db = tmp_path / "cases.db"
    case = research_cases.create_case("不可覆盖", db_path=db)

    def executor(_query, _request, _cancelled):
        research_cases.cancel_case(case["case_id"], db_path=db)
        return {"must_not_persist": True}

    result = research_cases.run_case(case["case_id"], executor=executor, db_path=db)

    assert result["state"] == "cancelled"
    assert result["result"] == {}
    with pytest.raises(ValueError, match="invalid research case transition"):
        research_cases.resume_case(case["case_id"], db_path=db)


def test_pause_resume_and_process_recovery_are_durable(tmp_path):
    db = tmp_path / "cases.db"
    case = research_cases.create_case("恢复", db_path=db)
    paused = research_cases.pause_case(case["case_id"], db_path=db)
    resumed = research_cases.resume_case(case["case_id"], db_path=db)

    assert paused["state"] == "paused"
    assert resumed["state"] == "queued"
    with research_cases._connect(db) as conn:
        conn.execute("UPDATE research_cases SET state='running' WHERE case_id=?", (case["case_id"],))
        conn.commit()
    assert research_cases.recover_interrupted_cases(db_path=db) == 1
    recovered = research_cases.get_case(case["case_id"], db_path=db)
    assert recovered["state"] == "paused"
    assert recovered["stop_reason"] == "process_interrupted"


def test_case_expiry_is_terminal(tmp_path):
    db = tmp_path / "cases.db"
    case = research_cases.create_case("过期", expires_in=10, now=100.0, db_path=db)

    assert research_cases.expire_cases(now=111.0, db_path=db) == 1
    expired = research_cases.get_case(case["case_id"], db_path=db, expire=False)
    assert expired["state"] == "expired"
    with pytest.raises(ValueError, match="invalid research case transition"):
        research_cases.resume_case(case["case_id"], db_path=db)


def test_case_cli_create_and_status(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "cases.db"
    with patch("sys.argv", ["guanlan", "case", "create", "AI 政策", "--request", '{"limit":80}', "--db", str(db)]):
        main()
    created = json.loads(capsys.readouterr().out)
    with patch("sys.argv", ["guanlan", "case", "status", created["case_id"], "--task", "--db", str(db)]):
        main()
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "working"
    assert status["taskId"] == created["case_id"]
