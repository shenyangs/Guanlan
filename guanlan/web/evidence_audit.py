# -*- coding: utf-8 -*-
"""Evidence audit entrypoints for research packets."""

from __future__ import annotations

from typing import Any

from guanlan.web import _impl as _compat


def build_evidence_audit(*args: Any, **kwargs: Any):
    return _compat.build_evidence_audit(*args, **kwargs)


__all__ = ["build_evidence_audit"]
