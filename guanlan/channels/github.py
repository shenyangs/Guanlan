# -*- coding: utf-8 -*-
"""GitHub — check if gh CLI is available."""

import shutil
import subprocess

from .base import Channel, skip_sensitive_probes


class GitHubChannel(Channel):
    name = "github"
    description = "GitHub 仓库和代码"
    backends = ["gh CLI"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        return "github.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        gh = shutil.which("gh")
        if not gh:
            return "warn", "gh CLI 未安装。安装：https://cli.github.com"
        if skip_sensitive_probes():
            return "ok", "gh CLI 已安装（已跳过认证探测，避免钥匙串弹窗）"
        try:
            r = subprocess.run(
                [gh, "auth", "status"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=5
            )
            if r.returncode == 0:
                return "ok", "完整可用（读取、搜索、Fork、Issue、PR 等）"
            return "warn", "gh CLI 已安装但未认证。运行 gh auth login 可解锁完整功能"
        except Exception:
            return "warn", "gh CLI 状态检查失败，运行 gh auth status 查看详情"
