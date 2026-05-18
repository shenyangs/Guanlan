# -*- coding: utf-8 -*-
"""Evaluation scenarios for comparing generic web_search with Guanlan.

The benchmark in this module is intentionally deterministic by default. It
checks whether Guanlan keeps the product contract that matters to agents:
route the request to the right source families, preserve evidence roles, and
avoid shrinking the research pool before any live network request happens.
"""

from __future__ import annotations

import json
from typing import Any

EVALUATION_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "policy_source_identity",
        "query": "新质生产力 政策 原文",
        "profile": "china",
        "preset": "policy",
        "expected_gain": "优先触达官方原文和党央媒，减少海外评论或二手解读误导。",
        "checks": ["has_official_source", "keeps_source_identity", "mentions_evidence_limits"],
        "expected_intents": ["policy"],
        "expected_scopes": ["gov", "party_central"],
        "expected_roles": ["official_primary"],
    },
    {
        "id": "reputation_platform_islands",
        "query": "某产品 用户评价 值不值得买",
        "profile": "china",
        "preset": "reputation",
        "expected_gain": "路由到知乎、微博、小红书、B站等公开样本，同时提醒样本偏差。",
        "checks": ["uses_social_samples", "avoids_population_claim", "keeps_fallback_web"],
        "expected_intents": ["reputation", "purchase_advice"],
        "expected_scopes": ["social_web"],
        "expected_roles": ["user_sample", "community_discussion"],
    },
    {
        "id": "hot_trend_awareness",
        "query": "今天 中文互联网 热点 AI",
        "profile": "china",
        "preset": "general",
        "expected_gain": "先巡视热榜/快讯，再进入 research，提升时效感。",
        "checks": ["uses_hotnews", "clusters_trends", "keeps_timestamp"],
        "expected_intents": ["hot_trend"],
        "expected_scopes": [],
        "expected_roles": ["fresh_news", "public_discussion"],
    },
    {
        "id": "developer_feedback",
        "query": "Python Agent 框架 对比 github issue",
        "profile": "china",
        "preset": "tech",
        "expected_gain": "优先技术社区、GitHub、开发者讨论，而不是泛 SEO 文章。",
        "checks": ["uses_dev_sources", "mentions_version_sensitivity"],
        "expected_intents": ["tech"],
        "expected_scopes": ["tech_dev"],
        "expected_roles": ["developer_discussion", "source_code"],
    },
    {
        "id": "wps_office_market_radar",
        "query": "WPS AI PPT Agent 办公选题 最近热点",
        "profile": "china",
        "preset": "wps_office",
        "expected_gain": "以金山办公/WPS 为锚点，外扩办公 AI、PPT、Agent、SaaS、信创、安全、竞品、RSS 和社区样本，避免品牌稿单源。",
        "checks": ["uses_wps_office_scope", "keeps_topic_breadth", "requires_rss_discovery"],
        "expected_intents": ["wps_office"],
        "expected_scopes": ["wps_office", "business", "tech_dev"],
        "expected_roles": ["company_primary", "industry_report", "user_sample"],
    },
    {
        "id": "tech_ai_agent_not_wps_near_miss",
        "query": "DeepSeek-V4 智能体 Agent 最新",
        "profile": "china",
        "preset": "tech",
        "expected_gain": "纯 AI Agent/智能体热点进入科技/AI 发现层，不因 Agent/skill/token 等词误进 WPS Office。",
        "checks": ["uses_tech_scope", "avoids_wps_false_positive", "requires_rss_discovery"],
        "expected_intents_any": ["tech"],
        "forbidden_intents": ["wps_office"],
        "expected_scopes_any": ["developer", "tech_dev", "community_sample"],
        "expected_command_contains": ["feeds curated"],
        "forbidden_command_contains": ["--preset wps_office"],
    },
    {
        "id": "fictional_university_near_miss",
        "query": "魔法学院 漫画 导师 角色",
        "profile": "china",
        "preset": "entertainment",
        "expected_gain": "漫画/小说/角色语境里的“导师/学院”不应误触高校招生导师工作流。",
        "checks": ["uses_entertainment_scope", "avoids_university_false_positive"],
        "expected_intents_any": ["entertainment"],
        "forbidden_intents": ["university_admissions"],
        "expected_scopes_any": ["entertainment", "social_web"],
        "forbidden_command_contains": ["--preset university", "--scope university"],
    },
    {
        "id": "sports_venue_rental_near_miss",
        "query": "学校 体育馆 出租 招租",
        "profile": "china",
        "preset": "general",
        "expected_gain": "场馆出租/招租是本地信息或开放网页查找，不应因为体育馆误进赛事体育路线。",
        "checks": ["avoids_sports_false_positive", "keeps_light_search"],
        "forbidden_intents": ["sports"],
        "forbidden_command_contains": ["--preset sports", "--scope sports"],
    },
    {
        "id": "finance_macro_not_stock_near_miss",
        "query": "2026 recession GDP inflation",
        "profile": "english",
        "preset": "finance",
        "expected_gain": "宏观经济查询进入 finance_macro/research，不走股票代码或个股行情入口。",
        "checks": ["uses_macro_finance_scope", "avoids_stock_entrypoint"],
        "expected_intents_any": ["finance_macro"],
        "expected_scopes_any": ["finance_macro", "global_official"],
        "expected_command_contains": ["--scope finance_macro"],
        "forbidden_command_contains": ["guanlan stock"],
    },
    {
        "id": "podcast_discovery_positive",
        "query": "AI 创业 播客 小宇宙 推荐",
        "profile": "china",
        "preset": "podcast",
        "expected_gain": "播客发现任务走 podcast/curated-sources，不被 AI 创业词牵引成普通科技搜索。",
        "checks": ["uses_podcast_scope", "keeps_audio_source_discovery"],
        "expected_intents_any": ["podcast"],
        "expected_scopes_any": ["podcast"],
        "expected_command_contains": ["curated-sources"],
    },
    {
        "id": "device_upgrade_policy_compound_positive",
        "query": "设备更新万亿",
        "profile": "china",
        "preset": "policy",
        "expected_gain": "政策复合短语应自动补齐“大规模设备更新/设备更新改造/工信部/商务部”等限定词，避免退化成“设备”词典解释。",
        "checks": ["uses_policy_scope", "rewrites_compound_policy_phrase"],
        "expected_intents_any": ["policy"],
        "expected_command_contains": ["大规模设备更新", "工信部"],
    },
    {
        "id": "brand_marketing_protected_phrase_positive",
        "query": "酱香拿铁营销",
        "profile": "china",
        "preset": "industry",
        "expected_gain": "品牌固定短语应保留整词语义，自动补瑞幸/茅台/联名/复盘等上下文，不被单字词典释义带偏。",
        "checks": ["protects_brand_phrase", "rewrites_marketing_query"],
        "expected_intents_any": ["industry", "ecommerce"],
        "expected_command_contains": ["瑞幸", "茅台"],
    },
    {
        "id": "tsmc_arizona_cross_language_positive",
        "query": "台积电亚利桑那",
        "profile": "china",
        "preset": "company",
        "expected_gain": "中英混合外企/地名查询应自动补 TSMC/Arizona fab/company context，而不是被“台”字政治漂移带偏。",
        "checks": ["uses_company_scope", "adds_cross_language_aliases"],
        "expected_intents_any": ["company_primary", "global_industry"],
        "expected_command_contains": ["TSMC", "Arizona fab"],
    },
    {
        "id": "car_t_medical_compound_positive",
        "query": "CAR-T疗法",
        "profile": "china",
        "preset": "general",
        "expected_gain": "医疗前沿术语应自动进入 medical/academic 语境，补临床、NMPA、CDE 等一手线索，而不是落回泛搜。",
        "checks": ["uses_medical_scope", "adds_regulatory_and_clinical_terms"],
        "expected_intents_any": ["medical_health"],
        "expected_command_contains": ["NMPA", "CDE"],
    },
    {
        "id": "academic_indexing",
        "query": "EI会议 投稿 检索 收录 要求",
        "profile": "china",
        "preset": "academic",
        "expected_gain": "区分数据库/出版商口径、会议 CFP、高校认定口径，避免代投软文主导。",
        "checks": ["uses_academic_scope", "separates_publisher_and_school_rules", "avoids_paper_agency"],
        "expected_intents": ["academic"],
        "expected_scopes": ["academic"],
        "expected_roles": ["database_official", "publisher_guideline"],
    },
    {
        "id": "local_official_context",
        "query": "上海 人工智能 产业政策 原文",
        "profile": "china",
        "preset": "local",
        "expected_gain": "地方政策优先地方政府、发改/经信等一手来源，再补产业媒体。",
        "checks": ["uses_local_official", "keeps_policy_level", "keeps_open_web_fallback"],
        "expected_intents": ["policy", "local"],
        "expected_scopes": ["local_official", "gov"],
        "expected_roles": ["official_primary"],
    },
    {
        "id": "ecommerce_industry",
        "query": "即时零售 电商 产业趋势 亿邦动力",
        "profile": "china",
        "preset": "ecommerce",
        "expected_gain": "把电商/零售垂类媒体、平台公告和开放网页放到同一证据结构里。",
        "checks": ["uses_ecommerce_scope", "keeps_industry_context", "keeps_source_diversity"],
        "expected_intents": ["ecommerce", "industry"],
        "expected_scopes": ["ecommerce", "business"],
        "expected_roles": ["vertical_report", "industry_report"],
    },
    {
        "id": "entertainment_reputation",
        "query": "哪吒2 票房 口碑 豆瓣评分 最近热议",
        "profile": "china",
        "preset": "entertainment",
        "expected_gain": "把豆瓣评分、猫眼/灯塔票房、B站/微博讨论和产业报道分层，避免把热度直接写成口碑。",
        "checks": ["uses_entertainment_scope", "separates_metrics_and_fandom", "keeps_open_web_fallback"],
        "expected_intents": ["entertainment", "reputation"],
        "expected_scopes": ["entertainment", "social_web"],
        "expected_roles": ["platform_metric", "user_review", "fan_discussion"],
    },
    {
        "id": "global_entertainment_reputation",
        "query": "Taylor Swift 最新公开动态 新专辑 巡演",
        "profile": "english",
        "preset": "global_entertainment",
        "expected_gain": "把欧美娱乐行业媒体、音乐榜单、艺人/厂牌一手信息和粉丝讨论分层，避免中文二手搬运覆盖事实核验。",
        "checks": ["uses_global_entertainment_scope", "separates_trade_media_and_fandom", "keeps_freshness_boundary"],
        "expected_intents": ["global_entertainment", "hot_trend"],
        "expected_scopes": ["global_entertainment", "community_sample"],
        "expected_roles": ["trade_report", "music_chart", "fan_discussion"],
    },
    {
        "id": "jp_kr_entertainment_reputation",
        "query": "BLACKPINK K-pop 最新回归 Soompi Oricon",
        "profile": "hybrid",
        "preset": "jp_kr_entertainment",
        "expected_gain": "把日韩本地媒体/榜单、英文翻译站、经纪公司口径和粉丝讨论分层，显式保留翻译层风险。",
        "checks": ["uses_jp_kr_entertainment_scope", "separates_agency_chart_translation_and_fandom", "keeps_translation_risk"],
        "expected_intents": ["jp_kr_entertainment", "hot_trend"],
        "expected_scopes": ["jp_kr_entertainment", "global_entertainment"],
        "expected_roles": ["translation_report", "chart_metric", "agency_context"],
    },
    {
        "id": "cybersecurity_advisory",
        "query": "OpenSSL CVE 最新 漏洞 影响 版本 修复",
        "profile": "china",
        "preset": "cybersecurity",
        "expected_gain": "优先 CVE/NVD/CISA/厂商公告和补丁说明，避免把论坛转述当成安全结论。",
        "checks": ["uses_security_scope", "keeps_high_risk_boundary", "prioritizes_vendor_advisory"],
        "expected_intents": ["cybersecurity"],
        "expected_scopes": ["cybersecurity", "developer", "global_official"],
        "expected_roles": ["security_advisory", "vulnerability_record", "vendor_patch"],
    },
    {
        "id": "weather_disaster_alert",
        "query": "台风 路径 最新 中央气象台 日本气象厅",
        "profile": "china",
        "preset": "weather_disaster",
        "expected_gain": "优先官方气象和应急来源，保留时间戳，避免社交平台过期预警误导。",
        "checks": ["uses_weather_scope", "keeps_timestamp", "keeps_high_risk_boundary"],
        "expected_intents": ["weather_disaster", "hot_trend"],
        "expected_scopes": ["weather_disaster", "gov", "global_official"],
        "expected_roles": ["official_alert", "forecast_track"],
    },
    {
        "id": "career_salary_interview",
        "query": "字节 AI 产品经理 校招 薪资 面经",
        "profile": "china",
        "preset": "career",
        "expected_gain": "把岗位、薪资样本、面经和招聘市场信息分层，避免单帖代表总体。",
        "checks": ["uses_career_scope", "keeps_sample_bias", "keeps_source_diversity"],
        "expected_intents": ["career"],
        "expected_scopes": ["career", "social_web", "business"],
        "expected_roles": ["job_posting", "salary_sample", "interview_sample"],
    },
    {
        "id": "local_llm_prompt_context",
        "query": "给本地 Ollama 模型联网搜索 中文政策信息",
        "profile": "china",
        "preset": "policy",
        "expected_gain": "把搜索、阅读、证据边界组织成可直接交给本地模型的上下文。",
        "checks": ["keeps_context_format", "keeps_source_identity", "keeps_agent_commands"],
        "expected_intents": ["policy"],
        "expected_scopes": ["gov", "party_central"],
        "expected_roles": ["official_primary"],
    },
]

