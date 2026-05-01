# -*- coding: utf-8 -*-
"""Tests for agent-facing search and read primitives."""

import json
from unittest.mock import patch

from guanlan import webtools


class _FakeResponse:
    def __init__(self, text: str, content_type: str = "text/html"):
        self._text = text
        self.headers = {"content-type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        return self._text.encode()


def test_search_web_parses_duckduckgo_html(monkeypatch):
    html = """
    <html>
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Example A</a>
      <a class="result__snippet">First snippet</a>
      <a class="result__a" href="https://example.com/b">Example B</a>
    </html>
    """

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(html),
    )

    results = webtools.search_web("agent search", limit=5)

    assert len(results) == 2
    assert results[0]["title"] == "Example A"
    assert results[0]["url"] == "https://example.com/a"
    assert results[0]["snippet"] == "First snippet"
    assert results[0]["rank"] == 1
    assert results[0]["domain"] == "example.com"
    assert results[0]["source_type"] == "通用网页"
    assert results[0]["score"] > 0


def test_search_web_trace_keeps_score_parts(monkeypatch):
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: [
            webtools.SearchResult(title="Agent search result", url="https://example.com/a")
        ],
    )

    results = webtools.search_web("agent search", backend="duckduckgo", trace=True)

    assert "score_parts" in results[0]
    assert results[0]["score_parts"]["keyword_match"] > 0
    assert results[0]["trace"]["cache"] == "disabled"


def test_search_web_cache_ttl_reuses_results(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(webtools, "cache_dir", lambda: tmp_path / "cache")

    def fake_search(query, limit=10):
        calls.append(query)
        return [webtools.SearchResult(title="Cached", url="https://example.com/cache")]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    first = webtools.search_web("cache query", backend="duckduckgo", cache_ttl=3600, trace=True)
    monkeypatch.setattr(
        webtools,
        "_search_duckduckgo",
        lambda query, limit=10: (_ for _ in ()).throw(RuntimeError("network should not run")),
    )
    second = webtools.search_web("cache query", backend="duckduckgo", cache_ttl=3600, trace=True)

    assert len(calls) == 1
    assert first[0]["title"] == "Cached"
    assert second[0]["title"] == "Cached"
    assert second[0]["trace"]["cache"] == "hit"


def test_search_web_plugin_backend(tmp_path):
    plugin = tmp_path / "plugin_backend.py"
    plugin.write_text(
        "import json, sys\n"
        "query = sys.argv[1]\n"
        "print(json.dumps([{'title': 'Plugin ' + query, 'url': 'https://internal.example/a', 'snippet': 'S'}]))\n",
        encoding="utf-8",
    )

    results = webtools.search_web("knowledge", backend=f"plugin:{plugin}", limit=1)

    assert results[0]["title"] == "Plugin knowledge"
    assert results[0]["source"].startswith("plugin:")


def test_search_web_uses_china_backend_order():
    assert webtools.backend_order("auto", "china") == ["baidu", "bing", "duckduckgo"]


def test_search_web_applies_scope(monkeypatch):
    requested = []

    def fake_search(query, limit=10):
        requested.append(query)
        return [webtools.SearchResult(title="A", url="https://people.com.cn/a")]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "人工智能",
        backend="duckduckgo",
        scope="party_central",
        limit=1,
    )

    assert "site:people.com.cn" in requested[0]
    assert results[0]["title"] == "A"
    assert results[0]["source_type"] == "党央媒"
    assert results[0]["matched_scope"] == "party_central"


def test_search_web_prefers_requested_scope_for_overlapping_domains(monkeypatch):
    def fake_search(query, limit=10):
        return [webtools.SearchResult(title="亿邦动力", url="https://ebrun.com/article")]

    monkeypatch.setattr(webtools, "_search_duckduckgo", fake_search)

    results = webtools.search_web(
        "跨境电商",
        backend="duckduckgo",
        scope="ecommerce",
        limit=1,
    )

    assert results[0]["source_type"] == "电商/零售垂类"
    assert results[0]["matched_scope"] == "ecommerce"


def test_search_web_parses_bing_html(monkeypatch):
    html = """
    <ol id="b_results">
      <li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9h">Bing A</a></h2>
      <p>Bing snippet</p></li>
    </ol>
    """

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(html),
    )

    results = webtools.search_web("agent search", backend="bing", limit=5)

    assert results[0]["source"] == "bing"
    assert results[0]["title"] == "Bing A"
    assert results[0]["url"] == "https://example.com/a"
    assert results[0]["snippet"] == "Bing snippet"


def test_search_web_parses_baidu_html(monkeypatch):
    html = """
    <div class="result c-container" mu="https://example.cn/a">
      <h3 class="t"><a href="http://www.baidu.com/link?url=abc">百度结果</a></h3>
      <div class="c-abstract">百度摘要</div>
    </div>
    """

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(html),
    )

    results = webtools.search_web("agent search", backend="baidu", limit=5)

    assert results[0]["source"] == "baidu"
    assert results[0]["title"] == "百度结果"
    assert results[0]["url"] == "https://example.cn/a"
    assert results[0]["snippet"] == "百度摘要"


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


