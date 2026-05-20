# -*- coding: utf-8 -*-
"""Safe topic echo analysis for Guanlan.

Pulse is deliberately conservative. It summarizes signals from public search
snippets and optional short reads; it does not claim to measure the whole web.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from guanlan.limits import DEFAULT_PULSE_LIMIT, DEFAULT_READ_FALLBACK_LIMIT

POSITIVE_TERMS = (
    "好评",
    "推荐",
    "值得",
    "方便",
    "稳定",
    "提升",
    "优秀",
    "便宜",
    "省心",
    "可靠",
    "增长",
    "利好",
    "支持",
    "受欢迎",
    "创新",
    "改善",
    "高效",
    "实用",
    "满意",
    "清晰",
    "成功",
    "领先",
    "爆款",
)

NEGATIVE_TERMS = (
    "差评",
    "吐槽",
    "避雷",
    "投诉",
    "问题",
    "失败",
    "bug",
    "崩",
    "卡顿",
    "翻车",
    "下滑",
    "质疑",
    "风险",
    "担忧",
    "隐私",
    "价格高",
    "涨价",
    "失望",
    "骗",
    "割韭菜",
    "争议",
    "封禁",
    "不满",
    "退货",
    "售后",
    "维权",
    "曝光",
)

CONTROVERSY_TERMS = (
    "争议",
    "质疑",
    "吐槽",
    "辟谣",
    "隐私",
    "涨价",
    "监管",
    "封禁",
    "投诉",
    "维权",
    "风险",
    "舆论",
    "对立",
    "分歧",
    "道歉",
)


def build_pulse_report(
    query: str,
    limit: int = DEFAULT_PULSE_LIMIT,
    site: str | None = None,
    sites: list[str] | None = None,
    scope: str | None = None,
    backend: str = "auto",
    profile: str | None = "china",
    read_top: int = 0,
    read_backend: str = "auto",
    max_read_chars: int = 1600,
    cache_ttl: int = 0,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Build a conservative topic echo report from public evidence."""
    from guanlan.web.read import read_url
    from guanlan.web.search import source_distribution

    query = query.strip()
    if not query:
        raise ValueError("query is required")

    results = _collect_results(
        query,
        limit=max(limit, 1),
        site=site,
        sites=sites or [],
        scope=scope,
        backend=backend,
        profile=profile,
        cache_ttl=cache_ttl,
        use_cache=use_cache,
    )

    readings: list[dict[str, Any]] = []
    for item in _reading_candidates(results, max(read_top, 0)):
        try:
            content = read_url(
                str(item.get("url", "")),
                max_chars=max(max_read_chars, 1),
                backend=read_backend,
                fallback_search=True,
                fallback_limit=DEFAULT_READ_FALLBACK_LIMIT,
                profile=profile,
            )
            readings.append({"url": item.get("url", ""), "status": "ok", "content": content})
        except Exception as e:
            readings.append({"url": item.get("url", ""), "status": "error", "error": str(e)})

    read_by_url = {item["url"]: item.get("content", "") for item in readings if item.get("status") == "ok"}
    samples = [_sample_from_result(item, read_by_url.get(item.get("url", ""), "")) for item in results]
    positive_counts = _count_terms(samples, "positive_terms")
    negative_counts = _count_terms(samples, "negative_terms")
    controversy_counts = _count_terms(samples, "controversy_terms")
    tendency = _tendency(sum(positive_counts.values()), sum(negative_counts.values()))
    confidence = _confidence(
        result_count=len(results),
        read_count=len(read_by_url),
        source_count=len({item.get("source_type") for item in results if item.get("source_type")}),
        signal_count=sum(positive_counts.values()) + sum(negative_counts.values()),
        search_only=not read_by_url,
    )

    return {
        "query": query,
        "profile": profile or "",
        "scope": scope or "",
        "site": site or "",
        "sites": sites or [],
        "limit": max(limit, 1),
        "read_top": max(read_top, 0),
        "read_success": len(read_by_url),
        "sample_count": len(results),
        "tendency": tendency,
        "confidence": confidence,
        "positive_terms": _top_terms(positive_counts),
        "negative_terms": _top_terms(negative_counts),
        "controversy_terms": _top_terms(controversy_counts),
        "source_distribution": source_distribution(results, "source_type"),
        "domain_distribution": source_distribution(results, "domain"),
        "samples": samples,
        "readings": readings,
        "method": "heuristic-v1: public search snippets + optional short reads",
        "caveats": [
            "这是基于当前公开样本的讨论倾向，不代表全网舆论。",
            "搜索摘要、标题和少量摘读会受到平台、排序、时间和可访问性的影响。",
            "中文反讽、黑话和平台语境可能导致正负词误判；请结合证据样本复核。",
        ],
    }


