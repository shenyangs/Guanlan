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
    seeds: list[dict[str, Any]] = []

    if is_live_sports_lookup(query, intents=intents, scopes=scopes):
        seeds.extend(_sports_seeds(query))
    if _matches_vertical(intent_set, scope_set, "weather_disaster") or _contains_any(text, ("台风", "地震", "气象", "预警", "weather", "typhoon", "earthquake")):
        seeds.extend(_weather_seeds(query))
    if _matches_vertical(intent_set, scope_set, "cybersecurity") or _contains_any(text, ("cve", "漏洞", "补丁", "安全公告", "phishing", "ransomware")):
        seeds.extend(_security_seeds(query))
    if _matches_vertical(intent_set, scope_set, "science") and _contains_any(text, ("nasa", "esa", "jwst", "韦伯", "天文", "外星生命", "science", "nature")):
        seeds.extend(_science_seeds(query))
    if _matches_vertical(intent_set, scope_set, "global_entertainment") or _contains_any(text, ("billboard", "grammy", "hollywood", "taylor swift")):
        seeds.extend(_global_entertainment_seeds(query))
    if _matches_vertical(intent_set, scope_set, "jp_kr_entertainment") or _contains_any(text, ("k-pop", "kpop", "j-pop", "jpop", "oricon", "soompi", "blackpink", "bts")):
        seeds.extend(_jp_kr_entertainment_seeds(query))
    if _matches_vertical(intent_set, scope_set, "entertainment") and _contains_any(text, ("票房", "豆瓣", "评分", "电影", "综艺", "剧集", "游戏")):
        seeds.extend(_china_entertainment_seeds(query))
    if _matches_vertical(intent_set, scope_set, "academic") and _contains_any(text, ("ei", "sci", "scopus", "compendex", "投稿", "收录", "会议", "期刊", "论文")):
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
    for seed in direct_source_seeds(query, intents=intents, scopes=scopes, limit=limit):
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
        ("university_admissions", "university"),
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


def _weather_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("weather:nmc_warning", "中央气象台预警", "http://www.nmc.cn/publish/country/warning.html", "中央气象台全国预警入口，适合核验最新官方预警。", scope="weather_disaster", source_type="天气/灾害/预警", role="official_alert", trust=5),
        _seed("weather:nmc_typhoon", "中央气象台台风路径", "http://typhoon.nmc.cn/web.html", "中央气象台台风路径入口，适合核对台风路径和强度。", scope="weather_disaster", source_type="天气/灾害/预警", role="forecast_track", trust=5),
        _seed("weather:jma_typhoon", "Japan Meteorological Agency typhoon information", "https://www.jma.go.jp/bosai/map.html#contents=typhoon", "日本气象厅台风信息入口，适合跨机构核验路径。", scope="weather_disaster", source_type="天气/灾害/预警", role="forecast_track", trust=5),
        _seed("weather:usgs_earthquake", "USGS Earthquake Map", "https://earthquake.usgs.gov/earthquakes/map/", "USGS 地震实时地图入口，适合核验震级、位置和时间。", scope="weather_disaster", source_type="天气/灾害/预警", role="official_alert", trust=5),
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
    return [
        _seed("ent:douban_movie_search", "豆瓣电影搜索", f"https://search.douban.com/movie/subject_search?search_text={encoded}", "豆瓣电影搜索入口，适合核验评分、条目和用户评论样本。", scope="entertainment", source_type="文娱/内容平台", role="rating_sample", trust=3, read_ready=False),
        _seed("ent:maoyan_boxoffice", "猫眼专业版票房", "https://piaofang.maoyan.com/dashboard", "猫眼专业版票房入口，适合核验票房和市场热度口径。", scope="entertainment", source_type="文娱/内容平台", role="box_office_metric", trust=4),
        _seed("ent:taptap", "TapTap", "https://www.taptap.cn/", "TapTap 游戏条目和玩家样本入口，适合游戏口碑核验。", scope="entertainment", source_type="文娱/内容平台", role="user_sample", trust=3, read_ready=False),
    ]


def _academic_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("academic:engineering_village", "Engineering Village / Compendex", "https://www.elsevier.com/products/engineering-village", "Engineering Village 官方产品入口，适合核验 EI/Compendex 检索口径。", scope="academic", source_type="学术/论文检索", role="database_official", trust=5),
        _seed("academic:scopus", "Scopus", "https://www.scopus.com/", "Scopus 官方入口，适合核验期刊/会议索引，但具体收录需进一步检索。", scope="academic", source_type="学术/论文检索", role="database_official", trust=5),
        _seed("academic:elsevier_conferences", "Elsevier conferences", "https://www.elsevier.com/events/conferences", "Elsevier 会议入口，适合作会议/出版商背景核验。", scope="academic", source_type="学术/论文检索", role="publisher_guideline", trust=4),
    ]


def _test_prep_seeds(query: str) -> list[dict[str, Any]]:
    return [
        _seed("exam:neea", "中国教育考试网", "https://www.neea.edu.cn/", "中国教育考试网官方入口，适合核验国内考试公告和报名信息。", scope="test_prep", source_type="考试/培训/备考", role="official_primary", trust=5),
        _seed("exam:ielts", "IELTS official", "https://ielts.org/", "IELTS 官方入口，适合核验雅思考试政策和题型说明。", scope="test_prep", source_type="考试/培训/备考", role="official_primary", trust=5),
        _seed("exam:ets", "ETS", "https://www.ets.org/", "ETS 官方入口，适合核验 TOEFL/GRE 等考试规则。", scope="test_prep", source_type="考试/培训/备考", role="official_primary", trust=5),
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


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term.lower() in text for term in terms)


def _norm(query: str) -> str:
    return " ".join((query or "").lower().split())


def _extract_cves(query: str) -> list[str]:
    return [match.upper() for match in re.findall(r"\bCVE-\d{4}-\d{4,7}\b", query or "", flags=re.I)]


def _search_url(base: str, query: str, *, param: str = "q") -> str:
    return f"{base}?{urllib.parse.urlencode({param: query})}"
