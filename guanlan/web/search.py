# -*- coding: utf-8 -*-
"""Search-facing Guanlan web primitives."""

from guanlan.web.search_quality import (
    build_query_strategy,
    detect_recency_intent,
    detect_search_quality_profile,
    search_quality_summary,
)
from guanlan.web.search_ranking import rank_results, source_distribution
from guanlan.web.search_service import backend_order, cache_dir, cache_summary, search_web
from guanlan.web.search_types import (
    NetworkBackendError,
    SearchResult,
    SearchResults,
)

__all__ = [
    "NetworkBackendError",
    "SearchResult",
    "SearchResults",
    "backend_order",
    "build_query_strategy",
    "cache_dir",
    "cache_summary",
    "detect_recency_intent",
    "detect_search_quality_profile",
    "rank_results",
    "search_quality_summary",
    "search_web",
    "source_distribution",
]
