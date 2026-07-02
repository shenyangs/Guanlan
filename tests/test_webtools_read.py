# -*- coding: utf-8 -*-
"""Tests for URL reading, batch reads, and read quality."""
# ruff: noqa: F401

import builtins
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from guanlan import webtools
from guanlan.limits import DEFAULT_READ_FALLBACK_LIMIT, DEFAULT_RESEARCH_LIMIT, DEFAULT_SEARCH_LIMIT
from guanlan.source_seeds import (
    direct_source_seeds,
    is_finance_lookup,
    is_live_sports_lookup,
    is_wps_office_lookup,
)
from tests.support.webtools_helpers import _FakeResponse


def test_wechat_sogou_optional_dependency_message(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "wechatsogou":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="wechat-sogou backend requires optional dependency"):
        webtools._build_wechat_sogou_api()


def test_read_url_uses_jina_reader(monkeypatch):
    requested = []

    def fake_urlopen(req, timeout=None):
        requested.append(req.full_url)
        return _FakeResponse("# Title\nContent")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    text = webtools.read_url("example.com/article", max_chars=8, backend="jina")

    assert requested == ["https://r.jina.ai/https://example.com/article"]
    assert text == "# Title\n"


def test_read_url_falls_back_to_direct_when_jina_fails(monkeypatch):
    requested = []

    def fake_urlopen(req, timeout=None):
        requested.append(req.full_url)
        if req.full_url.startswith("https://r.jina.ai/"):
            raise OSError("jina timeout")
        return _FakeResponse("<html><title>原网页</title><body><script>x</script>正文</body></html>")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    text = webtools.read_url("https://example.cn/article")

    assert requested == [
        "https://r.jina.ai/https://example.cn/article",
        "https://example.cn/article",
    ]
    assert "Title: 原网页" in text
    assert "正文" in text
    assert "script" not in text


def test_direct_html_reader_filters_navigation_and_footer_noise(monkeypatch):
    html = """
    <html>
      <head><title>测试新闻</title></head>
      <body>
        <nav>首页 新闻 财经 科技 登录 注册</nav>
        <header>下载APP 分享 收藏</header>
        <main class="article-content">
          <h1>测试新闻标题</h1>
          <p>这是第一段正文，包含足够多的中文内容，用来验证正文抽取是否保留核心信息。</p>
          <p>这是第二段正文，继续说明事件背景、公开资料和可验证线索。</p>
        </main>
        <footer>版权所有 ICP 备案 联系我们</footer>
      </body>
    </html>
    """
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(html))

    text = webtools.read_url("https://example.cn/article", backend="direct")

    assert "这是第一段正文" in text
    assert "这是第二段正文" in text
    assert "首页 新闻 财经" not in text
    assert "版权所有" not in text
    assert "登录 注册" not in text


def test_direct_html_reader_drops_related_login_and_app_noise(monkeypatch):
    html = """
    <html>
      <head><title>深度文章</title></head>
      <body>
        <div class="login-panel">登录后查看更多 打开APP</div>
        <article>
          <h1>产业观察</h1>
          <p>第一段正文说明产业变化、企业反馈和公开数据，足够长以成为有效正文。</p>
          <p>第二段正文继续补充政策背景、市场反应和后续观察重点。</p>
        </article>
        <div class="related-news">相关阅读 热门推荐 下一篇</div>
      </body>
    </html>
    """
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(html))

    text = webtools.read_url("https://example.cn/deep", backend="direct")

    assert "第一段正文说明产业变化" in text
    assert "第二段正文继续补充政策背景" in text
    assert "登录后查看更多" not in text
    assert "相关阅读" not in text


def test_direct_html_reader_decodes_gbk_charset(monkeypatch):
    html = """
    <html>
      <head><meta charset="gb2312"><title>联商测试</title></head>
      <body><article><p>即时零售行业进入质量深耕阶段，平台融合和供给效率成为重点。</p></article></body>
    </html>
    """.encode("gb18030")

    class GbkResponse:
        headers = {"content-type": "text/html; charset=gb2312"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            return html

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: GbkResponse())

    text = webtools.read_url("https://example.cn/gbk", backend="direct")

    assert "联商测试" in text
    assert "即时零售行业进入质量深耕阶段" in text
    assert "�" not in text


