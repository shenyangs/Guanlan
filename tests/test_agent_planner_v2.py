# -*- coding: utf-8 -*-
"""Tests for Guanlan Agent Planner v2 contracts."""

from guanlan.agent_planner import build_agent_plan_v2, review_agent_observation


def test_agent_plan_v2_keeps_basic_search_light():
    payload = build_agent_plan_v2("观澜 官网")

    assert payload["schema_version"] == "agent_plan_v2"
    assert payload["primary_command"].startswith("guanlan search")
    assert payload["task_model"]["task_type"] == "general_search"
    assert "research" in payload["capability_selection"]["downranked_capabilities"]
    assert not any(item["command"].startswith("guanlan research") for item in payload["agent_next_steps"])


def test_agent_plan_v2_fresh_ai_task_adds_hotnews_and_feeds_without_research():
    payload = build_agent_plan_v2("WPS AI 灵犀 最近热点", mode="fresh")
    chain = payload["capability_selection"]["recommended_chain"]

    assert payload["primary_command"] == "guanlan hotnews today --limit 80 --trends"
    assert "hotnews" in chain
    assert "feeds" in chain
    assert "research" in payload["capability_selection"]["downranked_capabilities"]
    assert not any(item["command"].startswith("guanlan research") for item in payload["agent_next_steps"])


def test_agent_plan_v2_brand_reputation_prefers_daily_path():
    payload = build_agent_plan_v2("某品牌 最近舆情 风险 今天", mode="fresh")

    assert payload["task_model"]["task_type"] == "brand_reputation"
    assert "daily" in payload["capability_selection"]["recommended_chain"]
    assert "品牌" in payload["task_model"]["target_audience"]


def test_agent_plan_v2_known_site_entry_prefers_map_then_read():
    payload = build_agent_plan_v2("在 docs.example.com 里找 pricing API 文档")

    assert payload["task_model"]["task_type"] == "site_entry_discovery"
    assert payload["primary_command"].startswith("guanlan map docs.example.com")
    assert "--read-top 2" in payload["primary_command"]
    assert payload["summary"].startswith("先跑 `guanlan map")
    assert payload["recommended_commands"][0]["command"].startswith("guanlan map docs.example.com")
    assert "map" in payload["capability_selection"]["recommended_chain"]
    assert payload["capability_selection"]["primary_capability"] == "map"
    assert "readings 中 usable" in " ".join(payload["self_check_contract"]["must_check"])


def test_agent_review_empty_or_small_result_repairs_with_large_pool():
    payload = review_agent_observation("LPG 丙烷 进口增长 2024", {"results": [], "limit": 5})

    assert payload["schema_version"] == "agent_review_v1"
    assert payload["next_decision"] == "repair"
    assert {"empty_results", "small_limit"} <= set(payload["signals"])
    assert any("--limit 80" in command for command in payload["next_commands"])


def test_agent_review_read_unusable_routes_to_diagnosis():
    payload = review_agent_observation(
        "页面补证",
        {"url": "https://example.com/a", "quality": {"status": "unusable"}, "message": "兜底状态: unusable"},
    )

    assert payload["next_decision"] == "repair"
    assert "read_unusable" in payload["signals"]
    assert payload["next_commands"] == ["guanlan diagnose page https://example.com/a --json"]


def test_agent_review_search_context_only_repairs_without_user_error():
    payload = review_agent_observation(
        "页面补证",
        {
            "url": "https://example.com/a",
            "read_evidence": {
                "schema_version": "read_evidence_v1",
                "usable": False,
                "extract_contract": {
                    "schema_version": "read_extract_contract_v1",
                    "status": "context_only",
                    "selected_backend": "search_fallback",
                    "can_cite_as_page_body": False,
                    "requires_followup": True,
                    "recommended_next_actions": ["read_original_url", "diagnose_page"],
                },
            },
        },
    )

    assert payload["next_decision"] == "repair"
    assert "search_context_only" in payload["signals"]
    assert payload["next_commands"] == ["guanlan diagnose page https://example.com/a --json"]
    assert "不要说 Guanlan 崩了" in payload["must_not"][0]


def test_agent_review_research_timeout_downgrades_to_search_read():
    payload = review_agent_observation("四川 通信管理局 骚扰电话 综合整治 2024 2025", "guanlan research 失败: The operation was aborted.")

    assert payload["next_decision"] == "repair"
    assert "research_failed" in payload["signals"]
    assert any(command.startswith("guanlan search") for command in payload["next_commands"])
    assert any("read <selected_url>" in command for command in payload["next_commands"])


def test_agent_review_read_pack_unusable_repairs_with_next_reads():
    payload = review_agent_observation(
        "站点文档",
        {
            "read_pack": {
                "schema_version": "representative_read_pack_v1",
                "summary": {"attempted": 2, "usable_count": 0, "error_count": 2},
                "next_read_commands": ["guanlan read https://example.com/docs --quality-report"],
            }
        },
    )

    assert payload["next_decision"] == "repair"
    assert "read_pack_unusable" in payload["signals"]
    assert payload["next_commands"] == ["guanlan read https://example.com/docs --quality-report"]


def test_agent_review_read_pack_usable_can_answer():
    payload = review_agent_observation(
        "站点文档",
        {
            "read_pack": {
                "schema_version": "representative_read_pack_v1",
                "summary": {"attempted": 1, "usable_count": 1, "error_count": 0},
                "readings": [{"url": "https://example.com/docs", "usable": True}],
            }
        },
    )

    assert payload["next_decision"] == "answer"
    assert "read_pack_usable" in payload["signals"]
