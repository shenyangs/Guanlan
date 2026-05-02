# -*- coding: utf-8 -*-
"""Intent-aware routing plans for Guanlan research.

The router is intentionally heuristic and local-first. It produces soft plans:
preferred scopes and sites should guide ranking and research jobs, while open
web fallback remains available unless the user explicitly restricts the query.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RoutePlan:
    query: str
    primary_intents: list[str] = field(default_factory=list)
    secondary_intents: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    freshness: str = ""
    risk_level: str = "low"
    evidence_roles: list[str] = field(default_factory=list)
    preferred_scopes: list[str] = field(default_factory=list)
    fallback_scopes: list[str] = field(default_factory=list)
    target_sites: list[str] = field(default_factory=list)
    avoid_as_primary: list[str] = field(default_factory=list)
    query_variants: list[str] = field(default_factory=list)
    backend_hint: list[str] = field(default_factory=list)
    read_top: int = 2
    limit: int = 50
    advisor_recommended: bool = False
    warnings: list[str] = field(default_factory=list)
    explain: list[str] = field(default_factory=list)
    confidence: float = 0.4

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_INTENT_RULES: tuple[dict[str, Any], ...] = (
    {
        "intent": "policy",
        "terms": ("政策", "监管", "法规", "通知", "办法", "意见", "征求意见", "部委", "国务院", "备案", "合规"),
        "scopes": ("gov", "party_central"),
        "fallback": ("local_official", "business"),
        "roles": ("official_primary", "authoritative_report"),
        "warning": "政策/监管问题应优先核验官方原文，媒体解读只能作为背景。",
    },
    {
        "intent": "official_position",
        "terms": ("官方", "央媒", "权威", "表述", "口径", "定调", "人民日报", "新华社", "央视"),
        "scopes": ("party_central", "gov"),
        "fallback": ("local_official",),
        "roles": ("official_narrative", "authoritative_report"),
    },
    {
        "intent": "local",
        "terms": ("地方", "城市", "区域", "省", "市", "区县", "园区", "北京", "上海", "深圳", "广州", "杭州", "成都"),
        "scopes": ("local_official", "gov"),
        "fallback": ("party_central", "business"),
        "roles": ("local_context", "official_primary"),
    },
    {
        "intent": "reputation",
        "terms": ("评价", "口碑", "体验", "吐槽", "避雷", "测评", "推荐吗", "好用吗", "怎么样", "小红书", "知乎", "微博", "b站"),
        "scopes": ("social_web", "tech_dev", "business"),
        "fallback": ("ecommerce",),
        "sites": ("zhihu.com", "weibo.com", "xiaohongshu.com", "bilibili.com"),
        "roles": ("user_sample", "community_discussion", "vertical_report"),
        "warning": "社交和社区材料适合发现样本线索，不代表总体比例。",
    },
    {
        "intent": "purchase_advice",
        "terms": ("值不值得买", "能买吗", "要不要买", "购买", "选购", "对比", "推荐哪", "踩雷", "缺点", "优缺点"),
        "scopes": ("social_web", "business", "ecommerce"),
        "fallback": ("tech_dev",),
        "sites": ("zhihu.com", "xiaohongshu.com", "bilibili.com"),
        "roles": ("user_sample", "official_specs", "review"),
        "warning": "购买建议需要同时核验官方参数、垂类评测和用户样本，不能只看单个平台。",
    },
    {
        "intent": "industry",
        "terms": ("行业", "产业", "商业化", "公司", "竞品", "融资", "市场", "趋势", "供应链", "创业"),
        "scopes": ("business", "finance", "ecommerce"),
        "fallback": ("party_central", "social_web"),
        "roles": ("industry_report", "company_context", "market_news"),
    },
    {
        "intent": "ecommerce",
        "terms": ("电商", "零售", "跨境", "出海", "品牌", "渠道", "供应链", "产业带", "亚马逊", "抖音电商"),
        "scopes": ("ecommerce", "business"),
        "fallback": ("social_web", "finance"),
        "roles": ("vertical_report", "case", "consumer_signal"),
    },
    {
        "intent": "tech",
        "terms": ("技术", "开源", "框架", "github", "sdk", "api", "部署", "bug", "benchmark", "选型", "开发者"),
        "scopes": ("tech_dev",),
        "fallback": ("business", "social_web"),
        "sites": ("github.com", "v2ex.com", "juejin.cn", "segmentfault.com"),
        "roles": ("source_code", "technical_note", "developer_discussion"),
    },
    {
        "intent": "finance",
        "terms": ("财经", "股价", "股票", "财报", "公告", "投资", "融资", "上市", "基金", "债券", "营收", "利润"),
        "scopes": ("finance", "business"),
        "fallback": ("gov", "social_web"),
        "roles": ("market_news", "filing_context", "risk_context"),
        "warning": "财经材料时效和立场差异大，不能把市场观点写成投资建议。",
    },
    {
        "intent": "hot_trend",
        "terms": ("今天", "今日", "最新", "最近", "近期", "热点", "热搜", "热议", "刷屏", "突发", "舆情", "快讯"),
        "scopes": ("social_web", "business", "finance"),
        "fallback": ("party_central", "tech_dev"),
        "roles": ("fresh_news", "public_discussion"),
    },
)

_DOMAIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auto", ("汽车", "车", "新能源车", "智驾", "小米yu7", "蔚来", "理想", "小鹏", "特斯拉", "比亚迪")),
    ("ai", ("ai", "人工智能", "大模型", "agent", "智能体", "llm", "算力")),
    ("consumer", ("手机", "电脑", "家电", "相机", "耳机", "消费", "购买", "值不值得买")),
    ("career", ("招聘", "求职", "岗位", "薪资", "面试", "简历")),
    ("health", ("医疗", "疾病", "药", "治疗", "医生", "症状", "医院")),
    ("legal", ("法律", "诉讼", "判决", "合同", "律师", "侵权")),
)

_HIGH_RISK_TERMS = ("医疗", "疾病", "治疗", "药", "法律", "诉讼", "投资", "股票", "买入", "卖出", "借贷", "保险")


def build_route_plan(
    query: str,
    *,
    preset: str | None = None,
    scope: str | None = None,
    site: str | None = None,
    sites: list[str] | None = None,
    profile: str | None = None,
    limit: int | None = None,
    read_top: int | None = None,
) -> RoutePlan:
    """Build a soft route plan for a user query."""
    clean_query = " ".join((query or "").split())
    text = clean_query.lower()
    matched_rules: list[dict[str, Any]] = []
    reasons: list[str] = []
    for rule in _INTENT_RULES:
        hits = [term for term in rule["terms"] if _term_matches(text, str(term))]
        if hits:
            matched_rules.append(rule)
            reasons.append(f"{rule['intent']}: {','.join(hits[:4])}")

    if preset and preset not in {"", "general"}:
        preset_rule = _preset_rule(str(preset))
        if preset_rule:
            matched_rules.insert(0, preset_rule)
            reasons.append(f"preset:{preset}")

    primary = _unique([str(rule["intent"]) for rule in matched_rules])[:2] or ["general"]
    secondary = _unique([str(rule["intent"]) for rule in matched_rules])[2:5]
    domains = _detect_domains(text)
    freshness = _detect_freshness(text)
    high_risk = _contains_any(text, _HIGH_RISK_TERMS)

    preferred_scopes = _unique(_flatten(rule.get("scopes", ()) for rule in matched_rules))
    fallback_scopes = _unique(_flatten(rule.get("fallback", ()) for rule in matched_rules))
    if {"policy", "official_position"} & set(primary + secondary):
        policy_primary = {"gov", "party_central", "local_official"}
        overflow = [scope_id for scope_id in preferred_scopes if scope_id not in policy_primary]
        preferred_scopes = [scope_id for scope_id in preferred_scopes if scope_id in policy_primary]
        fallback_scopes = _unique(fallback_scopes + overflow)
    target_sites = _unique(_flatten(rule.get("sites", ()) for rule in matched_rules))
    if site:
        target_sites.insert(0, site)
    if sites:
        target_sites = _unique(list(sites) + target_sites)

    evidence_roles = _unique(_flatten(rule.get("roles", ()) for rule in matched_rules))
    if not evidence_roles:
        evidence_roles = ["broad_web", "source_diversity", "topic_representative"]

    warnings = _unique([str(rule["warning"]) for rule in matched_rules if rule.get("warning")])
    if high_risk:
        warnings.append("该查询可能涉及高影响决策；输出应保留边界，建议核验专业来源。")
    if "reputation" in primary or "reputation" in secondary:
        warnings.append("口碑/社交样本不可直接代表总体比例，应和垂类媒体或官方信息交叉验证。")
    if scope:
        warnings.append("用户显式指定 scope，路由只能作为排序和解释辅助，不应覆盖用户选择。")
    if site or sites:
        warnings.append("用户显式指定站点，优先尊重站内/平台定向搜索。")

    advisor_recommended = bool(
        {"purchase_advice", "reputation", "finance", "policy", "industry", "tech"} & set(primary + secondary)
        or high_risk
    )
    read_default = 3 if {"policy", "official_position", "tech", "industry"} & set(primary + secondary) else 2
    if "reputation" in primary + secondary and not high_risk:
        read_default = 1

    plan = RoutePlan(
        query=clean_query,
        primary_intents=primary,
        secondary_intents=secondary,
        domains=domains,
        freshness=freshness,
        risk_level="high" if high_risk else ("medium" if advisor_recommended else "low"),
        evidence_roles=evidence_roles,
        preferred_scopes=preferred_scopes,
        fallback_scopes=[scope_id for scope_id in fallback_scopes if scope_id not in preferred_scopes],
        target_sites=target_sites[:8],
        avoid_as_primary=_avoid_as_primary(primary + secondary),
        query_variants=_query_variants(clean_query, primary + secondary, domains),
        backend_hint=["baidu", "bing", "duckduckgo"] if profile == "china" else ["duckduckgo", "bing"],
        read_top=max(read_top if read_top is not None else read_default, 0),
        limit=max(limit if limit is not None else 50, 1),
        advisor_recommended=advisor_recommended,
        warnings=_unique(warnings),
        explain=_unique(reasons + _domain_reasons(domains) + _route_explanations(primary, preferred_scopes, target_sites)),
        confidence=_confidence(matched_rules, scope=scope, site=site, sites=sites),
    )
    return plan


def format_route_plan_markdown(plan: RoutePlan | dict[str, Any]) -> str:
    """Render a route plan as Markdown for humans and agents."""
    data = plan.to_dict() if isinstance(plan, RoutePlan) else dict(plan)
    lines = [f"# 观澜路由计划 / {data.get('query', '')}", ""]
    rows = [
        ("主要意图", ", ".join(data.get("primary_intents") or [])),
        ("次要意图", ", ".join(data.get("secondary_intents") or []) or "无"),
        ("领域标签", ", ".join(data.get("domains") or []) or "未识别"),
        ("时效需求", data.get("freshness") or "默认"),
        ("风险等级", data.get("risk_level") or "low"),
        ("建议 advisor", "是" if data.get("advisor_recommended") else "否"),
        ("建议读取", str(data.get("read_top", 0))),
        ("建议候选池", str(data.get("limit", 0))),
    ]
    for key, value in rows:
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 证据结构"])
    lines.append(f"- 证据角色: {', '.join(data.get('evidence_roles') or [])}")
    lines.append(f"- 优先 scope: {', '.join(data.get('preferred_scopes') or []) or 'open web'}")
    lines.append(f"- 兜底 scope: {', '.join(data.get('fallback_scopes') or []) or 'open web'}")
    lines.append(f"- 推荐站点: {', '.join(data.get('target_sites') or []) or '无'}")
    lines.append(f"- 不宜作为主证据: {', '.join(data.get('avoid_as_primary') or []) or '无'}")
    lines.extend(["", "## 查询改写"])
    for variant in data.get("query_variants") or []:
        lines.append(f"- {variant}")
    if data.get("warnings"):
        lines.extend(["", "## 边界提醒"])
        for warning in data.get("warnings") or []:
            lines.append(f"- {warning}")
    if data.get("explain"):
        lines.extend(["", "## 路由理由"])
        for item in data.get("explain") or []:
            lines.append(f"- {item}")
    return "\n".join(lines)


def route_plan_context(plan: RoutePlan | dict[str, Any]) -> str:
    data = plan.to_dict() if isinstance(plan, RoutePlan) else dict(plan)
    return json.dumps(data, ensure_ascii=False, indent=2)


def _preset_rule(preset: str) -> dict[str, Any] | None:
    mapping = {
        "policy": "policy",
        "official": "official_position",
        "local": "local",
        "reputation": "reputation",
        "industry": "industry",
        "ecommerce": "ecommerce",
        "tech": "tech",
        "finance": "finance",
    }
    intent = mapping.get(preset)
    if not intent:
        return None
    for rule in _INTENT_RULES:
        if rule["intent"] == intent:
            return dict(rule)
    return None


def _term_matches(text: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9_.-]+", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", text, flags=re.I))
    return term.lower() in text


def _detect_domains(text: str) -> list[str]:
    domains = []
    for label, terms in _DOMAIN_RULES:
        if any(_term_matches(text, term) for term in terms):
            domains.append(label)
    return domains


def _detect_freshness(text: str) -> str:
    if any(term in text for term in ("今天", "今日", "24小时", "实时", "刚刚", "热搜", "突发")):
        return "today"
    if any(term in text for term in ("最近", "近期", "最新", "进展", "动态", "热议", "快讯")):
        return "recent"
    return ""


def _query_variants(query: str, intents: list[str], domains: list[str]) -> list[str]:
    variants = [query]
    if "policy" in intents:
        variants.append(f"{query} 政策 原文 通知")
    if "reputation" in intents:
        variants.append(f"{query} 评价 体验 吐槽")
    if "purchase_advice" in intents:
        variants.append(f"{query} 优缺点 值不值得买")
    if "tech" in intents:
        variants.append(f"{query} github issue 文档 实践")
    if "finance" in intents:
        variants.append(f"{query} 公告 财报 风险")
    if "auto" in domains:
        variants.append(f"{query} 汽车 车主 试驾")
    return _unique(variants)[:5]


def _avoid_as_primary(intents: list[str]) -> list[str]:
    avoid = []
    if "policy" in intents or "official_position" in intents:
        avoid.extend(["社交/内容平台", "商业软文", "SEO 聚合页"])
    if "reputation" in intents or "purchase_advice" in intents:
        avoid.extend(["单条爆款帖", "疑似营销内容", "无来源二手汇总"])
    if "finance" in intents:
        avoid.extend(["社交荐股", "未核验市场传言"])
    return _unique(avoid)


def _route_explanations(intents: list[str], scopes: list[str], sites: list[str]) -> list[str]:
    output = []
    if scopes:
        output.append(f"按意图优先查看 {', '.join(scopes)}，但保留开放搜索兜底以避免信源池过窄。")
    else:
        output.append("未识别强路由意图，优先做开放网页搜索并按信源类型重排。")
    if sites:
        output.append(f"补充平台定向站点: {', '.join(sites[:4])}。")
    if "purchase_advice" in intents:
        output.append("购买/选型问题需要官方信息、垂类评测和用户样本三角验证。")
    return output


def _domain_reasons(domains: list[str]) -> list[str]:
    return [f"domain:{domain}" for domain in domains]


def _confidence(rules: list[dict[str, Any]], **kwargs: Any) -> float:
    score = 0.35 + min(len(rules), 4) * 0.13
    if kwargs.get("scope") or kwargs.get("site") or kwargs.get("sites"):
        score += 0.12
    return round(min(score, 0.92), 2)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term.lower() in text for term in terms)


def _flatten(groups: Any) -> list[str]:
    values: list[str] = []
    for group in groups:
        values.extend(str(item) for item in group)
    return values


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output
