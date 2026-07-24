#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate Guanlan's reproducible public quality report."""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guanlan import __version__, evaluation, quality
from guanlan.live_smoke_history import (
    DEFAULT_LIVE_SMOKE_HISTORY_PATH,
    build_live_smoke_trend,
    read_live_smoke_history,
)
from scripts.reliability_guard import load_baseline

ROOT = Path(__file__).resolve().parents[1]

HIGH_RISK_ROUTING_GROUPS: dict[str, tuple[str, ...]] = {
    "finance": ("finance",),
    "legal_policy": ("policy",),
    "entertainment": ("entertainment",),
    "education_university": ("education", "test_prep", "university"),
    "sports_local_life": ("local_life", "sports", "transport"),
    "tech_wps": ("tech", "wps_office"),
}


def build_quality_report(*, include_distribution: bool = False, live_smoke_history_path: str | Path | None = None) -> dict[str, Any]:
    """Build a deterministic report; live signals are history-only unless explicitly enabled."""

    benchmark = evaluation.run_benchmark(mode="quick", limit=50)
    eval_suite = evaluation.run_eval_suite("chinese-web-v1", mode="quick", limit=80)
    routing = build_routing_regression_inventory()
    quality_signals = build_quality_signals()
    reliability_baseline = build_reliability_baseline_section()
    live_smoke = build_live_smoke_section(live_smoke_history_path)
    distribution = build_distribution_section(include_distribution=include_distribution)
    legacy_inventory = build_legacy_inventory()
    return {
        "schema_version": "guanlan_quality_report_v1",
        "generated_at": _utc_now(),
        "version": __version__,
        "benchmark": _compact_benchmark(benchmark),
        "eval_suite": _compact_eval_suite(eval_suite),
        "routing_regression": routing,
        "live_smoke": live_smoke,
        "quality_signals": quality_signals,
        "reliability_baseline": reliability_baseline,
        "distribution": distribution,
        "legacy_inventory": legacy_inventory,
        "principles": {
            "deterministic": "benchmark/eval/routing/quality sections avoid live network by default.",
            "live_boundary": "live-smoke trend is diagnostic evidence, not proof that a topic has no results.",
            "distribution_boundary": "pip local TLS errors are classified separately from PyPI stale-version evidence.",
        },
    }


def build_routing_regression_inventory(fixture: Path | None = None) -> dict[str, Any]:
    path = fixture or (ROOT / "tests" / "fixtures" / "routing_regression_cases.jsonl")
    cases = _load_jsonl(path)
    categories: dict[str, Counter[str]] = defaultdict(Counter)
    expected_fields = Counter()
    forbidden_fields = Counter()
    for case in cases:
        categories[str(case.get("category") or "uncategorized")][str(case.get("case_type") or "unknown")] += 1
        for key in case:
            if key.startswith("expected_"):
                expected_fields[key] += 1
            if key.startswith("forbidden_"):
                forbidden_fields[key] += 1
    high_risk = {}
    missing: list[str] = []
    for group, group_categories in HIGH_RISK_ROUTING_GROUPS.items():
        counts = Counter()
        for case in cases:
            if str(case.get("category") or "") in group_categories:
                counts[str(case.get("case_type") or "unknown")] += 1
        has_floor = counts.get("positive", 0) > 0 and counts.get("near_miss", 0) > 0
        high_risk[group] = {
            "categories": list(group_categories),
            "case_types": dict(sorted(counts.items())),
            "coverage_floor": "pass" if has_floor else "fail",
            "minimum": "positive + near_miss",
        }
        if not has_floor:
            missing.append(group)
    return {
        "fixture": str(path.relative_to(ROOT)),
        "total_cases": len(cases),
        "category_distribution": {key: dict(sorted(value.items())) for key, value in sorted(categories.items())},
        "case_type_distribution": dict(sorted(Counter(str(item.get("case_type") or "unknown") for item in cases).items())),
        "expected_field_usage": dict(sorted(expected_fields.items())),
        "forbidden_field_usage": dict(sorted(forbidden_fields.items())),
        "high_risk_coverage": high_risk,
        "missing_high_risk_coverage": missing,
        "rule_inventory": _routing_rule_inventory(cases),
    }


