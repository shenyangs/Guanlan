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
import contextlib
import json
import os
import secrets
import sys
import time

from guanlan import __version__
from guanlan.limits import (
    DEFAULT_ARCHIVE_LIST_LIMIT,
    DEFAULT_ARCHIVE_SEARCH_LIMIT,
    DEFAULT_FEEDS_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_PULSE_LIMIT,
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    MAX_FEEDS_LIMIT,
)
from guanlan.profiles import VALID_PROFILES

_AUTO_FEEDBACK_SENT = set()


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


def _print_sensitive_access_notice(action: str, browser: str | None = None):
    """Print a reassuring notice before actions that may trigger Keychain prompts."""
    target = f"{browser} 浏览器 Cookie" if browser else "认证/登录态"
    print()
    print("观澜安全提示")
    print("=" * 40)
    print(f"即将进行：{action}")
    print(f"可能出现 macOS 钥匙串弹窗，用于允许读取本机的 {target}。")
    print("这一步不会读取你的系统登录密码，也不会上传任何 Cookie、Token 或个人数据。")
    print("观澜只会在本机提取相关平台的登录态，用于你明确授权的搜索/读取能力。")
    print("如果你不想授权，可以在弹窗中选择拒绝；观澜会继续使用公开搜索、网页阅读和热榜能力。")
    print("=" * 40)
    print()
    sys.stdout.flush()
    try:
        delay = float(os.environ.get("GUANLAN_NOTICE_DELAY", "1.5"))
    except ValueError:
        delay = 1.5
    if delay > 0:
        time.sleep(delay)


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
                                "reddit,bilibili,douyin,linkedin,all)")

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
                           help="Source id: today, snapshot, baidu, weibo, bilibili-hot-search, bilibili, ithome, sspai, xinzhiyuan, youtube-ai-rss, zeli-hn, buzzing, zhihu, v2ex, newsnow:<id>, vvhan:<id>, uapis:<id>, tophub:<id>, hotboard:<id>, or list")
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
    p_browser_assist_plan = browser_assist_sub.add_parser("plan", help="Build a host-browser visible evidence task")
    p_browser_assist_plan.add_argument("url", help="Target page URL")
    p_browser_assist_plan.add_argument("--page-type", default="access_gate", help="Diagnosis page type hint")
    p_browser_assist_plan.add_argument("--signal", action="append", default=[], help="Diagnosis signal hint; can be repeated")
    p_browser_assist_plan.add_argument("--platform", default="", help="Optional platform label override")
    p_browser_assist_plan.add_argument("--max-pages", type=int, default=3, help="Maximum browser-visible target pages in the host-agent task")
    p_browser_assist_plan.add_argument("--max-chars-per-page", type=int, default=3000, help="Maximum visible characters per page for the host-agent task")
    p_browser_assist_plan.add_argument("--task-goal", default="", help="Optional host-agent task goal")
    p_browser_assist_plan.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_browser_assist_plan.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")
    p_browser_assist_run = browser_assist_sub.add_parser("run", help="Bridge a browser-assist task to host-browser/open-cli/xhs-cli adapters")
    p_browser_assist_run.add_argument("url", help="Target page URL")
    p_browser_assist_run.add_argument("--adapter", default="host-browser", help="Adapter: host-browser, open-cli, xhs-cli")
    p_browser_assist_run.add_argument("--execute", action="store_true", help="Execute external adapter when safe/configured; host-browser still returns a host task")
    p_browser_assist_run.add_argument("--command-template", default="", help="External CLI command template; supports {url} and {output}")
    p_browser_assist_run.add_argument("--output", default="", help="Optional JSONL output path for parsed adapter payloads")
    p_browser_assist_run.add_argument("--timeout", type=int, default=90, help="External adapter timeout seconds")
    p_browser_assist_run.add_argument("--page-type", default="access_gate", help="Diagnosis page type hint")
    p_browser_assist_run.add_argument("--signal", action="append", default=[], help="Diagnosis signal hint; can be repeated")
    p_browser_assist_run.add_argument("--platform", default="", help="Optional platform label override")
    p_browser_assist_run.add_argument("--max-pages", type=int, default=3, help="Maximum browser-visible target pages")
    p_browser_assist_run.add_argument("--max-chars-per-page", type=int, default=3000, help="Maximum visible characters per page")
    p_browser_assist_run.add_argument("--task-goal", default="", help="Optional host-agent task goal")
    p_browser_assist_run.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_browser_assist_run.add_argument("--json", action="store_true", help="Print normalized JSON instead of Markdown")

    # ── search ──
    p_search = sub.add_parser("search", help="Search the web for agent-ready results")
    p_search.add_argument("query", nargs="?", default="", help="Search query")
    p_search.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT,
                          help="Maximum number of search results")
    p_search.add_argument("--site", default="",
                          help="Restrict search to a domain, e.g. zhihu.com")
    p_search.add_argument("--scope", default="",
                          help="Curated China source scope, e.g. party_central, local_official, ecommerce")
    p_search.add_argument("--list-scopes", action="store_true",
                          help="List curated search scopes and exit")
    p_search.add_argument("--backend", default="auto",
                          help="Search backend: auto, duckduckgo, bing, baidu, wechat-sogou, or plugin:name")
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
                            help="Research preset: general, policy, official, industry, ecommerce, reputation, entertainment, global_entertainment, jp_kr_entertainment, cybersecurity, sports, weather_disaster, science, career, podcast, test_prep, tech, academic, finance, local, company, global_policy, global_reputation, global_industry")
    p_research.add_argument("--list-presets", action="store_true",
                            help="List research presets and exit")
    p_research.add_argument("--limit", type=int, default=None,
                            help="Maximum number of search results; defaults to preset value")
    p_research.add_argument("--site", default="",
                            help="Restrict search to a domain, e.g. zhihu.com")
    p_research.add_argument("--sites", default="",
                            help="Comma-separated domains for site-directed research, e.g. zhihu.com,weibo.com")
    p_research.add_argument("--scope", default="",
                            help="Curated China source scope, e.g. party_central, local_official, ecommerce")
    p_research.add_argument("--search-backend", default="auto",
                            help="Search backend: auto, duckduckgo, bing, baidu, wechat-sogou, or plugin:name")
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
                          help="Research preset: general, policy, official, industry, ecommerce, reputation, cybersecurity, sports, weather_disaster, science, career, podcast, test_prep, tech, academic, finance, local, company, global_policy, global_reputation, global_industry")
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
                         help="Search backend: auto, duckduckgo, bing, baidu, wechat-sogou, or plugin:name")
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
                         help="Source: curated, curated-sources, baidu-rss, wechat-rss, list, or a direct RSS/Atom URL")
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
                         help="Curated RSS keyword filter, or source-catalog query for curated-sources")
    p_feeds.add_argument("--time-filter", choices=["1d", "3d", "1w", "1m", "3m"], default="",
                         help="Curated RSS time window")
    p_feeds.add_argument("--format", choices=["markdown", "json", "context"], default="markdown",
                         help="Output format")
    p_feeds.add_argument("--json", action="store_true",
                         help="Print normalized JSON instead of Markdown")

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
    p_archive_browser_note.add_argument("--from-json", default="", help="JSON/JSONL file or '-' from host-browser visible-page extraction")
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
    p_archive_pack.add_argument("--format", choices=["markdown", "jsonl", "rag-jsonl", "llamaindex-jsonl", "langchain-jsonl", "openwebui-jsonl"], default="markdown", help="Pack format")
    p_archive_pack.add_argument("--output", default="", help="Optional output path; omit to print to stdout")
    p_archive_pack.add_argument("--json", action="store_true", help="Print write summary as JSON when --output is used")
    p_archive_pack.add_argument("--db", default="", help="Optional archive database path")

    p_archive_wiki = archive_sub.add_parser("wiki", help="Build or query a local Agent Wiki from the archive")
    archive_wiki_sub = p_archive_wiki.add_subparsers(dest="wiki_command", help="Archive wiki commands")
    p_archive_wiki_build = archive_wiki_sub.add_parser("build", help="Build a static Markdown/HTML Agent Wiki")
    p_archive_wiki_build.add_argument("--output", default="", help="Output directory; defaults to ~/.guanlan/wiki")
    p_archive_wiki_build.add_argument("--topic", default="", help="Optional topic query to build a focused wiki")
    p_archive_wiki_build.add_argument("--format", choices=["html", "markdown", "both"], default="html", help="Wiki output format")
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
    p_quality_live.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_quality_perf = quality_sub.add_parser("performance", help="Run deterministic performance regression guards")
    p_quality_perf.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")
    p_quality_backend = quality_sub.add_parser("backend-fixtures", help="Run deterministic backend quality fixture guards")
    p_quality_backend.add_argument("--format", choices=["markdown", "json", "jsonl"], default="markdown")

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

    # ── watch ──
    sub.add_parser("watch", help="Quick health check + update check (for scheduled tasks)")

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
    elif args.command == "watch":
        _cmd_watch()
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
    elif args.command == "diagnose":
        _cmd_diagnose(args)
    elif args.command == "browser-assist":
        _cmd_browser_assist(args)
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
    elif args.command == "sources":
        _cmd_sources(args)
    elif args.command in {"prompt", "context"}:
        _cmd_prompt(args)
    elif args.command == "pulse":
        _cmd_pulse(args)
    elif args.command == "feeds":
        _cmd_feeds(args)
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


