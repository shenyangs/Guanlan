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


def test_route_plan_detects_policy_and_avoids_social_primary():
    plan = build_route_plan("人工智能 监管 政策 最新通知", profile="china")

    assert plan.primary_intents[0] == "policy"
    assert "gov" in plan.preferred_scopes
    assert "party_central" in plan.preferred_scopes
    assert "社交/内容平台" in plan.avoid_as_primary
    assert "baidu-rss" in plan.recommended_feeds
    assert any("--preset policy" in command for command in plan.recommended_commands)
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
    assert any("--preset entertainment" in command for command in plan.recommended_commands)
    assert "粉圈控评" in plan.avoid_as_primary
    assert any("宣发" in warning or "单平台" in warning for warning in plan.warnings)
    assert plan.advisor_recommended is True


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
    assert any(command.startswith("guanlan feeds curated") for command in tech.recommended_commands)
    assert any("RSS" in warning for warning in tech.warnings)
    assert generic.recommended_feeds == []
    assert "guanlan feeds wechat-rss --limit 80" in wechat.recommended_commands
    assert any(command.startswith("guanlan feeds curated") for command in reading.recommended_commands)


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


def test_route_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "route", "某产品 用户评价 值不值得买", "--json"]):
        main()

    captured = capsys.readouterr()
    assert '"primary_intents"' in captured.out
    assert "purchase_advice" in captured.out
