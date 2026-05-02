# -*- coding: utf-8 -*-
"""Curated search scopes for agent research.

The lists are intentionally conservative and human-maintained. They are not a
ranking endorsement; they give agents a safer first pass over recognizable
public-information sources before widening the search.
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
            "nhc.gov.cn",
            "nmpa.gov.cn",
            "moj.gov.cn",
            "court.gov.cn",
            "npc.gov.cn",
            "wenshu.court.gov.cn",
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
    "academic": SearchScope(
        id="academic",
        name="学术与论文检索",
        description="适合论文投稿、学术会议、EI/SCI/Scopus 检索、出版商规范和高校认定口径。",
        source_type="学术/论文检索",
        trust_level=4,
        domains=(
            "elsevier.com",
            "engineeringvillage.com",
            "sciencedirect.com",
            "ieee.org",
            "acm.org",
            "springer.com",
            "webofscience.com",
            "clarivate.com",
            "cnki.net",
            "wanfangdata.com.cn",
            "cqvip.com",
            "xueshu.baidu.com",
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
    "entertainment": SearchScope(
        id="entertainment",
        name="文娱与内容消费",
        description="适合影视、综艺、音乐、游戏、明星、票房、播放热度和公开口碑的第一轮路由。",
        source_type="文娱/内容平台",
        trust_level=3,
        domains=(
            "douban.com",
            "maoyan.com",
            "piaofang.maoyan.com",
            "lighthouse.alibaba.com",
            "taopiaopiao.com",
            "mtime.com",
            "1905.com",
            "bilibili.com",
            "weibo.com",
            "v.qq.com",
            "iqiyi.com",
            "youku.com",
            "mgtv.com",
            "taptap.cn",
            "gamersky.com",
            "3dmgame.com",
            "ign.com.cn",
            "indienova.com",
        ),
    ),
    "global_official": SearchScope(
        id="global_official",
        name="英文官方/监管与公共机构",
        description="适合政策、监管、标准、统计、司法和公共卫生等英文一手来源核验。",
        source_type="英文官方/监管",
        trust_level=5,
        domains=(
            "usa.gov",
            "whitehouse.gov",
            "congress.gov",
            "federalregister.gov",
            "sec.gov",
            "ftc.gov",
            "fda.gov",
            "nist.gov",
            "iso.org",
            "iec.ch",
            "cdc.gov",
            "who.int",
            "oecd.org",
            "worldbank.org",
            "europa.eu",
            "ec.europa.eu",
        ),
    ),
    "company_primary": SearchScope(
        id="company_primary",
        name="公司一手资料",
        description="适合产品、价格、发布说明、状态页、投资者关系和官方博客核验。",
        source_type="公司一手资料",
        trust_level=5,
        domains=(
            "openai.com",
            "anthropic.com",
            "googleblog.com",
            "blog.google",
            "microsoft.com",
            "azure.microsoft.com",
            "aws.amazon.com",
            "aboutamazon.com",
            "meta.com",
            "ai.meta.com",
            "nvidia.com",
            "apple.com",
            "tesla.com",
            "stripe.com",
            "shopify.com",
        ),
    ),
    "developer": SearchScope(
        id="developer",
        name="英文开发者与开源",
        description="适合官方文档、代码仓库、issue、release notes、工程实践和开发者反馈。",
        source_type="英文开发者/开源",
        trust_level=4,
        domains=(
            "github.com",
            "docs.github.com",
            "stackoverflow.com",
            "developer.mozilla.org",
            "docs.python.org",
            "nodejs.org",
            "npmjs.com",
            "pypi.org",
            "kubernetes.io",
            "docs.docker.com",
            "cloudflare.com",
            "vercel.com",
        ),
    ),
    "global_news": SearchScope(
        id="global_news",
        name="国际主流新闻",
        description="适合事实报道、时间线和多方说法核验；注意编辑立场和付费墙。",
        source_type="国际主流媒体",
        trust_level=4,
        domains=(
            "reuters.com",
            "apnews.com",
            "bbc.com",
            "cnn.com",
            "nytimes.com",
            "washingtonpost.com",
            "theguardian.com",
            "ft.com",
            "wsj.com",
            "bloomberg.com",
            "theverge.com",
            "technologyreview.com",
        ),
    ),
    "industry_analysis": SearchScope(
        id="industry_analysis",
        name="英文产业与分析",
        description="适合产业判断、商业分析、投资观点和市场结构线索；需和一手来源交叉验证。",
        source_type="英文产业/分析",
        trust_level=3,
        domains=(
            "gartner.com",
            "forrester.com",
            "mckinsey.com",
            "bain.com",
            "bcg.com",
            "a16z.com",
            "stratechery.com",
            "theinformation.com",
            "semianalysis.com",
            "ben-evans.com",
        ),
    ),
    "community_sample": SearchScope(
        id="community_sample",
        name="英文社区样本",
        description="适合公开讨论、开发者/用户样本和争议线索；不能代表总体比例。",
        source_type="英文社区样本",
        trust_level=2,
        domains=(
            "reddit.com",
            "news.ycombinator.com",
            "lobste.rs",
            "medium.com",
            "dev.to",
            "producthunt.com",
            "quora.com",
        ),
    ),
    "market_review": SearchScope(
        id="market_review",
        name="英文评价与消费样本",
        description="适合 SaaS、应用、消费品和服务评价样本；注意商业激励和刷评偏差。",
        source_type="评价/消费样本",
        trust_level=2,
        domains=(
            "g2.com",
            "capterra.com",
            "trustpilot.com",
            "trustradius.com",
            "amazon.com",
            "apps.apple.com",
            "play.google.com",
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
    "scholar": "academic",
    "academic": "academic",
    "paper": "academic",
    "social": "social_web",
    "global-gov": "global_official",
    "global_gov": "global_official",
    "regulator": "global_official",
    "regulation": "global_official",
    "standards": "global_official",
    "company": "company_primary",
    "vendor": "company_primary",
    "primary": "company_primary",
    "docs": "developer",
    "developer": "developer",
    "opensource": "developer",
    "open-source": "developer",
    "news": "global_news",
    "media_global": "global_news",
    "analysis": "industry_analysis",
    "industry_global": "industry_analysis",
    "community": "community_sample",
    "reddit": "community_sample",
    "reviews": "market_review",
    "review": "market_review",
    "saas-review": "market_review",
    "entertainment": "entertainment",
    "culture": "entertainment",
    "wenyu": "entertainment",
    "yule": "entertainment",
    "movie": "entertainment",
    "film": "entertainment",
    "tv": "entertainment",
    "music": "entertainment",
    "game": "entertainment",
    "gaming": "entertainment",
    "douban": "entertainment",
    "maoyan": "entertainment",
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
