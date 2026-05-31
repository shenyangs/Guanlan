# -*- coding: utf-8 -*-
"""Explicit support constants and helpers for Guanlan search-quality logic."""

from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any

from guanlan.limits import DEFAULT_SEARCH_LIMIT
from guanlan.search_quality import query_relevance_terms as _query_relevance_terms
from guanlan.wps_semantics import WPS_OFFICE_TERMS, wps_office_subroute

_RECENCY_DEFAULT_WINDOW_DAYS = 30
_QUERY_REWRITE_STOPWORDS = {
    "怎么", "如何", "以及", "还有", "一下", "这个", "那个", "相关", "情况",
    "问题", "最新", "最近", "今天", "刚刚", "请问",
}
_MEANINGLESS_QUERY_ALLOWLIST = {
    "gpt", "gpt4", "gpt-4", "gpt5", "gpt-5", "openai", "claude", "gemini",
    "qwen", "glm", "cve", "react", "vue", "nextjs", "next.js", "python", "java",
    "golang", "typescript", "javascript", "cpp", "c++", "ios", "android",
}
_QUERY_KEYBOARD_RUNS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_LONG_QUERY_KEYPHRASE_HINTS = (
    "具身智能", "人形机器人", "机器人", "人工智能", "融资", "产品", "商业化",
    "政策", "供应链", "订单", "客户", "趋势", "GDP", "人口", "股价", "天气",
)
_ROBOTICS_AI_TERMS = (
    "具身智能", "具身", "人形机器人", "机器人", "智元", "宇树", "傅利叶",
    "银河通用", "逐际动力", "灵巧手", "双足", "sim2real", "端到端",
    "触觉感知", "embodied ai", "humanoid robot", "humanoid", "robotics",
)
_WPS_OFFICE_TERMS = tuple(WPS_OFFICE_TERMS)


def _wps_office_subroute(query: str) -> str:
    return wps_office_subroute(query)


