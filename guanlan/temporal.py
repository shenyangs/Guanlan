# -*- coding: utf-8 -*-
"""Deterministic snapshot and conservative claim change analysis."""

from __future__ import annotations

import difflib
import re
from typing import Any

from guanlan.evidence_kernel import build_passages, extract_claim_candidates, stable_id

SNAPSHOT_DIFF_SCHEMA_VERSION = "snapshot_diff_v1"
CLAIM_DELTA_SCHEMA_VERSION = "claim_delta_v1"


def build_snapshot_diff(before: dict[str, Any], after: dict[str, Any], *, context_lines: int = 2) -> dict[str, Any]:
    before_text = str(before.get("content") or "")
    after_text = str(after.get("content") or "")
    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()
    opcodes = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False).get_opcodes()
    changes: list[dict[str, Any]] = []
    added = removed = 0
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        removed_lines = before_lines[i1:i2]
        added_lines = after_lines[j1:j2]
        removed += len(removed_lines)
        added += len(added_lines)
        changes.append(
            {
                "change_id": stable_id("chg", before.get("snapshot_id"), after.get("snapshot_id"), tag, i1, i2, j1, j2),
                "kind": {"replace": "modified", "insert": "added", "delete": "removed"}[tag],
                "before_line_start": i1 + 1 if removed_lines else None,
                "before_line_end": i2 if removed_lines else None,
                "after_line_start": j1 + 1 if added_lines else None,
                "after_line_end": j2 if added_lines else None,
                "removed_lines": removed_lines,
                "added_lines": added_lines,
                "context_before": before_lines[max(0, i1 - max(context_lines, 0)) : i1],
                "context_after": after_lines[j2 : j2 + max(context_lines, 0)],
            }
        )
    ratio = difflib.SequenceMatcher(a=before_text, b=after_text, autojunk=False).ratio()
    return {
        "schema_version": SNAPSHOT_DIFF_SCHEMA_VERSION,
        "before_snapshot_id": str(before.get("snapshot_id") or ""),
        "after_snapshot_id": str(after.get("snapshot_id") or ""),
        "changed": before_text != after_text,
        "similarity": round(ratio, 6),
        "summary": {"change_blocks": len(changes), "added_lines": added, "removed_lines": removed},
        "changes": changes,
        "boundary": "确定性行级差异；不推断变化原因或事实真伪。",
    }


def build_claim_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_claims = _claims(before)
    after_claims = _claims(after)
    before_keys = {(item["category"], _normalize_value(item["value"])): item for item in before_claims}
    after_keys = {(item["category"], _normalize_value(item["value"])): item for item in after_claims}
    removed = [item for key, item in before_keys.items() if key not in after_keys]
    added = [item for key, item in after_keys.items() if key not in before_keys]
    deltas: list[dict[str, Any]] = []

    used_added: set[str] = set()
    used_removed: set[str] = set()
    for old in removed:
        candidates = [
            new for new in added
            if new["category"] == old["category"]
            and new["claim_id"] not in used_added
            and _context_signature(new) == _context_signature(old)
        ]
        if len(candidates) == 1:
            new = candidates[0]
            used_removed.add(str(old["claim_id"]))
            used_added.add(str(new["claim_id"]))
            deltas.append(_delta("value_changed", old, new))
    for item in removed:
        if item["claim_id"] not in used_removed:
            deltas.append(_delta("claim_removed", item, None))
    for item in added:
        if item["claim_id"] not in used_added:
            deltas.append(_delta("claim_added", None, item))
    counts: dict[str, int] = {}
    for item in deltas:
        counts[item["change_type"]] = counts.get(item["change_type"], 0) + 1
    return {
        "schema_version": CLAIM_DELTA_SCHEMA_VERSION,
        "before_snapshot_id": str(before.get("snapshot_id") or ""),
        "after_snapshot_id": str(after.get("snapshot_id") or ""),
        "changed": bool(deltas),
        "summary": counts,
        "deltas": deltas,
        "supported_change_types": ["claim_added", "claim_removed", "value_changed"],
        "boundary": "仅比较严格 token 候选；不自动输出 refuting_evidence、superseded 或事实裁决。",
    }


def _claims(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    content = str(snapshot.get("content") or "")
    passages = build_passages(snapshot, content)
    claims, _ = extract_claim_candidates(passages, max_claims=256)
    passage_text = {item["passage_id"]: item["text"] for item in passages}
    for claim in claims:
        claim["context"] = passage_text.get(claim["passage_id"], "")
    return claims


def _context_signature(claim: dict[str, Any]) -> str:
    context = str(claim.get("context") or "")
    value = str(claim.get("value") or "")
    return re.sub(r"\s+", " ", context.replace(value, "<VALUE>")).strip().lower()


def _normalize_value(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _delta(change_type: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "delta_id": stable_id(
            "delta",
            change_type,
            (before or {}).get("claim_id"),
            (after or {}).get("claim_id"),
        ),
        "change_type": change_type,
        "category": str((after or before or {}).get("category") or ""),
        "before": before,
        "after": after,
    }
