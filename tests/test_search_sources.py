# -*- coding: utf-8 -*-
"""Tests for curated China search source scopes."""

import pytest

from guanlan.search_sources import classify_domain, list_search_scopes, resolve_scope, scoped_query


def test_search_scopes_include_requested_china_sources():
    scopes = list_search_scopes()

    assert "people.com.cn" in scopes["party_central"]["domains"]
    assert scopes["party_central"]["source_type"] == "党央媒"
    assert scopes["party_central"]["trust_level"] == 5
    assert "xinhuanet.com" in scopes["party_central"]["domains"]
    assert "bjd.com.cn" in scopes["local_official"]["domains"]
    assert "southcn.com" in scopes["local_official"]["domains"]
    assert "ebrun.com" in scopes["ecommerce"]["domains"]


def test_resolve_scope_aliases():
    assert resolve_scope("central").id == "party_central"
    assert resolve_scope("local").id == "local_official"
    assert resolve_scope("retail").id == "ecommerce"


def test_resolve_scope_rejects_unknown():
    with pytest.raises(ValueError):
        resolve_scope("not-a-scope")


def test_scoped_query_limits_site_expression():
    query = scoped_query("人工智能", ["people.com.cn", "xinhuanet.com"], max_sites=2)

    assert query == "(site:people.com.cn OR site:xinhuanet.com) 人工智能"


def test_classify_domain_matches_subdomains():
    meta = classify_domain("theory.people.com.cn")

    assert meta["source_type"] == "党央媒"
    assert meta["matched_scope"] == "party_central"
    assert meta["trust_level"] == 5


def test_classify_domain_prefers_requested_scope_for_overlapping_sources():
    meta = classify_domain("ebrun.com", preferred_scope="ecommerce")

    assert meta["source_type"] == "电商/零售垂类"
    assert meta["matched_scope"] == "ecommerce"
