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
        command="guanlan hotnews bilibili-hot-search --limit 50",
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
        command="guanlan hotnews sspai --limit 50",
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
        command="guanlan hotnews xinzhiyuan --limit 50",
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
        command="guanlan hotnews zeli-hn --limit 50",
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
        command="guanlan hotnews buzzing --limit 50",
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