def test_format_search_markdown():
    md = webtools.format_search_markdown(
        [
            {
                "rank": 1,
                "source": "duckduckgo",
                "title": "Result",
                "url": "https://example.com",
                "snippet": "Snippet",
            }
        ]
    )

    assert "# 观澜搜索" in md
    assert "1. [duckduckgo/通用网页" in md
    assert "Result" in md
    assert "https://example.com" in md


def test_search_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("guanlan.webtools.search_web", return_value=[{"title": "A", "url": "https://a"}]):
        with patch("sys.argv", ["guanlan", "search", "query", "--json"]):
            main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)[0]["title"] == "A"


def test_search_cli_outputs_context(capsys):
    from guanlan.cli import main

    with patch(
        "guanlan.webtools.search_web",
        return_value=[
            {
                "title": "A",
                "url": "https://a.example",
                "snippet": "S",
                "source_type": "通用网页",
                "score": 1.0,
            }
        ],
    ):
        with patch("sys.argv", ["guanlan", "search", "query", "--format", "context"]):
            main()
    captured = capsys.readouterr()
    assert "观澜搜索上下文" in captured.out
    assert "[A](https://a.example)" in captured.out


def test_research_cli_outputs_json(capsys):
    from guanlan.cli import main

    packet = {"query": "query", "results": [], "readings": []}
    with patch("guanlan.webtools.build_research_packet", return_value=packet):
        with patch("sys.argv", ["guanlan", "research", "query", "--json", "--read-top", "0"]):
            main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)["query"] == "query"


def test_research_cli_lists_presets(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "research", "--list-presets"]):
        main()
    captured = capsys.readouterr()
    presets = json.loads(captured.out)
    assert "policy" in presets
    assert presets["policy"]["scope"] == "gov"


def test_search_cli_lists_scopes(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "search", "--list-scopes"]):
        main()
    captured = capsys.readouterr()
    scopes = json.loads(captured.out)
    assert "party_central" in scopes
    assert "ecommerce" in scopes


def test_read_cli_outputs_text(capsys):
    from guanlan.cli import main

    with patch("guanlan.webtools.read_url", return_value="content"):
        with patch("sys.argv", ["guanlan", "read", "https://example.com"]):
            main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "content"


def test_read_cli_batch_outputs_json(capsys, tmp_path):
    from guanlan.cli import main

    url_file = tmp_path / "urls.txt"
    url_file.write_text("https://example.com/a\nhttps://example.com/b\n", encoding="utf-8")
    records = [{"rank": 1, "url": "https://example.com/a", "status": "ok", "content": "A"}]
    with patch("guanlan.webtools.read_batch", return_value=records):
        with patch("sys.argv", ["guanlan", "read", "batch", str(url_file), "--format", "json"]):
            main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)[0]["content"] == "A"


def test_read_cli_passes_backend():
    from guanlan.cli import main

    with patch("guanlan.webtools.read_url", return_value="content") as mocked:
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--backend", "direct"]):
            main()

    mocked.assert_called_once_with(
        "https://example.com",
        max_chars=None,
        backend="direct",
        fallback_search=True,
        fallback_limit=5,
        profile="china",
        cache_ttl=0,
        use_cache=True,
        watch=False,
    )


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


def test_format_search_markdown_shows_topic_cluster():
    md = webtools.format_search_markdown(
        [
            {
                "rank": 1,
                "source": "bing",
                "source_type": "通用网页",
                "title": "同题代表",
                "url": "https://example.com/a",
                "topic_role": "representative",
                "topic_size": 2,
            }
        ]
    )

    assert "topic=representative/2" in md


def test_format_search_context_is_compact_table():
    context = webtools.format_search_context(
        [
            {
                "rank": 1,
                "source_type": "党央媒",
                "title": "结果",
                "url": "https://example.com/a",
                "snippet": "摘要",
                "score": 1.5,
                "topic_key": "topic-1",
                "topic_role": "single",
            }
        ]
    )

    assert "来源 | 标题 | 摘要 | 可信度 | Topic" in context
    assert "[结果](https://example.com/a)" in context


def test_format_source_chart_shows_type_and_domain_distribution():
    chart = webtools.format_source_chart(
        [
            {
                "source_type": "党央媒",
                "domain": "people.com.cn",
                "url": "https://people.com.cn/a",
            },
            {
                "source_type": "党央媒",
                "domain": "xinhuanet.com",
                "url": "https://xinhuanet.com/b",
            },
            {
                "source_type": "社交/内容平台",
                "domain": "zhihu.com",
                "url": "https://zhihu.com/c",
            },
        ]
    )

    assert "## 来源分布" in chart
    assert "党央媒" in chart
    assert "66.7%" in chart
    assert "people.com.cn" in chart
    assert "#" in chart


def test_search_cli_outputs_source_chart(capsys):
    from guanlan.cli import main

    with patch(
        "guanlan.webtools.search_web",
        return_value=[
            {
                "title": "A",
                "url": "https://people.com.cn/a",
                "domain": "people.com.cn",
                "source_type": "党央媒",
            }
        ],
    ):
        with patch("sys.argv", ["guanlan", "search", "query", "--source-chart"]):
            main()
    captured = capsys.readouterr()
    assert "观澜搜索" in captured.out
    assert "来源分布" in captured.out
    assert "people.com.cn" in captured.out


