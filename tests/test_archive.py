# -*- coding: utf-8 -*-
"""Tests for Guanlan local archive."""

import json
from unittest.mock import patch

from guanlan import archive


def test_archive_add_document_and_search(tmp_path):
    db = tmp_path / "archive.db"

    record = archive.add_document(
        "example.com/policy",
        "# 人工智能政策\n\n这是一份关于人工智能政策和治理的材料。",
        db_path=db,
    )
    results = archive.search_documents("人工智能", db_path=db)

    assert record["status"] == "created"
    assert record["title"] == "人工智能政策"
    assert results[0]["title"] == "人工智能政策"
    assert "人工智能" in results[0]["excerpt"]
    assert results[0]["metadata"]["source_card"]["domain"] == "example.com"
    assert results[0]["metadata"]["read_quality"]["chars"] > 0


def test_archive_search_recalls_chinese_technical_terms_without_exact_phrase(tmp_path):
    db = tmp_path / "archive.db"

    archive.add_document(
        "https://example.com/kv-cache",
        "# KV Cache 优化\n\n本文讨论推理服务里的 PagedAttention，并介绍 vLLM 与 SGLang 如何管理 KV Cache。"
        "KIVI 用于 KV Cache 量化，KVQuant 也属于相关优化方向。",
        db_path=db,
    )

    framework_results = archive.search_documents("开源推理框架 vLLM SGLang", db_path=db)
    quant_results = archive.search_documents("KV Cache 量化方法 KIVI", db_path=db)

    assert framework_results[0]["title"] == "KV Cache 优化"
    assert "vLLM" in framework_results[0]["excerpt"] or "SGLang" in framework_results[0]["excerpt"]
    assert quant_results[0]["title"] == "KV Cache 优化"
    assert "KIVI" in quant_results[0]["excerpt"]


