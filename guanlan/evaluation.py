# -*- coding: utf-8 -*-
"""Evaluation scenarios for comparing generic web_search with Guanlan.

The benchmark in this module is intentionally deterministic by default. It
checks whether Guanlan keeps the product contract that matters to agents:
route the request to the right source families, preserve evidence roles, and
avoid shrinking the research pool before any live network request happens.
"""

from __future__ import annotations

import json
from typing import Any

EVALUATION_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "policy_source_identity",
        "query": "新质生产力 政策 原文",
        "profile": "china",
        "preset": "policy",
        "expected_gain": "优先触达官方原文和党央媒，减少海外评论或二手解读误导。",
        "checks": ["has_official_source", "keeps_source_identity", "mentions_evidence_limits"],
        "expected_intents": ["policy"],
        "expected_scopes": ["gov", "party_central"],
        "expected_roles": ["official_primary"],
    },
    {
        "id": "reputation_platform_islands",
        "query": "某产品 用户评价 值不值得买",
        "profile": "china",
        "preset": "reputation",
        "expected_gain": "路由到知乎、微博、小红书、B站等公开样本，同时提醒样本偏差。",
        "checks": ["uses_social_samples", "avoids_population_claim", "keeps_fallback_web"],
        "expected_intents": ["reputation", "purchase_advice"],
        "expected_scopes": ["social_web"],
        "expected_roles": ["user_sample", "community_discussion"],
    },
    {
        "id": "hot_trend_awareness",
        "query": "今天 中文互联网 热点 AI",
        "profile": "china",
        "preset": "general",
        "expected_gain": "先巡视热榜/快讯，再进入 research，提升时效感。",
        "checks": ["uses_hotnews", "clusters_trends", "keeps_timestamp"],
        "expected_intents": ["hot_trend"],
        "expected_scopes": [],
        "expected_roles": ["fresh_news", "public_discussion"],
    },
    {
        "id": "developer_feedback",
        "query": "Python Agent 框架 对比 github issue",
        "profile": "china",
        "preset": "tech",
        "expected_gain": "优先技术社区、GitHub、开发者讨论，而不是泛 SEO 文章。",
        "checks": ["uses_dev_sources", "mentions_version_sensitivity"],
        "expected_intents": ["tech"],
        "expected_scopes": ["tech_dev"],
        "expected_roles": ["developer_discussion", "source_code"],
    },
    {
        "id": "academic_indexing",
        "query": "EI会议 投稿 检索 收录 要求",
        "profile": "china",
        "preset": "academic",
        "expected_gain": "区分数据库/出版商口径、会议 CFP、高校认定口径，避免代投软文主导。",
        "checks": ["uses_academic_scope", "separates_publisher_and_school_rules", "avoids_paper_agency"],
        "expected_intents": ["academic"],
        "expected_scopes": ["academic"],
        "expected_roles": ["database_official", "publisher_guideline"],
    },
    {
        "id": "local_official_context",
        "query": "上海 人工智能 产业政策 原文",
        "profile": "china",
        "preset": "local",
        "expected_gain": "地方政策优先地方政府、发改/经信等一手来源，再补产业媒体。",
        "checks": ["uses_local_official", "keeps_policy_level", "keeps_open_web_fallback"],
        "expected_intents": ["policy", "local"],
        "expected_scopes": ["local_official", "gov"],
        "expected_roles": ["official_primary"],
    },
    {
        "id": "ecommerce_industry",
        "query": "即时零售 电商 产业趋势 亿邦动力",
        "profile": "china",
        "preset": "ecommerce",
        "expected_gain": "把电商/零售垂类媒体、平台公告和开放网页放到同一证据结构里。",
        "checks": ["uses_ecommerce_scope", "keeps_industry_context", "keeps_source_diversity"],
        "expected_intents": ["ecommerce", "industry"],
        "expected_scopes": ["ecommerce", "business"],
        "expected_roles": ["vertical_report", "industry_report"],
    },
    {
        "id": "local_llm_prompt_context",
        "query": "给本地 Ollama 模型联网搜索 中文政策信息",
        "profile": "china",
        "preset": "policy",
        "expected_gain": "把搜索、阅读、证据边界组织成可直接交给本地模型的上下文。",
        "checks": ["keeps_context_format", "keeps_source_identity", "keeps_agent_commands"],
        "expected_intents": ["policy"],
        "expected_scopes": ["gov", "party_central"],
        "expected_roles": ["official_primary"],
    },
]