def test_build_research_packet_reads_representative_results(monkeypatch):
    search_results = [
        {
            "rank": 1,
            "title": "代表结果",
            "url": "https://example.com/a",
            "source_type": "党央媒",
            "topic_key": "topic-1",
            "topic_role": "representative",
        },
        {
            "rank": 2,
            "title": "相关转载",
            "url": "https://example.com/b",
            "source_type": "党央媒",
            "topic_key": "topic-1",
            "topic_role": "related",
        },
        {
            "rank": 3,
            "title": "另一视角",
            "url": "https://gov.cn/c",
            "source_type": "政府/部委",
            "topic_key": "topic-2",
            "topic_role": "single",
        },
    ]

    monkeypatch.setattr(webtools, "search_web", lambda *args, **kwargs: search_results)
    monkeypatch.setattr(webtools, "read_url", lambda url, **kwargs: f"READ {url}")

    packet = webtools.build_research_packet("人工智能", read_top=2)

    assert packet["query"] == "人工智能"
    assert packet["result_count"] == 3
    assert packet["topic_count"] == 2
    assert packet["source_mix"] == {"党央媒": 2, "政府/部委": 1}
    assert [item["url"] for item in packet["readings"]] == [
        "https://example.com/a",
        "https://gov.cn/c",
    ]
    assert packet["readings"][0]["content"] == "READ https://example.com/a"


def test_build_research_packet_applies_preset_defaults(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(webtools, "search_web", fake_search)

    packet = webtools.build_research_packet("人工智能监管", preset="policy")

    assert [call["scope"] for call in calls] == ["gov", "party_central"]
    assert all(call["limit"] == 6 for call in calls)
    assert packet["preset"] == "policy"
    assert packet["scope"] == "gov"
    assert packet["scopes"] == ["gov", "party_central"]
    assert packet["read_top"] == 3


def test_build_research_packet_user_scope_overrides_preset(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(webtools, "search_web", fake_search)

    packet = webtools.build_research_packet(
        "人工智能监管",
        preset="policy",
        scope="party_central",
        read_top=0,
    )

    assert [call["scope"] for call in calls] == ["party_central"]
    assert packet["scope"] == "party_central"
    assert packet["scopes"] == ["party_central"]
    assert packet["read_top"] == 0


def test_build_research_packet_site_request_skips_preset_scopes(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(webtools, "search_web", fake_search)

    packet = webtools.build_research_packet(
        "用户评价",
        preset="reputation",
        site="zhihu.com",
    )

    assert calls == [
        {
            "limit": 10,
            "site": "zhihu.com",
            "scope": None,
            "backend": "auto",
            "profile": "china",
        }
    ]
    assert packet["scope"] == "social_web"
    assert packet["scopes"] == []


def test_build_research_packet_preset_adds_site_evidence_groups(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        target = kwargs.get("scope") or kwargs.get("site") or "web"
        return [
            {
                "rank": 1,
                "title": f"{target} result",
                "url": f"https://example.com/{len(calls)}",
                "source_type": "通用网页",
                "score": 1.0,
            }
        ]

    monkeypatch.setattr(webtools, "search_web", fake_search)

    packet = webtools.build_research_packet("产品评价", preset="reputation", read_top=0)

    searched_scopes = [call.get("scope") for call in calls if call.get("scope")]
    searched_sites = [call.get("site") for call in calls if call.get("site")]
    assert searched_scopes == ["social_web", "tech_dev", "business"]
    assert "zhihu.com" in searched_sites
    assert "weibo.com" in searched_sites
    assert packet["sites"][:2] == ["zhihu.com", "weibo.com"]
    assert {group["type"] for group in packet["result_groups"]} == {"scope", "site"}


def test_format_research_markdown():
    md = webtools.format_research_markdown(
        {
            "query": "人工智能",
            "result_count": 1,
            "topic_count": 1,
            "source_mix": {"党央媒": 1},
            "guidance": ["优先交叉验证。"],
            "results": [
                {
                    "rank": 1,
                    "source": "bing",
                    "source_type": "党央媒",
                    "title": "结果",
                    "url": "https://example.com/a",
                }
            ],
            "readings": [
                {
                    "title": "结果",
                    "url": "https://example.com/a",
                    "source_type": "党央媒",
                    "status": "ok",
                    "content": "正文摘录",
                }
            ],
        }
    )

    assert "# 观澜研究证据包 / 人工智能" in md
    assert "## 信源概览" in md
    assert "党央媒: 1" in md
    assert "正文摘录" in md


def test_read_watch_outputs_diff(monkeypatch, tmp_path):
    monkeypatch.setattr(webtools, "cache_dir", lambda: tmp_path / "cache")

    first = webtools._format_read_watch("https://example.com/a", "line one")
    second = webtools._format_read_watch("https://example.com/a", "line two")

    assert "首次快照" in first
    assert "发现内容变化" in second
    assert "-line one" in second
    assert "+line two" in second