# ── Command handlers ────────────────────────────────


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
        # douyin/linkedin: manual setup, no auto-install
    }
    COOKIE_CHANNELS = {"twitter", "xueqiu", "bilibili"}

    requested_channels = set()
    if args.channels:
        raw = [c.strip().lower() for c in args.channels.split(",") if c.strip()]
        if "all" in raw:
            requested_channels = set(CHANNEL_INSTALLERS.keys()) | {"xueqiu", "douyin", "linkedin"}
        else:
            requested_channels = set(raw)

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


def _cmd_hotnews(args):
    """Fetch Chinese hotnews from native public sources."""

    from guanlan.config import Config
    from guanlan.hotnews import (
        build_hotnews_brief,
        build_hotnews_snapshot_report,
        build_trend_report,
        fetch_hotnews,
        format_hotnews_brief_markdown,
        format_hotnews_markdown,
        format_snapshot_report_markdown,
        format_trend_report_markdown,
        list_sources,
    )

    source = (args.source or "today").lower()
    if source == "list":
        print(json.dumps(list_sources(), ensure_ascii=False, indent=2))
        return
    snapshot_mode = source == "snapshot"
    if snapshot_mode:
        source = (args.snapshot_source or "today").lower()
        args.trends = args.trends or source == "today"

    if source == "zhihu":
        print(
            "[!] zhihu 热榜是 experimental 源，部分环境会 401/403；失败时请用 "
            '`guanlan search "知乎 热榜 关键词" --site zhihu.com --profile china` 兜底。',
            file=sys.stderr,
        )

    try:
        config = Config()
        newsnow_base_url = args.newsnow_base_url or config.get("newsnow_base_url")
        items = fetch_hotnews(
            source=source,
            limit=max(args.limit, 1),
            backend=args.backend,
            newsnow_base_url=newsnow_base_url,
        )
    except Exception as e:
        if source == "zhihu":
            print(
                "Fallback: guanlan search \"知乎 热榜 关键词\" --site zhihu.com --profile china",
                file=sys.stderr,
            )
        if source.startswith("newsnow:") or args.backend == "newsnow":
            print(
                "NewsNow fallback: try another BASE_URL with "
                "`guanlan configure newsnow-base-url https://your-newsnow.example`.",
                file=sys.stderr,
            )
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        payload = {"items": items}
        trend_report = build_trend_report(items) if (args.trends or args.brief) else None
        if args.trends:
            payload["trend_report"] = trend_report
        if args.brief:
            payload["brief"] = build_hotnews_brief(items, trend_report=trend_report)
        if snapshot_mode or args.watch:
            payload["snapshot"] = build_hotnews_snapshot_report(
                source,
                items,
                save=bool(args.watch),
                path=args.snapshot_db or None,
            )
        expanded_payload = bool(args.trends or args.brief or snapshot_mode or args.watch)
        print(json.dumps(payload if expanded_payload else items, ensure_ascii=False, indent=2))
    else:
        print(format_hotnews_markdown(items, title=f"观澜{'信源快照' if snapshot_mode else '热榜'} / {source}"))
        trend_report = build_trend_report(items) if (args.trends or args.brief) else None
        if args.trends:
            print()
            print(format_trend_report_markdown(trend_report or {}, title=f"观澜趋势归并 / {source}"))
        if args.brief:
            print()
            print(format_hotnews_brief_markdown(build_hotnews_brief(items, trend_report=trend_report), title=f"观澜今日水势简报 / {source}"))
        if snapshot_mode or args.watch:
            print()
            print(
                format_snapshot_report_markdown(
                    build_hotnews_snapshot_report(
                        source,
                        items,
                        save=bool(args.watch),
                        path=args.snapshot_db or None,
                    ),
                    title=f"观澜信源快照 / {source}",
                )
            )


