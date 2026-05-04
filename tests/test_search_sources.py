# -*- coding: utf-8 -*-
"""Tests for curated China search source scopes."""

import pytest

from guanlan.search_sources import classify_domain, list_search_scopes, resolve_scope, scoped_query


def test_search_scopes_include_requested_china_sources():
    scopes = list_search_scopes()

    assert "people.com.cn" in scopes["party_central"]["domains"]
    assert scopes["party_central"]["source_type"] == "党央媒"
    assert scopes["party_central"]["trust_level"] == 5
    assert "xinhuanet.com" in scopes["party_central"]["domains"]
    assert "bjd.com.cn" in scopes["local_official"]["domains"]
    assert "southcn.com" in scopes["local_official"]["domains"]
    assert "ebrun.com" in scopes["ecommerce"]["domains"]
    assert "engineeringvillage.com" in scopes["academic"]["domains"]
    assert scopes["academic"]["source_type"] == "学术/论文检索"
    assert "edu.cn" in scopes["university"]["domains"]
    assert "cs.tsinghua.edu.cn" in scopes["university"]["domains"]
    assert scopes["university"]["source_type"] == "高校/院系官网"
    assert scopes["university"]["trust_level"] == 5
    assert "douban.com" in scopes["entertainment"]["domains"]
    assert "maoyan.com" in scopes["entertainment"]["domains"]
    assert "bangumi.tv" in scopes["entertainment"]["domains"]
    assert "pixiv.net" in scopes["entertainment"]["domains"]
    assert scopes["entertainment"]["source_type"] == "文娱/内容平台"
    assert "billboard.com" in scopes["global_entertainment"]["domains"]
    assert "variety.com" in scopes["global_entertainment"]["domains"]
    assert scopes["global_entertainment"]["source_type"] == "欧美文娱/音乐产业"
    assert "soompi.com" in scopes["jp_kr_entertainment"]["domains"]
    assert "oricon.co.jp" in scopes["jp_kr_entertainment"]["domains"]
    assert scopes["jp_kr_entertainment"]["source_type"] == "日韩文娱/K-pop/J-pop"
    assert "sec.gov" in scopes["global_official"]["domains"]
    assert scopes["global_official"]["source_type"] == "英文官方/监管"
    assert "openai.com" in scopes["company_primary"]["domains"]
    assert "github.com" in scopes["developer"]["domains"]
    assert "nvd.nist.gov" in scopes["cybersecurity"]["domains"]
    assert scopes["cybersecurity"]["source_type"] == "网络安全/漏洞/反诈"
    assert "espn.com" in scopes["sports"]["domains"]
    assert "nmc.cn" in scopes["weather_disaster"]["domains"]
    assert "nasa.gov" in scopes["science"]["domains"]
    assert "xiaoyuzhoufm.com" in scopes["podcast"]["domains"]
    assert "levels.fyi" in scopes["career"]["domains"]
    assert "ielts.org" in scopes["test_prep"]["domains"]
    assert "cninfo.com.cn" in scopes["finance_disclosure"]["domains"]
    assert scopes["finance_disclosure"]["source_type"] == "财经/公告披露"
    assert "quote.eastmoney.com" in scopes["finance_quote"]["domains"]
    assert scopes["finance_quote"]["source_type"] == "财经/行情数据"
    assert "stats.gov.cn" in scopes["finance_macro"]["domains"]
    assert "xueqiu.com" in scopes["finance_sentiment"]["domains"]
    assert "data.eastmoney.com" in scopes["finance_research"]["domains"]


def test_resolve_scope_aliases():
    assert resolve_scope("central").id == "party_central"
    assert resolve_scope("local").id == "local_official"
    assert resolve_scope("retail").id == "ecommerce"
    assert resolve_scope("scholar").id == "academic"
    assert resolve_scope("admission").id == "university"
    assert resolve_scope("graduate").id == "university"
    assert resolve_scope("faculty").id == "university"
    assert resolve_scope("company").id == "company_primary"
    assert resolve_scope("reddit").id == "community_sample"
    assert resolve_scope("movie").id == "entertainment"
    assert resolve_scope("douban").id == "entertainment"
    assert resolve_scope("acg").id == "entertainment"
    assert resolve_scope("manga").id == "entertainment"
    assert resolve_scope("anime").id == "entertainment"
    assert resolve_scope("hollywood").id == "global_entertainment"
    assert resolve_scope("billboard").id == "global_entertainment"
    assert resolve_scope("kpop").id == "jp_kr_entertainment"
    assert resolve_scope("oricon").id == "jp_kr_entertainment"
    assert resolve_scope("cve").id == "cybersecurity"
    assert resolve_scope("weather").id == "weather_disaster"
    assert resolve_scope("sports").id == "sports"
    assert resolve_scope("podcast").id == "podcast"
    assert resolve_scope("salary").id == "career"
    assert resolve_scope("ielts").id == "test_prep"
    assert resolve_scope("quote").id == "finance_quote"
    assert resolve_scope("stock").id == "finance_quote"
    assert resolve_scope("filing").id == "finance_disclosure"
    assert resolve_scope("macro").id == "finance_macro"
    assert resolve_scope("xueqiu").id == "finance_sentiment"
    assert resolve_scope("brokerage").id == "finance_research"


