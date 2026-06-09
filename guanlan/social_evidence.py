# -*- coding: utf-8 -*-
"""Social platform evidence contracts for Guanlan.

This module is a product/contract layer, not a crawler implementation. It
describes how Agent-facing workflows should treat social platform pages as
session-dependent evidence samples after user authorization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class SocialPlatformCapability:
    id: str
    name: str
    domains: tuple[str, ...]
    content_types: tuple[str, ...]
    evidence_role: str
    supports_keyword_search: bool = True
    supports_detail: bool = True
    supports_creator_profile: bool = True
    supports_comments: bool = True
    supports_sub_comments: bool = False
    supports_metrics: bool = True
    public_entrypoint: str = "search_or_public_page"
    authorized_entrypoint: str = "browser_visible_page"
    session_reuse_default: bool = True
    login_or_verification_likely: bool = True
    cookie_reuse_supported: bool = True
    browser_history_context_supported: bool = True
    explicit_credential_flow_supported: bool = True
    credential_material_exposure: str = "none_in_browser_visible_payload"
    browser_history_exposure: str = "not_exported; current target tab context only"
    sample_boundary: str = "public_or_user_visible_sample_not_representative"
    risk_tags: tuple[str, ...] = ()
    recommended_collection: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SocialMetricSnapshot:
    metric: str = ""
    value: str = ""
    unit: str = ""
    value_text: str = ""
    captured_from: str = "visible_page"
    confidence: str = "visible_sample"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SocialCommentSample:
    text: str = ""
    author: str = ""
    published_at: str = ""
    reply_to: str = ""
    engagement_summary: str = ""
    is_sub_comment: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SocialCreatorProfile:
    handle: str = ""
    display_name: str = ""
    bio: str = ""
    verification_hint: str = ""
    follower_summary: str = ""
    platform_home_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SocialPostSample:
    platform: str = ""
    content_type: str = ""
    content_id: str = ""
    url: str = ""
    title: str = ""
    text: str = ""
    author: str = ""
    published_at: str = ""
    engagement_summary: str = ""
    visible_context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SOCIAL_PLATFORM_CAPABILITIES: tuple[SocialPlatformCapability, ...] = (
    SocialPlatformCapability(
        id="xiaohongshu",
        name="小红书",
        domains=("xiaohongshu.com", "xhslink.com"),
        content_types=("note", "comment", "creator_profile", "search_result"),
        evidence_role="social_user_visible_note_sample",
        supports_sub_comments=True,
        public_entrypoint="site search / public note URL / hotboard clues",
        risk_tags=("login_wall", "sample_bias", "platform_framing", "xsec_token_context"),
        recommended_collection=(
            "先用 search/social_web 或 hotboard 发现候选笔记",
            "用户授权后复用当前浏览器会话读取目标笔记可见内容",
            "评论只取目标页可见摘要；需要更多样本时声明 min_visible_items",
        ),
    ),
    SocialPlatformCapability(
        id="rednote",
        name="Rednote",
        domains=("rednote.com",),
        content_types=("note", "comment", "creator_profile", "search_result"),
        evidence_role="social_user_visible_note_sample",
        supports_sub_comments=True,
        public_entrypoint="site search / public note URL",
        risk_tags=("login_wall", "sample_bias", "platform_framing"),
        recommended_collection=(
            "按小红书同类公开笔记处理，但保留 rednote 平台标签",
            "用户授权后复用当前浏览器会话读取目标页可见内容",
            "不要把海外版样本外推到国内小红书总体口碑",
        ),
    ),
    SocialPlatformCapability(
        id="douyin",
        name="抖音",
        domains=("douyin.com", "iesdouyin.com", "v.douyin.com"),
        content_types=("short_video", "comment", "creator_profile", "search_result"),
        evidence_role="social_user_visible_video_sample",
        supports_sub_comments=True,
        public_entrypoint="hotboard / public share URL / scoped search",
        risk_tags=("dynamic_page", "login_wall", "fast_changing", "platform_framing"),
        recommended_collection=(
            "先用热榜或公开分享链接定位目标视频",
            "用户授权后读取标题、文案、作者、发布时间、可见互动和评论摘要",
            "视频播放、下载或写操作不属于观澜默认证据链",
        ),
    ),
    SocialPlatformCapability(
        id="kuaishou",
        name="快手",
        domains=("kuaishou.com", "www.kuaishou.com", "v.kuaishou.com"),
        content_types=("short_video", "comment", "creator_profile", "search_result"),
        evidence_role="social_user_visible_video_sample",
        supports_sub_comments=True,
        public_entrypoint="hotboard / public share URL / scoped search",
        risk_tags=("dynamic_page", "login_wall", "fast_changing", "platform_framing"),
        recommended_collection=(
            "先用热榜或公开分享链接定位目标作品",
            "用户授权后读取目标页可见文案、作者、发布时间和评论摘要",
            "互动数只作样本语境，不写成全站比例",
        ),
    ),
    SocialPlatformCapability(
        id="bilibili",
        name="B站",
        domains=("bilibili.com", "b23.tv", "space.bilibili.com", "m.bilibili.com"),
        content_types=("video", "dynamic", "comment", "creator_profile", "search_result"),
        evidence_role="social_video_attention_sample",
        supports_sub_comments=True,
        login_or_verification_likely=False,
        public_entrypoint="native hotnews / yt-dlp metadata / public page",
        risk_tags=("creator_bias", "sample_bias", "platform_metric_context"),
        recommended_collection=(
            "优先用 B站热搜/热门和公开视频页发现线索",
            "读取目标视频标题、UP主、发布时间、简介、可见播放/弹幕/评论语境",
            "弹幕和评论是平台样本，不能代表总体舆论",
        ),
    ),
    SocialPlatformCapability(
        id="weibo",
        name="微博",
        domains=("weibo.com", "m.weibo.cn", "s.weibo.com"),
        content_types=("post", "hot_topic", "comment", "creator_profile", "search_result"),
        evidence_role="social_public_discussion_sample",
        supports_sub_comments=True,
        public_entrypoint="native hotnews / public search / scoped search",
        risk_tags=("fast_changing", "platform_framing", "sample_bias", "login_wall"),
        recommended_collection=(
            "先用微博热搜或 scoped search 定位话题/帖子",
            "用户授权后读取目标帖可见正文、作者、时间、转评赞和评论摘要",
            "热搜是注意力信号，不是事实结论",
        ),
    ),
    SocialPlatformCapability(
        id="tieba",
        name="百度贴吧",
        domains=("tieba.baidu.com",),
        content_types=("thread", "reply", "creator_profile", "search_result"),
        evidence_role="forum_thread_sample",
        supports_sub_comments=False,
        login_or_verification_likely=False,
        public_entrypoint="public thread / scoped search",
        risk_tags=("forum_bias", "sample_bias", "old_thread_resurface"),
        recommended_collection=(
            "按帖子/楼层样本处理，优先保留吧名、楼层时间和上下文",
            "旧帖被顶起时要区分首帖时间和最新回复时间",
            "不要把单吧样本外推到全网口碑",
        ),
    ),
    SocialPlatformCapability(
        id="zhihu",
        name="知乎",
        domains=("zhihu.com", "zhuanlan.zhihu.com"),
        content_types=("question", "answer", "article", "comment", "creator_profile", "search_result"),
        evidence_role="qa_or_column_user_visible_sample",
        supports_sub_comments=True,
        public_entrypoint="site search / hotboard / public question URL",
        risk_tags=("opinionated", "sample_bias", "login_wall", "answer_order_bias"),
        recommended_collection=(
            "区分问题、回答、专栏文章和评论区",
            "只把赞同/评论数当作当前可见排序语境",
            "推荐回答和目标回答不要混在同一条证据里",
        ),
    ),
    SocialPlatformCapability(
        id="douban",
        name="豆瓣",
        domains=("douban.com",),
        content_types=("review", "rating", "discussion", "group_topic", "creator_profile"),
        evidence_role="review_or_interest_graph_sample",
        supports_sub_comments=False,
        login_or_verification_likely=False,
        public_entrypoint="public subject/review/group URL / scoped search",
        risk_tags=("rating_sample_bias", "community_bias", "login_wall"),
        recommended_collection=(
            "区分条目评分、短评、长评和小组讨论",
            "评分是平台样本指标，不能替代票房/销售/官方数据",
            "小组讨论只作社区样本",
        ),
    ),
)


_BY_ID = {item.id: item for item in SOCIAL_PLATFORM_CAPABILITIES}


def list_social_platform_capabilities() -> list[dict[str, Any]]:
    """Return the platform capability matrix as serializable dicts."""

    return [item.to_dict() for item in SOCIAL_PLATFORM_CAPABILITIES]


def social_visible_output_schema(platform: str = "") -> dict[str, Any]:
    """Return a stable, Agent-facing schema for visible social evidence."""

    capability = social_platform_capability(platform)
    content_types = list(capability.get("content_types") or [])
    return {
        "schema_version": "social_evidence_v1",
        "platform": capability.get("id") or "string",
        "source_layer": "community_sample",
        "evidence_role": capability.get("evidence_role") or "social_visible_sample",
        "content_type": content_types[0] if content_types else "string",
        "content_id": "string",
        "post": SocialPostSample(
            platform=capability.get("id") or "string",
            content_type=content_types[0] if content_types else "string",
        ).to_dict(),
        "creator_profile": SocialCreatorProfile().to_dict(),
        "metric_snapshots": [SocialMetricSnapshot().to_dict()],
        "comment_samples": [SocialCommentSample().to_dict()],
        "requested_min_items": "integer",
        "collected_count": "integer",
        "partial_reason": "string",
        "source_mode": "browser_visible",
        "browser_assisted": True,
        "user_authorized": True,
        "visible_page_only": True,
        "session_dependent": True,
        "sample_boundary": capability.get("sample_boundary") or "sample_not_representative",
    }


def social_platform_capability(platform: str = "") -> dict[str, Any]:
    """Resolve one platform capability by id or URL/domain."""

    platform_id = infer_social_platform(platform)
    capability = _BY_ID.get(platform_id)
    return capability.to_dict() if capability else {}


def infer_social_platform(value: str = "") -> str:
    """Infer a social platform id from a platform id, URL, or domain."""

    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    normalized_id = raw.replace("_", "-")
    if normalized_id in _BY_ID:
        return normalized_id
    host = urlparse(raw).netloc.lower() if "://" in raw else raw
    host = host.split("/")[0].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    for capability in SOCIAL_PLATFORM_CAPABILITIES:
        for domain in capability.domains:
            if host == domain or host.endswith("." + domain):
                return capability.id
    return ""


def social_browser_assist_template(platform: str = "") -> dict[str, Any]:
    """Build a browser-visible extraction template for a social platform."""

    capability = social_platform_capability(platform)
    if not capability:
        return {}
    fields = [
        "url",
        "title",
        "visible_text",
        "author",
        "published_at",
        "engagement_summary",
        "visible_comment_summary",
        "creator_profile_summary",
        "captured_at",
        "visible_context",
        "requested_min_items",
        "collected_count",
        "partial_reason",
        "skipped_reason",
    ]
    return {
        "name": f"{capability['name']}可见社交样本",
        "evidence_role": capability["evidence_role"],
        "source_layer": "community_sample",
        "content_types": list(capability["content_types"]),
        "extract_fields": [
            *fields,
            "content_type",
            "content_id",
            "metric_snapshots",
            "comment_samples",
            "creator_profile",
        ],
        "field_hints": [
            "只读取用户授权的目标页或同一任务候选页可见内容。",
            "可以复用当前浏览器已有登录态、Cookie 和历史上下文让目标页可见，但默认不导出这些材料，也不把它们写进输出。",
            "评论/弹幕/回复只作为平台样本，不能外推总体口碑。",
            *list(capability.get("recommended_collection") or ()),
        ],
        "quality_checks": [
            "visible_text、visible_comment_summary 或 skipped_reason 至少有一项非空。",
            "如果是列表、评论或搜索页，输出 requested_min_items、collected_count 和 partial_reason。",
            "作者、发布时间、互动数缺失时保留空值，不编造。",
            "输出必须保留 source_layer=community_sample 与 session_dependent=true。",
        ],
        "risk_tags": list(capability["risk_tags"]),
        "sample_boundary": capability["sample_boundary"],
        "supported_capabilities": {
            "keyword_search": capability["supports_keyword_search"],
            "detail": capability["supports_detail"],
            "creator_profile": capability["supports_creator_profile"],
            "comments": capability["supports_comments"],
            "sub_comments": capability["supports_sub_comments"],
            "metrics": capability["supports_metrics"],
        },
        "session_policy": {
            "reuse_existing_browser_session_by_default": capability["session_reuse_default"],
            "cookie_reuse": "allowed_for_rendering_target_page_but_not_exported_by_default"
            if capability["cookie_reuse_supported"]
            else "not_supported",
            "browser_history_reuse": "allowed_as_current_session_context_but_not_exported_by_default"
            if capability["browser_history_context_supported"]
            else "not_supported",
            "explicit_credential_flow": "supported_but_requires_separate_explicit_authorization"
            if capability["explicit_credential_flow_supported"]
            else "not_supported",
            "credential_material_exposure": capability["credential_material_exposure"],
            "browser_history_exposure": capability["browser_history_exposure"],
        },
    }


def build_social_evidence_protocol(platform: str = "") -> dict[str, Any]:
    """Return Agent-facing collection boundaries for one social platform."""

    capability = social_platform_capability(platform)
    if not capability:
        return {"enabled": False}
    return {
        "enabled": True,
        "schema_version": "social_evidence_protocol_v1",
        "platform": capability["id"],
        "name": capability["name"],
        "evidence_role": capability["evidence_role"],
        "source_layer": "community_sample",
        "public_entrypoint": capability["public_entrypoint"],
        "authorized_entrypoint": capability["authorized_entrypoint"],
        "session_reuse_default": capability["session_reuse_default"],
        "login_or_verification_likely": capability["login_or_verification_likely"],
        "sample_boundary": capability["sample_boundary"],
        "risk_tags": list(capability["risk_tags"]),
        "supported_capabilities": {
            "keyword_search": capability["supports_keyword_search"],
            "detail": capability["supports_detail"],
            "creator_profile": capability["supports_creator_profile"],
            "comments": capability["supports_comments"],
            "sub_comments": capability["supports_sub_comments"],
            "metrics": capability["supports_metrics"],
        },
        "allowed_modes": [
            "public_discovery",
            "user_authorized_visible_page",
            "existing_browser_session_context_reuse",
            "target_private_account_visible_page_after_explicit_authorization",
            "explicit_credential_material_after_separate_authorization",
        ],
        "session_policy": {
            "reuse_existing_browser_session_by_default": capability["session_reuse_default"],
            "cookie_reuse_supported": capability["cookie_reuse_supported"],
            "browser_history_context_supported": capability["browser_history_context_supported"],
            "explicit_credential_flow_supported": capability["explicit_credential_flow_supported"],
            "cookie_reuse_boundary": "allowed_to_keep_target_page_renderable_but_not_exported_by_default",
            "browser_history_boundary": "current_session_context_only_not_exported",
            "credential_material_export_boundary": "requires_separate_explicit_authorization",
        },
        "not_allowed_in_browser_visible_payload": [
            "cookie_values",
            "tokens",
            "passwords",
            "keychain_material",
            "browser_history_export",
            "local_storage",
            "session_storage",
            "browser_database_rows",
            "unrelated_private_pages",
        ],
        "stopping_condition": [
            "目标页可见内容已提取",
            "达到 requested_min_items 或出现合理 partial_reason",
            "遇到未授权登录墙、私域页、支付/发布/提交入口",
        ],
        "output_schema": social_visible_output_schema(platform),
    }


def normalize_social_evidence_payload(payload: dict[str, Any], *, platform: str = "") -> dict[str, Any]:
    """Normalize a social visible-page item before higher-level aggregation."""

    if not isinstance(payload, dict):
        raise ValueError("social evidence payload must be an object")
    inferred_platform = platform or infer_social_platform(str(payload.get("platform") or payload.get("url") or ""))
    capability = social_platform_capability(inferred_platform)
    content_type = str(payload.get("content_type") or payload.get("post_type") or "").strip()
    content_id = str(payload.get("content_id") or payload.get("post_id") or payload.get("note_id") or "").strip()
    url = str(payload.get("url") or "").strip()
    title = str(payload.get("title") or "").strip()
    text = str(payload.get("visible_text") or payload.get("text") or payload.get("content") or "").strip()
    author = str(payload.get("author") or "").strip()
    published_at = str(payload.get("published_at") or "").strip()
    engagement_summary = str(payload.get("engagement_summary") or "").strip()
    visible_context = str(payload.get("visible_context") or "").strip()
    creator_profile = _normalize_creator_profile(payload.get("creator_profile"))
    if not creator_profile["display_name"] and author:
        creator_profile["display_name"] = author
    comment_samples = _normalize_comment_samples(payload.get("comment_samples") or payload.get("comments"))
    metric_snapshots = _normalize_metric_snapshots(
        payload.get("metric_snapshots")
        or payload.get("metric_snapshot")
        or payload.get("metrics")
    )
    return {
        "schema_version": "social_evidence_v1",
        "platform": inferred_platform,
        "source_layer": "community_sample",
        "evidence_role": capability.get("evidence_role") or "social_visible_sample",
        "content_type": content_type or (list(capability.get("content_types") or [""])[:1] or [""])[0],
        "content_id": content_id,
        "url": url,
        "title": title,
        "text": text,
        "author": author,
        "published_at": published_at,
        "engagement_summary": engagement_summary,
        "visible_comment_summary": str(payload.get("visible_comment_summary") or "").strip(),
        "creator_profile_summary": str(payload.get("creator_profile_summary") or "").strip(),
        "visible_context": visible_context,
        "post": SocialPostSample(
            platform=inferred_platform,
            content_type=content_type or (list(capability.get("content_types") or [""])[:1] or [""])[0],
            content_id=content_id,
            url=url,
            title=title,
            text=text,
            author=author,
            published_at=published_at,
            engagement_summary=engagement_summary,
            visible_context=visible_context,
        ).to_dict(),
        "creator_profile": creator_profile,
        "metric_snapshots": metric_snapshots,
        "comment_samples": comment_samples,
        "requested_min_items": int(payload.get("requested_min_items") or 0),
        "collected_count": int(payload.get("collected_count") or 0),
        "partial_reason": str(payload.get("partial_reason") or "").strip(),
        "source_mode": str(payload.get("source_mode") or "browser_visible").strip(),
        "browser_assisted": bool(payload.get("browser_assisted", True)),
        "visible_page_only": bool(payload.get("visible_page_only", True)),
        "user_authorized": bool(payload.get("user_authorized", True)),
        "session_dependent": bool(payload.get("session_dependent", True)),
        "sample_boundary": capability.get("sample_boundary") or "sample_not_representative",
    }


def _normalize_metric_snapshots(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metric = str(row.get("metric") or row.get("name") or "").strip()
        value_text = str(row.get("value_text") or row.get("label") or row.get("display") or "").strip()
        value_raw = row.get("value")
        value_value = str(value_raw if value_raw is not None else "").strip()
        if not (metric or value_text or value_value):
            continue
        out.append(
            SocialMetricSnapshot(
                metric=metric,
                value=value_value,
                unit=str(row.get("unit") or "").strip(),
                value_text=value_text,
                captured_from=str(row.get("captured_from") or "visible_page").strip() or "visible_page",
                confidence=str(row.get("confidence") or "visible_sample").strip() or "visible_sample",
            ).to_dict()
        )
    return out


def _normalize_comment_samples(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or row.get("content") or "").strip()
        author = str(row.get("author") or row.get("user") or row.get("nickname") or "").strip()
        published_at = str(row.get("published_at") or row.get("time") or "").strip()
        if not (text or author or published_at):
            continue
        out.append(
            SocialCommentSample(
                text=text,
                author=author,
                published_at=published_at,
                reply_to=str(row.get("reply_to") or "").strip(),
                engagement_summary=str(row.get("engagement_summary") or row.get("likes") or "").strip(),
                is_sub_comment=bool(row.get("is_sub_comment", False)),
            ).to_dict()
        )
    return out


def _normalize_creator_profile(value: Any) -> dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    return SocialCreatorProfile(
        handle=str(row.get("handle") or row.get("username") or "").strip(),
        display_name=str(row.get("display_name") or row.get("name") or row.get("nickname") or "").strip(),
        bio=str(row.get("bio") or row.get("description") or "").strip(),
        verification_hint=str(row.get("verification_hint") or row.get("verified") or "").strip(),
        follower_summary=str(row.get("follower_summary") or row.get("followers") or "").strip(),
        platform_home_url=str(row.get("platform_home_url") or row.get("url") or "").strip(),
    ).to_dict()