def test_read_url_treats_mojibake_jina_as_weak_and_falls_back(monkeypatch):
    requested = []

    def fake_urlopen(req, timeout=None):
        requested.append(req.full_url)
        if req.full_url.startswith("https://r.jina.ai/"):
            return _FakeResponse("Title: ��������\nMarkdown Content:\n������������������������")
        return _FakeResponse(
            "<html><title>正文</title><body><article>"
            "<p>这是干净的中文正文，说明降级读取成功，并且保留了足够多的上下文。</p>"
            "<p>第二段继续补充事件背景、来源说明、公开信息和可验证线索，避免被判定为弱读取。</p>"
            "<p>第三段提供更多正文长度，用于模拟真实新闻页面中的主体内容，而不是导航栏或登录提示。</p>"
            "</article></body></html>"
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    text = webtools.read_url("https://example.cn/article", backend="auto")

    assert requested == [
        "https://r.jina.ai/https://example.cn/article",
        "https://example.cn/article",
    ]
    assert "这是干净的中文正文" in text
    assert "����" not in text


def test_read_url_percent_encodes_cjk_url_before_network(monkeypatch):
    requested = []

    def fake_urlopen(req, timeout=None):
        requested.append(req.full_url)
        return _FakeResponse("# 百科\n中文路径读取成功")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    packet = webtools.read_url_with_trace(
        "https://baike.baidu.com/item/2026年WPS被指系统卡顿、强制占C盘事件/68033679",
        backend="jina",
    )

    assert requested
    assert "2026年" not in requested[0]
    assert "%E5%B9%B4" in requested[0]
    assert packet["url"].endswith("/68033679")
    assert packet["trace"]["request_url"].startswith("https://baike.baidu.com/item/2026%E5%B9%B4")
    assert "中文路径读取成功" in packet["content"]


def test_read_url_uses_wechat_article_extractor_before_jina(monkeypatch):
    html = """
    <html>
      <head>
        <meta property="og:title" content="我用 OpenClaw 做后端开发"/>
        <meta name="author" content="孟健"/>
      </head>
      <body>
        <div id="js_content" class="rich_media_content">
          <p>第一段公众号正文，说明 Agent 后端开发、支付集成和上线过程，保留足够多的可读信息。</p>
          <p>第二段继续说明 Stripe、数据库、部署、错误处理和调试过程，避免被当成登录壳。</p>
          <p>第三段补充复盘、公开经验和可验证的操作边界，确保正文长度足够稳定。</p>
        </div>
      </body>
    </html>
    """
    requested = []

    def fake_urlopen(req, timeout=None):
        requested.append(req.full_url)
        return _FakeResponse(html)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    packet = webtools.read_url_with_trace("https://mp.weixin.qq.com/s/example", backend="auto")

    assert requested == ["https://mp.weixin.qq.com/s/example"]
    assert packet["trace"]["selected_backend"] == "wechat_article"
    assert "Title: 我用 OpenClaw 做后端开发" in packet["content"]
    assert "Author: 孟健" in packet["content"]
    assert "第一段公众号正文" in packet["content"]
    assert "html(false" not in packet["content"]


def test_read_url_wechat_extractor_keeps_nested_article_and_drops_chrome(monkeypatch):
    html = """
    <html>
      <head>
        <script>var msg_title = "嵌套公众号正文"; var nickname = "观澜测试号"; var ct = "1778700000";</script>
      </head>
      <body>
        <div id="js_article">
          <div class="rich_media_meta_list">作者 二维码 分享</div>
          <div id="js_content" class="rich_media_content">
            <section><p>第一段正文里有嵌套 section 和 div，用来模拟公众号常见排版结构，也说明公开文章读取应当优先保留主体内容，而不是被外层标题栏、二维码或底部互动按钮污染。</p></section>
            <div><p>第二段正文继续展开品牌舆情、传播节点、媒体引用和证据边界，包含足够多的中文正文、标点和上下文，使质量画像判断它是一篇真实文章，而不是登录提示或页面壳。</p></div>
            <p>第三段正文补充公开文章的来源上下文、发布时间和后续归档方式，强调该路径只读取公开 HTML，不触碰 Cookie、credentials、IndexedDB 或公众号后台。</p>
            <div id="js_pc_qr_code">微信扫一扫 二维码</div>
          </div>
          <div id="js_article_bottom_bar">点赞 评论 分享</div>
        </div>
      </body>
    </html>
    """

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(html))

    packet = webtools.read_url_with_trace("https://mp.weixin.qq.com/s/nested", backend="auto")

    assert packet["trace"]["selected_backend"] == "wechat_article"
    assert "嵌套公众号正文" in packet["content"]
    assert "观澜测试号" in packet["content"]
    assert "第一段正文里有嵌套 section" in packet["content"]
    assert "第二段正文继续展开品牌舆情" in packet["content"]
    assert "微信扫一扫" not in packet["content"]
    assert "点赞 评论 分享" not in packet["content"]
    assert "wechat_public_article_html" in packet["content"]