def _cmd_route(args):
    """Explain the soft routing plan for a query."""

    from guanlan.router import build_route_plan, format_route_plan_markdown
    from guanlan.workflow_decider import decide_workflow, format_workflow_decision_markdown

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    plan = build_route_plan(
        args.query,
        preset=args.preset,
        scope=args.scope or None,
        site=args.site or None,
        sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
        profile=args.profile or None,
        limit=max(args.limit, 1),
        read_top=max(args.read_top, 0) if args.read_top is not None else None,
    )
    workflow_decision = decide_workflow(
        args.query,
        command="route",
        preset=args.preset,
        scope=args.scope or None,
        site=args.site or None,
        sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
        profile=args.profile or None,
        limit=max(args.limit, 1),
        read_top=max(args.read_top, 0) if args.read_top is not None else None,
        route_plan=plan,
    )
    if args.json:
        payload = plan.to_dict()
        payload["workflow_decision"] = workflow_decision.to_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_route_plan_markdown(plan))
        print()
        print(format_workflow_decision_markdown(workflow_decision))


def _cmd_workflow(args):
    """Decide whether a task should stay light or use a heavier workflow."""

    from guanlan.workflow_decider import decide_workflow, format_workflow_decision_markdown

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    decision = decide_workflow(
        args.query,
        command=args.workflow_command_context,
        preset=args.preset,
        scope=args.scope or None,
        site=args.site or None,
        sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
        profile=args.profile or None,
        limit=max(args.limit, 1),
        read_top=max(args.read_top, 0) if args.read_top is not None else None,
    )
    if args.json:
        print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_workflow_decision_markdown(decision))


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
        format_browser_assist_adapters_markdown,
        format_browser_assist_markdown,
        format_browser_assist_run_markdown,
        list_browser_assist_adapters,
        run_browser_assist_adapter,
    )

    if args.browser_assist_command == "adapters":
        adapters = list_browser_assist_adapters()
        output_format = "json" if args.json else args.format
        print(json.dumps(adapters, ensure_ascii=False, indent=2) if output_format == "json" else format_browser_assist_adapters_markdown(adapters))
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
        task_goal=args.task_goal,
    )
    if args.platform:
        plan["platform"] = args.platform
        if isinstance(plan.get("browser_assist_task"), dict):
            plan["browser_assist_task"]["platform"] = args.platform
    output_format = "json" if args.json else args.format
    print(json.dumps(plan, ensure_ascii=False, indent=2) if output_format == "json" else format_browser_assist_markdown(plan))


