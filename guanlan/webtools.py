# -*- coding: utf-8 -*-
"""Compatibility facade for Guanlan web primitives.

The implementation lives under ``guanlan.web``. This module remains only as a
backward-compatible import surface for tests, MCP glue, and older internal
callers while the rest of the codebase migrates to the split modules.
"""

from guanlan.web import _impl as _impl

_IMPL_EXPORT_NAMES = {name for name in dir(_impl) if not name.startswith("__")}

for _name in dir(_impl):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_impl, _name)

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
_IMPL_ORIGINALS = {name: getattr(_impl, name) for name in _SYNC_ENTRYPOINTS if hasattr(_impl, name)}
_SEARCH_SYNC_NAMES = {
    "cache_dir",
    "backend_order",
    "_search_baidu",
    "_search_bing",
    "_search_bing_generic",
    "_search_bing_html",
    "_search_duckduckgo",
    "_search_backend_with_network",
}
_FACADE_INTERNAL_NAMES = {
    "_impl",
    "_IMPL_EXPORT_NAMES",
    "_SYNC_ENTRYPOINTS",
    "_WRAPPER_OVERRIDES",
    "_IMPL_ORIGINALS",
    "_SEARCH_SYNC_NAMES",
    "_FACADE_INTERNAL_NAMES",
    "_sync_impl_overrides",
    "__all__",
}


def _sync_impl_overrides() -> None:
    for _name, _value in list(globals().items()):
        if _name.startswith("__") or _name in _FACADE_INTERNAL_NAMES:
            continue
        if _name in _WRAPPER_OVERRIDES and _value is _WRAPPER_OVERRIDES[_name]:
            if _name in _IMPL_ORIGINALS and getattr(_impl, _name) is not _IMPL_ORIGINALS[_name]:
                setattr(_impl, _name, _IMPL_ORIGINALS[_name])
            continue
        if hasattr(_impl, _name) and getattr(_impl, _name) is not _value:
            setattr(_impl, _name, _value)


def search_web(*args, **kwargs):
    for _name in _SEARCH_SYNC_NAMES:
        if _name not in globals() or not hasattr(_impl, _name):
            continue
        _value = globals()[_name]
        if _name in _WRAPPER_OVERRIDES and _value is _WRAPPER_OVERRIDES[_name]:
            if _name in _IMPL_ORIGINALS and getattr(_impl, _name) is not _IMPL_ORIGINALS[_name]:
                setattr(_impl, _name, _IMPL_ORIGINALS[_name])
            continue
        setattr(_impl, _name, _value)
    _sync_impl_overrides()
    return _impl.search_web(*args, **kwargs)


def backend_order(*args, **kwargs):
    _sync_impl_overrides()
    return _impl.backend_order(*args, **kwargs)


def _bing_cjk_drift_active(*args, **kwargs):
    _sync_impl_overrides()
    return _impl._bing_cjk_drift_active(*args, **kwargs)


def _record_bing_cjk_drift(*args, **kwargs):
    _sync_impl_overrides()
    return _impl._record_bing_cjk_drift(*args, **kwargs)


def _format_read_watch(*args, **kwargs):
    _sync_impl_overrides()
    return _impl._format_read_watch(*args, **kwargs)


def rank_results(*args, **kwargs):
    _sync_impl_overrides()
    return _impl.rank_results(*args, **kwargs)


def detect_search_quality_profile(*args, **kwargs):
    _sync_impl_overrides()
    return _impl.detect_search_quality_profile(*args, **kwargs)


def search_quality_summary(*args, **kwargs):
    _sync_impl_overrides()
    return _impl.search_quality_summary(*args, **kwargs)


def build_query_strategy(*args, **kwargs):
    _sync_impl_overrides()
    return _impl.build_query_strategy(*args, **kwargs)


def read_url(*args, **kwargs):
    _sync_impl_overrides()
    return _impl.read_url(*args, **kwargs)


def read_url_with_trace(*args, **kwargs):
    _sync_impl_overrides()
    return _impl.read_url_with_trace(*args, **kwargs)


def read_batch(
    urls,
    max_chars=None,
    backend="auto",
    fallback_search=True,
    fallback_limit=_impl.DEFAULT_READ_FALLBACK_LIMIT,
    profile="china",
    cache_ttl=0,
    strict=False,
    extract="article",
    concurrency=1,
):
    _sync_impl_overrides()
    return _impl.read_batch(
        urls,
        max_chars=max_chars,
        backend=backend,
        fallback_search=fallback_search,
        fallback_limit=fallback_limit,
        profile=profile,
        cache_ttl=cache_ttl,
        strict=strict,
        extract=extract,
        concurrency=concurrency,
    )


def build_research_packet(*args, **kwargs):
    _sync_impl_overrides()
    return _impl.build_research_packet(*args, **kwargs)


_WRAPPER_OVERRIDES.update({name: globals()[name] for name in _SYNC_ENTRYPOINTS})


__all__ = sorted(name for name in _IMPL_EXPORT_NAMES if not name.startswith("_"))
