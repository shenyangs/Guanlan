# -*- coding: utf-8 -*-
"""Tests for Guanlan light/heavy workflow decisions."""

from guanlan.workflow_decider import (
    DIRECT,
    GUIDED,
    INVESTIGATE,
    build_agent_plan,
    decide_workflow,
    format_agent_plan_markdown,
    format_workflow_decision_markdown,
)


def test_simple_lookup_stays_direct_and_light():
    decision = decide_workflow("观澜 官网", command="search", profile="china")

    assert decision.tier == DIRECT
    assert decision.recommended_entrypoint == "search"
    assert decision.do_not_overthink is True
    assert decision.recommended_limit >= 80
    assert "research" not in decision.command_path[:1]


def test_policy_research_uses_guided_workflow():
    decision = decide_workflow("人工智能 监管 政策 最新通知", command="search", profile="china")

    assert decision.tier == GUIDED
    assert decision.recommended_entrypoint == "search"
    assert "route" in decision.command_path
    assert "scoped search" in decision.command_path
    assert "read" in decision.command_path
    assert decision.recommended_limit >= 80
    assert decision.recommended_read_top == 0


def test_explicit_compare_uses_investigate_tier():
    decision = decide_workflow("OpenAI Claude Gemini 对比 价格 风险", command="search", profile="china")

    assert decision.tier == INVESTIGATE
    assert decision.recommended_entrypoint == "compare"
    assert decision.minimum_steps >= 3
    assert "WebFetch" in " ".join(decision.fallback_policy)


def test_tech_query_reminds_rss_without_forcing_basic_search_heavy():
    decision = decide_workflow("Python Agent 框架 对比 github issue", command="research", profile="china")

    assert decision.tier in {GUIDED, INVESTIGATE}
    assert "feeds" in decision.command_path or any(
        "RSS" in item or "feeds" in item or "精品内容流" in item for item in decision.fallback_policy
    )


def test_stock_quote_lookup_uses_stock_entrypoint_without_overthinking():
    decision = decide_workflow("贵州茅台 股价", command="search", profile="china")

    assert decision.tier == DIRECT
    assert decision.recommended_entrypoint == "stock"
    assert decision.do_not_overthink is True
    assert "stock quote" in " ".join(decision.command_path)


def test_stock_risk_research_starts_with_stock_layer():
    decision = decide_workflow("宁德时代 股价 财报 公告 最近风险", command="search", profile="china")

    assert decision.tier == GUIDED
    assert decision.recommended_entrypoint == "stock"
    assert decision.recommended_read_top >= 5
    assert decision.command_path[:2] == ["stock plan", "stock detail/quote"]


def test_market_intelligence_queries_use_guided_workflow():
    decision = decide_workflow("某品牌 公关危机 负面舆情 投诉爆发", command="search", profile="china")
    app_review = decide_workflow("某 App Store 评论 差评 评分变化", command="search", profile="china")

    assert decision.tier == GUIDED
    assert decision.recommended_entrypoint == "search"
    assert "crisis_watch" in decision.route_intents
    assert decision.recommended_limit >= 80
    assert app_review.tier == GUIDED
    assert "app_review" in app_review.route_intents


def test_workflow_markdown_is_agent_readable():
    decision = decide_workflow("某公司 档案 风险 舆情", command="search", profile="china")
    text = format_workflow_decision_markdown(decision)

    assert "观澜工作流分流" in text
    assert "建议执行链路" in text
    assert "不要过度思考" in text
    assert "300000 ms" in text
    assert "Timeout 单位契约" in text
    assert "裸数字" in text


def test_workflow_json_exposes_timeout_seconds_and_ms():
    decision = decide_workflow("某公司 档案 风险 舆情", command="search", profile="china")
    payload = decision.to_dict()

    assert payload["timeout_budget_seconds"] == 300
    assert payload["timeout_budget_ms"] == 300000
    assert any("timeout_ms" in item for item in payload["timeout_unit_contract"])


def test_agent_plan_keeps_simple_lookup_low_choice():
    plan = build_agent_plan("观澜 官网", profile="china")
    payload = plan.to_dict()

    assert plan.primary_command.startswith("guanlan search")
    assert payload["decision"]["do_not_overthink"] is True
    assert payload["agent_next_steps"][0]["command"] == plan.primary_command
    assert len(payload["recommended_commands"]) <= 3


def test_agent_plan_fresh_wps_keeps_hotnews_and_feeds_visible():
    plan = build_agent_plan("WPS AI 灵犀 Claw AI PPT AI笔记 AI知识库 最近热点", mode="fresh", profile="china")
    commands = [item.command for item in plan.recommended_commands]

    assert plan.primary_command == "guanlan hotnews today --limit 80 --trends"
    assert any(command == "guanlan hotnews today --limit 80 --trends" for command in commands)
    assert any(command == "guanlan feeds curated --category ai --limit 80" for command in commands)
    assert any("--scope wps_office" in command for command in commands)
    assert not any(command.startswith("guanlan research") for command in commands)
    assert plan.recommended_commands[0].role == "primary"
    assert plan.recommended_commands[0].required is True
    assert len(commands) <= 5