def _cmd_search(args):
    """Search the web and format results for agents."""

    from guanlan.search_sources import list_search_scopes
    from guanlan.webtools import (
        format_search_context,
        format_search_markdown,
        format_search_prompt,
        format_search_trace,
        format_source_chart,
        search_web,
    )

    if getattr(args, "list_scopes", False):
        print(json.dumps(list_search_scopes(), ensure_ascii=False, indent=2))
        return
    if not args.query:
        print("Error: query is required unless --list-scopes is used", file=sys.stderr)
        sys.exit(2)

    try:
        results = search_web(
            args.query,
            limit=max(args.limit, 1),
            site=args.site or None,
            scope=args.scope or None,
            backend=args.backend,
            profile=args.profile or None,
            network_mode=args.network,
            trace=args.trace,
            cluster_threshold=args.cluster_threshold,
            cache_ttl=max(args.cache_ttl, 0),
            use_cache=not args.no_cache,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    _auto_feedback_for_search(args, results)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        diagnostics = getattr(results, "diagnostics", None)
        if diagnostics and not results:
            print(json.dumps({"results": [], "diagnostics": diagnostics}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(results, ensure_ascii=False, indent=2))
    elif output_format == "context":
        suffix = f" / {args.scope}" if args.scope else ""
        print(format_search_context(results, title=f"观澜搜索上下文{suffix} / {args.query}"))
        if args.source_chart:
            print(format_source_chart(results))
    elif output_format == "prompt":
        suffix = f" / {args.scope}" if args.scope else ""
        print(format_search_prompt(results, query=args.query, title=f"观澜搜索 Prompt{suffix}"))
    else:
        suffix = f" / {args.scope}" if args.scope else ""
        print(format_search_markdown(results, title=f"观澜搜索{suffix} / {args.query}"))
        if args.trace:
            print(format_search_trace(results))
        if args.source_chart:
            print(format_source_chart(results))


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
    # Default-on to avoid missing agent wrappers that don't expose runtime markers.
    # Can still be disabled explicitly via GUANLAN_AUTO_FEEDBACK=0 or telemetry off.
    telemetry_env = _normalized_bool(os.environ.get("GUANLAN_TELEMETRY"))
    if telemetry_env is False:
        return False
    with contextlib.suppress(Exception):
        from guanlan.config import Config

        config = Config()
        telemetry_cfg = _normalized_bool(config.get("telemetry_enabled", True))
        if telemetry_cfg is False:
            return False
    return True


def _submit_auto_feedback(query, reason, *, command, profile, backend):
    if not _auto_feedback_enabled():
        return
    query = str(query or "").strip()
    reason = str(reason or "").strip()
    if not query or not reason:
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


def _cmd_research(args):
    """Build an agent-ready research evidence packet."""

    from guanlan.router import format_route_chart
    from guanlan.webtools import (
        build_research_packet,
        format_advisor_context,
        format_evidence_audit_context,
        format_freshness_guard_markdown,
        format_research_markdown,
        format_research_prompt,
        format_search_context,
        format_source_chart,
        format_source_mix_guard_markdown,
        list_research_presets,
    )

    if getattr(args, "list_presets", False):
        print(json.dumps(list_research_presets(), ensure_ascii=False, indent=2))
        return
    if not args.query:
        print("Error: query is required unless --list-presets is used", file=sys.stderr)
        sys.exit(2)

    try:
        packet = build_research_packet(
            args.query,
            preset=args.preset,
            limit=max(args.limit, 1) if args.limit is not None else None,
            site=args.site or None,
            sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
            scope=args.scope or None,
            search_backend=args.search_backend,
            profile=args.profile or None,
            read_top=max(args.read_top, 0) if args.read_top is not None else None,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            advisor=args.advisor,
            advisor_style=args.advisor_style,
            select_top=max(args.select_top, 0) if args.select_top is not None else None,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    _auto_feedback_for_research(args, packet)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    elif output_format == "context":
        evidence = packet.get("selected_evidence") or packet.get("results", [])
        print(format_search_context(evidence, title=f"观澜研究上下文 / {args.query}"))
        if isinstance(packet.get("evidence_audit"), dict):
            print()
            print(format_evidence_audit_context(packet["evidence_audit"]))
        if isinstance(packet.get("freshness_guard"), dict):
            print()
            print(format_freshness_guard_markdown(packet["freshness_guard"]))
        if isinstance(packet.get("source_mix_guard"), dict):
            print()
            print(format_source_mix_guard_markdown(packet["source_mix_guard"]))
        if args.advisor and isinstance(packet.get("advisor"), dict):
            print()
            print(format_advisor_context(packet["advisor"]))
        if args.source_chart:
            print(format_source_chart(packet.get("results", [])))
        if args.route_chart:
            print(format_route_chart(packet.get("route_plan", {})))
    elif output_format == "prompt":
        print(format_research_prompt(packet, style=args.prompt_style))
    else:
        print(format_research_markdown(packet))
        if args.source_chart:
            print(format_source_chart(packet.get("results", [])))
        if args.route_chart:
            print(format_route_chart(packet.get("route_plan", {})))


def _cmd_investigate(args):
    """Run an explicit upper-layer investigation workflow."""

    from guanlan.investigation import (
        build_investigation_packet,
        format_investigation_context,
        format_investigation_markdown,
    )

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    try:
        packet = build_investigation_packet(
            args.query,
            preset=args.preset,
            profile=args.profile or None,
            limit=max(args.limit, 1) if args.limit is not None else None,
            read_top=max(args.read_top, 0) if args.read_top is not None else None,
            budget=args.budget,
            dry_run=bool(args.dry_run),
            search_backend=args.search_backend,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            advisor=not bool(args.no_advisor),
            advisor_style=args.advisor_style,
            select_top=max(args.select_top, 0) if args.select_top is not None else None,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_investigation_context(packet))
    else:
        print(format_investigation_markdown(packet))


def _cmd_recipe(args):
    """Render reusable research recipe plans for agents."""

    from guanlan.recipes import (
        build_recipe_plan,
        format_recipe_json,
        format_recipe_list_markdown,
        format_recipe_plan_markdown,
        get_recipe,
        list_recipes,
    )

    command = getattr(args, "recipe_command", None)
    if not command:
        print(format_recipe_list_markdown())
        return
    try:
        if command == "list":
            recipes = list_recipes()
            print(format_recipe_json(recipes) if args.json else format_recipe_list_markdown(recipes))
            return
        if command == "show":
            recipe = get_recipe(args.recipe_id).to_dict()
            print(format_recipe_json(recipe) if args.json else format_recipe_list_markdown([recipe]))
            return
        if command == "run":
            if not args.query:
                print("Error: query is required", file=sys.stderr)
                sys.exit(2)
            plan = build_recipe_plan(
                args.recipe_id,
                args.query,
                profile=args.profile,
                limit=max(args.limit, 1),
                read_top=args.read_top,
            )
            print(format_recipe_json(plan) if args.json else format_recipe_plan_markdown(plan))
            return
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"Error: unknown recipe command: {command}", file=sys.stderr)
    sys.exit(2)


def _cmd_sources(args):
    """Inspect Guanlan's read-only source registry."""

    from guanlan.source_registry import (
        audit_source_registry,
        explain_sources,
        export_source_registry,
        format_source_audit_markdown,
        format_source_explain_markdown,
        format_source_registry_export_json,
        format_source_show_markdown,
        format_sources_markdown,
        list_source_cards,
        show_source,
    )

    command = getattr(args, "sources_command", None)
    if command == "list":
        rows = list_source_cards(scope=args.scope or None, limit=max(args.limit, 1))
        if args.format == "json":
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            suffix = f" / {args.scope}" if args.scope else ""
            print(format_sources_markdown(rows, title=f"观澜信源矩阵{suffix}"))
        return
    if command == "show":
        payload = show_source(args.target)
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(format_source_show_markdown(payload))
        return
    if command == "explain":
        if not args.query:
            print("Error: query is required", file=sys.stderr)
            sys.exit(2)
        payload = explain_sources(args.query, profile=args.profile or None, limit=max(args.limit, 1))
        if getattr(args, "trace", False):
            payload["trace"] = {
                "adapter": "source-registry-2.0",
                "network": "not_used",
                "boundary": payload.get("boundary", ""),
            }
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(format_source_explain_markdown(payload))
        return
    if command == "audit":
        report = audit_source_registry()
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_source_audit_markdown(report))
        return
    if command == "export":
        print(format_source_registry_export_json(export_source_registry()))
        return
    print("Error: sources command is required: list, show, explain, audit, or export", file=sys.stderr)
    sys.exit(2)


def _cmd_compare(args):
    """Compare multiple subjects through Guanlan evidence packets."""
    from guanlan.research_workflows import (
        build_compare_report,
        format_compare_markdown,
        format_workflow_context,
    )

    try:
        report = build_compare_report(
            list(args.subjects or []),
            focus=args.focus,
            preset=args.preset,
            profile=args.profile,
            limit=max(args.limit, 1),
            read_top=max(args.read_top, 0),
            search_backend=args.search_backend,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            select_top=max(args.select_top, 1),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_workflow_context(report, title="观澜对比研究上下文"))
    else:
        print(format_compare_markdown(report))


def _cmd_timeline(args):
    """Build a dated timeline from Guanlan evidence."""
    from guanlan.research_workflows import (
        build_timeline_report,
        format_timeline_markdown,
        format_workflow_context,
    )

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)
    try:
        report = build_timeline_report(
            args.query,
            preset=args.preset,
            profile=args.profile,
            limit=max(args.limit, 1),
            read_top=max(args.read_top, 0),
            search_backend=args.search_backend,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            max_events=max(args.max_events, 1),
            order=args.order,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_workflow_context(report, title="观澜时间线上下文"))
    else:
        print(format_timeline_markdown(report))


