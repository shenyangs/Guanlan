# -*- coding: utf-8 -*-
"""Tests for webtools-backed CLI handlers."""
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


def test_bing_cjk_drift_cooldown_persists_for_cli_processes(tmp_path, monkeypatch):
    monkeypatch.setenv("GUANLAN_TEST_ALLOW_BACKEND_HEALTH", "1")
    monkeypatch.setattr(webtools, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(webtools, "_BING_CJK_DRIFT_UNTIL", 0.0)

    assert webtools._bing_cjk_drift_active() is False
    webtools._record_bing_cjk_drift()

    monkeypatch.setattr(webtools, "_BING_CJK_DRIFT_UNTIL", 0.0)
    assert webtools._bing_cjk_drift_active() is True
    assert webtools.backend_order("auto", "china", query="低空经济政策补贴") == [
        "baidu",
        "duckduckgo",
        "bing",
    ]


def test_search_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("guanlan.web.search.search_web", return_value=[{"title": "A", "url": "https://a"}]):
        with patch("sys.argv", ["guanlan", "search", "query", "--json"]):
            main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)[0]["title"] == "A"


def test_search_cli_outputs_empty_diagnostics_json(capsys):
    from guanlan.cli import main

    empty = webtools.SearchResults(
        [],
        diagnostics={
            "query": "blocked query",
            "backend_diagnostics": [{"backend": "baidu", "status": "blocked"}],
            "backend_recovery": {"status": "failed"},
        },
    )
    with patch("guanlan.web.search.search_web", return_value=empty):
        with patch("sys.argv", ["guanlan", "search", "blocked query", "--json"]):
            main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["results"] == []
    assert payload["diagnostics"]["backend_diagnostics"][0]["status"] == "blocked"