def build_quality_signals() -> dict[str, Any]:
    reports = {
        "foundational": quality.run_foundational_checks(mode="quick", limit=50),
        "coverage": quality.run_coverage_checks(mode="quick", limit=50),
        "regression": quality.run_regression_checks(mode="quick", limit=50),
        "robustness": quality.run_robustness_checks(mode="quick", limit=50),
        "backend_fixtures": quality.run_backend_fixture_checks(),
        "performance": quality.run_performance_checks(),
    }
    return {
        name: {
            "mode": report.get("mode", "quick"),
            "summary": report.get("summary") or {},
            "failed_checks": _check_ids(report, "fail"),
            "warned_checks": _check_ids(report, "warn"),
        }
        for name, report in reports.items()
    }


def build_reliability_baseline_section() -> dict[str, Any]:
    """Expose the deterministic no-regression contract without re-running it."""

    baseline = load_baseline()
    return {
        "status": "configured",
        "reference_version": baseline.get("reference_version"),
        "checks": baseline.get("checks") or {},
        "boundary": baseline.get("boundary"),
    }


def build_live_smoke_section(history_path: str | Path | None = None, *, window: int = 10) -> dict[str, Any]:
    path = Path(history_path).expanduser() if history_path else DEFAULT_LIVE_SMOKE_HISTORY_PATH
    history = read_live_smoke_history(path)
    if not history:
        return {
            "status": "no_history",
            "history_path": _display_path(path),
            "runs_considered": 0,
            "boundary": "未发现本地 live-smoke 历史；公开报告不伪造公网实时分数。",
        }
    trend = build_live_smoke_trend(history, window=window)
    return {
        "status": "history",
        "history_path": _display_path(path),
        "runs_available": len(history),
        "trend_window": window,
        "trend": trend,
        "boundary": "live-smoke 趋势用于识别公网/源站/后端漂移，默认不作为 release blocker。",
    }


def build_distribution_section(*, include_distribution: bool = False) -> dict[str, Any]:
    if not include_distribution:
        return {
            "status": "not_probed",
            "boundary": "默认报告不触网；运行 scripts/distribution_status.py 可单独验证 GitHub/PyPI/Homebrew/官网。",
        }
    from scripts.distribution_status import build_distribution_report

    return build_distribution_report(__version__)


def build_legacy_inventory(path: Path | None = None) -> dict[str, Any]:
    legacy_path = path or (ROOT / "guanlan" / "web" / "_legacy_web_impl.py")
    source = legacy_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    buckets: dict[str, list[str]] = defaultdict(list)
    for name in functions:
        buckets[_legacy_bucket(name)].append(name)
    compatibility = _legacy_compatibility_seams()
    return {
        "file": str(legacy_path.relative_to(ROOT)),
        "loc": source.count("\n") + 1,
        "top_level_functions": len(functions),
        "buckets": {key: sorted(value) for key, value in sorted(buckets.items())},
        "compatibility_seams": compatibility,
        "guardrail": "legacy 层只保留兼容承载；新增业务逻辑应落到 split owner 模块。",
    }


