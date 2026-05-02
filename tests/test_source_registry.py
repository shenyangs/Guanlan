# -*- coding: utf-8 -*-
"""Tests for the centralized Guanlan source matrix."""

from guanlan import source_registry


def test_source_matrix_marks_native_and_optional_boundaries():
    sources = source_registry.list_hotnews_sources()

    assert sources["bilibili-hot-search"]["backend"] == "native"
    assert sources["sspai"]["backend"] == "native"
    assert sources["newsnow:thepaper"]["backend"] == "optional"
    assert sources["newsnow:thepaper"]["optional_backend"] == "newsnow"
    assert sources["newsnow:thepaper"]["verified"] is False
    assert sources["newsnow:thepaper"]["verification"] == "backend_dependent"
    assert "记录其信源身份与适用场景" in sources["newsnow:toutiao"]["notes"]


def test_source_matrix_resolves_aliases_and_feed_sources():
    assert source_registry.resolve_source_id("bili-hot-search") == "bilibili-hot-search"
    assert source_registry.get_source_metadata("bili-hot-search")["source_domain"] == "bilibili.com"

    feeds = source_registry.list_feed_sources()
    assert feeds["curated"]["evidence_role"] == "reading_discovery_signal"
    assert feeds["wechat-rss"]["risk_tags"] == ["third_party_rss", "login_wall"]
