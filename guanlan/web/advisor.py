# -*- coding: utf-8 -*-
"""Advisor view entrypoints for research packets."""

from __future__ import annotations

from typing import Any

from guanlan.web import _impl as _compat


def build_advisor_view(*args: Any, **kwargs: Any):
    return _compat.build_advisor_view(*args, **kwargs)


__all__ = ["build_advisor_view"]
