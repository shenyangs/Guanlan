# -*- coding: utf-8 -*-
"""Tests for safe topic echo analysis."""

import json
from unittest.mock import patch

from guanlan import pulse


def _sample_results():
    return [
        {
            "rank": 1,
            "title": "产品售后被投诉，用户吐槽涨价和 bug",
            "url": "https://weibo.com/a",
            "domain": "weibo.com",
            "snippet": "不少用户表示失望，担忧隐私和稳定性问题。",
            "source_type": "社交/内容平台",
        },
        {
            "rank": 2,
            "title": "体验报告：设计方便但价格高",
            "url": "https://zhihu.com/b",
            "domain": "zhihu.com",
            "snippet": "优点是实用和高效，争议点是售后。",
            "source_type": "社交/内容平台",
        },
        {
            "rank": 3,
            "title": "公司回应用户质疑",
            "url": "https://example.com/c",
            "domain": "example.com",
            "snippet": "将改善服务并修复问题。",
            "source_type": "商业/产业媒体",
        },
    ]


def test_build_pulse_report_is_conservative(monkeypatch):
    monkeypatch.setattr("guanlan.webtools.search_web", lambda *args, **kwargs: _sample_results())

    report = pulse.build_pulse_report("某产品", limit=3)

    assert report["query"] == "某产品"
    assert report["sample_count"] == 3
    assert report["read_success"] == 0
    assert report["tendency"] in {"偏负向", "正负交织"}
    assert report["confidence"] in {"低", "低-中"}
    assert any(item["term"] == "投诉" for item in report["negative_terms"])
    assert any(item["term"] == "涨价" for item in report["controversy_terms"])
    assert "不代表全网舆论" in report["caveats"][0]


def test_format_pulse_markdown_shows_caveats(monkeypatch):
    monkeypatch.setattr("guanlan.webtools.search_web", lambda *args, **kwargs: _sample_results())

    md = pulse.format_pulse_markdown(pulse.build_pulse_report("某产品", limit=3))

    assert "# 观澜回响 / 某产品" in md
    assert "## 安全提示" in md
    assert "讨论倾向" in md
    assert "证据样本" in md


def test_pulse_context_is_prompt_friendly(monkeypatch):
    monkeypatch.setattr("guanlan.webtools.search_web", lambda *args, **kwargs: _sample_results())

    context = pulse.format_pulse_context(pulse.build_pulse_report("某产品", limit=3))

    assert "字段 | 内容" in context
    assert "来源 | 标题 | 摘要 | 倾向" in context
    assert "不代表全网舆论" in context


def test_pulse_cli_outputs_json(capsys):
    from guanlan.cli import main

    with patch("guanlan.webtools.search_web", return_value=_sample_results()):
        with patch("sys.argv", ["guanlan", "pulse", "某产品", "--json", "--limit", "3"]):
            main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["query"] == "某产品"
    assert payload["sample_count"] == 3
