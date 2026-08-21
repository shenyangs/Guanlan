# -*- coding: utf-8 -*-
"""CLI handlers for durable Research Cases."""

from __future__ import annotations

import json
import sys


def _cmd_case(args) -> None:
    from guanlan.research_cases import (
        cancel_case,
        create_case,
        get_case,
        list_cases,
        pause_case,
        resume_case,
        run_case,
        task_view,
    )

    command = str(getattr(args, "case_command", "") or "")
    db_path = getattr(args, "db", "") or None
    try:
        if command == "create":
            result = create_case(
                args.query,
                request=_json_object(args.request, "--request"),
                requirements=_json_object(args.requirements, "--requirements"),
                budget=_json_object(args.budget, "--budget"),
                expires_in=None if args.no_expiry else max(int(args.expires_in), 1),
                db_path=db_path,
            )
        elif command == "run":
            result = run_case(args.case_id, db_path=db_path)
        elif command == "status":
            result = task_view(args.case_id, db_path=db_path) if args.task else get_case(args.case_id, db_path=db_path)
        elif command == "list":
            result = list_cases(state=args.state or None, limit=max(args.limit, 1), db_path=db_path)
        elif command == "pause":
            result = pause_case(args.case_id, reason=args.reason, db_path=db_path)
        elif command == "resume":
            result = resume_case(args.case_id, db_path=db_path)
        elif command == "cancel":
            result = cancel_case(args.case_id, reason=args.reason, db_path=db_path)
        else:
            print("Error: case command is required: create, run, status, list, pause, resume, cancel", file=sys.stderr)
            sys.exit(2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _json_object(value: str, flag: str) -> dict:
    if not str(value or "").strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{flag} must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{flag} must be a JSON object")
    return parsed
