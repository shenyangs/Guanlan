# -*- coding: utf-8 -*-
"""Runtime contract guards for downstream agents."""

from guanlan import archive, webtools


def test_search_result_runtime_contract_keeps_evidence_metadata():
    results = webtools.rank_results(
        [
            webtools.SearchResult(
                title="国务院人工智能政策原文",
                url="https://www.gov.cn/zhengce/ai.htm",
                snippet="政策原文和发布时间",
                source="fixture",
            )
        ],
        query="人工智能 政策 原文",
        backend_order=["fixture"],
        preferred_scope="gov",
    )
    payload = results[0].to_dict()

    for field in ["title", "url", "snippet", "domain", "source_type", "evidence_role", "score", "trace"]:
        assert field in payload
    assert payload["trace"]["source_card"]["authority_score"] >= 0
    assert "risk_tags" in payload["trace"]["source_card"]


def test_research_packet_runtime_contract_keeps_route_and_diagnostics(monkeypatch):
    monkeypatch.setattr(
        "guanlan.webtools._research_search",
        lambda *args, **kwargs: (
            [
                {
                    "title": "政策原文",
                    "url": "https://www.gov.cn/zhengce/ai.htm",
                    "snippet": "政策原文",
                    "domain": "gov.cn",
                    "source_type": "政府/部委",
                    "evidence_role": "official_primary",
                    "score": 100,
                    "rank": 1,
                    "trace": {"source_card": {"risk_tags": []}},
                }
            ],
            [],
            [],
        ),
    )

    packet = webtools.build_research_packet(
        "人工智能 政策 原文",
        preset="policy",
        profile="china",
        limit=50,
        read_top=0,
    )

    for field in [
        "query",
        "preset",
        "result_count",
        "route_plan",
        "query_strategy",
        "results",
        "selected_evidence",
        "source_diagnostics",
        "readings",
        "read_quality_summary",
    ]:
        assert field in packet
    assert packet["result_count"] == 1
    assert packet["route_plan"]["limit"] >= 50


def test_archive_runtime_contract_keeps_rag_and_quality_metadata(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document(
        "https://example.com/a",
        "# 标题\n正文包含人工智能政策材料。" * 10,
        metadata={"source_type": "政府/部委", "topic_key": "policy"},
        db_path=db,
    )

    record = archive.search_documents("人工智能政策", trace=True, db_path=db)[0]
    exported = archive.export_documents(db_path=db)[0]

    assert record["metadata"]["source_card"]
    assert record["metadata"]["read_quality"]
    assert record["metadata"]["quality_report"]
    assert record["search_trace"]["semantic"] == "not-vector"
    assert exported["rag"]["source"] == "https://example.com/a"
    assert exported["rag"]["source_type"] == "政府/部委"
