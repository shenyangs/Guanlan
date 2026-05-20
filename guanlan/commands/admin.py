# -*- coding: utf-8 -*-
"""Administrative and runtime command handlers for Guanlan CLI."""

import json
import os
import secrets
import sys

from guanlan import __version__
from guanlan.commands._ops_helpers import (
    _classify_github_response_error,
    _github_get_with_retry,
    _parse_twitter_cookie_input,
    _print_sensitive_access_notice,
    _print_update_notice_if_available,
    _update_error_text,
)


def _cmd_welcome():
    """Show the short user-facing onboarding card."""
    from guanlan.onboarding import format_welcome_card, mark_welcome_shown

    print(format_welcome_card())
    mark_welcome_shown()

def _cmd_capabilities(args):
    """Show the Guanlan capability map for humans and agents."""
    from guanlan.capabilities import format_capabilities_json, format_capabilities_markdown

    if getattr(args, "json", False):
        print(format_capabilities_json())
    else:
        print(format_capabilities_markdown())

def _cmd_stock(args):
    """Run structured stock data commands."""
    from guanlan.stock_cli import run_stock_command

    run_stock_command(args)

def _cmd_install(args):
    """One-shot deterministic installer."""
    import os

    from guanlan.config import Config
    from guanlan.doctor import check_all, format_report
    from guanlan.profiles import get_profile

    safe_mode = args.safe
    dry_run = args.dry_run

    config = Config()
    active_profile = get_profile(config, args.profile or None)
    print()
    print("观澜 / Guanlan Installer")
    print("=" * 40)

    # Ensure tools directory exists (for upstream tool repos)
    tools_dir = os.path.expanduser("~/.guanlan/tools")
    os.makedirs(tools_dir, exist_ok=True)

    if dry_run:
        print("DRY RUN — showing what would be done (no changes)")
        print()
    if safe_mode:
        print("SAFE MODE — skipping automatic system changes")
        print()

    # ── Parse --channels ──
    CHANNEL_INSTALLERS = {
        "twitter":     _install_twitter_deps,
        "weibo":       _install_weibo_deps,
        "wechat":      _install_wechat_deps,
        "xiaoyuzhou":  _install_xiaoyuzhou_deps,
        "xiaohongshu": _install_xhs_deps,
        "reddit":      _install_reddit_deps,
        "bilibili":    _install_bili_deps,
        "zsxq":        _install_zsxq_deps,
        "zhishixingqiu": _install_zsxq_deps,
        "browseruse":  _install_browser_use_deps,
        "browser-use": _install_browser_use_deps,
        "openguanlan": _install_openguanlan_deps,
        "open-guanlan": _install_openguanlan_deps,
        "opencli":     _install_opencli_deps,
        "open-cli":    _install_opencli_deps,
        # douyin/linkedin: manual setup, no auto-install
    }
    COOKIE_CHANNELS = {"twitter", "xueqiu", "bilibili"}

    requested_channels = set()
    if args.channels:
        raw = [c.strip().lower() for c in args.channels.split(",") if c.strip()]
        normalized = ["browseruse" if item in {"browser-use", "browser_use"} else item for item in raw]
        if "all" in normalized:
            requested_channels = set(CHANNEL_INSTALLERS.keys()) | {"xueqiu", "douyin", "linkedin"}
        else:
            requested_channels = set(normalized)

    # Auto-detect environment
    env = args.env
    if env == "auto":
        env = _detect_environment()

    if env == "server":
        print("Environment: Server/VPS (auto-detected)")
    else:
        print("Environment: Local computer (auto-detected)")
    print(f"Profile: {active_profile}")

    # Apply explicit flags
    if args.proxy:
        if dry_run:
            print("[dry-run] Would configure proxy for Bilibili")
        else:
            config.set("bilibili_proxy", args.proxy)
            print("✅ Proxy configured for Bilibili")

    # ── Install core system dependencies (lightweight, always) ──
    print()
    if dry_run:
        _install_system_deps_dryrun()
    elif safe_mode:
        _install_system_deps_safe()
    else:
        _install_system_deps()

    # ── mcporter (for Exa search) ──
    print()
    if dry_run:
        print("[dry-run] Would install mcporter and configure Exa search")
    elif safe_mode:
        _install_mcporter_safe()
    else:
        _install_mcporter()

    # ── Install optional channels (only if --channels specified) ──
    if requested_channels and not dry_run and not safe_mode:
        print()
        print("Installing optional channels...")
        for ch_name in sorted(requested_channels):
            installer = CHANNEL_INSTALLERS.get(ch_name)
            if installer:
                installer()

    if requested_channels and dry_run:
        print()
        print(f"[dry-run] Would install optional channels: {', '.join(sorted(requested_channels))}")

    # ── Cookie import is always explicit ──
    needs_cookies = bool(requested_channels & COOKIE_CHANNELS)
    if env == "local" and needs_cookies and not safe_mode and not dry_run:
        print()
        print("Cookie import is explicit and will not run automatically.")
        print("To unlock cookie-based channels later, run:")
        print("  guanlan configure --from-browser chrome")
        print("or paste exported cookies with Cookie-Editor. This avoids surprise Keychain prompts.")
    elif env == "local" and needs_cookies and dry_run:
        print()
        print("[dry-run] Would not auto-import cookies. Use `guanlan configure --from-browser chrome` explicitly.")

    # Environment-specific advice
    if env == "server":
        print()
        print("Tip: Bilibili may block server IPs.")
        print("   Reddit: rdt-cli works without proxy (pipx install rdt-cli).")
        print("   For Bilibili full access: guanlan configure proxy http://user:pass@ip:port")
        print("   Cheap option: https://www.webshare.io ($1/month)")

    # Test channels
    if not dry_run:
        print()
        print("Testing channels...")
        results = check_all(config, profile=active_profile, skip_sensitive=True)
        ok = sum(1 for r in results.values() if r["status"] == "ok")
        total = len(results)

        # Final status
        print()
        print(format_report(results, profile=active_profile))
        print()

        # ── Install agent skill ──
        _install_skill()

        print(f"✅ Installation complete! {ok}/{total} channels active.")

        if not requested_channels:
            # First install — hint about optional channels
            print()
            print("More channels available! Use --channels to install:")
            print("   guanlan install --channels=twitter,weibo,xiaohongshu,...")
            print("   guanlan install --channels=all  (install everything)")

        print()
        print("后续可以运行 `guanlan doctor --trace` 查看诊断路径。")
        from guanlan.onboarding import show_welcome_once

        show_welcome_once()
    else:
        print()
        print("Dry run complete. No changes were made.")

def _install_skill():
    """Install 观澜 / Guanlan as an agent skill (OpenClaw / Claude Code / .agents)."""
    import importlib.resources
    import os
    import shutil

    def _is_english_locale(value: str) -> bool:
        normalized = value.strip().lower()
        return normalized.startswith("en") or normalized.startswith("english")

    def _skill_resource_name() -> str:
        locale_candidates = (
            os.environ.get("GUANLAN_LANG", ""),
            os.environ.get("LC_ALL", ""),
            os.environ.get("LC_MESSAGES", ""),
            os.environ.get("LANG", ""),
        )
        if any(_is_english_locale(candidate) for candidate in locale_candidates):
            return "SKILL_en.md"
        return "SKILL.md"

    def _read_skill_markdown(skill_pkg):
        resource_name = _skill_resource_name()
        try:
            return skill_pkg.joinpath(resource_name).read_text(encoding="utf-8")
        except FileNotFoundError:
            return skill_pkg.joinpath("SKILL.md").read_text(encoding="utf-8")

    def _copy_skill_dir(target: str) -> bool:
        """Copy entire skill directory (locale-specific SKILL.md + references/)."""
        try:
            # Clear existing installation
            if os.path.exists(target):
                shutil.rmtree(target)
            os.makedirs(target, exist_ok=True)

            # Get skill directory from package (with fallback for editable installs)
            try:
                skill_pkg = importlib.resources.files("guanlan").joinpath("skill")
                skill_md = _read_skill_markdown(skill_pkg)
            except Exception:
                from pathlib import Path
                skill_pkg = Path(__file__).resolve().parent / "skill"
                skill_md = _read_skill_markdown(skill_pkg)

            # Copy SKILL.md using the selected locale file
            with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write(skill_md)

            # Copy references/ directory
            refs_pkg = skill_pkg.joinpath("references")
            refs_target = os.path.join(target, "references")
            os.makedirs(refs_target, exist_ok=True)

            for ref_file in refs_pkg.iterdir():
                name = ref_file.name if hasattr(ref_file, 'name') else str(ref_file).split('/')[-1]
                if name.endswith(".md"):
                    content = ref_file.read_text(encoding="utf-8") if hasattr(ref_file, 'read_text') else ref_file.read_text()
                    with open(os.path.join(refs_target, name), "w", encoding="utf-8") as f:
                        f.write(content)

            return True
        except Exception as e:
            print(f"  Warning: Could not install skill: {e}")
            return False

    # Determine skill install path (priority: .agents > openclaw > claude)
    skill_dirs = [
        os.path.expanduser("~/.agents/skills"),      # Generic agents (priority)
        os.path.expanduser("~/.openclaw/skills"),    # OpenClaw
        os.path.expanduser("~/.claude/skills"),      # Claude Code (if exists)
    ]

    # Insert OPENCLAW_HOME path at the beginning if environment variable is set
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        skill_dirs.insert(0, os.path.join(openclaw_home, ".openclaw", "skills"))

    installed = False
    for skill_dir in skill_dirs:
        if os.path.isdir(skill_dir):
            target = os.path.join(skill_dir, "guanlan")
            if _copy_skill_dir(target):
                platform_name = "Agent" if ".agents" in skill_dir else "OpenClaw" if "openclaw" in skill_dir else "Claude Code"
                print(f"Skill installed for {platform_name}: {target}")
                installed = True

    if not installed:
        # No known skill directory found — create for .agents by default
        target = os.path.expanduser("~/.agents/skills/guanlan")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if _copy_skill_dir(target):
            print(f"Skill installed: {target}")
        else:
            print("  -- Could not install agent skill (optional)")
            print("  -- Tip: install OpenClaw, Claude Code, or create ~/.agents/skills/ manually")

