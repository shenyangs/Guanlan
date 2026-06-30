# -*- coding: utf-8 -*-
"""Tests for public RSS/OPML feed discovery."""

from guanlan import feeds


def test_fetch_curated_builds_filtered_public_rss_url(monkeypatch):
    calls = []

    def fake_fetch(url, limit=50, source_id="rss", **_kwargs):
        calls.append((url, limit, source_id))
        return [{"title": "AI Article", "url": "https://example.com", "source_id": source_id}]

    monkeypatch.setattr(feeds, "fetch_rss_feed", fake_fetch)

    items = feeds.fetch_curated(
        limit=5,
        language="zh",
        category="ai",
        resource_type="article",
        featured=True,
        min_score=90,
        keyword="Agent",
        time_filter="1d",
    )

    assert items[0]["source_id"] == "curated"
    url, limit, source_id = calls[0]
    assert url.startswith("https://www." + "best" + "blogs" + ".dev/zh/feeds/rss?")
    assert "category=ai" in url
    assert "type=article" in url
    assert "featured=y" in url
    assert "minScore=90" in url
    assert "keyword=Agent" in url
    assert "timeFilter=1d" in url
    assert limit == 5
    assert source_id == "curated"


def test_fetch_rss_feed_normalizes_entries(monkeypatch):
    raw = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Test Feed</title>
      <item>
        <title>Example &amp; Article</title>
        <link>https://example.com/a</link>
        <description><![CDATA[<p>Useful <b>summary</b>.</p>]]></description>
        <author>Alice</author>
        <category>AI</category>
        <category>Agent</category>
        <pubDate>Sat, 02 May 2026 06:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    monkeypatch.setattr(feeds, "_read_bytes", lambda *_args, **_kwargs: raw)

    items = feeds.fetch_rss_feed("https://example.com/rss", limit=3, source_id="demo")

    assert items[0]["title"] == "Example & Article"
    assert items[0]["url"] == "https://example.com/a"
    assert items[0]["source_id"] == "demo"
    assert items[0]["source_title"] == "Test Feed"
    assert items[0]["category"] == "reading"
    assert items[0]["published_at"] == "Sat, 02 May 2026 06:00:00 GMT"
    assert items[0]["author"] == "Alice"
    assert items[0]["summary"] == "Useful summary."
    assert items[0]["tags"] == ["AI", "Agent"]
    assert items[0]["metrics"] == {}
    assert items[0]["rank"] == 1
    assert items[0]["source_confidence"] == "medium"
    assert items[0]["evidence_role"] == "reading_signal"
    assert items[0]["source_card"]["domain"] == "example.com"
    assert items[0]["freshness"] == "dated"
    assert items[0]["fetched_at"]
    assert items[0]["feed_status"]["status"] == "fresh"


