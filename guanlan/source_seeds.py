# -*- coding: utf-8 -*-
"""High-signal source entrypoints for vertical lookup tasks.

These seeds are not treated as final answers. They give agents a small set of
credible pages to read when a query clearly belongs to a vertical where search
engines often underperform or return stale/parser-noisy results.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from guanlan.wps_semantics import (
    WPS_BRAND_TERMS,
    WPS_UNAMBIGUOUS_VERTICAL_TERMS,
    is_wps_office_semantic_query,
)

_LIVE_SPORTS_TERMS = (
    "比分",
    "赛果",
    "战绩",
    "赛程",
    "积分榜",
    "排名",
    "季后赛",
    "首轮",
    "决赛",
    "半决赛",
    "总决赛",
    "playoff",
    "playoffs",
    "score",
    "scores",
    "scoreboard",
    "schedule",
    "standings",
    "bracket",
    "results",
)
_SPORTS_ENTITY_TERMS = (
    "nba",
    "wnba",
    "mlb",
    "nfl",
    "nhl",
    "fifa",
    "uefa",
    "英超",
    "欧冠",
    "世界杯",
    "lpl",
    "电竞",
)
_DEV_EXCLUDE_TERMS = (
    "api",
    "github",
    "sdk",
    "代码",
    "开源",
    "项目",
    "爬虫",
    "预测",
    "模型",
    "教程",
    "benchmark",
)
_FINANCE_ENTITY_TERMS = (
    "股票",
    "股价",
    "行情",
    "指数",
    "板块",
    "涨跌幅",
    "etf",
    "基金",
    "财报",
    "年报",
    "公告",
    "披露",
    "减持",
    "质押",
    "停复牌",
    "监管",
    "处罚",
    "宏观",
    "社融",
    "利率",
    "汇率",
    "外储",
    "雪球",
    "股吧",
    "研报",
    "估值",
    "市盈率",
    "nasdaq",
    "sec",
)
_FINANCE_QUOTE_TERMS = (
    "股价",
    "行情",
    "指数",
    "大盘",
    "涨跌",
    "涨跌幅",
    "板块",
    "排名",
    "盘口",
    "实时",
    "今日",
    "今天",
    "etf",
    "基金净值",
    "quote",
    "stock price",
    "market cap",
)
_FINANCE_DISCLOSURE_TERMS = (
    "公告",
    "披露",
    "财报",
    "年报",
    "季报",
    "减持",
    "质押",
    "停牌",
    "复牌",
    "监管函",
    "处罚",
    "问询函",
    "风险提示",
    "filing",
    "10-k",
    "10-q",
    "sec",
)
_FINANCE_MACRO_TERMS = (
    "宏观",
    "gdp",
    "cpi",
    "ppi",
    "社融",
    "m2",
    "利率",
    "降息",
    "加息",
    "汇率",
    "外储",
    "央行",
    "统计局",
    "fedwatch",
    "lpr",
    "贷款市场报价利率",
    "住房贷款利率",
    "住房公积金贷款利率",
    "商品住宅销售价格",
    "70个大中城市",
    "居民收入和消费支出",
    "支付体系运行总体情况",
    "移动支付",
    "业务金额",
    "业务笔数",
    "逆回购",
    "买断式逆回购",
    "mlf",
    "流动性",
    "资金面",
    "债市",
    "美债收益率",
    "treasury yield",
    "us treasury yield",
)
_FINANCE_SENTIMENT_TERMS = (
    "雪球",
    "股吧",
    "散户",
    "情绪",
    "热议",
    "讨论",
    "看多",
    "看空",
    "舆情",
)
_FINANCE_RESEARCH_TERMS = (
    "研报",
    "券商",
    "机构观点",
    "行业报告",
    "估值",
    "评级",
    "目标价",
    "分析师",
)
_US_TICKER_ALIASES = {
    "英伟达": "NVDA",
    "nvidia": "NVDA",
    "特斯拉": "TSLA",
    "tesla": "TSLA",
    "苹果": "AAPL",
    "apple": "AAPL",
    "微软": "MSFT",
    "microsoft": "MSFT",
    "谷歌": "GOOGL",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "meta": "META",
    "亚马逊": "AMZN",
    "amazon": "AMZN",
}
_US_TICKER_STOPWORDS = {
    "AI",
    "API",
    "APP",
    "CEO",
    "CLI",
    "CPI",
    "CVE",
    "ETF",
    "GDP",
    "GRE",
    "HTML",
    "HTTP",
    "IPO",
    "JSON",
    "LLM",
    "MCP",
    "NBA",
    "PDF",
    "PPI",
    "RSS",
    "SDK",
    "SEC",
    "URL",
    "USD",
    "XML",
}
_WPS_OFFICE_BRAND_TERMS = tuple(WPS_BRAND_TERMS)
_WPS_OFFICE_VERTICAL_TERMS = tuple(WPS_UNAMBIGUOUS_VERTICAL_TERMS)


def direct_source_seeds(
    query: str,
    *,
    intents: list[str] | None = None,
    scopes: list[str] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return direct source candidates for high-confidence vertical tasks."""
    text = _norm(query)
    intent_set = {str(item) for item in intents or [] if str(item)}
    scope_set = {str(item) for item in scopes or [] if str(item)}
    finance_like = is_finance_lookup(query, intents=intents, scopes=scopes)
    seeds: list[dict[str, Any]] = []

    if is_live_sports_lookup(query, intents=intents, scopes=scopes):
        seeds.extend(_sports_seeds(query))
    if is_wps_office_lookup(query, intents=intents, scopes=scopes):
        seeds.extend(_wps_office_seeds(query))
    if finance_like:
        seeds.extend(_finance_seeds(query, intents=intents, scopes=scopes))
    if _matches_vertical(intent_set, scope_set, "weather_disaster") or _contains_any(text, ("台风", "地震", "气象", "预警", "weather", "typhoon", "earthquake")):
        seeds.extend(_weather_seeds(query))
    explicit_policy_like = _matches_vertical(intent_set, scope_set, "policy") or bool(scope_set & {"gov", "party_central", "local_official"})
    if (
        explicit_policy_like
        or (not finance_like and _contains_any(text, ("政策", "通知", "公告", "法规", "意见", "办法", "申报", "指南")))
    ):
        seeds.extend(_policy_official_seeds(query))
    if (
        _matches_vertical(intent_set, scope_set, "legal_judicial")
        or (not finance_like and _contains_any(text, ("法律", "司法解释", "裁判文书", "法院", "纠纷", "婚前财产", "房产加名")))
    ):
        seeds.extend(_legal_official_seeds(query))
    security_terms = ("cve", "漏洞", "补丁", "安全公告", "phishing", "ransomware")
    if "cybersecurity" in intent_set or ("cybersecurity" in scope_set and _contains_any(text, security_terms)) or _contains_any(text, security_terms):
        seeds.extend(_security_seeds(query))
    if _matches_vertical(intent_set, scope_set, "science") and _contains_any(text, ("nasa", "esa", "jwst", "韦伯", "天文", "外星生命", "science", "nature")):
        seeds.extend(_science_seeds(query))
    if _matches_vertical(intent_set, scope_set, "medical_health") or _contains_any(text, ("car-t", "疗法", "适应症", "医保谈判", "药品目录", "nmpa", "cde", "clinical")):
        seeds.extend(_medical_health_seeds(query))
    if _matches_vertical(intent_set, scope_set, "global_entertainment") or _contains_any(text, ("billboard", "grammy", "hollywood", "taylor swift")):
        seeds.extend(_global_entertainment_seeds(query))
    if _matches_vertical(intent_set, scope_set, "jp_kr_entertainment") or _contains_any(text, ("k-pop", "kpop", "j-pop", "jpop", "oricon", "soompi", "blackpink", "bts")):
        seeds.extend(_jp_kr_entertainment_seeds(query))
    if _matches_vertical(intent_set, scope_set, "entertainment") and _contains_any(text, ("票房", "豆瓣", "评分", "电影", "综艺", "剧集", "游戏", "动漫", "漫画", "番剧", "轻小说", "二次元", "manga", "anime", "chiikawa", "吉伊卡哇", "ちいかわ")):
        seeds.extend(_china_entertainment_seeds(query))
    if _matches_vertical(intent_set, scope_set, "academic") and _contains_any(text, ("ei", "sci", "scopus", "compendex", "投稿", "收录", "会议", "期刊", "论文", "paper", "preprint", "arxiv", "预印本")):
        seeds.extend(_academic_seeds(query))
    if _matches_vertical(intent_set, scope_set, "test_prep") or _contains_any(text, ("雅思", "托福", "gre", "ielts", "toefl", "考试", "题库")):
        seeds.extend(_test_prep_seeds(query))
    return _dedupe_seeds(seeds)[: max(limit, 0)]