def _uninstall_skill():
    """Remove SKILL.md from all known agent skill directories."""
    import shutil

    skill_dirs = [
        ("~/.openclaw/skills/guanlan", "OpenClaw"),
        ("~/.claude/skills/guanlan", "Claude Code"),
        ("~/.agents/skills/guanlan", "Agent"),
    ]

    # Also check OPENCLAW_HOME
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        skill_dirs.insert(
            0,
            (os.path.join(openclaw_home, ".openclaw", "skills", "guanlan"), "OpenClaw"),
        )

    removed = False
    for skill_path_template, platform_name in skill_dirs:
        skill_path = os.path.expanduser(skill_path_template)
        if os.path.isdir(skill_path):
            try:
                shutil.rmtree(skill_path)
                print(f"  Removed {platform_name} skill: {skill_path}")
                removed = True
            except Exception as e:
                print(f"  Could not remove {skill_path}: {e}")

    if not removed:
        print("  No skill installations found.")

def _cmd_skill(args):
    """Manage agent skill registration."""
    if args.install:
        _install_skill()
    elif args.uninstall:
        _uninstall_skill()

def _cmd_format(args):
    """Clean and format platform API output from stdin."""
    import sys

    if args.platform == "xhs":
        from guanlan.channels.xiaohongshu import format_xhs_result

        raw = sys.stdin.read().strip()
        if not raw:
            print("Error: no input on stdin", file=sys.stderr)
            sys.exit(1)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"Error: invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)

        cleaned = format_xhs_result(data)
        print(json.dumps(cleaned, ensure_ascii=False, indent=2))
    elif args.platform == "hotnews":
        from guanlan.hotnews import format_hotnews_markdown, normalize_hotnews_payload

        raw = sys.stdin.read().strip()
        if not raw:
            print("Error: no input on stdin", file=sys.stderr)
            sys.exit(1)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"Error: invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)

        cleaned = normalize_hotnews_payload(data)
        print(format_hotnews_markdown(cleaned))

def _cmd_archive(args):
    """Manage the local Markdown archive."""

    from guanlan.commands.archive import handle_archive_command

    handle_archive_command(args)

