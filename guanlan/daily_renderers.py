# -*- coding: utf-8 -*-
"""Additional daily report renderers."""

from __future__ import annotations

import html
from typing import Any


def format_daily_im(report: dict[str, Any]) -> str:
    """Render a compact IM-friendly daily."""
    title = str(report.get("title") or report.get("query") or "中文互联网")
    lines = [f"【观澜日报】{title}"]
    health = report.get("editorial_health") or {}
    if health.get("status") == "block":
        lines.append("采编状态：block，当前材料不能当成品日报。")
    elif health.get("status"):
        lines.append(f"采编状态：{health.get('status')}")
    summary = report.get("highlights") or []
    if summary:
        lines.append("")
        lines.append("今日摘要")
        lines.extend(f"- {item}" for item in summary[:3])
    storylines = report.get("storylines") or []
    if storylines:
        lines.append("")
        lines.append("今日主线")
        for idx, story in enumerate(storylines[:5], start=1):
            lines.append(
                f"{idx}. {story.get('headline', '')}｜{story.get('freshness_label') or story.get('freshness', '')}"
                f"｜风险 {story.get('risk_level', 'low')}｜动作 {story.get('recommended_action', '')}"
            )
            evidence = story.get("evidence_items") or []
            if evidence:
                first = evidence[0]
                url = str(first.get("url") or "")
                source = str(first.get("source") or "")
                lines.append(f"   证据：{first.get('title', '')}" + (f"（{source}）" if source else ""))
                if url:
                    lines.append(f"   链接：{url}")
    decisions = report.get("editorial_decisions") or []
    if decisions:
        lines.append("")
        lines.append("可行动作")
        for row in decisions[:5]:
            teams = "、".join(row.get("teams") or [])
            lines.append(f"- {row.get('recommended_action', '')}｜{row.get('headline', '')}｜{teams}")
    boundaries = report.get("boundaries") or []
    if boundaries:
        lines.append("")
        lines.append("边界")
        lines.extend(f"- {item}" for item in boundaries[:3])
    return "\n".join(lines)