def direct_source_read_commands(
    query: str,
    *,
    intents: list[str] | None = None,
    scopes: list[str] | None = None,
    limit: int = 3,
    max_chars: int = 12000,
) -> list[str]:
    """Return read commands that should be visible in route plans."""
    commands: list[str] = []
    seed_limit = max(limit * 4, limit)
    for seed in direct_source_seeds(query, intents=intents, scopes=scopes, limit=seed_limit):
        if not seed.get("read_ready", True):
            continue
        url = str(seed.get("url") or "")
        if not url:
            continue
        commands.append(f'guanlan read "{url}" --max-chars {max_chars} --quality-report')
    return commands[: max(limit, 0)]


def is_live_sports_lookup(
    query: str,
    *,
    intents: list[str] | None = None,
    scopes: list[str] | None = None,
) -> bool:
    """Detect sports score/schedule/standings lookups, not sports developer/API tasks."""
    text = _norm(query)
    intent_set = {str(item) for item in intents or [] if str(item)}
    scope_set = {str(item) for item in scopes or [] if str(item)}
    sports_context = "sports" in intent_set or "sports" in scope_set or _contains_any(text, _SPORTS_ENTITY_TERMS)
    if not sports_context:
        return False
    has_live_need = _contains_any(text, _LIVE_SPORTS_TERMS) or _contains_any(text, ("今天", "今日", "最新", "实时"))
    if not has_live_need:
        return False
    if _contains_any(text, _DEV_EXCLUDE_TERMS) and not _contains_any(text, _LIVE_SPORTS_TERMS):
        return False
    return True


def is_finance_lookup(
    query: str,
    *,
    intents: list[str] | None = None,
    scopes: list[str] | None = None,
) -> bool:
    """Detect finance/capital-market tasks that need evidence-layered source seeds."""
    text = _norm(query)
    intent_set = {str(item) for item in intents or [] if str(item)}
    scope_set = {str(item) for item in scopes or [] if str(item)}
    finance_intents = {
        "finance",
        "finance_quote",
        "finance_company",
        "finance_disclosure",
        "finance_news",
        "finance_macro",
        "finance_sentiment",
        "finance_research",
    }
    if finance_intents & intent_set:
        return True
    if (finance_intents - {"finance"}) & scope_set:
        return True
    if _contains_any(text, _FINANCE_ENTITY_TERMS):
        return True
    if _extract_a_share_symbol(query):
        return True
    alias_match = any(term.lower() in text for term in _US_TICKER_ALIASES)
    if alias_match:
        return True
    if _extract_us_tickers(query) and _contains_any(
        text,
        _FINANCE_ENTITY_TERMS + _FINANCE_QUOTE_TERMS + _FINANCE_DISCLOSURE_TERMS,
    ):
        return True
    return False


def is_wps_office_lookup(
    query: str,
    *,
    intents: list[str] | None = None,
    scopes: list[str] | None = None,
) -> bool:
    """Detect WPS/AI Office research tasks that benefit from official entry seeds."""
    intent_set = {str(item) for item in intents or [] if str(item)}
    scope_set = {str(item) for item in scopes or [] if str(item)}
    if _matches_vertical(intent_set, scope_set, "wps_office"):
        return True
    if is_wps_office_semantic_query(query):
        return True
    return False


