# -*- coding: utf-8 -*-
"""Tests for Guanlan demand routing and source taxonomy."""

from unittest.mock import patch

from guanlan.router import build_route_plan, format_route_plan_markdown
from guanlan.source_taxonomy import source_card_for_domain


def test_route_plan_detects_purchase_reputation_need():
    plan = build_route_plan("小米 YU7 用户评价 值不值得买", profile="china")

    assert "reputation" in plan.primary_intents + plan.secondary_intents
    assert "purchase_advice" in plan.primary_intents + plan.secondary_intents
    assert "social_web" in plan.preferred_scopes
    assert "zhihu.com" in plan.target_sites
    assert any("guanlan pulse" in command for command in plan.recommended_commands)
    assert plan.advisor_recommended is True
    assert any("社交" in warning or "购买" in warning for warning in plan.warnings)


def test_route_plan_detects_public_opinion_competitor_and_app_review_needs():
    opinion = build_route_plan("某产品 最近舆情 风评 被夸还是被骂", profile="china")
    crisis = build_route_plan("某品牌 公关危机 负面舆情 投诉爆发 道歉 澄清", profile="china")
    competitor = build_route_plan("某产品 竞品情报 竞争对手 定价变化 功能对比", profile="china")
    app_review = build_route_plan("某 App Store 评论 差评 评分变化 ASO", profile="china")

    assert "public_opinion" in opinion.primary_intents + opinion.secondary_intents
    assert "social_web" in opinion.preferred_scopes
    assert "market_review" in opinion.preferred_scopes
    assert "public_discussion" in opinion.evidence_roles
    assert any("guanlan pulse" in command for command in opinion.recommended_commands)
    assert "crisis_watch" in crisis.primary_intents + crisis.secondary_intents
    assert "risk_signal" in crisis.evidence_roles
    assert any("guanlan pulse" in command for command in crisis.recommended_commands)
    assert any("hotnews today" in command for command in crisis.recommended_commands)
    assert "competitor_watch" in competitor.primary_intents + competitor.secondary_intents
    assert "company_primary" in competitor.preferred_scopes
    assert "market_review" in competitor.preferred_scopes
    assert any("guanlan dossier" in command for command in competitor.recommended_commands)
    assert "app_review" in app_review.primary_intents + app_review.secondary_intents
    assert "market_review" in app_review.preferred_scopes
    assert "apps.apple.com" in app_review.target_sites
    assert any("--scope market_review" in command for command in app_review.recommended_commands)


def test_route_plan_detects_policy_and_avoids_social_primary():
    plan = build_route_plan("人工智能 监管 政策 最新通知", profile="china")

    assert plan.primary_intents[0] == "policy"
    assert "gov" in plan.preferred_scopes
    assert "party_central" in plan.preferred_scopes
    assert "社交/内容平台" in plan.avoid_as_primary
    assert "baidu-rss" in plan.recommended_feeds
    assert any("--scope gov" in command for command in plan.recommended_commands)
    assert plan.read_top >= 2


def test_route_plan_detects_academic_indexing_need():
    plan = build_route_plan("EI会议的所有标准和要求", profile="china")

    assert "academic" in plan.primary_intents + plan.secondary_intents
    assert "academic" in plan.preferred_scopes
    assert "elsevier.com" in plan.target_sites
    assert any("--preset academic" in command for command in plan.recommended_commands)
    assert any("学术会议" in warning or "检索" in warning for warning in plan.warnings)


def test_route_plan_detects_university_admissions_need():
    plan = build_route_plan("清华大学计算机系研究生招生的导师情况", profile="china")

    assert "university_admissions" in plan.primary_intents + plan.secondary_intents
    assert "university" in plan.preferred_scopes
    assert "academic" in plan.fallback_scopes
    assert "cs.tsinghua.edu.cn" in plan.target_sites
    assert "faculty_profile" in plan.evidence_roles
    assert any("--preset university" in command for command in plan.recommended_commands)
    assert "论文数据库首页" in plan.avoid_as_primary
    assert any("学术数据库不是主证据" in warning for warning in plan.warnings)


