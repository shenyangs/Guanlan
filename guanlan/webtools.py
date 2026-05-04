# -*- coding: utf-8 -*-
"""Search and read primitives for AI agents.

These helpers are deliberately conservative: default search uses public HTML
results and page reading uses Jina Reader. No cookies, browser access, or
Keychain access are involved.
"""

from __future__ import annotations

import base64
import concurrent.futures
import datetime as dt
import difflib
import hashlib
import html
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from guanlan.limits import (
    DEFAULT_FEEDS_LIMIT,
    DEFAULT_READ_FALLBACK_LIMIT,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_SEARCH_LIMIT,
)
from guanlan.router import build_route_plan, format_route_plan_markdown
from guanlan.search_quality import (
    LOW_RELEVANCE_RESULT_STATUS as _LOW_RELEVANCE_RESULT_STATUS,
)
from guanlan.search_quality import (
    UNSAFE_RESULT_STATUS as _UNSAFE_RESULT_STATUS,
)
from guanlan.search_quality import (
    assess_backend_batch_quality as _assess_backend_batch_quality,
)
from guanlan.search_quality import (
    filter_unsafe_search_results as _filter_unsafe_search_results,
)
from guanlan.search_quality import (
    query_relevance_terms as _query_relevance_terms,
)
from guanlan.search_quality import (
    result_text_contains as _result_text_contains,
)
from guanlan.source_seeds import (
    direct_source_seeds,
    dominant_vertical_preset,
    is_finance_lookup,
    is_live_sports_lookup,
)
from guanlan.source_taxonomy import source_card_for_domain

_UA = "Mozilla/5.0 (compatible; Guanlan/1.4)"
_TIMEOUT = 20
_SEARCH_TIMEOUT = 8
_CACHE_VERSION = 2
_NETWORK_HEALTH_TTL_SECONDS = 300
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
    "访问过于频繁",
    "请验证以继续访问",
    "系统检测到您的ip",
    "upgrade_browser",
    "window.location.href",
    "galileotelemetry",
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

