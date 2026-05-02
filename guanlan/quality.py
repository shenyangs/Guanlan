# -*- coding: utf-8 -*-
"""Quality gate for Guanlan's agent-facing research workflow."""

from __future__ import annotations

import json
from typing import Any

from guanlan import hotnews, webtools
from guanlan.evaluation import list_evaluation_scenarios

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


def run_quality_checks(mode: str = "quick", limit: int = 5) -> dict[str, Any]:
    """Run quick deterministic checks, with optional live network probes."""
    mode = mode if mode in {"quick", "live"} else "quick"
    checks: list[dict[str, Any]] = []
    checks.extend(_check_search_ranking())
    checks.extend(_check_read_quality())
    checks.extend(_check_trend_quality())
    checks.extend(_check_advisor_quality())
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


def format_quality_jsonl(report: dict[str, Any]) -> str:
    """Render checks as JSONL for external harnesses."""
    return "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in report.get("checks") or [])


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
