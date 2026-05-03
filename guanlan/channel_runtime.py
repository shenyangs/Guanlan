# -*- coding: utf-8 -*-
"""Experimental read-only channel runtime adapters.

The runtime layer is intentionally not wired into the main search/read path yet.
It gives Guanlan a low-risk place to test whether stable channels can share a
search/read/health shape without disturbing existing doctor/status behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from guanlan.channel_catalog import get_channel_metadata
from guanlan.source_registry import get_source_metadata


@dataclass(frozen=True)
class ChannelHealth:
    channel: str
    status: str
    stability: str
    verification: str
    risk_level: str
    boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeResult:
    channel: str
    kind: str
    status: str
    items: list[dict[str, Any]]
    boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChannelRuntime(Protocol):
    name: str

    def health(self) -> ChannelHealth: ...

    def search(self, query: str, limit: int = 10) -> RuntimeResult: ...

    def read(self, url: str, max_chars: int | None = None) -> RuntimeResult: ...


class BaseRuntime:
    name = "base"

    def health(self) -> ChannelHealth:
        meta = get_channel_metadata(self.name)
        return ChannelHealth(
            channel=self.name,
            status="available",
            stability=str(meta.get("stability") or "best-effort"),
            verification=str(meta.get("verification") or "unverified"),
            risk_level=str(meta.get("risk_level") or "low"),
            boundary="runtime adapter 试点；doctor/status 仍是渠道健康主入口。",
        )

    def search(self, query: str, limit: int = 10) -> RuntimeResult:
        return RuntimeResult(
            channel=self.name,
            kind="search",
            status="unsupported",
            items=[],
            boundary="该试点 runtime 尚未提供 search；请继续使用现有 guanlan search/research。",
        )

    def read(self, url: str, max_chars: int | None = None) -> RuntimeResult:
        return RuntimeResult(
            channel=self.name,
            kind="read",
            status="unsupported",
            items=[],
            boundary="该试点 runtime 尚未提供 read；请继续使用现有 guanlan read。",
        )


class WebRuntime(BaseRuntime):
    name = "web"

    def read(self, url: str, max_chars: int | None = None) -> RuntimeResult:
        from guanlan.webtools import read_url

        content = read_url(url, max_chars=max_chars, backend="auto")
        return RuntimeResult(
            channel=self.name,
            kind="read",
            status="ok",
            items=[{"url": url, "content": content}],
            boundary="web runtime 只读 URL，不读取 Cookie 或登录态。",
        )


class RssRuntime(BaseRuntime):
    name = "rss"

    def search(self, query: str, limit: int = 10) -> RuntimeResult:
        from guanlan.feeds import fetch_feed_source

        items = fetch_feed_source("curated", limit=max(limit, 1), keyword=query or None)
        return RuntimeResult(
            channel=self.name,
            kind="search",
            status="ok",
            items=items,
            boundary="RSS runtime 使用现有 feeds curated 路径；只做低风险试点，不替代 feeds 命令。",
        )


class GithubRuntime(BaseRuntime):
    name = "github"

    def search(self, query: str, limit: int = 10) -> RuntimeResult:
        meta = get_source_metadata("newsnow:github-trending-today")
        return RuntimeResult(
            channel=self.name,
            kind="search",
            status="planned",
            items=[{"query": query, "source": meta, "recommended_command": f"guanlan search {query!r} --scope tech_dev --limit {max(limit, 1)}"}],
            boundary="GitHub runtime 先只暴露推荐入口；实际搜索仍走现有 search scope。",
        )


class V2exRuntime(BaseRuntime):
    name = "v2ex"

    def search(self, query: str, limit: int = 10) -> RuntimeResult:
        return RuntimeResult(
            channel=self.name,
            kind="search",
            status="planned",
            items=[{"query": query, "recommended_command": f"guanlan hotnews v2ex --limit {max(limit, 1)}"}],
            boundary="V2EX runtime 先只暴露热榜/社区入口建议；不改变 hotnews/search 主路径。",
        )


_RUNTIME_REGISTRY: dict[str, type[BaseRuntime]] = {
    "web": WebRuntime,
    "rss": RssRuntime,
    "github": GithubRuntime,
    "v2ex": V2exRuntime,
}


def list_runtime_adapters() -> list[dict[str, Any]]:
    return [get_runtime(name).health().to_dict() for name in sorted(_RUNTIME_REGISTRY)]


def get_runtime(name: str) -> BaseRuntime:
    key = (name or "").strip().lower()
    runtime_cls = _RUNTIME_REGISTRY.get(key)
    if not runtime_cls:
        raise ValueError(f"unsupported runtime adapter: {name}")
    return runtime_cls()
