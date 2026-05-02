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


def test_fetch_bilibili_hot_search_normalizes_public_hotwords(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "_read_json",
        lambda _url: {
            "code": 0,
            "list": [
                {
                    "show_name": "AI 视频工具",
                    "keyword": "AI 视频工具",
                    "heat_score": 888,
                    "heat_layer": "high",
                }
            ],
        },
    )

    items = hotnews.fetch_hotnews("bilibili-hot-search", limit=1)

    assert items[0]["source_id"] == "bilibili-hot-search"
    assert items[0]["title"] == "AI 视频工具"
    assert "search.bilibili.com" in items[0]["url"]
    assert items[0]["metrics"]["heat"] == 888
    assert items[0]["evidence_role"] == "video_attention_signal"


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


def test_fetch_sspai_parses_public_rss(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "_read_text",
        lambda _url: """
        <rss><channel><item>
          <title>少数派文章</title>
          <link>https://sspai.com/post/1</link>
          <description><![CDATA[<p>效率工具摘要</p>]]></description>
          <pubDate>Fri, 01 May 2026 09:00:00 GMT</pubDate>
        </item></channel></rss>
        """,
    )

    items = hotnews.fetch_hotnews("sspai", limit=1)

    assert items[0]["source_id"] == "sspai"
    assert items[0]["title"] == "少数派文章"
    assert items[0]["evidence_role"] == "tech_reading_signal"


def test_fetch_xinzhiyuan_reads_wordpress_json(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "_read_json",
        lambda _url: [
            {
                "id": 42,
                "date_gmt": "2026-05-02T06:00:00",
                "link": "https://aiera.com.cn/ai-news",
                "title": {"rendered": "新模型 &amp; 新应用"},
                "excerpt": {"rendered": "<p>AI 产业摘要</p>"},
            }
        ],
    )

    items = hotnews.fetch_hotnews("xinzhiyuan", limit=1)

    assert items[0]["source_id"] == "xinzhiyuan"
    assert items[0]["title"] == "新模型 & 新应用"
    assert items[0]["summary"] == "AI 产业摘要"
    assert items[0]["metrics"]["post_id"] == 42
    assert items[0]["evidence_role"] == "ai_news_signal"