def test_route_plan_detects_entertainment_need():
    plan = build_route_plan("哪吒2 票房 口碑 豆瓣评分 最近热议", profile="china")

    assert "entertainment" in plan.primary_intents + plan.secondary_intents
    assert "entertainment" in plan.preferred_scopes
    assert "douban.com" in plan.target_sites
    assert "maoyan.com" in plan.target_sites
    assert any("--scope entertainment" in command for command in plan.recommended_commands)
    assert "粉圈控评" in plan.avoid_as_primary
    assert any("宣发" in warning or "单平台" in warning for warning in plan.warnings)
    assert plan.advisor_recommended is True


def test_route_plan_routes_magic_school_manga_to_entertainment_not_university():
    plan = build_route_plan("魔法学院日常漫画 治愈系 魔女", profile="china")

    assert "entertainment" in plan.primary_intents + plan.secondary_intents
    assert "university_admissions" not in plan.primary_intents
    assert "bangumi.tv" in plan.target_sites
    assert "pixiv.net" in plan.target_sites
    assert any("--scope entertainment" in command for command in plan.recommended_commands)


def test_route_plan_detects_global_entertainment_need():
    plan = build_route_plan("Taylor Swift 最新公开动态 新专辑 巡演", profile="china")

    assert "global_entertainment" in plan.primary_intents + plan.secondary_intents
    assert "global_entertainment" in plan.preferred_scopes
    assert "billboard.com" in plan.target_sites
    assert "variety.com" in plan.target_sites
    assert plan.backend_hint == ["duckduckgo", "bing"]
    assert any("--preset global_entertainment --profile english" in command for command in plan.recommended_commands)
    assert any("--scope global_entertainment" in command for command in plan.recommended_commands)
    assert "未证实恋情/巡演传闻" in plan.avoid_as_primary


def test_route_plan_detects_jp_kr_entertainment_need():
    plan = build_route_plan("BLACKPINK K-pop 最新回归 争议", profile="china")

    assert "jp_kr_entertainment" in plan.primary_intents + plan.secondary_intents
    assert "jp_kr_entertainment" in plan.preferred_scopes
    assert "soompi.com" in plan.target_sites
    assert "oricon.co.jp" in plan.target_sites
    assert plan.backend_hint == ["duckduckgo", "bing"]
    assert any("--preset jp_kr_entertainment --profile hybrid" in command for command in plan.recommended_commands)
    assert "机翻搬运" in plan.avoid_as_primary


def test_route_plan_detects_cross_region_entertainment_long_tail():
    western = build_route_plan("Dune 3 casting latest Deadline Variety report", profile="english")
    hbo = build_route_plan("HBO 最近有什么好看的新剧 烂番茄 评分", profile="china")
    kpop = build_route_plan("Jennie 退团 真的假的 韩媒 有正式回应吗", profile="china")

    assert "global_entertainment" in western.primary_intents + western.secondary_intents
    assert "global_entertainment" in hbo.primary_intents + hbo.secondary_intents
    assert hbo.backend_hint == ["duckduckgo", "bing"]
    assert "jp_kr_entertainment" in kpop.primary_intents + kpop.secondary_intents
    assert kpop.backend_hint == ["duckduckgo", "bing"]


def test_route_plan_detects_security_weather_sports_science_gaps():
    cve = build_route_plan("OpenSSL CVE 最新 漏洞 影响 版本 修复", profile="china")
    weather = build_route_plan("台风 路径 最新 中央气象台 日本气象厅", profile="china")
    sports = build_route_plan("梅西 今天比赛 数据 伤病 最新", profile="china")
    science = build_route_plan("詹姆斯韦伯 发现 外星生命 真的假的 NASA", profile="china")

    assert "cybersecurity" in cve.primary_intents + cve.secondary_intents
    assert cve.risk_level == "high"
    assert "cybersecurity" in cve.preferred_scopes
    assert any("--scope cybersecurity" in command for command in cve.recommended_commands)
    assert "weather_disaster" in weather.primary_intents + weather.secondary_intents
    assert weather.risk_level == "high"
    assert "weather_disaster" in weather.preferred_scopes
    assert "sports" in sports.primary_intents + sports.secondary_intents
    assert "sports" in sports.preferred_scopes
    assert "science" in science.primary_intents + science.secondary_intents
    assert "science" in science.preferred_scopes