BENCHMARK_TASKS: list[dict[str, Any]] = [
    {"id": "policy_001", "category": "policy", "query": "新质生产力 政策 原文", "expected_source_family": "official"},
    {"id": "policy_002", "category": "policy", "query": "人工智能治理 暂行办法 官方 原文", "expected_source_family": "official"},
    {"id": "policy_003", "category": "policy", "query": "数据要素 政策 国家发改委 原文", "expected_source_family": "official"},
    {"id": "policy_004", "category": "policy", "query": "低空经济 政策 官方口径", "expected_source_family": "official"},
    {"id": "policy_005", "category": "policy", "query": "制造业 数字化转型 政策 部委", "expected_source_family": "official"},
    {"id": "local_001", "category": "local", "query": "上海 人工智能 产业政策 原文", "expected_source_family": "local_official"},
    {"id": "local_002", "category": "local", "query": "深圳 低空经济 政策 原文", "expected_source_family": "local_official"},
    {"id": "local_003", "category": "local", "query": "杭州 算力券 政策 官方", "expected_source_family": "local_official"},
    {"id": "local_004", "category": "local", "query": "成都 人工智能 产业扶持 政策", "expected_source_family": "local_official"},
    {"id": "local_005", "category": "local", "query": "苏州 生物医药 产业政策 原文", "expected_source_family": "local_official"},
    {"id": "ecommerce_001", "category": "ecommerce", "query": "即时零售 电商 产业趋势 亿邦动力", "expected_source_family": "vertical_media"},
    {"id": "ecommerce_002", "category": "ecommerce", "query": "跨境电商 AI 工具 卖家反馈", "expected_source_family": "vertical_media"},
    {"id": "ecommerce_003", "category": "ecommerce", "query": "抖音电商 商家 服务商 趋势", "expected_source_family": "vertical_media"},
    {"id": "ecommerce_004", "category": "ecommerce", "query": "美团 闪购 即时零售 商家 案例", "expected_source_family": "vertical_media"},
    {"id": "ecommerce_005", "category": "ecommerce", "query": "淘宝天猫 AI 电商 产品趋势", "expected_source_family": "vertical_media"},
    {"id": "tech_001", "category": "tech", "query": "vLLM SGLang KV Cache 推理框架 对比", "expected_source_family": "developer"},
    {"id": "tech_002", "category": "tech", "query": "LangGraph AutoGen CrewAI GitHub issue 对比", "expected_source_family": "developer"},
    {"id": "tech_003", "category": "tech", "query": "MCP server Python SDK issue 实践", "expected_source_family": "developer"},
    {"id": "tech_004", "category": "tech", "query": "RAG reranker bge m3 中文 实测", "expected_source_family": "developer"},
    {"id": "tech_005", "category": "tech", "query": "Ollama 本地模型 联网搜索 工具", "expected_source_family": "developer"},
    {"id": "reputation_001", "category": "reputation", "query": "某 AI 笔记软件 用户评价 值不值得买", "expected_source_family": "user_sample"},
    {"id": "reputation_002", "category": "reputation", "query": "AI 眼镜 用户评价 小红书 知乎", "expected_source_family": "user_sample"},
    {"id": "reputation_003", "category": "reputation", "query": "新能源汽车 车主评价 缺点", "expected_source_family": "user_sample"},
    {"id": "reputation_004", "category": "reputation", "query": "儿童学习机 用户反馈 真实体验", "expected_source_family": "user_sample"},
    {"id": "reputation_005", "category": "reputation", "query": "国产数据库 用户口碑 迁移成本", "expected_source_family": "user_sample"},
    {"id": "hot_001", "category": "hot", "query": "今天 中文互联网 热点 AI", "expected_source_family": "hotnews"},
    {"id": "hot_002", "category": "hot", "query": "今天 微博 B站 科技 热点", "expected_source_family": "hotnews"},
    {"id": "hot_003", "category": "hot", "query": "最近 AI 应用 创业 热点", "expected_source_family": "hotnews"},
    {"id": "hot_004", "category": "hot", "query": "今天 财经 市场 热点 财联社", "expected_source_family": "hotnews"},
    {"id": "hot_005", "category": "hot", "query": "最近 开发者社区 热门项目", "expected_source_family": "hotnews"},
    {"id": "academic_001", "category": "academic", "query": "EI会议 投稿 检索 收录 要求", "expected_source_family": "academic"},
    {"id": "academic_002", "category": "academic", "query": "CCF 推荐会议 人工智能 投稿 官网", "expected_source_family": "academic"},
    {"id": "academic_003", "category": "academic", "query": "SCI 期刊 APC 出版商 官方说明", "expected_source_family": "academic"},
    {"id": "academic_004", "category": "academic", "query": "高校 科研奖励 论文认定 政策", "expected_source_family": "academic"},
    {"id": "academic_005", "category": "academic", "query": "arXiv 论文 代码 GitHub 中文解读", "expected_source_family": "academic"},
    {"id": "local_llm_001", "category": "local_llm", "query": "给本地 Ollama 模型联网搜索 中文政策信息", "expected_source_family": "agent_context"},
    {"id": "local_llm_002", "category": "local_llm", "query": "Open WebUI 调用本地 HTTP 搜索证据", "expected_source_family": "agent_context"},
    {"id": "local_llm_003", "category": "local_llm", "query": "LM Studio 本地模型 RAG 导入 中文网页", "expected_source_family": "agent_context"},
    {"id": "local_llm_004", "category": "local_llm", "query": "本地模型 读取网页 生成引用证据", "expected_source_family": "agent_context"},
    {"id": "local_llm_005", "category": "local_llm", "query": "无联网大模型 获取今日热点 上下文", "expected_source_family": "agent_context"},
]


