# -*- coding: utf-8 -*-
"""Central source matrix for Guanlan read-only discovery surfaces."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceEntry:
    """One source row shared by hotnews, feeds, routing, MCP, and HTTP."""

    id: str
    name: str
    surface: str
    platform: str
    category: str
    backend: str
    status: str
    risk: str = "low"
    evidence_role: str = "open_web_signal"
    source_domain: str = ""
    content_direction: str = ""
    freshness: str = ""
    quality: str = ""
    route_when: str = ""
    command: str = ""
    confidence: str = "medium"
    caveat: str = ""
    notes: str = ""
    fallback: str = ""
    optional_backend: str = ""
    verified: bool = True
    verification: str = "direct"
    risk_tags: tuple[str, ...] = field(default_factory=tuple)
    aliases: tuple[str, ...] = field(default_factory=tuple)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        extra = data.pop("extra", {}) or {}
        data.update(extra)
        if self.backend == "optional":
            data["verified"] = False
            data["verification"] = "backend_dependent"
            if not data.get("notes"):
                data["notes"] = "可选增强源：观澜记录其信源身份与适用场景；抓取可用性取决于外部后端和上游公开页面状态。"
        data["risk_tags"] = list(self.risk_tags)
        data["aliases"] = list(self.aliases)
        return {key: value for key, value in data.items() if value not in ("", [], {}, None)}


_HOTNEWS_NATIVE: tuple[SourceEntry, ...] = (
    SourceEntry(
        id="today",
        name="今日多源热榜",
        surface="hotnews",
        platform="guanlan",
        category="hotnews",
        backend="native",
        status="stable",
        evidence_role="multi_source_snapshot",
        notes="聚合 baidu、weibo、bilibili-hot-search、ithome、v2ex；单源失败不影响其它来源。",
        caveat="多源快照只说明当前公开水势，不等同于事实结论。",
    ),
    SourceEntry(
        id="baidu",
        name="百度热搜",
        surface="hotnews",
        platform="baidu",
        category="hotnews",
        backend="native",
        status="stable",
        evidence_role="fresh_trend_signal",
        source_domain="baidu.com",
        freshness="minutes",
        quality="public trend board",
    ),
    SourceEntry(
        id="weibo",
        name="微博热搜",
        surface="hotnews",
        platform="weibo",
        category="social",
        backend="native",
        status="best-effort",
        evidence_role="public_discussion_signal",
        source_domain="weibo.com",
        freshness="minutes",
        notes="公开只读热搜端点；不读取 Cookie 或登录态，但可能受反爬和地区网络影响。",
        risk_tags=("sample_bias", "platform_framing", "fast_changing"),
    ),
    SourceEntry(
        id="bilibili-hot-search",
        name="B站热搜",
        surface="hotnews",
        platform="bilibili",
        category="video",
        backend="native",
        status="stable",
        evidence_role="video_attention_signal",
        source_domain="bilibili.com",
        freshness="minutes",
        quality="public hotword endpoint",
        route_when="用户问 B 站/视频平台热搜、热词、年轻用户讨论水势。",
        command="guanlan hotnews bilibili-hot-search --limit 80",
        caveat="热搜词适合发现注意力流向，不代表视频内容事实。",
        aliases=("bilibili-search", "bili-hot-search"),
        risk_tags=("creator_bias", "sample_bias", "fast_changing"),
    ),
    SourceEntry(
        id="bilibili",
        name="B站热门视频",
        surface="hotnews",
        platform="bilibili",
        category="video",
        backend="native",
        status="best-effort",
        evidence_role="video_attention_signal",
        source_domain="bilibili.com",
        notes="公开全站热门视频榜，不等同于 B站搜索框热搜；接口偶尔会限流或返回风控码。",
        aliases=("bili",),
        risk_tags=("creator_bias", "sample_bias"),
    ),
    SourceEntry(
        id="ithome",
        name="IT之家资讯",
        surface="hotnews",
        platform="ithome",
        category="tech",
        backend="native",
        status="stable",
        evidence_role="tech_news_signal",
        source_domain="ithome.com",
        freshness="minutes",
        quality="public RSS",
        notes="公开 RSS 源，适合作为科技资讯快照。",
    ),
    SourceEntry(
        id="sspai",
        name="少数派文章",
        surface="hotnews",
        platform="sspai",
        category="tech",
        backend="native",
        status="stable",
        evidence_role="tech_reading_signal",
        source_domain="sspai.com",
        freshness="hours",
        quality="public RSS",
        route_when="用户问中文科技/效率工具/数码生活最近值得读什么。",
        command="guanlan hotnews sspai --limit 80",
        caveat="这是高质量内容流，不是全网热榜；适合补充阅读候选。",
        risk_tags=("editorial_selection",),
    ),
    SourceEntry(
        id="xinzhiyuan",
        name="新智元",
        surface="hotnews",
        platform="xinzhiyuan",
        category="ai",
        backend="native",
        status="stable",
        evidence_role="ai_news_signal",
        source_domain="aiera.com.cn",
        freshness="hours",
        quality="public WordPress JSON",
        route_when="用户问中文 AI 产业、模型、科研和公司动态的最新资讯。",
        command="guanlan hotnews xinzhiyuan --limit 80",
        caveat="媒体资讯适合做 AI 领域线索；重要事实仍应回读原文并交叉核验。",
        risk_tags=("media_framing", "ai_hype"),
    ),
    SourceEntry(
        id="youtube-ai-rss",
        name="YouTube AI 频道 RSS",
        surface="hotnews",
        platform="youtube",
        category="video",
        backend="native",
        status="stable",
        evidence_role="video_source_signal",
        source_domain="youtube.com",
        freshness="hours",
        quality="official YouTube channel RSS",
        route_when="用户问海外 AI 产品、创业、访谈和视频内容动态。",
        command="guanlan hotnews youtube-ai-rss --limit 30",
        caveat="这是少量人工挑选频道的公开视频更新，不代表 YouTube 全站热度。",
        risk_tags=("curated_channel_pool", "creator_bias"),
    ),
    SourceEntry(
        id="zeli-hn",
        name="Zeli HN 24h",
        surface="hotnews",
        platform="zeli",
        category="tech",
        backend="native",
        status="best-effort",
        evidence_role="developer_discussion_signal",
        source_domain="zeli.app",
        freshness="hours",
        quality="public Hacker News 24h API",
        route_when="用户问海外开发者社区最近 24 小时关注什么。",
        command="guanlan hotnews zeli-hn --limit 80",
        caveat="这是 HN 的二次整理视角，适合补充，不替代原始 Hacker News。",
        risk_tags=("third_party_aggregation", "community_bias"),
    ),
    SourceEntry(
        id="buzzing",
        name="Buzzing",
        surface="hotnews",
        platform="buzzing",
        category="tech",
        backend="native",
        status="best-effort",
        evidence_role="global_tech_signal",
        source_domain="buzzing.cc",
        freshness="hours",
        quality="public structured JSON feed",
        route_when="用户问全球科技/开发者圈近期被讨论的链接。",
        command="guanlan hotnews buzzing --limit 80",
        caveat="来源较分散，适合发现线索；不应直接作为权威事实来源。",
        risk_tags=("third_party_aggregation", "sample_bias"),
    ),
    SourceEntry(
        id="zhihu",
        name="知乎热榜",
        surface="hotnews",
        platform="zhihu",
        category="hotnews",
        backend="native",
        status="experimental",
        verified=False,
        verification="experimental_public_endpoint",
        evidence_role="qa_discussion_signal",
        source_domain="zhihu.com",
        notes="实验源：公开接口在部分环境会返回 401/403，不承诺稳定可用。",
        fallback='guanlan search "知乎 热榜 关键词" --site zhihu.com --profile china',
        risk_tags=("sample_bias", "login_wall", "opinionated"),
    ),
    SourceEntry(
        id="v2ex",
        name="V2EX 热门",
        surface="hotnews",
        platform="v2ex",
        category="community",
        backend="native",
        status="stable",
        evidence_role="developer_discussion_signal",
        source_domain="v2ex.com",
        risk_tags=("sample_bias", "community_bias"),
    ),
)


_HOTNEWS_OPTIONAL: tuple[SourceEntry, ...] = (
    SourceEntry(id="newsnow:toutiao", name="今日头条", surface="hotnews", platform="toutiao", category="china", backend="optional", optional_backend="newsnow", status="optional", evidence_role="fresh_trend_signal", source_domain="toutiao.com"),
    SourceEntry(id="newsnow:thepaper", name="澎湃新闻", surface="hotnews", platform="thepaper", category="china", backend="optional", optional_backend="newsnow", status="optional", evidence_role="news_signal", source_domain="thepaper.cn", caveat="公开网页形态易受反爬影响，先作为可选后端线索源。"),
    SourceEntry(id="newsnow:ifeng", name="凤凰网", surface="hotnews", platform="ifeng", category="china", backend="optional", optional_backend="newsnow", status="optional", evidence_role="news_signal", source_domain="ifeng.com"),
    SourceEntry(id="newsnow:tieba", name="贴吧", surface="hotnews", platform="tieba", category="china", backend="optional", optional_backend="newsnow", status="optional", evidence_role="public_discussion_signal", source_domain="tieba.baidu.com", risk_tags=("sample_bias", "platform_framing")),
    SourceEntry(id="newsnow:36kr-quick", name="36氪快讯", surface="hotnews", platform="36kr-quick", category="tech", backend="optional", optional_backend="newsnow", status="optional", evidence_role="industry_news_signal", source_domain="36kr.com"),
    SourceEntry(id="newsnow:juejin", name="掘金热榜", surface="hotnews", platform="juejin", category="tech", backend="optional", optional_backend="newsnow", status="optional", evidence_role="developer_discussion_signal", source_domain="juejin.cn", risk_tags=("sample_bias", "community_bias")),
    SourceEntry(id="newsnow:cls-telegraph", name="财联社电报", surface="hotnews", platform="cls-telegraph", category="finance", backend="optional", optional_backend="newsnow", status="optional", evidence_role="market_news_signal", source_domain="cls.cn", risk_tags=("market_volatility",)),
    SourceEntry(id="newsnow:cls-hot", name="财联社热门", surface="hotnews", platform="cls-hot", category="finance", backend="optional", optional_backend="newsnow", status="optional", evidence_role="market_news_signal", source_domain="cls.cn", risk_tags=("market_volatility",)),
    SourceEntry(id="newsnow:wallstreetcn-quick", name="华尔街见闻快讯", surface="hotnews", platform="wallstreetcn-quick", category="finance", backend="optional", optional_backend="newsnow", status="optional", evidence_role="market_news_signal", source_domain="wallstreetcn.com", risk_tags=("market_volatility",)),
    SourceEntry(id="newsnow:wallstreetcn-hot", name="华尔街见闻热门", surface="hotnews", platform="wallstreetcn-hot", category="finance", backend="optional", optional_backend="newsnow", status="optional", evidence_role="market_news_signal", source_domain="wallstreetcn.com", risk_tags=("market_volatility",)),
    SourceEntry(id="newsnow:github-trending-today", name="GitHub Trending", surface="hotnews", platform="github-trending-today", category="tech", backend="optional", optional_backend="newsnow", status="optional", evidence_role="developer_signal", source_domain="github.com"),
    SourceEntry(id="newsnow:hackernews", name="Hacker News", surface="hotnews", platform="hackernews", category="tech", backend="optional", optional_backend="newsnow", status="optional", evidence_role="developer_discussion_signal", source_domain="news.ycombinator.com", risk_tags=("community_bias",)),
)


_FEEDS: tuple[SourceEntry, ...] = (
    SourceEntry(
        id="curated",
        name="精品内容流",
        surface="feeds",
        platform="rss",
        category="reading",
        backend="native",
        status="stable",
        evidence_role="reading_discovery_signal",
        content_direction="技术、AI、产品、商业科技、个人成长等高质量文章/播客/视频/推文聚合。",
        freshness="hourly",
        quality="high-signal curated RSS with summaries and tags",
        route_when="用户问值得读什么、技术/AI 最近有什么好文章、需要高质量阅读候选池。",
        command="guanlan feeds curated --limit 80",
        confidence="medium-high",
        caveat="适合阅读发现，不等同于实时热榜或事实核验。",
    ),
    SourceEntry(
        id="ai-vertical",
        name="AI 垂类精选动态源",
        surface="feeds",
        platform="aihot",
        category="ai",
        backend="native",
        status="best-effort",
        evidence_role="ai_vertical_discovery_signal",
        source_domain="aihot.virxact.com",
        content_direction="近 7 天 AI 模型、产品、行业、论文、技巧观点的精选动态线索。",
        freshness="near_realtime",
        quality="vertical selected AI news API with original URLs and generated summaries",
        route_when="用户问 AI/WPS/AI Office/Agent/大模型近期动态、选题雷达或行业脉冲时，由 route/research 自动补充。",
        command="自动由 guanlan research ... --preset tech|wps_office 路由；无独立用户入口。",
        confidence="medium",
        caveat="这是精选动态和摘要层，适合发现线索；模型参数、发布时间、价格、法律/监管等关键事实必须回读原始 URL。",
        risk_tags=("editorial_selection", "llm_summary", "source_requires_original_verification", "beta_source"),
        aliases=("aihot", "ai-hot"),
    ),
    SourceEntry(
        id="curated-sources",
        name="精品源目录",
        surface="feeds",
        platform="opml",
        category="source_catalog",
        backend="native",
        status="stable",
        evidence_role="source_catalog_entry",
        content_direction="公开 OPML 源目录，覆盖工程、AI、产品、商业科技、播客、视频和部分公众号 RSS。",
        freshness="catalog",
        quality="human-maintained source pool",
        route_when="用户要找长期订阅源、扩展信源白名单、构建阅读/RAG 源池。",
        command="guanlan feeds curated-sources --keyword AI --limit 80",
        caveat="目录只说明源存在，不代表每个源当下都可访问或持续高质量。",
    ),
    SourceEntry(
        id="baidu-rss",
        name="百度实时热点 RSS",
        surface="feeds",
        platform="baidu-rss",
        category="hotnews",
        backend="native",
        status="best-effort",
        evidence_role="fresh_trend_signal",
        content_direction="百度实时热点，带热度值、摘要和搜索链接。",
        freshness="minutes",
        quality="high-freshness trend signal",
        route_when="用户问今天/实时热点、想补充百度热榜 RSS 视角，或原生百度接口波动时。",
        command="guanlan feeds baidu-rss --limit 80",
        caveat="链接是搜索结果页，适合发现热点词，不适合作为事件原文证据。",
        risk_tags=("third_party_rss",),
    ),
    SourceEntry(
        id="wechat-rss",
        name="微信热门文章 RSS",
        surface="feeds",
        platform="wechat-rss",
        category="wechat",
        backend="native",
        status="best-effort",
        evidence_role="wechat_article_signal",
        content_direction="动态微信热门文章，常含较长摘要，链接指向公众号文章。",
        freshness="minutes",
        quality="high-freshness wechat article signal",
        route_when="用户问公众号/微信生态最近热文、中文科技媒体热文、需要微信文章线索。",
        command="guanlan feeds wechat-rss --limit 80",
        confidence="medium-low",
        caveat="第三方 RSS 聚合，适合线索发现；公众号全文仍可能受微信反爬、登录墙或转载链路影响。",
        risk_tags=("third_party_rss", "login_wall"),
    ),
    SourceEntry(
        id="arxiv",
        name="arXiv 预印本",
        surface="feeds",
        platform="arxiv",
        category="academic",
        backend="native",
        status="stable",
        evidence_role="preprint_record",
        source_domain="arxiv.org",
        content_direction="arXiv 公开 API，适合查找计算机、AI、物理等领域预印本和论文线索。",
        freshness="dated",
        quality="official public Atom API",
        route_when="用户问 arXiv、预印本、论文线索、近期学术进展或技术研究包。",
        command="guanlan feeds arxiv --keyword \"AI Agent\" --limit 80",
        confidence="medium-high",
        caveat="arXiv 是预印本索引，不等同于同行评议结论；重要结论需回读论文和交叉核验。",
        risk_tags=("preprint_not_peer_reviewed",),
        aliases=("preprint", "paper"),
    ),
    SourceEntry(
        id="watchlist",
        name="订阅源观察",
        surface="feeds",
        platform="local-watchlist",
        category="reading",
        backend="native",
        status="stable",
        evidence_role="watchlist_update_signal",
        content_direction="读取本机显式 RSS/Atom 清单，适合长期观察指定博客、机构公告、项目更新和内容源。",
        freshness="feed_dependent",
        quality="explicit local feed list with cache/stale status",
        route_when="用户要 watchlist、订阅源观察、长期跟踪博客/项目/机构更新，或需要把显式 feed URL 批量读取。",
        command="guanlan feeds watchlist --limit 80",
        caveat="只读取用户本机清单中的公开 RSS/Atom；源质量取决于清单维护，自动发现不作为默认承诺。",
        risk_tags=("user_watchlist", "feed_dependent"),
        aliases=("watch", "feeds-watch"),
    ),
)


SOURCE_MATRIX: dict[str, SourceEntry] = {entry.id: entry for entry in (*_HOTNEWS_NATIVE, *_HOTNEWS_OPTIONAL, *_FEEDS)}

_ALIASES: dict[str, str] = {
    alias: entry.id
    for entry in SOURCE_MATRIX.values()
    for alias in entry.aliases
}


def resolve_source_id(source_id: str) -> str:
    """Resolve a source id or central alias."""
    key = (source_id or "").strip().lower()
    return _ALIASES.get(key, key)


def get_source_entry(source_id: str) -> SourceEntry | None:
    """Return one source matrix entry, including optional backend shorthand."""
    resolved = resolve_source_id(source_id)
    if resolved in SOURCE_MATRIX:
        return SOURCE_MATRIX[resolved]
    optional_id = f"newsnow:{resolved}"
    return SOURCE_MATRIX.get(optional_id)


def get_source_metadata(source_id: str) -> dict[str, Any]:
    """Return source metadata as a mutable dictionary."""
    entry = get_source_entry(source_id)
    return entry.to_dict() if entry else {}


def list_sources(surface: str | None = None, backend: str | None = None) -> dict[str, dict[str, Any]]:
    """List source matrix rows filtered by surface and backend."""
    surface_key = (surface or "").strip().lower()
    backend_key = (backend or "").strip().lower()
    result: dict[str, dict[str, Any]] = {}
    for source_id, entry in SOURCE_MATRIX.items():
        if surface_key and entry.surface != surface_key:
            continue
        if backend_key and entry.backend != backend_key:
            continue
        result[source_id] = entry.to_dict()
    return result


def list_hotnews_sources() -> dict[str, dict[str, Any]]:
    """Return hotnews source rows, native first and optional second."""
    return list_sources(surface="hotnews")


def list_feed_sources() -> dict[str, dict[str, Any]]:
    """Return feed source rows."""
    return list_sources(surface="feeds")


def list_optional_backend_sources(backend: str) -> dict[str, dict[str, Any]]:
    """Return optional source rows for one backend, keyed by backend-native id."""
    backend_key = (backend or "").strip().lower()
    result: dict[str, dict[str, Any]] = {}
    for entry in SOURCE_MATRIX.values():
        if entry.backend != "optional" or entry.optional_backend != backend_key:
            continue
        native_id = entry.id.split(":", 1)[1] if ":" in entry.id else entry.id
        result[native_id] = entry.to_dict()
    return result


def list_source_cards(scope: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    """Return read-only source cards adapted from search scopes and taxonomy.

    This is Source Registry 2.0's safe adapter layer: it does not merge or
    rewrite existing source structures; it exposes them in a stable shape for
    agents and humans.
    """

    from guanlan.search_sources import SEARCH_SCOPES
    from guanlan.source_taxonomy import source_card_for_domain

    scope_key = (scope or "").strip().lower()
    rows: list[dict[str, Any]] = []
    for scope_id, search_scope in SEARCH_SCOPES.items():
        if scope_key and scope_id != scope_key:
            continue
        for domain in search_scope.domains:
            card = source_card_for_domain(domain, preferred_scope=scope_id).to_dict()
            rows.append(_source_card_row(scope_id, search_scope.to_dict(), card))
            if len(rows) >= max(limit, 1):
                return rows
    return rows


def show_source(target: str) -> dict[str, Any]:
    """Show one source by matrix id, alias, domain, or scope id."""

    from guanlan.search_entrypoints import get_search_engine_entrypoint
    from guanlan.search_sources import SEARCH_SCOPES
    from guanlan.source_taxonomy import source_card_for_domain

    key = (target or "").strip().lower()
    if not key:
        return {}
    matrix = get_source_metadata(key)
    if matrix:
        return {"kind": "matrix_source", **matrix}
    entrypoint = get_search_engine_entrypoint(key)
    if entrypoint:
        return {"kind": "search_entrypoint", **entrypoint}
    if key in SEARCH_SCOPES:
        scope = SEARCH_SCOPES[key]
        rows = list_source_cards(scope=key, limit=len(scope.domains))
        return {"kind": "scope", "scope": scope.to_dict(), "sources": rows}
    card = source_card_for_domain(key).to_dict()
    return {"kind": "domain", **_source_card_row(card.get("scope_id") or "", {}, card)}


def explain_sources(query: str, *, profile: str | None = None, limit: int = 12) -> dict[str, Any]:
    """Explain source routing for a query through the registry adapter."""

    from guanlan.router import build_route_plan
    from guanlan.search_entrypoints import suggest_search_entrypoints

    plan = build_route_plan(query, profile=profile, limit=80)
    plan_data = plan.to_dict()
    rows: list[dict[str, Any]] = []
    for scope_id in plan_data.get("preferred_scopes") or []:
        rows.extend(list_source_cards(scope=scope_id, limit=3))
        if len(rows) >= max(limit, 1):
            break
    if not rows:
        rows = list_source_cards(limit=max(limit, 1))
    return {
        "query": query,
        "route_plan": plan_data,
        "sources": rows[: max(limit, 1)],
        "search_entrypoint_policy": suggest_search_entrypoints(
            query,
            profile=profile,
            route_plan=plan_data,
        ),
        "explain": _source_explain_text(plan_data),
        "boundary": "sources explain 是只读信源解释，不联网，不等同于实际搜索结果。",
    }


def export_source_registry() -> dict[str, Any]:
    """Export source registry surfaces without rewriting their source modules."""

    from guanlan.channel_catalog import CHANNEL_CATALOG
    from guanlan.search_entrypoints import list_search_engine_entrypoints

    cards = list_source_cards(limit=500)
    search_entrypoints = list_search_engine_entrypoints()
    return {
        "schema": "guanlan-source-registry-2.0",
        "boundary": "只读导出：聚合 source matrix、search scopes、source taxonomy 和 channel catalog；不改写运行时。",
        "matrix_sources": list_sources(),
        "search_entrypoints": search_entrypoints,
        "source_cards": cards,
        "channel_catalog": CHANNEL_CATALOG,
        "counts": {
            "matrix_sources": len(SOURCE_MATRIX),
            "search_entrypoints": len(search_entrypoints),
            "source_cards": len(cards),
            "channels": len(CHANNEL_CATALOG),
        },
    }


def audit_source_registry() -> dict[str, Any]:
    """Audit high-attention source wording for drift across registry surfaces."""

    from guanlan.channel_catalog import CHANNEL_CATALOG

    high_focus = ["wechat", "zhihu", "xiaohongshu", "weibo", "bilibili", "douyin", "xueqiu", "rss", "web"]
    matrix_by_platform: dict[str, list[dict[str, Any]]] = {}
    for entry in SOURCE_MATRIX.values():
        row = entry.to_dict()
        matrix_by_platform.setdefault(str(row.get("platform") or row.get("id") or ""), []).append(row)
    checks: list[dict[str, Any]] = []
    for platform in high_focus:
        catalog = CHANNEL_CATALOG.get(platform, {})
        matrix_rows = matrix_by_platform.get(platform, [])
        if not catalog and not matrix_rows:
            checks.append(
                {
                    "id": platform,
                    "status": "warn",
                    "issue": "missing_from_registry",
                    "message": "高关注平台未在 channel catalog 或 source matrix 中出现。",
                }
            )
            continue
        catalog_stability = str(catalog.get("stability") or "")
        matrix_status = sorted({str(row.get("status") or "") for row in matrix_rows if row.get("status")})
        conflict = bool(
            catalog_stability == "stable"
            and any(status in {"experimental", "optional"} for status in matrix_status)
        )
        checks.append(
            {
                "id": platform,
                "status": "warn" if conflict else "pass",
                "catalog_stability": catalog_stability,
                "catalog_verification": catalog.get("verification", ""),
                "matrix_status": matrix_status,
                "risk_level": catalog.get("risk_level", ""),
                "auth": catalog.get("auth", ""),
                "message": _audit_message(platform, catalog, matrix_rows, conflict=conflict),
            }
        )
    summary = _audit_summary(checks)
    return {
        "summary": summary,
        "checks": checks,
        "boundary": "sources audit 是口径体检，不联网、不改变平台可用性，也不自动修复。",
        "suggested_next": [
            "若某平台 status 冲突，先统一 channel_catalog 与 source_registry 文案，再同步 README/Skill。",
            "高风控平台继续保持 best-effort/opt-in/experimental 表述，避免端到端稳定承诺。",
        ],
    }


def format_source_registry_export_json(payload: dict[str, Any]) -> str:
    """Render source registry export as stable JSON text."""

    import json

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def format_source_audit_markdown(report: dict[str, Any]) -> str:
    """Render source registry audit as Markdown."""

    summary = report.get("summary") or {}
    lines = [
        "# 观澜信源口径体检",
        "",
        f"- 结果: pass={summary.get('pass', 0)} warn={summary.get('warn', 0)} fail={summary.get('fail', 0)}",
        f"- 边界: {report.get('boundary', '')}",
        "",
        "## 高关注平台",
    ]
    for item in report.get("checks") or []:
        lines.append(
            f"- [{item.get('status')}] {item.get('id')}: "
            f"catalog={item.get('catalog_stability', '')}/{item.get('catalog_verification', '')}; "
            f"matrix={','.join(item.get('matrix_status') or []) or '-'}; {item.get('message', '')}"
        )
    if report.get("suggested_next"):
        lines.extend(["", "## 下一步"])
        lines.extend(f"- {step}" for step in report.get("suggested_next") or [])
    return "\n".join(lines)


def format_sources_markdown(rows: list[dict[str, Any]], title: str = "观澜信源矩阵") -> str:
    """Render source card rows as Markdown."""

    lines = [f"# {title}", "", "Source Registry 2.0 只读适配层：汇总现有 scope、taxonomy 和 source matrix，不重写搜索主链路。", ""]
    if not rows:
        lines.append("暂无匹配信源。")
        return "\n".join(lines)
    for row in rows:
        lines.extend(
            [
                f"## {row.get('source_id') or row.get('domain')}",
                f"- domain: {row.get('domain', '')}",
                f"- scope: {row.get('scope_id', '')} / {row.get('source_type', '')}",
                f"- authority/sample/freshness: {row.get('authority_score')} / {row.get('sample_value')} / {row.get('freshness_value')}",
                f"- roles: {', '.join(row.get('content_roles') or [])}",
                f"- risk_tags: {', '.join(row.get('risk_tags') or []) or 'none'}",
                f"- best_for: {row.get('best_for', '')}",
                f"- not_for: {row.get('not_for', '')}",
                f"- stability: {row.get('stability', '')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def format_source_show_markdown(payload: dict[str, Any]) -> str:
    """Render one source/scope/domain payload as Markdown."""

    if not payload:
        return "# 观澜信源详情\n\n未找到匹配信源。"
    kind = payload.get("kind")
    if kind == "scope":
        scope = payload.get("scope") or {}
        lines = [f"# 观澜 Scope / {scope.get('id', '')}", "", f"- 名称: {scope.get('name', '')}", f"- 类型: {scope.get('source_type', '')}", f"- trust_level: {scope.get('trust_level', '')}", f"- 说明: {scope.get('description', '')}", ""]
        lines.append(format_sources_markdown(payload.get("sources") or [], title="Scope 内信源卡"))
        return "\n".join(lines).rstrip()
    if kind == "matrix_source":
        lines = [f"# 观澜信源详情 / {payload.get('id', '')}", ""]
        for key in ["name", "surface", "platform", "category", "backend", "status", "evidence_role", "source_domain", "quality", "route_when", "command", "caveat", "notes"]:
            if payload.get(key):
                lines.append(f"- {key}: {payload.get(key)}")
        if payload.get("risk_tags"):
            lines.append("- risk_tags: " + ", ".join(payload.get("risk_tags") or []))
        return "\n".join(lines)
    if kind == "search_entrypoint":
        lines = [f"# 观澜搜索入口 / {payload.get('id', '')}", ""]
        for key in ["name", "region", "status", "integration", "evidence_role", "best_for", "caveat", "url_template"]:
            if payload.get(key):
                lines.append(f"- {key}: {payload.get(key)}")
        if payload.get("operator_support"):
            lines.append("- operator_support: " + ", ".join(payload.get("operator_support") or []))
        if payload.get("risk_tags"):
            lines.append("- risk_tags: " + ", ".join(payload.get("risk_tags") or []))
        lines.append("- boundary: 搜索入口是只读目录，不代表 Guanlan 会裸抓该引擎。")
        return "\n".join(lines)
    return format_sources_markdown([payload], title=f"观澜信源详情 / {payload.get('domain', '')}")


def format_source_explain_markdown(payload: dict[str, Any]) -> str:
    """Render source explanation as Markdown."""

    lines = [f"# 观澜信源解释 / {payload.get('query', '')}", ""]
    for item in payload.get("explain") or []:
        lines.append(f"- {item}")
    lines.append(f"- 边界: {payload.get('boundary', '')}")
    entrypoint_policy = payload.get("search_entrypoint_policy") or {}
    if entrypoint_policy:
        selected = entrypoint_policy.get("selected") or []
        names = [str(item.get("name") or item.get("id") or "") for item in selected[:5] if item]
        lines.append(f"- 搜索入口策略: {entrypoint_policy.get('policy', '')}")
        if names:
            lines.append(f"- 可解释入口: {', '.join(names)}")
        if entrypoint_policy.get("boundary"):
            lines.append(f"- 入口边界: {entrypoint_policy.get('boundary')}")
    lines.append("")
    lines.append(format_sources_markdown(payload.get("sources") or [], title="推荐信源卡"))
    return "\n".join(lines).rstrip()


def _source_card_row(scope_id: str, scope: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    domain = str(card.get("domain") or "")
    source_id = f"{scope_id}:{domain}" if scope_id else domain
    source_type = str(card.get("source_type") or scope.get("source_type") or "通用网页")
    roles = list(card.get("content_roles") or [])
    risk_tags = list(card.get("risk_tags") or [])
    return {
        "source_id": source_id,
        "domain": domain,
        "scope_id": scope_id or card.get("scope_id") or "open_web",
        "source_type": source_type,
        "authority_score": card.get("authority_score", 0.2),
        "sample_value": card.get("sample_value", 0.2),
        "freshness_value": card.get("freshness_value", 0.2),
        "risk_tags": risk_tags,
        "content_roles": roles,
        "best_for": _best_for(scope, card),
        "not_for": _not_for(card),
        "stability": card.get("stability") or "best_effort",
        "authority_role": card.get("authority_role") or "open_web",
        "notes": card.get("notes") or scope.get("description") or "",
    }


def _best_for(scope: dict[str, Any], card: dict[str, Any]) -> str:
    roles = ", ".join(card.get("content_roles") or [])
    desc = str(scope.get("description") or "").strip()
    if desc and roles:
        return f"{desc}；适合作为 {roles}。"
    return desc or (f"适合作为 {roles}。" if roles else "开放网页线索。")


def _not_for(card: dict[str, Any]) -> str:
    risks = set(card.get("risk_tags") or [])
    if "not_investment_advice" in risks:
        return "不能作为买入、卖出或持有建议。"
    if {"sample_bias", "not_representative", "platform_framing"} & risks:
        return "不能代表总体比例或最终事实，只能作公开样本。"
    if {"bureaucratic_language", "slow_update"} & risks:
        return "不适合单独解释现实执行效果，需要补媒体/样本。"
    if {"vendor_framing", "marketing_language"} & risks:
        return "不适合单独评价第三方口碑或真实性能。"
    return "不应脱离来源身份单独下结论。"


def _source_explain_text(plan: dict[str, Any]) -> list[str]:
    intents = ", ".join(plan.get("primary_intents") or []) or "general"
    scopes = ", ".join(plan.get("preferred_scopes") or []) or "open web"
    roles = ", ".join(plan.get("evidence_roles") or []) or "broad_web"
    lines = [f"主要意图为 {intents}，优先 scope 为 {scopes}。", f"需要覆盖的证据角色：{roles}。"]
    if plan.get("warnings"):
        lines.extend(str(item) for item in list(plan.get("warnings") or [])[:3])
    return lines


def _audit_message(platform: str, catalog: dict[str, Any], matrix_rows: list[dict[str, Any]], *, conflict: bool) -> str:
    if conflict:
        return "channel catalog 写 stable，但 source matrix 存在 experimental/optional，需要人工统一口径。"
    if platform in {"xiaohongshu", "weibo", "douyin", "zhihu"}:
        return "保持高风控/实验/最佳努力边界，不应包装成稳定端到端能力。"
    if platform in {"rss", "web"}:
        return "基础开放源应保持 stable/verified 口径。"
    if catalog or matrix_rows:
        return "口径未发现明显冲突。"
    return "未找到足够元数据。"


def _audit_summary(checks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(checks),
        "pass": sum(1 for item in checks if item.get("status") == "pass"),
        "warn": sum(1 for item in checks if item.get("status") == "warn"),
        "fail": sum(1 for item in checks if item.get("status") == "fail"),
    }