def test_route_plan_handles_long_tail_agent_auto_regressions():
    legal = build_route_plan("劳动仲裁 加班费 证据 判例 最新", profile="china")
    fraud = build_route_plan("收到ETC短信 链接 骗局 怎么办", profile="china")
    charity = build_route_plan("某基金会 捐款 去向 透明度 查询", profile="china")
    game = build_route_plan("黑神话悟空 DLC 爆料 销量 Steam", profile="china")
    venue_rental = build_route_plan("学校 体育馆 出租 招租 江苏 常州", profile="china")
    secondhand = build_route_plan("V100 326 二手价格", profile="china")

    assert "legal_judicial" in legal.primary_intents + legal.secondary_intents
    assert "cybersecurity" in fraud.primary_intents + fraud.secondary_intents
    assert "reputation" in charity.primary_intents + charity.secondary_intents
    assert "finance" not in charity.primary_intents + charity.secondary_intents
    assert not any(command.startswith("guanlan stock") for command in charity.recommended_commands)
    assert "entertainment" in game.primary_intents + game.secondary_intents
    assert "sports" not in venue_rental.primary_intents + venue_rental.secondary_intents
    assert "ecommerce" in secondhand.primary_intents + secondhand.secondary_intents
    assert "company_primary" not in secondhand.primary_intents + secondhand.secondary_intents


def test_route_plan_handles_telemetry_ai_company_terms():
    figma_ai = build_route_plan("Firefly Boards Figma AI 可编辑", profile="china")
    product_hunt = build_route_plan("Product Hunt AI工具 2026", profile="china")
    character = build_route_plan("Character.ai valuation users 2025 2026 Google acquisition", profile="china")
    macro = build_route_plan("2026 recession GDP inflation", profile="china")

    assert "tech" in figma_ai.primary_intents + figma_ai.secondary_intents
    assert "tech" in product_hunt.primary_intents + product_hunt.secondary_intents
    assert "company_primary" in character.primary_intents + character.secondary_intents
    assert "global_industry" in character.primary_intents + character.secondary_intents
    assert "finance_macro" in macro.primary_intents + macro.secondary_intents


def test_route_plan_recommends_direct_reads_for_live_nba_lookup():
    plan = build_route_plan("NBA季后赛2026年首轮战绩比分", profile="china")

    assert plan.primary_intents[0] == "sports"
    assert any(command.startswith("guanlan read ") and "espn.com/nba/story" in command for command in plan.recommended_commands)
    assert any("nba.com/games" in command for command in plan.recommended_commands)
    read_index = next(idx for idx, command in enumerate(plan.recommended_commands) if command.startswith("guanlan read "))
    search_index = next(idx for idx, command in enumerate(plan.recommended_commands) if command.startswith("guanlan search "))
    assert read_index < search_index


def test_route_plan_detects_finance_layers_and_commands():
    plan = build_route_plan("宁德时代 股价 财报 公告 最近风险", profile="china")
    intents = plan.primary_intents + plan.secondary_intents

    assert "finance" in intents
    assert "finance_quote" in intents
    assert "finance_disclosure" in intents
    assert "finance_disclosure" in plan.preferred_scopes
    assert "finance_quote" in plan.preferred_scopes
    assert "company_filing" in plan.evidence_roles
    assert "market_quote" in plan.evidence_roles
    assert plan.risk_level == "high"
    assert "社交荐股" in plan.avoid_as_primary
    assert any(command.startswith("guanlan stock plan") for command in plan.recommended_commands)
    assert any(command.startswith("guanlan stock quote") for command in plan.recommended_commands)
    assert any(command.startswith("guanlan stock detail") for command in plan.recommended_commands)
    assert any("--scope finance_disclosure" in command for command in plan.recommended_commands)
    assert any(command.startswith("guanlan read ") and ("cninfo.com.cn" in command or "sse.com.cn" in command) for command in plan.recommended_commands)
    assert any("投资建议" in warning for warning in plan.warnings)