def test_read_url_uses_search_context_when_reading_is_blocked(monkeypatch):
    monkeypatch.setattr(webtools, "_read_with_jina", lambda url: "请先登录后查看")
    monkeypatch.setattr(webtools, "_read_direct", lambda url: "访问受限，请完成安全验证")
    monkeypatch.setattr(
        webtools,
        "search_web",
        lambda query, limit=5, site=None, profile=None: [
            {
                "rank": 1,
                "source": "duckduckgo",
                "source_type": "通用网页",
                "title": "替代来源",
                "url": "https://example.com/mirror",
                "snippet": "公开搜索摘要",
                "score": 1.2,
            }
        ],
    )

    text = webtools.read_url(
        "https://example.com/articles/ai-report",
        fallback_search=True,
        fallback_limit=3,
    )

    assert "# 观澜阅读兜底" in text
    assert "原始 URL: https://example.com/articles/ai-report" in text
    assert "替代来源" in text
    assert "jina: weak or blocked content" in text
    assert "direct: weak or blocked content" in text


def test_read_url_does_not_emit_unverified_numeric_path_fallback(monkeypatch):
    monkeypatch.setattr(webtools, "_read_with_jina", lambda url: "请先登录后查看")
    monkeypatch.setattr(webtools, "_read_direct", lambda url: "访问受限，请完成安全验证")
    monkeypatch.setattr(
        webtools,
        "search_web",
        lambda query, limit=5, site=None, profile=None: [
            {
                "rank": 1,
                "source": "duckduckgo",
                "source_type": "通用网页",
                "title": "IT之家首页",
                "url": "https://www.ithome.com/",
                "snippet": "首页内容",
                "score": 1.2,
            },
            {
                "rank": 2,
                "source": "duckduckgo",
                "source_type": "通用网页",
                "title": "台湾 iThome 250",
                "url": "https://www.ithome.com.tw/news/250",
                "snippet": "不同站点内容",
                "score": 1.0,
            },
        ],
    )

    text = webtools.read_url(
        "https://www.ithome.com/0/946/250.htm",
        fallback_search=True,
        fallback_limit=3,
    )

    assert "兜底状态: unusable" in text
    assert "不要引用本页搜索兜底作为证据" in text
    assert "台湾 iThome" not in text


def test_strict_read_does_not_use_search_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(webtools, "_read_with_jina", lambda url: (_ for _ in ()).throw(OSError("ascii encode")))
    monkeypatch.setattr(webtools, "_read_direct", lambda url: (_ for _ in ()).throw(OSError("ascii encode")))
    monkeypatch.setattr(webtools, "search_web", lambda *args, **kwargs: calls.append((args, kwargs)) or [])

    with pytest.raises(RuntimeError, match="ascii encode"):
        webtools.read_url(
            "https://baike.baidu.com/item/2026年WPS被指系统卡顿、强制占C盘事件/68033679",
            backend="auto",
            fallback_search=True,
            strict=True,
        )

    assert calls == []


def test_strict_read_accepts_high_score_noisy_article(monkeypatch):
    article = "\n".join(
        [
            "Title: “背刺”用户？WPS吃相难看，金山办公利润涨疯！",
            "广告",
            *[
                "2026年6月21日，WPS相关话题引发用户讨论，正文持续介绍系统卡顿、缓存占用和会员收费争议。"
                for _ in range(30)
            ],
        ]
    )
    monkeypatch.setattr(webtools, "_read_with_jina", lambda url: (_ for _ in ()).throw(OSError("jina 503")))
    monkeypatch.setattr(webtools, "_read_direct", lambda url: article)

    packet = webtools.read_url_with_trace(
        "https://baijiahao.baidu.com/s?id=1868821907936304170&wfr=spider&for=pc",
        backend="auto",
        strict=True,
    )

    assert packet["trace"]["selected_backend"] == "direct"
    assert packet["quality"]["label"] == "noisy"
    assert packet["quality"]["strict_pass"] is True
    assert packet["quality_report"]["usable"] is True
    assert "WPS相关话题" in packet["content"]