def dominant_vertical_preset(
    query: str,
    *,
    current_preset: str,
    route_intents: list[str],
) -> str:
    """Return a safer preset when the current one clearly contradicts the query."""
    current = (current_preset or "general").strip().lower()
    if current in {"", "general"}:
        return ""
    intents = [str(item) for item in route_intents if str(item)]
    intent_set = set(intents)
    if current in intent_set:
        return ""
    if current == "university" and "university_admissions" in intent_set:
        return ""
    if is_live_sports_lookup(query, intents=intents):
        return "sports" if current != "sports" else ""
    priority = (
        ("finance_quote", "finance"),
        ("finance_disclosure", "finance"),
        ("finance_company", "finance"),
        ("finance_macro", "finance"),
        ("finance_sentiment", "finance"),
        ("finance_research", "finance"),
        ("finance", "finance"),
        ("university_admissions", "university"),
        ("wps_office", "wps_office"),
        ("weather_disaster", "weather_disaster"),
        ("cybersecurity", "cybersecurity"),
        ("global_entertainment", "global_entertainment"),
        ("jp_kr_entertainment", "jp_kr_entertainment"),
        ("entertainment", "entertainment"),
        ("academic", "academic"),
        ("science", "science"),
        ("career", "career"),
        ("podcast", "podcast"),
        ("test_prep", "test_prep"),
    )
    for intent, preset in priority:
        if intent in intent_set and current != preset:
            return preset
    return ""


def _sports_seeds(query: str) -> list[dict[str, Any]]:
    text = _norm(query)
    seeds: list[dict[str, Any]] = []
    if "nba" in text or "季后赛" in text:
        if "2026" in text and _contains_any(text, ("季后赛", "playoff", "playoffs", "首轮", "bracket")):
            seeds.append(
                _seed(
                    "sports:nba:espn_2026_playoffs",
                    "ESPN NBA Playoffs 2026 schedule, scores and bracket",
                    "https://www.espn.com/nba/story/_/id/48419498/nba-playoffs-2026-play-finals-schedule-scores-news-highlights-bracket-dates",
                    "ESPN 当前季后赛专题页，通常汇总赛程、比分、系列赛大比分、晋级状态和新闻更新。",
                    scope="sports",
                    source_type="体育/赛事/转会",
                    role="official_stat",
                    trust=4,
                )
            )
        seeds.extend(
            [
                _seed(
                    "sports:nba:espn_scoreboard",
                    "ESPN NBA Scoreboard",
                    "https://www.espn.com/nba/scoreboard",
                    "ESPN NBA 实时/近期比分入口，适合核验今日比赛和单场赛果。",
                    scope="sports",
                    source_type="体育/赛事/转会",
                    role="official_stat",
                    trust=4,
                ),
                _seed(
                    "sports:nba:nba_games",
                    "NBA.com Games",
                    "https://www.nba.com/games",
                    "NBA 官方比赛入口，适合核对赛程、对阵、比分和比赛状态。",
                    scope="sports",
                    source_type="体育/赛事/转会",
                    role="official_stat",
                    trust=5,
                ),
                _seed(
                    "sports:nba:nba_playoffs",
                    "NBA.com Playoffs",
                    "https://www.nba.com/playoffs",
                    "NBA 官方季后赛入口，适合核对季后赛赛程、系列赛和官方视频/战报线索。",
                    scope="sports",
                    source_type="体育/赛事/转会",
                    role="official_stat",
                    trust=5,
                ),
            ]
        )
    if _contains_any(text, ("足球", "英超", "欧冠", "fifa", "uefa", "soccer", "football")):
        seeds.extend(
            [
                _seed("sports:soccer:espn_scoreboard", "ESPN Soccer Scoreboard", "https://www.espn.com/soccer/scoreboard", "ESPN 足球比分入口，适合核对近期赛果。", scope="sports", source_type="体育/赛事/转会", role="official_stat", trust=4),
                _seed("sports:soccer:uefa_fixtures", "UEFA Champions League fixtures and results", "https://www.uefa.com/uefachampionsleague/fixtures-results/", "UEFA 官方赛程与赛果入口。", scope="sports", source_type="体育/赛事/转会", role="official_stat", trust=5),
                _seed("sports:soccer:fifa_fixtures", "FIFA scores and fixtures", "https://www.fifa.com/en/tournaments", "FIFA 官方赛事入口，可继续进入对应赛事的赛程和比分页面。", scope="sports", source_type="体育/赛事/转会", role="official_stat", trust=5),
            ]
        )
    return seeds


def _wps_office_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed(
            "wps:official",
            "WPS 官网",
            "https://www.wps.cn/",
            "WPS 官方入口，适合核验产品发布、功能入口、下载和品牌一手表述。",
            scope="wps_office",
            source_type="办公软件/AI Office/SaaS",
            role="company_primary",
            trust=5,
        ),
        _seed(
            "wps:wps365",
            "WPS 365",
            "https://365.wps.cn/",
            "WPS 365 官方入口，适合核验政企协作、AI Office、文档协作和企业办公套件定位。",
            scope="wps_office",
            source_type="办公软件/AI Office/SaaS",
            role="product_primary",
            trust=5,
        ),
        _seed(
            "wps:lingxi",
            "WPS 灵犀",
            "https://lingxi.wps.cn/",
            "WPS 灵犀官方入口，适合核验 AI 原生办公、办公智能体、灵犀 Claw 和移动/跨端 AI 办公定位。",
            scope="wps_office",
            source_type="办公软件/AI Office/SaaS",
            role="product_primary",
            trust=5,
        ),
        _seed(
            "wps:community",
            "WPS 官方社区",
            "https://bbs.wps.cn/",
            "WPS 官方社区入口，适合发现公开用户反馈、功能讨论和产品使用样本；样本不代表总体。",
            scope="wps_office",
            source_type="办公软件/AI Office/SaaS",
            role="user_sample",
            trust=3,
            read_ready=False,
        ),
        _seed(
            "wps:security",
            "金山办公安全中心",
            "https://security.wps.cn/",
            "金山办公安全与合规入口，适合核验办公安全、数据保护和企业信任相关线索。",
            scope="wps_office",
            source_type="办公软件/AI Office/SaaS",
            role="security_advisory",
            trust=4,
        ),
        _seed(
            "wps:kdocs",
            "金山文档",
            "https://www.kdocs.cn/",
            "金山文档产品入口，适合核验在线文档、协作、云文档和公开模板/协作场景线索。",
            scope="wps_office",
            source_type="办公软件/AI Office/SaaS",
            role="collaboration_product",
            trust=4,
        ),
    ]


