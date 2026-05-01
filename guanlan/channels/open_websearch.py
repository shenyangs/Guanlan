# -*- coding: utf-8 -*-
"""Open-WebSearch — free multi-engine search with China-friendly engines."""

import shutil
import subprocess

from .base import Channel


class OpenWebSearchChannel(Channel):
    name = "open_websearch"
    description = "中文多引擎搜索"
    backends = ["open-webSearch MCP"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        return False

    def check(self, config=None):
        mcporter = shutil.which("mcporter")
        if not mcporter:
            return "off", (
                "需要 mcporter + open-webSearch MCP。候选上游：\n"
                "  https://github.com/Aas-ee/open-webSearch\n"
                "配置后建议使用 alias: open-websearch"
            )

        try:
            r = subprocess.run(
                [mcporter, "config", "list"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except Exception:
            return "off", "mcporter 连接异常"

        output = r.stdout.lower()
        if any(alias in output for alias in ("open-websearch", "open_websearch", "websearch")):
            return "ok", "多引擎中文搜索可用（Baidu/Bing/GitHub/Juejin/CSDN 等，取决于上游配置）"
        return "off", (
            "mcporter 已装但 open-webSearch 未配置。候选上游：\n"
            "  https://github.com/Aas-ee/open-webSearch\n"
            "建议注册 alias: open-websearch"
        )