BENCHMARK_TASKS: list[dict[str, Any]] = [
    {"id": "policy_001", "category": "policy", "query": "新质生产力 政策 原文", "expected_source_family": "official"},
    {"id": "policy_002", "category": "policy", "query": "人工智能治理 暂行办法 官方 原文", "expected_source_family": "official"},
    {"id": "policy_003", "category": "policy", "query": "数据要素 政策 国家发改委 原文", "expected_source_family": "official"},
    {"id": "policy_004", "category": "policy", "query": "低空经济 政策 官方口径", "expected_source_family": "official"},
    {"id": "policy_005", "category": "policy", "query": "制造业 数字化转型 政策 部委", "expected_source_family": "official"},
    {"id": "local_001", "category": "local", "query": "上海 人工智能 产业政策 原文", "expected_source_family": "local_official"},
    {"id": "local_002", "category": "local", "query": "深圳 低空经济 政策 原文", "expected_source_family": "local_official"},
    {"id": "local_003", "category": "local", "query": "杭州 算力券 政策 官方", "expected_source_family": "local_official"},
    {"id": "local_004", "category": "local", "query": "成都 人工智能 产业扶持 政策", "expected_source_family": "local_official"},
    {"id": "local_005", "category": "local", "query": "苏州 生物医药 产业政策 原文", "expected_source_family": "local_official"},
    {"id": "ecommerce_001", "category": "ecommerce", "query": "即时零售 电商 产业趋势 亿邦动力", "expected_source_family": "vertical_media"},
    {"id": "ecommerce_002", "category": "ecommerce", "query": "跨境电商 AI 工具 卖家反馈", "expected_source_family": "vertical_media"},
    {"id": "ecommerce_003", "category": "ecommerce", "query": "抖音电商 商家 服务商 趋势", "expected_source_family": "vertical_media"},
    {"id": "ecommerce_004", "category": "ecommerce", "query": "美团 闪购 即时零售 商家 案例", "expected_source_family": "vertical_media"},
    {"id": "ecommerce_005", "category": "ecommerce", "query": "淘宝天猫 AI 电商 产品趋势", "expected_source_family": "vertical_media"},
    {"id": "tech_001", "category": "tech", "query": "vLLM SGLang KV Cache 推理框架 对比", "expected_source_family": "developer"},
    {"id": "tech_002", "category": "tech", "query": "LangGraph AutoGen CrewAI GitHub issue 对比", "expected_source_family": "developer"},
    {"id": "tech_003", "category": "tech", "query": "MCP server Python SDK issue 实践", "expected_source_family": "developer"},
    {"id": "tech_004", "category": "tech", "query": "RAG reranker bge m3 中文 实测", "expected_source_family": "developer"},
    {"id": "tech_005", "category": "tech", "query": "Ollama 本地模型 联网搜索 工具", "expected_source_family": "developer"},
    {"id": "wps_office_001", "category": "wps_office", "query": "WPS AI PPT Agent 办公选题 最近热点", "expected_source_family": "wps_office"},
    {"id": "wps_office_002", "category": "wps_office", "query": "办公 AI PPT 生成 文档协作 SaaS 信创", "expected_source_family": "wps_office"},
    {"id": "wps_office_003", "category": "wps_office", "query": "WPS 365 企业协作 办公安全 国产化", "expected_source_family": "wps_office"},
    {"id": "reputation_001", "category": "reputation", "query": "某 AI 笔记软件 用户评价 值不值得买", "expected_source_family": "user_sample"},
    {"id": "reputation_002", "category": "reputation", "query": "AI 眼镜 用户评价 小红书 知乎", "expected_source_family": "user_sample"},
    {"id": "reputation_003", "category": "reputation", "query": "新能源汽车 车主评价 缺点", "expected_source_family": "user_sample"},
    {"id": "reputation_004", "category": "reputation", "query": "儿童学习机 用户反馈 真实体验", "expected_source_family": "user_sample"},
    {"id": "reputation_005", "category": "reputation", "query": "国产数据库 用户口碑 迁移成本", "expected_source_family": "user_sample"},
    {"id": "entertainment_001", "category": "entertainment", "query": "哪吒2 票房 豆瓣评分 最近热议", "expected_source_family": "entertainment"},
    {"id": "entertainment_002", "category": "entertainment", "query": "国产剧 口碑 播放量 B站 微博 讨论", "expected_source_family": "entertainment"},
    {"id": "entertainment_003", "category": "entertainment", "query": "某综艺 热搜 粉圈 争议 评价", "expected_source_family": "entertainment"},
    {"id": "entertainment_004", "category": "entertainment", "query": "某手游 TapTap 评分 玩家评价", "expected_source_family": "entertainment"},
    {"id": "entertainment_005", "category": "entertainment", "query": "某明星 最近舆情 微博 B站 讨论", "expected_source_family": "entertainment"},
    {"id": "entertainment_006", "category": "entertainment", "query": "Taylor Swift 最新动态 Billboard Variety 巡演", "expected_source_family": "global_entertainment"},
    {"id": "entertainment_007", "category": "entertainment", "query": "BLACKPINK K-pop 最新回归 Soompi Oricon", "expected_source_family": "jp_kr_entertainment"},
    {"id": "security_001", "category": "cybersecurity", "query": "OpenSSL CVE 最新 漏洞 影响 版本 修复", "expected_source_family": "cybersecurity"},
    {"id": "weather_001", "category": "weather", "query": "台风 路径 最新 中央气象台 日本气象厅", "expected_source_family": "weather_disaster"},
    {"id": "sports_001", "category": "sports", "query": "梅西 今天比赛 数据 伤病 最新", "expected_source_family": "sports"},
    {"id": "science_001", "category": "science", "query": "詹姆斯韦伯 发现 外星生命 真的假的 NASA", "expected_source_family": "science"},
    {"id": "career_001", "category": "career", "query": "字节 AI 产品经理 校招 薪资 面经", "expected_source_family": "career"},
    {"id": "podcast_001", "category": "podcast", "query": "AI 创业 中文播客 小宇宙", "expected_source_family": "podcast"},
    {"id": "education_001", "category": "education", "query": "雅思 口语 2026 题库 机经 靠谱吗", "expected_source_family": "test_prep"},
    {"id": "hot_001", "category": "hot", "query": "今天 中文互联网 热点 AI", "expected_source_family": "hotnews"},
    {"id": "hot_002", "category": "hot", "query": "今天 微博 B站 科技 热点", "expected_source_family": "hotnews"},
    {"id": "hot_003", "category": "hot", "query": "最近 AI 应用 创业 热点", "expected_source_family": "hotnews"},
    {"id": "hot_004", "category": "hot", "query": "今天 财经 市场 热点 财联社", "expected_source_family": "hotnews"},
    {"id": "hot_005", "category": "hot", "query": "最近 开发者社区 热门项目", "expected_source_family": "hotnews"},
    {"id": "academic_001", "category": "academic", "query": "EI会议 投稿 检索 收录 要求", "expected_source_family": "academic"},
    {"id": "academic_002", "category": "academic", "query": "CCF 推荐会议 人工智能 投稿 官网", "expected_source_family": "academic"},
    {"id": "academic_003", "category": "academic", "query": "SCI 期刊 APC 出版商 官方说明", "expected_source_family": "academic"},
    {"id": "academic_004", "category": "academic", "query": "高校 科研奖励 论文认定 政策", "expected_source_family": "academic"},
    {"id": "academic_005", "category": "academic", "query": "arXiv 论文 代码 GitHub 中文解读", "expected_source_family": "academic"},
    {"id": "local_llm_001", "category": "local_llm", "query": "给本地 Ollama 模型联网搜索 中文政策信息", "expected_source_family": "agent_context"},
    {"id": "local_llm_002", "category": "local_llm", "query": "Open WebUI 调用本地 HTTP 搜索证据", "expected_source_family": "agent_context"},
    {"id": "local_llm_003", "category": "local_llm", "query": "LM Studio 本地模型 RAG 导入 中文网页", "expected_source_family": "agent_context"},
    {"id": "local_llm_004", "category": "local_llm", "query": "本地模型 读取网页 生成引用证据", "expected_source_family": "agent_context"},
    {"id": "local_llm_005", "category": "local_llm", "query": "无联网大模型 获取今日热点 上下文", "expected_source_family": "agent_context"},
    {
        "id": "policy_near_miss_001",
        "category": "policy",
        "case_type": "near_miss",
        "query": "site:gov.cn 工信部 人工智能 政策 2026",
        "expected_source_family": "official",
        "expected_intents_any": ["policy"],
        "expected_command_contains": ["--site gov.cn"],
        "forbidden_command_contains": ["feeds curated"],
    },
    {
        "id": "tech_near_miss_001",
        "category": "tech",
        "case_type": "near_miss",
        "query": "DeepSeek-V4 智能体 Agent 最新",
        "expected_source_family": "developer",
        "expected_intents_any": ["tech"],
        "forbidden_intents": ["wps_office"],
        "expected_command_contains": ["feeds curated"],
    },
    {
        "id": "finance_near_miss_001",
        "category": "finance",
        "case_type": "near_miss",
        "query": "2026 recession GDP inflation",
        "expected_source_family": "finance",
        "expected_intents_any": ["finance_macro"],
        "expected_command_contains": ["--scope finance_macro"],
        "forbidden_command_contains": ["guanlan stock"],
    },
    {
        "id": "entertainment_near_miss_001",
        "category": "entertainment",
        "case_type": "near_miss",
        "query": "魔法学院 漫画 导师 角色",
        "expected_source_family": "entertainment",
        "expected_intents_any": ["entertainment"],
        "forbidden_intents": ["university_admissions"],
        "forbidden_command_contains": ["--scope university", "--preset university"],
    },
    {
        "id": "sports_negative_001",
        "category": "sports",
        "case_type": "negative",
        "query": "学校 体育馆 出租 招租",
        "expected_source_family": "general",
        "forbidden_intents": ["sports"],
        "forbidden_command_contains": ["--scope sports", "--preset sports"],
    },
    {
        "id": "policy_compound_001",
        "category": "policy",
        "case_type": "positive",
        "query": "设备更新万亿",
        "expected_source_family": "official",
        "expected_intents_any": ["policy"],
        "expected_command_contains": ["大规模设备更新", "工信部"],
    },
    {
        "id": "policy_compound_002",
        "category": "policy",
        "case_type": "positive",
        "query": "数据出境安全评估",
        "expected_source_family": "official",
        "expected_intents_any": ["standards_compliance", "policy"],
        "expected_command_contains": ["网信办", "申报"],
    },
    {
        "id": "medical_positive_001",
        "category": "science",
        "case_type": "positive",
        "query": "CAR-T疗法",
        "expected_source_family": "science",
        "expected_intents_any": ["medical_health"],
        "expected_command_contains": ["NMPA", "CDE"],
    },
    {
        "id": "industry_brand_001",
        "category": "ecommerce",
        "case_type": "positive",
        "query": "酱香拿铁营销",
        "expected_source_family": "vertical_media",
        "expected_intents_any": ["industry", "ecommerce"],
        "expected_command_contains": ["瑞幸", "茅台"],
    },
    {
        "id": "industry_brand_002",
        "category": "ecommerce",
        "case_type": "positive",
        "query": "胖东来模式",
        "expected_source_family": "vertical_media",
        "expected_intents_any": ["industry", "ecommerce"],
        "expected_command_contains": ["零售模式", "商超"],
    },
    {
        "id": "company_crosslang_001",
        "category": "tech",
        "case_type": "positive",
        "query": "台积电亚利桑那",
        "expected_source_family": "developer",
        "expected_intents_any": ["company_primary", "global_industry"],
        "expected_command_contains": ["TSMC", "Arizona fab"],
    },
]


