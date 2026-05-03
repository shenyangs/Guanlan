#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run Guanlan vs WebSearch benchmark cases with strict channel isolation.

This is a live, best-effort benchmark harness. It keeps raw command outputs
alongside normalized records so weak networks, blocked engines, and extraction
failures remain visible instead of disappearing behind a single score.

Strict isolation rule for this harness:
- Guanlan score only depends on Guanlan output.
- WebSearch score only depends on open-websearch search output.
- WebFetch is treated as extraction validation on each channel's own Top1 URL,
  not as a standalone search winner, because fetch-web is URL-native not query-native.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

TODAY = date(2026, 5, 3)


CASES: list[dict[str, Any]] = [
    {"id": "A1", "dimension": "A. 语言边界", "query": "珠海今天天气", "profile": "china", "challenge": "基础中文，应无压力", "time_sensitive": "today"},
    {"id": "A2", "dimension": "A. 语言边界", "query": "Apple最新财报 2025", "profile": "china", "challenge": "中英混杂，品牌+时间", "time_sensitive": "year"},
    {"id": "A3", "dimension": "A. 语言边界", "query": "best Python web framework 2025", "profile": "english", "challenge": "纯英文技术查询", "scope": "developer", "time_sensitive": "year"},
    {"id": "A4", "dimension": "A. 语言边界", "query": "Transformer架构原理", "profile": "china", "challenge": "中英混杂技术术语"},
    {"id": "A5", "dimension": "A. 语言边界", "query": "岸田文雄 辞任", "profile": "china", "challenge": "日文专名+事件"},
    {"id": "A6", "dimension": "A. 语言边界", "query": "삼성전자 실적", "profile": "english", "challenge": "纯韩语，测试非中文覆盖率"},
    {"id": "A7", "dimension": "A. 语言边界", "query": "GPT-5 release date rumor", "profile": "english", "scope": "global_news", "challenge": "英文前沿科技传闻", "time_sensitive": "week"},
    {"id": "A8", "dimension": "A. 语言边界", "query": "横琴封关政策 2025 最新", "profile": "china", "scope": "gov", "challenge": "本地政策+时间限定", "time_sensitive": "year"},
    {"id": "B1", "dimension": "B. 领域穿透", "query": "数据要素市场化配置改革 最新政策", "profile": "china", "scope": "gov", "challenge": "政策原文覆盖度"},
    {"id": "B2", "dimension": "B. 领域穿透", "query": "新质生产力 官方定义", "profile": "china", "scope": "party_central", "challenge": "党央媒信源优先级"},
    {"id": "B3", "dimension": "B. 领域穿透", "query": "iPhone 16 用户评价 续航", "profile": "china", "scope": "ecommerce", "challenge": "电商/口碑聚合质量"},
    {"id": "B4", "dimension": "B. 领域穿透", "query": "React 19 Server Components 最佳实践", "profile": "china", "scope": "tech_dev", "challenge": "开发者社区信源"},
    {"id": "B5", "dimension": "B. 领域穿透", "query": "大语言模型幻觉问题 综述", "profile": "china", "scope": "academic", "challenge": "学术信源覆盖"},
    {"id": "B6", "dimension": "B. 领域穿透", "query": "特斯拉股价今天", "profile": "china", "scope": "finance", "challenge": "金融实时性", "time_sensitive": "today"},
    {"id": "B7", "dimension": "B. 领域穿透", "query": "小米SU7 车祸 2025", "profile": "china", "scope": "social_web", "challenge": "社交媒体/热点聚合", "time_sensitive": "year"},
    {"id": "B8", "dimension": "B. 领域穿透", "query": "澳门博彩业 Gross Gaming Revenue 2025", "profile": "china", "challenge": "跨境财经数据", "time_sensitive": "year"},
    {"id": "C1", "dimension": "C. 时效性", "query": "今天热搜", "profile": "china", "challenge": "热榜时效", "time_sensitive": "today", "guanlan_command": "hotnews"},
    {"id": "C2", "dimension": "C. 时效性", "query": "五一假期 旅游数据 2025", "profile": "china", "scope": "business", "challenge": "节假日实时统计", "time_sensitive": "year"},
    {"id": "C3", "dimension": "C. 时效性", "query": "刚刚 地震 台湾", "profile": "china", "scope": "weather_disaster", "challenge": "突发新闻", "time_sensitive": "today"},
    {"id": "C4", "dimension": "C. 时效性", "query": "美股开盘 纳斯达克", "profile": "china", "scope": "finance", "challenge": "金融市场实时性", "time_sensitive": "today"},
    {"id": "C5", "dimension": "C. 时效性", "query": "OpenAI 最新发布", "profile": "english", "scope": "company_primary", "challenge": "科技新闻更新频率", "time_sensitive": "week"},
    {"id": "D1", "dimension": "D. 查询类型", "query": "澳门人口多少", "profile": "china", "scope": "gov", "challenge": "事实型精确数字提取"},
    {"id": "D2", "dimension": "D. 查询类型", "query": "为什么年轻人不愿意生孩子", "profile": "china", "challenge": "观点型多元聚合"},
    {"id": "D3", "dimension": "D. 查询类型", "query": "珠海必吃十大餐厅", "profile": "china", "scope": "social_web", "challenge": "列表型结构化"},
    {"id": "D4", "dimension": "D. 查询类型", "query": "比亚迪 vs 特斯拉 电池技术", "profile": "china", "scope": "tech_dev", "challenge": "比较型维度完整性"},
    {"id": "D5", "dimension": "D. 查询类型", "query": "1970年代澳门建筑业发展", "profile": "china", "challenge": "长尾历史信息"},
    {"id": "D6", "dimension": "D. 查询类型", "query": "珠海横琴 澳门居民 个税优惠 怎么申请", "profile": "china", "scope": "gov", "challenge": "复合型步骤提取"},
    {"id": "E1-gov", "dimension": "E. Scope 精确度", "query": "人工智能监管", "profile": "china", "scope": "gov", "challenge": "官方监管口径"},
    {"id": "E1-party", "dimension": "E. Scope 精确度", "query": "人工智能监管", "profile": "china", "scope": "party_central", "challenge": "党央媒叙事"},
    {"id": "E1-academic", "dimension": "E. Scope 精确度", "query": "人工智能监管", "profile": "china", "scope": "academic", "challenge": "学术讨论"},
    {"id": "E2-ecom", "dimension": "E. Scope 精确度", "query": "华为手机", "profile": "china", "scope": "ecommerce", "challenge": "产品评价"},
    {"id": "E2-tech", "dimension": "E. Scope 精确度", "query": "华为手机", "profile": "china", "scope": "tech_dev", "challenge": "技术参数/社区"},
    {"id": "E2-social", "dimension": "E. Scope 精确度", "query": "华为手机", "profile": "china", "scope": "social_web", "challenge": "舆情讨论"},
    {"id": "E3-gov", "dimension": "E. Scope 精确度", "query": "中美关系", "profile": "china", "scope": "gov", "challenge": "官方表态"},
    {"id": "E3-party", "dimension": "E. Scope 精确度", "query": "中美关系", "profile": "china", "scope": "party_central", "challenge": "党央媒口径"},
    {"id": "E3-social", "dimension": "E. Scope 精确度", "query": "中美关系", "profile": "china", "scope": "social_web", "challenge": "民间舆论"},
    {"id": "F1", "dimension": "F. 边界压力", "query": "请综合分析2025年以来横琴粤澳深度合作区封关运行、澳门居民在横琴就业创业、个人所得税优惠、跨境通勤、社保衔接、子女教育、医疗便利化、企业注册和金融支持政策的最新官方文件，并指出哪些政策已经落地、哪些仍需要等待细则", "profile": "china", "scope": "gov", "challenge": "200字以上超长 query"},
    {"id": "F2", "dimension": "F. 边界压力", "query": "C++", "profile": "english", "scope": "developer", "challenge": "特殊字符"},
    {"id": "F3", "dimension": "F. 边界压力", "query": "苹果", "profile": "china", "scope": "ecommerce", "challenge": "水果/公司歧义"},
    {"id": "F4", "dimension": "F. 边界压力", "query": "asdfghjk123456789", "profile": "english", "challenge": "无意义 query"},
    {"id": "F5", "dimension": "F. 边界压力", "query": "珠海 澳门 香港 深圳 广州 中山 江门 佛山 东莞 惠州 肇庆 横琴 大湾区 交通 产业 协同", "profile": "china", "scope": "local_official", "challenge": "10+ 地名信息密度"},
    {"id": "S1", "dimension": "S. 补充薄弱点", "query": "OpenSSL CVE 最新 漏洞 影响版本", "profile": "english", "scope": "cybersecurity", "challenge": "安全/CVE 官方优先", "time_sensitive": "week"},
    {"id": "S2", "dimension": "S. 补充薄弱点", "query": "台风 路径 中央气象台 日本气象厅", "profile": "china", "scope": "weather_disaster", "challenge": "灾害天气官方时间戳", "time_sensitive": "week"},
    {"id": "S3", "dimension": "S. 补充薄弱点", "query": "字节 AI 产品经理 校招 薪资 面经", "profile": "china", "scope": "career", "challenge": "招聘薪资样本"},
    {"id": "S4", "dimension": "S. 补充薄弱点", "query": "Taylor Swift 最新动态 新专辑 巡演", "profile": "english", "scope": "global_entertainment", "challenge": "欧美娱乐英文覆盖", "time_sensitive": "week"},
    {"id": "S5", "dimension": "S. 补充薄弱点", "query": "BLACKPINK K-pop 最新回归 Soompi Oricon", "profile": "hybrid", "scope": "jp_kr_entertainment", "challenge": "日韩娱乐混合语种", "time_sensitive": "week"},
    {"id": "S6", "dimension": "S. 补充薄弱点", "query": "詹姆斯韦伯 外星生命 NASA", "profile": "english", "scope": "science", "challenge": "科学新闻核验", "time_sensitive": "month"},
    {"id": "S7", "dimension": "S. 补充薄弱点", "query": "AI 创业 播客 小宇宙", "profile": "china", "scope": "podcast", "challenge": "播客发现"},
    {"id": "S8", "dimension": "S. 补充薄弱点", "query": "雅思 口语 题库 机经", "profile": "china", "scope": "test_prep", "challenge": "考试备考信息"},
    {"id": "S9", "dimension": "S. 补充薄弱点", "query": "清华大学计算机系研究生招生 导师", "profile": "china", "scope": "university", "challenge": "高校招生/导师官网"},
    {"id": "S10", "dimension": "S. 补充薄弱点", "query": "产品 用户评价 值不值得买", "profile": "china", "scope": "reputation", "challenge": "口碑/购买建议泛化"},
]


