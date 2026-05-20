# -*- coding: utf-8 -*-
"""Ranking and source distribution entrypoints for search results."""

from __future__ import annotations

from typing import Any

from guanlan.web import _impl as _compat


def rank_results(*args: Any, **kwargs: Any):
    return _compat.rank_results(*args, **kwargs)


def source_distribution(*args: Any, **kwargs: Any):
    return _compat.source_distribution(*args, **kwargs)


__all__ = ["rank_results", "source_distribution"]