def test_search_cli_outputs_context(capsys):
    from guanlan.cli import main

    with patch(
        "guanlan.web.search.search_web",
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


def test_search_cli_outputs_prompt(capsys):
    from guanlan.cli import main

    with patch(
        "guanlan.web.search.search_web",
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
        with patch("sys.argv", ["guanlan", "search", "query", "--format", "prompt"]):
            main()
    captured = capsys.readouterr()
    assert "观澜搜索 Prompt" in captured.out
    assert "## 用户问题" in captured.out
    assert "query" in captured.out


def test_research_cli_outputs_json(capsys):
    from guanlan.cli import main

    packet = {"query": "query", "results": [], "readings": []}
    with patch("guanlan.web.research.build_research_packet", return_value=packet):
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
    assert "entertainment" in presets
    assert presets["entertainment"]["scope"] == "entertainment"
    assert presets["global_entertainment"]["scope"] == "global_entertainment"
    assert presets["jp_kr_entertainment"]["scope"] == "jp_kr_entertainment"
    assert presets["cybersecurity"]["scope"] == "cybersecurity"
    assert presets["sports"]["scope"] == "sports"
    assert presets["weather_disaster"]["scope"] == "weather_disaster"
    assert presets["science"]["scope"] == "science"
    assert presets["career"]["scope"] == "career"
    assert presets["podcast"]["scope"] == "podcast"
    assert presets["test_prep"]["scope"] == "test_prep"
    assert presets["finance"]["scope"] == "finance"
    assert "finance_disclosure" in presets["finance"]["scopes"]
    assert "finance_quote" in presets["finance"]["scopes"]
    assert "university" in presets
    assert presets["university"]["scope"] == "university"


def test_search_cli_lists_scopes(capsys):
    from guanlan.cli import main

    with patch("sys.argv", ["guanlan", "search", "--list-scopes"]):
        main()
    captured = capsys.readouterr()
    scopes = json.loads(captured.out)
    assert "party_central" in scopes
    assert "ecommerce" in scopes


def test_prompt_cli_builds_local_llm_prompt(capsys):
    from guanlan.cli import main

    packet = {
        "query": "本地模型联网",
        "results": [],
        "selected_evidence": [],
        "readings": [],
        "guidance": ["保留来源"],
    }
    with patch("guanlan.web.research.build_research_packet", return_value=packet) as mocked:
        with patch("sys.argv", ["guanlan", "prompt", "本地模型联网", "--limit", "80"]):
            main()
    captured = capsys.readouterr()
    assert "观澜本地模型联网 Prompt" in captured.out
    assert "本地模型联网" in captured.out
    assert mocked.call_args.kwargs["limit"] == 80
    assert mocked.call_args.kwargs["advisor"] is True


def test_prompt_cli_passes_prompt_style(capsys):
    from guanlan.cli import main

    packet = {
        "query": "本地模型联网",
        "results": [],
        "selected_evidence": [],
        "readings": [],
        "guidance": [],
    }
    with patch("guanlan.web.research.build_research_packet", return_value=packet):
        with patch("sys.argv", ["guanlan", "prompt", "本地模型联网", "--style", "decision", "--read-top", "0"]):
            main()
    captured = capsys.readouterr()
    assert "当前输出风格: decision" in captured.out


def test_context_cli_alias_builds_local_llm_prompt(capsys):
    from guanlan.cli import main

    packet = {
        "query": "本地模型联网",
        "results": [],
        "selected_evidence": [],
        "readings": [],
        "guidance": [],
    }
    with patch("guanlan.web.research.build_research_packet", return_value=packet) as mocked:
        with patch("sys.argv", ["guanlan", "context", "本地模型联网", "--read-top", "0"]):
            main()
    captured = capsys.readouterr()

    assert "观澜本地模型联网 Prompt" in captured.out
    assert mocked.call_args.kwargs["read_top"] == 0


def test_read_cli_outputs_text(capsys):
    from guanlan.cli import main

    with patch("guanlan.web.read.read_url", return_value="content"):
        with patch("sys.argv", ["guanlan", "read", "https://example.com"]):
            main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "content"


def test_read_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("guanlan.web.read.read_url", return_value="content"):
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--format", "json"]):
            main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["url"] == "https://example.com"
    assert payload["content"] == "content"


def test_read_cli_outputs_context(capsys):
    from guanlan.cli import main

    with patch("guanlan.web.read.read_url", return_value="content"):
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--format", "context"]):
            main()
    captured = capsys.readouterr()
    assert "# 观澜阅读上下文" in captured.out
    assert "URL: https://example.com" in captured.out
    assert "content" in captured.out


def test_read_cli_outputs_trace_json(capsys):
    from guanlan.cli import main

    packet = {
        "url": "https://example.com",
        "content": "content",
        "quality": {"label": "clean", "score": 100},
        "trace": {"selected_backend": "direct", "attempts": []},
    }
    with patch("guanlan.web.read.read_url_with_trace", return_value=packet):
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--format", "json", "--trace"]):
            main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["quality"]["label"] == "clean"
    assert payload["trace"]["selected_backend"] == "direct"


def test_read_cli_batch_outputs_json(capsys, tmp_path):
    from guanlan.cli import main

    url_file = tmp_path / "urls.txt"
    url_file.write_text("https://example.com/a\nhttps://example.com/b\n", encoding="utf-8")
    records = [{"rank": 1, "url": "https://example.com/a", "status": "ok", "content": "A"}]
    with patch("guanlan.web.read.read_batch", return_value=records):
        with patch("sys.argv", ["guanlan", "read", "batch", str(url_file), "--format", "json"]):
            main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)[0]["content"] == "A"


def test_read_cli_passes_backend():
    from guanlan.cli import main

    with patch("guanlan.web.read.read_url", return_value="content") as mocked:
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--backend", "direct"]):
            main()

    mocked.assert_called_once_with(
        "https://example.com",
        max_chars=None,
        backend="direct",
        fallback_search=True,
        fallback_limit=DEFAULT_READ_FALLBACK_LIMIT,
        profile="china",
        cache_ttl=0,
        use_cache=True,
        watch=False,
    )


def test_read_cli_quality_report_uses_trace_packet(capsys):
    from guanlan.cli import main

    packet = {
        "url": "https://example.com",
        "content": "这是正文内容。" * 30,
        "quality": webtools.assess_read_quality("这是正文内容。" * 30),
        "trace": {"selected_backend": "direct", "cache": "disabled"},
    }
    packet["quality_report"] = webtools.build_read_quality_report(
        packet["content"],
        url=packet["url"],
        quality=packet["quality"],
        trace=packet["trace"],
    )
    with patch("guanlan.web.read.read_url_with_trace", return_value=packet):
        with patch("sys.argv", ["guanlan", "read", "https://example.com", "--quality-report"]):
            main()
    captured = capsys.readouterr()

    assert "阅读质量报告" in captured.out
    assert "阅读 Trace" not in captured.out


def test_search_cli_outputs_source_chart(capsys):
    from guanlan.cli import main

    with patch(
        "guanlan.web.search.search_web",
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
