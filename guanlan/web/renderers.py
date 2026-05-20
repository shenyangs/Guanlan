# -*- coding: utf-8 -*-
"""Renderer-facing Guanlan web primitives."""

from typing import Any

from guanlan.claim_ledger import format_claim_ledger_context, format_claim_ledger_markdown
from guanlan.web import _impl as _compat


def format_advisor_context(*args: Any, **kwargs: Any):
    return _compat.format_advisor_context(*args, **kwargs)


def format_advisor_markdown(*args: Any, **kwargs: Any):
    return _compat.format_advisor_markdown(*args, **kwargs)


def format_evidence_audit_context(*args: Any, **kwargs: Any):
    return _compat.format_evidence_audit_context(*args, **kwargs)


def format_evidence_audit_markdown(*args: Any, **kwargs: Any):
    return _compat.format_evidence_audit_markdown(*args, **kwargs)


def format_freshness_guard_markdown(*args: Any, **kwargs: Any):
    return _compat.format_freshness_guard_markdown(*args, **kwargs)


def format_read_batch_context(*args: Any, **kwargs: Any):
    return _compat.format_read_batch_context(*args, **kwargs)


def format_read_batch_markdown(*args: Any, **kwargs: Any):
    return _compat.format_read_batch_markdown(*args, **kwargs)


def format_read_batch_prompt(*args: Any, **kwargs: Any):
    return _compat.format_read_batch_prompt(*args, **kwargs)


def format_read_context(*args: Any, **kwargs: Any):
    return _compat.format_read_context(*args, **kwargs)


def format_read_prompt(*args: Any, **kwargs: Any):
    return _compat.format_read_prompt(*args, **kwargs)


def format_read_quality_report(*args: Any, **kwargs: Any):
    return _compat.format_read_quality_report(*args, **kwargs)


def format_read_trace(*args: Any, **kwargs: Any):
    return _compat.format_read_trace(*args, **kwargs)


def format_research_markdown(*args: Any, **kwargs: Any):
    return _compat.format_research_markdown(*args, **kwargs)


def format_research_prompt(*args: Any, **kwargs: Any):
    return _compat.format_research_prompt(*args, **kwargs)


def format_search_context(*args: Any, **kwargs: Any):
    return _compat.format_search_context(*args, **kwargs)


def format_search_markdown(*args: Any, **kwargs: Any):
    return _compat.format_search_markdown(*args, **kwargs)


def format_search_prompt(*args: Any, **kwargs: Any):
    return _compat.format_search_prompt(*args, **kwargs)


def format_search_trace(*args: Any, **kwargs: Any):
    return _compat.format_search_trace(*args, **kwargs)


def format_source_chart(*args: Any, **kwargs: Any):
    return _compat.format_source_chart(*args, **kwargs)


def format_source_diagnostics_markdown(*args: Any, **kwargs: Any):
    return _compat.format_source_diagnostics_markdown(*args, **kwargs)


def format_source_mix_guard_markdown(*args: Any, **kwargs: Any):
    return _compat.format_source_mix_guard_markdown(*args, **kwargs)


def source_distribution(*args: Any, **kwargs: Any):
    return _compat.source_distribution(*args, **kwargs)

__all__ = [
    "format_advisor_context",
    "format_advisor_markdown",
    "format_claim_ledger_context",
    "format_claim_ledger_markdown",
    "format_evidence_audit_context",
    "format_evidence_audit_markdown",
    "format_freshness_guard_markdown",
    "format_read_batch_context",
    "format_read_batch_markdown",
    "format_read_batch_prompt",
    "format_read_context",
    "format_read_prompt",
    "format_read_quality_report",
    "format_read_trace",
    "format_research_markdown",
    "format_research_prompt",
    "format_search_context",
    "format_search_markdown",
    "format_search_prompt",
    "format_search_trace",
    "format_source_chart",
    "format_source_diagnostics_markdown",
    "format_source_mix_guard_markdown",
    "source_distribution",
]
