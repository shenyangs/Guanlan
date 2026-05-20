# -*- coding: utf-8 -*-
"""Renderer entrypoints for Guanlan web packets."""

from __future__ import annotations

from typing import Any

from guanlan.web import _impl as _compat


def __getattr__(name: str):
    return getattr(_compat, name)


def _forward(name: str, *args: Any, **kwargs: Any):
    return getattr(_compat, name)(*args, **kwargs)


def format_search_trace(*args: Any, **kwargs: Any):
    return _forward("format_search_trace", *args, **kwargs)


__all__ = [
    "format_search_trace",
]
