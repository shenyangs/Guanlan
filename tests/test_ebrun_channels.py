# -*- coding: utf-8 -*-
"""Tests for Ebrun vertical channel routing."""

from guanlan import hotnews
from guanlan.ebrun_channels import ebrun_query_variants, match_ebrun_channels, resolve_ebrun_channel
from guanlan.router import build_route_plan
from guanlan.webtools import build_query_strategy


def test_ebrun_channel_resolution_and_matching():
    assert resolve_ebrun_channel("temu").sub_channel == "Temu"
    assert resolve_ebrun_channel("xhs").sub_channel == "小红书"

    matched = match_ebrun_channels("Temu 跨境电商 卖家 成本", limit=3)
    aliases = {item.alias for item in matched}
    assert "temu" in aliases
    assert "cross-border" in aliases

    ai_only = match_ebrun_channels("OpenAI 最新模型", limit=3)
    assert not any(item.alias == "ai" for item in ai_only)


def test_ebrun_query_variants_are_site_bounded():
    variants = ebrun_query_variants("小红书电商 买手 直播", limit=2)
    assert variants
    assert variants[0]["source_id"] == "ebrun:xiaohongshu"
    assert "site:ebrun.com" in variants[0]["query"]
    assert "小红书电商" in variants[0]["query"]


def test_ecommerce_route_recommends_ebrun_channel_followups():
    plan = build_route_plan("Temu 跨境电商 卖家 成本", profile="china")
    commands = "\n".join(plan.recommended_commands)
    assert "guanlan hotnews ebrun:" in commands
    assert "ebrun:temu" in commands or "ebrun:cross-border" in commands
    assert "site:ebrun.com" in commands


def test_ecommerce_query_strategy_adds_ebrun_channel_variant():
    plan = build_route_plan("视频号 电商 私域 商家", profile="china")
    strategy = build_query_strategy(
        "视频号 电商 私域 商家",
        route_plan=plan.to_dict(),
        quality={"requested_scope": "ecommerce"},
    )
    variants = strategy["variants"]
    assert any(item["role"] == "ecommerce_vertical_feed" for item in variants)
    assert any("site:ebrun.com" in item["query"] and "视频号" in item["query"] for item in variants)


def test_fetch_ebrun_normalizes_public_json(monkeypatch):
    def fake_read_json(url):
        assert url.endswith("information_channel_67.json")
        return [
            {
                "title": "Temu 卖家服务调整",
                "url": "https://www.ebrun.com/20260514/1.shtml",
                "author": "亿邦动力",
                "publish_time": "2026-05-14 10:00:00",
                "summary": "平台规则变化影响跨境卖家。",
            }
        ]

    monkeypatch.setattr(hotnews, "_read_json", fake_read_json)
    items = hotnews.fetch_ebrun("temu", limit=80)

    assert len(items) == 1
    assert items[0]["source_id"] == "ebrun:temu"
    assert items[0]["evidence_role"] == "ecommerce_vertical_feed"
    assert items[0]["source_card"]["scope_id"] == "ecommerce"
    assert items[0]["metrics"]["requested_limit"] == 80
    assert "server_side_limit_low" in items[0]["risk_tags"]
