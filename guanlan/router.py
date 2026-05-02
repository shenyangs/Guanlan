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
    recommended_feeds: list[str] = field(default_factory=list)
    recommended_commands: list[str] = field(default_factory=list)
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
        "intent": "global_policy",
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
        "scopes": ("global_official", "global_news"),
        "fallback": ("industry_analysis", "community_sample"),
        "roles": ("official_primary", "authoritative_report"),
        "warning": "英文政策/监管问题应优先核验政府、监管机构或标准组织原文，媒体报道只能作为背景。",
    },
    {
        "intent": "standards_compliance",
        "terms": (
            "标准",
            "认证",
            "合规",
            "审计",
            "等保",
            "iso",
            "iec",
            "nist",
            "soc2",
            "gdpr",
            "hipaa",
            "compliance",
            "certification",
            "standard",
            "standards",
        ),
        "scopes": ("global_official", "gov", "company_primary", "academic"),
        "fallback": ("developer", "industry_analysis", "business"),
        "sites": ("iso.org", "iec.ch", "nist.gov", "samr.gov.cn", "tc260.org.cn"),
        "roles": ("standard_original", "regulator_guidance", "implementation_context", "vendor_claim"),
        "warning": "标准/合规问题应区分标准原文、监管解释、厂商声明和实施经验；博客只能作落地参考。",
    },
    {
        "intent": "medical_health",
        "terms": (
            "医疗",
            "疾病",
            "药",
            "药品",
            "治疗",
            "诊断",
            "症状",
            "临床",
            "指南",
            "fda",
            "cdc",
            "who",
            "medical",
            "clinical",
            "treatment",
        ),
        "scopes": ("global_official", "gov", "academic"),
        "fallback": ("global_news", "business"),
        "sites": ("who.int", "cdc.gov", "fda.gov", "nhc.gov.cn", "nmpa.gov.cn"),
        "roles": ("clinical_guideline", "regulator_notice", "peer_review", "patient_context"),
        "warning": "医疗健康信息属于高影响领域，应优先专业机构/监管/指南来源，不输出诊断或治疗指令。",
    },
    {
        "intent": "legal_judicial",
        "terms": (
            "法律",
            "诉讼",
            "判决",
            "合同",
            "律师",
            "侵权",
            "司法解释",
            "法院",
            "裁判文书",
            "条例",
            "law",
            "legal",
            "court",
            "lawsuit",
        ),
        "scopes": ("gov", "global_official", "local_official", "academic"),
        "fallback": ("business", "community_sample"),
        "sites": ("npc.gov.cn", "court.gov.cn", "moj.gov.cn", "wenshu.court.gov.cn", "lawinfochina.com"),
        "roles": ("statute_original", "judicial_interpretation", "case_record", "legal_analysis"),
        "warning": "法律司法问题应区分法律条文、司法解释、判例/裁判文书和律师观点，不输出确定性法律意见。",
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
        "intent": "company_primary",
        "terms": (
            "pricing",
            "release notes",
            "release note",
            "changelog",
            "docs",
            "documentation",
            "status page",
            "terms of service",
            "investor relations",
            "earnings",
            "product update",
            "official blog",
        ),
        "scopes": ("company_primary", "developer"),
        "fallback": ("global_news", "community_sample"),
        "roles": ("company_primary", "technical_primary", "fresh_news"),
        "warning": "公司一手资料适合核验规格、价格和发布事实，但需要和用户/媒体样本区分开。",
    },
    {
        "intent": "global_reputation",
        "terms": ("review", "reviews", "reddit", "hacker news", "hn", "trustpilot", "g2", "capterra", "complaints", "worth it"),
        "scopes": ("community_sample", "market_review", "global_news"),
        "fallback": ("company_primary", "developer"),
        "sites": ("reddit.com", "news.ycombinator.com", "g2.com", "trustpilot.com"),
        "roles": ("user_sample", "community_discussion", "review"),
        "warning": "英文社区和评价站点适合发现样本线索，不代表总体比例或事实裁决。",
    },
    {
        "intent": "global_industry",
        "terms": ("market map", "industry analysis", "market share", "competitive landscape", "startup", "funding", "analyst report"),
        "scopes": ("industry_analysis", "global_news", "company_primary"),
        "fallback": ("community_sample",),
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
        "intent": "academic",
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
            "版面",
            "conference",
            "proceedings",
        ),
        "scopes": ("academic",),
        "fallback": ("tech_dev", "business", "social_web"),
        "sites": ("elsevier.com", "engineeringvillage.com", "ieee.org", "cnki.net", "xueshu.baidu.com"),
        "roles": ("database_official", "publisher_guideline", "institution_policy", "community_discussion"),
        "warning": "学术会议/检索问题应区分数据库官方说明、出版商要求、会议 CFP 和学校/单位认定口径；SEO 代投文章只能作线索。",
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
    ("policy", ("regulation", "policy", "compliance", "law", "standard")),
    ("company", ("pricing", "release notes", "docs", "official blog", "investor relations")),
    ("reviews", ("review", "reviews", "reddit", "g2", "trustpilot", "capterra")),
)

