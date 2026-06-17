# -*- coding: utf-8 -*-
"""Search entrypoint catalog and operator hints for Guanlan.

This module internalizes the useful parts of multi-engine search playbooks as
read-only routing knowledge. It deliberately does not execute raw search engine
URLs: Guanlan's normal search backends, scopes, quality gates, and recovery
logic remain the runtime path.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SearchEngineEntrypoint:
    id: str
    name: str
    region: str
    url_template: str
    status: str
    integration: str
    evidence_role: str
    best_for: str
    caveat: str
    operator_support: tuple[str, ...] = ()
    risk_tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["operator_support"] = list(self.operator_support)
        data["risk_tags"] = list(self.risk_tags)
        return data


SEARCH_ENGINE_ENTRYPOINTS: tuple[SearchEngineEntrypoint, ...] = (
    SearchEngineEntrypoint(
        id="baidu-web",
        name="百度网页搜索",
        region="cn",
        url_template="https://www.baidu.com/s?wd={query}",
        status="best-effort",
        integration="guanlan_native_backend",
        evidence_role="broad_chinese_web_signal",
        best_for="中文通用网页、政策线索、中文站点发现。",
        caveat="易遇到安全验证或 HTML 模板变化；不要把一次拦截解释为没有资料。",
        operator_support=("site:", '"..."', "-"),
        risk_tags=("bot_guard", "seo_noise", "parser_drift"),
    ),
    SearchEngineEntrypoint(
        id="bing-cn",
        name="Bing 中文入口",
        region="cn",
        url_template="https://cn.bing.com/search?q={query}&ensearch=0",
        status="best-effort",
        integration="guanlan_native_backend",
        evidence_role="broad_chinese_web_signal",
        best_for="中文网页补充、英文站中文入口、跨域检索。",
        caveat="中文复合词可能漂移；Guanlan 会做低相关拦截和 generic recovery。",
        operator_support=("site:", '"..."', "-", "OR", "filetype:"),
        risk_tags=("cjk_drift", "regional_template"),
    ),
    SearchEngineEntrypoint(
        id="bing-global",
        name="Bing 国际入口",
        region="global",
        url_template="https://www.bing.com/search?q={query}",
        status="best-effort",
        integration="guanlan_recovery_entrypoint",
        evidence_role="global_web_recovery_signal",
        best_for="Bing 中文入口漂移时补充国际网页结果。",
        caveat="作为恢复入口使用，不替代 scope/site 约束和结果质量过滤。",
        operator_support=("site:", '"..."', "-", "OR", "filetype:"),
        risk_tags=("regional_template",),
    ),
    SearchEngineEntrypoint(
        id="duckduckgo-html",
        name="DuckDuckGo HTML",
        region="global",
        url_template="https://duckduckgo.com/html/?q={query}",
        status="best-effort",
        integration="guanlan_native_backend",
        evidence_role="privacy_web_signal",
        best_for="低追踪网页补充、英文和技术线索、搜索后端恢复。",
        caveat="在部分网络会超时或结构变化；Guanlan 会避免重复慢后端拖垮外层调用。",
        operator_support=("site:", '"..."', "-", "OR"),
        risk_tags=("timeout_prone", "parser_drift"),
    ),
    SearchEngineEntrypoint(
        id="sogou-web",
        name="搜狗网页搜索",
        region="cn",
        url_template="https://www.sogou.com/web?query={query}",
        status="experimental",
        integration="catalog_only",
        evidence_role="chinese_web_auxiliary_signal",
        best_for="中文网页线索辅助，尤其是需要和微信生态相邻观察时。",
        caveat="当前不作为 Guanlan 默认后端；只作为可解释入口或未来实验源。",
        operator_support=("site:", '"..."', "-"),
        risk_tags=("bot_guard", "parser_not_integrated"),
    ),
    SearchEngineEntrypoint(
        id="wechat-sogou",
        name="搜狗微信",
        region="cn",
        url_template="https://wx.sogou.com/weixin?type=2&query={query}",
        status="best-effort",
        integration="optional_backend",
        evidence_role="wechat_article_signal",
        best_for="公众号文章线索、微信生态公开文章发现。",
        caveat="验证码和库兼容性波动大；正文仍需 read/公众号专项提取或授权补证。",
        operator_support=('"..."', "-"),
        risk_tags=("captcha", "login_wall", "third_party_index"),
    ),
    SearchEngineEntrypoint(
        id="so-360",
        name="360 搜索",
        region="cn",
        url_template="https://www.so.com/s?q={query}",
        status="experimental",
        integration="catalog_only",
        evidence_role="chinese_web_auxiliary_signal",
        best_for="中文网页线索辅助。",
        caveat="公网可用性波动，不进入默认搜索链路。",
        operator_support=("site:", '"..."', "-"),
        risk_tags=("availability_drift", "parser_not_integrated"),
    ),
    SearchEngineEntrypoint(
        id="toutiao-search",
        name="头条搜索",
        region="cn",
        url_template="https://so.toutiao.com/search?keyword={query}",
        status="experimental",
        integration="catalog_only",
        evidence_role="content_platform_signal",
        best_for="内容平台、社会热点、娱乐、品牌传播和用户注意力线索。",
        caveat="平台内容推荐和标题党偏差明显；只能做线索，不作事实主证据。",
        operator_support=('"..."', "-"),
        risk_tags=("platform_framing", "sample_bias", "seo_noise"),
    ),
    SearchEngineEntrypoint(
        id="jisilu-search",
        name="集思录搜索",
        region="cn",
        url_template="https://www.jisilu.cn/explore/?keyword={query}",
        status="experimental",
        integration="catalog_only",
        evidence_role="investor_community_signal",
        best_for="可转债、基金、套利、投资者讨论等财经社区样本。",
        caveat="常见访问门槛/风控；只能作为情绪或观点样本，不是投资建议。",
        operator_support=('"..."', "-"),
        risk_tags=("login_wall", "investor_sample", "not_investment_advice"),
    ),
    SearchEngineEntrypoint(
        id="google",
        name="Google",
        region="global",
        url_template="https://www.google.com/search?q={query}",
        status="reference",
        integration="catalog_only",
        evidence_role="global_web_reference",
        best_for="英文全球网页、技术、公司一手资料、国际媒体。",
        caveat="Guanlan 不依赖 Google 裸抓；需要外部读取时仍遵守宿主工具和来源边界。",
        operator_support=("site:", '"..."', "-", "OR", "filetype:", "tbs="),
        risk_tags=("regional_availability",),
    ),
    SearchEngineEntrypoint(
        id="google-hk",
        name="Google 香港",
        region="global",
        url_template="https://www.google.com.hk/search?q={query}",
        status="reference",
        integration="catalog_only",
        evidence_role="global_web_reference",
        best_for="中英混合网页、香港/国际结果补充。",
        caveat="只作目录入口，不作为 Guanlan 默认后端。",
        operator_support=("site:", '"..."', "-", "OR", "filetype:", "tbs="),
        risk_tags=("regional_availability",),
    ),
    SearchEngineEntrypoint(
        id="yahoo-search",
        name="Yahoo Search",
        region="global",
        url_template="https://search.yahoo.com/search?p={query}",
        status="reference",
        integration="catalog_only",
        evidence_role="global_web_reference",
        best_for="英文网页备用入口。",
        caveat="公网访问和页面结构波动，不进入默认后端。",
        operator_support=("site:", '"..."', "-", "OR"),
        risk_tags=("availability_drift",),
    ),
    SearchEngineEntrypoint(
        id="startpage",
        name="Startpage",
        region="global",
        url_template="https://www.startpage.com/sp/search?query={query}",
        status="reference",
        integration="catalog_only",
        evidence_role="privacy_web_reference",
        best_for="隐私搜索偏好的英文网页入口。",
        caveat="部分网络下易超时或被挑战；不作为默认恢复链。",
        operator_support=("site:", '"..."', "-", "OR"),
        risk_tags=("timeout_prone", "bot_guard"),
    ),
    SearchEngineEntrypoint(
        id="brave-search",
        name="Brave Search",
        region="global",
        url_template="https://search.brave.com/search?q={query}",
        status="reference",
        integration="catalog_only",
        evidence_role="privacy_web_reference",
        best_for="独立索引和英文网页备用入口。",
        caveat="部分环境直连不稳定；不进入默认搜索链。",
        operator_support=("site:", '"..."', "-", "OR"),
        risk_tags=("timeout_prone",),
    ),
    SearchEngineEntrypoint(
        id="ecosia",
        name="Ecosia",
        region="global",
        url_template="https://www.ecosia.org/search?q={query}",
        status="reference",
        integration="catalog_only",
        evidence_role="global_web_reference",
        best_for="英文网页备用入口。",
        caveat="结果和挑战页可能依赖 Bing；只作目录，不作默认后端。",
        operator_support=("site:", '"..."', "-", "OR"),
        risk_tags=("bot_guard", "bing_dependent"),
    ),
    SearchEngineEntrypoint(
        id="qwant",
        name="Qwant",
        region="global",
        url_template="https://www.qwant.com/?q={query}",
        status="reference",
        integration="catalog_only",
        evidence_role="privacy_web_reference",
        best_for="欧盟隐私搜索入口和英文/法文资料备用。",
        caveat="公网可用性波动；不作为默认恢复链。",
        operator_support=("site:", '"..."', "-", "OR"),
        risk_tags=("availability_drift",),
    ),
    SearchEngineEntrypoint(
        id="wolframalpha",
        name="WolframAlpha",
        region="global",
        url_template="https://www.wolframalpha.com/input?i={query}",
        status="reference",
        integration="catalog_only",
        evidence_role="computational_knowledge_reference",
        best_for="数学、单位换算、简单知识计算、英文结构化问题。",
        caveat="常有 JS/挑战页；计算结果应由专用 API/工具或原页面核验。",
        operator_support=(),
        risk_tags=("javascript_required", "bot_guard"),
    ),
)

_ENTRYPOINTS_BY_ID = {entry.id: entry for entry in SEARCH_ENGINE_ENTRYPOINTS}
_ALIASES = {
    "baidu": "baidu-web",
    "bing": "bing-cn",
    "bing-int": "bing-global",
    "bing_int": "bing-global",
    "ddg": "duckduckgo-html",
    "duckduckgo": "duckduckgo-html",
    "sogou": "sogou-web",
    "wechat": "wechat-sogou",
    "weixin": "wechat-sogou",
    "toutiao": "toutiao-search",
    "jisilu": "jisilu-search",
    "googlehk": "google-hk",
    "google_hk": "google-hk",
    "brave": "brave-search",
    "wa": "wolframalpha",
}


def list_search_engine_entrypoints(
    *, region: str | None = None, status: str | None = None
) -> dict[str, dict[str, Any]]:
    """Return search entrypoint catalog rows keyed by id."""

    region_key = (region or "").strip().lower()
    status_key = (status or "").strip().lower()
    rows: dict[str, dict[str, Any]] = {}
    for entry in SEARCH_ENGINE_ENTRYPOINTS:
        if region_key and entry.region != region_key:
            continue
        if status_key and entry.status != status_key:
            continue
        rows[entry.id] = entry.to_dict()
    return rows


def get_search_engine_entrypoint(entrypoint_id: str) -> dict[str, Any]:
    """Resolve one search entrypoint id or alias."""

    key = (entrypoint_id or "").strip().lower()
    resolved = _ALIASES.get(key, key)
    entry = _ENTRYPOINTS_BY_ID.get(resolved)
    return entry.to_dict() if entry else {}


def suggest_search_entrypoints(
    query: str,
    *,
    profile: str | None = None,
    route_plan: dict[str, Any] | None = None,
    limit: int = 6,
) -> dict[str, Any]:
    """Suggest catalog entrypoints as fallback knowledge, not execution steps."""

    text = str(query or "")
    profile_key = (profile or "").strip().lower()
    intents = set((route_plan or {}).get("primary_intents") or ()) | set(
        (route_plan or {}).get("secondary_intents") or ()
    )
    scopes = set((route_plan or {}).get("preferred_scopes") or ())
    selected: list[str] = []

    def add(entrypoint_id: str) -> None:
        if entrypoint_id not in selected and entrypoint_id in _ENTRYPOINTS_BY_ID:
            selected.append(entrypoint_id)

    if _contains_cjk(text) or profile_key in {"china", "hybrid", ""}:
        add("baidu-web")
        add("bing-cn")
        add("duckduckgo-html")
        if {"wechat_article", "social", "reputation"} & intents or "公众号" in text or "微信" in text:
            add("wechat-sogou")
        if {"entertainment", "reputation", "hot_trend"} & intents or {"entertainment", "social_web"} & scopes:
            add("toutiao-search")
        if "finance" in intents or any(scope.startswith("finance") for scope in scopes):
            add("jisilu-search")
    if not _contains_cjk(text) or profile_key in {"english", "global", "hybrid"}:
        add("google")
        add("duckduckgo-html")
        add("bing-global")
        if {"developer", "tech", "academic", "global_industry"} & intents:
            add("brave-search")
        if _looks_computational(text):
            add("wolframalpha")
    if not selected:
        selected = ["bing-cn", "duckduckgo-html", "google-hk"]

    rows = [_ENTRYPOINTS_BY_ID[item].to_dict() for item in selected[: max(limit, 1)]]
    return {
        "policy": "catalog_only_not_default_backend",
        "boundary": (
            "搜索入口目录只用于解释和人工补证；Guanlan 默认仍走 search scope、"
            "native backends、AnySearch 策略和质量门禁。"
        ),
        "selected": rows,
        "avoid": [
            "不要让 Agent 逐个裸抓 17 个搜索引擎。",
            "不要把临时 session cookie retry 包装成稳定恢复能力。",
            "不要绕过 --site、scope、query_strategy 和 evidence_role。",
        ],
    }


def build_search_operator_hints(
    query: str,
    *,
    recency: dict[str, Any] | None = None,
    site: str | None = None,
) -> list[dict[str, Any]]:
    """Return query-operator hints suitable for query_strategy traces."""

    text = str(query or "")
    recency = recency or {}
    hints: list[dict[str, Any]] = []
    explicit_site = site or _extract_site_operator(text)
    if explicit_site:
        hints.append(
            {
                "operator": "site:",
                "status": "hard_filter",
                "example": f"site:{explicit_site} {text.replace('site:' + explicit_site, '').strip()}".strip(),
                "boundary": "在 Guanlan 中优先用 --site 表达硬过滤；空结果不能放宽到域外。",
            }
        )
    else:
        hints.append(
            {
                "operator": "site:",
                "status": "available",
                "example": f"site:gov.cn {text}".strip(),
                "boundary": "只在用户需要指定来源、官方站点或域内检索时使用，不自动收窄普通搜索。",
            }
        )
    if '"' in text or "“" in text or "”" in text:
        hints.append(
            {
                "operator": "exact_phrase",
                "status": "already_present",
                "boundary": "精确短语可保护专名，但过度使用会降低召回。",
            }
        )
    elif _looks_like_named_phrase(text):
        hints.append(
            {
                "operator": "exact_phrase",
                "status": "suggested",
                "example": f"\"{_phrase_candidate(text)}\"",
                "boundary": "用于产品名、报告名、项目名等专名；不要把整段长 query 全部加引号。",
            }
        )
    if _looks_filetype_fit(text):
        hints.append(
            {
                "operator": "filetype:",
                "status": "suggested",
                "example": f"{text} filetype:pdf",
                "boundary": "适合白皮书、公告、招股书、报告、论文；PDF 命中仍需 read/下载质量判断。",
            }
        )
    if recency.get("enabled"):
        hints.append(
            {
                "operator": "time_filter",
                "status": "suggested",
                "example": "Google tbs=qdr:d/qdr:w 或 Guanlan recency query rewrite",
                "boundary": "搜索引擎时间参数不可跨后端通用；Guanlan 会用 time_window 标明哪些材料可写成今日/最新。",
            }
        )
    if len(text) > 48:
        hints.append(
            {
                "operator": "query_decomposition",
                "status": "suggested",
                "boundary": "长 query 先拆成实体、时间、来源角色，不要一次塞给单个搜索引擎。",
            }
        )
    return hints


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _looks_computational(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(r"\d+\s*(usd|cny|eur|gbp|km|kg|cm|inch|%)", lowered)
        or any(term in lowered for term in ("convert", "integrate", "derivative", "weather in", "stock"))
        or any(term in text for term in ("换算", "积分", "导数", "等于多少"))
    )


def _extract_site_operator(text: str) -> str:
    match = re.search(r"(?i)\bsite:([^\s]+)", text)
    return match.group(1).strip() if match else ""


def _looks_like_named_phrase(text: str) -> bool:
    clean = text.strip()
    if len(clean) < 4 or len(clean) > 36:
        return False
    return bool(re.search(r"[A-Z][A-Za-z0-9_.-]+", clean) or re.search(r"[\u4e00-\u9fff]{2,}(?:AI|Agent|MCP|API|PPT|SaaS|CLI)", clean))


def _phrase_candidate(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= 24:
        return clean
    tokens = clean.split()
    return " ".join(tokens[:4]) if tokens else clean[:24]


def _looks_filetype_fit(text: str) -> bool:
    lowered = text.lower()
    return any(
        term in lowered
        for term in (
            "pdf",
            "white paper",
            "report",
            "prospectus",
            "filing",
            "论文",
            "报告",
            "白皮书",
            "公告",
            "招股书",
            "年报",
            "指南",
        )
    )
