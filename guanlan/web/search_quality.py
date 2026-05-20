# -*- coding: utf-8 -*-
"""Search quality and query strategy entrypoints."""

from guanlan.web._search_quality_impl import (
    build_query_strategy,
    detect_recency_intent,
    detect_search_quality_profile,
    search_quality_summary,
)

__all__ = [
    "build_query_strategy",
    "detect_recency_intent",
    "detect_search_quality_profile",
    "search_quality_summary",
]
