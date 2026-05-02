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


def test_feed_source_catalog_describes_routing():
    catalog = feeds.list_feed_sources()

    assert {"curated", "curated-sources", "baidu-rss", "wechat-rss"} <= set(catalog)
    assert catalog["curated"]["backend"] == "native"
    assert catalog["wechat-rss"]["status"] == "best-effort"
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
