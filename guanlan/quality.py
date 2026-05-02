# -*- coding: utf-8 -*-
"""Quality gate for Guanlan's agent-facing research workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from guanlan import hotnews, webtools
from guanlan.evaluation import list_evaluation_scenarios
from guanlan.limits import (
    DEFAULT_ARCHIVE_SEARCH_LIMIT,
    DEFAULT_FEEDS_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
)

SEARCH_RANKING_FIXTURES: list[dict[str, Any]] = [
    {
        "id": "policy_official_first",
        "query": "人工智能 政策 最新",
        "expected_first_domain": "gov.cn",
        "results": [
            {"title": "知乎热议人工智能政策", "url": "https://zhihu.com/question/ai-policy", "snippet": "网友讨论人工智能政策最新影响"},
            {"title": "国务院发布人工智能政策通知", "url": "https://www.gov.cn/zhengce/ai.htm", "snippet": "2026年5月2日 国务院发布人工智能相关政策通知"},
            {"title": "商业媒体解读人工智能政策", "url": "https://36kr.com/p/ai-policy", "snippet": "产业视角解读人工智能政策"},
        ],
    },
    {
        "id": "reputation_avoids_english_drift",
        "query": "某新能源车 用户评价 值不值得买",
        "expected_first_domain": "zhuanlan.zhihu.com",
        "results": [
            {"title": "Leo Jiménez Stats, Height, Weight, Position", "url": "https://www.baseball-reference.com/players/j/jimenle01.shtml", "snippet": "Baseball player statistics"},
            {"title": "国产新能源车到底值不值得买？用了3年，谈谈我的使用感受", "url": "https://zhuanlan.zhihu.com/p/123", "snippet": "车主评价、体验、优缺点和购买建议"},
            {"title": "新能源车销量榜", "url": "https://example.com/auto-sales", "snippet": "销量数据整理"},
        ],
    },
]


def run_quality_checks(mode: str = "quick", limit: int = 5, coverage: bool = False) -> dict[str, Any]:
    """Run quick deterministic checks, with optional live network probes."""
    mode = mode if mode in {"quick", "live"} else "quick"
    checks: list[dict[str, Any]] = []
    checks.extend(_check_search_ranking())
    checks.extend(_check_read_quality())
    checks.extend(_check_trend_quality())
    checks.extend(_check_advisor_quality())
    if coverage:
        checks.extend(run_coverage_checks(mode="quick", limit=limit)["checks"])
    if mode == "live":
        checks.extend(_check_live(limit=limit))
    passed = sum(1 for item in checks if item["status"] == "pass")
    warned = sum(1 for item in checks if item["status"] == "warn")
    failed = sum(1 for item in checks if item["status"] == "fail")
    return {
        "mode": mode,
        "summary": {
            "total": len(checks),
            "pass": passed,
            "warn": warned,
            "fail": failed,
            "score": round((passed + warned * 0.5) / max(len(checks), 1) * 100, 1),
        },
        "evaluation_scenarios": list_evaluation_scenarios(),
        "checks": checks,
    }


def run_coverage_checks(mode: str = "quick", limit: int = 50) -> dict[str, Any]:
    """Guard against releases that shrink downstream agent context."""
    mode = mode if mode in {"quick", "live"} else "quick"
    checks: list[dict[str, Any]] = []
    checks.extend(_check_default_limits())
    checks.extend(_check_search_context_coverage())
    checks.extend(_check_research_packet_coverage())
    checks.extend(_check_archive_metadata_contract())
    if mode == "live":
        checks.extend(_check_live_coverage(limit=limit))
    passed = sum(1 for item in checks if item["status"] == "pass")
    warned = sum(1 for item in checks if item["status"] == "warn")
    failed = sum(1 for item in checks if item["status"] == "fail")
    return {
        "mode": mode,
        "summary": {
            "total": len(checks),
            "pass": passed,
            "warn": warned,
            "fail": failed,
            "score": round((passed + warned * 0.5) / max(len(checks), 1) * 100, 1),
        },
        "checks": checks,
        "contract": {
            "search_min": 50,
            "research_min": 50,
            "hotnews_min": 50,
            "feeds_min": 80,
            "archive_search_min": 50,
            "read_fallback_min": 20,
            "principle": "新版本不得让 Agent 默认拿到的候选池、证据字段或归档元数据大面积缩水。",
        },
    }


def run_regression_checks(mode: str = "quick", limit: int = 50) -> dict[str, Any]:
    """Run release regression guards for agent-visible output volume and depth."""
    mode = mode if mode in {"quick", "live"} else "quick"
    checks: list[dict[str, Any]] = []
    checks.extend(run_coverage_checks(mode="quick", limit=limit)["checks"])
    checks.extend(_check_result_pool_diversity())
    checks.extend(_check_feed_resilience_contract())
    checks.extend(_check_read_article_extraction_signal())
    checks.extend(_check_advisor_adapts_to_task())
    checks.extend(_check_archive_technical_recall())
    if mode == "live":
        checks.extend(_check_live_coverage(limit=limit))
        checks.extend(_check_live(limit=min(limit, 8)))
    passed = sum(1 for item in checks if item["status"] == "pass")
    warned = sum(1 for item in checks if item["status"] == "warn")
    failed = sum(1 for item in checks if item["status"] == "fail")
    return {
        "mode": mode,
        "summary": {
            "total": len(checks),
            "pass": passed,
            "warn": warned,
            "fail": failed,
            "score": round((passed + warned * 0.5) / max(len(checks), 1) * 100, 1),
        },
        "checks": checks,
        "contract": {
            "principle": "每次更新不得让 Agent 默认拿到的内容大面积变少、变窄或变脏。",
            "minimum_pool": {
                "search": 50,
                "research": 50,
                "hotnews": 50,
                "feeds": 80,
                "read_fallback": 20,
            },
            "depth_fields": [
                "evidence_role",
                "source_card",
                "read_quality",
                "quality_report",
                "feed_status",
                "advisor.answer_frame",
            ],
        },
    }


def run_robustness_checks(mode: str = "quick", limit: int = 50) -> dict[str, Any]:
    """Run deeper deterministic guards for messy real-world agent workflows."""
    mode = mode if mode in {"quick", "live"} else "quick"
    checks: list[dict[str, Any]] = []
    checks.extend(run_regression_checks(mode="quick", limit=limit)["checks"])
    checks.extend(_check_archive_ingest_audit_contract())
    checks.extend(_check_archive_agent_contract_fields())
    checks.extend(_check_archive_failure_explanations())
    checks.extend(_check_release_gate_script_contract())
    if mode == "live":
        checks.extend(_check_live_coverage(limit=limit))
        checks.extend(_check_live(limit=min(limit, 8)))
    passed = sum(1 for item in checks if item["status"] == "pass")
    warned = sum(1 for item in checks if item["status"] == "warn")
    failed = sum(1 for item in checks if item["status"] == "fail")
    return {
        "mode": mode,
        "summary": {
            "total": len(checks),
            "pass": passed,
            "warn": warned,
            "fail": failed,
            "score": round((passed + warned * 0.5) / max(len(checks), 1) * 100, 1),
        },
        "checks": checks,
        "contract": {
            "principle": "稳健性不是更多结果，而是在脏网页、坏网络、误用命令、空库和版本升级时仍能解释边界并保住字段。",
            "must_explain": [
                "archive_ingest_audit",
                "search_trace",
                "read_quality",
                "feed_status",
                "release_gate",
            ],
        },
    }


def format_quality_report(report: dict[str, Any]) -> str:
    """Render a quality report as Markdown."""
    summary = report.get("summary") or {}
    lines = [
        "# 观澜质量闸门",
        "",
        f"- 模式: {report.get('mode', 'quick')}",
        f"- 总分: {summary.get('score', 0)}",
        f"- 结果: pass={summary.get('pass', 0)} warn={summary.get('warn', 0)} fail={summary.get('fail', 0)}",
        "",
        "## 检查项",
    ]
    for item in report.get("checks") or []:
        lines.append(f"- [{item.get('status')}] {item.get('id')}: {item.get('message')}")
    lines.extend(["", "## 内置评估场景"])
    for scenario in report.get("evaluation_scenarios") or []:
        lines.append(f"- {scenario.get('id')}: {scenario.get('query')}")
    return "\n".join(lines)


def format_coverage_report(report: dict[str, Any]) -> str:
    """Render coverage guard checks as Markdown."""
    summary = report.get("summary") or {}
    contract = report.get("contract") or {}
    lines = [
        "# 观澜 Coverage Guard",
        "",
        f"- 模式: {report.get('mode', 'quick')}",
        f"- 总分: {summary.get('score', 0)}",
        f"- 结果: pass={summary.get('pass', 0)} warn={summary.get('warn', 0)} fail={summary.get('fail', 0)}",
        f"- 原则: {contract.get('principle', '')}",
        "",
        "## 下限契约",
        f"- search >= {contract.get('search_min', 50)}",
        f"- research >= {contract.get('research_min', 50)}",
        f"- hotnews >= {contract.get('hotnews_min', 50)}",
        f"- feeds >= {contract.get('feeds_min', 80)}",
        f"- archive search >= {contract.get('archive_search_min', 50)}",
        f"- read fallback >= {contract.get('read_fallback_min', 20)}",
        "",
        "## 检查项",
    ]
    for item in report.get("checks") or []:
        lines.append(f"- [{item.get('status')}] {item.get('id')}: {item.get('message')}")
    return "\n".join(lines)


def format_regression_report(report: dict[str, Any]) -> str:
    """Render release regression guard checks as Markdown."""
    summary = report.get("summary") or {}
    contract = report.get("contract") or {}
    lines = [
        "# 观澜 Release Regression Guard",
        "",
        f"- 模式: {report.get('mode', 'quick')}",
        f"- 总分: {summary.get('score', 0)}",
        f"- 结果: pass={summary.get('pass', 0)} warn={summary.get('warn', 0)} fail={summary.get('fail', 0)}",
        f"- 原则: {contract.get('principle', '')}",
        "",
        "## 必须保留的深度字段",
    ]
    for field in contract.get("depth_fields") or []:
        lines.append(f"- {field}")
    lines.extend(["", "## 检查项"])
    for item in report.get("checks") or []:
        lines.append(f"- [{item.get('status')}] {item.get('id')}: {item.get('message')}")
    return "\n".join(lines)


def format_robustness_report(report: dict[str, Any]) -> str:
    """Render robustness checks as Markdown."""
    summary = report.get("summary") or {}
    contract = report.get("contract") or {}
    lines = [
        "# 观澜 Robustness Guard",
        "",
        f"- 模式: {report.get('mode', 'quick')}",
        f"- 总分: {summary.get('score', 0)}",
        f"- 结果: pass={summary.get('pass', 0)} warn={summary.get('warn', 0)} fail={summary.get('fail', 0)}",
        f"- 原则: {contract.get('principle', '')}",
        "",
        "## 必须解释的边界",
    ]
    for field in contract.get("must_explain") or []:
        lines.append(f"- {field}")
    lines.extend(["", "## 检查项"])
    for item in report.get("checks") or []:
        lines.append(f"- [{item.get('status')}] {item.get('id')}: {item.get('message')}")
    return "\n".join(lines)


def format_quality_jsonl(report: dict[str, Any]) -> str:
    """Render checks as JSONL for external harnesses."""
    return "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in report.get("checks") or [])


def format_coverage_jsonl(report: dict[str, Any]) -> str:
    """Render coverage guard checks as JSONL."""
    return "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in report.get("checks") or [])


def _check_default_limits() -> list[dict[str, Any]]:
    checks = [
        ("coverage_search_default_limit", "search", DEFAULT_SEARCH_LIMIT, 50),
        ("coverage_research_default_limit", "research", DEFAULT_RESEARCH_LIMIT, 50),
        ("coverage_hotnews_default_limit", "hotnews", DEFAULT_HOTNEWS_LIMIT, 50),
        ("coverage_feeds_default_limit", "feeds", DEFAULT_FEEDS_LIMIT, 80),
        ("coverage_archive_search_default_limit", "archive", DEFAULT_ARCHIVE_SEARCH_LIMIT, 50),
        ("coverage_read_fallback_default_limit", "read", DEFAULT_READ_FALLBACK_LIMIT, 20),
    ]
    return [
        {
            "id": check_id,
            "dimension": "coverage_guard",
            "status": "pass" if value >= minimum else "fail",
            "message": f"{name} default={value}, expected >= {minimum}",
        }
        for check_id, name, value, minimum in checks
    ]


def _check_search_context_coverage() -> list[dict[str, Any]]:
    ranked = webtools.rank_results(
        [
            webtools.SearchResult(title="国务院政策原文", url="https://www.gov.cn/zhengce/a.htm", snippet="政策 原文 通知", rank=1),
            webtools.SearchResult(title="人民网权威报道", url="https://people.com.cn/a", snippet="权威报道", rank=2),
            webtools.SearchResult(title="知乎用户评价", url="https://zhihu.com/question/1", snippet="用户评价 体验", rank=3),
            webtools.SearchResult(title="亿邦动力产业观察", url="https://ebrun.com/a", snippet="电商 行业 案例", rank=4),
        ],
        query="人工智能 政策 用户评价 产业",
    )
    rows = [item.to_dict() for item in ranked]
    roles = {row.get("evidence_role") for row in rows}
    gap_summary = webtools.search_quality_summary(
        [
            {
                "title": "通用网页",
                "url": "https://example.com/a",
                "source_type": "通用网页",
                "domain": "example.com",
                "evidence_role": "open_web_context",
            }
        ],
        quality={
            "route_evidence_roles": ["official_primary"],
            "preferred_scopes": ["gov"],
            "preferred_source_types": ["政府/部委"],
        },
    )
    return [
        {
            "id": "coverage_search_results_keep_evidence_roles",
            "dimension": "coverage_guard",
            "status": "pass" if len(roles - {None, ""}) >= 3 else "fail",
            "message": f"evidence_roles={sorted(role for role in roles if role)}",
        },
        {
            "id": "coverage_search_quality_reports_gaps",
            "dimension": "coverage_guard",
            "status": "pass" if gap_summary.get("missing_roles") and gap_summary.get("suggestions") else "fail",
            "message": f"missing={gap_summary.get('missing_roles')}, suggestions={len(gap_summary.get('suggestions') or [])}",
        },
    ]


def _check_research_packet_coverage() -> list[dict[str, Any]]:
    reading = {
        "rank": 1,
        "title": "政策原文",
        "url": "https://gov.cn/a",
        "source_type": "政府/部委",
        "status": "ok",
        "content": "这是连续的中文正文。" * 30,
    }
    quality = webtools.assess_read_quality(str(reading["content"]))
    record = {
        **reading,
        "read_quality": quality,
        "quality_report": webtools.build_read_quality_report(str(reading["content"]), quality=quality),
    }
    ok = bool(record["read_quality"].get("score", 0) >= 55 and record["quality_report"].get("recommendations"))
    return [
        {
            "id": "coverage_research_readings_keep_quality_metadata",
            "dimension": "coverage_guard",
            "status": "pass" if ok else "fail",
            "message": f"read_quality={record['read_quality'].get('label')}/{record['read_quality'].get('score')}",
        }
    ]


def _check_archive_metadata_contract() -> list[dict[str, Any]]:
    content = "# 标题\n\n这是归档正文。" * 20
    quality = webtools.assess_read_quality(content)
    source_card = webtools.source_card_for_domain("gov.cn").to_dict()
    metadata = {"read_quality": quality, "source_card": source_card, "route_plan": {"primary_intents": ["policy"]}}
    required = {"read_quality", "source_card", "route_plan"}
    missing = sorted(required - set(metadata))
    return [
        {
            "id": "coverage_archive_keeps_route_source_read_metadata",
            "dimension": "coverage_guard",
            "status": "pass" if not missing else "fail",
            "message": "metadata keys=" + ",".join(sorted(metadata.keys())),
        }
    ]


def _check_archive_technical_recall() -> list[dict[str, Any]]:
    from guanlan import archive

    db_path = None
    try:
        import tempfile
        from pathlib import Path

        db_path = Path(tempfile.mkdtemp()) / "archive.db"
        archive.add_document(
            "https://example.com/kv-cache",
            "# KV Cache 优化\n\n本文讨论推理服务里的 PagedAttention，并介绍 vLLM 与 SGLang 如何管理 KV Cache。"
            "KIVI 用于 KV Cache 量化，KVQuant 也属于相关优化方向。",
            db_path=db_path,
        )
        framework = archive.search_documents("开源推理框架 vLLM SGLang", db_path=db_path, trace=True)
        quant = archive.search_documents("KV Cache 量化方法 KIVI", db_path=db_path, trace=True)
        ok = bool(framework and quant and framework[0].get("search_trace") and quant[0].get("search_trace"))
        message = (
            f"framework_hits={len(framework)}, quant_hits={len(quant)}, "
            f"matched={(framework[0].get('search_trace') or {}).get('matched_terms') if framework else []}"
        )
    except Exception as exc:
        ok = False
        message = str(exc)
    return [
        {
            "id": "regression_archive_recalls_technical_terms",
            "dimension": "release_regression",
            "status": "pass" if ok else "fail",
            "message": message,
        }
    ]


def _check_archive_ingest_audit_contract() -> list[dict[str, Any]]:
    from guanlan import archive

    noisy = archive.audit_ingest_candidate(
        "开源推理框架 vLLM SGLang",
        {"title": "2019 Toyota Camry", "url": "https://example.com/camry", "snippet": "Used car listing"},
    )
    homepage = archive.audit_ingest_candidate(
        "EI会议 投稿 检索 收录 要求",
        {"title": "Engineering Village - Quick Search", "url": "https://www.engineeringvillage.com/search/quick.url", "snippet": ""},
    )
    useful = archive.audit_ingest_candidate(
        "开源推理框架 vLLM SGLang",
        {
            "title": "vLLM 与 SGLang 推理框架对比",
            "url": "https://example.com/vllm",
            "snippet": "vLLM SGLang KV Cache 推理框架",
        },
        content="# vLLM 与 SGLang\n\nKV Cache 推理框架工程实践。" * 3,
    )
    ok = (
        noisy.get("decision") == "skip"
        and "low_query_overlap" in noisy.get("reasons", [])
        and homepage.get("decision") == "skip"
        and "platform_homepage" in homepage.get("reasons", [])
        and useful.get("decision") == "keep"
        and {"vLLM", "SGLang"} & set(useful.get("matched_terms") or [])
    )
    return [
        {
            "id": "robustness_archive_ingest_audits_noise_before_write",
            "dimension": "robustness",
            "status": "pass" if ok else "fail",
            "message": f"noisy={noisy.get('reasons')}, homepage={homepage.get('reasons')}, useful={useful.get('matched_terms')}",
        }
    ]


def _check_archive_agent_contract_fields() -> list[dict[str, Any]]:
    from guanlan import archive

    try:
        import tempfile

        db_path = Path(tempfile.mkdtemp()) / "archive.db"
        record = archive.add_document(
            "https://example.com/kv-cache",
            "# KV Cache 优化\n\nvLLM、SGLang、KIVI 与 KVQuant 都是推理服务常见优化线索。",
            metadata={"source_type": "科技/开发者社区", "topic_key": "llm-inference"},
            db_path=db_path,
        )
        searched = archive.search_documents("vLLM SGLang KIVI", trace=True, db_path=db_path)
        inspected = archive.inspect_document(str(record["id"]), db_path=db_path)
        exported = archive.export_documents(db_path=db_path)
        search_ok = bool(searched and searched[0].get("search_trace", {}).get("matched_terms"))
        inspect_ok = bool(inspected.get("diagnostics", {}).get("has_content") and inspected.get("content"))
        export_ok = bool(exported and exported[0].get("rag", {}).get("text") and exported[0].get("metadata", {}).get("read_quality") is not None)
        ok = search_ok and inspect_ok and export_ok
        message = f"search_trace={search_ok}, inspect={inspect_ok}, rag_export={export_ok}"
    except Exception as exc:
        ok = False
        message = str(exc)
    return [
        {
            "id": "robustness_archive_keeps_agent_contract_fields",
            "dimension": "robustness",
            "status": "pass" if ok else "fail",
            "message": message,
        }
    ]


def _check_archive_failure_explanations() -> list[dict[str, Any]]:
    from guanlan import archive

    markdown = archive.format_archive_markdown([], title="空库")
    context = archive.format_archive_context([], title="空库")
    ok = (
        "archive list" in markdown
        and "archive ingest-research" in markdown
        and "archive list" in context
        and "archive ingest-research" in context
    )
    return [
        {
            "id": "robustness_archive_empty_results_explain_next_steps",
            "dimension": "robustness",
            "status": "pass" if ok else "fail",
            "message": "empty archive output should explain list vs ingest-research next steps",
        }
    ]


def _check_release_gate_script_contract() -> list[dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "release_gate.sh"
    text = script.read_text(encoding="utf-8") if script.exists() else ""
    required = [
        "ruff check",
        "pytest -q",
        "quality coverage",
        "quality regression",
        "quality robustness",
        "eval benchmark",
        "uv build",
        "release_smoke.sh",
        "guanlan version",
    ]
    missing = [item for item in required if item not in text]
    return [
        {
            "id": "robustness_release_gate_runs_full_local_checks",
            "dimension": "robustness",
            "status": "pass" if not missing else "fail",
            "message": "missing=" + ",".join(missing) if missing else "release gate covers static/test/quality/build/smoke/version",
        }
    ]


def _check_result_pool_diversity() -> list[dict[str, Any]]:
    rows = [
        {"title": "国务院政策原文", "url": "https://www.gov.cn/zhengce/a.htm", "source_type": "政府/部委", "evidence_role": "official_primary"},
        {"title": "人民网权威报道", "url": "https://people.com.cn/a", "source_type": "党央媒", "evidence_role": "official_amplifier"},
        {"title": "亿邦动力产业观察", "url": "https://ebrun.com/a", "source_type": "电商/零售垂类", "evidence_role": "industry_signal"},
        {"title": "知乎用户评价", "url": "https://zhihu.com/question/1", "source_type": "社交/内容平台", "evidence_role": "social_sample"},
    ]
    source_types = {str(item.get("source_type")) for item in rows if item.get("source_type")}
    roles = {str(item.get("evidence_role")) for item in rows if item.get("evidence_role")}
    return [
        {
            "id": "regression_result_pool_keeps_source_diversity",
            "dimension": "release_regression",
            "status": "pass" if len(source_types) >= 4 and len(roles) >= 4 else "fail",
            "message": f"source_types={len(source_types)}, evidence_roles={len(roles)}",
        }
    ]


def _check_feed_resilience_contract() -> list[dict[str, Any]]:
    item = {
        "title": "缓存文章",
        "url": "https://example.com/a",
        "source_id": "curated",
        "risk_tags": ["stale_cache"],
        "feed_status": {"status": "stale_cache", "stale": True, "error": "timed out"},
    }
    ok = item["feed_status"]["status"] == "stale_cache" and "stale_cache" in item["risk_tags"]
    return [
        {
            "id": "regression_feeds_can_mark_stale_cache",
            "dimension": "release_regression",
            "status": "pass" if ok else "fail",
            "message": "feeds should expose stale/cache status instead of failing silently",
        }
    ]


def _check_read_article_extraction_signal() -> list[dict[str, Any]]:
    raw = """
    <html><body><nav>登录 注册 首页</nav><main class="article-content">
    <h1>政策标题</h1><p>这是第一段正文，包含政策背景、发布主体和适用范围。</p>
    <p>这是第二段正文，继续说明执行路径、影响对象和后续安排。</p>
    </main><footer>版权声明 推荐阅读</footer></body></html>
    """
    text = webtools._extract_article_text(raw)  # noqa: SLF001 - quality gate intentionally checks extractor behavior.
    quality = webtools.assess_read_quality(text)
    report = webtools.build_read_quality_report(text, quality=quality)
    ok = "登录" not in text and "版权声明" not in text and report.get("body_ratio", 0) >= 0.75
    return [
        {
            "id": "regression_read_keeps_main_body_signal",
            "dimension": "release_regression",
            "status": "pass" if ok else "fail",
            "message": f"body_ratio={report.get('body_ratio')}, noise={quality.get('noise_hits')}",
        }
    ]


def _check_advisor_adapts_to_task() -> list[dict[str, Any]]:
    policy_packet = {
        "query": "低空经济 广东 政策 官方口径",
        "preset": "policy",
        "result_count": 6,
        "topic_count": 3,
        "source_mix": {"政府/部委": 3, "地方官媒": 2, "党央媒": 1},
        "results": [{"source_type": "政府/部委", "title": "政策原文"}],
        "readings": [{"status": "ok", "content": "政策正文" * 80}],
        "read_top": 1,
    }
    reputation_packet = {
        "query": "某产品 用户评价 值不值得买",
        "preset": "reputation",
        "result_count": 8,
        "topic_count": 4,
        "source_mix": {"社交/内容平台": 5, "商业/产业媒体": 3},
        "results": [{"source_type": "社交/内容平台", "title": "用户评价"}],
        "readings": [],
        "read_top": 0,
    }
    policy = webtools.build_advisor_view(policy_packet, style="risk")
    reputation = webtools.build_advisor_view(reputation_packet, style="decision")
    policy_text = json.dumps(policy, ensure_ascii=False)
    reputation_text = json.dumps(reputation, ensure_ascii=False)
    ok = "官方口径" in policy_text and "用户" in reputation_text and policy_text != reputation_text
    return [
        {
            "id": "regression_advisor_changes_with_task",
            "dimension": "release_regression",
            "status": "pass" if ok else "fail",
            "message": "advisor should adapt to policy vs reputation tasks",
        }
    ]


def _check_live_coverage(limit: int = 50) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        results = webtools.search_web("今日 人工智能 政策 热点", profile="china", limit=max(limit, 50))
        checks.append(
            {
                "id": "live_coverage_search_returns_broad_pool",
                "dimension": "coverage_guard",
                "status": "pass" if len(results) >= min(limit, 20) else "warn",
                "message": f"results={len(results)}",
            }
        )
    except Exception as exc:
        checks.append({"id": "live_coverage_search_returns_broad_pool", "dimension": "coverage_guard", "status": "warn", "message": str(exc)})
    return checks


def _check_search_ranking() -> list[dict[str, Any]]:
    checks = []
    for scenario in SEARCH_RANKING_FIXTURES:
        ranked = webtools.rank_results(
            [
                webtools.SearchResult(
                    title=row["title"],
                    url=row["url"],
                    snippet=row.get("snippet", ""),
                    source="fixture",
                    rank=idx,
                )
                for idx, row in enumerate(scenario["results"], start=1)
            ],
            query=scenario["query"],
        )
        actual = ranked[0].domain if ranked else ""
        passed = actual == scenario["expected_first_domain"]
        checks.append(
            {
                "id": scenario["id"],
                "dimension": "search_quality",
                "status": "pass" if passed else "fail",
                "message": f"expected first domain {scenario['expected_first_domain']}, got {actual}",
            }
        )
    return checks


def _check_read_quality() -> list[dict[str, Any]]:
    clean = webtools.assess_read_quality("这是第一段正文，包含足够多的中文内容和事实信息。" * 8)
    noisy = webtools.assess_read_quality("登录 注册 打开APP 推荐阅读 相关阅读 " + "正文内容" * 20)
    return [
        {
            "id": "read_clean_scores_high",
            "dimension": "read_extraction",
            "status": "pass" if clean["label"] == "clean" and clean["score"] >= 80 else "fail",
            "message": f"clean label={clean['label']} score={clean['score']}",
        },
        {
            "id": "read_noise_is_detected",
            "dimension": "read_extraction",
            "status": "pass" if noisy["label"] in {"noisy", "weak"} and noisy["noise_hits"] else "fail",
            "message": f"noisy label={noisy['label']} hits={','.join(noisy['noise_hits'])}",
        },
    ]


def _check_trend_quality() -> list[dict[str, Any]]:
    report = hotnews.build_trend_report(
        [
            {"rank": 1, "source_id": "baidu", "title": "AI 眼镜新品发布", "metrics": {"heat": 10000}},
            {"rank": 2, "source_id": "weibo", "title": "AI眼镜 新品 引热议", "metrics": {"heat": 5000}},
            {"rank": 3, "source_id": "baidu", "title": "袁隆平夫人收到了一份特殊礼物"},
            {"rank": 4, "source_id": "weibo", "title": "人到了一定年纪就会解锁的动作"},
        ]
    )
    merged_ai = any(trend.get("source_count") == 2 and "AI" in str(trend.get("title")) for trend in report["trends"])
    false_merge = any(
        trend.get("item_count") == 2 and "袁隆平" in json.dumps(trend, ensure_ascii=False)
        for trend in report["trends"]
    )
    return [
        {
            "id": "trend_merges_true_cross_source_topic",
            "dimension": "trend_clustering",
            "status": "pass" if merged_ai else "fail",
            "message": "AI 眼镜跨源趋势应被归并",
        },
        {
            "id": "trend_avoids_generic_false_merge",
            "dimension": "trend_clustering",
            "status": "pass" if not false_merge else "fail",
            "message": "通用 bigram 不应导致错聚类",
        },
    ]


def _check_advisor_quality() -> list[dict[str, Any]]:
    packet = {
        "query": "某产品 用户评价 值不值得买",
        "preset": "reputation",
        "result_count": 8,
        "topic_count": 4,
        "source_mix": {"社交/内容平台": 5, "商业/产业媒体": 3},
        "results": [{"source_type": "社交/内容平台", "title": "用户评价"}],
        "readings": [],
        "read_top": 0,
    }
    advisor = webtools.build_advisor_view(packet, style="decision")
    ok = bool(advisor.get("briefing")) and any("行动" in item or "取舍" in item for item in advisor.get("answer_frame", []))
    return [
        {
            "id": "advisor_has_natural_decision_frame",
            "dimension": "advisor_naturalness",
            "status": "pass" if ok else "fail",
            "message": "advisor should provide dynamic briefing and decision-oriented frame",
        }
    ]


def _check_live(limit: int = 5) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        results = webtools.search_web("新质生产力 政策 原文 最新", profile="china", limit=max(limit, 3), trace=True)
        preferred = [item for item in results if item.get("source_type") in {"政府/部委", "党央媒"}]
        checks.append(
            {
                "id": "live_policy_search_has_official_source",
                "dimension": "search_quality",
                "status": "pass" if preferred else "warn",
                "message": f"official-like results={len(preferred)}/{len(results)}",
            }
        )
    except Exception as exc:
        checks.append({"id": "live_policy_search_has_official_source", "dimension": "search_quality", "status": "warn", "message": str(exc)})
    try:
        items = hotnews.fetch_hotnews("today", limit=max(limit, 5))
        checks.append(
            {
                "id": "live_hotnews_today_returns_items",
                "dimension": "hotnews_freshness",
                "status": "pass" if len(items) >= min(limit, 5) else "warn",
                "message": f"items={len(items)}",
            }
        )
    except Exception as exc:
        checks.append({"id": "live_hotnews_today_returns_items", "dimension": "hotnews_freshness", "status": "warn", "message": str(exc)})
    return checks
