# -*- coding: utf-8 -*-
"""Search and read primitives for AI agents.

These helpers are deliberately conservative: default search uses public HTML
results and page reading uses Jina Reader. No cookies, browser access, or
Keychain access are involved.
"""

from __future__ import annotations

import base64
import datetime as dt
import difflib
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from guanlan.limits import (
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
)
from guanlan.router import build_route_plan, format_route_plan_markdown
from guanlan.source_taxonomy import source_card_for_domain

_UA = "Mozilla/5.0 (compatible; Guanlan/1.4)"
_TIMEOUT = 20
_CACHE_VERSION = 2
_MIN_USEFUL_READ_CHARS = 180
_RECENCY_DEFAULT_WINDOW_DAYS = 30
_WEAK_READ_MARKERS = (
    "captcha",
    "access denied",
    "forbidden",
    "verify you are human",
    "enable javascript",
    "请完成安全验证",
    "访问受限",
    "验证码",
    "登录后查看",
    "请先登录",
)

_SEARCH_BLOCK_MARKERS: dict[str, tuple[str, ...]] = {
    "baidu": (
        "百度安全验证",
        "请输入验证码",
        "wappass.baidu.com",
        "百度安全中心",
    ),
    "bing": (
        "unusual traffic",
        "verify you are human",
        "captcha",
        "b_captcha",
        "our systems have detected",
    ),
    "duckduckgo": (
        "captcha",
        "verify you are human",
    ),
}

_QUALITY_INTENT_PROFILES: dict[str, dict[str, Any]] = {
    "policy": {
        "name": "政策/官方口径",
        "terms": ("政策", "监管", "法规", "通知", "意见", "办法", "国务院", "部委", "主管部门", "官方", "解读"),
        "preferred_scopes": ("gov", "party_central"),
        "preferred_source_types": ("政府/部委", "党央媒"),
        "caution_source_types": ("社交/内容平台",),
        "guidance": "优先政府/部委原文和党央媒权威报道，媒体解读只能作为背景。",
    },
    "global_policy": {
        "name": "英文政策/监管",
        "terms": (
            "regulation",
            "regulatory",
            "policy",
            "law",
            "rules",
            "compliance",
            "standard",
            "standards",
            "sec",
            "fda",
            "ftc",
            "nist",
            "eu",
        ),
        "preferred_scopes": ("global_official", "global_news"),
        "preferred_source_types": ("英文官方/监管", "国际主流媒体"),
        "caution_source_types": ("英文社区样本", "评价/消费样本"),
        "guidance": "优先政府、监管机构、标准组织和公开数据原文，媒体报道作为背景。",
    },
    "standards_compliance": {
        "name": "标准/合规/认证",
        "terms": ("标准", "认证", "合规", "审计", "等保", "iso", "iec", "nist", "soc2", "gdpr", "hipaa", "compliance", "certification", "standards"),
        "preferred_scopes": ("global_official", "gov", "company_primary", "academic"),
        "preferred_source_types": ("英文官方/监管", "政府/部委", "公司一手资料", "学术/论文检索"),
        "caution_source_types": ("社交/内容平台", "英文社区样本", "商业/产业媒体"),
        "guidance": "优先标准组织、监管机构和官方合规材料；实施经验和厂商声明需要标注立场。",
    },
    "medical_health": {
        "name": "医疗/健康高影响信息",
        "terms": ("医疗", "疾病", "药", "药品", "治疗", "诊断", "症状", "临床", "指南", "fda", "cdc", "who", "medical", "clinical", "treatment"),
        "preferred_scopes": ("global_official", "gov", "academic"),
        "preferred_source_types": ("英文官方/监管", "政府/部委", "学术/论文检索"),
        "caution_source_types": ("社交/内容平台", "英文社区样本", "商业/产业媒体"),
        "guidance": "优先公共卫生机构、药监/监管、临床指南和同行评议材料；不要输出诊疗结论。",
    },
    "legal_judicial": {
        "name": "法律/司法高影响信息",
        "terms": ("法律", "诉讼", "判决", "合同", "律师", "侵权", "司法解释", "法院", "裁判文书", "条例", "law", "legal", "court", "lawsuit"),
        "preferred_scopes": ("gov", "global_official", "local_official", "academic"),
        "preferred_source_types": ("政府/部委", "英文官方/监管", "地方官媒", "学术/论文检索"),
        "caution_source_types": ("社交/内容平台", "英文社区样本", "商业/产业媒体"),
        "guidance": "优先法律条文、司法解释、裁判文书和权威机构材料；律师文章只能作为观点。",
    },
    "company": {
        "name": "公司/产品一手资料",
        "terms": (
            "pricing",
            "release notes",
            "release note",
            "changelog",
            "docs",
            "documentation",
            "status page",
            "official blog",
            "api",
            "sdk",
            "terms of service",
            "investor relations",
        ),
        "preferred_scopes": ("company_primary", "developer"),
        "preferred_source_types": ("公司一手资料", "英文开发者/开源"),
        "caution_source_types": ("英文社区样本", "评价/消费样本"),
        "guidance": "优先公司官网、文档、发布说明、状态页和投资者关系材料，再补社区/媒体样本。",
    },
    "local": {
        "name": "地方政策/区域研究",
        "terms": ("地方", "城市", "区域", "省", "市", "区县", "产业园", "广东", "上海", "北京", "深圳", "杭州", "成都"),
        "preferred_scopes": ("local_official", "gov", "party_central"),
        "preferred_source_types": ("地方官媒", "政府/部委", "党央媒"),
        "caution_source_types": (),
        "guidance": "优先地方官媒、地方政府和中央口径交叉核验。",
    },
    "ecommerce": {
        "name": "电商/零售/跨境",
        "terms": ("电商", "零售", "跨境", "出海", "品牌", "渠道", "供应链", "产业带", "平台", "新消费"),
        "preferred_scopes": ("ecommerce", "business"),
        "preferred_source_types": ("电商/零售垂类", "商业/产业媒体"),
        "caution_source_types": (),
        "guidance": "优先垂类媒体和产业媒体，注意区分新闻、观点和软文。",
    },
    "finance": {
        "name": "财经/资本市场",
        "terms": ("财经", "股票", "股价", "财报", "融资", "上市", "投资", "基金", "债券", "宏观", "资本市场"),
        "preferred_scopes": ("finance", "business"),
        "preferred_source_types": ("财经/资本市场", "商业/产业媒体"),
        "caution_source_types": ("社交/内容平台",),
        "guidance": "优先公告、财报、财经快讯和权威财经媒体，市场观点不等于建议。",
    },
    "tech": {
        "name": "技术/开发者",
        "terms": ("技术", "开源", "框架", "模型", "api", "sdk", "github", "开发者", "部署", "bug", "benchmark"),
        "preferred_scopes": ("tech_dev", "developer"),
        "preferred_source_types": ("科技/开发者社区", "英文开发者/开源"),
        "caution_source_types": (),
        "guidance": "优先官方文档、代码仓库、开发者社区和可复现反馈。",
    },
    "academic": {
        "name": "学术/论文检索",
        "terms": (
            "ei",
            "sci",
            "ssci",
            "scopus",
            "compendex",
            "engineering index",
            "会议",
            "学术会议",
            "投稿",
            "检索",
            "收录",
            "论文",
            "期刊",
            "审稿",
            "conference",
            "proceedings",
        ),
        "preferred_scopes": ("academic",),
        "preferred_source_types": ("学术/论文检索",),
        "caution_source_types": ("社交/内容平台",),
        "guidance": "优先数据库/出版商官方说明、会议 CFP 和学校/单位认定口径；商业代投内容只能作线索。",
    },
    "reputation": {
        "name": "口碑/公开讨论",
        "terms": (
            "口碑",
            "评价",
            "体验",
            "吐槽",
            "避雷",
            "测评",
            "推荐",
            "小红书",
            "微博",
            "知乎",
            "b站",
            "bilibili",
            "review",
            "reviews",
            "reddit",
            "hacker news",
            "trustpilot",
            "g2",
            "capterra",
            "complaints",
        ),
        "preferred_scopes": ("social_web", "community_sample", "market_review", "tech_dev", "developer", "business"),
        "preferred_source_types": ("社交/内容平台", "英文社区样本", "评价/消费样本", "科技/开发者社区", "英文开发者/开源", "商业/产业媒体"),
        "caution_source_types": (),
        "guidance": "社交结果适合发现样本线索，不能直接代表总体比例。",
    },
}


