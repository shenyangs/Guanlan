# -*- coding: utf-8 -*-
"""Service boundary for additive evidence provenance contracts."""

from __future__ import annotations

from typing import Any

from guanlan.evidence_kernel import build_evidence_bundle


def attach_evidence_bundle(packet: dict[str, Any]) -> dict[str, Any]:
    """Attach provenance without changing any pre-existing packet field."""

    if "evidence_bundle_v1" not in packet:
        packet["evidence_bundle_v1"] = build_evidence_bundle(packet)
    return packet


__all__ = ["attach_evidence_bundle"]