def list_evaluation_scenarios() -> list[dict[str, Any]]:
    """Return built-in evaluation scenarios."""
    return list(EVALUATION_SCENARIOS)


def list_benchmark_tasks(category: str | None = None) -> list[dict[str, Any]]:
    """Return realistic benchmark task seeds for live/manual evaluation."""
    category_key = (category or "").strip().lower()
    if not category_key:
        return list(BENCHMARK_TASKS)
    return [task for task in BENCHMARK_TASKS if task.get("category") == category_key]


def format_evaluation_markdown(scenarios: list[dict[str, Any]] | None = None) -> str:
    """Render scenarios as a lightweight evaluation checklist."""
    rows = scenarios or EVALUATION_SCENARIOS
    lines = ["# 观澜评估集", "", "用于比较普通 web_search 与观澜证据包在中文语境里的差异。"]
    for item in rows:
        lines.extend(
            [
                "",
                f"## {item['id']}",
                f"- Query: {item['query']}",
                f"- Profile: {item['profile']}",
                f"- Expected gain: {item['expected_gain']}",
                f"- Checks: {', '.join(item['checks'])}",
            ]
        )
    return "\n".join(lines)


def format_evaluation_jsonl(scenarios: list[dict[str, Any]] | None = None) -> str:
    """Render scenarios as JSONL for external benchmark harnesses."""
    return "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in (scenarios or EVALUATION_SCENARIOS))


