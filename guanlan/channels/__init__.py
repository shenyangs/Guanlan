# -*- coding: utf-8 -*-
"""
Channel registry — lists all supported platforms for doctor checks.
"""

from typing import List, Optional

from .base import Channel
from .bilibili import BilibiliChannel
from .douyin import DouyinChannel
from .exa_search import ExaSearchChannel
from .github import GitHubChannel
from .hotnews import HotNewsChannel
from .linkedin import LinkedInChannel
from .open_websearch import OpenWebSearchChannel
from .reddit import RedditChannel
from .rss import RSSChannel
from .twitter import TwitterChannel
from .v2ex import V2EXChannel

# Import all channels
from .web import WebChannel
from .wechat import WeChatChannel
from .weibo import WeiboChannel
from .xiaohongshu import XiaoHongShuChannel
from .xiaoyuzhou import XiaoyuzhouChannel
from .xueqiu import XueqiuChannel
from .youtube import YouTubeChannel

ALL_CHANNELS: List[Channel] = [
    GitHubChannel(),
    TwitterChannel(),
    YouTubeChannel(),
    RedditChannel(),
    BilibiliChannel(),
    XiaoHongShuChannel(),
    DouyinChannel(),
    LinkedInChannel(),
    WeChatChannel(),
    WeiboChannel(),
    XiaoyuzhouChannel(),
    V2EXChannel(),
    XueqiuChannel(),
    RSSChannel(),
    ExaSearchChannel(),
    OpenWebSearchChannel(),
    HotNewsChannel(),
    WebChannel(),
]


def get_channel(name: str) -> Optional[Channel]:
    """Get a channel by name."""
    for ch in ALL_CHANNELS:
        if ch.name == name:
            return ch
    return None


def get_all_channels(profile: str | None = None) -> List[Channel]:
    """Get all registered channels."""
    if not profile:
        return ALL_CHANNELS

    from guanlan.channel_catalog import order_channel_names

    by_name = {ch.name: ch for ch in ALL_CHANNELS}
    ordered_names = order_channel_names(by_name.keys(), profile)
    return [by_name[name] for name in ordered_names]


__all__ = [
    "Channel",
    "ALL_CHANNELS",
    "get_channel", "get_all_channels",
]
