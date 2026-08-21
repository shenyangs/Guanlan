# -*- coding: utf-8 -*-
"""MCP Resources and durable Tasks extension contracts."""

from __future__ import annotations

import asyncio

from guanlan import archive, research_cases
from guanlan.integrations import mcp_server


def test_default_mcp_profiles_do_not_drift_and_tasks_is_opt_in():
    assert len(mcp_server._tool_definitions()) == 25
    assert len(mcp_server._tool_definitions("compact")) == 6
    assert {item["name"] for item in mcp_server._tool_definitions("tasks")} == mcp_server.MCP_TASK_TOOLS


def test_mcp_server_advertises_resources_and_task_lifecycle():
    server = mcp_server.create_server("tasks")
    capabilities = server.create_initialization_options().capabilities

    assert capabilities.resources is not None
    assert capabilities.tasks is not None
    assert capabilities.tasks.cancel is not None
    assert capabilities.tasks.requests.tools is not None
    assert {item["name"] for item in mcp_server._resource_templates()} == {
        "research-case", "research-case-result", "archive-snapshot", "snapshot-diff"
    }


def test_mcp_task_get_and_cancel_handlers_use_durable_case_store(tmp_path, monkeypatch):
    from mcp.types import (
        CancelTaskRequest,
        CancelTaskRequestParams,
        GetTaskRequest,
        GetTaskRequestParams,
    )

    db = tmp_path / "cases.db"
    monkeypatch.setattr(research_cases, "research_case_db_path", lambda: db)
    case = research_cases.create_case("MCP lifecycle")
    server = mcp_server.create_server("tasks")

    get_result = asyncio.run(
        server.request_handlers[GetTaskRequest](
            GetTaskRequest(params=GetTaskRequestParams(taskId=case["case_id"]))
        )
    )
    cancel_result = asyncio.run(
        server.request_handlers[CancelTaskRequest](
            CancelTaskRequest(params=CancelTaskRequestParams(taskId=case["case_id"]))
        )
    )

    assert get_result.root.status == "working"
    assert cancel_result.root.status == "cancelled"
    assert research_cases.get_case(case["case_id"])["state"] == "cancelled"


def test_resource_uri_reads_case_result_snapshot_and_diff(tmp_path, monkeypatch):
    case_db = tmp_path / "cases.db"
    archive_db = tmp_path / "archive.db"
    monkeypatch.setattr(research_cases, "research_case_db_path", lambda: case_db)
    monkeypatch.setattr(archive, "archive_db_path", lambda: archive_db)
    case = research_cases.create_case("资源", db_path=case_db)
    done = research_cases.run_case(case["case_id"], executor=lambda *_args: {"ok": True}, db_path=case_db)
    first = archive.add_document("https://example.com/a", "成功率 91%。", db_path=archive_db)
    second = archive.add_document("https://example.com/a", "成功率 99%。", db_path=archive_db)

    case_resource = mcp_server._read_resource_uri(f"guanlan://cases/{done['case_id']}")
    result_resource = mcp_server._read_resource_uri(f"guanlan://cases/{done['case_id']}/result")
    snapshot_resource = mcp_server._read_resource_uri(f"guanlan://snapshots/{second['current_snapshot_id']}")
    diff_resource = mcp_server._read_resource_uri(
        f"guanlan://diff/{first['current_snapshot_id']}/{second['current_snapshot_id']}"
    )
    assert case_resource["state"] == "completed"
    assert result_resource["result"] == {"ok": True}
    assert snapshot_resource["passages"]
    assert diff_resource["claim_delta"]["summary"] == {"value_changed": 1}


def test_http_research_case_lifecycle(tmp_path, monkeypatch):
    from guanlan import serve

    db = tmp_path / "cases.db"
    monkeypatch.setattr(research_cases, "research_case_db_path", lambda: db)
    status, created = serve.dispatch_request("POST", "/cases", {"query": "HTTP Case", "request": {"limit": 80}})
    status2, listed = serve.dispatch_request("GET", "/cases?state=queued")
    status3, cancelled = serve.dispatch_request("POST", f"/cases/{created['case_id']}/cancel")

    assert status == 201
    assert status2 == 200 and listed["cases"][0]["case_id"] == created["case_id"]
    assert status3 == 200 and cancelled["state"] == "cancelled"