def _weather_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("weather:nmc_warning", "中央气象台预警", "http://www.nmc.cn/publish/country/warning.html", "中央气象台全国预警入口，适合核验最新官方预警。", scope="weather_disaster", source_type="天气/灾害/预警", role="official_alert", trust=5),
        _seed("weather:nmc_typhoon", "中央气象台台风路径", "http://typhoon.nmc.cn/web.html", "中央气象台台风路径入口，适合核对台风路径和强度。", scope="weather_disaster", source_type="天气/灾害/预警", role="forecast_track", trust=5),
        _seed("weather:jma_typhoon", "Japan Meteorological Agency typhoon information", "https://www.jma.go.jp/bosai/map.html#contents=typhoon", "日本气象厅台风信息入口，适合跨机构核验路径。", scope="weather_disaster", source_type="天气/灾害/预警", role="forecast_track", trust=5),
        _seed("weather:usgs_earthquake", "USGS Earthquake Map", "https://earthquake.usgs.gov/earthquakes/map/", "USGS 地震实时地图入口，适合核验震级、位置和时间。", scope="weather_disaster", source_type="天气/灾害/预警", role="official_alert", trust=5),
    ]


def _policy_official_seeds(query: str) -> list[dict[str, Any]]:
    text = _norm(query)
    seeds = [
        _seed("policy:govcn_zhengce", "中国政府网政策频道", "https://www.gov.cn/zhengce/", "中国政府网政策频道入口，适合核验国家层面政策原文和国务院文件。", scope="gov", source_type="政府/部委", role="official_primary", trust=5),
        _seed("policy:govcn_search", "中国政府网搜索", _search_url("https://sousuo.www.gov.cn/sousuo/search.shtml", query, param="q"), "中国政府网站内搜索入口；适合在搜索引擎漂移时定点查找政策原文。", scope="gov", source_type="政府/部委", role="official_primary", trust=5, read_ready=False),
        _seed("policy:people", "人民网", "https://www.people.com.cn/", "党央媒入口，适合核验政策权威报道和官方表述。", scope="party_central", source_type="党央媒", role="authoritative_report", trust=5),
        _seed("policy:xinhuanet", "新华网", "https://www.news.cn/", "新华社/新华网入口，适合核验政策权威报道和官方表述。", scope="party_central", source_type="党央媒", role="authoritative_report", trust=5),
    ]
    if _contains_any(text, ("横琴", "粤澳", "自贸区", "合作区")):
        seeds.insert(0, _seed("policy:hengqin", "横琴粤澳深度合作区官网", "https://www.hengqin.gov.cn/", "横琴粤澳深度合作区官方入口，适合核验横琴政策、通知、公示和办事信息。", scope="gov", source_type="政府/部委", role="official_primary", trust=5))
        seeds.insert(1, _seed("policy:gd_gov", "广东省人民政府", "https://www.gd.gov.cn/", "广东省人民政府官方入口，适合核验广东及横琴相关政策背景。", scope="gov", source_type="政府/部委", role="official_primary", trust=5))
    city_domains = {
        "佛山": ("policy:foshan", "佛山市人民政府", "https://www.foshan.gov.cn/", "佛山市人民政府官方入口，适合核验佛山地方政策、通知和办事口径。"),
        "广州": ("policy:guangzhou", "广州市人民政府", "https://www.gz.gov.cn/", "广州市人民政府官方入口，适合核验广州地方政策、通知和办事口径。"),
        "深圳": ("policy:shenzhen", "深圳政府在线", "https://www.sz.gov.cn/", "深圳市人民政府官方入口，适合核验深圳地方政策、通知和办事口径。"),
        "珠海": ("policy:zhuhai", "珠海市人民政府", "https://www.zhuhai.gov.cn/", "珠海市人民政府官方入口，适合核验珠海地方政策、通知和办事口径。"),
        "东莞": ("policy:dongguan", "东莞市人民政府", "https://www.dg.gov.cn/", "东莞市人民政府官方入口，适合核验东莞地方政策、通知和办事口径。"),
        "中山": ("policy:zhongshan", "中山市人民政府", "https://www.zs.gov.cn/", "中山市人民政府官方入口，适合核验中山地方政策、通知和办事口径。"),
    }
    for city, (seed_id, title, url, snippet) in city_domains.items():
        if city in query:
            seeds.insert(0, _seed(seed_id, title, url, snippet, scope="gov", source_type="政府/部委", role="official_primary", trust=5))
            break
    return seeds


def _legal_official_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("legal:npc", "中国人大网法律法规库", "https://www.npc.gov.cn/", "中国人大网入口，适合核验法律条文、法律草案和立法信息。", scope="gov", source_type="政府/部委", role="statute_original", trust=5),
        _seed("legal:court", "最高人民法院", "https://www.court.gov.cn/", "最高人民法院入口，适合核验司法解释、指导案例和法院权威信息。", scope="gov", source_type="政府/部委", role="judicial_interpretation", trust=5),
        _seed("legal:moj", "司法部", "https://www.moj.gov.cn/", "司法部入口，适合核验法律法规、普法解读和行政法规信息。", scope="gov", source_type="政府/部委", role="statute_original", trust=5),
        _seed("legal:wenshu", "中国裁判文书网", "https://wenshu.court.gov.cn/", "裁判文书入口，适合查找案例线索；访问和检索能力可能受站点限制。", scope="gov", source_type="政府/部委", role="case_record", trust=5, read_ready=False),
    ]


