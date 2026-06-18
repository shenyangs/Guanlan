# -*- coding: utf-8 -*-
"""
观澜 / Guanlan CLI — installer, doctor, and configuration tool.

Usage:
    guanlan install --env=auto
    guanlan doctor
    guanlan configure twitter-cookies "auth_token=xxx; ct0=yyy"
    guanlan setup
"""

import argparse
import os
import sys

from guanlan import __version__
from guanlan.commands import _ops_helpers as _ops_helpers_module
from guanlan.commands import admin as _admin_module
from guanlan.commands.admin import (
    _cmd_archive,
    _cmd_capabilities,
    _cmd_configure,
    _cmd_doctor,
    _cmd_eval,
    _cmd_format,
    _cmd_health_watch,
    _cmd_install,
    _cmd_mcp,
    _cmd_plugin,
    _cmd_profile,
    _cmd_quality,
    _cmd_report,
    _cmd_serve,
    _cmd_setup,
    _cmd_skill,
    _cmd_status,
    _cmd_stock,
    _cmd_uninstall,
    _cmd_welcome,
)
from guanlan.commands.admin import (
    _cmd_check_update as _admin_cmd_check_update,
)
from guanlan.commands.daily import _cmd_daily
from guanlan.commands.feeds import _cmd_feeds, _cmd_pulse
from guanlan.commands.hotnews import _cmd_hotnews
from guanlan.commands.read import (
    _cmd_browser_assist,
    _cmd_diagnose,
    _cmd_read,
    _cmd_wechat_exporter,
)
from guanlan.commands.research import (
    _cmd_compare,
    _cmd_dossier,
    _cmd_feedback,
    _cmd_investigate,
    _cmd_prompt,
    _cmd_recipe,
    _cmd_research,
    _cmd_sources,
    _cmd_timeline,
    _cmd_yinshen,
)
from guanlan.commands.search import _cmd_agent, _cmd_route, _cmd_search, _cmd_workflow
from guanlan.commands.watch import _cmd_watch_intents
from guanlan.limits import (
    DEFAULT_ARCHIVE_LIST_LIMIT,
    DEFAULT_ARCHIVE_SEARCH_LIMIT,
    DEFAULT_FEEDS_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_PULSE_LIMIT,
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
)
from guanlan.profiles import VALID_PROFILES

_classify_github_response_error = _ops_helpers_module._classify_github_response_error
_github_get_with_retry = _admin_module._github_get_with_retry
_install_skill = _admin_module._install_skill
_install_xiaoyuzhou_deps = _admin_module._install_xiaoyuzhou_deps
_parse_twitter_cookie_input = _ops_helpers_module._parse_twitter_cookie_input
_print_background_update_notice_if_available = _ops_helpers_module._print_background_update_notice_if_available
_print_sensitive_access_notice = _ops_helpers_module._print_sensitive_access_notice
_print_update_notice_if_available = _admin_module._print_update_notice_if_available
_uninstall_skill = _admin_module._uninstall_skill


def _cmd_check_update():
    """Compatibility wrapper that preserves monkeypatch hooks on cli helpers."""
    _admin_module._github_get_with_retry = _github_get_with_retry
    return _admin_cmd_check_update()


def _ensure_utf8_console():
    """Best-effort Windows console UTF-8 setup for CLI runtime only."""
    if sys.platform != "win32":
        return
    # Avoid interfering with pytest/captured streams.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        import io
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        # Do not crash CLI just because encoding patch failed.
        pass


def _configure_logging(verbose: bool = False):
    """Suppress loguru output unless --verbose is set."""
    from loguru import logger
    logger.remove()  # Remove default stderr handler
    if verbose:
        logger.add(sys.stderr, level="INFO")


