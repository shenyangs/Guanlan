# -*- coding: utf-8 -*-
"""Research source diagnostics and guard entrypoints."""

from __future__ import annotations

from typing import Any

from guanlan.web import _impl as _compat


def build_source_diagnostics(*args: Any, **kwargs: Any):
    return _compat.build_source_diagnostics(*args, **kwargs)


def build_freshness_guard(*args: Any, **kwargs: Any):
    return _compat.build_freshness_guard(*args, **kwargs)


def build_source_mix_guard(*args: Any, **kwargs: Any):
    return _compat.build_source_mix_guard(*args, **kwargs)


__all__ = ["build_freshness_guard", "build_source_diagnostics", "build_source_mix_guard"]