def format_daily_html(report: dict[str, Any]) -> str:
    """Render a single-file static HTML daily."""
    title = str(report.get("title") or report.get("query") or "中文互联网")
    storylines = report.get("storylines") or []
    health = report.get("editorial_health") or {}
    source_health = report.get("source_health") or {}
    cards = "\n".join(_storyline_card(story) for story in storylines)
    actions = "\n".join(_action_row(row) for row in report.get("editorial_decisions") or [])
    overflow = "\n".join(_overflow_row(row) for row in report.get("overflow_items") or [])
    checks = "\n".join(f"<li>{_e(warning)}</li>" for warning in (health.get("warnings") or source_health.get("warnings") or []))
    if not checks:
        checks = "<li>当前未触发阻断型采编告警。</li>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>观澜日报 / {_e(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#18202a; --muted:#647084; --line:#e5e9f0; --soft:#f6f8fb; --brand:#0f766e; --warn:#b45309; --risk:#b91c1c; }}
    body {{ margin:0; font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#fff; }}
    main {{ max-width:1180px; margin:0 auto; padding:32px 24px 48px; }}
    h1 {{ font-size:32px; line-height:1.2; margin:0 0 8px; letter-spacing:0; }}
    h2 {{ font-size:20px; margin:28px 0 12px; border-bottom:1px solid var(--line); padding-bottom:8px; }}
    .meta {{ color:var(--muted); display:flex; gap:14px; flex-wrap:wrap; }}
    .summary {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:20px 0; }}
    .metric {{ border:1px solid var(--line); background:var(--soft); padding:12px; border-radius:8px; }}
    .metric strong {{ display:block; font-size:22px; }}
    .story {{ border:1px solid var(--line); border-radius:8px; padding:16px; margin:12px 0; }}
    .story h3 {{ font-size:18px; margin:0 0 8px; }}
    .chips {{ display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; }}
    .chip {{ border:1px solid var(--line); border-radius:999px; padding:2px 9px; color:var(--muted); background:#fff; }}
    .chip.risk-high {{ color:#fff; background:var(--risk); border-color:var(--risk); }}
    .chip.risk-medium {{ color:#fff; background:var(--warn); border-color:var(--warn); }}
    .evidence {{ margin:10px 0 0; padding-left:18px; }}
    a {{ color:var(--brand); text-decoration:none; }}
    table {{ border-collapse:collapse; width:100%; }}
    th,td {{ border:1px solid var(--line); padding:8px 10px; vertical-align:top; }}
    th {{ background:var(--soft); text-align:left; }}
    .muted {{ color:var(--muted); }}
    @media (max-width: 760px) {{ .summary {{ grid-template-columns:1fr 1fr; }} main {{ padding:24px 16px; }} }}
  </style>
</head>
<body>
<main>
  <h1>观澜日报 / {_e(title)}</h1>
  <div class="meta">
    <span>生成时间：{_e(str(report.get("generated_at") or ""))}</span>
    <span>版本：{_e(str(report.get("schema_version") or ""))}</span>
    <span>时间窗：{_e(str(report.get("time_window") or ""))}</span>
    <span>采编状态：{_e(str(health.get("status") or "unknown"))}</span>
  </div>
  <section class="summary">
    <div class="metric"><strong>{int(report.get("candidate_count") or 0)}</strong><span>公开线索</span></div>
    <div class="metric"><strong>{len(storylines)}</strong><span>主线</span></div>
    <div class="metric"><strong>{int(source_health.get("today_count") or 0)}</strong><span>今日证据</span></div>
    <div class="metric"><strong>{int(source_health.get("main_weak_lead_count") or 0)}</strong><span>正文弱线索</span></div>
  </section>
  <h2>今日主线</h2>
  {cards or '<p class="muted">暂无可用主线。</p>'}
  <h2>可行动作</h2>
  <table><thead><tr><th>动作</th><th>主线</th><th>团队</th><th>风险</th></tr></thead><tbody>{actions or '<tr><td colspan="4">暂无动作建议。</td></tr>'}</tbody></table>
  <h2>候补线索池</h2>
  <table><thead><tr><th>线索</th><th>层级</th><th>说明</th></tr></thead><tbody>{overflow or '<tr><td colspan="3">暂无候补线索。</td></tr>'}</tbody></table>
  <h2>采编自检</h2>
  <ul>{checks}</ul>
</main>
</body>
</html>"""


def _storyline_card(story: dict[str, Any]) -> str:
    risk = str(story.get("risk_level") or "low")
    chips = [
        str(story.get("freshness_label") or story.get("freshness") or ""),
        f"风险 {risk}",
        f"动作 {story.get('recommended_action', '')}",
        f"信心 {story.get('confidence', '')}",
        "团队 " + "、".join(story.get("teams") or []),
    ]
    evidence = "\n".join(_evidence_li(row) for row in story.get("evidence_items") or [])
    return f"""
  <article class="story">
    <h3>{_e(str(story.get("headline") or ""))}</h3>
    <div class="chips">{''.join(f'<span class="chip risk-{risk if chip == f"风险 {risk}" else ""}">{_e(chip)}</span>' for chip in chips if chip)}</div>
    <p><strong>发生了什么：</strong>{_e(str(story.get("what_happened") or ""))}</p>
    <p><strong>为什么重要：</strong>{_e(str(story.get("why_it_matters") or ""))}</p>
    <ul class="evidence">{evidence}</ul>
  </article>"""


def _evidence_li(row: dict[str, Any]) -> str:
    title = _e(str(row.get("title") or ""))
    source = _e(str(row.get("source") or ""))
    tier = _e(str(row.get("source_tier") or ""))
    url = str(row.get("url") or "")
    title_html = f'<a href="{_e(url)}">{title}</a>' if url else title
    return f"<li>{title_html} <span class=\"muted\">{source} · {tier}</span></li>"


def _action_row(row: dict[str, Any]) -> str:
    teams = "、".join(row.get("teams") or [])
    return (
        "<tr>"
        f"<td>{_e(str(row.get('recommended_action') or ''))}</td>"
        f"<td>{_e(str(row.get('headline') or ''))}</td>"
        f"<td>{_e(teams)}</td>"
        f"<td>{_e(str(row.get('risk_level') or ''))}</td>"
        "</tr>"
    )


def _overflow_row(row: dict[str, Any]) -> str:
    title = _e(str(row.get("title") or ""))
    url = str(row.get("url") or "")
    title_html = f'<a href="{_e(url)}">{title}</a>' if url else title
    return (
        "<tr>"
        f"<td>{title_html}</td>"
        f"<td>{_e(str(row.get('source_tier') or row.get('section_title') or ''))}</td>"
        f"<td>{_e(str(row.get('overflow_note') or ''))}</td>"
        "</tr>"
    )


def _e(value: str) -> str:
    return html.escape(str(value or ""), quote=True)