def test_archive_search_trace_explains_matched_terms(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document(
        "https://example.com/kv-cache",
        "# KV Cache 优化\n\nvLLM 与 SGLang 使用 PagedAttention 管理 KV Cache。",
        db_path=db,
    )

    results = archive.search_documents("开源推理框架 vLLM SGLang", trace=True, db_path=db)

    trace = results[0]["search_trace"]
    assert "vLLM" in trace["matched_terms"]
    assert "content" in trace["field_hits"]
    assert trace["semantic"] == "not-vector"


def test_archive_search_diagnostics_explain_empty_hits(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document("https://example.com/a", "# Alpha\n正文包含本地资料。", db_path=db)

    diagnostics = archive.archive_search_diagnostics("不存在的主题", records=[], db_path=db)

    assert diagnostics["documents"] == 1
    assert diagnostics["results"] == 0
    assert diagnostics["semantic"] == "not-vector"
    assert diagnostics["guidance"]


def test_archive_verify_checks_recall_and_quality(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document(
        "https://example.com/kv-cache",
        "# KV Cache 优化\n\nvLLM 与 SGLang 使用 PagedAttention 管理 KV Cache。",
        metadata={"read_quality": {"label": "clean", "score": 80}},
        db_path=db,
    )

    report = archive.verify_archive(db_path=db)
    rendered = archive.format_archive_verify(report)

    assert report["status"] == "ok"
    assert report["checks"]["sample_recall"] == "ok"
    assert report["recall_samples"][0]["status"] == "ok"
    assert "本地知识库体检" in rendered


def test_archive_updates_existing_url(tmp_path):
    db = tmp_path / "archive.db"

    first = archive.add_document("https://example.com/a", "# 旧标题\n旧内容", db_path=db)
    second = archive.add_document("https://example.com/a", "# 新标题\n新内容", db_path=db)
    docs = archive.list_documents(db_path=db)

    assert first["status"] == "created"
    assert second["status"] == "updated"
    assert len(docs) == 1
    assert docs[0]["title"] == "新标题"


def test_archive_add_url_uses_reader(tmp_path, monkeypatch):
    from guanlan import webtools

    db = tmp_path / "archive.db"
    monkeypatch.setattr(webtools, "read_url", lambda url, **kwargs: "# 标题\n正文")

    record = archive.add_url("https://example.com/article", db_path=db)

    assert record["status"] == "created"
    assert record["title"] == "标题"


def test_archive_add_browser_visible_note_preserves_boundary(tmp_path):
    db = tmp_path / "archive.db"

    record = archive.add_browser_visible_note(
        "https://www.xiaohongshu.com/explore/abc",
        "这是一段用户授权读取的浏览器可见笔记内容，包含产品口碑样本。",
        title="小红书口碑样本",
        author="可见作者",
        db_path=db,
    )
    results = archive.search_documents("产品口碑", db_path=db)
    metadata = results[0]["metadata"]

    assert record["browser_assisted"] is True
    assert record["visible_page_only"] is True
    assert metadata["source_mode"] == "browser_visible"
    assert metadata["browser_assisted"] is True
    assert metadata["visible_page_only"] is True
    assert metadata["user_authorized"] is True
    assert metadata["platform"] == "xiaohongshu"
    assert metadata["safety_boundary"]["credential_access"] == "forbidden"


def test_archive_cli_add_browser_note_outputs_json(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    with patch(
        "sys.argv",
        [
            "guanlan",
            "archive",
            "add-browser-note",
            "--url",
            "https://zhihu.com/question/1",
            "--text",
            "用户授权读取的可见回答内容",
            "--title",
            "知乎回答",
            "--db",
            str(db),
            "--json",
        ],
    ):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["browser_assisted"] is True
    assert payload["source_mode"] == "browser_visible"
    record = archive.search_documents("可见回答", db_path=db)[0]
    assert record["metadata"]["platform"] == "zhihu"
    assert record["metadata"]["evidence_chain"]["planned_by"] == "guanlan_browser_assist"

    with patch("sys.argv", ["guanlan", "archive", "inspect", str(record["id"]), "--db", str(db)]):
        main()
    inspected = capsys.readouterr()
    assert "浏览器辅助补证边界" in inspected.out


def test_archive_cli_add_browser_note_from_json_ingests_host_browser_payload(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    payload = tmp_path / "browser-notes.jsonl"
    payload.write_text(
        json.dumps(
            {
                "url": "https://www.xiaohongshu.com/explore/abc",
                "title": "小红书可见笔记",
                "visible_text": "这是宿主 Agent 在用户授权后从浏览器可见页读取到的正文。" * 4,
                "platform": "xiaohongshu",
                "author": "可见作者",
                "engagement_summary": "点赞 12，收藏 3",
                "visible_comment_summary": "可见评论集中讨论使用体验。",
                "captured_at": "2026-05-04T10:00:00+08:00",
                "source_mode": "browser_visible",
                "browser_assisted": True,
                "user_authorized": True,
                "visible_page_only": True,
                "session_dependent": True,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with patch(
        "sys.argv",
        [
            "guanlan",
            "archive",
            "add-browser-note",
            "--from-json",
            str(payload),
            "--db",
            str(db),
            "--json",
        ],
    ):
        main()

    captured = capsys.readouterr()
    records = json.loads(captured.out)
    assert records[0]["browser_assisted"] is True
    assert records[0]["browser_visible_quality"]["status"] == "pass"
    record = archive.search_documents("浏览器可见页", db_path=db)[0]
    assert record["metadata"]["source_mode"] == "browser_visible"
    assert record["metadata"]["schema_version"] == "browser_visible_v2"
    assert record["metadata"]["session_dependent"] is True
    assert record["metadata"]["browser_visible_fields"]["engagement_summary"] == "点赞 12，收藏 3"
    assert record["metadata"]["browser_visible_quality"]["usable"] is True


def test_archive_browser_note_rejects_sensitive_payload_keys(tmp_path):
    records = archive.add_browser_visible_payloads(
        [
            {
                "url": "https://www.xiaohongshu.com/explore/abc",
                "title": "不应入库",
                "visible_text": "正文",
                "cookies": "secret",
            }
        ],
        db_path=tmp_path / "archive.db",
    )

    assert records[0]["status"] == "error"
    assert "forbidden keys" in records[0]["error"]


def test_archive_format_context(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document("https://example.com/a", "# 标题\n正文包含跨境电商。", db_path=db)

    context = archive.format_archive_context(archive.search_documents("跨境电商", db_path=db))

    assert "来源 | 主题 | 内容层级 | 标题 | 摘要 | 时间" in context
    assert "[标题](https://example.com/a)" in context


def test_archive_cli_search_outputs_json(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    archive.add_document("https://example.com/a", "# 标题\n正文包含政策。", db_path=db)

    with patch("sys.argv", ["guanlan", "archive", "search", "政策", "--db", str(db), "--json"]):
        main()
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert payload[0]["title"] == "标题"


def test_archive_cli_search_trace_outputs_reasoning(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    archive.add_document("https://example.com/kv", "# KV Cache\nvLLM 和 SGLang", db_path=db)

    with patch("sys.argv", ["guanlan", "archive", "search", "vLLM SGLang", "--db", str(db), "--trace"]):
        main()
    captured = capsys.readouterr()

    assert "Archive Search Trace" in captured.out
    assert "vLLM" in captured.out


def test_archive_inspect_remove_and_reindex(tmp_path):
    db = tmp_path / "archive.db"
    record = archive.add_document("https://example.com/a", "# 标题\n正文", db_path=db)

    inspected = archive.inspect_document(str(record["id"]), db_path=db)
    reindexed = archive.reindex_archive(db_path=db)
    removed = archive.remove_document(str(record["id"]), db_path=db)

    assert inspected["content"].startswith("# 标题")
    assert inspected["diagnostics"]["has_content"] is True
    assert reindexed["documents"] == 1
    assert removed["status"] == "removed"
    assert archive.list_documents(db_path=db) == []


def test_archive_cli_add_batch_respects_blocked_records(tmp_path, capsys, monkeypatch):
    from guanlan import webtools
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    urls = tmp_path / "urls.txt"
    urls.write_text("https://www.xiaohongshu.com/explore/1\nhttps://example.com/a\n", encoding="utf-8")
    monkeypatch.setattr(webtools, "read_url", lambda url, **kwargs: "# 标题\n正文")

    with patch("sys.argv", ["guanlan", "archive", "add", "batch", str(urls), "--db", str(db), "--format", "json"]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload[0]["status"] == "blocked"
    assert payload[1]["status"] == "created"


def test_archive_export_filters_and_adds_rag_fields(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document(
        "https://gov.cn/a",
        "# 政策原文\n正文",
        metadata={"source_type": "政府/部委", "topic_key": "policy"},
        db_path=db,
    )
    archive.add_document(
        "https://example.com/b",
        "# 普通文章\n正文",
        metadata={"source_type": "通用网页", "topic_key": "general"},
        db_path=db,
    )

    records = archive.export_documents(db_path=db, source_type="政府", topic="policy")

    assert len(records) == 1
    assert records[0]["domain"] == "gov.cn"
    assert records[0]["rag"]["source_type"] == "政府/部委"
    assert records[0]["rag"]["topic"] == "policy"


def test_archive_export_can_filter_by_read_quality(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document(
        "https://good.example/a",
        "# 高质量正文\n" + "正文内容。" * 80,
        metadata={"read_quality": {"label": "clean", "score": 88}},
        db_path=db,
    )
    archive.add_document(
        "https://noisy.example/b",
        "# 噪声页面\n登录 注册 首页",
        metadata={"read_quality": {"label": "noisy", "score": 35}},
        db_path=db,
    )

    records = archive.export_documents(db_path=db, min_quality=60)

    assert len(records) == 1
    assert records[0]["domain"] == "good.example"


def test_archive_quality_summary_and_cli_stats(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    archive.add_document(
        "https://good.example/a",
        "# 高质量正文\n" + "正文内容。" * 80,
        metadata={"read_quality": {"label": "clean", "score": 88}, "ingest_audit": {"decision": "keep"}},
        db_path=db,
    )
    archive.add_document(
        "https://noisy.example/b",
        "# 噪声页面\n登录 注册 首页",
        metadata={"read_quality": {"label": "noisy", "score": 35}},
        db_path=db,
    )

    summary = archive.archive_quality_summary(db_path=db, rag_min_quality=60)
    assert summary["documents"] == 2
    assert summary["rag_ready"] == 1
    assert summary["low_quality"] == 1
    assert summary["with_ingest_audit"] == 1

    with patch("sys.argv", ["guanlan", "archive", "stats", "--quality", "--db", str(db)]):
        main()
    captured = capsys.readouterr()

    assert "质量概览" in captured.out
    assert "RAG-ready 文档" in captured.out


def test_archive_cli_export_rag_jsonl(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    archive.add_document(
        "https://gov.cn/a",
        "# 政策原文\n正文",
        metadata={"source_type": "政府/部委", "topic_key": "policy"},
        db_path=db,
    )

    with patch("sys.argv", ["guanlan", "archive", "export", "--format", "rag-jsonl", "--db", str(db)]):
        main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["id"].startswith("guanlan-")
    assert payload["source"] == "https://gov.cn/a"
    assert payload["text"].startswith("# 政策原文")


def test_archive_export_profiles_for_common_rag_loaders(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document(
        "https://example.com/a",
        "# 标题\n正文",
        metadata={"source_type": "技术", "topic_key": "agent"},
        db_path=db,
    )
    records = archive.export_documents(db_path=db)

    llama = archive.export_record_for_profile(records[0], "llamaindex-jsonl")
    langchain = archive.export_record_for_profile(records[0], "langchain-jsonl")
    openwebui = archive.export_record_for_profile(records[0], "openwebui-jsonl")

    assert llama["text"].startswith("# 标题")
    assert llama["metadata"]["tool"] == "guanlan"
    assert llama["metadata"]["topic_label"] == "AI Agent"
    assert llama["metadata"]["content_mode"] in {"snippet", "partial_body", "full_body"}
    assert langchain["page_content"].startswith("# 标题")
    assert openwebui["content"].startswith("# 标题")
    assert "metadata" in openwebui


def test_archive_export_prioritizes_deeper_higher_quality_records(tmp_path):
    db = tmp_path / "archive.db"
    archive.add_document(
        "https://shallow.example/a",
        "# 浅摘要\nURL: https://shallow.example/a\n一句话摘要。",
        metadata={"topic_key": "topic-1", "topic_label": "横琴跨境电商", "content_mode": "snippet", "read_quality": {"score": 40}},
        db_path=db,
    )
    archive.add_document(
        "https://deep.example/b",
        "# 深正文\n" + "横琴跨境电商政策与监管规则。" * 120,
        metadata={"topic_key": "topic-1", "topic_label": "横琴跨境电商", "content_mode": "full_body", "read_quality": {"score": 88}},
        db_path=db,
    )

    records = archive.export_documents(db_path=db, topic="横琴跨境电商")

    assert len(records) == 2
    assert records[0]["domain"] == "deep.example"
    assert records[0]["topic_label"] == "横琴跨境电商"
    assert records[0]["content_mode"] == "full_body"


def test_archive_cli_verify_and_context(tmp_path, capsys):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    archive.add_document("https://example.com/a", "# AI Agent Wiki\n这是一个 Agent Wiki 资料。", db_path=db)

    with patch("sys.argv", ["guanlan", "archive", "verify", "--db", str(db)]):
        main()
    verify_out = capsys.readouterr().out
    assert "本地知识库体检" in verify_out

    with patch("sys.argv", ["guanlan", "archive", "context", "Agent Wiki", "--db", str(db)]):
        main()
    context_out = capsys.readouterr().out
    assert "Local Archive Context" in context_out
    assert "AI Agent Wiki" in context_out


def test_archive_ingest_search_persists_representative_evidence(tmp_path, monkeypatch):
    db = tmp_path / "archive.db"
    captured_kwargs = {}
    progress_events = []

    def fake_packet(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return {
            "result_count": 1,
            "preset": "general",
            "route_plan": {"primary_intents": ["policy"]},
            "selected_evidence": [
                {
                    "title": "政策原文",
                    "url": "https://gov.cn/a",
                    "snippet": "政策正文摘要",
                    "source_type": "政府/部委",
                    "topic_key": "policy",
                    "topic_role": "single",
                    "rank": 1,
                    "score": 9.0,
                }
            ],
            "readings": [{"url": "https://gov.cn/a", "status": "ok", "content": "# 政策原文\n全文"}],
        }

    monkeypatch.setattr("guanlan.webtools.build_research_packet", fake_packet)

    result = archive.ingest_search("人工智能 政策", db_path=db, progress_callback=progress_events.append)
    records = archive.search_documents("全文", db_path=db)

    assert result["archived_count"] == 1
    assert result["ingest_mode"] == "search-first"
    assert result["read_top"] == 0
    assert captured_kwargs["read_top"] == 0
    assert captured_kwargs["cache_ttl"] == 3600
    assert result["audit_summary"]["kept"] == 1
    assert result["timeout_budget_hint_seconds"] == 120
    assert result["timeout_recommendation"]["patient_wait_seconds"] == 120
    assert "不要过早判定卡死" in result["timeout_recommendation"]["agent_instruction"]
    assert result["phase_log"][0]["phase"] == "research_start"
    assert result["phase_log"][-1]["phase"] == "archive_done"
    assert progress_events[-1]["phase"] == "archive_done"
    assert result["next_steps"]
    assert records[0]["title"] == "政策原文"
    assert records[0]["metadata"]["source_type"] == "政府/部委"
    assert records[0]["metadata"]["topic_label"] == "政策"
    assert records[0]["metadata"]["content_mode"] in {"partial_body", "full_body"}
    assert records[0]["metadata"]["route_plan"]["primary_intents"] == ["policy"]
    assert records[0]["metadata"]["read_quality"]["chars"] > 0
    assert records[0]["metadata"]["source_card"]["domain"] == "gov.cn"


def test_archive_ingest_optional_reads_are_bounded_outside_research(tmp_path, monkeypatch):
    db = tmp_path / "archive.db"
    captured_packet_kwargs = {}
    captured_read_kwargs = {}

    def fake_packet(*args, **kwargs):
        captured_packet_kwargs.update(kwargs)
        return {
            "result_count": 1,
            "preset": "general",
            "route_plan": {"primary_intents": ["policy"]},
            "selected_evidence": [
                {
                    "title": "横琴跨境电商政策",
                    "url": "https://gov.cn/hengqin",
                    "snippet": "横琴 跨境 电商 政策",
                    "source_type": "政府/部委",
                    "rank": 1,
                }
            ],
            "readings": [],
        }

    def fake_read_batch(urls, **kwargs):
        captured_read_kwargs.update(kwargs)
        return [{"url": urls[0], "status": "ok", "content": "# 横琴跨境电商政策\n全文内容"}]

    monkeypatch.setattr("guanlan.webtools.build_research_packet", fake_packet)
    monkeypatch.setattr("guanlan.webtools.read_batch", fake_read_batch)

    result = archive.ingest_search("珠海横琴 跨境电商政策", read_top=1, db_path=db)
    records = archive.search_documents("全文内容", db_path=db)

    assert captured_packet_kwargs["read_top"] == 0
    assert captured_read_kwargs["backend"] == "direct"
    assert captured_read_kwargs["fallback_search"] is False
    assert captured_read_kwargs["concurrency"] == 3
    assert result["timeout_budget_hint_seconds"] == 240
    assert result["timeout_recommendation"]["retry_timeout_seconds"] == 300
    assert any(item["phase"] == "read_start" for item in result["phase_log"])
    assert any(item["phase"] == "read_done" for item in result["phase_log"])
    assert result["read_attempted_count"] == 1
    assert result["read_success_count"] == 1
    assert result["archived_count"] == 1
    assert records[0]["title"] == "横琴跨境电商政策"


def test_archive_ingest_dry_run_and_low_value_filter(tmp_path, monkeypatch):
    db = tmp_path / "archive.db"

    monkeypatch.setattr(
        "guanlan.webtools.build_research_packet",
        lambda *args, **kwargs: {
            "result_count": 2,
            "preset": "tech",
            "route_plan": {"primary_intents": ["tech"]},
            "selected_evidence": [
                {
                    "title": "2019 Toyota Camry",
                    "url": "https://example.com/camry",
                    "snippet": "Used car listing",
                    "source_type": "通用网页",
                },
                {
                    "title": "vLLM 与 SGLang 推理框架对比",
                    "url": "https://example.com/vllm",
                    "snippet": "vLLM SGLang KV Cache 推理框架",
                    "source_type": "科技/开发者社区",
                },
            ],
            "readings": [],
        },
    )

    result = archive.ingest_search("开源推理框架 vLLM SGLang", dry_run=True, db_path=db)

    assert result["dry_run"] is True
    assert result["archived_count"] == 0
    assert result["skipped_count"] == 1
    assert result["audit_summary"]["audited"] == 2
    assert result["audit_summary"]["reasons"]["low_query_overlap"] == 1
    assert {item["status"] for item in result["records"]} == {"skipped", "preview"}
    assert any(item["status"] == "preview" and item["audit"]["decision"] == "keep" for item in result["records"])
    assert archive.list_documents(db_path=db) == []


def test_archive_audit_keeps_matching_technical_terms_and_rejects_drift():
    drift = archive.audit_ingest_candidate(
        "开源推理框架 vLLM SGLang",
        {"title": "2019 Toyota Camry", "url": "https://example.com/camry", "snippet": "Used car listing"},
    )
    useful = archive.audit_ingest_candidate(
        "开源推理框架 vLLM SGLang",
        {
            "title": "vLLM 与 SGLang 推理框架对比",
            "url": "https://example.com/vllm",
            "snippet": "vLLM SGLang KV Cache 推理框架",
        },
        content="# vLLM 与 SGLang\n\nKV Cache 推理框架工程实践。" * 3,
    )

    assert drift["decision"] == "skip"
    assert "low_query_overlap" in drift["reasons"]
    assert useful["decision"] == "keep"
    assert {"vLLM", "SGLang"} & set(useful["matched_terms"])


def test_archive_cli_ingest_research_alias(tmp_path, capsys, monkeypatch):
    from guanlan.cli import main

    db = tmp_path / "archive.db"
    monkeypatch.setattr(
        "guanlan.webtools.build_research_packet",
        lambda *args, **kwargs: {
            "result_count": 1,
            "preset": "academic",
            "route_plan": {"primary_intents": ["academic"]},
            "selected_evidence": [
                {
                    "title": "EI 检索说明",
                    "url": "https://example.com/ei",
                    "snippet": "EI 检索要求",
                    "source_type": "学术/论文检索",
                }
            ],
            "readings": [],
        },
    )

    with patch("sys.argv", ["guanlan", "archive", "ingest-research", "EI检索", "--db", str(db)]):
        main()
    captured = capsys.readouterr()

    assert "已归档: 1" in captured.out
    assert "外层 timeout 建议" in captured.out
    assert "[archive] 搜索/研究候选中" in captured.err