def _cmd_dossier(args):
    """Build a structured Guanlan dossier for one entity."""
    from guanlan.research_workflows import (
        build_dossier_report,
        format_dossier_markdown,
        format_workflow_context,
    )

    if not args.entity:
        print("Error: entity is required", file=sys.stderr)
        sys.exit(2)
    try:
        report = build_dossier_report(
            args.entity,
            focus=args.focus,
            preset=args.preset,
            profile=args.profile,
            limit=max(args.limit, 1),
            read_top=max(args.read_top, 0),
            search_backend=args.search_backend,
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1) if args.max_read_chars is not None else None,
            select_top=max(args.select_top, 1),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_workflow_context(report, title="观澜研究档案上下文"))
    else:
        print(format_dossier_markdown(report))


def _cmd_prompt(args):
    """Build a local-LLM prompt from a broad Guanlan research packet."""

    from guanlan.webtools import build_research_packet, format_research_prompt

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)

    try:
        packet = build_research_packet(
            args.query,
            preset=args.preset,
            limit=max(args.limit or DEFAULT_RESEARCH_LIMIT, 1),
            site=args.site or None,
            sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
            scope=args.scope or None,
            search_backend=args.search_backend,
            profile=args.profile or None,
            read_top=max(args.read_top, 0),
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1),
            advisor=args.advisor,
            advisor_style=args.advisor_style,
            select_top=max(args.select_top, 1),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(format_research_prompt(packet, style=args.style))


