# -*- coding: utf-8 -*-
"""Reusable research recipes for Guanlan agents.

Recipes are workflow templates, not hidden automation. They make common
research moves explicit so agents can reuse them without overfitting one query.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import asdict, dataclass, field
from typing import Any

from guanlan.limits import DEFAULT_RESEARCH_LIMIT
from guanlan.workflow_decider import timeout_budget_ms, timeout_unit_contract


@dataclass(frozen=True)
class ResearchRecipe:
    """A stable recipe definition for agents."""

    id: str
    name: str
    description: str
    when_to_use: str
    preset: str = "general"
    scopes: list[str] = field(default_factory=list)
    evidence_layers: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    archive_policy: str = "读过、核验过的材料可以进入 archive；不要把搜索结果标题当正文入库。"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecipePlan:
    """Concrete commands for one query under a recipe."""

    recipe: dict[str, Any]
    query: str
    profile: str
    limit: int
    read_top: int
    timeout_budget_seconds: int = 180
    timeout_budget_ms: int = 180000
    commands: list[str] = field(default_factory=list)
    workflow_contract: list[str] = field(default_factory=list)
    timeout_unit_contract: list[str] = field(default_factory=list)
    expected_output: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_RECIPES: tuple[ResearchRecipe, ...] = (
    ResearchRecipe(
        id="university-advisor",
        name="高校招生/导师清单",
        description="查高校、院系、研究生招生、导师名单和培养方案，优先高校/院系官网。",
        when_to_use="用户问某高校导师、招生目录、研究生招生、推免复试、院系介绍或培养方案时。",
        preset="university",
        scopes=["university"],
        evidence_layers=["高校主站", "研究生招生网", "院系官网", "招生目录/培养方案"],
        boundaries=["不要用学术数据库替代招生/导师官方页面。", "如果学校没有研究生招生或导师清单，要自然说明缺口。"],
    ),
    ResearchRecipe(
        id="finance-risk",
        name="股票/公司风险",
        description="把行情、公告披露、财经新闻、宏观/行业、研报观点和投资者情绪分层。",
        when_to_use="用户问股票、股价、财报、公告、风险、资金流、雪球/股吧讨论或公司资本市场动态时。",
        preset="finance",
        scopes=["finance_quote", "finance_disclosure", "finance_news", "finance_macro", "finance_sentiment"],
        evidence_layers=["结构化行情", "公告披露", "监管/交易所", "财经新闻", "研报观点", "投资者情绪样本"],
        boundaries=["不输出买入、卖出或持有建议。", "动态财经页读不到正文时先改用结构化数据和披露源。"],
    ),
    ResearchRecipe(
        id="product-reputation",
        name="产品/公司口碑",
        description="分离官方宣传、媒体报道、社区讨论、用户反馈和风险样本。",
        when_to_use="用户问某产品值不值得买、口碑、投诉、替代品、竞品或公司信誉时。",
        preset="reputation",
        scopes=["reputation", "social_web", "business"],
        evidence_layers=["官方说明", "垂直媒体", "社区讨论", "投诉/风险样本", "对比视角"],
        boundaries=["社区样本不是总体统计。", "建议必须说明证据缺口和适用人群。"],
    ),
    ResearchRecipe(
        id="entertainment-pulse",
        name="文娱口碑/热度",
        description="区分榜单票房、平台评分、产业报道、宣发通稿和粉圈讨论。",
        when_to_use="用户问电影、综艺、明星、游戏、票房、评分、巡演、回归或热议时。",
        preset="entertainment",
        scopes=["entertainment", "social_web"],
        evidence_layers=["榜单/票房", "评分平台", "产业媒体", "官方/经纪公司", "粉丝/社区样本"],
        boundaries=["不要把单平台热度写成全网事实。", "翻译搬运和粉圈讨论只能作样本。"],
    ),
    ResearchRecipe(
        id="security-advisory",
        name="安全漏洞/反诈",
        description="优先 CVE/NVD/CISA/厂商公告/监管来源，核对影响版本和修复状态。",
        when_to_use="用户问 CVE、漏洞、补丁、钓鱼、诈骗短信、数据泄露或安全公告时。",
        preset="cybersecurity",
        scopes=["cybersecurity"],
        evidence_layers=["CVE/NVD", "CISA/监管", "厂商公告", "安全研究", "媒体转述"],
        boundaries=["不要根据未核验 PoC 指导攻击。", "必须区分影响版本、修复版本和缓解措施。"],
    ),
    ResearchRecipe(
        id="tech-radar",
        name="技术/AI 趋势",
        description="搜索结果之外必须补 RSS/开发者社区/项目源，避免只看营销稿。",
        when_to_use="用户问 AI、开发者工具、技术选型、开源项目、工程实践或技术趋势时。",
        preset="tech",
        scopes=["tech_dev", "business", "social_web"],
        evidence_layers=["官方/项目源", "开发者社区", "RSS/技术媒体", "论文/文档", "用户反馈"],
        boundaries=["技术结论要说明版本、发布时间和适用环境。", "营销稿不能替代文档或真实使用反馈。"],
    ),
    ResearchRecipe(
        id="trajectory-map",
        name="对象脉络/同类格局",
        description="把一个产品、公司、技术概念或人物拆成发展脉络、同类格局和交叉判断，形成可继续核验的研究骨架。",
        when_to_use="用户想系统搞懂一个对象、做竞品分析、梳理来龙去脉、判断赛道格局或准备深度研究材料时。",
        preset="general",
        scopes=["business", "tech_dev", "reputation", "social_web"],
        evidence_layers=[
            "对象定义/官方自述",
            "起源与关键节点",
            "阶段变化/路径依赖",
            "同类对象/竞品样本",
            "用户与社区反馈",
            "媒体/行业观察",
            "冲突、缺口与待核验问题",
        ],
        boundaries=[
            "先确认对象边界和同类对象，不要凭印象编造竞品清单。",
            "时间线只收有可见日期或可追溯节点的材料；无日期材料单列为背景。",
            "同类对比必须分清官方定位、媒体判断和用户样本，不能把单一社区意见写成总体结论。",
            "输出是证据骨架和研究判断，不是替用户做最终商业或投资决策。",
        ],
    ),
)


def list_recipes() -> list[dict[str, Any]]:
    return [recipe.to_dict() for recipe in _RECIPES]


def get_recipe(recipe_id: str) -> ResearchRecipe:
    key = _normalize_id(recipe_id)
    for recipe in _RECIPES:
        if key in {_normalize_id(recipe.id), _normalize_id(recipe.name)}:
            return recipe
    available = ", ".join(recipe.id for recipe in _RECIPES)
    raise KeyError(f"unknown recipe: {recipe_id}; available: {available}")


def suggest_recipe(query: str, *, route_plan: dict[str, Any] | None = None) -> ResearchRecipe:
    """Suggest a recipe from route intents and query terms."""

    text = (query or "").lower()
    intents = set()
    if route_plan:
        intents.update(str(item) for item in route_plan.get("primary_intents") or [])
        intents.update(str(item) for item in route_plan.get("secondary_intents") or [])
    if {"finance", "finance_quote", "finance_disclosure", "finance_macro", "finance_sentiment"} & intents or any(
        term in text for term in ("股票", "股价", "财报", "公告", "雪球", "fundflow", "stock")
    ):
        return get_recipe("finance-risk")
    if {"university_admissions", "university"} & intents or any(term in text for term in ("导师", "招生", "研究生", "院系官网")):
        return get_recipe("university-advisor")
    if {"entertainment", "global_entertainment", "jp_kr_entertainment"} & intents or any(
        term in text for term in ("电影", "综艺", "明星", "票房", "k-pop", "演唱会")
    ):
        return get_recipe("entertainment-pulse")
    if "cybersecurity" in intents or any(term in text for term in ("cve", "漏洞", "诈骗", "钓鱼")):
        return get_recipe("security-advisory")
    if any(
        term in text
        for term in (
            "竞品",
            "对比分析",
            "深度研究",
            "系统研究",
            "搞懂",
            "摸清楚",
            "来龙去脉",
            "发展历程",
            "演进",
            "格局",
            "赛道",
            "同类",
        )
    ):
        return get_recipe("trajectory-map")
    if "tech" in intents or any(term in text for term in ("github", "开源", "技术", "ai", "llm")):
        return get_recipe("tech-radar")
    return get_recipe("product-reputation")


def build_recipe_plan(
    recipe_id: str,
    query: str,
    *,
    profile: str = "china",
    limit: int = DEFAULT_RESEARCH_LIMIT,
    read_top: int | None = None,
) -> dict[str, Any]:
    recipe = get_recipe(recipe_id)
    clean_query = " ".join((query or "").split())
    effective_limit = max(int(limit or DEFAULT_RESEARCH_LIMIT), DEFAULT_RESEARCH_LIMIT)
    effective_read_top = _default_read_top(recipe, read_top)
    timeout_seconds = _default_timeout_budget_seconds(recipe)
    commands = _commands_for_recipe(recipe, clean_query, profile=profile, limit=effective_limit, read_top=effective_read_top)
    plan = RecipePlan(
        recipe=recipe.to_dict(),
        query=clean_query,
        profile=profile,
        limit=effective_limit,
        read_top=effective_read_top,
        timeout_budget_seconds=timeout_seconds,
        timeout_budget_ms=timeout_budget_ms(timeout_seconds),
        commands=commands,
        workflow_contract=[
            "先执行 recipe 给出的高层链路，不要退化成一次泛搜。",
            "把不同 evidence layer 分开写，不能把社区样本、媒体观点和官方披露混为一谈。",
            "只有当前链路仍缺关键证据时，才调用宿主 Agent 的通用 WebFetch/WebSearch 补证。",
        ],
        timeout_unit_contract=timeout_unit_contract(timeout_seconds),
        expected_output=[
            "来源分层清楚的证据包",
            "可引用材料与不可引用线索分开",
            "明确缺口、冲突、时间戳和下一步",
        ],
        boundaries=list(recipe.boundaries) + [recipe.archive_policy],
    )
    return plan.to_dict()


def format_recipe_list_markdown(recipes: list[dict[str, Any]] | None = None) -> str:
    data = recipes or list_recipes()
    lines = ["# 观澜研究 Recipe", "", "这些是可复用的研究流程模板，用来降低 Agent 误用率。", ""]
    for item in data:
        lines.append(f"## {item.get('id')} / {item.get('name')}")
        lines.append(f"- 适用: {item.get('when_to_use')}")
        lines.append(f"- 证据层: {', '.join(item.get('evidence_layers') or [])}")
        lines.append(f"- 命令: `guanlan recipe run {item.get('id')} \"你的问题\"`")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_recipe_plan_markdown(plan: dict[str, Any]) -> str:
    recipe = dict(plan.get("recipe") or {})
    lines = [
        f"# 观澜 Recipe / {recipe.get('id')} / {recipe.get('name')}",
        "",
        f"- 查询: {plan.get('query')}",
        f"- profile: {plan.get('profile')}",
        f"- limit: {plan.get('limit')}",
        f"- read_top: {plan.get('read_top')}",
        f"- timeout: {plan.get('timeout_budget_seconds')} 秒 / {plan.get('timeout_budget_ms')} ms",
        f"- 定位: {recipe.get('description')}",
        "",
        "## 证据层",
    ]
    lines.extend(f"- {item}" for item in recipe.get("evidence_layers") or [])
    lines.extend(["", "## 建议命令"])
    lines.extend(f"- `{item}`" for item in plan.get("commands") or [])
    lines.extend(["", "## 工作流契约"])
    lines.extend(f"- {item}" for item in plan.get("workflow_contract") or [])
    lines.extend(["", "## Timeout 单位契约"])
    lines.extend(f"- {item}" for item in plan.get("timeout_unit_contract") or [])
    lines.extend(["", "## 预期输出"])
    lines.extend(f"- {item}" for item in plan.get("expected_output") or [])
    if plan.get("boundaries"):
        lines.extend(["", "## 边界"])
        lines.extend(f"- {item}" for item in plan.get("boundaries") or [])
    return "\n".join(lines).rstrip()


def format_recipe_json(payload: dict[str, Any] | list[dict[str, Any]]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _commands_for_recipe(recipe: ResearchRecipe, query: str, *, profile: str, limit: int, read_top: int) -> list[str]:
    q = shlex.quote(query or "query")
    commands = [f"guanlan workflow {q} --json", f"guanlan route {q} --profile {profile} --limit {limit} --json"]
    if recipe.id == "finance-risk":
        commands.extend(
            [
                f"guanlan stock detail {q}",
                f"guanlan research {q} --preset finance --profile {profile} --limit {limit} --read-top {read_top} --advisor",
                f"guanlan search {q} --profile {profile} --scope finance_disclosure --limit {limit} --trace",
                f"guanlan search {q} --profile {profile} --scope finance_sentiment --limit {limit} --trace",
            ]
        )
    elif recipe.id == "university-advisor":
        commands.extend(
            [
                f"guanlan research {q} --preset university --profile {profile} --limit {limit} --read-top 0",
                f"guanlan search {q} --profile {profile} --scope university --limit {limit} --trace",
            ]
        )
    elif recipe.id == "entertainment-pulse":
        commands.extend(
            [
                f"guanlan research {q} --preset entertainment --profile {profile} --limit {limit} --read-top {read_top}",
                f"guanlan hotnews today --limit {limit} --trends",
                f"guanlan pulse {q} --format context",
            ]
        )
    elif recipe.id == "security-advisory":
        commands.extend(
            [
                f"guanlan research {q} --preset cybersecurity --profile {profile} --limit {limit} --read-top {max(read_top, 5)}",
                f"guanlan search {q} --scope cybersecurity --limit {limit} --trace",
            ]
        )
    elif recipe.id == "tech-radar":
        commands.extend(
            [
                f"guanlan research {q} --preset tech --profile {profile} --limit {limit} --read-top {read_top}",
                "guanlan feeds curated --limit 80",
            ]
        )
    elif recipe.id == "trajectory-map":
        commands.extend(
            [
                f"guanlan research {q} --profile {profile} --limit {limit} --read-top {read_top} --advisor",
                f"guanlan timeline {q} --limit {limit} --format context",
                f"guanlan dossier {q} --focus '定义 起源 演变 同类格局 口碑 风险 缺口' --limit {limit} --format context",
                f"guanlan compare {q} '主要同类对象' --focus '定位 技术路线 用户口碑 商业模式 风险' --limit {limit} --format context",
                f"guanlan sources explain {q}",
            ]
        )
    else:
        commands.extend(
            [
                f"guanlan research {q} --preset reputation --profile {profile} --limit {limit} --read-top {read_top} --advisor",
                f"guanlan search {q} --profile {profile} --scope social_web --limit {limit} --trace",
                f"guanlan dossier {q} --limit {limit} --format context",
            ]
        )
    commands.append(f"guanlan archive ingest-research {q} --limit {limit} --dry-run")
    return commands


def _default_read_top(recipe: ResearchRecipe, requested: int | None) -> int:
    if requested is not None:
        return max(int(requested), 0)
    if recipe.id in {"university-advisor", "academic-indexing"}:
        return 0
    if recipe.id in {"finance-risk", "security-advisory"}:
        return 5
    return 3


def _default_timeout_budget_seconds(recipe: ResearchRecipe) -> int:
    if recipe.id == "trajectory-map":
        return 300
    if recipe.id in {"finance-risk", "entertainment-pulse", "security-advisory", "tech-radar"}:
        return 240
    return 180


def _normalize_id(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
