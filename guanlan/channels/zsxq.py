# -*- coding: utf-8 -*-
"""ZhiShiXingQiu — optional private knowledge-community channel."""

from __future__ import annotations

import shutil
import subprocess
from urllib.parse import urlparse

from .base import Channel, skip_sensitive_probes


class ZsxqChannel(Channel):
    name = "zsxq"
    description = "知识星球私域知识社区"
    backends = ["zsxq-cli"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return "zsxq.com" in domain or "zsxq.cn" in domain or "zsxq.com.cn" in domain

    def check(self, config=None):
        cli = shutil.which("zsxq-cli")
        if not cli:
            return "off", (
                "可选知识星球能力未安装。需要时运行：\n"
                "  npm install -g zsxq-cli\n"
                "安装后由用户授权登录：\n"
                "  zsxq-cli auth login"
            )
        if skip_sensitive_probes():
            return "warn", "zsxq-cli 已安装（已跳过登录态探测，避免触发授权/钥匙串提示）。"

        try:
            result = subprocess.run(
                [cli, "auth", "status"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            output = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0:
                return "ok", "zsxq-cli 已安装且认证状态可用；默认只读，发帖/评论/标签等写操作必须用户明确确认。"
            if "not" in output.lower() or "login" in output.lower() or "unauth" in output.lower():
                return "warn", "zsxq-cli 已安装但未登录。运行 `zsxq-cli auth login`，让用户完成授权链接/验证码确认。"
            return "warn", "zsxq-cli 已安装但认证状态不明确；运行 `zsxq-cli doctor` 查看详情。"
        except Exception:
            return "warn", "zsxq-cli 已安装但状态检查失败；可运行 `zsxq-cli doctor` 诊断。"