def _cmd_mcp(args):
    """Print MCP integration helpers."""

    from guanlan.mcp_config import build_mcp_config, format_mcp_config_markdown

    command = getattr(args, "mcp_command", None)
    if command != "config":
        print("Error: mcp command is required: config", file=sys.stderr)
        sys.exit(2)
    try:
        if args.format == "json":
            print(
                json.dumps(
                    build_mcp_config(client=args.client, command=args.server_command),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(format_mcp_config_markdown(client=args.client, command=args.server_command))
            print()
            print(
                "接好 MCP 后，可以问 Agent："
                "“请调用 guanlan_capabilities，告诉我观澜能做什么。”"
            )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

def _cmd_serve(args):
    """Run local read-only HTTP service."""
    if args.print_token:
        print(secrets.token_urlsafe(24))
        return
    token = args.token or os.environ.get("GUANLAN_SERVE_TOKEN", "")
    if token == "auto":
        token = secrets.token_urlsafe(24)
        print(f"Generated GUANLAN_SERVE_TOKEN: {token}", file=sys.stderr)
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not token:
        print(
            "[!] 默认建议只监听 127.0.0.1；当前未设置 --token / GUANLAN_SERVE_TOKEN。服务虽只读，但可能暴露本地 archive 内容和搜索行为。",
            file=sys.stderr,
        )
    elif args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("[i] 非本地监听已启用 token 校验；请仍确认网络边界。", file=sys.stderr)
    from guanlan.serve import run_server

    run_server(host=args.host, port=max(args.port, 1), token=token)

def _cmd_plugin(args):
    """Manage read-only plugin backends."""
    from guanlan.plugins import list_plugins, plugin_template, register_plugin

    command = getattr(args, "plugin_command", None)
    try:
        if command == "list":
            print(json.dumps(list_plugins(), ensure_ascii=False, indent=2))
            return
        if command == "register":
            print(json.dumps(register_plugin(args.name, args.path), ensure_ascii=False, indent=2))
            return
        if command == "template":
            print(plugin_template(args.name))
            return
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print("Error: plugin command is required: list, register, template", file=sys.stderr)
    sys.exit(2)

def _cmd_eval(args):
    """Show built-in evaluation scenarios."""
    from guanlan.evaluation import (
        format_benchmark_jsonl,
        format_benchmark_markdown,
        format_benchmark_tasks_markdown,
        format_eval_suite_jsonl,
        format_eval_suite_markdown,
        format_eval_suites_markdown,
        format_evaluation_jsonl,
        format_evaluation_markdown,
        list_benchmark_tasks,
        list_eval_suites,
        list_evaluation_scenarios,
        run_benchmark,
        run_eval_suite,
        write_eval_suite_html,
    )

    command = getattr(args, "eval_command", None)
    if command not in {"scenarios", "tasks", "benchmark", "suite"}:
        print("Error: eval command is required: scenarios, tasks, benchmark, or suite", file=sys.stderr)
        sys.exit(2)
    if command == "suite":
        suite_command = getattr(args, "eval_suite_command", None)
        if suite_command == "list":
            suites = list_eval_suites()
            if args.format == "json":
                print(json.dumps(suites, ensure_ascii=False, indent=2))
            else:
                print(format_eval_suites_markdown(suites))
            return
        if suite_command == "run":
            report = run_eval_suite(args.suite_id, mode=args.mode, limit=max(args.limit, 1))
            if args.format == "json":
                print(json.dumps(report, ensure_ascii=False, indent=2))
            elif args.format == "jsonl":
                print(format_eval_suite_jsonl(report))
            else:
                print(format_eval_suite_markdown(report))
            if report.get("summary", {}).get("fail", 0):
                sys.exit(1)
            return
        if suite_command == "report":
            report = run_eval_suite(args.suite_id, mode=args.mode, limit=max(args.limit, 1))
            output = write_eval_suite_html(report, args.output)
            print(f"Eval suite report written: {output}")
            if report.get("summary", {}).get("fail", 0):
                sys.exit(1)
            return
        print("Error: eval suite command is required: list, run, or report", file=sys.stderr)
        sys.exit(2)
    if command == "benchmark":
        report = run_benchmark(mode=args.mode, limit=max(args.limit, 1))
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.format == "jsonl":
            print(format_benchmark_jsonl(report))
        else:
            print(format_benchmark_markdown(report))
        if report.get("summary", {}).get("fail", 0):
            sys.exit(1)
        return
    if command == "tasks":
        tasks = list_benchmark_tasks(category=args.category or None)
        if args.format == "json":
            print(json.dumps(tasks, ensure_ascii=False, indent=2))
        elif args.format == "jsonl":
            for task in tasks:
                print(json.dumps(task, ensure_ascii=False, sort_keys=True))
        else:
            print(format_benchmark_tasks_markdown(tasks))
        return
    scenarios = list_evaluation_scenarios()
    if args.format == "json":
        print(json.dumps(scenarios, ensure_ascii=False, indent=2))
    elif args.format == "jsonl":
        print(format_evaluation_jsonl(scenarios))
    else:
        print(format_evaluation_markdown(scenarios))

def _cmd_quality(args):
    """Run Guanlan quality gates."""
    from guanlan.quality import (
        format_backend_fixtures_report,
        format_coverage_jsonl,
        format_coverage_report,
        format_foundational_report,
        format_performance_report,
        format_quality_jsonl,
        format_quality_report,
        format_regression_report,
        format_robustness_report,
        run_backend_fixture_checks,
        run_coverage_checks,
        run_foundational_checks,
        run_live_smoke_checks,
        run_performance_checks,
        run_quality_checks,
        run_regression_checks,
        run_robustness_checks,
    )

    command = getattr(args, "quality_command", None)
    if command not in {
        "run",
        "foundational",
        "coverage",
        "regression",
        "robustness",
        "performance",
        "backend-fixtures",
        "live-smoke",
    }:
        print(
            "Error: quality command is required: run, foundational, coverage, regression, robustness, performance, "
            "backend-fixtures, or live-smoke",
            file=sys.stderr,
        )
        sys.exit(2)
    if command == "live-smoke":
        report = run_live_smoke_checks(
            limit=max(args.limit, 1),
            timeout_budget=max(args.timeout_budget, 1),
            profile=args.profile,
            history_path=args.history_path,
            trend_window=max(args.trend_window, 1),
            record_history=bool(args.record_history),
        )
        report["contract"]["blocking"] = bool(args.strict)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.format == "jsonl":
            print(format_quality_jsonl(report))
        else:
            print(format_quality_report(report))
        if args.strict and report.get("summary", {}).get("fail", 0):
            sys.exit(1)
        return
    if command == "foundational":
        report = run_foundational_checks(mode=args.mode, limit=max(args.limit, 1))
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.format == "jsonl":
            print(format_coverage_jsonl(report))
        else:
            print(format_foundational_report(report))
        if report.get("summary", {}).get("fail", 0):
            sys.exit(1)
        return
    if command == "coverage":
        report = run_coverage_checks(mode=args.mode, limit=max(args.limit, 1))
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.format == "jsonl":
            print(format_coverage_jsonl(report))
        else:
            print(format_coverage_report(report))
        if report.get("summary", {}).get("fail", 0):
            sys.exit(1)
        return
    if command == "regression":
        report = run_regression_checks(mode=args.mode, limit=max(args.limit, 1))
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.format == "jsonl":
            print(format_coverage_jsonl(report))
        else:
            print(format_regression_report(report))
        if report.get("summary", {}).get("fail", 0):
            sys.exit(1)
        return
    if command == "robustness":
        report = run_robustness_checks(mode=args.mode, limit=max(args.limit, 1))
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.format == "jsonl":
            print(format_coverage_jsonl(report))
        else:
            print(format_robustness_report(report))
        if report.get("summary", {}).get("fail", 0):
            sys.exit(1)
        return
    if command == "performance":
        report = run_performance_checks()
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.format == "jsonl":
            print(format_coverage_jsonl(report))
        else:
            print(format_performance_report(report))
        if report.get("summary", {}).get("fail", 0):
            sys.exit(1)
        return
    if command == "backend-fixtures":
        report = run_backend_fixture_checks()
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.format == "jsonl":
            print(format_coverage_jsonl(report))
        else:
            print(format_backend_fixtures_report(report))
        if report.get("summary", {}).get("fail", 0):
            sys.exit(1)
        return

    report = run_quality_checks(mode=args.mode, limit=max(args.limit, 1), coverage=getattr(args, "coverage", False))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.format == "jsonl":
        print(format_quality_jsonl(report))
    else:
        print(format_quality_report(report))
    if report.get("summary", {}).get("fail", 0):
        sys.exit(1)


def _cmd_report(args):
    """Render optional static HTML reports from existing JSON payloads."""

    from guanlan.reports import read_report_payload, write_html_report

    command = getattr(args, "report_command", None)
    if command != "html":
        print("Error: report command is required: html", file=sys.stderr)
        sys.exit(2)

    try:
        stdin_text = sys.stdin.read() if args.input == "-" else None
        payload = read_report_payload(args.input or None, stdin_text=stdin_text)
        result = write_html_report(
            payload,
            args.output,
            title=args.title,
            subtitle=args.subtitle,
            score_mode=args.score_mode,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("# 观澜旁支 HTML 报表")
    print()
    print(f"- 输出: {result['path']}")
    print(f"- 条目: {result['items']}")
    print(f"- 指标: {result['metrics']}")
    print(f"- 色彩模式: {result['score_mode']}")
    print("- 边界: 只渲染已有 JSON/样例数据，不触发搜索、阅读或归档。")


def _install_system_deps():
    """Install system-level dependencies: gh CLI, Node.js (for mcporter)."""
    import platform
    import shutil
    import subprocess
    import tempfile

    print("Checking system dependencies...")

    # ── gh CLI ──
    if shutil.which("gh"):
        print("  ✅ gh CLI already installed")
    else:
        print("  Installing gh CLI...")
        os_type = platform.system().lower()
        if os_type == "linux":
            try:
                # Official GitHub apt source setup without invoking a shell.
                keyring_path = "/usr/share/keyrings/githubcli-archive-keyring.gpg"
                list_path = "/etc/apt/sources.list.d/github-cli.list"
                arch = subprocess.run(
                    ["dpkg", "--print-architecture"],
                    capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                ).stdout.strip() or "amd64"
                subprocess.run(
                    ["curl", "-fsSL", "https://cli.github.com/packages/githubcli-archive-keyring.gpg", "-o", keyring_path],
                    capture_output=True, timeout=60,
                )
                repo_line = (
                    f"deb [arch={arch} signed-by={keyring_path}] "
                    "https://cli.github.com/packages stable main\n"
                )
                with open(list_path, "w", encoding="utf-8") as f:
                    f.write(repo_line)
                subprocess.run(["apt-get", "update", "-qq"], capture_output=True, timeout=60)
                subprocess.run(["apt-get", "install", "-y", "-qq", "gh"], capture_output=True, timeout=60)
                if shutil.which("gh"):
                    print("  ✅ gh CLI installed")
                else:
                    print("  [!]  gh CLI install failed. You can try: snap install gh, or download from https://github.com/cli/cli/releases")
            except Exception:
                print("  [!]  gh CLI install failed. You can try: snap install gh, or download from https://github.com/cli/cli/releases")
        elif os_type == "darwin":
            if shutil.which("brew"):
                try:
                    subprocess.run(["brew", "install", "gh"], capture_output=True, timeout=120)
                    if shutil.which("gh"):
                        print("  ✅ gh CLI installed")
                    else:
                        print("  [!]  gh CLI install failed. Try: brew install gh")
                except Exception:
                    print("  [!]  gh CLI install failed. Try: brew install gh")
            else:
                print("  [!]  gh CLI not found. Install: https://cli.github.com")
        else:
            print("  [!]  gh CLI not found. Install: https://cli.github.com")

    # ── Node.js (needed for mcporter) ──
    if shutil.which("node") and shutil.which("npm"):
        print("  ✅ Node.js already installed")
    else:
        print("  Installing Node.js...")
        try:
            # Use NodeSource setup script without invoking a shell pipeline.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".sh") as tf:
                script_path = tf.name
            subprocess.run(
                ["curl", "-fsSL", "https://deb.nodesource.com/setup_22.x", "-o", script_path],
                capture_output=True, timeout=60,
            )
            subprocess.run(
                ["bash", script_path],
                capture_output=True, timeout=120,
            )
            try:
                os.unlink(script_path)
            except Exception:
                pass
            subprocess.run(
                ["apt-get", "install", "-y", "-qq", "nodejs"],
                capture_output=True, timeout=120,
            )
            if shutil.which("node"):
                print("  ✅ Node.js installed")
            else:
                print("  [!]  Node.js install failed. Try: apt install nodejs npm, or nvm install 22, or download from https://nodejs.org")
        except Exception:
            print("  [!]  Node.js install failed. Try: apt install nodejs npm, or nvm install 22, or download from https://nodejs.org")

    # ── undici (proxy support for Node.js fetch) ──
    npm_cmd = shutil.which("npm")
    if npm_cmd:
        npm_root = subprocess.run([npm_cmd, "root", "-g"], capture_output=True, encoding="utf-8", errors="replace", timeout=5).stdout.strip()
        undici_path = os.path.join(npm_root, "undici", "index.js") if npm_root else ""
        if os.path.exists(undici_path):
            print("  ✅ undici already installed (Node.js proxy support)")
        else:
            try:
                subprocess.run([npm_cmd, "install", "-g", "undici"], capture_output=True, encoding="utf-8", errors="replace", timeout=60)
                print("  ✅ undici installed (Node.js proxy support)")
            except Exception:
                print("  -- undici install failed (optional — may not work behind proxies)")

    # ── yt-dlp JS runtime config (YouTube requires external JS runtime) ──
    if shutil.which("node"):
        ytdlp_config_dir = os.path.expanduser("~/.config/yt-dlp")
        ytdlp_config = os.path.join(ytdlp_config_dir, "config")
        needs_config = True
        if os.path.exists(ytdlp_config):
            with open(ytdlp_config, "r") as f:
                if "--js-runtimes" in f.read():
                    needs_config = False
                    print("  ✅ yt-dlp JS runtime already configured")
        if needs_config:
            try:
                os.makedirs(ytdlp_config_dir, exist_ok=True)
                with open(ytdlp_config, "a") as f:
                    f.write("--js-runtimes node\n")
                print("  ✅ yt-dlp configured to use Node.js as JS runtime (YouTube)")
            except Exception:
                print("  -- Could not configure yt-dlp JS runtime (YouTube may not work)")

def _install_xiaoyuzhou_deps():
    """Install Xiaoyuzhou podcast transcription script."""
    import shutil

    from guanlan.config import Config

    config = Config()
    print("Setting up Xiaoyuzhou podcast transcription...")

    tools_dir = os.path.expanduser("~/.guanlan/tools/xiaoyuzhou")
    script_dst = os.path.join(tools_dir, "transcribe.sh")

    if os.path.isfile(script_dst):
        print("  ✅ Xiaoyuzhou transcription script already installed")
    else:
        # Copy script from package
        script_src = os.path.join(os.path.dirname(__file__), "scripts", "transcribe_xiaoyuzhou.sh")
        if os.path.isfile(script_src):
            try:
                os.makedirs(tools_dir, exist_ok=True)
                import shutil as _shutil
                _shutil.copy2(script_src, script_dst)
                os.chmod(script_dst, 0o755)
                print("  ✅ Xiaoyuzhou transcription script installed")
            except Exception as e:
                print(f"  [!]  Failed to install script: {e}")
        else:
            print("  [!]  Script source not found in package")

    # Check ffmpeg
    if shutil.which("ffmpeg"):
        print("  ✅ ffmpeg available")
    else:
        print("  -- ffmpeg not found. Install: apt install -y ffmpeg (or brew install ffmpeg)")

    # Check GROQ_API_KEY
    has_key = bool(os.environ.get("GROQ_API_KEY")) or bool(config.get("groq_api_key"))
    if has_key:
        print("  ✅ Groq API key configured")
    else:
        print("  -- Groq API key not set. Get free key at https://console.groq.com")
        print("     Then run: guanlan configure groq-key gsk_xxxxx")

def _install_twitter_deps():
    """Install twitter-cli for Twitter search + timeline."""
    import shutil
    import subprocess

    print("Setting up Twitter (twitter-cli)...")
    if shutil.which("twitter"):
        print("  ✅ twitter-cli already installed")
        return
    for tool, cmd in [("pipx", ["pipx", "install", "twitter-cli"]),
                      ("uv", ["uv", "tool", "install", "twitter-cli"])]:
        if shutil.which(tool):
            try:
                subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=120)
                if shutil.which("twitter"):
                    print("  ✅ twitter-cli installed")
                    return
            except Exception:
                pass
    print("  [!]  twitter-cli install failed. Run: pipx install twitter-cli")

def _install_browser_use_deps():
    """Install browser-use CLI bridge for browser-assisted evidence handoff."""
    import shutil
    import subprocess

    print("Setting up browser-use CLI...")

    browser_use_bin = shutil.which("browser-use")
    if browser_use_bin:
        print("  ✅ browser-use already installed")
        return

    if sys.version_info < (3, 11):
        version_text = f"{sys.version_info.major}.{sys.version_info.minor}"
        print(f"  -- Current Python {version_text} is below browser-use requirement (>=3.11).")
        print("     Use a Python 3.11+ env and run: uvx --from 'browser-use[cli]' browser-use doctor")
        return

    for tool, cmd in [
        ("uv", ["uv", "tool", "install", "browser-use[cli]"]),
        ("pipx", ["pipx", "install", "browser-use[cli]"]),
    ]:
        if not shutil.which(tool):
            continue
        try:
            subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=180)
            if shutil.which("browser-use"):
                print("  ✅ browser-use installed")
                return
        except Exception:
            pass
    print("  [!]  browser-use install failed. Try: uvx --from 'browser-use[cli]' browser-use doctor")

def _install_opencli_deps():
    """Install OpenCLI CLI; Browser Bridge extension remains a manual browser step."""
    import shutil
    import subprocess

    print("Setting up OpenCLI browser bridge...")
    if shutil.which("opencli"):
        print("  ✅ opencli already installed")
    else:
        npm = shutil.which("npm")
        if not npm:
            print("  [!] npm not found. Install Node.js/npm first, then run: npm install -g @jackwener/opencli@latest")
            return
        try:
            subprocess.run(
                [npm, "install", "-g", "@jackwener/opencli@latest"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
        except Exception as exc:
            print(f"  [!] opencli install failed: {exc}")
            return
        if shutil.which("opencli"):
            print("  ✅ opencli installed")
        else:
            print("  [!] opencli install did not expose an `opencli` command. Check npm global bin path.")
            return
    print("  Next manual browser step:")
    print("    1. Install/enable the OpenCLI Chrome extension:")
    print("       https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk")
    print("    2. Run: opencli doctor")
    print("    3. Run: guanlan browser-assist adapters --check --json")

def _install_openguanlan_deps():
    """Explain the OpenGuanlan browser-assist layer and optional bridge path."""
    import shutil

    print("OpenGuanlan is Guanlan's browser-assist layer.")
    print("  Default path requires no extension or daemon:")
    print("     guanlan browser-assist run \"URL\" --adapter openguanlan --json")
    if shutil.which("openguanlan"):
        print("  ✅ optional openguanlan bridge command is available")
        print("  Run: openguanlan setup --json")
        print("  Run: openguanlan daemon")
        print("  Run: openguanlan doctor --json")
    else:
        print("  -- openguanlan is bundled with Guanlan 0.5.30+.")
        print("  -- Reinstall/upgrade Guanlan, then refresh your shell path:")
        print("     uv tool install --force --upgrade --refresh --default-index https://pypi.org/simple guanlan && hash -r")
    print("  Optional bridge manual browser step:")
    print("     open chrome://extensions and Load unpacked the directory from `openguanlan extension path`")
    print("  Optional bridge adapter:")
    print("     guanlan browser-assist run \"URL\" --adapter openguanlan-bridge --json")
    print("  OpenCLI remains an optional compatibility path, not the Guanlan-native default.")

def _install_xhs_deps():
    """Install xhs-cli (xiaohongshu-cli) for XiaoHongShu."""
    import shutil
    import subprocess

    print("Setting up XiaoHongShu (xhs-cli)...")
    if shutil.which("xhs"):
        print("  ✅ xhs-cli already installed")
        return
    for tool, cmd in [("pipx", ["pipx", "install", "xiaohongshu-cli"]),
                      ("uv", ["uv", "tool", "install", "xiaohongshu-cli"])]:
        if shutil.which(tool):
            try:
                subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=120)
                if shutil.which("xhs"):
                    print("  ✅ xhs-cli installed (run `xhs login` to authenticate)")
                    return
            except Exception:
                pass
    print("  [!]  xhs-cli install failed. Run: pipx install xiaohongshu-cli")

def _install_zsxq_deps():
    """Install zsxq-cli for optional ZhiShiXingQiu workflows."""
    import shutil
    import subprocess

    print("Setting up ZhiShiXingQiu (zsxq-cli)...")
    if shutil.which("zsxq-cli"):
        print("  ✅ zsxq-cli already installed")
        print("  Login when needed: zsxq-cli auth login")
        return
    npm = shutil.which("npm")
    if not npm:
        print("  [!]  npm not found. Install Node.js first, then run: npm install -g zsxq-cli")
        return
    try:
        subprocess.run(
            [npm, "install", "-g", "zsxq-cli"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if shutil.which("zsxq-cli"):
            print("  ✅ zsxq-cli installed")
            print("  Login when needed: zsxq-cli auth login")
            return
    except Exception:
        pass
    print("  [!]  zsxq-cli install failed. Run: npm install -g zsxq-cli")

def _install_reddit_deps():
    """Install rdt-cli for Reddit search + reading."""
    import shutil
    import subprocess

    print("Setting up Reddit (rdt-cli)...")
    if shutil.which("rdt"):
        print("  ✅ rdt-cli already installed")
        return
    for tool, cmd in [("pipx", ["pipx", "install", "rdt-cli"]),
                      ("uv", ["uv", "tool", "install", "rdt-cli"])]:
        if shutil.which(tool):
            try:
                subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=120)
                if shutil.which("rdt"):
                    print("  ✅ rdt-cli installed")
                    return
            except Exception:
                pass
    print("  [!]  rdt-cli install failed. Run: pipx install rdt-cli")

def _install_bili_deps():
    """Install bili-cli for Bilibili hot/rank/search."""
    import shutil
    import subprocess

    print("Setting up Bilibili (bili-cli)...")
    if shutil.which("bili"):
        print("  ✅ bili-cli already installed")
        return
    for tool, cmd in [("pipx", ["pipx", "install", "bilibili-cli"]),
                      ("uv", ["uv", "tool", "install", "bilibili-cli"])]:
        if shutil.which(tool):
            try:
                subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=120)
                if shutil.which("bili"):
                    print("  ✅ bili-cli installed")
                    return
            except Exception:
                pass
    print("  [!]  bili-cli install failed. Run: pipx install bilibili-cli")

def _install_weibo_deps():
    """Install Weibo MCP server."""
    import shutil
    import subprocess

    print("Setting up Weibo MCP server...")

    # Check if already installed and working
    mcporter = shutil.which("mcporter")
    if mcporter:
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "weibo" in r.stdout:
                print("  ✅ Weibo MCP already configured")
                return
        except Exception:
            pass

    # Install MCP server package
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             "mcp-server-weibo"],
            check=True, timeout=120
        )
        print("  ✅ mcp-server-weibo installed")
    except Exception as e:
        print(f"  [!]  mcp-server-weibo install failed: {e}")
        return

    # Register with mcporter
    if mcporter:
        try:
            subprocess.run(
                [mcporter, "config", "add", "weibo", "--command", "mcp-server-weibo"],
                check=True, capture_output=True, timeout=10
            )
            print("  ✅ Weibo MCP registered with mcporter")
        except Exception:
            print("  [!]  mcporter config add failed. Run manually: mcporter config add weibo --command 'mcp-server-weibo'")
    else:
        print("  -- mcporter not found, skipping MCP registration. Install mcporter first, then run: mcporter config add weibo --command 'mcp-server-weibo'")

