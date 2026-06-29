# -*- coding: utf-8 -*-
"""Shared CLI feedback helpers."""

import contextlib
import json
import os
import sys

_AUTO_FEEDBACK_SENT = set()

def _normalized_bool(value):
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None

def _is_agent_runtime():
    env = os.environ
    return bool(
        env.get("CODEX_HOME")
        or env.get("CODEX_SANDBOX")
        or env.get("OPENAI_CODEX")
        or env.get("CLAUDECODE")
        or env.get("CLAUDE_CODE_ENTRYPOINT")
        or env.get("CURSOR_TRACE_ID")
        or env.get("CURSOR_AGENT")
        or env.get("OPENWEBUI_URL")
        or env.get("OPEN_WEBUI")
    )

def _auto_feedback_enabled():
    flag = _normalized_bool(os.environ.get("GUANLAN_AUTO_FEEDBACK"))
    if flag is not None:
        return flag
    with contextlib.suppress(Exception):
        from guanlan.config import Config

        config = Config()
        config_flag = _normalized_bool(config.get("auto_feedback_enabled", None))
        if config_flag is not None:
            return config_flag
    return False

def _submit_auto_feedback(query, reason, *, command, profile, backend):
    if not _auto_feedback_enabled():
        return
    query = str(query or "").strip()
    reason = str(reason or "").strip()
    if not query or not reason:
        return
    with contextlib.suppress(Exception):
        from guanlan.sensitive import contains_sensitive_text

        if contains_sensitive_text(query) or contains_sensitive_text(reason):
            return
    dedupe_key = (command, query, reason)
    if dedupe_key in _AUTO_FEEDBACK_SENT:
        return
    _AUTO_FEEDBACK_SENT.add(dedupe_key)
    with contextlib.suppress(Exception):
        from guanlan.feedback import submit_feedback

        submit_feedback(
            query,
            reason,
            command=command,
            surface="cli",
            profile=profile or "",
            backend=backend or "",
        )

def _auto_feedback_for_search(args, results):
    query = str(getattr(args, "query", "") or "").strip()
    if not query:
        return
    reasons = []
    if not results:
        reasons.append("搜索结果为空")
    if results:
        trace = dict(results[0].get("trace") or {})
        quality_summary = dict(trace.get("quality_summary") or {})
        warnings = [str(item) for item in list(quality_summary.get("warnings") or []) if item]
        if warnings:
            reasons.append("；".join(warnings[:2]))
        hit_count = int(quality_summary.get("preferred_hit_count") or 0)
        total_count = int(quality_summary.get("result_count") or len(results))
        if total_count > 0 and hit_count == 0:
            reasons.append("结果未命中目标信源类型")
        backend_recovery = dict(trace.get("backend_recovery") or {})
        if backend_recovery.get("should_warn"):
            issue = str(backend_recovery.get("issue") or "").strip()
            if issue:
                reasons.append(f"搜索后端异常: {issue}")
        if len(results) < max(3, min(int(getattr(args, "limit", 0) or 0), 5)):
            reasons.append("有效结果数量偏少")
    if not reasons:
        return
    reason_text = " | ".join(dict.fromkeys(reasons))[:600]
    _submit_auto_feedback(
        query,
        reason_text,
        command="search",
        profile=str(getattr(args, "profile", "") or ""),
        backend=str(getattr(args, "backend", "") or ""),
    )

def _auto_feedback_for_research(args, packet):
    query = str(getattr(args, "query", "") or "").strip()
    if not query:
        return
    reasons = []
    search_errors = [str(item) for item in list(packet.get("search_errors") or []) if item]
    if search_errors:
        reasons.append("部分检索失败: " + "；".join(search_errors[:2]))
    selected = list(packet.get("selected_evidence") or [])
    if len(selected) < 3:
        reasons.append("代表证据不足")
    freshness_guard = dict(packet.get("freshness_guard") or {})
    if freshness_guard.get("required") and int(freshness_guard.get("window_hits") or 0) == 0:
        reasons.append("时效窗口内证据不足")
    source_mix_guard = dict(packet.get("source_mix_guard") or {})
    guard_warnings = [str(item) for item in list(source_mix_guard.get("warnings") or []) if item]
    if guard_warnings:
        reasons.append("；".join(guard_warnings[:2]))
    if not reasons:
        return
    reason_text = " | ".join(dict.fromkeys(reasons))[:600]
    _submit_auto_feedback(
        query,
        reason_text,
        command="research",
        profile=str(getattr(args, "profile", "") or ""),
        backend=str(getattr(args, "search_backend", "") or ""),
    )

def _cmd_feedback(args):
    """Submit search dissatisfaction feedback for server-side diagnosis."""

    from guanlan.feedback import submit_feedback

    query = str(args.query or "").strip()
    reason = str(args.reason or "").strip()
    if not query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    if not reason:
        print("Error: --reason is required", file=sys.stderr)
        sys.exit(2)

    result = submit_feedback(
        query,
        reason,
        command=args.feedback_command,
        surface="cli",
        profile=args.profile or "",
        backend=args.backend or "",
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if result.get("ok") and result.get("queued"):
        print("✅ 反馈已保存，将在网络恢复后自动上报。")
    elif result.get("ok"):
        print("✅ 反馈已提交，感谢帮助我们改进搜索质量。")
    else:
        print(f"❌ 反馈提交失败: {result.get('message')}", file=sys.stderr)
        sys.exit(1)

__all__ = ['_normalized_bool', '_is_agent_runtime', '_auto_feedback_enabled', '_submit_auto_feedback', '_auto_feedback_for_search', '_auto_feedback_for_research', '_cmd_feedback']
