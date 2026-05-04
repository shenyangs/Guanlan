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
)
from guanlan.source_seeds import direct_source_read_commands

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
        "terms": ("政策", "监管", "法规", "通知", "办法", "意见", "征求意见", "部委", "国务院", "工信部", "专精特新", "备案", "合规"),
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
            "反诈",
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
            "合同",
            "律师",
            "侵权",
            "司法解释",
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
            "合同",
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
        ),
        "scopes": ("jp_kr_entertainment", "global_entertainment", "community_sample"),
        "fallback": ("global_news", "company_primary"),
        "sites": ("soompi.com", "oricon.co.jp", "natalie.mu", "entertain.naver.com", "koreaherald.com", "koreatimes.co.kr"),
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
        "sites": ("douban.com", "maoyan.com", "bilibili.com", "weibo.com", "taptap.cn", "bangumi.tv", "pixiv.net", "mangapedia.com", "manba.co.jp"),
        "roles": ("platform_metric", "user_review", "industry_report", "fan_discussion", "official_release"),
        "warning": "文娱问题应区分平台热度、用户评分、产业报道、宣发通稿和粉圈讨论；漫画/番剧/轻小说题材优先看条目站、创作者社区和公开口碑，单平台热搜不能代表总体口碑。",
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
            "航运",
            "运价",
            "红海",
            "关税",
            "海外销量",
            "大豆",
            "进口价格",
            "压榨",
            "market size",
            "report",
            "中标",
            "招标",
            *_ROBOTICS_AI_TERMS,
        ),
        "scopes": ("business", "finance", "ecommerce"),
        "fallback": ("party_central", "social_web", "tech_dev"),
        "roles": ("industry_report", "company_context", "market_news"),
    },
    {
        "intent": "company_primary",
        "terms": (
            "付费",
            "订阅",
            "定价",
            "价格",
            "套餐",
            "会员",
            "商业化",
            "发布",
            "上线",
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
        "terms": (
            "market map",
            "industry analysis",
            "market share",
            "competitive landscape",
            "startup",
            "funding",
            "analyst report",
            "market size",
            "report",
            "red sea",
            "shipping",
            "tariff",
            "global supply chain",
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
        "terms": ("播客", "小宇宙", "音频", "节目", "单集", "主播", "podcast", "rss audio"),
        "scopes": ("podcast", "social_web", "tech_dev"),
        "fallback": ("business", "community_sample"),
        "sites": ("xiaoyuzhoufm.com", "podcasts.apple.com", "spotify.com", "listennotes.com"),
        "roles": ("episode_catalog", "show_metadata", "listener_sample", "rss_feed"),
        "warning": "播客发现应区分节目/单集元数据、听众评价和转写内容；榜单只能作发现线索。",
    },
    {
        "intent": "tech",
        "terms": ("技术", "开源", "框架", "github", "sdk", "api", "部署", "bug", "benchmark", "选型", "开发者", "mcp", "教程", "rag", "reranker", "ollama", "本地模型", "联网搜索", "自动加字幕", "剪映", *_ROBOTICS_AI_TERMS),
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
            "板块",
            "etf",
            "基金净值",
            "实时",
            "quote",
            "stock price",
            "market cap",
        ),
        "scopes": ("finance_quote", "finance_news"),
        "fallback": ("finance_disclosure", "finance_sentiment"),
        "sites": ("quote.eastmoney.com", "finance.sina.com.cn", "xueqiu.com", "finance.yahoo.com", "nasdaq.com"),
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
        ),
        "scopes": ("finance_macro", "finance_news", "global_official"),
        "fallback": ("finance_research", "business"),
        "sites": ("stats.gov.cn", "pbc.gov.cn", "safe.gov.cn", "fred.stlouisfed.org", "cmegroup.com", "imf.org"),
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
        "terms": ("今天", "今日", "最新", "最近", "近期", "热点", "热搜", "热议", "刷屏", "突发", "舆情", "快讯"),
        "scopes": ("social_web", "business", "finance"),
        "fallback": ("party_central", "tech_dev"),
        "roles": ("fresh_news", "public_discussion"),
    },
)

_DOMAIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auto", ("汽车", "车", "新能源车", "智驾", "小米yu7", "蔚来", "理想", "小鹏", "特斯拉", "比亚迪")),
    ("ai", ("ai", "人工智能", "大模型", "agent", "智能体", "llm", "算力", *_ROBOTICS_AI_TERMS)),
    ("consumer", ("手机", "电脑", "家电", "相机", "耳机", "消费", "购买", "值不值得买")),
    ("career", ("招聘", "求职", "岗位", "薪资", "面试", "简历", "校招", "面经", "salary", "interview")),
    ("education", ("高校", "大学", "研究生", "招生", "导师", "院系", "推免", "考研", "雅思", "托福", "机经")),
    ("health", ("医疗", "疾病", "药", "治疗", "医生", "症状", "医院", "孕期", "肺结节", "布洛芬")),
    ("legal", ("法律", "诉讼", "判决", "合同", "律师", "侵权", "工伤", "竞业", "版权")),
    ("finance", ("财经", "股票", "股价", "行情", "财报", "公告", "基金", "债券", "宏观", "降息", "雪球", "股吧", "研报", "nvidia", "etf")),
    ("cybersecurity", ("cve", "漏洞", "补丁", "诈骗", "反诈", "钓鱼", "openssl")),
    ("sports", ("体育", "比赛", "伤病", "转会", "梅西", "mbappe", "messi", "nba")),
    ("weather", ("天气", "气象", "台风", "预警", "地震", "noaa", "jma")),
    ("science", ("科学", "nasa", "詹姆斯韦伯", "外星生命", "jwst")),
    ("podcast", ("播客", "小宇宙", "podcast")),
    ("policy", ("regulation", "policy", "compliance", "law", "standard")),
    ("company", ("pricing", "release notes", "docs", "official blog", "investor relations")),
    ("reviews", ("review", "reviews", "reddit", "g2", "trustpilot", "capterra")),
    ("entertainment", ("文娱", "娱乐", "影视", "电影", "剧集", "综艺", "明星", "票房", "豆瓣", "猫眼", "游戏", "动漫", "漫画", "番剧", "轻小说", "二次元", "bangumi", "pixiv")),
    ("western_entertainment", ("欧美娱乐", "西方娱乐", "好莱坞", "hollywood", "billboard", "grammy", "taylor swift", "hbo", "deadline", "variety", "奥斯卡")),
    ("jp_kr_entertainment", ("日韩娱乐", "韩娱", "日娱", "韩媒", "日媒", "韩网", "k-pop", "kpop", "j-pop", "jpop", "oricon", "soompi")),
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
    if site:
        target_sites.insert(0, site)
    if sites:
        target_sites = _unique(list(sites) + target_sites)
    if not (site or sites) and "university_admissions" in primary + secondary:
        target_sites = _unique(_university_target_sites(clean_query) + target_sites)
    if not (site or sites or scope or preset):
        target_sites = _unique(target_sites + _source_pack_target_sites(primary + secondary))
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
            "entertainment",
            "global_entertainment",
            "jp_kr_entertainment",
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
    read_default = 5 if {"policy", "official_position", "tech", "industry", "global_entertainment", "jp_kr_entertainment", "cybersecurity", "weather_disaster", "science", "sports", "career", "podcast", "test_prep", *finance_intents} & set(primary + secondary) else 3
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
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
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
) -> list[str]:
    """Build a small command shortlist for agents after routing."""
    commands: list[str] = []
    quoted = _shell_quote(query)
    profile_part = f" --profile {profile}" if profile in {"china", "english", "hybrid"} else ""
    effective_read_top = 5 if read_top is None else max(read_top, 0)
    reading_discovery = _is_reading_discovery(query.lower())
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}

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

    if (
        "hot_trend" in intents
        and not reading_discovery
        and profile != "english"
        and not {"global_entertainment", "jp_kr_entertainment", "cybersecurity", "weather_disaster", "science", "sports", "podcast", *finance_intents} & set(intents)
    ):
        commands.append(f"guanlan hotnews today --limit {hotnews_limit}")

    if "university_admissions" in intents:
        commands.append(f"guanlan research {quoted} --preset university{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope university --limit {search_limit}")
    elif "academic" in intents:
        academic_read_top = max(effective_read_top, 5)
        commands.append(f"guanlan research {quoted} --preset academic{profile_part} --limit {research_limit} --read-top {academic_read_top}")
    elif "standards_compliance" in intents and not (profile == "english" and "global_policy" in intents):
        commands.append(f"guanlan research {quoted}{profile_part} --scope global_official --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope gov --limit {search_limit}")
    elif "medical_health" in intents:
        commands.append(f"guanlan research {quoted}{profile_part} --scope global_official --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        commands.append(f"guanlan search {quoted}{profile_part} --scope academic --limit {search_limit}")
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
    elif "entertainment" in intents:
        if profile != "english":
            commands.append(f"guanlan hotnews weibo --limit {hotnews_limit}")
            commands.append(f"guanlan hotnews bilibili --limit {hotnews_limit}")
        commands.append(f"guanlan research {quoted} --preset entertainment{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 3)}")
        commands.append(f"guanlan pulse {quoted}{profile_part} --limit {pulse_limit} --format context")
    elif "reputation" in intents or "purchase_advice" in intents:
        commands.append(f"guanlan pulse {quoted}{profile_part} --limit {pulse_limit} --format context")
        commands.append(f"guanlan research {quoted} --preset reputation{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 3)}")
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
        commands.extend(stock_commands[:2])
        commands.extend(direct_reads[: 1 if stock_commands else 3])
        commands.append(f"guanlan research {quoted} --preset finance{profile_part} --limit {research_limit} --read-top {max(effective_read_top, 5)}")
        if "finance_quote" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_quote --limit {search_limit} --trace")
        if "finance_disclosure" in intents or "finance" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_disclosure --limit {search_limit} --trace")
        if "finance_macro" in intents:
            commands.append(f"guanlan search {quoted}{profile_part} --scope finance_macro --limit {search_limit} --trace")
        if "finance_sentiment" in intents:
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
        commands.extend(_hotboard_route_commands(query, intents=intents, domains=domains))

    return _unique(commands)[:10]


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
            "industry",
            "ecommerce",
            "finance",
            "finance_quote",
            "finance_disclosure",
            "finance_macro",
            "finance_sentiment",
            "finance_research",
        }
        & set(intents)
    )


def _structured_stock_commands(query: str, intents: list[str]) -> list[str]:
    """Suggest structured stock data before dynamic finance web pages."""
    finance_quote_like = bool({"finance", "finance_quote", "finance_sentiment"} & set(intents))
    if not finance_quote_like:
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
    commands = [f"guanlan stock quote {quoted_target}"]
    if "finance_quote" in intents or "finance" in intents:
        commands.append(f"guanlan stock detail {quoted_target}")
    if "finance_sentiment" in intents or re.search(r"资金流向|主力|净流入|fund\s*flow", query, flags=re.I):
        commands.append(f"guanlan stock fundflow {quoted_target}")
    return commands


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


def _english_scope_equivalents(scopes: list[str]) -> list[str]:
    mapping = {
        "gov": ["global_official"],
        "party_central": ["global_official", "global_news"],
        "local_official": ["global_official", "global_news"],
        "business": ["industry_analysis", "global_news"],
        "ecommerce": ["industry_analysis", "market_review"],
        "tech_dev": ["developer", "community_sample"],
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