def format_pulse_markdown(report: dict[str, Any]) -> str:
    """Render a Pulse report as Markdown."""
    lines = [f"# 观澜回响 / {report.get('query', '')}", ""]
    lines.extend(["## 安全提示"])
    for caveat in report.get("caveats", []):
        lines.append(f"- {caveat}")

    lines.extend(
        [
            "",
            "## 概览",
            f"- 讨论倾向: {report.get('tendency', '样本不足')}",
            f"- 置信度: {report.get('confidence', '低')}",
            f"- 样本数: 搜索结果 {report.get('sample_count', 0)}；原文摘读成功 {report.get('read_success', 0)}",
            f"- 方法: {report.get('method', '')}",
        ]
    )
    if report.get("scope"):
        lines.append(f"- Scope: {report['scope']}")
    if report.get("site"):
        lines.append(f"- Site: {report['site']}")
    if report.get("sites"):
        lines.append(f"- Sites: {', '.join(report['sites'])}")

    lines.extend(["", "## 来源分布"])
    lines.extend(_format_distribution(report.get("source_distribution", [])))
    lines.extend(["", "## 域名分布"])
    lines.extend(_format_distribution(report.get("domain_distribution", [])))

    lines.extend(["", "## 关键词信号"])
    lines.append(f"- 正向词: {_term_text(report.get('positive_terms', []))}")
    lines.append(f"- 负向词: {_term_text(report.get('negative_terms', []))}")
    lines.append(f"- 争议点: {_term_text(report.get('controversy_terms', []))}")

    lines.extend(["", "## 证据样本"])
    samples = report.get("samples", [])
    if not samples:
        lines.append("暂无样本。")
    for idx, item in enumerate(samples[:8], start=1):
        lines.append(f"{idx}. [{item.get('stance', 'neutral')}] {item.get('title', '')}")
        lines.append(f"   {item.get('url', '')}")
        if item.get("snippet"):
            lines.append(f"   {item['snippet'][:220]}")
        matched = _sample_match_text(item)
        if matched:
            lines.append(f"   信号: {matched}")
    return "\n".join(lines)


def format_pulse_context(report: dict[str, Any]) -> str:
    """Render compact prompt context for agents."""
    lines = [
        f"# 观澜回响上下文 / {report.get('query', '')}",
        "",
        "字段 | 内容",
        "--- | ---",
        f"讨论倾向 | {report.get('tendency', '样本不足')}",
        f"置信度 | {report.get('confidence', '低')}",
        f"样本 | 搜索结果 {report.get('sample_count', 0)}；原文摘读成功 {report.get('read_success', 0)}",
        f"正向词 | {_term_text(report.get('positive_terms', []))}",
        f"负向词 | {_term_text(report.get('negative_terms', []))}",
        f"争议点 | {_term_text(report.get('controversy_terms', []))}",
        "边界 | 基于当前公开样本，不代表全网舆论；中文反讽和平台语境需人工复核。",
        "",
        "来源 | 标题 | 摘要 | 倾向",
        "--- | --- | --- | ---",
    ]
    for item in report.get("samples", [])[:8]:
        source = _pipe_safe(str(item.get("source_type") or item.get("domain") or "web"))
        title = _pipe_safe(str(item.get("title", "")))
        url = str(item.get("url", ""))
        snippet = _pipe_safe(str(item.get("snippet", ""))[:140])
        stance = str(item.get("stance", "neutral"))
        lines.append(f"{source} | [{title}]({url}) | {snippet} | {stance}")
    return "\n".join(lines)