def _security_seeds(query: str) -> list[dict[str, Any]]:
    cves = _extract_cves(query)
    seeds: list[dict[str, Any]] = []
    for cve in cves[:2]:
        seeds.append(_seed(f"security:nvd:{cve}", f"NVD {cve}", f"https://nvd.nist.gov/vuln/detail/{cve}", "NVD 漏洞详情页，适合核验 CVSS、影响版本、引用和更新时间。", scope="cybersecurity", source_type="网络安全/漏洞/反诈", role="vulnerability_record", trust=5))
        seeds.append(_seed(f"security:cve:{cve}", f"CVE.org {cve}", f"https://www.cve.org/CVERecord?id={cve}", "CVE.org 官方记录，适合核验漏洞编号和 CNA 原始描述。", scope="cybersecurity", source_type="网络安全/漏洞/反诈", role="vulnerability_record", trust=5))
    seeds.extend(
        [
            _seed("security:cisa_kev", "CISA Known Exploited Vulnerabilities Catalog", "https://www.cisa.gov/known-exploited-vulnerabilities-catalog", "CISA KEV 已知被利用漏洞目录，适合判断是否已被在野利用。", scope="cybersecurity", source_type="网络安全/漏洞/反诈", role="security_advisory", trust=5),
            _seed("security:openssl_advisories", "OpenSSL Security Advisories", "https://www.openssl.org/news/secadv/", "OpenSSL 官方安全公告入口，适合核验 OpenSSL 漏洞和修复版本。", scope="cybersecurity", source_type="网络安全/漏洞/反诈", role="vendor_patch", trust=5),
            _seed("security:msrc", "Microsoft Security Response Center", "https://msrc.microsoft.com/update-guide", "Microsoft 安全更新指南，适合核验微软产品漏洞和补丁状态。", scope="cybersecurity", source_type="网络安全/漏洞/反诈", role="vendor_patch", trust=5),
        ]
    )
    return seeds


def _science_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("science:nasa_news", "NASA News", "https://www.nasa.gov/news/", "NASA 官方新闻入口，适合核验 NASA 项目、天文发现和任务动态。", scope="science", source_type="科学机构/科研新闻", role="institution_primary", trust=5),
        _seed("science:esa_news", "ESA News", "https://www.esa.int/Newsroom", "ESA 官方新闻入口，适合与 NASA/论文交叉核验欧洲航天相关信息。", scope="science", source_type="科学机构/科研新闻", role="institution_primary", trust=5),
        _seed("science:arxiv_search", "arXiv Search", _search_url("https://arxiv.org/search/", query, param="query"), "arXiv 搜索入口，适合寻找预印本，但不能等同于同行评议结论。", scope="academic", source_type="学术/论文检索", role="preprint", trust=4),
    ]


def _medical_health_seeds(query: str) -> list[dict[str, Any]]:
    seeds = [
        _seed("medical:nmpa", "国家药监局", "https://www.nmpa.gov.cn/", "国家药监局官方入口，适合核验药品审批、说明书、适应症和监管公告。", scope="medical_health", source_type="政府/部委", role="regulator_notice", trust=5),
        _seed("medical:cde", "国家药监局药审中心", "https://www.cde.org.cn/", "CDE 官方入口，适合核验临床试验、审评进展和药品技术审评线索。", scope="medical_health", source_type="政府/部委", role="clinical_guideline", trust=5),
        _seed("medical:who", "WHO", "https://www.who.int/", "WHO 官方入口，适合核验国际公共卫生、疾病和治疗指导背景。", scope="medical_health", source_type="英文官方/监管", role="clinical_guideline", trust=5),
    ]
    text = _norm(query)
    if _contains_any(text, ("car-t", "疗法", "适应症", "clinical")):
        seeds.append(
            _seed(
                "medical:clinicaltrials",
                "ClinicalTrials.gov",
                _search_url("https://clinicaltrials.gov/search", query, param="term"),
                "ClinicalTrials.gov 公开检索入口，适合核验 CAR-T 等疗法的临床试验和适应症线索。",
                scope="medical_health",
                source_type="学术/论文检索",
                role="peer_review",
                trust=4,
            )
        )
    if _contains_any(text, ("医保", "谈判", "药品目录")):
        seeds.append(
            _seed(
                "medical:nhsa",
                "国家医保局",
                "https://www.nhsa.gov.cn/",
                "国家医保局官方入口，适合核验医保谈判、药品目录调整和支付政策。",
                scope="medical_health",
                source_type="政府/部委",
                role="official_primary",
                trust=5,
            )
        )
    return seeds


def _global_entertainment_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("global_ent:billboard_charts", "Billboard Charts", "https://www.billboard.com/charts/", "Billboard 榜单入口，适合核验欧美音乐榜单和排名。", scope="global_entertainment", source_type="欧美文娱/音乐产业", role="chart_metric", trust=4),
        _seed("global_ent:grammy", "GRAMMY Awards", "https://www.grammy.com/", "格莱美官方入口，适合核验奖项、提名和获奖信息。", scope="global_entertainment", source_type="欧美文娱/音乐产业", role="award_official", trust=5),
        _seed("global_ent:variety", "Variety", "https://variety.com/", "欧美娱乐行业媒体入口，适合影视/音乐产业报道。", scope="global_entertainment", source_type="欧美文娱/音乐产业", role="industry_report", trust=4),
    ]


def _jp_kr_entertainment_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("jpkr:oricon", "Oricon Rankings", "https://www.oricon.co.jp/rank/", "Oricon 日本榜单入口，适合核验 J-pop/J-drama 排名和销量榜单。", scope="jp_kr_entertainment", source_type="日韩文娱/K-pop/J-pop", role="chart_metric", trust=4),
        _seed("jpkr:soompi", "Soompi", "https://www.soompi.com/", "Soompi 英文韩娱报道入口，适合发现 K-pop/K-drama 线索，但需注意翻译层。", scope="jp_kr_entertainment", source_type="日韩文娱/K-pop/J-pop", role="translation_report", trust=3),
        _seed("jpkr:naver_ent", "Naver Entertainment", "https://entertain.naver.com/home", "Naver 韩娱入口，适合核验韩国本地媒体报道和经纪公司动态线索。", scope="jp_kr_entertainment", source_type="日韩文娱/K-pop/J-pop", role="local_media", trust=4),
    ]


