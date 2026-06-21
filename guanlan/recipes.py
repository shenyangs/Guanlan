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
from guanlan.wps_semantics import is_wps_office_semantic_query


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
    read_contract: list[str] = field(default_factory=list)
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
        id="public-opinion-pulse",
        name="公开舆情/风评回响",
        description="把社交平台公开讨论、评论样本、媒体报道和时间窗分层，形成谨慎的舆情回响。",
        when_to_use="用户问某产品/品牌/事件现在风评如何、被夸还是被骂、社媒在讨论什么、声量和争议点时。",
        preset="public_opinion",
        scopes=["social_web", "market_review", "business"],
        evidence_layers=["公开讨论样本", "评论/评分样本", "媒体报道", "平台热度", "时间窗与样本偏差"],
        boundaries=["公开样本不是民调，也不是全网总体比例。", "输出必须说明平台、时间窗、样本偏差和未覆盖来源。"],
    ),
    ResearchRecipe(
        id="brand-risk-watch",
        name="品牌负面/危机观察",
        description="把投诉、负面扩散、媒体报道、官方/公司回应和待核验事实分层。",
        when_to_use="用户问某品牌/公司是否出现负面、危机、公关风险、投诉爆发、抵制、召回、道歉或澄清时。",
        preset="crisis",
        scopes=["social_web", "business", "market_review", "gov"],
        evidence_layers=["负面信号", "投诉样本", "媒体报道", "官方/公司回应", "扩散平台与时间线", "待核验事实"],
        boundaries=["不要把单条投诉或爆款帖写成危机定论。", "危机判断必须保留已证实事实、未证实传言和公司回应边界。"],
    ),
    ResearchRecipe(
        id="competitor-watch",
        name="竞品情报/同类监测",
        description="把同类对象、官网/价格页、功能更新、评价样本、行业报道和格局判断组织成可复用证据链。",
        when_to_use="用户问竞品、竞争对手、同类产品、市场格局、功能对比、定价变化或竞品长期监测时。",
        preset="competitor",
        scopes=["company_primary", "business", "market_review", "social_web"],
        evidence_layers=["对象边界", "同类/竞品清单", "公司一手资料", "价格/功能更新", "评价样本", "行业报道", "待追踪变更"],
        boundaries=["先确认对象边界和同类标准，不凭印象生成竞品清单。", "评价站、社区和榜单只能作样本或线索，不能当市场份额。"],
    ),
    ResearchRecipe(
        id="pricing-watch",
        name="价格/套餐变化观察",
        description="优先核验官方价格页、帮助中心、发布说明和历史快照，再补用户反应与媒体报道。",
        when_to_use="用户问某产品是否涨价/降价、套餐是否变化、订阅价格、付费墙或价格对比时。",
        preset="pricing_watch",
        scopes=["company_primary", "market_review", "business"],
        evidence_layers=["官方价格页", "帮助中心/条款", "发布说明", "历史快照", "用户反应", "媒体报道"],
        boundaries=["价格必须标注地区、币种、时间和套餐边界。", "过期缓存或社区转述不能替代官方价格页。"],
    ),
    ResearchRecipe(
        id="review-mining",
        name="评论样本/用户语言挖掘",
        description="把用户评论拆成痛点、好评、差评、功能诉求、版本/地区边界和代表原话。",
        when_to_use="用户问评论分析、差评原因、用户反馈、评分下降、功能诉求或想从评论里提炼用户语言时。",
        preset="review_intel",
        scopes=["market_review", "social_web", "business"],
        evidence_layers=["评分/评论样本", "差评主题", "好评主题", "功能诉求", "版本/地区边界", "代表用户语言"],
        boundaries=["评论样本不是总体比例；不要把刷评、营销样本或单平台评论写成总体结论。", "引用用户原话时要短摘录、保留来源和时间。"],
    ),
    ResearchRecipe(
        id="app-review-pulse",
        name="应用商店评论/评分观察",
        description="围绕 App Store、Google Play 与公开应用市场信号，观察评分、版本反馈、差评主题和用户语言。",
        when_to_use="用户问某 App 的商店评论、评分变化、ASO、版本反馈、差评主题或应用市场口碑时。",
        preset="app_review",
        scopes=["market_review", "company_primary", "social_web"],
        evidence_layers=["应用商店评分", "版本评论", "地区边界", "差评主题", "好评主题", "公开市场信号"],
        boundaries=["应用商店数据要标注地区、版本、采样时间和平台。", "第三方榜单或下载估计不能当官方经营数据。"],
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
        id="wps-office-radar",
        name="WPS/AI Office 选题雷达",
        description="以金山办公/WPS 为锚点，外扩 WPS AI、WPS 灵犀/Claw、AI PPT/HTML素材、WPS笔记、AI 知识库/KaaS、WPS for Pad/鸿蒙、Agent/skill/MCP、AI 泛办公和竞品热点。",
        when_to_use="用户问金山办公、WPS、WPS AI、WPS 灵犀、灵犀 Claw、WPS 365、AI Office、办公 Agent、AI PPT、HTML素材、WPS笔记、AI 知识库、WPS for Pad、鸿蒙办公、文档协作、信创办公或办公安全选题时。",
        preset="wps_office",
        scopes=["wps_office", "business", "tech_dev", "social_web", "cybersecurity"],
        evidence_layers=[
            "风险预警：会员/积分/隐私/数据安全/幻觉/格式错乱/产品混淆",
            "灵犀/Claw：办公智能体、数字员工、MCP/skill、工具调用、执行型 AI、AI 工时/定价",
            "WPS AI：AI 写作/伴写2.0、AI 阅读/PDF问答、AI 数据/写公式/条件格式、AI 设计、AI PPT/HTML素材、移动办公",
            "灵犀使用场景：AI创作、AI搜索/深度搜索/信息溯源、AI阅读/多文件解读、数据分析、划词工具栏、截图问答、微信小程序、语音文档对话",
            "泛办公机会：AI 笔记/WPS笔记/龙虾直写、AI 知识库、OCR/文档解析/MonkeyOCR、KaaS/知识广场、WPS for Pad/iPadOS、鸿蒙/小艺/分布式协同、WPS云文档政务民生案例",
            "WPS 365/企业大脑：AI Docs、AI Hub、Copilot Pro、智能搜索、团队考试/知识自测/知识检测、数字资产保护与合规管理",
            "GEO/AI 问答认知：WPS 与 WPS AI 分开诊断，覆盖 Office 替代、国产办公软件、AI 写文档、AI 做 PPT、AI 总结 PDF、办公智能体等真实问法",
            "C 端传播输出：心智建立、重点战役、社区机会、风险告警四层分开写",
            "竞品/行业动态：Copilot、Google Workspace、飞书/钉钉/WorkBuddy、AI PPT 工具",
            "AI/科技媒体和 RSS：curated、ai-vertical、wechat-rss 作为发现层，不替代原文",
            "高质量 AI/大佬内容：仅作趋势和选题线索，关键事实回读原文或官方资料",
            "用户/社区样本：知乎、小红书、微博、B站、V2EX、WPS 社区等公开语言和情绪样本",
        ],
        boundaries=[
            "不要把任务缩成品牌稿检索；垂直赛道、竞品线索、Agent/AI Office 趋势同样重要。",
            "社区、热榜和大佬内容只作选题/情绪/趋势样本，关键事实必须回到 WPS 官方、竞品官方、行业媒体或原文。",
            "显性 WPS/灵犀事实优先官方和行业源；Agent、MCP、skill、AI 大佬内容不能替代 WPS 产品事实。",
            "GEO 诊断中 WPS 办公软件品牌和 WPS AI 智能办公能力品牌要分开评估，避免把普通办公软件认知与 AI 办公能力认知混在一起。",
        ],
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
    if "wps_office" in intents or is_wps_office_semantic_query(query) or any(
        term in text
        for term in (
            "金山办公",
            "金山文档",
            "wps",
            "wps ai",
            "wps365",
            "wps 365",
            "wps灵犀",
            "灵犀 claw",
            "ai office",
            "office ai",
            "办公ai",
            "ai办公",
            "ai ppt",
            "ai笔记",
            "ai 知识库",
            "ppt生成",
            "协同办公",
            "信创办公",
        )
    ):
        return get_recipe("wps-office-radar")
    if "cybersecurity" in intents or any(term in text for term in ("cve", "漏洞", "诈骗", "钓鱼")):
        return get_recipe("security-advisory")
    if {"crisis_watch"} & intents or any(term in text for term in ("公关危机", "负面舆情", "投诉爆发", "抵制", "召回", "道歉", "澄清", "pr crisis", "backlash")):
        return get_recipe("brand-risk-watch")
    if {"app_review"} & intents or any(term in text for term in ("app store 评论", "应用商店评论", "google play 评论", "应用评分", "aso")):
        return get_recipe("app-review-pulse")
    if {"review_intel"} & intents or any(term in text for term in ("评论分析", "评论挖掘", "用户评论", "差评", "好评", "评分下降")):
        return get_recipe("review-mining")
    if {"public_opinion"} & intents or any(term in text for term in ("舆情", "风评", "声量", "社媒", "被骂", "被夸", "social sentiment")):
        return get_recipe("public-opinion-pulse")
    if {"pricing_watch"} & intents or any(term in text for term in ("定价变化", "价格变化", "价格调整", "涨价", "降价", "套餐变化", "pricing change")):
        return get_recipe("pricing-watch")
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
    if {"competitor_watch"} & intents or any(term in text for term in ("竞品情报", "竞品监控", "竞争对手", "竞对", "同类产品")):
        return get_recipe("competitor-watch")
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
        read_contract=_read_contract_for_recipe(recipe, effective_read_top),
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
    if plan.get("read_contract"):
        lines.extend(["", "## 代表页读取契约"])
        lines.extend(f"- {item}" for item in plan.get("read_contract") or [])
    lines.extend(["", "## 预期输出"])
    lines.extend(f"- {item}" for item in plan.get("expected_output") or [])
    if plan.get("boundaries"):
        lines.extend(["", "## 边界"])
        lines.extend(f"- {item}" for item in plan.get("boundaries") or [])
    return "\n".join(lines).rstrip()


def format_recipe_json(payload: dict[str, Any] | list[dict[str, Any]]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _read_contract_for_recipe(recipe: ResearchRecipe, read_top: int) -> list[str]:
    contract = [
        "搜索、route、feeds、hotnews 产出的是 URL/信号入口；只有 read/read_pack 中 usable=true 的正文可作为事实证据。",
        "未读 URL、弱正文、下载站/镜像站/SEO 聚合只能进入线索池，不能撑主结论。",
    ]
    if read_top <= 0:
        contract.append("当前 read_top=0：本 recipe 默认只给入口和证据角色，引用事实前需补 `guanlan read URL --quality-report`。")
    else:
        contract.append(f"当前 read_top={read_top}：优先读取官方/垂直/高质量代表页，保留 weak/error 页面边界。")
    if recipe.id in {"pricing-watch", "competitor-watch", "wps-office-radar", "trajectory-map"}:
        contract.append("若任务给出明确官网或产品站点，先用 `guanlan map SITE --query ... --read-top 2` 找代表页，再补全网来源。")
    return contract


def _commands_for_recipe(recipe: ResearchRecipe, query: str, *, profile: str, limit: int, read_top: int) -> list[str]:
    q = shlex.quote(query or "query")
    commands = [f"guanlan workflow {q} --json", f"guanlan route {q} --profile {profile} --limit {limit} --json"]
    if recipe.id == "finance-risk":
        commands.extend(
            [
                f"guanlan stock plan {q}",
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
    elif recipe.id == "public-opinion-pulse":
        commands.extend(
            [
                f"guanlan pulse {q} --profile {profile} --limit {limit} --format context",
                f"guanlan research {q} --preset public_opinion --profile {profile} --limit {limit} --read-top {read_top} --advisor",
                f"guanlan search {q} --profile {profile} --scope social_web --limit {limit} --trace",
                f"guanlan search {q} --profile {profile} --scope market_review --limit {limit} --trace",
                f"guanlan hotnews today --limit {limit} --trends",
            ]
        )
    elif recipe.id == "brand-risk-watch":
        commands.extend(
            [
                f"guanlan hotnews today --limit {limit} --trends",
                f"guanlan pulse {q} --profile {profile} --limit {limit} --format context",
                f"guanlan research {q} --preset crisis --profile {profile} --limit {limit} --read-top {max(read_top, 5)} --advisor",
                f"guanlan search {q} --profile {profile} --scope social_web --limit {limit} --trace",
                f"guanlan timeline {q} --limit {limit} --format context",
            ]
        )
    elif recipe.id == "competitor-watch":
        commands.extend(
            [
                f"guanlan research {q} --preset competitor --profile {profile} --limit {limit} --read-top {max(read_top, 5)} --advisor",
                f"guanlan dossier {q} --focus '定位 竞品 功能 定价 口碑 风险 待追踪' --limit {limit} --format context",
                f"guanlan search {q} --profile {profile} --scope company_primary --limit {limit} --trace",
                f"guanlan search {q} --profile {profile} --scope market_review --limit {limit} --trace",
                f"guanlan compare {q} '主要同类对象' --focus '定位 功能 定价 用户反馈 渠道 风险' --limit {limit} --format context",
            ]
        )
    elif recipe.id == "pricing-watch":
        commands.extend(
            [
                f"guanlan research {q} --preset pricing_watch --profile {profile} --limit {limit} --read-top {max(read_top, 5)}",
                f"guanlan search {q} --profile {profile} --scope company_primary --limit {limit} --trace",
                f"guanlan search {q} --profile {profile} --scope market_review --limit {limit} --trace",
                f"guanlan timeline {q} --limit {limit} --format context",
            ]
        )
    elif recipe.id == "review-mining":
        commands.extend(
            [
                f"guanlan research {q} --preset review_intel --profile {profile} --limit {limit} --read-top {read_top} --advisor",
                f"guanlan search {q} --profile {profile} --scope market_review --limit {limit} --trace",
                f"guanlan pulse {q} --profile {profile} --limit {limit} --format context",
            ]
        )
    elif recipe.id == "app-review-pulse":
        commands.extend(
            [
                f"guanlan research {q} --preset app_review --profile {profile} --limit {limit} --read-top {read_top} --advisor",
                f"guanlan search {q} --profile {profile} --scope market_review --limit {limit} --trace",
                f"guanlan search {q} --site apps.apple.com --profile {profile} --limit {limit}",
                f"guanlan search {q} --site play.google.com --profile {profile} --limit {limit}",
                f"guanlan pulse {q} --profile {profile} --limit {limit} --format context",
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
    elif recipe.id == "wps-office-radar":
        commands.extend(
            [
                f"guanlan research {q} --preset wps_office --profile {profile} --limit {limit} --read-top {max(read_top, 5)} --advisor",
                f"guanlan search {q} --profile {profile} --scope wps_office --limit {limit} --trace",
                "guanlan feeds curated --category ai --limit 80",
                "guanlan feeds wechat-rss --limit 80",
                "guanlan hotnews today --limit 80 --trends",
                f"guanlan pulse {q} --profile {profile} --limit {limit} --format context",
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
    if recipe.id in {"finance-risk", "security-advisory", "wps-office-radar", "brand-risk-watch", "competitor-watch", "pricing-watch"}:
        return 5
    return 3


def _default_timeout_budget_seconds(recipe: ResearchRecipe) -> int:
    if recipe.id == "trajectory-map":
        return 300
    if recipe.id in {"finance-risk", "entertainment-pulse", "security-advisory", "tech-radar", "wps-office-radar", "public-opinion-pulse", "brand-risk-watch", "competitor-watch", "pricing-watch", "review-mining", "app-review-pulse"}:
        return 240
    return 180


def _normalize_id(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