def _cmd_pulse(args):
    """Analyze public topic echo with explicit caveats."""

    from guanlan.pulse import (
        build_pulse_report,
        format_pulse_context,
        format_pulse_markdown,
    )

    if not args.query:
        print("Error: query is required", file=sys.stderr)
        sys.exit(2)

    try:
        report = build_pulse_report(
            args.query,
            limit=max(args.limit, 1),
            site=args.site or None,
            sites=[s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None,
            scope=args.scope or None,
            backend=args.backend,
            profile=args.profile or None,
            read_top=max(args.read_top, 0),
            read_backend=args.read_backend,
            max_read_chars=max(args.max_read_chars, 1),
            cache_ttl=max(args.cache_ttl, 0),
            use_cache=not args.no_cache,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif output_format == "context":
        print(format_pulse_context(report))
    else:
        print(format_pulse_markdown(report))


def _cmd_feeds(args):
    """Discover content and source catalogs from public RSS/OPML."""

    from guanlan.feeds import (
        fetch_feed_source,
        format_feed_catalog_markdown,
        format_feed_items_context,
        format_feed_items_markdown,
        format_feed_sources_markdown,
        format_json,
        list_curated_sources,
        list_feed_sources,
        resolve_feed_source,
    )

    source = resolve_feed_source(args.source or "curated")
    limit = min(max(args.limit, 1), MAX_FEEDS_LIMIT)
    output_format = "json" if args.json else args.format

    try:
        if source == "list":
            catalog = list_feed_sources()
            if output_format == "json":
                print(format_json(catalog))
            else:
                print(format_feed_catalog_markdown(catalog))
            return
        if source == "curated-sources":
            sources = list_curated_sources(limit=limit, query=args.keyword or None)
            if output_format == "json":
                print(format_json(sources))
            else:
                suffix = f" / {args.keyword}" if args.keyword else ""
                print(format_feed_sources_markdown(sources, title=f"观澜 RSS 源目录 / 精品源{suffix}"))
            return
        items = fetch_feed_source(
            source,
            limit=limit,
            language=args.language,
            category=args.category or None,
            resource_type=args.resource_type or None,
            featured=args.featured,
            min_score=args.min_score,
            keyword=args.keyword or None,
            time_filter=args.time_filter or None,
        )
        source_titles = {
            "curated": "精品内容流",
            "baidu-rss": "百度实时热点 RSS",
            "wechat-rss": "微信热门文章 RSS",
        }
        title = f"观澜内容发现 / {source_titles.get(source, 'RSS')}"
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if output_format == "json":
        print(format_json(items))
    elif output_format == "context":
        print(format_feed_items_context(items, title=f"{title} 上下文"))
    else:
        print(format_feed_items_markdown(items, title=title))


def _cmd_read(args):
    """Read a URL and print Markdown for agents."""

    from guanlan.webtools import (
        format_read_batch_context,
        format_read_batch_markdown,
        format_read_batch_prompt,
        format_read_context,
        format_read_prompt,
        format_read_quality_report,
        format_read_trace,
        read_batch,
        read_url,
        read_url_with_trace,
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
        if args.trace or args.quality_report:
            read_packet = read_url_with_trace(
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
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif args.format == "context":
            print(format_read_context(content, url=args.url))
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
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _read_quality_kwargs(args) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    if getattr(args, "strict", False):
        kwargs["strict"] = True
    if getattr(args, "extract", "article") != "article":
        kwargs["extract"] = args.extract
    return kwargs


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

    # NOTE: twitter-cli, weibo, xiaoyuzhou, wechat, xhs-cli etc. are optional.
    # They are installed via --channels flag, not here.
    # See CHANNEL_INSTALLERS in _cmd_install().


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

    # NOTE: xhs-cli is now optional, installed via --channels=xiaohongshu


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


def _parse_twitter_cookie_input(value: str):
    """Parse Twitter cookie input from either separate values or a cookie header."""
    auth_token = None
    ct0 = None

    if "auth_token=" in value and "ct0=" in value:
        # Full cookie string — parse it.
        for part in value.replace(";", " ").split():
            if part.startswith("auth_token="):
                auth_token = part.split("=", 1)[1]
            elif part.startswith("ct0="):
                ct0 = part.split("=", 1)[1]
    elif len(value.split()) == 2 and "=" not in value:
        # Two separate values: AUTH_TOKEN CT0.
        parts = value.split()
        auth_token = parts[0]
        ct0 = parts[1]

    return auth_token, ct0


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

    # Keep doctor read-only. Skill installation is explicit via `guanlan skill --install`.


def _print_update_notice_if_available(printer=print) -> None:
    """Print a best-effort update notice without affecting command success."""
    try:
        from guanlan import __version__
        from guanlan.update_check import format_update_notice, get_update_info

        info = get_update_info(__version__)
        if info:
            printer("")
            printer(format_update_notice(info))
    except Exception:
        return


def _should_show_background_update_notice(args) -> bool:
    command = str(getattr(args, "command", "") or "")
    return command in {
        "search",
        "read",
        "research",
        "hotnews",
        "route",
        "compare",
        "timeline",
        "dossier",
        "prompt",
        "context",
        "pulse",
        "feeds",
        "status",
    }


def _print_background_update_notice_if_available(args) -> None:
    """Print a compact stderr-only update notice for routine agent commands."""
    if not _should_show_background_update_notice(args):
        return
    try:
        from guanlan import __version__
        from guanlan.update_check import cached_update_info, format_compact_update_notice

        info = cached_update_info(__version__, timeout=0.8)
        if not info:
            return
        print("", file=sys.stderr)
        print(format_compact_update_notice(info), file=sys.stderr)
    except Exception:
        return


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


def _classify_update_error(exc):
    """Classify update-check errors for user-friendly diagnostics."""
    import requests

    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        msg = str(exc).lower()
        dns_markers = [
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname",
            "getaddrinfo failed",
            "name resolution",
            "dns",
        ]
        if any(marker in msg for marker in dns_markers):
            return "dns"
        return "connection"
    if isinstance(exc, requests.exceptions.HTTPError):
        return "http"
    return "unknown"


def _update_error_text(kind):
    """Map internal error kinds to user-facing text."""
    mapping = {
        "timeout": "网络超时",
        "dns": "DNS 解析失败",
        "rate_limit": "GitHub API 速率限制",
        "connection": "网络连接失败",
        "server_error": "GitHub 服务暂时不可用",
        "http": "HTTP 请求失败",
        "unknown": "未知网络错误",
    }
    return mapping.get(kind, "请求失败")


def _classify_github_response_error(resp):
    """Classify non-200 GitHub responses that merit special handling."""
    if resp is None:
        return "unknown"
    if resp.status_code == 429:
        return "rate_limit"
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "")
        if remaining == "0":
            return "rate_limit"
        try:
            message = resp.json().get("message", "").lower()
            if "rate limit" in message:
                return "rate_limit"
        except Exception:
            pass
    if 500 <= resp.status_code < 600:
        return "server_error"
    return None


def _github_get_with_retry(url, timeout=10, retries=3, sleeper=time.sleep):
    """GET GitHub API with retry/backoff and basic error classification."""
    import requests

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            if attempt >= retries:
                return None, _classify_update_error(exc), attempt
            sleeper(2 ** (attempt - 1))
            continue

        err_kind = _classify_github_response_error(resp)
        if err_kind in ("rate_limit", "server_error"):
            if attempt >= retries:
                return None, err_kind, attempt
            delay = 2 ** (attempt - 1)
            retry_after = resp.headers.get("Retry-After")
            if err_kind == "rate_limit" and retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except Exception:
                    pass
            sleeper(delay)
            continue

        return resp, None, attempt

    return None, "unknown", retries


def _cmd_check_update():
    """Check for newer versions when a public release repo is configured."""
    from guanlan import __version__
    from guanlan.update_check import format_update_notice, get_update_info

    print(f"当前版本: v{__version__}")
    repo = os.environ.get("GUANLAN_UPDATE_REPO", "").strip()
    if not repo:
        info = get_update_info(__version__, timeout=3.0)
        if info:
            print(format_update_notice(info))
            return "update_available"
        print("✅ 已是最新版本，或暂时无法访问 PyPI。")
        return "up_to_date"

    release_url = f"https://api.github.com/repos/{repo}/releases/latest"
    commit_url = f"https://api.github.com/repos/{repo}/commits/main"

    # Fetch latest release with retry/backoff.
    resp, err, attempts = _github_get_with_retry(release_url, timeout=10, retries=3)
    if err:
        print(f"[!] 无法检查更新（{_update_error_text(err)}，已重试 {attempts} 次）")
        return "error"

    if resp.status_code == 200:
        data = resp.json()
        latest = data.get("tag_name", "").lstrip("v")
        body = data.get("body", "")

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


def _cmd_watch():
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
    from guanlan.webtools import cache_summary

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


if __name__ == "__main__":
    main()