def test_resolve_scope_rejects_unknown():
    with pytest.raises(ValueError):
        resolve_scope("not-a-scope")


def test_scoped_query_limits_site_expression():
    query = scoped_query("人工智能", ["people.com.cn", "xinhuanet.com"], max_sites=2)

    assert query == "(site:people.com.cn OR site:xinhuanet.com) 人工智能"


def test_classify_domain_matches_subdomains():
    meta = classify_domain("theory.people.com.cn")

    assert meta["source_type"] == "党央媒"
    assert meta["matched_scope"] == "party_central"
    assert meta["trust_level"] == 5


def test_classify_domain_prefers_requested_scope_for_overlapping_sources():
    meta = classify_domain("ebrun.com", preferred_scope="ecommerce")

    assert meta["source_type"] == "电商/零售垂类"
    assert meta["matched_scope"] == "ecommerce"


def test_classify_domain_detects_academic_sources():
    meta = classify_domain("www.engineeringvillage.com")

    assert meta["source_type"] == "学术/论文检索"
    assert meta["matched_scope"] == "academic"
    assert meta["trust_level"] == 4


def test_classify_domain_detects_university_sources():
    meta = classify_domain("cs.tsinghua.edu.cn")

    assert meta["source_type"] == "高校/院系官网"
    assert meta["matched_scope"] == "university"
    assert meta["trust_level"] == 5


def test_classify_domain_detects_entertainment_sources():
    douban = classify_domain("movie.douban.com")
    maoyan = classify_domain("piaofang.maoyan.com")
    billboard = classify_domain("www.billboard.com")
    soompi = classify_domain("www.soompi.com")
    oricon = classify_domain("www.oricon.co.jp")

    assert douban["source_type"] == "文娱/内容平台"
    assert douban["matched_scope"] == "entertainment"
    assert maoyan["source_type"] == "文娱/内容平台"
    assert maoyan["matched_scope"] == "entertainment"
    assert billboard["source_type"] == "欧美文娱/音乐产业"
    assert billboard["matched_scope"] == "global_entertainment"
    assert soompi["source_type"] == "日韩文娱/K-pop/J-pop"
    assert soompi["matched_scope"] == "jp_kr_entertainment"
    assert oricon["matched_scope"] == "jp_kr_entertainment"


def test_classify_domain_detects_english_source_scopes():
    official = classify_domain("www.sec.gov")
    company = classify_domain("platform.openai.com", preferred_scope="company_primary")
    developer = classify_domain("docs.github.com")
    community = classify_domain("old.reddit.com")

    assert official["source_type"] == "英文官方/监管"
    assert official["matched_scope"] == "global_official"
    assert company["source_type"] == "公司一手资料"
    assert company["matched_scope"] == "company_primary"
    assert developer["source_type"] == "英文开发者/开源"
    assert developer["matched_scope"] == "developer"
    assert community["source_type"] == "英文社区样本"


def test_classify_domain_detects_finance_layers():
    cninfo = classify_domain("www.cninfo.com.cn")
    quote = classify_domain("quote.eastmoney.com")
    macro = classify_domain("www.stats.gov.cn", preferred_scope="finance_macro")
    sentiment = classify_domain("guba.eastmoney.com")

    assert cninfo["source_type"] == "财经/公告披露"
    assert cninfo["matched_scope"] == "finance_disclosure"
    assert cninfo["trust_level"] == 5
    assert quote["source_type"] == "财经/行情数据"
    assert quote["matched_scope"] == "finance_quote"
    assert macro["matched_scope"] == "finance_macro"
    assert sentiment["matched_scope"] == "finance_sentiment"