def test_read_batch_keeps_per_url_status(monkeypatch):
    def fake_read(url, **kwargs):
        if "bad" in url:
            raise RuntimeError("blocked")
        return f"READ {url}"

    monkeypatch.setattr(webtools, "read_url", fake_read)

    records = webtools.read_batch(["https://good.example", "https://bad.example"])

    assert records[0]["status"] == "ok"
    assert records[0]["content"] == "READ https://good.example"
    assert records[1]["status"] == "error"
    assert records[1]["error"] == "blocked"


def test_read_batch_blocks_high_risk_social_domains(monkeypatch):
    called = []
    monkeypatch.setattr(webtools, "read_url", lambda url, **kwargs: called.append(url) or "content")

    records = webtools.read_batch(["https://www.xiaohongshu.com/explore/1", "https://example.com/a"])

    assert records[0]["status"] == "blocked"
    assert "authorization" in records[0]["error"]
    assert records[1]["status"] == "ok"
    assert called == ["https://example.com/a"]


def test_read_url_extracts_metadata_with_direct_backend(monkeypatch):
    html = """
    <html><head>
      <title>测试标题</title>
      <meta name="description" content="测试摘要">
      <meta property="article:published_time" content="2026-05-02">
    </head><body><article>正文</article></body></html>
    """

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(html))

    packet = webtools.read_url_with_trace(
        "https://example.com/a",
        backend="direct",
        extract="metadata",
    )

    assert "测试标题" in packet["content"]
    assert "article:published_time" in packet["content"]
    assert packet["trace"]["extract"] == "metadata"


def test_read_quality_report_flags_dynamic_finance_shell():
    text = "\n".join(
        [
            "东方财富行情中心",
            "沪深京 自选股 登录 注册",
            "数据加载中 请下载客户端 打开APP",
            "行情 板块 排名",
        ]
    )

    report = webtools.build_read_quality_report(
        text,
        url="https://quote.eastmoney.com/sh600519.html",
        quality=webtools.assess_read_quality(text),
    )

    assert report["dynamic_shell"] is True
    assert report["usable"] is False
    assert any("动态财经页壳" in item for item in report["recommendations"])
    rendered = webtools.format_read_quality_report(report)
    assert "dynamic_shell: true" in rendered


def test_read_quality_report_flags_xueqiu_waf_as_unusable():
    text = "\n".join(
        [
            "雪球-聪明的投资者都在这里",
            "登录 下载App",
            "系统检测到您的IP最近访问过于频繁，请验证以继续访问",
            "点击按钮进行验证 请点击重试",
        ]
    )

    report = webtools.build_read_quality_report(
        text,
        url="https://xueqiu.com/snowman/provider/zz/gp_detail?symbol=SH600519",
        quality=webtools.assess_read_quality(text),
    )

    assert report["usable"] is False
    assert report["dynamic_shell"] is True


def test_read_quality_report_flags_finance_upgrade_browser_shell():
    text = (
        "window.location.href='//finance.qq.com/gsfinance/upgrade_browser.htm' "
        "var url = 'https://galileotelemetry.tencent.com/collect'; "
        "window.AegisV2 = new Aegis({ id: 'SDK-demo' });"
    )

    report = webtools.build_read_quality_report(
        text,
        url="https://xueqiu.com/snowman/provider/zz/gp_detail?symbol=SH600519",
        quality=webtools.assess_read_quality(text),
    )

    assert report["usable"] is False
    assert report["dynamic_shell"] is True
    assert "upgrade_browser" in report["blocked_markers"]


def test_read_quality_report_marks_search_fallback_as_context_only():
    text = "# 观澜阅读兜底\n\n1. 搜索结果摘要，可作为继续核验线索。" + "补充内容" * 80

    report = webtools.build_read_quality_report(
        text,
        url="https://example.com/noisy",
        quality=webtools.assess_read_quality(text),
        trace={"selected_backend": "search_fallback"},
    )

    assert report["fallback"] is True
    assert report["usable"] is False
    assert webtools.format_read_quality_report(report).find("fallback: search_context_only") >= 0
    assert any("搜索兜底" in item for item in report["recommendations"])