def test_route_plan_detects_macro_and_sentiment_finance_needs():
    macro = build_route_plan("社融 CPI 降息 央行 最新", profile="china")
    sentiment = build_route_plan("某股票 雪球 股吧 看多看空 情绪", profile="china")

    assert "finance_macro" in macro.primary_intents + macro.secondary_intents
    assert "finance_macro" in macro.preferred_scopes
    assert "macro_data" in macro.evidence_roles
    assert any("--scope finance_macro" in command for command in macro.recommended_commands)
    assert "finance_sentiment" in sentiment.primary_intents + sentiment.secondary_intents
    assert "finance_sentiment" in sentiment.preferred_scopes
    assert "sentiment_sample" in sentiment.evidence_roles
    assert any("--scope finance_sentiment" in command for command in sentiment.recommended_commands)
    assert any("hotboard:catalog:finance" in command for command in sentiment.recommended_commands)


def test_route_plan_injects_hotboard_catalog_for_hot_queries():
    plan = build_route_plan("今天 财经市场 热点", profile="china")

    assert any("hotboard:catalog" in command for command in plan.recommended_commands)
    assert any("hotboard:snapshots:" in command for command in plan.recommended_commands)


def test_route_plan_detects_career_ecommerce_podcast_test_prep():
    career = build_route_plan("字节 AI 产品经理 校招 薪资 面经", profile="china")
    ecommerce = build_route_plan("今年抖音小店还值得做吗 真实商家反馈", profile="china")
    podcast = build_route_plan("最近 有哪些讲 AI 创业 的中文播客 小宇宙", profile="china")
    exam = build_route_plan("雅思 口语 2026 题库 机经 靠谱吗", profile="china")

    assert "career" in career.primary_intents + career.secondary_intents
    assert "career" in career.preferred_scopes
    assert "ecommerce" in ecommerce.primary_intents + ecommerce.secondary_intents
    assert "ecommerce" in ecommerce.preferred_scopes
    assert "podcast" in podcast.primary_intents + podcast.secondary_intents
    assert "podcast" in podcast.preferred_scopes
    assert "test_prep" in exam.primary_intents + exam.secondary_intents
    assert "test_prep" in exam.preferred_scopes


def test_route_plan_does_not_treat_bytedance_product_pricing_as_career():
    plan = build_route_plan("豆包 付费 订阅 字节跳动", profile="china")

    assert "career" not in plan.primary_intents
    assert "company_primary" in plan.primary_intents + plan.secondary_intents
    assert "company_primary" in plan.preferred_scopes


def test_route_plan_detects_english_company_primary_need():
    plan = build_route_plan("OpenAI API pricing release notes", profile="english")

    assert plan.primary_intents[0] == "company_primary"
    assert "company_primary" in plan.preferred_scopes
    assert "developer" in plan.preferred_scopes
    assert "company_primary" in plan.evidence_roles
    assert any("--preset company --profile english" in command for command in plan.recommended_commands)


def test_route_plan_keeps_cjk_ai_query_in_china_context_without_explicit_profile():
    plan = build_route_plan("AI 相关内容")

    assert plan.backend_hint == ["baidu", "bing", "duckduckgo"]
    assert any("--profile china" in command for command in plan.recommended_commands)


def test_route_plan_detects_english_policy_need():
    plan = build_route_plan("AI regulation NIST standard policy", profile="english")

    assert "global_policy" in plan.primary_intents + plan.secondary_intents
    assert "global_official" in plan.preferred_scopes
    assert "global_news" in plan.preferred_scopes
    assert any("--preset global_policy --profile english" in command for command in plan.recommended_commands)