def list_evaluation_scenarios() -> list[dict[str, Any]]:
    """Return built-in evaluation scenarios."""
    return list(EVALUATION_SCENARIOS)


def list_benchmark_tasks(category: str | None = None) -> list[dict[str, Any]]:
    """Return realistic benchmark task seeds for live/manual evaluation."""
    category_key = (category or "").strip().lower()
    if not category_key:
        return list(BENCHMARK_TASKS)
    return [task for task in BENCHMARK_TASKS if task.get("category") == category_key]


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


def run_benchmark(mode: str = "quick", limit: int = 50) -> dict[str, Any]:
    """Run a deterministic benchmark over built-in scenarios.

    ``mode`` is reserved for future live probes; ``quick`` deliberately avoids
    network access so it can be used as a release gate in CI.
    """
    from guanlan.router import build_route_plan

    mode = mode if mode in {"quick", "live"} else "quick"
    cases: list[dict[str, Any]] = []
    for scenario in EVALUATION_SCENARIOS:
        plan = build_route_plan(
            scenario["query"],
            preset=str(scenario.get("preset") or "general"),
            profile=str(scenario.get("profile") or "china"),
            limit=max(limit, 1),
        )
        plan_data = plan.to_dict()
        checks = _score_route_plan(scenario, plan_data, limit=max(limit, 1))
        passed = sum(1 for check in checks if check["status"] == "pass")
        warned = sum(1 for check in checks if check["status"] == "warn")
        failed = sum(1 for check in checks if check["status"] == "fail")
        score = round((passed + warned * 0.5) / max(len(checks), 1) * 100, 1)
        status = "fail" if failed else ("warn" if warned else "pass")
        cases.append(
            {
                "id": scenario["id"],
                "query": scenario["query"],
                "profile": scenario.get("profile", "china"),
                "preset": scenario.get("preset", "general"),
                "status": status,
                "score": score,
                "expected_gain": scenario["expected_gain"],
                "checks": checks,
                "route": {
                    "primary_intents": plan_data.get("primary_intents", []),
                    "secondary_intents": plan_data.get("secondary_intents", []),
                    "preferred_scopes": plan_data.get("preferred_scopes", []),
                    "evidence_roles": plan_data.get("evidence_roles", []),
                    "recommended_commands": plan_data.get("recommended_commands", []),
                    "limit": plan_data.get("limit", 0),
                    "read_top": plan_data.get("read_top", 0),
                },
            }
        )
    passed = sum(1 for item in cases if item["status"] == "pass")
    warned = sum(1 for item in cases if item["status"] == "warn")
    failed = sum(1 for item in cases if item["status"] == "fail")
    return {
        "mode": mode,
        "limit": max(limit, 1),
        "summary": {
            "total": len(cases),
            "pass": passed,
            "warn": warned,
            "fail": failed,
            "score": round(sum(float(item["score"]) for item in cases) / max(len(cases), 1), 1),
        },
        "principle": "评测重点不是搜到多少页面，而是 Agent 是否拿到了正确的中文信源结构、证据角色和足够大的候选池。",
        "cases": cases,
    }