def _china_entertainment_seeds(query: str) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(query)
    seeds = [
        _seed("ent:douban_movie_search", "豆瓣电影搜索", f"https://search.douban.com/movie/subject_search?search_text={encoded}", "豆瓣电影搜索入口，适合核验评分、条目和用户评论样本。", scope="entertainment", source_type="文娱/内容平台", role="rating_sample", trust=3, read_ready=False),
        _seed("ent:maoyan_boxoffice", "猫眼专业版票房", "https://piaofang.maoyan.com/dashboard", "猫眼专业版票房入口，适合核验票房和市场热度口径。", scope="entertainment", source_type="文娱/内容平台", role="box_office_metric", trust=4),
        _seed("ent:taptap", "TapTap", "https://www.taptap.cn/", "TapTap 游戏条目和玩家样本入口，适合游戏口碑核验。", scope="entertainment", source_type="文娱/内容平台", role="user_sample", trust=3, read_ready=False),
    ]
    if _contains_any(_norm(query), ("动漫", "漫画", "番剧", "轻小说", "二次元", "魔女", "学园", "治愈", "日常", "manga", "anime", "chiikawa", "吉伊卡哇", "ちいかわ")):
        seeds.extend(
            [
                _seed("ent:bangumi_subject", "Bangumi 条目搜索", f"https://bgm.tv/subject_search/{encoded}?cat=1", "Bangumi 条目搜索入口，适合发现漫画/动画条目、标签和公开口碑线索。", scope="entertainment", source_type="文娱/内容平台", role="catalog_entry", trust=4, read_ready=False),
                _seed("ent:pixiv_tag", "Pixiv 标签入口", f"https://www.pixiv.net/tags/{encoded}/artworks", "Pixiv 标签入口，适合发现漫画/插画/角色标签和创作者样本。", scope="entertainment", source_type="文娱/内容平台", role="creator_sample", trust=3, read_ready=False),
                _seed("ent:mangapedia", "MangaPedia", "https://mangapedia.com/", "MangaPedia 公开百科入口，适合核验漫画作品简介和推荐线索。", scope="entertainment", source_type="文娱/内容平台", role="catalog_entry", trust=4, read_ready=False),
                _seed("ent:manba", "マンバ", "https://manba.co.jp/", "マンバ漫画推荐入口，适合发现漫画题材清单和公开推荐样本。", scope="entertainment", source_type="文娱/内容平台", role="recommendation_sample", trust=3, read_ready=False),
            ]
        )
    return seeds


def _academic_seeds(query: str) -> list[dict[str, Any]]:
    seeds = [
        _seed("academic:engineering_village", "Engineering Village / Compendex", "https://www.elsevier.com/products/engineering-village", "Engineering Village 官方产品入口，适合核验 EI/Compendex 检索口径。", scope="academic", source_type="学术/论文检索", role="database_official", trust=5),
        _seed("academic:scopus", "Scopus", "https://www.scopus.com/", "Scopus 官方入口，适合核验期刊/会议索引，但具体收录需进一步检索。", scope="academic", source_type="学术/论文检索", role="database_official", trust=5),
        _seed("academic:elsevier_conferences", "Elsevier conferences", "https://www.elsevier.com/events/conferences", "Elsevier 会议入口，适合作会议/出版商背景核验。", scope="academic", source_type="学术/论文检索", role="publisher_guideline", trust=4),
    ]
    if _contains_any(_norm(query), ("arxiv", "预印本", "preprint", "paper", "论文", "机器学习", "machine learning", "ai", "agent")):
        seeds.insert(
            0,
            _seed(
                "academic:arxiv_api",
                "arXiv public API",
                _search_url("https://arxiv.org/search/", query, param="query"),
                "arXiv 公开检索入口，适合寻找预印本和论文线索；预印本不能直接等同于同行评议结论。",
                scope="academic",
                source_type="学术/论文检索",
                role="preprint_record",
                trust=4,
            ),
        )
    return seeds


def _test_prep_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("exam:neea", "中国教育考试网", "https://www.neea.edu.cn/", "中国教育考试网官方入口，适合核验国内考试公告和报名信息。", scope="test_prep", source_type="考试/培训/备考", role="official_primary", trust=5),
        _seed("exam:ielts", "IELTS official", "https://ielts.org/", "IELTS 官方入口，适合核验雅思考试政策和题型说明。", scope="test_prep", source_type="考试/培训/备考", role="official_primary", trust=5),
        _seed("exam:ets", "ETS", "https://www.ets.org/", "ETS 官方入口，适合核验 TOEFL/GRE 等考试规则。", scope="test_prep", source_type="考试/培训/备考", role="official_primary", trust=5),
    ]


def _finance_seeds(
    query: str,
    *,
    intents: list[str] | None = None,
    scopes: list[str] | None = None,
) -> list[dict[str, Any]]:
    text = _norm(query)
    intent_set = {str(item) for item in intents or [] if str(item)}
    scope_set = {str(item) for item in scopes or [] if str(item)}
    seeds: list[dict[str, Any]] = []
    wants_quote = _matches_any_finance(intent_set, scope_set, "finance_quote") or _contains_any(text, _FINANCE_QUOTE_TERMS)
    wants_disclosure = (
        _matches_any_finance(intent_set, scope_set, "finance_disclosure", "finance_company")
        or _contains_any(text, _FINANCE_DISCLOSURE_TERMS)
    )
    wants_macro = _matches_any_finance(intent_set, scope_set, "finance_macro") or _contains_any(text, _FINANCE_MACRO_TERMS)
    wants_sentiment = _matches_any_finance(intent_set, scope_set, "finance_sentiment") or _contains_any(text, _FINANCE_SENTIMENT_TERMS)
    wants_research = _matches_any_finance(intent_set, scope_set, "finance_research") or _contains_any(text, _FINANCE_RESEARCH_TERMS)
    if "finance" in intent_set or "finance" in scope_set:
        wants_disclosure = wants_disclosure or _contains_any(text, ("公司", "最近", "怎么样", "风险", "财报", "公告"))
        wants_news = True
    else:
        wants_news = _matches_any_finance(intent_set, scope_set, "finance_news") or _contains_any(text, ("财经", "快讯", "新闻", "事件", "大跌", "上涨", "下跌"))

    if wants_quote:
        seeds.extend(_finance_quote_seeds(query))
    if wants_disclosure:
        seeds.extend(_finance_disclosure_seeds(query))
    if wants_macro:
        seeds.extend(_finance_macro_seeds(query))
    if wants_news:
        seeds.extend(_finance_news_seeds(query))
    if wants_sentiment:
        seeds.extend(_finance_sentiment_seeds(query))
    if wants_research:
        seeds.extend(_finance_research_seeds(query))
    if not seeds:
        seeds.extend(_finance_disclosure_seeds(query)[:2])
        seeds.extend(_finance_news_seeds(query)[:2])
    return seeds