def _install_wechat_deps():
    """Install WeChat article reading and search dependencies."""
    import subprocess

    print("Setting up WeChat article tools...")

    # Check if already installed
    has_camoufox = False
    has_miku = False
    try:
        import camoufox  # noqa: F401
        has_camoufox = True
    except ImportError:
        pass
    try:
        import miku_ai  # noqa: F401
        has_miku = True
    except ImportError:
        pass

    # Install Python packages
    if has_camoufox and has_miku:
        print("  ✅ WeChat Python packages already installed")
    else:
        pkgs = []
        if not has_camoufox:
            pkgs.extend(["camoufox[geoip]", "markdownify", "beautifulsoup4", "httpx"])
        if not has_miku:
            pkgs.append("miku_ai")
        try:
            cmd = [sys.executable, "-m", "pip", "install", "--break-system-packages", "-q"] + pkgs
            subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=120)
            # Verify
            ok = True
            try:
                import importlib
                if not has_camoufox:
                    importlib.import_module("camoufox")
                if not has_miku:
                    importlib.import_module("miku_ai")
            except ImportError:
                ok = False
            if ok:
                print(f"  ✅ WeChat Python packages installed ({', '.join(pkgs)})")
            else:
                print(f"  [!]  Some WeChat packages failed to install. Try: pip install {' '.join(pkgs)}")
        except Exception:
            print(f"  [!]  WeChat packages install failed. Try: pip install {' '.join(pkgs)}")

    # Clone wechat-article-for-ai tool
    tools_dir = os.path.expanduser("~/.guanlan/tools")
    wechat_dir = os.path.join(tools_dir, "wechat-article-for-ai")
    if os.path.isfile(os.path.join(wechat_dir, "main.py")):
        print("  ✅ wechat-article-for-ai tool already installed")
    else:
        try:
            os.makedirs(tools_dir, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1",
                 "https://github.com/search?q=wechat-article-for-ai", wechat_dir],
                capture_output=True, encoding="utf-8", errors="replace", timeout=60,
            )
            if os.path.isfile(os.path.join(wechat_dir, "main.py")):
                print("  ✅ wechat-article-for-ai tool installed")
            else:
                print("  [!]  wechat-article-for-ai clone failed. Try: git clone https://github.com/search?q=wechat-article-for-ai " + wechat_dir)
        except Exception:
            print("  [!]  wechat-article-for-ai clone failed. Try: git clone https://github.com/search?q=wechat-article-for-ai " + wechat_dir)

