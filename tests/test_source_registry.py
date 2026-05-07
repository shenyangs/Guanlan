# -*- coding: utf-8 -*-
"""Tests for the centralized Guanlan source matrix."""

from guanlan import source_registry
from guanlan.channel_catalog import get_channel_metadata
from guanlan.serve import dispatch_request


def test_source_matrix_marks_native_and_optional_boundaries():
    sources = source_registry.list_hotnews_sources()

    assert sources["bilibili-hot-search"]["backend"] == "native"
    assert sources["sspai"]["backend"] == "native"
    assert sources["xinzhiyuan"]["evidence_role"] == "ai_news_signal"
    assert sources["youtube-ai-rss"]["quality"] == "official YouTube channel RSS"
    assert sources["zeli-hn"]["risk_tags"] == ["third_party_aggregation", "community_bias"]
    assert sources["buzzing"]["verification"] == "direct"
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
    assert feeds["arxiv"]["evidence_role"] == "preprint_record"
    assert source_registry.resolve_source_id("preprint") == "arxiv"
    assert source_registry.resolve_source_id("watch") == "watchlist"


def test_source_matrix_has_stable_required_fields_and_status_values():
    allowed_status = {"stable", "best-effort", "experimental", "optional"}
    allowed_backend = {"native", "optional", "rss", "curated"}
    sources = source_registry.list_sources()

    assert len(sources) == len(set(sources))
    for source_id, meta in sources.items():
        assert meta["id"] == source_id
        assert meta["name"]
        assert meta["surface"] in {"hotnews", "feeds"}
        assert meta["backend"] in allowed_backend
        assert meta["status"] in allowed_status
        assert meta["evidence_role"]
        assert isinstance(meta.get("risk_tags", []), list)


def test_hotnews_registry_and_channel_catalog_keep_same_reality_boundary():
    hotnews = source_registry.list_hotnews_sources()
    channel = get_channel_metadata("hotnews")

    assert hotnews["baidu"]["status"] == "stable"
    assert hotnews["zhihu"]["status"] == "experimental"
    assert hotnews["newsnow:thepaper"]["backend"] == "optional"
    assert "zhihu 为实验源" in channel["expectation"]
    assert channel["stability"] == "best-effort"


def test_http_sources_endpoint_uses_central_registry():
    status, body = dispatch_request("GET", "/sources?surface=hotnews")
    registry = source_registry.list_hotnews_sources()

    assert status == 200
    assert body["sources"] == registry
    assert body["sources"]["zhihu"]["status"] == "experimental"


def test_feeds_module_uses_registry_feed_catalog():
    from guanlan import feeds

    assert feeds.list_feed_sources() == source_registry.list_feed_sources()
    assert feeds.FEED_SOURCE_CATALOG == source_registry.list_feed_sources()