def test_fetch_rss_feed_uses_stale_cache_on_timeout(monkeypatch, tmp_path):
    raw = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Test Feed</title>
      <item><title>Cached Article</title><link>https://example.com/a</link></item>
    </channel></rss>"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(feeds, "_read_bytes", lambda *_args, **_kwargs: raw)

    fresh = feeds.fetch_rss_feed("https://example.com/rss", limit=3, source_id="demo")
    assert fresh[0]["feed_status"]["status"] == "fresh"

    def fail_read(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(feeds, "_read_bytes", fail_read)
    stale = feeds.fetch_rss_feed("https://example.com/rss", limit=3, source_id="demo")

    assert stale[0]["title"] == "Cached Article"
    assert stale[0]["feed_status"]["status"] == "stale_cache"
    assert stale[0]["feed_status"]["stale"] is True
    assert "stale_cache" in stale[0]["risk_tags"]
    assert "缓存兜底" in feeds.format_feed_items_markdown(stale)


def test_fetch_rss_feed_returns_diagnostic_item_without_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    def fail_read(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(feeds, "_read_bytes", fail_read)

    items = feeds.fetch_rss_feed("https://example.com/rss", limit=3, source_id="demo")

    assert items[0]["feed_status"]["status"] == "error"
    assert "source_unavailable" in items[0]["risk_tags"]
    assert "稍后重试" in items[0]["summary"]


def test_curated_feed_omits_index_url_without_original_link(monkeypatch):
    index_url = feeds.build_curated_rss_url().replace("/feeds/rss", "/article/abc123")
    raw = f"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Index Feed</title>
      <item>
        <title>Indexed Article</title>
        <link>{index_url}</link>
        <description>Useful summary without original URL.</description>
      </item>
    </channel></rss>""".encode()
    monkeypatch.setattr(feeds, "_read_bytes", lambda *_args, **_kwargs: raw)

    items = feeds.fetch_rss_feed("https://example.com/rss", limit=1, source_id="curated")

    assert items[0]["title"] == "Indexed Article"
    assert items[0]["url"] == ""
    assert items[0]["source_card"]["domain"] == ""
    assert "index_link_omitted" in items[0]["risk_tags"]
    assert feeds._CURATED_DOMAIN not in feeds.format_feed_items_markdown(items)


def test_curated_feed_prefers_original_link_from_summary(monkeypatch):
    index_url = feeds.build_curated_rss_url().replace("/feeds/rss", "/article/abc123")
    raw = f"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Index Feed</title>
      <item>
        <title>Indexed Article</title>
        <link>{index_url}</link>
        <description><![CDATA[<a href="https://original.example.com/post">原文</a>]]></description>
      </item>
    </channel></rss>""".encode()
    monkeypatch.setattr(feeds, "_read_bytes", lambda *_args, **_kwargs: raw)

    items = feeds.fetch_rss_feed("https://example.com/rss", limit=1, source_id="curated")

    assert items[0]["url"] == "https://original.example.com/post"
    assert items[0]["source_card"]["domain"] == "original.example.com"


def test_curated_feed_ignores_wechat_avatar_url(monkeypatch):
    raw = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Index Feed</title>
      <item>
        <title>Wechat Article</title>
        <link>http://wx.qlogo.cn/mmhead/example/0</link>
        <description>Useful summary without original URL.</description>
      </item>
    </channel></rss>"""
    monkeypatch.setattr(feeds, "_read_bytes", lambda *_args, **_kwargs: raw)

    items = feeds.fetch_rss_feed("https://example.com/rss", limit=1, source_id="curated")

    assert items[0]["url"] == ""
    assert "wx.qlogo.cn" not in feeds.format_feed_items_context(items)


def test_list_curated_sources_reads_opml_catalog(monkeypatch):
    raw = b"""<?xml version="1.0"?>
    <opml version="2.0"><body>
      <outline text="LangChain Blog" title="LangChain Blog" type="rss" xmlUrl="https://blog.langchain.dev/rss/"/>
      <outline text="Other" title="Other" type="rss" xmlUrl="https://example.com/rss"/>
    </body></opml>"""
    monkeypatch.setattr(feeds, "_read_bytes", lambda *_args, **_kwargs: raw)

    sources = feeds.list_curated_sources(limit=10, query="langchain")

    assert len(sources) == 1
    assert sources[0]["title"] == "LangChain Blog"
    assert sources[0]["url"] == "https://blog.langchain.dev/rss/"
    assert sources[0]["source_id"] == "curated:source"


def test_list_curated_sources_omits_proxy_urls(monkeypatch):
    proxy_url = "https://wechat2rss." + feeds._CURATED_DOMAIN + "/feed/example.xml"
    raw = f"""<?xml version="1.0"?>
    <opml version="2.0"><body>
      <outline text="Proxy Source" title="Proxy Source" type="rss" xmlUrl="{proxy_url}"/>
    </body></opml>""".encode()
    monkeypatch.setattr(feeds, "_read_bytes", lambda *_args, **_kwargs: raw)

    sources = feeds.list_curated_sources(limit=10)

    assert sources[0]["title"] == "Proxy Source"
    assert sources[0]["url"] == ""
    assert feeds._CURATED_DOMAIN not in feeds.format_feed_sources_markdown(sources)


def test_named_dynamic_sources_normalize_heat_and_wechat(monkeypatch):
    payloads = {
        feeds.AISHORT_BAIDU_RSS_URL: """<rss><channel><title>百度实时热点</title><item>
        <title>热点标题 热度：12345</title><link>https://baidu.example</link>
        <description>摘要</description></item></channel></rss>""".encode(),
        feeds.AISHORT_WECHAT_RSS_URL: """<rss><channel><title>瓦斯阅读</title><item>
        <title>微信热文</title><link>https://mp.weixin.qq.com/s/example</link>
        <description>长摘要</description></item></channel></rss>""".encode(),
    }
    monkeypatch.setattr(feeds, "_read_bytes", lambda url, **_kwargs: payloads[url])

    baidu = feeds.fetch_feed_source("baidu-rss", limit=1)
    wechat = feeds.fetch_feed_source("wechat-rss", limit=1)

    assert baidu[0]["title"] == "热点标题"
    assert baidu[0]["metrics"]["heat"] == 12345
    assert baidu[0]["category"] == "hotnews"
    assert baidu[0]["evidence_role"] == "fresh_trend_signal"
    assert wechat[0]["source_id"] == "wechat-rss"
    assert wechat[0]["category"] == "wechat"
    assert wechat[0]["evidence_role"] == "wechat_article_signal"


def test_fetch_ai_vertical_signals_uses_api_and_keeps_boundary(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    calls = []

    def fake_read_json(url, **_kwargs):
        calls.append(url)
        return {
            "count": 1,
            "items": [
                {
                    "id": "ai-1",
                    "title": "Claude Code 新能力发布",
                    "url": "https://claude.com/blog/example",
                    "source": "Claude Blog",
                    "publishedAt": "2026-05-13T00:00:00.000Z",
                    "summary": "摘要层线索，重要事实应回读原文。",
                    "category": "ai-products",
                }
            ],
        }

    monkeypatch.setattr(feeds, "_read_json", fake_read_json)

    items = feeds.fetch_ai_vertical_signals("WPS AI PPT Agent 办公选题", limit=3)

    assert "category=ai-products" in calls[0]
    assert "mode=selected" in calls[0]
    assert items[0]["source_id"] == "ai-vertical"
    assert items[0]["source_title"] == "AI 垂类精选动态源"
    assert items[0]["evidence_role"] == "ai_vertical_discovery_signal"
    assert "source_requires_original_verification" in items[0]["risk_tags"]
    assert items[0]["feed_status"]["status"] == "fresh"


def test_ai_vertical_signals_use_stale_cache_on_api_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        feeds,
        "_read_json",
        lambda *_args, **_kwargs: {
            "items": [
                {
                    "title": "Cached AI item",
                    "url": "https://example.com/ai",
                    "summary": "cached",
                    "category": "industry",
                }
            ]
        },
    )
    assert feeds.fetch_ai_vertical_signals("AI 行业动态", limit=1)[0]["feed_status"]["status"] == "fresh"

    def fail_json(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(feeds, "_read_json", fail_json)
    stale = feeds.fetch_ai_vertical_signals("AI 行业动态", limit=1)

    assert stale[0]["title"] == "Cached AI item"
    assert stale[0]["feed_status"]["status"] == "stale_cache"
    assert "stale_cache" in stale[0]["risk_tags"]


def test_fetch_feed_source_supports_ai_vertical(monkeypatch):
    seen = {}

    def fake_fetch(query="", **kwargs):
        seen["query"] = query
        seen.update(kwargs)
        return [{"title": "AI 动态", "url": "https://example.com/ai", "source_id": "ai-vertical"}]

    monkeypatch.setattr(feeds, "fetch_ai_vertical_signals", fake_fetch)

    items = feeds.fetch_feed_source("aihot", keyword="WPS AI", category="industry", limit=2)

    assert items[0]["source_id"] == "ai-vertical"
    assert seen["query"] == "WPS AI"
    assert seen["keyword"] == "WPS AI"
    assert seen["category"] == "industry"


def test_fetch_feed_source_supports_ai_official_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    official_feeds = (
        {
            "title": "OpenAI News",
            "xml_url": "https://example.com/openai/rss.xml",
            "html_url": "https://openai.com/news",
            "max_entries": 3,
        },
        {
            "title": "GitHub Changelog",
            "xml_url": "https://example.com/github/changelog.xml",
            "html_url": "https://github.blog/changelog/",
            "include_keywords": "copilot,ai",
            "max_entries": 3,
        },
    )
    monkeypatch.setattr(feeds, "AI_OFFICIAL_FEEDS", official_feeds)
    payloads = {
        "https://example.com/openai/rss.xml": b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><title>OpenAI News</title>
          <item>
            <title>OpenAI launches GPT Agent</title>
            <link>https://openai.com/news/gpt-agent</link>
            <description>Official product update.</description>
            <pubDate>Tue, 30 Jun 2026 08:00:00 GMT</pubDate>
          </item>
        </channel></rss>""",
        "https://example.com/github/changelog.xml": b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><title>GitHub Changelog</title>
          <item>
            <title>Restrict issue creation to collaborators</title>
            <link>https://github.blog/changelog/non-ai</link>
            <description>Repository settings update.</description>
            <pubDate>Tue, 30 Jun 2026 06:00:00 GMT</pubDate>
          </item>
          <item>
            <title>Copilot model update</title>
            <link>https://github.blog/changelog/copilot-model</link>
            <description>AI coding model update.</description>
            <pubDate>Tue, 30 Jun 2026 07:00:00 GMT</pubDate>
          </item>
        </channel></rss>""",
    }
    monkeypatch.setattr(feeds, "_read_bytes", lambda url, **_kwargs: payloads[url])

    items = feeds.fetch_feed_source("official-ai", limit=5)
    titles = [item["title"] for item in items]

    assert "OpenAI launches GPT Agent" in titles
    assert "Copilot model update" in titles
    assert "Restrict issue creation to collaborators" not in titles
    assert items[0]["source_id"] == "ai-official"
    assert items[0]["source_title"] == "AI 官方更新流"
    assert items[0]["evidence_role"] == "official_ai_update_signal"
    assert items[0]["feed_source"]["title"] in {"OpenAI News", "GitHub Changelog"}
    assert "source_requires_original_verification" in items[0]["risk_tags"]


def test_fetch_feed_source_supports_ai_media_strict_title_filter(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    media_feeds = (
        {
            "title": "The Verge",
            "xml_url": "https://example.com/verge/rss.xml",
            "html_url": "https://www.theverge.com/ai-artificial-intelligence",
            "include_keywords": "ai,openai",
            "strict_title_filter": True,
            "max_entries": 3,
        },
    )
    monkeypatch.setattr(feeds, "AI_MEDIA_FEEDS", media_feeds)
    raw = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>The Verge</title>
      <item>
        <title>Streaming hardware sale</title>
        <link>https://www.theverge.com/deals/hardware</link>
        <description>This unrelated summary mentions AI once.</description>
        <pubDate>Tue, 30 Jun 2026 08:00:00 GMT</pubDate>
      </item>
      <item>
        <title>OpenAI previews new AI coding agent</title>
        <link>https://www.theverge.com/ai/openai-agent</link>
        <description>External reporting signal.</description>
        <pubDate>Tue, 30 Jun 2026 09:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    monkeypatch.setattr(feeds, "_read_bytes", lambda *_args, **_kwargs: raw)

    items = feeds.fetch_feed_source("ai-news-media", keyword="coding", limit=5)

    assert len(items) == 1
    assert items[0]["title"] == "OpenAI previews new AI coding agent"
    assert items[0]["source_id"] == "ai-media"
    assert items[0]["source_title"] == "AI 媒体观察流"
    assert items[0]["evidence_role"] == "ai_media_report_signal"
    assert "media_framing" in items[0]["risk_tags"]


def test_fetch_arxiv_normalizes_public_api_results(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    raw = b"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2605.05191v1</id>
        <updated>2026-05-06T12:00:00Z</updated>
        <published>2026-05-06T12:00:00Z</published>
        <title>LongSeeker: Elastic Context Orchestration</title>
        <summary> A paper about search agents. </summary>
        <author><name>Alice</name></author>
        <author><name>Bob</name></author>
        <link href="https://arxiv.org/abs/2605.05191" rel="alternate"/>
      </entry>
    </feed>"""
    calls = []

    def fake_read(url, **_kwargs):
        calls.append(url)
        return raw

    monkeypatch.setattr(feeds, "_read_bytes", fake_read)

    items = feeds.fetch_feed_source("arxiv", keyword="AI Agent browser assist", limit=3)

    assert "search_query=all%3AAI+Agent+browser+assist" in calls[0]
    assert items[0]["source_id"] == "arxiv"
    assert items[0]["title"] == "LongSeeker: Elastic Context Orchestration"
    assert items[0]["url"] == "https://arxiv.org/abs/2605.05191"
    assert items[0]["author"] == "Alice, Bob"
    assert items[0]["evidence_role"] == "preprint_record"
    assert "preprint_not_peer_reviewed" in items[0]["risk_tags"]


def test_fetch_arxiv_returns_search_entrypoint_when_api_is_limited(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    def fail_read(*_args, **_kwargs):
        raise TimeoutError("rate limited")

    monkeypatch.setattr(feeds, "_read_bytes", fail_read)

    items = feeds.fetch_feed_source("arxiv", keyword="AI Agent browser assist", limit=3)

    assert items[0]["evidence_role"] == "preprint_search_entrypoint"
    assert "arxiv.org/search" in items[0]["url"]
    assert items[0]["feed_status"]["status"] == "fallback_entrypoint"
    assert items[1]["feed_status"]["status"] == "error"


def test_fetch_watchlist_reads_explicit_feed_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    watchlist = tmp_path / "feeds.json"
    watchlist.write_text(
        '[{"title":"Simon","url":"https://simon.example/atom.xml","category":"tech"}]',
        encoding="utf-8",
    )
    raw = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Simon Feed</title>
      <item><title>Live blog</title><link>https://simon.example/live</link><pubDate>Thu, 07 May 2026 06:00:00 GMT</pubDate></item>
    </channel></rss>"""
    monkeypatch.setattr(feeds, "_read_bytes", lambda *_args, **_kwargs: raw)

    items = feeds.fetch_feed_source("watchlist", watchlist_path=watchlist, limit=5)

    assert items[0]["source_id"] == "watchlist"
    assert items[0]["title"] == "Live blog"
    assert items[0]["watchlist_source"]["title"] == "Simon"
    assert items[0]["evidence_role"] == "watchlist_update_signal"
    assert "user_watchlist" in items[0]["risk_tags"]


def test_fetch_watchlist_reports_missing_file_without_external_binary(tmp_path):
    items = feeds.fetch_watchlist(path=tmp_path / "missing.json", limit=5)

    assert items[0]["source_id"] == "watchlist"
    assert items[0]["feed_status"]["status"] == "error"
    assert "订阅源清单" in items[0]["feed_status"]["error"]


def test_feed_source_catalog_describes_routing():
    catalog = feeds.list_feed_sources()

    assert {
        "curated",
        "curated-sources",
        "ai-official",
        "ai-media",
        "ai-vertical",
        "baidu-rss",
        "wechat-rss",
        "arxiv",
        "watchlist",
    } <= set(catalog)
    assert catalog["curated"]["backend"] == "native"
    assert catalog["ai-official"]["evidence_role"] == "official_ai_update_signal"
    assert catalog["ai-media"]["evidence_role"] == "ai_media_report_signal"
    assert catalog["wechat-rss"]["status"] == "best-effort"
    assert catalog["arxiv"]["evidence_role"] == "preprint_record"
    assert catalog["watchlist"]["evidence_role"] == "watchlist_update_signal"
    assert "路由" in feeds.format_feed_catalog_markdown(catalog)


def test_feed_markdown_is_agent_readable():
    md = feeds.format_feed_items_markdown(
        [
            {
                "title": "Scaling Pain",
                "url": "https://example.com/a",
                "source_title": "精品内容流",
                "summary": "A useful engineering write-up.",
                "tags": ["AI", "Systems"],
            }
        ],
        title="观澜内容发现 / 精品内容流",
    )

    assert "# 观澜内容发现 / 精品内容流" in md
    assert "[精品内容流] Scaling Pain" in md
    assert "摘要: A useful engineering write-up." in md


def test_compact_feed_items_keeps_source_evidence():
    compact = feeds.compact_feed_items(
        [
            {
                "rank": 1,
                "source_id": "baidu-rss",
                "source_title": "百度实时热点 RSS",
                "title": "热点标题",
                "url": "https://example.com/a",
                "summary": "一段较长摘要" * 20,
                "metrics": {"heat": 123, "unused": "drop"},
                "evidence_role": "fresh_trend_signal",
                "freshness": "near_realtime",
                "risk_tags": ["third_party_rss"],
                "source_card": {"domain": "example.com", "source_type": "媒体/内容源"},
            }
        ],
        summary_chars=12,
    )

    assert compact[0]["metrics"] == {"heat": 123}
    assert compact[0]["evidence_role"] == "fresh_trend_signal"
    assert compact[0]["source_card"]["domain"] == "example.com"
    assert len(compact[0]["summary"]) <= 12