def test_direct_article_extractor_uses_paragraph_density_when_container_is_noisy():
    raw = """
    <html><body>
      <div class="nav">首页 登录 注册 推荐阅读</div>
      <div class="layout"><div class="left">热门推荐 打开APP</div>
      <div class="weird-box">
        <p>第一段正文介绍政策背景，包含发布主体、适用范围和执行目标。</p>
        <p>第二段正文继续说明产业影响、地方落实路径和企业需要关注的事项。</p>
        <p>第三段正文给出后续安排，强调公开信息、权威来源和时间节点。</p>
      </div></div>
      <div class="footer">版权声明 联系我们</div>
    </body></html>
    """

    text = webtools._extract_article_text(raw)

    assert "第一段正文" in text
    assert "地方落实路径" in text
    assert "登录 注册" not in text
    assert "版权声明" not in text


def test_rank_results_merges_duplicate_sources():
    results = webtools.rank_results(
        [
            webtools.SearchResult(title="A", url="https://example.com/a?utm_source=x", source="bing"),
            webtools.SearchResult(title="A", url="https://www.example.com/a", source="duckduckgo"),
        ],
        query="A",
        backend_order=["bing", "duckduckgo"],
    )

    assert len(results) == 1
    assert results[0].source == "bing+duckduckgo"


def test_rank_results_clusters_same_topic_and_promotes_diversity():
    results = webtools.rank_results(
        [
            webtools.SearchResult(
                title="央行发布人工智能金融服务新规",
                url="https://example.com/a",
                source="bing",
                rank=1,
            ),
            webtools.SearchResult(
                title="人民银行发布人工智能金融服务新规 解读",
                url="https://example.cn/b",
                source="duckduckgo",
                rank=2,
            ),
            webtools.SearchResult(
                title="跨境电商平台推出新功能",
                url="https://example.org/c",
                source="baidu",
                rank=3,
            ),
        ],
        query="人工智能 金融",
        backend_order=["bing", "duckduckgo", "baidu"],
    )

    assert results[0].topic_role == "representative"
    assert results[0].topic_size == 2
    assert results[1].topic_role == "single"
    assert results[2].topic_role == "related"
    assert results[2].topic_key == results[0].topic_key


def test_rank_results_interleaves_source_types_for_better_evidence_mix():
    results = webtools.rank_results(
        [
            webtools.SearchResult(
                title="人工智能产业观察",
                url="https://people.com.cn/a",
                source="bing",
                rank=1,
            ),
            webtools.SearchResult(
                title="人工智能企业案例",
                url="https://xinhuanet.com/b",
                source="bing",
                rank=2,
            ),
            webtools.SearchResult(
                title="人工智能政策通知",
                url="https://gov.cn/c",
                source="bing",
                rank=3,
            ),
        ],
        query="人工智能",
        backend_order=["bing"],
    )

    assert [item.source_type for item in results[:3]] == ["党央媒", "政府/部委", "党央媒"]


def test_html_to_markdownish_prefers_chinese_article_body():
    html = """
    <html><head><title>标题</title><meta name="source" content="新华社">
    <meta property="article:published_time" content="2026-05-02"></head>
    <body>
      <nav>首页 新闻 财经 科技 登录 注册</nav>
      <div class="side recommend">推荐阅读 登录 下载APP</div>
      <div id="js_content">
        <p>这是第一段正文，介绍政策背景和核心事实。</p>
        <p>这是第二段正文，包含更多连续信息和分析。</p>
      </div>
      <footer>版权所有 联系我们</footer>
    </body></html>
    """
    text = webtools._html_to_markdownish(html, url="https://example.com/a")

    assert "Source: 新华社" in text
    assert "Published: 2026-05-02" in text
    assert "这是第一段正文" in text
    assert "下载APP" not in text


def test_read_watch_outputs_diff(monkeypatch, tmp_path):
    monkeypatch.setattr(webtools, "cache_dir", lambda: tmp_path / "cache")

    first = webtools._format_read_watch("https://example.com/a", "line one")
    second = webtools._format_read_watch("https://example.com/a", "line two")

    assert "首次快照" in first
    assert "发现内容变化" in second
    assert "-line one" in second
    assert "+line two" in second
