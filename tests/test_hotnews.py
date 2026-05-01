# -*- coding: utf-8 -*-
"""Tests for native hotnews sources and formatters."""

import json
from unittest.mock import patch

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
    assert "baidu" in data
    assert "zhihu" in data
    assert "v2ex" in data


def test_format_hotnews_cli_reads_json(capsys):
    from guanlan.cli import main

    payload = json.dumps({"items": [{"title": "热榜标题", "url": "https://example.com"}]})
    with patch("sys.argv", ["guanlan", "format", "hotnews"]):
        with patch("sys.stdin.read", return_value=payload):
            main()
    captured = capsys.readouterr()
    assert "热榜标题" in captured.out
