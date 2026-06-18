# -*- coding: utf-8 -*-
"""Regression tests for AI model release/comparison search quality."""

from guanlan import webtools


def test_ai_model_comparison_query_rewrites_conversational_fillers():
    query = "好像这次 GLM 5.2 的声量比 kimi 2.7 高，前者强在哪儿"
    quality = webtools.detect_search_quality_profile(query, profile="china")
    route = webtools.build_route_plan(query, profile="china").to_dict()
    quality["route_intents"] = route["primary_intents"] + route["secondary_intents"]

    shape = webtools._analyze_search_query_shape(query, quality=quality, route_plan=route)

    assert shape["rewritten"] is True
    assert "GLM 5.2" in shape["backend_query"]
    assert "Kimi 2.7" in shape["backend_query"]
    assert "对比" in shape["backend_query"]
    assert "声量" in shape["backend_query"]
    assert "能力" in shape["backend_query"]
    assert "好像" not in shape["backend_query"]
    assert "前者" not in shape["backend_query"]


def test_ai_model_query_strategy_uses_clean_query_for_tech_variants():
    query = "好像这次 GLM 5.2 的声量比 kimi 2.7 高，前者强在哪儿"
    quality = webtools.detect_search_quality_profile(query, profile="china")
    route = webtools.build_route_plan(query, profile="china").to_dict()
    quality["route_intents"] = route["primary_intents"] + route["secondary_intents"]

    strategy = webtools.build_query_strategy(query, route_plan=route, quality=quality)
    variants = {item["role"]: item["query"] for item in strategy["variants"]}

    for role in ("technical_primary", "developer_discussion", "entity_compare"):
        assert "GLM 5.2" in variants[role]
        assert "Kimi 2.7" in variants[role]
        assert "好像" not in variants[role]
        assert "前者" not in variants[role]


def test_ai_model_version_query_keeps_official_as_anchor_not_default_top_answer():
    query = "GLM 5.2 vs Kimi 2.7 Code 谁更强"
    quality = webtools.detect_search_quality_profile(query, profile="china")
    route = webtools.build_route_plan(query, profile="china").to_dict()
    quality["route_intents"] = route["primary_intents"] + route["secondary_intents"]
    quality["route_evidence_roles"] = route["evidence_roles"]
    quality["preferred_scopes"] = route["preferred_scopes"]

    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="GLM-5 发布，智谱新模型有哪些亮点？",
                url="https://baijiahao.baidu.com/s?id=demo",
                snippet="文章介绍 GLM-5 的性能、参数和能力。",
                source="fixture",
                rank=1,
            ),
            webtools.SearchResult(
                title="GLM 5.2 vs Kimi 2.7 Code: 谁才是最强国产编程模型?",
                url="https://blog.csdn.net/demo/article/details/1",
                snippet="多模型横评，包含 GLM 5.2 和 Kimi 2.7。",
                source="fixture",
                rank=2,
            ),
            webtools.SearchResult(
                title="GLM-5.2 Coding Plan 发布说明",
                url="https://docs.bigmodel.cn/cn/coding-plan/overview",
                snippet="智谱官方发布 GLM-5.2 Coding Plan，介绍 1M 上下文和模型能力。",
                source="fixture",
                rank=3,
            ),
            webtools.SearchResult(
                title="Z.ai - Inspiring AGI to Benefit Humanity",
                url="https://www.zhipuai.cn/",
                snippet="智谱 AI 官网，介绍 GLM-PC、Agent OpenDay 和产品入口。",
                source="fixture",
                rank=4,
            ),
            webtools.SearchResult(
                title="GLM 5.2 与 Kimi 2.7 编程模型实测",
                url="https://www.qbitai.com/2026/06/glm-kimi-code.html",
                snippet="量子位报道国产编程模型横评，包含官方发布信息和测试说明。",
                source="fixture",
                rank=5,
            ),
            webtools.SearchResult(
                title="Kimi - Moonshot AI",
                url="https://www.moonshot.cn/",
                snippet="Moonshot AI 官网与 Kimi 产品入口。",
                source="fixture",
                rank=6,
            ),
        ],
        query=query,
        backend_order=["fixture"],
        preferred_scope="tech_dev",
        quality=quality,
    )

    domains = [item.domain for item in ranked]
    assert domains.index("qbitai.com") < domains.index("docs.bigmodel.cn")
    assert domains.index("docs.bigmodel.cn") < domains.index("zhipuai.cn")
    assert domains.index("qbitai.com") < domains.index("zhipuai.cn")
    assert domains.index("qbitai.com") < domains.index("moonshot.cn")
    assert domains.index("qbitai.com") < domains.index("blog.csdn.net")
    assert domains.index("baijiahao.baidu.com") == len(domains) - 1
    official_doc = next(item for item in ranked if item.domain == "docs.bigmodel.cn")
    official_home = next(item for item in ranked if item.domain == "zhipuai.cn")
    baijiahao = next(item for item in ranked if item.domain == "baijiahao.baidu.com")
    csdn = next(item for item in ranked if item.domain == "blog.csdn.net")
    assert official_doc.score_parts["official_information_penalty"] == 0
    assert official_home.score_parts["official_information_penalty"] < 0
    assert baijiahao.evidence_role == "low_value_seo"
    assert baijiahao.score_parts["entity_mismatch_penalty"] < 0
    assert csdn.score_parts["source_risk_penalty"] <= -0.75


def test_search_quality_gate_detects_low_value_model_version_mismatch():
    batch = [
        webtools.SearchResult(
            title="GLM-5 发布，智谱新模型有哪些亮点？",
            url="https://baijiahao.baidu.com/s?id=demo",
            snippet="文章介绍 GLM-5 的性能、参数和能力。",
            source="bing",
            rank=1,
        )
    ]

    gate = webtools._assess_backend_batch_quality("GLM 5.2 声量比 Kimi 2.7 高 前者强在哪", batch, {"intent": "tech"})

    assert gate["usable"] is False
    assert "low_value_domain_pollution" in gate["reason"]
    assert gate["pollution"]["severity"] == "high"
    assert "model_version_mismatch:GLM 5.2" in gate["pollution"]["samples"][0]["reason"]
