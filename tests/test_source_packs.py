# -*- coding: utf-8 -*-
"""Tests for curated source packs."""

from guanlan.router import build_route_plan
from guanlan.search_sources import classify_domain, resolve_scope
from guanlan.source_packs import (
    SOURCE_PACKS,
    hotboard_nodes_for_intents,
    recommended_sites_for_intents,
)
from guanlan.source_taxonomy import source_card_for_domain


def test_source_packs_are_selective_and_exclude_low_value_categories():
    assert "policy_research" in SOURCE_PACKS
    assert "tech_research" in SOURCE_PACKS
    assert "finance_research" in SOURCE_PACKS
    assert "entertainment_research" in SOURCE_PACKS
    assert "developer_research" in SOURCE_PACKS
    assert "university_official" in SOURCE_PACKS
    assert "shopping" not in SOURCE_PACKS
    assert "blog" not in SOURCE_PACKS
    assert "epaper" not in SOURCE_PACKS


def test_policy_pack_promotes_half_month_talk_without_treating_it_as_generic_hotnews():
    party = resolve_scope("party_central")
    assert "banyuetan.org" in party.domains
    assert "qstheory.cn" in party.domains
    card = source_card_for_domain("banyuetan.org")
    assert card.scope_id == "party_central"
    assert card.authority_score >= 0.8


def test_vertical_packs_extend_search_scopes_with_curated_domains():
    tech = resolve_scope("tech_dev")
    finance_news = resolve_scope("finance_news")
    entertainment = resolve_scope("entertainment")
    developer = resolve_scope("developer")
    company_primary = resolve_scope("company_primary")
    science = resolve_scope("science")
    community = resolve_scope("community_sample")
    ecommerce = resolve_scope("ecommerce")
    university = resolve_scope("university")

    assert "jiqizhixin.com" in tech.domains
    assert "qbitai.com" in tech.domains
    assert "ebrun.com" in ecommerce.domains
    assert "21jingji.com" in finance_news.domains
    assert "gelonghui.com" in resolve_scope("finance_research").domains
    assert "gcores.com" in entertainment.domains
    assert "yystv.cn" in entertainment.domains
    assert "hellogithub.com" in developer.domains
    assert "huggingface.co" in developer.domains
    assert "github.blog" in developer.domains
    assert "deepmind.google" in company_primary.domains
    assert "mistral.ai" in company_primary.domains
    assert "openrouter.ai" in company_primary.domains
    assert "bair.berkeley.edu" in science.domains
    assert "ml.cmu.edu" in science.domains
    assert "simonwillison.net" in community.domains
    assert "testerhome.com" in tech.domains
    assert "buaa.edu.cn" in university.domains
    assert "whu.edu.cn" in university.domains


def test_classify_domain_uses_source_pack_domains():
    assert classify_domain("qbitai.com")["matched_scope"] == "tech_dev"
    assert classify_domain("deepmind.google")["matched_scope"] == "company_primary"
    assert classify_domain("huggingface.co")["matched_scope"] == "developer"
    assert classify_domain("bair.berkeley.edu")["matched_scope"] == "science"
    assert classify_domain("simonwillison.net")["matched_scope"] == "community_sample"
    assert classify_domain("ebrun.com", preferred_scope="ecommerce")["matched_scope"] == "ecommerce"
    assert classify_domain("cls.cn")["matched_scope"] == "finance_news"
    assert classify_domain("movie.douban.com", preferred_scope="entertainment")["matched_scope"] == "entertainment"
    assert classify_domain("buaa.edu.cn")["matched_scope"] == "university"


def test_source_pack_recommendations_feed_router_without_overwriting_main_route():
    finance_sites = recommended_sites_for_intents(["finance", "finance_sentiment"], limit=5)
    assert "cls.cn" in finance_sites
    assert "stcn.com" in finance_sites
    assert "xueqiu.com" not in finance_sites[:3]

    company_sites = recommended_sites_for_intents(["company_primary"], limit=5)
    assert {"openai.com", "anthropic.com", "deepmind.google"} <= set(company_sites)

    nodes = hotboard_nodes_for_intents(["finance"], limit=2)
    assert nodes
    assert all(node["node_id"] for node in nodes)

    plan = build_route_plan("AI Agent 技术文章 最近值得读", profile="china")
    assert "ithome.com" in plan.target_sites or "sspai.com" in plan.target_sites
    assert any(command.startswith("guanlan feeds curated") for command in plan.recommended_commands)

    ecommerce_plan = build_route_plan("跨境电商 独立站 出海 产业趋势", profile="china")
    assert ecommerce_plan.target_sites[0] == "ebrun.com"
    assert any("hotboard:snapshots:3adq0LMvng" in command for command in ecommerce_plan.recommended_commands)