def _collect_results(
    query: str,
    limit: int,
    site: str | None,
    sites: list[str],
    scope: str | None,
    backend: str,
    profile: str | None,
    cache_ttl: int,
    use_cache: bool,
) -> list[dict[str, Any]]:
    from guanlan.web.search import search_web

    targets = _normalize_sites(([site] if site else []) + sites)
    if not targets:
        return search_web(
            query,
            limit=limit,
            site=site,
            scope=scope,
            backend=backend,
            profile=profile,
            cache_ttl=cache_ttl,
            use_cache=use_cache,
        )

    combined: list[dict[str, Any]] = []
    per_site_limit = max(3, min(limit, (limit // max(len(targets), 1)) + 2))
    for target in targets:
        combined.extend(
            search_web(
                query,
                limit=per_site_limit,
                site=target,
                backend=backend,
                profile=profile,
                cache_ttl=cache_ttl,
                use_cache=use_cache,
            )
        )
    return _dedupe_dict_results(combined)[:limit]


def _sample_from_result(item: dict[str, Any], reading: str = "") -> dict[str, Any]:
    title = _collapse_ws(str(item.get("title", "")))
    snippet = _collapse_ws(str(item.get("snippet", "")))
    text = " ".join(part for part in (title, snippet, reading[:800]) if part)
    positive = _matched_terms(text, POSITIVE_TERMS)
    negative = _matched_terms(text, NEGATIVE_TERMS)
    controversy = _matched_terms(text, CONTROVERSY_TERMS)
    stance = _sample_stance(len(positive), len(negative))
    return {
        "title": title,
        "url": str(item.get("url", "")),
        "domain": str(item.get("domain", "")),
        "source_type": str(item.get("source_type", "通用网页")),
        "snippet": snippet,
        "stance": stance,
        "positive_terms": positive,
        "negative_terms": negative,
        "controversy_terms": controversy,
    }


def _reading_candidates(results: list[dict[str, Any]], read_top: int) -> list[dict[str, Any]]:
    if read_top <= 0:
        return []
    candidates = [item for item in results if item.get("topic_role") != "related"]
    if len(candidates) < read_top:
        seen = {item.get("url") for item in candidates}
        candidates.extend(item for item in results if item.get("url") not in seen)
    return candidates[:read_top]


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    matched = []
    for term in terms:
        if term.lower() in lowered:
            matched.append(term)
    return matched


def _count_terms(samples: list[dict[str, Any]], field: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for sample in samples:
        counts.update(sample.get(field, []))
    return counts


def _top_terms(counts: Counter[str], limit: int = 8) -> list[dict[str, Any]]:
    return [{"term": term, "count": count} for term, count in counts.most_common(limit)]


def _tendency(positive: int, negative: int) -> str:
    if positive == 0 and negative == 0:
        return "倾向不明显"
    if positive >= max(negative * 1.5, negative + 2):
        return "偏正向"
    if negative >= max(positive * 1.5, positive + 2):
        return "偏负向"
    if positive and negative:
        return "正负交织"
    return "倾向不明显"


def _confidence(
    result_count: int,
    read_count: int,
    source_count: int,
    signal_count: int,
    search_only: bool,
) -> str:
    if result_count < 5 or signal_count < 2:
        return "低"
    if result_count >= 8 and source_count >= 2 and signal_count >= 4:
        return "低-中" if search_only else "中"
    if read_count >= 2 and source_count >= 2:
        return "中"
    return "低-中"


def _sample_stance(positive: int, negative: int) -> str:
    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "neutral"


def _normalize_sites(sites: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for site in sites:
        value = (site or "").strip().lower()
        if not value:
            continue
        value = value.removeprefix("https://").removeprefix("http://").removeprefix("www.")
        value = value.split("/", 1)[0]
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized


def _dedupe_dict_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for item in results:
        key = str(item.get("url", "")).split("#", 1)[0]
        if not key or key in seen:
            continue
        seen.add(key)
        copied = dict(item)
        copied["rank"] = len(deduped) + 1
        deduped.append(copied)
    return deduped


def _format_distribution(rows: list[dict[str, Any]], width: int = 20) -> list[str]:
    if not rows:
        return ["- 暂无数据。"]
    max_count = max(int(item.get("count", 0)) for item in rows) or 1
    max_label = max(len(str(item.get("label", ""))) for item in rows)
    lines = []
    for item in rows[:8]:
        label = str(item.get("label", "unknown"))
        count = int(item.get("count", 0))
        percent = float(item.get("percent", 0.0))
        bar = "#" * max(1, round(count / max_count * width))
        lines.append(f"- {label.ljust(max_label)} {bar.ljust(width)} {percent:5.1f}% ({count})")
    return lines


def _term_text(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "未检出明显词项"
    return "，".join(f"{item['term']}({item['count']})" for item in rows)


def _sample_match_text(item: dict[str, Any]) -> str:
    parts = []
    if item.get("positive_terms"):
        parts.append("正向 " + "、".join(item["positive_terms"]))
    if item.get("negative_terms"):
        parts.append("负向 " + "、".join(item["negative_terms"]))
    if item.get("controversy_terms"):
        parts.append("争议 " + "、".join(item["controversy_terms"]))
    return "；".join(parts)


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _pipe_safe(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()
