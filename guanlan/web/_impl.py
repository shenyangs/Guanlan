# -*- coding: utf-8 -*-
"""Compatibility bindings for the split Guanlan web stack.

Business logic lives in owner modules such as ``_read_impl`` and
``_search_quality_impl`` plus the transitional ``_legacy_web_impl`` runtime.
This module is kept small so older imports can keep working while new code uses
``guanlan.web.search/read/research/renderers``.
"""

from __future__ import annotations

import importlib
from typing import Any

_legacy = importlib.import_module("guanlan.web._legacy_web_impl")

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)

_read_impl = importlib.import_module("guanlan.web._read_impl")
_search_quality_impl = importlib.import_module("guanlan.web._search_quality_impl")

for _module in (_read_impl, _search_quality_impl):
    for _name in getattr(_module, "__all__", []):
        globals()[_name] = getattr(_module, _name)

_SYNC_ENTRYPOINTS = {
    "_bing_cjk_drift_active",
    "_format_read_watch",
    "_record_bing_cjk_drift",
    "backend_order",
    "search_web",
    "rank_results",
    "detect_search_quality_profile",
    "search_quality_summary",
    "build_query_strategy",
    "read_url",
    "read_url_with_trace",
    "read_batch",
    "build_research_packet",
}
_WRAPPER_OVERRIDES: dict[str, object] = {}
_LEGACY_ORIGINALS = {name: getattr(_legacy, name) for name in _SYNC_ENTRYPOINTS if hasattr(_legacy, name)}
_INTERNAL_NAMES = {
    "Any",
    "importlib",
    "_legacy",
    "_read_impl",
    "_search_quality_impl",
    "_SYNC_ENTRYPOINTS",
    "_WRAPPER_OVERRIDES",
    "_LEGACY_ORIGINALS",
    "_INTERNAL_NAMES",
    "_sync_legacy_overrides",
    "__all__",
}


def _sync_legacy_overrides() -> None:
    for _name, _value in list(globals().items()):
        if _name.startswith("__") or _name in _INTERNAL_NAMES:
            continue
        if _name in _WRAPPER_OVERRIDES and _value is _WRAPPER_OVERRIDES[_name]:
            if _name in _LEGACY_ORIGINALS and getattr(_legacy, _name, None) is not _LEGACY_ORIGINALS[_name]:
                setattr(_legacy, _name, _LEGACY_ORIGINALS[_name])
            continue
        if hasattr(_legacy, _name) and getattr(_legacy, _name) is not _value:
            setattr(_legacy, _name, _value)


def search_web(*args: Any, **kwargs: Any):
    _sync_legacy_overrides()
    return _legacy.search_web(*args, **kwargs)


def backend_order(*args: Any, **kwargs: Any):
    _sync_legacy_overrides()
    return _legacy.backend_order(*args, **kwargs)


def _bing_cjk_drift_active(*args: Any, **kwargs: Any):
    _sync_legacy_overrides()
    return _legacy._bing_cjk_drift_active(*args, **kwargs)


def _record_bing_cjk_drift(*args: Any, **kwargs: Any):
    _sync_legacy_overrides()
    return _legacy._record_bing_cjk_drift(*args, **kwargs)


def _format_read_watch(*args: Any, **kwargs: Any):
    _sync_legacy_overrides()
    return _legacy._format_read_watch(*args, **kwargs)


def rank_results(*args: Any, **kwargs: Any):
    _sync_legacy_overrides()
    return _legacy.rank_results(*args, **kwargs)


def detect_search_quality_profile(*args: Any, **kwargs: Any):
    return _search_quality_impl.detect_search_quality_profile(*args, **kwargs)


def search_quality_summary(*args: Any, **kwargs: Any):
    return _search_quality_impl.search_quality_summary(*args, **kwargs)


def build_query_strategy(*args: Any, **kwargs: Any):
    return _search_quality_impl.build_query_strategy(*args, **kwargs)


def read_url(*args: Any, **kwargs: Any):
    _sync_legacy_overrides()
    return _read_impl.read_url(*args, **kwargs)


def read_url_with_trace(*args: Any, **kwargs: Any):
    _sync_legacy_overrides()
    return _read_impl.read_url_with_trace(*args, **kwargs)


def read_batch(*args: Any, **kwargs: Any):
    _sync_legacy_overrides()
    return _read_impl.read_batch(*args, **kwargs)


def build_research_packet(*args: Any, **kwargs: Any):
    _sync_legacy_overrides()
    return _legacy.build_research_packet(*args, **kwargs)


_WRAPPER_OVERRIDES.update({name: globals()[name] for name in _SYNC_ENTRYPOINTS if name in globals()})

read_url.__module__ = "guanlan.web._read_impl"
read_url_with_trace.__module__ = "guanlan.web._read_impl"
read_batch.__module__ = "guanlan.web._read_impl"
detect_search_quality_profile.__module__ = "guanlan.web._search_quality_impl"
search_quality_summary.__module__ = "guanlan.web._search_quality_impl"
build_query_strategy.__module__ = "guanlan.web._search_quality_impl"

__all__ = sorted(name for name in globals() if not name.startswith("_"))
