# -*- coding: utf-8 -*-
"""Sidecar static HTML report rendering for Guanlan outputs.

This module is intentionally downstream-only: it accepts existing JSON/result
payloads and renders a self-contained HTML file. It does not run search, read,
archive, or any network operation.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_REPORT_TITLE = "Guanlan Report"
DEFAULT_REPORT_SUBTITLE = "Sidecar visual report generated from local Guanlan-style JSON."


def sample_report_payload() -> dict[str, Any]:
    """Return a compact demo payload for first-time report generation."""
    return {
        "title": "观澜旁支报表样例",
        "subtitle": "静态 HTML、深色信息密度、左侧指标栏、右侧主视觉图。",
        "summary": "这个报表能力只负责把已有结果渲染成可分享页面，不覆盖 search/read/research/hotnews 主链路。",
        "metrics": [
            {"label": "样本数", "value": "12", "note": "demo items"},
            {"label": "来源数", "value": "6", "note": "source diversity"},
            {"label": "平均信号", "value": "6.8", "note": "0-10"},
        ],
        "method": [
            "输入：本地 JSON、stdin，或内置 demo payload。",
            "渲染：单文件 HTML/CSS，无外部依赖。",
            "边界：不联网、不读取 Cookie、不写入 archive。",
        ],
        "not_this": [
            "不是新的搜索后端。",
            "不是事实裁决或民调。",
            "不是主 CLI 输出格式的替代品。",
        ],
        "items": [
            {"title": "搜索证据池", "source": "guanlan search", "summary": "多后端结果、信源分类、可追踪降级。", "score": 7.8, "value": 34, "category": "discover"},
            {"title": "研究证据包", "source": "guanlan research", "summary": "把结果整理为 Agent 可读证据包。", "score": 8.2, "value": 28, "category": "research"},
            {"title": "热榜观察", "source": "guanlan hotnews", "summary": "跨源热榜、趋势归并和简报。", "score": 6.9, "value": 21, "category": "signals"},
            {"title": "网页阅读", "source": "guanlan read", "summary": "Jina、直连、搜索兜底的阅读链路。", "score": 7.4, "value": 18, "category": "read"},
            {"title": "本地 archive", "source": "guanlan archive", "summary": "本地资料沉淀和检索，需要继续强化召回。", "score": 5.6, "value": 13, "category": "memory"},
            {"title": "助理视角", "source": "advisor", "summary": "基于证据的谨慎建议，不替代专业判断。", "score": 7.1, "value": 16, "category": "advisor"},
        ],
    }


def read_report_payload(input_path: str | None = None, *, stdin_text: str | None = None) -> Any:
    """Load JSON payload from a path, stdin text, or built-in sample."""
    if input_path == "-":
        text = stdin_text or ""
        if not text.strip():
            raise ValueError("stdin is empty; pass JSON into `guanlan report html --input -`")
        return json.loads(text)
    if input_path:
        return json.loads(Path(input_path).read_text(encoding="utf-8"))
    return sample_report_payload()


def write_html_report(
    payload: Any,
    output_path: str,
    *,
    title: str = "",
    subtitle: str = "",
    score_mode: str = "signal",
) -> dict[str, Any]:
    """Render payload to a static HTML file and return a small write summary."""
    html = render_html_report(payload, title=title, subtitle=subtitle, score_mode=score_mode)
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    normalized = normalize_report_payload(payload, title=title, subtitle=subtitle, score_mode=score_mode)
    return {
        "path": str(path.resolve()),
        "items": len(normalized["items"]),
        "metrics": len(normalized["metrics"]),
        "score_mode": normalized["score_mode"],
    }


def render_html_report(
    payload: Any,
    *,
    title: str = "",
    subtitle: str = "",
    score_mode: str = "signal",
    generated_at: str | None = None,
) -> str:
    """Render a self-contained dark HTML report."""
    normalized = normalize_report_payload(payload, title=title, subtitle=subtitle, score_mode=score_mode)
    generated = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    items = normalized["items"]
    tiles = _render_tiles(items, score_mode=normalized["score_mode"])
    findings = _render_findings(items[:12])
    metrics = _render_metrics(normalized["metrics"])
    categories = _render_distribution("分类", _count_by(items, "category"))
    sources = _render_distribution("来源", _count_by(items, "source"))
    caveats = _render_list(normalized["not_this"])
    method = _render_list(normalized["method"])
    title_html = escape(normalized["title"])
    subtitle_html = escape(normalized["subtitle"])
    summary_html = escape(normalized["summary"])

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title_html}</title>
  <style>
    :root {{
      --bg: #090a11;
      --panel: #11131d;
      --panel-2: #171923;
      --ink: #f3f4f0;
      --muted: #a7adbd;
      --quiet: #747b8d;
      --line: rgba(255,255,255,.09);
      --shadow: 0 30px 90px rgba(0,0,0,.36);
      --radius: 22px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 78% 8%, rgba(217, 135, 43, .16), transparent 27%),
        radial-gradient(circle at 20% 85%, rgba(96, 132, 50, .18), transparent 32%),
        var(--bg);
      color: var(--ink);
      font-family: "Avenir Next", "DIN Alternate", "PingFang SC", "Hiragino Sans GB", sans-serif;
      letter-spacing: -0.015em;
    }}
    .shell {{
      width: min(1500px, calc(100vw - 32px));
      min-height: calc(100vh - 32px);
      margin: 16px auto;
      display: grid;
      grid-template-columns: 310px 1fr;
      border: 1px solid var(--line);
      border-radius: 28px;
      overflow: hidden;
      background: rgba(12, 13, 21, .84);
      box-shadow: var(--shadow);
    }}
    aside {{
      padding: 28px 26px;
      background: linear-gradient(180deg, rgba(20,22,34,.96), rgba(10,11,18,.98));
      border-right: 1px solid var(--line);
    }}
    main {{ padding: 18px; min-width: 0; }}
    .eyebrow {{
      color: #d8b65b;
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: .16em;
      margin-bottom: 12px;
    }}
    h1 {{ margin: 0 0 10px; font-size: 30px; line-height: 1.05; letter-spacing: -0.04em; }}
    .subtitle {{ color: var(--muted); line-height: 1.55; font-size: 14px; }}
    .summary {{
      margin: 24px 0;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 16px;
      color: #d9ddcf;
      background: rgba(255,255,255,.035);
      line-height: 1.55;
      font-size: 14px;
    }}
    .metrics {{ display: grid; gap: 10px; margin: 22px 0; }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 13px 14px;
      background: rgba(255,255,255,.035);
    }}
    .metric .label {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
    .metric .value {{ margin-top: 6px; font-size: 28px; font-weight: 900; letter-spacing: -0.04em; }}
    .metric .note {{ color: var(--quiet); font-size: 12px; margin-top: 3px; }}
    .side-section {{ margin-top: 26px; }}
    .side-section h2 {{ margin: 0 0 10px; font-size: 13px; color: #e7e3c6; }}
    .side-section ul {{ margin: 0; padding-left: 17px; color: var(--muted); font-size: 12px; line-height: 1.65; }}
    .dist-row {{ display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; margin: 8px 0; color: var(--muted); font-size: 12px; }}
    .bar {{ height: 7px; border-radius: 999px; background: rgba(255,255,255,.06); overflow: hidden; }}
    .bar span {{ display: block; height: 100%; background: linear-gradient(90deg, #6c8f2e, #d89a2f); }}
    .topline {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 4px 18px;
      color: var(--muted);
      font-size: 13px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255,255,255,.035);
      color: #d7dbc9;
      white-space: nowrap;
    }}
    .map {{
      display: grid;
      grid-template-columns: repeat(18, minmax(34px, 1fr));
      grid-auto-rows: 58px;
      gap: 5px;
      min-height: 650px;
    }}
    .tile {{
      grid-column: span var(--sx);
      grid-row: span var(--sy);
      min-width: 0;
      overflow: hidden;
      border: 1px solid rgba(0,0,0,.45);
      border-radius: 8px;
      padding: 10px;
      background:
        linear-gradient(145deg, rgba(255,255,255,.12), transparent 38%),
        var(--tile);
      color: #f7f4e8;
      text-decoration: none;
      position: relative;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.04);
    }}
    .tile:hover {{ filter: brightness(1.12); }}
    .tile-title {{ font-size: clamp(13px, 1.25vw, 19px); font-weight: 900; line-height: 1.05; text-shadow: 0 1px 0 rgba(0,0,0,.18); }}
    .tile-meta {{ margin-top: 4px; color: rgba(255,255,255,.72); font-size: 12px; line-height: 1.35; }}
    .tile-summary {{ margin-top: 10px; color: rgba(255,255,255,.78); font-size: 12px; line-height: 1.45; max-width: 52ch; }}
    .below {{
      display: grid;
      grid-template-columns: 1.4fr .9fr;
      gap: 18px;
      margin-top: 18px;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: rgba(255,255,255,.035);
      padding: 20px;
    }}
    .card h2 {{ margin: 0 0 14px; font-size: 17px; }}
    .finding {{
      display: grid;
      grid-template-columns: 34px 1fr auto;
      gap: 12px;
      align-items: start;
      padding: 12px 0;
      border-top: 1px solid var(--line);
    }}
    .finding:first-of-type {{ border-top: 0; }}
    .rank {{ color: #d8b65b; font-weight: 900; }}
    .finding-title {{ color: var(--ink); font-weight: 800; }}
    .finding-title a {{ color: inherit; text-decoration: none; }}
    .finding-title a:hover {{ text-decoration: underline; }}
    .finding-summary {{ color: var(--muted); font-size: 13px; line-height: 1.5; margin-top: 4px; }}
    .score {{ color: #f2d179; font-variant-numeric: tabular-nums; font-weight: 800; }}
    @media (max-width: 900px) {{
      .shell {{ grid-template-columns: 1fr; }}
      aside {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .map {{ grid-template-columns: repeat(6, 1fr); grid-auto-rows: 72px; }}
      .below {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="eyebrow">Guanlan Sidecar Report</div>
      <h1>{title_html}</h1>
      <div class="subtitle">{subtitle_html}</div>
      <div class="summary">{summary_html}</div>
      <div class="metrics">{metrics}</div>
      {categories}
      {sources}
      <div class="side-section">
        <h2>What this is NOT</h2>
        {caveats}
      </div>
      <div class="side-section">
        <h2>Method</h2>
        {method}
      </div>
    </aside>
    <main>
      <div class="topline">
        <span>Generated {escape(generated)} · local static HTML</span>
        <span class="badge">旁支能力 · 不触发搜索/读取/归档</span>
      </div>
      <section class="map" aria-label="report mosaic">
        {tiles}
      </section>
      <section class="below">
        <div class="card">
          <h2>Top Items</h2>
          {findings}
        </div>
        <div class="card">
          <h2>Reading Rule</h2>
          <p class="finding-summary">颜色和面积是可视化编码，不是事实裁决。正式结论应回到原始链接、时间、来源类型和证据角色。</p>
          <p class="finding-summary">这个 HTML 适合汇报、归档和分享；严肃研究仍建议同时保留 Guanlan 原始 JSON/Markdown 输出。</p>
        </div>
      </section>
    </main>
  </div>
</body>
</html>"""