def test_route_plan_detects_standards_compliance_need():
    plan = build_route_plan("SOC2 合规认证标准和审计要求", profile="china")

    assert "standards_compliance" in plan.primary_intents + plan.secondary_intents
    assert "global_official" in plan.preferred_scopes
    assert "standard_original" in plan.evidence_roles
    assert "厂商单方合规声明" in plan.avoid_as_primary
    assert any("--scope global_official" in command for command in plan.recommended_commands)


def test_route_plan_detects_medical_health_need():
    plan = build_route_plan("某药品 FDA 临床治疗指南和副作用", profile="china")

    assert "medical_health" in plan.primary_intents + plan.secondary_intents
    assert plan.risk_level == "high"
    assert "clinical_guideline" in plan.evidence_roles
    assert any("医疗健康" in warning for warning in plan.warnings)


def test_route_plan_detects_legal_judicial_need():
    plan = build_route_plan("合同侵权诉讼 判决依据和司法解释", profile="china")

    assert "legal_judicial" in plan.primary_intents + plan.secondary_intents
    assert plan.risk_level == "high"
    assert "statute_original" in plan.evidence_roles
    assert "gov" in plan.preferred_scopes


def test_route_plan_recommends_rss_sources_by_need():
    wechat = build_route_plan("今天微信公众号有什么 AI 热文", profile="china")
    reading = build_route_plan("最近有什么值得读的 Agent 技术文章", profile="china")
    tech = build_route_plan("Python Agent 框架 对比 github issue", profile="china")
    generic = build_route_plan("帮我查一下某公司情况", profile="china")

    assert "wechat-rss" in wechat.recommended_feeds
    assert "baidu-rss" in wechat.recommended_feeds
    assert "curated" in reading.recommended_feeds
    assert "curated" in tech.recommended_feeds
    assert "ai-official" in tech.recommended_feeds
    assert "ai-media" in tech.recommended_feeds
    assert "ai-vertical" in tech.recommended_feeds
    assert any(command.startswith("guanlan feeds curated") for command in tech.recommended_commands)
    assert "guanlan feeds ai-official --limit 80" in tech.recommended_commands
    assert "guanlan feeds ai-media --limit 80" in tech.recommended_commands
    assert not any("feeds aihot" in command or "feeds ai-vertical" in command for command in tech.recommended_commands)
    assert any("RSS" in warning for warning in tech.warnings)
    assert generic.recommended_feeds == []
    assert "guanlan feeds wechat-rss --limit 80" in wechat.recommended_commands
    assert any(command.startswith("guanlan feeds curated") for command in reading.recommended_commands)


def test_route_plan_detects_wps_office_market_radar():
    plan = build_route_plan("WPS AI PPT Agent 办公选题 最近热点", profile="china")
    intents = plan.primary_intents + plan.secondary_intents

    assert "wps_office" in intents
    assert "wps_office" in plan.preferred_scopes
    assert "wps_ai" in plan.wps_lanes
    assert "claw_agent" in plan.wps_lanes
    assert "WPS AI" in plan.wps_semantic_matches["brand_terms"]
    assert "business" in plan.preferred_scopes
    assert "tech_dev" in plan.preferred_scopes
    assert "wps.cn" in plan.target_sites
    assert "36kr.com" in plan.target_sites
    assert "company_primary" in plan.evidence_roles
    assert "industry_report" in plan.evidence_roles
    assert "user_sample" in plan.evidence_roles
    assert "curated" in plan.recommended_feeds
    assert "ai-official" in plan.recommended_feeds
    assert "ai-media" in plan.recommended_feeds
    assert "ai-vertical" in plan.recommended_feeds
    assert "wechat-rss" in plan.recommended_feeds
    assert plan.read_top >= 5
    assert plan.advisor_recommended is True
    assert "品牌通稿单源" in plan.avoid_as_primary
    assert "institution_rollout" in plan.evidence_roles
    assert any("职场效率" in query for query in plan.query_variants)
    assert any("Gamma Canva" in query for query in plan.query_variants)
    assert any("国产 AI PPT 工具 横评" in query for query in plan.query_variants)
    assert any("--scope wps_office" in command for command in plan.recommended_commands)
    assert any("feeds curated" in command for command in plan.recommended_commands)
    assert "guanlan feeds ai-official --limit 80" in plan.recommended_commands
    assert "guanlan feeds ai-media --limit 80" in plan.recommended_commands
    assert not any("feeds aihot" in command or "feeds ai-vertical" in command for command in plan.recommended_commands)