def test_agent_plan_deep_compare_uses_investigate_primary():
    plan = build_agent_plan("OpenAI Claude Gemini 对比 价格 风险", mode="deep", profile="china")

    assert plan.primary_command.startswith("guanlan investigate")
    assert plan.recommended_commands[0].timeout_budget_ms == 300000
    assert plan.decision["recommended_entrypoint"] == "compare"


def test_agent_plan_tech_latest_keeps_hotnews_feeds_and_tech_research():
    plan = build_agent_plan("AI Agent 框架 对比 GitHub issue 最新", profile="china")
    commands = [item.command for item in plan.recommended_commands]

    assert plan.primary_command.startswith("guanlan search")
    assert "--scope tech_dev" in plan.primary_command
    assert "guanlan hotnews today --limit 80 --trends" in commands
    assert "guanlan feeds curated --category ai --limit 80" in commands
    assert not any(command.startswith("guanlan research") for command in commands)


def test_agent_plan_ai_model_comparison_includes_official_site_searches():
    plan = build_agent_plan("好像这次 GLM 5.2 的声量比 kimi 2.7 高，前者强在哪儿", profile="china")
    commands = [item.command for item in plan.recommended_commands]

    assert "--scope tech_dev" in plan.primary_command
    assert any("--site zhipuai.cn" in command for command in commands)
    assert any("--site moonshot.cn" in command for command in commands)
    assert any("feeds curated --category ai" in command for command in commands)


def test_agent_plan_finance_risk_keeps_stock_and_finance_research():
    plan = build_agent_plan("宁德时代 股价 财报 公告 最近风险", profile="china")
    commands = [item.command for item in plan.recommended_commands]

    assert plan.primary_command.startswith("guanlan stock plan")
    assert any("--scope finance_quote" in command for command in commands)
    assert any(command.startswith("guanlan stock detail") for command in commands)
    assert not any(command.startswith("guanlan research") for command in commands)


def test_agent_plan_cross_industry_matrix_has_safe_primary_commands():
    cases = {
        "图书": ("刘慈欣 新书 书评 推荐", "guanlan search"),
        "文娱": ("哪吒2 票房 口碑 豆瓣评分 最新", "--scope entertainment"),
        "民生": ("医保 异地就医 政策 办理 最新", "--scope gov"),
        "高校": ("清华大学 计算机系 研究生招生 导师", "--scope university"),
        "学术": ("EI会议 投稿 检索 要求", "--scope academic"),
        "农业": ("农业农村部 玉米 病虫害 防控 政策 最新", "--scope gov"),
        "政策": ("人工智能 监管 政策 最新通知", "--scope gov"),
    }

    for _label, (query, expected) in cases.items():
        plan = build_agent_plan(query, profile="china")
        assert expected in plan.primary_command
        assert plan.recommended_commands[0].command == plan.primary_command
        assert len(plan.recommended_commands) <= 5


def test_agent_plan_long_tail_regressions_do_not_blame_agent():
    fraud = build_agent_plan("收到ETC短信 链接 骗局 怎么办", profile="china")
    charity = build_agent_plan("某基金会 捐款 去向 透明度 查询", profile="china")
    podcast = build_agent_plan("AI 创业 播客 小宇宙 推荐", profile="china")
    bank = build_agent_plan("银行 理财 净值 回撤 风险 最新", profile="china")
    archive = build_agent_plan("本地 archive 查 观澜 WPS 资料", profile="china")
    url_read = build_agent_plan("读一下 mp.weixin.qq.com/s/abc 公众号文章", profile="china")

    assert "--scope cybersecurity" in fraud.primary_command
    assert not any("known-exploited" in item.command or "openssl.org/news/secadv" in item.command for item in fraud.recommended_commands)
    assert "--scope social_web" in charity.primary_command
    assert not any(item.command.startswith("guanlan stock") for item in charity.recommended_commands)
    assert "--scope podcast" in podcast.primary_command
    assert any("feeds curated-sources" in item.command for item in podcast.recommended_commands)
    assert "--scope finance_research" in bank.primary_command
    assert not any(item.command.startswith("guanlan stock") for item in bank.recommended_commands)
    assert archive.primary_command.startswith("guanlan archive context")
    assert len(archive.recommended_commands) <= 2
    assert url_read.primary_command.startswith("guanlan read https://mp.weixin.qq.com/s/abc")


