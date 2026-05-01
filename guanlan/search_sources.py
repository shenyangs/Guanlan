# -*- coding: utf-8 -*-
"""Curated search scopes for China-aware agent research.

The lists are intentionally conservative and human-maintained. They are not a
ranking endorsement; they give agents a safer first pass over recognizable
Chinese public-information sources before widening the search.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SearchScope:
    id: str
    name: str
    description: str
    source_type: str
    trust_level: int
    domains: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


SEARCH_SCOPES: dict[str, SearchScope] = {
    "party_central": SearchScope(
        id="party_central",
        name="党央媒与中央重点媒体",
        description="适合政策、宏观叙事、官方表述和权威报道的第一轮检索。",
        source_type="党央媒",
        trust_level=5,
        domains=(
            "people.com.cn",
            "xinhuanet.com",
            "cctv.com",
            "cntv.cn",
            "qstheory.cn",
            "12371.cn",
            "gmw.cn",
            "ce.cn",
            "cnr.cn",
            "cri.cn",
            "chinanews.com.cn",
            "china.com.cn",
            "chinadaily.com.cn",
        ),
    ),
    "gov": SearchScope(
        id="gov",
        name="政府与部委网站",
        description="适合政策原文、法规、统计、产业主管部门通知和官方公告。",
        source_type="政府/部委",
        trust_level=5,
        domains=(
            "gov.cn",
            "mfa.gov.cn",
            "ndrc.gov.cn",
            "miit.gov.cn",
            "mofcom.gov.cn",
            "mof.gov.cn",
            "stats.gov.cn",
            "samr.gov.cn",
            "pbc.gov.cn",
            "csrc.gov.cn",
            "cac.gov.cn",
        ),
    ),
    "local_official": SearchScope(
        id="local_official",
        name="核心地方官媒",
        description="适合观察地方政策、区域产业、城市治理和地方舆论表述。",
        source_type="地方官媒",
        trust_level=4,
        domains=(
            "bjd.com.cn",
            "jfdaily.com",
            "thepaper.cn",
            "eastday.com",
            "southcn.com",
            "ycwb.com",
            "xhby.net",
            "dzwww.com",
            "dahe.cn",
            "rednet.cn",
            "cnhubei.com",
            "cqnews.net",
            "newssc.org",
            "yunnan.cn",
            "fjnews.com",
            "hinews.cn",
            "gxnews.com.cn",
            "hebnews.cn",
        ),
    ),
    "business": SearchScope(
        id="business",
        name="商业与产业媒体",
        description="适合商业模式、公司动态、一级市场、产业观察和创投报道。",
        source_type="商业/产业媒体",
        trust_level=3,
        domains=(
            "36kr.com",
            "huxiu.com",
            "cyzone.cn",
            "iyiou.com",
            "ebrun.com",
            "tmtpost.com",
            "geekpark.net",
            "pingwest.com",
            "leiphone.com",
            "donews.com",
            "jiemian.com",
            "yicai.com",
        ),
    ),
    "ecommerce": SearchScope(
        id="ecommerce",
        name="电商与零售垂类",
        description="适合电商平台、跨境、品牌零售、新消费和产业带研究。",
        source_type="电商/零售垂类",
        trust_level=3,
        domains=(
            "ebrun.com",
            "iyiou.com",
            "donews.com",
            "jiemian.com",
            "linkshop.com",
            "ccfa.org.cn",
            "100ec.cn",
            "chuhai-club.com",
            "cifnews.com",
            "egainnews.com",
        ),
    ),
    "tech_dev": SearchScope(
        id="tech_dev",
        name="科技与开发者社区",
        description="适合技术趋势、产品反馈、开发者讨论和工程实践。",
        source_type="科技/开发者社区",
        trust_level=3,
        domains=(
            "v2ex.com",
            "juejin.cn",
            "segmentfault.com",
            "csdn.net",
            "cnblogs.com",
            "oschina.net",
            "infoq.cn",
            "51cto.com",
            "sspai.com",
            "ithome.com",
        ),
    ),
    "finance": SearchScope(
        id="finance",
        name="财经与资本市场",
        description="适合财经快讯、上市公司、证券市场、宏观和产业金融。",
        source_type="财经/资本市场",
        trust_level=4,
        domains=(
            "cls.cn",
            "wallstreetcn.com",
            "eastmoney.com",
            "stcn.com",
            "cnstock.com",
            "yicai.com",
            "caixin.com",
            "21jingji.com",
            "jrj.com.cn",
            "xueqiu.com",
        ),
    ),
    "social_web": SearchScope(
        id="social_web",
        name="社交与内容平台公开页",
        description="适合做公开网页层面的口碑、讨论和内容线索搜索。",
        source_type="社交/内容平台",
        trust_level=2,
        domains=(
            "weibo.com",
            "xiaohongshu.com",
            "zhihu.com",
            "bilibili.com",
            "douyin.com",
            "toutiao.com",
            "kuaishou.com",
        ),
    ),
}


SEARCH_SCOPE_ALIASES = {
    "central": "party_central",
    "party": "party_central",
    "official": "gov",
    "local": "local_official",
    "media": "party_central",
    "vertical": "business",
    "biz": "business",
    "retail": "ecommerce",
    "dev": "tech_dev",
    "tech": "tech_dev",
    "social": "social_web",
}


def list_search_scopes() -> dict[str, dict]:
    """Return all curated search scopes as dictionaries."""
    return {key: scope.to_dict() for key, scope in SEARCH_SCOPES.items()}


def resolve_scope(scope_id: str) -> SearchScope:
    """Resolve a scope id or alias."""
    key = (scope_id or "").strip().lower()
    key = SEARCH_SCOPE_ALIASES.get(key, key)
    if key not in SEARCH_SCOPES:
        available = ", ".join(sorted(SEARCH_SCOPES))
        raise ValueError(f"Unknown search scope: {scope_id}. Available: {available}")
    return SEARCH_SCOPES[key]


def scoped_query(query: str, domains: list[str] | tuple[str, ...], max_sites: int = 12) -> str:
    """Build a portable site-restricted query for multiple search engines."""
    selected = [d.strip() for d in domains if d.strip()][:max_sites]
    if not selected:
        return query
    if len(selected) == 1:
        return f"site:{selected[0]} {query}"
    site_expr = " OR ".join(f"site:{domain}" for domain in selected)
    return f"({site_expr}) {query}"


def classify_domain(domain: str, preferred_scope: str | None = None) -> dict:
    """Classify a domain by curated scope membership.

    When a caller already searched within a scope, overlapping domains should
    inherit that requested context. For example, ebrun.com can be both a
    business source and an ecommerce vertical source.
    """
    normalized = (domain or "").lower().removeprefix("www.")
    scopes = list(SEARCH_SCOPES.values())
    if preferred_scope:
        preferred = resolve_scope(preferred_scope)
        scopes = [preferred] + [scope for scope in scopes if scope.id != preferred.id]
    for scope in scopes:
        for candidate in scope.domains:
            if normalized == candidate or normalized.endswith("." + candidate):
                return {
                    "source_type": scope.source_type,
                    "matched_scope": scope.id,
                    "trust_level": scope.trust_level,
                }
    return {
        "source_type": "通用网页",
        "matched_scope": "",
        "trust_level": 1,
    }