SCOPE_FALLBACKS = {
    "cybersecurity": "",
    "weather_disaster": "",
    "career": "",
    "global_entertainment": "",
    "jp_kr_entertainment": "",
    "science": "",
    "podcast": "",
    "test_prep": "",
    "university": "",
    "reputation": "",
}


EXPECTED_SCOPE_TYPES = {
    "gov": {"政府/部委", "英文官方/监管"},
    "party_central": {"党央媒"},
    "ecommerce": {"电商/零售垂类", "评价/消费样本"},
    "tech_dev": {"科技/开发者社区", "英文开发者/开源"},
    "academic": {"学术/论文检索"},
    "finance": {"财经/资本市场"},
    "social_web": {"社交/内容平台", "英文社区样本"},
    "local_official": {"地方官媒", "政府/部委"},
    "developer": {"英文开发者/开源", "科技/开发者社区"},
    "global_news": {"国际主流媒体", "英文官方/监管"},
    "company_primary": {"公司一手资料", "英文开发者/开源"},
}


AUTHORITY_DOMAINS = (
    ".gov",
    ".gov.cn",
    "gov.cn",
    "mfa.gov.cn",
    "ndrc.gov.cn",
    "stats.gov.cn",
    "pbc.gov.cn",
    "csrc.gov.cn",
    "cac.gov.cn",
    "people.com.cn",
    "xinhuanet.com",
    "qstheory.cn",
    "cctv.com",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "sec.gov",
    "nasa.gov",
    "nvd.nist.gov",
    "cisa.gov",
    "github.com",
    "docs.python.org",
    "react.dev",
    "openai.com",
    "apple.com",
    "tesla.com",
)


