# -*- coding: utf-8 -*-
"""Read-facing Guanlan web primitives."""

from typing import Any

from guanlan.web import _impl as _compat
from guanlan.web._read_impl import (
    assess_read_quality,
    build_read_quality_report,
    format_read_quality_report,
    read_batch,
    read_url,
    read_url_with_trace,
)


def format_read_batch_context(*args: Any, **kwargs: Any):
    return _compat.format_read_batch_context(*args, **kwargs)


def format_read_batch_markdown(*args: Any, **kwargs: Any):
    return _compat.format_read_batch_markdown(*args, **kwargs)

__all__ = [
    "assess_read_quality",
    "build_read_quality_report",
    "format_read_batch_context",
    "format_read_batch_markdown",
    "format_read_quality_report",
    "read_batch",
    "read_url",
    "read_url_with_trace",
]