def _finance_quote_seeds(query: str) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = [
        _seed("finance:quote:eastmoney_board", "东方财富行情中心", "https://quote.eastmoney.com/center/gridlist.html#hs_a_board", "A 股行情和板块入口，适合发现指数、涨跌幅和板块排名；页面多为动态渲染，需注意延迟和读取方式。", scope="finance_quote", source_type="财经/行情数据", role="market_quote", trust=3, read_ready=False),
        _seed("finance:quote:sina", "新浪财经行情中心", "https://finance.sina.com.cn/realstock/company/sh000001/nc.shtml", "公开行情页面入口，适合核验指数和个股行情线索；强实时结论需标注时间和来源。", scope="finance_quote", source_type="财经/行情数据", role="market_quote", trust=3, read_ready=False),
        _seed("finance:quote:xueqiu", "雪球行情与讨论", "https://xueqiu.com/", "雪球行情和投资者讨论入口，行情/热股可用但常依赖 Cookie；讨论只作情绪样本。", scope="finance_sentiment", source_type="财经/情绪样本", role="sentiment_sample", trust=2, read_ready=False),
    ]
    a_share = _extract_a_share_symbol(query)
    if a_share:
        prefix = "sh" if a_share.startswith(("5", "6", "9")) else "sz"
        seeds.insert(0, _seed(f"finance:quote:eastmoney:{prefix}{a_share}", f"东方财富 {prefix.upper()}{a_share} 行情", f"https://quote.eastmoney.com/{prefix}{a_share}.html", "东方财富个股行情入口；适合让 Agent 定点核验价格、涨跌幅和交易状态，但必须标注时间/延迟。", scope="finance_quote", source_type="财经/行情数据", role="market_quote", trust=3, read_ready=False))
        seeds.insert(1, _seed(f"finance:quote:xueqiu:{prefix}{a_share}", f"雪球 {prefix.upper()}{a_share}", f"https://xueqiu.com/S/{prefix.upper()}{a_share}", "雪球个股入口，适合行情和讨论样本；情绪不可作为事实主证据。", scope="finance_sentiment", source_type="财经/情绪样本", role="sentiment_sample", trust=2, read_ready=False))
    for ticker in _extract_us_tickers(query)[:2]:
        seeds.append(_seed(f"finance:quote:yahoo:{ticker}", f"Yahoo Finance {ticker}", f"https://finance.yahoo.com/quote/{urllib.parse.quote(ticker)}", "Yahoo Finance 美股行情入口，适合核验价格、财务摘要和相关新闻；需标注时间和可能延迟。", scope="finance_quote", source_type="财经/行情数据", role="market_quote", trust=3, read_ready=False))
        seeds.append(_seed(f"finance:quote:nasdaq:{ticker}", f"Nasdaq {ticker}", f"https://www.nasdaq.com/market-activity/stocks/{urllib.parse.quote(ticker.lower())}", "Nasdaq 个股市场数据入口，适合美股行情与公司资料核验。", scope="finance_quote", source_type="财经/行情数据", role="market_quote", trust=4, read_ready=False))
    return seeds


def _finance_disclosure_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("finance:disclosure:cninfo", "巨潮资讯公告检索", "https://www.cninfo.com.cn/new/index", "A 股上市公司公告和定期报告入口；适合核验财报、减持、质押、问询和风险披露。", scope="finance_disclosure", source_type="财经/公告披露", role="company_filing", trust=5),
        _seed("finance:disclosure:sse", "上交所上市公司公告", "https://www.sse.com.cn/disclosure/listedinfo/announcement/", "上交所官方公告入口；适合核验沪市公告、监管和停复牌等事项。", scope="finance_disclosure", source_type="财经/公告披露", role="exchange_announcement", trust=5),
        _seed("finance:disclosure:szse", "深交所上市公司公告", "https://www.szse.cn/disclosure/listed/notice/index.html", "深交所官方公告入口；适合核验深市公告、监管和风险提示。", scope="finance_disclosure", source_type="财经/公告披露", role="exchange_announcement", trust=5),
        _seed("finance:disclosure:hkexnews", "HKEXnews 披露易", "https://www.hkexnews.hk/index_c.htm", "港股公告披露入口；适合核验港股上市公司公告和监管披露。", scope="finance_disclosure", source_type="财经/公告披露", role="exchange_announcement", trust=5),
        _seed("finance:disclosure:sec_edgar", "SEC EDGAR Company Search", "https://www.sec.gov/edgar/search/", "SEC EDGAR 官方检索入口；适合核验美股 10-K、10-Q、8-K 等披露。", scope="finance_disclosure", source_type="财经/公告披露", role="company_filing", trust=5),
    ]


