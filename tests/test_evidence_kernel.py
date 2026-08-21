# -*- coding: utf-8 -*-
"""Contract tests for the additive evidence provenance kernel."""

from guanlan.evidence_kernel import (
    build_document_snapshot,
    build_evidence_bundle,
    build_passages,
    extract_claim_candidates,
)


def test_snapshot_and_passage_ids_are_deterministic_and_offsets_round_trip():
    content = "# 发布说明\n\n价格是 ¥20，命中率 99.5%。\n\n## 日期\n\n发布日期为 2026-08-21。"
    left = build_document_snapshot(
        url="https://Example.com:443/release#top", content=content, title="说明"
    )
    right = build_document_snapshot(
        url="https://example.com/release", content=content, title="说明"
    )

    assert left["snapshot_id"] == right["snapshot_id"]
    passages = build_passages(left, content)
    assert passages
    assert all(content[item["char_start"] : item["char_end"]] == item["text"] for item in passages)
    assert passages[-1]["heading_path"] == ["发布说明", "日期"]


def test_claim_candidates_only_create_non_judgmental_mentions():
    content = "模型为 GPT-5，价格 ¥20，准确率 91%。普通句子不应产生事实关系。"
    snapshot = build_document_snapshot(url="https://example.com/a", content=content)
    passages = build_passages(snapshot, content)
    claims, links = extract_claim_candidates(passages)

    assert {claim["category"] for claim in claims} == {
        "model_version",
        "price",
        "percentage_metric",
    }
    assert {link["relation"] for link in links} == {"mentions"}
    assert all(
        content[claim["char_start"] : claim["char_end"]] == claim["value"] for claim in claims
    )
    assert not any(link["relation"] in {"supports", "refutes"} for link in links)


def test_bundle_uses_only_citable_page_bodies_for_snapshots():
    results = [
        {"url": "https://example.com/a", "title": "A", "source": "Example"},
        {"url": "https://clue.example/b", "title": "B", "source": "Clue"},
    ]
    packet = {
        "query": "版本",
        "results": results,
        "selected_evidence": results[:1],
        "readings": [
            {
                "url": "https://example.com/a",
                "title": "A",
                "source": "Example",
                "usable": True,
                "content": "# A\n\n版本为 GPT-5。",
                "extract_contract": {"can_cite_as_page_body": True},
            },
            {
                "url": "https://clue.example/b",
                "title": "B",
                "source": "Clue",
                "usable": True,
                "content": "搜索上下文中的 ¥999 不可作正文。",
                "extract_contract": {"can_cite_as_page_body": False},
            },
        ],
    }

    bundle = build_evidence_bundle(packet)

    assert bundle["schema_version"] == "evidence_bundle_v1"
    assert bundle["coverage"]["source_count"] == 2
    assert bundle["coverage"]["snapshot_count"] == 1
    assert {item["url"] for item in bundle["document_snapshots"]} == {"https://example.com/a"}
    assert {item["value"] for item in bundle["claim_candidates"]} == {"GPT-5"}
    assert packet["results"] is results


def test_non_citable_bundle_is_empty_but_explains_boundary():
    bundle = build_evidence_bundle({"query": "x", "results": [], "readings": []})

    assert bundle["document_snapshots"] == []
    assert bundle["passages"] == []
    assert bundle["claim_candidates"] == []
    assert "不代表支持" in bundle["boundary"]


def test_public_research_service_attaches_bundle_without_mutating_existing_results(monkeypatch):
    from guanlan.web import _impl, research

    results = [{"url": "https://example.com/a", "title": "A"}]
    legacy_packet = {
        "query": "A",
        "results": results,
        "selected_evidence": results[:],
        "readings": [],
        "existing_contract": {"unchanged": True},
    }

    def fake_build(*_args, **_kwargs):
        return legacy_packet

    monkeypatch.setattr(_impl._legacy, "build_research_packet", fake_build)
    monkeypatch.setitem(_impl._LEGACY_ORIGINALS, "build_research_packet", fake_build)

    packet = research.build_research_packet("A")

    assert packet["results"] is results
    assert packet["existing_contract"] == {"unchanged": True}
    assert packet["evidence_bundle_v1"]["schema_version"] == "evidence_bundle_v1"
