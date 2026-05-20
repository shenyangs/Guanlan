# -*- coding: utf-8 -*-
"""Research packet service entrypoints."""

from __future__ import annotations

from typing import Any

from guanlan.web import _impl as _compat


def build_research_packet(*args: Any, **kwargs: Any):
    return _compat.build_research_packet(*args, **kwargs)


def list_research_presets(*args: Any, **kwargs: Any):
    return _compat.list_research_presets(*args, **kwargs)


def resolve_research_preset(*args: Any, **kwargs: Any):
    return _compat.resolve_research_preset(*args, **kwargs)


__all__ = ["build_research_packet", "list_research_presets", "resolve_research_preset"]
