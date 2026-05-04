# -*- coding: utf-8 -*-
"""Tests for the packaged hotboard source catalog."""

from guanlan import hotboard_catalog as hotboard


def test_hotboard_catalog_is_packaged_and_full_enough():
    meta = hotboard.catalog_meta()
    nodes = hotboard.catalog_nodes()

    assert meta["provider"] == "hotboard_catalog"
    assert meta["unique_count"] >= 10000
    assert len(nodes) == meta["unique_count"]
    assert not any("ed249" in str(value).lower() for value in meta.values())


def test_hotboard_resolves_common_aliases():
    node = hotboard.resolve_node("weibo")

    assert node is not None
    assert node["hashid"] == "KqndgxeLl9"
    assert node["name"] == "微博"
    assert node["command"].endswith("hotboard:node:KqndgxeLl9 --limit 80")


def test_hotboard_searches_catalog_by_category_without_api():
    rows = hotboard.search_catalog(category="finance", limit=5)

    assert rows
    assert all(row["category_name"] == "财经" for row in rows)
    assert any("雪球" in row["name"] or "财经" in row["name"] for row in rows)


def test_hotboard_route_recommendation_falls_back_to_category_pool():
    rows = hotboard.recommend_nodes_for_route("固态电池量产时间表", intents=["finance"], limit=3)

    assert rows
    assert all(row["category_name"] == "财经" for row in rows)