def _install_system_deps_safe():
    """Safe mode: check what's installed, print instructions for what's missing."""
    import shutil

    print("Checking system dependencies (safe mode — no auto-install)...")

    deps = [
        ("gh", ["gh"], "GitHub CLI", "https://cli.github.com — or: apt install gh / brew install gh"),
        ("node", ["node", "npm"], "Node.js", "https://nodejs.org — or: apt install nodejs npm"),
    ]

    missing = []
    for name, binaries, label, install_hint in deps:
        found = any(shutil.which(b) for b in binaries)
        if found:
            print(f"  ✅ {label} already installed")
        else:
            print(f"  -- {label} not found")
            missing.append((label, install_hint))

    if missing:
        print()
        print("  To install missing dependencies manually:")
        for label, hint in missing:
            print(f"    {label}: {hint}")
    else:
        print("  All system dependencies are installed!")

def _install_system_deps_dryrun():
    """Dry-run: just show what would be checked/installed."""
    import shutil

    print("[dry-run] System dependency check:")

    checks = [
        ("gh CLI", ["gh"], "apt install gh / brew install gh"),
        ("Node.js", ["node"], "curl NodeSource setup | bash + apt install nodejs"),
    ]

    for label, binaries, method in checks:
        found = any(shutil.which(b) for b in binaries)
        if found:
            print(f"  ✅ {label}: already installed, skip")
        else:
            print(f"  {label}: would install via: {method}")