def _finance_macro_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("finance:macro:nbs", "国家统计局", "https://www.stats.gov.cn/", "中国官方统计数据入口；适合核验 GDP、CPI、PPI、工业、人口等宏观数据。", scope="finance_macro", source_type="财经/宏观数据", role="macro_data", trust=5),
        _seed("finance:macro:pbc", "中国人民银行", "https://www.pbc.gov.cn/", "央行政策、社融、货币金融统计和利率政策入口。", scope="finance_macro", source_type="财经/宏观数据", role="central_bank_notice", trust=5),
        _seed("finance:macro:safe", "国家外汇管理局", "https://www.safe.gov.cn/", "外汇、国际收支和外储等官方数据入口。", scope="finance_macro", source_type="财经/宏观数据", role="macro_data", trust=5),
        _seed("finance:macro:fred", "FRED Economic Data", "https://fred.stlouisfed.org/", "美国宏观经济数据入口，适合核验利率、通胀和就业等指标。", scope="finance_macro", source_type="财经/宏观数据", role="macro_data", trust=5),
        _seed("finance:macro:cme_fedwatch", "CME FedWatch", "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html", "市场隐含美联储利率概率入口；这是市场定价指标，不等于政策决定。", scope="finance_macro", source_type="财经/宏观数据", role="market_expectation", trust=4),
    ]


def _finance_news_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("finance:news:cls", "财联社", "https://www.cls.cn/", "财经快讯和市场事件入口；适合发现近期事件，需和公告/监管源交叉验证。", scope="finance_news", source_type="财经/新闻报道", role="market_news", trust=3, read_ready=False),
        _seed("finance:news:stcn", "证券时报网", "https://www.stcn.com/", "证券时报财经报道入口，适合公司新闻和市场事件核验。", scope="finance_news", source_type="财经/新闻报道", role="market_news", trust=4, read_ready=False),
        _seed("finance:news:cnstock", "上海证券报中国证券网", "https://www.cnstock.com/", "上证报财经报道入口，适合资本市场和公司新闻核验。", scope="finance_news", source_type="财经/新闻报道", role="market_news", trust=4, read_ready=False),
        _seed("finance:news:yicai", "第一财经", "https://www.yicai.com/", "财经新闻和商业报道入口，适合市场事件和产业背景。", scope="finance_news", source_type="财经/新闻报道", role="market_news", trust=4, read_ready=False),
    ]


def _finance_sentiment_seeds(query: str) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(query)
    return [
        _seed("finance:sentiment:xueqiu_search", "雪球搜索", f"https://xueqiu.com/k?q={encoded}", "雪球公开讨论入口；只作投资者情绪和争议样本，不作事实主证据。", scope="finance_sentiment", source_type="财经/情绪样本", role="sentiment_sample", trust=2, read_ready=False),
        _seed("finance:sentiment:guba", "东方财富股吧", f"https://guba.eastmoney.com/search.html?keyword={encoded}", "股吧讨论入口；适合观察散户情绪、传言和争议，不代表事实或总体比例。", scope="finance_sentiment", source_type="财经/情绪样本", role="sentiment_sample", trust=2, read_ready=False),
        _seed("finance:sentiment:weibo", "微博搜索", f"https://s.weibo.com/weibo?q={encoded}", "微博公开讨论入口；适合观察舆情，不作投资或事实主证据。", scope="finance_sentiment", source_type="财经/情绪样本", role="sentiment_sample", trust=2, read_ready=False),
    ]


def _finance_research_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("finance:research:eastmoney_report", "东方财富研报中心", "https://data.eastmoney.com/report/", "研报聚合入口；适合发现机构观点，但观点需和公告、财报、行业数据交叉验证。", scope="finance_research", source_type="财经/研报观点", role="analyst_opinion", trust=3, read_ready=False),
        _seed("finance:research:iresearch", "艾瑞咨询", "https://www.iresearch.com.cn/", "行业报告入口；适合产业和市场规模背景，不替代上市公司公告。", scope="finance_research", source_type="财经/研报观点", role="industry_report", trust=3, read_ready=False),
        _seed("finance:research:199it", "199IT 数据资讯", "https://www.199it.com/", "行业数据和报告线索入口；需要核验原报告来源和方法。", scope="finance_research", source_type="财经/研报观点", role="industry_report", trust=2, read_ready=False),
    ]


def _seed(
    seed_id: str,
    title: str,
    url: str,
    snippet: str,
    *,
    scope: str,
    source_type: str,
    role: str,
    trust: int,
    read_ready: bool = True,
) -> dict[str, Any]:
    return {
        "seed_id": seed_id,
        "title": title,
        "url": url,
        "snippet": snippet,
        "source": "direct_source",
        "matched_scope": scope,
        "source_type": source_type,
        "evidence_role": role,
        "trust_level": trust,
        "read_ready": read_ready,
    }


def _dedupe_seeds(seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for seed in seeds:
        url = str(seed.get("url") or "").strip()
        key = url.lower().rstrip("/")
        if not url or key in seen:
            continue
        seen.add(key)
        output.append(seed)
    return output


def _matches_vertical(intent_set: set[str], scope_set: set[str], name: str) -> bool:
    return name in intent_set or name in scope_set


def _matches_any_finance(intent_set: set[str], scope_set: set[str], *names: str) -> bool:
    return bool(set(names) & (intent_set | scope_set))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term.lower() in text for term in terms)


def _norm(query: str) -> str:
    return " ".join((query or "").lower().split())


def _extract_cves(query: str) -> list[str]:
    return [match.upper() for match in re.findall(r"\bCVE-\d{4}-\d{4,7}\b", query or "", flags=re.I)]


def _extract_a_share_symbol(query: str) -> str:
    text = query or ""
    match = re.search(r"(?<!\d)(?:sh|sz)?([035689]\d{5})(?!\d)", text, flags=re.I)
    if not match:
        return ""
    return match.group(1)


def _extract_us_tickers(query: str) -> list[str]:
    text = query or ""
    lowered = text.lower()
    tickers: list[str] = []
    for term, ticker in _US_TICKER_ALIASES.items():
        if term.lower() in lowered:
            tickers.append(ticker)
    for match in re.findall(r"\b[A-Z]{1,5}\b", text):
        ticker = match.upper()
        if ticker in _US_TICKER_STOPWORDS:
            continue
        tickers.append(ticker)
    output: list[str] = []
    seen: set[str] = set()
    for ticker in tickers:
        if ticker in seen:
            continue
        seen.add(ticker)
        output.append(ticker)
    return output


def _search_url(base: str, query: str, *, param: str = "q") -> str:
    return f"{base}?{urllib.parse.urlencode({param: query})}"