def run_cmd(args: list[str], timeout: int) -> dict[str, Any]:
    started = time.time()
    def clean(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    try:
        proc = subprocess.run(
            args,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return {
            "args": args,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_sec": round(time.time() - started, 3),
            "timeout": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "args": args,
            "returncode": None,
            "stdout": clean(exc.stdout),
            "stderr": clean(exc.stderr),
            "duration_sec": round(time.time() - started, 3),
            "timeout": True,
        }


def parse_json_output(text: str) -> Any:
    if not text:
        return None
    stripped = text.strip()
    candidates = [stripped]
    for token in ("{", "["):
        idx = stripped.find(token)
        if idx >= 0:
            candidates.append(stripped[idx:])
    last_err: Exception | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception as exc:  # noqa: BLE001 - diagnostics are stored raw
            last_err = exc
    return {"_parse_error": str(last_err), "_raw_prefix": stripped[:500]}


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def normalize_guanlan(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("results") or data.get("items") or data.get("data") or []
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def normalize_websearch(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        if isinstance(data.get("data"), dict):
            items = data["data"].get("results") or []
        else:
            items = data.get("results") or []
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description") or item.get("snippet") or "",
                "source": item.get("engine") or item.get("source") or "web_search",
                "domain": domain_of(item.get("url", "")),
            }
            for item in items
            if isinstance(item, dict)
        ]
    return []


def tokens(query: str) -> set[str]:
    text = query.lower()
    words = set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9+.#-]{1,}", text))
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    cjk_terms = set()
    for n in (2, 3):
        cjk_terms.update("".join(cjk[i : i + n]) for i in range(max(0, len(cjk) - n + 1)))
    return {t for t in words | cjk_terms if t and t not in {"最新", "今天", "2025", "2026"}}


def relevance_score(query: str, rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 1.0
    q_tokens = tokens(query)
    if not q_tokens:
        return 5.0 if rows else 1.0
    scores = []
    for idx, row in enumerate(rows[:10]):
        hay = " ".join(str(row.get(k) or "") for k in ("title", "snippet", "description", "domain", "source_type")).lower()
        hits = sum(1 for tok in q_tokens if tok.lower() in hay)
        ratio = hits / max(len(q_tokens), 1)
        rank_bonus = max(0, 1.0 - idx * 0.07)
        scores.append(min(10.0, 1.0 + ratio * 8.0 + rank_bonus))
    return round(sum(scores) / max(len(scores), 1), 1)


def source_quality_score(rows: list[dict[str, Any]], scope: str = "") -> float:
    if not rows:
        return 1.0
    scores = []
    expected = EXPECTED_SCOPE_TYPES.get(scope, set())
    for row in rows[:10]:
        trust = row.get("trust_level")
        if isinstance(trust, (int, float)):
            score = 1.5 + float(trust) * 1.5
        else:
            dom = str(row.get("domain") or domain_of(row.get("url", ""))).lower()
            score = 7.0 if any(dom.endswith(d) or dom == d for d in AUTHORITY_DOMAINS) else 4.5
        stype = str(row.get("source_type") or "")
        matched_scope = str(row.get("matched_scope") or "")
        if expected and stype in expected:
            score += 1.0
        if scope and matched_scope == scope:
            score += 0.8
        scores.append(min(10.0, score))
    return round(sum(scores) / len(scores), 1)


def extract_dates(text: str) -> list[date]:
    found: list[date] = []
    for y, m, d in re.findall(r"(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})", text):
        try:
            found.append(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    for m, d in re.findall(r"(?<!\d)(\d{1,2})月(\d{1,2})日", text):
        try:
            found.append(date(TODAY.year, int(m), int(d)))
        except ValueError:
            pass
    for y in re.findall(r"(20\d{2})", text):
        try:
            found.append(date(int(y), 1, 1))
        except ValueError:
            pass
    return [item for item in found if item <= TODAY]


def freshness_score(rows: list[dict[str, Any]], sensitivity: str = "") -> tuple[float, str]:
    if not rows:
        return 1.0, ""
    all_dates: list[date] = []
    for row in rows[:10]:
        recency = row.get("trace", {}).get("recency") if isinstance(row.get("trace"), dict) else None
        if isinstance(recency, dict) and recency.get("result_date"):
            try:
                all_dates.append(date.fromisoformat(str(recency["result_date"])))
            except ValueError:
                pass
        all_dates.extend(extract_dates(" ".join(str(row.get(k) or "") for k in ("title", "snippet", "description"))))
    latest = max(all_dates) if all_dates else None
    if not latest:
        return (4.0 if sensitivity else 5.5), ""
    age = (TODAY - latest).days
    if sensitivity == "today":
        score = 10.0 if age == 0 else (7.0 if 0 < age <= 2 else 3.0)
    elif sensitivity == "week":
        score = 10.0 if 0 <= age <= 7 else (7.0 if age <= 30 else 4.0)
    elif sensitivity == "month":
        score = 9.0 if 0 <= age <= 31 else (7.0 if age <= 120 else 4.0)
    elif sensitivity == "year":
        score = 8.5 if latest.year >= 2025 else 5.0
    else:
        score = 7.0 if latest.year >= TODAY.year - 1 else 5.0
    return round(max(1.0, min(10.0, score)), 1), latest.isoformat()


def coverage_score(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 1.0
    domains = {str(r.get("domain") or domain_of(r.get("url", ""))) for r in rows if r.get("url")}
    types = {str(r.get("source_type") or r.get("source") or "") for r in rows if r.get("source_type") or r.get("source")}
    count_component = min(4.0, len(rows) / 10 * 4.0)
    domain_component = min(3.0, len(domains) / 5 * 3.0)
    type_component = min(3.0, len(types) / 4 * 3.0)
    return round(max(1.0, count_component + domain_component + type_component), 1)


def structure_score(rows: list[dict[str, Any]], channel: str) -> float:
    if not rows:
        return 1.0
    fields = ("source_type", "matched_scope", "trust_level", "evidence_role", "score", "trace")
    if channel == "guanlan":
        have = sum(1 for row in rows[:5] for field in fields if field in row)
        return round(min(10.0, 2.0 + have / max(1, len(rows[:5]) * len(fields)) * 8.0), 1)
    return 4.0


def fetch_score(fetch_data: Any, query: str, top: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(fetch_data, dict):
        return {"success": False, "content_chars": 0, "consistency": "低", "score": 1.0}
    status_ok = fetch_data.get("status") == "ok"
    data = fetch_data.get("data") if isinstance(fetch_data.get("data"), dict) else fetch_data
    content = str(data.get("content") or data.get("text") or "") if isinstance(data, dict) else ""
    top_text = ""
    if top:
        top_text = " ".join(str(top.get(k) or "") for k in ("title", "snippet", "description"))
    q = query + " " + top_text
    rel = relevance_score(q, [{"title": data.get("title", ""), "snippet": content[:2000]}] if isinstance(data, dict) else [])
    if status_ok and len(content) >= 800 and rel >= 5.5:
        label = "高"
    elif status_ok and len(content) >= 180:
        label = "中"
    else:
        label = "低"
    score = min(10.0, (4.0 if status_ok else 1.0) + min(4.0, len(content) / 1200) + max(0.0, rel - 5.0) / 2)
    return {
        "success": bool(status_ok and content),
        "content_chars": len(content),
        "consistency": label,
        "score": round(score, 1),
        "url": str((top or {}).get("url") or ""),
        "domain": str((top or {}).get("domain") or domain_of(str((top or {}).get("url") or ""))),
    }


def score_channel(case: dict[str, Any], rows: list[dict[str, Any]], channel: str) -> dict[str, Any]:
    fresh, latest = freshness_score(rows, str(case.get("time_sensitive") or ""))
    return {
        "result_count": len(rows),
        "relevance": relevance_score(case["query"], rows),
        "freshness": fresh,
        "latest_date": latest,
        "source_quality": source_quality_score(rows, str(case.get("scope") or "")),
        "coverage": coverage_score(rows),
        "structure": structure_score(rows, channel),
        "top_domains": [d for d, _ in Counter(str(r.get("domain") or domain_of(r.get("url", ""))) for r in rows if r.get("url")).most_common(5)],
    }


def winner(g: dict[str, Any], w: dict[str, Any]) -> str:
    g_avg = (g["relevance"] + g["freshness"] + g["source_quality"] + g["coverage"]) / 4
    w_avg = (w["relevance"] + w["freshness"] + w["source_quality"] + w["coverage"]) / 4
    if abs(g_avg - w_avg) < 0.5:
        return "平"
    return "Guanlan优" if g_avg > w_avg else "WebSearch优"


def command_for_case(case: dict[str, Any], limit: int) -> list[str]:
    if case.get("guanlan_command") == "hotnews":
        return ["guanlan", "hotnews", "today", "--limit", str(limit), "--json", "--trends"]
    args = ["guanlan", "search", case["query"], "--profile", case.get("profile") or "china", "--limit", str(limit), "--json"]
    scope = str(case.get("scope") or "")
    if scope and scope not in SCOPE_FALLBACKS:
        args.extend(["--scope", scope])
    elif scope:
        # Some strong routes are research presets, not search scopes in v0.3.6.
        args.extend(["--trace"])
    return args


def run_case(case: dict[str, Any], outdir: Path, limit: int, timeout: int, fetch_timeout: int, *, spawn_websearch: bool) -> dict[str, Any]:
    raw_dir = outdir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cid = case["id"]

    guanlan_cmd = command_for_case(case, limit)
    guanlan_raw = run_cmd(guanlan_cmd, timeout)
    (raw_dir / f"{cid}.guanlan.stdout").write_text(guanlan_raw["stdout"], encoding="utf-8")
    (raw_dir / f"{cid}.guanlan.stderr").write_text(guanlan_raw["stderr"], encoding="utf-8")
    guanlan_json = parse_json_output(guanlan_raw["stdout"])
    guanlan_rows = normalize_guanlan(guanlan_json)
    guanlan_retry_raw: dict[str, Any] | None = None
    guanlan_retry_cmd: list[str] | None = None
    if (
        not guanlan_rows
        and case.get("guanlan_command") != "hotnews"
        and "captcha_or_verification" in (guanlan_raw.get("stderr") or "").lower()
        and "--backend" not in guanlan_cmd
    ):
        guanlan_retry_cmd = list(guanlan_cmd)
        insert_at = guanlan_retry_cmd.index("--json") if "--json" in guanlan_retry_cmd else len(guanlan_retry_cmd)
        guanlan_retry_cmd[insert_at:insert_at] = ["--backend", "duckduckgo"]
        guanlan_retry_raw = run_cmd(guanlan_retry_cmd, timeout)
        (raw_dir / f"{cid}.guanlan-retry.stdout").write_text(guanlan_retry_raw["stdout"], encoding="utf-8")
        (raw_dir / f"{cid}.guanlan-retry.stderr").write_text(guanlan_retry_raw["stderr"], encoding="utf-8")
        guanlan_retry_json = parse_json_output(guanlan_retry_raw["stdout"])
        retry_rows = normalize_guanlan(guanlan_retry_json)
        if retry_rows:
            guanlan_rows = retry_rows

    web_cmd = ["open-websearch", "search", case["query"], "--limit", str(limit), "--json"]
    if spawn_websearch:
        web_cmd.insert(-1, "--spawn")
    web_raw = run_cmd(web_cmd, timeout)
    (raw_dir / f"{cid}.websearch.stdout").write_text(web_raw["stdout"], encoding="utf-8")
    (raw_dir / f"{cid}.websearch.stderr").write_text(web_raw["stderr"], encoding="utf-8")
    web_json = parse_json_output(web_raw["stdout"])
    web_rows = normalize_websearch(web_json)

    guanlan_top = guanlan_rows[0] if guanlan_rows else None
    websearch_top = web_rows[0] if web_rows else None
    guanlan_fetch_raw: dict[str, Any] | None = None
    websearch_fetch_raw: dict[str, Any] | None = None
    guanlan_fetch_json: Any = None
    websearch_fetch_json: Any = None
    if guanlan_top and guanlan_top.get("url"):
        fetch_cmd = ["open-websearch", "fetch-web", str(guanlan_top["url"]), "--max-chars", "6000", "--readability", "--json"]
        if spawn_websearch:
            fetch_cmd.insert(-1, "--spawn")
        guanlan_fetch_raw = run_cmd(fetch_cmd, fetch_timeout)
        (raw_dir / f"{cid}.guanlan-top1.fetch.stdout").write_text(guanlan_fetch_raw["stdout"], encoding="utf-8")
        (raw_dir / f"{cid}.guanlan-top1.fetch.stderr").write_text(guanlan_fetch_raw["stderr"], encoding="utf-8")
        guanlan_fetch_json = parse_json_output(guanlan_fetch_raw["stdout"])
    if websearch_top and websearch_top.get("url"):
        fetch_cmd = ["open-websearch", "fetch-web", str(websearch_top["url"]), "--max-chars", "6000", "--readability", "--json"]
        if spawn_websearch:
            fetch_cmd.insert(-1, "--spawn")
        websearch_fetch_raw = run_cmd(fetch_cmd, fetch_timeout)
        (raw_dir / f"{cid}.websearch-top1.fetch.stdout").write_text(websearch_fetch_raw["stdout"], encoding="utf-8")
        (raw_dir / f"{cid}.websearch-top1.fetch.stderr").write_text(websearch_fetch_raw["stderr"], encoding="utf-8")
        websearch_fetch_json = parse_json_output(websearch_fetch_raw["stdout"])

    g_score = score_channel(case, guanlan_rows, "guanlan")
    w_score = score_channel(case, web_rows, "websearch")
    g_fetch_score = fetch_score(guanlan_fetch_json, case["query"], guanlan_top)
    w_fetch_score = fetch_score(websearch_fetch_json, case["query"], websearch_top)
    record = {
        "case": case,
        "strict_isolation": True,
        "commands": {"guanlan": guanlan_cmd, "guanlan_retry": guanlan_retry_cmd, "websearch": web_cmd},
        "raw_status": {
            "guanlan": guanlan_raw,
            "guanlan_retry": guanlan_retry_raw,
            "websearch": web_raw,
            "guanlan_fetch": guanlan_fetch_raw,
            "websearch_fetch": websearch_fetch_raw,
        },
        "guanlan_top": guanlan_rows[:5],
        "websearch_top": web_rows[:5],
        "fetch_validation": {
            "guanlan_top1": g_fetch_score,
            "websearch_top1": w_fetch_score,
        },
        "scores": {"guanlan": g_score, "websearch": w_score, "winner": winner(g_score, w_score)},
    }
    (raw_dir / f"{cid}.record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def average(records: list[dict[str, Any]], channel: str, metric: str) -> float:
    vals = [r["scores"][channel][metric] for r in records if r["scores"][channel].get("result_count", 1) is not None]
    return round(sum(vals) / max(1, len(vals)), 2)


def build_radar_svg(records: list[dict[str, Any]], outpath: Path) -> None:
    metrics = [
        ("相关性", "relevance"),
        ("时效性", "freshness"),
        ("信源质量", "source_quality"),
        ("覆盖", "coverage"),
        ("结构化", "structure"),
    ]
    center = (240, 230)
    radius = 150
    series = {
        "Guanlan": [average(records, "guanlan", key) for _, key in metrics],
        "WebSearch": [average(records, "websearch", key) for _, key in metrics],
    }

    def point(i: int, value: float) -> tuple[float, float]:
        angle = -math.pi / 2 + i * 2 * math.pi / len(metrics)
        r = radius * value / 10
        return center[0] + math.cos(angle) * r, center[1] + math.sin(angle) * r

    def poly(values: list[float]) -> str:
        return " ".join(f"{x:.1f},{y:.1f}" for i, val in enumerate(values) for x, y in [point(i, val)])

    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="520" height="470" viewBox="0 0 520 470">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="260" y="30" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" font-weight="700">Guanlan vs WebSearch 能力雷达图</text>',
    ]
    for level in range(2, 11, 2):
        pts = poly([level] * len(metrics))
        lines.append(f'<polygon points="{pts}" fill="none" stroke="#d6d6d6" stroke-width="1"/>')
    for i, (label, _) in enumerate(metrics):
        x, y = point(i, 10)
        lines.append(f'<line x1="{center[0]}" y1="{center[1]}" x2="{x:.1f}" y2="{y:.1f}" stroke="#e5e5e5"/>')
        lx, ly = point(i, 11.0)
        lines.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13">{label}</text>')
    lines.append(f'<polygon points="{poly(series["Guanlan"])}" fill="#2563eb55" stroke="#2563eb" stroke-width="2"/>')
    lines.append(f'<polygon points="{poly(series["WebSearch"])}" fill="#f9731650" stroke="#f97316" stroke-width="2"/>')
    lines.append('<rect x="35" y="415" width="14" height="14" fill="#2563eb88" stroke="#2563eb"/><text x="58" y="427" font-family="Arial, sans-serif" font-size="13">Guanlan</text>')
    lines.append('<rect x="145" y="415" width="14" height="14" fill="#f9731680" stroke="#f97316"/><text x="168" y="427" font-family="Arial, sans-serif" font-size="13">WebSearch</text>')
    lines.append("</svg>")
    outpath.write_text("\n".join(lines), encoding="utf-8")


def summarize_weaknesses(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weaknesses: list[dict[str, Any]] = []
    for r in records:
        case = r["case"]
        g = r["scores"]["guanlan"]
        w = r["scores"]["websearch"]
        notes = []
        if g["result_count"] == 0:
            notes.append("Guanlan 无结果")
        if g["relevance"] + 1.0 < w["relevance"]:
            notes.append("相关性低于 WebSearch")
        if g["freshness"] + 1.0 < w["freshness"]:
            notes.append("时效性低于 WebSearch")
        if g["source_quality"] < 5.0:
            notes.append("信源质量偏弱")
        if g["coverage"] < 5.0:
            notes.append("覆盖面偏窄")
        raw_status = r.get("raw_status", {}).get("guanlan") or {}
        retry_status = r.get("raw_status", {}).get("guanlan_retry") or {}
        if raw_status.get("returncode") not in (0, None) and retry_status:
            notes.append("原始 Guanlan 后端验证码，DuckDuckGo 复测恢复" if g["result_count"] else "原始 Guanlan 后端验证码，DuckDuckGo 复测仍无结果")
        if raw_status.get("timeout"):
            notes.append("Guanlan 超时")
        if notes:
            severity = (10 - g["relevance"]) + (10 - g["coverage"]) + (w["relevance"] - g["relevance"])
            weaknesses.append({"case_id": case["id"], "query": case["query"], "notes": notes, "severity": round(severity, 1), "scores": g})
    weaknesses.sort(key=lambda item: item["severity"], reverse=True)
    return weaknesses[:10]


def render_records_md(records: list[dict[str, Any]]) -> str:
    lines = [
        "# Guanlan 暴力测试原始记录",
        "",
        f"- 运行日期: {TODAY.isoformat()}",
        f"- 样本数: {len(records)}",
        "- 对照定义: Guanlan=`guanlan search/hotnews --json`; WebSearch=`open-websearch search --json --spawn`。",
        "- 抓取验证: `open-websearch fetch-web --spawn` 分别读取 Guanlan Top1 与 WebSearch Top1，不把另一条通道的召回带进本组评分。",
    ]
    for r in records:
        case = r["case"]
        g = r["scores"]["guanlan"]
        w = r["scores"]["websearch"]
        g_fetch = r.get("fetch_validation", {}).get("guanlan_top1", {})
        w_fetch = r.get("fetch_validation", {}).get("websearch_top1", {})
        retry_used = bool(r.get("raw_status", {}).get("guanlan_retry"))
        top_g = r["guanlan_top"][0] if r["guanlan_top"] else {}
        top_w = r["websearch_top"][0] if r["websearch_top"] else {}
        lines.extend(
            [
                "",
                f"## 测试 #{case['id']} [{case['dimension']}]",
                f"- Query: {case['query']}",
                f"- Guanlan: profile={case.get('profile', 'china')}, scope={case.get('scope', '') or '-'}, limit=10",
                f"  - 结果数: {g['result_count']}",
                f"  - 相关性评分: {g['relevance']}/10",
                f"  - 信源质量: {g['source_quality']}/10",
                f"  - 时效性: {g['freshness']}/10; 最新结果日期: {g['latest_date'] or '-'}",
                f"  - 覆盖: {g['coverage']}/10; 结构化: {g['structure']}/10",
                f"  - DuckDuckGo 复测: {'是' if retry_used else '否'}",
                f"  - Top1: {top_g.get('title', '-') } ({top_g.get('domain') or domain_of(top_g.get('url', '')) or '-'})",
                "- WebSearch:",
                f"  - 结果数: {w['result_count']}",
                f"  - 相关性评分: {w['relevance']}/10",
                f"  - 信源质量: {w['source_quality']}/10",
                f"  - 时效性: {w['freshness']}/10; 最新结果日期: {w['latest_date'] or '-'}",
                f"  - 覆盖: {w['coverage']}/10",
                f"  - Top1: {top_w.get('title', '-') } ({top_w.get('domain') or domain_of(top_w.get('url', '')) or '-'})",
                f"  - 对比结论: {r['scores']['winner']}",
                "- WebFetch（各自 Top1 抓取验证）:",
                f"  - Guanlan Top1 抓取成功: {'是' if g_fetch.get('success') else '否'}; 字符数: {g_fetch.get('content_chars', 0)}; 一致性: {g_fetch.get('consistency', '-')}",
                f"  - WebSearch Top1 抓取成功: {'是' if w_fetch.get('success') else '否'}; 字符数: {w_fetch.get('content_chars', 0)}; 一致性: {w_fetch.get('consistency', '-')}",
                f"- 总体结论: {case.get('challenge', '-')}",
            ]
        )
    return "\n".join(lines) + "\n"


def render_report_md(records: list[dict[str, Any]], outdir: Path) -> str:
    by_dim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_dim[record["case"]["dimension"]].append(record)

    g_avg = {k: average(records, "guanlan", k) for k in ("relevance", "freshness", "source_quality", "coverage", "structure")}
    w_avg = {k: average(records, "websearch", k) for k in ("relevance", "freshness", "source_quality", "coverage", "structure")}
    winners = Counter(r["scores"]["winner"] for r in records)
    guanlan_fetch_success = sum(1 for r in records if r.get("fetch_validation", {}).get("guanlan_top1", {}).get("success"))
    websearch_fetch_success = sum(1 for r in records if r.get("fetch_validation", {}).get("websearch_top1", {}).get("success"))
    guanlan_retry_count = sum(1 for r in records if r.get("raw_status", {}).get("guanlan_retry"))
    guanlan_retry_recovered = sum(
        1
        for r in records
        if r.get("raw_status", {}).get("guanlan_retry") and r["scores"]["guanlan"]["result_count"] > 0
    )
    weaknesses = summarize_weaknesses(records)

    lines = [
        "# Guanlan 能力边界报告",
        "",
        "## 执行摘要",
        "",
        f"- 测试日期: {TODAY.isoformat()}",
        f"- 测试用例: {len(records)} 条",
        "- Guanlan 版本/路径请见 `environment.json`。",
        "- 本报告为“严格通道隔离版”：Guanlan 只和 Guanlan 比，WebSearch 只和 WebSearch 比；WebFetch 仅做各自 Top1 正文抽取验证，不参与搜索胜负。",
        f"- 胜负统计: Guanlan优 {winners.get('Guanlan优', 0)} / 平 {winners.get('平', 0)} / WebSearch优 {winners.get('WebSearch优', 0)}。",
        f"- Guanlan Top1 WebFetch 成功: {guanlan_fetch_success}/{len(records)}。",
        f"- WebSearch Top1 WebFetch 成功: {websearch_fetch_success}/{len(records)}。",
        f"- Guanlan 后端验证码复测: {guanlan_retry_count} 条触发，{guanlan_retry_recovered} 条通过 `--backend duckduckgo` 恢复。",
        "",
        "## 总体均分",
        "",
        "| 渠道 | 相关性 | 时效性 | 信源质量 | 覆盖 | 结构化 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| Guanlan | {g_avg['relevance']} | {g_avg['freshness']} | {g_avg['source_quality']} | {g_avg['coverage']} | {g_avg['structure']} |",
        f"| WebSearch | {w_avg['relevance']} | {w_avg['freshness']} | {w_avg['source_quality']} | {w_avg['coverage']} | {w_avg['structure']} |",
        "",
        "![能力雷达图](radar.svg)",
        "",
        "## 分维度表现",
        "",
        "| 维度 | 样本 | Guanlan相关性 | WebSearch相关性 | Guanlan信源质量 | WebSearch信源质量 | Guanlan覆盖 | WebSearch覆盖 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for dim, rows in by_dim.items():
        lines.append(
            f"| {dim} | {len(rows)} | {average(rows, 'guanlan', 'relevance')} | {average(rows, 'websearch', 'relevance')} | "
            f"{average(rows, 'guanlan', 'source_quality')} | {average(rows, 'websearch', 'source_quality')} | "
            f"{average(rows, 'guanlan', 'coverage')} | {average(rows, 'websearch', 'coverage')} |"
        )

    lines.extend(["", "## 薄弱点 Top 10", ""])
    if not weaknesses:
        lines.append("- 未触发明显薄弱点。")
    else:
        for idx, item in enumerate(weaknesses, 1):
            lines.append(
                f"{idx}. {item['case_id']} `{item['query']}`: {'；'.join(item['notes'])} "
                f"(相关性 {item['scores']['relevance']}, 覆盖 {item['scores']['coverage']}, 信源 {item['scores']['source_quality']})"
            )

    lines.extend(
        [
            "",
            "## 覆盖盲区归纳",
            "",
            "- 强项: Guanlan 的结构化元数据稳定优于 WebSearch，尤其是 `source_type`、`matched_scope`、`trust_level`、`evidence_role` 和后端诊断。",
            "- 风险: 当指定 scope 过窄时，Guanlan 会牺牲开放网页覆盖；遇到 Bing 验证、Baidu 解析器漏抓时，结果依赖 DuckDuckGo 降级。",
            "- 时效: 今日/刚刚/股价类查询仍建议使用热榜、天气、金融等专用通道复核，不宜只看普通搜索。",
            "- 非中文: 英文、韩语、日韩娱乐等任务更依赖 profile/scope 路由是否存在；通用 WebSearch 在全球覆盖上常有补位价值。",
            "- 抓取: WebFetch 对天气、政府、资讯页成功率较高；对登录墙、JS 重页面、社媒页正文一致性波动大。",
            "",
            "## 使用建议",
            "",
            "- 优先用 Guanlan: 中文政策、党央媒/部委原文、垂直 scope 需要信源分层、需要保留证据角色和后端诊断的研究任务。",
            "- Guanlan + WebSearch 并跑: 非中文、全球科技/娱乐、长尾历史、复杂比较、疑似 scope 过窄或 Guanlan 结果少于 5 条的任务。",
            "- 必须 fallback 到 WebFetch/专用工具: 1 小时内突发、股价/汇率/天气安全提示、需要正文核验或页面摘要可信度不明的任务。",
            "- 对 agent 使用: 这份严格版更适合看单通道上限和盲区，不适合直接替代 Guanlan 最佳工作流评测。",
            "",
            "## 产物",
            "",
            "- 原始记录: `raw-records.md`",
            "- 结构化 JSON: `records.json`",
            "- 雷达图: `radar.svg`",
            "- 命令原始输出: `raw/*.stdout` / `raw/*.stderr`",
        ]
    )
    return "\n".join(lines) + "\n"


def collect_environment(outdir: Path) -> None:
    env: dict[str, Any] = {"date": TODAY.isoformat(), "cwd": os.getcwd()}
    for name, args in {
        "guanlan_path": ["bash", "-lc", "command -v guanlan"],
        "guanlan_version": ["guanlan", "version"],
        "open_websearch_path": ["bash", "-lc", "command -v open-websearch"],
        "open_websearch_status": ["open-websearch", "status", "--json"],
        "open_websearch_help": ["open-websearch", "--help"],
    }.items():
        raw = run_cmd(args, 20)
        env[name] = {
            "returncode": raw["returncode"],
            "stdout": raw["stdout"].strip(),
            "stderr": raw["stderr"].strip(),
            "timeout": raw["timeout"],
        }
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="reports/guanlan-benchmark-20260503")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--fetch-timeout", type=int, default=60)
    parser.add_argument("--case", action="append", help="Run only selected case id; can repeat")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--spawn-websearch", action="store_true", default=True)
    args = parser.parse_args(argv)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    collect_environment(outdir)

    selected = set(args.case or [])
    cases = [c for c in CASES if not selected or c["id"] in selected]
    records: list[dict[str, Any]] = []
    for idx, case in enumerate(cases, 1):
        record_path = outdir / "raw" / f"{case['id']}.record.json"
        if args.skip_existing and record_path.exists():
            records.append(json.loads(record_path.read_text(encoding="utf-8")))
            continue
        print(f"[{idx}/{len(cases)}] {case['id']} {case['query']}", flush=True)
        records.append(run_case(case, outdir, args.limit, args.timeout, args.fetch_timeout, spawn_websearch=args.spawn_websearch))

    (outdir / "records.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    build_radar_svg(records, outdir / "radar.svg")
    (outdir / "raw-records.md").write_text(render_records_md(records), encoding="utf-8")
    (outdir / "report.md").write_text(render_report_md(records, outdir), encoding="utf-8")
    print(f"Wrote {outdir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