def normalize_report_payload(
    payload: Any,
    *,
    title: str = "",
    subtitle: str = "",
    score_mode: str = "signal",
) -> dict[str, Any]:
    """Normalize lists or Guanlan-style dictionaries into a report payload."""
    if isinstance(payload, list):
        raw: dict[str, Any] = {"items": payload}
    elif isinstance(payload, dict):
        raw = dict(payload)
    else:
        raise ValueError("report input must be a JSON object or array")

    items_raw = _extract_items(raw)
    items = [_normalize_item(item, index) for index, item in enumerate(items_raw)]
    if not items:
        items = [_normalize_item(item, index) for index, item in enumerate(sample_report_payload()["items"])]

    normalized_mode = score_mode if score_mode in {"signal", "risk", "quality"} else "signal"
    return {
        "title": title or str(raw.get("title") or raw.get("name") or DEFAULT_REPORT_TITLE),
        "subtitle": subtitle or str(raw.get("subtitle") or raw.get("description") or DEFAULT_REPORT_SUBTITLE),
        "summary": str(raw.get("summary") or raw.get("abstract") or _auto_summary(items)),
        "metrics": _normalize_metrics(raw.get("metrics"), items),
        "method": _normalize_text_list(
            raw.get("method") or raw.get("methodology"),
            fallback=[
                "输入来自本地 JSON、stdin 或内置样例。",
                "渲染过程不联网，不调用 Guanlan 搜索/阅读/归档主链路。",
                "结果适合展示和讨论，不替代原始证据审计。",
            ],
        ),
        "not_this": _normalize_text_list(
            raw.get("not_this") or raw.get("caveats") or raw.get("limitations"),
            fallback=[
                "不是事实最终裁决。",
                "不是全网民意或平台完整统计。",
                "不是 Guanlan 主链路输出的替代品。",
            ],
        ),
        "items": items,
        "score_mode": normalized_mode,
    }


