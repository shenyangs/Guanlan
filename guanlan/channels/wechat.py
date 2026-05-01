# -*- coding: utf-8 -*-
"""WeChat Official Account articles — read and search.

Read:   Exa crawling (primary) / Camoufox stealth browser (optional)
Search: Exa web_search with includeDomains mp.weixin.qq.com / WechatSogou (optional backup)
"""

import shutil
import subprocess

from .base import Channel


def _exa_available() -> bool:
    mcporter = shutil.which("mcporter")
    if not mcporter:
        return False
    try:
        r = subprocess.run(
            [mcporter, "config", "list"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=5,
        )
        return "exa" in r.stdout.lower()
    except Exception:
        return False


def _wechat_sogou_available() -> bool:
    try:
        import wechatsogou  # noqa: F401

        return True
    except ImportError:
        return False


class WeChatChannel(Channel):
    name = "wechat"
    description = "微信公众号文章"
    backends = ["Exa via mcporter (backend-ready)", "WechatSogou (optional)", "Camoufox (optional)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "mp.weixin.qq.com" in d or "weixin.qq.com" in d

    def check(self, config=None):
        has_exa = _exa_available()
        has_wechat_sogou = _wechat_sogou_available()
        has_camoufox = False
        try:
            import camoufox  # noqa: F401
            has_camoufox = True
        except ImportError:
            pass

        if has_exa or has_wechat_sogou or has_camoufox:
            ready = []
            if has_exa:
                ready.append("Exa")
            if has_wechat_sogou:
                ready.append("WechatSogou")
            if has_camoufox:
                ready.append("Camoufox")
            return "warn", (
                f"backend-ready / unverified / best-effort：已检测到 {'、'.join(ready)}。"
                "这只代表公众号搜索/阅读路径已具备后端，不代表端到端稳定可用；"
                "遇到验证码、登录墙、反爬或正文缺失时，请降级为普通网页搜索、同题转载页或手动授权路径。"
            )
        return "off", (
            "未检测到公众号后端。可选安装 mcporter + Exa、WechatSogou 或 Camoufox；"
            "安装后也只会标记为 backend-ready，端到端可用性仍需按具体文章验证。"
        )
