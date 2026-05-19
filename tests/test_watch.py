# -*- coding: utf-8 -*-
"""Tests for Guanlan standing intent watch workflows."""

from guanlan import watch


def test_create_list_remove_watch_intent(tmp_path):
    store = tmp_path / "watch.json"

    created = watch.create_watch_intent(
        "OpenAI API release notes",
        name="OpenAI releases",
        profile="english",
        feed_source="curated",
        schedule="daily 09:00",
        tags=["tech", "api"],
        store_path=store,
    )

    assert created["id"] == "openai-releases"
    assert created["seen_count"] == 0
    assert "seen" not in created
    rows = watch.list_watch_intents(store_path=store)
    assert rows[0]["query"] == "OpenAI API release notes"
    assert rows[0]["feed_source"] == "curated"

    shown = watch.get_watch_intent("openai-releases", store_path=store)
    assert shown["schedule"] == "daily 09:00"

    removed = watch.remove_watch_intent("openai-releases", store_path=store)
    assert removed["id"] == "openai-releases"
    assert watch.list_watch_intents(store_path=store) == []


def test_watch_plan_is_local_and_agent_readable():
    plan = watch.build_watch_plan(
        "Python Agent framework GitHub issue 对比",
        profile="china",
        feed_source="auto",
        limit=80,
    )

    assert plan["mode"] == "standing_intent"
    assert plan["boundary"].startswith("local_watch_plan")
    assert "watch add" in plan["commands"]["create"]
    assert "watch fire" in plan["commands"]["diagnostic_fire"]
    assert plan["suggested_feed_source"] in {"curated", "arxiv", "baidu-rss"}
    assert "Guanlan Watch 计划" in watch.format_watch_plan_markdown(plan)


def test_watch_fire_marks_new_and_repeated_when_recording(monkeypatch, tmp_path):
    store = tmp_path / "watch.json"
    watch.create_watch_intent(
        "OpenAI API release notes",
        name="OpenAI releases",
        profile="english",
        feed_source="curated",
        store_path=store,
    )

    monkeypatch.setattr(
        watch,
        "_collect_search_items",
        lambda *_args, **_kwargs: (
            [
                watch._normalize_item(
                    title="OpenAI API changelog",
                    url="https://developers.openai.com/api/changelog",
                    summary="New release notes.",
                    source="bing",
                    origin="search",
                    evidence_role="documentation",
                    published_at="2026-05-18",
                )
            ],
            "",
        ),
    )
    monkeypatch.setattr(
        watch,
        "_collect_feed_items",
        lambda *_args, **_kwargs: (
            [
                watch._normalize_item(
                    title="OpenAI API changelog",
                    url="https://developers.openai.com/api/changelog",
                    summary="Duplicate from feed.",
                    source="精品内容流",
                    origin="feeds:curated",
                    evidence_role="reading_signal",
                    published_at="2026-05-18",
                )
            ],
            "",
        ),
    )

    first = watch.fire_watch_intent("openai-releases", limit=5, record_seen=True, store_path=store)
    assert first["new_count"] == 1
    assert first["repeated_count"] == 0
    assert first["items"][0]["is_new"] is True

    second = watch.fire_watch_intent("openai-releases", limit=5, record_seen=True, store_path=store)
    assert second["new_count"] == 0
    assert second["repeated_count"] == 1
    assert second["items"][0]["is_new"] is False
    assert watch.get_watch_intent("openai-releases", store_path=store)["seen_count"] == 1


def test_watch_fire_without_record_seen_is_diagnostic(monkeypatch, tmp_path):
    store = tmp_path / "watch.json"
    watch.create_watch_intent("AI safety policy", name="policy", store_path=store)
    monkeypatch.setattr(
        watch,
        "_collect_search_items",
        lambda *_args, **_kwargs: (
            [
                watch._normalize_item(
                    title="AI safety policy update",
                    url="https://example.com/policy",
                    summary="Policy update.",
                    source="search",
                    origin="search",
                    evidence_role="official_primary",
                    published_at="",
                )
            ],
            "",
        ),
    )
    monkeypatch.setattr(watch, "_collect_feed_items", lambda *_args, **_kwargs: ([], ""))

    report = watch.fire_watch_intent("policy", limit=3, record_seen=False, store_path=store)

    assert report["new_count"] == 1
    assert report["diagnostics"]["record_seen"] is False
    assert watch.get_watch_intent("policy", store_path=store)["seen_count"] == 0