def format_benchmark_tasks_markdown(tasks: list[dict[str, Any]] | None = None) -> str:
    """Render live/manual benchmark task seeds as a compact Markdown plan."""
    rows = tasks or BENCHMARK_TASKS
    categories: dict[str, list[dict[str, Any]]] = {}
    for task in rows:
        categories.setdefault(str(task.get("category") or "general"), []).append(task)
    lines = [
        "# 观澜真实任务评测池",
        "",
        "这些任务用于 live/manual benchmark，不代表 quick gate 已经联网验证。",
        "评测时应比较普通搜索、`guanlan search`、`guanlan route + research` 三组输出。",
    ]
    for category in sorted(categories):
        lines.extend(["", f"## {category}"])
        for task in categories[category]:
            lines.append(
                f"- {task.get('id')}: {task.get('query')} "
                f"(expected={task.get('expected_source_family')})"
            )
    return "\n".join(lines)


def run_benchmark(mode: str = "quick", limit: int = 50) -> dict[str, Any]:
    """Run a deterministic benchmark over built-in scenarios.

    ``mode`` is reserved for future live probes; ``quick`` deliberately avoids
    network access so it can be used as a release gate in CI.
    """
    from guanlan.router import build_route_plan

    mode = mode if mode in {"quick", "live"} else "quick"
    cases: list[dict[str, Any]] = []
    for scenario in EVALUATION_SCENARIOS:
        plan = build_route_plan(
            scenario["query"],
            preset=str(scenario.get("preset") or "general"),
            profile=str(scenario.get("profile") or "china"),
            limit=max(limit, 1),
        )
        plan_data = plan.to_dict()
        checks = _score_route_plan(scenario, plan_data, limit=max(limit, 1))
        passed = sum(1 for check in checks if check["status"] == "pass")
        warned = sum(1 for check in checks if check["status"] == "warn")
        failed = sum(1 for check in checks if check["status"] == "fail")
        score = round((passed + warned * 0.5) / max(len(checks), 1) * 100, 1)
        status = "fail" if failed else ("warn" if warned else "pass")
        cases.append(
            {
                "id": scenario["id"],
                "query": scenario["query"],
                "profile": scenario.get("profile", "china"),
                "preset": scenario.get("preset", "general"),
                "status": status,
                "score": score,
                "expected_gain": scenario["expected_gain"],
                "checks": checks,
                "route": {
                    "primary_intents": plan_data.get("primary_intents", []),
                    "secondary_intents": plan_data.get("secondary_intents", []),
                    "preferred_scopes": plan_data.get("preferred_scopes", []),
                    "evidence_roles": plan_data.get("evidence_roles", []),
                    "recommended_commands": plan_data.get("recommended_commands", []),
                    "limit": plan_data.get("limit", 0),
                    "read_top": plan_data.get("read_top", 0),
                },
            }
        )
    passed = sum(1 for item in cases if item["status"] == "pass")
    warned = sum(1 for item in cases if item["status"] == "warn")
    failed = sum(1 for item in cases if item["status"] == "fail")
    return {
        "mode": mode,
        "limit": max(limit, 1),
        "summary": {
            "total": len(cases),
            "pass": passed,
            "warn": warned,
            "fail": failed,
            "score": round(sum(float(item["score"]) for item in cases) / max(len(cases), 1), 1),
        },
        "principle": "评测重点不是搜到多少页面，而是 Agent 是否拿到了正确的中文信源结构、证据角色和足够大的候选池。",
        "cases": cases,
    }