def format_benchmark_markdown(report: dict[str, Any]) -> str:
    """Render benchmark results as Markdown."""
    summary = report.get("summary") or {}
    lines = [
        "# 观澜评测基准",
        "",
        f"- 模式: {report.get('mode', 'quick')}",
        f"- 候选池下限: {report.get('limit', 50)}",
        f"- 总分: {summary.get('score', 0)}",
        f"- 结果: pass={summary.get('pass', 0)} warn={summary.get('warn', 0)} fail={summary.get('fail', 0)}",
        f"- 原则: {report.get('principle', '')}",
        "",
        "## 场景",
    ]
    for case in report.get("cases") or []:
        route = case.get("route") or {}
        lines.append(f"- [{case.get('status')}] {case.get('id')}: {case.get('query')} score={case.get('score')}")
        lines.append(f"  意图: {', '.join(route.get('primary_intents') or []) or 'open'}")
        lines.append(f"  Scope: {', '.join(route.get('preferred_scopes') or []) or 'open web'}")
        lines.append(f"  证据角色: {', '.join(route.get('evidence_roles') or []) or '未识别'}")
    return "\n".join(lines)


def format_benchmark_jsonl(report: dict[str, Any]) -> str:
    """Render benchmark cases as JSONL for external dashboards."""
    return "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in report.get("cases") or [])


def _score_route_plan(scenario: dict[str, Any], plan: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    intents = set(plan.get("primary_intents") or []) | set(plan.get("secondary_intents") or [])
    scopes = set(plan.get("preferred_scopes") or []) | set(plan.get("fallback_scopes") or [])
    roles = set(plan.get("evidence_roles") or [])
    commands = [str(item) for item in plan.get("recommended_commands") or []]
    checks: list[dict[str, Any]] = []

    expected_intents = set(scenario.get("expected_intents") or [])
    checks.append(
        _benchmark_check(
            "route_intent",
            bool(expected_intents & intents) if expected_intents else bool(intents),
            f"expected intent {sorted(expected_intents)} in route {sorted(intents)}",
        )
    )

    expected_scopes = set(scenario.get("expected_scopes") or [])
    checks.append(
        _benchmark_check(
            "source_scope",
            bool(expected_scopes & scopes) if expected_scopes else True,
            f"expected scope {sorted(expected_scopes) or ['open web']} in route {sorted(scopes) or ['open web']}",
        )
    )

    expected_roles = set(scenario.get("expected_roles") or [])
    checks.append(
        _benchmark_check(
            "evidence_role",
            bool(expected_roles & roles) if expected_roles else bool(roles),
            f"expected role {sorted(expected_roles)} in route {sorted(roles)}",
        )
    )

    checks.append(
        _benchmark_check(
            "pool_floor",
            int(plan.get("limit") or 0) >= min(limit, 50),
            f"route limit={plan.get('limit', 0)}, expected >= {min(limit, 50)}",
        )
    )
    checks.append(
        _benchmark_check(
            "agent_command",
            any("--limit 50" in command or "--limit 80" in command for command in commands),
            "recommended commands should keep a substantial result pool",
            warn=True,
        )
    )
    return checks


def _benchmark_check(check_id: str, passed: bool, message: str, *, warn: bool = False) -> dict[str, Any]:
    if passed:
        status = "pass"
    else:
        status = "warn" if warn else "fail"
    return {"id": check_id, "status": status, "message": message}