def render_markdown(report: dict[str, Any]) -> str:
    benchmark = report["benchmark"]
    suite = report["eval_suite"]
    routing = report["routing_regression"]
    quality_signals = report["quality_signals"]
    reliability_baseline = report["reliability_baseline"]
    live = report["live_smoke"]
    distribution = report["distribution"]
    legacy = report["legacy_inventory"]
    lines = [
        "# Guanlan Public Quality Report / 观澜公开质量报告",
        "",
        f"- 版本: `v{report['version']}`",
        f"- 生成时间: `{report['generated_at']}`",
        "- 口径: 确定性基准、评测套件、路由回归和质量门禁默认不触网；公网漂移只从 live-smoke 历史读取。",
        "",
        "## 1. Deterministic Benchmark",
        "",
        f"- 场景数: {benchmark['summary'].get('total')}",
        f"- 结果: pass={benchmark['summary'].get('pass')} warn={benchmark['summary'].get('warn')} fail={benchmark['summary'].get('fail')}",
        f"- 分数: {benchmark['summary'].get('score')}",
        f"- 失败样例: {', '.join(benchmark['failed_case_ids']) or '无'}",
        "",
        "## 2. Eval Suite chinese-web-v1",
        "",
        f"- 任务数: {suite['summary'].get('total')}",
        f"- 结果: pass={suite['summary'].get('pass')} warn={suite['summary'].get('warn')} fail={suite['summary'].get('fail')}",
        f"- 分数: {suite['summary'].get('score')}",
        "- 类别分布:",
    ]
    for category, summary in sorted((suite.get("category_summary") or {}).items()):
        lines.append(
            f"  - `{category}`: total={summary.get('total')} pass={summary.get('pass')} warn={summary.get('warn')} fail={summary.get('fail')}"
        )
    lines.extend(
        [
            "",
            "## 3. Routing Regression Inventory",
            "",
            f"- 夹具: `{routing['fixture']}`",
            f"- 总数: {routing['total_cases']}",
            f"- Case types: {json.dumps(routing['case_type_distribution'], ensure_ascii=False, sort_keys=True)}",
            "- 高风险类目覆盖:",
        ]
    )
    for group, item in routing["high_risk_coverage"].items():
        lines.append(f"  - `{group}`: {item['coverage_floor']} {json.dumps(item['case_types'], ensure_ascii=False, sort_keys=True)}")
    lines.extend(
        [
            f"- 覆盖缺口: {', '.join(routing['missing_high_risk_coverage']) or '无'}",
            "",
            "## 4. Quality Gate Signals",
            "",
            "| Gate | pass | warn | fail | score |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, item in quality_signals.items():
        summary = item.get("summary") or {}
        lines.append(
            f"| `{name}` | {summary.get('pass', 0)} | {summary.get('warn', 0)} | {summary.get('fail', 0)} | {summary.get('score', 0)} |"
        )
    lines.extend(
        [
            "",
            "## 5. Deterministic Reliability Baseline",
            "",
            f"- 状态: `{reliability_baseline.get('status')}`",
            f"- 参考版本: `v{reliability_baseline.get('reference_version')}`",
            f"- 保护项: {', '.join(sorted(reliability_baseline.get('checks') or {}))}",
            f"- 边界: {reliability_baseline.get('boundary')}",
            "",
            "## 6. Live Smoke Trend",
            "",
            f"- 状态: `{live.get('status')}`",
            f"- 历史路径: `{live.get('history_path')}`",
            f"- 边界: {live.get('boundary')}",
            "",
            "## 7. Distribution Surface",
            "",
            f"- 状态: `{distribution.get('status')}`",
            f"- 边界: {distribution.get('boundary', '见 distribution_status_v1 明细。')}",
            "",
            "## 8. Legacy Inventory",
            "",
            f"- 文件: `{legacy['file']}`",
            f"- LOC: {legacy['loc']}",
            f"- 顶层函数: {legacy['top_level_functions']}",
            f"- 显式兼容入口: {', '.join(legacy['compatibility_seams']['entrypoints']) or '无'}",
            f"- 同步函数: `{legacy['compatibility_seams']['sync_function']}`",
            "- 分桶:",
        ]
    )
    for bucket, names in legacy["buckets"].items():
        lines.append(f"  - `{bucket}`: {len(names)}")
    lines.append("")
    lines.append("## Boundary")
    lines.append("")
    lines.append("- 确定性通过不代表公网实时一定可用；公网阻断、ICP/403、搜索后端漂移需要看 live-smoke 和 distribution status。")
    lines.append("- pip 本机证书错误会标成 `local_tls_error`，不等同于 PyPI 仍是旧版。")
    lines.append("- legacy inventory 是后续拆分清单，不是新增功能承诺。")
    return "\n".join(lines) + "\n"


def write_report(
    *,
    markdown_output: Path | None = None,
    json_output: Path | None = None,
    include_distribution: bool = False,
    live_smoke_history_path: str | Path | None = None,
) -> dict[str, Any]:
    report = build_quality_report(
        include_distribution=include_distribution,
        live_smoke_history_path=live_smoke_history_path,
    )
    if markdown_output:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(render_markdown(report), encoding="utf-8")
    if json_output:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _compact_benchmark(report: dict[str, Any]) -> dict[str, Any]:
    cases = report.get("cases") or []
    return {
        "mode": report.get("mode"),
        "limit": report.get("limit"),
        "summary": report.get("summary") or {},
        "failed_case_ids": [str(item.get("id")) for item in cases if item.get("status") == "fail"],
        "warned_case_ids": [str(item.get("id")) for item in cases if item.get("status") == "warn"],
        "principle": report.get("principle"),
    }


def _compact_eval_suite(report: dict[str, Any]) -> dict[str, Any]:
    cases = report.get("cases") or []
    return {
        "suite_id": (report.get("suite") or {}).get("id"),
        "mode": report.get("mode"),
        "limit": report.get("limit"),
        "summary": report.get("summary") or {},
        "category_summary": report.get("category_summary") or {},
        "failed_case_ids": [str(item.get("id")) for item in cases if item.get("status") == "fail"],
        "warned_case_ids": [str(item.get("id")) for item in cases if item.get("status") == "warn"],
        "boundary": report.get("boundary"),
    }


def _routing_rule_inventory(cases: list[dict[str, Any]]) -> dict[str, Any]:
    intent_rules = Counter()
    scope_rules = Counter()
    site_rules = Counter()
    demotion_rules = Counter()
    for case in cases:
        for key in ("expected_intents", "expected_intents_any"):
            intent_rules.update(_as_list(case.get(key)))
        intent_rules.update(f"!{item}" for item in _as_list(case.get("forbidden_intents")))
        for key in ("expected_scopes", "expected_scopes_any"):
            scope_rules.update(_as_list(case.get(key)))
        scope_rules.update(f"!{item}" for item in _as_list(case.get("forbidden_scopes")))
        site_rules.update(_as_list(case.get("expected_sites_contains")))
        demotion_rules.update(_as_list(case.get("forbidden_command_contains")))
    return {
        "intent_rules": dict(sorted(intent_rules.items())),
        "scope_rules": dict(sorted(scope_rules.items())),
        "site_rules": dict(sorted(site_rules.items())),
        "demotion_rules": dict(sorted(demotion_rules.items())),
    }


def _legacy_bucket(name: str) -> str:
    lowered = name.lower()
    if "render" in lowered or "format" in lowered:
        return "renderers"
    if "research" in lowered or "advisor" in lowered or "dossier" in lowered or "timeline" in lowered or "compare" in lowered:
        return "research"
    if "read" in lowered or "fetch" in lowered or "html" in lowered or "page" in lowered:
        return "read"
    if "search" in lowered or "bing" in lowered or "baidu" in lowered or "duck" in lowered or "rank" in lowered or "dedupe" in lowered:
        return "search"
    if "sync" in lowered or "legacy" in lowered or "compat" in lowered or lowered.startswith("_"):
        return "compat"
    return "other"


def _legacy_compatibility_seams() -> dict[str, Any]:
    """Expose the remaining legacy bridge instead of hiding global sync."""

    impl_path = ROOT / "guanlan" / "web" / "_impl.py"
    source = impl_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    entrypoints: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "_SYNC_ENTRYPOINTS" for target in node.targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (TypeError, ValueError):
            value = ()
        if isinstance(value, (set, tuple, list)):
            entrypoints = sorted(str(item) for item in value)
        break
    return {
        "module": str(impl_path.relative_to(ROOT)),
        "sync_function": "_sync_legacy_overrides",
        "entrypoints": entrypoints,
        "owner_rule": "兼容同步只允许存在于 guanlan.web._impl；新 owner 模块不得新增 direct legacy import。",
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            rows.append(json.loads(text))
    return rows


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _check_ids(report: dict[str, Any], status: str) -> list[str]:
    return [str(item.get("id") or "") for item in report.get("checks") or [] if item.get("status") == status]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    """Render optional local history paths without exposing a user directory."""

    try:
        return "~/" + str(path.resolve().relative_to(Path.home().resolve()))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Guanlan's reproducible quality report.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", default="docs/benchmark-report.md")
    parser.add_argument("--json-output", default="docs/reports/latest-quality.json")
    parser.add_argument("--include-distribution", action="store_true", help="Probe live distribution surfaces.")
    parser.add_argument("--live-smoke-history-path", default="", help="Optional live-smoke history JSONL path.")
    args = parser.parse_args(argv)

    output = Path(args.output)
    json_output = Path(args.json_output) if args.json_output else None
    history_path = args.live_smoke_history_path or None
    if args.format == "json":
        report = write_report(
            json_output=output,
            include_distribution=args.include_distribution,
            live_smoke_history_path=history_path,
        )
        if json_output and json_output != output:
            json_output.parent.mkdir(parents=True, exist_ok=True)
            json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        write_report(
            markdown_output=output,
            json_output=json_output,
            include_distribution=args.include_distribution,
            live_smoke_history_path=history_path,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
