# -*- coding: utf-8 -*-
"""Tests for sidecar HTML report rendering."""

import json

from guanlan.reports import normalize_report_payload, render_html_report, write_html_report


def test_report_normalizes_plain_result_list():
    payload = [
        {
            "title": "Result A",
            "url": "https://example.com/a",
            "source_title": "Example",
            "snippet": "Useful context.",
            "score": 8.5,
            "value": "1万",
        }
    ]

    normalized = normalize_report_payload(payload, title="Demo")

    assert normalized["title"] == "Demo"
    assert normalized["items"][0]["title"] == "Result A"
    assert normalized["items"][0]["source"] == "Example"
    assert normalized["items"][0]["value"] == 10000


def test_report_html_escapes_content_and_drops_unsafe_href():
    html = render_html_report(
        {
            "title": "<script>bad()</script>",
            "items": [
                {
                    "title": "<b>Unsafe</b>",
                    "url": "javascript:alert(1)",
                    "summary": "<img src=x>",
                    "score": 9,
                }
            ],
        }
    )

    assert "&lt;script&gt;bad()&lt;/script&gt;" in html
    assert "&lt;b&gt;Unsafe&lt;/b&gt;" in html
    assert "&lt;img src=x&gt;" in html
    assert "javascript:alert" not in html
    assert "旁支能力" in html


def test_write_html_report_creates_single_file(tmp_path):
    output = tmp_path / "report.html"
    result = write_html_report(
        {
            "title": "测试报告",
            "items": [{"title": "A", "source": "S", "summary": "One", "score": 7}],
        },
        str(output),
    )

    assert result["path"] == str(output)
    assert result["items"] == 1
    html = output.read_text(encoding="utf-8")
    assert "测试报告" in html
    assert "local static HTML" in html


def test_json_payload_can_round_trip_to_report(tmp_path):
    payload = {
        "items": [
            {"title": "Feed", "source_id": "curated", "summary": "Article", "ai_score": 88}
        ]
    }
    input_path = tmp_path / "payload.json"
    output_path = tmp_path / "report.html"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = json.loads(input_path.read_text(encoding="utf-8"))
    result = write_html_report(loaded, str(output_path), score_mode="quality")

    assert result["score_mode"] == "quality"
    assert output_path.exists()