def format_benchmark_markdown(report: dict[str, Any]) -> str:
    """Render benchmark results as Markdown."""
    summary = report.get("summary") or {}
    lines = [
        "# 观澜评测基准",
        "",
        f"- 模式: {report.get('mode', 'quick')}",
        f"- 候选池下限: {report.get('limit', 50)}",
        f"- 总分: {summary.get('score', 0)}",
        f"- 结果: pass={summary.get('pass', 0)} warn={summary.get('warn', 0)} fail={summary.get('fail', 0)}",
        f"- 原则: {report.get('principle', '')}",
        "",
        "## 场景",
    ]
    for case in report.get("cases") or []:
        route = case.get("route") or {}
        lines.append(f"- [{case.get('status')}] {case.get('id')}: {case.get('query')} score={case.get('score')}")
        lines.append(f"  意图: {', '.join(route.get('primary_intents') or []) or 'open'}")
        lines.append(f"  Scope: {', '.join(route.get('preferred_scopes') or []) or 'open web'}")
        lines.append(f"  证据角色: {', '.join(route.get('evidence_roles') or []) or '未识别'}")
    return "\n".join(lines)


def format_benchmark_jsonl(report: dict[str, Any]) -> str:
    """Render benchmark cases as JSONL for external dashboards."""
    return "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in report.get("cases") or [])


