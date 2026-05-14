# -*- coding: utf-8 -*-
"""Ebrun vertical channel routing helpers.

This module keeps Ebrun as a first-class ecommerce/retail source without
requiring users to install an external skill. It stores only channel facts and
routing terms; fetching remains read-only and bounded by the upstream JSON feed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

EBRUN_BASE_URL = "https://www.ebrun.com/"
EBRUN_SERVER_LIMIT_NOTE = "Ebrun public channel feed currently returns a small latest-items window, usually around 10 rows."


@dataclass(frozen=True)
class EbrunChannel:
    alias: str
    channel: str
    sub_channel: str
    path: str
    keywords: tuple[str, ...]
    query_terms: tuple[str, ...]
    evidence_role: str = "ecommerce_vertical_feed"

    @property
    def source_id(self) -> str:
        return f"ebrun:{self.alias}"

    @property
    def api_url(self) -> str:
        return EBRUN_BASE_URL + self.path.lstrip("/")

    def to_dict(self) -> dict[str, str | list[str]]:
        data = asdict(self)
        data["source_id"] = self.source_id
        data["api_url"] = self.api_url
        data["server_limit_note"] = EBRUN_SERVER_LIMIT_NOTE
        data["keywords"] = list(self.keywords)
        data["query_terms"] = list(self.query_terms)
        return data


def _ch(
    alias: str,
    channel: str,
    sub_channel: str,
    path: str,
    keywords: Iterable[str],
    query_terms: Iterable[str],
    evidence_role: str = "ecommerce_vertical_feed",
) -> EbrunChannel:
    return EbrunChannel(
        alias=alias,
        channel=channel,
        sub_channel=sub_channel,
        path=path,
        keywords=tuple(keywords),
        query_terms=tuple(query_terms),
        evidence_role=evidence_role,
    )


EBRUN_CHANNELS: tuple[EbrunChannel, ...] = (
    _ch(
        "recommend",
        "推荐",
        "最新",
        "_index/ClaudeCode/SkillJson/information_recommend.json",
        ("亿邦", "电商新闻", "电商资讯", "最新电商"),
        ("电商", "零售", "产业", "案例"),
        "ecommerce_news_signal",
    ),
    _ch("retail", "未来零售", "最新", "_index/ClaudeCode/SkillJson/information_channel_50.json", ("未来零售", "零售", "即时零售", "电商零售", "本地生活"), ("未来零售", "即时零售", "渠道", "商家")),
    _ch("taobao-tmall", "未来零售", "淘宝天猫", "_index/ClaudeCode/SkillJson/information_channel_55.json", ("淘宝", "天猫", "淘天", "阿里妈妈", "双11", "618"), ("淘宝天猫", "淘天", "商家", "大促")),
    _ch("douyin", "未来零售", "抖音", "_index/ClaudeCode/SkillJson/information_channel_56.json", ("抖音", "抖音电商", "抖音小店", "直播电商"), ("抖音电商", "直播电商", "商家", "达人")),
    _ch("jd", "未来零售", "京东", "_index/ClaudeCode/SkillJson/information_channel_57.json", ("京东", "京喜", "京东到家"), ("京东", "即时零售", "供应链", "商家")),
    _ch("wechat-video", "未来零售", "视频号", "_index/ClaudeCode/SkillJson/information_channel_60.json", ("视频号", "微信小店", "微信电商", "私域"), ("视频号", "微信小店", "私域电商", "商家")),
    _ch("meituan", "未来零售", "美团", "_index/ClaudeCode/SkillJson/information_channel_61.json", ("美团", "美团闪购", "即时零售", "本地生活", "到店"), ("美团", "即时零售", "本地生活", "商家")),
    _ch("kuaishou", "未来零售", "快手", "_index/ClaudeCode/SkillJson/information_channel_59.json", ("快手", "快手电商", "老铁经济"), ("快手电商", "直播电商", "商家")),
    _ch("pinduoduo", "未来零售", "拼多多", "_index/ClaudeCode/SkillJson/information_channel_58.json", ("拼多多", "多多买菜", "百亿补贴"), ("拼多多", "平台", "商家", "价格")),
    _ch("xiaohongshu", "未来零售", "小红书", "_index/ClaudeCode/SkillJson/information_channel_62.json", ("小红书", "买手", "种草", "生活方式电商"), ("小红书电商", "买手", "种草", "商家")),
    _ch("cross-border", "跨境电商", "最新", "_index/ClaudeCode/SkillJson/information_channel_51.json", ("跨境", "跨境电商", "出海", "海外仓", "独立站", "外贸"), ("跨境电商", "出海", "海外仓", "卖家")),
    _ch("amazon", "跨境电商", "亚马逊", "_index/ClaudeCode/SkillJson/information_channel_68.json", ("亚马逊", "amazon", "亚马逊卖家", "FBA"), ("亚马逊", "卖家", "FBA", "跨境")),
    _ch("alibaba-international", "跨境电商", "阿里国际", "_index/ClaudeCode/SkillJson/information_channel_84.json", ("阿里国际", "速卖通", "aliexpress", "AIDC", "国际站"), ("阿里国际", "速卖通", "跨境", "商家")),
    _ch("tiktok-shop", "跨境电商", "TikTok", "_index/ClaudeCode/SkillJson/information_channel_65.json", ("tiktok", "TikTok Shop", "tik tok", "抖音海外"), ("TikTok Shop", "跨境", "卖家", "达人")),
    _ch("temu", "跨境电商", "Temu", "_index/ClaudeCode/SkillJson/information_channel_67.json", ("temu", "拼多多海外", "全托管"), ("Temu", "跨境", "卖家", "全托管")),
    _ch("shein", "跨境电商", "SHEIN", "_index/ClaudeCode/SkillJson/information_channel_66.json", ("shein", "希音", "快时尚"), ("SHEIN", "品牌出海", "供应链", "跨境")),
    _ch("industrial", "产业互联网", "最新", "_index/ClaudeCode/SkillJson/information_channel_52.json", ("产业互联网", "产业", "产业数字化", "工业品"), ("产业互联网", "产业数字化", "企业服务", "供应链")),
    _ch("b2b", "产业互联网", "B2B", "_index/ClaudeCode/SkillJson/information_channel_77.json", ("b2b", "B2B", "工业品", "企业采购"), ("B2B", "工业品", "采购", "供应链")),
    _ch("industrial-tech", "产业互联网", "产业科技", "_index/ClaudeCode/SkillJson/information_channel_74.json", ("产业科技", "工业科技", "智能制造", "机器人"), ("产业科技", "智能制造", "工业", "案例")),
    _ch("data-elements", "产业互联网", "数据要素", "_index/ClaudeCode/SkillJson/information_channel_78.json", ("数据要素", "数据资产", "数据交易", "数据空间"), ("数据要素", "数据资产", "产业", "政策")),
    _ch("industrial-overseas", "产业互联网", "产业出海", "_index/ClaudeCode/SkillJson/information_channel_75.json", ("产业出海", "制造出海", "供应链出海"), ("产业出海", "供应链", "全球化", "案例")),
    _ch("supply-chain", "产业互联网", "数智供应链", "_index/ClaudeCode/SkillJson/information_channel_79.json", ("供应链", "数智供应链", "物流", "仓储"), ("供应链", "物流", "仓储", "数智化")),
    _ch("procurement", "产业互联网", "数智化采购", "_index/ClaudeCode/SkillJson/information_channel_73.json", ("采购", "数智化采购", "采购数字化"), ("采购", "数字化", "B2B", "企业服务")),
    _ch("brand", "品牌", "最新", "_index/ClaudeCode/SkillJson/information_channel_87.json", ("品牌", "新消费", "消费品牌", "DTC"), ("品牌", "新消费", "渠道", "增长"), "brand_industry_signal"),
    _ch("new-brand", "品牌", "新竞争力品牌", "_index/ClaudeCode/SkillJson/information_channel_89.json", ("新竞争力品牌", "新品牌", "消费品牌", "品牌大会"), ("新品牌", "消费品牌", "增长", "案例"), "brand_industry_signal"),
    _ch("brand-globalization", "品牌", "品牌全球化", "_index/ClaudeCode/SkillJson/information_channel_90.json", ("品牌全球化", "品牌出海", "全球化品牌", "DTC出海"), ("品牌全球化", "品牌出海", "DTC", "案例"), "brand_globalization_signal"),
    _ch("ai", "AI", "最新", "_index/ClaudeCode/SkillJson/information_channel_88.json", ("AI电商", "AI客服", "人工智能电商", "AIGC电商", "智能客服", "AI投放"), ("AI", "电商", "商家", "客服", "投放"), "ai_ecommerce_signal"),
)

_CHANNEL_BY_ALIAS = {channel.alias: channel for channel in EBRUN_CHANNELS}
_ALIAS_NORMALIZATION = {
    "latest": "recommend",
    "news": "recommend",
    "future-retail": "retail",
    "future_retail": "retail",
    "retail-latest": "retail",
    "tmall": "taobao-tmall",
    "taobao": "taobao-tmall",
    "jingdong": "jd",
    "pdd": "pinduoduo",
    "xhs": "xiaohongshu",
    "redbook": "xiaohongshu",
    "crossborder": "cross-border",
    "cross_border": "cross-border",
    "cross-border-latest": "cross-border",
    "ali-international": "alibaba-international",
    "aliexpress": "alibaba-international",
    "tiktok": "tiktok-shop",
    "tiktokshop": "tiktok-shop",
    "industry": "industrial",
    "industrial-internet": "industrial",
    "data": "data-elements",
    "data-elements": "data-elements",
    "global-brand": "brand-globalization",
    "brand-global": "brand-globalization",
}


def list_ebrun_channels() -> list[dict[str, str | list[str]]]:
    return [channel.to_dict() for channel in EBRUN_CHANNELS]


def resolve_ebrun_channel(source: str = "recommend") -> EbrunChannel:
    key = (source or "recommend").strip().lower().removeprefix("ebrun:")
    key = _ALIAS_NORMALIZATION.get(key, key)
    if key in _CHANNEL_BY_ALIAS:
        return _CHANNEL_BY_ALIAS[key]
    for channel in EBRUN_CHANNELS:
        names = {channel.channel.lower(), channel.sub_channel.lower(), *(kw.lower() for kw in channel.keywords)}
        if key in names:
            return channel
    raise ValueError(f"Unknown Ebrun channel: {source}")


def match_ebrun_channels(query: str, *, limit: int = 3) -> list[EbrunChannel]:
    text = str(query or "").lower()
    if not text:
        return [resolve_ebrun_channel("recommend")]
    ecommerce_context = any(
        term in text
        for term in (
            "电商", "零售", "跨境", "出海", "品牌", "商家", "供应链", "产业互联网", "直播带货",
            "平台", "淘宝", "天猫", "京东", "抖音", "小红书", "亚马逊", "temu", "shein", "tiktok",
        )
    )
    scored: list[tuple[int, int, EbrunChannel]] = []
    for idx, channel in enumerate(EBRUN_CHANNELS):
        score = 0
        if channel.channel.lower() in text:
            score += 3
        if channel.sub_channel.lower() in text:
            score += 4
        for keyword in channel.keywords:
            kw = keyword.lower()
            if kw and kw in text:
                score += 3 if len(kw) >= 3 else 1
        for term in channel.query_terms:
            kw = term.lower()
            if kw and kw in text:
                score += 1
        if channel.alias == "ai" and not ecommerce_context:
            score = 0
        if score > 0:
            scored.append((score, -idx, channel))
    if not scored and ecommerce_context:
        scored.append((1, 0, resolve_ebrun_channel("recommend")))
    scored.sort(key=lambda item: (-item[0], item[1]))
    result: list[EbrunChannel] = []
    seen: set[str] = set()
    for _score, _idx, channel in scored:
        if channel.alias not in seen:
            seen.add(channel.alias)
            result.append(channel)
        if len(result) >= limit:
            break
    return result


def ebrun_query_variants(query: str, *, limit: int = 2) -> list[dict[str, str]]:
    variants: list[dict[str, str]] = []
    for channel in match_ebrun_channels(query, limit=limit):
        terms = " ".join(channel.query_terms[:4])
        variants.append(
            {
                "role": channel.evidence_role,
                "query": f"{query} {terms} site:ebrun.com",
                "channel": channel.channel,
                "sub_channel": channel.sub_channel,
                "source_id": channel.source_id,
                "api_url": channel.api_url,
                "reason": f"亿邦动力{channel.channel}/{channel.sub_channel}频道适合补充电商垂类报道和案例线索",
            }
        )
    return variants
