# -*- coding: utf-8 -*-
"""Read, diagnosis, and browser-assist command handlers for Guanlan CLI."""

import json
import sys

from guanlan.errors import format_user_error
from guanlan.tool_invocation import normalize_read_request


def _cmd_diagnose(args):
    """Diagnose page readability and evidence usability."""

    if not getattr(args, "diagnose_command", None):
        print("Error: diagnose command is required (try: guanlan diagnose page URL)", file=sys.stderr)
        sys.exit(2)
    if args.diagnose_command != "page":
        print(f"Error: unknown diagnose command: {args.diagnose_command}", file=sys.stderr)
        sys.exit(2)
    if not args.url:
        print("Error: URL is required", file=sys.stderr)
        sys.exit(2)
    from guanlan.page_diagnosis import (
        diagnose_page,
        format_page_diagnosis_json,
        format_page_diagnosis_markdown,
    )

    payload = diagnose_page(
        args.url,
        max_chars=max(args.max_chars, 1) if args.max_chars is not None else None,
        backend=args.backend,
        fallback_search=bool(args.fallback_search),
        fallback_limit=max(args.fallback_limit, 1),
        profile=args.profile or None,
        strict=bool(args.strict),
    )
    print(format_page_diagnosis_json(payload) if args.json else format_page_diagnosis_markdown(payload))

def _cmd_browser_assist(args):
    """Build user-authorized visible browser evidence plans."""

    if not getattr(args, "browser_assist_command", None):
        print("Error: browser-assist command is required (try: guanlan browser-assist plan URL)", file=sys.stderr)
        sys.exit(2)
    from guanlan.browser_assist import (
        build_browser_assist_plan,
        build_browser_assist_session_contract,
        build_opencli_browser_bridge_setup_plan,
        build_openguanlan_browser_bridge_setup_plan,
        format_browser_assist_adapters_markdown,
        format_browser_assist_markdown,
        format_browser_assist_run_markdown,
        format_opencli_browser_bridge_setup_markdown,
        format_openguanlan_browser_bridge_setup_markdown,
        list_browser_assist_adapters,
        run_browser_assist_adapter,
    )

    if args.browser_assist_command == "setup-openguanlan":
        setup = build_openguanlan_browser_bridge_setup_plan()
        output_format = "json" if args.json else args.format
        print(json.dumps(setup, ensure_ascii=False, indent=2) if output_format == "json" else format_openguanlan_browser_bridge_setup_markdown(setup))
        return

    if args.browser_assist_command == "setup-opencli":
        setup = build_opencli_browser_bridge_setup_plan(
            execute=bool(getattr(args, "execute", False)),
            timeout=max(getattr(args, "timeout", 180), 1),
        )
        output_format = "json" if args.json else args.format
        print(json.dumps(setup, ensure_ascii=False, indent=2) if output_format == "json" else format_opencli_browser_bridge_setup_markdown(setup))
        return

    if args.browser_assist_command == "adapters":
        adapters = list_browser_assist_adapters(
            check=bool(getattr(args, "check", False)),
            platform=getattr(args, "platform", "") or "",
            dry_run_url=getattr(args, "dry_run_url", "") or "https://example.com/article",
        )
        output_format = "json" if args.json else args.format
        print(json.dumps(adapters, ensure_ascii=False, indent=2) if output_format == "json" else format_browser_assist_adapters_markdown(adapters))
        return

    if args.browser_assist_command == "sessions":
        session_contract = build_browser_assist_session_contract(
            getattr(args, "url", "") or "",
            platform=getattr(args, "platform", "") or "",
            task_goal=getattr(args, "task_goal", "") or "",
            min_visible_items=max(getattr(args, "min_visible_items", 0), 0),
        )
        output_format = "json" if args.json else args.format
        if output_format == "json":
            print(json.dumps(session_contract, ensure_ascii=False, indent=2))
        else:
            print(_format_browser_assist_session_markdown(session_contract))
        return

    if args.browser_assist_command == "run":
        result = run_browser_assist_adapter(
            args.url,
            adapter=args.adapter,
            execute=bool(args.execute),
            command_template=args.command_template,
            timeout=max(args.timeout, 1),
            output_path=args.output,
            page_type=args.page_type,
            signals=list(args.signal or []),
            platform=args.platform,
            max_pages=max(args.max_pages, 1),
            max_chars_per_page=max(args.max_chars_per_page, 1),
            min_visible_items=max(args.min_visible_items, 0),
            task_goal=args.task_goal,
        )
        output_format = "json" if args.json else args.format
        print(json.dumps(result, ensure_ascii=False, indent=2) if output_format == "json" else format_browser_assist_run_markdown(result))
        return

    if args.browser_assist_command != "plan":
        print(f"Error: unknown browser-assist command: {args.browser_assist_command}", file=sys.stderr)
        sys.exit(2)

    plan = build_browser_assist_plan(
        args.url,
        page_type=args.page_type,
        signals=list(args.signal or []),
        force=True,
        max_pages=max(args.max_pages, 1),
        max_chars_per_page=max(args.max_chars_per_page, 1),
        min_visible_items=max(args.min_visible_items, 0),
        task_goal=args.task_goal,
    )
    if args.platform:
        plan["platform"] = args.platform
        if isinstance(plan.get("browser_assist_task"), dict):
            plan["browser_assist_task"]["platform"] = args.platform
    output_format = "json" if args.json else args.format
    print(json.dumps(plan, ensure_ascii=False, indent=2) if output_format == "json" else format_browser_assist_markdown(plan))