RESEARCH_PRESETS: dict[str, dict[str, Any]] = {
    "general": {
        "name": "通用研究",
        "description": "适合一般资料检索与多来源核验。",
        "profile": "china",
        "scope": "",
        "scopes": [],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 2,
        "max_read_chars": 2400,
        "guidance": ["先看不同 topic 和 source_type，再组织结论。"],
    },
    "policy": {
        "name": "政策研究",
        "description": "优先政府/部委信源，适合政策原文、通知、法规和监管口径。",
        "profile": "china",
        "scope": "gov",
        "scopes": ["gov", "party_central"],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 3200,
        "guidance": ["优先引用政策原文、主管部门通知和官方公告，不要用媒体解读替代原文。"],
    },
    "official": {
        "name": "官方表述",
        "description": "优先党央媒与中央重点媒体，适合宏观叙事和权威报道。",
        "profile": "china",
        "scope": "party_central",
        "scopes": ["party_central", "gov"],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 3000,
        "guidance": ["区分官方原文、权威报道和二次解读，保留措辞差异。"],
    },
    "industry": {
        "name": "产业研究",
        "description": "优先商业与产业媒体，适合公司动态、商业模式和行业趋势。",
        "profile": "china",
        "scope": "business",
        "scopes": ["business", "ecommerce", "finance"],
        "sites": ["36kr.com", "huxiu.com", "yicai.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": ["注意区分新闻事实、商业观点和软文营销。"],
    },
    "ecommerce": {
        "name": "电商零售",
        "description": "优先电商/零售垂类媒体，适合跨境、品牌、渠道和产业带研究。",
        "profile": "china",
        "scope": "ecommerce",
        "scopes": ["ecommerce", "business"],
        "sites": ["ebrun.com", "100ec.cn", "cifnews.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": ["优先关注平台、品牌、渠道、供应链和交易场景。"],
    },
    "reputation": {
        "name": "产品口碑",
        "description": "优先社交与内容平台公开页，适合用户评价、讨论和体验线索。",
        "profile": "china",
        "scope": "social_web",
        "scopes": ["social_web", "tech_dev", "business"],
        "sites": ["zhihu.com", "weibo.com", "xiaohongshu.com", "bilibili.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 2,
        "max_read_chars": 2400,
        "guidance": ["口碑材料偏样本线索，不要直接当作总体结论。"],
    },
    "tech": {
        "name": "技术选型",
        "description": "优先科技与开发者社区，适合工程实践、技术反馈和开发者讨论。",
        "profile": "china",
        "scope": "tech_dev",
        "scopes": ["tech_dev", "social_web"],
        "sites": ["v2ex.com", "juejin.cn", "segmentfault.com", "github.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": ["优先提取版本、限制、真实使用反馈和可复现依据。"],
    },
    "academic": {
        "name": "学术检索",
        "description": "优先学术数据库、出版商和会议/高校口径，适合 EI/SCI/Scopus、投稿、收录和认定要求。",
        "profile": "china",
        "scope": "academic",
        "scopes": ["academic", "tech_dev", "business"],
        "sites": ["elsevier.com", "engineeringvillage.com", "ieee.org", "cnki.net", "xueshu.baidu.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 3200,
        "guidance": ["把数据库官方说明、出版商/会议要求、高校或单位认定口径和经验帖分开写，不要混成单一标准。"],
    },
    "finance": {
        "name": "财经研究",
        "description": "优先财经与资本市场信源，适合公司、股票、市场和宏观金融。",
        "profile": "china",
        "scope": "finance",
        "scopes": ["finance", "business"],
        "sites": ["cls.cn", "eastmoney.com", "xueqiu.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": ["财经内容注意时效性和风险，不把市场观点当作投资建议。"],
    },
    "local": {
        "name": "地方研究",
        "description": "优先核心地方官媒，适合区域政策、城市治理和地方产业。",
        "profile": "china",
        "scope": "local_official",
        "scopes": ["local_official", "gov", "party_central"],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": ["注意地方口径、区域边界和政策适用范围。"],
    },
    "global_policy": {
        "name": "英文政策监管",
        "description": "优先英文官方、监管机构、标准组织和主流新闻，适合政策、法规、合规和标准核验。",
        "profile": "english",
        "scope": "global_official",
        "scopes": ["global_official", "global_news"],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 3200,
        "guidance": ["优先引用官方/监管/标准组织原文，新闻和分析只作为背景。"],
    },
    "company": {
        "name": "英文公司与产品",
        "description": "优先公司官网、官方文档、发布说明、价格页、状态页和开发者资料。",
        "profile": "english",
        "scope": "company_primary",
        "scopes": ["company_primary", "developer", "global_news"],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 3200,
        "guidance": ["把公司一手资料、媒体转述、社区反馈和测评样本分开写。"],
    },
    "global_reputation": {
        "name": "英文口碑样本",
        "description": "优先 Reddit、Hacker News、G2、Trustpilot 等公开社区和评价样本。",
        "profile": "english",
        "scope": "community_sample",
        "scopes": ["community_sample", "market_review", "global_news", "company_primary"],
        "sites": ["reddit.com", "news.ycombinator.com", "g2.com", "trustpilot.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 1,
        "max_read_chars": 2400,
        "guidance": ["英文口碑材料偏样本线索，注意商业激励、平台偏差和幸存者偏差。"],
    },
    "global_industry": {
        "name": "英文产业分析",
        "description": "优先产业分析、主流新闻和公司一手资料，适合市场结构、竞品和趋势研究。",
        "profile": "english",
        "scope": "industry_analysis",
        "scopes": ["industry_analysis", "global_news", "company_primary", "community_sample"],
        "sites": [],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 3000,
        "guidance": ["区分事实、分析、预测和商业立场；关键事实回到公司或官方一手来源核验。"],
    },
}


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source: str = "duckduckgo"
    rank: int = 0
    domain: str = ""
    source_type: str = "通用网页"
    matched_scope: str = ""
    trust_level: int = 1
    evidence_role: str = "open_web_context"
    score: float = 0.0
    score_parts: dict[str, float] = field(default_factory=dict)
    topic_key: str = ""
    topic_size: int = 1
    topic_role: str = "single"
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _DuckDuckGoHTMLParser(HTMLParser):
    """Small parser for DuckDuckGo's no-JS HTML results."""

    def __init__(self):
        super().__init__()
        self.results: list[SearchResult] = []
        self._in_title = False
        self._in_snippet = False
        self._current_href = ""
        self._current_title: list[str] = []
        self._last_result: SearchResult | None = None
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attrs_dict = {k: v or "" for k, v in attrs}
        classes = set(attrs_dict.get("class", "").split())
        if tag == "a" and "result__a" in classes:
            self._in_title = True
            self._current_href = attrs_dict.get("href", "")
            self._current_title = []
        elif tag in {"a", "td"} and "result-link" in classes:
            self._in_title = True
            self._current_href = attrs_dict.get("href", "")
            self._current_title = []
        elif "result__snippet" in classes:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag: str):
        if tag == "a" and self._in_title:
            title = _collapse_ws("".join(self._current_title))
            url = _normalize_ddg_url(self._current_href)
            if title and url and not _is_duckduckgo_noise(url):
                result = SearchResult(
                    title=title,
                    url=url,
                    rank=len(self.results) + 1,
                )
                self.results.append(result)
                self._last_result = result
            self._in_title = False
            self._current_href = ""
            self._current_title = []
        elif self._in_snippet and tag in {"a", "td", "div"}:
            snippet = _collapse_ws("".join(self._snippet_parts))
            if self._last_result and snippet and not self._last_result.snippet:
                self._last_result.snippet = snippet
            self._in_snippet = False
            self._snippet_parts = []

    def handle_data(self, data: str):
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._snippet_parts.append(data)


_WECHAT_SOGOU_BACKENDS = {"wechat-sogou", "wechat_sogou", "sogou-wechat", "sogou_wechat"}


def backend_order(
    backend: str = "auto",
    profile: str | None = None,
    site: str | None = None,
    query: str | None = None,
) -> list[str]:
    """Return search backend order for a profile."""
    backend = (backend or "auto").lower()
    if backend in _WECHAT_SOGOU_BACKENDS:
        return ["wechat-sogou"]
    if backend != "auto":
        return [backend]
    if profile == "china":
        order = ["baidu", "bing", "duckduckgo"]
    else:
        order = ["duckduckgo", "bing"]
    if _is_wechat_search_intent(site=site, query=query):
        order.append("wechat-sogou")
    return order


def resolve_query_profile(query: str, profile: str | None = None) -> str | None:
    """Keep English expansion opt-in while preserving China defaults for CJK queries."""
    if profile:
        return profile
    if _contains_cjk(query):
        return "china"
    return profile


def cache_dir() -> Path:
    """Return the Guanlan cache directory."""
    return Path.home() / ".guanlan" / "cache"


def _cache_key(kind: str, payload: dict[str, Any]) -> str:
    raw = json.dumps({"kind": kind, "v": _CACHE_VERSION, **payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(kind: str, key: str) -> Path:
    return cache_dir() / kind / f"{key}.json"


def _cache_get(kind: str, key: str, ttl: int) -> dict[str, Any] | None:
    path = _cache_path(kind, key)
    if ttl <= 0 or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    created_at = float(data.get("created_at", 0) or 0)
    if time.time() - created_at > ttl:
        return None
    payload = data.get("payload")
    return payload if isinstance(payload, dict) else None


def _cache_set(kind: str, key: str, payload: dict[str, Any]) -> None:
    path = _cache_path(kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": _CACHE_VERSION, "created_at": time.time(), "kind": kind, "payload": payload}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cache_summary() -> dict[str, Any]:
    """Return lightweight local cache stats for status output."""
    root = cache_dir()
    summary: dict[str, Any] = {"path": str(root), "exists": root.exists(), "kinds": {}, "total_files": 0}
    if not root.exists():
        return summary
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        files = list(child.glob("*.json"))
        summary["kinds"][child.name] = len(files)
        summary["total_files"] += len(files)
    return summary


def search_web(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    site: str | None = None,
    scope: str | None = None,
    backend: str = "auto",
    profile: str | None = None,
    trace: bool = False,
    cluster_threshold: str = "conservative",
    cache_ttl: int = 0,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Search the web and return normalized result dictionaries."""
    original_query = query.strip()
    query = original_query
    if not original_query:
        raise ValueError("query is required")
    profile = resolve_query_profile(original_query, profile)
    recency = detect_recency_intent(original_query)
    quality = detect_search_quality_profile(original_query, scope=scope, site=site, profile=profile)
    route_plan = build_route_plan(
        original_query,
        scope=scope,
        site=site,
        profile=profile,
        limit=limit,
    )
    quality = _quality_with_route_plan(quality, route_plan.to_dict(), explicit_scope=scope, site=site)
    query_strategy = build_query_strategy(
        original_query,
        route_plan=route_plan.to_dict(),
        recency=recency,
        quality=quality,
    )
    if scope:
        from guanlan.search_sources import resolve_scope, scoped_query

        domains = list(resolve_scope(scope).domains)
        if site:
            domains.insert(0, site.strip())
        query = scoped_query(query, domains)
    elif site:
        query = f"site:{site.strip()} {query}"
    query = _apply_recency_query(query, recency)

    cache_meta = {
        "enabled": bool(cache_ttl and cache_ttl > 0 and use_cache),
        "status": "disabled",
        "ttl": max(cache_ttl, 0),
    }
    cache_key = ""
    if cache_meta["enabled"]:
        cache_key = _cache_key(
            "search",
            {
                "query": original_query,
                "effective_query": query,
                "limit": max(limit, 1),
                "site": site or "",
                "scope": scope or "",
                "backend": backend,
                "profile": profile or "",
                "cluster_threshold": cluster_threshold,
                "recency": {
                    "enabled": recency["enabled"],
                    "window_days": recency["window_days"],
                    "start_date": recency["start_date"],
                    "end_date": recency["end_date"],
                },
                "quality_intent": quality["intent"],
            },
        )
        cached = _cache_get("search", cache_key, ttl=cache_ttl)
        if cached is not None:
            results = [dict(item) for item in cached.get("results", [])]
            for item in results:
                item.setdefault("trace", {})
                item["trace"]["cache"] = "hit"
                item["trace"]["cache_key"] = cache_key
                if not trace:
                    item.pop("score_parts", None)
            return results[:limit]
        cache_meta["status"] = "miss"

    errors: list[str] = []
    results: list[SearchResult] = []
    order = backend_order(backend, profile, site=site, query=original_query)
    backend_diagnostics: list[dict[str, Any]] = []
    for name in order:
        attempt: dict[str, Any] = {
            "backend": name,
            "status": "unknown",
            "result_count": 0,
            "error": "",
            "note": "",
        }
        try:
            batch: list[SearchResult]
            if name == "duckduckgo":
                batch = _search_duckduckgo(query, limit=limit)
            elif name == "bing":
                batch = _search_bing(query, limit=limit)
            elif name == "baidu":
                batch = _search_baidu(query, limit=limit)
            elif name == "wechat-sogou":
                if backend == "auto" and len(_dedupe_results(results)) >= limit:
                    attempt.update(
                        {
                            "status": "skipped",
                            "note": "已有足够候选，跳过高摩擦微信公众号后端。",
                        }
                    )
                    continue
                batch = _search_wechat_sogou(original_query, limit=limit)
            elif name.startswith("plugin:"):
                batch = _search_plugin_backend(name, query, limit=limit)
            else:
                raise ValueError(f"unknown backend: {name}")
            attempt["result_count"] = len(batch)
            attempt["status"] = "ok" if batch else _zero_result_backend_status(name)
            if not batch:
                attempt["note"] = _zero_result_backend_note(name)
            results.extend(batch)
        except Exception as e:
            errors.append(f"{name}: {e}")
            attempt.update(
                {
                    "status": _exception_backend_status(str(e)),
                    "error": str(e),
                    "note": _backend_error_note(name, str(e)),
                }
            )
        finally:
            backend_diagnostics.append(attempt)

    if not results and errors:
        fatal_errors = [
            error
            for error in errors
            if not (backend == "auto" and error.startswith("wechat-sogou:"))
        ]
        if fatal_errors:
            raise RuntimeError("; ".join(fatal_errors))
    backend_summary = _backend_diagnostic_summary(backend_diagnostics)
    backend_recovery = build_search_recovery_plan(
        original_query,
        diagnostics=backend_diagnostics,
        route_plan=route_plan.to_dict(),
        profile=profile,
        backend=backend,
        limit=limit,
    )
    ranked = rank_results(
        results,
        query=original_query,
        backend_order=order,
        preferred_scope=scope,
        cluster_threshold=cluster_threshold,
        recency=recency,
        quality=quality,
    )
    output_full = [r.to_dict() for r in ranked[:limit]]
    quality_summary = search_quality_summary(output_full, quality=quality)
    for item in output_full:
        item.setdefault("trace", {})
        item["trace"].update(
            {
                "effective_query": query,
                "backend_order": order,
                "cache": cache_meta["status"],
                "cache_key": cache_key,
                "cluster_threshold": cluster_threshold,
                "query_recency": recency,
                "route_plan": route_plan.to_dict(),
                "query_strategy": query_strategy,
                "query_quality": quality,
                "quality_summary": quality_summary,
                "backend_diagnostics": backend_diagnostics,
                "backend_summary": backend_summary,
                "backend_recovery": backend_recovery,
                "errors": list(errors),
            }
        )
    if cache_meta["enabled"]:
        _cache_set("search", cache_key, {"results": output_full})
    output = [dict(item) for item in output_full]
    if not trace:
        for item in output:
            item.pop("score_parts", None)
    return output


def rank_results(
    results: list[SearchResult],
    query: str = "",
    backend_order: list[str] | None = None,
    preferred_scope: str | None = None,
    cluster_threshold: str = "conservative",
    recency: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
) -> list[SearchResult]:
    """Normalize, dedupe, classify, and score search results."""
    backend_order = backend_order or []
    quality = quality or detect_search_quality_profile(query, scope=preferred_scope)
    deduped = _dedupe_results(results)
    for item in deduped:
        item.domain = _domain(item.url)
        try:
            from guanlan.search_sources import classify_domain

            meta = classify_domain(item.domain, preferred_scope=preferred_scope)
        except Exception:
            meta = {"source_type": "通用网页", "matched_scope": "", "trust_level": 1}
        item.source_type = meta["source_type"]
        item.matched_scope = meta["matched_scope"]
        item.trust_level = meta["trust_level"]
        source_card = source_card_for_domain(
            item.domain,
            preferred_scope=preferred_scope,
        )
        item.trace["source_card"] = source_card.to_dict()
        item.evidence_role = _infer_evidence_role(item, source_card.to_dict(), quality=quality)
        item.score_parts = _score_result_parts(
            item,
            query=query,
            backend_order=backend_order,
            recency=recency,
            quality=quality,
        )
        item.score = item.score_parts["total"]
        item.trace["recency"] = _result_recency_trace(item, recency)
        item.trace["quality"] = _result_quality_trace(item, quality)
    ranked = sorted(deduped, key=lambda r: (-r.score, r.rank))
    _assign_topic_clusters(ranked, threshold=cluster_threshold)
    ranked = _order_topic_representatives_first(ranked)
    for idx, item in enumerate(ranked, start=1):
        item.rank = idx
    return ranked


def _zero_result_backend_status(backend: str) -> str:
    if backend in {"baidu", "bing"}:
        return "parser_miss"
    if backend == "duckduckgo":
        return "no_results_or_parser_miss"
    return "no_results"


def _zero_result_backend_note(backend: str) -> str:
    notes = {
        "baidu": "Baidu 页面可访问但结果解析器未抓到条目；这通常意味着 HTML 结构/区域化模板变了，应视为解析器待修而非没有资料。",
        "bing": "Bing 页面可访问但结果解析器未抓到条目；这通常意味着 HTML 结构/区域化模板变了，应视为解析器待修而非没有资料。",
        "duckduckgo": "DuckDuckGo 未产出结果；可能是无结果、结构变化或查询限制过窄，建议换 query 或补充 scope/site。",
        "wechat-sogou": "WechatSogou 返回 0 条结果，可能是验证码、关键词过窄或库版本不兼容。",
    }
    return notes.get(backend, "该后端未产出结果。")


def _exception_backend_status(error: str) -> str:
    lowered = error.lower()
    if "captcha" in lowered or "verification" in lowered or "安全验证" in error or "验证码" in error:
        return "blocked"
    return "error"


def _backend_error_note(backend: str, error: str) -> str:
    lowered = error.lower()
    if "captcha" in lowered or "verification" in lowered or "安全验证" in error or "验证码" in error:
        return f"{backend} 疑似触发验证/反爬；不要把它当作无相关资料，应改用其他后端或 scope 补搜。"
    if "timed out" in lowered or "timeout" in lowered:
        return f"{backend} 请求超时；建议稍后重试或降低并发。"
    if "http error 403" in lowered or "forbidden" in lowered:
        return f"{backend} 返回访问拒绝；建议换后端或用站点定向。"
    return f"{backend} 后端异常；保留后续后端兜底结果。"


def _backend_diagnostic_summary(diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [item["backend"] for item in diagnostics if item.get("status") == "ok"]
    parser_miss = [item["backend"] for item in diagnostics if item.get("status") == "parser_miss"]
    zero_results = [
        item["backend"]
        for item in diagnostics
        if item.get("status") in {"no_results", "no_results_or_parser_miss"}
    ]
    blocked = [item["backend"] for item in diagnostics if item.get("status") == "blocked"]
    errors = [item["backend"] for item in diagnostics if item.get("status") == "error"]
    first_ok_index = next((idx for idx, item in enumerate(diagnostics) if item.get("status") == "ok"), None)
    fallback_used = bool(
        first_ok_index is not None
        and any(
            item.get("status") in {"parser_miss", "no_results", "no_results_or_parser_miss", "blocked", "error"}
            for item in diagnostics[:first_ok_index]
        )
    )
    return {
        "ok": ok,
        "parser_miss": parser_miss,
        "zero_results": zero_results,
        "blocked": blocked,
        "errors": errors,
        "fallback_used": fallback_used,
        "primary_backend": diagnostics[0]["backend"] if diagnostics else "",
        "primary_status": diagnostics[0]["status"] if diagnostics else "",
    }


def build_search_recovery_plan(
    query: str,
    *,
    diagnostics: list[dict[str, Any]],
    route_plan: dict[str, Any] | None = None,
    profile: str | None = None,
    backend: str = "auto",
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> dict[str, Any]:
    """Build agent-facing recovery guidance for degraded search backends."""
    if not diagnostics:
        return {}
    route_plan = route_plan or {}
    problem_statuses = {"parser_miss", "no_results", "no_results_or_parser_miss", "blocked", "error"}
    problems = [item for item in diagnostics if item.get("status") in problem_statuses]
    ok_backends = [str(item.get("backend")) for item in diagnostics if item.get("status") == "ok"]
    if not problems:
        return {
            "status": "ok",
            "active_backends": ok_backends,
            "auto_downgrade": False,
            "guidance": ["所有搜索后端均产出可用候选，无需恢复动作。"],
            "followup_commands": [],
        }

    first_ok_index = next((idx for idx, item in enumerate(diagnostics) if item.get("status") == "ok"), None)
    auto_downgrade = bool(
        first_ok_index is not None
        and any(item.get("status") in problem_statuses for item in diagnostics[:first_ok_index])
    )
    blocked = [str(item.get("backend")) for item in problems if item.get("status") == "blocked"]
    parser_miss = [str(item.get("backend")) for item in problems if item.get("status") == "parser_miss"]
    errors = [str(item.get("backend")) for item in problems if item.get("status") == "error"]

    guidance: list[str] = []
    if "baidu" in blocked:
        guidance.append("Baidu 当前被安全验证/反爬拦截；不要自动重试或尝试破解验证码，把它当作本轮不可用。")
    if parser_miss:
        guidance.append(f"{', '.join(parser_miss)} 页面可访问但解析器未抓到结果，应视为解析器/模板问题而非资料不存在。")
    if auto_downgrade and ok_backends:
        guidance.append(f"已自动降级到 {', '.join(ok_backends)}，当前结果仍可继续使用，但应补充定向信源核验。")
    if errors and not ok_backends:
        guidance.append(f"{', '.join(errors)} 后端异常，建议稍后重试或改用可选搜索服务。")

    commands = _search_recovery_commands(
        query,
        route_plan=route_plan,
        profile=profile,
        ok_backends=ok_backends,
        limit=limit,
    )
    return {
        "status": "degraded" if ok_backends else "failed",
        "active_backends": ok_backends,
        "blocked_backends": blocked,
        "parser_miss_backends": parser_miss,
        "error_backends": errors,
        "auto_downgrade": auto_downgrade,
        "guidance": _unique_keep_order(guidance),
        "followup_commands": commands,
    }


def _search_recovery_commands(
    query: str,
    *,
    route_plan: dict[str, Any],
    profile: str | None,
    ok_backends: list[str],
    limit: int,
) -> list[str]:
    quoted = _shell_quote_for_command(query)
    profile_part = f" --profile {profile}" if profile in {"china", "english", "hybrid"} else ""
    command_limit = max(limit, 50)
    commands: list[str] = []
    for backend_name in ("bing", "duckduckgo"):
        if backend_name in ok_backends:
            commands.append(f"guanlan search {quoted}{profile_part} --backend {backend_name} --limit {command_limit} --trace")
            break
    for scope_id in route_plan.get("preferred_scopes") or []:
        if scope_id:
            commands.append(f"guanlan search {quoted}{profile_part} --scope {scope_id} --limit {command_limit} --trace")
        if len(commands) >= 3:
            break
    for command in route_plan.get("recommended_commands") or []:
        commands.append(str(command))
        if len(commands) >= 4:
            break
    if not any("guanlan research" in command for command in commands):
        commands.append(f"guanlan research {quoted}{profile_part} --limit {command_limit} --read-top 0")
    return _unique_keep_order(commands)[:5]


def _shell_quote_for_command(value: str) -> str:
    escaped = (value or "").replace('"', '\\"')
    return f'"{escaped}"'


def _raise_for_search_block(page: str, backend: str) -> None:
    markers = _SEARCH_BLOCK_MARKERS.get(backend, ())
    page_lower = page.lower()
    for marker in markers:
        if marker.lower() in page_lower:
            raise RuntimeError(f"captcha_or_verification: {marker}")


def _search_duckduckgo(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    _raise_for_search_block(page, "duckduckgo")

    parser = _DuckDuckGoHTMLParser()
    parser.feed(page)
    return _dedupe_results(parser.results)[:limit]


def _search_bing(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "count": min(max(limit, 1), 50)})
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    _raise_for_search_block(page, "bing")

    results: list[SearchResult] = []
    for block in re.findall(r'<li class="b_algo".*?</li>', page, flags=re.S):
        match = re.search(r"<h2[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.S)
        if not match:
            continue
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        title = _strip_tags(match.group(2))
        url = _normalize_bing_url(match.group(1))
        snippet = _strip_tags(snippet_match.group(1)) if snippet_match else ""
        if title and url:
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source="bing",
                    rank=len(results) + 1,
                )
            )
        if len(results) >= limit:
            break
    return results


def _search_baidu(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    # Baidu redirects HTTPS to HTTP for classic result HTML in some regions.
    url = "http://www.baidu.com/s?" + urllib.parse.urlencode({"wd": query, "rn": min(max(limit, 1), 50)})
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    _raise_for_search_block(page, "baidu")

    results: list[SearchResult] = []
    blocks = re.findall(r'<div class="result c-container.*?(?=<div class="result c-container|\Z)', page, flags=re.S)
    for block in blocks:
        title_match = re.search(r"<h3[^>]*>.*?<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.S)
        if not title_match:
            continue
        title = _strip_tags(title_match.group(2))
        href = html.unescape(title_match.group(1))
        mu_match = re.search(r'\bmu="([^"]+)"', block)
        url = html.unescape(mu_match.group(1)) if mu_match else href
        snippet = _strip_tags(_best_baidu_snippet(block))
        if title and url:
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source="baidu",
                    rank=len(results) + 1,
                )
            )
        if len(results) >= limit:
            break
    return results


def _search_wechat_sogou(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    api = _build_wechat_sogou_api()
    safe_query = _strip_site_filters(query)
    results: list[SearchResult] = []

    def reject_captcha(*_args, **_kwargs):
        raise RuntimeError("Sogou WeChat captcha required")

    pages = max(1, min(5, (max(limit, 1) + 9) // 10))
    for page in range(1, pages + 1):
        rows = api.search_article(
            safe_query,
            page=page,
            identify_image_callback=reject_captcha,
            decode_url=True,
        )
        for row in rows:
            item = _wechat_sogou_result(row, rank=len(results) + 1)
            if item:
                results.append(item)
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return results


def _build_wechat_sogou_api():
    try:
        import wechatsogou
    except ImportError as e:
        raise RuntimeError(
            "wechat-sogou backend requires optional dependency: "
            "install with `pip install 'guanlan[wechat]'` or "
            "`uv pip install 'guanlan[wechat]'`"
        ) from e
    return wechatsogou.WechatSogouAPI(captcha_break_time=1, timeout=min(_TIMEOUT, 10))


def _wechat_sogou_result(row: Any, rank: int) -> SearchResult | None:
    if not isinstance(row, dict):
        return None
    article = row.get("article")
    gzh = row.get("gzh")
    if not isinstance(article, dict):
        return None
    if not isinstance(gzh, dict):
        gzh = {}
    title = _collapse_ws(str(article.get("title") or ""))
    url = str(article.get("url") or article.get("content_url") or "").strip()
    if not title or not url.startswith(("http://", "https://")):
        return None

    abstract = _collapse_ws(str(article.get("abstract") or ""))
    wechat_name = _collapse_ws(str(gzh.get("wechat_name") or ""))
    published = _format_unix_date(article.get("time") or article.get("datetime"))
    snippet_parts = [part for part in (abstract, f"公众号: {wechat_name}" if wechat_name else "", f"发布: {published}" if published else "") if part]
    return SearchResult(
        title=title,
        url=url,
        snippet=" | ".join(snippet_parts),
        source="wechat_sogou",
        rank=rank,
    )


def _search_plugin_backend(backend: str, query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SearchResult]:
    plugin_ref = backend.split(":", 1)[1].strip()
    if not plugin_ref:
        raise ValueError("plugin backend requires plugin:name or plugin:/path/to/script.py")
    script_path = _resolve_plugin_backend_path(plugin_ref)
    proc = subprocess.run(
        [sys.executable, str(script_path), query, str(limit)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"plugin backend exited {proc.returncode}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"plugin backend returned invalid JSON: {e}") from e
    rows = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise RuntimeError("plugin backend must return a JSON array or {'results': [...]}")
    results: list[SearchResult] = []
    for idx, row in enumerate(rows[:limit], start=1):
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", "")).strip()
        url = str(row.get("url", "")).strip()
        if not title or not url:
            continue
        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=str(row.get("snippet", "")).strip(),
                source=f"plugin:{plugin_ref}",
                rank=idx,
            )
        )
    return results


def _resolve_plugin_backend_path(plugin_ref: str) -> Path:
    candidate = Path(plugin_ref).expanduser()
    if candidate.is_file():
        return candidate
    from guanlan.config import Config

    backends = Config().get("backends", {}) or {}
    config = backends.get(plugin_ref) if isinstance(backends, dict) else None
    if not isinstance(config, dict) or config.get("type") != "plugin":
        raise ValueError(f"unknown plugin backend: {plugin_ref}")
    path = Path(str(config.get("path", ""))).expanduser()
    if not path.is_file():
        raise ValueError(f"plugin backend path does not exist: {path}")
    return path


def _is_wechat_search_intent(site: str | None = None, query: str | None = None) -> bool:
    text = f"{site or ''} {query or ''}".lower()
    return "mp.weixin.qq.com" in text or "weixin.qq.com" in text


def _strip_site_filters(query: str) -> str:
    cleaned = re.sub(r"\bsite:\s*[\w.-]+", " ", query or "", flags=re.I)
    return _collapse_ws(cleaned) or query.strip()


def _format_unix_date(value: Any) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    try:
        return dt.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""


def read_url(
    url: str,
    max_chars: int | None = None,
    backend: str = "auto",
    fallback_search: bool = False,
    fallback_limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
    cache_ttl: int = 0,
    use_cache: bool = True,
    watch: bool = False,
    strict: bool = False,
    extract: str = "article",
) -> str:
    """Read a URL with Jina/direct fallbacks and optional search context."""
    return str(
        read_url_with_trace(
            url,
            max_chars=max_chars,
            backend=backend,
            fallback_search=fallback_search,
            fallback_limit=fallback_limit,
            profile=profile,
            cache_ttl=cache_ttl,
            use_cache=use_cache,
            watch=watch,
            strict=strict,
            extract=extract,
        )["content"]
    )


def read_url_with_trace(
    url: str,
    max_chars: int | None = None,
    backend: str = "auto",
    fallback_search: bool = False,
    fallback_limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
    cache_ttl: int = 0,
    use_cache: bool = True,
    watch: bool = False,
    strict: bool = False,
    extract: str = "article",
) -> dict[str, Any]:
    """Read a URL and return content plus backend/quality trace."""
    url = url.strip()
    if not url:
        raise ValueError("url is required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    cache_key = ""
    extract = (extract or "article").lower()
    if extract not in {"article", "text", "metadata", "links"}:
        raise ValueError("extract must be one of: article, text, metadata, links")

    if cache_ttl and cache_ttl > 0 and use_cache and not watch:
        cache_key = _cache_key(
            "read",
            {
                "url": url,
                "max_chars": max_chars or 0,
                "backend": backend,
                "fallback_search": fallback_search,
                "fallback_limit": fallback_limit,
                "profile": profile or "",
                "strict": strict,
                "extract": extract,
            },
        )
        cached = _cache_get("read", cache_key, ttl=cache_ttl)
        if cached is not None:
            text = str(cached.get("text", ""))
            quality = assess_read_quality(text)
            packet = {
                "url": url,
                "content": text,
                "quality": quality,
                "trace": {
                    "backend": backend,
                    "selected_backend": str(cached.get("selected_backend") or "cache"),
                    "strict": bool(strict),
                    "extract": extract,
                    "cache": "hit",
                    "cache_key": cache_key,
                    "attempts": list(cached.get("attempts") or []),
                    "fallback_search": False,
                },
            }
            packet["quality_report"] = build_read_quality_report(text, url=url, quality=quality, trace=packet["trace"])
            return packet

    backend = (backend or "auto").lower()
    errors: list[str] = []
    attempts: list[dict[str, Any]] = []
    text = ""
    weak_text = ""
    selected_backend = ""
    prefer_direct = extract in {"metadata", "links"}
    if backend in ("auto", "jina") and not prefer_direct:
        try:
            candidate = _read_with_jina(url)
            candidate_quality = assess_read_quality(candidate)
            if backend == "auto" and _read_should_fallback(candidate_quality, strict=strict):
                errors.append("jina: weak or blocked content")
                weak_text = weak_text or candidate
                attempts.append({"backend": "jina", "status": "weak", "chars": len(candidate), "quality": candidate_quality})
            else:
                text = candidate
                selected_backend = "jina"
                attempts.append({"backend": "jina", "status": "ok", "chars": len(candidate), "quality": candidate_quality})
        except Exception as e:
            errors.append(f"jina: {e}")
            attempts.append({"backend": "jina", "status": "error", "error": str(e)})
            if backend == "jina":
                raise
    if not text and backend in ("auto", "direct"):
        try:
            candidate = _call_read_direct(url, extract=extract)
            candidate_quality = assess_read_quality(candidate)
            if backend == "auto" and _read_should_fallback(candidate_quality, strict=strict):
                errors.append("direct: weak or blocked content")
                weak_text = weak_text or candidate
                attempts.append({"backend": "direct", "status": "weak", "chars": len(candidate), "quality": candidate_quality})
            else:
                text = candidate
                selected_backend = "direct"
                attempts.append({"backend": "direct", "status": "ok", "chars": len(candidate), "quality": candidate_quality})
        except Exception as e:
            errors.append(f"direct: {e}")
            attempts.append({"backend": "direct", "status": "error", "error": str(e)})
            if backend == "direct":
                raise
    fallback_used = False
    if not text and fallback_search and backend == "auto":
        try:
            text = _read_search_context(url, errors=errors, limit=fallback_limit, profile=profile)
            selected_backend = "search_fallback"
            fallback_used = True
            attempts.append({"backend": "search_fallback", "status": "ok", "chars": len(text), "quality": assess_read_quality(text)})
        except Exception as e:
            errors.append(f"search_context: {e}")
            attempts.append({"backend": "search_fallback", "status": "error", "error": str(e)})
    if not text and weak_text:
        text = weak_text
        selected_backend = selected_backend or "weak_fallback"
    if not text and errors:
        raise RuntimeError("; ".join(errors))
    if max_chars and max_chars > 0:
        text = text[:max_chars]
    if watch:
        text = _format_read_watch(url, text)
        selected_backend = "watch"
    quality = assess_read_quality(text)
    trace_payload = {
        "backend": backend,
        "selected_backend": selected_backend or backend,
        "strict": bool(strict),
        "extract": extract,
        "cache": "miss" if cache_key else "disabled",
        "cache_key": cache_key,
        "attempts": attempts,
        "errors": errors,
        "fallback_search": fallback_used,
    }
    if cache_key:
        _cache_set(
            "read",
            cache_key,
            {"text": text, "selected_backend": selected_backend or backend, "attempts": attempts},
        )
    packet = {"url": url, "content": text, "quality": quality, "trace": trace_payload}
    packet["quality_report"] = build_read_quality_report(text, url=url, quality=quality, trace=trace_payload)
    return packet


def assess_read_quality(text: str) -> dict[str, Any]:
    """Return a lightweight readability/noise score for extracted content."""
    normalized = _collapse_ws(text or "")
    noise_terms = (
        "登录",
        "注册",
        "广告",
        "客户端下载",
        "打开APP",
        "推荐阅读",
        "相关阅读",
        "上一篇",
        "下一篇",
        "发表评论",
        "版权声明",
    )
    noise_hits = [term for term in noise_terms if term.lower() in normalized.lower()]
    cjk_chars = sum(1 for char in normalized if "\u4e00" <= char <= "\u9fff")
    mojibake = _looks_mojibake(normalized)
    fallback = normalized.startswith("# 观澜阅读兜底")
    line_count = len([line for line in (text or "").splitlines() if line.strip()])
    avg_line_len = round(len(normalized) / max(line_count, 1), 1)
    noise_ratio = round(len(noise_hits) / max(line_count, 1), 3)
    weak = len(normalized) < _MIN_USEFUL_READ_CHARS or mojibake or any(marker in normalized.lower() for marker in _WEAK_READ_MARKERS)
    score = 100
    if fallback:
        score -= 25
    if weak:
        score -= 45
    if mojibake:
        score -= 35
    score -= min(len(noise_hits) * 8, 32)
    if cjk_chars < 80 and _contains_cjk(normalized):
        score -= 12
    score = max(score, 0)
    if fallback:
        label = "fallback"
    elif weak:
        label = "weak"
    elif noise_hits:
        label = "noisy"
    else:
        label = "clean"
    return {
        "label": label,
        "score": score,
        "chars": len(normalized),
        "cjk_chars": cjk_chars,
        "noise_hits": noise_hits,
        "mojibake": mojibake,
        "weak": weak,
        "fallback": fallback,
        "line_count": line_count,
        "avg_line_len": avg_line_len,
        "noise_ratio": noise_ratio,
        "strict_pass": bool(label == "clean" and score >= 70),
    }


def build_read_quality_report(
    text: str,
    *,
    url: str = "",
    quality: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable read-quality payload for CLI, research, and archive."""
    quality = dict(quality or assess_read_quality(text))
    trace = dict(trace or {})
    normalized = text or ""
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    short_lines = sum(1 for line in lines if len(_collapse_ws(line)) <= 18)
    link_like_lines = sum(1 for line in lines if re.search(r"https?://|阅读原文|点击|打开APP|下载", line, flags=re.I))
    body_ratio = round(max(0.0, 1.0 - min(quality.get("noise_ratio", 0) * 3 + link_like_lines / max(len(lines), 1), 0.95)), 3)
    blocked_markers = [marker for marker in _WEAK_READ_MARKERS if marker in _collapse_ws(normalized).lower()]
    usable = bool(quality.get("score", 0) >= 55 and quality.get("chars", 0) >= 160 and not blocked_markers)
    recommendations: list[str] = []
    if quality.get("fallback"):
        recommendations.append("当前内容来自搜索兜底，只能作为线索，建议补读原文或更稳定转载页。")
    if blocked_markers:
        recommendations.append("疑似登录墙/安全验证/访问限制，建议改用公开转载、官方来源或人工授权后的平台能力。")
    if quality.get("noise_hits"):
        recommendations.append("正文中仍有导航、登录或推荐阅读噪音，回答时优先引用连续正文段落。")
    if quality.get("chars", 0) < 500:
        recommendations.append("正文较短，可能只读到摘要或页面片段，建议扩大 read 或补充 search/research。")
    if not recommendations:
        recommendations.append("正文可用度较好，可作为证据摘读；仍建议和搜索结果中的来源身份交叉验证。")
    return {
        "url": url,
        "label": quality.get("label", "unknown"),
        "score": quality.get("score", 0),
        "usable": usable,
        "body_ratio": body_ratio,
        "chars": quality.get("chars", 0),
        "cjk_chars": quality.get("cjk_chars", 0),
        "line_count": quality.get("line_count", 0),
        "avg_line_len": quality.get("avg_line_len", 0),
        "short_line_count": short_lines,
        "link_like_line_count": link_like_lines,
        "noise_hits": quality.get("noise_hits", []),
        "blocked_markers": blocked_markers,
        "selected_backend": trace.get("selected_backend", ""),
        "cache": trace.get("cache", "disabled"),
        "recommendations": recommendations,
    }


def format_read_quality_report(report_or_packet: dict[str, Any]) -> str:
    """Render a read quality report as compact Markdown."""
    report = dict(report_or_packet.get("quality_report") or report_or_packet)
    lines = [
        "## 阅读质量报告",
        f"- label: {report.get('label', 'unknown')} score={report.get('score', 0)} usable={report.get('usable', False)}",
        f"- chars: {report.get('chars', 0)} cjk={report.get('cjk_chars', 0)} lines={report.get('line_count', 0)} body_ratio={report.get('body_ratio', 0)}",
        f"- backend/cache: {report.get('selected_backend', '') or '-'} / {report.get('cache', 'disabled')}",
    ]
    noise = report.get("noise_hits") or []
    if noise:
        lines.append(f"- noise: {', '.join(str(item) for item in noise)}")
    blocked = report.get("blocked_markers") or []
    if blocked:
        lines.append(f"- blocked_markers: {', '.join(str(item) for item in blocked)}")
    recommendations = report.get("recommendations") or []
    if recommendations:
        lines.append("- 建议:")
        lines.extend(f"  - {item}" for item in recommendations[:4])
    return "\n".join(lines)


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text or "")


def read_batch(
    urls: list[str],
    max_chars: int | None = None,
    backend: str = "auto",
    fallback_search: bool = True,
    fallback_limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
    cache_ttl: int = 0,
    strict: bool = False,
    extract: str = "article",
) -> list[dict[str, Any]]:
    """Read multiple URLs with per-item errors kept in the result list."""
    records: list[dict[str, Any]] = []
    for idx, url in enumerate(urls, start=1):
        clean_url = url.strip()
        if not clean_url:
            continue
        blocked_reason = _batch_block_reason(clean_url)
        if blocked_reason:
            records.append({"rank": idx, "url": clean_url, "status": "blocked", "error": blocked_reason})
            continue
        try:
            content = read_url(
                clean_url,
                max_chars=max_chars,
                backend=backend,
                fallback_search=fallback_search,
                fallback_limit=fallback_limit,
                profile=profile,
                cache_ttl=cache_ttl,
                strict=strict,
                extract=extract,
            )
            records.append({"rank": idx, "url": clean_url, "status": "ok", "content": content})
        except Exception as e:
            records.append({"rank": idx, "url": clean_url, "status": "error", "error": str(e)})
    return records


def _batch_block_reason(url: str) -> str:
    domain = _domain(url if url.startswith(("http://", "https://")) else "https://" + url)
    blocked_domains = {
        "xiaohongshu.com": "xiaohongshu",
        "xhslink.com": "xiaohongshu",
        "weibo.com": "weibo",
        "m.weibo.cn": "weibo",
        "twitter.com": "twitter",
        "x.com": "twitter",
        "linkedin.com": "linkedin",
        "douyin.com": "douyin",
    }
    for suffix, channel in blocked_domains.items():
        if domain == suffix or domain.endswith("." + suffix):
            return (
                f"batch read is disabled for {channel}; use explicit single reads or platform tools "
                "after user authorization"
            )
    return ""


def _read_search_context(
    url: str,
    errors: list[str] | None = None,
    limit: int = DEFAULT_READ_FALLBACK_LIMIT,
    profile: str | None = "china",
) -> str:
    """Build a search-based context packet when direct reading fails."""
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    query = _query_from_url(url)
    results = search_web(
        query,
        limit=max(limit, 1),
        site=domain or None,
        profile=profile,
    )
    if not results and domain:
        results = search_web(f"{domain} {query}", limit=max(limit, 1), profile=profile)

    lines = [
        "# 观澜阅读兜底",
        "",
        f"原始 URL: {url}",
        "",
        "说明: 原文读取失败或正文疑似不完整，以下内容来自公开搜索结果，适合作为继续核验的线索，不等同于原文全文。",
    ]
    if errors:
        lines.extend(["", "读取问题:"])
        lines.extend(f"- {err}" for err in errors)
    lines.extend(["", format_search_markdown(results, title=f"观澜搜索兜底 / {query}")])
    return "\n".join(lines)


def _snapshot_path(url: str) -> Path:
    key = _cache_key("snapshot", {"url": url})
    return cache_dir() / "snapshots" / f"{key}.json"


def _format_read_watch(url: str, text: str) -> str:
    """Compare current read content with the saved local snapshot."""
    path = _snapshot_path(url)
    saved_text = ""
    if path.exists():
        try:
            saved_text = str(json.loads(path.read_text(encoding="utf-8")).get("text", ""))
        except Exception:
            saved_text = ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"url": url, "updated_at": time.time(), "text": text}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not saved_text:
        return "\n".join(
            [
                "# 观澜内容追踪",
                "",
                f"URL: {url}",
                "状态: 已保存首次快照，后续再次运行会输出 diff。",
                "",
                text,
            ]
        )
    if saved_text == text:
        return "\n".join(["# 观澜内容追踪", "", f"URL: {url}", "状态: 未发现内容变化。"])
    diff = difflib.unified_diff(
        saved_text.splitlines(),
        text.splitlines(),
        fromfile="saved",
        tofile="current",
        lineterm="",
    )
    return "\n".join(["# 观澜内容追踪", "", f"URL: {url}", "状态: 发现内容变化。", "", "```diff", *diff, "```"])


def list_research_presets() -> dict[str, dict[str, Any]]:
    """Return available research presets."""
    return {key: dict(value) for key, value in RESEARCH_PRESETS.items()}


def resolve_research_preset(preset: str | None) -> dict[str, Any]:
    key = (preset or "general").strip().lower()
    if key not in RESEARCH_PRESETS:
        available = ", ".join(sorted(RESEARCH_PRESETS))
        raise ValueError(f"Unknown research preset: {preset}. Available: {available}")
    resolved = dict(RESEARCH_PRESETS[key])
    resolved["id"] = key
    return resolved


def build_research_packet(
    query: str,
    limit: int | None = None,
    site: str | None = None,
    sites: list[str] | None = None,
    scope: str | None = None,
    search_backend: str = "auto",
    profile: str | None = None,
    read_top: int | None = None,
    read_backend: str = "auto",
    max_read_chars: int | None = None,
    preset: str | None = "general",
    advisor: bool = False,
    advisor_style: str = "brief",
    select_top: int | None = None,
) -> dict[str, Any]:
    """Build an agent-ready evidence packet from search + selected reads."""
    preset_config = resolve_research_preset(preset)
    effective_limit = max(limit if limit is not None else preset_config["limit"], 1)
    effective_profile = profile or preset_config["profile"]
    preset_config = _research_preset_for_profile(preset_config, effective_profile)
    explicit_scope = scope if scope not in (None, "") else None
    explicit_sites = _normalize_sites(([site] if site else []) + (sites or []))
    route_plan = build_route_plan(
        query,
        preset=_route_preset_for_profile(preset_config["id"], effective_profile),
        scope=explicit_scope,
        site=site,
        sites=explicit_sites,
        profile=effective_profile,
        limit=effective_limit,
        read_top=read_top,
    )
    recency = detect_recency_intent(query)
    query_strategy = build_query_strategy(
        query,
        route_plan=route_plan.to_dict(),
        recency=recency,
        quality=detect_search_quality_profile(query, scope=explicit_scope, site=site, profile=effective_profile),
    )
    effective_scope = explicit_scope if explicit_scope is not None else preset_config["scope"]
    effective_sites = _research_sites(preset_config, site=site, sites=sites, explicit_scope=explicit_scope)
    effective_scopes = _research_scopes(
        preset_config,
        explicit_scope=explicit_scope,
        explicit_sites=effective_sites,
        site=site,
    )
    if explicit_scope is None and not explicit_sites:
        effective_scopes = _unique_keep_order(
            effective_scopes
            + list(route_plan.preferred_scopes)
        )[:6]
        if not effective_sites:
            effective_sites = _normalize_sites(list(route_plan.target_sites))[:6]
    effective_read_top = max(read_top if read_top is not None else preset_config["read_top"], 0)
    if read_top is None and preset_config["id"] == "general":
        effective_read_top = route_plan.read_top
    effective_max_read_chars = max(
        max_read_chars if max_read_chars is not None else preset_config["max_read_chars"],
        1,
    )
    effective_select_top = max(select_top if select_top is not None else 8, 0)
    results, search_errors, result_groups = _research_search(
        query,
        limit=effective_limit,
        sites=effective_sites,
        scopes=effective_scopes,
        search_backend=search_backend,
        profile=effective_profile,
        include_open_fallback=not bool(explicit_scope or explicit_sites),
        query_strategy=query_strategy,
    )
    readings: list[dict[str, Any]] = []
    for item in _select_reading_candidates(results, effective_read_top):
        try:
            content = read_url(
                item["url"],
                max_chars=effective_max_read_chars,
                backend=read_backend,
                fallback_search=True,
                fallback_limit=DEFAULT_READ_FALLBACK_LIMIT,
                profile=effective_profile,
            )
            read_quality = assess_read_quality(content)
            readings.append(
                _reading_record(
                    item,
                    status="ok",
                    content=content,
                    read_quality=read_quality,
                    quality_report=build_read_quality_report(content, url=str(item.get("url", "")), quality=read_quality),
                )
            )
        except Exception as e:
            readings.append(_reading_record(item, status="error", error=str(e)))

    packet = {
        "query": query,
        "preset": preset_config["id"],
        "preset_name": preset_config["name"],
        "profile": effective_profile or "",
        "site": site or "",
        "sites": effective_sites,
        "scope": effective_scope or "",
        "scopes": effective_scopes,
        "search_backend": search_backend,
        "read_backend": read_backend,
        "read_top": effective_read_top,
        "route_plan": route_plan.to_dict(),
        "query_strategy": query_strategy,
        "result_count": len(results),
        "source_mix": _source_mix(results),
        "source_diagnostics": build_source_diagnostics(results, route_plan=route_plan.to_dict()),
        "topic_count": len({item.get("topic_key") for item in results if item.get("topic_key")}),
        "search_errors": search_errors,
        "result_groups": result_groups,
        "results": results,
        "selected_evidence": _select_representative_evidence(results, effective_select_top),
        "readings": readings,
        "read_quality_summary": _read_quality_summary(readings),
        "guidance": list(preset_config.get("guidance", [])) + [
            "这是一份证据上下文，不是最终结论。",
            "先看“精选代表证据”，再回到完整搜索池补充细节；不要只凭第一条结果下判断。",
            "优先使用不同 topic、不同 source_type 的材料交叉验证。",
            "topic=related 的结果可作为补充线索，不要当成独立证据重复计数。",
            "阅读兜底内容只代表公开搜索线索，不等同于原文全文。",
            "路由计划是软约束：优先源用于提高适配度，开放搜索兜底用于避免信息池过窄。",
            "查询策略会把同一问题拆成不同证据角色；回答时要保留“官方、媒体、社区、用户样本”的差异。",
        ],
    }
    packet["evidence_audit"] = build_evidence_audit(packet)
    if advisor:
        packet["advisor"] = build_advisor_view(packet, style=advisor_style)
    return packet


def format_research_markdown(packet: dict[str, Any]) -> str:
    """Render a research packet as compact Markdown for agents."""
    query = str(packet.get("query", "")).strip()
    lines = [f"# 观澜研究证据包 / {query}", ""]
    lines.append("## 使用说明")
    for note in packet.get("guidance", []):
        lines.append(f"- {note}")

    lines.extend(["", "## 信源概览"])
    lines.append(f"- 结果数: {packet.get('result_count', 0)}")
    lines.append(f"- Topic 数: {packet.get('topic_count', 0)}")
    source_mix = packet.get("source_mix", {})
    if source_mix:
        mix = "；".join(f"{key}: {value}" for key, value in source_mix.items())
        lines.append(f"- 信源类型: {mix}")
    if packet.get("scope"):
        lines.append(f"- Scope: {packet['scope']}")
    if packet.get("scopes"):
        lines.append(f"- Scopes: {', '.join(packet['scopes'])}")
    if packet.get("site"):
        lines.append(f"- Site: {packet['site']}")
    if packet.get("sites"):
        lines.append(f"- Sites: {', '.join(packet['sites'])}")
    if packet.get("preset"):
        lines.append(f"- Preset: {packet.get('preset')} / {packet.get('preset_name', '')}")
    if packet.get("search_errors"):
        lines.append(f"- 部分搜索失败: {'；'.join(packet['search_errors'])}")
    query_strategy = packet.get("query_strategy") or {}
    if isinstance(query_strategy, dict) and query_strategy.get("variants"):
        lines.extend(["", "## 查询策略"])
        lines.append(f"- 提醒: {query_strategy.get('agent_hint', '')}")
        for item in list(query_strategy.get("variants") or [])[:6]:
            lines.append(f"- {item.get('role')}: `{item.get('query')}` — {item.get('reason')}")
    route_plan = packet.get("route_plan") or {}
    if isinstance(route_plan, dict) and route_plan:
        lines.extend(["", "## 路由计划"])
        lines.append(f"- 主要意图: {', '.join(route_plan.get('primary_intents') or []) or 'general'}")
        if route_plan.get("secondary_intents"):
            lines.append(f"- 次要意图: {', '.join(route_plan.get('secondary_intents') or [])}")
        lines.append(f"- 证据角色: {', '.join(route_plan.get('evidence_roles') or [])}")
        lines.append(f"- 优先 scope: {', '.join(route_plan.get('preferred_scopes') or []) or 'open web'}")
        if route_plan.get("fallback_scopes"):
            lines.append(f"- 兜底 scope: {', '.join(route_plan.get('fallback_scopes') or [])}")
        if route_plan.get("target_sites"):
            lines.append(f"- 推荐站点: {', '.join(route_plan.get('target_sites') or [])}")
        for warning in route_plan.get("warnings", [])[:4]:
            lines.append(f"- 边界: {warning}")

    diagnostics = packet.get("source_diagnostics")
    if isinstance(diagnostics, dict):
        lines.extend(["", format_source_diagnostics_markdown(diagnostics)])

    audit = packet.get("evidence_audit")
    if isinstance(audit, dict):
        lines.extend(["", format_evidence_audit_markdown(audit)])

    advisor = packet.get("advisor")
    if isinstance(advisor, dict):
        lines.extend(["", format_advisor_markdown(advisor)])

    selected = packet.get("selected_evidence", [])
    if selected:
        lines.extend(["", "## 精选代表证据", ""])
        lines.append(format_search_markdown(selected, title="代表证据"))

    groups = packet.get("result_groups", [])
    if groups:
        lines.extend(["", "## 子证据块"])
        for group in groups:
            label = str(group.get("label", ""))
            group_type = str(group.get("type", ""))
            count = group.get("result_count", 0)
            lines.extend(["", f"### {group_type}: {label}", f"- 结果数: {count}"])
            if group.get("error"):
                lines.append(f"- 错误: {group['error']}")
            group_results = group.get("results", [])
            if group_results:
                lines.extend(["", format_search_markdown(group_results[:3], title=f"{group_type} / {label}")])

    lines.extend(["", "## 搜索证据", ""])
    lines.append(format_search_markdown(packet.get("results", []), title="搜索结果"))

    readings = packet.get("readings", [])
    if readings:
        lines.extend(["", "## 原文摘读"])
        for item in readings:
            title = _collapse_ws(str(item.get("title", "")))
            url = str(item.get("url", ""))
            status = str(item.get("status", ""))
            source_type = str(item.get("source_type", "通用网页"))
            lines.extend(["", f"### [{status}] {title}", f"- URL: {url}", f"- 信源类型: {source_type}"])
            read_quality = item.get("read_quality") or {}
            if isinstance(read_quality, dict) and read_quality:
                lines.append(
                    "- 阅读质量: "
                    f"{read_quality.get('label', 'unknown')} "
                    f"score={read_quality.get('score', 0)} "
                    f"chars={read_quality.get('chars', 0)}"
                )
            if item.get("error"):
                lines.append(f"- 读取错误: {item['error']}")
            content = str(item.get("content", "")).strip()
            if content:
                lines.extend(["", content])
    return "\n".join(lines)


def format_research_prompt(packet: dict[str, Any], style: str = "deep") -> str:
    """Render a complete prompt for local LLMs that have no search tool."""
    query = str(packet.get("query", "")).strip()
    style = style if style in {"concise", "deep", "evidence", "decision"} else "deep"
    style_rules = {
        "concise": ["用短答案优先，证据只列最关键 3-5 条。", "如果信息不足，用一句话说明缺口。"],
        "deep": ["分层组织结论、依据、分歧和下一步。", "尽量保留不同信源的角色差异。"],
        "evidence": ["先列证据表，再给推断。", "每个关键判断后标注来源或证据类型。"],
        "decision": ["输出可行动建议、适用条件和暂缓条件。", "把风险、成本和下一步核验放在结尾。"],
    }[style]
    lines = [
        "# 观澜本地模型联网 Prompt",
        "",
        "你将基于观澜提供的中文互联网证据回答用户问题。请严格遵守：",
        "- 先回答问题，再列依据。",
        "- 保留来源链接，说明哪些判断来自事实、哪些只是推断。",
        "- 不要把搜索样本写成全网结论。",
        "- 证据不足时直接说明缺口，并给下一步检索建议。",
        "- 涉及医疗、法律、金融和重大决策时，只给信息整理与风险提醒。",
        f"- 当前输出风格: {style}。",
        *[f"- {rule}" for rule in style_rules],
        "",
        f"## 用户问题\n{query}",
        "",
        "## 观澜证据包",
        "",
    ]
    guidance = packet.get("guidance", [])
    if guidance:
        lines.append("### 使用规则")
        lines.extend(f"- {item}" for item in guidance)
        lines.append("")
    route_plan = packet.get("route_plan")
    if isinstance(route_plan, dict) and route_plan:
        lines.append("### 路由计划")
        lines.append(format_route_plan_markdown(route_plan))
        lines.append("")
    query_strategy = packet.get("query_strategy")
    if isinstance(query_strategy, dict) and query_strategy.get("variants"):
        lines.append("### 查询策略")
        lines.append(str(query_strategy.get("agent_hint") or ""))
        for item in list(query_strategy.get("variants") or [])[:6]:
            lines.append(f"- {item.get('role')}: {item.get('query')} ({item.get('reason')})")
        lines.append("")
    diagnostics = packet.get("source_diagnostics")
    if isinstance(diagnostics, dict):
        lines.append("### 信源诊断")
        lines.append(format_source_diagnostics_markdown(diagnostics))
        lines.append("")
    audit = packet.get("evidence_audit")
    if isinstance(audit, dict):
        lines.append("### 证据审计")
        lines.append(format_evidence_audit_context(audit))
        lines.append("")
    selected = packet.get("selected_evidence") or packet.get("results", [])[:8]
    lines.append(format_search_context(selected, title="精选代表证据"))
    readings = packet.get("readings", [])
    if readings:
        lines.extend(["", "### 原文摘读"])
        for item in readings:
            title = _collapse_ws(str(item.get("title", "")))
            url = str(item.get("url", ""))
            status = str(item.get("status", ""))
            content = _collapse_ws(str(item.get("content") or item.get("error") or ""))
            lines.extend(["", f"- [{status}] {title}", f"  来源: {url}", f"  摘要: {content[:900]}"])
    advisor = packet.get("advisor")
    if isinstance(advisor, dict):
        lines.extend(["", format_advisor_context(advisor)])
    lines.extend(
        [
            "",
            "## 请输出",
            "- 简明结论",
            "- 关键依据与来源",
            "- 不确定性和证据缺口",
            "- 可执行的下一步",
        ]
    )
    return "\n".join(lines)


def format_search_prompt(results: list[dict[str, Any]], query: str, title: str = "观澜搜索 Prompt") -> str:
    """Render search results as a complete local-LLM prompt."""
    return "\n".join(
        [
            f"# {title}",
            "",
            "你将基于以下观澜搜索证据回答用户问题。请保留来源链接，区分事实与推断，不要把样本写成全网结论。",
            "",
            f"## 用户问题\n{query}",
            "",
            format_search_context(results, title="搜索证据"),
            "",
            "## 请输出",
            "- 结论",
            "- 依据",
            "- 不确定性",
            "- 下一步检索建议",
        ]
    )


def format_read_prompt(content: str, query: str = "", url: str = "") -> str:
    """Render a single read result as a complete local-LLM prompt."""
    question = query or "请总结并分析这份材料。"
    source = f"\n来源: {url}\n" if url else ""
    return "\n".join(
        [
            "# 观澜网页阅读 Prompt",
            "",
            "请基于以下网页正文回答问题。不要引入正文以外的事实；如果正文不足，请说明不足。",
            source.rstrip(),
            f"## 用户问题\n{question}",
            "",
            "## 网页正文",
            content.strip(),
            "",
            "## 请输出",
            "- 摘要",
            "- 关键事实",
            "- 可引用来源",
            "- 不确定性",
        ]
    ).strip()


def format_read_context(content: str, url: str = "") -> str:
    """Render a single read result as compact agent context."""
    lines = ["# 观澜阅读上下文", ""]
    if url:
        lines.append(f"URL: {url}")
        lines.append("")
    lines.append(content.strip())
    return "\n".join(lines).strip() + "\n"


def format_read_trace(trace_packet: dict[str, Any]) -> str:
    """Render read backend and quality trace as Markdown."""
    trace = trace_packet.get("trace") or {}
    quality = trace_packet.get("quality") or {}
    lines = [
        "## 阅读 Trace",
        f"- selected_backend: {trace.get('selected_backend', '')}",
        f"- cache: {trace.get('cache', 'disabled')}",
        (
            "- quality: "
            f"{quality.get('label', 'unknown')} "
            f"score={quality.get('score', 0)} "
            f"chars={quality.get('chars', 0)} "
            f"noise={','.join(quality.get('noise_hits') or []) or 'none'}"
        ),
    ]
    attempts = trace.get("attempts") or []
    if attempts:
        lines.append("- attempts:")
        for item in attempts:
            item_quality = item.get("quality") or {}
            detail = f"  - {item.get('backend')}: {item.get('status')}"
            if item.get("chars") is not None:
                detail += f" chars={item.get('chars')}"
            if item_quality:
                detail += f" quality={item_quality.get('label')}/{item_quality.get('score')}"
            if item.get("error"):
                detail += f" error={item.get('error')}"
            lines.append(detail)
    errors = trace.get("errors") or []
    if errors:
        lines.append("- errors:")
        lines.extend(f"  - {error}" for error in errors)
    return "\n".join(lines)


def format_read_batch_prompt(records: list[dict[str, Any]], query: str = "请综合分析这些网页。") -> str:
    """Render batch read records as a complete local-LLM prompt."""
    return "\n".join(
        [
            "# 观澜批量阅读 Prompt",
            "",
            "请综合以下多篇网页。保留来源，合并重复信息，指出分歧和缺口。",
            "",
            f"## 用户问题\n{query}",
            "",
            format_read_batch_context(records),
            "",
            "## 请输出",
            "- 综合结论",
            "- 分来源依据",
            "- 分歧和不确定性",
            "- 下一步",
        ]
    )


def _research_scopes(
    preset_config: dict[str, Any],
    explicit_scope: str | None = None,
    explicit_sites: list[str] | None = None,
    site: str | None = None,
) -> list[str]:
    if explicit_scope:
        return [explicit_scope]
    # A caller-provided site request should stay narrowly site-bound unless the
    # caller also provides an explicit scope. Preset sites can still coexist
    # with preset scopes.
    if site and explicit_sites:
        return []
    scopes = [scope for scope in preset_config.get("scopes", []) if scope]
    if scopes:
        return scopes
    primary = preset_config.get("scope", "")
    return [primary] if primary else []


def _research_preset_for_profile(preset_config: dict[str, Any], profile: str | None) -> dict[str, Any]:
    """Adapt legacy China presets to the English source map when requested."""
    if profile != "english":
        return preset_config
    preset_id = str(preset_config.get("id") or "")
    replacements: dict[str, dict[str, Any]] = {
        "policy": {
            "scope": "global_official",
            "scopes": ["global_official", "global_news"],
            "sites": [],
            "guidance": ["优先英文官方/监管/标准组织原文，新闻报道只作为背景。"],
        },
        "official": {
            "scope": "global_official",
            "scopes": ["global_official", "global_news"],
            "sites": [],
            "guidance": ["优先英文官方、监管机构、标准组织或公司一手声明。"],
        },
        "industry": {
            "scope": "industry_analysis",
            "scopes": ["industry_analysis", "global_news", "company_primary"],
            "sites": [],
            "guidance": ["英文产业研究需区分事实、分析、预测和商业立场。"],
        },
        "ecommerce": {
            "scope": "industry_analysis",
            "scopes": ["industry_analysis", "global_news", "company_primary", "market_review"],
            "sites": [],
            "guidance": ["英文电商/零售问题优先公司、主流新闻、产业分析和评价样本交叉验证。"],
        },
        "reputation": {
            "scope": "community_sample",
            "scopes": ["community_sample", "market_review", "global_news", "company_primary"],
            "sites": ["reddit.com", "news.ycombinator.com", "g2.com", "trustpilot.com"],
            "guidance": ["英文口碑材料偏样本线索，不要直接代表总体比例。"],
        },
        "tech": {
            "scope": "developer",
            "scopes": ["developer", "company_primary", "community_sample"],
            "sites": ["github.com", "stackoverflow.com", "docs.github.com"],
            "guidance": ["优先官方文档、代码仓库、release notes、issue 和可复现开发者反馈。"],
        },
        "finance": {
            "scope": "global_official",
            "scopes": ["global_official", "global_news", "company_primary", "industry_analysis"],
            "sites": ["sec.gov", "reuters.com", "bloomberg.com"],
            "guidance": ["英文财经问题注意时效和风险，优先公告、监管文件、财报和主流财经报道。"],
        },
        "local": {
            "scope": "global_official",
            "scopes": ["global_official", "global_news"],
            "sites": [],
            "guidance": ["英文地域/公共政策问题优先对应政府、监管或公共机构原文。"],
        },
    }
    replacement = replacements.get(preset_id)
    if not replacement:
        return preset_config
    adapted = dict(preset_config)
    adapted.update(replacement)
    adapted["profile"] = "english"
    return adapted


def _route_preset_for_profile(preset_id: str, profile: str | None) -> str:
    if profile != "english":
        return preset_id
    mapping = {
        "policy": "global_policy",
        "official": "global_policy",
        "industry": "global_industry",
        "ecommerce": "global_industry",
        "reputation": "global_reputation",
        "finance": "global_policy",
        "company": "company",
    }
    return mapping.get(preset_id, preset_id)


def _research_sites(
    preset_config: dict[str, Any],
    site: str | None = None,
    sites: list[str] | None = None,
    explicit_scope: str | None = None,
) -> list[str]:
    explicit = _normalize_sites(([site] if site else []) + (sites or []))
    if explicit:
        return explicit
    if explicit_scope:
        return []
    return _normalize_sites(preset_config.get("sites", []))


def _normalize_sites(sites: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for site in sites:
        value = (site or "").strip().lower()
        if not value:
            continue
        value = value.removeprefix("https://").removeprefix("http://").removeprefix("www.")
        value = value.split("/", 1)[0]
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized


def _research_search(
    query: str,
    limit: int,
    sites: list[str],
    scopes: list[str],
    search_backend: str,
    profile: str | None,
    include_open_fallback: bool = True,
    query_strategy: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    groups: list[dict[str, Any]] = []
    jobs: list[tuple[str, str]] = [("scope", scope_id) for scope_id in scopes]
    jobs.extend(("site", site_id) for site_id in sites)
    if jobs and include_open_fallback:
        jobs.append(("general", "open_web"))
    if not jobs:
        results = search_web(query, limit=limit, backend=search_backend, profile=profile)
        return results, errors, [{"type": "general", "label": "web", "result_count": len(results), "results": results}]

    combined: list[dict[str, Any]] = []
    per_job_limit = max(3, min(limit, (limit // max(len(jobs), 1)) + 2))
    for job_type, target in jobs:
        job_query = _query_for_research_job(query, job_type, target, query_strategy)
        try:
            result = search_web(
                job_query,
                limit=per_job_limit,
                site=target if job_type == "site" else None,
                scope=target if job_type == "scope" else None,
                backend=search_backend,
                profile=profile,
            )
            combined.extend(result)
            groups.append({"type": job_type, "label": target, "query": job_query, "result_count": len(result), "results": result})
        except Exception as e:
            message = f"{job_type}:{target}: {e}"
            errors.append(message)
            groups.append({"type": job_type, "label": target, "query": job_query, "result_count": 0, "results": [], "error": str(e)})
    if not combined and errors:
        raise RuntimeError("; ".join(errors))
    return _merge_ranked_result_dicts(combined, limit=limit), errors, groups


def _query_for_research_job(
    query: str,
    job_type: str,
    target: str,
    query_strategy: dict[str, Any] | None = None,
) -> str:
    strategy = query_strategy or {}
    variants = list(strategy.get("variants") or [])
    if not variants:
        return query
    target = (target or "").lower()
    role_preferences: list[str] = []
    if job_type == "scope":
        if target in {"gov", "party_central", "local_official"}:
            role_preferences = ["official_primary", "authoritative_report", "fresh_news"]
        elif target == "global_official":
            role_preferences = ["official_primary", "authoritative_report", "fresh_news", "base"]
        elif target == "company_primary":
            role_preferences = ["company_primary", "technical_primary", "fresh_news", "base"]
        elif target == "developer":
            role_preferences = ["technical_primary", "developer_discussion", "base"]
        elif target in {"community_sample", "market_review"}:
            role_preferences = ["user_sample", "review", "fresh_news", "base"]
        elif target in {"global_news", "industry_analysis"}:
            role_preferences = ["industry_report", "company_context", "fresh_news", "base"]
        elif target in {"social_web", "tech_dev"}:
            role_preferences = ["user_sample", "developer_discussion", "review"]
        elif target in {"business", "ecommerce", "finance"}:
            role_preferences = ["industry_report", "fresh_news"]
        elif target == "academic":
            role_preferences = ["database_official", "publisher_guideline", "institution_policy", "base"]
        elif target in {"global_official"}:
            role_preferences = [
                "standard_original",
                "regulator_guidance",
                "clinical_guideline",
                "official_primary",
                "base",
            ]
    elif job_type == "site":
        if any(site in target for site in ("zhihu", "weibo", "xiaohongshu", "bilibili")):
            role_preferences = ["user_sample", "review", "fresh_news"]
        elif any(site in target for site in ("gov.cn", "people", "xinhuanet", "cctv")):
            role_preferences = ["official_primary", "authoritative_report"]
        elif any(site in target for site in ("reddit", "ycombinator", "g2.com", "trustpilot", "capterra")):
            role_preferences = ["user_sample", "review", "fresh_news"]
        elif any(site in target for site in ("github", "stackoverflow", "docs.")):
            role_preferences = ["technical_primary", "developer_discussion", "base"]
        elif any(site in target for site in ("openai", "anthropic", "microsoft", "google", "amazon", "meta")):
            role_preferences = ["company_primary", "technical_primary", "fresh_news"]
    elif job_type == "general":
        role_preferences = ["fresh_news", "base"]
    for role in role_preferences:
        for item in variants:
            if item.get("role") == role:
                return str(item.get("query") or query)
    return str(variants[0].get("query") or query)


def _merge_ranked_result_dicts(results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    candidates = [_result_from_dict(item) for item in results if item.get("url")]
    candidates.sort(key=lambda item: (-item.score, item.rank))
    deduped = _dedupe_results(candidates)
    ranked = sorted(deduped, key=lambda item: (-item.score, item.rank))
    if not all(item.topic_key for item in ranked):
        _assign_topic_clusters(ranked)
    ranked = _order_topic_representatives_first(ranked)
    for idx, item in enumerate(ranked, start=1):
        item.rank = idx
    return [item.to_dict() for item in ranked[:limit]]


def _result_from_dict(item: dict[str, Any]) -> SearchResult:
    return SearchResult(
        title=str(item.get("title", "")),
        url=str(item.get("url", "")),
        snippet=str(item.get("snippet", "")),
        source=str(item.get("source", "search")),
        rank=int(item.get("rank") or 0),
        domain=str(item.get("domain", "")),
        source_type=str(item.get("source_type", "通用网页")),
        matched_scope=str(item.get("matched_scope", "")),
        trust_level=int(item.get("trust_level") or 1),
        score=float(item.get("score") or 0),
        score_parts=dict(item.get("score_parts") or {}),
        topic_key=str(item.get("topic_key", "")),
        topic_size=int(item.get("topic_size") or 1),
        topic_role=str(item.get("topic_role", "single")),
        trace=dict(item.get("trace") or {}),
        evidence_role=str(item.get("evidence_role", "open_web_context")),
    )


def _select_representative_evidence(results: list[dict[str, Any]], select_top: int) -> list[dict[str, Any]]:
    """Pick a small, diverse evidence set from the broad candidate pool."""
    if select_top <= 0:
        return []
    chosen: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_topics: set[str] = set()
    seen_source_types: set[str] = set()
    seen_domains: set[str] = set()

    def evidence_score(item: dict[str, Any]) -> tuple[float, int]:
        score = float(item.get("score") or 0.0)
        topic = str(item.get("topic_key") or "")
        source_type = str(item.get("source_type") or "")
        domain = str(item.get("domain") or "")
        if item.get("topic_role") == "representative":
            score += 1.2
        if topic and topic not in seen_topics:
            score += 1.0
        if source_type and source_type not in seen_source_types:
            score += 0.6
        if domain and domain not in seen_domains:
            score += 0.3
        rank = int(item.get("rank") or 9999)
        return score, -rank

    candidates = [item for item in results if item.get("url")]
    primary_candidates = [item for item in candidates if item.get("topic_role") != "related"]
    if len(primary_candidates) >= select_top:
        candidates = primary_candidates
    while candidates and len(chosen) < select_top:
        best = max(candidates, key=evidence_score)
        candidates.remove(best)
        url = str(best.get("url") or "")
        if url in seen_urls:
            continue
        chosen.append(best)
        seen_urls.add(url)
        if best.get("topic_key"):
            seen_topics.add(str(best.get("topic_key")))
        if best.get("source_type"):
            seen_source_types.add(str(best.get("source_type")))
        if best.get("domain"):
            seen_domains.add(str(best.get("domain")))
    return chosen


def _select_reading_candidates(results: list[dict[str, Any]], read_top: int) -> list[dict[str, Any]]:
    if read_top <= 0:
        return []
    candidates = [item for item in results if item.get("topic_role") != "related"]
    if len(candidates) < read_top:
        seen = {item.get("url") for item in candidates}
        candidates.extend(item for item in results if item.get("url") not in seen)
    return candidates[:read_top]


def _reading_record(
    item: dict[str, Any],
    status: str,
    content: str = "",
    error: str = "",
    read_quality: dict[str, Any] | None = None,
    quality_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "rank": item.get("rank", 0),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "source_type": item.get("source_type", "通用网页"),
        "topic_key": item.get("topic_key", ""),
        "topic_role": item.get("topic_role", ""),
        "evidence_role": item.get("evidence_role", ""),
        "status": status,
        "content": content,
        "error": error,
        "read_quality": dict(read_quality or {}),
        "quality_report": dict(quality_report or {}),
    }


def _read_quality_summary(readings: list[dict[str, Any]]) -> dict[str, Any]:
    qualities = [item.get("read_quality") for item in readings if isinstance(item.get("read_quality"), dict) and item.get("read_quality")]
    status_counts: dict[str, int] = {}
    for item in readings:
        status = str(item.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    if not qualities:
        return {
            "count": 0,
            "usable_count": 0,
            "low_quality_count": 0,
            "avg_score": 0,
            "labels": {},
            "status_counts": status_counts,
            "recommendation": "未成功读取正文；下游 Agent 应使用搜索摘要并补读更合适的一手来源。",
        }
    labels: dict[str, int] = {}
    for quality in qualities:
        label = str(quality.get("label") or "unknown")
        labels[label] = labels.get(label, 0) + 1
    usable = [quality for quality in qualities if quality.get("score", 0) >= 55 and quality.get("chars", 0) >= 160]
    low_quality = [
        item
        for item in readings
        if isinstance(item.get("read_quality"), dict)
        and (item["read_quality"].get("score", 0) < 55 or item["read_quality"].get("chars", 0) < 160)
    ]
    avg_score = round(sum(float(quality.get("score") or 0) for quality in qualities) / max(len(qualities), 1), 1)
    if not usable:
        recommendation = "正文质量偏弱；回答前建议扩大 read-top、尝试 --read-backend direct，或回到搜索结果挑选更干净的来源。"
    elif len(usable) < len(qualities):
        recommendation = "部分页面正文偏弱；可引用 usable 页面，低质量页面只作线索。"
    else:
        recommendation = "代表页面正文质量可用；仍需保留来源、日期和平台边界。"
    return {
        "count": len(qualities),
        "usable_count": len(usable),
        "low_quality_count": len(low_quality),
        "avg_score": avg_score,
        "labels": labels,
        "status_counts": status_counts,
        "low_quality_urls": [str(item.get("url") or "") for item in low_quality[:5] if item.get("url")],
        "recommendation": recommendation,
    }


def build_evidence_audit(packet: dict[str, Any]) -> dict[str, Any]:
    """Build conservative cross-evidence audit hints without deciding the final answer."""
    query = str(packet.get("query", "")).strip()
    observations = _evidence_observations(packet)
    version_conflicts = _audit_version_conflicts(observations)
    claim_differences = _audit_claim_differences(observations)
    timeline = _audit_timeline(observations)
    warnings: list[str] = []
    if version_conflicts:
        warnings.append("检测到同一模型/实体的多个版本或叫法；回答前需要按来源、时间和官方材料交叉验证。")
    if claim_differences:
        warnings.append("检测到价格、参数量、日期或指标等结构化事实存在多个候选值；不要直接合并为单一结论。")
    if len(timeline) >= 2:
        warnings.append("检测到多个发布时间线索；较新的材料可能修正旧材料，但不能仅凭日期自动判定真伪。")
    if observations and not version_conflicts and not claim_differences:
        warnings.append("未发现明显版本号冲突；仍需核对关键数字、价格、参数量和发布日期。")
    verification_steps = [
        "把版本号、价格、参数量、发布日期等结构化事实单独列出来，不要直接合并相近说法。",
        "优先补查官方公告、模型文档、发布博客或权威媒体；博客/社区材料作为线索而非最终口径。",
        "出现冲突时说明“哪些来源这样说、日期分别是什么”，再给出你的取舍依据。",
    ]
    return {
        "title": "证据审计提示",
        "mode": "evidence_audit",
        "query": query,
        "observation_count": len(observations),
        "version_conflicts": version_conflicts,
        "claim_differences": claim_differences,
        "timeline": timeline[:8],
        "warnings": warnings,
        "verification_steps": verification_steps,
        "boundary": "这是交叉验证提示，不是事实裁决；观澜只标出需要核验的冲突和时间线索。",
    }


def format_evidence_audit_markdown(audit: dict[str, Any]) -> str:
    """Render evidence audit hints for research Markdown."""
    lines = [f"## {audit.get('title') or '证据审计提示'}"]
    boundary = str(audit.get("boundary") or "").strip()
    if boundary:
        lines.append(f"- 边界: {boundary}")
    warnings = [str(item) for item in audit.get("warnings", []) if str(item).strip()]
    if warnings:
        lines.append("- 提醒: " + "；".join(warnings[:3]))
    conflicts = list(audit.get("version_conflicts") or [])
    if conflicts:
        lines.append("- 版本/叫法冲突:")
        for conflict in conflicts[:5]:
            family = str(conflict.get("family") or "实体")
            mentions = " / ".join(str(item) for item in conflict.get("mentions", [])[:6])
            lines.append(f"  - {family}: {mentions}")
            for source in conflict.get("sources", [])[:4]:
                date = str(source.get("date") or "日期未知")
                title = _collapse_ws(str(source.get("title") or ""))[:90]
                url = str(source.get("url") or "")
                lines.append(f"    - {date} | {source.get('source_type', '通用网页')} | {title} | {url}")
    differences = list(audit.get("claim_differences") or [])
    if differences:
        lines.append("- 结构化事实差异:")
        for diff in differences[:6]:
            category = str(diff.get("category") or "claim")
            values = " / ".join(str(item) for item in diff.get("values", [])[:6])
            lines.append(f"  - {category}: {values}")
            for source in diff.get("sources", [])[:4]:
                date = str(source.get("date") or "日期未知")
                title = _collapse_ws(str(source.get("title") or ""))[:90]
                lines.append(f"    - {date} | {source.get('value')} | {title} | {source.get('url', '')}")
    timeline = list(audit.get("timeline") or [])
    if timeline:
        lines.append("- 时间线索:")
        for item in timeline[:5]:
            title = _collapse_ws(str(item.get("title") or ""))[:90]
            lines.append(f"  - {item.get('date')}: {title} ({item.get('source_type', '通用网页')})")
    steps = [str(item) for item in audit.get("verification_steps", []) if str(item).strip()]
    if steps:
        lines.append("- 建议核验:")
        lines.extend(f"  - {step}" for step in steps[:4])
    return "\n".join(lines)


def format_evidence_audit_context(audit: dict[str, Any]) -> str:
    """Render compact audit hints for prompt/context modes."""
    lines = [f"# {audit.get('title') or '证据审计提示'}"]
    if audit.get("boundary"):
        lines.append(f"边界: {audit['boundary']}")
    for warning in audit.get("warnings", [])[:3]:
        lines.append(f"- {warning}")
    for conflict in audit.get("version_conflicts", [])[:5]:
        mentions = " / ".join(str(item) for item in conflict.get("mentions", [])[:6])
        lines.append(f"- 冲突: {conflict.get('family')}: {mentions}")
    for diff in audit.get("claim_differences", [])[:5]:
        values = " / ".join(str(item) for item in diff.get("values", [])[:6])
        lines.append(f"- 差异: {diff.get('category')}: {values}")
    for item in audit.get("timeline", [])[:5]:
        lines.append(f"- 时间: {item.get('date')} | {item.get('title')} | {item.get('url')}")
    return "\n".join(lines)


def _evidence_observations(packet: dict[str, Any]) -> list[dict[str, Any]]:
    results = list(packet.get("selected_evidence") or []) + list(packet.get("results") or [])
    readings = list(packet.get("readings") or [])
    observations: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in results:
        url = str(item.get("url") or "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        text = _collapse_ws(
            " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("snippet") or ""),
                ]
            )
        )
        observations.append(_audit_observation(item, text=text, kind="search"))
    for item in readings:
        url = str(item.get("url") or "")
        text = _collapse_ws(
            " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("content") or ""),
                    str(item.get("error") or ""),
                ]
            )
        )
        if not text.strip():
            continue
        observations.append(_audit_observation(item, text=text[:5000], kind="read"))
    return observations


def _audit_observation(item: dict[str, Any], text: str, kind: str) -> dict[str, Any]:
    title = _collapse_ws(str(item.get("title") or ""))
    url = str(item.get("url") or "")
    source_type = str(item.get("source_type") or "通用网页")
    result = _result_from_dict(
        {
            "title": title,
            "url": url,
            "snippet": text[:800],
            "source_type": source_type,
            "domain": item.get("domain") or _domain(url),
        }
    )
    date = _extract_result_date(result)
    return {
        "kind": kind,
        "title": title,
        "url": url,
        "domain": item.get("domain") or _domain(url),
        "source_type": source_type,
        "date": date.isoformat() if isinstance(date, dt.date) else "",
        "mentions": _extract_version_mentions(text),
        "claims": _extract_structured_claims(text),
    }


def _extract_version_mentions(text: str) -> list[dict[str, str]]:
    patterns = [
        ("GPT", r"\bGPT[-\s]?\d+(?:\.\d+)?\b"),
        ("Claude", r"\bClaude(?:\s+(?:Opus|Sonnet|Haiku))?\s+\d+(?:\.\d+)?\b"),
        ("Claude", r"\bClaude\s+(?:Opus|Sonnet|Haiku|Mythos)(?:\s+\d+(?:\.\d+)?)?\b"),
        ("GLM", r"\bGLM[-\s]?\d+(?:\.\d+)?\b"),
        ("Qwen", r"\bQwen\s*\d+(?:\.\d+)?\b"),
        ("Gemini", r"\bGemini\s+\d+(?:\.\d+)?\b"),
        ("DeepSeek", r"\bDeepSeek[-\s]?[A-Za-z]?\d+(?:\.\d+)?\b"),
    ]
    mentions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for family, pattern in patterns:
        for match in re.finditer(pattern, text or "", flags=re.I):
            raw = _collapse_ws(match.group(0))
            canonical = re.sub(r"\s+", " ", raw).strip()
            key = (family, canonical.lower())
            if key in seen:
                continue
            seen.add(key)
            mentions.append({"family": family, "mention": canonical})
    return mentions


def _audit_version_conflicts(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_family: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for obs in observations:
        for mention in obs.get("mentions", []):
            family = str(mention.get("family") or "")
            value = str(mention.get("mention") or "")
            if not family or not value:
                continue
            by_family.setdefault(family, {}).setdefault(value, []).append(obs)
    conflicts: list[dict[str, Any]] = []
    for family, values in by_family.items():
        if len(values) < 2:
            continue
        sources: list[dict[str, str]] = []
        for value, obs_list in values.items():
            for obs in obs_list[:2]:
                sources.append(
                    {
                        "mention": value,
                        "title": str(obs.get("title") or ""),
                        "url": str(obs.get("url") or ""),
                        "date": str(obs.get("date") or ""),
                        "source_type": str(obs.get("source_type") or "通用网页"),
                    }
                )
        conflicts.append(
            {
                "family": family,
                "mentions": sorted(values.keys(), key=str.lower),
                "sources": sources,
                "severity": "needs_review",
            }
        )
    return conflicts


def _extract_structured_claims(text: str) -> list[dict[str, str]]:
    """Extract lightweight structured factual claims that often need cross-checking."""
    patterns = [
        (
            "price",
            r"(?:[$¥￥]\s?\d+(?:\.\d+)?(?:\s*(?:/|per|每)\s*(?:1m|million|百万|千|k|tokens?|token))?|(?:\d+(?:\.\d+)?\s*(?:元|美元|人民币)(?:\s*(?:/|每)\s*(?:百万|千|tokens?|token|次))?))",
        ),
        (
            "parameter_count",
            r"\b\d+(?:\.\d+)?\s*(?:B|M|K|T)\s*(?:parameters?|params?)?\b|(?:\d+(?:\.\d+)?\s*(?:万亿|千亿|百亿|亿|万)\s*参数)",
        ),
        (
            "percentage_metric",
            r"\b\d+(?:\.\d+)?\s?%",
        ),
        (
            "date",
            r"\b20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?\b",
        ),
    ]
    claims: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for category, pattern in patterns:
        for match in re.finditer(pattern, text or "", flags=re.I):
            raw = _collapse_ws(match.group(0))
            value = _normalize_claim_value(category, raw)
            key = (category, value.lower())
            if not value or key in seen:
                continue
            seen.add(key)
            claims.append({"category": category, "value": value})
    return claims


def _normalize_claim_value(category: str, value: str) -> str:
    normalized = _collapse_ws(value).replace("￥", "¥")
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if category == "date":
        normalized = normalized.replace("年", "-").replace("月", "-").replace("日", "")
        normalized = normalized.replace("/", "-").replace(".", "-")
        parts = [part for part in normalized.split("-") if part]
        if len(parts) >= 2 and all(part.isdigit() for part in parts[:2]):
            year = parts[0]
            month = parts[1].zfill(2)
            day = parts[2].zfill(2) if len(parts) >= 3 and parts[2].isdigit() else ""
            return "-".join(part for part in (year, month, day) if part)
    return normalized


def _audit_claim_differences(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_category: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for obs in observations:
        for claim in obs.get("claims", []):
            category = str(claim.get("category") or "")
            value = str(claim.get("value") or "")
            if not category or not value:
                continue
            by_category.setdefault(category, {}).setdefault(value, []).append(obs)
    differences: list[dict[str, Any]] = []
    for category, values in by_category.items():
        if len(values) < 2 or len(values) > 8:
            continue
        source_urls = {str(obs.get("url") or "") for obs_list in values.values() for obs in obs_list}
        if len(source_urls) < 2:
            continue
        sources: list[dict[str, str]] = []
        for value, obs_list in values.items():
            for obs in obs_list[:2]:
                sources.append(
                    {
                        "value": value,
                        "title": str(obs.get("title") or ""),
                        "url": str(obs.get("url") or ""),
                        "date": str(obs.get("date") or ""),
                        "source_type": str(obs.get("source_type") or "通用网页"),
                    }
                )
        differences.append(
            {
                "category": category,
                "values": sorted(values.keys(), key=str.lower),
                "sources": sources,
                "severity": "needs_review",
            }
        )
    return differences


def _audit_timeline(observations: list[dict[str, Any]]) -> list[dict[str, str]]:
    timeline: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for obs in observations:
        date = str(obs.get("date") or "")
        url = str(obs.get("url") or "")
        if not date or (date, url) in seen:
            continue
        seen.add((date, url))
        timeline.append(
            {
                "date": date,
                "title": str(obs.get("title") or ""),
                "url": url,
                "source_type": str(obs.get("source_type") or "通用网页"),
            }
        )
    return sorted(timeline, key=lambda item: item["date"], reverse=True)


def build_advisor_view(packet: dict[str, Any], style: str = "brief") -> dict[str, Any]:
    """Build evidence-bound guidance that helps an agent write its own advice."""
    query = str(packet.get("query", "")).strip()
    preset = str(packet.get("preset", "general")).strip() or "general"
    results = list(packet.get("results") or [])
    readings = list(packet.get("readings") or [])
    source_mix = dict(packet.get("source_mix") or _source_mix(results))
    topic_count = int(packet.get("topic_count") or 0)
    result_count = int(packet.get("result_count") or len(results))
    read_top = int(packet.get("read_top") or 0)

    intents = _advisor_intents(query, preset, packet, source_mix)
    supports = _advisor_supports(source_mix, topic_count, result_count, readings)
    limits = _advisor_limits(packet, source_mix, topic_count, result_count, readings, read_top)
    next_steps = _advisor_next_steps(query, preset, source_mix, limits)
    style = style if style in {"brief", "decision", "risk", "strategy"} else "brief"
    answer_frame = _advisor_answer_frame(preset, query, source_mix, supports, limits, next_steps, style=style)

    return {
        "title": "助理视角规则",
        "mode": "agent_guidance",
        "style": style,
        "stance": "以下内容用于指导 Agent 生成建议：它只约束如何基于当前证据思考，不代表用户真实目的，也不构成最终结论。",
        "briefing": _advisor_briefing(query, preset, source_mix, supports, limits, next_steps, style=style),
        "answer_frame": answer_frame,
        "natural_guidance": _advisor_natural_guidance(query, preset, source_mix, supports, limits, next_steps, style=style),
        "synthesis_rules": _advisor_synthesis_rules(preset, query, source_mix),
        "suggested_angles": intents,
        "possible_intents": intents,
        "evidence_supports": supports,
        "evidence_limits": limits,
        "scenario_advice": _advisor_scenario_advice(preset, query, source_mix),
        "next_steps": next_steps,
        "response_contract": _advisor_response_contract(packet, limits),
    }


def format_advisor_markdown(advisor: dict[str, Any]) -> str:
    """Render advisor output as a compact, caveated Markdown block."""
    lines = [f"## {advisor.get('title') or '助理视角'}"]
    stance = str(advisor.get("stance") or "").strip()
    if stance:
        lines.extend(["", stance])
    sections = [
        ("自然作答骨架", advisor.get("answer_frame") or []),
        ("自然表达提示", advisor.get("natural_guidance") or []),
        ("给 Agent 的写作规则", advisor.get("synthesis_rules") or []),
        ("可展开的判断方向", advisor.get("suggested_angles") or advisor.get("possible_intents") or []),
        ("当前证据能支持", advisor.get("evidence_supports") or []),
        ("当前证据边界", advisor.get("evidence_limits") or []),
        ("不同场景的展开方式", advisor.get("scenario_advice") or []),
        ("输出时必须避免", advisor.get("response_contract") or []),
        ("建议补充", advisor.get("next_steps") or []),
    ]
    for title, items in sections:
        if not items:
            continue
        lines.extend(["", f"### {title}"])
        for item in items:
            lines.append(f"- {item}")
    return "\n".join(lines)


def format_advisor_context(advisor: dict[str, Any]) -> str:
    """Render advisor output for compact LLM context mode."""
    lines = [f"# {advisor.get('title') or '助理视角'}"]
    stance = str(advisor.get("stance") or "").strip()
    if stance:
        lines.append(stance)
    briefing = str(advisor.get("briefing") or "").strip()
    if briefing:
        lines.append("briefing: " + briefing)
    for key, title in (
        ("answer_frame", "自然作答骨架"),
        ("natural_guidance", "自然表达提示"),
        ("synthesis_rules", "写作规则"),
        ("suggested_angles", "可展开方向"),
        ("evidence_supports", "适合支持"),
        ("evidence_limits", "不适合支持"),
        ("scenario_advice", "下一步"),
        ("response_contract", "输出边界"),
    ):
        items = [str(item) for item in advisor.get(key, []) if str(item).strip()]
        if items:
            lines.append(f"{title}: " + "；".join(items[:3]))
    return "\n".join(lines)


def _advisor_briefing(
    query: str,
    preset: str,
    source_mix: dict[str, int],
    supports: list[str],
    limits: list[str],
    next_steps: list[str],
    style: str = "brief",
) -> str:
    """Summarize how an agent should naturally use the advisor block."""
    source_phrase = _advisor_source_phrase(source_mix)
    strength = _advisor_strength_phrase(supports, limits)
    action = next_steps[0] if next_steps else "继续补证后再下结论"
    angle = _advisor_primary_angle(preset, query)
    style_opening = {
        "brief": "先给一段短判断",
        "decision": "先给可选行动和取舍",
        "risk": "先把风险和不可下结论处说清楚",
        "strategy": "先把局势、机会和后续打法分层",
    }.get(style, "先给一段短判断")
    return (
        f"可以把这次检索当作“{angle}”的初步证据包：{source_phrase}。"
        f"{strength} 面向用户时，{style_opening}，再交代证据边界，最后落到下一步：{action}。"
    )


def _advisor_answer_frame(
    preset: str,
    query: str,
    source_mix: dict[str, int],
    supports: list[str],
    limits: list[str],
    next_steps: list[str],
    style: str = "brief",
) -> list[str]:
    """Return a non-template answer scaffold that the calling agent can adapt."""
    angle = _advisor_primary_angle(preset, query)
    source_phrase = _advisor_source_phrase(source_mix)
    if style == "decision":
        frame = [
            f"先给“可以做/暂缓做/继续核验”的行动分叉，说明这是围绕“{angle}”的证据判断。",
            f"再交代主要来源结构：{source_phrase}，让用户知道“谁在说”。",
        ]
    elif style == "risk":
        frame = [
            f"先说当前最容易误判的地方，不要把“{angle}”包装成最终结论。",
            f"再交代主要来源结构：{source_phrase}，特别标出样本偏差和缺口。",
        ]
    elif style == "strategy":
        frame = [
            f"先把“{angle}”拆成局势、机会、风险和下一步四层。",
            f"再交代主要来源结构：{source_phrase}，让用户理解判断基础。",
        ]
    else:
        frame = [
            f"开场先点明这只是围绕“{angle}”的证据判断，不要直接包装成最终结论。",
            f"第二步交代主要来源结构：{source_phrase}，让用户知道“谁在说”。",
        ]
    if supports:
        frame.append(f"第三步只展开证据能支撑的部分，例如：{supports[0]}。")
    if limits:
        frame.append(f"第四步主动说出限制：{limits[0]}。")
    if next_steps:
        frame.append(f"结尾给一个可执行动作：{next_steps[0]}。")
    return frame[:5]


def _advisor_natural_guidance(
    query: str,
    preset: str,
    source_mix: dict[str, int],
    supports: list[str],
    limits: list[str],
    next_steps: list[str],
    style: str = "brief",
) -> list[str]:
    """Return short, non-final phrasing hints for the calling agent."""
    angle = _advisor_primary_angle(preset, query)
    source_phrase = _advisor_source_phrase(source_mix)
    lead_map = {
        "brief": f"可以用一句话先定调：这是一份关于“{angle}”的初步观察，不是全网结论。",
        "decision": f"可以先把选择摆出来：现在更适合继续核验、谨慎推进，还是先暂停，取决于“{angle}”里哪些证据最硬。",
        "risk": f"可以先提醒误判风险：当前材料能帮助看见“{angle}”，但不能替代权威核验或完整样本。",
        "strategy": f"可以按“现状-机会-风险-下一步”写，让“{angle}”从材料堆变成行动路线。",
    }
    hints = [
        lead_map.get(style, lead_map["brief"]),
        f"写来源结构时不要说“网上都说”，改成“当前样本{source_phrase}”。",
    ]
    if supports:
        hints.append(f"能展开的部分优先围绕：{supports[0]}。")
    if limits:
        hints.append(f"必须顺手交代边界：{limits[0]}。")
    if next_steps:
        hints.append(f"结尾不要空泛，可以落到：{next_steps[0]}。")
    return _unique_keep_order(hints)[:5]


def _advisor_source_phrase(source_mix: dict[str, int]) -> str:
    if not source_mix:
        return "当前来源结构还不清晰，需要先补充不同信源"
    sorted_sources = sorted(source_mix.items(), key=lambda row: (-int(row[1]), row[0]))
    parts = [f"{source_type} {count} 条" for source_type, count in sorted_sources[:3]]
    if len(sorted_sources) > 3:
        parts.append("以及其他来源")
    return "主要来自 " + "、".join(parts)


def _advisor_strength_phrase(supports: list[str], limits: list[str]) -> str:
    if supports and limits:
        return f"它适合用来{supports[0]}，但{limits[0]}。"
    if supports:
        return f"它适合用来{supports[0]}。"
    if limits:
        return f"当前证据仍偏线索级，尤其要注意：{limits[0]}。"
    return "当前证据可以辅助判断，但仍应保留不确定性。"


def _advisor_primary_angle(preset: str, query: str) -> str:
    text = query.lower()
    if preset in {"policy", "official", "local"} or _contains_any(text, ["政策", "监管", "通知", "官方"]):
        return "官方口径与影响判断"
    if preset in {"reputation", "ecommerce"} or _contains_any(text, ["评价", "口碑", "购买", "值不值得", "产品"]):
        return "口碑线索与行动建议"
    if preset in {"industry", "finance"} or _contains_any(text, ["行业", "融资", "财报", "股价", "商业化"]):
        return "行业趋势与风险识别"
    if preset == "tech" or _contains_any(text, ["框架", "开源", "github", "技术", "选型"]):
        return "技术选型与真实限制"
    if _contains_any(text, ["热点", "最近", "今天", "近期"]):
        return "近期水势与后续追踪"
    return "主题判断与下一步研究"


def _advisor_synthesis_rules(
    preset: str,
    query: str,
    source_mix: dict[str, int],
) -> list[str]:
    rules = [
        "先用证据回答用户真正要解决的问题，再说明不确定性和需要补证的地方",
        "把建议写成可执行的下一步，而不是复述搜索结果或固定模板",
        "明确区分事实、推断、风险提醒和行动建议",
    ]
    if preset in {"policy", "official", "local"} or _contains_any(query, ["政策", "监管", "通知", "官方"]):
        rules.append("涉及政策或官方口径时，优先引用原文和发文主体，再解释影响")
    if preset in {"reputation", "ecommerce"} or _contains_any(query, ["口碑", "评价", "购买", "产品"]):
        rules.append("涉及口碑时，提炼高频场景和用户原话，不把样本热度写成总体比例")
    if any(_source_has(key, ["社交", "内容平台"]) for key in source_mix):
        rules.append("社交材料只能支持线索和表达，不直接支持总体判断")
    if _high_stakes_query(query):
        rules.append("涉及医疗、法律、金融或重大决策时，只给研究路线和风险提示")
    return _unique_keep_order(rules)[:5]


def _advisor_intents(
    query: str,
    preset: str,
    packet: dict[str, Any],
    source_mix: dict[str, int],
) -> list[str]:
    text = query.lower()
    sites = " ".join(str(site).lower() for site in packet.get("sites", []) or [])
    site = str(packet.get("site", "")).lower()
    scope = str(packet.get("scope", "")).lower()
    haystack = " ".join([text, sites, site, scope, preset])
    intents: list[str] = []

    if preset in {"policy", "official", "local"} or _contains_any(haystack, ["政策", "监管", "通知", "法规", "官方", "gov", "party_central"]):
        intents.extend(["寻找可引用的官方依据或政策口径", "判断某项政策、监管或公共议题对业务/研究的影响"])
    if preset in {"reputation", "ecommerce"} or _contains_any(haystack, ["评价", "口碑", "吐槽", "小红书", "知乎", "微博", "购买", "产品"]):
        intents.extend(["判断产品、品牌或服务的真实口碑线索", "为购买、选型、运营或竞品分析寻找用户语言"])
    if preset in {"industry", "finance"} or _contains_any(haystack, ["融资", "裁员", "财报", "股价", "行业", "商业化", "公司"]):
        intents.extend(["评估公司、行业或商业趋势是否值得继续关注", "识别合作、求职、投资或供应链相关风险"])
    if preset == "tech" or _contains_any(haystack, ["框架", "开源", "github", "技术", "开发者", "选型", "api"]):
        intents.extend(["做技术选型或工程调研", "寻找真实使用反馈、限制和可复现线索"])
    if any("社交" in key or "内容平台" in key for key in source_mix):
        intents.append("观察公开讨论中的情绪、痛点和高频表达")

    intents.append("快速判断这个主题是否值得进入更深一轮核验")
    return _unique_keep_order(intents)[:4]


def _advisor_supports(
    source_mix: dict[str, int],
    topic_count: int,
    result_count: int,
    readings: list[dict[str, Any]],
) -> list[str]:
    supports: list[str] = []
    source_keys = list(source_mix)
    if any(_source_has(key, ["政府", "部委", "党央媒", "官方"]) for key in source_keys):
        supports.append("判断官方口径、政策表述或权威报道中的主要说法")
    if any(_source_has(key, ["商业", "产业", "财经", "电商"]) for key in source_keys):
        supports.append("梳理商业媒体、产业媒体或财经来源中的趋势线索")
    if any(_source_has(key, ["社交", "内容平台", "开发者", "社区"]) for key in source_keys):
        supports.append("发现公开讨论里的用户语言、痛点、情绪和使用场景")
    if topic_count >= 3:
        supports.append("从多个 topic 中挑出不同角度，避免只围绕同一篇转载反复计数")
    elif result_count > 0:
        supports.append("形成初步线索清单，适合决定下一步读哪些原文")
    if any(item.get("status") == "ok" and str(item.get("content", "")).strip() for item in readings):
        supports.append("基于已读取原文片段做更稳的摘要和引用")
    return supports or ["形成初步搜索线索，但更适合继续核验而不是直接下结论"]


def _advisor_limits(
    packet: dict[str, Any],
    source_mix: dict[str, int],
    topic_count: int,
    result_count: int,
    readings: list[dict[str, Any]],
    read_top: int,
) -> list[str]:
    limits: list[str] = []
    source_keys = list(source_mix)
    successful_reads = [
        item for item in readings if item.get("status") == "ok" and str(item.get("content", "")).strip()
    ]
    if result_count < 3:
        limits.append("结果数量偏少，暂时不适合做强结论")
    if len(source_mix) <= 1 and result_count >= 3:
        limits.append("来源类型较单一，容易放大单一圈层或单一媒体视角")
    if topic_count <= 1 and result_count >= 3:
        limits.append("同题聚类较集中，可能存在转载或同源重复")
    if read_top == 0 or not successful_reads:
        limits.append("目前主要依赖搜索摘要，缺少原文级核验")
    if any(_source_has(key, ["社交", "内容平台"]) for key in source_keys):
        limits.append("社交平台材料适合发现样本线索，不适合直接代表总体口碑")
    if packet.get("search_errors"):
        limits.append("部分搜索后端失败，结果覆盖面可能不完整")
    if _high_stakes_query(str(packet.get("query", ""))):
        limits.append("这个查询可能涉及高影响决策，建议把当前输出只当作研究线索")
    return _unique_keep_order(limits)


def _advisor_scenario_advice(
    preset: str,
    query: str,
    source_mix: dict[str, int],
) -> list[str]:
    advice: list[str] = []
    text = query.lower()
    if preset in {"policy", "official", "local"}:
        advice.append("如果你是为了写材料或引用依据：优先读取政府/部委原文，再用媒体解读补背景")
        advice.append("如果你是为了判断影响：把政策原文、实施地区、适用对象和时间节点分开核对")
    if preset in {"reputation", "ecommerce"} or _contains_any(text, ["评价", "口碑", "购买", "产品"]):
        advice.append("如果你是为了购买或采用：先看负面反馈是否集中在同一版本、渠道或使用场景")
        advice.append("如果你是为了竞品/运营：提取用户原话和高频痛点，但不要用热门样本估算总体比例")
    if preset in {"industry", "finance"}:
        advice.append("如果你是为了商业判断：把事实报道、市场观点和公司宣传分开看")
        advice.append("如果你是为了风险判断：优先补官方公告、财报或一手披露材料")
    if preset == "tech":
        advice.append("如果你是为了技术选型：优先补版本、维护活跃度、真实限制和失败案例")
        advice.append("如果你是为了写方案：把社区反馈和官方文档分别引用")
    if any(_source_has(key, ["社交", "内容平台"]) for key in source_mix):
        advice.append("如果你是为了舆情观察：关注重复出现的表达和场景，不要只看单条高互动内容")
    if not advice:
        advice.append("如果你是为了快速了解：先读不同 source_type 的代表结果，再决定是否扩大搜索范围")
        advice.append("如果你是为了做判断：先补一手来源或原文摘读，再把当前结果当作辅助材料")
    return _unique_keep_order(advice)[:4]


def _advisor_next_steps(
    query: str,
    preset: str,
    source_mix: dict[str, int],
    limits: list[str],
) -> list[str]:
    steps: list[str] = []
    if any("原文" in item or "摘要" in item for item in limits):
        steps.append("读取 2-3 条不同 topic、不同 source_type 的代表原文")
    if any("来源类型较单一" in item for item in limits):
        steps.append("补一个不同信源池，例如官方、产业媒体或社交公开页")
    if any("社交平台" in item for item in limits):
        steps.append("把社交样本当作痛点池，再用官方说明或第三方评测交叉验证")
    if preset in {"policy", "official", "local"} and not any(_source_has(key, ["政府", "部委"]) for key in source_mix):
        steps.append("增加 gov 或 party_central scope，优先找原文")
    if preset in {"reputation", "ecommerce"} and not any(_source_has(key, ["社交", "内容平台"]) for key in source_mix):
        steps.append("补充知乎、微博、小红书、B站等公开页搜索，但注意登录态和样本偏差")
    if _high_stakes_query(query):
        steps.append("涉及重大决策时，补充权威来源或专业意见后再行动")
    steps.append("把当前建议视为下一步研究路线，而不是最终判断")
    return _unique_keep_order(steps)[:4]


def _advisor_response_contract(packet: dict[str, Any], limits: list[str]) -> list[str]:
    contract = [
        "不要声称已经知道用户真实动机，只能说“可能在关心”",
        "不要把当前搜索样本写成全网结论",
        "不要省略来源、证据边界和失败后端带来的覆盖缺口",
    ]
    if any("高影响决策" in item for item in limits) or _high_stakes_query(str(packet.get("query", ""))):
        contract.append("不要给医疗、法律、金融等高风险事项的最终建议")
    if packet.get("read_top") == 0:
        contract.append("没有原文摘读时，不要写成已经完成深度阅读")
    return contract


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle.lower() in text for needle in needles)


def _source_has(source_type: str, needles: list[str]) -> bool:
    return any(needle in source_type for needle in needles)


def _unique_keep_order(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _collapse_ws(str(item))
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


def _high_stakes_query(query: str) -> bool:
    return _contains_any(
        query.lower(),
        ["投资", "股票", "股价", "医疗", "诊断", "药", "法律", "诉讼", "裁员", "offer", "入职", "合规"],
    )


def _source_mix(results: list[dict[str, Any]]) -> dict[str, int]:
    mix: dict[str, int] = {}
    for item in results:
        key = str(item.get("source_type") or "通用网页")
        mix[key] = mix.get(key, 0) + 1
    return dict(sorted(mix.items(), key=lambda item: (-item[1], item[0])))


def build_source_diagnostics(
    results: list[dict[str, Any]],
    route_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize source diversity, evidence roles, and blind spots."""
    route_plan = route_plan or {}
    cards = []
    for item in results:
        domain = str(item.get("domain") or _domain(str(item.get("url", ""))))
        if not domain:
            continue
        card = (item.get("trace") or {}).get("source_card")
        if not isinstance(card, dict):
            card = source_card_for_domain(domain, preferred_scope=item.get("matched_scope") or None).to_dict()
        cards.append(card)
    source_mix = _source_mix(results)
    role_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for card in cards:
        for role in card.get("content_roles") or []:
            role_counts[str(role)] = role_counts.get(str(role), 0) + 1
        for risk in card.get("risk_tags") or []:
            risk_counts[str(risk)] = risk_counts.get(str(risk), 0) + 1
    count = max(len(cards), 1)
    authority_avg = round(sum(float(card.get("authority_score") or 0) for card in cards) / count, 3)
    sample_avg = round(sum(float(card.get("sample_value") or 0) for card in cards) / count, 3)
    freshness_avg = round(sum(float(card.get("freshness_value") or 0) for card in cards) / count, 3)
    domains = {str(item.get("domain") or _domain(str(item.get("url", "")))) for item in results if item.get("url")}
    warnings: list[str] = []
    intents = set(route_plan.get("primary_intents") or []) | set(route_plan.get("secondary_intents") or [])
    if len(source_mix) <= 1 and len(results) >= 4:
        warnings.append("信源类型过于集中，容易把单一圈层误写成整体情况。")
    if len(domains) <= 2 and len(results) >= 5:
        warnings.append("域名集中度偏高，需警惕同源转载或单站偏差。")
    if {"policy", "official_position"} & intents and authority_avg < 0.45:
        warnings.append("政策/官方问题的一手权威来源偏少，应补 gov 或 party_central。")
    if {"reputation", "purchase_advice"} & intents and sample_avg < 0.45:
        warnings.append("口碑/购买问题的用户样本偏少，应补知乎、微博、小红书、B站等公开页。")
    if ("hot_trend" in intents or (route_plan.get("freshness") or "")) and freshness_avg < 0.45:
        warnings.append("近期/热点问题的新鲜度不足，应缩短时间窗口或使用 hotnews。")
    return {
        "result_count": len(results),
        "source_type_count": len(source_mix),
        "domain_count": len(domains),
        "authority_avg": authority_avg,
        "sample_avg": sample_avg,
        "freshness_avg": freshness_avg,
        "source_mix": source_mix,
        "role_counts": dict(sorted(role_counts.items(), key=lambda row: (-row[1], row[0]))),
        "risk_counts": dict(sorted(risk_counts.items(), key=lambda row: (-row[1], row[0]))),
        "warnings": warnings,
    }


def format_source_diagnostics_markdown(diagnostics: dict[str, Any]) -> str:
    """Render source diagnostics as a compact evidence compass."""
    lines = ["## 信源诊断"]
    lines.append(
        "- 权威/样本/新鲜度: "
        f"{diagnostics.get('authority_avg', 0)}/"
        f"{diagnostics.get('sample_avg', 0)}/"
        f"{diagnostics.get('freshness_avg', 0)}"
    )
    lines.append(
        "- 多样性: "
        f"source_type={diagnostics.get('source_type_count', 0)} "
        f"domain={diagnostics.get('domain_count', 0)}"
    )
    roles = diagnostics.get("role_counts") or {}
    if roles:
        lines.append("- 证据角色: " + "；".join(f"{key}: {value}" for key, value in list(roles.items())[:6]))
    risks = diagnostics.get("risk_counts") or {}
    if risks:
        lines.append("- 风险标签: " + "；".join(f"{key}: {value}" for key, value in list(risks.items())[:6]))
    for warning in diagnostics.get("warnings") or []:
        lines.append(f"- 边界: {warning}")
    return "\n".join(lines)


def source_distribution(results: list[dict[str, Any]], field: str = "source_type") -> list[dict[str, Any]]:
    """Return count/percent rows for source diagnostics."""
    counts: dict[str, int] = {}
    for item in results:
        if field == "domain":
            key = str(item.get("domain") or _domain(str(item.get("url", ""))) or "unknown")
        elif field == "source":
            key = str(item.get("source") or "search")
        else:
            key = str(item.get("source_type") or "通用网页")
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values())
    rows = []
    for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        rows.append(
            {
                "label": label,
                "count": count,
                "percent": (count / total * 100) if total else 0.0,
            }
        )
    return rows


def format_source_chart(
    results: list[dict[str, Any]],
    title: str = "来源分布",
    width: int = 24,
) -> str:
    """Render an ASCII source distribution chart for CLI diagnostics."""
    lines = ["", f"## {title}"]
    if not results:
        lines.append("- 暂无可统计结果。")
        return "\n".join(lines)

    sections = [
        ("信源类型", source_distribution(results, "source_type")),
        ("域名/平台", source_distribution(results, "domain")),
    ]
    for section_title, rows in sections:
        lines.extend(["", f"### {section_title}"])
        lines.extend(_format_chart_rows(rows, width=width))
    return "\n".join(lines)


def _format_chart_rows(rows: list[dict[str, Any]], width: int = 24) -> list[str]:
    if not rows:
        return ["- 暂无数据。"]
    max_count = max(int(row.get("count", 0)) for row in rows) or 1
    max_label = max(len(str(row.get("label", ""))) for row in rows)
    lines = []
    for row in rows:
        label = str(row.get("label", "unknown"))
        count = int(row.get("count", 0))
        percent = float(row.get("percent", 0.0))
        bar_len = max(1, round(count / max_count * width)) if count else 0
        bar = "#" * bar_len
        lines.append(f"- {label.ljust(max_label)} {bar.ljust(width)} {percent:5.1f}% ({count})")
    return lines


def format_search_markdown(results: list[dict[str, Any]], title: str = "观澜搜索") -> str:
    """Render search results as compact Markdown for agent context."""
    lines = [f"# {title}", ""]
    if not results:
        lines.append("暂无搜索结果。")
        return "\n".join(lines)

    for idx, item in enumerate(results, start=1):
        rank = item.get("rank") or idx
        item_title = _collapse_ws(str(item.get("title", "")))
        url = str(item.get("url", "")).strip()
        snippet = _collapse_ws(str(item.get("snippet", "")))
        source = str(item.get("source", "search")).strip()
        source_type = str(item.get("source_type", "通用网页")).strip()
        score = item.get("score", 0)
        score_label = f" score={score:.2f}" if isinstance(score, (int, float)) and score else ""
        topic_size = item.get("topic_size", 1)
        topic_role = str(item.get("topic_role", "single"))
        topic_label = ""
        if isinstance(topic_size, int) and topic_size > 1:
            topic_label = f" topic={topic_role}/{topic_size}"
        evidence_role = str(item.get("evidence_role", "")).strip()
        role_label = f" role={evidence_role}" if evidence_role else ""
        lines.append(f"{rank}. [{source}/{source_type}{score_label}{topic_label}{role_label}] {item_title}")
        if url:
            lines.append(f"   {url}")
        if snippet:
            lines.append(f"   {snippet[:240]}")
    return "\n".join(lines)


def format_search_context(results: list[dict[str, Any]], title: str = "观澜搜索上下文") -> str:
    """Render compact LLM-friendly search context."""
    lines = [f"# {title}", "", "来源 | 标题 | 摘要 | 可信度 | Topic", "--- | --- | --- | --- | ---"]
    if not results:
        lines.append("无结果 | - | - | - | -")
        return "\n".join(lines)
    for idx, item in enumerate(results, start=1):
        evidence_role = str(item.get("evidence_role") or "")
        source_label = str(item.get("source_type") or item.get("source") or "web")
        if evidence_role:
            source_label = f"{source_label}/{evidence_role}"
        source = _pipe_safe(source_label)
        title_text = _pipe_safe(_collapse_ws(str(item.get("title", ""))))
        snippet = _pipe_safe(_collapse_ws(str(item.get("snippet", "")))[:140])
        score = item.get("score", 0)
        score_text = f"{score:.2f}" if isinstance(score, (int, float)) else str(score or "")
        topic = str(item.get("topic_key") or f"result-{idx}")
        role = str(item.get("topic_role") or "single")
        url = str(item.get("url") or "")
        lines.append(f"{source} | [{title_text}]({url}) | {snippet} | {score_text} | {topic}/{role}")
    return "\n".join(lines)


def format_search_trace(results: list[dict[str, Any]]) -> str:
    """Render score and routing trace for search results."""
    lines = ["", "## 搜索 Trace"]
    if not results:
        lines.append("- 无结果。")
        return "\n".join(lines)
    query_quality = (results[0].get("trace") or {}).get("query_quality") or {}
    quality_summary = (results[0].get("trace") or {}).get("quality_summary") or {}
    route_plan = (results[0].get("trace") or {}).get("route_plan") or {}
    query_strategy = (results[0].get("trace") or {}).get("query_strategy") or {}
    backend_diagnostics = (results[0].get("trace") or {}).get("backend_diagnostics") or []
    backend_summary = (results[0].get("trace") or {}).get("backend_summary") or {}
    backend_recovery = (results[0].get("trace") or {}).get("backend_recovery") or {}
    if backend_diagnostics:
        parts = []
        for item in backend_diagnostics:
            backend_name = item.get("backend", "")
            status = item.get("status", "")
            count = item.get("result_count", 0)
            if status == "ok":
                parts.append(f"{backend_name}=ok({count})")
            elif status == "parser_miss":
                parts.append(f"{backend_name}=parser_miss")
            elif status == "no_results_or_parser_miss":
                parts.append(f"{backend_name}=no_results_or_parser_miss")
            elif status == "no_results":
                parts.append(f"{backend_name}=no_results")
            elif status == "blocked":
                parts.append(f"{backend_name}=blocked")
            elif status == "error":
                parts.append(f"{backend_name}=error")
            elif status == "skipped":
                parts.append(f"{backend_name}=skipped")
            else:
                parts.append(f"{backend_name}={status or 'unknown'}")
        lines.append("- backend_status: " + ", ".join(parts))
        if backend_summary.get("fallback_used"):
            lines.append("  backend_warning: 前置后端未产出有效结果，当前结果依赖后续后端兜底。")
        for item in backend_diagnostics:
            note = str(item.get("note") or "")
            if note and item.get("status") in {"parser_miss", "no_results", "no_results_or_parser_miss", "blocked", "error"}:
                lines.append(f"  backend_note:{item.get('backend')} => {note}")
    if backend_recovery and backend_recovery.get("status") != "ok":
        active = ",".join(backend_recovery.get("active_backends") or []) or "none"
        lines.append(
            "- backend_recovery: "
            f"status={backend_recovery.get('status', 'unknown')} "
            f"auto_downgrade={backend_recovery.get('auto_downgrade', False)} "
            f"active={active}"
        )
        for item in backend_recovery.get("guidance") or []:
            lines.append(f"  recovery: {item}")
        for command in backend_recovery.get("followup_commands") or []:
            lines.append(f"  followup: `{command}`")
    if route_plan:
        lines.append(
            "- route_plan: "
            f"intents={','.join(route_plan.get('primary_intents') or []) or 'general'} "
            f"scopes={','.join(route_plan.get('preferred_scopes') or []) or 'open'} "
            f"sites={','.join(route_plan.get('target_sites') or []) or 'none'} "
            f"risk={route_plan.get('risk_level', 'low')}"
        )
        for warning in route_plan.get("warnings", [])[:3]:
            lines.append(f"  route_warning: {warning}")
    if query_strategy:
        variants = query_strategy.get("variants") or []
        lines.append(
            "- query_strategy: "
            f"intent={query_strategy.get('intent', 'general')} "
            f"variants={len(variants)}"
        )
        for item in variants[:4]:
            lines.append(f"  variant:{item.get('role')} => {item.get('query')}")
    if query_quality:
        preferred = ",".join(query_quality.get("preferred_source_types") or []) or "none"
        lines.append(
            "- query_quality: "
            f"intent={query_quality.get('intent', 'general')} "
            f"preferred={preferred} "
            f"hits={quality_summary.get('preferred_hit_count', 0)}/{quality_summary.get('result_count', 0)}"
        )
        for warning in quality_summary.get("warnings", []):
            lines.append(f"  warning: {warning}")
        for suggestion in quality_summary.get("suggestions", []):
            lines.append(f"  suggestion: {suggestion}")
    for idx, item in enumerate(results, start=1):
        title = _collapse_ws(str(item.get("title", "")))
        parts = item.get("score_parts") or {}
        trace = item.get("trace") or {}
        recency = trace.get("recency") or {}
        quality = trace.get("quality") or {}
        part_text = ", ".join(
            f"{key}={value}" for key, value in parts.items() if key != "total"
        )
        recency_text = ""
        if recency.get("enabled"):
            result_date = recency.get("result_date") or "unknown"
            age_days = recency.get("age_days")
            in_window = recency.get("in_window")
            recency_text = (
                f"; recency={recency.get('window_days')}d "
                f"date={result_date} age={age_days} in_window={in_window}"
            )
        quality_text = ""
        if quality:
            quality_text = (
                f"; quality_fit={quality.get('fit')} "
                f"matched={quality.get('matched_reason', '')}"
            )
        lines.append(
            f"- result {idx}: score={item.get('score', 0)} ({part_text}); "
            f"topic={item.get('topic_key', '')}/{item.get('topic_role', '')}; "
            f"cache={trace.get('cache', 'disabled')}{recency_text}{quality_text}; title={title}"
        )
    return "\n".join(lines)


def format_read_batch_markdown(records: list[dict[str, Any]]) -> str:
    """Render batch read records as Markdown."""
    lines = ["# 观澜批量阅读", ""]
    if not records:
        lines.append("暂无 URL。")
        return "\n".join(lines)
    for item in records:
        status = str(item.get("status", ""))
        url = str(item.get("url", ""))
        lines.extend(["", f"## [{status}] {item.get('rank', '')}. {url}"])
        if item.get("error"):
            lines.append(f"读取错误: {item['error']}")
        content = str(item.get("content", "")).strip()
        if content:
            lines.extend(["", content])
    return "\n".join(lines)


def format_read_batch_context(records: list[dict[str, Any]]) -> str:
    """Render batch read records as compact prompt context."""
    lines = ["# 观澜批量阅读上下文", ""]
    for item in records:
        url = str(item.get("url", ""))
        status = str(item.get("status", ""))
        content = _collapse_ws(str(item.get("content") or item.get("error") or ""))
        lines.append(f"[{item.get('rank', '')}] {status} | {url} | {content[:500]}")
    return "\n".join(lines)


def _pipe_safe(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def detect_search_quality_profile(
    query: str,
    scope: str | None = None,
    site: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Detect source-quality preferences for a search query.

    This is intentionally advisory: it changes ranking weights and trace output,
    but it does not silently narrow the query to a scope unless the caller asked
    for one.
    """
    text = _collapse_ws(query).lower()
    reasons: list[str] = []
    intent = "general"
    matched_terms: list[str] = []

    explicit_scope = (scope or "").strip()
    if explicit_scope:
        try:
            from guanlan.search_sources import resolve_scope

            resolved = resolve_scope(explicit_scope)
            return {
                "intent": f"scope:{resolved.id}",
                "name": f"显式 scope / {resolved.name}",
                "matched_terms": [],
                "preferred_scopes": [resolved.id],
                "preferred_source_types": [resolved.source_type],
                "caution_source_types": [],
                "profile": profile or "",
                "site": site or "",
                "requested_scope": resolved.id,
                "guidance": "用户已指定 scope，优先尊重该信源池。",
                "reasons": [f"requested_scope:{resolved.id}"],
            }
        except Exception:
            reasons.append(f"unknown_scope:{explicit_scope}")

    for candidate, data in _QUALITY_INTENT_PROFILES.items():
        terms = [term for term in data["terms"] if _quality_term_matches(text, str(term))]
        if terms:
            intent = candidate
            matched_terms = terms
            reasons.append(f"matched_terms:{','.join(terms[:4])}")
            break

    data = _QUALITY_INTENT_PROFILES.get(intent, {})
    preferred_scopes = list(data.get("preferred_scopes", []))
    preferred_source_types = list(data.get("preferred_source_types", []))
    if profile == "china" and intent == "general":
        reasons.append("profile:china")
    if profile == "english" and intent == "general":
        reasons.append("profile:english")
    if site:
        reasons.append(f"site:{site}")

    return {
        "intent": intent,
        "name": data.get("name", "通用网页研究"),
        "matched_terms": matched_terms,
        "preferred_scopes": preferred_scopes,
        "preferred_source_types": preferred_source_types,
        "caution_source_types": list(data.get("caution_source_types", [])),
        "profile": profile or "",
        "site": site or "",
        "requested_scope": explicit_scope,
        "guidance": data.get("guidance", "先看来源类型、topic 和时效性，再决定是否扩大搜索。"),
        "reasons": reasons,
    }


def _quality_with_route_plan(
    quality: dict[str, Any],
    route_plan: dict[str, Any],
    explicit_scope: str | None = None,
    site: str | None = None,
) -> dict[str, Any]:
    """Softly enrich quality preferences from the route plan."""
    enriched = dict(quality or {})
    preferred_scopes = list(enriched.get("preferred_scopes") or [])
    preferred_types = list(enriched.get("preferred_source_types") or [])
    if not explicit_scope and not site:
        for scope_id in route_plan.get("preferred_scopes") or []:
            if scope_id not in preferred_scopes:
                preferred_scopes.append(scope_id)
        try:
            from guanlan.search_sources import resolve_scope

            for scope_id in preferred_scopes:
                source_type = resolve_scope(scope_id).source_type
                if source_type not in preferred_types:
                    preferred_types.append(source_type)
        except Exception:
            pass
    enriched["preferred_scopes"] = preferred_scopes
    enriched["preferred_source_types"] = preferred_types
    enriched["route_intents"] = list(route_plan.get("primary_intents") or [])
    enriched["route_evidence_roles"] = list(route_plan.get("evidence_roles") or [])
    enriched["route_warnings"] = list(route_plan.get("warnings") or [])
    if enriched.get("intent") == "general" and route_plan.get("primary_intents"):
        enriched["intent"] = "+".join(route_plan.get("primary_intents") or ["general"])
        enriched["name"] = "路由识别 / " + enriched["intent"]
    enriched.setdefault("reasons", [])
    enriched["reasons"] = list(enriched.get("reasons") or []) + [
        f"route:{intent}" for intent in route_plan.get("primary_intents") or [] if intent != "general"
    ]
    return enriched


def search_quality_summary(
    results: list[dict[str, Any]],
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize whether a result set matches the query quality profile."""
    quality = quality or {}
    preferred_types = set(quality.get("preferred_source_types") or [])
    preferred_scopes = set(quality.get("preferred_scopes") or [])
    source_mix = _source_mix(results)
    preferred_hits = [
        item
        for item in results
        if item.get("source_type") in preferred_types or item.get("matched_scope") in preferred_scopes
    ]
    domains = {
        str(item.get("domain") or _domain(str(item.get("url", ""))))
        for item in results
        if item.get("url")
    }
    warnings: list[str] = []
    suggestions: list[str] = []
    if preferred_types and not preferred_hits:
        warnings.append("未命中当前意图偏好的信源类型，建议补充 scope 或站点定向搜索。")
        suggestions.append(_source_gap_suggestion(quality, preferred_types, preferred_scopes))
    if len(source_mix) <= 1 and len(results) >= 4:
        warnings.append("来源类型较单一，可能需要扩大信源面。")
        suggestions.append("补充开放网页或相邻 scope，避免只看单一信源类型。")
    if len(domains) <= 1 and len(results) >= 3:
        warnings.append("域名集中度较高，注意同源转载或单站偏差。")
        suggestions.append("补充 2-3 个不同域名结果，尤其是原文、权威报道和社区样本的交叉来源。")
    role_counts: dict[str, int] = {}
    for item in results:
        role = str(item.get("evidence_role") or "")
        if role:
            role_counts[role] = role_counts.get(role, 0) + 1
    route_roles = [str(role) for role in quality.get("route_evidence_roles") or [] if str(role)]
    missing_roles = [role for role in route_roles if role not in role_counts]
    for role in missing_roles[:3]:
        suggestions.append(_role_gap_suggestion(role))

    return {
        "intent": quality.get("intent", "general"),
        "preferred_hit_count": len(preferred_hits),
        "result_count": len(results),
        "source_type_count": len(source_mix),
        "domain_count": len(domains),
        "source_mix": source_mix,
        "role_counts": dict(sorted(role_counts.items(), key=lambda row: (-row[1], row[0]))),
        "missing_roles": missing_roles,
        "warnings": warnings,
        "suggestions": _unique_keep_order([item for item in suggestions if item]),
    }


def _source_gap_suggestion(
    quality: dict[str, Any],
    preferred_types: set[str],
    preferred_scopes: set[str],
) -> str:
    if preferred_scopes:
        scope_hint = ",".join(sorted(preferred_scopes))
        return f"建议补搜 `--scope {scope_hint.split(',')[0]}` 或指定相关官方/垂类站点。"
    if preferred_types:
        return "建议补充 " + "、".join(sorted(preferred_types)[:3]) + " 类型信源。"
    intent = str(quality.get("intent") or "general")
    return f"建议根据 {intent} 意图补充更贴近问题的第一手信源。"


def _role_gap_suggestion(role: str) -> str:
    mapping = {
        "official_primary": "缺少官方原文/主管部门口径，建议补搜 `--scope gov`、`--scope party_central` 或 `--scope global_official`。",
        "authoritative_report": "缺少权威报道，建议补搜党央媒或核心地方官媒。",
        "user_sample": "缺少公开用户样本，建议补搜知乎、微博、小红书、B站等公开页，并标明样本偏差。",
        "industry_report": "缺少产业/垂类材料，建议补搜商业媒体、电商垂类或行业报告。",
        "fresh_news": "缺少近期材料，建议加入最近/今日/本周等时效词并开启 trace 核对时间线。",
        "developer_discussion": "缺少开发者实践反馈，建议补搜 GitHub、V2EX、掘金或技术社区。",
        "company_primary": "缺少公司一手资料，建议补搜 `--scope company_primary` 或官方文档/价格/发布说明。",
        "technical_primary": "缺少技术一手资料，建议补搜 `--scope developer`、官方文档、GitHub release 或 issue。",
        "review": "缺少评价样本，建议补搜 Reddit、Hacker News、G2、Trustpilot 等公开样本并说明偏差。",
        "standard_original": "缺少标准原文/标准组织材料，建议补搜 `--scope global_official` 或指定 ISO/IEC/NIST 等站点。",
        "regulator_guidance": "缺少监管解释或主管机构材料，建议补搜 `--scope gov` 或 `--scope global_official`。",
        "clinical_guideline": "缺少临床指南/专业机构材料，建议补搜 WHO、CDC、FDA、卫健委或学术数据库。",
        "statute_original": "缺少法律条文原文，建议补搜 `--scope gov` 或指定人大、法院、司法部等站点。",
        "case_record": "缺少案例/裁判文书材料，建议补搜法院、裁判文书或权威法律数据库。",
    }
    return mapping.get(role, f"缺少 `{role}` 角色证据，建议补充对应信源后再下判断。")


def _quality_term_matches(text: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9_+-]+", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", text, flags=re.I))
    return term.lower() in text


def detect_recency_intent(query: str) -> dict[str, Any]:
    """Detect whether a query needs tighter time bounds."""
    text = _collapse_ws(query).lower()
    today = dt.date.today()
    matched_terms: list[str] = []
    window_days = 0
    label = ""

    explicit_windows: tuple[tuple[str, int, tuple[str, ...]], ...] = (
        ("today", 1, ("今天", "今日", "当天", "当日", "刚刚", "实时", "24小时", "近24小时", "now", "today")),
        ("yesterday", 2, ("昨天", "昨日", "48小时", "近48小时")),
        ("week", 7, ("近一周", "最近一周", "过去一周", "一周内", "本周", "这周", "7天", "7日", "七天")),
        (
            "month",
            30,
            ("近一个月", "最近一个月", "过去一个月", "一个月内", "本月", "这个月", "30天", "30日", "三十天"),
        ),
        ("quarter", 90, ("近三个月", "最近三个月", "过去三个月", "一个季度", "本季度", "90天", "90日")),
    )
    for candidate_label, days, terms in explicit_windows:
        found = [term for term in terms if _recency_term_matches(text, term)]
        if found:
            label = candidate_label
            window_days = days
            matched_terms.extend(found)
            break

    if not window_days and _recency_term_matches(text, "今年"):
        label = "year_to_date"
        year_start = dt.date(today.year, 1, 1)
        window_days = max((today - year_start).days + 1, 1)
        matched_terms.append("今年")

    if not window_days:
        hot_terms = ("热点", "热搜", "快讯", "突发", "爆发", "热议", "刷屏")
        found_hot = [term for term in hot_terms if _recency_term_matches(text, term)]
        if found_hot:
            label = "hot"
            window_days = 7
            matched_terms.extend(found_hot)

    if not window_days:
        recent_terms = (
            "近期",
            "最近",
            "最新",
            "新近",
            "动态",
            "进展",
            "趋势",
            "舆情",
            "新闻",
            "报道",
            "current",
            "recent",
            "latest",
            "news",
        )
        found_recent = [term for term in recent_terms if _recency_term_matches(text, term)]
        if found_recent:
            label = "recent"
            window_days = _RECENCY_DEFAULT_WINDOW_DAYS
            matched_terms.extend(found_recent)

    if not window_days:
        return {
            "enabled": False,
            "label": "",
            "window_days": 0,
            "start_date": "",
            "end_date": today.isoformat(),
            "matched_terms": [],
        }

    start = today - dt.timedelta(days=max(window_days - 1, 0))
    return {
        "enabled": True,
        "label": label,
        "window_days": window_days,
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "matched_terms": matched_terms,
    }


def build_query_strategy(
    query: str,
    *,
    route_plan: dict[str, Any] | None = None,
    recency: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build query rewrites that preserve source roles instead of one flat query."""
    clean_query = _collapse_ws(query)
    route_plan = route_plan or build_route_plan(clean_query).to_dict()
    recency = recency or detect_recency_intent(clean_query)
    quality = quality or {}
    intents = list(route_plan.get("primary_intents") or []) + list(route_plan.get("secondary_intents") or [])
    roles = list(route_plan.get("evidence_roles") or [])
    variants: list[dict[str, str]] = []

    def add(role: str, q: str, reason: str) -> None:
        normalized = _collapse_ws(q)
        if not normalized:
            return
        if any(item["query"] == normalized for item in variants):
            return
        variants.append({"role": role, "query": normalized, "reason": reason})

    add("base", clean_query, "用户原始问题，保留语义中心")
    if {"policy", "official_position", "local"} & set(intents):
        add("official_primary", f"{clean_query} 官方 原文 通知", "政策/官方问题先找一手口径")
        add("authoritative_report", f"{clean_query} 人民日报 新华社 央视", "补党央媒与权威报道")
    if "global_policy" in intents:
        add("official_primary", f"{clean_query} official regulation standard primary source", "英文政策/监管问题先找官方或标准组织原文")
        add("authoritative_report", f"{clean_query} Reuters AP BBC analysis timeline", "补主流新闻时间线和背景")
    if "company_primary" in intents:
        add("company_primary", f"{clean_query} official docs pricing release notes", "公司/产品问题优先找一手资料")
        add("technical_primary", f"{clean_query} github changelog status documentation", "补开发者文档、release 和状态页")
    if {"reputation", "purchase_advice"} & set(intents):
        add("user_sample", f"{clean_query} 用户评价 吐槽 体验", "口碑问题先找用户样本语言")
        add("review", f"{clean_query} 测评 优缺点 值不值得买", "补评测和购买决策材料")
    if "global_reputation" in intents:
        add("user_sample", f"{clean_query} reddit hacker news user review complaints", "英文口碑问题先找公开社区样本")
        add("review", f"{clean_query} G2 Trustpilot Capterra review", "补评价站点样本并标注偏差")
    if {"industry", "ecommerce", "finance"} & set(intents):
        add("industry_report", f"{clean_query} 行业 趋势 公司 案例", "产业/商业问题补行业材料")
    if "global_industry" in intents:
        add("industry_report", f"{clean_query} market analysis competitive landscape analyst report", "英文产业问题补分析和市场结构材料")
        add("company_context", f"{clean_query} investor relations annual report official", "补公司一手资料和投资者关系材料")
    if "tech" in intents:
        add("developer_discussion", f"{clean_query} github issue benchmark 开源", "技术问题补开发者与可复现线索")
    if "academic" in intents:
        add("database_official", f"{clean_query} Compendex Engineering Village Elsevier official", "学术检索问题先找数据库/出版商口径")
        add("publisher_guideline", f"{clean_query} CFP author guidelines proceedings", "补会议 CFP、作者指南和论文集要求")
        add("institution_policy", f"{clean_query} 学校 研究生院 认定 要求", "补国内高校或单位认定口径")
    if "standards_compliance" in intents:
        add("standard_original", f"{clean_query} official standard regulator guidance", "标准/合规问题先找标准组织或监管原文")
        add("implementation_context", f"{clean_query} implementation checklist audit requirement", "补实施和审计语境，但不替代原文")
    if "medical_health" in intents:
        add("clinical_guideline", f"{clean_query} clinical guideline regulator official", "医疗健康问题先找指南、监管和专业机构")
        add("peer_review", f"{clean_query} systematic review clinical evidence", "补同行评议或综述证据")
    if "legal_judicial" in intents:
        add("statute_original", f"{clean_query} 法律 条文 司法解释 官方", "法律问题先找条文和司法解释")
        add("case_record", f"{clean_query} 裁判文书 案例 法院", "补裁判文书或案例材料")
    if recency.get("enabled") or "hot_trend" in intents:
        add("fresh_news", _apply_recency_query(f"{clean_query} 最新 进展", recency), "近期/热点问题收束时间窗口")
        if {"policy", "official_position", "local", "company_primary"} & set(intents):
            add("fresh_primary", _apply_recency_query(f"{clean_query} 官方 发布 时间", recency), "近期问题优先补一手发布时间线索")
        if {"reputation", "purchase_advice"} & set(intents):
            add("fresh_user_sample", _apply_recency_query(f"{clean_query} 最新 用户 反馈", recency), "近期口碑需要补新鲜用户样本")
    if roles and len(variants) == 1:
        add(str(roles[0]), f"{clean_query} 依据 来源", "按路由证据角色补充查询")

    time_window = _query_strategy_time_window(recency)
    return {
        "primary_query": variants[0]["query"] if variants else clean_query,
        "recency": recency,
        "time_window": time_window,
        "intent": quality.get("intent") or (intents[0] if intents else "general"),
        "roles": roles,
        "variants": variants[:8],
        "search_quality_v2": {
            "prefer_broad_pool": True,
            "minimum_recommended_limit": DEFAULT_RESEARCH_LIMIT,
            "recency_bounded": bool(recency.get("enabled")),
            "source_role_queries": len(variants),
        },
        "agent_hint": "不要只用一个宽泛 query；按证据角色分别搜索，再合并去重和标注边界；涉及近期/热点时必须保留时间窗口。",
    }


def _query_strategy_time_window(recency: dict[str, Any]) -> dict[str, Any]:
    if not recency.get("enabled"):
        return {"enabled": False}
    return {
        "enabled": True,
        "label": recency.get("label") or "recent",
        "window_days": recency.get("window_days"),
        "start_date": recency.get("start_date"),
        "end_date": recency.get("end_date"),
        "matched_terms": list(recency.get("matched_terms") or []),
        "instruction": "近期/热点查询应优先使用窗口内结果；窗口外材料只作背景，不应写成最新。",
    }


def _apply_recency_query(query: str, recency: dict[str, Any]) -> str:
    if not recency.get("enabled"):
        return query
    if _query_already_has_absolute_date(query):
        return query
    today = _recency_today(recency)
    window_days = int(recency.get("window_days") or 0)
    suffix = f"{today.year}年{today.month}月 最新"
    if window_days <= 1:
        suffix = f"{today.year}年{today.month}月{today.day}日 最新"
    elif window_days <= 7:
        suffix = f"{today.year}年{today.month}月 近{window_days}天 最新"
    elif recency.get("label") == "year_to_date":
        suffix = f"{today.year}年 最新"
    if suffix in query:
        return query
    return f"{query} {suffix}".strip()


def _query_already_has_absolute_date(query: str) -> bool:
    return bool(
        re.search(r"(?:19|20)\d{2}", query)
        or re.search(r"\d{1,2}\s*月\s*\d{1,2}\s*日", query)
        or re.search(r"\d{4}\s*[-/.]\s*\d{1,2}", query)
    )


def _recency_term_matches(text: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9]+", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", text, flags=re.I))
    return term in text


def _recency_today(recency: dict[str, Any] | None = None) -> dt.date:
    if recency:
        try:
            end_date = str(recency.get("end_date") or "")
            if end_date:
                return dt.date.fromisoformat(end_date)
        except ValueError:
            pass
    return dt.date.today()


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: dict[str, SearchResult] = {}
    deduped: list[SearchResult] = []
    for item in results:
        key = _canonical_url(item.url)
        if not key:
            continue
        if key in seen:
            existing = seen[key]
            if len(item.snippet) > len(existing.snippet):
                existing.snippet = item.snippet
            if item.source not in existing.source.split("+"):
                existing.source = existing.source + "+" + item.source
            continue
        seen[key] = item
        item.rank = len(deduped) + 1
        deduped.append(item)
    return deduped


def _result_recency_trace(item: SearchResult, recency: dict[str, Any] | None = None) -> dict[str, Any]:
    metrics = _result_recency_metrics(item, recency)
    if not metrics["enabled"]:
        return {"enabled": False}
    result_date = metrics.get("result_date")
    return {
        "enabled": True,
        "window_days": metrics["window_days"],
        "start_date": metrics["start_date"],
        "end_date": metrics["end_date"],
        "matched_terms": metrics["matched_terms"],
        "result_date": result_date.isoformat() if isinstance(result_date, dt.date) else "",
        "age_days": metrics.get("age_days"),
        "in_window": metrics["in_window"],
    }


def _result_quality_trace(item: SearchResult, quality: dict[str, Any] | None = None) -> dict[str, Any]:
    quality = quality or {}
    preferred_types = set(quality.get("preferred_source_types") or [])
    preferred_scopes = set(quality.get("preferred_scopes") or [])
    matched_reason = ""
    if item.matched_scope and item.matched_scope in preferred_scopes:
        matched_reason = f"scope:{item.matched_scope}"
    elif item.source_type and item.source_type in preferred_types:
        matched_reason = f"source_type:{item.source_type}"
    elif quality.get("requested_scope") and item.matched_scope == quality.get("requested_scope"):
        matched_reason = f"requested_scope:{item.matched_scope}"
    return {
        "intent": quality.get("intent", "general"),
        "name": quality.get("name", ""),
        "fit": bool(matched_reason),
        "matched_reason": matched_reason,
        "preferred_scopes": list(preferred_scopes),
        "preferred_source_types": list(preferred_types),
        "guidance": quality.get("guidance", ""),
    }


def _infer_evidence_role(
    item: SearchResult,
    source_card: dict[str, Any],
    quality: dict[str, Any] | None = None,
) -> str:
    """Map source taxonomy roles to one compact role for downstream agents."""
    roles = {str(role) for role in source_card.get("content_roles") or []}
    fit_tags = {str(tag) for tag in source_card.get("fit_tags") or []}
    scope = str(item.matched_scope or source_card.get("scope_id") or "")
    source_type = str(item.source_type or "")
    title_blob = f"{item.title} {item.snippet}".lower()
    route_roles = {str(role) for role in (quality or {}).get("route_evidence_roles") or []}
    if scope in {"gov", "global_official"} or "primary_source" in roles or "regulation" in roles or "notice" in roles:
        return "official_primary"
    if scope in {"party_central", "local_official"} or "authoritative_report" in roles:
        return "authoritative_report"
    if scope == "company_primary" or roles & {"official_specs", "pricing", "company_statement"}:
        return "company_primary"
    if "source_code" in roles or "release" in roles or "documentation" in roles:
        return "technical_primary"
    if roles & {"practice", "discussion", "technical_note", "issue", "developer_discussion"}:
        return "developer_discussion"
    if roles & {"user_sample", "public_discussion", "consumer_note", "social_post", "question_answer"}:
        return "user_sample"
    if roles & {"vertical_report", "report", "analysis", "case", "market_news", "filing_context", "market_context"}:
        return "market_context" if "finance" in fit_tags else "industry_report"
    if "fresh_news" in route_roles or re.search(r"最新|今日|今天|刚刚|发布|快讯|热榜|热点", title_blob):
        return "fresh_news"
    if "政府" in source_type:
        return "official_primary"
    if "党央媒" in source_type or "地方官媒" in source_type:
        return "authoritative_report"
    if "社交" in source_type:
        return "user_sample"
    if "英文社区" in source_type or "评价/消费" in source_type:
        return "user_sample"
    if "公司一手" in source_type:
        return "company_primary"
    return "open_web_context"


def _result_recency_metrics(item: SearchResult, recency: dict[str, Any] | None = None) -> dict[str, Any]:
    recency = recency or {}
    enabled = bool(recency.get("enabled"))
    today = _recency_today(recency)
    window_days = int(recency.get("window_days") or 0)
    start_date = str(recency.get("start_date") or "")
    result_date = _extract_result_date(item, today=today) if enabled else None
    age_days = (today - result_date).days if result_date else None
    return {
        "enabled": enabled,
        "window_days": window_days,
        "start_date": start_date,
        "end_date": today.isoformat(),
        "matched_terms": list(recency.get("matched_terms") or []),
        "result_date": result_date,
        "age_days": age_days,
        "in_window": bool(result_date and age_days is not None and age_days <= max(window_days, 0)),
        "has_freshness_words": _has_freshness_words(item),
    }


def _extract_result_date(item: SearchResult, today: dt.date | None = None) -> dt.date | None:
    today = today or dt.date.today()
    text = _collapse_ws(f"{item.title} {item.snippet}")
    if not text:
        return None

    relative = _extract_relative_result_date(text, today)
    if relative:
        return relative

    patterns = (
        r"((?:19|20)\d{2})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})\s*日?",
        r"((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3)) if len(match.groups()) >= 3 and match.group(3) else 1
        parsed = _safe_date(year, month, day)
        if parsed:
            return parsed

    match = re.search(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if match:
        parsed = _safe_date(today.year, int(match.group(1)), int(match.group(2)))
        if parsed and parsed > today + dt.timedelta(days=7):
            parsed = _safe_date(today.year - 1, int(match.group(1)), int(match.group(2)))
        return parsed

    return None


def _extract_relative_result_date(text: str, today: dt.date) -> dt.date | None:
    if any(marker in text for marker in ("刚刚", "今天", "今日", "分钟前", "小时前")):
        return today
    if "昨天" in text:
        return today - dt.timedelta(days=1)
    if "前天" in text:
        return today - dt.timedelta(days=2)

    day_match = re.search(r"(\d+)\s*(?:天|日)\s*前", text)
    if day_match:
        return today - dt.timedelta(days=int(day_match.group(1)))
    week_match = re.search(r"(\d+)\s*(?:周|星期|礼拜)\s*前", text)
    if week_match:
        return today - dt.timedelta(days=int(week_match.group(1)) * 7)
    month_match = re.search(r"(\d+)\s*(?:个)?月\s*前", text)
    if month_match:
        return today - dt.timedelta(days=int(month_match.group(1)) * 30)
    year_match = re.search(r"(\d+)\s*年\s*前", text)
    if year_match:
        return today - dt.timedelta(days=int(year_match.group(1)) * 365)
    return None


def _safe_date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _has_freshness_words(item: SearchResult) -> bool:
    text = f"{item.title} {item.snippet}".lower()
    markers = (
        "今天",
        "今日",
        "刚刚",
        "最新",
        "热点",
        "热搜",
        "快讯",
        "突发",
        "实时",
        "进展",
        "latest",
        "breaking",
        "today",
    )
    return any(marker in text for marker in markers)


def _score_result_parts(
    item: SearchResult,
    query: str = "",
    backend_order: list[str] | None = None,
    recency: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
) -> dict[str, float]:
    backend_order = backend_order or []
    quality = quality or {}
    parts: dict[str, float] = {
        "base": 1.0,
        "source_credibility": min(item.trust_level, 5) * 0.25,
        "authority_fit": 0.0,
        "sample_fit": 0.0,
        "freshness_fit": 0.0,
        "intent_fit": 0.0,
        "source_quality": _source_quality_weight(item.source_type),
        "content_length": 0.2 if item.snippet else 0.0,
        "keyword_match": 0.0,
        "backend_priority": 0.0,
        "recency_boost": 0.0,
        "ad_penalty": 0.0,
        "intent_mismatch_penalty": 0.0,
        "language_mismatch_penalty": 0.0,
        "source_risk_penalty": 0.0,
        "semantic_noise_penalty": 0.0,
        "stale_penalty": 0.0,
    }
    source_card = (item.trace or {}).get("source_card") or {}
    route_intents = set(quality.get("route_intents") or [])
    route_roles = set(quality.get("route_evidence_roles") or [])
    fit_tags = set(source_card.get("fit_tags") or [])
    content_roles = set(source_card.get("content_roles") or [])
    risk_tags = set(source_card.get("risk_tags") or [])
    authority_score = float(source_card.get("authority_score") or 0.0)
    sample_value = float(source_card.get("sample_value") or 0.0)
    freshness_value = float(source_card.get("freshness_value") or 0.0)
    if route_intents & {"policy", "official_position", "local", "finance", "global_policy", "company_primary"}:
        parts["authority_fit"] = authority_score * 0.45
    if route_intents & {"reputation", "global_reputation", "purchase_advice", "tech"}:
        parts["sample_fit"] = sample_value * 0.42
    if route_intents & {"hot_trend"} or (recency and recency.get("enabled")):
        parts["freshness_fit"] = freshness_value * 0.32
    if route_roles and (route_roles & (fit_tags | content_roles)):
        parts["intent_fit"] += 0.18
    if risk_tags & {"soft_article", "sponsored_content", "seo_content", "commercial_content"}:
        parts["source_risk_penalty"] -= 0.18
    if risk_tags & {"sample_bias", "not_representative"} and route_intents & {"policy", "global_policy", "finance"}:
        parts["source_risk_penalty"] -= 0.22
    title_text = (item.title + " " + item.snippet).lower()
    terms = [t.lower() for t in re.split(r"\s+", query) if t and not t.startswith("site:")]
    if terms:
        matched = sum(1 for term in terms if term in title_text)
        parts["keyword_match"] = min(matched / max(len(terms), 1), 1.0) * 0.8
    first_backend = (item.source.split("+")[0] or "").strip()
    if first_backend in backend_order:
        parts["backend_priority"] = max(0, len(backend_order) - backend_order.index(first_backend)) * 0.05
    preferred_scopes = set(quality.get("preferred_scopes") or [])
    preferred_source_types = set(quality.get("preferred_source_types") or [])
    caution_source_types = set(quality.get("caution_source_types") or [])
    if item.matched_scope and item.matched_scope in preferred_scopes:
        parts["intent_fit"] += 0.65
    elif item.source_type and item.source_type in preferred_source_types:
        parts["intent_fit"] += 0.48
    if item.source_type and item.source_type in caution_source_types:
        parts["intent_mismatch_penalty"] = -0.35
    if _is_chinese_context_query(query, quality) and _result_lacks_chinese_context(item):
        parts["language_mismatch_penalty"] = -0.75
    if _is_low_relevance_ai_noise(item, query):
        parts["semantic_noise_penalty"] = -1.4
    if _is_low_relevance_academic_noise(item, query, quality):
        parts["semantic_noise_penalty"] = min(parts["semantic_noise_penalty"], -2.0)
    if recency and recency.get("enabled"):
        metrics = _result_recency_metrics(item, recency)
        if metrics["result_date"] and metrics["age_days"] is not None:
            age_days = max(int(metrics["age_days"]), 0)
            window_days = max(int(metrics["window_days"] or 1), 1)
            if metrics["in_window"]:
                freshness = max((window_days - age_days) / window_days, 0)
                parts["recency_boost"] = 0.35 + freshness * 0.75
            else:
                overdue = max(age_days - window_days, 0)
                parts["stale_penalty"] = -min(2.4, 0.45 + overdue / window_days)
        else:
            parts["stale_penalty"] = -0.12
        if metrics["has_freshness_words"]:
            parts["recency_boost"] += 0.15
    if _looks_like_ad(item):
        parts["ad_penalty"] = -0.8
    total = sum(parts.values())
    parts["total"] = round(max(total, 0.1), 3)
    return {key: round(value, 3) for key, value in parts.items()}


def _is_chinese_context_query(query: str, quality: dict[str, Any] | None = None) -> bool:
    """Return true when a Chinese query expects Chinese-context evidence."""
    if not _contains_cjk(query):
        return False
    text = query.lower()
    # Technical queries often need English/GitHub evidence even when the user
    # writes in Chinese, so keep the language penalty off for that route.
    tech_terms = ("github", "api", "sdk", "python", "issue", "bug", "benchmark", "repo")
    if any(term in text for term in tech_terms):
        return False
    intent = str((quality or {}).get("intent") or "")
    if "tech" in intent:
        return False
    return True


def _result_lacks_chinese_context(item: SearchResult) -> bool:
    text = _collapse_ws(f"{item.title} {item.snippet}")
    cjk_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    if cjk_chars >= 4:
        return False
    domain = item.domain or _domain(item.url)
    if domain.endswith((".cn", ".com.cn", ".org.cn", ".gov.cn")):
        return False
    return True


def _is_low_relevance_ai_noise(item: SearchResult, query: str) -> bool:
    """Return true for calendar/history pages that match dates but not AI-model intent."""
    combined = _collapse_ws(f"{query} {item.title} {item.snippet}").lower()
    ai_terms = ("llm", "large language model", "ai model", "model release", "gpt", "claude", "gemini", "qwen", "glm")
    if not any(term in combined for term in ai_terms):
        return False
    domain = item.domain or _domain(item.url)
    title_snippet = _collapse_ws(f"{item.title} {item.snippet}").lower()
    noisy_domains = ("timeanddate.com", "calendar-365.com", "calendardate.com", "onthisday.com")
    calendar_terms = ("calendar", "holiday", "holidays", "on this day", "historical events", "events in", "year 2026")
    has_calendar_signal = any(term in title_snippet for term in calendar_terms)
    has_ai_signal = any(term in title_snippet for term in ai_terms)
    if any(domain == noisy or domain.endswith("." + noisy) for noisy in noisy_domains):
        return has_calendar_signal or not has_ai_signal
    return has_calendar_signal and not has_ai_signal


def _is_low_relevance_academic_noise(
    item: SearchResult,
    query: str,
    quality: dict[str, Any] | None = None,
) -> bool:
    """Penalize lexical EI noise when the query is about academic indexing."""
    combined_query = _collapse_ws(query).lower()
    quality = quality or {}
    is_academic = "academic" in str(quality.get("intent") or "")
    academic_query_terms = (
        "ei会议",
        "ei 会议",
        "ei检索",
        "ei 检索",
        "compendex",
        "scopus",
        "学术会议",
        "投稿",
        "收录",
        "论文",
        "conference",
        "proceedings",
    )
    if not (is_academic or any(term in combined_query for term in academic_query_terms)):
        return False
    title_snippet = _collapse_ws(f"{item.title} {item.snippet}").lower()
    noisy_phrases = (
        "exponential integral",
        "e^i",
        "e^{i",
        "'ie' or 'ei'",
        "spelling- 'ie'",
        "esl worksheet",
    )
    if any(phrase in title_snippet for phrase in noisy_phrases):
        return True
    domain = item.domain or _domain(item.url)
    if domain.endswith(("math.stackexchange.com", "usingenglish.com")):
        strong_academic_terms = (
            "engineering index",
            "compendex",
            "scopus",
            "conference",
            "proceedings",
            "paper",
            "journal",
            "会议",
            "检索",
            "收录",
            "论文",
            "投稿",
            "期刊",
            "审稿",
        )
        return not any(term in title_snippet for term in strong_academic_terms)
    academic_result_terms = (
        "ei",
        "engineering index",
        "compendex",
        "scopus",
        "conference",
        "proceedings",
        "paper",
        "journal",
        "会议",
        "检索",
        "收录",
        "论文",
        "投稿",
        "期刊",
        "审稿",
    )
    if any(term in title_snippet for term in academic_result_terms):
        return False
    return False


def _source_quality_weight(source_type: str) -> float:
    weights = {
        "政府/部委": 0.35,
        "党央媒": 0.35,
        "英文官方/监管": 0.35,
        "公司一手资料": 0.3,
        "地方官媒": 0.24,
        "国际主流媒体": 0.22,
        "财经/资本市场": 0.2,
        "英文开发者/开源": 0.18,
        "英文产业/分析": 0.16,
        "电商/零售垂类": 0.16,
        "商业/产业媒体": 0.14,
        "科技/开发者社区": 0.12,
        "评价/消费样本": 0.06,
        "英文社区样本": 0.05,
        "社交/内容平台": 0.04,
        "通用网页": 0.0,
    }
    return weights.get(source_type or "通用网页", 0.0)


def _assign_topic_clusters(results: list[SearchResult], threshold: str = "conservative") -> None:
    """Mark near-duplicate search results that discuss the same topic."""
    clusters: list[dict[str, Any]] = []
    for item in results:
        tokens = _topic_tokens(item.title)
        normalized = _normalize_topic_text(item.title)
        matched: dict[str, Any] | None = None
        for cluster in clusters:
            if _same_topic(normalized, tokens, cluster["normalized"], cluster["tokens"], threshold=threshold):
                matched = cluster
                break
        if matched is None:
            matched = {
                "key": f"topic-{len(clusters) + 1}",
                "normalized": normalized,
                "tokens": tokens,
                "items": [],
            }
            clusters.append(matched)
        item.topic_key = matched["key"]
        matched["items"].append(item)

    for cluster in clusters:
        items = cluster["items"]
        size = len(items)
        for idx, item in enumerate(items):
            item.topic_size = size
            item.topic_role = "single" if size == 1 else ("representative" if idx == 0 else "related")


def _order_topic_representatives_first(results: list[SearchResult]) -> list[SearchResult]:
    representatives = [item for item in results if item.topic_role != "related"]
    related = [item for item in results if item.topic_role == "related"]
    return _interleave_by_source_type(representatives) + related


def _interleave_by_source_type(results: list[SearchResult]) -> list[SearchResult]:
    """Prefer source-type diversity among already-ranked representative items."""
    buckets: dict[str, list[SearchResult]] = {}
    for item in results:
        key = item.source_type or "通用网页"
        buckets.setdefault(key, []).append(item)

    ordered: list[SearchResult] = []
    while buckets:
        for key in list(buckets):
            bucket = buckets[key]
            if bucket:
                ordered.append(bucket.pop(0))
            if not bucket:
                del buckets[key]
    return ordered


def _same_topic(
    left_text: str,
    left_tokens: set[str],
    right_text: str,
    right_tokens: set[str],
    threshold: str = "conservative",
) -> bool:
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    if min(len(left_text), len(right_text)) >= 12 and (left_text in right_text or right_text in left_text):
        return True
    if len(left_tokens) < 4 or len(right_tokens) < 4:
        return False
    overlap = left_tokens & right_tokens
    union = left_tokens | right_tokens
    min_overlap, ratio = {
        "conservative": (4, 0.42),
        "balanced": (3, 0.34),
        "loose": (3, 0.26),
    }.get((threshold or "conservative").lower(), (4, 0.42))
    return len(overlap) >= min_overlap and len(overlap) / max(len(union), 1) >= ratio


def _normalize_topic_text(text: str) -> str:
    text = _collapse_ws(text).lower()
    text = re.sub(r"[【\[].*?[】\]]", " ", text)
    text = re.sub(
        r"[\s\-_—|]+.{0,18}(?:网|新闻|客户端|频道|日报|时报|周刊|央视|人民网|新华网|新浪|搜狐|腾讯|网易|百家号)$",
        " ",
        text,
    )
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text


def _topic_tokens(text: str) -> set[str]:
    normalized = _collapse_ws(text).lower()
    tokens: set[str] = set()
    for segment in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", normalized):
        if re.fullmatch(r"[\u4e00-\u9fff]+", segment):
            for size in (2, 3):
                if len(segment) >= size:
                    tokens.update(segment[i : i + size] for i in range(len(segment) - size + 1))
        elif segment not in {"http", "https", "html", "www", "com", "cn"}:
            tokens.add(segment)
    return {token for token in tokens if token not in _TOPIC_STOP_TOKENS}


_TOPIC_STOP_TOKENS = {
    "中国",
    "我国",
    "进行",
    "相关",
    "最新",
    "消息",
    "新闻",
    "报道",
    "发布",
    "表示",
    "关于",
    "如何",
    "什么",
}


def _canonical_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        return url.strip()
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [
        (k, v)
        for k, v in query
        if not (k.lower().startswith("utm_") or k.lower() in {"spm", "from", "wfr", "for"})
    ]
    return urllib.parse.urlunparse(
        (
            parsed.scheme.lower() or "https",
            parsed.netloc.lower().removeprefix("www."),
            parsed.path.rstrip("/") or "/",
            "",
            urllib.parse.urlencode(filtered),
            "",
        )
    )


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _looks_like_ad(item: SearchResult) -> bool:
    text = f"{item.title} {item.snippet}".lower()
    return any(marker in text for marker in ("广告", "推广", "sponsored", "ad "))


def _is_weak_read(text: str) -> bool:
    normalized = _collapse_ws(text)
    if len(normalized) < _MIN_USEFUL_READ_CHARS:
        return True
    if _looks_mojibake(normalized):
        return True
    lowered = normalized.lower()
    return any(marker in lowered for marker in _WEAK_READ_MARKERS)


def _read_should_fallback(quality: dict[str, Any], strict: bool = False) -> bool:
    label = str(quality.get("label") or "")
    score = int(quality.get("score") or 0)
    if label in {"weak", "fallback"}:
        return True
    if strict and (label == "noisy" or score < 70):
        return True
    return False


def _call_read_direct(url: str, extract: str = "article") -> str:
    """Call _read_direct while keeping old monkeypatched test doubles compatible."""
    try:
        return _read_direct(url, extract=extract)
    except TypeError as exc:
        if extract == "article" and "unexpected keyword" in str(exc):
            return _read_direct(url)  # type: ignore[call-arg]
        raise


def _looks_mojibake(text: str) -> bool:
    """Detect common charset failures on older Chinese sites."""
    sample = (text or "")[:5000]
    if not sample:
        return False
    replacement = sample.count("�")
    cjk = sum(1 for char in sample if "\u4e00" <= char <= "\u9fff")
    if replacement >= 8 and replacement > max(4, cjk // 20):
        return True
    return bool(re.search(r"(?:��){3,}", sample))


def _decode_response_body(raw: bytes, content_type: str = "") -> str:
    """Decode response bytes with Chinese legacy charset fallbacks."""
    charsets: list[str] = []
    header_match = re.search(r"charset=([\w.\-]+)", content_type or "", flags=re.I)
    if header_match:
        charsets.append(header_match.group(1))
    head = raw[:4096].decode("ascii", errors="ignore")
    meta_match = re.search(r"<meta[^>]+charset=['\"]?([\w.\-]+)", head, flags=re.I)
    if meta_match:
        charsets.append(meta_match.group(1))
    meta_http = re.search(r"content=['\"][^'\"]*charset=([\w.\-]+)", head, flags=re.I)
    if meta_http:
        charsets.append(meta_http.group(1))
    charsets.extend(["utf-8", "gb18030", "gbk", "gb2312"])

    tried: set[str] = set()
    best = ""
    for charset in charsets:
        normalized = charset.lower().replace("_", "-")
        if normalized in tried:
            continue
        tried.add(normalized)
        try:
            decoded = raw.decode(charset, errors="replace")
        except LookupError:
            continue
        if not best or decoded.count("�") < best.count("�"):
            best = decoded
        if not _looks_mojibake(decoded):
            return decoded
    return best or raw.decode("utf-8", errors="replace")


def _query_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    path = urllib.parse.unquote(parsed.path or "")
    stem = re.sub(r"\.[a-zA-Z0-9]{1,8}$", " ", path)
    stem = re.sub(r"[/_\-+]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    if stem:
        return stem[:120]
    return domain or url


def _read_with_jina(url: str) -> str:
    jina_url = f"https://r.jina.ai/{url}"
    req = urllib.request.Request(
        jina_url,
        headers={"User-Agent": _UA, "Accept": "text/plain"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _read_direct(url: str, extract: str = "article") -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,text/plain",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw_bytes = resp.read()
        content_type = resp.headers.get("content-type", "")
    raw = _decode_response_body(raw_bytes, content_type)
    if "text/plain" in content_type:
        return raw
    if extract == "metadata":
        return _extract_html_metadata(raw, url=url)
    if extract == "links":
        return _extract_html_links(raw, url=url)
    if extract == "text":
        return _strip_tags(raw)
    return _html_to_markdownish(raw, url=url)


def _html_to_markdownish(raw: str, url: str = "") -> str:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    title = _strip_tags(title_match.group(1)) if title_match else ""
    metadata = _extract_article_metadata(raw)
    text = _extract_article_text(raw)
    lines = []
    if title:
        lines.extend([f"Title: {title}", ""])
    if url:
        lines.extend([f"URL Source: {url}", ""])
    for key, value in metadata.items():
        if value and value != title:
            lines.append(f"{key}: {value}")
    if metadata:
        lines.append("")
    lines.append("Markdown Content:")
    lines.append(text)
    return "\n".join(lines)


def _extract_article_text(raw: str) -> str:
    """Extract readable article text while filtering common page chrome."""
    body = re.sub(r"<!--.*?-->", " ", raw or "", flags=re.S)
    body = re.sub(r"<(script|style|noscript|svg|canvas|iframe)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    body = re.sub(
        r"<(header|footer|nav|aside|form|button|select|option)[^>]*>.*?</\1>",
        " ",
        body,
        flags=re.S | re.I,
    )
    body = _drop_noise_blocks(body)
    body = _prefer_main_content(body)
    body = re.sub(r"</?(?:p|div|section|article|main|h[1-6]|li|blockquote|tr|br)[^>]*>", "\n", body, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body or ""))
    raw_lines = [line.strip(" \t\r\n-•·|") for line in text.splitlines()]
    lines: list[str] = []
    seen: set[str] = set()
    for line in raw_lines:
        line = _collapse_ws(line)
        if _is_noise_content_line(line):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    if not lines:
        return _extract_density_text(raw) or _strip_tags(raw)
    text = "\n\n".join(lines)
    density_text = _extract_density_text(raw)
    if density_text and _text_body_score(density_text) > _text_body_score(text) * 1.15:
        return density_text
    return text


def _extract_density_text(raw: str) -> str:
    """Fallback extractor based on paragraph density for irregular Chinese pages."""
    body = re.sub(r"<!--.*?-->", " ", raw or "", flags=re.S)
    body = re.sub(r"<(script|style|noscript|svg|canvas|iframe|form)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    blocks: list[str] = []
    for match in re.finditer(r"<(h[1-3]|p|li|blockquote)\b[^>]*>(.*?)</\1>", body, flags=re.S | re.I):
        text = _collapse_ws(_strip_tags(match.group(2)))
        if _is_noise_content_line(text):
            continue
        if len(text) < 12 and not re.search(r"[\u4e00-\u9fff].{4,}", text):
            continue
        blocks.append(text)
    if not blocks:
        return ""
    # Keep the densest contiguous window so sidebars with scattered text do not dominate.
    best: list[str] = []
    best_score = -1
    for start in range(len(blocks)):
        window: list[str] = []
        for line in blocks[start : start + 14]:
            window.append(line)
            score = _text_body_score("\n".join(window))
            if score > best_score:
                best_score = score
                best = list(window)
    seen: set[str] = set()
    cleaned: list[str] = []
    for line in best:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(line)
    return "\n\n".join(cleaned)


def _text_body_score(text: str) -> float:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    punctuation = len(re.findall(r"[，。；：、！？,.!?]", text or ""))
    noise = sum(1 for term in ("登录", "注册", "打开APP", "推荐阅读", "相关阅读", "版权声明") if term in (text or ""))
    lines = [line for line in (text or "").splitlines() if line.strip()]
    avg_len = len(_collapse_ws(text)) / max(len(lines), 1)
    return cjk * 2 + punctuation * 8 + avg_len - noise * 80


def _extract_html_metadata(raw: str, url: str = "") -> str:
    """Extract title, common metadata, and publication hints from HTML."""
    fields: list[tuple[str, str]] = []
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw or "", re.S | re.I)
    if title_match:
        fields.append(("title", _strip_tags(title_match.group(1))))
    for match in re.finditer(r"<meta\b([^>]+)>", raw or "", flags=re.I | re.S):
        attrs = _html_attrs(match.group(1))
        key = attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or ""
        value = attrs.get("content") or ""
        key = key.lower().strip()
        if not key or not value:
            continue
        if key in {
            "description",
            "keywords",
            "author",
            "article:author",
            "article:published_time",
            "article:modified_time",
            "og:title",
            "og:description",
            "pubdate",
            "date",
            "publishdate",
        }:
            fields.append((key, _collapse_ws(value)))
    lines = ["# 观澜网页元信息"]
    if url:
        lines.append(f"- url: {url}")
    seen: set[str] = set()
    for key, value in fields:
        if not value:
            continue
        dedupe = f"{key}:{value}".lower()
        if dedupe in seen:
            continue
        seen.add(dedupe)
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _extract_html_links(raw: str, url: str = "") -> str:
    """Extract visible links from HTML as a simple Markdown list."""
    base = url
    links: list[tuple[str, str]] = []
    for match in re.finditer(r"<a\b([^>]+)>(.*?)</a>", raw or "", flags=re.I | re.S):
        attrs = _html_attrs(match.group(1))
        href = (attrs.get("href") or "").strip()
        text = _strip_tags(match.group(2))
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        absolute = urllib.parse.urljoin(base, html.unescape(href))
        if _is_noise_content_line(text):
            continue
        links.append((text[:80] or absolute, absolute))
    lines = ["# 观澜网页链接"]
    if url:
        lines.append(f"- url: {url}")
    seen: set[str] = set()
    for text, href in links[:80]:
        if href in seen:
            continue
        seen.add(href)
        lines.append(f"- [{text}]({href})")
    return "\n".join(lines)


def _html_attrs(fragment: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, _quote, value in re.findall(r"([\w:-]+)\s*=\s*(['\"])(.*?)\2", fragment or "", flags=re.S):
        attrs[key.lower()] = html.unescape(value)
    return attrs


def _drop_noise_blocks(body: str) -> str:
    """Remove common navigation, login, comment, related-story, and ad blocks."""
    noise_attr = (
        r"(?:nav|navbar|menu|footer|header|sidebar|aside|breadcrumb|share|social|comment|"
        r"recommend|related|relate|hot|popular|advert|ad-|ads|login|signin|signup|"
        r"download|app|qrcode|qr-code|copyright|toolbar|pagination|下一篇|上一篇)"
    )
    pattern = rf"<(div|section|ul|ol)\b[^>]*(?:id|class|role)=['\"][^'\"]*{noise_attr}[^'\"]*['\"][^>]*>.*?</\1>"
    previous = None
    cleaned = body
    # Repeat a few times because shallow regex removal can expose nested noisy blocks.
    for _ in range(4):
        previous = cleaned
        cleaned = re.sub(pattern, " ", cleaned, flags=re.S | re.I)
        if cleaned == previous:
            break
    return cleaned


def _prefer_main_content(body: str) -> str:
    candidates = _content_candidates(body)
    if not candidates:
        return body
    best = max(candidates, key=_content_score)
    return best if _content_score(best) >= 120 else body


def _content_candidates(body: str) -> list[str]:
    candidates: list[str] = []
    attr_pattern = (
        r"(?:article|content|main|正文|内容|稿件|文章|详情|post|entry|detail|news|"
        r"rich_media_content|js_content|main-content|article-content|article_content|"
        r"article_body|articleBody|content_area|contentArea|detailContent|text_content|"
        r"TRS_Editor|zoom|con_txt|news_txt|pages_content)"
    )
    for pattern in (
        r"<article\b[^>]*>(.*?)</article>",
        r"<main\b[^>]*>(.*?)</main>",
        r"<div\b[^>]*(?:id|class)=['\"][^'\"]*(?:js_content|rich_media_content)[^'\"]*['\"][^>]*>(.*?)</div>",
        rf"<div\b[^>]*(?:id|class)=['\"][^'\"]*{attr_pattern}[^'\"]*['\"][^>]*>(.*?)</div>",
        rf"<section\b[^>]*(?:id|class)=['\"][^'\"]*{attr_pattern}[^'\"]*['\"][^>]*>(.*?)</section>",
    ):
        candidates.extend(match.group(1) for match in re.finditer(pattern, body, flags=re.S | re.I))
    return candidates


def _extract_article_metadata(raw: str) -> dict[str, str]:
    """Extract publication hints often used by Chinese news sites."""
    html_text = raw or ""
    metadata: dict[str, str] = {}
    meta_keys = {
        "author": "Author",
        "article:author": "Author",
        "source": "Source",
        "mediaid": "Source",
        "article:published_time": "Published",
        "pubdate": "Published",
        "publishdate": "Published",
        "date": "Published",
        "weixin:author": "Author",
        "og:article:author": "Author",
    }
    for match in re.finditer(r"<meta\b([^>]+)>", html_text, flags=re.I | re.S):
        attrs = _html_attrs(match.group(1))
        raw_key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower().strip()
        value = _collapse_ws(attrs.get("content") or "")
        label = meta_keys.get(raw_key)
        if label and value and label not in metadata:
            metadata[label] = value[:120]
    visible_patterns = (
        ("Published", r"(?:发布时间|发布日期|发稿时间|时间)[:：]\s*([0-9]{4}[-年/\.]\d{1,2}[-月/\.]\d{1,2}(?:\s+\d{1,2}:\d{2})?)"),
        ("Source", r"(?:来源|稿源)[:：]\s*([^<\n\r]{2,40})"),
        ("Author", r"(?:作者|记者|编辑)[:：]\s*([^<\n\r]{2,40})"),
    )
    stripped = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_text, flags=re.S | re.I)
    for label, pattern in visible_patterns:
        if label in metadata:
            continue
        match = re.search(pattern, stripped, flags=re.I)
        if match:
            metadata[label] = _strip_tags(match.group(1))[:120]
    return metadata


def _content_score(html_fragment: str) -> int:
    text = _strip_tags(html_fragment)
    if not text:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    paragraphs = len(re.findall(r"</p>|<br\b|</h[1-6]>", html_fragment, flags=re.I))
    link_text = "".join(re.findall(r"<a\b[^>]*>(.*?)</a>", html_fragment, flags=re.S | re.I))
    link_len = len(_strip_tags(link_text))
    return len(text) + cjk * 2 + paragraphs * 40 - link_len * 2


def _is_noise_content_line(line: str) -> bool:
    if not line:
        return True
    if len(line) <= 1:
        return True
    lowered = line.lower()
    noise_markers = (
        "登录",
        "注册",
        "分享",
        "收藏",
        "点赞",
        "评论",
        "发表评论",
        "下载app",
        "下载 app",
        "客户端",
        "扫码",
        "二维码",
        "广告",
        "推荐阅读",
        "相关阅读",
        "热门推荐",
        "返回首页",
        "首页",
        "导航",
        "菜单",
        "上一页",
        "下一页",
        "上一篇",
        "下一篇",
        "版权所有",
        "copyright",
        "icp",
        "京公网安备",
        "联系我们",
        "关于我们",
        "打开app",
        "打开 app",
        "展开全文",
        "继续阅读",
        "点击查看",
        "点击下载",
        "微信扫一扫",
        "用微信扫码",
        "扫码关注",
        "更多精彩",
        "特别声明",
        "免责声明",
    )
    if len(line) <= 28 and any(marker in lowered for marker in noise_markers):
        return True
    if re.fullmatch(r"[\W_]+", line):
        return True
    if len(line) <= 18 and re.search(r"(首页|新闻|财经|科技|娱乐|体育|视频|图片|专题|登录|注册)", line):
        return True
    punctuation = len(re.findall(r"[，。；：、,.!?！？]", line))
    if len(line) <= 36 and punctuation == 0 and re.search(r"(客户端|专题|频道|订阅|投稿|爆料|更多|排行|热搜)", line):
        return True
    return False


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def _strip_tags(text: str) -> str:
    return _collapse_ws(re.sub(r"<[^>]+>", " ", text or ""))


def _best_baidu_snippet(block: str) -> str:
    # Prefer common abstract/summary containers, then fall back to visible text.
    for pattern in (
        r'<span[^>]+class="[^"]*(?:content-right|content|abstract)[^"]*"[^>]*>(.*?)</span>',
        r'<div[^>]+class="[^"]*(?:c-abstract|abstract|content)[^"]*"[^>]*>(.*?)</div>',
    ):
        match = re.search(pattern, block, re.S)
        if match:
            return match.group(1)
    return ""


def _normalize_ddg_url(url: str) -> str:
    url = html.unescape(url or "").strip()
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if parsed.path == "/l/":
        params = urllib.parse.parse_qs(parsed.query)
        uddg = params.get("uddg", [""])[0]
        if uddg:
            return urllib.parse.unquote(uddg)
    if url.startswith("//"):
        return "https:" + url
    return url


def _normalize_bing_url(url: str) -> str:
    url = html.unescape(url or "").strip()
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    encoded = params.get("u", [""])[0]
    if encoded.startswith("a1"):
        encoded = encoded[2:]
        padding = "=" * (-len(encoded) % 4)
        try:
            return base64.urlsafe_b64decode(encoded + padding).decode("utf-8", errors="replace")
        except Exception:
            return url
    return url


def _is_duckduckgo_noise(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host.endswith("duckduckgo.com")
