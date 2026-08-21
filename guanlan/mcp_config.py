# -*- coding: utf-8 -*-
"""MCP client config snippets for Guanlan."""

from __future__ import annotations

import json
from typing import Any

SUPPORTED_CLIENTS = ("generic", "claude", "cursor", "codex", "openwebui")


def build_mcp_config(client: str = "generic", command: str = "guanlan-mcp", profile: str = "full") -> dict[str, Any]:
    """Return a copyable read-only MCP client config."""
    client = (client or "generic").strip().lower()
    if client not in SUPPORTED_CLIENTS:
        raise ValueError(f"Unknown MCP client: {client}")
    normalized_profile = str(profile or "full").strip().lower()
    if normalized_profile not in {"full", "compact"}:
        raise ValueError("MCP profile must be one of: full, compact")
    server = {"command": command or "guanlan-mcp", "args": [] if normalized_profile == "full" else ["--profile", normalized_profile]}
    if client == "openwebui":
        return {"servers": {"guanlan": server}}
    return {"mcpServers": {"guanlan": server}}


def format_mcp_config_markdown(client: str = "generic", command: str = "guanlan-mcp", profile: str = "full") -> str:
    """Render MCP config with brief install guidance."""
    config = build_mcp_config(client=client, command=command, profile=profile)
    config_json = json.dumps(config, ensure_ascii=False, indent=2)
    return "\n".join(
        [
            "# Guanlan MCP 配置",
            "",
            f"- Client: {client}",
            f"- Command: `{command}`",
            f"- Profile: `{profile}`（默认 full；compact 仅保留 6 个核心只读工具）",
            "- 用途: 让支持 MCP 的 Agent 调用观澜搜索、阅读、研究、热榜、回响和本地归档检索。",
            "- 边界: 默认只读；不会发布、评论、点赞、私信；不会主动读取浏览器 Cookie。",
            "",
            "```json",
            config_json,
            "```",
            "",
            "安装后可先运行：",
            "",
            "```bash",
            "guanlan status",
            "guanlan doctor --trace",
            "```",
        ]
    )
