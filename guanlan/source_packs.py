# -*- coding: utf-8 -*-
"""Curated source packs distilled from verified public surfaces and Guanlan judgement.

These packs are source-logic assets, not hotboard result lists. They encode a
small set of stable, high-value sources that can strengthen routing and scoped
search while keeping noisy catalogs, epapers, shopping boards, and high-noise
social feeds out of the main evidence path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class SourcePackEntry:
    name: str
    domain: str
    scope_id: str
    evidence_role: str
    tier: str = "core"
    authority: float = 0.5
    sample_value: float = 0.3
    freshness: float = 0.5
    hotboard_node_id: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value not in ("", None)}


SOURCE_PACKS: dict[str, tuple[SourcePackEntry, ...]] = {
    "policy_research": (
        SourcePackEntry("中国政府网", "gov.cn", "gov", "official_primary", "core", 0.97, 0.05, 0.62, "47o8ELqvMm"),
        SourcePackEntry("人民网", "people.com.cn", "party_central", "authoritative_report", "core", 0.88, 0.18, 0.66, "8Rv2GNwdLw"),
        SourcePackEntry("新华网", "xinhuanet.com", "party_central", "authoritative_report", "core", 0.88, 0.16, 0.66, "47o8RJgdMm"),
        SourcePackEntry("央视新闻", "news.cctv.com", "party_central", "authoritative_report", "core", 0.86, 0.16, 0.68, "aqeEKPjv9R"),
        SourcePackEntry("求是网", "qstheory.cn", "party_central", "official_narrative", "core", 0.9, 0.08, 0.48, "Jndkwjyd3V"),
        SourcePackEntry("半月谈", "banyuetan.org", "party_central", "policy_interpretation", "core", 0.82, 0.2, 0.62, "ENeY0pZdY4"),
        SourcePackEntry("光明网", "gmw.cn", "party_central", "authoritative_report", "core", 0.82, 0.18, 0.6),
        SourcePackEntry("经济日报", "ce.cn", "party_central", "macro_policy_report", "core", 0.82, 0.18, 0.62),
        SourcePackEntry("央广网", "cnr.cn", "party_central", "authoritative_report", "core", 0.8, 0.18, 0.64),
        SourcePackEntry("中国新闻网", "chinanews.com.cn", "party_central", "news_signal", "core", 0.76, 0.22, 0.72),
    ),
    "tech_research": (
        SourcePackEntry("IT之家", "ithome.com", "tech_dev", "tech_news_signal", "core", 0.58, 0.48, 0.9, "74Kvx59dkx"),
        SourcePackEntry("少数派", "sspai.com", "tech_dev", "tech_reading_signal", "core", 0.56, 0.55, 0.72, "NaEdZZXdrO"),
        SourcePackEntry("36氪", "36kr.com", "business", "industry_report", "core", 0.54, 0.38, 0.8, "Q1Vd5Ko85R"),
        SourcePackEntry("虎嗅", "huxiu.com", "business", "industry_analysis", "core", 0.52, 0.38, 0.76, "pQvNBrJvNE"),
        SourcePackEntry("钛媒体", "tmtpost.com", "business", "industry_analysis", "core", 0.52, 0.36, 0.76, "Y3QeLAGo7k"),
        SourcePackEntry("亿邦动力", "ebrun.com", "ecommerce", "ecommerce_industry_report", "core", 0.56, 0.36, 0.78, "3adq0LMvng"),
        SourcePackEntry("极客公园", "geekpark.net", "tech_dev", "product_context", "core", 0.5, 0.42, 0.72, "qndgkK0dLl"),
        SourcePackEntry("爱范儿", "ifanr.com", "tech_dev", "consumer_tech_signal", "core", 0.48, 0.42, 0.76, "74KvxK7okx"),
        SourcePackEntry("雷峰网", "leiphone.com", "tech_dev", "ai_industry_report", "core", 0.52, 0.36, 0.72, "Jb0vmWJeB1"),
        SourcePackEntry("机器之心", "jiqizhixin.com", "tech_dev", "ai_research_news", "core", 0.56, 0.34, 0.74, "qENeYzwoY4"),
        SourcePackEntry("量子位", "qbitai.com", "tech_dev", "ai_news_signal", "core", 0.54, 0.34, 0.78, "MZd7azPorO"),
        SourcePackEntry("新智元", "aiera.com.cn", "tech_dev", "ai_news_signal", "core", 0.5, 0.34, 0.78),
        SourcePackEntry("晚点 LatePost", "latepost.com", "business", "industry_report", "core", 0.58, 0.3, 0.72, "KGoRlY5dl6"),
        SourcePackEntry("InfoQ 中国", "infoq.cn", "tech_dev", "technical_context", "core", 0.56, 0.42, 0.68, "3QeLXr9e7k"),
        SourcePackEntry("ReadHub", "readhub.cn", "tech_dev", "topic_discovery", "vertical", 0.42, 0.5, 0.82),
        SourcePackEntry("Solidot", "solidot.org", "tech_dev", "developer_news_signal", "vertical", 0.48, 0.42, 0.72),
        SourcePackEntry("OpenAI", "openai.com", "company_primary", "company_primary", "core", 0.86, 0.12, 0.84, "wkvlPNYvz1"),
        SourcePackEntry("Anthropic", "anthropic.com", "company_primary", "company_primary", "core", 0.84, 0.12, 0.82),
        SourcePackEntry("Google DeepMind", "deepmind.google", "company_primary", "company_primary", "core", 0.84, 0.14, 0.82, "BwdGEJwoPx"),
        SourcePackEntry("Google Research", "research.google", "company_primary", "research_primary", "core", 0.8, 0.16, 0.76),
        SourcePackEntry("Mistral AI", "mistral.ai", "company_primary", "company_primary", "core", 0.78, 0.14, 0.78),
        SourcePackEntry("xAI", "x.ai", "company_primary", "company_primary", "core", 0.78, 0.14, 0.8),
        SourcePackEntry("Cursor", "cursor.com", "company_primary", "product_primary", "core", 0.72, 0.22, 0.8),
        SourcePackEntry("OpenRouter", "openrouter.ai", "company_primary", "platform_primary", "core", 0.72, 0.24, 0.82),
        SourcePackEntry("Runway", "runwayml.com", "company_primary", "product_primary", "core", 0.7, 0.24, 0.78),
        SourcePackEntry("Midjourney", "midjourney.com", "company_primary", "product_primary", "core", 0.7, 0.24, 0.78),
        SourcePackEntry("Apple Machine Learning Research", "machinelearning.apple.com", "company_primary", "research_primary", "core", 0.82, 0.14, 0.72),
        SourcePackEntry("LMSYS", "lmsys.org", "science", "ai_benchmark", "vertical", 0.66, 0.36, 0.72),
        SourcePackEntry("Berkeley AI Research", "bair.berkeley.edu", "science", "academic_lab_blog", "vertical", 0.7, 0.32, 0.66),
        SourcePackEntry("CMU Machine Learning Blog", "ml.cmu.edu", "science", "academic_lab_blog", "vertical", 0.7, 0.32, 0.66),
        SourcePackEntry("EleutherAI", "eleuther.ai", "science", "open_research", "vertical", 0.62, 0.42, 0.66),
        SourcePackEntry("arXiv", "arxiv.org", "science", "preprint", "vertical", 0.74, 0.28, 0.76),
        SourcePackEntry("SemiAnalysis", "semianalysis.com", "industry_analysis", "industry_analysis", "vertical", 0.58, 0.34, 0.74),
    ),
    "finance_research": (
        SourcePackEntry("财联社", "cls.cn", "finance_news", "market_news", "core", 0.62, 0.25, 0.92, "qndg5MpoLl"),
        SourcePackEntry("证券时报", "stcn.com", "finance_news", "market_news", "core", 0.64, 0.22, 0.84, "KGoR535el6"),
        SourcePackEntry("上海证券报", "cnstock.com", "finance_news", "market_news", "core", 0.64, 0.22, 0.82, "qndgZnVvLl"),
        SourcePackEntry("中国证券报", "cs.com.cn", "finance_news", "market_news", "core", 0.64, 0.22, 0.82),
        SourcePackEntry("第一财经", "yicai.com", "finance_news", "market_news", "core", 0.6, 0.28, 0.82, "0MdKam4ow1"),
        SourcePackEntry("21财经", "21jingji.com", "finance_news", "market_news", "core", 0.58, 0.28, 0.8, "4Kvx5R0dkx"),
        SourcePackEntry("华尔街见闻", "wallstreetcn.com", "finance_news", "market_timeline", "core", 0.54, 0.3, 0.88, "wWmoO8kv4E"),
        SourcePackEntry("经济观察网", "eeo.com.cn", "finance_news", "industry_report", "core", 0.56, 0.28, 0.72, "YqoXgQ4eOD"),
        SourcePackEntry("每日经济新闻", "nbd.com.cn", "finance_news", "market_news", "core", 0.56, 0.28, 0.78, "YqoXVNzdOD"),
        SourcePackEntry("财新", "caixin.com", "finance_news", "investigative_report", "core", 0.62, 0.24, 0.72),
        SourcePackEntry("东方财富", "eastmoney.com", "finance_quote", "market_quote", "vertical", 0.48, 0.48, 0.88, "3QeL0axe7k"),
        SourcePackEntry("雪球", "xueqiu.com", "finance_sentiment", "sentiment_sample", "sample", 0.28, 0.88, 0.9, "X12owXzvNV"),
        SourcePackEntry("股吧", "guba.eastmoney.com", "finance_sentiment", "sentiment_sample", "sample", 0.2, 0.88, 0.9),
        SourcePackEntry("格隆汇", "gelonghui.com", "finance_research", "market_opinion", "vertical", 0.46, 0.36, 0.82, "KGoRAk1el6"),
    ),
    "entertainment_research": (
        SourcePackEntry("豆瓣电影", "movie.douban.com", "entertainment", "rating_sample", "core", 0.36, 0.88, 0.68, "Lwkvlxyvz1"),
        SourcePackEntry("豆瓣", "douban.com", "entertainment", "review_sample", "core", 0.34, 0.86, 0.62),
        SourcePackEntry("猫眼", "maoyan.com", "entertainment", "box_office", "core", 0.5, 0.72, 0.9, "9JndkpJe3V"),
        SourcePackEntry("猫眼专业版", "piaofang.maoyan.com", "entertainment", "box_office", "core", 0.52, 0.68, 0.92),
        SourcePackEntry("灯塔专业版", "lighthouse.alibaba.com", "entertainment", "box_office", "core", 0.5, 0.64, 0.9),
        SourcePackEntry("1905电影网", "1905.com", "entertainment", "film_news", "core", 0.54, 0.3, 0.74),
        SourcePackEntry("时光网", "mtime.com", "entertainment", "film_news", "core", 0.44, 0.52, 0.68),
        SourcePackEntry("B站", "bilibili.com", "entertainment", "video_attention_signal", "sample", 0.34, 0.78, 0.88, "74KvxwokxM"),
        SourcePackEntry("微博", "weibo.com", "entertainment", "public_discussion_signal", "sample", 0.28, 0.9, 0.9, "KqndgxeLl9"),
        SourcePackEntry("TapTap", "taptap.com", "entertainment", "game_rating_sample", "core", 0.36, 0.82, 0.74, "6ARe1k2v7n"),
        SourcePackEntry("游民星空", "gamersky.com", "entertainment", "game_news", "vertical", 0.42, 0.5, 0.72, "ARe1kXnv7n"),
        SourcePackEntry("3DM", "3dmgame.com", "entertainment", "game_news", "vertical", 0.4, 0.5, 0.72, "YqoXQR0vOD"),
        SourcePackEntry("机核", "gcores.com", "entertainment", "game_culture", "vertical", 0.46, 0.58, 0.7, "wWmoOVYe4E"),
        SourcePackEntry("游研社", "yystv.cn", "entertainment", "game_culture", "vertical", 0.46, 0.56, 0.72, "Om4ej8mvxE"),
    ),
    "developer_research": (
        SourcePackEntry("GitHub", "github.com", "developer", "code_host", "core", 0.82, 0.42, 0.82, "3QeL4qBe7k"),
        SourcePackEntry("Hugging Face", "huggingface.co", "developer", "model_hub", "vertical", 0.7, 0.58, 0.86, "MZd7LrperO"),
        SourcePackEntry("GitHub Blog", "github.blog", "developer", "developer_news", "vertical", 0.66, 0.42, 0.82),
        SourcePackEntry("Cloudflare Blog", "blog.cloudflare.com", "developer", "developer_news", "vertical", 0.68, 0.36, 0.84, "3adqz15eng"),
        SourcePackEntry("NVIDIA Developer", "developer.nvidia.com", "developer", "technical_primary", "vertical", 0.72, 0.32, 0.78),
        SourcePackEntry("V2EX", "v2ex.com", "tech_dev", "developer_discussion", "sample", 0.34, 0.88, 0.86, "wWmoORe4EO"),
        SourcePackEntry("掘金", "juejin.cn", "tech_dev", "developer_article", "core", 0.46, 0.68, 0.78, "1Vd5xE5v85"),
        SourcePackEntry("SegmentFault", "segmentfault.com", "tech_dev", "developer_article", "core", 0.46, 0.62, 0.72, "W1VdJZdLQM"),
        SourcePackEntry("开源中国", "oschina.net", "tech_dev", "opensource_news", "core", 0.48, 0.55, 0.74, "rYqoXZzdOD"),
        SourcePackEntry("博客园", "cnblogs.com", "tech_dev", "developer_article", "core", 0.42, 0.62, 0.64, "LBwdGgdPxq"),
        SourcePackEntry("CSDN", "csdn.net", "tech_dev", "developer_article", "vertical", 0.34, 0.66, 0.7, "n3moBVoN5O"),
        SourcePackEntry("InfoQ", "infoq.cn", "tech_dev", "technical_context", "core", 0.56, 0.42, 0.68, "3QeLXr9e7k"),
        SourcePackEntry("HelloGitHub", "hellogithub.com", "developer", "opensource_discovery", "core", 0.54, 0.58, 0.7, "wkvlB6Pez1"),
        SourcePackEntry("TesterHome", "testerhome.com", "tech_dev", "qa_engineering_discussion", "vertical", 0.42, 0.66, 0.68, "n4qv9poaKN"),
        SourcePackEntry("看雪", "bbs.kanxue.com", "cybersecurity", "security_community_signal", "vertical", 0.5, 0.62, 0.72, "Kqndg1xoLl"),
        SourcePackEntry("Simon Willison", "simonwillison.net", "community_sample", "technical_commentary", "sample", 0.48, 0.7, 0.78),
        SourcePackEntry("Ethan Mollick", "oneusefulthing.org", "community_sample", "ai_commentary", "sample", 0.46, 0.68, 0.72),
        SourcePackEntry("Interconnects", "interconnects.ai", "community_sample", "ai_commentary", "sample", 0.48, 0.66, 0.72),
        SourcePackEntry("Andrej Karpathy", "karpathy.ai", "community_sample", "technical_commentary", "sample", 0.52, 0.62, 0.58),
        SourcePackEntry("Sam Altman Blog", "blog.samaltman.com", "community_sample", "founder_commentary", "sample", 0.5, 0.5, 0.55),
    ),
    "wps_office_research": (
        SourcePackEntry("WPS 官网", "wps.cn", "wps_office", "company_primary", "core", 0.82, 0.16, 0.78),
        SourcePackEntry("WPS 365", "365.wps.cn", "wps_office", "product_primary", "core", 0.84, 0.16, 0.82),
        SourcePackEntry("WPS 官方社区", "bbs.wps.cn", "wps_office", "support_community", "core", 0.5, 0.62, 0.72),
        SourcePackEntry("金山办公安全中心", "security.wps.cn", "wps_office", "security_advisory", "core", 0.78, 0.18, 0.72),
        SourcePackEntry("金山文档", "kdocs.cn", "wps_office", "collaboration_product", "core", 0.74, 0.22, 0.72),
        SourcePackEntry("WPS Global", "wps.com", "wps_office", "company_primary", "core", 0.76, 0.2, 0.74),
        SourcePackEntry("金山办公 IR", "ir.kingsoft.com", "wps_office", "investor_relation", "core", 0.72, 0.12, 0.68),
        SourcePackEntry("WPS 灵犀", "lingxi.wps.cn", "wps_office", "product_primary", "core", 0.82, 0.16, 0.82, notes="WPS 灵犀/AI 原生办公官方入口；适合作为产品定位核验源。"),
        SourcePackEntry("Microsoft 365", "microsoft.com", "wps_office", "competitor_primary", "vertical", 0.72, 0.2, 0.76),
        SourcePackEntry("Microsoft Support", "support.microsoft.com", "wps_office", "support_doc", "vertical", 0.7, 0.24, 0.72),
        SourcePackEntry("Microsoft Tech Community", "techcommunity.microsoft.com", "wps_office", "product_community", "sample", 0.48, 0.66, 0.76),
        SourcePackEntry("Google Workspace", "workspace.google.com", "wps_office", "competitor_primary", "vertical", 0.72, 0.18, 0.76),
        SourcePackEntry("Kimi", "kimi.com", "wps_office", "competitor_primary", "vertical", 0.64, 0.28, 0.8, notes="通用 AI/长文档场景竞品语境；不能替代办公套件事实源。"),
        SourcePackEntry("豆包", "doubao.com", "wps_office", "competitor_primary", "vertical", 0.62, 0.28, 0.82, notes="国产 AI 助手与办公效率语境竞品；需回读官方能力边界。"),
        SourcePackEntry("Notion", "notion.so", "wps_office", "product_primary", "vertical", 0.62, 0.34, 0.74),
        SourcePackEntry("Canva", "canva.com", "wps_office", "presentation_ai_tool", "vertical", 0.62, 0.38, 0.78),
        SourcePackEntry("Gamma", "gamma.app", "wps_office", "presentation_ai_tool", "vertical", 0.58, 0.42, 0.8),
        SourcePackEntry("Beautiful.ai", "beautiful.ai", "wps_office", "presentation_ai_tool", "vertical", 0.54, 0.36, 0.7),
        SourcePackEntry("飞书", "feishu.cn", "wps_office", "collaboration_product", "vertical", 0.6, 0.42, 0.78),
        SourcePackEntry("Lark", "larkoffice.com", "wps_office", "collaboration_product", "vertical", 0.58, 0.38, 0.76),
        SourcePackEntry("语雀", "yuque.com", "wps_office", "document_collaboration", "vertical", 0.48, 0.6, 0.72),
        SourcePackEntry("石墨文档", "shimo.im", "wps_office", "document_collaboration", "vertical", 0.48, 0.6, 0.68),
        SourcePackEntry("IT之家", "ithome.com", "wps_office", "tech_news_signal", "core", 0.58, 0.48, 0.9, "74Kvx59dkx"),
        SourcePackEntry("少数派", "sspai.com", "wps_office", "productivity_reading", "core", 0.56, 0.55, 0.72, "NaEdZZXdrO"),
        SourcePackEntry("36氪", "36kr.com", "wps_office", "industry_report", "core", 0.54, 0.38, 0.8, "Q1Vd5Ko85R"),
        SourcePackEntry("虎嗅", "huxiu.com", "wps_office", "industry_analysis", "core", 0.52, 0.38, 0.76, "pQvNBrJvNE"),
        SourcePackEntry("雷峰网", "leiphone.com", "wps_office", "ai_industry_report", "core", 0.52, 0.36, 0.72, "Jb0vmWJeB1"),
        SourcePackEntry("机器之心", "jiqizhixin.com", "wps_office", "ai_research_news", "core", 0.56, 0.34, 0.74, "qENeYzwoY4"),
        SourcePackEntry("量子位", "qbitai.com", "wps_office", "ai_news_signal", "core", 0.54, 0.34, 0.78, "MZd7azPorO"),
        SourcePackEntry("InfoQ 中国", "infoq.cn", "wps_office", "technical_context", "vertical", 0.56, 0.42, 0.68, "3QeLXr9e7k"),
        SourcePackEntry("OpenAI", "openai.com", "wps_office", "ai_office_trend_primary", "vertical", 0.86, 0.12, 0.84, "wkvlPNYvz1", "AI/Agent 趋势发现层；不能替代 WPS 事实源。"),
        SourcePackEntry("Anthropic", "anthropic.com", "wps_office", "ai_agent_trend_primary", "vertical", 0.84, 0.12, 0.82, notes="AI Agent/工具调用趋势发现层；需回读原文。"),
        SourcePackEntry("Google DeepMind", "deepmind.google", "wps_office", "ai_research_trend_primary", "vertical", 0.84, 0.14, 0.82, "BwdGEJwoPx", "AI 能力趋势发现层；关键产品事实仍以官方/行业源核验。"),
        SourcePackEntry("Simon Willison", "simonwillison.net", "wps_office", "ai_commentary_signal", "sample", 0.5, 0.7, 0.78, notes="高质量 AI/Agent 评论与工具使用线索，仅作 discovery signal。"),
        SourcePackEntry("Ethan Mollick", "oneusefulthing.org", "wps_office", "ai_productivity_commentary", "sample", 0.48, 0.68, 0.72, notes="AI 办公/教育/生产力评论线索，仅作趋势样本。"),
        SourcePackEntry("Andrej Karpathy", "karpathy.ai", "wps_office", "technical_commentary", "sample", 0.52, 0.62, 0.58, notes="AI 技术和 Agent 叙事线索，仅作高质量样本。"),
        SourcePackEntry("Sam Altman Blog", "blog.samaltman.com", "wps_office", "founder_commentary", "sample", 0.5, 0.5, 0.55, notes="AI 行业叙事线索，仅作背景样本。"),
        SourcePackEntry("Hacker News", "news.ycombinator.com", "wps_office", "developer_discussion", "sample", 0.28, 0.9, 0.82, notes="开发者社区讨论样本，不作事实主证据。"),
        SourcePackEntry("GitHub Trending", "github.com", "wps_office", "developer_project_signal", "sample", 0.5, 0.72, 0.86, "3QeL4qBe7k", "AI Agent/办公自动化项目发现层。"),
        SourcePackEntry("V2EX", "v2ex.com", "wps_office", "developer_discussion", "sample", 0.34, 0.88, 0.86, "wWmoORe4EO"),
        SourcePackEntry("掘金", "juejin.cn", "wps_office", "developer_article", "sample", 0.46, 0.68, 0.78, "1Vd5xE5v85"),
        SourcePackEntry("G2", "g2.com", "wps_office", "saas_review_sample", "sample", 0.32, 0.82, 0.66),
        SourcePackEntry("Product Hunt", "producthunt.com", "wps_office", "product_launch_signal", "sample", 0.36, 0.78, 0.82),
        SourcePackEntry("Reddit", "reddit.com", "wps_office", "community_discussion", "sample", 0.24, 0.9, 0.78),
    ),
    "university_official": (
        SourcePackEntry("清华大学", "tsinghua.edu.cn", "university", "university_official", "core", 0.9, 0.12, 0.58, "wkvl6xkez1"),
        SourcePackEntry("北京大学", "pku.edu.cn", "university", "university_official", "core", 0.9, 0.12, 0.58, "JndkO2Zd3V"),
        SourcePackEntry("复旦大学", "fudan.edu.cn", "university", "university_official", "core", 0.88, 0.12, 0.56, "wkvlzprez1"),
        SourcePackEntry("上海交通大学", "sjtu.edu.cn", "university", "university_official", "core", 0.88, 0.12, 0.56, "DOvnXY2eEB"),
        SourcePackEntry("浙江大学", "zju.edu.cn", "university", "university_official", "core", 0.88, 0.12, 0.56, "nBe0g1Qd37"),
        SourcePackEntry("南京大学", "nju.edu.cn", "university", "university_official", "core", 0.88, 0.12, 0.56, "5PdMDppvmg"),
        SourcePackEntry("中国科学技术大学", "ustc.edu.cn", "university", "university_official", "core", 0.88, 0.12, 0.56, "Q0orqpWe8B"),
        SourcePackEntry("哈尔滨工业大学", "hit.edu.cn", "university", "university_official", "core", 0.86, 0.12, 0.54, "aEdZMEVvrO"),
        SourcePackEntry("武汉大学", "whu.edu.cn", "university", "university_official", "core", 0.86, 0.12, 0.54, "YqoXKNxeOD"),
        SourcePackEntry("北京航空航天大学", "buaa.edu.cn", "university", "university_official", "core", 0.86, 0.12, 0.54, "YKd60NKoaP"),
    ),
}

SCOPE_PACKS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "party_central": (("policy_research", ("core",)),),
    "gov": (("policy_research", ("core",)),),
    "business": (("tech_research", ("core", "vertical")),),
    "ecommerce": (("tech_research", ("core",)),),
    "tech_dev": (("tech_research", ("core", "vertical")), ("developer_research", ("core", "vertical", "sample"))),
    "wps_office": (("wps_office_research", ("core", "vertical", "sample")),),
    "cybersecurity": (("developer_research", ("vertical",)),),
    "finance": (("finance_research", ("core", "vertical")),),
    "finance_news": (("finance_research", ("core",)),),
    "finance_quote": (("finance_research", ("vertical",)),),
    "finance_sentiment": (("finance_research", ("sample",)),),
    "finance_research": (("finance_research", ("core", "vertical")),),
    "entertainment": (("entertainment_research", ("core", "vertical", "sample")),),
    "social_web": (("entertainment_research", ("sample",)), ("developer_research", ("sample",))),
    "university": (("university_official", ("core",)),),
    "company_primary": (("tech_research", ("core",)),),
    "developer": (("developer_research", ("core", "vertical")),),
    "science": (("tech_research", ("vertical",)),),
    "industry_analysis": (("tech_research", ("vertical",)),),
    "community_sample": (("developer_research", ("sample",)),),
}

SCOPE_ENTRY_SCOPE_ALLOW: dict[str, set[str]] = {
    "finance": {"finance_news", "finance_quote", "finance_research"},
    "social_web": {"entertainment", "tech_dev", "finance_sentiment"},
}

INTENT_PACKS: dict[str, tuple[str, ...]] = {
    "policy": ("policy_research",),
    "official_position": ("policy_research",),
    "industry": ("tech_research", "finance_research"),
    "ecommerce": ("tech_research",),
    "tech": ("tech_research", "developer_research"),
    "company_primary": ("tech_research",),
    "science": ("tech_research",),
    "global_industry": ("tech_research",),
    "wps_office": ("wps_office_research", "tech_research", "developer_research"),
    "finance": ("finance_research",),
    "finance_news": ("finance_research",),
    "finance_quote": ("finance_research",),
    "finance_disclosure": ("finance_research",),
    "finance_macro": ("finance_research",),
    "finance_sentiment": ("finance_research",),
    "finance_research": ("finance_research",),
    "entertainment": ("entertainment_research",),
    "reputation": ("entertainment_research", "developer_research"),
    "purchase_advice": ("entertainment_research", "developer_research"),
    "career": ("developer_research",),
    "cybersecurity": ("developer_research",),
    "university_admissions": ("university_official",),
}

INTENT_SCOPE_FILTERS: dict[str, set[str]] = {
    "company_primary": {"company_primary"},
    "ecommerce": {"ecommerce"},
    "global_industry": {"company_primary", "industry_analysis", "business"},
    "industry": {"business", "ecommerce", "finance_news", "finance_research"},
    "science": {"science"},
    "tech": {"tech_dev", "developer", "business"},
}


def list_source_packs() -> dict[str, list[dict]]:
    return {pack_id: [entry.to_dict() for entry in entries] for pack_id, entries in SOURCE_PACKS.items()}


def pack_entries(pack_id: str, *, tiers: Iterable[str] = ("core", "vertical", "sample")) -> tuple[SourcePackEntry, ...]:
    allowed = set(tiers)
    return tuple(entry for entry in SOURCE_PACKS.get(pack_id, ()) if entry.tier in allowed)


def pack_domains(pack_id: str, *, tiers: Iterable[str] = ("core", "vertical", "sample")) -> tuple[str, ...]:
    return _unique_domains(entry.domain for entry in pack_entries(pack_id, tiers=tiers))


def domains_for_scope(scope_id: str) -> tuple[str, ...]:
    domains: list[str] = []
    for pack_id, tiers in SCOPE_PACKS.get(scope_id, ()):  # type: ignore[assignment]
        allowed_entry_scopes = SCOPE_ENTRY_SCOPE_ALLOW.get(scope_id, {scope_id})
        domains.extend(
            entry.domain
            for entry in pack_entries(pack_id, tiers=tiers)
            if entry.scope_id in allowed_entry_scopes
        )
    return _unique_domains(domains)


def recommended_sites_for_intents(intents: Iterable[str], *, limit: int = 6) -> list[str]:
    sites: list[str] = []
    intent_list = [str(intent) for intent in intents]
    if "ecommerce" in intent_list:
        sites.extend(_recommended_sites_for_intent("ecommerce"))
    for intent in intent_list:
        if intent == "ecommerce":
            continue
        sites.extend(_recommended_sites_for_intent(intent))
    return list(_unique_domains(sites))[:limit]


def _recommended_sites_for_intent(intent: str) -> list[str]:
    allowed_scopes = INTENT_SCOPE_FILTERS.get(str(intent))
    sites: list[str] = []
    for pack_id in INTENT_PACKS.get(str(intent), ()):
        entries = pack_entries(pack_id, tiers=("core", "vertical"))
        if allowed_scopes:
            entries = tuple(entry for entry in entries if entry.scope_id in allowed_scopes)
        sites.extend(entry.domain for entry in sorted(entries, key=lambda item: (-item.authority, -item.freshness)))
    return sites


def hotboard_nodes_for_intents(intents: Iterable[str], *, limit: int = 4) -> list[dict[str, str]]:
    nodes: list[dict[str, str]] = []
    seen: set[str] = set()
    intent_list = [str(intent) for intent in intents]
    if "ecommerce" in intent_list:
        _append_hotboard_nodes(nodes, seen, "ecommerce", scope_id="ecommerce", limit=limit)
        if len(nodes) >= limit:
            return nodes
    for intent in intent_list:
        for pack_id in INTENT_PACKS.get(str(intent), ()):
            for entry in pack_entries(pack_id):
                if _append_hotboard_entry(nodes, seen, entry, limit=limit):
                    return nodes
    return nodes


def _append_hotboard_nodes(
    nodes: list[dict[str, str]],
    seen: set[str],
    intent: str,
    *,
    scope_id: str,
    limit: int,
) -> None:
    for pack_id in INTENT_PACKS.get(intent, ()):
        for entry in pack_entries(pack_id):
            if entry.scope_id == scope_id and _append_hotboard_entry(nodes, seen, entry, limit=limit):
                return


def _append_hotboard_entry(
    nodes: list[dict[str, str]],
    seen: set[str],
    entry: SourcePackEntry,
    *,
    limit: int,
) -> bool:
    if entry.hotboard_node_id and entry.hotboard_node_id not in seen:
        seen.add(entry.hotboard_node_id)
        nodes.append(
            {
                "name": entry.name,
                "domain": entry.domain,
                "node_id": entry.hotboard_node_id,
                "scope_id": entry.scope_id,
                "tier": entry.tier,
                "evidence_role": entry.evidence_role,
            }
        )
    return len(nodes) >= limit


def _unique_domains(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        domain = str(value or "").strip().lower().removeprefix("www.")
        if domain and domain not in seen:
            seen.add(domain)
            result.append(domain)
    return tuple(result)