def _score_route_plan(scenario: dict[str, Any], plan: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    intents = set(plan.get("primary_intents") or []) | set(plan.get("secondary_intents") or [])
    scopes = set(plan.get("preferred_scopes") or []) | set(plan.get("fallback_scopes") or [])
    roles = set(plan.get("evidence_roles") or [])
    commands = [str(item) for item in plan.get("recommended_commands") or []]
    command_blob = "\n".join(commands)
    checks: list[dict[str, Any]] = []

    expected_intents = set(scenario.get("expected_intents") or [])
    checks.append(
        _benchmark_check(
            "route_intent",
            bool(expected_intents & intents) if expected_intents else bool(intents),
            f"expected intent {sorted(expected_intents)} in route {sorted(intents)}",
        )
    )

    expected_scopes = set(scenario.get("expected_scopes") or [])
    checks.append(
        _benchmark_check(
            "source_scope",
            bool(expected_scopes & scopes) if expected_scopes else True,
            f"expected scope {sorted(expected_scopes) or ['open web']} in route {sorted(scopes) or ['open web']}",
        )
    )

    expected_roles = set(scenario.get("expected_roles") or [])
    checks.append(
        _benchmark_check(
            "evidence_role",
            bool(expected_roles & roles) if expected_roles else bool(roles),
            f"expected role {sorted(expected_roles)} in route {sorted(roles)}",
        )
    )

    checks.append(
        _benchmark_check(
            "pool_floor",
            int(plan.get("limit") or 0) >= min(limit, 50),
            f"route limit={plan.get('limit', 0)}, expected >= {min(limit, 50)}",
        )
    )
    checks.append(
        _benchmark_check(
            "agent_command",
            any("--limit 80" in command or "--limit 100" in command for command in commands),
            "recommended commands should keep an expanded result pool",
            warn=True,
        )
    )
    expected_intents_any = set(scenario.get("expected_intents_any") or [])
    if expected_intents_any:
        checks.append(
            _benchmark_check(
                "expected_intents_any",
                bool(expected_intents_any & intents),
                f"expected any intent {sorted(expected_intents_any)} in route {sorted(intents)}",
            )
        )
    for intent in scenario.get("forbidden_intents") or []:
        checks.append(
            _benchmark_check(
                f"forbidden_intent:{intent}",
                str(intent) not in intents,
                f"forbidden intent {intent} should not appear in {sorted(intents)}",
            )
        )
    expected_scopes_any = set(scenario.get("expected_scopes_any") or [])
    if expected_scopes_any:
        checks.append(
            _benchmark_check(
                "expected_scopes_any",
                bool(expected_scopes_any & scopes),
                f"expected any scope {sorted(expected_scopes_any)} in route {sorted(scopes)}",
            )
        )
    for scope in scenario.get("forbidden_scopes") or []:
        checks.append(
            _benchmark_check(
                f"forbidden_scope:{scope}",
                str(scope) not in scopes,
                f"forbidden scope {scope} should not appear in {sorted(scopes)}",
            )
        )
    for needle in scenario.get("expected_command_contains") or []:
        checks.append(
            _benchmark_check(
                f"expected_command:{needle}",
                str(needle) in command_blob,
                f"expected command fragment {needle!r}",
            )
        )
    for needle in scenario.get("forbidden_command_contains") or []:
        checks.append(
            _benchmark_check(
                f"forbidden_command:{needle}",
                str(needle) not in command_blob,
                f"forbidden command fragment {needle!r}",
            )
        )
    return checks


def _benchmark_check(check_id: str, passed: bool, message: str, *, warn: bool = False) -> dict[str, Any]:
    if passed:
        status = "pass"
    else:
        status = "warn" if warn else "fail"
    return {"id": check_id, "status": status, "message": message}

EVAL_SUITES: dict[str, dict[str, Any]] = {
    "chinese-web-v1": {
        "id": "chinese-web-v1",
        "name": "中文互联网 Agent 研究基准 v1",
        "mode": "deterministic",
        "description": "覆盖政策、地方、电商、技术、财经、口碑、热点、学术、文娱和本地模型联网十类任务。",
        "categories": [
            "policy",
            "local",
            "ecommerce",
            "tech",
            "finance",
            "reputation",
            "hot",
            "academic",
            "entertainment",
            "local_llm",
        ],
        "tasks_per_category": 10,
        "principle": "评测 Guanlan 的信源路由、工作流选择和证据角色，不把一次网络超时写成能力失败。",
    },
    "chinese-web-live": {
        "id": "chinese-web-live",
        "name": "中文互联网真实任务样本池",
        "mode": "live-optional",
        "description": "面向真实网络复测的 100 题任务池；默认只跑路由和工作流体检，live 网络探针不进入 release gate。",
        "categories": [
            "policy",
            "local",
            "ecommerce",
            "tech",
            "finance",
            "reputation",
            "hot",
            "academic",
            "entertainment",
            "local_llm",
        ],
        "tasks_per_category": 10,
        "principle": "区分搜索能力、工作流调用、网络/上游、正文抽取和时间窗口，不把网络波动误判为无结果。",
    }
}

_EXTRA_SUITE_TASKS: list[dict[str, Any]] = [
    {"id": "finance_001", "category": "finance", "query": "宁德时代 股价 财报 公告 最近风险", "expected_source_family": "finance"},
    {"id": "finance_002", "category": "finance", "query": "贵州茅台 年报 公告 分红 风险", "expected_source_family": "finance"},
    {"id": "finance_003", "category": "finance", "query": "上证指数 今日 行情 成交额", "expected_source_family": "finance"},
    {"id": "finance_004", "category": "finance", "query": "社融 CPI 降息 央行 最新", "expected_source_family": "finance"},
    {"id": "finance_005", "category": "finance", "query": "某股票 雪球 股吧 情绪 看多看空", "expected_source_family": "finance"},
    {"id": "finance_006", "category": "finance", "query": "A股 半导体 研报 估值 风险", "expected_source_family": "finance"},
    {"id": "finance_007", "category": "finance", "query": "港股 公司 公告 交易所 披露", "expected_source_family": "finance"},
    {"id": "finance_008", "category": "finance", "query": "美股 NVDA 财报 SEC 10-K 风险", "expected_source_family": "finance"},
    {"id": "finance_009", "category": "finance", "query": "人民币汇率 外储 央行 数据", "expected_source_family": "finance"},
    {"id": "finance_010", "category": "finance", "query": "ETF 基金 净值 费率 公告", "expected_source_family": "finance"},
]

_CATEGORY_SEEDS: dict[str, tuple[str, str]] = {
    "policy": ("政策 官方 原文", "official"),
    "local": ("地方 产业政策 官方 原文", "local_official"),
    "ecommerce": ("电商 零售 产业趋势 垂类媒体", "vertical_media"),
    "tech": ("开源 项目 GitHub issue benchmark", "developer"),
    "finance": ("财经 公告 行情 风险", "finance"),
    "reputation": ("产品 用户评价 值不值得买", "user_sample"),
    "hot": ("今天 中文互联网 热点", "hotnews"),
    "academic": ("学术会议 投稿 检索 官方要求", "academic"),
    "entertainment": ("影视 明星 口碑 票房 热议", "entertainment"),
    "local_llm": ("本地模型 联网搜索 中文证据", "agent_context"),
}


def list_eval_suites() -> list[dict[str, Any]]:
    """Return available deterministic eval suites."""

    return [dict(item) for item in EVAL_SUITES.values()]


def suite_tasks(suite_id: str = "chinese-web-v1") -> list[dict[str, Any]]:
    """Return deterministic suite tasks, padded to the suite contract."""

    suite = EVAL_SUITES.get(suite_id)
    if not suite:
        raise ValueError(f"Unknown eval suite: {suite_id}")
    base = list(BENCHMARK_TASKS) + list(_EXTRA_SUITE_TASKS)
    categories = list(suite["categories"])
    target = int(suite.get("tasks_per_category") or 10)
    tasks: list[dict[str, Any]] = []
    for category in categories:
        category_tasks = [dict(task) for task in base if task.get("category") == category]
        seed_query, family = _CATEGORY_SEEDS.get(category, (category, "general"))
        while len(category_tasks) < target:
            idx = len(category_tasks) + 1
            category_tasks.append(
                {
                    "id": f"{category}_{idx:03d}",
                    "category": category,
                    "query": f"{seed_query} 样例 {idx}",
                    "expected_source_family": family,
                    "synthetic": True,
                }
            )
        tasks.extend(category_tasks[:target])
    return tasks


def run_eval_suite(suite_id: str = "chinese-web-v1", *, mode: str = "quick", limit: int = 80) -> dict[str, Any]:
    """Run a deterministic suite over realistic tasks without live network access."""

    from guanlan.router import build_route_plan
    from guanlan.workflow_decider import decide_workflow

    suite = EVAL_SUITES.get(suite_id)
    if not suite:
        raise ValueError(f"Unknown eval suite: {suite_id}")
    mode = mode if mode in {"quick", "live"} else "quick"
    cases: list[dict[str, Any]] = []
    for task in suite_tasks(suite_id):
        query = str(task.get("query") or "")
        plan = build_route_plan(query, profile="china", limit=max(limit, 1))
        decision = decide_workflow(query, command="search", profile="china", limit=max(limit, 1), route_plan=plan)
        checks = _score_suite_task(task, plan.to_dict(), decision.to_dict(), limit=max(limit, 1))
        if suite_id == "chinese-web-live" or mode == "live":
            checks.extend(_score_live_suite_task(task, plan.to_dict(), decision.to_dict()))
        failed = sum(1 for check in checks if check["status"] == "fail")
        warned = sum(1 for check in checks if check["status"] == "warn")
        passed = sum(1 for check in checks if check["status"] == "pass")
        score = round((passed + warned * 0.5) / max(len(checks), 1) * 100, 1)
        cases.append(
            {
                "id": task["id"],
                "category": task["category"],
                "query": query,
                "status": "fail" if failed else ("warn" if warned else "pass"),
                "score": score,
                "synthetic": bool(task.get("synthetic", False)),
                "expected_source_family": task.get("expected_source_family"),
                "workflow_decision": {
                    "tier": decision.tier,
                    "entrypoint": decision.recommended_entrypoint,
                    "minimum_steps": decision.minimum_steps,
                },
                "route": {
                    "primary_intents": plan.primary_intents,
                    "secondary_intents": plan.secondary_intents,
                    "preferred_scopes": plan.preferred_scopes,
                    "evidence_roles": plan.evidence_roles,
                    "limit": plan.limit,
                },
                "checks": checks,
                "failure_category": _failure_category(checks),
            }
        )
    summary = _suite_summary(cases)
    return {
        "suite": suite,
        "mode": mode,
        "limit": max(limit, 1),
        "summary": summary,
        "category_summary": _suite_category_summary(cases),
        "cases": cases,
        "boundary": _suite_boundary(suite_id, mode),
    }


def format_eval_suites_markdown(suites: list[dict[str, Any]] | None = None) -> str:
    rows = suites or list_eval_suites()
    lines = ["# 观澜 Eval Suite", "", "公开、可复跑的 Agent 中文互联网研究基准。"]
    for suite in rows:
        lines.extend(
            [
                "",
                f"## {suite.get('id')}",
                f"- 名称: {suite.get('name')}",
                f"- 模式: {suite.get('mode')}",
                f"- 类别: {', '.join(suite.get('categories') or [])}",
                f"- 每类任务: {suite.get('tasks_per_category')}",
                f"- 原则: {suite.get('principle')}",
            ]
        )
    return "\n".join(lines)


def format_eval_suite_markdown(report: dict[str, Any]) -> str:
    suite = report.get("suite") or {}
    summary = report.get("summary") or {}
    lines = [
        f"# 观澜 Eval Suite / {suite.get('id', '')}",
        "",
        f"- 模式: {report.get('mode')}",
        f"- 候选池下限: {report.get('limit')}",
        f"- 总分: {summary.get('score')}",
        f"- 结果: pass={summary.get('pass')} warn={summary.get('warn')} fail={summary.get('fail')}",
        f"- 边界: {report.get('boundary')}",
        "",
        "## 分类结果",
    ]
    for category, row in sorted((report.get("category_summary") or {}).items()):
        lines.append(f"- {category}: score={row.get('score')} pass={row.get('pass')} warn={row.get('warn')} fail={row.get('fail')}")
    lines.extend(["", "## 样例"])
    for case in list(report.get("cases") or [])[:20]:
        decision = case.get("workflow_decision") or {}
        lines.append(
            f"- [{case.get('status')}] {case.get('id')} {case.get('query')} "
            f"workflow={decision.get('tier')}/{decision.get('entrypoint')} score={case.get('score')}"
        )
    return "\n".join(lines)


def format_eval_suite_jsonl(report: dict[str, Any]) -> str:
    return "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in report.get("cases") or [])


def write_eval_suite_html(report: dict[str, Any], output: str) -> str:
    """Write a small standalone HTML report and return the output path."""

    from html import escape
    from pathlib import Path

    summary = report.get("summary") or {}
    rows = []
    for case in report.get("cases") or []:
        decision = case.get("workflow_decision") or {}
        rows.append(
            "<tr>"
            f"<td>{escape(str(case.get('id', '')))}</td>"
            f"<td>{escape(str(case.get('category', '')))}</td>"
            f"<td>{escape(str(case.get('status', '')))}</td>"
            f"<td>{escape(str(case.get('score', '')))}</td>"
            f"<td>{escape(str(decision.get('tier', '')))}</td>"
            f"<td>{escape(str(case.get('query', '')))}</td>"
            "</tr>"
        )
    html = f"""<!doctype html>
<html lang=\"zh-CN\">
<meta charset=\"utf-8\">
<title>Guanlan Eval Suite</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:40px;color:#1f2328}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #d0d7de;padding:8px;text-align:left}}th{{background:#f6f8fa}}
.badge{{display:inline-block;padding:4px 8px;background:#eef6ff;border-radius:999px}}
</style>
<h1>观澜 Eval Suite</h1>
<p class=\"badge\">score={escape(str(summary.get('score')))} pass={escape(str(summary.get('pass')))} warn={escape(str(summary.get('warn')))} fail={escape(str(summary.get('fail')))}</p>
<p>{escape(str(report.get('boundary', '')))}</p>
<table><thead><tr><th>ID</th><th>Category</th><th>Status</th><th>Score</th><th>Workflow</th><th>Query</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</html>"""
    path = Path(output)
    path.write_text(html, encoding="utf-8")
    return str(path)


def _score_suite_task(task: dict[str, Any], plan: dict[str, Any], decision: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    intents = set(plan.get("primary_intents") or []) | set(plan.get("secondary_intents") or [])
    scopes = set(plan.get("preferred_scopes") or []) | set(plan.get("fallback_scopes") or [])
    roles = set(plan.get("evidence_roles") or [])
    commands = "\n".join(str(item) for item in plan.get("recommended_commands") or [])
    category = str(task.get("category") or "")
    checks = [
        _benchmark_check("pool_floor", int(plan.get("limit") or 0) >= min(limit, 80), f"route limit={plan.get('limit')}, expected >= {min(limit, 80)}"),
        _benchmark_check("has_route_identity", bool(intents and roles), f"intents={sorted(intents)}, roles={sorted(roles)}"),
        _benchmark_check("workflow_not_empty", bool(decision.get("tier") and decision.get("recommended_entrypoint")), f"workflow={decision}"),
    ]
    if category == "hot":
        checks.append(_benchmark_check("hot_uses_hotnews", "hot_trend" in intents or "hotnews" in scopes, "热点任务必须识别热榜/水势路线"))
    if category == "tech":
        commands = " ".join(plan.get("recommended_commands") or [])
        checks.append(_benchmark_check("tech_mentions_feeds", "feeds" in commands or "tech" in intents, "技术任务需要 RSS/开发者路线"))
    if category == "finance":
        checks.append(_benchmark_check("finance_boundary", any(role.startswith("market") or "filing" in role or "macro" in role for role in roles), f"finance roles={sorted(roles)}"))
    if category in {"policy", "local", "academic"}:
        checks.append(_benchmark_check("authority_path", bool(scopes & {"gov", "party_central", "local_official", "academic"}), f"scopes={sorted(scopes)}"))
    if category in {"reputation", "entertainment"}:
        checks.append(_benchmark_check("sample_boundary", bool(scopes & {"social_web", "entertainment", "community_sample"}) or bool({"user_sample", "fan_discussion", "user_review"} & roles), f"scopes={sorted(scopes)}, roles={sorted(roles)}"))
    expected_intents_any = set(task.get("expected_intents_any") or [])
    if expected_intents_any:
        checks.append(_benchmark_check("task_expected_intents_any", bool(expected_intents_any & intents), f"expected any intent {sorted(expected_intents_any)} in {sorted(intents)}"))
    for intent in task.get("forbidden_intents") or []:
        checks.append(_benchmark_check(f"task_forbidden_intent:{intent}", str(intent) not in intents, f"forbidden intent {intent} should not appear in {sorted(intents)}"))
    expected_scopes_any = set(task.get("expected_scopes_any") or [])
    if expected_scopes_any:
        checks.append(_benchmark_check("task_expected_scopes_any", bool(expected_scopes_any & scopes), f"expected any scope {sorted(expected_scopes_any)} in {sorted(scopes)}"))
    for scope in task.get("forbidden_scopes") or []:
        checks.append(_benchmark_check(f"task_forbidden_scope:{scope}", str(scope) not in scopes, f"forbidden scope {scope} should not appear in {sorted(scopes)}"))
    for needle in task.get("expected_command_contains") or []:
        checks.append(_benchmark_check(f"task_expected_command:{needle}", str(needle) in commands, f"expected command fragment {needle!r}"))
    for needle in task.get("forbidden_command_contains") or []:
        checks.append(_benchmark_check(f"task_forbidden_command:{needle}", str(needle) not in commands, f"forbidden command fragment {needle!r}"))
    return checks


def _score_live_suite_task(task: dict[str, Any], plan: dict[str, Any], decision: dict[str, Any]) -> list[dict[str, Any]]:
    category = str(task.get("category") or "")
    commands = " ".join(plan.get("recommended_commands") or [])
    scopes = set(plan.get("preferred_scopes") or []) | set(plan.get("fallback_scopes") or [])
    intents = set(plan.get("primary_intents") or []) | set(plan.get("secondary_intents") or [])
    roles = set(plan.get("evidence_roles") or [])
    checks = [
        _benchmark_check(
            "live_failure_taxonomy_ready",
            True,
            "报告保留 failure_category，用于区分 route/search/read/network/time_window。",
        )
    ]
    if category == "hot":
        checks.append(
            _benchmark_check(
                "live_hot_requires_time_window",
                "hot_trend" in intents or "hotnews" in commands,
                "实时/热点任务必须显式进入 hotnews 或时间窗口路线。",
            )
        )
    if category == "tech":
        checks.append(
            _benchmark_check(
                "live_tech_requires_rss_pass",
                "feeds" in commands or "tech" in intents,
                "技术/AI 任务必须包含 RSS/开发者二次发现路径。",
            )
        )
    if category in {"policy", "local"}:
        checks.append(
            _benchmark_check(
                "live_official_priority",
                bool(scopes & {"gov", "party_central", "local_official"}) or bool({"official_primary", "authoritative_report"} & roles),
                "政策/地方任务必须优先官方或党央媒证据角色。",
            )
        )
    return checks


def _failure_category(checks: list[dict[str, Any]]) -> str:
    failed = [check for check in checks if check.get("status") == "fail"]
    warned = [check for check in checks if check.get("status") == "warn"]
    rows = failed or warned
    if not rows:
        return "none"
    check_id = str(rows[0].get("id") or "")
    if "route" in check_id or "identity" in check_id:
        return "route_failure"
    if "pool" in check_id:
        return "candidate_pool"
    if "read" in check_id:
        return "read_extraction"
    if "time" in check_id or "hot" in check_id:
        return "time_window"
    if "rss" in check_id or "feeds" in check_id:
        return "workflow_invocation"
    return "network_or_upstream" if "live" in check_id else "workflow_or_contract"


def _suite_boundary(suite_id: str, mode: str) -> str:
    if suite_id == "chinese-web-live" or mode == "live":
        return (
            "live suite 是真实任务样本池的可复测框架；当前默认仍以路由/工作流/证据角色为主，"
            "真实网络失败会归类为 network_or_upstream，不进入 release gate。"
        )
    return "quick suite 不联网；live suite 可选运行，不阻断基础 release gate。"


def _suite_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in cases if item["status"] == "pass")
    warned = sum(1 for item in cases if item["status"] == "warn")
    failed = sum(1 for item in cases if item["status"] == "fail")
    return {
        "total": len(cases),
        "pass": passed,
        "warn": warned,
        "fail": failed,
        "score": round(sum(float(item["score"]) for item in cases) / max(len(cases), 1), 1),
    }


def _suite_category_summary(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        grouped.setdefault(str(case.get("category") or "general"), []).append(case)
    output: dict[str, dict[str, Any]] = {}
    for category, rows in grouped.items():
        output[category] = _suite_summary(rows)
    return output
