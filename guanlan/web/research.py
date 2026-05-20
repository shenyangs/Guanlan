# -*- coding: utf-8 -*-
"""Research-facing Guanlan web primitives."""

from guanlan.web.advisor import build_advisor_view
from guanlan.web.evidence_audit import build_evidence_audit
from guanlan.web.guards import (
    build_freshness_guard,
    build_source_diagnostics,
    build_source_mix_guard,
)
from guanlan.web.research_service import (
    build_research_packet,
    list_research_presets,
    resolve_research_preset,
)

__all__ = [
    "build_advisor_view",
    "build_evidence_audit",
    "build_freshness_guard",
    "build_research_packet",
    "build_source_diagnostics",
    "build_source_mix_guard",
    "list_research_presets",
    "resolve_research_preset",
]