def _extract_items(raw: dict[str, Any]) -> list[Any]:
    for key in ("items", "results", "records", "data", "documents", "entries"):
        value = raw.get(key)
        if isinstance(value, list):
            return value
    for key in ("packet", "payload"):
        value = raw.get(key)
        if isinstance(value, dict):
            nested = _extract_items(value)
            if nested:
                return nested
    return []


def _normalize_item(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {"title": str(item)}

    url = str(_pick(item, "url", "link", "href", default="") or "")
    title = str(_pick(item, "title", "name", "headline", "query", default="") or "")
    if not title:
        title = _domain_from_url(url) or f"Item {index + 1}"
    source = str(
        _pick(
            item,
            "source",
            "source_title",
            "source_id",
            "backend",
            "domain",
            default="",
        )
        or ""
    )
    if not source:
        source = _domain_from_url(url) or "unknown"
    summary = str(
        _pick(
            item,
            "summary",
            "snippet",
            "description",
            "abstract",
            "content",
            "text",
            default="",
        )
        or ""
    )
    category = str(_pick(item, "category", "source_type", "intent", "evidence_role", default="general") or "general")
    score = _coerce_number(
        _pick(
            item,
            "score",
            "source_score",
            "quality",
            "quality_score",
            "ai_score",
            "trust_score",
            "risk_score",
            default=None,
        )
    )
    if score is None:
        rank = _coerce_number(_pick(item, "rank", "position", default=None))
        score = max(1.0, 10.0 - (rank or index + 1) * 0.45)
    score = _normalize_score(score)
    value = _coerce_number(_pick(item, "value", "count", "heat", "size", "weight", "employment", default=None))
    if value is None:
        value = max(1.0, score * 3.0)

    return {
        "rank": index + 1,
        "title": _compact(title, 80),
        "url": url,
        "source": _compact(source, 40),
        "summary": _compact(summary, 220),
        "category": _compact(category, 36),
        "score": score,
        "value": max(value, 1.0),
    }


def _normalize_metrics(raw_metrics: Any, items: list[dict[str, Any]]) -> list[dict[str, str]]:
    if isinstance(raw_metrics, list) and raw_metrics:
        metrics = []
        for item in raw_metrics[:8]:
            if not isinstance(item, dict):
                continue
            metrics.append(
                {
                    "label": str(item.get("label") or item.get("name") or "Metric"),
                    "value": str(item.get("value") or item.get("count") or "0"),
                    "note": str(item.get("note") or item.get("description") or ""),
                }
            )
        if metrics:
            return metrics

    sources = {item["source"] for item in items if item.get("source")}
    scores = [float(item["score"]) for item in items if item.get("score") is not None]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    return [
        {"label": "样本数", "value": str(len(items)), "note": "rendered items"},
        {"label": "来源数", "value": str(len(sources)), "note": "unique source labels"},
        {"label": "平均信号", "value": f"{avg_score:.1f}", "note": "0-10 visual score"},
    ]


def _normalize_text_list(value: Any, *, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or fallback
    if isinstance(value, str) and value.strip():
        return [line.strip() for line in value.splitlines() if line.strip()] or fallback
    return fallback


def _auto_summary(items: list[dict[str, Any]]) -> str:
    sources = len({item["source"] for item in items if item.get("source")})
    return f"共渲染 {len(items)} 条结果，覆盖 {sources} 个来源；这是展示层报表，不改变 Guanlan 主链路。"


def _render_tiles(items: list[dict[str, Any]], *, score_mode: str) -> str:
    max_value = max((float(item.get("value") or 1.0) for item in items), default=1.0)
    lines = []
    for index, item in enumerate(items):
        ratio = math.sqrt(float(item.get("value") or 1.0) / max_value)
        sx = _clamp_int(round(2 + ratio * 7), 2, 10)
        sy = _clamp_int(round(1 + ratio * 6), 1, 7)
        if index == 0:
            sx = max(sx, 8)
            sy = max(sy, 5)
        color = _score_color(float(item["score"]), score_mode=score_mode)
        href = _safe_href(item.get("url", ""))
        tag = "a" if href else "div"
        href_attr = f' href="{escape(href, quote=True)}" target="_blank" rel="noreferrer"' if href else ""
        summary = escape(str(item.get("summary") or ""))
        summary_html = f'<div class="tile-summary">{summary}</div>' if summary and sx >= 4 and sy >= 3 else ""
        lines.append(
            f'<{tag} class="tile" style="--sx:{sx};--sy:{sy};--tile:{color};"{href_attr}>'
            f'<div class="tile-title">{escape(str(item["title"]))}</div>'
            f'<div class="tile-meta">{escape(str(item["score"]))}/10 · {escape(str(item["source"]))}</div>'
            f"{summary_html}</{tag}>"
        )
    return "\n        ".join(lines)


def _render_findings(items: list[dict[str, Any]]) -> str:
    lines = []
    for item in items:
        href = _safe_href(item.get("url", ""))
        title = escape(str(item["title"]))
        if href:
            title = f'<a href="{escape(href, quote=True)}" target="_blank" rel="noreferrer">{title}</a>'
        lines.append(
            '<div class="finding">'
            f'<div class="rank">#{item["rank"]}</div>'
            '<div>'
            f'<div class="finding-title">{title}</div>'
            f'<div class="finding-summary">{escape(str(item.get("summary") or item.get("source") or ""))}</div>'
            '</div>'
            f'<div class="score">{float(item["score"]):.1f}</div>'
            '</div>'
        )
    return "\n          ".join(lines)


def _render_metrics(metrics: list[dict[str, str]]) -> str:
    return "\n        ".join(
        '<div class="metric">'
        f'<div class="label">{escape(metric["label"])}</div>'
        f'<div class="value">{escape(metric["value"])}</div>'
        f'<div class="note">{escape(metric.get("note", ""))}</div>'
        '</div>'
        for metric in metrics
    )


def _render_distribution(title: str, counts: dict[str, int]) -> str:
    if not counts:
        return ""
    total = sum(counts.values()) or 1
    rows = []
    for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:6]:
        pct = round(count / total * 100)
        rows.append(
            '<div class="dist-row">'
            f'<span>{escape(label)}</span><span>{count}</span>'
            f'<div class="bar" style="grid-column: 1 / -1"><span style="width:{pct}%"></span></div>'
            '</div>'
        )
    return f'<div class="side-section"><h2>{escape(title)}</h2>{"".join(rows)}</div>'


def _render_list(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        label = str(item.get(key) or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts


def _score_color(score: float, *, score_mode: str) -> str:
    score = max(0.0, min(score, 10.0))
    if score_mode == "quality":
        hue = 8 + score * 10
    else:
        hue = 105 - score * 8.5
    saturation = 56
    lightness = 24 if score < 7 else 28
    return f"hsl({hue:.0f} {saturation}% {lightness}%)"


def _normalize_score(value: float) -> float:
    if value > 10 and value <= 100:
        return round(value / 10.0, 1)
    if value > 100:
        return 10.0
    return round(max(0.0, min(value, 10.0)), 1)


def _coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    multiplier = 1.0
    if "亿" in text:
        multiplier = 100000000.0
    elif "万" in text:
        multiplier = 10000.0
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0)) * multiplier


def _pick(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return default


def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def _safe_href(url: Any) -> str:
    text = str(url or "").strip()
    if text.startswith(("https://", "http://")):
        return text
    return ""


def _compact(text: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "…"


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))
