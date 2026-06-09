# -*- coding: utf-8 -*-
"""Tests for Guanlan social evidence contracts."""

from guanlan.social_evidence import (
    build_social_evidence_protocol,
    infer_social_platform,
    normalize_social_evidence_payload,
    social_browser_assist_template,
    social_platform_capability,
    social_visible_output_schema,
)


def test_infer_social_platform_covers_short_video_and_forum_hosts():
    assert infer_social_platform("https://www.douyin.com/video/123") == "douyin"
    assert infer_social_platform("https://v.kuaishou.com/abc") == "kuaishou"
    assert infer_social_platform("https://tieba.baidu.com/p/123") == "tieba"


def test_social_platform_capability_exposes_media_crawler_style_matrix():
    capability = social_platform_capability("xiaohongshu")

    assert capability["supports_keyword_search"] is True
    assert capability["supports_detail"] is True
    assert capability["supports_creator_profile"] is True
    assert capability["supports_comments"] is True
    assert capability["supports_sub_comments"] is True
    assert capability["supports_metrics"] is True
    assert capability["cookie_reuse_supported"] is True
    assert capability["browser_history_context_supported"] is True


def test_social_browser_assist_template_exposes_structured_social_fields():
    template = social_browser_assist_template("weibo")

    assert "metric_snapshots" in template["extract_fields"]
    assert "comment_samples" in template["extract_fields"]
    assert "creator_profile" in template["extract_fields"]
    assert template["session_policy"]["cookie_reuse"].startswith("allowed_for_rendering_target_page")
    assert template["supported_capabilities"]["comments"] is True


def test_social_evidence_protocol_allows_session_reuse_but_not_default_export():
    protocol = build_social_evidence_protocol("zhihu")

    assert protocol["enabled"] is True
    assert "existing_browser_session_context_reuse" in protocol["allowed_modes"]
    assert "explicit_credential_material_after_separate_authorization" in protocol["allowed_modes"]
    assert protocol["session_policy"]["cookie_reuse_supported"] is True
    assert protocol["session_policy"]["credential_material_export_boundary"] == "requires_separate_explicit_authorization"
    assert protocol["output_schema"]["creator_profile"]["display_name"] == ""


def test_social_visible_output_schema_contains_nested_objects():
    schema = social_visible_output_schema("bilibili")

    assert schema["post"]["platform"] == "bilibili"
    assert isinstance(schema["metric_snapshots"], list)
    assert isinstance(schema["comment_samples"], list)
    assert "creator_profile" in schema


def test_normalize_social_evidence_payload_keeps_nested_social_samples():
    payload = normalize_social_evidence_payload(
        {
            "platform": "weibo",
            "url": "https://weibo.com/123",
            "title": "WPS AI 讨论",
            "visible_text": "用户在微博讨论 WPS AI 的新功能。",
            "author": "某博主",
            "published_at": "2026-06-08",
            "engagement_summary": "转发 3 评论 8 点赞 12",
            "content_type": "post",
            "content_id": "123",
            "creator_profile": {
                "display_name": "某博主",
                "handle": "@demo",
                "verification_hint": "黄V",
            },
            "metric_snapshots": [{"metric": "likes", "value": 12, "value_text": "12赞"}],
            "comment_samples": [{"text": "这个功能挺实用", "author": "路人甲"}],
        }
    )

    assert payload["post"]["content_id"] == "123"
    assert payload["creator_profile"]["handle"] == "@demo"
    assert payload["metric_snapshots"][0]["metric"] == "likes"
    assert payload["comment_samples"][0]["text"] == "这个功能挺实用"