_HIGH_RISK_TERMS = (
    "医疗",
    "疾病",
    "治疗",
    "药",
    "法律",
    "诉讼",
    "投资",
    "股票",
    "买入",
    "卖出",
    "借贷",
    "保险",
    "medical",
    "treatment",
    "legal",
    "lawsuit",
    "investment",
    "stock",
    "insurance",
)


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
    profile = _resolve_query_profile(clean_query, profile)
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
    if profile == "english":
        preferred_scopes = _english_scope_equivalents(preferred_scopes)
        fallback_scopes = _english_scope_equivalents(fallback_scopes)
    precision_intents = {"standards_compliance", "medical_health", "legal_judicial", "academic"}
    if {"policy", "official_position"} & set(primary + secondary) and not precision_intents & set(primary + secondary):
        policy_primary = {"gov", "party_central", "local_official"}
        if profile in {"english", "global"}:
            policy_primary = {"global_official", "global_news"}
        overflow = [scope_id for scope_id in preferred_scopes if scope_id not in policy_primary]
        preferred_scopes = [scope_id for scope_id in preferred_scopes if scope_id in policy_primary]
        fallback_scopes = _unique(fallback_scopes + overflow)
    target_sites = _unique(_flatten(rule.get("sites", ()) for rule in matched_rules))
    if site:
        target_sites.insert(0, site)
    if sites:
        target_sites = _unique(list(sites) + target_sites)
    if profile == "english" and not (site or sites):
        target_sites = _english_site_equivalents(target_sites)

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
        {
            "purchase_advice",
            "reputation",
            "global_reputation",
            "finance",
            "policy",
            "global_policy",
            "industry",
            "global_industry",
            "tech",
            "company_primary",
            "standards_compliance",
            "medical_health",
            "legal_judicial",
        }
        & set(primary + secondary)
        or high_risk
    )
    try:
        from guanlan.feeds import recommend_feed_sources

        recommended_feeds = recommend_feed_sources(clean_query)
    except Exception:
        recommended_feeds = []
    reading_discovery = _is_reading_discovery(text)
    if "hot_trend" in primary + secondary and not reading_discovery and "baidu-rss" not in recommended_feeds:
        recommended_feeds.append("baidu-rss")
    if "tech" in primary + secondary and "curated" not in recommended_feeds:
        recommended_feeds.append("curated")
    recommended_feeds = _unique(recommended_feeds)
    recommended_commands = _recommended_commands(
        clean_query,
        intents=primary + secondary,
        domains=domains,
        feeds=recommended_feeds,
        preferred_scopes=preferred_scopes,
        target_sites=target_sites,
        profile=profile,
        read_top=read_top,
    )
    read_default = 3 if {"policy", "official_position", "tech", "industry"} & set(primary + secondary) else 2
    if {"standards_compliance", "medical_health", "legal_judicial"} & set(primary + secondary):
        read_default = 3
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
        recommended_feeds=recommended_feeds,
        recommended_commands=recommended_commands,
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
    lines.append(f"- 推荐 RSS: {', '.join(data.get('recommended_feeds') or []) or '无'}（仅作补充线索，不覆盖主 scope）")
    lines.append(f"- 不宜作为主证据: {', '.join(data.get('avoid_as_primary') or []) or '无'}")
    if data.get("recommended_commands"):
        lines.extend(["", "## 建议命令"])
        for command in data.get("recommended_commands") or []:
            lines.append(f"- `{command}`")
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
        "global_policy": "global_policy",
        "regulation": "global_policy",
        "official": "official_position",
        "local": "local",
        "reputation": "reputation",
        "global_reputation": "global_reputation",
        "reviews": "global_reputation",
        "industry": "industry",
        "global_industry": "global_industry",
        "company": "company_primary",
        "company_primary": "company_primary",
        "ecommerce": "ecommerce",
        "tech": "tech",
        "academic": "academic",
        "scholar": "academic",
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
    if "global_policy" in intents:
        variants.append(f"{query} official regulation policy primary source")
    if "reputation" in intents:
        variants.append(f"{query} 评价 体验 吐槽")
    if "global_reputation" in intents:
        variants.append(f"{query} review reddit hacker news complaints")
    if "purchase_advice" in intents:
        variants.append(f"{query} 优缺点 值不值得买")
    if "company_primary" in intents:
        variants.append(f"{query} official docs pricing release notes")
    if "tech" in intents:
        variants.append(f"{query} github issue 文档 实践")
    if "global_industry" in intents:
        variants.append(f"{query} market analysis competitive landscape")
    if "academic" in intents:
        variants.append(f"{query} 官方 数据库 出版商 要求")
        variants.append(f"{query} 学校 研究生院 认定 论文")
        variants.append(f"{query} CFP author guidelines proceedings")
    if "standards_compliance" in intents:
        variants.append(f"{query} official standard regulator guidance")
        variants.append(f"{query} 标准 原文 监管 认证 要求")
    if "medical_health" in intents:
        variants.append(f"{query} clinical guideline regulator official")
        variants.append(f"{query} 指南 监管 官方 适应症")
    if "legal_judicial" in intents:
        variants.append(f"{query} 法律 条文 司法解释 裁判文书")
        variants.append(f"{query} statute court regulation official")
    if "finance" in intents:
        variants.append(f"{query} 公告 财报 风险")
    if "auto" in domains:
        variants.append(f"{query} 汽车 车主 试驾")
    return _unique(variants)[:5]


