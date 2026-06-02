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

from guanlan.limits import (
    DEFAULT_FEEDS_LIMIT,
    DEFAULT_HOTNEWS_LIMIT,
    DEFAULT_PULSE_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    MAX_AGENT_RESEARCH_READ_TOP,
)
from guanlan.query_semantics import analyze_query_semantics, semantic_query_variants
from guanlan.source_seeds import direct_source_read_commands
from guanlan.wps_semantics import (
    WPS_OFFICE_TERMS,
    analyze_wps_semantics,
    wps_office_subroute,
    wps_route_query_variants,
    wps_semantic_summary,
)

_ROBOTICS_AI_TERMS = (
    "具身智能",
    "具身",
    "人形机器人",
    "机器人",
    "智元",
    "宇树",
    "傅利叶",
    "银河通用",
    "逐际动力",
    "灵巧手",
    "双足",
    "sim2real",
    "端到端",
    "触觉感知",
    "embodied ai",
    "humanoid robot",
    "humanoid",
    "robotics",
)

_WPS_OFFICE_TERMS = tuple(WPS_OFFICE_TERMS)


def _wps_office_subroute(query: str) -> str:
    """Classify WPS market queries into distinct topic lanes."""
    return wps_office_subroute(query)


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
    wps_lanes: list[str] = field(default_factory=list)
    wps_semantic_matches: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_INTENT_RULES: tuple[dict[str, Any], ...] = (
    {
        "intent": "policy",
        "terms": (
            "政策",
            "监管",
            "法规",
            "通知",
            "办法",
            "意见",
            "征求意见",
            "专项整治",
            "录用公示",
            "部委",
            "国务院",
            "教育部",
            "双一流",
            "一流学科建设高校",
            "选调生",
            "公务员",
            "电子税务局",
            "燃气安全",
            "充装站",
            "瓶安",
            "工信部",
            "无障碍环境建设法",
            "信息无障碍",
            "适老化",
            "公共场所数字化指示",
            "yd/t",
            "非遗",
            "非物质文化遗产",
            "非遺",
            "制香",
            "申报政策",
            "申報政策",
            "数字素养",
            "全民数字素养",
            "提升全民数字素养与技能",
            "中央网信办",
            "网信办",
            "教师职称",
            "职称评审",
            "副高评审",
            "课题申报",
            "学术伦理",
            "数据安全法",
            "个人信息保护法",
            "爬虫合规",
            "专精特新",
            "备案",
            "合规",
            "住房公积金",
            "住房公积金贷款",
            "公积金贷款",
            "首套房",
            "最低首付比例",
            "最低首付款比例",
            "个人住房贷款",
            "商业性个人住房贷款",
            "房地产市场平稳健康发展",
            "税收政策",
            "契税",
            "财政部",
            "税务总局",
            "金融监督管理总局",
            "国家金融监督管理总局",
            "支付体系运行总体情况",
            "非银行支付机构网络支付业务管理办法",
            "支付账户",
            "中医药振兴发展重大工程",
            "中医药振兴发展重大工程实施方案",
            "中医药传承创新发展",
            "中医药文化",
            "中医养生保健服务规范",
            "医疗广告管理办法",
            "广告法",
            "中医药法",
            "不得保证治愈",
            "不得从事医疗活动",
            "国家中医药管理局",
            "国家市场监督管理总局",
        ),
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
            "uscis",
            "h1b",
            "h-1b",
            "visa",
            "申根",
            "签证",
            "移民",
            "出口管制",
            "cbam",
            "拥堵费",
            "congestion pricing",
            "欧洲无障碍法案",
            "eaa",
            "european accessibility act",
            "eu accessibility",
            "eur-lex",
            "uk eu trade",
            "brexit reset",
            "diplomatic relations",
            "starmer",
            "reform uk",
            "uk politics",
            "immigration bill",
            "英国移民法案",
            "欧盟贸易",
            "斯塔默",
            "改革党",
            "反倾销",
            "anti-dumping",
            "antidumping",
            "ad commission",
            "反补贴",
            "anti-subsidy",
            "countervailing",
            "关税税率",
            "军事演习",
            "军事部署",
            "西南诸岛",
            "地缘政治",
        ),
        "scopes": ("global_official", "global_news"),
        "fallback": ("industry_analysis", "community_sample"),
        "sites": ("ec.europa.eu", "eur-lex.europa.eu", "europa.eu", "w3.org"),
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
            "无障碍",
            "信息无障碍",
            "适老化",
            "大字模式",
            "大字体",
            "wcag",
            "eaa",
            "yd/t",
            "字体大小",
            "字号",
            "对比度",
            "公共场所数字化指示",
            "accessibility",
        ),
        "scopes": ("global_official", "gov", "company_primary", "academic"),
        "fallback": ("developer", "industry_analysis", "business"),
        "sites": (
            "iso.org",
            "iec.ch",
            "nist.gov",
            "samr.gov.cn",
            "std.samr.gov.cn",
            "tc260.org.cn",
            "miit.gov.cn",
            "w3.org",
            "ec.europa.eu",
            "eur-lex.europa.eu",
        ),
        "roles": ("standard_original", "regulator_guidance", "implementation_context", "vendor_claim"),
        "warning": "标准/合规问题应区分标准原文、监管解释、厂商声明和实施经验；博客只能作落地参考。",
    },
    {
        "intent": "cybersecurity",
        "terms": (
            "cve",
            "漏洞",
            "补丁",
            "安全公告",
            "安全更新",
            "修复版本",
            "影响版本",
            "openssl",
            "log4j",
            "钓鱼",
            "诈骗",
            "短信链接",
            "诈骗短信",
            "反诈",
            "骗局",
            "欺诈",
            "木马",
            "勒索",
            "phishing",
            "vulnerability",
            "exploit",
            "security advisory",
            "patch",
            "mitigation",
            "nvd",
            "cisa",
            "cnvd",
            "cnnvd",
            "prompt injection",
            "indirect prompt injection",
            "tool calling attack",
            "agent security",
            "malicious skill",
            "mcp attack",
            "pre-authenticated download links",
            "copilot cowork",
            "postgresql",
            "postgres",
            "security update",
            "security updates",
        ),
        "scopes": ("cybersecurity", "developer", "global_official"),
        "fallback": ("gov", "global_news", "tech_dev"),
        "sites": ("nvd.nist.gov", "cisa.gov", "cnvd.org.cn", "cnnvd.org.cn", "openssl.org", "msrc.microsoft.com"),
        "roles": ("security_advisory", "vulnerability_record", "vendor_patch", "official_warning"),
        "warning": "网络安全/反诈问题应优先 CVE/厂商公告/监管或公安反诈来源；论坛和自媒体只能作复现或样本线索。",
    },
    {
        "intent": "medical_health",
        "terms": (
            "医疗",
            "疾病",
            "药",
            "药品",
            "治疗",
            "治未病",
            "中医药",
            "中医养生",
            "中医养生保健",
            "宣传疗效",
            "医疗广告",
            "诊断",
            "症状",
            "临床",
            "指南",
            "医生",
            "医院",
            "副作用",
            "适应症",
            "禁忌",
            "孕期",
            "怀孕",
            "孕妇",
            "哺乳",
            "布洛芬",
            "肺结节",
            "肌酸",
            "视黄醇",
            "早c晚a",
            "敏感肌",
            "猫咪",
            "宠物医院",
            "呕吐",
            "要不要手术",
            "能不能吃",
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
            "判例",
            "合同",
            "律师",
            "侵权",
            "司法解释",
            "房产纠纷",
            "婚前财产",
            "财产纠纷",
            "房产加名",
            "纠纷",
            "劳动仲裁",
            "仲裁",
            "加班费",
            "工伤",
            "竞业",
            "劳动争议",
            "版权",
            "著作权",
            "投诉",
            "维权",
            "假货",
            "许可证",
            "license",
            "agpl",
            "法院",
            "裁判文书",
            "条例",
            "广告法",
            "中医药法",
            "医疗广告管理办法",
            "中医养生保健服务规范",
            "不得保证治愈",
            "不得从事医疗活动",
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
        "terms": ("官方", "央媒", "权威", "表述", "口径", "定调", "人民日报", "新华社", "央视", "军事领域", "军事热点", "国防部"),
        "scopes": ("party_central", "gov"),
        "fallback": ("local_official",),
        "roles": ("official_narrative", "authoritative_report"),
    },
    {
        "intent": "local",
        "terms": ("地方", "城市", "区域", "区县", "园区", "北京", "上海", "深圳", "广州", "杭州", "成都", "沈阳", "广西", "珠海", "横琴", "伊春", "新疆", "伊犁"),
        "scopes": ("local_official", "gov"),
        "fallback": ("party_central", "business"),
        "roles": ("local_context", "official_primary"),
    },
    {
        "intent": "local_life",
        "terms": (
            "骑行路线",
            "骑行",
            "徒步路线",
            "Citywalk",
            "citywalk",
            "热门店",
            "小店",
            "文艺小店",
            "安静小店",
            "人気店",
            "焼き鳥",
            "美食",
            "餐厅",
            "餐馆",
            "咖啡店",
            "咖啡馆",
            "书吧",
            "晨间",
            "brunch",
            "早午餐",
            "不排队",
            "发呆",
            "安静",
            "看海",
            "夜景",
            "书店",
            "深夜书店",
            "自驾",
            "景区",
            "独库公路",
            "伊昭公路",
            "赛里木湖",
            "喀拉峻",
            "夏塔",
            "恰西",
            "库尔德宁",
            "琼库什台",
            "旅行攻略",
            "展览",
            "新展览",
            "主题展览",
            "展会",
            "周末好去处",
            "好去处",
        ),
        "scopes": ("social_web", "business"),
        "fallback": ("local_official", "ecommerce", "community_sample"),
        "sites": ("xiaohongshu.com", "dianping.com", "mafengwo.cn", "tripadvisor.com", "damai.cn", "showstart.com"),
        "roles": ("local_guide", "user_sample", "official_context", "review_sample"),
        "warning": "本地生活/路线/餐饮问题应区分官方入口、攻略样本、平台评价和当天时效；单平台榜单不能代表总体。",
    },
    {
        "intent": "transport",
        "terms": (
            "开行日历",
            "开行计划",
            "运营计划",
            "列车运行图",
            "车次",
            "铁路",
            "高铁",
            "12306",
            "路况",
            "开通 时间",
            "开通时间",
            "限速",
            "加油站",
            "独库公路",
            "伊昭公路",
            "train schedule",
            "railway timetable",
        ),
        "scopes": ("local_official", "gov", "business"),
        "fallback": ("social_web",),
        "sites": ("12306.cn", "railway12306.cn", "china-railway.com.cn"),
        "roles": ("official_schedule", "operator_notice", "service_update", "traveler_sample"),
        "warning": "铁路/交通开行信息应优先官方或运营方公告，第三方票务和论坛只能作线索。",
    },
    {
        "intent": "weather_disaster",
        "terms": (
            "天气",
            "气象",
            "台风",
            "路径",
            "预警",
            "暴雨",
            "洪水",
            "地震",
            "灾害",
            "应急",
            "中央气象台",
            "日本气象厅",
            "weather",
            "typhoon",
            "hurricane",
            "earthquake",
            "storm",
            "noaa",
            "jma",
            "usgs",
        ),
        "scopes": ("weather_disaster", "gov", "global_official"),
        "fallback": ("local_official", "global_news"),
        "sites": ("nmc.cn", "cma.gov.cn", "weather.com.cn", "jma.go.jp", "noaa.gov", "usgs.gov"),
        "roles": ("official_alert", "forecast_track", "disaster_notice", "public_safety"),
        "warning": "天气灾害问题应优先官方实时预警、气象机构和应急部门，社交平台只适合作现场样本。",
    },
    {
        "intent": "science",
        "terms": (
            "科学",
            "发现",
            "外星生命",
            "詹姆斯韦伯",
            "韦伯望远镜",
            "天文",
            "nasa",
            "esa",
            "jwst",
            "webb telescope",
            "alien life",
            "nature",
            "science",
            "arxiv",
            "paper",
        ),
        "scopes": ("science", "academic", "global_official"),
        "fallback": ("global_news", "community_sample"),
        "sites": ("nasa.gov", "esa.int", "nature.com", "science.org", "arxiv.org"),
        "roles": ("institution_primary", "peer_review", "science_news", "preprint"),
        "warning": "科学发现应优先机构原文、论文或预印本，科普/媒体报道只能作为解释层。",
    },
    {
        "intent": "sports",
        "terms": (
            "体育",
            "比赛",
            "赛程",
            "比分",
            "伤病",
            "转会",
            "续约",
            "梅西",
            "姆巴佩",
            "mbappe",
            "messi",
            "real madrid",
            "nba",
            "fifa",
            "uefa",
            "lpl",
            "电竞",
        ),
        "scopes": ("sports", "global_news", "community_sample"),
        "fallback": ("social_web", "entertainment"),
        "sites": ("espn.com", "skysports.com", "theathletic.com", "fifa.com", "uefa.com", "hupu.com", "dongqiudi.com"),
        "roles": ("official_stat", "sports_report", "transfer_report", "fan_discussion"),
        "warning": "体育信息应区分官方赛程/伤病、媒体报道、转会爆料和球迷讨论；爆料不能直接当事实。",
    },
    {
        "intent": "global_entertainment",
        "terms": (
            "欧美娱乐",
            "西方娱乐",
            "好莱坞",
            "hollywood",
            "deadline",
            "variety",
            "hollywood reporter",
            "rottentomatoes",
            "烂番茄",
            "hbo",
            "netflix",
            "dune",
            "casting",
            "renewal",
            "season",
            "release date",
            "tv series",
            "前哨奖",
            "影评人协会",
            "celebrity",
            "celeb",
            "pop star",
            "music chart",
            "billboard",
            "grammy",
            "oscar",
            "emmy",
            "album",
            "single",
            "tour",
            "concert",
            "streaming",
            "box office",
            "anti hero",
            "anti-hero",
            "taylor swift",
            "swift",
            "beyonce",
            "lady gaga",
            "ariana grande",
            "sabrina carpenter",
            "billie eilish",
            "dua lipa",
            "drake",
            "kanye",
            "selena gomez",
            "justin bieber",
        ),
        "scopes": ("global_entertainment", "company_primary", "community_sample"),
        "fallback": ("global_news", "jp_kr_entertainment"),
        "sites": ("billboard.com", "variety.com", "deadline.com", "hollywoodreporter.com", "rollingstone.com", "people.com"),
        "roles": ("trade_report", "music_chart", "official_release", "celebrity_report", "fan_discussion"),
        "warning": "欧美娱乐问题应优先英文行业媒体、榜单/奖项和艺人/厂牌一手信息；粉丝账号、狗仔和二手搬运只能作线索。",
    },
    {
        "intent": "jp_kr_entertainment",
        "terms": (
            "日韩娱乐",
            "日本娱乐",
            "韩国娱乐",
            "韩娱",
            "日娱",
            "韩媒",
            "日媒",
            "韩网",
            "韩国本地评价",
            "退团",
            "女团",
            "男团",
            "回归",
            "经纪公司回应",
            "本地评价",
            "桥本环奈",
            "jennie",
            "jisoo",
            "lisa",
            "rose",
            "rosé",
            "netflix 韩剧",
            "k-pop",
            "kpop",
            "k drama",
            "k-drama",
            "kdrama",
            "j-pop",
            "jpop",
            "j drama",
            "j-drama",
            "jdrama",
            "oricon",
            "soompi",
            "naver",
            "weverse",
            "hybe",
            "bts",
            "blackpink",
            "newjeans",
            "aespa",
            "ive",
            "le sserafim",
            "twice",
            "stray kids",
            "seventeen",
            "nct",
            "starto",
            "snow man",
            "アニメ",
            "アニメ 新作",
            "青春アニメ",
            "新刊",
            "最新刊",
            "続編",
            "劇場版",
            "展覧会",
            "イベント",
            "ライトノベル",
            "ラノベ",
            "弱キャラ友崎くん",
            "違国日記",
            "异国日记",
            "ぼっち・ざ・ろっく",
            "僕の心のヤバイやつ",
            "僕ヤバ",
            "とんがり帽子のアトリエ",
            "スキップとローファー",
            "skip and loafer",
            "青春コンプレックス",
            "コミュ症",
            "コミュ障",
            "星の王子",
            "葬送的芙莉莲",
            "芙莉莲",
            "夏目友人帐",
            "尖帽子魔法工坊",
            "尖帽子的魔法工坊",
            "漫改动画",
            "漫改动画新番",
            "代餐",
            "同人壁纸",
            "壁紙",
            "相反的你和我",
            "ost",
            "歌单",
        ),
        "scopes": ("jp_kr_entertainment", "global_entertainment", "community_sample"),
        "fallback": ("global_news", "company_primary"),
        "sites": ("soompi.com", "oricon.co.jp", "natalie.mu", "pixiv.net", "entertain.naver.com", "koreaherald.com", "koreatimes.co.kr"),
        "roles": ("translation_report", "chart_metric", "agency_context", "fan_discussion", "official_release"),
        "warning": "日韩娱乐问题要区分经纪公司/榜单/本地媒体、英文翻译站和粉丝讨论；跨语言转述需保留翻译层风险。",
    },
    {
        "intent": "entertainment",
        "terms": (
            "文娱",
            "娱乐",
            "影视",
            "电影",
            "电视剧",
            "剧集",
            "综艺",
            "明星",
            "偶像",
            "演员",
            "票房",
            "排片",
            "播放量",
            "收视率",
            "评分",
            "豆瓣",
            "猫眼",
            "灯塔",
            "音乐",
            "专辑",
            "演唱会",
            "游戏",
            "手游",
            "主机游戏",
            "steam",
            "dlc",
            "mod",
            "模组",
            "销量",
            "黑神话",
            "巫师",
            "witcher",
            "cdpr",
            "赛博朋克",
            "cyberpunk",
            "玩家反响",
            "类似剧推荐",
            "剧推荐",
            "婚姻剧毒",
            "观后感",
            "无剧透",
            "pearl abyss",
            "红色沙漠",
            "crimson desert",
            "手柄重映射",
            "更新补丁",
            "战锤",
            "warhammer",
            "星际战士",
            "space marine",
            "桌面游戏",
            "新规则",
            "绝区零",
            "比利·基德",
            "比利基德",
            "星辉骑士",
            "背景故事",
            "真实身份",
            "动漫",
            "二次元",
            "漫画",
            "番剧",
            "轻小说",
            "学园",
            "治愈",
            "魔女",
            "manga",
            "anime",
            "bangumi",
            "pixiv",
        ),
        "scopes": ("entertainment", "social_web", "business"),
        "fallback": ("finance", "tech_dev", "global_entertainment", "jp_kr_entertainment"),
        "sites": (
            "douban.com",
            "maoyan.com",
            "bilibili.com",
            "weibo.com",
            "taptap.cn",
            "bangumi.tv",
            "pixiv.net",
            "mangapedia.com",
            "manba.co.jp",
            "warhammer-community.com",
            "games-workshop.com",
        ),
        "roles": ("platform_metric", "user_review", "industry_report", "fan_discussion", "official_release"),
        "warning": "文娱问题应区分平台热度、用户评分、产业报道、宣发通稿和粉圈讨论；漫画/番剧/轻小说题材优先看条目站、创作者社区和公开口碑，单平台热搜不能代表总体口碑。",
    },
    {
        "intent": "design_trend",
        "terms": (
            "流行色",
            "色彩趋势",
            "设计趋势",
            "产品配色",
            "配色趋势",
            "ui 配色",
            "视觉趋势",
            "丁香紫",
            "pantone",
            "color trend",
            "colour trend",
            "palette",
            "插画",
            "温柔插画",
            "ai生成",
            "ai 生成",
            "ai插画",
            "ai 插画",
        ),
        "scopes": ("social_web", "business", "industry_analysis"),
        "fallback": ("ecommerce", "community_sample"),
        "sites": ("pantone.com", "behance.net", "dribbble.com", "xiaohongshu.com", "pinterest.com"),
        "roles": ("design_reference", "trend_report", "platform_sample", "brand_example"),
        "warning": "设计趋势/配色问题应区分权威色彩机构、设计社区样本、品牌案例和平台种草；流行色不是事实性标准。",
    },
    {
        "intent": "reputation",
        "terms": (
            "评价",
            "口碑",
            "体验",
            "吐槽",
            "避雷",
            "测评",
            "推荐吗",
            "好用吗",
            "怎么样",
            "小红书",
            "知乎",
            "微博",
            "b站",
            "投诉",
            "黑猫",
            "车质网",
            "真实车主",
            "透明度",
            "基金会",
            "慈善",
            "公益",
            "捐款",
            "善款",
            "sentiment",
            "boycott",
            "complaint",
            "complaints",
        ),
        "scopes": ("social_web", "tech_dev", "business"),
        "fallback": ("ecommerce",),
        "sites": ("zhihu.com", "weibo.com", "xiaohongshu.com", "bilibili.com"),
        "roles": ("user_sample", "community_discussion", "vertical_report"),
        "warning": "社交和社区材料适合发现样本线索，不代表总体比例。",
    },
    {
        "intent": "public_opinion",
        "terms": (
            "舆情",
            "舆论",
            "风评",
            "声量",
            "口碑监测",
            "社媒",
            "社交媒体",
            "评论区",
            "讨论热度",
            "正负面",
            "被骂",
            "被夸",
            "social listening",
            "social sentiment",
            "brand sentiment",
        ),
        "scopes": ("social_web", "business", "market_review"),
        "fallback": ("finance_sentiment", "community_sample", "entertainment"),
        "sites": ("weibo.com", "zhihu.com", "xiaohongshu.com", "bilibili.com", "douban.com"),
        "roles": ("public_discussion", "sentiment_sample", "review_sample", "media_report"),
        "warning": "舆情/风评只能代表当前公开样本池，必须说明平台偏差、样本量和时间窗。",
    },
    {
        "intent": "crisis_watch",
        "terms": (
            "公关危机",
            "危机预警",
            "舆情危机",
            "负面舆情",
            "负面新闻",
            "集体投诉",
            "投诉爆发",
            "抵制",
            "翻车",
            "下架",
            "召回",
            "道歉",
            "澄清",
            "危机处理",
            "crisis watch",
            "pr crisis",
            "backlash",
            "boycott",
        ),
        "scopes": ("social_web", "business", "market_review", "gov"),
        "fallback": ("party_central", "local_official", "company_primary"),
        "sites": ("weibo.com", "tousu.sina.com.cn", "zhihu.com", "xiaohongshu.com", "12315.cn"),
        "roles": ("risk_signal", "complaint_sample", "media_report", "official_response", "company_statement"),
        "warning": "危机/负面监测要区分投诉样本、媒体报道、官方回应和平台扩散，不要把单个爆款帖写成总体事实。",
    },
    {
        "intent": "competitor_watch",
        "terms": (
            "竞品情报",
            "竞品监控",
            "竞品分析",
            "竞争对手",
            "竞对",
            "同类产品",
            "替代品",
            "市场格局",
            "功能对比",
            "产品对比",
            "竞争格局",
            "competitive intelligence",
            "competitor tracking",
            "competitive landscape",
        ),
        "scopes": ("company_primary", "business", "market_review", "social_web"),
        "fallback": ("industry_analysis", "developer", "finance_news"),
        "sites": ("producthunt.com", "g2.com", "capterra.com", "trustpilot.com", "36kr.com", "huxiu.com"),
        "roles": ("company_primary", "pricing_page", "release_note", "industry_report", "review_sample", "user_sample"),
        "warning": "竞品情报应先核验公司一手资料和产品页，再用媒体/评价/社区样本补充，不要凭印象生成竞品清单。",
    },
    {
        "intent": "pricing_watch",
        "terms": (
            "定价变化",
            "价格变化",
            "价格调整",
            "涨价",
            "降价",
            "套餐变化",
            "订阅变化",
            "价格页",
            "付费墙",
            "收费标准",
            "收费",
            "年费",
            "annual price",
            "pricing change",
            "price change",
            "plan changes",
        ),
        "scopes": ("company_primary", "market_review", "business"),
        "fallback": ("global_news", "community_sample", "developer"),
        "sites": ("producthunt.com", "g2.com", "capterra.com", "trustpilot.com"),
        "roles": ("pricing_page", "release_note", "customer_reaction", "media_report"),
        "warning": "价格/套餐变化要优先官方价格页、公告或帮助中心；社区和评价站只能作用户反应样本。",
    },
    {
        "intent": "review_intel",
        "terms": (
            "评论分析",
            "评论挖掘",
            "用户评论",
            "差评",
            "好评",
            "评分变化",
            "评分下滑",
            "用户反馈",
            "评价样本",
            "review mining",
            "customer reviews",
            "user reviews",
            "靠谱吗",
        ),
        "scopes": ("market_review", "social_web", "business"),
        "fallback": ("company_primary", "community_sample"),
        "sites": ("apps.apple.com", "play.google.com", "g2.com", "capterra.com", "trustpilot.com", "zhihu.com", "weibo.com"),
        "roles": ("review_sample", "rating_signal", "complaint_sample", "feature_request", "user_language"),
        "warning": "评论样本适合提炼用户语言和问题簇，不代表真实用户总体比例；需要保留平台和版本边界。",
    },
    {
        "intent": "app_review",
        "terms": (
            "app store 评论",
            "appstore 评论",
            "应用商店评论",
            "应用评论",
            "ios 评论",
            "安卓评论",
            "google play 评论",
            "play store reviews",
            "app reviews",
            "aso",
            "应用评分",
        ),
        "scopes": ("market_review", "company_primary", "social_web"),
        "fallback": ("business", "community_sample"),
        "sites": ("apps.apple.com", "play.google.com", "qimai.cn", "diandian.com"),
        "roles": ("app_store_review", "rating_signal", "version_feedback", "user_language", "app_market_signal"),
        "warning": "应用商店评论要区分版本、地区、评分样本和用户原话；不要把榜单/下载估计当成官方经营数据。",
    },
    {
        "intent": "wps_office",
        "terms": _WPS_OFFICE_TERMS,
        "scopes": ("wps_office", "business", "tech_dev", "company_primary", "cybersecurity"),
        "fallback": ("social_web", "finance_news", "industry_analysis", "community_sample", "market_review"),
        "sites": (
            "wps.cn",
            "365.wps.cn",
            "bbs.wps.cn",
            "security.wps.cn",
            "ithome.com",
            "36kr.com",
            "sspai.com",
            "leiphone.com",
            "jiqizhixin.com",
            "qbitai.com",
            "microsoft.com",
            "canva.com",
        ),
        "roles": (
            "company_primary",
            "official_specs",
            "industry_report",
            "institution_rollout",
            "user_sample",
            "developer_discussion",
            "fresh_news",
            "security_advisory",
        ),
        "warning": "WPS/AI Office 选题不能只看品牌通稿；应分开核验官方产品、竞品/办公 SaaS、AI/科技媒体、用户/社区样本、信创与安全约束。",
    },
    {
        "intent": "purchase_advice",
        "terms": (
            "值不值得买",
            "能买吗",
            "要不要买",
            "购买",
            "选购",
            "对比",
            "推荐哪",
            "踩雷",
            "缺点",
            "优缺点",
            "怎么选",
            "防骗",
            "验机",
            "字大",
            "电池好",
            "不容易坏",
            "哪个牌子",
            "安全座椅",
            "used car",
            "pre-purchase",
            "inspection checklist",
            "mechanic inspection",
        ),
        "scopes": ("social_web", "business", "ecommerce"),
        "fallback": ("tech_dev",),
        "sites": ("zhihu.com", "xiaohongshu.com", "bilibili.com"),
        "roles": ("user_sample", "official_specs", "review"),
        "warning": "购买建议需要同时核验官方参数、垂类评测和用户样本，不能只看单个平台。",
    },
    {
        "intent": "industry",
        "terms": (
            "行业",
            "产业",
            "商业化",
            "公司",
            "竞品",
            "融资",
            "市场",
            "趋势",
            "供应链",
            "创业",
            "市场规模",
            "市场预测",
            "职业服务",
            "在线招聘",
            "questmobile",
            "艾瑞",
            "ai陪伴",
            "ai 陪伴",
            "复合增速",
            "cagr",
            "出货量",
            "清洁能源",
            "光伏",
            "光热",
            "熔盐储罐",
            "主营业务",
            "可穿戴",
            "智能眼镜",
            "航运",
            "业务板块",
            "纺织服装",
            "户外动力设备",
            "ope",
            "船舶制造",
            "医疗设备进口",
            "大宗商品",
            "机电",
            "食材成本",
            "配菜",
            "蔬菜拼盘",
            "烤鱼品牌",
            "海带苗",
            "鸡枞菌",
            "姜饼瓜",
            "商业模式",
            "市场份额",
            "销量增长",
            "国内市场份额",
            "问界",
            "赛力斯",
            "新能源汽车",
            "新能源车",
            "电动车",
            "宠物陪伴机器人",
            "宠物智能",
            "智能项圈",
            "情感陪伴机器人",
            "宠物机器人",
            "香养基地",
            "伊春森工",
            "伊春森工集团",
            "林下经济",
            "运价",
            "红海",
            "关税",
            "海外销量",
            "大豆",
            "进口价格",
            "压榨",
            "market size",
            "report",
            "companion robot",
            "pet companion",
            "昇腾",
            "910b",
            "910c",
            "中标",
            "招标",
            "深远海",
            "柔直",
            "柔性直流",
            "输电技术",
            "海上风电",
            "海缆",
            "组织架构",
            "组织结构",
            "组织变革",
            "业务线划分",
            "事业部",
            "大客户管理",
            "中创新航",
            "calb",
            "国轩高科",
            "gotion",
            "亿纬锂能",
            "宁德时代",
            "catl",
            "evogo",
            "时代电服",
            "巧克力换电",
            "骐骥换电",
            "华为",
            *_ROBOTICS_AI_TERMS,
        ),
        "scopes": ("business", "finance", "ecommerce"),
        "fallback": ("party_central", "social_web", "tech_dev"),
        "roles": ("industry_report", "company_context", "market_news"),
    },
    {
        "intent": "company_primary",
        "terms": (
            "涂鸦智能",
            "tuya",
            "tuyaopen",
            "cobuilder",
            "iot paas",
        ),
        "scopes": ("company_primary", "developer", "tech_dev"),
        "fallback": ("business", "global_news", "community_sample"),
        "sites": ("tuya.com", "developer.tuya.com", "iot.tuya.com", "github.com"),
        "roles": ("company_primary", "developer_documentation", "technical_primary", "fresh_news"),
        "warning": "平台/开发者生态问题应先核验公司一手发布、开发者文档和代码入口，再补媒体与社区样本。",
    },
    {
        "intent": "company_primary",
        "terms": (
            "付费",
            "订阅",
            "定价",
            "价格",
            "报价",
            "服务费",
            "套餐",
            "会员",
            "商业化",
            "发布",
            "上线",
            "pricing",
            "usage",
            "billing",
            "bills",
            "quota",
            "quotas",
            "usage limit",
            "usage limits",
            "limits",
            "valuation",
            "users",
            "revenue",
            "acquisition",
            "layoffs",
            "guidance",
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
            "发售时间",
            "发售日期",
            "开发进度",
            "股东",
            "法定代表人",
            "董事长",
            "创始人",
            "工商",
            "企业信用",
            "公司背景",
            "社保代理",
            "google cloud",
            "gemini api",
            "cloud console",
            "开发者平台",
            "开发者大会",
            "harness ci/cd",
            "delegate 代理原理",
            "natspec",
            "product partner",
            "建筑规格",
            "clip studio paint",
            "clip studio",
            "聚合数据",
            "天聚地合",
            "juhe",
            "seedance",
            "豆包",
            "doubao",
            "字节跳动",
            "volcengine",
            "character.ai",
            "c.ai",
            "peloton",
            "notion ai",
            "notion",
            "calm",
            "replika",
            "lovot",
            "groove-x",
            "groovex",
            "coze",
            "扣子",
            "bot 数",
            "用户数",
            "node.js",
            "nodejs",
            "node js",
            "node.js 20",
            "微信支付",
            "支付宝",
            "账单导出",
            "导出账单",
            "交易账单",
            "交易记录",
            "个人账单",
            "支付开放平台",
            "icost",
            "callback url",
            "x-callback-url",
            "url scheme",
            "组织架构",
            "组织结构",
            "组织变革",
            "管理层调整",
            "业务线",
            "事业部",
            "营销中心",
            "销售组织架构",
            "大客户管理",
            "直销模式",
            "全球布局",
            "中创新航",
            "calb",
            "国轩高科",
            "gotion",
            "亿纬锂能",
            "宁德时代",
            "catl",
            "evogo",
            "时代电服",
            "巧克力换电",
            "骐骥换电",
            "换电品牌",
            "华为",
            "铁三角",
            "ar sr fr",
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
        "terms": (
            "market map",
            "industry analysis",
            "market share",
            "competitive landscape",
            "startup",
            "funding",
            "analyst report",
            "market size",
            "valuation",
            "revenue",
            "users",
            "acquisition",
            "acquisitions",
            "merger",
            "mergers",
            "m&a",
            "enterprise m&a",
            "企业并购",
            "并购",
            "英国企业",
            "uk companies",
            "industry policy",
            "report",
            "red sea",
            "shipping",
            "tariff",
            "global supply chain",
            "中国互联网络发展状况统计报告",
            "互联网络发展状况统计报告",
            "cnnic",
            "网络支付 用户规模",
        ),
        "scopes": ("industry_analysis", "global_news", "company_primary"),
        "fallback": ("community_sample",),
        "roles": ("industry_report", "company_context", "market_news"),
    },
    {
        "intent": "ecommerce",
        "terms": (
            "电商",
            "零售",
            "跨境",
            "出海",
            "品牌",
            "渠道",
            "供应链",
            "产业带",
            "亚马逊",
            "京东",
            "淘宝",
            "天猫",
            "拼多多",
            "ecommerce",
            "e-commerce",
            "shopify",
            "shopee",
            "lazada",
            "tiktok shop",
            "dropshipping",
            "instagram",
            "独立站",
            "woocommerce",
            "闲鱼 技术服务",
            "闲鱼规则",
            "直通车",
            "抖音电商",
            "抖音小店",
            "小店",
            "团购",
            "抖音团购",
            "真实商家",
            "实体店",
            "加盟",
            "本地生活",
            "餐馆",
            "茶饮",
            "二手",
            "二手价格",
            "闲鱼",
            "转转",
            "回收价",
            "中古",
            "resale",
            "second hand",
            "显卡",
            "rtx",
            "tech accessories",
            "ai hardware",
            "智能硬件",
            "数码配件",
            "smart devices",
            "smart home",
            "食材成本",
            "配菜",
            "蔬菜拼盘",
            "烤鱼品牌",
            "探鱼",
            "半天妖",
            "鱼酷",
            "海带苗",
            "鸡枞菌",
            "姜饼瓜",
        ),
        "scopes": ("ecommerce", "business"),
        "fallback": ("social_web", "finance"),
        "roles": ("vertical_report", "case", "consumer_signal"),
    },
    {
        "intent": "career",
        "terms": (
            "招聘",
            "求职",
            "岗位",
            "薪资",
            "面试",
            "简历",
            "校招",
            "社招",
            "面经",
            "offer",
            "hc",
            "算法工程师",
            "产品经理",
            "职业定位",
            "核心竞争力",
            "个人商业模式画布",
            "个人说明书",
            "working with me",
            "云成本工程师",
            "finops",
            "求职者",
            "反向背调",
            "interview loop",
            "salary",
            "levels",
            "levels.fyi",
            "glassdoor",
            "research engineer",
        ),
        "scopes": ("career", "social_web", "business"),
        "fallback": ("company_primary", "community_sample"),
        "sites": ("nowcoder.com", "yingjiesheng.com", "zhipin.com", "levels.fyi", "glassdoor.com", "linkedin.com"),
        "roles": ("job_posting", "salary_sample", "interview_sample", "company_context"),
        "warning": "职场/薪资/面经信息样本偏差很大，应区分官方岗位、候选人经验、薪资样本和招聘报告。",
    },
    {
        "intent": "podcast",
        "terms": ("播客", "小宇宙", "音频", "节目", "单集", "主播", "电台", "声线", "粤语电台", "podcast", "rss audio"),
        "scopes": ("podcast", "social_web", "tech_dev"),
        "fallback": ("business", "community_sample"),
        "sites": ("xiaoyuzhoufm.com", "podcasts.apple.com", "spotify.com", "listennotes.com"),
        "roles": ("episode_catalog", "show_metadata", "listener_sample", "rss_feed"),
        "warning": "播客发现应区分节目/单集元数据、听众评价和转写内容；榜单只能作发现线索。",
    },
    {
        "intent": "tech",
        "terms": (
            "技术",
            "开源",
            "框架",
            "github",
            "sdk",
            "api",
            "部署",
            "bug",
            "benchmark",
            "选型",
            "开发者",
            "mcp",
            "人工智能 今天",
            "人工智能 今日",
            "人工智能 热门",
            "人工智能 热点",
            "openclaw",
            "opencli",
            "wechat-article-exporter",
            "wechat article exporter",
            "tuyaopen",
            "cobuilder",
            "iot paas",
            "霞鹜文楷",
            "lxgw",
            "lxgwwenkai",
            "wenkai",
            "屏幕阅读版",
            "字重",
            "字体优化",
            "字体 优化",
            "视力障碍 字体",
            "教程",
            "rag",
            "reranker",
            "ollama",
            "本地模型",
            "联网搜索",
            "自动加字幕",
            "剪映",
            "product hunt",
            "hermes agent",
            "内存占用",
            "后台运行",
            "cpu 性能测试",
            "性能测试",
            "vscode",
            "vs code",
            "visual studio code",
            "调试新特性",
            "debugging",
            "wordpress",
            "woocommerce",
            "spectra",
            "seo",
            "seedance",
            "视频生成模型",
            "豆包",
            "doubao",
            "字节跳动",
            "volcengine",
            "ai写作",
            "ai写小说",
            "ai 写小说",
            "ai绘画",
            "ai 绘画",
            "ai画画",
            "ai 画画",
            "ai agent",
            "智能体",
            "大模型",
            "deepseek",
            "llama",
            "昇腾",
            "910b",
            "910c",
            "gpu",
            "figma",
            "firefly",
            "ai tool",
            "ai工具",
            "ai读书笔记工具",
            "读书笔记工具",
            "多agent",
            "多 agent",
            "multi-agent",
            "multi agent",
            "ai内容生成",
            "ai 内容生成",
            "系统架构",
            "实践案例",
            "多轮对话",
            "确认节点",
            "交互设计",
            "用户引导",
            "ai陪伴",
            "ai 陪伴",
            "ai companion",
            "companion ai",
            "personality ai",
            "小冰",
            "aip",
            "node.js",
            "nodejs",
            "node js",
            "lts",
            "安装包",
            "下载地址",
            "url scheme",
            "urlscheme",
            "callback url",
            "x-callback-url",
            "notificationlistenerservice",
            "notification listener service",
            "通知监听服务",
            "android 通知监听",
            "tasker",
            "icost",
            *_ROBOTICS_AI_TERMS,
        ),
        "scopes": ("tech_dev",),
        "fallback": ("business", "social_web"),
        "sites": ("github.com", "v2ex.com", "juejin.cn", "segmentfault.com"),
        "roles": ("source_code", "technical_note", "developer_discussion"),
        "warning": "科技/技术类内容必须额外补一轮 RSS/精品内容流，避免只看到搜索引擎排名或社区单点样本。",
    },
    {
        "intent": "university_admissions",
        "terms": (
            "研究生招生",
            "博士招生",
            "硕士招生",
            "招生目录",
            "招生简章",
            "导师",
            "导师名单",
            "导师介绍",
            "导师情况",
            "院系",
            "计算机系",
            "研究生院",
            "教务处",
            "期末考试",
            "考试时间",
            "校园通知",
            "推免",
            "复试",
            "考研",
            "faculty",
            "advisor",
            "supervisor",
            "graduate admissions",
        ),
        "scopes": ("university",),
        "fallback": ("academic", "tech_dev"),
        "sites": ("edu.cn",),
        "roles": ("university_official", "department_page", "faculty_profile", "admission_catalog"),
        "warning": "高校招生/导师问题应优先院系官网、研究生招生网、招生目录和导师主页；学术数据库不是主证据。",
    },
    {
        "intent": "test_prep",
        "terms": (
            "雅思",
            "托福",
            "ielts",
            "toefl",
            "题库",
            "机经",
            "口语题库",
            "考试政策",
            "培训合规",
            "备考",
            "真题",
        ),
        "scopes": ("test_prep", "social_web", "company_primary"),
        "fallback": ("academic", "gov"),
        "sites": ("ielts.org", "ets.org", "neea.edu.cn", "chinaielts.org", "zhihu.com"),
        "roles": ("exam_official", "prep_material", "candidate_sample", "training_context"),
        "warning": "考试备考资料应区分官方考试政策、培训机构材料和考生经验；机经/题库不宜当作确定事实。",
    },
    {
        "intent": "education_learning",
        "terms": (
            "化学学习",
            "学习技巧",
            "初中",
            "高中",
            "元素周期表",
            "记忆方法",
            "stoichiometry",
            "balancing equations",
            "common student errors",
            "practice tool",
            "interactive",
            "problem solving strategy",
        ),
        "scopes": ("social_web", "academic"),
        "fallback": ("test_prep", "company_primary", "community_sample"),
        "sites": ("khanacademy.org", "phet.colorado.edu", "chemcollective.org", "neea.edu.cn"),
        "roles": ("learning_resource", "official_curriculum", "practice_tool", "teacher_strategy"),
        "warning": "学习资源应区分官方/机构材料、教师经验、互动工具和社区样本；不要把 SEO 题库当权威。",
    },
    {
        "intent": "education_service",
        "terms": (
            "夏令营",
            "冬令营",
            "研学",
            "营地",
            "暑期",
            "家长评价",
            "小学生",
            "青少年",
            "费用",
            "年龄",
            "住宿",
        ),
        "scopes": ("social_web", "business", "company_primary"),
        "fallback": ("gov", "market_review"),
        "sites": ("xiaohongshu.com", "zhihu.com", "weibo.com", "heimao.com"),
        "roles": ("official_program", "parent_sample", "complaint_sample", "safety_context"),
        "warning": "教育服务/夏令营口碑应分开官方招生页、家长样本、投诉样本和安全/保险条款；投诉样本不能外推总体。",
    },
    {
        "intent": "reading_notes",
        "terms": (
            "书摘",
            "读书笔记",
            "阅读笔记",
            "阅读感悟",
            "书评",
            "豆瓣读书",
            "少儿阅读",
            "图书馆",
            "阅读清单",
            "经典语录",
            "经典句子",
            "狐狸驯养",
            "长大后才懂",
            "读后感",
            "把自己作为方法",
            "小王子 阅读",
            "小王子 经典",
            "小王子 狐狸",
            "人月神话",
            "被讨厌的勇气",
            "阿德勒",
            "课题分离",
            "三体",
            "给岁月以文明",
            "给文明以岁月",
            "礼记",
            "聘义",
            "君子比德于玉",
            "黄帝内经",
            "上古天真论",
            "法于阴阳",
            "和于术数",
            "食饮有节",
            "起居有常",
            "天人相应",
            "顺四时",
            "caldecott",
            "caldecott medal",
            "medal winners",
        ),
        "scopes": ("social_web", "business"),
        "fallback": ("local_official", "entertainment", "community_sample"),
        "sites": ("book.douban.com", "douban.com", "weread.qq.com", "goodreads.com", "ala.org"),
        "roles": ("book_record", "reader_note", "library_context", "review_sample"),
        "warning": "书摘/读书笔记应避免长段版权文本；读者笔记和平台评分只能作样本。",
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
        "terms": (
            "财经",
            "资本市场",
            "股价",
            "股票",
            "财报",
            "公告",
            "投资",
            "上市",
            "基金",
            "债券",
            "净值",
            "营收",
            "利润",
            "英伟达",
            "nvidia",
            "大跌",
            "etf",
            "质押",
            "银行倒闭",
            "银行",
            "倒闭",
            "机构观点",
            "利空",
            "下跌原因",
        ),
        "scopes": ("finance_disclosure", "finance_company", "finance_news", "finance_quote"),
        "fallback": ("finance_macro", "finance_research", "finance_sentiment", "business"),
        "sites": ("cninfo.com.cn", "sse.com.cn", "szse.cn", "eastmoney.com", "cls.cn", "xueqiu.com"),
        "roles": ("company_filing", "market_quote", "market_news", "macro_data", "sentiment_sample"),
        "warning": "财经材料必须区分行情、公告披露、新闻、宏观数据、研报观点和投资者情绪；不能把市场观点写成投资建议。",
    },
    {
        "intent": "finance_quote",
        "terms": (
            "股价",
            "行情",
            "涨跌",
            "涨跌幅",
            "盘口",
            "大盘",
            "指数",
            "富时",
            "a50",
            "期货",
            "收盘",
            "美股收盘",
            "标普500",
            "纳指",
            "道指",
            "板块",
            "etf",
            "etf联接",
            "基金概况",
            "跟踪指数",
            "持仓",
            "成立日期",
            "成立时间",
            "混合发起c",
            "基金净值",
            "今日净值",
            "净值",
            "联接基金",
            "联接c",
            "ftse",
            "ftse 100",
            "gilts",
            "bond yields",
            "uk stocks",
            "实时",
            "quote",
            "stock price",
            "market cap",
            "futures",
            "s&p 500",
            "nasdaq",
            "dow",
        ),
        "scopes": ("finance_quote", "finance_news"),
        "fallback": ("finance_disclosure", "finance_sentiment"),
        "sites": ("quote.eastmoney.com", "finance.sina.com.cn", "xueqiu.com", "finance.yahoo.com", "nasdaq.com", "londonstockexchange.com"),
        "roles": ("market_quote", "index_data", "market_news", "sentiment_sample"),
        "warning": "行情页多为动态渲染且可能延迟；回答必须标注时间/来源，不能据此给买卖建议。",
    },
    {
        "intent": "finance_disclosure",
        "terms": (
            "公告",
            "披露",
            "财报",
            "年报",
            "季报",
            "半年报",
            "减持",
            "质押",
            "停牌",
            "复牌",
            "监管函",
            "问询函",
            "处罚",
            "风险提示",
            "10-k",
            "10-q",
            "filing",
        ),
        "scopes": ("finance_disclosure", "finance_company", "finance_news"),
        "fallback": ("finance_quote", "finance_macro", "finance_sentiment"),
        "sites": ("cninfo.com.cn", "sse.com.cn", "szse.cn", "hkexnews.hk", "sec.gov", "csrc.gov.cn"),
        "roles": ("company_filing", "exchange_announcement", "regulatory_notice", "risk_disclosure"),
        "warning": "公告披露和监管来源优先于媒体转述；摘要不能替代原公告，注意公告日期和适用市场。",
    },
    {
        "intent": "finance_macro",
        "terms": (
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
            "美联储",
            "统计局",
            "fedwatch",
            "非农",
            "通胀",
            "imf",
            "bank of england",
            "boe",
            "interest rate",
            "inflation",
            "uk economy",
            "economic growth",
            "growth forecast",
            "英国经济",
            "经济增长",
            "预期 上调",
            "上调",
            "lpr",
            "贷款市场报价利率",
            "5年期以上",
            "住房贷款利率",
            "个人住房贷款利率",
            "个人住房公积金贷款利率",
            "住房公积金贷款利率",
            "商品住宅销售价格",
            "70个大中城市",
            "居民收入和消费支出",
            "全国居民人均消费支出",
            "支付体系运行总体情况",
            "移动支付",
            "业务金额",
            "业务笔数",
        ),
        "scopes": ("finance_macro", "finance_news", "global_official"),
        "fallback": ("finance_research", "business"),
        "sites": ("stats.gov.cn", "pbc.gov.cn", "safe.gov.cn", "fred.stlouisfed.org", "cmegroup.com", "imf.org", "bankofengland.co.uk", "ons.gov.uk"),
        "roles": ("macro_data", "central_bank_notice", "statistics_release", "market_expectation"),
        "warning": "宏观数据必须核对发布机构、统计口径和日期；市场预期不等于政策决定。",
    },
    {
        "intent": "finance_sentiment",
        "terms": (
            "雪球",
            "股吧",
            "散户",
            "情绪",
            "看多",
            "看空",
            "热议",
            "舆情",
            "韭菜",
            "爆仓",
            "利空",
            "下跌原因",
            "暴涨",
            "炒作",
            "概念",
            "主力资金",
            "北向资金",
            "资金流向",
        ),
        "scopes": ("finance_sentiment", "finance_news"),
        "fallback": ("finance_disclosure", "finance_quote"),
        "sites": ("xueqiu.com", "guba.eastmoney.com", "eastmoney.com", "weibo.com"),
        "roles": ("sentiment_sample", "public_discussion", "market_news"),
        "warning": "投资者讨论只代表公开样本和情绪线索，不代表事实、总体比例或投资建议。",
    },
    {
        "intent": "finance_research",
        "terms": (
            "研报",
            "券商",
            "机构观点",
            "行业报告",
            "估值",
            "评级",
            "目标价",
            "分析师",
            "一致预期",
        ),
        "scopes": ("finance_research", "finance_disclosure", "finance_news"),
        "fallback": ("finance_macro", "business"),
        "sites": ("data.eastmoney.com", "pdf.dfcfw.com", "stock.finance.sina.com.cn", "iresearch.com.cn", "199it.com"),
        "roles": ("analyst_opinion", "industry_report", "company_filing", "market_news"),
        "warning": "研报和评级属于观点层，必须和公告、财报、宏观/行业数据交叉验证。",
    },
    {
        "intent": "hot_trend",
        "terms": ("今天", "今日", "最新", "最近", "近期", "热点", "热搜", "热议", "刷屏", "突发", "舆情", "快讯", "重大新闻", "时政", "社会热点"),
        "scopes": ("social_web", "business", "finance"),
        "fallback": ("party_central", "tech_dev"),
        "roles": ("fresh_news", "public_discussion"),
    },
)

_DOMAIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auto", ("汽车", "车", "新能源车", "新能源汽车", "智驾", "问界", "赛力斯", "小米yu7", "蔚来", "理想", "小鹏", "特斯拉", "比亚迪")),
    ("ai", ("ai", "人工智能", "大模型", "agent", "智能体", "llm", "算力", "seedance", "豆包", "doubao", "ai写作", "ai写小说", *_ROBOTICS_AI_TERMS)),
    ("wps_office", _WPS_OFFICE_TERMS),
    ("consumer", ("手机", "电脑", "家电", "相机", "耳机", "消费", "购买", "值不值得买")),
    ("career", ("招聘", "求职", "岗位", "薪资", "面试", "简历", "校招", "面经", "salary", "interview")),
    ("education", ("高校", "大学", "研究生", "招生", "导师", "院系", "推免", "考研", "雅思", "托福", "机经")),
    ("health", ("医疗", "疾病", "药", "治疗", "医生", "症状", "医院", "孕期", "肺结节", "布洛芬")),
    ("legal", ("法律", "诉讼", "判决", "合同", "律师", "侵权", "工伤", "竞业", "版权")),
    ("finance", ("财经", "股票", "股价", "行情", "财报", "公告", "基金", "债券", "宏观", "降息", "雪球", "股吧", "研报", "nvidia", "etf", "ftse", "imf", "持仓", "跟踪指数")),
    ("cybersecurity", ("cve", "漏洞", "补丁", "诈骗", "反诈", "钓鱼", "openssl", "postgresql", "prompt injection", "agent security", "mcp attack")),
    ("sports", ("体育", "比赛", "伤病", "转会", "梅西", "mbappe", "messi", "nba")),
    ("weather", ("天气", "气象", "台风", "预警", "地震", "noaa", "jma")),
    ("science", ("科学", "nasa", "詹姆斯韦伯", "外星生命", "jwst")),
    ("podcast", ("播客", "小宇宙", "podcast")),
    ("policy", ("regulation", "policy", "compliance", "law", "standard", "非遗", "数字素养", "教师职称", "反补贴", "军事部署")),
    ("company", ("pricing", "release notes", "docs", "official blog", "investor relations", "clip studio", "聚合数据", "天聚地合", "seedance", "doubao")),
    ("reviews", ("review", "reviews", "reddit", "g2", "trustpilot", "capterra")),
    ("public_opinion", ("舆情", "舆论", "风评", "声量", "社媒", "评论区", "social sentiment")),
    ("competitive_intel", ("竞品", "竞对", "竞争对手", "竞品情报", "竞品监控", "competitive landscape")),
    ("app_reviews", ("app store 评论", "应用商店评论", "google play 评论", "应用评分", "aso")),
    ("entertainment", ("文娱", "娱乐", "影视", "电影", "剧集", "综艺", "明星", "票房", "豆瓣", "猫眼", "游戏", "动漫", "漫画", "番剧", "轻小说", "二次元", "bangumi", "pixiv", "スキップとローファー", "尖帽子魔法工坊")),
    ("western_entertainment", ("欧美娱乐", "西方娱乐", "好莱坞", "hollywood", "billboard", "grammy", "taylor swift", "hbo", "deadline", "variety", "奥斯卡")),
    ("jp_kr_entertainment", ("日韩娱乐", "韩娱", "日娱", "韩媒", "日媒", "韩网", "k-pop", "kpop", "j-pop", "jpop", "oricon", "soompi", "スキップとローファー", "尖帽子魔法工坊")),
)