def _cmd_wechat_exporter(args):
    """Run optional user-configured WeChat article exporter commands."""

    if not getattr(args, "wechat_exporter_command", None):
        print("Error: wechat-exporter command is required (try: guanlan wechat-exporter status)", file=sys.stderr)
        sys.exit(2)
    from guanlan.wechat_exporter import (
        account_by_url,
        download_article,
        exporter_status,
        list_articles,
        search_accounts,
    )

    try:
        command = args.wechat_exporter_command
        if command == "status":
            payload = exporter_status(
                base_url=args.base_url or None,
                auth_key_env=args.auth_env,
                probe=bool(args.probe),
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else _format_wechat_exporter_status_markdown(payload))
            return
        if command == "download":
            if not args.url:
                print("Error: URL is required", file=sys.stderr)
                sys.exit(2)
            payload = download_article(
                args.url,
                output_format=args.format,
                base_url=args.base_url or None,
                auth_key_env=args.auth_env,
            )
            if args.json or args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(str(payload.get("content") or ""))
            return
        if command in {"account-search", "accounts"}:
            if not args.keyword:
                print("Error: keyword is required", file=sys.stderr)
                sys.exit(2)
            payload = search_accounts(
                args.keyword,
                begin=max(args.begin, 0),
                size=max(args.size, 1),
                base_url=args.base_url or None,
                auth_key_env=args.auth_env,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else _format_wechat_exporter_records_markdown(payload, record_key="list"))
            return
        if command == "articles":
            if not args.fakeid:
                print("Error: fakeid is required", file=sys.stderr)
                sys.exit(2)
            payload = list_articles(
                args.fakeid,
                begin=max(args.begin, 0),
                size=max(args.size, 1),
                keyword=args.keyword or "",
                base_url=args.base_url or None,
                auth_key_env=args.auth_env,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else _format_wechat_exporter_records_markdown(payload, record_key="articles"))
            return
        if command == "account-by-url":
            if not args.url:
                print("Error: URL is required", file=sys.stderr)
                sys.exit(2)
            payload = account_by_url(args.url, base_url=args.base_url or None, auth_key_env=args.auth_env)
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else _format_wechat_exporter_records_markdown(payload, record_key="list"))
            return
        print(f"Error: unknown wechat-exporter command: {command}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

def _format_wechat_exporter_status_markdown(payload: dict) -> str:
    lines = [
        "# 观澜 WeChat Exporter 适配器",
        "",
        f"- 状态: {payload.get('status')}",
        f"- Base URL: {payload.get('base_url') or '-'}",
        f"- Base URL 环境变量: `{payload.get('base_url_env')}`",
        f"- Auth Key 环境变量: `{payload.get('auth_key_env')}`",
        f"- Auth Key: {'已配置' if payload.get('auth_key_configured') else '未配置'}",
        f"- 边界: {payload.get('boundary')}",
        "",
        "## 能力",
    ]
    lines.extend(f"- {item}" for item in payload.get("capabilities") or [])
    setup = payload.get("setup") or []
    if setup:
        lines.append("")
        lines.append("## 配置")
        lines.extend(f"- `{item}`" for item in setup)
    if payload.get("probe"):
        lines.append("")
        lines.append("## 探测")
        lines.append(f"- status: {payload['probe'].get('status')}")
        if payload["probe"].get("error"):
            lines.append(f"- error: {payload['probe'].get('error')}")
    return "\n".join(lines)

def _format_wechat_exporter_records_markdown(payload: dict, *, record_key: str) -> str:
    records = payload.get(record_key) or []
    lines = [
        "# 观澜 WeChat Exporter 结果",
        "",
        f"- operation: {payload.get('operation') or '-'}",
        f"- boundary: {payload.get('boundary') or '-'}",
        "",
    ]
    if not isinstance(records, list) or not records:
        lines.append("暂无记录。")
        return "\n".join(lines)
    for idx, item in enumerate(records[:20], 1):
        if not isinstance(item, dict):
            lines.append(f"{idx}. {item}")
            continue
        title = item.get("title") or item.get("nickname") or item.get("alias") or item.get("fakeid") or "未命名"
        url = item.get("link") or item.get("url") or ""
        summary = item.get("digest") or item.get("signature") or item.get("author_name") or ""
        lines.append(f"{idx}. {title}")
        if url:
            lines.append(f"   {url}")
        if summary:
            lines.append(f"   {summary}")
    return "\n".join(lines)

def _format_browser_assist_session_markdown(contract: dict) -> str:
    """Render browser-assist session contract without importing rich UI helpers."""

    lines = [
        "# 观澜浏览器辅助补证会话契约",
        "",
        f"- Session: `{contract.get('session_id_hint', '')}`",
        f"- 平台: {contract.get('platform') or '-'}",
        f"- URL: {contract.get('target_url') or '-'}",
        f"- 目标: {contract.get('task_goal') or '-'}",
        f"- 授权: {'需要' if contract.get('requires_user_authorization') else '不需要'}",
        f"- Timeout: {contract.get('timeout_budget_seconds')} 秒 / {contract.get('timeout_budget_ms')} ms",
        f"- 单位规则: {contract.get('unit_rule')}",
    ]
    rules = contract.get("same_session_rules") or []
    if rules:
        lines.append("")
        lines.append("## 同一会话规则")
        lines.extend(f"- {item}" for item in rules)
    readiness = contract.get("readiness_signals") or {}
    preferred = readiness.get("preferred_signals") or []
    if preferred:
        lines.append("")
        lines.append("## 就绪信号")
        lines.extend(f"- {item}" for item in preferred)
    sufficiency = contract.get("sufficiency_contract") or {}
    if sufficiency:
        lines.append("")
        lines.append("## 充分性")
        lines.append(f"- requested_min_items: {sufficiency.get('requested_min_items', 0)}")
        lines.extend(f"- {item}" for item in sufficiency.get("rules") or [])
    return "\n".join(lines)

def _cmd_read(args):
    """Read a URL and print Markdown for agents."""

    from guanlan.agent_planner import build_agent_followup, format_agent_followup_context
    from guanlan.web.read import (
        format_read_batch_context,
        format_read_batch_markdown,
        format_read_quality_report,
        read_batch,
        read_url,
        read_url_with_trace,
    )
    from guanlan.web.renderers import (
        format_read_batch_prompt,
        format_read_context,
        format_read_prompt,
        format_read_trace,
    )

    try:
        if args.url == "batch":
            if not args.batch_file:
                print("Error: read batch requires a URL list file", file=sys.stderr)
                sys.exit(2)
            with open(args.batch_file, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]
            records = read_batch(
                urls,
                max_chars=args.max_chars or None,
                backend=args.backend,
                fallback_search=args.fallback_search,
                fallback_limit=max(args.fallback_limit, 1),
                profile=args.profile or None,
                cache_ttl=max(args.cache_ttl, 0),
                concurrency=max(args.concurrency, 1),
                **_read_quality_kwargs(args),
            )
            if args.format == "json":
                print(json.dumps(records, ensure_ascii=False, indent=2))
            elif args.format == "context":
                print(format_read_batch_context(records))
            elif args.format == "prompt":
                print(format_read_batch_prompt(records, query=args.question or "请综合分析这些网页。"))
            else:
                print(format_read_batch_markdown(records))
            return
        if not args.url:
            print("Error: URL is required", file=sys.stderr)
            sys.exit(2)
        read_packet = None
        if args.trace or args.quality_report or args.format == "json":
            request = normalize_read_request({**vars(args), **_read_quality_kwargs(args)}, default_profile=None)
            request["watch"] = bool(args.watch)
            read_packet = read_url_with_trace(**request)
            content = str(read_packet.get("content", ""))
        else:
            content = read_url(
                args.url,
                max_chars=args.max_chars or None,
                backend=args.backend,
                fallback_search=args.fallback_search,
                fallback_limit=max(args.fallback_limit, 1),
                profile=args.profile or None,
                cache_ttl=max(args.cache_ttl, 0),
                use_cache=not args.no_cache,
                watch=args.watch,
                **_read_quality_kwargs(args),
            )
        if args.format == "json":
            payload = read_packet if read_packet is not None else {"url": args.url, "content": content}
            payload["agent_followup"] = build_agent_followup("guanlan_read", payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif args.format == "context":
            print(format_read_context(content, url=args.url))
            followup_text = format_agent_followup_context(
                build_agent_followup(
                    "guanlan_read",
                    read_packet if read_packet is not None else {"url": args.url, "content": content},
                )
            )
            if followup_text:
                print()
                print(followup_text)
            if args.quality_report and read_packet is not None:
                print()
                print(format_read_quality_report(read_packet))
            if args.trace and read_packet is not None:
                print()
                print(format_read_trace(read_packet))
        elif args.format == "prompt":
            print(format_read_prompt(content, query=args.question, url=args.url))
            if args.quality_report and read_packet is not None:
                print()
                print(format_read_quality_report(read_packet))
            if args.trace and read_packet is not None:
                print()
                print(format_read_trace(read_packet))
        else:
            print(content)
            if args.quality_report and read_packet is not None:
                print()
                print(format_read_quality_report(read_packet))
            if args.trace and read_packet is not None:
                print()
                print(format_read_trace(read_packet))
    except Exception as exc:
        print(f"Error: {format_user_error(exc)}", file=sys.stderr)
        sys.exit(1)

def _read_quality_kwargs(args) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    if getattr(args, "strict", False):
        kwargs["strict"] = True
    if getattr(args, "extract", "article") != "article":
        kwargs["extract"] = args.extract
    return kwargs

__all__ = ['_cmd_diagnose', '_cmd_browser_assist', '_cmd_wechat_exporter', '_format_wechat_exporter_status_markdown', '_format_wechat_exporter_records_markdown', '_format_browser_assist_session_markdown', '_cmd_read', '_read_quality_kwargs']