def _avoid_as_primary(intents: list[str]) -> list[str]:
    avoid = []
    if "policy" in intents or "official_position" in intents or "global_policy" in intents:
        avoid.extend(["社交/内容平台", "英文社区样本", "商业软文", "SEO 聚合页"])
    if "reputation" in intents or "global_reputation" in intents or "purchase_advice" in intents:
        avoid.extend(["单条爆款帖", "疑似营销内容", "无来源二手汇总", "单一 review 站点评分"])
    if "finance" in intents:
        avoid.extend(["社交荐股", "未核验市场传言"])
    if "academic" in intents:
        avoid.extend(["代投软文", "SEO 聚合页", "无出处经验帖"])
    if "standards_compliance" in intents:
        avoid.extend(["培训机构软文", "厂商单方合规声明", "无编号标准摘抄"])
    if "medical_health" in intents:
        avoid.extend(["问诊广告", "未经核验偏方", "单篇自媒体健康建议"])
    if "legal_judicial" in intents:
        avoid.extend(["营销型律师文章", "断章取义案例", "无条文依据问答"])
    return _unique(avoid)


def _recommended_commands(
    query: str,
    *,
    intents: list[str],
    domains: list[str],
    feeds: list[str],
    preferred_scopes: list[str],
    target_sites: list[str],
    profile: str | None,
    read_top: int | None,
) -> list[str]:
    """Build a small command shortlist for agents after routing."""
    commands: list[str] = []
    quoted = _shell_quote(query)
    profile_part = f" --profile {profile}" if profile in {"china", "english", "hybrid"} else ""
    effective_read_top = 2 if read_top is None else max(read_top, 0)
    reading_discovery = _is_reading_discovery(query.lower())

    if "hot_trend" in intents and not reading_discovery and profile != "english":
        commands.append("guanlan hotnews today --limit 50")
    if "academic" in intents:
        academic_read_top = max(read_top if read_top is not None else 0, 0)
        commands.append(f"guanlan research {quoted} --preset academic{profile_part} --limit 50 --read-top {academic_read_top}")
    elif "standards_compliance" in intents and not (profile == "english" and "global_policy" in intents):
        commands.append(f"guanlan research {quoted}{profile_part} --scope global_official --limit 50 --read-top {max(effective_read_top, 3)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope gov --limit 50")
    elif "medical_health" in intents:
        commands.append(f"guanlan research {quoted}{profile_part} --scope global_official --limit 50 --read-top {max(effective_read_top, 3)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope academic --limit 50")
    elif "legal_judicial" in intents:
        commands.append(f"guanlan research {quoted}{profile_part} --scope gov --limit 50 --read-top {max(effective_read_top, 3)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope global_official --limit 50")
    elif "global_policy" in intents:
        commands.append(f"guanlan research {quoted} --preset global_policy{profile_part} --limit 50 --read-top {max(effective_read_top, 2)}")
    elif "policy" in intents:
        commands.append(f"guanlan research {quoted} --preset policy{profile_part} --limit 50 --read-top {max(effective_read_top, 2)}")
    elif "official_position" in intents:
        commands.append(f"guanlan research {quoted} --preset official{profile_part} --limit 50 --read-top {max(effective_read_top, 2)}")
    elif "global_reputation" in intents:
        commands.append(f"guanlan research {quoted} --preset global_reputation{profile_part} --limit 50 --read-top {effective_read_top}")
    elif "reputation" in intents or "purchase_advice" in intents:
        commands.append(f"guanlan pulse {quoted}{profile_part} --limit 80 --format context")
        commands.append(f"guanlan research {quoted} --preset reputation{profile_part} --limit 50 --read-top {effective_read_top}")
    elif "company_primary" in intents:
        commands.append(f"guanlan research {quoted} --preset company{profile_part} --limit 50 --read-top {max(effective_read_top, 2)}")
    elif "tech" in intents:
        commands.append(f"guanlan research {quoted} --preset tech{profile_part} --limit 50 --read-top {max(effective_read_top, 2)}")
    elif "global_industry" in intents:
        commands.append(f"guanlan research {quoted} --preset global_industry{profile_part} --limit 50 --read-top {max(effective_read_top, 2)}")
    elif "industry" in intents:
        commands.append(f"guanlan research {quoted} --preset industry{profile_part} --limit 50 --read-top {max(effective_read_top, 2)}")
    elif "finance" in intents:
        commands.append(f"guanlan research {quoted} --preset finance{profile_part} --limit 50 --read-top {max(effective_read_top, 1)}")

    if not commands:
        scope = preferred_scopes[0] if preferred_scopes else ""
        scope_part = f" --scope {scope}" if scope else ""
        commands.append(f"guanlan search {quoted}{profile_part}{scope_part} --limit 50")

    if target_sites and not any(site in commands[0] for site in target_sites[:1]):
        commands.append(f"guanlan search {quoted} --site {target_sites[0]}{profile_part} --limit 50")

    for feed in feeds:
        if feed == "curated":
            category = " --category ai" if "ai" in domains else ""
            commands.append(f"guanlan feeds curated{category} --limit 80")
        elif feed == "curated-sources":
            commands.append(f"guanlan feeds curated-sources --keyword {quoted} --limit 80")
        elif feed == "baidu-rss":
            commands.append("guanlan feeds baidu-rss --limit 80")
        elif feed == "wechat-rss":
            commands.append("guanlan feeds wechat-rss --limit 80")

    return _unique(commands)[:6]