def _install_mcporter():
    """Install mcporter and configure Exa search."""
    import shutil
    import subprocess

    print("Setting up mcporter (search backend)...")

    if shutil.which("mcporter"):
        print("  ✅ mcporter already installed")
    else:
        # Check for npm/npx
        if not shutil.which("npm") and not shutil.which("npx"):
            print("  [!]  mcporter requires Node.js. Install Node.js first:")
            print("     https://nodejs.org/ or: curl -fsSL https://fnm.vercel.app/install | bash")
            return
        try:
            subprocess.run(
                ["npm", "install", "-g", "mcporter"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=120,
            )
            if shutil.which("mcporter"):
                print("  ✅ mcporter installed")
            else:
                print("  [X] mcporter install failed. Retry: npm install -g mcporter (check network/timeout), or try: npx mcporter@latest list")
                return
        except Exception as e:
            print(f"  [X] mcporter install failed: {e}")
            return

    # Configure Exa MCP (free, no key needed)
    try:
        r = subprocess.run(
            ["mcporter", "config", "list"], capture_output=True, encoding="utf-8", errors="replace", timeout=5
        )
        if "exa" not in r.stdout:
            subprocess.run(
                ["mcporter", "config", "add", "exa", "https://mcp.exa.ai/mcp"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=10,
            )
            print("  ✅ Exa search configured (free, no API key needed)")
        else:
            print("  ✅ Exa search already configured")
    except Exception:
        print("  [!]  Could not configure Exa. Run manually: mcporter config add exa https://mcp.exa.ai/mcp")

def _install_mcporter_safe():
    """Safe mode: check mcporter status, print instructions."""
    import shutil

    print("Checking mcporter (safe mode)...")

    if shutil.which("mcporter"):
        print("  ✅ mcporter already installed")
        print("  To configure Exa search: mcporter config add exa https://mcp.exa.ai/mcp")
    else:
        print("  -- mcporter not installed")
        print("  To install: npm install -g mcporter")
        print("  Then configure Exa: mcporter config add exa https://mcp.exa.ai/mcp")

def _detect_environment():
    """Auto-detect if running on local computer or server."""
    import os

    # Check common server indicators
    indicators = 0

    # SSH session
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        indicators += 2

    # Docker / container
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        indicators += 2

    # No display (headless)
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        indicators += 1

    # Cloud VM identifiers
    for cloud_file in ["/sys/hypervisor/uuid", "/sys/class/dmi/id/product_name"]:
        if os.path.exists(cloud_file):
            try:
                with open(cloud_file) as f:
                    content = f.read().lower()
                if any(x in content for x in ["amazon", "google", "microsoft", "digitalocean", "linode", "vultr", "hetzner"]):
                    indicators += 2
            except Exception:
                pass

    # systemd-detect-virt
    try:
        import subprocess
        result = subprocess.run(["systemd-detect-virt"], capture_output=True, encoding="utf-8", errors="replace", timeout=3)
        if result.returncode == 0 and result.stdout.strip() != "none":
            indicators += 1
    except Exception:
        pass

    return "server" if indicators >= 2 else "local"

def _cmd_configure(args):
    """Set a config value and test it, or auto-extract from browser."""
    import shutil

    from guanlan.config import Config

    config = Config()

    # ── Auto-extract from browser ──
    if args.from_browser:
        from guanlan.cookie_extract import configure_from_browser

        browser = args.from_browser
        _print_sensitive_access_notice("从浏览器读取平台 Cookie", browser=browser)
        print(f"Extracting cookies from {browser}...")
        print()

        results = configure_from_browser(browser, config)

        found_any = False
        for platform, success, message in results:
            if success:
                print(f"  ✅ {platform}: {message}")
                found_any = True
            else:
                print(f"  -- {platform}: {message}")

        print()
        if found_any:
            print("✅ Cookies configured! Run `guanlan doctor` to see updated status.")
        else:
            print(f"No cookies found. Make sure you're logged into the platforms in {browser}.")
        return

    # ── Manual configure ──
    if not args.key:
        print("Usage: guanlan configure <key> <value>")
        print("   or: guanlan configure --from-browser chrome")
        return

    value = " ".join(args.value) if args.value else ""
    if not value:
        print(f"Missing value for {args.key}")
        return

    if args.key == "proxy":
        config.set("bilibili_proxy", value)
        print("✅ Proxy configured for Bilibili!")
        print("  Note: Reddit 已改为通过 rdt-cli 访问，无需代理。")

    elif args.key == "newsnow-base-url":
        config.set("newsnow_base_url", value.rstrip("/"))
        print("✅ NewsNow BASE_URL configured!")
        print("  Example: guanlan hotnews newsnow:36kr-quick --limit 80")

    elif args.key == "anysearch-key":
        config.set("anysearch_api_key", value)
        print("✅ AnySearch API key configured.")
        print("  Guanlan will use it only when you choose `--backend anysearch` or enable `anysearch-auto`.")

    elif args.key == "anysearch-auto":
        from guanlan.anysearch import ANYSEARCH_AUTO_MODES

        normalized = value.strip().lower()
        if normalized not in ANYSEARCH_AUTO_MODES:
            print("Expected anysearch-auto value: off, fallback, or preferred")
            return
        config.set("anysearch_auto", normalized)
        print(f"✅ AnySearch auto mode set to {normalized}.")
        if normalized == "off":
            print("  Guanlan will not add AnySearch to automatic backend routing.")
        elif normalized == "fallback":
            print("  Guanlan may use AnySearch after default backends when query fit or quality signals justify it.")
        else:
            print("  Guanlan may prioritize AnySearch for English, technical, academic, finance, security, or broad agent-search tasks.")

    elif args.key == "anysearch-anonymous-auto":
        normalized = value.strip().lower()
        if normalized in {"on", "true", "1", "yes"}:
            config.set("anysearch_anonymous_auto", True)
            print("✅ AnySearch anonymous auto mode enabled.")
            print("  Queries may be sent to api.anysearch.com without a user API key when anysearch-auto is enabled.")
        elif normalized in {"off", "false", "0", "no"}:
            config.set("anysearch_anonymous_auto", False)
            print("✅ AnySearch anonymous auto mode disabled.")
        else:
            print("Expected anysearch-anonymous-auto value: on or off")

    elif args.key == "telemetry":
        normalized = value.strip().lower()
        if normalized in {"on", "true", "1", "yes"}:
            config.set("telemetry_enabled", True)
            print("✅ Anonymous telemetry enabled.")
        elif normalized in {"off", "false", "0", "no"}:
            config.set("telemetry_enabled", False)
            print("✅ Anonymous telemetry disabled.")
        else:
            print("Expected telemetry value: on or off")

    elif args.key == "telemetry-endpoint":
        config.set("telemetry_endpoint", value.rstrip("/"))
        print("✅ Telemetry endpoint configured!")
        print("  Guanlan will only send anonymous command/tool lifecycle metadata.")

    elif args.key == "twitter-cookies":
        # Accept two formats:
        # 1. auth_token ct0 (two separate values)
        # 2. Full cookie header string: "auth_token=xxx; ct0=yyy; ..."
        auth_token, ct0 = _parse_twitter_cookie_input(value)

        if auth_token and ct0:
            config.set("twitter_auth_token", auth_token)
            config.set("twitter_ct0", ct0)

            # Sync credentials to twitter-cli env
            print("✅ Twitter cookies configured!")

            print("Testing Twitter access...", end=" ")
            try:
                import subprocess
                twitter_bin = shutil.which("twitter")
                if not twitter_bin:
                    print("[!] twitter-cli not installed. Run: pipx install twitter-cli")
                else:
                    import os
                    env = os.environ.copy()
                    env["TWITTER_AUTH_TOKEN"] = auth_token
                    env["TWITTER_CT0"] = ct0
                    result = subprocess.run(
                        [twitter_bin, "status"],
                        capture_output=True, encoding="utf-8", errors="replace", timeout=15,
                        env=env,
                    )
                    output = (result.stdout or "") + (result.stderr or "")
                    if "ok: true" in output:
                        print("✅ Twitter access works!")
                    else:
                        print("[!] Auth check failed (cookies might be wrong)")
            except Exception as e:
                print(f"[X] Failed: {e}")
        else:
            print("[X] Could not find auth_token and ct0 in your input.")
            print("   Accepted formats:")
            print("   1. guanlan configure twitter-cookies AUTH_TOKEN CT0")
            print('   2. guanlan configure twitter-cookies "auth_token=xxx; ct0=yyy; ..."')

    elif args.key == "youtube-cookies":
        config.set("youtube_cookies_from", value)
        print(f"✅ YouTube cookie source configured: {value}")
        print("   yt-dlp will use cookies from this browser for age-restricted/member videos.")

    elif args.key == "xhs-cookies":
        _configure_xhs_cookies(value)

    elif args.key == "github-token":
        config.set("github_token", value)
        print("✅ GitHub token configured!")

    elif args.key == "groq-key":
        config.set("groq_api_key", value)
        print("✅ Groq key configured!")

def _configure_xhs_cookies(value):
    """Import cookies into xiaohongshu-mcp Docker container.

    Accepts two formats:
    1. Cookie-Editor JSON export (array of cookie objects)
    2. Header String: "name1=value1; name2=value2; ..."

    The xiaohongshu-mcp container stores cookies at $COOKIES_PATH
    (default: /app/data/cookies.json or cookies.json in workdir).
    Format: JSON array of {name, value, domain, path, expires, httpOnly, secure, sameSite}.
    """
    import shutil
    import subprocess

    value = value.strip()
    if not value:
        print("[X] Missing cookie value.")
        print("   Usage: guanlan configure xhs-cookies '<cookie JSON or header string>'")
        return

    # Detect format and parse
    cookies_json = None

    # Try JSON format first (Cookie-Editor JSON export)
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list) and parsed:
                # Validate it looks like cookie objects
                first = parsed[0]
                if isinstance(first, dict) and "name" in first and "value" in first:
                    cookies_json = json.dumps(parsed)
                    print(f"  Parsed {len(parsed)} cookies from JSON format")
                else:
                    print("[X] JSON array doesn't contain cookie objects (need name/value fields)")
                    return
            else:
                print("[X] Empty or invalid JSON array")
                return
        except json.JSONDecodeError as e:
            print(f"[X] Invalid JSON: {e}")
            return

    # Header String format: "key1=val1; key2=val2; ..."
    if cookies_json is None and "=" in value:
        cookies = []
        for part in value.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            name, val = part.split("=", 1)
            name = name.strip()
            val = val.strip()
            if name:
                cookies.append({
                    "name": name,
                    "value": val,
                    "domain": ".xiaohongshu.com",
                    "path": "/",
                    "expires": -1,
                    "size": len(name) + len(val),
                    "httpOnly": False,
                    "secure": False,
                    "session": True,
                    "sameSite": "Lax",
                })
        if cookies:
            cookies_json = json.dumps(cookies)
            print(f"  Parsed {len(cookies)} cookies from Header String format")
        else:
            print("[X] Could not parse any cookies from input")
            return

    if not cookies_json:
        print("[X] Could not parse cookies. Accepted formats:")
        print('   1. JSON array: \'[{"name":"x","value":"y","domain":".xiaohongshu.com",...}]\'')
        print('   2. Header String: "key1=val1; key2=val2; ..."')
        return

    # Find the container
    docker = shutil.which("docker")
    if not docker:
        # No Docker - write to a local file for manual import
        cookie_path = os.path.expanduser("~/.guanlan/xhs-cookies.json")
        with open(cookie_path, "w") as f:
            f.write(cookies_json)
        os.chmod(cookie_path, 0o600)
        print(f"  Cookies saved to {cookie_path}")
        print("  Docker not found. Copy manually:")
        print(f"  docker cp {cookie_path} xiaohongshu-mcp:/app/data/cookies.json")
        return

    # Check if xiaohongshu-mcp container is running
    try:
        result = subprocess.run(
            [docker, "ps", "--filter", "name=xiaohongshu-mcp", "--format", "{{.Names}}"],
            capture_output=True, encoding="utf-8", timeout=5,
        )
        container_name = result.stdout.strip()
        if not container_name:
            print("[X] xiaohongshu-mcp container is not running.")
            print("   Start it first:")
            print("   docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp")
            return
    except Exception as e:
        print(f"[X] Could not check Docker: {e}")
        return

    # Find the cookies path inside the container
    try:
        result = subprocess.run(
            [docker, "exec", container_name, "printenv", "COOKIES_PATH"],
            capture_output=True, encoding="utf-8", timeout=5,
        )
        cookie_path_in_container = result.stdout.strip()
        if not cookie_path_in_container:
            cookie_path_in_container = "/app/cookies.json"  # fallback: absolute path in workdir
    except Exception:
        cookie_path_in_container = "/app/cookies.json"

    # Write cookies into the container
    try:
        # Write to temp file then docker cp
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(cookies_json)
            tmp_path = f.name

        result = subprocess.run(
            [docker, "cp", tmp_path, f"{container_name}:{cookie_path_in_container}"],
            capture_output=True, encoding="utf-8", timeout=10,
        )
        os.unlink(tmp_path)

        if result.returncode != 0:
            print(f"[X] Failed to copy cookies: {result.stderr}")
            return

        print(f"✅ Cookies written to {container_name}:{cookie_path_in_container}")
        # Restart container so it reloads cookies from disk
        print("  Restarting container to reload cookies...", end=" ", flush=True)
        try:
            subprocess.run(
                [docker, "restart", container_name],
                capture_output=True, encoding="utf-8", timeout=30,
            )
            print("done")
        except Exception as e:
            print(f"\n  [!] Could not restart container: {e}")
            print(f"  Restart manually: docker restart {container_name}")
    except Exception as e:
        print(f"[X] Failed to write cookies: {e}")
        return

    # Verify login status via mcporter
    mcporter = shutil.which("mcporter")
    if mcporter:
        print("  Verifying login status...", end=" ")
        try:
            result = subprocess.run(
                [mcporter, "call", "xiaohongshu.check_login_status()"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=15,
            )
            if "已登录" in result.stdout or "logged" in result.stdout.lower():
                print("✅ Login verified!")
            else:
                print("[!] Login check returned unexpected result:")
                print(f"  {result.stdout.strip()[:200]}")
                print("  Cookies were written but login might not be valid. Try fresh cookies.")
        except Exception as e:
            print(f"[!] Could not verify: {e}")
    else:
        print("  (mcporter not found, skipping verification)")

def _cmd_uninstall(args):
    """Remove all 观澜 / Guanlan config, tokens, and skill files."""
    import shutil
    import subprocess

    dry_run = args.dry_run
    keep_config = args.keep_config

    print()
    print("观澜 / Guanlan Uninstaller")
    print("=" * 40)

    if dry_run:
        print("DRY RUN — showing what would be removed (no changes)")
        print()

    removed_any = False

    # ── 1. Config directory (~/.guanlan/) ──
    config_dir = os.path.expanduser("~/.guanlan")
    if not keep_config:
        if os.path.isdir(config_dir):
            if dry_run:
                print(f"[dry-run] Would remove config directory: {config_dir}")
                print("          (contains config.yaml with all tokens/cookies/API keys)")
            else:
                try:
                    shutil.rmtree(config_dir)
                    print(f"  Removed config directory: {config_dir}")
                    removed_any = True
                except Exception as e:
                    print(f"  Could not remove {config_dir}: {e}")
        else:
            print(f"  Config directory not found (already clean): {config_dir}")
    else:
        print(f"  Skipping config directory (--keep-config): {config_dir}")

    # ── 2. Skill files ──
    skill_dirs = [
        ("~/.openclaw/skills/guanlan", "OpenClaw"),
        ("~/.claude/skills/guanlan", "Claude Code"),
        ("~/.agents/skills/guanlan", "Agent"),
    ]

    for skill_path_template, platform_name in skill_dirs:
        skill_path = os.path.expanduser(skill_path_template)
        if os.path.isdir(skill_path):
            if dry_run:
                print(f"[dry-run] Would remove {platform_name} skill: {skill_path}")
            else:
                try:
                    shutil.rmtree(skill_path)
                    print(f"  Removed {platform_name} skill: {skill_path}")
                    removed_any = True
                except Exception as e:
                    print(f"  Could not remove {skill_path}: {e}")

    # ── 3. mcporter MCP entries ──
    if shutil.which("mcporter"):
        for mcp_name in ("exa", "xiaohongshu"):
            try:
                r = subprocess.run(
                    ["mcporter", "list"], capture_output=True, encoding="utf-8", errors="replace", timeout=10
                )
                if mcp_name in r.stdout:
                    if dry_run:
                        print(f"[dry-run] Would remove mcporter entry: {mcp_name}")
                    else:
                        subprocess.run(
                            ["mcporter", "config", "remove", mcp_name],
                            capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                        )
                        print(f"  Removed mcporter entry: {mcp_name}")
                        removed_any = True
            except Exception:
                pass

    # ── 4. Summary and optional steps ──
    print()
    if dry_run:
        print("Dry run complete. No changes were made.")
        print("Run without --dry-run to actually remove the above.")
    else:
        if removed_any:
            print("观澜 / Guanlan data removed.")
        else:
            print("Nothing to remove — already clean.")

    print()
    print("Optional: remove the 观澜 / Guanlan Python package itself:")
    print("  pip uninstall guanlan")
    print()
    print("Optional: remove tools installed by 观澜 / Guanlan:")
    print("  npm uninstall -g mcporter")
    print("  pipx uninstall twitter-cli")
    print("  npm uninstall -g undici")

def _cmd_doctor(args):
    if getattr(args, "install_check", False):
        from guanlan.update_check import format_install_check, run_install_check

        print(format_install_check(run_install_check(__version__, timeout=3.0)))
        return

    from guanlan.config import Config
    from guanlan.doctor import (
        check_all,
        format_config_scan,
        format_report,
        format_trace,
        scan_config,
    )
    from guanlan.profiles import get_profile
    try:
        from rich import print as rprint
    except ImportError:
        rprint = print
    config = Config()
    active_profile = get_profile(config, args.profile or None)
    skip_sensitive = not getattr(args, "auth_check", False)
    if not skip_sensitive:
        _print_sensitive_access_notice("深度检查认证、Cookie 与登录态")
    results = check_all(config, profile=active_profile, skip_sensitive=skip_sensitive)
    rprint(format_report(results, profile=active_profile))
    if getattr(args, "trace", False):
        rprint(format_trace(results, skip_sensitive=skip_sensitive))
    if getattr(args, "check_config", False):
        rprint(format_config_scan(scan_config(config)))
    if skip_sensitive:
        rprint("[dim]提示：已跳过认证/登录态深度探测。使用 `guanlan doctor --auth-check` 可启用深度检查。[/dim]")
    _print_update_notice_if_available(rprint)

def _cmd_profile(args):
    from guanlan.config import Config
    from guanlan.profiles import VALID_PROFILES, get_profile, set_profile

    config = Config()
    if args.action == "show":
        print(get_profile(config))
        return

    if args.action == "set":
        if not args.value:
            print("Profile value required. Choose: " + ", ".join(VALID_PROFILES))
            sys.exit(2)
        if args.value not in VALID_PROFILES:
            print("Unknown profile. Choose: " + ", ".join(VALID_PROFILES))
            sys.exit(2)
        profile = set_profile(config, args.value)
        print(f"Profile set to {profile}")
        return

def _cmd_setup():
    from guanlan.config import Config

    config = Config()
    print()
    print("观澜 / Guanlan Setup")
    print("=" * 40)
    print()

    # Step 1: Exa (via mcporter, no API key required)
    import shutil
    import subprocess

    print("【推荐】全网搜索 — Exa（通过 mcporter）")
    print("  免费，无需 API Key")

    if not shutil.which("mcporter"):
        print("  当前状态: -- mcporter 未安装")
        print("  安装：npm install -g mcporter")
        print("  然后：mcporter config add exa https://mcp.exa.ai/mcp")
        print()
    else:
        try:
            r = subprocess.run(
                ["mcporter", "config", "list"], capture_output=True, encoding="utf-8", errors="replace", timeout=10
            )
            if "exa" in r.stdout.lower():
                print("  当前状态: ✅ 已配置")
            else:
                print("  当前状态: -- 未配置")
                setup_now = input("  现在自动配置 Exa 吗？[Y/n]: ").strip().lower()
                if setup_now in ("", "y", "yes"):
                    add_r = subprocess.run(
                        ["mcporter", "config", "add", "exa", "https://mcp.exa.ai/mcp"],
                        capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                    )
                    if add_r.returncode == 0:
                        print("  ✅ Exa 已配置")
                    else:
                        print("  [!] 自动配置失败，请手动执行：")
                        print("     mcporter config add exa https://mcp.exa.ai/mcp")
        except Exception:
            print("  [!] 无法检查 Exa 配置，请手动执行：")
            print("     mcporter config add exa https://mcp.exa.ai/mcp")
        print()

    # Step 2: GitHub API is optional and must be configured explicitly.
    print("【信息】GitHub API — 基础搜索不需要 Token")
    print("  只有大量使用 GitHub REST API 时才可能需要提额。")
    current = config.get("github_token")
    if current:
        print("  当前状态: ✅ 已配置")
    else:
        print("  当前状态: 未配置（正常，公开搜索/阅读不依赖它）")
        print("  如确实需要：guanlan configure github-token <token>")
    print()

    # Step 3: Reddit — rdt-cli
    print("【信息】Reddit — 通过 rdt-cli 搜索和阅读，无需配置")
    print("  安装：pipx install rdt-cli")
    print()

    # Step 4: Groq is optional and must be configured explicitly.
    print("【信息】Groq API — 仅用于视频无字幕时的语音转文字")
    current = config.get("groq_api_key")
    if current:
        print("  当前状态: ✅ 已配置")
    else:
        print("  当前状态: 未配置（正常，网页搜索/热榜/RSS 不依赖它）")
        print("  如确实需要：guanlan configure groq-key <key>")
    print()

    # Summary
    print("=" * 40)
    print(f"✅ 配置已保存到 {config.config_path}")
    print("运行 guanlan doctor 查看完整状态")
    print()

def _cmd_check_update():
    """Check for newer versions when a public release repo is configured."""
    from guanlan import __version__
    from guanlan.update_check import (
        UpdateInfo,
        format_update_notice,
        get_update_info,
        is_newer_version,
        pypi_version_surfaces,
    )

    print(f"当前版本: v{__version__}")
    pypi_surfaces = pypi_version_surfaces(timeout=3.0)
    pypi_latest = str(pypi_surfaces.get("latest") or "").strip()
    if pypi_latest:
        print(f"PyPI 最新: v{pypi_latest}")
        json_latest = str(pypi_surfaces.get("pypi_json") or "").strip()
        simple_latest = str(pypi_surfaces.get("pypi_simple") or "").strip()
        if json_latest and simple_latest and json_latest != simple_latest:
            print(f"PyPI JSON/simple 暂不一致: json=v{json_latest}, simple=v{simple_latest}；按较高公开版本判断。")

    repo = os.environ.get("GUANLAN_UPDATE_REPO", "").strip()
    if not repo:
        info = UpdateInfo(__version__, pypi_latest) if pypi_latest and is_newer_version(pypi_latest, __version__) else None
        if not info:
            info = get_update_info(__version__, timeout=3.0)
        if info:
            print(format_update_notice(info))
            return "update_available"
        if pypi_latest:
            print("✅ 当前版本不低于 PyPI 公开最新版本。")
        else:
            print("✅ 已是最新版本，或暂时无法访问 PyPI。")
        return "up_to_date"

    release_url = f"https://api.github.com/repos/{repo}/releases/latest"
    commit_url = f"https://api.github.com/repos/{repo}/commits/main"

    # Fetch latest release with retry/backoff.
    resp, err, attempts = _github_get_with_retry(release_url, timeout=10, retries=3)
    if err:
        print(f"[!] 无法检查更新（{_update_error_text(err)}，已重试 {attempts} 次）")
        if pypi_latest and is_newer_version(pypi_latest, __version__):
            print("已改用 PyPI 公开版本面判断。")
            print(format_update_notice(UpdateInfo(__version__, pypi_latest)))
            return "update_available"
        if pypi_latest:
            print("✅ PyPI 显示当前已是最新版本。")
            return "up_to_date"
        return "error"

    if resp.status_code == 200:
        data = resp.json()
        latest = data.get("tag_name", "").lstrip("v")
        body = data.get("body", "")
        if latest:
            print(f"GitHub 最新: v{latest}")
        if latest and pypi_latest and latest != pypi_latest:
            public_latest = latest if is_newer_version(latest, pypi_latest) else pypi_latest
            print(f"[!] GitHub/PyPI 公开版本暂不一致；按较高版本 v{public_latest} 判断。")
            latest = public_latest

        if latest and latest != __version__:
            print(f"最新版本: v{latest} ← 有更新！")
            if body:
                print()
                print("更新内容：")
                # Show first 20 lines of release notes
                for line in body.strip().split("\n")[:20]:
                    print(f"  {line}")
            print()
            print("更新命令:")
            print(f"  pip install --upgrade https://github.com/{repo}/archive/main.zip")
            return "update_available"
        print("✅ 已是最新版本")
        return "up_to_date"

    release_err = _classify_github_response_error(resp)
    if release_err == "rate_limit":
        print("[!] 无法检查更新（GitHub API 速率限制，请稍后重试）")
        if pypi_latest and is_newer_version(pypi_latest, __version__):
            print("已改用 PyPI 公开版本面判断。")
            print(format_update_notice(UpdateInfo(__version__, pypi_latest)))
            return "update_available"
        if pypi_latest:
            print("✅ PyPI 显示当前已是最新版本。")
            return "up_to_date"
        return "error"

    # No releases yet, fall back to latest main commit.
    resp2, err2, attempts2 = _github_get_with_retry(commit_url, timeout=10, retries=2)
    if err2:
        print(f"[!] 无法检查更新（{_update_error_text(err2)}，已重试 {attempts + attempts2} 次）")
        return "error"
    if resp2.status_code == 200:
        commit = resp2.json()
        sha = commit.get("sha", "")[:7]
        msg = commit.get("commit", {}).get("message", "").split("\n")[0]
        date = commit.get("commit", {}).get("committer", {}).get("date", "")[:10]
        print(f"最新提交: {sha} ({date}) {msg}")
        print()
        print("更新命令:")
        print(f"  pip install --upgrade https://github.com/{repo}/archive/main.zip")
        return "unknown"

    commit_err = _classify_github_response_error(resp2)
    if commit_err == "rate_limit":
        print("[!] 无法检查更新（GitHub API 速率限制，请稍后重试）")
        return "error"

    print(f"[!] 无法检查更新（GitHub 返回 {resp2.status_code}）")
    return "error"

def _cmd_health_watch():
    """Quick health check + update check, designed for scheduled tasks.

    Only outputs problems. If everything is fine, outputs a single line.
    """
    from guanlan import __version__
    from guanlan.config import Config
    from guanlan.doctor import check_all

    config = Config()
    issues = []

    # Check channels
    results = check_all(config, skip_sensitive=True)
    ok = sum(1 for r in results.values() if r["status"] == "ok")
    total = len(results)

    # Find broken channels (were working, now broken)
    for key, r in results.items():
        if r["status"] in ("off", "error"):
            issues.append(f"[X] {r['name']}：{r['message']}")
        elif r["status"] == "warn":
            issues.append(f"[!] {r['name']}：{r['message']}")

    # Check for updates only after a public release repo is configured.
    update_available = False
    new_version = ""
    release_body = ""
    update_repo = os.environ.get("GUANLAN_UPDATE_REPO", "").strip()
    if update_repo:
        resp, err, _attempts = _github_get_with_retry(
            f"https://api.github.com/repos/{update_repo}/releases/latest",
            timeout=10,
            retries=2,
        )
        if not err and resp and resp.status_code == 200:
            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            if latest and latest != __version__:
                update_available = True
                new_version = latest
                release_body = data.get("body", "")

    # Output
    if not issues and not update_available:
        print(f"观澜 / Guanlan: 全部正常 ({ok}/{total} 渠道可用，v{__version__})")
        return

    print("观澜 / Guanlan 监控报告")
    print("=" * 40)
    print(f"版本: v{__version__}  |  渠道: {ok}/{total}")

    if issues:
        print()
        for issue in issues:
            print(f"  {issue}")

    if update_available:
        print()
        print(f"新版本可用: v{new_version}")
        if release_body:
            for line in release_body.strip().split("\n")[:10]:
                print(f"    {line}")
        print(f"  更新: pip install --upgrade https://github.com/{update_repo}/archive/main.zip")

def _cmd_status():
    """Show health, stability metadata, and local cache summary."""
    from guanlan.archive import archive_stats
    from guanlan.config import Config
    from guanlan.doctor import check_all
    from guanlan.telemetry import telemetry_status
    from guanlan.web.search import cache_summary

    config = Config()
    results = check_all(config, skip_sensitive=True)
    ok = sum(1 for r in results.values() if r["status"] == "ok")
    total = len(results)
    stability_counts: dict[str, int] = {}
    readiness_counts: dict[str, int] = {}
    for item in results.values():
        stability_key = str(item.get("stability", "best-effort"))
        readiness_key = str(item.get("readiness", "unknown"))
        stability_counts[stability_key] = stability_counts.get(stability_key, 0) + 1
        readiness_counts[readiness_key] = readiness_counts.get(readiness_key, 0) + 1

    print("观澜 / Guanlan 状态面板")
    print("=" * 40)
    print(f"渠道健康: {ok}/{total}")
    print(
        "就绪状态: "
        + "，".join(f"{key}={value}" for key, value in sorted(readiness_counts.items()))
    )
    print(
        "稳定性: "
        + "，".join(f"{key}={value}" for key, value in sorted(stability_counts.items()))
    )
    print()
    print("渠道 | 运行 | 就绪 | 验证 | 稳定性 | 风险 | 授权 | 批量")
    print("--- | --- | --- | --- | --- | --- | --- | ---")
    for name, item in results.items():
        print(
            f"{name} | {item.get('status')} | {item.get('readiness')} | "
            f"{item.get('verification')} | {item.get('stability')} | "
            f"{item.get('risk_level')} | {item.get('auth')} | {item.get('batch')}"
        )

    cache = cache_summary()
    print()
    print("本地缓存")
    print(f"路径: {cache['path']}")
    if not cache["exists"]:
        print("状态: 尚未创建")
    else:
        print(f"文件数: {cache['total_files']}")
        for kind, count in cache.get("kinds", {}).items():
            print(f"- {kind}: {count}")

    archive = archive_stats()
    print()
    print("本地知识库")
    print(f"路径: {archive['path']}")
    print(f"文档数: {archive['documents']}")

    telemetry = telemetry_status(config)
    print()
    print("匿名遥测")
    print(f"状态: {'启用' if telemetry['enabled'] else '未启用'}")
    if telemetry["configured"]:
        print(f"端点: {telemetry['endpoint']}")
    else:
        print("端点: 未配置")

__all__ = ['_cmd_welcome', '_cmd_capabilities', '_cmd_stock', '_cmd_install', '_install_skill', '_uninstall_skill', '_cmd_skill', '_cmd_format', '_cmd_archive', '_cmd_mcp', '_cmd_serve', '_cmd_plugin', '_cmd_eval', '_cmd_quality', '_cmd_report', '_install_system_deps', '_install_xiaoyuzhou_deps', '_install_twitter_deps', '_install_browser_use_deps', '_install_opencli_deps', '_install_openguanlan_deps', '_install_xhs_deps', '_install_zsxq_deps', '_install_reddit_deps', '_install_bili_deps', '_install_weibo_deps', '_install_wechat_deps', '_install_system_deps_safe', '_install_system_deps_dryrun', '_install_mcporter', '_install_mcporter_safe', '_detect_environment', '_cmd_configure', '_configure_xhs_cookies', '_cmd_uninstall', '_cmd_doctor', '_cmd_profile', '_cmd_setup', '_cmd_check_update', '_cmd_health_watch', '_cmd_status']
