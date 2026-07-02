# -*- coding: utf-8 -*-
"""Regression tests for WPS external-evidence routing."""

from guanlan import webtools
from guanlan.source_seeds import direct_source_seeds, wps_office_needs_open_web


def test_wps_external_information_queries_skip_official_entrypoint_seeds():
    complaint_query = "WPS C盘刺客 套娃收费 新华网 人民网 中国新闻网"
    media_query = "WPS 背刺 光明网评论"

    assert wps_office_needs_open_web(complaint_query, intents=["wps_office"], scopes=["wps_office"])
    assert wps_office_needs_open_web(media_query, intents=["wps_office"], scopes=["wps_office"])
    assert direct_source_seeds(complaint_query, intents=["wps_office"], scopes=["wps_office"]) == []
    assert direct_source_seeds(media_query, intents=["wps_office"], scopes=["wps_office"]) == []
    assert not wps_office_needs_open_web("WPS AI 官网 下载", intents=["wps_office"], scopes=["wps_office"])


def test_wps_external_information_scope_uses_open_query_and_skips_entry_seeds(monkeypatch):
    requested = []

    def fake_search(query, limit=10):
        requested.append(query)
        return [
            webtools.SearchResult(
                title="WPS 背刺 光明网评论",
                url="https://news.gmw.cn/example",
                snippet="光明网评论 WPS 收费和用户体验争议。",
            )
        ]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "WPS 背刺 光明网评论",
        backend="duckduckgo",
        profile="china",
        scope="wps_office",
        limit=10,
        trace=True,
    )

    assert requested
    assert requested[0] == "WPS 背刺 光明网评论"
    assert "site:wps.cn" not in requested[0]
    urls = [item["url"] for item in results]
    assert "https://news.gmw.cn/example" in urls
    assert not any("365.wps.cn" in url or "lingxi.wps.cn" in url for url in urls)


def test_wps_external_information_ranking_prefers_outside_evidence():
    query = "WPS 背刺 光明网评论"
    route = webtools.build_route_plan(query, scope="wps_office").to_dict()
    quality = webtools.detect_search_quality_profile(query, scope="wps_office")
    quality = webtools._quality_with_route_plan(quality, route, explicit_scope="wps_office")

    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="WPS 365",
                url="https://365.wps.cn/",
                snippet="WPS 365 官方入口，适合协同办公。",
                source="duckduckgo",
                rank=1,
            ),
            webtools.SearchResult(
                title="WPS 背刺 光明网评论",
                url="https://news.gmw.cn/example",
                snippet="光明网评论 WPS 收费和用户体验争议。",
                source="duckduckgo",
                rank=2,
            ),
        ],
        query=query,
        preferred_scope="wps_office",
        quality=quality,
    )

    assert ranked[0].domain == "news.gmw.cn"
    assert ranked[0].score_parts["wps_external_evidence_boost"] > 0
    assert ranked[1].domain == "365.wps.cn"
    assert ranked[1].score_parts["wps_official_entry_penalty"] < 0


def test_wps_external_information_keeps_official_after_top_five():
    query = "WPS 背刺 套娃收费 C盘刺客 用户投诉"
    route = webtools.build_route_plan(query, scope="wps_office").to_dict()
    quality = webtools.detect_search_quality_profile(query, scope="wps_office")
    quality = webtools._quality_with_route_plan(quality, route, explicit_scope="wps_office")

    ranked = webtools.rank_results(
        [
            webtools.SearchResult(
                title="WPS 365",
                url="https://365.wps.cn/",
                snippet="WPS 365 官方入口，适合协同办公。",
                source="fixture",
                rank=1,
            ),
            webtools.SearchResult(
                title="WPS 被指 C 盘刺客 用户吐槽收费套娃",
                url="https://news.qq.com/rain/a/wps-complaint",
                snippet="报道 WPS C盘缓存、会员收费和用户体验争议。",
                source="fixture",
                rank=2,
            ),
            webtools.SearchResult(
                title="WPS 背刺 用户讨论",
                url="https://www.zhihu.com/question/wps",
                snippet="用户样本讨论 WPS 广告、缓存和会员收费。",
                source="fixture",
                rank=3,
            ),
            webtools.SearchResult(
                title="金山办公 WPS 舆情观察",
                url="https://finance.sina.com.cn/tech/wps.html",
                snippet="产业媒体观察 WPS 口碑争议和商业模式。",
                source="fixture",
                rank=4,
            ),
            webtools.SearchResult(
                title="WPS 收费争议评论",
                url="https://news.gmw.cn/wps-comment",
                snippet="媒体评论 WPS 套娃收费与用户体验。",
                source="fixture",
                rank=5,
            ),
            webtools.SearchResult(
                title="WPS 会员投诉样本",
                url="https://tousu.sina.com.cn/complaint/wps",
                snippet="用户投诉样本涉及会员扣费和广告弹窗。",
                source="fixture",
                rank=6,
            ),
        ],
        query=query,
        preferred_scope="wps_office",
        quality=quality,
    )

    top_five_domains = [item.domain for item in ranked[:5]]
    assert not any(domain.endswith("wps.cn") for domain in top_five_domains)
    assert ranked[5].domain == "365.wps.cn"