def test_route_plan_separates_wps_subroute_query_variants():
    lingxi = build_route_plan("WPS 灵犀", profile="china")
    wps365 = build_route_plan("WPS 365", profile="china")
    wps = build_route_plan("WPS", profile="china")

    assert any("Office 替代" in query for query in wps.query_variants)
    assert any("国产办公软件" in query for query in wps.query_variants)
    assert any("Microsoft Office" in query for query in wps.query_variants)
    assert "lingxi" in lingxi.wps_lanes
    assert any("AI办公全能伙伴" in query for query in lingxi.query_variants)
    assert any("语音文档对话" in query for query in lingxi.query_variants)
    assert any("原生 Office 智能体" in query for query in lingxi.query_variants)
    assert any("Microsoft Copilot" in query for query in lingxi.query_variants)
    assert any("企业大脑" in query for query in wps365.query_variants)
    assert any("Microsoft 365 Copilot" in query for query in wps365.query_variants)


def test_route_plan_detects_wps_lingxi_claw_semantics_without_wps_prefix():
    plan = build_route_plan("灵犀 Claw MCP skill 数字员工", profile="china")
    intents = plan.primary_intents + plan.secondary_intents

    assert "wps_office" in intents
    assert {"lingxi", "claw_agent"} <= set(plan.wps_lanes)
    assert any("MCP skill 工具调用" in query for query in plan.query_variants)
    assert any("AI替你干活" in query for query in plan.query_variants)


def test_route_plan_detects_ai_office_adjacent_but_not_generic_skill_query():
    adjacent = build_route_plan("AI 笔记 知识库 Agent", profile="china")
    generic = build_route_plan("Python token skill", profile="china")
    pure_agent = build_route_plan("DeepSeek-V4 智能体 Agent 最新", profile="china")

    assert "wps_office" in adjacent.primary_intents + adjacent.secondary_intents
    assert "ai_office_adjacent" in adjacent.wps_lanes
    assert any("AI 笔记 AI 知识库 KaaS" in query for query in adjacent.query_variants)
    assert "wps_office" not in generic.primary_intents + generic.secondary_intents
    assert "wps_office" not in pure_agent.primary_intents + pure_agent.secondary_intents
    assert "tech" in pure_agent.primary_intents + pure_agent.secondary_intents


def test_route_plan_covers_wps_product稿_details_without_overrouting_generic_terms():
    html = build_route_plan("WPS HTML素材 代码嵌入 交互式演示", profile="china")
    pad = build_route_plan("WPS for Pad iPadOS App Store 国际版", profile="china")
    note = build_route_plan("WPS笔记 龙虾直写 MCP CLI", profile="china")
    generic_mobile = build_route_plan("App Store iCloud Apple Pencil 最新", profile="china")
    generic_gov = build_route_plan("政务服务 交通出行 实时共享", profile="china")

    assert "wps_office" in html.primary_intents + html.secondary_intents
    assert any("HTML素材" in query and "交互式演示" in query for query in html.query_variants)
    assert "wps_office" in pad.primary_intents + pad.secondary_intents
    assert any("WPS for Pad iPadOS App Store 国际版" in query for query in pad.query_variants)
    assert "wps_office" in note.primary_intents + note.secondary_intents
    assert any("WPS笔记" in query and "龙虾直写" in query for query in note.query_variants)
    assert "wps_office" not in generic_mobile.primary_intents + generic_mobile.secondary_intents
    assert "wps_office" not in generic_gov.primary_intents + generic_gov.secondary_intents