_QUALITY_INTENT_PROFILES: dict[str, dict[str, Any]] = {
    "policy": {
        "name": "政策/官方口径",
        "terms": (
            "政策", "监管", "法规", "通知", "意见", "办法", "国务院", "部委", "主管部门", "官方", "解读",
            "非遗", "非物质文化遗产", "非遺", "制香", "数字素养", "全民数字素养", "教师职称",
            "职称评审", "课题申报", "数据安全法", "个人信息保护法", "爬虫合规",
        ),
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
            "uk eu trade",
            "brexit reset",
            "starmer",
            "reform uk",
            "immigration bill",
            "反倾销",
            "anti-dumping",
            "antidumping",
            "反补贴",
            "anti-subsidy",
            "countervailing",
            "军事演习",
            "军事部署",
            "西南诸岛",
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
            "prompt injection",
            "indirect prompt injection",
            "tool calling attack",
            "agent security",
            "mcp attack",
            "malicious skill",
            "postgresql",
            "postgres",
            "security update",
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
        "terms": ("法律", "诉讼", "判决", "合同", "律师", "侵权", "司法解释", "法院", "裁判文书", "条例", "房产纠纷", "婚前财产", "财产纠纷", "房产加名", "纠纷", "工伤", "竞业", "劳动争议", "版权", "著作权", "维权", "投诉", "数据安全法", "个人信息保护法", "爬虫", "反爬", "法律风险", "license", "agpl", "law", "legal", "court", "lawsuit"),
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
            "volcengine",
            "character.ai",
            "peloton",
            "notion ai",
            "notion",
            "calm",
            "replika",
            "lovot",
            "groove-x",
            "coze",
            "扣子",
            "node.js",
            "nodejs",
        ),
        "preferred_scopes": ("company_primary", "developer"),
        "preferred_source_types": ("公司一手资料", "英文开发者/开源"),
        "caution_source_types": ("英文社区样本", "评价/消费样本"),
        "guidance": "优先公司官网、文档、发布说明、状态页和投资者关系材料，再补社区/媒体样本。",
    },
    "wps_office": {
        "name": "金山办公/WPS 与 AI Office",
        "terms": _WPS_OFFICE_TERMS,
        "preferred_scopes": ("wps_office", "business", "tech_dev", "company_primary", "cybersecurity", "social_web"),
        "preferred_source_types": ("办公软件/AI Office/SaaS", "商业/产业媒体", "科技/开发者社区", "公司一手资料", "网络安全/漏洞/反诈", "社交/内容平台"),
        "caution_source_types": ("通用网页",),
        "guidance": "以 WPS/金山办公为锚点，放大到办公 AI、PPT/文档协作、SaaS、信创、安全、竞品和用户样本；品牌通稿、单条社媒和工具榜单不能作主证据。",
    },
    "local": {
        "name": "地方政策/区域研究",
        "terms": ("地方", "城市", "区域", "省", "市", "区县", "产业园", "广东", "上海", "北京", "深圳", "杭州", "成都", "珠海", "横琴", "伊春", "新疆", "伊犁", "brunch", "咖啡店", "咖啡馆", "书店", "发呆", "独库公路", "伊昭公路"),
        "preferred_scopes": ("local_official", "gov", "party_central"),
        "preferred_source_types": ("地方官媒", "政府/部委", "党央媒"),
        "caution_source_types": (),
        "guidance": "优先地方官媒、地方政府和中央口径交叉核验。",
    },
    "ecommerce": {
        "name": "电商/零售/跨境",
        "terms": ("电商", "零售", "跨境", "出海", "品牌", "渠道", "供应链", "产业带", "平台", "新消费", "抖音小店", "小店", "团购", "抖音团购", "真实商家", "实体店", "加盟", "本地生活", "餐馆", "茶饮", "闲鱼", "闲鱼规则", "技术服务", "直通车", "shopify", "woocommerce", "独立站", "食材成本", "配菜", "海带苗", "鸡枞菌", "姜饼瓜"),
        "preferred_scopes": ("ecommerce", "business"),
        "preferred_source_types": ("电商/零售垂类", "商业/产业媒体"),
        "caution_source_types": (),
        "guidance": "优先垂类媒体和产业媒体，注意区分新闻、观点和软文。",
    },
    "career": {
        "name": "招聘/薪资/面经",
        "terms": ("招聘", "求职", "岗位", "薪资", "面试", "简历", "校招", "社招", "面经", "offer", "hc", "算法工程师", "产品经理", "职业定位", "核心竞争力", "个人商业模式画布", "个人说明书", "working with me", "finops", "云成本工程师", "interview loop", "salary", "levels", "glassdoor"),
        "preferred_scopes": ("career", "social_web", "business"),
        "preferred_source_types": ("招聘/职场/薪资", "社交/内容平台", "商业/产业媒体"),
        "caution_source_types": ("通用网页",),
        "guidance": "优先岗位/公司官方信息、薪资样本、面经和招聘市场报告，并标注样本偏差。",
    },
    "reading_notes": {
        "name": "读书笔记/阅读样本",
        "terms": (
            "书摘",
            "读书笔记",
            "阅读笔记",
            "阅读感悟",
            "书评",
            "豆瓣读书",
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
        ),
        "preferred_scopes": ("social_web", "business"),
        "preferred_source_types": ("社交/内容平台", "文娱/内容平台", "商业/产业媒体"),
        "caution_source_types": ("通用网页",),
        "guidance": "读书笔记和书摘应优先读者样本与图书条目，避免长段版权文本；平台评分只能作样本。",
    },
    "local_life": {
        "name": "本地生活/到店攻略",
        "terms": ("骑行路线", "骑行", "brunch", "咖啡店", "咖啡馆", "书店", "深夜书店", "发呆", "不排队", "看海", "夜景", "旅行攻略", "周末好去处", "横琴", "自驾", "景区", "赛里木湖", "喀拉峻", "夏塔", "库尔德宁", "琼库什台"),
        "preferred_scopes": ("social_web", "business", "local_official"),
        "preferred_source_types": ("社交/内容平台", "评价/消费样本", "地方官媒"),
        "caution_source_types": ("通用网页",),
        "guidance": "本地生活问题应分开攻略样本、到店评价和官方开放信息；单个平台榜单不能代表总体。",
    },
    "purchase_advice": {
        "name": "购买/检查清单",
        "terms": ("值不值得买", "购买", "选购", "优缺点", "验机", "used car", "pre-purchase", "inspection checklist", "mechanic inspection"),
        "preferred_scopes": ("social_web", "market_review", "business"),
        "preferred_source_types": ("社交/内容平台", "评价/消费样本", "商业/产业媒体"),
        "caution_source_types": ("通用网页",),
        "guidance": "购买或检查清单问题应交叉核验专业指南、平台评价和用户样本，避免只看 SEO 清单。",
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
            "食材成本",
            "配菜",
            "企业并购",
            "并购",
            "m&a",
            "industry policy",
            "宠物陪伴机器人",
            "宠物机器人",
            "宠物智能",
            "情感陪伴机器人",
            "问界",
            "赛力斯",
            "新能源汽车",
            "新能源车",
            "市场份额",
            "ai陪伴",
            "ai 陪伴",
            "职业服务",
            "在线招聘",
            "questmobile",
            "艾瑞",
            "伊春森工",
            "香养基地",
            "林下经济",
            *_ROBOTICS_AI_TERMS,
        ),
        "preferred_scopes": ("business", "finance", "ecommerce"),
        "preferred_source_types": ("商业/产业媒体", "财经/资本市场", "电商/零售垂类"),
        "caution_source_types": ("社交/内容平台",),
        "guidance": "优先产业媒体、公司一手资料和融资/市场材料；融资是产业维度时，不应只按财经口径收窄。",
    },
    "finance": {
        "name": "财经/资本市场",
        "terms": ("财经", "股票", "股价", "财报", "融资", "上市", "投资", "基金", "债券", "宏观", "资本市场", "英伟达", "nvidia", "大跌", "etf", "质押", "银行倒闭", "fedwatch", "降息", "净值", "持仓", "跟踪指数", "基金概况", "成立日期", "利空", "下跌原因", "ftse", "gilts", "bond yields", "imf", "bank of england"),
        "preferred_scopes": ("finance", "finance_disclosure", "finance_company", "finance_quote", "finance_news", "finance_macro"),
        "preferred_source_types": ("财经/公告披露", "财经/行情数据", "财经/新闻报道", "财经/宏观数据", "财经/资本市场", "商业/产业媒体"),
        "caution_source_types": ("社交/内容平台", "财经/情绪样本", "财经/研报观点"),
        "guidance": "优先公告披露、交易所/监管、行情入口、宏观官方数据和可信财经新闻；研报/情绪只作观点或样本，不输出投资建议。",
    },
    "tech": {
        "name": "技术/开发者",
        "terms": ("技术", "开源", "框架", "模型", "api", "sdk", "github", "开发者", "部署", "bug", "benchmark", "mcp", "教程", "自动加字幕", "剪映", "hermes agent", "内存占用", "cpu 性能测试", "vscode", "vs code", "visual studio code", "调试新特性", "node.js", "nodejs", "node js", "lts", "安装包", "下载地址", "wordpress", "woocommerce", "spectra", "seo", "seedance", "豆包", "doubao", "视频生成模型", "ai写作", "ai写小说", "ai绘画", "ai画画", "winui3", "winui 3", "windows app sdk", "sam 3", "segment anything with concepts", "ultralytics", *_ROBOTICS_AI_TERMS),
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
            "漫改动画",
            "画风分析",
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
            "アニメ",
            "新刊",
            "続編",
            "劇場版",
            "葬送的芙莉莲",
            "芙莉莲",
            "夏目友人帐",
            "尖帽子魔法工坊",
            "尖帽子的魔法工坊",
            "スキップとローファー",
            "skip and loafer",
            "漫改动画",
            "代餐",
            "弱キャラ友崎くん",
            "ぼっち・ざ・ろっく",
            "僕の心のヤバイやつ",
            "同人壁纸",
            "ost",
            "歌单",
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


_UNIVERSITY_ENTITY_TERMS = (
    "大学", "高校", "学院", "院系", "清华", "北大", "北京大学", "浙大", "浙江大学",
    "复旦", "上海交大", "上海交通大学", "中科大", "中国科学技术大学", "南京大学",
    "tsinghua", "pku", "zju", "fudan", "sjtu", "ustc", "nju",
)
_UNIVERSITY_TASK_TERMS = (
    "研究生招生", "博士招生", "硕士招生", "招生目录", "招生简章", "招生专业目录",
    "导师", "导师名单", "导师介绍", "导师情况", "研究生院", "院系", "计算机系",
    "推免", "复试", "考研", "培养方案", "faculty", "advisor", "supervisor", "graduate admissions",
)
_ACG_QUERY_TERMS = (
    "漫画", "番剧", "轻小说", "动漫", "动画", "二次元", "魔女", "学园", "治愈",
    "日常", "连载", "单行本", "manga", "anime", "comic", "light novel", "bangumi", "pixiv",
    "mangapedia", "manba",
)
_UNIVERSITY_STRONG_SIGNAL_TERMS = (
    "招生", "导师", "院系", "研究生", "研究生院", "推免", "复试", "考研",
    "faculty", "advisor", "supervisor", "graduate admissions",
)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _contains_any(text: str, needles: list[str] | tuple[str, ...]) -> bool:
    return any(needle.lower() in text for needle in needles)


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _unique_keep_order(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _collapse_ws(str(item))
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


def _source_mix(results: list[dict[str, Any]]) -> dict[str, int]:
    mix: dict[str, int] = {}
    for item in results:
        key = str(item.get("source_type") or "通用网页")
        mix[key] = mix.get(key, 0) + 1
    return dict(sorted(mix.items(), key=lambda item: (-item[1], item[0])))


def _search_limit_advice(
    limit: int,
    *,
    query: str = "问题",
    profile: str | None = None,
    scope: str | None = None,
    site: str | None = None,
) -> dict[str, Any]:
    current = max(int(limit or 0), 0)
    threshold = 30
    if current >= threshold:
        return {"enabled": False, "limit": current, "recommended_limit": DEFAULT_SEARCH_LIMIT}
    repair_command = _expanded_limit_repair_command(query, profile=profile, scope=scope, site=site)
    return {
        "enabled": True,
        "limit": current,
        "recommended_limit": DEFAULT_SEARCH_LIMIT,
        "threshold": threshold,
        "severity": "warn" if current < 20 else "note",
        "message": (
            f"当前 --limit {current} 适合 smoke test，不适合严肃研究；"
            f"Agent 应先无感补跑 --limit {DEFAULT_SEARCH_LIMIT}，再压缩输出给用户。"
        ),
        "agent_instruction": (
            "不要因为用户给了很小的 limit 就直接下最终结论；除非用户明确只要 smoke，"
            "先执行 silent_repair_commands 里的扩大候选池命令，再合并呈现。"
        ),
        "repair_policy": "silent_expand_then_summarize",
        "silent_repair_commands": [
            {
                "role": "expanded_search",
                "command": repair_command,
                "reason": f"当前 {current} 条只适合 smoke；补到 {DEFAULT_SEARCH_LIMIT} 条作为研究级候选池。",
            }
        ],
        "suggested_command": repair_command,
    }


def _expanded_limit_repair_command(
    query: str,
    *,
    profile: str | None = None,
    scope: str | None = None,
    site: str | None = None,
) -> str:
    quoted = _shell_quote_for_command(query or "问题")
    parts = [f"guanlan search {quoted}"]
    if profile:
        parts.append(f"--profile {profile}")
    if site:
        parts.append(f"--site {site}")
    if scope:
        parts.append(f"--scope {scope}")
    parts.append(f"--limit {DEFAULT_SEARCH_LIMIT}")
    parts.append("--trace")
    return " ".join(parts)


def _shell_quote_for_command(value: str) -> str:
    escaped = (value or "").replace('"', '\"')
    return f'"{escaped}"'


def _is_university_admissions_query(query: str) -> bool:
    text = _collapse_ws(query).lower()
    if any(term in text for term in _UNIVERSITY_TASK_TERMS if len(term) >= 4):
        return True
    return any(term in text for term in _UNIVERSITY_ENTITY_TERMS) and any(
        term in text for term in ("招生", "导师", "院系", "研究生", "faculty", "advisor", "supervisor")
    )


def _is_acg_entertainment_query(query: str) -> bool:
    text = _collapse_ws(query).lower()
    return _contains_any(text, _ACG_QUERY_TERMS)


def _has_strong_university_signal(query: str) -> bool:
    text = _collapse_ws(query).lower()
    return _contains_any(text, _UNIVERSITY_STRONG_SIGNAL_TERMS)


def _should_prefer_entertainment_over_university(query: str) -> bool:
    text = _collapse_ws(query).lower()
    return _is_acg_entertainment_query(text) and not _has_strong_university_signal(text)


__all__ = [
    "_LONG_QUERY_KEYPHRASE_HINTS",
    "_MEANINGLESS_QUERY_ALLOWLIST",
    "_QUALITY_INTENT_PROFILES",
    "_QUERY_KEYBOARD_RUNS",
    "_QUERY_REWRITE_STOPWORDS",
    "_RECENCY_DEFAULT_WINDOW_DAYS",
    "_collapse_ws",
    "_contains_cjk",
    "_domain",
    "_is_acg_entertainment_query",
    "_query_relevance_terms",
    "_search_limit_advice",
    "_shell_quote_for_command",
    "_should_prefer_entertainment_over_university",
    "_source_mix",
    "_unique_keep_order",
    "_wps_office_subroute",
]
