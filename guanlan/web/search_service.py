# -*- coding: utf-8 -*-
"""Search orchestration entrypoints for the Guanlan web subsystem."""

from __future__ import annotations

from typing import Any

from guanlan.web import _impl as _compat


def search_web(*args: Any, **kwargs: Any):
    return _compat.search_web(*args, **kwargs)


def backend_order(*args: Any, **kwargs: Any):
    return _compat.backend_order(*args, **kwargs)


def cache_dir(*args: Any, **kwargs: Any):
    return _compat.cache_dir(*args, **kwargs)


def cache_summary(*args: Any, **kwargs: Any):
    return _compat.cache_summary(*args, **kwargs)


__all__ = ["backend_order", "cache_dir", "cache_summary", "search_web"]