_HIGH_RISK_TERMS = (
    "医疗",
    "疾病",
    "治疗",
    "药",
    "医生",
    "孕期",
    "怀孕",
    "布洛芬",
    "肺结节",
    "手术",
    "法律",
    "诉讼",
    "工伤",
    "竞业",
    "签证",
    "移民",
    "投资",
    "股票",
    "银行倒闭",
    "etf",
    "质押",
    "fedwatch",
    "降息",
    "cve",
    "漏洞",
    "诈骗",
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
    site_operator = _extract_site_operator(clean_query)
    if site_operator and not site:
        site = site_operator
    semantic_analysis = analyze_query_semantics(clean_query)
    matched_rules: list[dict[str, Any]] = []
    reasons: list[str] = []
    for rule in _INTENT_RULES:
        hits = [term for term in rule["terms"] if _term_matches(text, str(term))]
        if hits:
            matched_rules.append(rule)
            reasons.append(f"{rule['intent']}: {','.join(hits[:4])}")
    wps_analysis = analyze_wps_semantics(clean_query)
    if wps_analysis.get("is_wps_office") and not any(rule["intent"] == "wps_office" for rule in matched_rules):
        wps_rule = _preset_rule("wps_office")
        if wps_rule:
            matched_rules.append(wps_rule)
            summary_terms = (
                list(wps_analysis.get("brand_terms") or [])
                + list(wps_analysis.get("vertical_terms") or [])
                + list(wps_analysis.get("ambiguous_ai_terms") or [])
            )
            reasons.append(f"wps_office_semantic:{','.join(summary_terms[:4])}")
    if semantic_analysis.get("intent_hints"):
        for intent in reversed(list(semantic_analysis.get("intent_hints") or [])):
            if any(str(rule.get("intent") or "") == intent for rule in matched_rules):
                continue
            semantic_rule = next((rule for rule in _INTENT_RULES if str(rule.get("intent") or "") == intent), None)
            if semantic_rule:
                matched_rules.insert(0, semantic_rule)
        if semantic_analysis.get("matched_rules"):
            reasons.append(
                "query_semantic:" + ",".join(str(item) for item in list(semantic_analysis.get("matched_rules") or [])[:4])
            )

    if _should_demote_broad_legal(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "legal_judicial"]
        reasons = [reason for reason in reasons if not reason.startswith("legal_judicial:")]
    if _should_demote_broad_finance_sentiment(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "finance_sentiment"]
        reasons = [reason for reason in reasons if not reason.startswith("finance_sentiment:")]
    if _should_demote_official_macro_stock_finance(text, matched_rules):
        matched_rules = [
            rule
            for rule in matched_rules
            if rule.get("intent") not in {"finance", "finance_quote", "finance_disclosure"}
        ]
        reasons = [
            reason
            for reason in reasons
            if not (
                reason.startswith("finance:")
                or reason.startswith("finance_quote:")
                or reason.startswith("finance_disclosure:")
            )
        ]
    if _should_demote_real_estate_ecommerce(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "ecommerce"]
        reasons = [reason for reason in reasons if not reason.startswith("ecommerce:")]
    if _should_demote_technical_docs_official_policy(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") not in {"policy", "official_position"}]
        reasons = [
            reason
            for reason in reasons
            if not (reason.startswith("policy:") or reason.startswith("official_position:"))
        ]
    if _should_demote_game_patch_cybersecurity(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "cybersecurity"]
        reasons = [reason for reason in reasons if not reason.startswith("cybersecurity:")]
    if _should_demote_charity_finance(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") not in {"finance", "finance_quote"}]
        reasons = [
            reason
            for reason in reasons
            if not (reason.startswith("finance:") or reason.startswith("finance_quote:"))
        ]
    if _should_demote_secondhand_company_primary(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "company_primary"]
        reasons = [reason for reason in reasons if not reason.startswith("company_primary:")]
    if _should_demote_marketplace_company_primary(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "company_primary"]
        reasons = [reason for reason in reasons if not reason.startswith("company_primary:")]
    if _should_demote_marketplace_finance(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") not in {"finance", "finance_quote"}]
        reasons = [
            reason
            for reason in reasons
            if not (reason.startswith("finance:") or reason.startswith("finance_quote:"))
        ]
    if _should_demote_procurement_finance(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") not in {"finance", "finance_disclosure"}]
        reasons = [
            reason
            for reason in reasons
            if not (reason.startswith("finance:") or reason.startswith("finance_disclosure:"))
        ]
    if _should_demote_country_industry_stock_finance(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") not in {"finance", "finance_disclosure", "finance_quote"}]
        reasons = [
            reason
            for reason in reasons
            if not (
                reason.startswith("finance:")
                or reason.startswith("finance_disclosure:")
                or reason.startswith("finance_quote:")
            )
        ]
    if _should_demote_finance_wps_office(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "wps_office"]
        reasons = [reason for reason in reasons if not reason.startswith("wps_office:") and not reason.startswith("wps_office_semantic:")]
    if _should_demote_food_price_company_primary(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "company_primary"]
        reasons = [reason for reason in reasons if not reason.startswith("company_primary:")]
    if _should_demote_business_segment_finance_quote(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "finance_quote"]
        reasons = [reason for reason in reasons if not reason.startswith("finance_quote:")]
    if _should_demote_personal_career_industry(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "industry"]
        reasons = [reason for reason in reasons if not reason.startswith("industry:")]
    if _should_demote_market_report_career(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "career"]
        reasons = [reason for reason in reasons if not reason.startswith("career:")]
    if _should_demote_marketplace_rules_tech(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "tech"]
        reasons = [reason for reason in reasons if not reason.startswith("tech:")]
    if _should_demote_broad_entertainment(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "entertainment"]
        reasons = [reason for reason in reasons if not reason.startswith("entertainment:")]
    if _should_demote_auto_sales_entertainment(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "entertainment"]
        reasons = [reason for reason in reasons if not reason.startswith("entertainment:")]
    if _should_demote_reading_notes_entertainment(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "entertainment"]
        reasons = [reason for reason in reasons if not reason.startswith("entertainment:")]
    if _should_demote_game_reaction_tech(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "tech"]
        reasons = [reason for reason in reasons if not reason.startswith("tech:")]
    if _should_demote_education_service_tech(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "tech"]
        reasons = [reason for reason in reasons if not reason.startswith("tech:")]
    if _should_demote_policy_topic_tech(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "tech"]
        reasons = [reason for reason in reasons if not reason.startswith("tech:")]
    if _should_demote_global_accessibility_domestic_policy(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "policy"]
        reasons = [reason for reason in reasons if not reason.startswith("policy:")]
    if _should_demote_pricing_standards_compliance(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "standards_compliance"]
        reasons = [reason for reason in reasons if not reason.startswith("standards_compliance:")]
    if _should_demote_standard_purchase_advice(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "purchase_advice"]
        reasons = [reason for reason in reasons if not reason.startswith("purchase_advice:")]
    if _should_demote_academic_generic_standards(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "standards_compliance"]
        reasons = [reason for reason in reasons if not reason.startswith("standards_compliance:")]
    if _should_demote_fictional_university(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "university_admissions"]
        reasons = [reason for reason in reasons if not reason.startswith("university_admissions:")]
    if _should_demote_sports_venue_rental(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "sports"]
        reasons = [reason for reason in reasons if not reason.startswith("sports:")]
    if _should_demote_broad_sports_score(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "sports"]
        reasons = [reason for reason in reasons if not reason.startswith("sports:")]
    if _should_demote_local_life_ecommerce(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "ecommerce"]
        reasons = [reason for reason in reasons if not reason.startswith("ecommerce:")]
    if _should_demote_company_business_ecommerce(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "ecommerce"]
        reasons = [reason for reason in reasons if not reason.startswith("ecommerce:")]
    if _should_demote_ai_tool_reading_notes(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "reading_notes"]
        reasons = [reason for reason in reasons if not reason.startswith("reading_notes:")]
    if _should_demote_energy_infrastructure_tech(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "tech"]
        reasons = [reason for reason in reasons if not reason.startswith("tech:")]
    if _should_demote_health_policy_entertainment(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "entertainment"]
        reasons = [reason for reason in reasons if not reason.startswith("entertainment:")]
    if _should_demote_regulator_market_industry(text, matched_rules):
        matched_rules = [rule for rule in matched_rules if rule.get("intent") != "industry"]
        reasons = [reason for reason in reasons if not reason.startswith("industry:")]
    matched_rules = _prioritize_sample_intelligence_rules(matched_rules)

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
    finance_intents = {"finance", "finance_quote", "finance_company", "finance_disclosure", "finance_news", "finance_macro", "finance_sentiment", "finance_research"}
    high_risk_intents = {"medical_health", "legal_judicial", *finance_intents, "global_policy", "cybersecurity", "weather_disaster"}

    preferred_scopes = _unique(_flatten(rule.get("scopes", ()) for rule in matched_rules))
    fallback_scopes = _unique(_flatten(rule.get("fallback", ()) for rule in matched_rules))
    cross_region_entertainment = {"global_entertainment", "jp_kr_entertainment"} & set(primary + secondary)
    if cross_region_entertainment:
        cross_region_primary = {
            "global_entertainment",
            "jp_kr_entertainment",
            "community_sample",
            "global_news",
            "company_primary",
        }
        overflow = [scope_id for scope_id in preferred_scopes if scope_id not in cross_region_primary]
        preferred_scopes = [scope_id for scope_id in preferred_scopes if scope_id in cross_region_primary]
        fallback_scopes = _unique(fallback_scopes + overflow)
    high_impact_scope_sets = {
        "cybersecurity": {"cybersecurity", "developer", "global_official", "gov"},
        "weather_disaster": {"weather_disaster", "gov", "global_official", "local_official"},
        "medical_health": {"global_official", "gov", "academic"},
        "legal_judicial": {"gov", "global_official", "local_official", "academic"},
        "global_policy": {"global_official", "global_news"},
    }
    active_high_impact = [
        intent_id for intent_id, scope_set in high_impact_scope_sets.items()
        if intent_id in primary + secondary and scope_set & set(preferred_scopes)
    ]
    if active_high_impact:
        allowed_scopes = set().union(*(high_impact_scope_sets[intent_id] for intent_id in active_high_impact))
        overflow = [scope_id for scope_id in preferred_scopes if scope_id not in allowed_scopes]
        preferred_scopes = [scope_id for scope_id in preferred_scopes if scope_id in allowed_scopes]
        fallback_scopes = _unique(fallback_scopes + overflow)
    if profile == "english":
        preferred_scopes = _english_scope_equivalents(preferred_scopes)
        fallback_scopes = _english_scope_equivalents(fallback_scopes)
    precision_intents = {"standards_compliance", "medical_health", "legal_judicial", "academic"}
    if (
        {"policy", "official_position"} & set(primary + secondary)
        and "global_policy" not in primary + secondary
        and not precision_intents & set(primary + secondary)
    ):
        policy_primary = {"gov", "party_central", "local_official"}
        if profile in {"english", "global"}:
            policy_primary = {"global_official", "global_news"}
        overflow = [scope_id for scope_id in preferred_scopes if scope_id not in policy_primary]
        preferred_scopes = [scope_id for scope_id in preferred_scopes if scope_id in policy_primary]
        fallback_scopes = _unique(fallback_scopes + overflow)
    target_sites = _unique(_flatten(rule.get("sites", ()) for rule in matched_rules))
    if semantic_analysis.get("preferred_sites"):
        target_sites = _unique(list(semantic_analysis.get("preferred_sites") or []) + target_sites)
    if site:
        target_sites.insert(0, site)
    if sites:
        target_sites = _unique(list(sites) + target_sites)
    if not (site or sites) and "university_admissions" in primary + secondary:
        target_sites = _unique(_university_target_sites(clean_query) + target_sites)
    if not (site or sites or scope or preset):
        target_sites = _unique(target_sites + _source_pack_target_sites(primary + secondary))
    if not (site or sites):
        target_sites = _unique(_topic_specific_target_sites(clean_query) + target_sites)
    if cross_region_entertainment and not (site or sites):
        domestic_entertainment_sites = {"douban.com", "maoyan.com", "bilibili.com", "weibo.com", "taptap.cn"}
        target_sites = [site_id for site_id in target_sites if site_id not in domestic_entertainment_sites]
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
            *finance_intents,
            "policy",
            "global_policy",
            "industry",
            "global_industry",
            "tech",
            "company_primary",
            "standards_compliance",
            "medical_health",
            "legal_judicial",
            "cybersecurity",
            "weather_disaster",
            "science",
            "sports",
            "career",
            "podcast",
            "test_prep",
            "education_learning",
            "education_service",
            "reading_notes",
            "transport",
            "local_life",
            "design_trend",
            "public_opinion",
            "crisis_watch",
            "competitor_watch",
            "pricing_watch",
            "review_intel",
            "app_review",
            "entertainment",
            "global_entertainment",
            "jp_kr_entertainment",
            "wps_office",
            "university_admissions",
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
    if (
        "hot_trend" in primary + secondary
        and not reading_discovery
        and not {"global_entertainment", "jp_kr_entertainment", "cybersecurity", "weather_disaster", "science", "sports", "podcast", *finance_intents} & set(primary + secondary)
        and "baidu-rss" not in recommended_feeds
    ):
        recommended_feeds.append("baidu-rss")
    if "tech" in primary + secondary and "curated" not in recommended_feeds:
        recommended_feeds.append("curated")
    ai_vertical_terms = (
        "人工智能",
        "大模型",
        "agent",
        "智能体",
        "llm",
        "openai",
        "anthropic",
        "claude",
        "gemini",
        "sora",
        "mcp",
    )
    if ("tech" in primary + secondary and _contains_any(text, ai_vertical_terms)) and "ai-vertical" not in recommended_feeds:
        recommended_feeds.append("ai-vertical")
    if "wps_office" in primary + secondary:
        if "curated" not in recommended_feeds:
            recommended_feeds.append("curated")
        if "ai-vertical" not in recommended_feeds:
            recommended_feeds.append("ai-vertical")
        if profile == "china" and "wechat-rss" not in recommended_feeds:
            recommended_feeds.append("wechat-rss")
    recommended_feeds = _unique(recommended_feeds)
    if site or sites:
        recommended_feeds = []
    recommended_commands = _recommended_commands(
        clean_query,
        intents=primary + secondary,
        domains=domains,
        feeds=recommended_feeds,
        preferred_scopes=preferred_scopes,
        target_sites=target_sites,
        profile=profile,
        read_top=read_top,
        explicit_site_filter=bool(site or sites),
    )
    read_default = 5 if {"policy", "official_position", "tech", "wps_office", "industry", "public_opinion", "crisis_watch", "competitor_watch", "pricing_watch", "review_intel", "app_review", "global_entertainment", "jp_kr_entertainment", "cybersecurity", "weather_disaster", "science", "sports", "career", "podcast", "test_prep", *finance_intents} & set(primary + secondary) else 3
    if {"standards_compliance", "medical_health", "legal_judicial", "cybersecurity", "weather_disaster"} & set(primary + secondary):
        read_default = 5
    if "reputation" in primary + secondary and not high_risk:
        read_default = 3

    plan = RoutePlan(
        query=clean_query,
        primary_intents=primary,
        secondary_intents=secondary,
        domains=domains,
        freshness=freshness,
        risk_level="high" if high_risk or high_risk_intents & set(primary + secondary) else ("medium" if advisor_recommended else "low"),
        evidence_roles=evidence_roles,
        preferred_scopes=preferred_scopes,
        fallback_scopes=[scope_id for scope_id in fallback_scopes if scope_id not in preferred_scopes],
        target_sites=target_sites[:8],
        avoid_as_primary=_avoid_as_primary(primary + secondary),
        query_variants=_query_variants(clean_query, primary + secondary, domains),
        backend_hint=(
            ["duckduckgo", "bing"]
            if {"global_entertainment", "jp_kr_entertainment", "global_policy", "cybersecurity", "weather_disaster", "science", "sports", "finance_quote", "finance_macro"} & set(primary + secondary)
            else (["baidu", "bing", "duckduckgo"] if profile == "china" else ["duckduckgo", "bing"])
        ),
        recommended_feeds=recommended_feeds,
        recommended_commands=recommended_commands,
        read_top=max(read_top if read_top is not None else read_default, 0),
        limit=max(limit if limit is not None else DEFAULT_RESEARCH_LIMIT, 1),
        advisor_recommended=advisor_recommended,
        warnings=_unique(warnings),
        explain=_unique(reasons + _domain_reasons(domains) + _route_explanations(primary, preferred_scopes, target_sites)),
        confidence=_confidence(matched_rules, scope=scope, site=site, sites=sites),
        wps_lanes=list(wps_analysis.get("lanes") or []) if "wps_office" in primary + secondary else [],
        wps_semantic_matches=wps_semantic_summary(clean_query) if "wps_office" in primary + secondary else {},
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


def format_route_chart(plan: RoutePlan | dict[str, Any], width: int = 24) -> str:
    """Render a compact ASCII view of route weight for diagnostics."""
    data = plan.to_dict() if isinstance(plan, RoutePlan) else dict(plan)
    lines = ["", "## 路由诊断图"]
    sections = [
        ("意图", list(data.get("primary_intents") or []) + list(data.get("secondary_intents") or [])),
        ("证据角色", list(data.get("evidence_roles") or [])),
        ("优先 scope", list(data.get("preferred_scopes") or [])),
    ]
    for title, values in sections:
        lines.extend(["", f"### {title}"])
        if not values:
            lines.append("- open web " + "#".ljust(width) + " 100.0% (1)")
            continue
        counts: dict[str, int] = {}
        for value in values:
            label = str(value or "unknown")
            counts[label] = counts.get(label, 0) + 1
        max_count = max(counts.values()) or 1
        total = sum(counts.values()) or 1
        max_label = max(len(label) for label in counts)
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            bar_len = max(1, round(count / max_count * width))
            bar = "#" * bar_len
            percent = count / total * 100
            lines.append(f"- {label.ljust(max_label)} {bar.ljust(width)} {percent:5.1f}% ({count})")
    confidence = float(data.get("confidence", 0.0) or 0.0)
    lines.extend(["", f"- 路由置信度: {confidence:.2f}"])
    return "\n".join(lines)


def _preset_rule(preset: str) -> dict[str, Any] | None:
    mapping = {
        "policy": "policy",
        "global_policy": "global_policy",
        "regulation": "global_policy",
        "official": "official_position",
        "local": "local",
        "public_opinion": "public_opinion",
        "public-opinion": "public_opinion",
        "opinion": "public_opinion",
        "sentiment": "public_opinion",
        "crisis": "crisis_watch",
        "crisis_watch": "crisis_watch",
        "crisis-watch": "crisis_watch",
        "competitor": "competitor_watch",
        "competitor_watch": "competitor_watch",
        "competitor-watch": "competitor_watch",
        "competitive": "competitor_watch",
        "pricing_watch": "pricing_watch",
        "pricing-watch": "pricing_watch",
        "price_watch": "pricing_watch",
        "price-watch": "pricing_watch",
        "review_intel": "review_intel",
        "review-intel": "review_intel",
        "review_mining": "review_intel",
        "review-mining": "review_intel",
        "app_review": "app_review",
        "app-review": "app_review",
        "aso": "app_review",
        "reputation": "reputation",
        "global_reputation": "global_reputation",
        "reviews": "global_reputation",
        "industry": "industry",
        "global_industry": "global_industry",
        "company": "company_primary",
        "company_primary": "company_primary",
        "ecommerce": "ecommerce",
        "entertainment": "entertainment",
        "culture": "entertainment",
        "wenyu": "entertainment",
        "yule": "entertainment",
        "movie": "entertainment",
        "film": "entertainment",
        "game": "entertainment",
        "gaming": "entertainment",
        "global_entertainment": "global_entertainment",
        "western_entertainment": "global_entertainment",
        "hollywood": "global_entertainment",
        "celebrity": "global_entertainment",
        "pop": "global_entertainment",
        "jp_kr_entertainment": "jp_kr_entertainment",
        "japan_entertainment": "jp_kr_entertainment",
        "korea_entertainment": "jp_kr_entertainment",
        "kpop": "jp_kr_entertainment",
        "jpop": "jp_kr_entertainment",
        "kdrama": "jp_kr_entertainment",
        "sports": "sports",
        "cybersecurity": "cybersecurity",
        "security": "cybersecurity",
        "weather": "weather_disaster",
        "weather_disaster": "weather_disaster",
        "science": "science",
        "podcast": "podcast",
        "career": "career",
        "test_prep": "test_prep",
        "education": "test_prep",
        "university": "university_admissions",
        "admission": "university_admissions",
        "admissions": "university_admissions",
        "graduate": "university_admissions",
        "faculty": "university_admissions",
        "advisor": "university_admissions",
        "wps_office": "wps_office",
        "wps": "wps_office",
        "wps365": "wps_office",
        "wps_365": "wps_office",
        "wps-ai": "wps_office",
        "wps_ai": "wps_office",
        "office_ai": "wps_office",
        "ai_office": "wps_office",
        "office-ai": "wps_office",
        "ai-office": "wps_office",
        "kingsoft_office": "wps_office",
        "kingsoft-office": "wps_office",
        "ppt": "wps_office",
        "presentation": "wps_office",
        "xinchuang": "wps_office",
        "tech": "tech",
        "academic": "academic",
        "scholar": "academic",
        "finance": "finance",
        "stock": "finance_quote",
        "stocks": "finance_quote",
        "quote": "finance_quote",
        "market": "finance_quote",
        "finance_quote": "finance_quote",
        "finance_disclosure": "finance_disclosure",
        "disclosure": "finance_disclosure",
        "filing": "finance_disclosure",
        "finance_company": "finance_disclosure",
        "ir": "finance_disclosure",
        "macro": "finance_macro",
        "finance_macro": "finance_macro",
        "finance_sentiment": "finance_sentiment",
        "xueqiu": "finance_sentiment",
        "guba": "finance_sentiment",
        "finance_research": "finance_research",
        "brokerage": "finance_research",
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
    variants.extend(semantic_query_variants(query, limit=4))
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
    if "policy" in intents:
        variants.append(f"{query} 政策 原文 通知")
    if "global_policy" in intents:
        variants.append(f"{query} official regulation policy primary source")
    if "reputation" in intents:
        variants.append(f"{query} 评价 体验 吐槽")
    if "global_reputation" in intents:
        variants.append(f"{query} review reddit hacker news complaints")
    if "public_opinion" in intents:
        variants.append(f"{query} 舆情 风评 声量 正负面")
        variants.append(f"{query} 微博 知乎 小红书 B站 评论")
    if "design_trend" in intents:
        variants.append(f"{query} Pantone Behance Dribbble")
        variants.append(f"{query} 小红书 设计趋势 产品配色 案例")
    if "crisis_watch" in intents:
        variants.append(f"{query} 负面 投诉 道歉 澄清")
        variants.append(f"{query} 媒体报道 官方回应 用户投诉")
    if "competitor_watch" in intents:
        variants.append(f"{query} 竞品 对比 定价 功能 更新")
        variants.append(f"{query} 官网 pricing changelog review")
    if "pricing_watch" in intents:
        variants.append(f"{query} 官方 定价 套餐 价格调整")
        variants.append(f"{query} pricing plans changelog release notes")
    if "review_intel" in intents:
        variants.append(f"{query} 用户评论 差评 好评 反馈")
        variants.append(f"{query} reviews complaints rating feedback")
    if "app_review" in intents:
        variants.append(f"{query} App Store 评论 Google Play 评分")
        variants.append(f"{query} 应用商店 版本 差评 用户反馈")
    if "purchase_advice" in intents:
        variants.append(f"{query} 优缺点 值不值得买")
    if "global_entertainment" in intents:
        variants.append(f"{query} Billboard Variety Deadline latest")
        variants.append(f"{query} official statement album single tour")
        variants.append(f"{query} Reddit fan discussion rumor debunk")
    if "jp_kr_entertainment" in intents:
        variants.append(f"{query} Soompi Naver Korea Herald")
        variants.append(f"{query} Oricon Natalie Modelpress")
        variants.append(f"{query} agency official statement")
        variants.append(f"{query} Korean media Japanese media official")
    if "entertainment" in intents:
        variants.append(f"{query} 豆瓣 评分 评价")
        variants.append(f"{query} 猫眼 灯塔 票房 热度")
        variants.append(f"{query} 微博 B站 讨论")
        if _contains_any(query.lower(), ["动漫", "漫画", "番剧", "轻小说", "二次元", "学园", "魔女", "治愈", "日常", "manga", "anime"]):
            variants.append(f"{query} Bangumi Pixiv 漫画 推荐")
            variants.append(f"{query} mangapedia manba 豆瓣 条目")
    if "company_primary" in intents:
        variants.append(f"{query} official docs pricing release notes")
    if "wps_office" in intents:
        variants.extend(wps_route_query_variants(query))
    if "tech" in intents:
        variants.append(f"{query} github issue 文档 实践")
    if "cybersecurity" in intents:
        variants.append(f"{query} CVE NVD CISA vendor advisory")
        variants.append(f"{query} 漏洞 补丁 官方 安全公告")
    if "weather_disaster" in intents:
        variants.append(f"{query} 官方 预警 气象台 路径")
        variants.append(f"{query} NOAA JMA official alert")
    if "science" in intents:
        variants.append(f"{query} NASA ESA paper official")
        variants.append(f"{query} Nature Science arXiv")
    if "sports" in intents:
        variants.append(f"{query} official injury report transfer reliable source")
        variants.append(f"{query} ESPN Sky Sports official")
    if "career" in intents:
        variants.append(f"{query} 薪资 面经 校招 招聘")
        variants.append(f"{query} salary interview levels official careers")
    if "podcast" in intents:
        variants.append(f"{query} 小宇宙 播客 单集 RSS")
        variants.append(f"{query} podcast episode RSS")
    if "test_prep" in intents:
        variants.append(f"{query} 官方 考试 政策 题库")
        variants.append(f"{query} official exam IELTS TOEFL")
    if "global_industry" in intents:
        variants.append(f"{query} market analysis competitive landscape")
    if "university_admissions" in intents:
        variants.append(f"{query} 官网 研究生招生 导师 招生目录")
        variants.append(f"{query} 院系 导师 研究方向")
        variants.append(f"{query} 研究生院 招生简章 复试 推免")
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
    if finance_intents & set(intents):
        variants.append(f"{query} 公告 财报 风险")
    if "finance_quote" in intents:
        variants.append(f"{query} 行情 股价 涨跌幅 指数")
    if "finance_disclosure" in intents:
        variants.append(f"{query} 巨潮资讯 交易所 公告 财报")
    if "finance_macro" in intents:
        variants.append(f"{query} 央行 统计局 官方数据")
    if "finance_sentiment" in intents:
        variants.append(f"{query} 雪球 股吧 热议 情绪")
    if "finance_research" in intents:
        variants.append(f"{query} 研报 券商 评级 估值")
    if "auto" in domains:
        variants.append(f"{query} 汽车 车主 试驾")
    return _unique(variants)[:5]


def _avoid_as_primary(intents: list[str]) -> list[str]:
    avoid = []
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
    if "policy" in intents or "official_position" in intents or "global_policy" in intents:
        avoid.extend(["社交/内容平台", "英文社区样本", "商业软文", "SEO 聚合页"])
    if "reputation" in intents or "global_reputation" in intents or "purchase_advice" in intents:
        avoid.extend(["单条爆款帖", "疑似营销内容", "无来源二手汇总", "单一 review 站点评分"])
    if "public_opinion" in intents:
        avoid.extend(["单个平台热帖", "未标注时间窗的情绪判断", "把样本声量写成总体民意"])
    if "crisis_watch" in intents:
        avoid.extend(["情绪化标题党", "无原文截图的爆料", "把单条投诉写成危机定论", "未核验道歉/澄清截图"])
    if "competitor_watch" in intents:
        avoid.extend(["凭印象列竞品", "无来源功能表", "过期价格截图", "把评价站排名当市场份额"])
    if "pricing_watch" in intents:
        avoid.extend(["过期价格页缓存", "社区转述价格", "无官方页面的套餐变化", "地区/币种未标注价格"])
    if "review_intel" in intents or "app_review" in intents:
        avoid.extend(["刷评样本", "无版本/地区边界的评分", "把评论比例写成真实用户比例", "下载量估算冒充官方数据"])
    if "entertainment" in intents:
        avoid.extend(["单平台热搜", "粉圈控评", "宣发通稿", "无来源搬运", "刷分/水军样本"])
    if "global_entertainment" in intents:
        avoid.extend(["粉丝账号爆料", "狗仔/小报单源", "无来源搬运", "未证实恋情/巡演传闻", "AI 生成八卦站"])
    if "jp_kr_entertainment" in intents:
        avoid.extend(["机翻搬运", "粉圈控评", "论坛单帖", "标题党韩娱站", "未核验经纪公司传闻"])
    if finance_intents & set(intents):
        avoid.extend(["社交荐股", "未核验市场传言", "无公告支撑的自媒体解读", "把研报目标价当确定结论", "无时间戳行情截图"])
    if "cybersecurity" in intents:
        avoid.extend(["未复现漏洞帖", "无 CVE 编号转载", "恐吓式安全营销", "单一论坛爆料"])
    if "weather_disaster" in intents:
        avoid.extend(["未核验社交现场图", "自媒体天气图", "过期预警"])
    if "sports" in intents:
        avoid.extend(["无来源转会爆料", "球迷论坛单帖", "过期伤病消息"])
    if "science" in intents:
        avoid.extend(["夸大科普标题", "无论文/机构来源报道", "阴谋论内容"])
    if "career" in intents:
        avoid.extend(["单个候选人样本", "过期薪资贴", "招聘广告软文"])
    if "wps_office" in intents:
        avoid.extend(["品牌通稿单源", "单条社媒吐槽", "无原文的 AI 工具榜单", "过期产品截图", "竞品软文"])
    if "podcast" in intents:
        avoid.extend(["无节目链接推荐", "营销榜单", "未核验转写"])
    if "test_prep" in intents:
        avoid.extend(["贩卖机经广告", "无出处题库", "过期考试政策"])
    if "academic" in intents:
        avoid.extend(["代投软文", "SEO 聚合页", "无出处经验帖"])
    if "university_admissions" in intents:
        avoid.extend(["论文数据库首页", "培训机构择校文章", "考研论坛二手汇总", "过期招生目录"])
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
    explicit_site_filter: bool = False,
) -> list[str]:
    """Build a small command shortlist for agents after routing."""
    commands: list[str] = []
    semantic_variants = semantic_query_variants(query, limit=1)
    command_query = semantic_variants[0] if semantic_variants else query
    quoted = _shell_quote(command_query)
    profile_part = f" --profile {profile}" if profile in {"china", "english", "hybrid"} else ""
    effective_read_top = 5 if read_top is None else max(read_top, 0)
    reading_discovery = _is_reading_discovery(query.lower())
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
    capital_finance_intents = {"finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}

    search_limit = DEFAULT_SEARCH_LIMIT
    research_limit = DEFAULT_RESEARCH_LIMIT
    hotnews_limit = DEFAULT_HOTNEWS_LIMIT
    pulse_limit = DEFAULT_PULSE_LIMIT
    feeds_limit = DEFAULT_FEEDS_LIMIT
    direct_reads = direct_source_read_commands(
        query,
        intents=intents,
        scopes=preferred_scopes,
        limit=3,
    )
    if _is_game_patch_without_security(query.lower()):
        direct_reads = [
            command
            for command in direct_reads
            if not _contains_any(command.lower(), ("cisa.gov", "openssl.org", "msrc.microsoft.com", "nvd.nist.gov"))
        ]

    if explicit_site_filter and target_sites:
        commands.append(f"guanlan search {quoted} --site {target_sites[0]}{profile_part} --limit {search_limit} --trace")
        commands.append('guanlan read "URL" --quality-report --trace')
        return _unique(commands)

    if (
        "hot_trend" in intents
        and not reading_discovery
        and profile != "english"
        and not {"global_entertainment", "jp_kr_entertainment", "cybersecurity", "weather_disaster", "science", "sports", "podcast", *finance_intents} & set(intents)
    ):
        commands.append(f"guanlan hotnews today --limit {hotnews_limit}")

    academic_like = "academic" in intents and _prefer_academic_route(query)

    if "university_admissions" in intents:
        commands.append(f"guanlan research {quoted} --preset university{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope university --limit {search_limit}")
    elif academic_like:
        academic_read_top = max(effective_read_top, 5)
        commands.append(f"guanlan research {quoted} --preset academic{profile_part} --limit {research_limit} --read-top {academic_read_top}")
    elif "medical_health" in intents:
        commands.append(f"guanlan research {quoted}{profile_part} --scope global_official --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope academic --limit {search_limit}")
    elif "standards_compliance" in intents and not (profile == "english" and "global_policy" in intents):
        commands.append(f"guanlan research {quoted}{profile_part} --scope global_official --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope gov --limit {search_limit}")
    elif "legal_judicial" in intents:
        commands.append(f"guanlan research {quoted}{profile_part} --scope gov --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope global_official --limit {search_limit}")
    elif "cybersecurity" in intents:
        commands.append(f"guanlan research {quoted}{profile_part} --scope cybersecurity --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope cybersecurity --backend duckduckgo --limit {search_limit} --trace")
    elif "weather_disaster" in intents:
        commands.append(f"guanlan search {quoted}{profile_part} --scope weather_disaster --backend duckduckgo --limit {search_limit} --trace")
        commands.append(f"guanlan research {quoted}{profile_part} --scope weather_disaster --limit {research_limit} --read-top {max(effective_read_top, 5)}")
    elif "science" in intents:
        commands.append(f"guanlan research {quoted}{profile_part} --scope science --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope science --backend duckduckgo --limit {search_limit}")
    elif "global_policy" in intents:
        commands.append(f"guanlan research {quoted} --preset global_policy{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
    elif "policy" in intents:
        commands.append(f"guanlan search {quoted}{profile_part} --scope gov --limit {search_limit} --trace")
        commands.append(f"guanlan research {quoted} --preset policy{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
    elif "official_position" in intents:
        commands.append(f"guanlan research {quoted} --preset official{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
    elif "global_entertainment" in intents:
        commands.append(f"guanlan research {quoted} --preset global_entertainment --profile english --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted} --profile english --scope global_entertainment --limit {search_limit}")
        commands.append(f"guanlan pulse {quoted} --profile english --limit {pulse_limit} --format context")
    elif "jp_kr_entertainment" in intents:
        commands.append(f"guanlan research {quoted} --preset jp_kr_entertainment --profile hybrid --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted} --profile hybrid --scope jp_kr_entertainment --limit {search_limit}")
        commands.append(f"guanlan pulse {quoted} --profile hybrid --limit {pulse_limit} --format context")
    elif "sports" in intents:
        commands.extend(direct_reads)
        commands.append(f"guanlan search {quoted}{profile_part} --scope sports --backend duckduckgo --limit {search_limit} --trace")
        commands.append(f"guanlan research {quoted}{profile_part} --scope sports --limit {research_limit} --read-top {max(effective_read_top, 5)}")
    elif "global_reputation" in intents:
        commands.append(f"guanlan research {quoted} --preset global_reputation{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 3)}")
    elif "crisis_watch" in intents:
        if profile != "english":
            commands.append(f"guanlan hotnews today --limit {hotnews_limit} --trends")
        commands.append(f"guanlan pulse {quoted}{profile_part} --limit {pulse_limit} --format context")
        commands.append(f"guanlan research {quoted} --preset crisis{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)} --advisor")
        commands.append(f"guanlan search {quoted}{profile_part} --scope social_web --limit {search_limit} --trace")
    elif "public_opinion" in intents:
        commands.append(f"guanlan pulse {quoted}{profile_part} --limit {pulse_limit} --format context")
        commands.append(f"guanlan research {quoted} --preset public_opinion{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 3)} --advisor")
        commands.append(f"guanlan search {quoted}{profile_part} --scope social_web --limit {search_limit} --trace")
    elif "competitor_watch" in intents:
        commands.append(f"guanlan research {quoted} --preset competitor{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)} --advisor")
        commands.append(f"guanlan dossier {quoted} --focus \"定位 竞品 功能 定价 口碑 风险\" --limit {research_limit} --format context")
        commands.append(f"guanlan search {quoted}{profile_part} --scope company_primary --limit {search_limit} --trace")
        commands.append(f"guanlan search {quoted}{profile_part} --scope market_review --limit {search_limit} --trace")
    elif "pricing_watch" in intents:
        commands.append(f"guanlan research {quoted} --preset pricing_watch{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope company_primary --limit {search_limit} --trace")
        commands.append(f"guanlan search {quoted}{profile_part} --scope market_review --limit {search_limit} --trace")
    elif "app_review" in intents:
        commands.append(f"guanlan research {quoted} --preset app_review{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 3)} --advisor")
        commands.append(f"guanlan search {quoted}{profile_part} --scope market_review --limit {search_limit} --trace")
        commands.append(f"guanlan pulse {quoted}{profile_part} --limit {pulse_limit} --format context")
    elif "review_intel" in intents:
        commands.append(f"guanlan research {quoted} --preset review_intel{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 3)} --advisor")
        commands.append(f"guanlan search {quoted}{profile_part} --scope market_review --limit {search_limit} --trace")
        commands.append(f"guanlan pulse {quoted}{profile_part} --limit {pulse_limit} --format context")
    elif "entertainment" in intents:
        if profile != "english":
            commands.append(f"guanlan hotnews weibo --limit {hotnews_limit}")
            commands.append(f"guanlan hotnews bilibili --limit {hotnews_limit}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope entertainment --limit {search_limit} --trace")
        commands.append(f"guanlan research {quoted} --preset entertainment{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 3)}")
        commands.append(f"guanlan pulse {quoted}{profile_part} --limit {pulse_limit} --format context")
    elif "reputation" in intents or "purchase_advice" in intents:
        commands.append(f"guanlan pulse {quoted}{profile_part} --limit {pulse_limit} --format context")
        commands.append(f"guanlan research {quoted} --preset reputation{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 3)}")
    elif "wps_office" in intents:
        commands.extend(direct_reads[:2])
        commands.append(f"guanlan research {quoted} --preset wps_office{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)} --advisor")
        commands.append(f"guanlan search {quoted}{profile_part} --scope wps_office --limit {search_limit} --trace")
        if profile != "english":
            commands.append(f"guanlan pulse {quoted}{profile_part} --limit {pulse_limit} --format context")
            commands.append("guanlan feeds curated --category ai --limit 80")
            commands.append("guanlan feeds wechat-rss --limit 80")
            commands.append("guanlan hotnews hotboard:catalog:tech --limit 30")
    elif capital_finance_intents & set(intents):
        stock_commands = _structured_stock_commands(query, intents)
        commands.extend(stock_commands[:3])
        commands.extend(direct_reads[: 1 if stock_commands else 3])
        commands.append(f"guanlan research {quoted} --preset finance{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        if "finance_quote" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_quote --limit {search_limit} --trace")
        if "finance_disclosure" in intents or "finance" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_disclosure --limit {search_limit} --trace")
        if "finance_macro" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_macro --limit {search_limit} --trace")
        if "finance_sentiment" in intents:
            commands.append("guanlan hotnews hotboard:catalog:finance --limit 30")
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_sentiment --limit {search_limit} --trace")
        if "finance_research" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_research --limit {search_limit} --trace")
    elif "company_primary" in intents:
        commands.append(f"guanlan research {quoted} --preset company{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
    elif "career" in intents:
        commands.append(f"guanlan research {quoted}{profile_part} --scope career --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope career --limit {search_limit}")
    elif "podcast" in intents:
        commands.append(f"guanlan search {quoted}{profile_part} --scope podcast --limit {search_limit}")
        commands.append(f"guanlan feeds curated-sources --keyword {quoted} --limit {feeds_limit}")
    elif "tech" in intents:
        commands.append(f"guanlan research {quoted} --preset tech{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
    elif "test_prep" in intents:
        commands.append(f"guanlan research {quoted}{profile_part} --scope test_prep --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope test_prep --limit {search_limit}")
    elif "global_industry" in intents:
        commands.append(f"guanlan research {quoted} --preset global_industry{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
    elif "industry" in intents:
        commands.append(f"guanlan research {quoted} --preset industry{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
    elif finance_intents & set(intents):
        stock_commands = _structured_stock_commands(query, intents)
        commands.extend(stock_commands[:3])
        commands.extend(direct_reads[: 1 if stock_commands else 3])
        commands.append(f"guanlan research {quoted} --preset finance{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        if "finance_quote" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_quote --limit {search_limit} --trace")
        if "finance_disclosure" in intents or "finance" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_disclosure --limit {search_limit} --trace")
        if "finance_macro" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_macro --limit {search_limit} --trace")
        if "finance_sentiment" in intents:
            commands.append("guanlan hotnews hotboard:catalog:finance --limit 30")
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_sentiment --limit {search_limit} --trace")
        if "finance_research" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_research --limit {search_limit} --trace")

    if not commands:
        scope = preferred_scopes[0] if preferred_scopes else ""
        scope_part = f" --scope {scope}" if scope else ""
        commands.append(f"guanlan search {quoted}{profile_part}{scope_part} --limit {search_limit}")

    for command in direct_reads:
        if command not in commands:
            commands.append(command)

    if target_sites and not any(site in commands[0] for site in target_sites[:1]):
        target_profile_part = profile_part
        if "global_entertainment" in intents:
            target_profile_part = " --profile english"
        elif "jp_kr_entertainment" in intents:
            target_profile_part = " --profile hybrid"
        commands.append(f"guanlan search {quoted} --site {target_sites[0]}{target_profile_part} --limit {search_limit}")

    for feed in feeds:
        if feed == "curated":
            category = " --category ai" if "ai" in domains else ""
            commands.append(f"guanlan feeds curated{category} --limit {feeds_limit}")
        elif feed == "curated-sources":
            commands.append(f"guanlan feeds curated-sources --keyword {quoted} --limit {feeds_limit}")
        elif feed == "baidu-rss":
            commands.append(f"guanlan feeds baidu-rss --limit {feeds_limit}")
        elif feed == "wechat-rss":
            commands.append(f"guanlan feeds wechat-rss --limit {feeds_limit}")

    if _needs_hotboard_route(intents):
        commands.extend(_ebrun_route_commands(query, intents=intents))
        commands.extend(_hotboard_route_commands(query, intents=intents, domains=domains))

    guarded = _guard_research_commands_for_agents(commands)
    return _prioritize_agent_route_commands(_unique(guarded))[:10]


def _guard_research_commands_for_agents(commands: list[str]) -> list[str]:
    return [_guard_research_command(command) for command in commands]


def _prioritize_agent_route_commands(commands: list[str]) -> list[str]:
    """Keep heavy research suggestions visible but behind lighter evidence-gathering steps."""

    def priority(command: str) -> tuple[int, int]:
        kind = command.split(maxsplit=2)[1] if command.startswith("guanlan ") and len(command.split()) > 1 else ""
        if kind == "stock":
            return (0, 0)
        if kind == "read":
            return (1, 0)
        if kind == "search":
            return (2, 0)
        if kind in {"feeds", "pulse"}:
            return (3, 0)
        if kind == "hotnews" and any(marker in command for marker in (" hotboard:", " ebrun:")):
            return (5, 0)
        if kind == "hotnews":
            return (4, 0)
        if kind in {"compare", "timeline", "dossier"}:
            return (6, 0)
        if kind == "research":
            return (8, 0)
        return (5, 0)

    return [command for _index, command in sorted(enumerate(commands), key=lambda item: (*priority(item[1]), item[0]))]


def _guard_research_command(command: str) -> str:
    if not command.startswith("guanlan research "):
        return command
    max_top = MAX_AGENT_RESEARCH_READ_TOP

    def replace_read_top(match: re.Match[str]) -> str:
        try:
            value = int(match.group(1))
        except ValueError:
            value = 0
        return f"--read-top {min(max(value, 0), max_top)}"

    guarded = re.sub(r"--read-top\s+(\d+)", replace_read_top, command)
    if "--read-top " not in guarded:
        guarded = f"{guarded} --read-top 0"
    if "--max-search-jobs" not in guarded:
        guarded = f"{guarded} --max-search-jobs 2"
    return guarded


def _ebrun_route_commands(query: str, *, intents: list[str]) -> list[str]:
    """Suggest Ebrun vertical channel follow-ups for ecommerce-like tasks."""
    if not ({"ecommerce", "industry"} & set(intents)):
        return []
    try:
        from guanlan.ebrun_channels import ebrun_query_variants, match_ebrun_channels
    except Exception:
        return []

    commands: list[str] = []
    for channel in match_ebrun_channels(query, limit=2):
        commands.append(f"guanlan hotnews {channel.source_id} --limit 10")
    for variant in ebrun_query_variants(query, limit=1):
        variant_query = str(variant.get("query") or query).replace('"', '\\"')
        commands.append(f'guanlan search "{variant_query}" --profile china --scope ecommerce --limit 80 --trace')
    return commands[:3]


def _hotboard_route_commands(query: str, *, intents: list[str], domains: list[str]) -> list[str]:
    """Suggest local hotboard catalog expansion without making detail API the default."""
    try:
        from guanlan.hotboard_catalog import ROUTE_CATEGORY_BY_INTENT, recommend_nodes_for_route
    except Exception:
        return []

    categories = _unique([ROUTE_CATEGORY_BY_INTENT[intent] for intent in intents if intent in ROUTE_CATEGORY_BY_INTENT])
    if not categories and "hot_trend" not in intents:
        return []
    commands: list[str] = []
    for category in categories[:1]:
        commands.append(f"guanlan hotnews hotboard:catalog:{category} --limit 30")
    curated_nodes = _source_pack_hotboard_nodes(intents, limit=2)
    fallback_nodes = recommend_nodes_for_route(query, intents=intents, domains=domains, limit=2)
    for node in [*curated_nodes, *fallback_nodes][:2]:
        node_id = str(node.get("node_id") or node.get("hashid") or "")
        if node_id:
            commands.append(f"guanlan hotnews hotboard:snapshots:{node_id} --limit 20")
    return commands[:3]


def _source_pack_target_sites(intents: list[str]) -> list[str]:
    try:
        from guanlan.source_packs import recommended_sites_for_intents

        return recommended_sites_for_intents(intents, limit=6)
    except Exception:
        return []


def _source_pack_hotboard_nodes(intents: list[str], *, limit: int = 2) -> list[dict[str, str]]:
    try:
        from guanlan.source_packs import hotboard_nodes_for_intents

        return hotboard_nodes_for_intents(intents, limit=limit)
    except Exception:
        return []


def _needs_hotboard_route(intents: list[str]) -> bool:
    return bool(
        {
            "hot_trend",
            "entertainment",
            "reputation",
            "purchase_advice",
            "public_opinion",
            "crisis_watch",
            "competitor_watch",
            "review_intel",
            "app_review",
            "industry",
            "ecommerce",
            "finance",
            "finance_quote",
            "finance_disclosure",
            "finance_macro",
            "finance_sentiment",
            "finance_research",
            "wps_office",
        }
        & set(intents)
    )


def _structured_stock_commands(query: str, intents: list[str]) -> list[str]:
    """Suggest structured stock data before dynamic finance web pages."""
    finance_quote_like = bool({"finance", "finance_quote", "finance_sentiment"} & set(intents))
    if not finance_quote_like:
        return []
    if "finance_macro" in intents and "finance_quote" not in intents:
        quote_terms = (
            "股票",
            "股价",
            "行情",
            "代码",
            "涨跌",
            "资金流向",
            "stock price",
            "share price",
            "ticker",
            "earnings",
        )
        if not _contains_any(query.lower(), quote_terms):
            return []
    try:
        from guanlan.stockdata import infer_stock_target, normalize_symbol
    except Exception:
        return []
    target = infer_stock_target(query)
    if not target:
        return []
    normalized = normalize_symbol(target)
    raw = " ".join((query or "").split()).strip()
    looks_symbol = bool(re.fullmatch(r"(?:sh|sz|bj)\d{6}|hk\d{5}|us[A-Z]{1,5}", normalized))
    cleaned_target = target != raw
    if not (looks_symbol or cleaned_target or "finance_quote" in intents):
        return []
    quoted_target = _shell_quote(target)
    commands = [f"guanlan stock plan {quoted_target}", f"guanlan stock quote {quoted_target}"]
    if "finance_quote" in intents or "finance" in intents:
        commands.append(f"guanlan stock detail {quoted_target}")
    if "finance_sentiment" in intents or re.search(r"资金流向|主力|净流入|fund\s*flow", query, flags=re.I):
        commands.append(f"guanlan stock fundflow {quoted_target}")
    return commands


def _shell_quote(value: str) -> str:
    escaped = (value or "").replace('"', '\\"')
    return f'"{escaped}"'


def _extract_site_operator(query: str) -> str:
    match = re.search(r"\bsite:([A-Za-z0-9.-]+\.[A-Za-z]{2,})", query or "", re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _is_reading_discovery(text: str) -> bool:
    return any(term in text for term in ("值得读", "好文章", "技术文章", "技术博客", "阅读", "精品源", "rss", "opml"))


def _prefer_academic_route(query: str) -> bool:
    text = query.lower()
    academic_terms = (
        "ei",
        "sci",
        "ssci",
        "scopus",
        "compendex",
        "engineering village",
        "投稿",
        "收录",
        "检索",
        "会议",
        "期刊",
        "paper",
        "preprint",
        "arxiv",
        "预印本",
        "proceedings",
        "cfp",
    )
    return _contains_any(text, academic_terms)


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
    if "public_opinion" in intents:
        output.append("舆情/风评问题需要把公开讨论、评论样本、媒体报道和时间窗分开看；样本不是民调。")
    if "crisis_watch" in intents:
        output.append("危机监测需要先看负面信号和投诉扩散，再核验媒体报道、官方/公司回应与事实边界。")
    if "competitor_watch" in intents:
        output.append("竞品观察需要先确认对象边界和同类对象，再核验官网/价格页/更新记录/评价样本。")
    if "pricing_watch" in intents:
        output.append("价格观察优先官方价格页、帮助中心或发布说明；社区转述只能作反应样本。")
    if "review_intel" in intents:
        output.append("评论挖掘适合提取用户语言、痛点和功能诉求，但必须保留平台/地区/版本偏差。")
    if "app_review" in intents:
        output.append("应用评论需要区分 App Store/Google Play 等应用商店评分、版本评论和第三方榜单估算。")
    if "company_primary" in intents:
        output.append("英文产品/公司问题优先核验公司一手资料，再补媒体和社区样本。")
    if "global_policy" in intents:
        output.append("英文政策/监管问题需要官方、监管或标准组织原文作为主证据。")
    if "academic" in intents:
        output.append("学术检索问题需要数据库/出版商口径、会议 CFP 和高校认定口径分开核验。")
    if "university_admissions" in intents:
        output.append("高校招生/导师问题优先院系官网、研究生招生网、招生目录和导师主页；学术数据库只作背景。")
    if "entertainment" in intents:
        output.append("文娱内容需要把票房/播放/榜单、用户评分、产业报道和粉圈讨论分层看，避免把热度写成口碑。")
    if "global_entertainment" in intents:
        output.append("欧美娱乐内容需要优先英文行业媒体、榜单/奖项与艺人/厂牌一手信息，粉丝和八卦站只能作线索。")
    if "jp_kr_entertainment" in intents:
        output.append("日韩娱乐内容需要分清本地媒体/榜单、经纪公司口径、英文翻译站和粉丝讨论，并标注跨语言转述风险。")
    if "tech" in intents:
        output.append("科技/技术内容除开发者社区和代码仓库外，必须额外补一轮 RSS/精品内容流作为阅读发现视角。")
    if "wps_office" in intents:
        output.append("WPS/AI Office 选题要以金山办公/WPS 为锚点，同时主动外扩到办公 AI、PPT/文档协作、SaaS、信创、安全、竞品和社区样本；必须补 RSS/精品内容流，避免只看品牌稿。")
    if "standards_compliance" in intents:
        output.append("标准/合规问题需要标准原文、监管解释、实施材料和厂商声明分层引用。")
    if "medical_health" in intents:
        output.append("医疗健康问题需要专业机构、监管和临床指南作主证据，并明确非诊疗建议边界。")
    if "legal_judicial" in intents:
        output.append("法律司法问题需要条文、司法解释、裁判文书和专业解读分开核验。")
    if "cybersecurity" in intents:
        output.append("网络安全问题需要 CVE/NVD/CISA/厂商公告与补丁说明作主证据，社区复现只能作补充。")
    if "weather_disaster" in intents:
        output.append("天气灾害问题需要官方气象/应急机构的实时预警与路径信息作为主证据。")
    if "science" in intents:
        output.append("科学新闻需要机构原文、论文或预印本作为主证据，媒体报道用于解释传播层。")
    if "sports" in intents:
        output.append("体育问题需要区分官方数据、媒体报道、转会爆料和球迷讨论。")
    if "career" in intents:
        output.append("职场问题需要区分官方岗位、薪资样本、面经和招聘市场报告。")
    if "podcast" in intents:
        output.append("播客发现需要节目/单集元数据、RSS 和听众样本分层看。")
    if "test_prep" in intents:
        output.append("考试备考问题需要官方考试政策、培训材料和考生经验分层核验。")
    if {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"} & set(intents):
        output.append("财经问题需要把行情、公告披露、监管/宏观数据、财经新闻、研报观点和投资者情绪分层看；只输出证据边界，不给投资建议。")
    return output


def _domain_reasons(domains: list[str]) -> list[str]:
    return [f"domain:{domain}" for domain in domains]


def _university_target_sites(query: str) -> list[str]:
    """Add high-signal university sites when the named school is obvious."""
    text = (query or "").lower()
    sites: list[str] = []
    if any(term in text for term in ("清华", "tsinghua")):
        sites.extend(
            [
                "cs.tsinghua.edu.cn",
                "yz.tsinghua.edu.cn",
                "gradadmission.tsinghua.edu.cn",
                "www.tsinghua.edu.cn",
            ]
        )
    if any(term in text for term in ("北大", "北京大学", "pku")):
        sites.extend(["eecs.pku.edu.cn", "grs.pku.edu.cn", "admission.pku.edu.cn", "www.pku.edu.cn"])
    if any(term in text for term in ("浙大", "浙江大学", "zju")):
        sites.extend(["cs.zju.edu.cn", "grs.zju.edu.cn", "www.zju.edu.cn"])
    if any(term in text for term in ("复旦", "fudan")):
        sites.extend(["cs.fudan.edu.cn", "gsao.fudan.edu.cn", "www.fudan.edu.cn"])
    if any(term in text for term in ("上海交大", "上海交通大学", "sjtu")):
        sites.extend(["cs.sjtu.edu.cn", "yzb.sjtu.edu.cn", "www.sjtu.edu.cn"])
    if any(term in text for term in ("中科大", "中国科学技术大学", "ustc")):
        sites.extend(["cs.ustc.edu.cn", "gradschool.ustc.edu.cn", "www.ustc.edu.cn"])
    if any(term in text for term in ("南大", "南京大学", "nju")):
        sites.extend(["cs.nju.edu.cn", "grawww.nju.edu.cn", "www.nju.edu.cn"])
    return _unique(sites)


def _topic_specific_target_sites(query: str) -> list[str]:
    """Promote known high-signal original sites for recurring niche topics."""
    text = (query or "").lower()
    sites: list[str] = []
    if any(term in text for term in ("yd/t", "工信部", "信息无障碍", "适老化", "无障碍环境建设法", "公共场所数字化指示")):
        sites.extend(["miit.gov.cn", "std.samr.gov.cn", "samr.gov.cn", "w3.org"])
    if any(term in text for term in ("中医药", "治未病", "中医养生", "中医药法", "中医养生保健")):
        sites.extend(["natcm.gov.cn", "gov.cn", "nhc.gov.cn", "npc.gov.cn"])
    if any(term in text for term in ("医疗广告", "广告法", "宣传疗效", "不得保证治愈", "市场监督管理总局", "市场监管总局")):
        sites.extend(["samr.gov.cn", "npc.gov.cn", "gov.cn"])
    if any(term in text for term in ("非遗", "非物质文化遗产", "非遺", "制香", "申报政策", "申報政策")):
        sites.extend(["ihchina.cn", "mct.gov.cn", "gov.cn"])
    if any(term in text for term in ("伊春", "香养基地", "伊春森工", "林下经济")):
        sites.extend(["yichun.gov.cn", "hlj.gov.cn"])
    if any(term in text for term in ("新疆", "伊犁", "独库公路", "伊昭公路", "赛里木湖", "喀拉峻", "夏塔", "库尔德宁", "琼库什台")):
        sites.extend(["xj.gov.cn", "xjjt.gov.cn", "yili.gov.cn"])
    if any(term in text for term in ("数字素养", "全民数字素养", "提升全民数字素养与技能", "中央网信办", "网信办")):
        sites.extend(["cac.gov.cn", "moe.gov.cn", "miit.gov.cn", "mohrss.gov.cn", "gov.cn"])
    if any(term in text for term in ("数据安全法", "个人信息保护法", "爬虫", "反爬", "招聘平台", "开放数据")):
        sites.extend(["cac.gov.cn", "npc.gov.cn", "samr.gov.cn", "court.gov.cn"])
    if any(term in text for term in ("教师职称", "副高评审", "职称评审", "课题申报", "学术伦理", "广东省")):
        sites.extend(["gd.gov.cn", "hrss.gd.gov.cn", "edu.gd.gov.cn", "szeb.sz.gov.cn"])
    if "深圳" in text and any(term in text for term in ("住房公积金", "公积金贷款", "首套房", "最低首付")):
        sites.extend(["gjj.sz.gov.cn", "zjj.sz.gov.cn", "sz.gov.cn"])
    if any(term in text for term in ("贷款市场报价利率", "lpr", "中国人民银行", "支付体系运行总体情况", "移动支付", "非银行支付机构")):
        sites.extend(["pbc.gov.cn", "chinamoney.com.cn"])
    if any(term in text for term in ("国家统计局", "70个大中城市", "商品住宅销售价格", "居民收入和消费支出", "全国居民人均消费支出")):
        sites.extend(["stats.gov.cn"])
    if any(term in text for term in ("契税", "税收政策", "房地产市场平稳健康发展", "财政部", "税务总局")):
        sites.extend(["mof.gov.cn", "chinatax.gov.cn", "gov.cn"])
    if any(term in text for term in ("中国互联网络发展状况统计报告", "互联网络发展状况统计报告", "cnnic", "网络支付 用户规模")):
        sites.extend(["cnnic.net.cn"])
    if any(term in text for term in ("深远海", "柔直", "柔性直流", "输电技术", "海上风电", "海缆")):
        sites.extend(["nea.gov.cn", "sgcc.com.cn", "csg.cn", "csee.org.cn"])
    if any(term in text for term in ("中创新航", "calb")):
        sites.extend(["calb-tech.com", "hkexnews.hk"])
    if any(term in text for term in ("国轩高科", "gotion")):
        sites.extend(["gotion.com.cn", "gotion.com", "cninfo.com.cn"])
    if any(term in text for term in ("亿纬锂能", "eve energy", "evebattery")):
        sites.extend(["evebattery.com", "cninfo.com.cn"])
    if any(term in text for term in ("宁德时代", "catl", "evogo", "时代电服", "巧克力换电", "骐骥换电")):
        sites.extend(["catl.com", "cninfo.com.cn"])
    if any(term in text for term in ("华为", "huawei", "铁三角", "销售组织架构")):
        sites.extend(["huawei.com", "consumer.huawei.com", "carrier.huawei.com"])
    bill_export_terms = ("账单导出", "导出账单", "交易账单", "交易记录", "个人账单", "csv", "邮箱")
    if "微信支付" in text and any(term in text for term in bill_export_terms):
        sites.extend(["pay.weixin.qq.com", "kf.qq.com"])
    if "支付宝" in text and any(term in text for term in bill_export_terms):
        sites.extend(["help.alipay.com", "opendocs.alipay.com"])
    if any(term in text for term in ("notificationlistenerservice", "notification listener service", "通知监听服务", "android 通知监听")):
        sites.extend(["developer.android.com"])
    if any(term in text for term in ("icost", "callback url", "x-callback-url", "url scheme")):
        sites.extend(["help.icostapp.com"])
    if any(term in text for term in ("postgresql", "postgres")):
        sites.extend(["postgresql.org", "nvd.nist.gov", "cisa.gov"])
    if any(term in text for term in ("node.js", "nodejs", "node js")):
        sites.extend(["nodejs.org", "github.com/nodejs/node"])
    if any(term in text for term in ("vscode", "vs code", "visual studio code", "调试新特性")):
        sites.extend(["code.visualstudio.com", "github.com/microsoft/vscode"])
    if any(term in text for term in ("wordpress", "woocommerce", "spectra")):
        sites.extend(["wordpress.org", "woocommerce.com", "wpspectra.com"])
    if any(term in text for term in ("clip studio paint", "clip studio")):
        sites.extend(["clipstudio.net", "celsys.com"])
    if any(term in text for term in ("聚合数据", "天聚地合", "juhe")):
        sites.extend(["juhe.cn", "www.juhe.cn"])
    if any(term in text for term in ("seedance", "豆包", "doubao", "字节跳动", "volcengine")):
        sites.extend(["volcengine.com", "doubao.com", "coze.cn", "bytedance.com"])
    if any(term in text for term in ("coze", "扣子")):
        sites.extend(["coze.cn", "coze.com", "volcengine.com", "bytedance.com"])
    if any(term in text for term in ("notion", "notion ai")):
        sites.extend(["notion.com"])
    if "calm" in text:
        sites.extend(["calm.com"])
    if "replika" in text:
        sites.extend(["replika.com"])
    if any(term in text for term in ("lovot", "groove-x", "groovex")):
        sites.extend(["groove-x.com", "lovot.life"])
    if any(term in text for term in ("used car", "pre-purchase", "mechanic inspection")):
        sites.extend(["consumerreports.org", "nhtsa.gov"])
    if any(term in text for term in ("pearl abyss", "红色沙漠", "crimson desert")):
        sites.extend(["pearlabyss.com"])
    if any(term in text for term in ("绝区零", "比利·基德", "比利基德", "星辉骑士")):
        sites.extend(["zenless.hoyoverse.com", "hoyolab.com", "miyoushe.com"])
    if any(term in text for term in ("可灵", "kling", "即梦", "海螺", "通义万相")):
        sites.extend(["klingai.com", "jimeng.jianying.com", "hailuoai.video", "tongyi.aliyun.com"])
    if any(term in text for term in ("军事领域", "军事热点", "国防部")):
        sites.extend(["mod.gov.cn", "81.cn", "xinhuanet.com"])
    if any(term in text for term in ("军事演习", "军事部署", "西南诸岛")):
        sites.extend(["mod.go.jp", "mofa.go.jp", "japan.kantei.go.jp"])
    if any(term in text for term in ("反补贴", "anti-subsidy", "countervailing", "关税税率", "中国电动车")):
        sites.extend(["ec.europa.eu", "trade.ec.europa.eu", "eur-lex.europa.eu"])
    if any(term in text for term in ("欧洲无障碍法案", "eaa", "european accessibility act")):
        sites.extend(["ec.europa.eu", "eur-lex.europa.eu", "w3.org"])
    if any(
        term in text
        for term in (
            "英国企业",
            "uk companies",
            "企业并购",
            "m&a",
            "uk eu trade",
            "starmer",
            "改革党",
            "英国移民法案",
            "欧盟贸易",
            "斯塔默",
        )
    ):
        sites.extend(["gov.uk", "ons.gov.uk", "ft.com"])
    if any(term in text for term in ("ftse", "gilts", "bond yields", "uk stocks")):
        sites.extend(["londonstockexchange.com", "bankofengland.co.uk", "finance.yahoo.com"])
    if any(term in text for term in ("bank of england", "boe", "英国经济", "经济增长")):
        sites.extend(["bankofengland.co.uk", "ons.gov.uk", "imf.org"])
    if "imf" in text:
        sites.extend(["imf.org"])
    if any(term in text for term in ("harness ci/cd", "delegate 代理原理")):
        sites.extend(["harness.io", "developer.harness.io"])
    if any(term in text for term in ("natspec", "product partner", "建筑规格")):
        sites.extend(["natspec.com.au"])
    if any(term in text for term in ("反倾销", "anti-dumping", "antidumping", "ad commission")):
        sites.extend(["adcommission.gov.au", "industry.gov.au"])
    if any(term in text for term in ("战锤", "warhammer", "星际战士", "space marine")):
        sites.extend(["warhammer-community.com", "games-workshop.com"])
    if any(term in text for term in ("青秀山", "青秀山风景区", "兰湖", "国玉堂艺术馆")):
        sites.extend(["qxsfjq.com", "nanning.gov.cn", "gxzf.gov.cn"])
    if any(term in text for term in ("三体", "给岁月以文明", "给文明以岁月")):
        sites.extend(["book.douban.com", "douban.com", "weread.qq.com"])
    if any(term in text for term in ("礼记", "聘义", "君子比德于玉", "黄帝内经", "上古天真论", "法于阴阳")):
        sites.extend(["ctext.org", "zh.wikisource.org", "guoxue.com"])
    return _unique(sites)


def _english_scope_equivalents(scopes: list[str]) -> list[str]:
    mapping = {
        "gov": ["global_official"],
        "party_central": ["global_official", "global_news"],
        "local_official": ["global_official", "global_news"],
        "business": ["industry_analysis", "global_news"],
        "ecommerce": ["industry_analysis", "market_review"],
        "tech_dev": ["developer", "community_sample"],
        "wps_office": ["company_primary", "developer", "industry_analysis", "community_sample", "market_review"],
        "finance": ["global_official", "global_news", "company_primary"],
        "finance_quote": ["global_news", "company_primary"],
        "finance_disclosure": ["global_official", "company_primary"],
        "finance_company": ["company_primary", "global_official"],
        "finance_news": ["global_news", "industry_analysis"],
        "finance_macro": ["global_official", "global_news"],
        "finance_sentiment": ["community_sample", "market_review"],
        "finance_research": ["industry_analysis", "global_news"],
        "social_web": ["community_sample", "market_review"],
        "entertainment": ["global_entertainment", "community_sample"],
        "university": ["global_official", "academic"],
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


def _should_demote_official_macro_stock_finance(text: str, rules: list[dict[str, Any]]) -> bool:
    """Official housing, tax, payment, and statistics lookups are not stock tasks."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"finance", "finance_quote", "finance_disclosure"} & intents:
        return False
    official_macro_terms = (
        "中国人民银行",
        "央行",
        "贷款市场报价利率",
        "lpr",
        "支付体系运行总体情况",
        "移动支付",
        "业务金额",
        "业务笔数",
        "非银行支付机构",
        "支付账户",
        "住房公积金",
        "公积金贷款",
        "个人住房贷款",
        "最低首付",
        "首套房",
        "契税",
        "税收政策",
        "房地产市场平稳健康发展",
        "财政部",
        "税务总局",
        "商品住宅销售价格",
        "二手住宅",
        "居民收入和消费支出",
        "国家统计局",
        "互联网络发展状况统计报告",
        "cnnic",
    )
    capital_market_terms = (
        "股票",
        "股价",
        "上市公司",
        "交易所",
        "财报",
        "年报",
        "季报",
        "研报",
        "减持",
        "质押",
        "雪球",
        "股吧",
        "基金净值",
        "etf",
        "cninfo",
        "sse",
        "szse",
    )
    return _contains_any(text, official_macro_terms) and not _contains_any(text, capital_market_terms)


def _should_demote_real_estate_ecommerce(text: str, rules: list[dict[str, Any]]) -> bool:
    """Real-estate statistics and housing policy should not be treated as second-hand commerce."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "ecommerce" not in intents:
        return False
    real_estate_terms = (
        "商品住宅",
        "二手住宅",
        "住宅销售价格",
        "房地产",
        "住房公积金",
        "公积金贷款",
        "首套房",
        "最低首付",
        "个人住房贷款",
    )
    return _contains_any(text, real_estate_terms) and bool({"policy", "finance_macro", "local"} & intents)


def _should_demote_technical_docs_official_policy(text: str, rules: list[dict[str, Any]]) -> bool:
    """Generic 官方/通知 terms inside developer docs should not force gov routing."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"policy", "official_position"} & intents:
        return False
    if not {"tech", "company_primary"} & intents:
        return False
    doc_terms = ("官方文档", "文档", "docs", "documentation", "developer", "开发者文档")
    technical_terms = (
        "android",
        "notificationlistenerservice",
        "notification listener service",
        "通知监听服务",
        "api",
        "sdk",
        "url scheme",
        "callback url",
        "x-callback-url",
        "icost",
        "tasker",
        "github",
    )
    hard_policy_terms = (
        "政策",
        "法规",
        "监管",
        "办法",
        "条例",
        "征求意见",
        "数据安全法",
        "个人信息保护法",
        "合规",
        "法律风险",
    )
    return _contains_any(text, doc_terms) and _contains_any(text, technical_terms) and not _contains_any(text, hard_policy_terms)


def _should_demote_broad_legal(text: str, rules: list[dict[str, Any]]) -> bool:
    """Avoid routing brand/product complaint monitoring into legal search only."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "legal_judicial" not in intents:
        return False
    if not {"reputation", "public_opinion", "crisis_watch", "review_intel"} & intents:
        return False
    strong_legal_terms = (
        "法律",
        "诉讼",
        "判决",
        "判例",
        "合同",
        "律师",
        "侵权",
        "司法解释",
        "房产纠纷",
        "婚前财产",
        "财产纠纷",
        "房产加名",
        "纠纷",
        "劳动仲裁",
        "仲裁",
        "加班费",
        "工伤",
        "竞业",
        "版权",
        "著作权",
        "许可证",
        "法院",
        "裁判文书",
        "条例",
        "lawsuit",
        "court",
        "legal",
    )
    return not _contains_any(text, strong_legal_terms)


def _should_demote_charity_finance(text: str, rules: list[dict[str, Any]]) -> bool:
    """Keep charity/foundation transparency queries out of stock/fund routing."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"finance", "finance_quote"} & intents:
        return False
    charity_terms = ("基金会", "慈善", "公益", "善款", "捐款", "捐赠")
    if not _contains_any(text, charity_terms):
        return False
    capital_market_terms = (
        "股票",
        "股价",
        "基金净值",
        "etf",
        "行情",
        "大盘",
        "财报",
        "公告",
        "雪球",
        "股吧",
        "研报",
        "投资者",
        "看多",
        "看空",
        "净值",
        "收益率",
        "申购",
        "赎回",
    )
    return not _contains_any(text, capital_market_terms)


def _should_demote_sports_venue_rental(text: str, rules: list[dict[str, Any]]) -> bool:
    """Avoid treating sports venue rental/local listings as sports news."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "sports" not in intents:
        return False
    venue_terms = ("体育馆", "场馆", "运动场", "篮球馆", "羽毛球馆")
    rental_terms = ("出租", "招租", "租赁", "场地", "招商")
    return _contains_any(text, venue_terms) and _contains_any(text, rental_terms)


def _should_demote_broad_sports_score(text: str, rules: list[dict[str, Any]]) -> bool:
    """Keep 对比/对比分析 from matching the sports score term 比分."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "sports" not in intents:
        return False
    sports_entities = (
        "体育",
        "赛程",
        "比赛",
        "比分直播",
        "伤病",
        "转会",
        "梅西",
        "姆巴佩",
        "mbappe",
        "messi",
        "nba",
        "fifa",
        "uefa",
        "lpl",
        "电竞",
    )
    non_sports_context = ("对比", "对比分析", "产品流程", "用户体验", "ppt", "wps", "ai ppt", "gamma", "tome")
    return _contains_any(text, non_sports_context) and not _contains_any(text, sports_entities)


def _should_demote_local_life_ecommerce(text: str, rules: list[dict[str, Any]]) -> bool:
    """横琴/到店攻略里的小店不是抖音小店/零售电商。"""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"local_life", "ecommerce"} <= intents:
        return False
    local_visit_terms = (
        "横琴",
        "咖啡",
        "咖啡店",
        "咖啡馆",
        "书店",
        "书吧",
        "文艺小店",
        "安静小店",
        "早午餐",
        "brunch",
        "周末",
        "晨间",
        "看书",
    )
    marketplace_terms = ("抖音小店", "淘宝", "天猫", "京东", "拼多多", "亚马逊", "shopify", "shopee", "lazada")
    return _contains_any(text, local_visit_terms) and not _contains_any(text, marketplace_terms)


def _should_demote_company_business_ecommerce(text: str, rules: list[dict[str, Any]]) -> bool:
    """Battery/company business-model lookups can contain 品牌 but need company/industry sources."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "ecommerce" not in intents or not {"company_primary", "industry", "global_industry"} & intents:
        return False
    company_business_terms = (
        "宁德时代",
        "catl",
        "evogo",
        "时代电服",
        "巧克力换电",
        "骐骥换电",
        "换电品牌",
        "中创新航",
        "calb",
        "国轩高科",
        "gotion",
        "亿纬锂能",
        "华为",
        "组织架构",
        "组织结构",
        "组织变革",
        "业务模式",
        "管理层调整",
        "事业部",
        "销售组织架构",
    )
    marketplace_terms = ("淘宝", "天猫", "京东", "拼多多", "亚马逊", "抖音小店", "shopify", "shopee", "lazada")
    return _contains_any(text, company_business_terms) and not _contains_any(text, marketplace_terms)


def _should_demote_ai_tool_reading_notes(text: str, rules: list[dict[str, Any]]) -> bool:
    """AI 读书笔记工具是产品/口碑任务，不是书摘或读者笔记任务。"""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "reading_notes" not in intents:
        return False
    tool_context = ("ai", "ai工具", "工具", "神器", "产品")
    reading_tool_terms = ("读书笔记工具", "阅读笔记工具", "ai读书笔记", "ai 读书笔记")
    return _contains_any(text, reading_tool_terms) and _contains_any(text, tool_context)


def _should_demote_energy_infrastructure_tech(text: str, rules: list[dict[str, Any]]) -> bool:
    """Power-infrastructure technology news needs industry/official energy sources, not dev feeds."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "tech" not in intents or not {"industry", "global_industry"} & intents:
        return False
    energy_terms = ("深远海", "柔直", "柔性直流", "输电技术", "海上风电", "海缆", "电网")
    dev_terms = ("github", "sdk", "api", "源码", "代码", "部署", "bug", "开源", "开发者", "文档")
    return _contains_any(text, energy_terms) and not _contains_any(text, dev_terms)


def _should_demote_health_policy_entertainment(text: str, rules: list[dict[str, Any]]) -> bool:
    """医疗广告/中医政策里的治愈是法规语境，不是文娱治愈题材。"""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "entertainment" not in intents or not {"medical_health", "legal_judicial", "policy"} & intents:
        return False
    health_policy_terms = (
        "医疗广告",
        "中医药",
        "中医养生",
        "中医养生保健",
        "宣传疗效",
        "不得保证治愈",
        "不得从事医疗活动",
        "国家市场监督管理总局",
        "国家中医药管理局",
    )
    hard_entertainment_terms = ("电影", "电视剧", "动漫", "漫画", "番剧", "游戏", "演员", "票房")
    return _contains_any(text, health_policy_terms) and not _contains_any(text, hard_entertainment_terms)


def _should_demote_regulator_market_industry(text: str, rules: list[dict[str, Any]]) -> bool:
    """市场监督管理总局 is a regulator, not a market/industry signal."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "industry" not in intents or not {"policy", "legal_judicial", "medical_health"} & intents:
        return False
    regulator_terms = ("国家市场监督管理总局", "市场监督管理总局", "市场监管总局", "市场监管")
    return _contains_any(text, regulator_terms)


def _should_demote_secondhand_company_primary(text: str, rules: list[dict[str, Any]]) -> bool:
    """Second-hand price lookups should not inherit generic company-site routing."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "company_primary" not in intents:
        return False
    secondhand_terms = ("二手", "闲鱼", "转转", "回收价", "中古", "second hand", "resale")
    price_terms = ("价格", "报价", "多少钱", "行情", "估价", "price")
    if not (_contains_any(text, secondhand_terms) and _contains_any(text, price_terms)):
        return False
    official_terms = ("官网", "官方", "发布", "上线", "订阅", "会员", "pricing", "release notes", "official")
    return not _contains_any(text, official_terms)


def _should_demote_marketplace_company_primary(text: str, rules: list[dict[str, Any]]) -> bool:
    """Marketplace product price lookups should not be treated as vendor docs."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"company_primary", "ecommerce"} <= intents:
        return False
    marketplace_terms = (
        "京东",
        "淘宝",
        "天猫",
        "拼多多",
        "shopify",
        "instagram",
        "显卡",
        "rtx",
        "tech accessories",
        "ai hardware",
        "智能硬件",
        "数码配件",
    )
    price_terms = ("价格", "报价", "行情", "多少钱", "price")
    official_terms = ("官网", "官方", "release notes", "official blog", "docs", "documentation")
    return _contains_any(text, marketplace_terms) and _contains_any(text, price_terms) and not _contains_any(text, official_terms)


def _should_demote_marketplace_finance(text: str, rules: list[dict[str, Any]]) -> bool:
    """Product-market 行情 should not trigger stock/quote workflows."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "ecommerce" not in intents or not {"finance", "finance_quote"} & intents:
        return False
    product_terms = (
        "京东",
        "淘宝",
        "天猫",
        "拼多多",
        "显卡",
        "rtx",
        "rx 9070",
        "充电宝",
        "数码配件",
        "智能硬件",
        "tech accessories",
        "ai hardware",
    )
    capital_market_terms = (
        "股票",
        "股价",
        "大盘",
        "指数",
        "etf",
        "基金净值",
        "期货",
        "富时",
        "a50",
        "标普",
        "纳指",
        "道指",
        "nasdaq",
        "dow",
        "stock price",
    )
    return _contains_any(text, product_terms) and not _contains_any(text, capital_market_terms)


def _should_demote_procurement_finance(text: str, rules: list[dict[str, Any]]) -> bool:
    """招标/采购公告 is procurement evidence, not capital-market finance by default."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"finance", "finance_disclosure"} & intents:
        return False
    procurement_terms = ("招标", "采购", "中标", "外包", "建库", "供应商", "采购项目")
    capital_market_terms = (
        "财报",
        "年报",
        "季报",
        "半年报",
        "减持",
        "质押",
        "停牌",
        "复牌",
        "监管函",
        "问询函",
        "交易所",
        "上市公司",
        "股票",
        "股价",
        "投资者",
        "cninfo",
        "sse",
        "szse",
    )
    return _contains_any(text, procurement_terms) and not _contains_any(text, capital_market_terms)


def _should_demote_country_industry_stock_finance(text: str, rules: list[dict[str, Any]]) -> bool:
    """Country/industry M&A scans should not become structured stock tasks."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"finance", "finance_disclosure", "finance_quote"} & intents:
        return False
    country_terms = ("英国", "uk companies", "british companies", "british", "英企")
    industry_terms = (
        "英国企业",
        "企业并购",
        "并购",
        "m&a",
        "merger",
        "acquisition",
        "industry policy",
        "行业政策",
    )
    capital_market_terms = (
        "股票代码",
        "股价",
        "今日净值",
        "基金净值",
        "etf联接",
        "a50",
        "期货",
        "上证",
        "深证",
        "纳指",
        "道指",
        "ftse 100",
    )
    return (
        (_contains_any(text, country_terms) or "企业并购" in text or "行业政策" in text)
        and _contains_any(text, industry_terms)
        and not _contains_any(text, capital_market_terms)
    )


def _should_demote_finance_wps_office(text: str, rules: list[dict[str, Any]]) -> bool:
    """Stock-market 金山办公/WPS queries need finance evidence before product routing."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
    if "wps_office" not in intents or not finance_intents & intents:
        return False
    stock_context = (
        "股价",
        "股票",
        "下跌",
        "跌幅",
        "利空",
        "研报",
        "目标价",
        "营收",
        "利润",
        "业绩",
        "688111",
        "金山办公",
    )
    return bool(re.search(r"\b\d{6}\b", text)) or _contains_any(text, stock_context)


def _should_demote_food_price_company_primary(text: str, rules: list[dict[str, Any]]) -> bool:
    """Ingredient cost lookups are retail/food-market evidence, not vendor docs."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "company_primary" not in intents:
        return False
    food_terms = (
        "食材",
        "食材成本",
        "配菜",
        "蔬菜拼盘",
        "烤鱼",
        "海带苗",
        "鸡枞菌",
        "姜饼瓜",
        "辣锅",
        "清汤",
    )
    price_terms = ("价格", "报价", "成本", "多少钱", "行情")
    official_terms = ("官网", "官方", "投资者关系", "年报", "公告")
    return _contains_any(text, food_terms) and _contains_any(text, price_terms) and not _contains_any(text, official_terms)


def _should_demote_business_segment_finance_quote(text: str, rules: list[dict[str, Any]]) -> bool:
    """Company business-segment queries use industry/company evidence; 板块 alone is not a quote request."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "finance_quote" not in intents or not {"industry", "company_primary"} & intents:
        return False
    business_terms = (
        "业务板块",
        "主营业务",
        "业务",
        "商业模式",
        "公司",
        "集团",
        "纺织服装",
        "户外动力设备",
        "船舶制造",
        "医疗设备进口",
        "大宗商品",
        "机电",
    )
    live_quote_terms = (
        "股价",
        "行情",
        "涨跌",
        "涨跌幅",
        "盘口",
        "大盘",
        "指数",
        "富时",
        "a50",
        "期货",
        "收盘",
        "etf",
        "基金净值",
        "实时",
        "quote",
        "stock price",
        "market cap",
        "futures",
        "nasdaq",
        "dow",
    )
    return _contains_any(text, business_terms) and not _contains_any(text, live_quote_terms)


def _should_demote_personal_career_industry(text: str, rules: list[dict[str, Any]]) -> bool:
    """Personal career canvases are career/self-positioning tasks, not industry analysis."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"career", "industry"} <= intents:
        return False
    personal_terms = (
        "个人商业模式画布",
        "职业定位",
        "核心竞争力",
        "个人说明书",
        "working with me",
        "自我介绍",
    )
    company_terms = ("公司", "企业", "行业", "产业", "市场规模", "融资", "财报", "公告")
    return _contains_any(text, personal_terms) and not _contains_any(text, company_terms)


def _should_demote_market_report_career(text: str, rules: list[dict[str, Any]]) -> bool:
    """Recruiting-market reports are industry research, not job-search routing."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"career", "industry"} <= intents:
        return False
    market_terms = ("市场规模", "预测", "艾瑞", "questmobile", "行业报告", "市场报告", "职业服务")
    job_terms = ("岗位职责", "薪资", "面经", "简历", "offer", "校招", "社招", "面试")
    return _contains_any(text, market_terms) and not _contains_any(text, job_terms)


def _should_demote_marketplace_rules_tech(text: str, rules: list[dict[str, Any]]) -> bool:
    """Marketplace rule/API access questions should start from ecommerce/platform policy evidence."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"ecommerce", "tech"} <= intents:
        return False
    marketplace_terms = ("闲鱼", "淘宝", "天猫", "直通车", "招聘平台")
    rule_terms = ("规则", "技术服务", "开放数据", "开放 api", "数据获取", "爬虫", "合规")
    developer_terms = ("github", "源码", "代码", "bug", "部署", "benchmark", "开源项目")
    return _contains_any(text, marketplace_terms) and _contains_any(text, rule_terms) and not _contains_any(text, developer_terms)


def _should_demote_auto_sales_entertainment(text: str, rules: list[dict[str, Any]]) -> bool:
    """Auto sales/share queries should not be captured by generic entertainment 销量."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"industry", "entertainment"} <= intents:
        return False
    auto_terms = ("问界", "赛力斯", "比亚迪", "新能源车", "新能源汽车", "电动车", "汽车", "智驾")
    sales_terms = ("销量", "市场份额", "出海", "海外销量", "增长")
    media_terms = ("游戏", "steam", "电影", "剧集", "动漫", "番剧", "漫画", "票房", "播放量")
    return _contains_any(text, auto_terms) and _contains_any(text, sales_terms) and not _contains_any(text, media_terms)


def _should_demote_broad_finance_sentiment(text: str, rules: list[dict[str, Any]]) -> bool:
    """Keep generic 舆情 queries out of the stock workflow unless finance is explicit."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "finance_sentiment" not in intents:
        return False
    finance_terms = (
        "股票",
        "股价",
        "a股",
        "基金",
        "etf",
        "行情",
        "大盘",
        "财报",
        "公告",
        "雪球",
        "股吧",
        "研报",
        "投资者",
        "看多",
        "看空",
        "爆仓",
        "stock",
    )
    if _contains_any(text, finance_terms):
        return False
    return bool({"public_opinion", "crisis_watch", "review_intel", "app_review", "reputation", "company_primary", "tech", "industry"} & intents)


def _should_demote_game_patch_cybersecurity(text: str, rules: list[dict[str, Any]]) -> bool:
    """Game update patches are entertainment/company evidence, not CVE security patches."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "cybersecurity" not in intents:
        return False
    return _is_game_patch_without_security(text)


def _is_game_patch_without_security(text: str) -> bool:
    game_terms = (
        "游戏",
        "手柄重映射",
        "红色沙漠",
        "crimson desert",
        "pearl abyss",
        "玩家",
        "dlc",
        "mod",
        "steam",
    )
    patch_terms = ("补丁", "patch", "更新补丁")
    security_terms = ("cve", "漏洞", "安全公告", "安全更新", "影响版本", "exploit", "vulnerability", "nvd", "cisa")
    return _contains_any(text, game_terms) and _contains_any(text, patch_terms) and not _contains_any(text, security_terms)


def _should_demote_broad_entertainment(text: str, rules: list[dict[str, Any]]) -> bool:
    """Avoid letting generic 评分/评论 terms steal App review routing."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "entertainment" not in intents or "app_review" not in intents:
        return False
    entertainment_terms = (
        "电影",
        "电视剧",
        "剧集",
        "综艺",
        "明星",
        "演员",
        "票房",
        "排片",
        "播放量",
        "音乐",
        "专辑",
        "演唱会",
        "游戏",
        "手游",
        "动漫",
        "漫画",
        "番剧",
        "二次元",
        "豆瓣",
        "猫眼",
        "taptap",
        "k-pop",
        "hollywood",
    )
    return not _contains_any(text, entertainment_terms)


def _should_demote_reading_notes_entertainment(text: str, rules: list[dict[str, Any]]) -> bool:
    """Keep book notes/reviews out of movie/game entertainment routing."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"reading_notes", "entertainment"} <= intents:
        return False
    reading_terms = ("书摘", "读书笔记", "阅读笔记", "书评", "豆瓣读书", "图书馆", "少儿阅读")
    visual_entertainment_terms = (
        "电影",
        "电视剧",
        "综艺",
        "明星",
        "票房",
        "游戏",
        "手游",
        "steam",
        "动漫",
        "漫画",
        "番剧",
        "演唱会",
    )
    return _contains_any(text, reading_terms) and not _contains_any(text, visual_entertainment_terms)


def _should_demote_game_reaction_tech(text: str, rules: list[dict[str, Any]]) -> bool:
    """Keep game release/reaction queries in entertainment unless they ask for engineering details."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"entertainment", "tech"} <= intents:
        return False
    game_context = ("巫师", "witcher", "cdpr", "steam", "玩家反响", "玩家争议", "mod", "模组", "发售")
    engineering_terms = ("sdk", "api", "github", "源码", "代码", "开发教程", "部署", "bug", "benchmark")
    return _contains_any(text, game_context) and not _contains_any(text, engineering_terms)


def _should_demote_education_service_tech(text: str, rules: list[dict[str, Any]]) -> bool:
    """Summer-camp reputation should not be swallowed by generic AI/robotics tech terms."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "tech" not in intents or not {"education_service", "reputation"} & intents:
        return False
    service_terms = ("夏令营", "研学", "营地", "暑期", "家长评价", "小学生", "青少年", "投诉")
    engineering_terms = ("github", "sdk", "api", "源码", "代码", "部署", "benchmark", "论文", "开源")
    return _contains_any(text, service_terms) and not _contains_any(text, engineering_terms)


def _should_demote_policy_topic_tech(text: str, rules: list[dict[str, Any]]) -> bool:
    """Treat AI policy/regulation queries as policy, not a parallel tech workflow."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "tech" not in intents or not {"policy", "global_policy", "standards_compliance"} & intents:
        return False
    policy_terms = (
        "政策",
        "监管",
        "法规",
        "通知",
        "办法",
        "意见",
        "合规",
        "专项整治",
        "原文",
        "反补贴",
        "反倾销",
        "关税",
        "军事演习",
        "军事部署",
        "西南诸岛",
        "地缘政治",
        "regulation",
        "policy",
    )
    engineering_terms = ("github", "sdk", "api", "源码", "代码", "部署", "benchmark", "开源", "框架", "教程")
    return _contains_any(text, policy_terms) and not _contains_any(text, engineering_terms)


def _should_demote_global_accessibility_domestic_policy(text: str, rules: list[dict[str, Any]]) -> bool:
    """European accessibility law should start from EU/standards sources, not China gov scope."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"policy", "global_policy"} <= intents:
        return False
    global_terms = (
        "欧洲无障碍法案",
        "eaa",
        "european accessibility act",
        "欧盟",
        "欧洲",
        "eu accessibility",
        "eur-lex",
    )
    domestic_terms = (
        "中国",
        "国务院",
        "工信部",
        "教育部",
        "国家标准",
        "国家",
        "miit",
        "samr",
        "gov.cn",
    )
    return _contains_any(text, global_terms) and not _contains_any(text, domestic_terms)


def _should_demote_pricing_standards_compliance(text: str, rules: list[dict[str, Any]]) -> bool:
    """收费标准/价格表 is pricing evidence unless it names a real standard or regulator."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "standards_compliance" not in intents or not {"pricing_watch", "company_primary"} & intents:
        return False
    pricing_terms = ("收费标准", "收费", "价格", "套餐", "订阅", "price", "pricing", "annual price")
    product_terms = ("可灵", "即梦", "海螺", "通义万相", "ai视频生成", "视频生成", "subscription", "premium")
    hard_standard_terms = (
        "国家标准",
        "行业标准",
        "iso",
        "iec",
        "nist",
        "wcag",
        "yd/t",
        "合规",
        "认证",
        "审计",
        "监管",
        "具体条款",
    )
    return _contains_any(text, pricing_terms) and _contains_any(text, product_terms) and not _contains_any(text, hard_standard_terms)


def _should_demote_standard_purchase_advice(text: str, rules: list[dict[str, Any]]) -> bool:
    """Do not let 对比度 inside standards text trigger shopping-style purchase advice."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "purchase_advice" not in intents or not {"policy", "global_policy", "standards_compliance"} & intents:
        return False
    standard_terms = (
        "对比度",
        "字号",
        "字体大小",
        "无障碍",
        "适老化",
        "大字模式",
        "wcag",
        "yd/t",
        "标准",
        "具体条款",
    )
    shopping_terms = (
        "值不值得买",
        "能买吗",
        "要不要买",
        "购买",
        "选购",
        "推荐哪",
        "哪个牌子",
        "优缺点",
    )
    return _contains_any(text, standard_terms) and not _contains_any(text, shopping_terms)


def _should_demote_academic_generic_standards(text: str, rules: list[dict[str, Any]]) -> bool:
    """Academic CFP/indexing 'standards and requirements' should stay in academic routing."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if not {"academic", "standards_compliance"} <= intents:
        return False
    academic_terms = (
        "ei",
        "sci",
        "scopus",
        "会议",
        "学术会议",
        "投稿",
        "检索",
        "收录",
        "论文",
        "期刊",
        "cfp",
        "proceedings",
    )
    hard_standard_terms = (
        "iso",
        "iec",
        "nist",
        "wcag",
        "yd/t",
        "无障碍",
        "适老化",
        "等保",
        "gdpr",
        "合规",
        "认证",
        "审计",
        "监管",
    )
    return _contains_any(text, academic_terms) and not _contains_any(text, hard_standard_terms)


def _should_demote_fictional_university(text: str, rules: list[dict[str, Any]]) -> bool:
    """Keep fiction/comic character queries with 导师/学院 out of admissions routing."""
    intents = {str(rule.get("intent") or "") for rule in rules}
    if "university_admissions" not in intents:
        return False
    fiction_terms = (
        "漫画",
        "动漫",
        "番剧",
        "轻小说",
        "小说",
        "剧情",
        "角色",
        "人物",
        "同人",
        "二次元",
        "魔法学院",
        "游戏角色",
        "npc",
    )
    if not _contains_any(text, fiction_terms):
        return False
    admissions_anchors = (
        "研究生招生",
        "博士招生",
        "硕士招生",
        "招生目录",
        "招生简章",
        "研究生院",
        "院系",
        "推免",
        "复试",
        "考研",
        "计算机系",
        "高校",
        "大学",
        "edu.cn",
        "官网",
    )
    return not _contains_any(text, admissions_anchors)


def _prioritize_sample_intelligence_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {
        "app_review": 0,
        "crisis_watch": 0,
        "competitor_watch": 0,
        "pricing_watch": 0,
        "review_intel": 1,
        "public_opinion": 8,
    }
    ordered = sorted(enumerate(rules), key=lambda item: (priority.get(str(item[1].get("intent") or ""), 10), item[0]))
    return [rule for _, rule in ordered]


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
