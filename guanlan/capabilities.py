# -*- coding: utf-8 -*-
"""Human- and agent-readable Guanlan capability map."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Capability:
    """A discoverable Guanlan capability with its safest default entry points."""

    id: str
    name: str
    description: str
    when_to_use: str
    cli: list[str]
    mcp: str | None = None
    status: str = "stable"
    boundary: str = "只读、公开优先；需要授权时停下来问用户。"
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "when_to_use": self.when_to_use,
            "cli": self.cli,
            "mcp": self.mcp,
            "status": self.status,
            "boundary": self.boundary,
            "examples": self.examples,
        }


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        id="discover",
        name="能力发现",
        description="解释 Guanlan 能做什么、每个能力该在什么时候用，以及默认边界。",
        when_to_use="用户或 Agent 不确定 Guanlan 有哪些功能、该先调用什么时。",
        cli=["guanlan welcome", "guanlan capabilities", "guanlan capabilities --json"],
        mcp="guanlan_capabilities",
        examples=["观澜能做什么？", "我应该用 search 还是 research？"],
    ),
    Capability(
        id="route",
        name="需求与信源路由",
        description="先判断问题更像政策、官方、口碑、产业、电商、技术、财经还是热点，并给出优先信源和证据角色。",
        when_to_use="搜索前不知道该查哪些来源，或用户关心严谨性、信源分类、为什么这样搜。",
        cli=["guanlan route \"中文研究需求\"", "guanlan route \"某产品 用户评价 值不值得买\" --json"],
        mcp="guanlan_route",
        boundary="路由是软约束，不把世界缩小成白名单；仍保留开放网页兜底。",
        examples=["这个问题该去哪搜？", "帮我区分官方、媒体和用户评价。"],
    ),
    Capability(
        id="search",
        name="中文互联网搜索",
        description="多后端搜索、去重、信源分类、可信度评分、scope/site 定向和 Agent 上下文输出。",
        when_to_use="用户说查一下、搜一下、找资料，或需要一批可筛选的网页证据。",
        cli=[
            "guanlan search \"关键词\" --limit 50",
            "guanlan search \"中文问题\" --profile china --limit 50",
            "guanlan search \"政策问题\" --profile china --scope party_central",
            "guanlan search --list-scopes",
        ],
        mcp="guanlan_search",
        examples=["查一下低空经济最新政策。", "只搜知乎上关于这个产品的评价。"],
    ),
    Capability(
        id="read",
        name="网页阅读",
        description="把 URL 读取成 Agent 可用 Markdown，按 Jina Reader、直连 HTML、搜索兜底逐级降级。",
        when_to_use="用户给了链接，或 research 需要读取代表性原文。",
        cli=["guanlan read \"https://example.com/article\" --max-chars 12000", "guanlan read \"URL\" --backend direct"],
        mcp="guanlan_read",
        boundary="只读公开页面；登录墙、反爬、403 时降级，不自动读取 Cookie。",
        examples=["读一下这篇文章。", "Jina 读出来噪音太多，试试直连。"],
    ),
    Capability(
        id="research",
        name="研究证据包",
        description="把搜索、路由、代表证据、可选原文摘录和来源分布整理成一份 Agent-ready evidence packet。",
        when_to_use="用户希望查清楚、给依据、整理资料、做研究，不只是要几个链接。",
        cli=[
            "guanlan research \"关键词\" --profile china",
            "guanlan research \"政策问题\" --preset policy",
            "guanlan research \"产品 用户评价\" --preset reputation --read-top 0",
        ],
        mcp="guanlan_research",
        examples=["帮我查清楚这个行业趋势。", "整理一下这个产品的公开口碑。"],
    ),
    Capability(
        id="advisor",
        name="助理视角",
        description="基于检索材料生成谨慎的建议写作规则：可能意图、证据边界、下一步和风险提醒。",
        when_to_use="用户要建议、影响、下一步、风险，或想知道为什么会搜索这个内容。",
        cli=[
            "guanlan research \"query\" --profile china --advisor",
            "guanlan research \"产品 用户评价\" --preset reputation --read-top 0 --advisor",
        ],
        mcp="guanlan_research(advisor=true)",
        boundary="只能提出证据支持下的假设；不能断言用户真实意图，不能替代法律、医疗、金融等专业判断。",
        examples=["查完后给我建议。", "你猜我搜这个可能是为了什么？"],
    ),
    Capability(
        id="hotnews",
        name="热榜观察",
        description="抓取中文热榜、社区热帖和可选 NewsNow 源，支持跨源趋势归并和简报。",
        when_to_use="用户问今天热点、某个平台在讨论什么、中文互联网当日水势。",
        cli=[
            "guanlan hotnews today --limit 50",
            "guanlan hotnews weibo --limit 50",
            "guanlan hotnews bilibili --limit 50",
            "guanlan hotnews ithome --limit 50",
            "guanlan hotnews v2ex --limit 50",
            "guanlan hotnews today --trends --brief",
            "guanlan hotnews list",
        ],
        mcp="guanlan_hotnews",
        boundary="热榜代表平台公开榜单，不代表全网民意；知乎等源可能 best-effort 或 experimental。",
        examples=["今天中文互联网有什么热点？", "技术社区今天在聊什么？"],
    ),
    Capability(
        id="pulse",
        name="话题回响",
        description="从公开样本粗略观察一个话题的正负向、争议点和代表样本。",
        when_to_use="用户问这个产品/事件现在是被夸还是被骂，或想看舆论回响。",
        cli=["guanlan pulse \"产品名 用户评价\" --format context", "guanlan pulse \"话题\" --limit 80"],
        mcp="guanlan_pulse",
        boundary="这是公开样本回响，不是民调；必须保留样本量和偏差提醒。",
        examples=["看看这个产品现在风评怎么样。", "这件事网上主要在骂什么？"],
    ),
    Capability(
        id="archive",
        name="本地知识库",
        description="把网页或研究结果保存成本地 Markdown 档案，并支持本地检索和导出。",
        when_to_use="用户希望沉淀资料、复用已读材料，或给本地 RAG/长期项目准备语料。",
        cli=[
            "guanlan archive add \"URL\"",
            "guanlan archive ingest-search \"关键词\" --limit 80",
            "guanlan archive search \"关键词\" --format context",
            "guanlan archive export --format jsonl",
        ],
        mcp="guanlan_archive_search",
        boundary="默认保存在本机；不上传档案内容。",
        examples=["把这批资料存起来。", "在我之前归档里搜一下。"],
    ),
    Capability(
        id="local_llm",
        name="本地模型联网前置",
        description="给 LM Studio、Ollama、Open WebUI 等本地模型准备带证据和回答规则的 Prompt，或通过 MCP/HTTP 接入。",
        when_to_use="本地模型不知道 Guanlan，也没有联网能力，需要 Guanlan 先搜、读、整理。",
        cli=[
            "guanlan prompt \"问题\" --profile china",
            "guanlan research \"问题\" --format prompt",
            "guanlan mcp config --client generic",
            "guanlan serve --host 127.0.0.1 --port 8765",
        ],
        mcp=None,
        boundary="模型不会天然知道 Guanlan；要么接 MCP/HTTP，要么把 prompt/evidence 复制给模型。",
        examples=["怎么把 LM Studio 接上观澜？", "给本地模型准备一个带资料的输入。"],
    ),
    Capability(
        id="health",
        name="状态与诊断",
        description="查看渠道可用性、稳定性、授权边界、缓存状态和配置安全扫描。",
        when_to_use="安装后验证、排查为什么某个平台不可用、检查是否需要授权或外部依赖。",
        cli=["guanlan status", "guanlan doctor --trace", "guanlan doctor --check-config"],
        mcp="guanlan_status",
        boundary="深度认证检查和浏览器 Cookie 读取必须由用户明确授权。",
        examples=["当前哪些渠道可用？", "为什么微博/微信没有跑通？"],
    ),
)


def list_capabilities() -> list[dict[str, Any]]:
    """Return the capability map as JSON-serializable dictionaries."""
    return [capability.to_dict() for capability in CAPABILITIES]


def format_capabilities_markdown(capabilities: list[dict[str, Any]] | None = None) -> str:
    """Render a compact capability guide for humans and agents."""
    items = capabilities or list_capabilities()
    lines = [
        "# 观澜能力地图",
        "",
        "当用户或 Agent 不知道观澜能做什么时，先看这张表。默认策略：公开信息优先、只读优先、需要授权时停下来问用户。",
        "",
        "## 快速入口",
        "",
        "- 不知道该用什么：`guanlan capabilities`",
        "- 刚装好想快速上手：`guanlan welcome`",
        "- 不知道去哪搜：`guanlan route \"问题\"`",
        "- 只要搜索结果：`guanlan search \"问题\" --limit 50`",
        "- 要证据包：`guanlan research \"问题\" --profile china`",
        "- 要建议/下一步：`guanlan research \"问题\" --advisor`",
        "- 看今日热点：`guanlan hotnews today --limit 50`",
        "- 查可用状态：`guanlan status`",
        "",
        "## 能力清单",
        "",
    ]
    for item in items:
        lines.append(f"### {item['name']} (`{item['id']}`)")
        lines.append(f"- 适用：{item['when_to_use']}")
        lines.append(f"- 能力：{item['description']}")
        lines.append(f"- 状态：{item['status']}")
        lines.append(f"- 边界：{item['boundary']}")
        if item.get("mcp"):
            lines.append(f"- MCP：`{item['mcp']}`")
        lines.append("- CLI：")
        lines.extend(f"  - `{command}`" for command in item.get("cli", []))
        if item.get("examples"):
            lines.append("- 典型用户说法：" + "；".join(item["examples"]))
        lines.append("")
    lines.append("Agent 规则：如果用户问“你能做什么/观澜有哪些功能/该怎么查”，先调用 capabilities；如果用户给出具体问题但信源不清，先 route，再 search/research。")
    return "\n".join(lines).rstrip()


def format_capabilities_json() -> str:
    """Return pretty JSON for the CLI."""
    return json.dumps(list_capabilities(), ensure_ascii=False, indent=2)
