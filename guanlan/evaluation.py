# -*- coding: utf-8 -*-
"""Evaluation scenarios for comparing generic web_search with Guanlan."""

from __future__ import annotations

import json
from typing import Any

EVALUATION_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "policy_source_identity",
        "query": "新质生产力 政策 原文",
        "profile": "china",
        "expected_gain": "优先触达官方原文和党央媒，减少海外评论或二手解读误导。",
        "checks": ["has_official_source", "keeps_source_identity", "mentions_evidence_limits"],
    },
    {
        "id": "reputation_platform_islands",
        "query": "某产品 用户评价 值不值得买",
        "profile": "china",
        "expected_gain": "路由到知乎、微博、小红书、B站等公开样本，同时提醒样本偏差。",
        "checks": ["uses_social_samples", "avoids_population_claim", "keeps_fallback_web"],
    },
    {
        "id": "hot_trend_awareness",
        "query": "今天 中文互联网 热点 AI",
        "profile": "china",
        "expected_gain": "先巡视热榜/快讯，再进入 research，提升时效感。",
        "checks": ["uses_hotnews", "clusters_trends", "keeps_timestamp"],
    },
    {
        "id": "developer_feedback",
        "query": "Python Agent 框架 对比 github issue",
        "profile": "china",
        "expected_gain": "优先技术社区、GitHub、开发者讨论，而不是泛 SEO 文章。",
        "checks": ["uses_dev_sources", "mentions_version_sensitivity"],
    },
]


def list_evaluation_scenarios() -> list[dict[str, Any]]:
    """Return built-in evaluation scenarios."""
    return list(EVALUATION_SCENARIOS)


def format_evaluation_markdown(scenarios: list[dict[str, Any]] | None = None) -> str:
    """Render scenarios as a lightweight evaluation checklist."""
    rows = scenarios or EVALUATION_SCENARIOS
    lines = ["# 观澜评估集", "", "用于比较普通 web_search 与观澜证据包在中文语境里的差异。"]
    for item in rows:
        lines.extend(
            [
                "",
                f"## {item['id']}",
                f"- Query: {item['query']}",
                f"- Profile: {item['profile']}",
                f"- Expected gain: {item['expected_gain']}",
                f"- Checks: {', '.join(item['checks'])}",
            ]
        )
    return "\n".join(lines)


def format_evaluation_jsonl(scenarios: list[dict[str, Any]] | None = None) -> str:
    """Render scenarios as JSONL for external benchmark harnesses."""
    return "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in (scenarios or EVALUATION_SCENARIOS))