def _shell_quote(value: str) -> str:
    escaped = (value or "").replace('"', '\\"')
    return f'"{escaped}"'


def _is_reading_discovery(text: str) -> bool:
    return any(term in text for term in ("值得读", "好文章", "技术文章", "技术博客", "阅读", "精品源", "rss", "opml"))


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
    if "company_primary" in intents:
        output.append("英文产品/公司问题优先核验公司一手资料，再补媒体和社区样本。")
    if "global_policy" in intents:
        output.append("英文政策/监管问题需要官方、监管或标准组织原文作为主证据。")
    if "academic" in intents:
        output.append("学术检索问题需要数据库/出版商口径、会议 CFP 和高校认定口径分开核验。")
    if "standards_compliance" in intents:
        output.append("标准/合规问题需要标准原文、监管解释、实施材料和厂商声明分层引用。")
    if "medical_health" in intents:
        output.append("医疗健康问题需要专业机构、监管和临床指南作主证据，并明确非诊疗建议边界。")
    if "legal_judicial" in intents:
        output.append("法律司法问题需要条文、司法解释、裁判文书和专业解读分开核验。")
    return output


def _domain_reasons(domains: list[str]) -> list[str]:
    return [f"domain:{domain}" for domain in domains]


def _english_scope_equivalents(scopes: list[str]) -> list[str]:
    mapping = {
        "gov": ["global_official"],
        "party_central": ["global_official", "global_news"],
        "local_official": ["global_official", "global_news"],
        "business": ["industry_analysis", "global_news"],
        "ecommerce": ["industry_analysis", "market_review"],
        "tech_dev": ["developer", "community_sample"],
        "finance": ["global_official", "global_news", "company_primary"],
        "social_web": ["community_sample", "market_review"],
    }
    output: list[str] = []
    for scope in scopes:
        output.extend(mapping.get(scope, [scope]))
    return _unique(output)


def _english_site_equivalents(sites: list[str]) -> list[str]:
    replacements = {
        "v2ex.com": [],
        "juejin.cn": [],
        "segmentfault.com": ["stackoverflow.com"],
        "zhihu.com": ["reddit.com"],
        "weibo.com": [],
        "xiaohongshu.com": ["trustpilot.com"],
        "bilibili.com": ["youtube.com"],
        "xueshu.baidu.com": ["scholar.google.com"],
        "cnki.net": [],
    }
    output: list[str] = []
    for site in sites:
        output.extend(replacements.get(site, [site]))
    return _unique(output)


def _confidence(rules: list[dict[str, Any]], **kwargs: Any) -> float:
    score = 0.35 + min(len(rules), 4) * 0.13
    if kwargs.get("scope") or kwargs.get("site") or kwargs.get("sites"):
        score += 0.12
    return round(min(score, 0.92), 2)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term.lower() in text for term in terms)


def _resolve_query_profile(query: str, profile: str | None) -> str | None:
    """Keep English expansion opt-in while preserving China defaults for CJK queries."""
    if profile:
        return profile
    if _contains_cjk(query):
        return "china"
    return profile


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text or "")


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