def test_agent_plan_telemetry_regressions_keep_auto_mode_broad_and_precise():
    figma_ai = build_agent_plan("Firefly Boards Figma AI 可编辑", profile="china")
    character = build_agent_plan("Character.ai valuation users 2025 2026 Google acquisition", profile="china")
    palantir = build_agent_plan("Palantir AIP 2026 revenue valuation", profile="china")
    macro = build_agent_plan("2026 recession GDP inflation", profile="china")
    gov_site = build_agent_plan("site:gov.cn 商务部 外卖 餐饮 配送", profile="china")
    nvidia = build_agent_plan("NVIDIA stock price earnings guidance 2026", profile="china")
    secondhand = build_agent_plan("V100 326 二手价格", profile="china")
    social_style = build_agent_plan("小红书 无名 风格 女生 可爱 文艺", profile="china")
    pure_agent = build_agent_plan("DeepSeek-V4 智能体 Agent 最新", profile="china")
    ai_hardware = build_agent_plan("华为 昇腾 910B 910C 性能 对标", profile="china")
    companion_robot = build_agent_plan("pet companion robot market 2025 2026", profile="china")

    assert "--scope tech_dev" in figma_ai.primary_command
    assert any("feeds curated --category ai" in item.command for item in figma_ai.recommended_commands)
    assert "--scope company_primary" in character.primary_command
    assert not any("--site openai.com" in item.command for item in character.recommended_commands)
    assert "--scope company_primary" in palantir.primary_command
    assert not any("--site github.com" in item.command for item in palantir.recommended_commands)
    assert macro.primary_command.startswith("guanlan search")
    assert "--scope finance_macro" in macro.primary_command
    assert not macro.primary_command.startswith("guanlan stock")
    assert not any("stats.gov.cn" in item.command or "pbc.gov.cn" in item.command for item in macro.recommended_commands)
    assert "--site gov.cn" in gov_site.primary_command
    assert not any("--preset policy" in item.command or "feeds curated" in item.command for item in gov_site.recommended_commands)
    assert nvidia.primary_command.startswith("guanlan stock plan")
    assert any("--scope finance_quote" in item.command for item in nvidia.recommended_commands)
    assert not any("--site cninfo.com.cn" in item.command for item in nvidia.recommended_commands)
    assert "--scope ecommerce" in secondhand.primary_command
    assert "--scope social_web" in social_style.primary_command
    assert "--scope tech_dev" in pure_agent.primary_command
    assert "--preset wps_office" not in pure_agent.primary_command
    assert "--scope tech_dev" in ai_hardware.primary_command
    assert any("--scope industry_analysis" in item.command for item in companion_robot.recommended_commands)
    assert not any("--site latepost.com" in item.command for item in companion_robot.recommended_commands)


def test_agent_plan_exposes_silent_auto_repair_contract():
    company = build_agent_plan("Character.ai valuation users 2025 2026 Google acquisition", profile="china")
    site = build_agent_plan("site:gov.cn 工信部 人工智能 政策 2026", profile="china")
    url = build_agent_plan("读一下 https://example.com/article", profile="china")

    payload = company.to_dict()
    assert payload["quality_tripwires"]
    assert payload["silent_repair_commands"]
    assert any("preferred_hit_count" in item["signal"] for item in payload["quality_tripwires"])
    assert any("不要说 Guanlan 崩了" in item for item in payload["auto_repair_policy"])
    assert "--scope company_primary" in company.primary_command
    assert not any("--site openai.com" in item.command for item in company.silent_repair_commands)
    assert site.silent_repair_commands
    assert all("--preset policy" not in item.command and "feeds curated" not in item.command for item in site.silent_repair_commands)
    assert any("site:" in item["signal"] or "site_filter" in item["signal"] for item in site.quality_tripwires)
    assert any(item.command.startswith("guanlan diagnose page https://example.com/article") for item in url.silent_repair_commands)


def test_agent_plan_keeps_research_out_of_default_policy_repairs():
    plan = build_agent_plan("四川和湖北通信管理局2024-2025年骚扰电话综合整治政策差异", profile="china")
    payload = plan.to_dict()
    commands = [item["command"] for item in payload["agent_next_steps"] + payload["silent_repair_commands"]]

    assert plan.primary_command.startswith("guanlan search")
    assert "--scope gov" in plan.primary_command
    assert not any(command.startswith("guanlan research") for command in commands)
    assert any(command.startswith("guanlan search") and "--scope gov" in command for command in commands)


def test_agent_plan_markdown_is_agent_readable():
    plan = build_agent_plan("人工智能 监管 政策 最新通知", profile="china")
    text = format_agent_plan_markdown(plan)

    assert "观澜 Agent 自动挡" in text
    assert "主命令" in text
    assert "下一步命令" in text
    assert "自动补救契约" in text
    assert "跑偏触发器" in text
