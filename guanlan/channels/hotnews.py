# -*- coding: utf-8 -*-
"""HotNews — aggregated trending topics for Chinese platforms."""

import shutil
import subprocess

from guanlan.hotnews import list_sources

from .base import Channel


class HotNewsChannel(Channel):
    name = "hotnews"
    description = "中文平台热榜聚合"
    backends = ["native public endpoints", "mcp-hotnews-server (optional)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False

    def check(self, config=None):
        sources = list_sources()
        stable_sources = ", ".join(
            sorted(k for k, v in sources.items() if v.get("status") == "stable")
        )
        experimental_sources = ", ".join(
            sorted(k for k, v in sources.items() if v.get("status") == "experimental")
        )
        native_sources = stable_sources
        if experimental_sources:
            native_sources += f"；实验源：{experimental_sources}"
        mcporter = shutil.which("mcporter")
        if not mcporter:
            return "ok", (
                f"原生热榜源可用（{native_sources}）。"
                "可选配置 mcp-hotnews-server 扩展更多平台。"
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
            return "ok", (
                f"原生热榜源可用（{native_sources}）。"
                "mcporter 连接异常，仅影响可选 MCP 热榜后端。"
            )

        output = r.stdout.lower()
        if any(alias in output for alias in ("hotnews", "hot-news", "mcp-hotnews")):
            return "ok", (
                f"原生热榜源可用（{native_sources}），"
                "且可选 hotnews MCP 已配置。"
            )
        return "ok", (
            f"原生热榜源可用（{native_sources}）。"
            "mcporter 已装但 hotnews MCP 未配置，可选扩展：mcp-hotnews-server。"
        )