def test_fetch_youtube_ai_rss_parses_official_channel_feed(monkeypatch):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:yt="http://www.youtube.com/xml/schemas/2015"
          xmlns:media="http://search.yahoo.com/mrss/">
      <entry>
        <yt:videoId>abc123</yt:videoId>
        <title>AI 产品访谈</title>
        <link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
        <published>2026-05-02T05:00:00+00:00</published>
        <media:group><media:description>视频摘要</media:description></media:group>
      </entry>
    </feed>
    """
    monkeypatch.setattr(hotnews, "YOUTUBE_AI_CHANNELS", (("Test Channel", "UC1"),))
    monkeypatch.setattr(hotnews, "_read_text", lambda *_args, **_kwargs: xml)

    items = hotnews.fetch_hotnews("youtube-ai-rss", limit=1)

    assert items[0]["source_id"] == "youtube-ai-rss"
    assert items[0]["title"] == "AI 产品访谈"
    assert items[0]["url"] == "https://www.youtube.com/watch?v=abc123"
    assert items[0]["metrics"]["channel"] == "Test Channel"
    assert items[0]["evidence_role"] == "video_source_signal"


def test_fetch_zeli_hn_reads_public_api(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "_read_json",
        lambda _url: {
            "posts": [
                {
                    "id": "477",
                    "title": "HN AI 讨论",
                    "url": "https://news.ycombinator.com/item?id=477",
                    "time": 1760000000,
                }
            ]
        },
    )

    items = hotnews.fetch_hotnews("zeli-hn", limit=1)

    assert items[0]["source_id"] == "zeli-hn"
    assert items[0]["title"] == "HN AI 讨论"
    assert items[0]["metrics"]["hn_id"] == "477"
    assert items[0]["published_at"].startswith("2025-10-09")


def test_fetch_buzzing_reads_structured_feed(monkeypatch):
    monkeypatch.setattr(
        hotnews,
        "_read_json",
        lambda _url: {
            "items": [
                {
                    "title": "Global AI link",
                    "url": "https://example.com/ai",
                    "source": "example.com",
                    "category": "ai",
                    "date_published": "2026-05-02T04:00:00Z",
                }
            ]
        },
    )

    items = hotnews.fetch_hotnews("buzzing", limit=1)

    assert items[0]["source_id"] == "buzzing"
    assert items[0]["title"] == "Global AI link"
    assert items[0]["metrics"]["source"] == "example.com"
    assert items[0]["evidence_role"] == "global_tech_signal"


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
    monkeypatch.setattr(hotnews, "fetch_bilibili_hot_search", lambda limit=20: (_ for _ in ()).throw(RuntimeError("403")))
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
    monkeypatch.setattr(hotnews, "fetch_bilibili_hot_search", lambda limit=20: make_items("bilibili-hot-search", limit))
    monkeypatch.setattr(hotnews, "fetch_ithome", lambda limit=20: make_items("ithome", limit))
    monkeypatch.setattr(hotnews, "fetch_v2ex", lambda limit=20: make_items("v2ex", limit))

    items = hotnews.fetch_hotnews("today", limit=50)

    assert len(items) == 50
    assert items[-1]["rank"] == 50


def test_hotnews_build_trend_report_merges_cross_source_topics():
    items = [
        {"rank": 1, "source_id": "baidu", "title": "AI 眼镜新品发布", "metrics": {"heat": 10000}},
        {"rank": 2, "source_id": "weibo", "title": "AI眼镜 新品 引热议", "metrics": {"heat": 5000}},
        {"rank": 3, "source_id": "v2ex", "title": "Python 框架讨论"},
    ]

    report = hotnews.build_trend_report(items)

    assert report["trend_count"] == 2
    assert report["trends"][0]["source_count"] == 2
    assert {"baidu", "weibo"} <= set(report["trends"][0]["sources"])
    assert report["trends"][0]["resonance"] == "two-source"
    assert report["trends"][0]["research_commands"]
    md = hotnews.format_trend_report_markdown(report)
    assert "观澜趋势归并" in md
    assert "AI 眼镜新品发布" in md
    assert "共振" in md


def test_hotnews_trend_report_avoids_generic_bigram_false_merge():
    items = [
        {"rank": 1, "source_id": "baidu", "title": "袁隆平夫人收到了一份特殊礼物"},
        {"rank": 2, "source_id": "weibo", "title": "人到了一定年纪就会解锁的动作"},
    ]

    report = hotnews.build_trend_report(items)

    assert report["trend_count"] == 2
    assert all(trend["item_count"] == 1 for trend in report["trends"])


def test_hotnews_brief_includes_followup_queries():
    items = [
        hotnews.HotNewsItem(platform="baidu", source_id="baidu", category="hotnews", title="AI 眼镜新品发布", rank=1).to_dict(),
        hotnews.HotNewsItem(platform="weibo", source_id="weibo", category="social", title="AI眼镜 新品 引热议", rank=2).to_dict(),
    ]

    brief = hotnews.build_hotnews_brief(items)
    md = hotnews.format_hotnews_brief_markdown(brief)

    assert brief["sample_count"] == 2
    assert brief["highlights"][0]["research_queries"]
    assert "resonance" in brief["highlights"][0]
    assert "观澜今日水势简报" in md
    assert "继续查" in md


def test_hotnews_items_carry_evidence_metadata():
    item = hotnews.HotNewsItem(
        platform="weibo",
        source_id="weibo",
        category="social",
        title="讨论样本",
        url="https://weibo.com/example",
        rank=1,
    ).to_dict()

    enriched = hotnews.enrich_hotnews_item(item)
    distribution = hotnews.build_source_distribution([enriched])

    assert enriched["evidence_role"] == "public_discussion_signal"
    assert enriched["source_card"]["domain"] == "weibo.com"
    assert "sample_bias" in enriched["risk_tags"]
    assert distribution["evidence_role_counts"]["public_discussion_signal"] == 1


def test_compact_hotnews_items_preserves_evidence_boundary():
    compact = hotnews.compact_hotnews_items(
        [
            {
                "rank": 1,
                "source_id": "weibo",
                "title": "讨论样本",
                "url": "https://weibo.com/example",
                "summary": "这是一段较长的样本摘要" * 20,
                "metrics": {"heat": 123, "unused": "drop"},
            }
        ],
        summary_chars=12,
    )

    assert compact[0]["evidence_role"] == "public_discussion_signal"
    assert compact[0]["metrics"] == {"heat": 123}
    assert "sample_bias" in compact[0]["risk_tags"]
    assert compact[0]["source_card"]["domain"] == "weibo.com"
    assert len(compact[0]["summary"]) == 12


def test_hotnews_snapshot_compare_tracks_new_and_rank_changes(tmp_path):
    path = tmp_path / "snapshots.jsonl"
    previous = [
        {"source_id": "baidu", "title": "A", "url": "https://example.com/a", "rank": 2},
        {"source_id": "baidu", "title": "B", "url": "https://example.com/b", "rank": 1},
    ]
    current = [
        {"source_id": "baidu", "title": "A", "url": "https://example.com/a", "rank": 1},
        {"source_id": "baidu", "title": "C", "url": "https://example.com/c", "rank": 2},
    ]

    hotnews.save_hotnews_snapshot("baidu", previous, path=str(path))
    report = hotnews.build_hotnews_snapshot_report("baidu", current, save=True, path=str(path))
    md = hotnews.format_snapshot_report_markdown(report)

    assert report["previous_snapshot"]["item_count"] == 2
    assert report["comparison"]["new_items"][0]["title"] == "C"
    assert report["comparison"]["disappeared_items"][0]["title"] == "B"
    assert report["comparison"]["rank_changes"][0]["title"] == "A"
    assert "新上榜" in md


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
    assert "bilibili-hot-search" in data
    assert "ithome" in data
    assert "sspai" in data
    assert "xinzhiyuan" in data
    assert "youtube-ai-rss" in data
    assert "zeli-hn" in data
    assert "buzzing" in data
    assert "zhihu" in data
    assert data["zhihu"]["status"] == "experimental"
    assert data["zhihu"]["verified"] is False
    assert "v2ex" in data
    assert "newsnow:36kr-quick" in data
    assert data["bilibili-hot-search"]["backend"] == "native"
    assert data["newsnow:36kr-quick"]["backend"] == "optional"
    assert data["newsnow:36kr-quick"]["status"] == "optional"


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