_NETWORK_HEALTH_CACHE: dict[str, dict[str, Any]] = {}
_BING_CJK_DRIFT_COOLDOWN_SECONDS = 300
_BING_CJK_DRIFT_UNTIL = 0.0
_VALID_NETWORK_MODES = {"auto", "current", "direct", "proxy"}
_NETWORK_PROBLEM_STATUSES = {"network_unreachable", "proxy_error", "network_changed"}
_QUERY_TOKEN_STOPWORDS = {
    "企业",
    "公司",
    "情况",
    "相关",
    "最新",
    "近期",
    "动态",
    "行业",
    "产业",
    "技术",
    "市场",
    "趋势",
    "融资",
}
_QUERY_REWRITE_STOPWORDS = {
    "怎么",
    "如何",
    "以及",
    "还有",
    "一下",
    "这个",
    "那个",
    "相关",
    "情况",
    "问题",
    "最新",
    "最近",
    "今天",
    "刚刚",
    "请问",
}
_MEANINGLESS_QUERY_ALLOWLIST = {
    "gpt",
    "gpt4",
    "gpt-4",
    "gpt5",
    "gpt-5",
    "openai",
    "claude",
    "gemini",
    "qwen",
    "glm",
    "cve",
    "react",
    "vue",
    "nextjs",
    "next.js",
    "python",
    "java",
    "golang",
    "typescript",
    "javascript",
    "cpp",
    "c++",
    "ios",
    "android",
}
_QUERY_KEYBOARD_RUNS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_LONG_QUERY_KEYPHRASE_HINTS = (
    "具身智能",
    "人形机器人",
    "机器人",
    "人工智能",
    "融资",
    "产品",
    "商业化",
    "政策",
    "供应链",
    "订单",
    "客户",
    "趋势",
    "GDP",
    "人口",
    "股价",
    "天气",
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
            "uscis",
            "h1b",
            "h-1b",
            "visa",
            "申根",
            "签证",
            "移民",
            "美联储",
            "fedwatch",
            "cme fedwatch",
            "降息",
            "出口管制",
            "cbam",
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
    "cybersecurity": {
        "name": "网络安全/CVE/反诈",
        "terms": (
            "cve",
            "漏洞",
            "补丁",
            "安全公告",
            "修复版本",
            "影响版本",
            "openssl",
            "钓鱼",
            "诈骗",
            "短信链接",
            "反诈",
            "phishing",
            "vulnerability",
            "exploit",
            "security advisory",
            "nvd",
            "cisa",
            "cnvd",
            "cnnvd",
        ),
        "preferred_scopes": ("cybersecurity", "developer", "global_official"),
        "preferred_source_types": ("网络安全/漏洞/反诈", "英文开发者/开源", "英文官方/监管"),
        "caution_source_types": ("社交/内容平台", "英文社区样本", "商业/产业媒体"),
        "guidance": "优先 CVE/NVD/CISA/厂商公告、补丁说明和公安/监管反诈来源；论坛复现只能作补充。",
    },
    "medical_health": {
        "name": "医疗/健康高影响信息",
        "terms": ("医疗", "疾病", "药", "药品", "治疗", "诊断", "症状", "临床", "指南", "医生", "医院", "孕期", "怀孕", "布洛芬", "肺结节", "肌酸", "视黄醇", "敏感肌", "猫咪", "呕吐", "fda", "cdc", "who", "medical", "clinical", "treatment"),
        "preferred_scopes": ("global_official", "gov", "academic"),
        "preferred_source_types": ("英文官方/监管", "政府/部委", "学术/论文检索"),
        "caution_source_types": ("社交/内容平台", "英文社区样本", "商业/产业媒体"),
        "guidance": "优先公共卫生机构、药监/监管、临床指南和同行评议材料；不要输出诊疗结论。",
    },
    "legal_judicial": {
        "name": "法律/司法高影响信息",
        "terms": ("法律", "诉讼", "判决", "合同", "律师", "侵权", "司法解释", "法院", "裁判文书", "条例", "工伤", "竞业", "劳动争议", "版权", "著作权", "维权", "投诉", "license", "agpl", "law", "legal", "court", "lawsuit"),
        "preferred_scopes": ("gov", "global_official", "local_official", "academic"),
        "preferred_source_types": ("政府/部委", "英文官方/监管", "地方官媒", "学术/论文检索"),
        "caution_source_types": ("社交/内容平台", "英文社区样本", "商业/产业媒体"),
        "guidance": "优先法律条文、司法解释、裁判文书和权威机构材料；律师文章只能作为观点。",
    },
    "company": {
        "name": "公司/产品一手资料",
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
        "terms": ("电商", "零售", "跨境", "出海", "品牌", "渠道", "供应链", "产业带", "平台", "新消费", "抖音小店", "小店", "团购", "抖音团购", "真实商家", "实体店", "加盟", "本地生活", "餐馆", "茶饮"),
        "preferred_scopes": ("ecommerce", "business"),
        "preferred_source_types": ("电商/零售垂类", "商业/产业媒体"),
        "caution_source_types": (),
        "guidance": "优先垂类媒体和产业媒体，注意区分新闻、观点和软文。",
    },
    "career": {
        "name": "招聘/薪资/面经",
        "terms": ("招聘", "求职", "岗位", "薪资", "面试", "简历", "校招", "社招", "面经", "offer", "hc", "算法工程师", "产品经理", "interview loop", "salary", "levels", "glassdoor"),
        "preferred_scopes": ("career", "social_web", "business"),
        "preferred_source_types": ("招聘/职场/薪资", "社交/内容平台", "商业/产业媒体"),
        "caution_source_types": ("通用网页",),
        "guidance": "优先岗位/公司官方信息、薪资样本、面经和招聘市场报告，并标注样本偏差。",
    },
    "industry": {
        "name": "产业/公司研究",
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
            "压榨",
            "market size",
            "report",
            "中标",
            "招标",
            *_ROBOTICS_AI_TERMS,
        ),
        "preferred_scopes": ("business", "finance", "ecommerce"),
        "preferred_source_types": ("商业/产业媒体", "财经/资本市场", "电商/零售垂类"),
        "caution_source_types": ("社交/内容平台",),
        "guidance": "优先产业媒体、公司一手资料和融资/市场材料；融资是产业维度时，不应只按财经口径收窄。",
    },
    "finance": {
        "name": "财经/资本市场",
        "terms": ("财经", "股票", "股价", "财报", "融资", "上市", "投资", "基金", "债券", "宏观", "资本市场", "英伟达", "nvidia", "大跌", "etf", "质押", "银行倒闭", "fedwatch", "降息"),
        "preferred_scopes": ("finance", "finance_disclosure", "finance_company", "finance_quote", "finance_news", "finance_macro"),
        "preferred_source_types": ("财经/公告披露", "财经/行情数据", "财经/新闻报道", "财经/宏观数据", "财经/资本市场", "商业/产业媒体"),
        "caution_source_types": ("社交/内容平台", "财经/情绪样本", "财经/研报观点"),
        "guidance": "优先公告披露、交易所/监管、行情入口、宏观官方数据和可信财经新闻；研报/情绪只作观点或样本，不输出投资建议。",
    },
    "tech": {
        "name": "技术/开发者",
        "terms": ("技术", "开源", "框架", "模型", "api", "sdk", "github", "开发者", "部署", "bug", "benchmark", "mcp", "教程", "自动加字幕", "剪映", *_ROBOTICS_AI_TERMS),
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
    "university_admissions": {
        "name": "高校招生/导师/院系官网",
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
            "推免",
            "复试",
            "考研",
            "faculty",
            "advisor",
            "supervisor",
            "graduate admissions",
        ),
        "preferred_scopes": ("university",),
        "preferred_source_types": ("高校/院系官网",),
        "caution_source_types": ("学术/论文检索", "社交/内容平台"),
        "guidance": "优先院系官网、研究生招生网、招生目录和导师主页；学术数据库或论坛只能作为背景线索。",
    },
    "test_prep": {
        "name": "考试/培训/备考",
        "terms": ("雅思", "托福", "ielts", "toefl", "题库", "机经", "口语题库", "考试政策", "培训合规", "备考", "真题"),
        "preferred_scopes": ("test_prep", "social_web", "company_primary"),
        "preferred_source_types": ("考试/培训/备考", "社交/内容平台", "公司一手资料"),
        "caution_source_types": ("通用网页", "商业/产业媒体"),
        "guidance": "优先官方考试政策，再看培训机构资料和考生经验；题库/机经需要标注不确定性。",
    },
    "entertainment": {
        "name": "文娱/内容消费",
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
        "preferred_scopes": ("entertainment", "social_web", "business"),
        "preferred_source_types": ("文娱/内容平台", "社交/内容平台", "商业/产业媒体"),
        "caution_source_types": ("通用网页", "评价/消费样本"),
        "guidance": "文娱问题应分清平台数据、用户评分、专业/产业报道和粉圈讨论；漫画/番剧/轻小说题材优先看条目站、创作者社区和公开口碑，不要把单平台热度当作总体口碑。",
    },
    "global_entertainment": {
        "name": "欧美娱乐/音乐产业",
        "terms": (
            "欧美娱乐",
            "西方娱乐",
            "好莱坞",
            "hollywood",
            "deadline",
            "variety",
            "hbo",
            "netflix",
            "dune",
            "casting",
            "renewal",
            "season",
            "release date",
            "rottentomatoes",
            "烂番茄",
            "前哨奖",
            "celebrity",
            "billboard",
            "grammy",
            "oscar",
            "album",
            "single",
            "tour",
            "concert",
            "taylor swift",
            "beyonce",
            "lady gaga",
            "ariana grande",
            "sabrina carpenter",
            "billie eilish",
        ),
        "preferred_scopes": ("global_entertainment", "company_primary", "community_sample"),
        "preferred_source_types": ("欧美文娱/音乐产业", "公司一手资料", "英文社区样本"),
        "caution_source_types": ("通用网页", "评价/消费样本"),
        "guidance": "欧美娱乐问题优先英文行业媒体、榜单/奖项和艺人/厂牌一手信息；粉丝账号、八卦站和狗仔材料只能作线索。",
    },
    "jp_kr_entertainment": {
        "name": "日韩娱乐/K-pop/J-pop",
        "terms": (
            "日韩娱乐",
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
            "桥本环奈",
            "jennie",
            "k-pop",
            "kpop",
            "k-drama",
            "kdrama",
            "j-pop",
            "jpop",
            "oricon",
            "soompi",
            "naver",
            "hybe",
            "bts",
            "blackpink",
            "newjeans",
            "aespa",
            "twice",
            "stray kids",
        ),
        "preferred_scopes": ("jp_kr_entertainment", "global_entertainment", "community_sample"),
        "preferred_source_types": ("日韩文娱/K-pop/J-pop", "欧美文娱/音乐产业", "英文社区样本"),
        "caution_source_types": ("通用网页", "社交/内容平台"),
        "guidance": "日韩娱乐问题要区分本地媒体/榜单、经纪公司口径、英文翻译站和粉丝讨论，并保留跨语言转述风险。",
    },
    "sports": {
        "name": "体育/赛事/转会",
        "terms": ("体育", "比赛", "赛程", "比分", "伤病", "转会", "合同", "续约", "梅西", "姆巴佩", "mbappe", "messi", "real madrid", "nba", "fifa", "uefa", "lpl", "电竞"),
        "preferred_scopes": ("sports", "global_news", "community_sample"),
        "preferred_source_types": ("体育/赛事/转会", "国际主流媒体", "英文社区样本"),
        "caution_source_types": ("社交/内容平台", "通用网页"),
        "guidance": "区分官方赛程/伤病、媒体报道、转会爆料和球迷讨论；爆料不能直接当事实。",
    },
    "weather_disaster": {
        "name": "天气/灾害/预警",
        "terms": ("天气", "气象", "台风", "路径", "预警", "暴雨", "洪水", "地震", "灾害", "应急", "中央气象台", "日本气象厅", "weather", "typhoon", "hurricane", "earthquake", "noaa", "jma", "usgs"),
        "preferred_scopes": ("weather_disaster", "gov", "global_official"),
        "preferred_source_types": ("天气/灾害/预警", "政府/部委", "英文官方/监管"),
        "caution_source_types": ("社交/内容平台", "通用网页"),
        "guidance": "优先官方气象/应急机构的实时预警与路径信息，避免引用过期预警。",
    },
    "science": {
        "name": "科学机构/科研新闻",
        "terms": ("科学", "发现", "外星生命", "詹姆斯韦伯", "韦伯望远镜", "天文", "nasa", "esa", "jwst", "webb telescope", "alien life", "nature", "science", "arxiv"),
        "preferred_scopes": ("science", "academic", "global_official"),
        "preferred_source_types": ("科学机构/科研新闻", "学术/论文检索", "英文官方/监管"),
        "caution_source_types": ("通用网页", "社交/内容平台"),
        "guidance": "优先机构原文、论文或预印本，媒体报道只作为解释层。",
    },
    "podcast": {
        "name": "播客/音频/RSS",
        "terms": ("播客", "小宇宙", "音频", "节目", "单集", "主播", "podcast", "rss audio"),
        "preferred_scopes": ("podcast", "social_web", "tech_dev"),
        "preferred_source_types": ("播客/音频/RSS", "社交/内容平台", "科技/开发者社区"),
        "caution_source_types": ("通用网页",),
        "guidance": "优先节目/单集元数据、RSS 和听众样本；榜单只能作发现线索。",
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
    "entertainment": {
        "name": "文娱研究",
        "description": "优先文娱/内容平台与公开讨论样本，适合影视、综艺、音乐、游戏、明星、票房和口碑。",
        "profile": "china",
        "scope": "entertainment",
        "scopes": ["entertainment", "social_web", "business"],
        "sites": ["douban.com", "maoyan.com", "bilibili.com", "weibo.com", "taptap.cn", "bangumi.tv", "pixiv.net", "mangapedia.com", "manba.co.jp"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 2,
        "max_read_chars": 2600,
        "guidance": [
            "把平台数据、用户评分/评论、产业报道、宣发通稿和粉圈讨论分开看。",
            "票房、播放、榜单和热搜只能说明平台口径下的热度，不直接等于大众口碑。",
            "漫画/番剧/轻小说题材优先补条目站、创作者社区和公开推荐入口，不要只看影视站点。",
        ],
    },
    "global_entertainment": {
        "name": "欧美娱乐研究",
        "description": "优先欧美娱乐行业媒体、音乐榜单、奖项与艺人/厂牌一手信息，适合 Hollywood、明星、巡演、新歌专辑和争议动态。",
        "profile": "english",
        "scope": "global_entertainment",
        "scopes": ["global_entertainment", "community_sample", "global_news"],
        "sites": ["billboard.com", "variety.com", "deadline.com", "hollywoodreporter.com", "rollingstone.com", "people.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": [
            "优先英文行业媒体、榜单/奖项和艺人/厂牌一手信息；粉丝账号、狗仔和八卦站只能作线索。",
            "新歌、巡演、恋情、争议和奖项应分开核验；未被主流英文源确认的动态不要写成事实。",
        ],
    },
    "jp_kr_entertainment": {
        "name": "日韩娱乐研究",
        "description": "优先日韩娱乐、本地榜单、K-pop/J-pop、韩剧日剧、经纪公司动态和翻译站交叉验证。",
        "profile": "hybrid",
        "scope": "jp_kr_entertainment",
        "scopes": ["jp_kr_entertainment", "global_entertainment", "community_sample"],
        "sites": ["soompi.com", "oricon.co.jp", "natalie.mu", "entertain.naver.com", "koreaherald.com", "koreatimes.co.kr"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2800,
        "guidance": [
            "区分经纪公司/榜单/本地媒体、英文翻译站和粉丝讨论；跨语言转述要保留翻译层风险。",
            "Allkpop/Koreaboo 等高声量站适合发现线索，不宜单独作为事实依据。",
        ],
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
    "cybersecurity": {
        "name": "网络安全/CVE/反诈",
        "description": "优先漏洞库、厂商安全公告、监管/反诈来源，适合 CVE、补丁和诈骗风险核验。",
        "profile": "hybrid",
        "scope": "cybersecurity",
        "scopes": ["cybersecurity", "developer", "global_official"],
        "sites": ["nvd.nist.gov", "cisa.gov", "cnvd.org.cn", "openssl.org", "msrc.microsoft.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 5,
        "max_read_chars": 3200,
        "guidance": ["优先 CVE/NVD/CISA/厂商公告和补丁说明；论坛复现只作辅助，不输出攻击步骤。"],
    },
    "sports": {
        "name": "体育赛事与转会",
        "description": "优先体育官方、赛事数据和可信体育媒体，适合比赛、伤病、转会和合同动态。",
        "profile": "hybrid",
        "scope": "sports",
        "scopes": ["sports", "global_news", "community_sample"],
        "sites": ["espn.com", "skysports.com", "theathletic.com", "fifa.com", "uefa.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 5,
        "max_read_chars": 2800,
        "guidance": ["区分官方赛程/伤病、媒体报道、转会爆料和球迷讨论。"],
    },
    "weather_disaster": {
        "name": "天气灾害预警",
        "description": "优先官方气象、应急和灾害机构，适合台风路径、地震和预警。",
        "profile": "hybrid",
        "scope": "weather_disaster",
        "scopes": ["weather_disaster", "gov", "global_official"],
        "sites": ["nmc.cn", "cma.gov.cn", "jma.go.jp", "noaa.gov", "usgs.gov"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 5,
        "max_read_chars": 3200,
        "guidance": ["只把官方实时预警和气象机构路径作为主证据，注意时间和地点。"],
    },
    "science": {
        "name": "科学新闻核验",
        "description": "优先科研机构、论文、预印本和科学媒体，适合科学发现真伪核验。",
        "profile": "english",
        "scope": "science",
        "scopes": ["science", "academic", "global_official"],
        "sites": ["nasa.gov", "esa.int", "nature.com", "science.org", "arxiv.org"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 5,
        "max_read_chars": 3200,
        "guidance": ["优先机构原文、论文或预印本，媒体报道只作解释层；警惕夸大标题。"],
    },
    "career": {
        "name": "招聘薪资面经",
        "description": "优先岗位、薪资样本、面经和招聘市场资料，适合校招/社招/海外求职。",
        "profile": "hybrid",
        "scope": "career",
        "scopes": ["career", "social_web", "business"],
        "sites": ["nowcoder.com", "yingjiesheng.com", "zhipin.com", "levels.fyi", "glassdoor.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 4,
        "max_read_chars": 2800,
        "guidance": ["岗位、薪资和面经样本偏差很大，应和公司官方岗位及报告交叉验证。"],
    },
    "podcast": {
        "name": "播客发现",
        "description": "优先播客目录、节目页、单集页和 RSS，适合播客推荐和节目搜索。",
        "profile": "china",
        "scope": "podcast",
        "scopes": ["podcast", "social_web", "tech_dev"],
        "sites": ["xiaoyuzhoufm.com", "podcasts.apple.com", "spotify.com", "listennotes.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 3,
        "max_read_chars": 2400,
        "guidance": ["区分节目/单集元数据、RSS 和听众评价；榜单只作发现线索。"],
    },
    "test_prep": {
        "name": "考试备考",
        "description": "优先官方考试机构、培训资料和考生经验，适合雅思/托福/题库/机经。",
        "profile": "china",
        "scope": "test_prep",
        "scopes": ["test_prep", "social_web", "company_primary"],
        "sites": ["ielts.org", "ets.org", "neea.edu.cn", "chinaielts.org", "zhihu.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 4,
        "max_read_chars": 2800,
        "guidance": ["官方考试政策优先；题库/机经需要标注不确定性和时效性。"],
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
    "university": {
        "name": "高校招生与导师",
        "description": "优先高校、研究生招生网和院系官网，适合招生目录、导师名单、院系介绍和培养方案。",
        "profile": "china",
        "scope": "university",
        "scopes": ["university", "academic", "tech_dev"],
        "sites": ["edu.cn"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 4,
        "max_read_chars": 3200,
        "guidance": [
            "先找学校/院系/研究生招生官网，再把导师主页、招生目录、专业目录和历史通知分开引用。",
            "学术数据库、考研论坛和培训机构文章只能作为背景线索，不应替代官方页面。",
        ],
    },
    "finance": {
        "name": "财经研究",
        "description": "优先公告披露、行情入口、财经新闻、宏观数据、研报观点和情绪样本分层，适合公司、股票、市场和宏观金融。",
        "profile": "china",
        "scope": "finance",
        "scopes": ["finance_disclosure", "finance_company", "finance_quote", "finance_news", "finance_macro", "finance_research", "finance_sentiment"],
        "sites": ["cninfo.com.cn", "sse.com.cn", "szse.cn", "csrc.gov.cn", "eastmoney.com", "cls.cn", "xueqiu.com"],
        "limit": DEFAULT_RESEARCH_LIMIT,
        "read_top": 5,
        "max_read_chars": 3200,
        "guidance": [
            "先分清行情、公告披露、交易所/监管、宏观官方数据、财经新闻、研报观点和投资者情绪。",
            "行情页可能动态渲染或延迟，必须标注时间/来源；雪球、股吧、微博只作情绪样本。",
            "财经研究只能整理公开证据和风险边界，不能写成买入、卖出或持有建议。",
        ],
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
    published_at: str = ""
    date_source: str = ""
    freshness_confidence: str = ""
    stale_risk: str = ""
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SearchResults(list):
    """List-like search results with diagnostics for empty-result CLI output."""

    def __init__(self, rows=None, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(rows or [])
        self.diagnostics = diagnostics or {}


class NetworkBackendError(RuntimeError):
    """Backend failed across network paths; carries per-path attempts."""

    def __init__(self, status: str, message: str, attempts: list[dict[str, Any]]):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.attempts = attempts


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
_SHORT_SCOPED_QUERY_MAX_SITES = {
    "global_entertainment": 4,
    "jp_kr_entertainment": 4,
    "cybersecurity": 4,
    "sports": 4,
    "weather_disaster": 4,
    "science": 4,
    "career": 4,
    "podcast": 4,
    "test_prep": 4,
}


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
        if query and _contains_cjk(query) and _bing_cjk_drift_active():
            order = ["baidu", "duckduckgo", "bing"]
    else:
        order = ["duckduckgo", "bing"]
    if _is_wechat_search_intent(site=site, query=query):
        order.append("wechat-sogou")
    return order


def _bing_cjk_drift_active(now: float | None = None) -> bool:
    current = now if now is not None else time.time()
    if current < _BING_CJK_DRIFT_UNTIL:
        return True
    if not _backend_health_persistence_enabled():
        return False
    try:
        payload = json.loads(_bing_cjk_drift_path().read_text(encoding="utf-8"))
        return current < float(payload.get("expires_at", 0) or 0)
    except Exception:
        return False


def _record_bing_cjk_drift(now: float | None = None) -> None:
    global _BING_CJK_DRIFT_UNTIL
    if not _backend_health_persistence_enabled():
        return
    current = now if now is not None else time.time()
    expires_at = current + _BING_CJK_DRIFT_COOLDOWN_SECONDS
    _BING_CJK_DRIFT_UNTIL = expires_at
    try:
        path = _bing_cjk_drift_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "backend": "bing",
                    "issue": "cjk_retrieval_drift",
                    "expires_at": expires_at,
                    "ttl_seconds": _BING_CJK_DRIFT_COOLDOWN_SECONDS,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def _bing_cjk_drift_path() -> Path:
    return cache_dir() / "backend_health" / "bing_cjk_drift.json"


def _backend_health_persistence_enabled() -> bool:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return os.environ.get("GUANLAN_TEST_ALLOW_BACKEND_HEALTH") == "1"
    return True


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
    network_mode: str = "auto",
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
    network_mode = _normalize_network_mode(network_mode)
    requested_scope = scope
    effective_scope = _effective_search_scope(original_query, scope)
    profile = resolve_query_profile(original_query, profile)
    network_profile = build_network_profile(network_mode=network_mode, profile=profile)
    recency = detect_recency_intent(original_query)
    quality = detect_search_quality_profile(original_query, scope=effective_scope, site=site, profile=profile)
    route_plan = build_route_plan(
        original_query,
        scope=effective_scope,
        site=site,
        profile=profile,
        limit=limit,
    )
    quality = _quality_with_route_plan(quality, route_plan.to_dict(), explicit_scope=effective_scope, site=site)
    query_shape = _analyze_search_query_shape(
        original_query,
        effective_scope=effective_scope,
        quality=quality,
        route_plan=route_plan.to_dict(),
    )
    query_strategy = build_query_strategy(
        original_query,
        route_plan=route_plan.to_dict(),
        recency=recency,
        quality=quality,
    )
    query_strategy["query_shape"] = query_shape
    limit_advice = _search_limit_advice(limit)
    time_constraint = _search_time_constraint(recency)
    if limit_advice["enabled"]:
        query_strategy["agent_limit_advice"] = limit_advice
    if time_constraint["enabled"]:
        query_strategy["time_constraint"] = time_constraint
    if query_shape.get("rejected"):
        backend_diagnostics = [
            {
                "backend": "query_guard",
                "status": "rejected",
                "result_count": 0,
                "error": "",
                "note": str(query_shape.get("reason") or "query_guard rejected the query"),
            }
        ]
        quality_summary = {
            "status": "warn",
            "quality_status": "needs_more_evidence",
            "intent": quality.get("intent", "general"),
            "preferred_hit_count": 0,
            "result_count": 0,
            "source_type_count": 0,
            "domain_count": 0,
            "source_mix": {},
            "role_counts": {},
            "missing_roles": [],
            "warnings": [str(query_shape.get("reason") or "query 信息量不足")],
            "interpretation": "当前不是观澜搜索能力失败，而是 query 信息量过低或接近乱码；观澜主动拒绝随机返回，以免 Agent 基于噪声证据继续推理。",
            "guanlan_next_steps": [
                "先把 query 扩写成更明确的问题，再继续运行 Guanlan。",
                "补充主题、对象、时间、地区、比较维度或官方/技术/口碑等约束词。",
            ],
            "agent_reporting_contract": [
                "不要把这种情况汇报成“Guanlan 搜索失败”；应表述为“当前 query 信息量不足，观澜主动拒绝随机返回”。",
            ],
            "user_facing_status": "当前 query 信息量过低，观澜主动拒绝随机返回；请先补充主题或约束后再搜。",
            "why_cautious": [str(query_shape.get("reason") or "query 信息量不足")],
            "agent_workflow_plan": {
                "tier": "rewrite-first",
                "minimum_guanlan_tools": 0,
                "planned_tool_count": 0,
                "tool_sequence": [],
                "workflow_kind": "query_rewrite_needed",
                "summary": "先重写 query，再进入 Guanlan 的正常搜索工作流。",
                "must_finish_before_fallback": True,
            },
            "followup_actions": [],
            "recommended_actions": [],
            "agent_execution_policy": {
                "mode": "rewrite_query_first",
                "should_run_followups": False,
                "instruction": "先扩写 query；不要让 Guanlan 或通用 web_search 对低信息量输入随机返回。",
                "fallback_rule": "扩写 query 前不要 fallback。",
                "action_count": 0,
            },
            "suggestions": [
                "把 query 扩写成“对象 + 关注点 + 时间/地区/来源类型”的形式后再搜。",
            ],
        }
        shared_diagnostics = _search_shared_diagnostics(
            original_query=original_query,
            effective_query=original_query,
            requested_scope=requested_scope,
            effective_scope=effective_scope,
            order=[],
            cache_meta={"enabled": False, "status": "disabled", "ttl": 0},
            cache_key="",
            cluster_threshold=cluster_threshold,
            recency=recency,
            route_plan=route_plan.to_dict(),
            query_strategy=query_strategy,
            query_shape=query_shape,
            quality=quality,
            quality_summary=quality_summary,
            backend_diagnostics=backend_diagnostics,
            backend_summary={
                "ok": [],
                "parser_miss": [],
                "zero_results": [],
                "low_relevance": [],
                "blocked": [],
                "errors": [],
                "fallback_used": False,
                "primary_backend": "query_guard",
                "primary_status": "rejected",
            },
            backend_recovery={},
            errors=[],
            network_profile=network_profile,
        )
        return SearchResults([], diagnostics=shared_diagnostics)
    query = str(query_shape.get("backend_query") or original_query)
    scope_domains: list[str] = []
    if effective_scope:
        from guanlan.search_sources import resolve_scope, scoped_query

        resolved_scope = resolve_scope(effective_scope)
        domains = list(resolved_scope.domains)
        if resolved_scope.id == "university":
            domains = _university_search_domains(route_plan.to_dict(), domains)
        if site:
            domains.insert(0, site.strip())
        scope_domains = _unique_keep_order([domain.strip() for domain in domains if domain.strip()])
        query = scoped_query(
            query,
            domains,
            max_sites=_SHORT_SCOPED_QUERY_MAX_SITES.get(resolved_scope.id, 12),
        )
    elif site:
        query = f"site:{site.strip()} {query}"
    query = _apply_recency_query(query, recency)
    fallback_open_query = _apply_recency_query(str(query_shape.get("fallback_open_query") or original_query), recency)

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
                "scope": effective_scope or "",
                "requested_scope": requested_scope or "",
                "backend": backend,
                "profile": profile or "",
                "network_mode": network_mode,
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
        if _usable_candidate_count(results, original_query, quality) >= max(limit, 1):
            attempt.update(
                {
                    "status": "skipped",
                    "result_count": 0,
                    "note": "已有足够可用候选，跳过后续后端以避免外层 Agent/MCP 调用超时。",
                }
            )
            backend_diagnostics.append(attempt)
            continue
        try:
            batch: list[SearchResult]
            network_attempts: list[dict[str, Any]] = []
            if name == "duckduckgo":
                batch, network_attempts = _search_backend_with_network(
                    name,
                    query,
                    limit=limit,
                    network_mode=network_mode,
                    profile=profile,
                )
            elif name == "bing":
                batch, network_attempts = _search_backend_with_network(
                    name,
                    query,
                    limit=limit,
                    network_mode=network_mode,
                    profile=profile,
                )
            elif name == "baidu":
                batch, network_attempts = _search_backend_with_network(
                    name,
                    query,
                    limit=limit,
                    network_mode=network_mode,
                    profile=profile,
                )
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
            if (
                not batch
                and effective_scope
                and effective_scope != "university"
                and not site
                and name in {"duckduckgo", "bing", "baidu"}
            ):
                fallback_batch: list[SearchResult] = []
                fallback_attempts: list[dict[str, Any]] = []
                if name == "duckduckgo":
                    fallback_batch, fallback_attempts = _search_backend_with_network(
                        name,
                        fallback_open_query,
                        limit=limit,
                        network_mode=network_mode,
                        profile=profile,
                    )
                elif name == "bing":
                    fallback_batch, fallback_attempts = _search_backend_with_network(
                        name,
                        fallback_open_query,
                        limit=limit,
                        network_mode=network_mode,
                        profile=profile,
                    )
                elif name == "baidu":
                    fallback_batch, fallback_attempts = _search_backend_with_network(
                        name,
                        fallback_open_query,
                        limit=limit,
                        network_mode=network_mode,
                        profile=profile,
                    )
                if fallback_batch:
                    batch = fallback_batch
                    network_attempts.extend(fallback_attempts)
                    attempt["note"] = (
                        "scoped query returned no results; retried the original query and kept scope-aware ranking."
                    )
            raw_result_count = len(batch)
            safety_filter = _filter_unsafe_search_results(batch)
            if safety_filter["dropped_count"]:
                attempt["safety_filter"] = safety_filter
                batch = safety_filter["kept_results"]
                attempt["raw_result_count"] = raw_result_count
            attempt["result_count"] = len(batch)
            if raw_result_count and not batch and safety_filter["dropped_count"]:
                attempt["status"] = _UNSAFE_RESULT_STATUS
                attempt["note"] = "该后端候选触发成人/不安全内容过滤，已拒绝返回这批结果。"
                continue
            if network_attempts:
                attempt["network_attempts"] = network_attempts
                attempt["network_mode"] = _first_ok_network_mode(network_attempts)
            batch_quality = _assess_backend_batch_quality(original_query, batch, quality)
            attempt["quality_gate"] = batch_quality
            if not batch and name == "bing" and _contains_cjk(original_query):
                recovered_batch, recovered_attempts, recovery_trace = _try_bing_generic_recovery(
                    original_query,
                    limit=limit,
                    network_mode=network_mode,
                    profile=profile,
                    quality=quality,
                )
                if recovered_attempts:
                    network_attempts.extend(recovered_attempts)
                    attempt["network_attempts"] = network_attempts
                    attempt["network_mode"] = _first_ok_network_mode(network_attempts)
                if recovery_trace:
                    attempt["bing_generic_recovery"] = recovery_trace
                if recovered_batch:
                    batch = recovered_batch
                    attempt["result_count"] = len(batch)
                    attempt["quality_gate"] = recovery_trace.get("quality_gate", batch_quality)
                    attempt["status"] = "ok"
                    attempt["note"] = (
                        "Bing CN 入口未产出候选；观澜已补跑 Bing generic 入口，"
                        "并仅保留通过相关性门控的候选。"
                    )
                    results.extend(batch)
                    continue
            if batch and not batch_quality["usable"] and (backend == "auto" or name == "bing"):
                if name == "bing" and _contains_cjk(original_query):
                    recovered_batch, recovered_attempts, recovery_trace = _try_bing_generic_recovery(
                        original_query,
                        limit=limit,
                        network_mode=network_mode,
                        profile=profile,
                        quality=quality,
                    )
                    if recovered_attempts:
                        network_attempts.extend(recovered_attempts)
                        attempt["network_attempts"] = network_attempts
                        attempt["network_mode"] = _first_ok_network_mode(network_attempts)
                    if recovery_trace:
                        attempt["bing_generic_recovery"] = recovery_trace
                    if recovered_batch:
                        batch = recovered_batch
                        attempt["result_count"] = len(batch)
                        attempt["quality_gate"] = recovery_trace.get("quality_gate", batch_quality)
                        attempt["status"] = "ok"
                        attempt["note"] = (
                            "Bing CN 入口中文召回疑似漂移；观澜已补跑 Bing generic 入口，"
                            "并仅保留通过相关性门控的候选。"
                        )
                        results.extend(batch)
                        continue
                    recovered_batch, recovered_attempts, recovery_trace = _try_bing_cjk_variant_recovery(
                        original_query,
                        limit=limit,
                        network_mode=network_mode,
                        profile=profile,
                        quality=quality,
                    )
                    if recovered_attempts:
                        network_attempts.extend(recovered_attempts)
                        attempt["network_attempts"] = network_attempts
                        attempt["network_mode"] = _first_ok_network_mode(network_attempts)
                    if recovery_trace:
                        attempt["bing_cjk_recovery"] = recovery_trace
                    if recovered_batch:
                        batch = recovered_batch
                        attempt["result_count"] = len(batch)
                        attempt["quality_gate"] = recovery_trace.get("quality_gate", batch_quality)
                        attempt["status"] = "ok"
                        attempt["note"] = (
                            "Bing 原始中文召回疑似漂移；观澜已补跑 Bing 中文消歧 query，"
                            "并仅保留通过相关性门控的候选。"
                        )
                        results.extend(batch)
                        continue
                    if backend == "auto":
                        _record_bing_cjk_drift()
                    attempt["bing_issue"] = {
                        "type": "cjk_retrieval_drift",
                        "agent_note": (
                            "Bing 本轮中文开放网页召回明显漂移；这是 Bing 候选池/排序问题，"
                            "不是观澜质量门槛过紧。观澜已拒绝污染结果并继续兜底。"
                        ),
                    }
                attempt["status"] = _LOW_RELEVANCE_RESULT_STATUS
                attempt["note"] = str(batch_quality["note"])
                attempt["rejected_samples"] = _diagnostic_result_samples(batch)
                continue
            attempt["status"] = "ok" if batch else _zero_result_backend_status(name)
            if not batch:
                attempt["note"] = _zero_result_backend_note(name)
            results.extend(batch)
        except Exception as e:
            errors.append(f"{name}: {e}")
            network_attempts = getattr(e, "attempts", None)
            if isinstance(network_attempts, list) and network_attempts:
                attempt["network_attempts"] = network_attempts
                attempt["network_mode"] = _first_ok_network_mode(network_attempts)
            attempt.update(
                {
                    "status": getattr(e, "status", None) or _exception_backend_status(str(e)),
                    "error": str(e),
                    "note": _backend_error_note(name, str(e)),
                }
            )
        finally:
            backend_diagnostics.append(attempt)

    if backend in {"auto", "duckduckgo"} and not site and effective_scope != "university":
        _run_duckduckgo_recovery_pass(
            results,
            diagnostics=backend_diagnostics,
            errors=errors,
            original_query=original_query,
            fallback_open_query=fallback_open_query,
            effective_scope=effective_scope,
            scope_domains=scope_domains,
            recency=recency,
            quality=quality,
            limit=limit,
            network_mode=network_mode,
            profile=profile,
        )

    if backend in {"auto", "duckduckgo"} and not site and effective_scope != "university":
        _run_multi_entity_fanout_pass(
            results,
            diagnostics=backend_diagnostics,
            errors=errors,
            original_query=original_query,
            query_shape=query_shape,
            effective_scope=effective_scope,
            scope_domains=scope_domains,
            recency=recency,
            quality=quality,
            limit=limit,
            network_mode=network_mode,
            profile=profile,
        )

    _append_direct_source_seed_results(
        results,
        diagnostics=backend_diagnostics,
        original_query=original_query,
        route_plan=route_plan.to_dict(),
        effective_scope=effective_scope,
        site=site,
        limit=limit,
    )

    if not results and effective_scope == "university" and not site and backend in {"auto", "duckduckgo"}:
        fallback_query = _apply_recency_query(original_query, recency)
        attempt = {
            "backend": "duckduckgo:open_fallback",
            "status": "unknown",
            "result_count": 0,
            "error": "",
            "note": "高校 scope 站点约束未产出结果，自动用开放网页补搜，并继续按高校实体和信源类型排序。",
        }
        try:
            batch, network_attempts = _search_backend_with_network(
                "duckduckgo",
                fallback_query,
                limit=limit,
                network_mode=network_mode,
                profile=profile,
            )
            attempt["result_count"] = len(batch)
            attempt["network_attempts"] = network_attempts
            attempt["network_mode"] = _first_ok_network_mode(network_attempts)
            attempt["status"] = "ok" if batch else "no_results_or_parser_miss"
            results.extend(batch)
        except Exception as e:
            errors.append(f"duckduckgo:open_fallback: {e}")
            network_attempts = getattr(e, "attempts", None)
            if isinstance(network_attempts, list) and network_attempts:
                attempt["network_attempts"] = network_attempts
                attempt["network_mode"] = _first_ok_network_mode(network_attempts)
            attempt.update(
                {
                    "status": getattr(e, "status", None) or _exception_backend_status(str(e)),
                    "error": str(e),
                    "note": _backend_error_note("duckduckgo:open_fallback", str(e)),
                }
            )
        finally:
            backend_diagnostics.append(attempt)

    if effective_scope == "university" and not site and backend in {"auto", "duckduckgo"}:
        inferred_domains = _infer_university_site_domains(results, original_query)
        for domain in inferred_domains[:1]:
            site_query = _apply_recency_query(f"site:{domain} {original_query}", recency)
            attempt = {
                "backend": "duckduckgo:site_inferred",
                "status": "unknown",
                "result_count": 0,
                "error": "",
                "note": f"已从高校搜索结果识别到学校主域 {domain}，自动补一轮站内搜索。",
                "site": domain,
            }
            try:
                batch, network_attempts = _search_backend_with_network(
                    "duckduckgo",
                    site_query,
                    limit=limit,
                    network_mode=network_mode,
                    profile=profile,
                )
                attempt["result_count"] = len(batch)
                attempt["network_attempts"] = network_attempts
                attempt["network_mode"] = _first_ok_network_mode(network_attempts)
                batch_quality = _assess_backend_batch_quality(original_query, batch, quality)
                attempt["quality_gate"] = batch_quality
                if batch and not batch_quality["usable"]:
                    attempt["status"] = _LOW_RELEVANCE_RESULT_STATUS
                    attempt["note"] = str(batch_quality["note"])
                    continue
                attempt["status"] = "ok" if batch else "no_results_or_parser_miss"
                results.extend(batch)
            except Exception as e:
                errors.append(f"duckduckgo:site_inferred: {e}")
                network_attempts = getattr(e, "attempts", None)
                if isinstance(network_attempts, list) and network_attempts:
                    attempt["network_attempts"] = network_attempts
                    attempt["network_mode"] = _first_ok_network_mode(network_attempts)
                attempt.update(
                    {
                        "status": getattr(e, "status", None) or _exception_backend_status(str(e)),
                        "error": str(e),
                        "note": _backend_error_note("duckduckgo:site_inferred", str(e)),
                    }
                )
            finally:
                backend_diagnostics.append(attempt)

    site_filter: dict[str, Any] = {"enabled": False}
    if site:
        results, site_filter = _apply_site_hard_filter(results, site)
        backend_diagnostics.append(
            {
                "backend": f"site_filter:{site_filter.get('site') or site}",
                "status": "ok" if site_filter.get("kept", 0) else "no_results",
                "result_count": site_filter.get("kept", 0),
                "error": "",
                "note": (
                    f"`--site {site_filter.get('site') or site}` 已按硬过滤执行，只保留该域名及其子域。"
                    if site_filter.get("kept", 0)
                    else f"`--site {site_filter.get('site') or site}` 已按硬过滤执行，候选全部来自域外，未放宽返回。"
                ),
                "site_filter": site_filter,
            }
        )

    if not results and errors:
        fatal_errors = [
            error
            for error in errors
            if not (
                backend == "auto"
                and (
                    error.startswith("wechat-sogou:")
                    or "captcha_or_verification" in error.lower()
                    or "百度安全验证" in error
                )
                or "network_unreachable" in error
                or "proxy_error" in error
                or "network_changed" in error
            )
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
    backend_summary = _backend_diagnostic_summary(backend_diagnostics)
    scope_distinction = _scope_distinction_diagnostics(results, quality=quality, effective_scope=effective_scope)
    external_fetch_strategy = _external_fetch_strategy(
        original_query,
        results=results,
        diagnostics=backend_diagnostics,
        backend_summary=backend_summary,
        route_plan=route_plan.to_dict(),
        site_filter=site_filter,
        scope_distinction=scope_distinction,
    )
    ranked = rank_results(
        results,
        query=original_query,
        backend_order=order,
        preferred_scope=effective_scope,
        cluster_threshold=cluster_threshold,
        recency=recency,
        quality=quality,
    )
    output_full = [r.to_dict() for r in ranked[:limit]]
    quality_summary = search_quality_summary(
        output_full,
        quality=quality,
        limit=limit,
        site_filter=site_filter,
        time_constraint=time_constraint,
        limit_advice=limit_advice,
        external_fetch_strategy=external_fetch_strategy,
        scope_distinction=scope_distinction,
    )
    for item in output_full:
        item.setdefault("trace", {})
        item["trace"].update(
            {
                "effective_query": query,
                "requested_scope": requested_scope or "",
                "effective_scope": effective_scope or "",
                "scope_rewrite": (
                    f"{requested_scope}->{effective_scope}"
                    if requested_scope and effective_scope and requested_scope != effective_scope
                    else ""
                ),
                "backend_order": order,
                "cache": cache_meta["status"],
                "cache_key": cache_key,
                "cluster_threshold": cluster_threshold,
                "query_recency": recency,
                "route_plan": route_plan.to_dict(),
                "query_strategy": query_strategy,
                "query_shape": query_shape,
                "query_quality": quality,
                "quality_summary": quality_summary,
                "site_filter": site_filter,
                "time_constraint": time_constraint,
                "agent_limit_advice": limit_advice,
                "scope_distinction": scope_distinction,
                "external_fetch_strategy": external_fetch_strategy,
                "backend_diagnostics": backend_diagnostics,
                "backend_summary": backend_summary,
                "backend_recovery": backend_recovery,
                "network_profile": network_profile,
                "network_health": network_health_snapshot(),
                "errors": list(errors),
            }
        )
    if cache_meta["enabled"]:
        _cache_set("search", cache_key, {"results": output_full})
    output = [dict(item) for item in output_full]
    if not trace:
        for item in output:
            item.pop("score_parts", None)
    shared_diagnostics = _search_shared_diagnostics(
        original_query=original_query,
        effective_query=query,
        requested_scope=requested_scope,
        effective_scope=effective_scope,
        order=order,
        cache_meta=cache_meta,
        cache_key=cache_key,
        cluster_threshold=cluster_threshold,
        recency=recency,
        route_plan=route_plan.to_dict(),
        query_strategy=query_strategy,
        query_shape=query_shape,
        quality=quality,
        quality_summary=quality_summary,
        site_filter=site_filter,
        time_constraint=time_constraint,
        limit_advice=limit_advice,
        scope_distinction=scope_distinction,
        external_fetch_strategy=external_fetch_strategy,
        backend_diagnostics=backend_diagnostics,
        backend_summary=backend_summary,
        backend_recovery=backend_recovery,
        errors=errors,
        network_profile=network_profile,
    )
    return SearchResults(output, diagnostics=shared_diagnostics)


def _search_shared_diagnostics(
    *,
    original_query: str,
    effective_query: str,
    requested_scope: str | None,
    effective_scope: str | None,
    order: list[str],
    cache_meta: dict[str, Any],
    cache_key: str,
    cluster_threshold: str,
    recency: dict[str, Any],
    route_plan: dict[str, Any],
    query_strategy: dict[str, Any],
    query_shape: dict[str, Any],
    quality: dict[str, Any],
    quality_summary: dict[str, Any],
    backend_diagnostics: list[dict[str, Any]],
    backend_summary: dict[str, Any],
    backend_recovery: dict[str, Any],
    errors: list[str],
    network_profile: dict[str, Any] | None = None,
    site_filter: dict[str, Any] | None = None,
    time_constraint: dict[str, Any] | None = None,
    limit_advice: dict[str, Any] | None = None,
    scope_distinction: dict[str, Any] | None = None,
    external_fetch_strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "query": original_query,
        "effective_query": effective_query,
        "requested_scope": requested_scope or "",
        "effective_scope": effective_scope or "",
        "scope_rewrite": (
            f"{requested_scope}->{effective_scope}"
            if requested_scope and effective_scope and requested_scope != effective_scope
            else ""
        ),
        "backend_order": order,
        "cache": cache_meta["status"],
        "cache_key": cache_key,
        "cluster_threshold": cluster_threshold,
        "query_recency": recency,
        "route_plan": route_plan,
        "query_strategy": query_strategy,
        "query_shape": query_shape,
        "query_quality": quality,
        "quality_summary": quality_summary,
        "site_filter": site_filter or {"enabled": False},
        "time_constraint": time_constraint or {"enabled": False},
        "agent_limit_advice": limit_advice or {"enabled": False},
        "scope_distinction": scope_distinction or {"enabled": False},
        "external_fetch_strategy": external_fetch_strategy or {"enabled": False},
        "backend_diagnostics": backend_diagnostics,
        "backend_summary": backend_summary,
        "backend_recovery": backend_recovery,
        "network_profile": network_profile or build_network_profile(),
        "network_health": network_health_snapshot(),
        "errors": list(errors),
    }


def _search_limit_advice(limit: int) -> dict[str, Any]:
    current = max(int(limit or 0), 0)
    threshold = 30
    if current >= threshold:
        return {"enabled": False, "limit": current, "recommended_limit": DEFAULT_SEARCH_LIMIT}
    return {
        "enabled": True,
        "limit": current,
        "recommended_limit": DEFAULT_SEARCH_LIMIT,
        "threshold": threshold,
        "severity": "warn" if current < 20 else "note",
        "message": (
            f"当前 --limit {current} 适合 smoke test，不适合严肃研究；"
            f"Agent 应尽量说服用户接受 --limit {DEFAULT_SEARCH_LIMIT}，再压缩输出给用户。"
        ),
        "agent_instruction": (
            "不要因为用户给了很小的 limit 就直接下最终结论；先说明小样本风险，"
            f"建议补跑 `guanlan search \"query\" --limit {DEFAULT_SEARCH_LIMIT} --trace`。"
        ),
    }


def _search_time_constraint(recency: dict[str, Any]) -> dict[str, Any]:
    if not recency.get("enabled"):
        return {"enabled": False}
    label = str(recency.get("label") or "recent")
    strict = label in {"year", "year_range"}
    return {
        "enabled": True,
        "label": label,
        "strictness": "strong" if strict else "medium",
        "start_date": str(recency.get("start_date") or ""),
        "end_date": str(recency.get("end_date") or ""),
        "matched_terms": list(recency.get("matched_terms") or []),
        "instruction": (
            "显式年份/年份范围是强约束：主结论优先使用窗口内证据，窗口外材料只作背景。"
            if strict
            else "近期/热点查询需要优先使用窗口内证据，旧材料只作背景。"
        ),
    }


def _normalize_site_constraint(site: str | None) -> str:
    value = (site or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/", 1)[0].strip(".")
    if value.startswith("www."):
        value = value[4:]
    return value


def _site_matches_constraint(domain: str, site: str) -> bool:
    domain = _normalize_site_constraint(domain)
    site = _normalize_site_constraint(site)
    if not domain or not site:
        return False
    return domain == site or domain.endswith("." + site)


def _apply_site_hard_filter(results: list[SearchResult], site: str) -> tuple[list[SearchResult], dict[str, Any]]:
    normalized = _normalize_site_constraint(site)
    kept: list[SearchResult] = []
    removed_domains: list[str] = []
    for item in results:
        domain = item.domain or _domain(item.url)
        if _site_matches_constraint(domain, normalized):
            kept.append(item)
            continue
        if domain:
            removed_domains.append(domain)
    return kept, {
        "enabled": True,
        "site": normalized,
        "mode": "hard",
        "kept": len(kept),
        "removed": len(results) - len(kept),
        "removed_domains": _unique_keep_order(removed_domains)[:8],
        "relaxed": False,
        "agent_instruction": (
            f"`--site {normalized}` 不应被放宽；若结果为空，Agent 应改为读该站点入口、站内搜索页或请求外部 WebFetch 补证。"
        ),
    }


def _scope_distinction_diagnostics(
    results: list[SearchResult],
    *,
    quality: dict[str, Any],
    effective_scope: str | None,
) -> dict[str, Any]:
    scope = str(effective_scope or quality.get("requested_scope") or "")
    if not scope:
        return {"enabled": False}
    preferred_scopes = {str(item) for item in quality.get("preferred_scopes") or [] if str(item)}
    preferred_types = {str(item) for item in quality.get("preferred_source_types") or [] if str(item)}
    domains = _unique_keep_order([item.domain or _domain(item.url) for item in results if item.url])
    source_types = _unique_keep_order([item.source_type for item in results if item.source_type])
    preferred_hits = [
        item
        for item in results
        if item.matched_scope in preferred_scopes or item.source_type in preferred_types or item.matched_scope == scope
    ]
    warnings: list[str] = []
    if results and not preferred_hits:
        warnings.append(f"`{scope}` scope 结果未明显命中偏好信源，可能被开放网页或相邻 scope 稀释。")
    if len(domains) <= 1 and len(results) >= 3:
        warnings.append("scope 结果域名过于集中，建议补一个相邻 scope 或目标站点。")
    if len(source_types) <= 1 and len(results) >= 4:
        warnings.append("scope 结果来源类型过于单一，建议补证据角色查询。")
    return {
        "enabled": True,
        "scope": scope,
        "status": "warn" if warnings else "ok",
        "preferred_hit_count": len(preferred_hits),
        "domain_count": len(domains),
        "source_type_count": len(source_types),
        "warnings": warnings,
        "agent_instruction": (
            "如果 scope_distinction=warn，不要把当前结果当成该垂直场景的完整答案；"
            "先按 query_strategy 的角色 query 或相邻 scope 补搜。"
        ),
    }


def _external_fetch_strategy(
    query: str,
    *,
    results: list[SearchResult],
    diagnostics: list[dict[str, Any]],
    backend_summary: dict[str, Any],
    route_plan: dict[str, Any],
    site_filter: dict[str, Any] | None = None,
    scope_distinction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    site_filter = site_filter or {}
    scope_distinction = scope_distinction or {}
    reasons: list[str] = []
    if not results:
        reasons.append("no_usable_results")
    if site_filter.get("enabled") and site_filter.get("kept", 0) == 0:
        reasons.append("site_filter_empty")
    search_ok = [
        str(item.get("backend") or "")
        for item in diagnostics
        if item.get("status") == "ok"
        and not str(item.get("backend") or "").startswith(("direct:", "site_filter:"))
    ]
    direct_seed_ok = any(
        item.get("status") == "ok" and str(item.get("backend") or "").startswith("direct:")
        for item in diagnostics
    )
    if not search_ok and direct_seed_ok:
        reasons.append("direct_seed_only")
    search_problem = any(
        item.get("status") not in {"ok", "skipped"}
        and not str(item.get("backend") or "").startswith(("direct:", "site_filter:"))
        for item in diagnostics
    )
    if not search_ok and (search_problem or (
        backend_summary.get("errors") or backend_summary.get("blocked") or backend_summary.get("parser_miss")
    )):
        reasons.append("backend_unavailable_or_parser_miss")
    if scope_distinction.get("status") == "warn" and len(results) < 3:
        reasons.append("scope_distinction_weak")
    if not reasons:
        return {"enabled": False}

    candidate_urls: list[str] = []
    for item in results[:6]:
        if item.url:
            candidate_urls.append(item.url)
    for diag in diagnostics:
        for key in ("url", "candidate_url"):
            url = str(diag.get(key) or "")
            if url:
                candidate_urls.append(url)
    for seed in route_plan.get("target_sites") or []:
        site = _normalize_site_constraint(str(seed))
        if site:
            candidate_urls.append(f"https://{site}")
    if site_filter.get("site"):
        candidate_urls.append(f"https://{site_filter['site']}")
    candidate_urls = _unique_keep_order(candidate_urls)[:8]
    return {
        "enabled": True,
        "reasons": _unique_keep_order(reasons),
        "candidate_urls": candidate_urls,
        "agent_instruction": (
            "这是 Guanlan 给 Agent 的外部补证策略：先说明“我用 Guanlan 规划信源和质量边界，"
            "再用 WebFetch 读取指定页面补证”。不要把 WebFetch 写成 Guanlan 脆弱或失败，"
            "而要写成观澜主动调度外部读取能力增强搜索结果。"
        ),
        "reporting_contract": [
            "外显回答时说明 WebFetch 是本轮搜索策略的一部分。",
            "保留 Guanlan 的 route/site/time/quality 约束，不要用 WebFetch 返回的单页覆盖整个证据包。",
        ],
        "webfetch_policy": "only_after_guanlan_workflow_gap",
    }


def _append_direct_source_seed_results(
    results: list[SearchResult],
    *,
    diagnostics: list[dict[str, Any]],
    original_query: str,
    route_plan: dict[str, Any],
    effective_scope: str | None,
    site: str | None,
    limit: int,
) -> None:
    """Add small authoritative entrypoint candidates for high-confidence vertical tasks."""
    if site:
        return
    intents = list(route_plan.get("primary_intents") or []) + list(route_plan.get("secondary_intents") or [])
    scopes = _unique_keep_order([scope for scope in [effective_scope, *(route_plan.get("preferred_scopes") or [])] if scope])
    should_seed_with_results = is_live_sports_lookup(original_query, intents=intents, scopes=scopes) or is_finance_lookup(original_query, intents=intents, scopes=scopes)
    if results and not should_seed_with_results:
        return
    seeds = direct_source_seeds(
        original_query,
        intents=intents,
        scopes=scopes,
        limit=min(max(limit, 1), 8),
    )
    if not seeds:
        return
    existing = {_canonical_url(item.url) for item in results if item.url}
    added: list[SearchResult] = []
    for seed in seeds:
        url = str(seed.get("url") or "")
        key = _canonical_url(url)
        if not url or key in existing:
            continue
        existing.add(key)
        role = str(seed.get("evidence_role") or "open_web_context")
        item = SearchResult(
            title=str(seed.get("title") or url),
            url=url,
            snippet=str(seed.get("snippet") or ""),
            source=str(seed.get("source") or "direct_source"),
            rank=len(results) + len(added) + 1,
            domain=_domain(url),
            source_type=str(seed.get("source_type") or "通用网页"),
            matched_scope=str(seed.get("matched_scope") or effective_scope or ""),
            trust_level=int(seed.get("trust_level") or 3),
            evidence_role=role,
        )
        item.trace.update(
            {
                "direct_source_seed": True,
                "seed_id": str(seed.get("seed_id") or ""),
                "seed_reason": "high_confidence_vertical_entrypoint",
                "evidence_role_hint": role,
                "read_ready": bool(seed.get("read_ready", True)),
            }
        )
        added.append(item)
    if not added:
        return
    results.extend(added)
    scopes_text = ",".join(_unique_keep_order([item.matched_scope for item in added if item.matched_scope])) or "vertical"
    diagnostics.append(
        {
            "backend": f"direct:{scopes_text}:seed",
            "status": "ok",
            "result_count": len(added),
            "error": "",
            "note": (
                "命中高确定性垂直场景，已直接加入权威入口候选；"
                "不要只依赖搜索引擎发现，下一步应 read 这些入口核验正文。"
            ),
            "seed_ids": [str(item.trace.get("seed_id") or "") for item in added],
        }
    )


def _run_duckduckgo_recovery_pass(
    results: list[SearchResult],
    *,
    diagnostics: list[dict[str, Any]],
    errors: list[str],
    original_query: str,
    fallback_open_query: str,
    effective_scope: str | None,
    scope_domains: list[str],
    recency: dict[str, Any],
    quality: dict[str, Any],
    limit: int,
    network_mode: str,
    profile: str | None,
) -> None:
    """Try lower-friction DuckDuckGo queries after blocked/over-narrow attempts."""
    if _usable_candidate_count(results, original_query, quality) >= _recovery_target_count(limit):
        return
    if not _recovery_needed(results, diagnostics, original_query, quality, limit):
        return

    attempted_queries = {
        str(item.get("query") or "").strip()
        for item in diagnostics
        if str(item.get("query") or "").strip()
    }
    if effective_scope and scope_domains:
        for domain in scope_domains[:3]:
            if _usable_candidate_count(results, original_query, quality) >= _recovery_target_count(limit):
                break
            query = _apply_recency_query(f"site:{domain} {original_query}", recency)
            if query in attempted_queries:
                continue
            attempted_queries.add(query)
            _run_duckduckgo_recovery_attempt(
                results,
                diagnostics=diagnostics,
                errors=errors,
                backend_name="duckduckgo:scope_lite",
                query=query,
                original_query=original_query,
                quality=quality,
                limit=limit,
                note=f"scope 查询未产出足够候选，自动拆成单域名站内补搜：{domain}。",
                site=domain,
                network_mode=network_mode,
                profile=profile,
            )

    if _usable_candidate_count(results, original_query, quality) < _recovery_target_count(limit):
        if fallback_open_query not in attempted_queries:
            attempted_queries.add(fallback_open_query)
            _run_duckduckgo_recovery_attempt(
                results,
                diagnostics=diagnostics,
                errors=errors,
                backend_name="duckduckgo:open_fallback",
                query=fallback_open_query,
                original_query=original_query,
                quality=quality,
                limit=limit,
                note="主后端受阻或 scope 过窄，自动用原始 query 开放补搜，并继续按信源质量排序。",
                network_mode=network_mode,
                profile=profile,
            )

    for variant in _duckduckgo_recovery_query_variants(original_query, effective_scope, quality):
        if _usable_candidate_count(results, original_query, quality) >= _recovery_target_count(limit):
            break
        query = _apply_recency_query(variant, recency)
        if query in attempted_queries:
            continue
        attempted_queries.add(query)
        _run_duckduckgo_recovery_attempt(
            results,
            diagnostics=diagnostics,
            errors=errors,
            backend_name="duckduckgo:query_variant",
            query=query,
            original_query=original_query,
            quality=quality,
            limit=limit,
            note="短词/特殊字符/歧义 query 未产出足够候选，自动追加保守 query variant。",
            network_mode=network_mode,
            profile=profile,
        )


def _run_multi_entity_fanout_pass(
    results: list[SearchResult],
    *,
    diagnostics: list[dict[str, Any]],
    errors: list[str],
    original_query: str,
    query_shape: dict[str, Any],
    effective_scope: str | None,
    scope_domains: list[str],
    recency: dict[str, Any],
    quality: dict[str, Any],
    limit: int,
    network_mode: str,
    profile: str | None,
) -> None:
    """Add bounded entity-specific passes for broad comparison/list queries."""
    if not query_shape.get("multi_entity"):
        return
    entities = [
        entity
        for entity in (str(item).strip() for item in query_shape.get("entities") or [])
        if entity and not re.fullmatch(r"(?:19|20)\d{2}", entity)
    ]
    entities = _unique_keep_order(entities)
    if len(entities) < 4:
        return
    if _multi_entity_coverage_count(results, entities) >= min(4, len(entities)):
        return

    focus_terms = _multi_entity_focus_terms(original_query, entities)
    attempted_queries = {
        str(item.get("query") or "").strip()
        for item in diagnostics
        if str(item.get("query") or "").strip()
    }
    per_entity_limit = max(2, min(5, (max(limit, 1) // min(len(entities), 5)) + 1))
    fanout_entities = entities[:5]
    for entity in fanout_entities:
        if _multi_entity_coverage_count(results, entities) >= min(4, len(entities)):
            break
        base_query = _collapse_ws(f"{entity} {' '.join(focus_terms)}")
        if not base_query or base_query == entity:
            base_query = _collapse_ws(f"{entity} {original_query}")
        query = base_query
        if effective_scope and scope_domains:
            from guanlan.search_sources import scoped_query

            query = scoped_query(
                base_query,
                scope_domains,
                max_sites=min(4, _SHORT_SCOPED_QUERY_MAX_SITES.get(effective_scope, 4)),
            )
        query = _apply_recency_query(query, recency)
        if query in attempted_queries:
            continue
        attempted_queries.add(query)
        _run_duckduckgo_recovery_attempt(
            results,
            diagnostics=diagnostics,
            errors=errors,
            backend_name="duckduckgo:entity_fanout",
            query=query,
            original_query=f"{entity} {original_query}",
            quality=quality,
            limit=per_entity_limit,
            note=(
                "检测到多实体查询，自动按实体拆分补搜，避免只保留第一个实体造成对比失真。"
            ),
            extra={"entity": entity, "fanout_total": len(fanout_entities)},
            network_mode=network_mode,
            profile=profile,
        )


def _multi_entity_coverage_count(results: list[SearchResult], entities: list[str]) -> int:
    if not results or not entities:
        return 0
    matched = {
        entity
        for entity in entities
        if any(_result_text_contains(result, entity) for result in results)
    }
    return len(matched)


def _multi_entity_focus_terms(query: str, entities: list[str]) -> list[str]:
    entity_set = {entity.lower() for entity in entities}
    focus_terms: list[str] = []
    for term in _query_relevance_terms(query):
        if term.lower() in entity_set:
            continue
        if term in {"最新", "最近", "今天", "刚刚"}:
            continue
        focus_terms.append(term)
    if any(term in query for term in ("对比", "比较")) and "对比" not in focus_terms:
        focus_terms.append("对比")
    if "排名" in query and "排名" not in focus_terms:
        focus_terms.append("排名")
    if not focus_terms:
        focus_terms.append("资料")
    return _unique_keep_order(focus_terms)[:5]


def _recovery_target_count(limit: int) -> int:
    return max(1, min(5, max(limit, 1)))


def _recovery_needed(
    results: list[SearchResult],
    diagnostics: list[dict[str, Any]],
    original_query: str,
    quality: dict[str, Any],
    limit: int,
) -> bool:
    if results:
        return False
    if _usable_candidate_count(results, original_query, quality) < _recovery_target_count(limit):
        return True
    problem_statuses = {
        "parser_miss",
        "no_results",
        "no_results_or_parser_miss",
        _LOW_RELEVANCE_RESULT_STATUS,
        _UNSAFE_RESULT_STATUS,
        "blocked",
        "error",
        *_NETWORK_PROBLEM_STATUSES,
    }
    return any(item.get("status") in problem_statuses for item in diagnostics)


def _run_duckduckgo_recovery_attempt(
    results: list[SearchResult],
    *,
    diagnostics: list[dict[str, Any]],
    errors: list[str],
    backend_name: str,
    query: str,
    original_query: str,
    quality: dict[str, Any],
    limit: int,
    note: str,
    site: str = "",
    extra: dict[str, Any] | None = None,
    network_mode: str = "auto",
    profile: str | None = None,
) -> None:
    attempt: dict[str, Any] = {
        "backend": backend_name,
        "status": "unknown",
        "result_count": 0,
        "error": "",
        "note": note,
        "query": query,
    }
    if site:
        attempt["site"] = site
    if extra:
        attempt.update(extra)
    try:
        batch, network_attempts = _search_backend_with_network(
            "duckduckgo",
            query,
            limit=limit,
            network_mode=network_mode,
            profile=profile,
        )
        attempt["network_attempts"] = network_attempts
        attempt["network_mode"] = _first_ok_network_mode(network_attempts)
        attempt["result_count"] = len(batch)
        batch_quality = _assess_backend_batch_quality(original_query, batch, quality)
        attempt["quality_gate"] = batch_quality
        if batch and not batch_quality["usable"]:
            attempt["status"] = _LOW_RELEVANCE_RESULT_STATUS
            attempt["note"] = f"{note} 但相关性门控未通过：{batch_quality['note']}"
            attempt["rejected_samples"] = _diagnostic_result_samples(batch)
            return
        attempt["status"] = "ok" if batch else "no_results_or_parser_miss"
        if not batch:
            attempt["note"] = f"{note} DuckDuckGo 仍未产出结果。"
        results.extend(batch)
    except Exception as e:
        errors.append(f"{backend_name}: {e}")
        network_attempts = getattr(e, "attempts", None)
        if isinstance(network_attempts, list) and network_attempts:
            attempt["network_attempts"] = network_attempts
            attempt["network_mode"] = _first_ok_network_mode(network_attempts)
        attempt.update(
            {
                "status": getattr(e, "status", None) or _exception_backend_status(str(e)),
                "error": str(e),
                "note": _backend_error_note(backend_name, str(e)),
            }
        )
    finally:
        diagnostics.append(attempt)


def _duckduckgo_recovery_query_variants(
    query: str,
    effective_scope: str | None,
    quality: dict[str, Any],
) -> list[str]:
    normalized = _collapse_ws(query).strip()
    lowered = normalized.lower()
    variants: list[str] = []
    if lowered in {"c++", '"c++"'}:
        variants.extend(["C++ programming language", "C plus plus language"])
    if normalized == "苹果" and effective_scope in {"ecommerce", "tech_dev", "social_web"}:
        if effective_scope == "ecommerce":
            variants.append("苹果 iPhone 手机 用户评价 价格")
        elif effective_scope == "tech_dev":
            variants.append("苹果 Apple iPhone 技术 参数 芯片")
        else:
            variants.append("苹果 Apple iPhone 微博 知乎 评价")
    if len(normalized) <= 4 and quality.get("preferred_scopes"):
        variants.append(f"{normalized} {quality['preferred_scopes'][0]}")
    return _unique_keep_order([item for item in variants if item and item != normalized])


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
        quality_scope = preferred_scope or _preferred_quality_scope_for_domain(
            item.domain,
            list(quality.get("preferred_scopes") or []),
        )
        try:
            from guanlan.search_sources import classify_domain

            meta = classify_domain(item.domain, preferred_scope=quality_scope)
        except Exception:
            meta = {"source_type": "通用网页", "matched_scope": "", "trust_level": 1}
        item.source_type = meta["source_type"]
        item.matched_scope = meta["matched_scope"]
        item.trust_level = meta["trust_level"]
        source_card = source_card_for_domain(
            item.domain,
            preferred_scope=quality_scope,
        )
        if source_card.source_type and (
            meta["source_type"] == "通用网页"
            or (source_card.scope_id and source_card.scope_id != meta.get("matched_scope", ""))
        ):
            item.source_type = source_card.source_type
            item.matched_scope = source_card.scope_id
            try:
                from guanlan.search_sources import resolve_scope

                if source_card.scope_id:
                    item.trust_level = resolve_scope(source_card.scope_id).trust_level
            except Exception:
                pass
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
        recency_trace = _result_recency_trace(item, recency)
        item.trace["recency"] = recency_trace
        item.published_at = str(recency_trace.get("result_date") or "")
        item.date_source = str(recency_trace.get("date_source") or "")
        item.freshness_confidence = str(recency_trace.get("freshness_confidence") or "")
        item.stale_risk = str(recency_trace.get("stale_risk") or "")
        item.trace["quality"] = _result_quality_trace(item, quality)
    ranked = sorted(deduped, key=lambda r: (-r.score, r.rank))
    _assign_topic_clusters(ranked, threshold=cluster_threshold)
    ranked = _order_topic_representatives_first(ranked)
    for idx, item in enumerate(ranked, start=1):
        item.rank = idx
    return ranked


def _usable_candidate_count(
    results: list[SearchResult],
    query: str,
    quality: dict[str, Any] | None = None,
) -> int:
    """Count candidates that pass the same coarse batch gate used for backend fallback."""
    if not results:
        return 0
    deduped = _dedupe_results(list(results))
    gate = _assess_backend_batch_quality(query, deduped, quality or {})
    if not gate["usable"]:
        return 0
    return len(deduped)


def _try_bing_cjk_variant_recovery(
    query: str,
    *,
    limit: int,
    network_mode: str,
    profile: str | None,
    quality: dict[str, Any],
) -> tuple[list[SearchResult], list[dict[str, Any]], dict[str, Any]]:
    """Give Bing one narrow CJK disambiguation pass before declaring drift."""
    attempts: list[dict[str, Any]] = []
    tried: list[dict[str, Any]] = []
    for variant in _bing_cjk_query_variants(query, quality=quality)[:2]:
        if not variant or variant == query:
            continue
        try:
            batch, network_attempts = _search_backend_with_network(
                "bing",
                variant,
                limit=limit,
                network_mode=network_mode,
                profile=profile,
            )
            attempts.extend(network_attempts)
            batch_quality = _assess_backend_batch_quality(query, batch, quality)
            tried.append(
                {
                    "query": variant,
                    "result_count": len(batch),
                    "status": "ok" if batch_quality["usable"] and batch else _LOW_RELEVANCE_RESULT_STATUS,
                    "quality_gate": batch_quality,
                }
            )
            if batch and batch_quality["usable"]:
                for item in batch:
                    item.trace["backend_query_variant"] = variant
                    item.trace["backend_query_variant_reason"] = "bing_cjk_disambiguation"
                return batch, attempts, {
                    "status": "recovered",
                    "strategy": "bing_cjk_disambiguation",
                    "selected_query": variant,
                    "tried": tried,
                    "quality_gate": batch_quality,
                    "agent_note": "Bing 原始中文召回漂移，观澜用消歧 query 补跑后才保留结果。",
                }
        except Exception as exc:  # noqa: BLE001 - represented as diagnostics, not fatal
            network_attempts = getattr(exc, "attempts", None)
            if isinstance(network_attempts, list):
                attempts.extend(network_attempts)
            tried.append(
                {
                    "query": variant,
                    "result_count": 0,
                    "status": getattr(exc, "status", None) or _exception_backend_status(str(exc)),
                    "error": str(exc),
                }
            )
    if not tried:
        return [], attempts, {}
    return [], attempts, {
        "status": "not_recovered",
        "strategy": "bing_cjk_disambiguation",
        "tried": tried,
        "agent_note": (
            "Bing 中文消歧补跑仍未产出可用结果；应按 Bing 上游召回漂移处理，"
            "不要归因于观澜质量门槛过紧。"
        ),
    }


def _try_bing_generic_recovery(
    query: str,
    *,
    limit: int,
    network_mode: str,
    profile: str | None,
    quality: dict[str, Any],
) -> tuple[list[SearchResult], list[dict[str, Any]], dict[str, Any]]:
    """Try Bing without region-locked query params when the CN entrypoint is weak."""
    try:
        batch, attempts = _search_backend_with_network(
            "bing_generic",
            query,
            limit=limit,
            network_mode=network_mode,
            profile=profile,
        )
    except Exception as exc:  # noqa: BLE001 - represented as diagnostics, not fatal
        attempts = getattr(exc, "attempts", None)
        return [], attempts if isinstance(attempts, list) else [], {
            "status": getattr(exc, "status", None) or _exception_backend_status(str(exc)),
            "strategy": "bing_generic",
            "error": str(exc),
            "agent_note": (
                "Bing CN 入口异常后，Bing generic 入口也未恢复；应继续使用后续后端或外部读取策略。"
            ),
        }

    batch_quality = _assess_backend_batch_quality(query, batch, quality)
    if batch and batch_quality["usable"]:
        for item in batch:
            item.source = "bing"
            item.trace["backend_query_variant"] = query
            item.trace["backend_query_variant_reason"] = "bing_generic_fallback"
            item.trace["backend_entrypoint"] = "bing_generic"
        return batch, attempts, {
            "status": "recovered",
            "strategy": "bing_generic",
            "result_count": len(batch),
            "quality_gate": batch_quality,
            "agent_note": "Bing CN 入口异常或漂移，观澜用 Bing generic 入口补跑后恢复了可用结果。",
        }

    return [], attempts, {
        "status": "not_recovered",
        "strategy": "bing_generic",
        "result_count": len(batch),
        "quality_gate": batch_quality,
        "rejected_samples": _diagnostic_result_samples(batch),
        "agent_note": (
            "Bing generic 入口仍未产出可用中文结果；应按 Bing 上游召回/页面问题处理，"
            "不要归因于观澜质量门槛过紧。"
        ),
    }


def _bing_cjk_query_variants(query: str, *, quality: dict[str, Any] | None = None) -> list[str]:
    normalized = _collapse_ws(query)
    terms = _query_relevance_terms(normalized)
    variants: list[str] = []
    if terms:
        variants.append(" ".join(terms))
    if "固态电池" in normalized:
        core = " ".join(term for term in terms if term not in {"固态硬盘", "ssd", "nvme"}) or normalized
        variants.append(f"{core} 动力电池 汽车 企业 产业化 -固态硬盘 -SSD -NVMe")
    if "低空经济" in normalized:
        variants.append("低空经济 政策 补贴 官方 通知 政府 部委 地方")
    if "小王子" in normalized and "狐狸" in normalized:
        variants.append('"小王子" 狐狸 驯服 台词 圣埃克苏佩里')
    if quality and quality.get("intent") == "policy":
        variants.append(f"{normalized} 官方 原文 通知 政府")
    return _unique_keep_order([item for item in variants if item and item != normalized])


def _diagnostic_result_samples(results: list[SearchResult], limit: int = 3) -> list[dict[str, str]]:
    """Keep a tiny, non-sensitive sample of rejected candidates for debugging."""
    samples: list[dict[str, str]] = []
    for item in results[: max(0, limit)]:
        samples.append(
            {
                "title": _collapse_ws(item.title)[:120],
                "domain": item.domain or _domain(item.url),
                "url": item.url,
                "snippet": _collapse_ws(item.snippet)[:160],
            }
        )
    return samples


def _preferred_quality_scope_for_domain(domain: str, preferred_scopes: list[str]) -> str | None:
    if not domain or not preferred_scopes:
        return None
    try:
        from guanlan.search_sources import resolve_scope

        normalized = domain.lower().removeprefix("www.")
        for scope_id in preferred_scopes:
            scope = resolve_scope(scope_id)
            if any(normalized == candidate or normalized.endswith("." + candidate) for candidate in scope.domains):
                return scope.id
    except Exception:
        return None
    return None


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
    if "proxy_error" in lowered or "proxy" in lowered and ("refused" in lowered or "tunnel" in lowered):
        return "proxy_error"
    if "network_unreachable" in lowered or "timed out" in lowered or "timeout" in lowered:
        return "network_unreachable"
    if "network_changed" in lowered:
        return "network_changed"
    if "captcha" in lowered or "verification" in lowered or "安全验证" in error or "验证码" in error:
        return "blocked"
    return "error"


def _backend_error_note(backend: str, error: str) -> str:
    lowered = error.lower()
    if "proxy_error" in lowered or ("proxy" in lowered and ("refused" in lowered or "tunnel" in lowered)):
        return f"{backend} 代理路径不可用；不要把它当作无资料，应切换 direct/current 或等待代理恢复。"
    if "network_unreachable" in lowered or "timed out" in lowered or "timeout" in lowered:
        return f"{backend} 当前网络路径不可达/超时；Guanlan 会尝试其他网络路径，仍失败时应报告为网络证据而非空结果。"
    if "network_changed" in lowered:
        return f"{backend} 多个网络路径状态不一致，可能刚切换代理或 DNS；建议立即用 --network direct/proxy 复测一次。"
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
    low_relevance = [item["backend"] for item in diagnostics if item.get("status") == _LOW_RELEVANCE_RESULT_STATUS]
    unsafe_filtered = [item["backend"] for item in diagnostics if item.get("status") == _UNSAFE_RESULT_STATUS]
    blocked = [item["backend"] for item in diagnostics if item.get("status") == "blocked"]
    errors = [item["backend"] for item in diagnostics if item.get("status") == "error"]
    network_errors = [item["backend"] for item in diagnostics if item.get("status") in _NETWORK_PROBLEM_STATUSES]
    problem_statuses = {
        "parser_miss",
        "no_results",
        "no_results_or_parser_miss",
        _LOW_RELEVANCE_RESULT_STATUS,
        _UNSAFE_RESULT_STATUS,
        "blocked",
        "error",
        *_NETWORK_PROBLEM_STATUSES,
    }
    first_ok_index = next((idx for idx, item in enumerate(diagnostics) if item.get("status") == "ok"), None)
    fallback_used = bool(
        first_ok_index is not None
        and any(
            item.get("status") in problem_statuses
            for item in diagnostics[:first_ok_index]
        )
    )
    return {
        "ok": ok,
        "parser_miss": parser_miss,
        "zero_results": zero_results,
        "low_relevance": low_relevance,
        "unsafe_filtered": unsafe_filtered,
        "blocked": blocked,
        "network_errors": network_errors,
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
    problem_statuses = {
        "parser_miss",
        "no_results",
        "no_results_or_parser_miss",
        _LOW_RELEVANCE_RESULT_STATUS,
        "blocked",
        "error",
        *_NETWORK_PROBLEM_STATUSES,
    }
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
    low_relevance = [str(item.get("backend")) for item in problems if item.get("status") == _LOW_RELEVANCE_RESULT_STATUS]
    unsafe_filtered = [str(item.get("backend")) for item in problems if item.get("status") == _UNSAFE_RESULT_STATUS]
    network_errors = [str(item.get("backend")) for item in problems if item.get("status") in _NETWORK_PROBLEM_STATUSES]
    errors = [str(item.get("backend")) for item in problems if item.get("status") == "error"]

    guidance: list[str] = []
    if "baidu" in blocked:
        guidance.append("Baidu 当前被安全验证/反爬拦截；不要自动重试或尝试破解验证码，把它当作本轮不可用。")
    if parser_miss:
        guidance.append(f"{', '.join(parser_miss)} 页面可访问但解析器未抓到结果，应视为解析器/模板问题而非资料不存在。")
    if low_relevance:
        guidance.append(f"{', '.join(low_relevance)} 返回了候选但相关性门控未通过，已继续补充后续后端。")
        if "bing" in low_relevance:
            guidance.append(
                "Bing 本轮中文开放网页召回明显漂移；这是 Bing 上游候选池/排序问题，"
                "不是观澜质量门槛过紧。观澜已拒绝污染结果，并应优先使用 Baidu/DuckDuckGo、scope 或 research 兜底。"
            )
    if "bing" in parser_miss or any(item.get("backend") == "bing" and item.get("status") in {"no_results", "no_results_or_parser_miss"} for item in problems):
        guidance.append(
            "Bing 已被调用但没有产出可用中文结果；Agent 应把它解释为 Bing 后端/上游结果问题，"
            "不要说成观澜质量门槛太紧。"
        )
    if unsafe_filtered:
        guidance.append(f"{', '.join(unsafe_filtered)} 返回了成人/不安全候选，观澜已过滤并拒绝把它当搜索证据。")
    if network_errors:
        guidance.append(
            f"{', '.join(network_errors)} 当前网络路径不可用或刚发生代理切换；"
            "不要汇报为无资料，应使用 --network direct/proxy/current 复测或等待网络健康缓存刷新。"
        )
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
        "low_relevance_backends": low_relevance,
        "unsafe_filtered_backends": unsafe_filtered,
        "network_error_backends": network_errors,
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
    command_limit = max(limit, DEFAULT_SEARCH_LIMIT)
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


def _normalize_network_mode(value: str | None = None) -> str:
    mode = (value or os.environ.get("GUANLAN_NETWORK") or "auto").strip().lower().replace("_", "-")
    aliases = {
        "": "auto",
        "default": "auto",
        "public": "auto",
        "system": "current",
        "env": "current",
        "none": "direct",
        "no-proxy": "direct",
    }
    mode = aliases.get(mode, mode)
    if mode not in _VALID_NETWORK_MODES:
        return "auto"
    return mode


def _configured_proxy_url() -> str:
    for key in (
        "GUANLAN_PROXY_URL",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _redact_proxy_url(value: str) -> str:
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return "<configured>"
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    auth = "***@" if parsed.username or parsed.password else ""
    return urllib.parse.urlunsplit((parsed.scheme, f"{auth}{host}{port}", "", "", ""))


def build_network_profile(network_mode: str | None = None, profile: str | None = None) -> dict[str, Any]:
    mode = _normalize_network_mode(network_mode)
    proxy_url = _configured_proxy_url()
    return {
        "mode": mode,
        "profile": profile or "",
        "proxy_detected": bool(proxy_url),
        "proxy": _redact_proxy_url(proxy_url),
        "attempt_order": _network_modes_for_backend("auto", mode, profile=profile),
        "preflight": "lazy_per_backend",
        "direct_available": True,
        "proxy_available": bool(proxy_url),
        "agent_instruction": (
            "本机能上网不等于所有搜索后端都可用；看到 network_unreachable/proxy_error 时不要报告为无资料，"
            "应切换 network/backend 或使用缓存。"
        ),
    }


def network_health_snapshot() -> dict[str, Any]:
    now = time.time()
    snapshot: dict[str, Any] = {}
    for key, item in list(_NETWORK_HEALTH_CACHE.items()):
        if now - float(item.get("updated_at", 0) or 0) > _NETWORK_HEALTH_TTL_SECONDS:
            _NETWORK_HEALTH_CACHE.pop(key, None)
            continue
        clean = dict(item)
        clean["updated_age_sec"] = round(now - float(item.get("updated_at", 0) or 0), 3)
        clean.pop("updated_at", None)
        snapshot[key] = clean
    return snapshot


def _record_network_health(backend: str, mode: str, status: str, error: str = "") -> None:
    _NETWORK_HEALTH_CACHE[f"{backend}:{mode}"] = {
        "backend": backend,
        "mode": mode,
        "status": status,
        "error": _collapse_ws(error)[:180],
        "updated_at": time.time(),
        "ttl_sec": _NETWORK_HEALTH_TTL_SECONDS,
    }


def _network_modes_for_backend(backend: str, requested: str, profile: str | None = None) -> list[str]:
    requested = _normalize_network_mode(requested)
    proxy_url = _configured_proxy_url()
    if requested != "auto":
        if requested == "proxy" and not proxy_url:
            return ["proxy"]
        return [requested]
    if backend == "baidu" or profile == "china":
        modes = ["current", "direct", "proxy"]
    else:
        modes = ["current", "proxy", "direct"]
    if not proxy_url:
        modes = [mode for mode in modes if mode != "proxy"]
    return _unique_keep_order(modes)


def _open_url_with_network(req: urllib.request.Request, *, timeout: int, network_mode: str):
    mode = _normalize_network_mode(network_mode)
    context = _default_ssl_context()
    if mode == "direct":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
        return opener.open(req, timeout=timeout)
    if mode == "proxy":
        proxy = _configured_proxy_url()
        if not proxy:
            raise RuntimeError("proxy_error: proxy mode requested but no proxy is configured")
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
            urllib.request.HTTPSHandler(context=context),
        )
        return opener.open(req, timeout=timeout)
    return _urlopen_with_context(req, timeout=timeout, context=context)


def _default_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _urlopen_with_context(
    req: urllib.request.Request,
    *,
    timeout: int,
    context: ssl.SSLContext,
):
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=context)
    except TypeError:
        # Test doubles and older patched urlopen callables may not accept context.
        return urllib.request.urlopen(req, timeout=timeout)


def _classify_network_exception(exc: Exception, mode: str) -> str:
    text = str(exc).lower()
    if mode == "proxy" and (
        "proxy" in text
        or "tunnel" in text
        or "connection refused" in text
        or "timed out" in text
        or "timeout" in text
    ):
        return "proxy_error"
    if isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in text:
        return "network_unreachable"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (socket.gaierror, TimeoutError, ConnectionError, ssl.SSLError, OSError)):
            return "network_unreachable"
    if isinstance(exc, (socket.gaierror, ConnectionError, ssl.SSLError, OSError)):
        return "network_unreachable"
    if "name or service not known" in text or "nodename nor servname" in text or "temporary failure" in text:
        return "network_unreachable"
    return ""


def _search_backend_with_network(
    backend: str,
    query: str,
    *,
    limit: int,
    network_mode: str,
    profile: str | None,
) -> tuple[list[SearchResult], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    non_network_errors: list[Exception] = []
    for mode in _network_modes_for_backend(backend, network_mode, profile=profile):
        attempt = {
            "backend": backend,
            "network_mode": mode,
            "status": "unknown",
            "error": "",
            "latency_ms": 0,
            "proxy_detected": bool(_configured_proxy_url()),
        }
        started = time.time()
        try:
            batch = _call_search_backend_once(backend, query, limit=limit, network_mode=mode)
            attempt["status"] = "ok"
            attempt["result_count"] = len(batch)
            attempt["latency_ms"] = int((time.time() - started) * 1000)
            _record_network_health(backend, mode, "ok")
            attempts.append(attempt)
            return batch, attempts
        except Exception as exc:  # noqa: BLE001 - classified into diagnostics
            attempt["latency_ms"] = int((time.time() - started) * 1000)
            network_status = _classify_network_exception(exc, mode)
            if network_status:
                attempt["status"] = network_status
                attempt["error"] = str(exc)
                _record_network_health(backend, mode, network_status, str(exc))
                attempts.append(attempt)
                continue
            attempt["status"] = _exception_backend_status(str(exc))
            attempt["error"] = str(exc)
            _record_network_health(backend, mode, attempt["status"], str(exc))
            attempts.append(attempt)
            non_network_errors.append(exc)
            if attempt["status"] == "blocked":
                continue
            break
    if non_network_errors:
        exc = non_network_errors[-1]
        if attempts:
            setattr(exc, "attempts", attempts)
        raise exc
    status = _network_failure_status(attempts)
    raise NetworkBackendError(status, _network_failure_message(attempts), attempts)


def _call_search_backend_once(
    backend: str,
    query: str,
    *,
    limit: int,
    network_mode: str,
) -> list[SearchResult]:
    fn = {
        "duckduckgo": _search_duckduckgo,
        "bing": _search_bing,
        "bing_generic": _search_bing_generic,
        "baidu": _search_baidu,
    }[backend]
    try:
        return fn(query, limit=limit, network_mode=network_mode)
    except TypeError as exc:
        if "network_mode" not in str(exc):
            raise
        return fn(query, limit=limit)


def _network_failure_status(attempts: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status") or "") for item in attempts}
    if "ok" in statuses:
        return "network_changed"
    if "proxy_error" in statuses and statuses <= {"proxy_error", "unknown"}:
        return "proxy_error"
    if statuses & {"network_unreachable", "proxy_error"}:
        return "network_unreachable"
    return "network_changed"


def _network_failure_message(attempts: list[dict[str, Any]]) -> str:
    bits = []
    for item in attempts:
        mode = item.get("network_mode", "")
        status = item.get("status", "")
        error = _collapse_ws(str(item.get("error") or ""))[:120]
        bits.append(f"{mode}={status}{': ' + error if error else ''}")
    return "; ".join(bits) or "network path unavailable"


def _first_ok_network_mode(attempts: list[dict[str, Any]]) -> str:
    for item in attempts:
        if item.get("status") == "ok":
            return str(item.get("network_mode") or "")
    return str(attempts[-1].get("network_mode") or "") if attempts else ""


def _raise_for_search_block(page: str, backend: str) -> None:
    markers = _SEARCH_BLOCK_MARKERS.get(backend, ())
    page_lower = page.lower()
    for marker in markers:
        if marker.lower() in page_lower:
            raise RuntimeError(f"captcha_or_verification: {marker}")


def _search_duckduckgo(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    network_mode: str = "current",
) -> list[SearchResult]:
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with _open_url_with_network(req, timeout=_SEARCH_TIMEOUT, network_mode=network_mode) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    _raise_for_search_block(page, "duckduckgo")

    parser = _DuckDuckGoHTMLParser()
    parser.feed(page)
    return _dedupe_results(parser.results)[:limit]


def _search_bing(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    network_mode: str = "current",
) -> list[SearchResult]:
    return _search_bing_html(query, limit=limit, network_mode=network_mode, regional=True)


def _search_bing_generic(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    network_mode: str = "current",
) -> list[SearchResult]:
    return _search_bing_html(query, limit=limit, network_mode=network_mode, regional=False)


def _search_bing_html(
    query: str,
    limit: int,
    network_mode: str,
    *,
    regional: bool,
) -> list[SearchResult]:
    params: dict[str, str | int] = {
        "q": query,
        "count": min(max(limit, 1), 50),
        "safeSearch": "Strict",
    }
    contains_cjk = _contains_cjk(query)
    if regional:
        if contains_cjk:
            params.update({"mkt": "zh-CN", "setLang": "zh-Hans", "cc": "CN"})
            accept_language = "zh-CN,zh;q=0.9,en;q=0.6"
        else:
            params.update({"mkt": "en-US", "setLang": "en", "cc": "US"})
            accept_language = "en-US,en;q=0.9"
    else:
        accept_language = "zh-CN,zh;q=0.9,en;q=0.6" if contains_cjk else "en-US,en;q=0.9"
    url = "https://www.bing.com/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": accept_language,
        },
    )
    with _open_url_with_network(req, timeout=_SEARCH_TIMEOUT, network_mode=network_mode) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    _raise_for_search_block(page, "bing")

    results: list[SearchResult] = []
    for block in re.findall(r'<li\b(?=[^>]*class=["\'][^"\']*\bb_algo\b[^"\']*["\'])[^>]*>.*?</li>', page, flags=re.S | re.I):
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


def _search_baidu(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    network_mode: str = "current",
) -> list[SearchResult]:
    # Baidu redirects HTTPS to HTTP for classic result HTML in some regions.
    url = "http://www.baidu.com/s?" + urllib.parse.urlencode({"wd": query, "rn": min(max(limit, 1), 50)})
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with _open_url_with_network(req, timeout=_SEARCH_TIMEOUT, network_mode=network_mode) as resp:
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
    return wechatsogou.WechatSogouAPI(captcha_break_time=1, timeout=_SEARCH_TIMEOUT)


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
        timeout=_SEARCH_TIMEOUT,
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
        "行情中心",
        "数据加载中",
        "自选股",
        "沪深京",
        "客户端下载",
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
    dynamic_shell = _looks_like_dynamic_finance_shell(
        normalized,
        url=url,
        quality=quality,
        body_ratio=body_ratio,
    )
    fallback = bool(quality.get("fallback"))
    usable = bool(
        quality.get("score", 0) >= 55
        and quality.get("chars", 0) >= 160
        and not blocked_markers
        and not dynamic_shell
        and not fallback
    )
    recommendations: list[str] = []
    if quality.get("fallback"):
        recommendations.append("当前内容来自搜索兜底，只能作为线索，建议补读原文或更稳定转载页。")
    if blocked_markers:
        recommendations.append("疑似登录墙/安全验证/访问限制，建议改用公开转载、官方来源或人工授权后的平台能力。")
    if quality.get("noise_hits"):
        recommendations.append("正文中仍有导航、登录或推荐阅读噪音，回答时优先引用连续正文段落。")
    if dynamic_shell:
        recommendations.append("疑似动态财经页壳或行情入口，正文不可直接作为事实证据；建议改用 `guanlan stock ...` 结构化行情、公告/监管源或可导出的数据页补证。")
    if quality.get("chars", 0) < 500:
        recommendations.append("正文较短，可能只读到摘要或页面片段，建议扩大 read 或补充 search/research。")
    if not recommendations:
        recommendations.append("正文可用度较好，可作为证据摘读；仍建议和搜索结果中的来源身份交叉验证。")
    return {
        "url": url,
        "label": quality.get("label", "unknown"),
        "score": quality.get("score", 0),
        "usable": usable,
        "fallback": fallback,
        "body_ratio": body_ratio,
        "chars": quality.get("chars", 0),
        "cjk_chars": quality.get("cjk_chars", 0),
        "line_count": quality.get("line_count", 0),
        "avg_line_len": quality.get("avg_line_len", 0),
        "short_line_count": short_lines,
        "link_like_line_count": link_like_lines,
        "noise_hits": quality.get("noise_hits", []),
        "blocked_markers": blocked_markers,
        "dynamic_shell": dynamic_shell,
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
    if report.get("dynamic_shell"):
        lines.append("- dynamic_shell: true")
    if report.get("fallback"):
        lines.append("- fallback: search_context_only")
    recommendations = report.get("recommendations") or []
    if recommendations:
        lines.append("- 建议:")
        lines.extend(f"  - {item}" for item in recommendations[:4])
    return "\n".join(lines)


def _looks_like_dynamic_finance_shell(
    text: str,
    *,
    url: str,
    quality: dict[str, Any],
    body_ratio: float,
) -> bool:
    domain = _domain(url)
    if domain not in {
        "quote.eastmoney.com",
        "eastmoney.com",
        "finance.sina.com.cn",
        "xueqiu.com",
        "guba.eastmoney.com",
        "10jqka.com.cn",
        "cn.investing.com",
        "finance.yahoo.com",
        "nasdaq.com",
    }:
        return False
    normalized = _collapse_ws(text).lower()
    markers = (
        "行情中心",
        "自选股",
        "沪深京",
        "数据加载中",
        "客户端下载",
        "打开app",
        "stock quote",
        "market activity",
        "portfolio",
        "系统检测到您的ip",
        "访问过于频繁",
        "请验证以继续访问",
        "upgrade_browser",
        "window.location.href",
        "galileotelemetry",
        "new aegis",
        "公司概况",
        "股权信息",
        "股票交易",
    )
    marker_hits = sum(1 for marker in markers if marker.lower() in normalized)
    if domain == "xueqiu.com" and any(marker.lower() in normalized for marker in ("访问过于频繁", "请验证以继续访问")):
        return True
    if any(marker in normalized for marker in ("upgrade_browser", "galileotelemetry", "window.location.href")):
        return True
    weak_size = int(quality.get("chars") or 0) < 900
    noisy_shape = body_ratio < 0.45 or int(quality.get("line_count") or 0) < 8
    return bool(marker_hits >= 2 and (weak_size or noisy_shape))


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
    concurrency: int = 1,
) -> list[dict[str, Any]]:
    """Read multiple URLs with per-item errors kept in the result list."""
    records: list[dict[str, Any]] = []
    jobs: list[tuple[int, str]] = []
    for idx, url in enumerate(urls, start=1):
        clean_url = url.strip()
        if not clean_url:
            continue
        blocked_reason = _batch_block_reason(clean_url)
        if blocked_reason:
            records.append({"rank": idx, "url": clean_url, "status": "blocked", "error": blocked_reason})
            continue
        jobs.append((idx, clean_url))

    def read_one(job: tuple[int, str]) -> dict[str, Any]:
        idx, clean_url = job
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
            return {"rank": idx, "url": clean_url, "status": "ok", "content": content}
        except Exception as e:
            return {"rank": idx, "url": clean_url, "status": "error", "error": str(e)}
    workers = max(1, min(int(concurrency or 1), 8))
    if workers == 1 or len(jobs) <= 1:
        records.extend(read_one(job) for job in jobs)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            records.extend(executor.map(read_one, jobs))
        for item in records:
            item["concurrency"] = workers
    records.sort(key=lambda item: int(item.get("rank") or 0))
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
    raw_results = search_web(
        query,
        limit=max(limit, 1),
        site=domain or None,
        profile=profile,
    )
    results = _filter_read_fallback_results(raw_results, url)
    if not results and domain:
        raw_results = search_web(f"{domain} {query}", limit=max(limit, 1), profile=profile)
        results = _filter_read_fallback_results(raw_results, url)

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
    if _url_path_is_weak_identity(url) and not results:
        lines.extend(
            [
                "",
                "兜底状态: unusable",
                "原因: URL 只有数字路径或弱身份信息，公开搜索未能确认同一页面；为避免把无关结果包装成原文上下文，本次不输出搜索兜底结果。",
                "给 Agent: 不要引用本页搜索兜底作为证据。请改用 `guanlan diagnose page \"URL\"`、站内结构化入口，或按 external_fetch_strategy 使用宿主 WebFetch 定点读取该 URL。",
            ]
        )
        return "\n".join(lines)
    lines.extend(["", format_search_markdown(results, title=f"观澜搜索兜底 / {query}")])
    return "\n".join(lines)


def _filter_read_fallback_results(results: list[dict[str, Any]], url: str) -> list[dict[str, Any]]:
    """Keep fallback search context only when it can identify the target page.

    Numeric news URLs such as ithome.com/0/946/250.htm are especially risky:
    searching the path numbers often returns unrelated pages. For those weak
    identities we require same-domain URL/path evidence before exposing context.
    """
    if not _url_path_is_weak_identity(url):
        return list(results)
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    identity = _url_identity_parts(url)
    target_path = identity.get("path", "")
    compact = identity.get("compact", "")
    tail = identity.get("tail", "")
    kept: list[dict[str, Any]] = []
    for item in results:
        item_url = str(item.get("url") or "")
        item_domain = _domain(item_url)
        if domain and item_domain != domain:
            continue
        normalized_url = urllib.parse.unquote(item_url).lower()
        if target_path and target_path.lower() in normalized_url:
            kept.append(item)
            continue
        if compact and compact in re.sub(r"\D+", "", normalized_url):
            kept.append(item)
            continue
        if tail and re.search(rf"(?:/|-|_){re.escape(tail)}(?:\\.|/|$)", normalized_url):
            kept.append(item)
    return kept


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
    cache_ttl: int = 0,
) -> dict[str, Any]:
    """Build an agent-ready evidence packet from search + selected reads."""
    preset_config = resolve_research_preset(preset)
    effective_limit = max(limit if limit is not None else preset_config["limit"], 1)
    effective_profile = profile or preset_config["profile"]
    preset_config = _research_preset_for_profile(preset_config, effective_profile)
    explicit_scope = scope if scope not in (None, "") else None
    explicit_sites = _normalize_sites(([site] if site else []) + (sites or []))
    preset_override: dict[str, str] = {}
    if explicit_scope is None and not explicit_sites:
        raw_route_plan = build_route_plan(
            query,
            scope=None,
            site=site,
            sites=explicit_sites,
            profile=effective_profile,
            limit=effective_limit,
            read_top=read_top,
        )
        override_preset = dominant_vertical_preset(
            query,
            current_preset=str(preset_config.get("id") or ""),
            route_intents=list(raw_route_plan.primary_intents) + list(raw_route_plan.secondary_intents),
        )
        if override_preset:
            old_preset = str(preset_config.get("id") or "")
            preset_config = resolve_research_preset(override_preset)
            effective_limit = max(limit if limit is not None else preset_config["limit"], 1)
            if profile is None:
                effective_profile = preset_config["profile"]
            preset_config = _research_preset_for_profile(preset_config, effective_profile)
            preset_override = {
                "from": old_preset,
                "to": str(preset_config.get("id") or override_preset),
                "reason": (
                    "用户 query 已明显命中更强的垂直路由，自动纠正不匹配 preset，"
                    "避免把简单场景带到错误信源池。"
                ),
            }
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
    if read_top is None:
        effective_read_top = max(effective_read_top, 5)
    if read_top is None and preset_config["id"] == "general":
        effective_read_top = max(route_plan.read_top, 5)
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
        cache_ttl=max(cache_ttl, 0),
    )
    feed_results, feed_errors, feed_groups = _research_feed_discovery(
        query,
        route_plan=route_plan.to_dict(),
        preset_id=preset_config["id"],
        limit=effective_limit,
        profile=effective_profile,
    )
    if feed_groups:
        result_groups.extend(feed_groups)
    if feed_errors:
        search_errors.extend(feed_errors)
    if feed_results:
        results = _merge_ranked_result_dicts(results + feed_results, limit=effective_limit)
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

    source_diagnostics = build_source_diagnostics(results, route_plan=route_plan.to_dict())
    freshness_guard = build_freshness_guard(results, route_plan=route_plan.to_dict(), recency=recency)
    source_mix_guard = build_source_mix_guard(results, route_plan=route_plan.to_dict())
    packet = {
        "query": query,
        "preset": preset_config["id"],
        "preset_name": preset_config["name"],
        "preset_override": preset_override,
        "profile": effective_profile or "",
        "site": site or "",
        "sites": effective_sites,
        "scope": effective_scope or "",
        "scopes": effective_scopes,
        "search_backend": search_backend,
        "read_backend": read_backend,
        "read_top": effective_read_top,
        "cache_ttl": max(cache_ttl, 0),
        "route_plan": route_plan.to_dict(),
        "query_strategy": query_strategy,
        "result_count": len(results),
        "source_mix": _source_mix(results),
        "source_diagnostics": source_diagnostics,
        "freshness_guard": freshness_guard,
        "source_mix_guard": source_mix_guard,
        "topic_count": len({item.get("topic_key") for item in results if item.get("topic_key")}),
        "search_errors": search_errors,
        "result_groups": result_groups,
        "results": results,
        "selected_evidence": _select_representative_evidence(results, effective_select_top),
        "readings": readings,
        "read_quality_summary": _read_quality_summary(readings),
        "guidance": list(preset_config.get("guidance", [])) + [
            *(
                [
                    f"已自动将 preset 从 {preset_override.get('from')} 纠正为 {preset_override.get('to')}；"
                    "这是为了保护明显垂直场景不被错误参数带偏。"
                ]
                if preset_override
                else []
            ),
            "这是一份证据上下文，不是最终结论。",
            "先看“精选代表证据”，再回到完整搜索池补充细节；不要只凭第一条结果下判断。",
            "优先使用不同 topic、不同 source_type 的材料交叉验证。",
            "topic=related 的结果可作为补充线索，不要当成独立证据重复计数。",
            "阅读兜底内容只代表公开搜索线索，不等同于原文全文。",
            "路由计划是软约束：优先源用于提高适配度，开放搜索兜底用于避免信息池过窄。",
            "查询策略会把同一问题拆成不同证据角色；回答时要保留“官方、媒体、社区、用户样本”的差异。",
            "时效护栏会标出无日期、旧内容和窗口外材料；最新问题不要把旧稿当新进展。",
            "UGC/信源配比护栏会限制用户生成内容占比；事实问题必须让官方/权威/一手材料站到主证据位。",
            "research 默认会读取更多代表证据；如外层超时，优先降低 read_top，不要缩小 limit。",
        ] + (
            ["科技/技术类路线已强制补跑 RSS/精品内容流；RSS 适合作阅读发现和新鲜线索，不替代代码仓库、官方文档或原文核验。"]
            if feed_groups
            else []
        ),
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
    preset_override = packet.get("preset_override")
    if isinstance(preset_override, dict) and preset_override:
        lines.append(
            "- Preset 纠偏: "
            f"{preset_override.get('from')} -> {preset_override.get('to')}；{preset_override.get('reason', '')}"
        )
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

    freshness_guard = packet.get("freshness_guard")
    if isinstance(freshness_guard, dict):
        lines.extend(["", format_freshness_guard_markdown(freshness_guard)])

    source_mix_guard = packet.get("source_mix_guard")
    if isinstance(source_mix_guard, dict):
        lines.extend(["", format_source_mix_guard_markdown(source_mix_guard)])

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
    freshness_guard = packet.get("freshness_guard")
    if isinstance(freshness_guard, dict):
        lines.append("### 时效护栏")
        lines.append(format_freshness_guard_markdown(freshness_guard))
        lines.append("")
    source_mix_guard = packet.get("source_mix_guard")
    if isinstance(source_mix_guard, dict):
        lines.append("### UGC/信源配比护栏")
        lines.append(format_source_mix_guard_markdown(source_mix_guard))
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
        "entertainment": {
            "scope": "global_entertainment",
            "scopes": ["global_entertainment", "community_sample", "global_news"],
            "sites": ["billboard.com", "variety.com", "deadline.com", "hollywoodreporter.com", "rollingstone.com", "people.com"],
            "guidance": ["英文文娱问题优先欧美行业媒体、榜单/奖项、艺人或厂牌一手信息，粉丝讨论只作样本。"],
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
        "entertainment": "global_entertainment",
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
    cache_ttl: int = 0,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    groups: list[dict[str, Any]] = []
    jobs: list[tuple[str, str]] = [("scope", scope_id) for scope_id in scopes]
    jobs.extend(("site", site_id) for site_id in sites)
    if jobs and include_open_fallback:
        jobs.append(("general", "open_web"))
    if not jobs:
        results = search_web(query, limit=limit, backend=search_backend, profile=profile, cache_ttl=cache_ttl)
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
                cache_ttl=cache_ttl,
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


def _research_feed_discovery(
    query: str,
    *,
    route_plan: dict[str, Any],
    preset_id: str,
    limit: int,
    profile: str | None,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Run the mandatory RSS discovery pass for technology routes."""
    if not _requires_tech_rss_discovery(route_plan, preset_id):
        return [], [], []
    feed_limit = max(1, min(DEFAULT_FEEDS_LIMIT, max(limit, 20)))
    language = "en" if profile == "english" else "zh"
    category = "ai" if "ai" in set(route_plan.get("domains") or []) else "programming"
    errors: list[str] = []
    groups: list[dict[str, Any]] = []
    try:
        from guanlan.feeds import fetch_feed_source

        items = fetch_feed_source(
            "curated",
            limit=feed_limit,
            language=language,
            category=category,
        )
        results = [
            converted
            for idx, item in enumerate(items, start=1)
            if (converted := _feed_item_to_search_result(item, rank=idx)) is not None
        ]
        unavailable = [
            str((item.get("feed_status") or {}).get("error") or item.get("summary") or "")
            for item in items
            if item.get("evidence_role") == "source_availability_signal"
        ]
        if unavailable and not results:
            errors.append(f"feed:curated: {unavailable[0]}")
        groups.append(
            {
                "type": "feed",
                "label": "curated",
                "query": f"{query} / RSS curated:{category}:{language}",
                "result_count": len(results),
                "results": results,
                "forced": True,
                "reason": "tech_route_requires_rss_discovery",
                "source": "guanlan feeds curated",
                "category": category,
                "language": language,
                **({"error": unavailable[0]} if unavailable and not results else {}),
            }
        )
        return results, errors, groups
    except Exception as exc:
        message = f"feed:curated: {exc}"
        errors.append(message)
        groups.append(
            {
                "type": "feed",
                "label": "curated",
                "query": f"{query} / RSS curated:{category}:{language}",
                "result_count": 0,
                "results": [],
                "forced": True,
                "reason": "tech_route_requires_rss_discovery",
                "source": "guanlan feeds curated",
                "category": category,
                "language": language,
                "error": str(exc),
            }
        )
        return [], errors, groups


def _requires_tech_rss_discovery(route_plan: dict[str, Any], preset_id: str) -> bool:
    primary = set(route_plan.get("primary_intents") or [])
    return preset_id == "tech" or "tech" in primary


def _feed_item_to_search_result(item: dict[str, Any], *, rank: int) -> dict[str, Any] | None:
    url = str(item.get("url") or "").strip()
    if not url or item.get("evidence_role") == "source_availability_signal":
        return None
    source_id = str(item.get("source_id") or "curated")
    source_card = dict(item.get("source_card") or {})
    domain = str(source_card.get("domain") or _domain(url))
    source_type = str(source_card.get("source_type") or "RSS/内容发现")
    status = item.get("feed_status") if isinstance(item.get("feed_status"), dict) else {}
    risk_tags = [str(tag) for tag in item.get("risk_tags", []) if tag]
    return {
        "title": str(item.get("title") or url),
        "url": url,
        "snippet": str(item.get("summary") or item.get("content_direction") or ""),
        "source": f"feeds:{source_id}",
        "rank": rank,
        "domain": domain,
        "source_type": source_type,
        "matched_scope": "rss",
        "trust_level": 3,
        "evidence_role": str(item.get("evidence_role") or "reading_discovery_signal"),
        "score": max(1.0, 4.8 - rank * 0.02),
        "score_parts": {"rss_discovery": 1.0, "rank": max(0.0, 1 - rank / max(DEFAULT_FEEDS_LIMIT, 1))},
        "topic_key": str(item.get("source_title") or source_id),
        "topic_size": 1,
        "topic_role": "single",
        "trace": {
            "source_card": source_card,
            "feed_status": status,
            "risk_tags": risk_tags,
            "source_id": source_id,
            "published_at": str(item.get("published_at") or ""),
            "forced_rss_discovery": True,
        },
    }


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
        elif target == "social_web":
            role_preferences = ["user_sample", "review", "fresh_news"]
        elif target == "tech_dev":
            role_preferences = ["technical_primary", "developer_discussion", "base"]
        elif target == "ecommerce":
            role_preferences = ["review", "user_sample", "industry_report", "fresh_news", "base"]
        elif target == "finance":
            role_preferences = ["company_filing", "regulatory_notice", "market_quote", "market_news", "macro_data", "sentiment_sample", "base"]
        elif target in {"finance_disclosure", "finance_company"}:
            role_preferences = ["company_filing", "regulatory_notice", "exchange_announcement", "base"]
        elif target == "finance_quote":
            role_preferences = ["market_quote", "index_data", "market_news", "base"]
        elif target == "finance_macro":
            role_preferences = ["macro_data", "central_bank_notice", "market_expectation", "base"]
        elif target == "finance_sentiment":
            role_preferences = ["sentiment_sample", "market_news", "base"]
        elif target == "finance_research":
            role_preferences = ["analyst_opinion", "industry_report", "company_filing", "base"]
        elif target == "finance_news":
            role_preferences = ["market_news", "fresh_news", "base"]
        elif target == "business":
            role_preferences = ["industry_report", "company_context", "fresh_news", "base"]
        elif target == "sports":
            role_preferences = ["official_stat", "sports_report", "fresh_news", "base"]
        elif target == "university":
            role_preferences = ["university_official", "department_page", "admission_catalog", "faculty_profile", "base"]
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
        elif any(site in target for site in ("espn", "nba.com", "fifa", "uefa", "skysports", "theathletic")):
            role_preferences = ["official_stat", "sports_report", "fresh_news", "base"]
        elif any(site in target for site in ("cninfo", "sse.com", "szse", "hkexnews", "sec.gov", "csrc.gov")):
            role_preferences = ["company_filing", "regulatory_notice", "exchange_announcement", "base"]
        elif any(site in target for site in ("eastmoney", "finance.sina", "xueqiu", "nasdaq", "finance.yahoo")):
            role_preferences = ["market_quote", "sentiment_sample", "market_news", "base"]
        elif any(site in target for site in ("stats.gov.cn", "pbc.gov.cn", "safe.gov.cn", "fred.stlouisfed", "cmegroup")):
            role_preferences = ["macro_data", "central_bank_notice", "market_expectation", "base"]
        elif any(site in target for site in ("cls.cn", "stcn", "cnstock", "yicai")):
            role_preferences = ["market_news", "fresh_news", "base"]
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
        published_at=str(item.get("published_at", "")),
        date_source=str(item.get("date_source", "")),
        freshness_confidence=str(item.get("freshness_confidence", "")),
        stale_risk=str(item.get("stale_risk", "")),
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
    if preset in {"entertainment", "global_entertainment", "jp_kr_entertainment"} or _contains_any(text, ["文娱", "影视", "电影", "剧集", "综艺", "明星", "票房", "豆瓣", "猫眼", "游戏", "动漫", "漫画", "番剧", "轻小说", "二次元", "hollywood", "billboard", "k-pop", "kpop", "j-pop", "jpop"]):
        return "热度、口碑与消费判断"
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
    if preset in {"entertainment", "global_entertainment", "jp_kr_entertainment"} or _contains_any(query, ["文娱", "影视", "电影", "剧集", "综艺", "明星", "票房", "豆瓣", "猫眼", "游戏", "动漫", "漫画", "番剧", "轻小说", "二次元", "hollywood", "billboard", "k-pop", "kpop", "j-pop", "jpop"]):
        rules.append("涉及文娱时，分清平台数据/榜单、用户评分、行业报道、宣发通稿和粉丝讨论")
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
    if preset in {"entertainment", "global_entertainment", "jp_kr_entertainment"} or _contains_any(haystack, ["文娱", "影视", "电影", "剧集", "综艺", "明星", "票房", "豆瓣", "猫眼", "游戏", "动漫", "漫画", "番剧", "轻小说", "二次元", "entertainment", "hollywood", "billboard", "k-pop", "kpop", "j-pop", "jpop"]):
        intents.extend(["判断作品、艺人或游戏的热度、口碑和争议点", "为观影/消费、内容选题或舆情观察寻找公开样本"])
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
    if any(_source_has(key, ["文娱", "内容平台", "欧美文娱", "日韩文娱", "音乐产业", "K-pop", "J-pop"]) for key in source_keys):
        supports.append("区分平台热度、用户评分/评论和公开讨论中的文娱口碑线索")
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
    if any(_source_has(key, ["文娱", "欧美文娱", "日韩文娱", "音乐产业", "K-pop", "J-pop"]) for key in source_keys):
        limits.append("文娱平台数据、粉圈讨论、翻译搬运和宣发内容容易互相放大，不能直接当作大众结论")
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
    if preset in {"entertainment", "global_entertainment", "jp_kr_entertainment"} or _contains_any(text, ["文娱", "影视", "电影", "剧集", "综艺", "明星", "票房", "豆瓣", "猫眼", "游戏", "动漫", "漫画", "番剧", "轻小说", "二次元", "hollywood", "billboard", "k-pop", "kpop", "j-pop", "jpop"]):
        advice.append("如果你是为了观影/游玩/追综艺：把评分、评论、票房/播放热度和争议点分开看")
        advice.append("如果你是为了选题或舆情：关注平台间差异，不要把粉圈高声量写成大众共识")
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
    if preset == "entertainment" and not any(_source_has(key, ["文娱", "内容平台"]) for key in source_mix):
        steps.append("补充豆瓣、猫眼/灯塔、B站、微博或游戏平台等文娱垂直来源")
    if preset == "global_entertainment" and not any(_source_has(key, ["欧美文娱", "音乐产业"]) for key in source_mix):
        steps.append("补充 Variety、Deadline、Hollywood Reporter、Billboard、Rolling Stone 等欧美文娱源")
    if preset == "jp_kr_entertainment" and not any(_source_has(key, ["日韩文娱", "K-pop", "J-pop"]) for key in source_mix):
        steps.append("补充 Soompi、Oricon、Natalie、Naver 娱乐、Korea Herald 等日韩文娱源")
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


def build_freshness_guard(
    results: list[dict[str, Any]],
    route_plan: dict[str, Any] | None = None,
    recency: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an agent-visible guard against stale material in time-sensitive searches."""
    route_plan = route_plan or {}
    recency = recency or {}
    intents = set(route_plan.get("primary_intents") or []) | set(route_plan.get("secondary_intents") or [])
    required = bool(recency.get("enabled") or route_plan.get("freshness") or "hot_trend" in intents)
    dated = []
    in_window = []
    stale = []
    unknown = []
    high_risk = []
    date_source_counts: dict[str, int] = {}
    for item in results:
        trace_recency = (item.get("trace") or {}).get("recency") or {}
        date_value = str(item.get("published_at") or trace_recency.get("result_date") or "")
        date_source = str(item.get("date_source") or trace_recency.get("date_source") or "")
        stale_risk = str(item.get("stale_risk") or trace_recency.get("stale_risk") or "unknown")
        if date_value:
            dated.append(item)
            date_source_counts[date_source or "unknown"] = date_source_counts.get(date_source or "unknown", 0) + 1
            if trace_recency.get("in_window"):
                in_window.append(item)
            if stale_risk in {"medium", "high"} or (required and trace_recency.get("enabled") and not trace_recency.get("in_window")):
                stale.append(item)
            if stale_risk == "high":
                high_risk.append(item)
        else:
            unknown.append(item)
    total = max(len(results), 1)
    dated_ratio = len(dated) / total
    in_window_ratio = len(in_window) / total
    unknown_ratio = len(unknown) / total
    stale_ratio = len(stale) / total
    if not required:
        status = "pass" if stale_ratio <= 0.35 else "warn"
    elif in_window_ratio >= 0.45 and stale_ratio <= 0.25:
        status = "pass"
    elif dated_ratio >= 0.35 and stale_ratio <= 0.45:
        status = "warn"
    else:
        status = "fail"
    warnings: list[str] = []
    if required and unknown:
        warnings.append(f"有 {len(unknown)} 条候选未解析到发布日期，不能直接当作最新材料。")
    if stale:
        warnings.append(f"有 {len(stale)} 条候选存在旧内容风险，引用时要标明日期或降级为背景。")
    if required and not in_window:
        warnings.append("未找到明确落在当前时效窗口内的候选，应补搜最新/今日/本周或使用 hotnews。")
    return {
        "status": status,
        "required": required,
        "result_count": len(results),
        "dated_count": len(dated),
        "in_window_count": len(in_window),
        "stale_count": len(stale),
        "unknown_date_count": len(unknown),
        "high_stale_risk_count": len(high_risk),
        "dated_ratio": round(dated_ratio, 3),
        "in_window_ratio": round(in_window_ratio, 3),
        "stale_ratio": round(stale_ratio, 3),
        "unknown_date_ratio": round(unknown_ratio, 3),
        "date_source_counts": dict(sorted(date_source_counts.items(), key=lambda row: (-row[1], row[0]))),
        "warnings": warnings,
        "rules": [
            "最新/近期问题必须优先使用带明确日期且落在窗口内的材料。",
            "无日期候选只能作线索；旧日期候选只能作背景或历史脉络。",
            "回答中要写清发布日期来源和旧内容风险，不要把旧稿当新进展。",
        ],
    }


def build_source_mix_guard(
    results: list[dict[str, Any]],
    route_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an agent-visible guard for UGC/source mix ratios."""
    route_plan = route_plan or {}
    intents = set(route_plan.get("primary_intents") or []) | set(route_plan.get("secondary_intents") or [])
    ugc_results = [item for item in results if _is_ugc_result(item)]
    authority_results = [
        item
        for item in results
        if str(item.get("evidence_role") or "")
        in {
            "official_primary",
            "authoritative_report",
            "company_primary",
            "technical_primary",
            "company_filing",
            "regulatory_notice",
            "macro_data",
            "central_bank_notice",
            "statistics_release",
            "market_quote",
        }
    ]
    industry_results = [item for item in results if str(item.get("evidence_role") or "") in {"industry_report", "market_context", "fresh_news"}]
    total = max(len(results), 1)
    ugc_ratio = len(ugc_results) / total
    factual_intents = {
        "policy",
        "official_position",
        "global_policy",
        "company_primary",
        "standards_compliance",
        "medical_health",
        "legal_judicial",
        "finance",
        "finance_quote",
        "finance_disclosure",
        "finance_macro",
        "finance_research",
    }
    sample_intents = {
        "reputation",
        "purchase_advice",
        "global_reputation",
        "entertainment",
        "global_entertainment",
        "jp_kr_entertainment",
    }
    tech_intents = {"tech", "academic"}
    if intents & factual_intents:
        max_ugc_ratio = 0.2
        min_authority = 2
    elif intents & sample_intents:
        max_ugc_ratio = 0.6
        min_authority = 1
    elif intents & tech_intents:
        max_ugc_ratio = 0.35
        min_authority = 1
    else:
        max_ugc_ratio = 0.4
        min_authority = 1
    warnings: list[str] = []
    if ugc_ratio > max_ugc_ratio:
        warnings.append(f"UGC/社区样本占比 {ugc_ratio:.0%}，高于当前意图建议上限 {max_ugc_ratio:.0%}。")
    if min_authority and len(authority_results) < min_authority and not (intents & sample_intents and industry_results):
        warnings.append("权威/一手/技术主证据偏少，应补官方、权威媒体、公司一手或技术原始材料。")
    if intents & sample_intents and not ugc_results:
        warnings.append("口碑/评价问题缺少用户样本，应补知乎、微博、小红书、B站、Reddit 等公开样本。")
    status = "pass" if not warnings else "warn"
    return {
        "status": status,
        "result_count": len(results),
        "ugc_count": len(ugc_results),
        "ugc_ratio": round(ugc_ratio, 3),
        "max_recommended_ugc_ratio": max_ugc_ratio,
        "authority_count": len(authority_results),
        "industry_count": len(industry_results),
        "warnings": warnings,
        "rules": [
            "事实/政策/财经问题中，UGC 只能作讨论样本，不能做主证据。",
            "口碑问题允许较高 UGC 占比，但必须声明样本偏差，并补官方参数或垂类材料。",
            "技术问题优先官方文档、代码仓库、issue 和工程实践，社区讨论需要交叉验证。",
        ],
    }


def _is_ugc_result(item: dict[str, Any]) -> bool:
    role = str(item.get("evidence_role") or "")
    source_type = str(item.get("source_type") or "")
    domain = str(item.get("domain") or _domain(str(item.get("url", ""))))
    if role in {"user_sample", "community_discussion", "review"}:
        return True
    if any(marker in source_type for marker in ("社交", "社区", "评价/消费", "英文社区", "文娱/内容平台")):
        return True
    return domain in {"zhihu.com", "weibo.com", "xiaohongshu.com", "bilibili.com", "reddit.com", "news.ycombinator.com", "xueqiu.com"}


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


def format_freshness_guard_markdown(guard: dict[str, Any]) -> str:
    """Render freshness guard as compact Markdown."""
    lines = ["## 时效护栏"]
    lines.append(
        "- 状态: "
        f"{guard.get('status', 'unknown')} | "
        f"需要时效核验: {bool(guard.get('required'))} | "
        f"有日期: {guard.get('dated_count', 0)}/{guard.get('result_count', 0)} | "
        f"窗口内: {guard.get('in_window_count', 0)} | "
        f"旧内容风险: {guard.get('stale_count', 0)} | "
        f"无日期: {guard.get('unknown_date_count', 0)}"
    )
    sources = guard.get("date_source_counts") or {}
    if sources:
        lines.append("- 日期来源: " + "；".join(f"{key}: {value}" for key, value in list(sources.items())[:5]))
    for warning in guard.get("warnings") or []:
        lines.append(f"- 边界: {warning}")
    return "\n".join(lines)


def format_source_mix_guard_markdown(guard: dict[str, Any]) -> str:
    """Render source-mix guard as compact Markdown."""
    lines = ["## UGC/信源配比护栏"]
    lines.append(
        "- 状态: "
        f"{guard.get('status', 'unknown')} | "
        f"UGC: {guard.get('ugc_count', 0)}/{guard.get('result_count', 0)} "
        f"({float(guard.get('ugc_ratio') or 0):.0%}) | "
        f"建议上限: {float(guard.get('max_recommended_ugc_ratio') or 0):.0%} | "
        f"权威/一手: {guard.get('authority_count', 0)} | "
        f"产业/新闻: {guard.get('industry_count', 0)}"
    )
    for warning in guard.get("warnings") or []:
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
        lines.extend(_format_empty_search_diagnostics(getattr(results, "diagnostics", {}) or {}))
        return "\n".join(lines)

    for idx, item in enumerate(results, start=1):
        rank = item.get("rank") or idx
        item_title = _collapse_ws(str(item.get("title", "")))
        url = str(item.get("url", "")).strip()
        snippet = _collapse_ws(str(item.get("snippet", "")))
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
        lines.append(f"{rank}. [{source_type}{score_label}{topic_label}{role_label}] {item_title}")
        if url:
            lines.append(f"   {url}")
        date_bits = []
        if item.get("published_at"):
            date_bits.append(f"日期: {item['published_at']}")
        if item.get("date_source"):
            date_bits.append(f"日期来源: {item['date_source']}")
        if item.get("freshness_confidence"):
            date_bits.append(f"时效置信: {item['freshness_confidence']}")
        if item.get("stale_risk") and item.get("stale_risk") != "low":
            date_bits.append(f"旧内容风险: {item['stale_risk']}")
        if date_bits:
            lines.append("   " + " | ".join(date_bits))
        if snippet:
            lines.append(f"   {snippet[:240]}")
    return "\n".join(lines)


def _format_empty_search_diagnostics(trace: dict[str, Any]) -> list[str]:
    """Explain why an empty result set is empty instead of hiding backend evidence."""
    if not trace:
        return ["暂无搜索结果。"]

    diagnostics = trace.get("backend_diagnostics") or []
    if not diagnostics:
        return ["暂无搜索结果。"]

    lines = ["暂无可用搜索结果。", "", "## 后端诊断"]
    status_bits: list[str] = []
    for item in diagnostics:
        backend = str(item.get("backend") or "unknown")
        status = str(item.get("status") or "unknown")
        count = int(item.get("result_count") or 0)
        if status == _LOW_RELEVANCE_RESULT_STATUS:
            status_bits.append(f"{backend}=low_relevance({count})")
        elif status == _UNSAFE_RESULT_STATUS:
            raw_count = int(item.get("raw_result_count") or count)
            status_bits.append(f"{backend}=unsafe_filtered({raw_count})")
        elif status == "ok":
            status_bits.append(f"{backend}=ok({count})")
        else:
            status_bits.append(f"{backend}={status}")
    lines.append("- backend_status: " + ", ".join(status_bits))

    for item in diagnostics:
        backend = str(item.get("backend") or "unknown")
        status = str(item.get("status") or "")
        note = _collapse_ws(str(item.get("note") or ""))
        if status == _LOW_RELEVANCE_RESULT_STATUS:
            quality_gate = item.get("quality_gate") or {}
            reason = str(quality_gate.get("reason") or "low_relevance")
            top_domain = str(quality_gate.get("top_domain") or "")
            term_coverage = quality_gate.get("term_coverage")
            domain_part = f" top_domain={top_domain}" if top_domain else ""
            coverage_part = f" term_coverage={term_coverage}" if term_coverage is not None else ""
            lines.append(
                f"- {backend}: 返回了 {item.get('result_count', 0)} 条候选，但未通过相关性门控"
                f"（reason={reason}{domain_part}{coverage_part}），已拒绝进入结果池。"
            )
            if note:
                lines.append(f"  note: {note}")
            bing_issue = item.get("bing_issue") or {}
            if isinstance(bing_issue, dict) and bing_issue.get("agent_note"):
                lines.append(f"  agent_note: {bing_issue.get('agent_note')}")
            bing_recovery = item.get("bing_cjk_recovery") or {}
            if isinstance(bing_recovery, dict) and bing_recovery.get("agent_note"):
                lines.append(f"  bing_recovery: {bing_recovery.get('agent_note')}")
            for sample in item.get("rejected_samples") or []:
                title = _collapse_ws(str(sample.get("title") or ""))[:80]
                domain = str(sample.get("domain") or "")
                url = str(sample.get("url") or "")
                suffix = f" ({domain})" if domain else ""
                link = f" - {url}" if url else ""
                lines.append(f"  rejected_sample: {title}{suffix}{link}")
        elif note and status not in {"ok", "skipped"}:
            lines.append(f"- {backend}: {status} - {note}")

    recovery = trace.get("backend_recovery") or {}
    commands = recovery.get("followup_commands") or []
    if commands:
        lines.extend(["", "## 建议补证"])
        for command in commands[:3]:
            lines.append(f"- `{command}`")
    return lines


def format_search_context(results: list[dict[str, Any]], title: str = "观澜搜索上下文") -> str:
    """Render compact LLM-friendly search context."""
    lines = [f"# {title}", ""]
    diagnostics = _search_context_diagnostics(results)
    if diagnostics:
        lines.extend(diagnostics)
        lines.append("")
    lines.extend(["来源 | 标题 | 摘要 | 可信度 | Topic", "--- | --- | --- | --- | ---"])
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


def _search_context_diagnostics(results: list[dict[str, Any]]) -> list[str]:
    if not results and not getattr(results, "diagnostics", None):
        return []
    trace = (results[0].get("trace") if results else getattr(results, "diagnostics", None)) or {}
    diagnostics = trace.get("backend_diagnostics") or []
    quality_summary = trace.get("quality_summary") or {}
    route_plan = trace.get("route_plan") or {}
    query_shape = trace.get("query_shape") or {}
    site_filter = trace.get("site_filter") or quality_summary.get("site_filter") or {}
    limit_advice = trace.get("agent_limit_advice") or quality_summary.get("agent_limit_advice") or {}
    external_fetch = trace.get("external_fetch_strategy") or quality_summary.get("external_fetch_strategy") or {}
    lines: list[str] = []
    quality_interpretation = str(quality_summary.get("interpretation") or "")
    quality_status = str(quality_summary.get("quality_status") or "")
    user_facing_status = str(quality_summary.get("user_facing_status") or "")
    if quality_status:
        lines.append(f"> 质量状态: `{quality_status}`")
    if user_facing_status:
        lines.append(f"> 当前进展: {user_facing_status}")
    if quality_interpretation:
        lines.append(f"> 质量画像: {quality_interpretation}")
    if isinstance(query_shape, dict) and query_shape.get("rewritten"):
        lines.append(f"> Query 修整: 已自动改写为 `{query_shape.get('backend_query', '')}`")
    if isinstance(query_shape, dict) and query_shape.get("rejected"):
        lines.append(f"> Query 护栏: {query_shape.get('reason', '')}")
    for note in query_shape.get("notes") or []:
        lines.append(f"> Query 说明: {note}")
    if isinstance(limit_advice, dict) and limit_advice.get("enabled"):
        lines.append(f"> 结果池提醒: {limit_advice.get('message')}")
    if isinstance(site_filter, dict) and site_filter.get("enabled"):
        lines.append(
            f"> 站点硬过滤: site={site_filter.get('site')} kept={site_filter.get('kept', 0)} "
            f"removed={site_filter.get('removed', 0)} relaxed={site_filter.get('relaxed', False)}"
        )
    if isinstance(external_fetch, dict) and external_fetch.get("enabled"):
        lines.append(f"> 外部补证策略: {external_fetch.get('agent_instruction')}")
    for reason in quality_summary.get("why_cautious") or []:
        lines.append(f"> 谨慎原因: {reason}")
    workflow_plan = quality_summary.get("agent_workflow_plan") or {}
    if isinstance(workflow_plan, dict) and workflow_plan.get("tier"):
        lines.append(
            f"> 工作流档位: `{workflow_plan.get('tier')}` "
            f"(至少 {workflow_plan.get('minimum_guanlan_tools', 0)} 个 Guanlan 工具)"
        )
    if isinstance(workflow_plan, dict) and workflow_plan.get("summary"):
        lines.append(f"> 工作流说明: {workflow_plan.get('summary')}")
    for tool in workflow_plan.get("tool_sequence") or []:
        lines.append(f"> 工具顺序: {tool}")
    for step in quality_summary.get("guanlan_next_steps") or []:
        lines.append(f"> 观澜补证: {step}")
    execution_policy = quality_summary.get("agent_execution_policy") or {}
    if isinstance(execution_policy, dict) and execution_policy.get("instruction"):
        lines.append(f"> 执行策略: {execution_policy.get('instruction')}")
    actions = quality_summary.get("followup_actions") or quality_summary.get("recommended_actions") or []
    for action in actions:
        if isinstance(action, dict):
            label = str(action.get("label") or "补证动作")
            command = str(action.get("command") or "")
            reason = str(action.get("reason") or "")
            command_part = f" `{command}`" if command else ""
            reason_part = f" - {reason}" if reason else ""
            run_policy = str(action.get("run_policy") or "")
            policy_part = f" [{run_policy}]" if run_policy else ""
            lines.append(f"> 执行动作: {label}{policy_part}{command_part}{reason_part}")
    for rule in quality_summary.get("agent_reporting_contract") or []:
        lines.append(f"> 汇报约束: {rule}")
    entity = _extract_university_entity(str(route_plan.get("query") or ""))
    intents = set(route_plan.get("primary_intents") or []) | set(route_plan.get("secondary_intents") or [])
    if entity and "university_admissions" in intents:
        entity_hits = [
            item
            for item in results
            if entity in _collapse_ws(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('url', '')}")
        ]
        if entity_hits and len(entity_hits) < len(results):
            lines.append(f"> 诊断: 已按目标学校实体 `{entity}` 降噪；优先引用完整命中该实体的页面。")
    for item in diagnostics:
        backend = str(item.get("backend") or "")
        status = str(item.get("status") or "")
        note = str(item.get("note") or "")
        if backend.startswith("direct:") and status == "ok":
            lines.append(f"> 诊断: {note}")
        if backend == "duckduckgo:open_fallback" and status == "ok":
            lines.append("> 诊断: `site:edu.cn` 未产出可用高校结果，已开放补搜，并继续按学校实体和高校信源降噪。")
        if backend == "duckduckgo:site_inferred" and status == "ok":
            site = str(item.get("site") or "")
            site_text = f" `{site}`" if site else ""
            lines.append(f"> 诊断: 已从结果识别学校主域{site_text}，并自动补了一轮站内搜索。")
        elif note and backend in {"duckduckgo:open_fallback", "duckduckgo:site_inferred"} and status != "ok":
            lines.append(f"> 诊断: {note}")
    return _unique_keep_order(lines)


def format_search_trace(results: list[dict[str, Any]]) -> str:
    """Render score and routing trace for search results."""
    lines = ["", "## 搜索 Trace"]
    if not results and not getattr(results, "diagnostics", None):
        lines.append("- 无结果。")
        return "\n".join(lines)
    trace = (results[0].get("trace") if results else getattr(results, "diagnostics", None)) or {}
    query_quality = trace.get("query_quality") or {}
    quality_summary = trace.get("quality_summary") or {}
    route_plan = trace.get("route_plan") or {}
    query_strategy = trace.get("query_strategy") or {}
    backend_diagnostics = trace.get("backend_diagnostics") or []
    backend_summary = trace.get("backend_summary") or {}
    backend_recovery = trace.get("backend_recovery") or {}
    scope_rewrite = trace.get("scope_rewrite") or ""
    query_shape = trace.get("query_shape") or {}
    site_filter = trace.get("site_filter") or quality_summary.get("site_filter") or {}
    time_constraint = trace.get("time_constraint") or quality_summary.get("time_constraint") or {}
    limit_advice = trace.get("agent_limit_advice") or quality_summary.get("agent_limit_advice") or {}
    scope_distinction = trace.get("scope_distinction") or quality_summary.get("scope_distinction") or {}
    external_fetch = trace.get("external_fetch_strategy") or quality_summary.get("external_fetch_strategy") or {}
    if isinstance(query_shape, dict) and query_shape:
        lines.append(
            "- query_shape: "
            f"status={query_shape.get('status', 'ok')} "
            f"short={query_shape.get('short_query', False)} "
            f"overlong={query_shape.get('overlong_query', False)} "
            f"multi_entity={query_shape.get('multi_entity', False)}"
        )
        if query_shape.get("backend_query"):
            lines.append(f"  query_backend: {query_shape.get('backend_query')}")
        if query_shape.get("reason"):
            lines.append(f"  query_reason: {query_shape.get('reason')}")
        for note in query_shape.get("notes") or []:
            lines.append(f"  query_note: {note}")
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
            elif status in _NETWORK_PROBLEM_STATUSES:
                parts.append(f"{backend_name}={status}")
            elif status == _LOW_RELEVANCE_RESULT_STATUS:
                parts.append(f"{backend_name}=low_relevance({count})")
            elif status == _UNSAFE_RESULT_STATUS:
                raw_count = item.get("raw_result_count", count)
                parts.append(f"{backend_name}=unsafe_filtered({raw_count})")
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
            if note and (
                item.get("status")
                in {
                    "parser_miss",
                    "no_results",
                    "no_results_or_parser_miss",
                    _LOW_RELEVANCE_RESULT_STATUS,
                    _UNSAFE_RESULT_STATUS,
                    "blocked",
                    "error",
                    *_NETWORK_PROBLEM_STATUSES,
                }
                or item.get("backend") in {"duckduckgo:open_fallback", "duckduckgo:site_inferred"}
            ):
                lines.append(f"  backend_note:{item.get('backend')} => {note}")
            if item.get("status") == _LOW_RELEVANCE_RESULT_STATUS:
                bing_issue = item.get("bing_issue") or {}
                if isinstance(bing_issue, dict) and bing_issue.get("agent_note"):
                    lines.append(f"  agent_note:{item.get('backend')} => {bing_issue.get('agent_note')}")
                bing_recovery = item.get("bing_cjk_recovery") or {}
                if isinstance(bing_recovery, dict) and bing_recovery.get("agent_note"):
                    lines.append(f"  bing_recovery:{item.get('backend')} => {bing_recovery.get('agent_note')}")
                for sample in item.get("rejected_samples") or []:
                    title = _collapse_ws(str(sample.get("title") or ""))[:80]
                    domain = str(sample.get("domain") or "")
                    suffix = f" ({domain})" if domain else ""
                    lines.append(f"  rejected_sample:{item.get('backend')} => {title}{suffix}")
            for network_attempt in item.get("network_attempts") or []:
                n_status = str(network_attempt.get("status") or "")
                if n_status and n_status != "ok":
                    mode = str(network_attempt.get("network_mode") or "")
                    error = _collapse_ws(str(network_attempt.get("error") or ""))[:100]
                    lines.append(
                        f"  network_attempt:{item.get('backend')}[{mode}] => {n_status}"
                        f"{' / ' + error if error else ''}"
                    )
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
    if scope_rewrite:
        lines.append(f"- scope_rewrite: {scope_rewrite}")
    if isinstance(site_filter, dict) and site_filter.get("enabled"):
        lines.append(
            "- site_filter: "
            f"site={site_filter.get('site')} mode={site_filter.get('mode')} "
            f"kept={site_filter.get('kept', 0)} removed={site_filter.get('removed', 0)} "
            f"relaxed={site_filter.get('relaxed', False)}"
        )
    if isinstance(time_constraint, dict) and time_constraint.get("enabled"):
        lines.append(
            "- time_constraint: "
            f"label={time_constraint.get('label')} strictness={time_constraint.get('strictness')} "
            f"start={time_constraint.get('start_date')} end={time_constraint.get('end_date')}"
        )
    if isinstance(limit_advice, dict) and limit_advice.get("enabled"):
        lines.append(
            "- agent_limit_advice: "
            f"limit={limit_advice.get('limit')} recommended={limit_advice.get('recommended_limit')} "
            f"threshold={limit_advice.get('threshold')}"
        )
    if isinstance(scope_distinction, dict) and scope_distinction.get("enabled"):
        lines.append(
            "- scope_distinction: "
            f"scope={scope_distinction.get('scope')} status={scope_distinction.get('status')} "
            f"preferred_hits={scope_distinction.get('preferred_hit_count', 0)} "
            f"domains={scope_distinction.get('domain_count', 0)}"
        )
        for warning in scope_distinction.get("warnings") or []:
            lines.append(f"  scope_warning: {warning}")
    if isinstance(external_fetch, dict) and external_fetch.get("enabled"):
        lines.append("- external_fetch_strategy: enabled reasons=" + ",".join(external_fetch.get("reasons") or []))
        for url in external_fetch.get("candidate_urls") or []:
            lines.append(f"  webfetch_candidate: {url}")
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
        if quality_summary.get("quality_status"):
            lines.append(f"  quality_status: {quality_summary.get('quality_status')}")
        if quality_summary.get("user_facing_status"):
            lines.append(f"  user_facing_status: {quality_summary.get('user_facing_status')}")
        for reason in quality_summary.get("why_cautious") or []:
            lines.append(f"  why_cautious: {reason}")
        if quality_summary.get("interpretation"):
            lines.append(f"  interpretation: {quality_summary.get('interpretation')}")
        workflow_plan = quality_summary.get("agent_workflow_plan") or {}
        if isinstance(workflow_plan, dict) and workflow_plan.get("tier"):
            lines.append(
                "  workflow_plan: "
                f"tier={workflow_plan.get('tier')} "
                f"minimum_tools={workflow_plan.get('minimum_guanlan_tools', 0)} "
                f"kind={workflow_plan.get('workflow_kind', '')}"
            )
            if workflow_plan.get("summary"):
                lines.append(f"  workflow_summary: {workflow_plan.get('summary')}")
            for tool in workflow_plan.get("tool_sequence") or []:
                lines.append(f"  workflow_tool: {tool}")
        for step in quality_summary.get("guanlan_next_steps") or []:
            lines.append(f"  guanlan_next: {step}")
        execution_policy = quality_summary.get("agent_execution_policy") or {}
        if isinstance(execution_policy, dict):
            lines.append(
                "  execution_policy: "
                f"mode={execution_policy.get('mode', '')} "
                f"should_run={execution_policy.get('should_run_followups', False)} "
                f"instruction={execution_policy.get('instruction', '')}"
            )
        actions = quality_summary.get("followup_actions") or quality_summary.get("recommended_actions") or []
        for action in actions:
            if isinstance(action, dict):
                lines.append(
                    "  action: "
                    f"{action.get('label', '')} => `{action.get('command', '')}` "
                    f"[{action.get('run_policy', '')}] "
                    f"({action.get('reason', '')})"
                )
        for rule in quality_summary.get("agent_reporting_contract") or []:
            lines.append(f"  report_as: {rule}")
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


_UNIVERSITY_ENTITY_TERMS = (
    "大学",
    "高校",
    "学院",
    "院系",
    "清华",
    "北大",
    "北京大学",
    "浙大",
    "浙江大学",
    "复旦",
    "上海交大",
    "上海交通大学",
    "中科大",
    "中国科学技术大学",
    "南京大学",
    "tsinghua",
    "pku",
    "zju",
    "fudan",
    "sjtu",
    "ustc",
    "nju",
)

_UNIVERSITY_TASK_TERMS = (
    "研究生招生",
    "博士招生",
    "硕士招生",
    "招生目录",
    "招生简章",
    "招生专业目录",
    "导师",
    "导师名单",
    "导师介绍",
    "导师情况",
    "研究生院",
    "院系",
    "计算机系",
    "推免",
    "复试",
    "考研",
    "培养方案",
    "faculty",
    "advisor",
    "supervisor",
    "graduate admissions",
)

_ACG_QUERY_TERMS = (
    "漫画",
    "番剧",
    "轻小说",
    "动漫",
    "动画",
    "二次元",
    "魔女",
    "学园",
    "治愈",
    "日常",
    "连载",
    "单行本",
    "manga",
    "anime",
    "comic",
    "light novel",
    "bangumi",
    "pixiv",
    "mangapedia",
    "manba",
)

_UNIVERSITY_STRONG_SIGNAL_TERMS = (
    "招生",
    "导师",
    "院系",
    "研究生",
    "研究生院",
    "推免",
    "复试",
    "考研",
    "faculty",
    "advisor",
    "supervisor",
    "graduate admissions",
)


def _is_university_admissions_query(query: str) -> bool:
    text = _collapse_ws(query).lower()
    if any(term in text for term in _UNIVERSITY_TASK_TERMS if len(term) >= 4):
        return True
    return any(term in text for term in _UNIVERSITY_ENTITY_TERMS) and any(
        term in text for term in ("招生", "导师", "院系", "研究生", "faculty", "advisor", "supervisor")
    )


def _is_acg_entertainment_query(query: str) -> bool:
    text = _collapse_ws(query).lower()
    return _contains_any(text, list(_ACG_QUERY_TERMS))


def _has_strong_university_signal(query: str) -> bool:
    text = _collapse_ws(query).lower()
    return _contains_any(text, list(_UNIVERSITY_STRONG_SIGNAL_TERMS))


def _should_prefer_entertainment_over_university(query: str) -> bool:
    text = _collapse_ws(query).lower()
    return _is_acg_entertainment_query(text) and not _has_strong_university_signal(text)


def _effective_search_scope(query: str, scope: str | None) -> str | None:
    """Route ambiguous academic requests to university official sources when needed."""
    if not scope:
        return scope
    try:
        from guanlan.search_sources import resolve_scope

        resolved = resolve_scope(scope)
    except Exception:
        return scope
    if resolved.id == "academic" and _is_university_admissions_query(query):
        return "university"
    return resolved.id


def _university_search_domains(route_plan: dict[str, Any], fallback_domains: list[str]) -> list[str]:
    """Keep university scope broad for unknown schools and precise for known schools."""
    target_sites = [str(site).strip() for site in route_plan.get("target_sites") or [] if str(site).strip()]
    specific_sites = [site for site in target_sites if site != "edu.cn"]
    if specific_sites:
        return _unique_keep_order(specific_sites[:4] + ["edu.cn"])
    if "edu.cn" in fallback_domains:
        return ["edu.cn"]
    return fallback_domains[:1] or ["edu.cn"]


def _infer_university_site_domains(results: list[SearchResult], query: str) -> list[str]:
    """Infer a named school's root domain from high-confidence university results."""
    entity = _extract_university_entity(query)
    if not entity:
        return []
    domains: list[str] = []
    for item in results:
        domain = _domain(item.url)
        root = _edu_cn_root_domain(domain)
        if not root:
            continue
        title = _collapse_ws(item.title)
        entity_pos = title.find(entity)
        if entity_pos < 0 or entity_pos > 16:
            continue
        if any(term in title for term in ("研究生", "招生", "导师", "学院", "大学")):
            domains.append(root)
    return _unique_keep_order(domains)


def _edu_cn_root_domain(domain: str) -> str:
    normalized = (domain or "").strip().lower().removeprefix("www.")
    if not normalized.endswith(".edu.cn"):
        return ""
    parts = [part for part in normalized.split(".") if part]
    if len(parts) < 3:
        return normalized
    return ".".join(parts[-3:])


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

    priority_order = (
        "cybersecurity",
        "weather_disaster",
        "medical_health",
        "legal_judicial",
        "sports",
        "science",
        "podcast",
        "test_prep",
        "career",
        "global_entertainment",
        "jp_kr_entertainment",
    )
    ordered_candidates = list(priority_order) + [
        key for key in _QUALITY_INTENT_PROFILES if key not in priority_order
    ]
    for candidate in ordered_candidates:
        data = _QUALITY_INTENT_PROFILES[candidate]
        terms = [term for term in data["terms"] if _quality_term_matches(text, str(term))]
        if terms:
            if candidate == "university_admissions" and _should_prefer_entertainment_over_university(text):
                reasons.append(f"skip:{candidate}:acg_disambiguation")
                continue
            intent = candidate
            matched_terms = terms
            reasons.append(f"matched_terms:{','.join(terms[:4])}")
            if candidate == "entertainment" and _is_acg_entertainment_query(text):
                reasons.append("acg_disambiguation:entertainment")
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
    enriched["route_query"] = str(route_plan.get("query") or "")
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
    *,
    limit: int | None = None,
    site_filter: dict[str, Any] | None = None,
    time_constraint: dict[str, Any] | None = None,
    limit_advice: dict[str, Any] | None = None,
    external_fetch_strategy: dict[str, Any] | None = None,
    scope_distinction: dict[str, Any] | None = None,
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
        warnings.append("未命中当前意图偏好的信源类型，需要补充 scope 或站点定向搜索。")
        suggestions.append(_source_gap_suggestion(quality, preferred_types, preferred_scopes))
    if len(source_mix) <= 1 and len(results) >= 4:
        warnings.append("来源类型较单一，可能需要扩大信源面。")
        suggestions.append("补充开放网页或相邻 scope，避免只看单一信源类型。")
    if len(domains) <= 1 and len(results) >= 3:
        warnings.append("域名集中度较高，注意同源转载或单站偏差。")
        suggestions.append("补充 2-3 个不同域名结果，尤其是原文、权威报道和社区样本的交叉来源。")
    limit_advice = limit_advice or _search_limit_advice(limit or len(results))
    if limit_advice.get("enabled"):
        warnings.append(str(limit_advice.get("message") or "当前结果池偏小，严肃研究建议扩大到默认结果池。"))
        suggestions.append(f"补跑 `guanlan search \"问题\" --limit {limit_advice.get('recommended_limit', DEFAULT_SEARCH_LIMIT)} --trace`。")
    site_filter = site_filter or {"enabled": False}
    if site_filter.get("enabled") and site_filter.get("kept", 0) == 0:
        warnings.append(f"`--site {site_filter.get('site', '')}` 硬过滤后没有站内结果；不要放宽成域外结果。")
        suggestions.append("改用站点入口、站内搜索页或 WebFetch 读取候选原文补证。")
    time_constraint = time_constraint or {"enabled": False}
    if time_constraint.get("enabled") and time_constraint.get("strictness") == "strong":
        suggestions.append("显式年份/年份范围是强约束；窗口外材料只能作为背景，不应写成主线证据。")
    scope_distinction = scope_distinction or {"enabled": False}
    if scope_distinction.get("status") == "warn":
        for warning in scope_distinction.get("warnings") or []:
            warnings.append(str(warning))
        suggestions.append("按 query_strategy 的证据角色 query 或相邻 scope 再补一轮，避免垂直路由被开放网页稀释。")
    external_fetch_strategy = external_fetch_strategy or {"enabled": False}
    if external_fetch_strategy.get("enabled"):
        suggestions.append("如 Guanlan 工作流后仍缺关键原文，可按 external_fetch_strategy 调用 WebFetch 补证。")
    role_counts: dict[str, int] = {}
    for item in results:
        role = str(item.get("evidence_role") or "")
        if role:
            role_counts[role] = role_counts.get(role, 0) + 1
    route_roles = [str(role) for role in quality.get("route_evidence_roles") or [] if str(role)]
    missing_roles = [role for role in route_roles if role not in role_counts]
    for role in missing_roles[:3]:
        suggestions.append(_role_gap_suggestion(role))
    status = "warn" if warnings or missing_roles else "pass"
    strong_primary_evidence = _quality_has_strong_primary_evidence(
        results,
        quality=quality,
        preferred_hits=preferred_hits,
        warnings=warnings,
    )
    quality_status = _quality_status(
        results,
        warnings,
        missing_roles,
        strong_primary_evidence=strong_primary_evidence,
    )
    interpretation = _quality_gap_interpretation(status)
    guanlan_next_steps = _quality_gap_next_steps(quality, warnings, missing_roles)
    reporting_contract = _quality_gap_reporting_contract(status)
    why_cautious = _quality_why_cautious(warnings, missing_roles)
    user_facing_status = _quality_user_facing_status(quality_status, why_cautious)
    followup_actions = _quality_followup_actions(quality, warnings, missing_roles, quality_status)
    workflow_plan = _quality_workflow_plan(quality, warnings, missing_roles, quality_status, followup_actions)
    execution_policy = _quality_execution_policy(quality_status, followup_actions, workflow_plan)

    return {
        "status": status,
        "quality_status": quality_status,
        "intent": quality.get("intent", "general"),
        "preferred_hit_count": len(preferred_hits),
        "result_count": len(results),
        "source_type_count": len(source_mix),
        "domain_count": len(domains),
        "source_mix": source_mix,
        "role_counts": dict(sorted(role_counts.items(), key=lambda row: (-row[1], row[0]))),
        "missing_roles": missing_roles,
        "strong_primary_evidence": strong_primary_evidence,
        "warnings": warnings,
        "site_filter": site_filter,
        "time_constraint": time_constraint,
        "agent_limit_advice": limit_advice,
        "scope_distinction": scope_distinction,
        "external_fetch_strategy": external_fetch_strategy,
        "interpretation": interpretation,
        "guanlan_next_steps": guanlan_next_steps,
        "agent_reporting_contract": reporting_contract,
        "user_facing_status": user_facing_status,
        "why_cautious": why_cautious,
        "agent_workflow_plan": workflow_plan,
        "followup_actions": followup_actions,
        "recommended_actions": followup_actions,
        "agent_execution_policy": execution_policy,
        "suggestions": _unique_keep_order([item for item in suggestions if item]),
    }


def _quality_status(
    results: list[dict[str, Any]],
    warnings: list[str],
    missing_roles: list[str],
    *,
    strong_primary_evidence: bool = False,
) -> str:
    if not results:
        return "needs_more_evidence"
    if not warnings and not missing_roles:
        return "ok"
    if strong_primary_evidence and not any("未命中" in warning for warning in warnings):
        return "usable_with_gaps"
    if missing_roles or any("未命中" in warning for warning in warnings):
        return "quality_strict"
    return "needs_more_evidence"


def _quality_has_strong_primary_evidence(
    results: list[dict[str, Any]],
    *,
    quality: dict[str, Any],
    preferred_hits: list[dict[str, Any]],
    warnings: list[str],
) -> bool:
    if not results or not preferred_hits:
        return False
    if any("未命中" in warning for warning in warnings):
        return False
    primary_roles = {
        "official_primary",
        "company_primary",
        "technical_primary",
        "security_advisory",
        "weather_primary",
        "science_primary",
        "university_official",
        "database_official",
        "standard_original",
        "statute_original",
        "clinical_guideline",
        "official_stat",
        "sports_report",
        "official_alert",
        "forecast_track",
        "vulnerability_record",
        "security_advisory",
        "institution_primary",
        "chart_metric",
        "market_quote",
        "company_filing",
        "exchange_announcement",
        "regulatory_notice",
        "macro_data",
        "central_bank_notice",
        "statistics_release",
    }
    strong_source_types = {
        "政府/部委",
        "党央媒",
        "公司一手资料",
        "高校/院系官网",
        "英文官方/监管",
        "网络安全/漏洞/反诈",
        "天气/灾害/预警",
        "科学机构/科研新闻",
        "学术/论文检索",
        "标准/合规",
        "法律/司法",
        "医疗/健康",
        "体育/赛事/转会",
        "财经/公告披露",
        "财经/行情数据",
        "财经/宏观数据",
        "财经/新闻报道",
        "文娱/内容平台",
        "欧美文娱/音乐产业",
        "日韩文娱/K-pop/J-pop",
        "考试/培训/备考",
    }
    preferred_scopes = {str(scope) for scope in quality.get("preferred_scopes") or [] if str(scope)}
    preferred_ratio = len(preferred_hits) / max(len(results), 1)
    role_hit = any(str(item.get("evidence_role") or "") in primary_roles for item in preferred_hits)
    scope_hit = any(str(item.get("matched_scope") or "") in preferred_scopes for item in preferred_hits)
    strong_type_hit = any(
        str(item.get("source_type") or "") in strong_source_types
        or int(item.get("trust_level") or 0) >= 4
        for item in preferred_hits
    )
    return strong_type_hit and (role_hit or scope_hit or preferred_ratio >= 0.5)


def _quality_why_cautious(warnings: list[str], missing_roles: list[str]) -> list[str]:
    reasons: list[str] = []
    for warning in warnings:
        reasons.append(warning)
    for role in missing_roles:
        reasons.append(f"缺少 `{role}` 角色证据。")
    return _unique_keep_order(reasons)


def _quality_user_facing_status(quality_status: str, why_cautious: list[str]) -> str:
    if quality_status == "ok":
        return "Guanlan 已返回可用证据；可以继续综合，但仍应保留来源和时效边界。"
    if quality_status == "usable_with_gaps":
        return "Guanlan 已返回强相关的一手/偏好信源；可以继续使用，但最好读取代表原文并说明仍有证据角色缺口。"
    if quality_status == "quality_strict":
        reason = why_cautious[0] if why_cautious else "当前证据包覆盖不足"
        return f"Guanlan 已找到线索，但质量画像提示还不适合直接下结论：{reason} 接下来直接用 Guanlan 补一轮证据。"
    return "Guanlan 已找到部分线索，但当前证据面还不够稳；接下来直接补不同 scope、站点或研究工作流。"


def _quality_followup_actions(
    quality: dict[str, Any],
    warnings: list[str],
    missing_roles: list[str],
    quality_status: str,
) -> list[dict[str, Any]]:
    if quality_status in {"ok", "usable_with_gaps"}:
        return [
            {
                "label": "读取代表原文",
                "command": "guanlan read \"URL\" --quality-report",
                "reason": "证据包可用时，继续摘读关键原文并核对正文质量。",
                "run_policy": "run_when_deepening_answer",
                "tool": "read",
            }
        ]
    query = _shell_quote_for_command(str(quality.get("route_query") or "问题"))
    intent = str(quality.get("intent") or "general")
    route_intents = [str(item) for item in quality.get("route_intents") or [] if str(item)]
    preferred_scopes = [str(item) for item in quality.get("preferred_scopes") or [] if str(item)]
    actions: list[dict[str, str]] = [
        {
            "label": "查看路由计划",
            "command": f"guanlan route {query} --json",
            "reason": "确认 Guanlan 推荐的 source pools、evidence roles 和 caveats。",
            "run_policy": "run_immediately",
            "tool": "route",
        }
    ]
    preset = _quality_followup_preset(intent, route_intents)
    actions.append(
        {
            "label": "跑深度研究",
            "command": f"guanlan research {query} --preset {preset} --advisor",
            "reason": "让 Guanlan 按证据角色重写 query、合并候选并标出补证缺口。",
            "run_policy": "run_immediately",
            "tool": "research",
        }
    )
    if preferred_scopes:
        actions.append(
            {
                "label": f"补 {preferred_scopes[0]} 信源",
                "command": f"guanlan search {query} --scope {preferred_scopes[0]} --limit 80 --trace",
                "reason": "补当前质量画像偏好的垂直信源池，不要只看开放网页 fallback。",
                "run_policy": "run_immediately",
                "tool": "search",
            }
        )
    if any(role in missing_roles for role in ("fresh_news", "public_discussion")) or "hot_trend" in route_intents:
        actions.append(
            {
                "label": "补最新热度",
                "command": "guanlan hotnews today --limit 80 --trends",
                "reason": "近期/热点问题需要热榜或趋势信号交叉确认。",
                "run_policy": "run_immediately",
                "tool": "hotnews",
            }
        )
    if "tech" in route_intents or intent == "tech":
        actions.append(
            {
                "label": "补 AI/RSS 线索",
                "command": "guanlan feeds curated --category ai --limit 80",
                "reason": "技术/AI 问题需要 RSS/精品内容流作为阅读发现线索。",
                "run_policy": "run_immediately",
                "tool": "feeds",
            }
        )
    if any("域名集中" in warning or "来源类型" in warning for warning in warnings):
        actions.append(
            {
                "label": "扩大信源面",
                "command": f"guanlan dossier {query} --limit 80 --format context",
                "reason": "用 dossier/compare/timeline 这类 Guanlan 工作流扩展证据面，而不是立刻切到通用 web_search。",
                "run_policy": "run_immediately",
                "tool": "dossier",
            }
        )
    return actions[:5]


def _quality_execution_policy(
    quality_status: str,
    followup_actions: list[dict[str, Any]],
    workflow_plan: dict[str, Any],
) -> dict[str, Any]:
    run_now = quality_status not in {"ok", "usable_with_gaps"} and bool(followup_actions)
    minimum_tools = int(workflow_plan.get("minimum_guanlan_tools") or 0)
    tool_sequence = [str(item) for item in workflow_plan.get("tool_sequence") or [] if str(item)]
    tool_text = " -> ".join(tool_sequence[:minimum_tools or len(tool_sequence)])
    return {
        "mode": "run_followups_now" if run_now else "continue_or_read",
        "should_run_followups": run_now,
        "instruction": (
            f"不要停在建议；在预算允许且用户未禁止时，直接完成至少 {minimum_tools} 个最适合的 Guanlan 工具步骤"
            f"（{tool_text or 'search -> read'}），再决定是否需要 fallback。"
            if run_now
            else "证据包已可用；需要深化时直接读取代表原文。"
        ),
        "fallback_rule": "只有 Guanlan followup_actions 执行后仍缺关键证据，才切到通用 web_search/web_fetch。",
        "action_count": len(followup_actions),
    }


def _quality_workflow_plan(
    quality: dict[str, Any],
    warnings: list[str],
    missing_roles: list[str],
    quality_status: str,
    followup_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    intent = str(quality.get("intent") or "general")
    route_intents = {str(item) for item in quality.get("route_intents") or [] if str(item)}
    tools = _unique_keep_order(str(action.get("tool") or "") for action in followup_actions if str(action.get("tool") or ""))
    requires_hotnews = (
        any(role in missing_roles for role in ("fresh_news", "public_discussion"))
        or "hot_trend" in route_intents
    )
    requires_feeds = "tech" in route_intents or intent == "tech"
    requires_breadth = any("域名集中" in warning or "来源类型" in warning for warning in warnings)
    if quality_status in {"ok", "usable_with_gaps"}:
        return {
            "tier": "2-step",
            "minimum_guanlan_tools": 2,
            "planned_tool_count": 2,
            "tool_sequence": ["search", "read"],
            "workflow_kind": "search_then_read",
            "summary": (
                "结果已可用时，先保留搜索证据，再读取代表原文完成核验；"
                "若仍缺角色证据，在回答中说明边界。"
            ),
            "must_finish_before_fallback": False,
        }

    minimum_tools = 3
    workflow_kind = "route_research_scope"
    summary = "默认至少完成 route、research、垂直 search 三步，再判断证据是否够用。"
    if requires_hotnews:
        minimum_tools = 4
        workflow_kind = "route_research_scope_hotnews"
        summary = "涉及实时/热点时，至少完成 route、research、scope search、hotnews 四步交叉补证。"
    elif requires_feeds:
        minimum_tools = 4
        workflow_kind = "route_research_scope_feeds"
        summary = "技术/AI 问题至少完成 route、research、scope search、feeds 四步，补 RSS 发现线索。"
    elif requires_breadth:
        minimum_tools = 4
        workflow_kind = "route_research_scope_breadth"
        summary = "来源过窄时，至少完成 route、research、scope search、dossier 四步扩展证据面。"

    if not tools:
        tools = ["route", "research", "search"]
    return {
        "tier": "4-step" if minimum_tools >= 4 else "3-step",
        "minimum_guanlan_tools": minimum_tools,
        "planned_tool_count": len(tools),
        "tool_sequence": tools,
        "workflow_kind": workflow_kind,
        "summary": summary,
        "must_finish_before_fallback": True,
    }


def _quality_gap_interpretation(status: str) -> str:
    if status != "warn":
        return ""
    return (
        "当前提示是观澜质量画像在提醒“证据包覆盖不足”，不是主题没有资料，也不等于观澜搜索能力失败；"
        "优先继续使用观澜的路由、研究、垂直 scope、feeds/hotnews/read 等能力补证据，再考虑切到通用 web_search/web_fetch。"
    )


def _quality_gap_reporting_contract(status: str) -> list[str]:
    if status != "warn":
        return [
            "可以向使用者说 Guanlan 已返回可用证据；仍需按来源边界引用。",
        ]
    return [
        "不要向 AI 使用者概括为“Guanlan 搜索失败”或“Guanlan 老是失败”。",
        "应表述为“当前 Guanlan 证据包未完全通过质量画像，需要继续补证据/换 scope/跑 research”。",
        "只有所有 Guanlan 后续能力都尝试后仍无可用证据，才说“本轮 Guanlan 未取得足够证据”。",
        "如果只是 Baidu/Bing/DuckDuckGo 某个后端异常，应说“某后端受限/低相关，Guanlan 已给出恢复路线”。",
    ]


def _quality_gap_next_steps(
    quality: dict[str, Any],
    warnings: list[str],
    missing_roles: list[str],
) -> list[str]:
    if not warnings and not missing_roles:
        return []
    intent = str(quality.get("intent") or "general")
    route_intents = [str(item) for item in quality.get("route_intents") or [] if str(item)]
    preferred_scopes = [str(item) for item in quality.get("preferred_scopes") or [] if str(item)]
    steps = [
        "先运行 `guanlan route \"问题\" --json` 看推荐的 source pools、evidence roles 和 caveats。",
    ]
    preset = _quality_followup_preset(intent, route_intents)
    if preset:
        steps.append(f"再运行 `guanlan research \"问题\" --preset {preset} --advisor`，让观澜按证据角色重写 query 并合并候选。")
    if preferred_scopes:
        steps.append(f"补跑 `guanlan search \"问题\" --scope {preferred_scopes[0]} --limit 80 --trace`，不要只看开放网页 fallback。")
    if any(role in missing_roles for role in ("fresh_news", "public_discussion")) or "hot_trend" in route_intents:
        steps.append("涉及近期/热点时补跑 `guanlan hotnews today --limit 80 --trends` 或对应平台热榜。")
    if "tech" in route_intents or intent == "tech":
        steps.append("技术/AI/开发者问题补跑 `guanlan feeds curated --category ai --limit 80`，RSS 是阅读发现线索。")
    if any("域名集中" in warning or "来源类型" in warning for warning in warnings):
        steps.append("用 Guanlan 的 `--scope`、`--site`、`compare/timeline/dossier` 扩大信源面，而不是立刻切到通用 web_search。")
    steps.append("只有 Guanlan 的多轮补证仍缺关键网页时，再用 web_search/web_fetch 作外部兜底，并保留观澜质量提示。")
    return _unique_keep_order(steps)[:5]


def _analyze_search_query_shape(
    query: str,
    *,
    effective_scope: str | None = None,
    quality: dict[str, Any] | None = None,
    route_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality = quality or {}
    route_plan = route_plan or {}
    clean_query = _collapse_ws(query)
    backend_query = clean_query
    notes: list[str] = []
    reasons: list[str] = []
    relevance_terms = _query_relevance_terms(clean_query)
    entities = _query_shape_entities(clean_query)
    is_meaningless = _looks_like_meaningless_query(clean_query)
    if is_meaningless:
        return {
            "status": "rejected",
            "rejected": True,
            "reason": "query 近似乱码或低信息量测试串，继续搜索更可能随机返回噪声页面。",
            "backend_query": "",
            "fallback_open_query": "",
            "relevance_terms": relevance_terms,
            "entities": entities,
            "short_query": len(clean_query) <= 8 or len(relevance_terms) <= 1,
            "overlong_query": len(clean_query) >= 100,
            "multi_entity": len(entities) >= 4,
            "rewritten": False,
            "notes": [],
        }

    if len(clean_query) >= 100:
        compressed = _compress_overlong_query(clean_query, route_plan=route_plan)
        if compressed and compressed != backend_query:
            backend_query = compressed
            notes.append("query 过长，已提炼为更可搜索的关键词串。")
            reasons.append("overlong_query")

    expanded = _expand_search_query(
        backend_query,
        effective_scope=effective_scope,
        quality=quality,
        entities=entities,
    )
    if expanded != backend_query:
        backend_query = expanded
        notes.append("query 偏短、偏歧义或缺少任务约束，已自动补充更贴近意图的词。")
        reasons.append("expanded_query")

    if len(entities) >= 4:
        notes.append("检测到多实体查询；单次搜索只适合先取线索，后续更适合 compare/dossier 分步整理。")
        reasons.append("multi_entity")

    status = "rewritten" if reasons else "ok"
    return {
        "status": status,
        "rejected": False,
        "reason": "",
        "backend_query": backend_query,
        "fallback_open_query": backend_query,
        "relevance_terms": relevance_terms,
        "entities": entities,
        "short_query": len(clean_query) <= 8 or len(relevance_terms) <= 1,
        "overlong_query": len(clean_query) >= 100,
        "multi_entity": len(entities) >= 4,
        "rewritten": bool(reasons),
        "rewrite_reasons": reasons,
        "notes": notes,
    }


def _compress_overlong_query(query: str, *, route_plan: dict[str, Any] | None = None) -> str:
    route_plan = route_plan or {}
    keywords: list[str] = []
    for hint in _LONG_QUERY_KEYPHRASE_HINTS:
        if hint.lower() in query.lower():
            keywords.append(hint)
    keywords.extend(_query_shape_entities(query))
    keywords.extend(_query_relevance_terms(query))
    keep: list[str] = []
    for token in keywords:
        normalized = token.strip()
        if not normalized or normalized in _QUERY_REWRITE_STOPWORDS:
            continue
        keep.append(normalized)
    keep = _unique_keep_order(keep)
    freshness = str(route_plan.get("freshness") or "")
    if freshness and freshness not in keep:
        keep.append(freshness)
    compact = " ".join(keep[:8]).strip()
    if len(compact) < 8:
        compact = query[:96].strip()
    return compact


def _expand_search_query(
    query: str,
    *,
    effective_scope: str | None = None,
    quality: dict[str, Any] | None = None,
    entities: list[str] | None = None,
) -> str:
    quality = quality or {}
    entities = entities or []
    normalized = _collapse_ws(query).strip()
    lowered = normalized.lower()
    additions: list[str] = []
    intent = str(quality.get("intent") or "")
    if normalized == "苹果" and effective_scope in {"ecommerce", "tech_dev", "social_web"}:
        if effective_scope == "ecommerce":
            additions.extend(["iPhone", "手机", "价格", "用户评价"])
        elif effective_scope == "tech_dev":
            additions.extend(["Apple", "iPhone", "芯片", "参数"])
        else:
            additions.extend(["Apple", "iPhone", "知乎", "微博", "评价"])
    if len(normalized) <= 8 or (len(_query_relevance_terms(normalized)) <= 1 and len(normalized) <= 16):
        if any(term in normalized for term in ("人口", "多少")):
            additions.extend(["统计", "数据", "官方"])
        if any(term in normalized for term in ("为什么", "原因")):
            additions.extend(["原因", "调查", "数据", "观点"])
        if effective_scope == "ecommerce":
            additions.extend(["价格", "购买", "评测", "用户评价"])
        elif effective_scope == "tech_dev":
            additions.extend(["官方", "文档", "GitHub"])
        elif effective_scope == "social_web":
            additions.extend(["知乎", "微博", "小红书", "讨论"])
        elif intent == "policy":
            additions.extend(["官方", "原文", "通知"])
        elif intent in {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"} or str(effective_scope or "").startswith("finance"):
            additions.extend(["财报", "公告", "市场"])
        elif intent == "tech":
            additions.extend(["官方", "文档", "benchmark"])
    if len(normalized) <= 40 and len(entities) >= 4 and not any(term in lowered for term in ("对比", "比较", "排名")):
        additions.extend(["对比", "数据"])
    additions = [item for item in _unique_keep_order(additions) if item and item not in normalized]
    if not additions:
        return normalized
    return f"{normalized} {' '.join(additions[:4])}".strip()


def _query_shape_entities(query: str) -> list[str]:
    tokens = re.split(r"[\s,，。；;、/|()（）]+", _collapse_ws(query))
    entities: list[str] = []
    for token in tokens:
        clean = token.strip()
        lower = clean.lower()
        if not clean or lower in _QUERY_REWRITE_STOPWORDS:
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", clean):
            entities.append(clean)
            continue
        if _contains_cjk(clean):
            if 2 <= len(clean) <= 8 and clean not in {"最新", "最近", "刚刚", "今天", "多少", "怎么申请", "为什么"}:
                entities.append(clean)
                continue
        elif re.search(r"[A-Za-z]", clean) and 2 <= len(clean) <= 20:
            entities.append(clean)
    return _unique_keep_order(entities)


def _looks_like_meaningless_query(query: str) -> bool:
    text = _collapse_ws(query).strip()
    if not text or _contains_cjk(text) or " " in text:
        return False
    lowered = text.lower()
    if any(term in lowered for term in _MEANINGLESS_QUERY_ALLOWLIST):
        return False
    if not re.fullmatch(r"[a-z0-9_-]{10,}", lowered):
        return False
    letters = [char for char in lowered if "a" <= char <= "z"]
    digits = [char for char in lowered if char.isdigit()]
    vowel_count = sum(1 for char in letters if char in "aeiou")
    vowel_ratio = vowel_count / max(len(letters), 1)
    keyboard_run = any(run in lowered for run in _QUERY_KEYBOARD_RUNS)
    return bool(keyboard_run or (digits and vowel_ratio < 0.2))


def _quality_followup_preset(intent: str, route_intents: list[str]) -> str:
    candidates = [intent, *route_intents]
    mapping = {
        "policy": "policy",
        "official_position": "official",
        "local": "local",
        "industry": "industry",
        "global_industry": "global_industry",
        "finance": "finance",
        "finance_quote": "finance",
        "finance_disclosure": "finance",
        "finance_macro": "finance",
        "finance_sentiment": "finance",
        "finance_research": "finance",
        "tech": "tech",
        "academic": "academic",
        "university_admissions": "university",
        "reputation": "reputation",
        "purchase_advice": "reputation",
        "global_reputation": "global_reputation",
        "entertainment": "entertainment",
        "global_entertainment": "global_entertainment",
        "jp_kr_entertainment": "jp_kr_entertainment",
        "company_primary": "company",
        "sports": "sports",
        "weather_disaster": "weather_disaster",
        "cybersecurity": "cybersecurity",
        "science": "science",
        "career": "career",
        "podcast": "podcast",
        "test_prep": "test_prep",
    }
    for candidate in candidates:
        clean = str(candidate).split(":", 1)[-1]
        if clean in mapping:
            return mapping[clean]
    return "general"


def _source_gap_suggestion(
    quality: dict[str, Any],
    preferred_types: set[str],
    preferred_scopes: set[str],
) -> str:
    if preferred_scopes:
        scope_hint = ",".join(sorted(preferred_scopes))
        return f"直接补搜 `--scope {scope_hint.split(',')[0]}` 或指定相关官方/垂类站点。"
    if preferred_types:
        return "直接补充 " + "、".join(sorted(preferred_types)[:3]) + " 类型信源。"
    intent = str(quality.get("intent") or "general")
    return f"按 {intent} 意图直接补充更贴近问题的第一手信源。"


def _role_gap_suggestion(role: str) -> str:
    mapping = {
        "official_primary": "缺少官方原文/主管部门口径，直接补搜 `--scope gov`、`--scope party_central` 或 `--scope global_official`。",
        "authoritative_report": "缺少权威报道，直接补搜党央媒或核心地方官媒。",
        "user_sample": "缺少公开用户样本，直接补搜知乎、微博、小红书、B站等公开页，并标明样本偏差。",
        "industry_report": "缺少产业/垂类材料，直接补搜商业媒体、电商垂类或行业报告。",
        "fresh_news": "缺少近期材料，直接加入最近/今日/本周等时效词并开启 trace 核对时间线。",
        "developer_discussion": "缺少开发者实践反馈，直接补搜 GitHub、V2EX、掘金或技术社区。",
        "company_primary": "缺少公司一手资料，直接补搜 `--scope company_primary` 或官方文档/价格/发布说明。",
        "technical_primary": "缺少技术一手资料，直接补搜 `--scope developer`、官方文档、GitHub release 或 issue。",
        "review": "缺少评价样本，直接补搜 Reddit、Hacker News、G2、Trustpilot 等公开样本并说明偏差。",
        "university_official": "缺少高校/院系官网材料，直接补搜 `--scope university` 或指定学校/院系站点。",
        "department_page": "缺少院系官网页面，直接补搜 `--scope university` 或指定院系域名。",
        "faculty_profile": "缺少导师主页/教师列表，直接补搜院系官网的导师、教师、师资队伍页面。",
        "admission_catalog": "缺少招生目录/招生简章，直接补搜研究生招生网或学校研招办页面。",
        "standard_original": "缺少标准原文/标准组织材料，直接补搜 `--scope global_official` 或指定 ISO/IEC/NIST 等站点。",
        "regulator_guidance": "缺少监管解释或主管机构材料，直接补搜 `--scope gov` 或 `--scope global_official`。",
        "clinical_guideline": "缺少临床指南/专业机构材料，直接补搜 WHO、CDC、FDA、卫健委或学术数据库。",
        "statute_original": "缺少法律条文原文，直接补搜 `--scope gov` 或指定人大、法院、司法部等站点。",
        "case_record": "缺少案例/裁判文书材料，直接补搜法院、裁判文书或权威法律数据库。",
        "market_quote": "缺少行情/指数数据入口，直接补搜 `--scope finance_quote`，并标注行情时间和可能延迟。",
        "company_filing": "缺少公告/财报/披露原文，直接补搜 `--scope finance_disclosure` 或指定巨潮、交易所、SEC。",
        "exchange_announcement": "缺少交易所公告入口，直接补搜 `--scope finance_disclosure` 或指定上交所/深交所/HKEXnews。",
        "regulatory_notice": "缺少监管函、问询、处罚或风险提示，直接补搜 `--scope finance_disclosure` 和监管机构站点。",
        "macro_data": "缺少宏观官方数据，直接补搜 `--scope finance_macro` 或指定统计局、央行、FRED。",
        "central_bank_notice": "缺少央行/货币政策口径，直接补搜 `--scope finance_macro` 或指定央行站点。",
        "sentiment_sample": "缺少投资者情绪样本，直接补搜 `--scope finance_sentiment`，但只能作为样本线索。",
        "analyst_opinion": "缺少研报/机构观点，直接补搜 `--scope finance_research`，并和公告财报交叉验证。",
        "market_news": "缺少财经新闻时间线，直接补搜 `--scope finance_news` 或财联社、证券时报、第一财经等站点。",
    }
    return mapping.get(role, f"缺少 `{role}` 角色证据，直接补充对应信源后再下判断。")


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
        explicit_year = _explicit_year_recency(text, today)
        if explicit_year:
            return explicit_year

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
        years = sorted({int(match) for match in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)})
        bounded_years = [year for year in years if 1990 <= year <= today.year + 1]
        if bounded_years:
            start_year = min(bounded_years)
            end_year = max(bounded_years)
            start = dt.date(start_year, 1, 1)
            end = dt.date(end_year, 12, 31)
            if end > today:
                end = today
            window_days = max((end - start).days + 1, 1)
            return {
                "enabled": True,
                "label": "year_range" if len(bounded_years) > 1 else "year",
                "window_days": window_days,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "matched_terms": [str(year) for year in bounded_years],
            }

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


def _explicit_year_recency(text: str, today: dt.date) -> dict[str, Any] | None:
    years = sorted({int(match) for match in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)})
    bounded_years = [year for year in years if 1990 <= year <= today.year + 1]
    if not bounded_years:
        return None
    start_year = min(bounded_years)
    end_year = max(bounded_years)
    start = dt.date(start_year, 1, 1)
    end = dt.date(end_year, 12, 31)
    if end > today:
        end = today
    window_days = max((end - start).days + 1, 1)
    return {
        "enabled": True,
        "label": "year_range" if len(bounded_years) > 1 else "year",
        "window_days": window_days,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "matched_terms": [str(year) for year in bounded_years],
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
    query_shape = _analyze_search_query_shape(
        clean_query,
        effective_scope=str(quality.get("requested_scope") or "") or None,
        quality=quality,
        route_plan=route_plan,
    )

    def add(role: str, q: str, reason: str) -> None:
        normalized = _collapse_ws(q)
        if not normalized:
            return
        if any(item["query"] == normalized for item in variants):
            return
        variants.append({"role": role, "query": normalized, "reason": reason})

    add("base", clean_query, "用户原始问题，保留语义中心")
    if query_shape.get("rewritten") and query_shape.get("backend_query"):
        add("query_rewrite", str(query_shape.get("backend_query")), "对过短、过长、歧义或多实体 query 先做搜索友好的重写")
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
    if "ecommerce" in intents or str(quality.get("requested_scope") or "") == "ecommerce":
        add("industry_report", f"{clean_query} 电商 零售 行业 数据 案例", "电商问题先看垂类媒体和行业材料")
        add("review", f"{clean_query} 价格 售后 投诉 用户评价 值不值得买", "补购买决策、售后和用户样本")
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
    requested_scope = str(quality.get("requested_scope") or "")
    if finance_intents & set(intents) or requested_scope.startswith("finance"):
        if "finance_quote" in intents or requested_scope == "finance_quote":
            add("market_quote", f"{clean_query} 行情 股价 涨跌幅 指数 东方财富 新浪财经", "行情问题先找可核验的市场数据入口并标注时间/延迟")
        if "finance_disclosure" in intents or "finance" in intents or requested_scope in {"finance", "finance_disclosure", "finance_company"}:
            add("company_filing", f"{clean_query} 巨潮资讯 交易所 公告 财报", "公司/股票问题先找公告、财报和交易所披露")
            add("regulatory_notice", f"{clean_query} 监管 问询函 处罚 风险提示", "补监管函、问询、处罚和风险披露")
        if "finance_macro" in intents or requested_scope == "finance_macro":
            add("macro_data", f"{clean_query} 央行 统计局 官方 数据", "宏观金融问题先找官方统计和央行口径")
            add("market_expectation", f"{clean_query} FedWatch 利率 预期 市场定价", "市场预期应和政策决定分开")
        if "finance_research" in intents or requested_scope == "finance_research":
            add("analyst_opinion", f"{clean_query} 研报 券商 评级 估值", "研报和评级属于观点层，不能替代披露")
        if "finance_sentiment" in intents or requested_scope == "finance_sentiment":
            add("sentiment_sample", f"{clean_query} 雪球 股吧 热议 情绪", "公开讨论只作情绪样本，不作事实主证据")
        add("market_news", f"{clean_query} 财经 快讯 新闻 事件", "补财经新闻时间线和事件背景")
    elif {"industry"} & set(intents):
        add("industry_report", f"{clean_query} 行业 趋势 公司 案例", "产业/商业问题补行业材料")
    if "global_industry" in intents:
        add("industry_report", f"{clean_query} market analysis competitive landscape analyst report", "英文产业问题补分析和市场结构材料")
        add("company_context", f"{clean_query} investor relations annual report official", "补公司一手资料和投资者关系材料")
    if "tech" in intents:
        add("technical_primary", f"{clean_query} docs release notes changelog API SDK", "技术问题先找官方文档、发布说明和可复现材料")
        add("developer_discussion", f"{clean_query} github issue benchmark 开源", "技术问题补开发者与可复现线索")
    if "sports" in intents:
        add("official_stat", f"{clean_query} official scoreboard schedule standings", "体育实时问题优先找官方比分、赛程和榜单入口")
        add("sports_report", f"{clean_query} ESPN NBA official scores playoffs schedule", "补可信体育媒体的战报、专题页和实时比分")
    if "university_admissions" in intents:
        add("university_official", f"{clean_query} 官网 研究生招生 导师 招生目录", "高校招生/导师问题先找学校和招生官网")
        add("department_page", f"{clean_query} 院系 导师 研究方向", "补院系官网和导师主页")
        add("admission_catalog", f"{clean_query} 研究生院 招生简章 招生目录 复试 推免", "补招生目录、简章和历史通知")
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
    if query_shape.get("multi_entity"):
        entity_terms = [str(item) for item in query_shape.get("entities") or [] if str(item)]
        add("entity_compare", f"{' '.join(entity_terms[:4])} 对比 {clean_query}", "多实体问题先显式保留比较意图和前几个关键实体")
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
        "query_shape": query_shape,
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
    result_date = metrics.get("result_date")
    result_date_text = result_date.isoformat() if isinstance(result_date, dt.date) else ""
    freshness_confidence = _result_freshness_confidence(metrics)
    stale_risk = _result_stale_risk(metrics)
    if not metrics["enabled"]:
        return {
            "enabled": False,
            "result_date": result_date_text,
            "date_source": metrics.get("date_source", ""),
            "age_days": metrics.get("age_days"),
            "freshness_confidence": freshness_confidence,
            "stale_risk": stale_risk,
        }
    return {
        "enabled": True,
        "window_days": metrics["window_days"],
        "start_date": metrics["start_date"],
        "end_date": metrics["end_date"],
        "matched_terms": metrics["matched_terms"],
        "result_date": result_date_text,
        "date_source": metrics.get("date_source", ""),
        "age_days": metrics.get("age_days"),
        "in_window": metrics["in_window"],
        "freshness_confidence": freshness_confidence,
        "stale_risk": stale_risk,
    }


def _result_freshness_confidence(metrics: dict[str, Any]) -> str:
    if not metrics.get("result_date"):
        return "unknown"
    age_days = metrics.get("age_days")
    if age_days is None:
        return "unknown"
    if metrics.get("enabled"):
        return "high" if metrics.get("in_window") else "stale"
    if age_days <= 14:
        return "high"
    if age_days <= 120:
        return "medium"
    return "low"


def _result_stale_risk(metrics: dict[str, Any]) -> str:
    age_days = metrics.get("age_days")
    if metrics.get("enabled"):
        if metrics.get("in_window"):
            return "low"
        return "medium" if metrics.get("result_date") else "high"
    if age_days is None:
        return "unknown"
    if age_days > 365:
        return "high"
    if age_days > 120:
        return "medium"
    return "low"


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
    role_hint = str((item.trace or {}).get("evidence_role_hint") or "")
    if role_hint:
        return role_hint
    if scope == "university" or roles & {"faculty_profile", "admission_catalog", "department_page", "official_notice"}:
        if "faculty_profile" in roles:
            return "faculty_profile"
        if "admission_catalog" in roles:
            return "admission_catalog"
        return "university_official"
    if scope == "sports" or roles & {"official_stat", "sports_report", "transfer_report", "fan_discussion"}:
        if "official_stat" in route_roles or re.search(r"比分|赛果|赛程|战绩|积分榜|score|scores|scoreboard|schedule|standings|bracket", title_blob):
            return "official_stat"
        if "transfer_report" in route_roles or re.search(r"转会|合同|续约|transfer|contract", title_blob):
            return "transfer_report"
        return "sports_report"
    finance_scopes = {"finance", "finance_quote", "finance_company", "finance_disclosure", "finance_news", "finance_macro", "finance_sentiment", "finance_research"}
    finance_roles = {
        "market_quote",
        "index_data",
        "fund_quote",
        "company_filing",
        "exchange_announcement",
        "annual_report",
        "financial_statement",
        "regulatory_notice",
        "risk_disclosure",
        "macro_data",
        "central_bank_notice",
        "statistics_release",
        "market_expectation",
        "sentiment_sample",
        "analyst_opinion",
        "market_news",
    }
    if scope in finance_scopes or roles & finance_roles or "finance" in fit_tags:
        if roles & {"market_quote", "index_data", "fund_quote"} or re.search(r"行情|股价|涨跌|指数|quote|market activity", title_blob):
            return "market_quote"
        if roles & {"company_filing", "annual_report", "financial_statement"} or re.search(r"公告|财报|年报|季报|披露|10-k|10-q|filing", title_blob):
            return "company_filing"
        if roles & {"exchange_announcement", "regulatory_notice", "risk_disclosure"} or re.search(r"监管|问询|处罚|风险提示|交易所", title_blob):
            return "regulatory_notice"
        if roles & {"macro_data", "central_bank_notice", "statistics_release"} or re.search(r"央行|统计局|gdp|cpi|ppi|社融|m2|利率|汇率|外储", title_blob):
            return "macro_data"
        if roles & {"market_expectation"}:
            return "market_expectation"
        if roles & {"sentiment_sample"} or re.search(r"雪球|股吧|热议|情绪|看多|看空", title_blob):
            return "sentiment_sample"
        if roles & {"analyst_opinion"} or re.search(r"研报|券商|评级|目标价|估值|分析师", title_blob):
            return "analyst_opinion"
        return "market_news"
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
    result_date, date_source = _extract_result_date_with_source(item, today=today)
    age_days = (today - result_date).days if result_date else None
    start = _safe_iso_date(start_date)
    end = _safe_iso_date(str(recency.get("end_date") or today.isoformat())) or today
    if result_date and start:
        in_window = start <= result_date <= end
    else:
        in_window = bool(result_date and age_days is not None and 0 <= age_days <= max(window_days, 0))
    return {
        "enabled": enabled,
        "window_days": window_days,
        "start_date": start_date,
        "end_date": end.isoformat(),
        "matched_terms": list(recency.get("matched_terms") or []),
        "result_date": result_date,
        "date_source": date_source,
        "age_days": age_days,
        "in_window": in_window,
        "has_freshness_words": _has_freshness_words(item),
    }


def _extract_result_date_with_source(item: SearchResult, today: dt.date | None = None) -> tuple[dt.date | None, str]:
    today = today or dt.date.today()
    text = _collapse_ws(f"{item.title} {item.snippet}")
    if text:
        relative = _extract_relative_result_date(text, today)
        if relative:
            return relative, "title_or_snippet"

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
                return parsed, "title_or_snippet"

        match = re.search(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
        if match:
            parsed = _safe_date(today.year, int(match.group(1)), int(match.group(2)))
            if parsed and parsed > today + dt.timedelta(days=7):
                parsed = _safe_date(today.year - 1, int(match.group(1)), int(match.group(2)))
            if parsed:
                return parsed, "title_or_snippet"

        year_match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)
        if year_match:
            parsed = _safe_date(int(year_match.group(1)), 1, 1)
            if parsed:
                return parsed, "year_mention"

    url = str(item.url or "")
    url_patterns = (
        r"/((?:19|20)\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)",
        r"((?:19|20)\d{2})[-_/](\d{1,2})[-_/](\d{1,2})",
    )
    for pattern in url_patterns:
        match = re.search(pattern, url)
        if not match:
            continue
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed:
            return parsed, "url"
    year_match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", url)
    if year_match:
        parsed = _safe_date(int(year_match.group(1)), 1, 1)
        if parsed:
            return parsed, "url_year"
    return None, ""


def _extract_result_date(item: SearchResult, today: dt.date | None = None) -> dt.date | None:
    parsed, _ = _extract_result_date_with_source(item, today=today)
    return parsed


def _extract_relative_result_date(text: str, today: dt.date) -> dt.date | None:
    if any(marker in text for marker in ("刚刚", "今天", "今日", "分钟前", "小时前")):
        return today
    if "昨天" in text:
        return today - dt.timedelta(days=1)
    if "前天" in text:
        return today - dt.timedelta(days=2)

    day_match = re.search(r"(\d+)\s*(?:天|日)\s*前", text)
    if day_match:
        days = min(int(day_match.group(1)), 36500)
        return today - dt.timedelta(days=days)
    week_match = re.search(r"(\d+)\s*(?:周|星期|礼拜)\s*前", text)
    if week_match:
        weeks = min(int(week_match.group(1)), 5200)
        return today - dt.timedelta(days=weeks * 7)
    month_match = re.search(r"(\d+)\s*(?:个)?月\s*前", text)
    if month_match:
        months = min(int(month_match.group(1)), 1200)
        return today - dt.timedelta(days=months * 30)
    year_match = re.search(r"(\d+)\s*年\s*前", text)
    if year_match:
        years = int(year_match.group(1))
        if years > 100:
            return None
        return today - dt.timedelta(days=years * 365)
    return None


def _safe_date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _safe_iso_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
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


def _result_mentions_time_terms(item: SearchResult, recency: dict[str, Any]) -> bool:
    text = _collapse_ws(f"{item.title} {item.snippet} {item.url}")
    terms = [str(term) for term in recency.get("matched_terms") or [] if str(term)]
    return any(re.search(rf"(?<!\d){re.escape(term)}(?!\d)", text) for term in terms)


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
        "time_constraint_fit": 0.0,
        "time_constraint_penalty": 0.0,
        "ad_penalty": 0.0,
        "intent_mismatch_penalty": 0.0,
        "language_mismatch_penalty": 0.0,
        "source_risk_penalty": 0.0,
        "entity_match": 0.0,
        "entity_mismatch_penalty": 0.0,
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
    finance_intents = {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment", "finance_research"}
    if route_intents & {"policy", "official_position", "local", "global_policy", "company_primary", *finance_intents}:
        parts["authority_fit"] = authority_score * 0.45
    if route_intents & {"tech", "cybersecurity"} and (
        {"documentation", "source_code", "release", "official_specs", "security_advisory", "vendor_patch"} & content_roles
    ):
        parts["authority_fit"] = max(parts["authority_fit"], authority_score * 0.42)
    if route_intents & {"reputation", "global_reputation", "purchase_advice", "tech"}:
        parts["sample_fit"] = sample_value * 0.42
    if route_intents & {"hot_trend"} or (recency and recency.get("enabled")):
        parts["freshness_fit"] = freshness_value * 0.32
    if route_roles and (route_roles & (fit_tags | content_roles)):
        parts["intent_fit"] += 0.18
    if risk_tags & {"soft_article", "sponsored_content", "seo_content", "commercial_content"}:
        parts["source_risk_penalty"] -= 0.18
    if risk_tags & {"sample_bias", "not_representative"} and route_intents & {"policy", "global_policy", *finance_intents}:
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
    if route_intents & {"tech", "cybersecurity"} and source_card.get("authority_role") in {"company_primary", "developer_source", "code_host"}:
        parts["intent_fit"] += 0.18
    if _is_chinese_context_query(query, quality) and _result_lacks_chinese_context(item):
        parts["language_mismatch_penalty"] = -0.75
    university_entity = _extract_university_entity(query)
    if "university_admissions" in route_intents and university_entity:
        if _result_mentions_entity(item, university_entity):
            parts["entity_match"] = 1.05
        else:
            if _is_affiliated_college_entity(university_entity) and _result_mentions_entity(item, _parent_university_entity(university_entity)):
                parts["entity_mismatch_penalty"] = -2.2
            else:
                parts["entity_mismatch_penalty"] = -1.25
    if _is_low_relevance_ai_noise(item, query):
        parts["semantic_noise_penalty"] = -1.4
    if _is_low_relevance_academic_noise(item, query, quality):
        parts["semantic_noise_penalty"] = min(parts["semantic_noise_penalty"], -2.0)
    if recency and recency.get("enabled"):
        metrics = _result_recency_metrics(item, recency)
        strict_time = str(recency.get("label") or "") in {"year", "year_range"}
        if strict_time:
            if metrics["result_date"] and metrics.get("in_window"):
                parts["time_constraint_fit"] = 1.25
            elif _result_mentions_time_terms(item, recency):
                parts["time_constraint_fit"] = 0.65
            elif metrics["result_date"]:
                parts["time_constraint_penalty"] = -2.4
            else:
                parts["time_constraint_penalty"] = -0.35
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


_DEPARTMENT_LIKE_UNIVERSITY_ENTITY_TERMS = (
    "计算机学院",
    "软件学院",
    "信息学院",
    "人工智能学院",
    "电子信息学院",
    "通信学院",
    "网络空间安全学院",
    "研究生院",
)


def _extract_university_entity(query: str) -> str:
    """Extract the named school entity from Chinese university/admission queries."""
    text = _collapse_ws(query)
    for token in re.split(r"\s+", text):
        candidate = token.strip(" ，,。；;:：()（）\"'")
        if candidate.endswith("大学") and len(candidate) >= 4:
            return candidate
        if candidate.endswith("学院") and len(candidate) >= 5 and candidate not in _DEPARTMENT_LIKE_UNIVERSITY_ENTITY_TERMS:
            return candidate
    for match in re.finditer(r"([\u4e00-\u9fff]{2,12}大学)", text):
        return match.group(1)
    for match in re.finditer(r"([\u4e00-\u9fff]{2,12}学院)", text):
        candidate = match.group(1)
        if candidate not in _DEPARTMENT_LIKE_UNIVERSITY_ENTITY_TERMS:
            return candidate
    return ""


def _result_mentions_entity(item: SearchResult, entity: str) -> bool:
    if not entity:
        return True
    text = _collapse_ws(f"{item.title} {item.snippet} {item.url}")
    return entity in text


def _is_affiliated_college_entity(entity: str) -> bool:
    return bool(entity and entity.endswith("学院") and "大学" in entity)


def _parent_university_entity(entity: str) -> str:
    if "大学" not in entity:
        return ""
    return entity.split("大学", 1)[0] + "大学"


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
    if _url_path_is_weak_identity(url):
        identity = _url_identity_parts(url)
        parts = [domain, identity.get("path", ""), identity.get("compact", ""), identity.get("tail", "")]
        return " ".join(_unique_keep_order([part for part in parts if part]))[:120]
    if stem:
        return stem[:120]
    return domain or url


def _url_identity_parts(url: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(parsed.path or "").strip("/")
    stem = re.sub(r"\.[a-zA-Z0-9]{1,8}$", "", path)
    tokens = [token for token in re.split(r"[/_\-+]+", stem) if token]
    numeric_tokens = [token for token in tokens if token.isdigit()]
    return {
        "path": path,
        "stem": stem,
        "compact": "".join(numeric_tokens),
        "tail": numeric_tokens[-1] if numeric_tokens else "",
    }


def _url_path_is_weak_identity(url: str) -> bool:
    identity = _url_identity_parts(url)
    stem = identity.get("stem", "")
    if not stem:
        return False
    tokens = [token for token in re.split(r"[/_\-+]+", stem) if token]
    return bool(tokens) and all(token.isdigit() for token in tokens)


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
