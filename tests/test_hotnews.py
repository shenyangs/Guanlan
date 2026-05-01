# -*- coding: utf-8 -*-
"""Tests for native hotnews sources and formatters."""

import json
from unittest.mock import patch

import pytest

from guanlan import hotnews


def test_fetch_baidu_normalizes_public_board_payload(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "_read_json",
        lambda _url: {
            "data": {
                "cards": [
                    {
                        "content": [
                            {
                                "content": [
                                    {
                                        "word": "AI 应用爆发",
                                        "desc": "相关讨论升温",
                                        "url": "https://example.com/a",
                                        "hotScore": "12345",
                                        "appUrl": "baiduboxapp://example",
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        },
    )

    items = hotnews.fetch_hotnews("baidu", limit=5)

    assert len(items) == 1
    assert items[0]["source_id"] == "baidu"
    assert items[0]["title"] == "AI 应用爆发"
    assert items[0]["summary"] == "相关讨论升温"
    assert items[0]["metrics"]["heat"] == "12345"
    assert items[0]["rank"] == 1


def test_fetch_zhihu_normalizes_topstory_payload(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "_read_json",
        lambda _url: {
            "data": [
                {
                    "target": {
                        "title_area": {"text": "如何看待某公司新模型？"},
                        "excerpt_area": {"text": "讨论集中在成本和效果。"},
                        "link": {"url": "https://www.zhihu.com/question/1"},
                        "metrics_area": {"text": "1000 万热度"},
                    }
                }
            ]
        },
    )

    items = hotnews.fetch_hotnews("zhihu", limit=1)

    assert items[0]["source_id"] == "zhihu"
    assert items[0]["title"] == "如何看待某公司新模型？"
    assert items[0]["url"] == "https://www.zhihu.com/question/1"
    assert items[0]["metrics"]["heat"] == "1000 万热度"


def test_fetch_weibo_normalizes_hot_search_payload(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "_read_json",
        lambda _url, **_kwargs: {
            "data": {
                "realtime": [
                    {
                        "word": "五一出行",
                        "note": "五一出行",
                        "num": 123456,
                        "flag_desc": "热",
                        "word_scheme": "#五一出行#",
                    }
                ]
            }
        },
    )

    items = hotnews.fetch_hotnews("weibo", limit=1)

    assert items[0]["source_id"] == "weibo"
    assert items[0]["title"] == "五一出行"
    assert "s.weibo.com" in items[0]["url"]
    assert items[0]["metrics"]["heat"] == 123456
    assert items[0]["metrics"]["label"] == "热"


def test_fetch_bilibili_normalizes_ranking_payload(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "_read_json",
        lambda _url: {
            "data": {
                "list": [
                    {
                        "title": "一个热门视频",
                        "desc": "视频简介",
                        "bvid": "BV123",
                        "owner": {"name": "UP 主"},
                        "stat": {"view": 1000, "like": 88, "reply": 9},
                    }
                ]
            }
        },
    )

    items = hotnews.fetch_hotnews("bilibili", limit=1)

    assert items[0]["source_id"] == "bilibili"
    assert items[0]["title"] == "一个热门视频"
    assert items[0]["url"] == "https://www.bilibili.com/video/BV123"
    assert items[0]["metrics"]["heat"] == 1000
    assert items[0]["metrics"]["views"] == 1000
    assert items[0]["metrics"]["owner"] == "UP 主"


def test_fetch_bilibili_falls_back_to_popular_payload(monkeypatch):
    requested = []

    def fake_read_json(url):
        requested.append(url)
        if "ranking" in url:
            return {"code": -352, "message": "-352"}
        return {
            "data": {
                "list": [
                    {
                        "title": "热门视频兜底",
                        "desc": "popular endpoint",
                        "bvid": "BV999",
                        "owner": {"name": "UP 主"},
                        "stat": {"view": 2000},
                    }
                ]
            }
        }

    monkeypatch.setattr(hotnews, "_read_json", fake_read_json)

    items = hotnews.fetch_hotnews("bilibili", limit=1)

    assert "ranking/v2" in requested[0]
    assert "popular?ps=1&pn=1" in requested[1]
    assert items[0]["title"] == "热门视频兜底"


def test_fetch_ithome_parses_public_rss(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "_read_text",
        lambda _url: """
        <rss><channel><item>
          <title>IT 之家消息</title>
          <link>https://www.ithome.com/0/001/001.htm</link>
          <description><![CDATA[<p>科技新闻摘要</p>]]></description>
          <pubDate>Fri, 01 May 2026 08:00:00 GMT</pubDate>
        </item></channel></rss>
        """,
    )

    items = hotnews.fetch_hotnews("ithome", limit=1)

    assert items[0]["source_id"] == "ithome"
    assert items[0]["title"] == "IT 之家消息"
    assert items[0]["summary"] == "科技新闻摘要"
    assert items[0]["published_at"] == "Fri, 01 May 2026 08:00:00 GMT"


def test_fetch_today_round_robins_sources_and_tolerates_failures(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "fetch_baidu",
        lambda limit=20: [
            hotnews.HotNewsItem(platform="baidu", source_id="baidu", category="hotnews", title="百度 1", rank=1),
            hotnews.HotNewsItem(platform="baidu", source_id="baidu", category="hotnews", title="百度 2", rank=2),
        ],
    )
    monkeypatch.setattr(
        hotnews,
        "fetch_weibo",
        lambda limit=20: [
            hotnews.HotNewsItem(platform="weibo", source_id="weibo", category="social", title="微博 1", rank=1)
        ],
    )
    monkeypatch.setattr(hotnews, "fetch_bilibili", lambda limit=20: (_ for _ in ()).throw(RuntimeError("403")))
    monkeypatch.setattr(hotnews, "fetch_ithome", lambda limit=20: [])
    monkeypatch.setattr(
        hotnews,
        "fetch_v2ex",
        lambda limit=20: [
            hotnews.HotNewsItem(platform="v2ex", source_id="v2ex", category="community", title="V2EX 1", rank=1)
        ],
    )

    items = hotnews.fetch_hotnews("today", limit=4)

    assert [item["title"] for item in items] == ["百度 1", "微博 1", "V2EX 1", "百度 2"]
    assert [item["rank"] for item in items] == [1, 2, 3, 4]
    assert items[0]["metrics"]["source_rank"] == 1


def test_fetch_today_can_fill_expanded_limit(monkeypatch):
    def make_items(source_id, limit=20):
        return [
            hotnews.HotNewsItem(
                platform=source_id,
                source_id=source_id,
                category="hotnews",
                title=f"{source_id} {idx}",
                rank=idx,
            )
            for idx in range(1, limit + 1)
        ]

    monkeypatch.setattr(hotnews, "fetch_baidu", lambda limit=20: make_items("baidu", limit))
    monkeypatch.setattr(hotnews, "fetch_weibo", lambda limit=20: make_items("weibo", limit))
    monkeypatch.setattr(hotnews, "fetch_bilibili", lambda limit=20: make_items("bilibili", limit))
    monkeypatch.setattr(hotnews, "fetch_ithome", lambda limit=20: make_items("ithome", limit))
    monkeypatch.setattr(hotnews, "fetch_v2ex", lambda limit=20: make_items("v2ex", limit))

    items = hotnews.fetch_hotnews("today", limit=50)

    assert len(items) == 50
    assert items[-1]["rank"] == 50


def test_normalize_hotnews_payload_accepts_newsnow_like_shape():
    payload = {
        "data": {
            "items": [
                {
                    "title": "财联社快讯",
                    "url": "https://example.com/news",
                    "desc": "市场消息摘要",
                    "hot": 99,
                }
            ]
        }
    }

    items = hotnews.normalize_hotnews_payload(payload, source_id="cls")

    assert items[0]["source_id"] == "cls"
    assert items[0]["title"] == "财联社快讯"
    assert items[0]["summary"] == "市场消息摘要"
    assert items[0]["metrics"]["heat"] == 99
    assert items[0]["fetched_at"]


def test_fetch_newsnow_normalizes_api_payload(monkeypatch):
    requested = []

    def fake_read_json(url):
        requested.append(url)
        return {
            "data": {
                "items": [
                    {
                        "title": "36氪快讯",
                        "url": "https://36kr.com/news",
                        "desc": "融资消息",
                        "hot": 7,
                    }
                ]
            }
        }

    monkeypatch.setattr(hotnews, "_read_json", fake_read_json)

    items = hotnews.fetch_hotnews(
        "newsnow:36kr-quick",
        limit=3,
        newsnow_base_url="https://newsnow.example",
    )

    assert requested == ["https://newsnow.example/api/s?id=36kr-quick"]
    assert items[0]["source_id"] == "newsnow:36kr-quick"
    assert items[0]["platform"] == "36kr-quick"
    assert items[0]["title"] == "36氪快讯"
    assert items[0]["summary"] == "融资消息"
    assert items[0]["metrics"]["heat"] == 7


def test_fetch_hotnews_auto_uses_newsnow_for_unknown_source(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "fetch_newsnow",
        lambda source, limit=20, base_url=None: [
            {
                "source_id": f"newsnow:{source}",
                "platform": source,
                "title": "IT之家消息",
                "rank": 1,
            }
        ],
    )

    items = hotnews.fetch_hotnews("juejin", limit=1)

    assert items[0]["source_id"] == "newsnow:juejin"
    assert items[0]["title"] == "IT之家消息"


def test_format_hotnews_markdown_is_agent_readable():
    md = hotnews.format_hotnews_markdown(
        [
            {
                "rank": 1,
                "source_id": "baidu",
                "title": "AI 热点",
                "url": "https://example.com",
                "summary": "一条摘要",
                "metrics": {"heat": "888"},
            }
        ]
    )

    assert "# 观澜热榜" in md
    assert "1. [baidu] AI 热点" in md
    assert "https://example.com" in md


def test_hotnews_cli_lists_sources(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "hotnews", "list"]):
        main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "today" in data
    assert "baidu" in data
    assert "weibo" in data
    assert "bilibili" in data
    assert "ithome" in data
    assert "zhihu" in data
    assert data["zhihu"]["status"] == "experimental"
    assert data["zhihu"]["verified"] is False
    assert "v2ex" in data
    assert "newsnow:36kr-quick" in data
    assert data["newsnow:36kr-quick"]["status"] == "best-effort"


def test_hotnews_cli_zhihu_failure_prints_search_fallback(capsys):
    from guanlan.cli import main

    with patch("guanlan.hotnews.fetch_hotnews", side_effect=RuntimeError("401")):
        with patch("sys.argv", ["guanlan", "hotnews", "zhihu"]):
            with pytest.raises(SystemExit):
                main()

    captured = capsys.readouterr()
    assert "experimental" in captured.err
    assert "Fallback: guanlan search" in captured.err


def test_format_hotnews_cli_reads_json(capsys):
    from guanlan.cli import main

    payload = json.dumps({"items": [{"title": "热榜标题", "url": "https://example.com"}]})
    with patch("sys.argv", ["guanlan", "format", "hotnews"]):
        with patch("sys.stdin.read", return_value=payload):
            main()
    captured = capsys.readouterr()
    assert "热榜标题" in captured.out