def test_route_plan_detects_embodied_ai_industry_need():
    plan = build_route_plan("人形机器人 智元 宇树 傅利叶", profile="china")

    assert "industry" in plan.primary_intents + plan.secondary_intents
    assert "tech" in plan.primary_intents + plan.secondary_intents
    assert "business" in plan.preferred_scopes
    assert "tech_dev" in plan.preferred_scopes + plan.fallback_scopes
    assert "ai" in plan.domains


def test_format_route_plan_markdown_is_agent_readable():
    plan = build_route_plan("Python Agent 框架 对比 github issue")
    text = format_route_plan_markdown(plan)

    assert "# 观澜路由计划" in text
    assert "技术" not in text or "tech" in text
    assert "证据角色" in text
    assert "推荐 RSS" in text
    assert "建议命令" in text
    assert "查询改写" in text


def test_source_card_separates_authority_and_sample_value():
    gov = source_card_for_domain("www.gov.cn")
    zhihu = source_card_for_domain("zhihu.com")

    assert gov.authority_score > zhihu.authority_score
    assert zhihu.sample_value > gov.sample_value
    assert "sample_bias" in zhihu.risk_tags


def test_source_card_marks_entertainment_sources_as_sample_heavy():
    douban = source_card_for_domain("movie.douban.com")
    maoyan = source_card_for_domain("piaofang.maoyan.com")
    billboard = source_card_for_domain("billboard.com")
    soompi = source_card_for_domain("soompi.com")

    assert douban.scope_id == "entertainment"
    assert douban.sample_value > douban.authority_score
    assert "rating" in douban.content_roles
    assert maoyan.scope_id == "entertainment"
    assert "box_office" in maoyan.content_roles
    assert billboard.scope_id == "global_entertainment"
    assert "music_chart" in billboard.content_roles
    assert soompi.scope_id == "jp_kr_entertainment"
    assert "translation_layer" in soompi.risk_tags


def test_source_card_marks_finance_layers():
    cninfo = source_card_for_domain("www.cninfo.com.cn")
    quote = source_card_for_domain("quote.eastmoney.com")
    xueqiu = source_card_for_domain("xueqiu.com")

    assert cninfo.scope_id == "finance_disclosure"
    assert "company_filing" in cninfo.content_roles
    assert cninfo.authority_score > xueqiu.authority_score
    assert quote.scope_id == "finance_quote"
    assert "market_quote" in quote.content_roles
    assert "sentiment_sample" in xueqiu.content_roles
    assert "sample_bias" in xueqiu.risk_tags


def test_source_card_marks_wps_office_layers():
    wps365 = source_card_for_domain("365.wps.cn")
    community = source_card_for_domain("bbs.wps.cn")

    assert wps365.scope_id == "wps_office"
    assert "official_specs" in wps365.content_roles
    assert "product_update" in wps365.content_roles
    assert community.scope_id == "wps_office"
    assert community.sample_value > community.authority_score
    assert "sample_bias" in community.risk_tags


def test_source_card_marks_app_store_reviews_as_samples():
    app_store = source_card_for_domain("apps.apple.com")
    google_play = source_card_for_domain("play.google.com")

    assert app_store.scope_id == "market_review"
    assert "app_store_review" in app_store.content_roles
    assert app_store.sample_value > app_store.authority_score
    assert "region_version_dependent" in app_store.risk_tags
    assert google_play.scope_id == "market_review"
    assert "version_feedback" in google_play.content_roles


def test_route_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "route", "某产品 用户评价 值不值得买", "--json"]):
        main()

    captured = capsys.readouterr()
    assert '"primary_intents"' in captured.out
    assert "purchase_advice" in captured.out
