#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replay the 2026-05-18 stress-report queries and print Markdown or JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    from guanlan.stress_replay import format_stress_report_markdown, replay_stress_report

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default="", help="Optional JSONL fixture path")
    parser.add_argument("--limit", type=int, default=10, help="Search result limit per query")
    parser.add_argument("--case", action="append", default=[], help="Optional case id to replay; can be repeated")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", default="", help="Optional output path; stdout when omitted")
    args = parser.parse_args()

    report = replay_stress_report(
        path=args.fixture or None,
        limit=max(args.limit, 1),
        case_ids=list(args.case or []),
    )
    text = (
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.format == "json"
        else format_stress_report_markdown(report)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
