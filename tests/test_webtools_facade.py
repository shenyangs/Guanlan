# -*- coding: utf-8 -*-
"""Tests for the compatibility boundary of guanlan.webtools."""

from __future__ import annotations

from guanlan import webtools


def test_webtools_star_import_hides_facade_internals():
    namespace: dict[str, object] = {}
    exec("from guanlan.webtools import *", namespace)

    assert "search_web" in namespace
    assert "build_research_packet" in namespace
    assert "_impl" not in namespace
    assert "_SYNC_ENTRYPOINTS" not in namespace
    assert "_search_bing" not in namespace
    assert hasattr(webtools, "_search_bing")