def main():
    _ensure_utf8_console()

    parser = argparse.ArgumentParser(
        prog="guanlan",
        description="Give your AI Agent eyes to see the entire internet",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs")
    parser.add_argument("--version", action="version", version=f"观澜 / Guanlan v{__version__}")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ── setup ──
    sub.add_parser("setup", help="Interactive configuration wizard")

    # ── welcome ──
    sub.add_parser("welcome", help="Show a short first-run guide for using Guanlan with agents")

    # ── capabilities ──
    p_capabilities = sub.add_parser(
        "capabilities",
        help="Show what Guanlan can do and which command/tool to use",
    )
    p_capabilities.add_argument("--json", action="store_true", help="Print capability map as JSON")

    # ── install ──
    p_install = sub.add_parser("install", help="One-shot installer with flags")
    p_install.add_argument("--env", choices=["local", "server", "auto"], default="auto",
                           help="Environment: local, server, or auto-detect")
    p_install.add_argument("--proxy", default="",
                           help="Residential proxy for Reddit/Bilibili (http://user:pass@ip:port)")
    p_install.add_argument("--safe", action="store_true",
                           help="Safe mode: skip automatic system changes, show what's needed instead")
    p_install.add_argument("--dry-run", action="store_true",
                           help="Show what would be done without making any changes")
    p_install.add_argument("--profile", choices=VALID_PROFILES, default="",
                           help="Region profile: global, china, english, or hybrid")
    p_install.add_argument("--channels", default="",
                           help="Comma-separated optional channels to install "
                                "(twitter,weibo,wechat,xiaoyuzhou,xueqiu,xiaohongshu,"
                                "reddit,bilibili,browseruse,douyin,linkedin,all)")

    # ── configure ──
    p_conf = sub.add_parser("configure", help="Set a config value or auto-extract from browser")
    p_conf.add_argument("key", nargs="?", default=None,
                        choices=["proxy", "github-token", "groq-key",
                                 "twitter-cookies", "youtube-cookies",
                                 "xhs-cookies", "newsnow-base-url",
                                 "telemetry", "telemetry-endpoint"],
                        help="What to configure (omit if using --from-browser)")
    p_conf.add_argument("value", nargs="*", help="The value(s) to set")
    p_conf.add_argument("--from-browser", metavar="BROWSER",
                        choices=["chrome", "firefox", "edge", "brave", "opera"],
                        help="Auto-extract ALL platform cookies from browser (chrome/firefox/edge/brave/opera)")

    # ── doctor ──
    p_doctor = sub.add_parser("doctor", help="Check platform availability")
    p_doctor.add_argument("--profile", choices=VALID_PROFILES, default="",
                          help="Region profile: global, china, english, or hybrid")
    p_doctor.add_argument(
        "--auth-check",
        action="store_true",
        help="Enable deep auth/cookie probes (may trigger Keychain prompts)",
    )
    p_doctor.add_argument(
        "--trace",
        action="store_true",
        help="Show diagnostic trace, including whether sensitive probes were skipped",
    )
    p_doctor.add_argument(
        "--check-config",
        action="store_true",
        help="Scan ~/.guanlan/config.yaml for plaintext cookies, tokens, keys, or proxy credentials",
    )
    p_doctor.add_argument(
        "--install-check",
        action="store_true",
        help="Check active Guanlan command path, version drift, and duplicate installs",
    )

    # ── profile ──
    p_profile = sub.add_parser("profile", help="Show or set the region profile")
    p_profile.add_argument("action", choices=["show", "set"], help="Profile action")
    p_profile.add_argument("value", nargs="?", help="Profile value: global, china, english, or hybrid")

    # ── uninstall ──
    p_uninstall = sub.add_parser("uninstall", help="Remove all 观澜 / Guanlan config, tokens, and skill files")
    p_uninstall.add_argument("--dry-run", action="store_true",
                             help="Show what would be removed without making any changes")
    p_uninstall.add_argument("--keep-config", action="store_true",
                             help="Remove skill files only, keep ~/.guanlan/ config and tokens")

    # ── skill ──
    p_skill = sub.add_parser("skill", help="Manage agent skill registration")
    p_skill_group = p_skill.add_mutually_exclusive_group(required=True)
    p_skill_group.add_argument("--install", action="store_true",
                               help="Install SKILL.md to agent skill directories")
    p_skill_group.add_argument("--uninstall", action="store_true",
                               help="Remove SKILL.md from agent skill directories")

    # ── format ──
    p_format = sub.add_parser("format", help="Clean and format platform API output")
    p_format.add_argument("platform", choices=["xhs", "hotnews"],
                          help="Platform to format (xhs, hotnews)")

    # ── hotnews ──
    p_hotnews = sub.add_parser("hotnews", help="Fetch Chinese hotnews from native sources")
    p_hotnews.add_argument("source", nargs="?", default="today",
                           help="Source id: today, snapshot, baidu, weibo, bilibili-hot-search, bilibili, ithome, sspai, xinzhiyuan, youtube-ai-rss, zeli-hn, buzzing, zhihu, v2ex, ebrun:<channel>, newsnow:<id>, vvhan:<id>, uapis:<id>, tophub:<id>, hotboard:<id>, or list")
    p_hotnews.add_argument("snapshot_source", nargs="?",
                           help="Source id when using `guanlan hotnews snapshot <source>`")
    p_hotnews.add_argument("--backend", default="auto",
                           help="Hotnews backend; auto uses native first, unknown sources as NewsNow. External providers are optional and cache-backed")
    p_hotnews.add_argument("--newsnow-base-url", default="",
                           help="Override NewsNow BASE_URL, e.g. https://newsnow.example.com")
    p_hotnews.add_argument("--limit", type=int, default=DEFAULT_HOTNEWS_LIMIT,
                           help="Maximum number of items to fetch")
    p_hotnews.add_argument("--json", action="store_true",
                           help="Print normalized JSON instead of Markdown")
    p_hotnews.add_argument("--trends", action="store_true",
                           help="For multi-source hotnews, append cross-source trend clusters")
    p_hotnews.add_argument("--brief", action="store_true",
                           help="Append a compact daily trend brief with follow-up queries")
    p_hotnews.add_argument("--watch", action="store_true",
                           help="Compare with the latest explicit local snapshot and save this run")
    p_hotnews.add_argument("--snapshot-db", default="",
                           help="Optional local JSONL path for explicit hotnews snapshots")

    # ── route ──
    p_route = sub.add_parser("route", help="Explain Guanlan's source and demand routing plan")
    p_route.add_argument("query", nargs="?", default="", help="Query or research need to route")
    p_route.add_argument("--preset", default="general",
                         help="Optional research preset context")
    p_route.add_argument("--site", default="", help="User-requested site, if any")
    p_route.add_argument("--sites", default="", help="Comma-separated user-requested sites")
    p_route.add_argument("--scope", default="", help="User-requested scope, if any")
    p_route.add_argument("--profile", choices=VALID_PROFILES, default="china",
                         help="Region profile")
    p_route.add_argument("--limit", type=int, default=DEFAULT_RESEARCH_LIMIT,
                         help="Candidate pool size to plan for")
    p_route.add_argument("--read-top", type=int, default=None,
                         help="Optional read count to plan for")
    p_route.add_argument("--json", action="store_true",
                         help="Print route plan JSON instead of Markdown")

    # ── workflow ──
    p_workflow = sub.add_parser("workflow", help="Decide whether a query needs light search or a heavier research workflow")
    p_workflow.add_argument("query", nargs="?", default="", help="Query or research need to classify")
    p_workflow.add_argument("--command", dest="workflow_command_context", default="search",
                            choices=["search", "read", "route", "research", "compare", "timeline", "dossier", "investigate"],
                            help="Current intended command, used to avoid over-planning basic search")
    p_workflow.add_argument("--preset", default="general", help="Optional research preset context")
    p_workflow.add_argument("--site", default="", help="User-requested site, if any")
    p_workflow.add_argument("--sites", default="", help="Comma-separated user-requested sites")
    p_workflow.add_argument("--scope", default="", help="User-requested scope, if any")
    p_workflow.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_workflow.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT, help="Candidate pool size to plan for")
    p_workflow.add_argument("--read-top", type=int, default=None, help="Optional read count to plan for")
    p_workflow.add_argument("--json", action="store_true", help="Print workflow decision JSON instead of Markdown")

    # ── agent ──
    p_agent = sub.add_parser("agent", help="Auto-plan the smallest safe Guanlan command chain for agents")
    p_agent.add_argument("query", nargs="?", default="", help="User need to turn into an agent command plan")
    p_agent.add_argument("--phase", choices=["plan", "review"], default="plan",
                         help="plan returns a decision card; review inspects a Guanlan observation and returns next_decision")
    p_agent.add_argument("--observation-json", default="",
                         help="JSON string or file path with a Guanlan result/error summary for --phase review")
    p_agent.add_argument("--mode", choices=["auto", "quick", "deep", "fresh"], default="auto",
                         help="Planning bias: auto keeps defaults, quick stays light, deep investigates, fresh adds hot signals")
    p_agent.add_argument("--preset", default="general", help="Optional research preset context")
    p_agent.add_argument("--site", default="", help="User-requested site, if any")
    p_agent.add_argument("--sites", default="", help="Comma-separated user-requested sites")
    p_agent.add_argument("--scope", default="", help="User-requested scope, if any")
    p_agent.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_agent.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT, help="Candidate pool size to plan for")
    p_agent.add_argument("--read-top", type=int, default=None, help="Optional read count to plan for")
    p_agent.add_argument("--max-commands", type=int, default=5, help="Maximum commands to include in the shortlist")
    p_agent.add_argument("--json", action="store_true", help="Print agent plan JSON instead of Markdown")

    # ── diagnose ──
    p_diagnose = sub.add_parser("diagnose", help="Diagnose why a URL is readable, weak, blocked, or only a fallback")
    diagnose_sub = p_diagnose.add_subparsers(dest="diagnose_command", help="Diagnosis commands")
    p_diagnose_page = diagnose_sub.add_parser("page", help="Diagnose one public page for evidence usability")
    p_diagnose_page.add_argument("url", nargs="?", default="", help="URL to diagnose")
    p_diagnose_page.add_argument("--backend", choices=["auto", "jina", "direct"], default="auto", help="Read backend")
    p_diagnose_page.add_argument("--max-chars", type=int, default=4000, help="Maximum chars to inspect")
    p_diagnose_page.add_argument("--fallback-search", action="store_true", default=True, help="Allow search context fallback")
    p_diagnose_page.add_argument("--no-fallback-search", action="store_false", dest="fallback_search", help="Disable search fallback")
    p_diagnose_page.add_argument("--fallback-limit", type=int, default=5, help="Search fallback result count")
    p_diagnose_page.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_diagnose_page.add_argument("--strict", action="store_true", help="Use stricter read-quality gate")
    p_diagnose_page.add_argument("--json", action="store_true", help="Print diagnosis JSON")

    # ── browser-assist ──
    p_browser_assist = sub.add_parser(
        "browser-assist",
        help="Plan user-authorized visible-browser evidence handoff without reading browser state",
    )
    browser_assist_sub = p_browser_assist.add_subparsers(dest="browser_assist_command", help="Browser assist commands")
    p_browser_assist_adapters = browser_assist_sub.add_parser("adapters", help="List browser-assist adapters")
    p_browser_assist_adapters.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_browser_assist_adapters.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_browser_assist_adapters.add_argument("--check", action="store_true", help="Run read-only adapter readiness checks")
    p_browser_assist_adapters.add_argument("--platform", default="", help="Optional platform label for adapter compatibility checks")
    p_browser_assist_adapters.add_argument("--dry-run-url", default="https://example.com/article", help="Example URL used to validate dry-run command construction")
    p_browser_assist_setup_opencli = browser_assist_sub.add_parser("setup-opencli", help="Plan or explicitly install OpenCLI browser bridge CLI")
    p_browser_assist_setup_opencli.add_argument("--execute", action="store_true", help="Install OpenCLI CLI with npm; browser extension remains a manual user step")
    p_browser_assist_setup_opencli.add_argument("--timeout", type=int, default=180, help="Install timeout seconds when --execute is used")
    p_browser_assist_setup_opencli.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_browser_assist_setup_opencli.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_browser_assist_setup_openguanlan = browser_assist_sub.add_parser("setup-openguanlan", help="Show the OpenGuanlan browser-assist layer and optional bridge plan")
    p_browser_assist_setup_openguanlan.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_browser_assist_setup_openguanlan.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_browser_assist_sessions = browser_assist_sub.add_parser("sessions", help="Describe the OpenGuanlan visible-page session contract")
    p_browser_assist_sessions.add_argument("url", nargs="?", default="", help="Target page URL")
    p_browser_assist_sessions.add_argument("--platform", default="", help="Optional platform label override")
    p_browser_assist_sessions.add_argument("--min-visible-items", type=int, default=0, help="Minimum visible list/comment/search items the host Agent should try to collect")
    p_browser_assist_sessions.add_argument("--task-goal", default="", help="Optional host-agent task goal")
    p_browser_assist_sessions.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_browser_assist_sessions.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_browser_assist_plan = browser_assist_sub.add_parser("plan", help="Build an OpenGuanlan visible evidence task")
    p_browser_assist_plan.add_argument("url", help="Target page URL")
    p_browser_assist_plan.add_argument("--page-type", default="access_gate", help="Diagnosis page type hint")
    p_browser_assist_plan.add_argument("--signal", action="append", default=[], help="Diagnosis signal hint; can be repeated")
    p_browser_assist_plan.add_argument("--platform", default="", help="Optional platform label override")
    p_browser_assist_plan.add_argument("--max-pages", type=int, default=3, help="Maximum browser-visible target pages in the host-agent task")
    p_browser_assist_plan.add_argument("--max-chars-per-page", type=int, default=3000, help="Maximum visible characters per page for the host-agent task")
    p_browser_assist_plan.add_argument("--min-visible-items", type=int, default=0, help="Minimum visible list/comment/search items to collect before marking partial")
    p_browser_assist_plan.add_argument("--task-goal", default="", help="Optional host-agent task goal")
    p_browser_assist_plan.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_browser_assist_plan.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_browser_assist_run = browser_assist_sub.add_parser("run", help="Bridge a browser-assist task to openguanlan/host-browser/open-cli/browser-use/xhs-cli adapters")
    p_browser_assist_run.add_argument("url", help="Target page URL")
    p_browser_assist_run.add_argument("--adapter", default="openguanlan", help="Adapter: openguanlan, host-browser, openguanlan-bridge, open-cli, browser-use, xhs-cli")
    p_browser_assist_run.add_argument("--execute", action="store_true", help="Execute external/optional bridge adapter when safe/configured; openguanlan returns a host-browser task")
    p_browser_assist_run.add_argument("--command-template", default="", help="External CLI command template; supports {url} and {output}")
    p_browser_assist_run.add_argument("--output", default="", help="Optional JSONL output path for parsed adapter payloads")
    p_browser_assist_run.add_argument("--timeout", type=int, default=90, help="External adapter timeout seconds")
    p_browser_assist_run.add_argument("--page-type", default="access_gate", help="Diagnosis page type hint")
    p_browser_assist_run.add_argument("--signal", action="append", default=[], help="Diagnosis signal hint; can be repeated")
    p_browser_assist_run.add_argument("--platform", default="", help="Optional platform label override")
    p_browser_assist_run.add_argument("--max-pages", type=int, default=3, help="Maximum browser-visible target pages")
    p_browser_assist_run.add_argument("--max-chars-per-page", type=int, default=3000, help="Maximum visible characters per page")
    p_browser_assist_run.add_argument("--min-visible-items", type=int, default=0, help="Minimum visible list/comment/search items to collect before marking partial")
    p_browser_assist_run.add_argument("--task-goal", default="", help="Optional host-agent task goal")
    p_browser_assist_run.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_browser_assist_run.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")

    # ── wechat-exporter ──
    p_wechat_exporter = sub.add_parser(
        "wechat-exporter",
        help="Use an optional user-configured WeChat article exporter service",
    )
    wechat_exporter_sub = p_wechat_exporter.add_subparsers(dest="wechat_exporter_command", help="WeChat exporter commands")
    p_wechat_exporter_status = wechat_exporter_sub.add_parser("status", help="Show exporter configuration and safety boundary")
    p_wechat_exporter_status.add_argument("--base-url", default="", help="Exporter base URL; otherwise read GUANLAN_WECHAT_EXPORTER_BASE_URL")
    p_wechat_exporter_status.add_argument("--auth-env", default="GUANLAN_WECHAT_EXPORTER_AUTH_KEY", help="Environment variable holding X-Auth-Key")
    p_wechat_exporter_status.add_argument("--probe", action="store_true", help="Probe /api/public/v1/authkey without printing credentials")
    p_wechat_exporter_status.add_argument("--json", action="store_true", help="Print JSON")
    p_wechat_exporter_download = wechat_exporter_sub.add_parser("download", help="Download one public WeChat article through the configured exporter")
    p_wechat_exporter_download.add_argument("url", nargs="?", default="", help="mp.weixin.qq.com article URL")
    p_wechat_exporter_download.add_argument("--format", choices=["html", "markdown", "text", "json"], default="markdown", help="Exporter output format")
    p_wechat_exporter_download.add_argument("--base-url", default="", help="Exporter base URL; otherwise read GUANLAN_WECHAT_EXPORTER_BASE_URL")
    p_wechat_exporter_download.add_argument("--auth-env", default="GUANLAN_WECHAT_EXPORTER_AUTH_KEY", help="Optional environment variable holding X-Auth-Key")
    p_wechat_exporter_download.add_argument("--json", action="store_true", help="Wrap output as JSON")
    p_wechat_exporter_accounts = wechat_exporter_sub.add_parser("account-search", aliases=["accounts"], help="Search official accounts using an authorized exporter")
    p_wechat_exporter_accounts.add_argument("keyword", nargs="?", default="", help="Official account keyword")
    p_wechat_exporter_accounts.add_argument("--begin", type=int, default=0, help="Start offset")
    p_wechat_exporter_accounts.add_argument("--size", type=int, default=20, help="Page size, max 20")
    p_wechat_exporter_accounts.add_argument("--base-url", default="", help="Exporter base URL; otherwise read GUANLAN_WECHAT_EXPORTER_BASE_URL")
    p_wechat_exporter_accounts.add_argument("--auth-env", default="GUANLAN_WECHAT_EXPORTER_AUTH_KEY", help="Environment variable holding X-Auth-Key")
    p_wechat_exporter_accounts.add_argument("--json", action="store_true", help="Print JSON")
    p_wechat_exporter_articles = wechat_exporter_sub.add_parser("articles", help="List articles for one official account fakeid using an authorized exporter")
    p_wechat_exporter_articles.add_argument("fakeid", nargs="?", default="", help="Official account fakeid")
    p_wechat_exporter_articles.add_argument("--keyword", default="", help="Optional article title keyword")
    p_wechat_exporter_articles.add_argument("--begin", type=int, default=0, help="Start offset")
    p_wechat_exporter_articles.add_argument("--size", type=int, default=20, help="Page size, max 20")
    p_wechat_exporter_articles.add_argument("--base-url", default="", help="Exporter base URL; otherwise read GUANLAN_WECHAT_EXPORTER_BASE_URL")
    p_wechat_exporter_articles.add_argument("--auth-env", default="GUANLAN_WECHAT_EXPORTER_AUTH_KEY", help="Environment variable holding X-Auth-Key")
    p_wechat_exporter_articles.add_argument("--json", action="store_true", help="Print JSON")
    p_wechat_exporter_account_by_url = wechat_exporter_sub.add_parser("account-by-url", help="Resolve an official account from an article URL using an authorized exporter")
    p_wechat_exporter_account_by_url.add_argument("url", nargs="?", default="", help="mp.weixin.qq.com article URL")
    p_wechat_exporter_account_by_url.add_argument("--base-url", default="", help="Exporter base URL; otherwise read GUANLAN_WECHAT_EXPORTER_BASE_URL")
    p_wechat_exporter_account_by_url.add_argument("--auth-env", default="GUANLAN_WECHAT_EXPORTER_AUTH_KEY", help="Environment variable holding X-Auth-Key")
    p_wechat_exporter_account_by_url.add_argument("--json", action="store_true", help="Print JSON")

    # ── search ──
    p_search = sub.add_parser("search", help="Search the web for agent-ready results")
    p_search.add_argument("query", nargs="?", default="", help="Search query")
    p_search.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT,
                          help="Maximum number of search results")
    p_search.add_argument("--site", default="",
                          help="Restrict search to a domain, e.g. zhihu.com")
    p_search.add_argument("--scope", default="",
                          help="Curated China source scope, e.g. party_central, local_official, ecommerce, wps_office")
    p_search.add_argument("--strict-scope", action="store_true",
                          help="Keep --scope narrow; skip automatic open-web mixing")
    p_search.add_argument("--list-scopes", action="store_true",
                          help="List curated search scopes and exit")
    p_search.add_argument("--backend", default="auto",
                          help="Search backend: auto, duckduckgo, bing, baidu, anysearch, wechat-sogou, or plugin:name")
    p_search.add_argument("--profile", choices=VALID_PROFILES, default="",
                          help="Region profile: global, china, english, or hybrid")
    p_search.add_argument("--network", choices=["auto", "current", "direct", "proxy"], default="auto",
                          help="Network path for search backends: auto, current env, direct, or proxy")
    p_search.add_argument("--format", choices=["markdown", "json", "context", "prompt"], default="markdown",
                          help="Output format")
    p_search.add_argument("--json", action="store_true",
                          help="Print normalized JSON instead of Markdown")
    p_search.add_argument("--trace", action="store_true",
                          help="Show score factors, cache status, backend order, and clustering trace")
    p_search.add_argument("--evidence-mode", choices=["off", "shadow", "assist"], default="shadow",
                          help="Evidence Mixer mode: off disables it, shadow keeps diagnostics, assist surfaces first-read guidance")
    p_search.add_argument("--source-chart", action="store_true",
                          help="Append an ASCII source/domain distribution chart")
    p_search.add_argument("--cluster-threshold", choices=["conservative", "balanced", "loose"],
                          default="conservative", help="Topic clustering strictness")
    p_search.add_argument("--cache-ttl", type=int, default=0,
                          help="Reuse identical search results for this many seconds")
    p_search.add_argument("--no-cache", action="store_true",
                          help="Bypass local cache even when --cache-ttl is set")

    # ── feedback ──
    from guanlan.stock_cli import add_stock_parser

    add_stock_parser(sub)

    # ── feedback ──
    p_feedback = sub.add_parser("feedback", help=argparse.SUPPRESS)
    p_feedback.add_argument("query", nargs="?", default="", help="Search query that felt unsatisfactory")
    p_feedback.add_argument("--reason", default="", help="Why results were unsatisfactory")
    p_feedback.add_argument("--command", dest="feedback_command", default="search",
                            choices=["search", "research", "read", "pulse", "hotnews", "other"],
                            help="Which command the feedback belongs to")
    p_feedback.add_argument("--profile", choices=VALID_PROFILES, default="",
                            help="Optional active profile to include")
    p_feedback.add_argument("--backend", default="",
                            help="Optional backend name to include, e.g. auto/duckduckgo/baidu")
    p_feedback.add_argument("--json", action="store_true",
                            help="Print feedback submit result as JSON")

    # ── research ──
    p_research = sub.add_parser("research", help="Build an agent-ready research evidence packet")
    p_research.add_argument("query", nargs="?", default="", help="Research query")
    p_research.add_argument("--preset", default="general",
                            help="Research preset: general, policy, official, industry, ecommerce, reputation, entertainment, global_entertainment, jp_kr_entertainment, cybersecurity, sports, weather_disaster, science, career, podcast, test_prep, tech, wps_office, academic, finance, local, company, global_policy, global_reputation, global_industry")
    p_research.add_argument("--list-presets", action="store_true",
                            help="List research presets and exit")
    p_research.add_argument("--limit", type=int, default=None,
                            help="Maximum number of search results; defaults to preset value")
    p_research.add_argument("--site", default="",
                            help="Restrict search to a domain, e.g. zhihu.com")
    p_research.add_argument("--sites", default="",
                            help="Comma-separated domains for site-directed research, e.g. zhihu.com,weibo.com")
    p_research.add_argument("--scope", default="",
                            help="Curated China source scope, e.g. party_central, local_official, ecommerce, wps_office")
    p_research.add_argument("--search-backend", default="auto",
                            help="Search backend: auto, duckduckgo, bing, baidu, anysearch, wechat-sogou, or plugin:name")
    p_research.add_argument("--read-backend", choices=["auto", "jina", "direct"],
                            default="auto", help="Read backend for selected evidence")
    p_research.add_argument("--read-top", type=int, default=None,
                            help="How many representative results to read; use 0 for search-only; defaults to preset value")
    p_research.add_argument("--max-read-chars", type=int, default=None,
                            help="Maximum characters per read excerpt; defaults to preset value")
    p_research.add_argument("--profile", choices=VALID_PROFILES, default="",
                            help="Region profile: global, china, english, or hybrid; defaults to preset value")
    p_research.add_argument("--format", choices=["markdown", "json", "context", "prompt"], default="markdown",
                            help="Output format")
    p_research.add_argument("--json", action="store_true",
                            help="Print normalized JSON instead of Markdown")
    p_research.add_argument("--source-chart", action="store_true",
                            help="Append an ASCII source/domain distribution chart")
    p_research.add_argument("--route-chart", action="store_true",
                            help="Append an ASCII route/intent/evidence diagnostic chart")
    p_research.add_argument("--advisor", action="store_true",
                            help="Append a cautious assistant view with intent hypotheses and next steps")
    p_research.add_argument("--advisor-style", choices=["brief", "decision", "risk", "strategy"], default="brief",
                            help="Advisor guidance style when --advisor is enabled")
    p_research.add_argument("--prompt-style", choices=["concise", "deep", "evidence", "decision"], default="deep",
                            help="Prompt style when --format prompt is used")
    p_research.add_argument("--select-top", type=int, default=None,
                            help="How many representative evidence items to highlight from the broad pool")
    p_research.add_argument("--max-search-jobs", type=int, default=None,
                            help="Cap research sub-search jobs for guarded/scout runs; unset keeps full preset routing")

    # ── investigate ──
    p_investigate = sub.add_parser("investigate", help="Run an explicit upper-layer investigation workflow")
    p_investigate.add_argument("query", nargs="?", default="", help="Investigation query")
    p_investigate.add_argument("--preset", default="general", help="Research preset")
    p_investigate.add_argument("--profile", choices=VALID_PROFILES, default="", help="Region profile")
    p_investigate.add_argument("--limit", type=int, default=None, help="Broad candidate pool")
    p_investigate.add_argument("--read-top", type=int, default=None, help="Representative URLs to read")
    p_investigate.add_argument("--budget", choices=["light", "standard", "deep"], default="standard",
                               help="Investigation budget: light=route+research, standard=add scoped/read, deep=more sidecar views")
    p_investigate.add_argument("--dry-run", action="store_true", help="Explain planned steps without search/read network calls")
    p_investigate.add_argument("--search-backend", default="auto", help="Search backend")
    p_investigate.add_argument("--read-backend", choices=["auto", "jina", "direct"], default="auto", help="Read backend")
    p_investigate.add_argument("--max-read-chars", type=int, default=None, help="Maximum characters per read excerpt")
    p_investigate.add_argument("--advisor", action="store_true", help="Append advisor rules; default is enabled for investigate")
    p_investigate.add_argument("--no-advisor", action="store_true", help="Disable advisor rules")
    p_investigate.add_argument("--advisor-style", choices=["brief", "decision", "risk", "strategy"], default="strategy")
    p_investigate.add_argument("--select-top", type=int, default=None, help="Representative evidence items")
    p_investigate.add_argument("--format", choices=["markdown", "json", "context"], default="markdown", help="Output format")
    p_investigate.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")

    # ── recipe ──
    p_recipe = sub.add_parser("recipe", help="Use reusable Guanlan research recipes")
    recipe_sub = p_recipe.add_subparsers(dest="recipe_command", help="Recipe commands")
    p_recipe_list = recipe_sub.add_parser("list", help="List built-in research recipes")
    p_recipe_list.add_argument("--json", action="store_true", help="Print recipes JSON")
    p_recipe_show = recipe_sub.add_parser("show", help="Show one research recipe")
    p_recipe_show.add_argument("recipe_id", help="Recipe id, e.g. finance-risk")
    p_recipe_show.add_argument("--json", action="store_true", help="Print recipe JSON")
    p_recipe_run = recipe_sub.add_parser("run", help="Render a concrete recipe plan for a query")
    p_recipe_run.add_argument("recipe_id", help="Recipe id, e.g. finance-risk")
    p_recipe_run.add_argument("query", nargs="?", default="", help="Research query")
    p_recipe_run.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_recipe_run.add_argument("--limit", type=int, default=DEFAULT_RESEARCH_LIMIT, help="Candidate pool size")
    p_recipe_run.add_argument("--read-top", type=int, default=None, help="Representative URLs to read")
    p_recipe_run.add_argument("--json", action="store_true", help="Print recipe plan JSON")

    # ── compare ──
    p_compare = sub.add_parser("compare", help="Compare multiple subjects with one evidence packet per subject")
    p_compare.add_argument("subjects", nargs="+", help="Two or more companies, products, policies, tools, or topics")
    p_compare.add_argument("--focus", default="", help="Shared comparison focus, e.g. 价格/口碑/政策影响")
    p_compare.add_argument("--preset", default="general", help="Research preset applied to every subject")
    p_compare.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_compare.add_argument("--limit", type=int, default=DEFAULT_RESEARCH_LIMIT, help="Search pool per subject")
    p_compare.add_argument("--read-top", type=int, default=0, help="Representative URLs to read per subject")
    p_compare.add_argument("--search-backend", default="auto", help="Search backend")
    p_compare.add_argument("--read-backend", choices=["auto", "jina", "direct"], default="auto", help="Read backend")
    p_compare.add_argument("--max-read-chars", type=int, default=None, help="Maximum characters per read excerpt")
    p_compare.add_argument("--select-top", type=int, default=6, help="Representative evidence items per subject")
    p_compare.add_argument("--format", choices=["markdown", "json", "context"], default="markdown", help="Output format")
    p_compare.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")

    # ── timeline ──
    p_timeline = sub.add_parser("timeline", help="Extract a dated event timeline from a broad evidence packet")
    p_timeline.add_argument("query", nargs="?", default="", help="Topic, policy, company, product, or event")
    p_timeline.add_argument("--preset", default="general", help="Research preset")
    p_timeline.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_timeline.add_argument("--limit", type=int, default=80, help="Broad search pool size")
    p_timeline.add_argument("--read-top", type=int, default=0, help="Representative URLs to read")
    p_timeline.add_argument("--search-backend", default="auto", help="Search backend")
    p_timeline.add_argument("--read-backend", choices=["auto", "jina", "direct"], default="auto", help="Read backend")
    p_timeline.add_argument("--max-read-chars", type=int, default=None, help="Maximum characters per read excerpt")
    p_timeline.add_argument("--max-events", type=int, default=20, help="Maximum dated events to return")
    p_timeline.add_argument("--order", choices=["desc", "asc"], default="desc", help="Event order")
    p_timeline.add_argument("--format", choices=["markdown", "json", "context"], default="markdown", help="Output format")
    p_timeline.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")

    # ── dossier ──
    p_dossier = sub.add_parser("dossier", help="Build a structured research dossier for one entity or issue")
    p_dossier.add_argument("entity", nargs="?", default="", help="Company, product, policy, person, event, or topic")
    p_dossier.add_argument("--focus", default="", help="Optional dossier focus")
    p_dossier.add_argument("--preset", default="general", help="Research preset")
    p_dossier.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_dossier.add_argument("--limit", type=int, default=80, help="Broad search pool size")
    p_dossier.add_argument("--read-top", type=int, default=2, help="Representative URLs to read")
    p_dossier.add_argument("--search-backend", default="auto", help="Search backend")
    p_dossier.add_argument("--read-backend", choices=["auto", "jina", "direct"], default="auto", help="Read backend")
    p_dossier.add_argument("--max-read-chars", type=int, default=2400, help="Maximum characters per read excerpt")
    p_dossier.add_argument("--select-top", type=int, default=10, help="Representative evidence items")
    p_dossier.add_argument("--format", choices=["markdown", "json", "context"], default="markdown", help="Output format")
    p_dossier.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")

    # ── yinshen ──
    p_yinshen = sub.add_parser(
        "yinshen",
        aliases=["angle"],
        help="Expand one keyword into evidence-backed media angles",
    )
    p_yinshen.add_argument("keyword", nargs="?", default="", help="Keyword or topic to expand")
    p_yinshen.add_argument("--preset", default="general", help="Research preset")
    p_yinshen.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_yinshen.add_argument("--limit", type=int, default=DEFAULT_RESEARCH_LIMIT, help="Base search pool size")
    p_yinshen.add_argument("--read-top", type=int, default=0, help="Representative URLs to read for the base keyword")
    p_yinshen.add_argument("--angle-limit", type=int, default=None, help="Search pool per extension angle; defaults to --limit")
    p_yinshen.add_argument("--angle-read-top", type=int, default=0, help="Representative URLs to read per angle")
    p_yinshen.add_argument("--angles", type=int, default=5, help="Number of extension angles, clamped to 1-8")
    p_yinshen.add_argument("--search-backend", default="auto", help="Search backend")
    p_yinshen.add_argument("--read-backend", choices=["auto", "jina", "direct"], default="auto", help="Read backend")
    p_yinshen.add_argument("--max-read-chars", type=int, default=None, help="Maximum characters per read excerpt")
    p_yinshen.add_argument("--select-top", type=int, default=12, help="Representative base evidence items")
    p_yinshen.add_argument("--plan-only", action="store_true", help="Build the angle map and queries without running per-angle deep searches")
    p_yinshen.add_argument("--format", choices=["markdown", "json", "context"], default="markdown", help="Output format")
    p_yinshen.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")

    # ── sources ──
    p_sources = sub.add_parser("sources", help="Inspect Guanlan's read-only source registry")
    sources_sub = p_sources.add_subparsers(dest="sources_command", help="Source registry commands")
    p_sources_list = sources_sub.add_parser("list", help="List source cards from scope/taxonomy registry")
    p_sources_list.add_argument("--scope", default="", help="Optional scope id, e.g. gov, ecommerce, finance_disclosure")
    p_sources_list.add_argument("--limit", type=int, default=50, help="Maximum source cards to show")
    p_sources_list.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_sources_show = sources_sub.add_parser("show", help="Show one source id, scope id, alias, or domain")
    p_sources_show.add_argument("target", help="Source id, scope id, alias, or domain")
    p_sources_show.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_sources_explain = sources_sub.add_parser("explain", help="Explain which source cards fit a query")
    p_sources_explain.add_argument("query", nargs="?", default="", help="Query or research need")
    p_sources_explain.add_argument("--profile", choices=VALID_PROFILES, default="china")
    p_sources_explain.add_argument("--limit", type=int, default=12)
    p_sources_explain.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_sources_explain.add_argument("--trace", action="store_true", help="Include read-only registry boundary diagnostics")
    p_sources_audit = sources_sub.add_parser("audit", help="Audit source wording and stability consistency")
    p_sources_audit.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_sources_export = sources_sub.add_parser("export", help="Export the read-only source registry")
    p_sources_export.add_argument("--format", choices=["json"], default="json")

    # ── prompt ──
    p_prompt = sub.add_parser(
        "prompt",
        aliases=["context"],
        help="Build a complete local-LLM prompt from Guanlan research evidence",
    )
    p_prompt.add_argument("query", nargs="?", default="", help="Question or research topic")
    p_prompt.add_argument("--preset", default="general",
                          help="Research preset: general, policy, official, industry, ecommerce, reputation, cybersecurity, sports, weather_disaster, science, career, podcast, test_prep, tech, wps_office, academic, finance, local, company, global_policy, global_reputation, global_industry")
    p_prompt.add_argument("--limit", type=int, default=80,
                          help="Broad search pool size for local model context")
    p_prompt.add_argument("--site", default="", help="Restrict search to a domain")
    p_prompt.add_argument("--sites", default="", help="Comma-separated domains for platform-directed research")
    p_prompt.add_argument("--scope", default="", help="Curated China source scope")
    p_prompt.add_argument("--search-backend", default="auto", help="Search backend")
    p_prompt.add_argument("--read-backend", choices=["auto", "jina", "direct"], default="auto",
                          help="Read backend for selected evidence")
    p_prompt.add_argument("--read-top", type=int, default=2,
                          help="Representative URLs to read into the prompt")
    p_prompt.add_argument("--max-read-chars", type=int, default=1800,
                          help="Maximum characters per read excerpt")
    p_prompt.add_argument("--profile", choices=VALID_PROFILES, default="china",
                          help="Region profile")
    p_prompt.add_argument("--advisor", action=argparse.BooleanOptionalAction, default=True,
                          help="Include advisor writing rules in the prompt")
    p_prompt.add_argument("--advisor-style", choices=["brief", "decision", "risk", "strategy"], default="brief",
                          help="Advisor guidance style")
    p_prompt.add_argument("--style", choices=["concise", "deep", "evidence", "decision"], default="deep",
                          help="Local LLM prompt style")
    p_prompt.add_argument("--select-top", type=int, default=8,
                          help="Representative evidence items to include")

    # ── pulse ──
    p_pulse = sub.add_parser("pulse", help="Analyze topic echo from public samples with clear caveats")
    p_pulse.add_argument("query", nargs="?", default="", help="Topic or query to analyze")
    p_pulse.add_argument("--limit", type=int, default=DEFAULT_PULSE_LIMIT,
                         help="Maximum number of search samples")
    p_pulse.add_argument("--site", default="",
                         help="Restrict search to a domain, e.g. zhihu.com")
    p_pulse.add_argument("--sites", default="",
                         help="Comma-separated domains for platform-directed pulse")
    p_pulse.add_argument("--scope", default="",
                         help="Curated China source scope")
    p_pulse.add_argument("--backend", default="auto",
                         help="Search backend: auto, duckduckgo, bing, baidu, anysearch, wechat-sogou, or plugin:name")
    p_pulse.add_argument("--profile", choices=VALID_PROFILES, default="china",
                         help="Region profile")
    p_pulse.add_argument("--read-top", type=int, default=0,
                         help="Optional representative URLs to read; default 0 keeps pulse search-only")
    p_pulse.add_argument("--read-backend", choices=["auto", "jina", "direct"],
                         default="auto", help="Read backend for optional evidence reads")
    p_pulse.add_argument("--max-read-chars", type=int, default=1600,
                         help="Maximum characters per optional read")
    p_pulse.add_argument("--cache-ttl", type=int, default=0,
                         help="Reuse identical search results for this many seconds")
    p_pulse.add_argument("--no-cache", action="store_true",
                         help="Bypass local cache even when --cache-ttl is set")
    p_pulse.add_argument("--format", choices=["markdown", "json", "context"], default="markdown",
                         help="Output format")
    p_pulse.add_argument("--json", action="store_true",
                         help="Print normalized JSON instead of Markdown")

    # ── feeds ──
    p_feeds = sub.add_parser("feeds", help="Discover high-quality public RSS content and source catalogs")
    p_feeds.add_argument("source", nargs="?", default="curated",
                         help="Source: curated, arxiv, watchlist, curated-sources, baidu-rss, wechat-rss, list, or a direct RSS/Atom URL")
    p_feeds.add_argument("--limit", type=int, default=DEFAULT_FEEDS_LIMIT,
                         help="Maximum number of items or sources")
    p_feeds.add_argument("--language", choices=["zh", "en"], default="zh",
                         help="Curated RSS language")
    p_feeds.add_argument("--category", choices=["programming", "ai", "product", "business"], default="",
                         help="Curated RSS category filter")
    p_feeds.add_argument("--type", dest="resource_type",
                         choices=["article", "podcast", "video", "twitter"], default="",
                         help="Curated RSS resource type filter")
    p_feeds.add_argument("--featured", action="store_true",
                         help="Only fetch featured curated content")
    p_feeds.add_argument("--min-score", type=int, default=None,
                         help="Curated RSS minimum AI score, 0-100")
    p_feeds.add_argument("--keyword", default="",
                         help="Curated RSS keyword filter, arXiv query, watchlist filter, or source-catalog query")
    p_feeds.add_argument("--watchlist", default="",
                         help="Path to a JSON/JSONL/plain-text RSS watchlist for feeds watchlist")
    p_feeds.add_argument("--time-filter", choices=["1d", "3d", "1w", "1m", "3m"], default="",
                         help="Curated RSS time window")
    p_feeds.add_argument("--format", choices=["markdown", "json", "context"], default="markdown",
                         help="Output format")
    p_feeds.add_argument("--json", action="store_true",
                         help="Print normalized JSON instead of Markdown")

    # ── daily ──
    p_daily = sub.add_parser("daily", help="Build a Guanlan-native daily brief from route/search/feeds/hotnews/watch")
    p_daily.add_argument("query", nargs="?", default="", help="Optional daily topic; omit for a broader public daily brief")
    p_daily.add_argument("--watch-id", default="", help="Reuse one saved watch intent as the daily subject")
    p_daily.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_daily.add_argument("--scope", default="", help="Curated source scope")
    p_daily.add_argument("--site", default="", help="Restrict search to one domain")
    p_daily.add_argument("--preset", default="", help="Research preset hint for the daily brief")
    p_daily.add_argument("--lens", default="", help="Optional analyst lens to keep in the report header")
    p_daily.add_argument("--feed-source", default="auto", help="Feed source: auto, curated, ai-vertical, arxiv, watchlist, baidu-rss, wechat-rss, or RSS URL")
    p_daily.add_argument("--watchlist", default="", help="RSS watchlist path when --feed-source watchlist")
    p_daily.add_argument("--hotnews-source", default="today", help="Hotnews source id, default today")
    p_daily.add_argument("--backend", default="auto", help="Search backend")
    p_daily.add_argument("--limit", type=int, default=12, help="Final number of daily items to keep")
    p_daily.add_argument("--search-limit", type=int, default=DEFAULT_SEARCH_LIMIT, help="Search candidate pool size before daily selection")
    p_daily.add_argument("--feeds-limit", type=int, default=20, help="Feed candidate count before daily selection")
    p_daily.add_argument("--hotnews-limit", type=int, default=20, help="Hotnews candidate count before daily selection")
    p_daily.add_argument("--read-top", type=int, default=3, help="Representative daily URLs to read; use 0 to keep search-only")
    p_daily.add_argument("--read-backend", choices=["auto", "jina", "direct"], default="auto", help="Read backend for representative daily URLs")
    p_daily.add_argument("--max-read-chars", type=int, default=1800, help="Maximum characters per representative daily read")
    p_daily.add_argument("--overflow-limit", type=int, default=20, help="How many non-selected daily candidates to list at the bottom; use 0 to hide")
    p_daily.add_argument("--time-window", choices=["today", "24h", "3d", "7d"], default="3d", help="Freshness window for using today/latest language")
    p_daily.add_argument("--edition", choices=["brand", "market", "reputation", "general"], default="brand", help="Editorial edition for action/team defaults")
    p_daily.add_argument("--record-history", action="store_true", help="Append a compact daily history record under ~/.guanlan/daily/history.jsonl")
    p_daily.add_argument("--history-path", default="", help="Override daily history JSONL path")
    p_daily.add_argument("--compare-days", type=int, default=0, help="Compare against saved daily history from the last N days")
    p_daily.add_argument("--cache-ttl", type=int, default=0, help="Reuse identical search cache for this many seconds")
    p_daily.add_argument("--no-search", action="store_true", help="Skip the search layer")
    p_daily.add_argument("--no-feeds", action="store_true", help="Skip the feeds layer")
    p_daily.add_argument("--no-hotnews", action="store_true", help="Skip the hotnews layer")
    p_daily.add_argument("--output", default="", help="Optional output path for Markdown/JSON/context")
    p_daily.add_argument("--store", default="", help="Optional watch store path when --watch-id is used")
    p_daily.add_argument("--format", choices=["markdown", "json", "context", "html", "im"], default="markdown", help="Output format")
    p_daily.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")

    # ── watch ──
    p_watch = sub.add_parser("watch", help="Manage standing research intents for Guanlan radar workflows")
    watch_sub = p_watch.add_subparsers(dest="watch_command", help="Watch commands")

    p_watch_plan = watch_sub.add_parser("plan", help="Plan a lightweight standing intent without saving it")
    p_watch_plan.add_argument("query", help="Long-running concern to watch")
    p_watch_plan.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_watch_plan.add_argument("--scope", default="", help="Curated source scope")
    p_watch_plan.add_argument("--site", default="", help="Restrict search to one domain")
    p_watch_plan.add_argument("--preset", default="", help="Research preset to bind when escalating")
    p_watch_plan.add_argument("--feed-source", default="auto", help="Feed source: auto, curated, arxiv, watchlist, baidu-rss, wechat-rss, or RSS URL")
    p_watch_plan.add_argument("--watchlist", default="", help="RSS watchlist path when --feed-source watchlist")
    p_watch_plan.add_argument("--lens", default="", help="Analyst lens or brief to keep with this intent")
    p_watch_plan.add_argument("--schedule", default="", help="Human-readable schedule label; no daemon is started")
    p_watch_plan.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT, help="Recommended candidate pool size")
    p_watch_plan.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_watch_plan.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")

    p_watch_add = watch_sub.add_parser("add", help="Save a standing intent locally")
    p_watch_add.add_argument("query", help="Long-running concern to watch")
    p_watch_add.add_argument("--id", dest="intent_id", default="", help="Stable id; autogenerated if omitted")
    p_watch_add.add_argument("--name", default="", help="Display name")
    p_watch_add.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_watch_add.add_argument("--scope", default="", help="Curated source scope")
    p_watch_add.add_argument("--site", default="", help="Restrict search to one domain")
    p_watch_add.add_argument("--preset", default="", help="Research preset to bind when escalating")
    p_watch_add.add_argument("--feed-source", default="auto", help="Feed source: auto, curated, arxiv, watchlist, baidu-rss, wechat-rss, or RSS URL")
    p_watch_add.add_argument("--watchlist", default="", help="RSS watchlist path when --feed-source watchlist")
    p_watch_add.add_argument("--lens", default="", help="Analyst lens or brief to keep with this intent")
    p_watch_add.add_argument("--schedule", default="", help="Human-readable schedule label; no daemon is started")
    p_watch_add.add_argument("--tag", action="append", default=[], help="Tag; can be repeated")
    p_watch_add.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_watch_add.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_watch_add.add_argument("--store", default="", help="Optional watch store path")

    p_watch_list = watch_sub.add_parser("list", help="List saved watch intents")
    p_watch_list.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_watch_list.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_watch_list.add_argument("--store", default="", help="Optional watch store path")

    p_watch_show = watch_sub.add_parser("show", help="Show one saved watch intent")
    p_watch_show.add_argument("identifier", help="Intent id or exact name")
    p_watch_show.add_argument("--include-seen", action="store_true", help="Include seen fingerprint state")
    p_watch_show.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_watch_show.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_watch_show.add_argument("--store", default="", help="Optional watch store path")

    p_watch_remove = watch_sub.add_parser("remove", help="Remove one saved watch intent")
    p_watch_remove.add_argument("identifier", help="Intent id or exact name")
    p_watch_remove.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_watch_remove.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_watch_remove.add_argument("--store", default="", help="Optional watch store path")

    p_watch_fire = watch_sub.add_parser("fire", help="Run one no-notification diagnostic pass for a saved intent")
    p_watch_fire.add_argument("identifier", help="Intent id or exact name")
    p_watch_fire.add_argument("--limit", type=int, default=30, help="Maximum merged items to return")
    p_watch_fire.add_argument("--search-limit", type=int, default=0, help="Search candidate count; defaults to --limit")
    p_watch_fire.add_argument("--feed-limit", type=int, default=0, help="Feed candidate count; defaults to --limit")
    p_watch_fire.add_argument("--backend", default="auto", help="Search backend")
    p_watch_fire.add_argument("--record-seen", action="store_true", help="Write match_seen-style local dedupe state")
    p_watch_fire.add_argument("--cache-ttl", type=int, default=0, help="Reuse identical search cache for this many seconds")
    p_watch_fire.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_watch_fire.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_watch_fire.add_argument("--store", default="", help="Optional watch store path")

    # ── read ──
    p_read = sub.add_parser("read", help="Read a URL as Markdown for agent context")
    p_read.add_argument("url", nargs="?", default="",
                        help="URL to read, or 'batch' for URL-list mode")
    p_read.add_argument("batch_file", nargs="?",
                        help="File containing one URL per line when using `read batch`")
    p_read.add_argument("--max-chars", type=int, default=0,
                        help="Truncate output to this many characters")
    p_read.add_argument("--backend", choices=["auto", "jina", "direct"], default="auto",
                        help="Read backend: auto tries Jina Reader then direct HTML fallback")
    p_read.add_argument("--format", choices=["markdown", "json", "context", "prompt"], default="markdown",
                        help="Output format for batch reads")
    p_read.add_argument("--question", default="",
                        help="Question to include when using --format prompt")
    p_read.add_argument("--fallback-search", action=argparse.BooleanOptionalAction, default=True,
                        help="When auto reading fails, return public search context instead of hard failing")
    p_read.add_argument("--fallback-limit", type=int, default=DEFAULT_READ_FALLBACK_LIMIT,
                        help="Maximum search results to include when fallback search is used")
    p_read.add_argument("--profile", choices=VALID_PROFILES, default="china",
                        help="Region profile for fallback search")
    p_read.add_argument("--cache-ttl", type=int, default=0,
                        help="Reuse identical read results for this many seconds")
    p_read.add_argument("--no-cache", action="store_true",
                        help="Bypass local cache even when --cache-ttl is set")
    p_read.add_argument("--watch", action="store_true",
                        help="Compare this read with the saved local snapshot and output a diff")
    p_read.add_argument("--trace", action="store_true",
                        help="Show read backend attempts and content quality score")
    p_read.add_argument("--quality-report", action="store_true",
                        help="Append a stable readability/noise report for agent diagnostics")
    p_read.add_argument("--strict", action="store_true",
                        help="Prefer failing/fallback over returning noisy extracted text")
    p_read.add_argument("--extract", choices=["article", "text", "metadata", "links"], default="article",
                        help="Direct-read extraction target")
    p_read.add_argument("--concurrency", type=int, default=1,
                        help="Explicit batch read concurrency; default 1 keeps legacy serial behavior")
    p_read.add_argument("--interval", default="",
                        help="Accepted for watch workflows; this CLI stores one snapshot per run")

    # ── report ──
    p_report = sub.add_parser("report", help="Render sidecar static HTML reports from existing JSON")
    report_sub = p_report.add_subparsers(dest="report_command", help="Report commands")
    p_report_html = report_sub.add_parser(
        "html",
        help="Render a self-contained HTML report from local JSON, stdin, or demo data",
    )
    p_report_html.add_argument("--input", default="",
                               help="JSON input path; use '-' for stdin. Omit for a demo report")
    p_report_html.add_argument("--output", default="guanlan-report.html",
                               help="Output HTML path")
    p_report_html.add_argument("--title", default="", help="Override report title")
    p_report_html.add_argument("--subtitle", default="", help="Override report subtitle")
    p_report_html.add_argument(
        "--score-mode",
        choices=["signal", "risk", "quality"],
        default="signal",
        help="Color encoding: signal/risk means higher is warmer; quality means higher is greener",
    )

    # ── archive ──
    p_archive = sub.add_parser("archive", help="Manage the local Markdown knowledge archive")
    archive_sub = p_archive.add_subparsers(dest="archive_command", help="Archive commands")

    p_archive_add = archive_sub.add_parser("add", help="Read URL(s) into the local archive")
    p_archive_add.add_argument("target", help="URL to archive, or 'batch' for URL-list mode")
    p_archive_add.add_argument("batch_file", nargs="?",
                               help="File containing one URL per line when target is 'batch'")
    p_archive_add.add_argument("--max-chars", type=int, default=0,
                               help="Truncate each read to this many characters before archiving")
    p_archive_add.add_argument("--backend", choices=["auto", "jina", "direct"], default="auto",
                               help="Read backend used before archiving")
    p_archive_add.add_argument("--fallback-search", action=argparse.BooleanOptionalAction, default=True,
                               help="Use public search context when direct reading fails")
    p_archive_add.add_argument("--fallback-limit", type=int, default=DEFAULT_READ_FALLBACK_LIMIT,
                               help="Maximum fallback search results")
    p_archive_add.add_argument("--profile", choices=VALID_PROFILES, default="china",
                               help="Region profile for fallback search")
    p_archive_add.add_argument("--format", choices=["markdown", "json"], default="markdown",
                               help="Output format")
    p_archive_add.add_argument("--concurrency", type=int, default=1,
                               help="Explicit batch archive read concurrency; default 1 keeps serial behavior")
    p_archive_add.add_argument("--db", default="", help="Optional archive database path")

    p_archive_browser_note = archive_sub.add_parser(
        "add-browser-note",
        help="Archive user-authorized visible browser evidence with explicit boundaries",
    )
    p_archive_browser_note.add_argument("--url", default="", help="Target page URL shown in the browser; optional with --from-json")
    p_archive_browser_note.add_argument("--text", default="", help="Visible page text to archive")
    p_archive_browser_note.add_argument("--text-file", default="", help="File containing visible page text")
    p_archive_browser_note.add_argument("--from-json", default="", help="JSON/JSONL file or '-' from OpenGuanlan visible-page extraction")
    p_archive_browser_note.add_argument("--title", default="", help="Visible page title")
    p_archive_browser_note.add_argument("--platform", default="", help="Optional platform label")
    p_archive_browser_note.add_argument("--author", default="", help="Visible author/account when relevant")
    p_archive_browser_note.add_argument("--published-at", default="", help="Visible publication time when relevant")
    p_archive_browser_note.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_archive_browser_note.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_archive_browser_note.add_argument("--db", default="", help="Optional archive database path")

    p_archive_search = archive_sub.add_parser("search", help="Search the local archive")
    p_archive_search.add_argument("query", help="Archive search query")
    p_archive_search.add_argument("--limit", type=int, default=DEFAULT_ARCHIVE_SEARCH_LIMIT, help="Maximum number of results")
    p_archive_search.add_argument("--format", choices=["markdown", "json", "context"], default="markdown",
                                  help="Output format")
    p_archive_search.add_argument("--json", action="store_true",
                                  help="Print normalized JSON instead of Markdown")
    p_archive_search.add_argument("--trace", action="store_true",
                                  help="Include matched terms, fields, score, and retrieval boundary")
    p_archive_search.add_argument("--semantic", action="store_true",
                                  help="Use explicit local semantic sidecar when available; fallback to FTS/LIKE")
    p_archive_search.add_argument("--db", default="", help="Optional archive database path")

    p_archive_list = archive_sub.add_parser("list", help="List recently archived documents")
    p_archive_list.add_argument("--limit", type=int, default=DEFAULT_ARCHIVE_LIST_LIMIT, help="Maximum number of records")
    p_archive_list.add_argument("--format", choices=["markdown", "json", "context"], default="markdown",
                                help="Output format")
    p_archive_list.add_argument("--json", action="store_true",
                                help="Print normalized JSON instead of Markdown")
    p_archive_list.add_argument("--db", default="", help="Optional archive database path")

    p_archive_stats = archive_sub.add_parser("stats", help="Show archive counts and domain distribution")
    p_archive_stats.add_argument("--json", action="store_true",
                                 help="Print normalized JSON instead of Markdown")
    p_archive_stats.add_argument("--quality", action="store_true",
                                 help="Include read-quality and RAG-readiness summary")
    p_archive_stats.add_argument("--rag-min-quality", type=int, default=60,
                                 help="Quality score threshold used for RAG-ready stats")
    p_archive_stats.add_argument("--db", default="", help="Optional archive database path")

    p_archive_inspect = archive_sub.add_parser("inspect", help="Inspect one archived document by id or URL")
    p_archive_inspect.add_argument("identifier", help="Archive id or URL")
    p_archive_inspect.add_argument("--format", choices=["markdown", "json"], default="markdown",
                                   help="Output format")
    p_archive_inspect.add_argument("--db", default="", help="Optional archive database path")

    p_archive_remove = archive_sub.add_parser("remove", help="Remove one archived document by id or URL")
    p_archive_remove.add_argument("identifier", help="Archive id or URL")
    p_archive_remove.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_archive_remove.add_argument("--db", default="", help="Optional archive database path")

    p_archive_reindex = archive_sub.add_parser("reindex", help="Rebuild the local archive FTS index")
    p_archive_reindex.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_archive_reindex.add_argument("--db", default="", help="Optional archive database path")

    p_archive_verify = archive_sub.add_parser("verify", help="Verify archive index, content quality, and sample recall")
    p_archive_verify.add_argument("--limit", type=int, default=8, help="Recent documents to sample for recall checks")
    p_archive_verify.add_argument("--min-quality", type=int, default=60, help="RAG/Wiki quality threshold")
    p_archive_verify.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_archive_verify.add_argument("--db", default="", help="Optional archive database path")

    p_archive_export = archive_sub.add_parser("export", help="Export archive records")
    p_archive_export.add_argument("--format", choices=["jsonl", "markdown", "rag-jsonl", "llamaindex-jsonl", "langchain-jsonl", "openwebui-jsonl"], default="jsonl",
                                  help="Export format")
    p_archive_export.add_argument("--domain", default="", help="Filter export by domain")
    p_archive_export.add_argument("--source-type", default="", help="Filter export by archived source_type metadata")
    p_archive_export.add_argument("--topic", default="", help="Filter export by archived topic metadata")
    p_archive_export.add_argument("--min-quality", type=int, default=None,
                                  help="Only export records whose read_quality score is at least this value")
    p_archive_export.add_argument("--db", default="", help="Optional archive database path")

    p_archive_context = archive_sub.add_parser("context", help="Build a local-model context from archive matches")
    p_archive_context.add_argument("query", help="Question or topic to search in the local archive")
    p_archive_context.add_argument("--limit", type=int, default=20, help="Maximum archive records")
    p_archive_context.add_argument("--min-quality", type=int, default=0, help="Mark lower-quality evidence as candidate")
    p_archive_context.add_argument("--max-chars", type=int, default=1200, help="Maximum characters per evidence excerpt")
    p_archive_context.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_archive_context.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_archive_context.add_argument("--semantic", action="store_true",
                                   help="Use explicit local semantic sidecar when available")
    p_archive_context.add_argument("--db", default="", help="Optional archive database path")

    p_archive_embed = archive_sub.add_parser("embed", help="Build an explicit local semantic sidecar for archive search")
    p_archive_embed.add_argument("--backend", choices=["local", "ollama", "openai"], default="local",
                                 help="Embedding backend; local is dependency-free, external backends are planned/opt-in")
    p_archive_embed.add_argument("--limit", type=int, default=500, help="Maximum archive records to embed")
    p_archive_embed.add_argument("--dry-run", action="store_true", help="Preview embedding without writing sidecar rows")
    p_archive_embed.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_archive_embed.add_argument("--db", default="", help="Optional archive database path")

    p_archive_pack = archive_sub.add_parser("pack", help="Package archive matches as Markdown or RAG JSONL")
    p_archive_pack.add_argument("query", help="Question or topic to pack from the local archive")
    p_archive_pack.add_argument("--limit", type=int, default=20, help="Maximum archive records")
    p_archive_pack.add_argument("--max-chars", type=int, default=1200, help="Maximum characters per evidence excerpt")
    p_archive_pack.add_argument("--format", choices=["markdown", "jsonl", "rag-jsonl", "llamaindex-jsonl", "langchain-jsonl", "openwebui-jsonl", "llm-wiki"], default="markdown", help="Pack format")
    p_archive_pack.add_argument("--output", default="", help="Optional output path; required directory for --format llm-wiki")
    p_archive_pack.add_argument("--json", action="store_true", help="Print write summary as JSON when --output is used")
    p_archive_pack.add_argument("--db", default="", help="Optional archive database path")

    p_archive_wiki = archive_sub.add_parser("wiki", help="Build or query a local Agent Wiki from the archive")
    archive_wiki_sub = p_archive_wiki.add_subparsers(dest="wiki_command", help="Archive wiki commands")
    p_archive_wiki_build = archive_wiki_sub.add_parser("build", help="Build a static Markdown/HTML Agent Wiki")
    p_archive_wiki_build.add_argument("--output", default="", help="Output directory; defaults to ~/.guanlan/wiki")
    p_archive_wiki_build.add_argument("--topic", default="", help="Optional topic query to build a focused wiki")
    p_archive_wiki_build.add_argument("--format", choices=["html", "markdown", "both", "llm-wiki"], default="html", help="Wiki output format")
    p_archive_wiki_build.add_argument("--limit", type=int, default=200, help="Maximum archive records")
    p_archive_wiki_build.add_argument("--min-quality", type=int, default=60, help="Core/candidate quality threshold")
    p_archive_wiki_build.add_argument("--no-candidates", action="store_true", help="Exclude candidate/low-quality pages")
    p_archive_wiki_build.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_archive_wiki_build.add_argument("--db", default="", help="Optional archive database path")
    p_archive_wiki_context = archive_wiki_sub.add_parser("context", help="Build prompt-ready context from the local Agent Wiki/archive")
    p_archive_wiki_context.add_argument("query", help="Question or topic to search in the local archive")
    p_archive_wiki_context.add_argument("--limit", type=int, default=20, help="Maximum archive records")
    p_archive_wiki_context.add_argument("--min-quality", type=int, default=0, help="Mark lower-quality evidence as candidate")
    p_archive_wiki_context.add_argument("--max-chars", type=int, default=1200, help="Maximum characters per evidence excerpt")
    p_archive_wiki_context.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_archive_wiki_context.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_archive_wiki_context.add_argument("--db", default="", help="Optional archive database path")

    p_archive_ingest = archive_sub.add_parser(
        "ingest-search",
        aliases=["ingest-research"],
        help="Run web research and archive representative evidence (not local archive search)",
    )
    p_archive_ingest.add_argument("query", help="Research query to ingest")
    p_archive_ingest.add_argument("--limit", type=int, default=DEFAULT_RESEARCH_LIMIT, help="Broad search pool size")
    p_archive_ingest.add_argument(
        "--read-top",
        type=int,
        default=0,
        help="Representative URLs to read before archiving; default 0 keeps ingest-search fast and stable",
    )
    p_archive_ingest.add_argument("--select-top", type=int, default=8, help="Representative evidence items to archive")
    p_archive_ingest.add_argument("--preset", default="general", help="Research preset")
    p_archive_ingest.add_argument("--profile", choices=VALID_PROFILES, default="china", help="Region profile")
    p_archive_ingest.add_argument(
        "--read-backend",
        choices=["auto", "jina", "direct"],
        default="direct",
        help="Read backend for optional --read-top enrichment; direct is faster and avoids Jina stalls",
    )
    p_archive_ingest.add_argument("--read-concurrency", type=int, default=3, help="Concurrent optional reads for --read-top")
    p_archive_ingest.add_argument("--cache-ttl", type=int, default=3600, help="Search/read cache TTL for retry-friendly ingest")
    p_archive_ingest.add_argument("--dry-run", action="store_true",
                                  help="Preview what would be archived without writing to the local database")
    p_archive_ingest.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_archive_ingest.add_argument("--db", default="", help="Optional archive database path")

    # ── serve ──
    p_serve = sub.add_parser("serve", help="Run a local read-only HTTP service")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host to bind; default keeps service local-only")
    p_serve.add_argument("--port", type=int, default=8765, help="Port to listen on")
    p_serve.add_argument("--token", default="",
                         help="Optional read-only HTTP token; can also use GUANLAN_SERVE_TOKEN")
    p_serve.add_argument("--print-token", action="store_true",
                         help="Print a random serve token and exit")

    # ── plugin ──
    p_plugin = sub.add_parser("plugin", help="Manage read-only search backend plugins")
    plugin_sub = p_plugin.add_subparsers(dest="plugin_command", help="Plugin commands")
    plugin_sub.add_parser("list", help="List registered plugins")
    p_plugin_register = plugin_sub.add_parser("register", help="Register a local read-only plugin backend")
    p_plugin_register.add_argument("name", help="Plugin backend name")
    p_plugin_register.add_argument("path", help="Path to plugin script")
    p_plugin_template = plugin_sub.add_parser("template", help="Print a plugin backend template")
    p_plugin_template.add_argument("name", nargs="?", default="my_company_api", help="Template plugin name")

    # ── eval ──
    p_eval = sub.add_parser("eval", help="Show Guanlan evaluation scenarios")
    eval_sub = p_eval.add_subparsers(dest="eval_command", help="Evaluation commands")
    p_eval_scenarios = eval_sub.add_parser("scenarios", help="Print built-in evaluation scenarios")
    p_eval_scenarios.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_eval_tasks = eval_sub.add_parser("tasks", help="Print realistic benchmark task seeds")
    p_eval_tasks.add_argument("--category", default="", help="Optional task category filter")
    p_eval_tasks.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_eval_benchmark = eval_sub.add_parser("benchmark", help="Run deterministic agent-facing benchmark")
    p_eval_benchmark.add_argument("--mode", choices=["quick", "live"], default="quick",
                                  help="Benchmark mode; quick is deterministic and offline")
    p_eval_benchmark.add_argument("--limit", type=int, default=50,
                                  help="Candidate pool size to verify in route plans")
    p_eval_benchmark.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_eval_suite = eval_sub.add_parser("suite", help="Run public deterministic eval suites")
    suite_sub = p_eval_suite.add_subparsers(dest="eval_suite_command", help="Eval suite commands")
    p_suite_list = suite_sub.add_parser("list", help="List available eval suites")
    p_suite_list.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_suite_run = suite_sub.add_parser("run", help="Run an eval suite")
    p_suite_run.add_argument("suite_id", nargs="?", default="chinese-web-v1")
    p_suite_run.add_argument("--mode", choices=["quick", "live"], default="quick")
    p_suite_run.add_argument("--limit", type=int, default=80)
    p_suite_run.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_suite_report = suite_sub.add_parser("report", help="Write an eval suite HTML report")
    p_suite_report.add_argument("suite_id", nargs="?", default="chinese-web-v1")
    p_suite_report.add_argument("--output", default="guanlan-eval-suite.html")
    p_suite_report.add_argument("--mode", choices=["quick", "live"], default="quick")
    p_suite_report.add_argument("--limit", type=int, default=80)

    # ── quality ──
    p_quality = sub.add_parser("quality", help="Run Guanlan quality gates")
    quality_sub = p_quality.add_subparsers(dest="quality_command", help="Quality commands")
    p_quality_run = quality_sub.add_parser("run", help="Run search/read/hotnews/advisor quality checks")
    p_quality_run.add_argument("--mode", choices=["quick", "live"], default="quick",
                               help="quick is deterministic; live performs network probes")
    p_quality_run.add_argument("--limit", type=int, default=5,
                               help="Live probe result limit")
    p_quality_run.add_argument("--coverage", action="store_true",
                               help="Also run coverage guards that prevent agent context shrinkage")
    p_quality_run.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_quality_foundational = quality_sub.add_parser("foundational", help="Run light/heavy workflow foundation guards")
    p_quality_foundational.add_argument("--mode", choices=["quick", "live"], default="quick",
                                        help="quick is deterministic; live performs network probes")
    p_quality_foundational.add_argument("--limit", type=int, default=50,
                                        help="Live probe result limit")
    p_quality_foundational.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_quality_coverage = quality_sub.add_parser("coverage", help="Run context coverage guards")
    p_quality_coverage.add_argument("--mode", choices=["quick", "live"], default="quick",
                                    help="quick is deterministic; live performs network probes")
    p_quality_coverage.add_argument("--limit", type=int, default=50,
                                    help="Live probe result limit")
    p_quality_coverage.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_quality_regression = quality_sub.add_parser("regression", help="Run release regression guards")
    p_quality_regression.add_argument("--mode", choices=["quick", "live"], default="quick",
                                      help="quick is deterministic; live performs network probes")
    p_quality_regression.add_argument("--limit", type=int, default=50,
                                      help="Live probe result limit")
    p_quality_regression.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_quality_robustness = quality_sub.add_parser("robustness", help="Run deeper robustness guards for archive/search/read/release contracts")
    p_quality_robustness.add_argument("--mode", choices=["quick", "live"], default="quick",
                                      help="quick is deterministic; live performs network probes")
    p_quality_robustness.add_argument("--limit", type=int, default=50,
                                      help="Live probe result limit")
    p_quality_robustness.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_quality_live = quality_sub.add_parser("live-smoke", help="Run optional live network smoke probes")
    p_quality_live.add_argument("--limit", type=int, default=5,
                                help="Live probe result limit")
    p_quality_live.add_argument("--timeout-budget", type=int, default=180,
                                help="Suggested outer timeout budget in seconds for agent/automation runners")
    p_quality_live.add_argument("--profile", choices=VALID_PROFILES, default="china",
                                help="Region profile for live probes")
    p_quality_live.add_argument("--strict", action="store_true",
                                help="Exit non-zero if live smoke reports failures")
    p_quality_live.add_argument("--record-history", action="store_true",
                                help="Append this live smoke run to the local JSONL trend history")
    p_quality_live.add_argument("--history-path", default=None,
                                help="Optional JSONL path for live smoke history")
    p_quality_live.add_argument("--trend-window", type=int, default=10,
                                help="Number of recent live smoke runs to summarize")
    p_quality_live.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_quality_perf = quality_sub.add_parser("performance", help="Run deterministic performance regression guards")
    p_quality_perf.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_quality_backend = quality_sub.add_parser("backend-fixtures", help="Run deterministic backend quality fixture guards")
    p_quality_backend.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_quality_mixer = quality_sub.add_parser("evidence-mixer", help="Run deterministic Evidence Mixer shadow-mode guards")
    p_quality_mixer.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")

    # ── mcp ──
    p_mcp = sub.add_parser("mcp", help="MCP helpers for agent integration")
    mcp_sub = p_mcp.add_subparsers(dest="mcp_command", help="MCP commands")
    p_mcp_config = mcp_sub.add_parser("config", help="Print a copyable MCP client configuration")
    p_mcp_config.add_argument("--client", choices=["generic", "claude", "cursor", "codex", "openwebui"],
                              default="generic", help="Target client profile")
    p_mcp_config.add_argument("--format", choices=["markdown", "json"], default="markdown",
                              help="Output format")
    p_mcp_config.add_argument("--command", dest="server_command", default="guanlan-mcp",
                              help="Command used to start the Guanlan MCP server")

    # ── check-update ──
    sub.add_parser("check-update", help="Check for new versions and changes")

    # ── watchdog ──
    sub.add_parser("watchdog", help="Quick health check + update check (for scheduled tasks)")

    # ── status ──
    sub.add_parser("status", help="Show channel readiness, verification, stability, and local cache summary")

    # ── version ──
    sub.add_parser("version", help="Show version")

    args = parser.parse_args()

    # Suppress loguru noise unless --verbose
    _configure_logging(getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "version":
        print(f"观澜 / Guanlan v{__version__}")
        sys.exit(0)

    from guanlan.telemetry import telemetry_span

    with telemetry_span(_telemetry_command_name(args), surface="cli"):
        _dispatch_command(args)
        _print_background_update_notice_if_available(args)


def _telemetry_command_name(args) -> str:
    """Return a privacy-safe command label for anonymous telemetry."""
    command = str(getattr(args, "command", "") or "unknown")
    # Only include subcommand names that are already part of the public command
    # shape. Do not include configure keys, queries, URLs, plugin paths, or values.
    subcommand_attrs = {
        "archive": "archive_command",
        "mcp": "mcp_command",
        "eval": "eval_command",
        "quality": "quality_command",
        "profile": "action",
        "report": "report_command",
        "stock": "stock_command",
        "diagnose": "diagnose_command",
        "browser-assist": "browser_assist_command",
        "recipe": "recipe_command",
    }
    attr = subcommand_attrs.get(command)
    if attr:
        value = str(getattr(args, attr, "") or "").strip()
        if value:
            return f"{command}.{value}"
    return command


def _dispatch_command(args):
    """Run a parsed command."""
    if args.command == "doctor":
        _cmd_doctor(args)
    elif args.command == "welcome":
        _cmd_welcome()
    elif args.command == "capabilities":
        _cmd_capabilities(args)
    elif args.command == "profile":
        _cmd_profile(args)
    elif args.command == "check-update":
        _cmd_check_update()
    elif args.command == "watchdog":
        _cmd_health_watch()
    elif args.command == "status":
        _cmd_status()
    elif args.command == "setup":
        _cmd_setup()
    elif args.command == "install":
        _cmd_install(args)
    elif args.command == "configure":
        _cmd_configure(args)
    elif args.command == "uninstall":
        _cmd_uninstall(args)
    elif args.command == "skill":
        _cmd_skill(args)
    elif args.command == "format":
        _cmd_format(args)
    elif args.command == "hotnews":
        _cmd_hotnews(args)
    elif args.command == "route":
        _cmd_route(args)
    elif args.command == "workflow":
        _cmd_workflow(args)
    elif args.command == "agent":
        _cmd_agent(args)
    elif args.command == "diagnose":
        _cmd_diagnose(args)
    elif args.command == "browser-assist":
        _cmd_browser_assist(args)
    elif args.command == "wechat-exporter":
        _cmd_wechat_exporter(args)
    elif args.command == "search":
        _cmd_search(args)
    elif args.command == "feedback":
        _cmd_feedback(args)
    elif args.command == "research":
        _cmd_research(args)
    elif args.command == "investigate":
        _cmd_investigate(args)
    elif args.command == "recipe":
        _cmd_recipe(args)
    elif args.command == "compare":
        _cmd_compare(args)
    elif args.command == "timeline":
        _cmd_timeline(args)
    elif args.command == "dossier":
        _cmd_dossier(args)
    elif args.command in {"yinshen", "angle"}:
        _cmd_yinshen(args)
    elif args.command == "sources":
        _cmd_sources(args)
    elif args.command in {"prompt", "context"}:
        _cmd_prompt(args)
    elif args.command == "pulse":
        _cmd_pulse(args)
    elif args.command == "feeds":
        _cmd_feeds(args)
    elif args.command == "daily":
        _cmd_daily(args)
    elif args.command == "watch":
        _cmd_watch_intents(args)
    elif args.command == "read":
        _cmd_read(args)
    elif args.command == "stock":
        _cmd_stock(args)
    elif args.command == "report":
        _cmd_report(args)
    elif args.command == "archive":
        _cmd_archive(args)
    elif args.command == "mcp":
        _cmd_mcp(args)
    elif args.command == "serve":
        _cmd_serve(args)
    elif args.command == "plugin":
        _cmd_plugin(args)
    elif args.command == "eval":
        _cmd_eval(args)
    elif args.command == "quality":
        _cmd_quality(args)


if __name__ == "__main__":
    main()
