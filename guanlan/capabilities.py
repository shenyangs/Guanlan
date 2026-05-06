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
        description="先判断问题更像政策、官方、口碑、产业、电商、技术、学术、财经还是热点，并给出优先信源、证据角色和建议执行命令。",
        when_to_use="搜索前不知道该查哪些来源/该跑哪个命令，或用户关心严谨性、信源分类、为什么这样搜。",
        cli=["guanlan route \"中文研究需求\"", "guanlan route \"OpenAI API pricing release notes\" --profile english --json"],
        mcp="guanlan_route",
        boundary="路由是软约束，建议命令是起手式，不把世界缩小成白名单；仍保留开放网页兜底。",
        examples=["这个问题该去哪搜？", "帮我区分官方、媒体和用户评价。"],
    ),
    Capability(
        id="workflow",
        name="轻重分流",
        description="判断一个任务应保持轻量 search/read，还是升级到 route/research/hotnews/feeds/compare/timeline/dossier/investigate。",
        when_to_use="Agent 不确定用户只是要基础搜索，还是需要严肃研究、对比、时间线、档案或高风险取证时。",
        cli=[
            "guanlan workflow \"观澜 官网\"",
            "guanlan workflow \"人工智能 监管 政策 最新通知\" --json",
            "guanlan investigate \"某公司 风险 舆情 档案\" --limit 80 --format context",
        ],
        mcp="guanlan_workflow / guanlan_investigate",
        boundary="轻任务不打扰，重任务不偷懒；workflow 是本地判断，不联网，不会让基础 search 自动变重。",
        examples=["这个问题要不要深查？", "先判断该 search 还是 research。"],
    ),
    Capability(
        id="page_diagnosis",
        name="页面诊断",
        description="判断一个 URL 是可读正文、动态页壳、访问门槛、搜索兜底还是弱正文，并给出下一步补证命令。",
        when_to_use="read 读到噪音、脚本壳、WAF、登录墙、搜索兜底，或 Agent 不知道该不该继续重试某页面时。",
        cli=[
            "guanlan diagnose page \"https://example.com/article\"",
            "guanlan diagnose page \"https://xueqiu.com/...\" --json",
        ],
        mcp="guanlan_page_diagnose",
        boundary="只诊断当前读取样本；默认不读取 Cookie 或登录态，不做点击、表单、交易等操作。",
        examples=["为什么这个页面读不到正文？", "雪球页面是不是 WAF 了？"],
    ),
    Capability(
        id="browser_assist",
        name="浏览器辅助补证",
        description="当公开读取不足时，生成用户授权的宿主浏览器可见页补证任务，并把补证材料按边界入库。",
        when_to_use="diagnose page 显示动态壳、登录墙、访问门槛、搜索兜底或弱正文，但该平台内容仍有样本价值时。",
        cli=[
            "guanlan browser-assist plan \"URL\" --json",
            "guanlan archive add-browser-note --from-json browser-notes.jsonl",
        ],
        mcp="guanlan_browser_assist_plan",
        boundary="只生成计划或归档用户授权的可见页笔记；不读取 Cookie、Token、钥匙串、私信、订单、后台，不执行写操作。",
        examples=["小红书页面公开读取不足，能不能让浏览器补一眼？", "把授权后的可见页笔记存入 archive。"],
    ),
    Capability(
        id="recipes",
        name="研究 Recipe",
        description="把高校导师、财经风险、产品口碑、文娱热度、安全公告、技术趋势等常见任务固化为可复用工作流模板。",
        when_to_use="Agent 容易误用单次泛搜，或用户希望按稳定流程完成一个垂直研究任务时。",
        cli=[
            "guanlan recipe list",
            "guanlan recipe run finance-risk \"宁德时代 股价 财报 公告 最近风险\"",
            "guanlan recipe run university-advisor \"南京师范大学中北学院 计算机 导师 招生\"",
        ],
        mcp="guanlan_recipe",
        boundary="recipe 输出的是执行计划和边界，不替代 search/read/research 主链路；执行前仍需按证据质量判断是否补证。",
        examples=["查股票风险该怎么跑？", "高校导师清单应该按什么流程搜？"],
    ),
    Capability(
        id="search",
        name="互联网搜索",
        description="多后端搜索、去重、信源分类、可信度评分、中文/英文 profile、scope/site 定向、Baidu 可用性诊断和 Agent 上下文输出。",
        when_to_use="用户说查一下、搜一下、找资料，或需要一批可筛选的网页证据。",
        cli=[
            "guanlan search \"关键词\" --limit 80",
            "guanlan search \"中文问题\" --profile china --limit 80",
            "guanlan search \"中文问题\" --profile china --limit 80 --trace",
            "guanlan search \"OpenAI API pricing\" --profile english --scope company_primary --limit 80",
            "guanlan search \"政策问题\" --profile china --scope party_central",
            "guanlan search \"EI会议 投稿 检索\" --profile china --scope academic",
            "guanlan search --list-scopes",
        ],
        mcp="guanlan_search",
        examples=["查一下低空经济最新政策。", "只搜知乎上关于这个产品的评价。"],
    ),
    Capability(
        id="sources",
        name="信源矩阵",
        description="只读查看 scope、domain、authority/sample/freshness、risk tags 和 evidence roles，用于解释来源身份和适用边界。",
        when_to_use="用户或 Agent 需要知道为什么优先某些来源、某域名能不能当主证据、某个 scope 下有哪些信源时。",
        cli=[
            "guanlan sources list --scope ecommerce",
            "guanlan sources show gov.cn",
            "guanlan sources explain \"新质生产力 政策\"",
        ],
        boundary="sources 是元数据解释层，不联网，不代表实际搜索结果；回答事实仍需 search/read/research。",
        examples=["为什么政策题优先 gov.cn？", "雪球能不能当财经主证据？"],
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
        description="把搜索、路由、代表证据、可选原文摘录、来源分布和证据审计整理成一份 Agent-ready evidence packet；科技类会强制补跑 RSS/精品内容流。",
        when_to_use="用户希望查清楚、给依据、整理资料、做研究，不只是要几个链接。",
        cli=[
            "guanlan research \"关键词\" --profile china",
            "guanlan research \"OpenAI API pricing release notes\" --preset company --profile english",
            "guanlan research \"政策问题\" --preset policy",
            "guanlan research \"Python Agent 框架 对比\" --preset tech",
            "guanlan research \"EI会议 投稿 检索 要求\" --preset academic --read-top 0",
            "guanlan research \"电影/综艺/游戏/明星 票房口碑\" --preset entertainment --read-top 0",
            "guanlan research \"产品 用户评价\" --preset reputation --read-top 0",
        ],
        mcp="guanlan_research",
        boundary="科技/AI/开发者路线会额外纳入 RSS discovery；RSS 是阅读发现和新鲜线索，不替代官方文档、代码仓库或原文核验。",
        examples=["帮我查清楚这个行业趋势。", "整理一下这个产品的公开口碑。"],
    ),
    Capability(
        id="entertainment",
        name="文娱路由",
        description="把中文文娱、欧美娱乐/音乐产业、日韩/K-pop/J-pop 分开路由，分别接入豆瓣/猫眼/B站/微博、Variety/Billboard/Deadline、Soompi/Oricon/Natalie/Naver 等来源。",
        when_to_use="用户问电影/剧集/综艺/明星/游戏怎么样、票房热度、豆瓣评分、Taylor Swift/K-pop/J-pop、粉圈争议、文娱舆情或内容消费建议时。",
        cli=[
            "guanlan route \"哪吒2 票房 口碑 豆瓣评分\" --json",
            "guanlan research \"哪吒2 票房 口碑 豆瓣评分\" --preset entertainment --limit 80 --read-top 0",
            "guanlan research \"Taylor Swift latest album tour\" --preset global_entertainment --profile english --limit 80",
            "guanlan research \"BLACKPINK K-pop comeback\" --preset jp_kr_entertainment --profile hybrid --limit 80",
            "guanlan search \"某电影 评分 票房\" --profile china --scope entertainment --limit 80",
            "guanlan search \"Taylor Swift latest\" --profile english --scope global_entertainment --limit 80",
            "guanlan search \"K-pop comeback\" --profile hybrid --scope jp_kr_entertainment --limit 80",
            "guanlan pulse \"某明星 争议 评价\" --profile china --limit 80 --format context",
            "guanlan hotnews weibo --limit 80",
            "guanlan hotnews bilibili --limit 80",
        ],
        mcp="guanlan_route / guanlan_research",
        boundary="文娱材料尤其容易受宣发、粉圈控评、平台算法、刷分、翻译搬运和八卦站影响；平台热度、榜单/奖项、评分、行业报道、经纪公司口径和公开讨论必须分层引用。",
        examples=["这部电影现在口碑怎么样？", "Taylor Swift 最近有什么可靠动态？", "BLACKPINK 回归消息哪些能确认？"],
    ),
    Capability(
        id="finance",
        name="财经路由",
        description="把财经查询拆成结构化行情、公告披露、公司一手、财经新闻、宏观数据、研报观点和投资者情绪，分别路由到对应信源。",
        when_to_use="用户问股票、股价、财报、公告、监管、宏观金融、基金/ETF、研报、雪球/股吧情绪、公司风险或资本市场动态时。",
        cli=[
            "guanlan route \"宁德时代 股价 财报 公告 最近风险\" --json",
            "guanlan stock quote \"宁德时代\"",
            "guanlan stock detail \"600519\"",
            "guanlan stock fundflow \"贵州茅台\"",
            "guanlan-stock rank --sort turnover --limit 20",
            "guanlan-stock index",
            "guanlan research \"宁德时代 股价 财报 公告 最近风险\" --preset finance --limit 80 --read-top 5 --advisor",
            "guanlan search \"贵州茅台 公告 财报\" --scope finance_disclosure --limit 80 --trace",
            "guanlan search \"上证指数 今日 行情\" --scope finance_quote --limit 80 --trace",
            "guanlan search \"社融 CPI 降息 央行\" --scope finance_macro --limit 80 --trace",
            "guanlan search \"某股票 雪球 股吧 情绪\" --scope finance_sentiment --limit 80 --trace",
            "guanlan search \"某行业 研报 评级 估值\" --scope finance_research --limit 80 --trace",
        ],
        mcp="guanlan_stock / guanlan_route / guanlan_search / guanlan_research / guanlan_read",
        boundary="财经输出只整理公开证据、时效和风险边界；结构化行情可能延迟，动态页可能只读到页面壳；研报和社交情绪不能写成买入、卖出或持有建议。",
        examples=["帮我查这家公司最近财报和风险。", "这只股票今天为什么大跌？", "雪球上大家怎么看？"],
    ),
    Capability(
        id="specialized_routes",
        name="垂直领域路由",
        description="为网络安全/CVE/反诈、天气灾害、体育、科学新闻、招聘薪资面经、播客和考试备考提供专门 scope 与证据分层。",
        when_to_use="用户问漏洞补丁、诈骗短信、台风路径、比赛伤病、科学发现、校招薪资、播客推荐、雅思题库等非通用网页搜索能可靠回答的问题。",
        cli=[
            "guanlan search \"OpenSSL CVE 最新 漏洞 影响版本\" --scope cybersecurity --limit 80 --trace",
            "guanlan search \"台风 路径 中央气象台 日本气象厅\" --scope weather_disaster --limit 80 --trace",
            "guanlan research \"梅西 比赛 伤病 最新\" --preset sports --limit 80",
            "guanlan research \"詹姆斯韦伯 外星生命 NASA\" --preset science --profile english --limit 80",
            "guanlan research \"字节 AI 产品经理 校招 薪资 面经\" --preset career --limit 80",
            "guanlan search \"AI 创业 播客 小宇宙\" --scope podcast --limit 80",
            "guanlan research \"雅思 口语 题库 机经\" --preset test_prep --limit 80",
        ],
        mcp="guanlan_route / guanlan_search / guanlan_research",
        boundary="高风险和强时效领域优先官方/机构/厂商来源；社交、论坛、粉丝或考生经验只作为样本线索。",
        examples=["OpenSSL 这个 CVE 影响哪些版本？", "台风现在路径怎样？", "雅思机经靠谱吗？"],
    ),
    Capability(
        id="evidence_audit",
        name="证据审计",
        description="在 research 证据包里标出版本号/叫法冲突、来源时间线和需要继续核验的结构化事实。",
        when_to_use="多篇材料对同一模型、价格、参数、发布时间等说法不一致，或用户需要交叉验证时。",
        cli=["guanlan research \"2026 April LLM release\" --profile english", "guanlan research \"模型 发布 价格 参数\" --format prompt"],
        mcp="guanlan_research",
        boundary="只提示冲突和核验路径，不直接裁定哪个说法一定正确。",
        examples=["这几篇文章版本号对不上，帮我标出来。", "按发布时间帮我核验这些模型发布说法。"],
    ),
    Capability(
        id="research_workflows",
        name="研究工作流",
        description="把 research 证据包进一步组织成对比、时间线和档案三种高阶研究产物。",
        when_to_use="用户问 compare/对比/竞品、事件脉络/时间线、某实体完整资料档案，而不是只要一份普通证据包。",
        cli=[
            "guanlan compare \"产品A\" \"产品B\" --focus \"价格 口碑\" --limit 80",
            "guanlan timeline \"某政策 最新进展\" --limit 80",
            "guanlan dossier \"某公司\" --focus \"业务 口碑 风险\" --limit 80",
        ],
        mcp="guanlan_compare / guanlan_timeline / guanlan_dossier",
        boundary="三类工作流都基于公开证据包做结构化整理，不裁定最终事实；关键判断仍需回到原文。",
        examples=["帮我对比这几个工具。", "按时间线梳理这件事。", "给我做一个公司档案。"],
    ),
    Capability(
        id="advisor",
        name="助理视角",
        description="基于检索材料生成谨慎的建议写作规则：可能意图、证据边界、下一步和风险提醒。",
        when_to_use="用户要建议、影响、下一步、风险，或想知道为什么会搜索这个内容。",
        cli=[
            "guanlan research \"query\" --profile china --advisor",
            "guanlan research \"query\" --profile english --advisor",
            "guanlan research \"产品 用户评价\" --preset reputation --read-top 0 --advisor",
        ],
        mcp="guanlan_research(advisor=true)",
        boundary="只能提出证据支持下的假设；不能断言用户真实意图，不能替代法律、医疗、金融等专业判断。",
        examples=["查完后给我建议。", "你猜我搜这个可能是为了什么？"],
    ),
    Capability(
        id="hotnews",
        name="热榜观察",
        description="抓取中文热榜、社区热帖和可选 NewsNow/VVHan/UAPI/TopHub 源，支持跨源趋势归并和简报。",
        when_to_use="用户问今天热点、某个平台在讨论什么、中文互联网当日水势。",
        cli=[
            "guanlan hotnews today --limit 80",
            "guanlan hotnews weibo --limit 80",
            "guanlan hotnews bilibili --limit 80",
            "guanlan hotnews ithome --limit 80",
            "guanlan hotnews v2ex --limit 80",
            "guanlan hotnews tophub:weibo --limit 80",
            "guanlan hotnews uapis:catalog --limit 80",
            "guanlan hotnews vvhan:all --limit 80",
            "guanlan hotnews today --trends --brief",
            "guanlan hotnews list",
        ],
        mcp="guanlan_hotnews",
        boundary="热榜代表平台公开榜单，不代表全网民意；外部聚合源会标注 external_backend，并可能返回缓存或过期快照。",
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
        id="feeds",
        name="精品内容发现",
        description="读取公开 RSS/Atom、动态热点 RSS 和精品源目录，发现高质量技术、AI、产品、商业科技与微信热门文章线索。",
        when_to_use="用户想看值得读的技术文章、AI 高分内容、公众号热文、实时热点 RSS，或需要 RSS 内容池/源目录。",
        cli=[
            "guanlan feeds curated --limit 80",
            "guanlan feeds curated --category ai --min-score 85 --limit 80",
            "guanlan feeds baidu-rss --limit 80",
            "guanlan feeds wechat-rss --limit 80",
            "guanlan feeds curated-sources --keyword AI --limit 80",
            "guanlan feeds list",
        ],
        mcp="guanlan_feeds",
        boundary="只读公开 RSS/OPML；动态源适合线索发现，不等同于事实核验或全网热度结论。",
        examples=["今天有哪些值得读的技术文章？", "公众号最近有什么热文？", "有哪些 AI 精品源？"],
    ),
    Capability(
        id="archive",
        name="本地知识库",
        description="把网页或研究结果保存成本地 Markdown 档案，并支持本地检索、体检、Wiki、Prompt context 和 RAG 导出。",
        when_to_use="用户希望沉淀资料、复用已读材料，或给本地 RAG/长期项目准备语料。",
        cli=[
            "guanlan archive add \"URL\"",
            "guanlan archive ingest-research \"关键词\" --limit 80",
            "guanlan archive search \"关键词\" --format context --trace",
            "guanlan archive verify",
            "guanlan archive inspect 1",
            "guanlan archive reindex",
            "guanlan archive export --format rag-jsonl",
            "guanlan archive export --format llamaindex-jsonl",
            "guanlan archive context \"问题\"",
        ],
        mcp="guanlan_archive_search",
        boundary="默认保存在本机；不上传档案内容。ingest-research 是联网研究并入库，archive search 才是本地库检索。",
        examples=["把这批资料存起来。", "在我之前归档里搜一下。"],
    ),
    Capability(
        id="agent_wiki",
        name="AI Agent Wiki",
        description="把本地 archive 组织成静态 Markdown/HTML Wiki，或按问题输出给 Agent/本地模型的证据上下文。",
        when_to_use="用户想把一次性调研沉淀成长期知识底座，或要把本地资料接到 Wiki、RAG、LM Studio/Ollama。",
        cli=[
            "guanlan archive wiki build --output ./guanlan-wiki",
            "guanlan archive wiki build --format both --topic \"AI Agent\"",
            "guanlan archive wiki context \"KV Cache 量化\"",
            "guanlan archive pack \"主题\" --format langchain-jsonl --output pack.jsonl",
        ],
        mcp=None,
        status="sidecar",
        boundary="Wiki 只反映本地 archive 中已有资料，不代表全网知识；低质量材料会标为 candidate，需要回原文核验。",
        examples=["把查过的资料整理成 Agent Wiki。", "把这个主题打包给本地模型。"],
    ),
    Capability(
        id="report",
        name="旁支 HTML 报表",
        description="把已有 JSON、stdin 或内置样例渲染成深色、高信息密度、可直接打开的静态 HTML 报表。",
        when_to_use="用户明确要报表、汇报页、可视化 HTML，或需要把 Guanlan 结果包装成可分享页面时。",
        cli=[
            "guanlan report html --input results.json --output report.html",
            "guanlan search \"问题\" --json | guanlan report html --input - --output search-report.html",
            "guanlan report html --output demo-report.html",
        ],
        mcp=None,
        status="sidecar",
        boundary="旁支展示层：只读取已有 JSON/样例数据，不触发搜索、阅读、归档或网络请求；不替代原始证据。",
        examples=["把这次测试结果出成一个高级 HTML 报表。", "给我一个能发给朋友看的可视化报告。"],
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
        "- 不知道去哪搜/该跑哪个命令：`guanlan route \"问题\"`",
        "- 不确定该轻搜还是深查：`guanlan workflow \"问题\"`",
        "- 页面读不出来：`guanlan diagnose page \"URL\"`",
        "- 要稳定研究模板：`guanlan recipe list` / `guanlan recipe run finance-risk \"问题\"`",
        "- 只要搜索结果：`guanlan search \"问题\" --limit 80`",
        "- 要证据包：`guanlan research \"问题\" --profile china` 或 `guanlan research \"question\" --profile english`",
        "- 要显式深查：`guanlan investigate \"问题\" --limit 80 --format context`",
        "- 要解释信源身份：`guanlan sources explain \"问题\"`",
        "- 要跑公开基准：`guanlan eval suite run chinese-web-v1`",
        "- 要对比/时间线/档案：`guanlan compare ...`、`guanlan timeline \"问题\"`、`guanlan dossier \"对象\"`",
        "- 要建议/下一步：`guanlan research \"问题\" --advisor`",
        "- 查过资料不要丢：`guanlan archive ingest-research \"问题\" --limit 80`，之后用 `archive verify/context/wiki/pack` 复用",
        "- 要本地模型/RAG/Wiki 上下文：`guanlan archive context \"问题\"` 或 `guanlan archive wiki context \"问题\"`",
        "- 要静态 HTML 报表：`guanlan report html --input results.json --output report.html`",
        "- 看今日热点：`guanlan hotnews today --limit 80`",
        "- 查可用状态：`guanlan status`",
        "",
        "## Agent 超时预算",
        "",
        "- 外层工具 timeout 建议：`search/read/status/doctor` 60-90 秒；`hotnews/feeds/pulse/read batch` 120 秒；`research/compare/timeline/dossier/archive ingest-research` 180-300 秒；安装/升级/发布 smoke 300-600 秒。",
        "- 单位按宿主字段名换算：`timeout_budget_seconds` 传秒；`timeout_ms` / `timeout_milliseconds` 传毫秒，例如 120 秒 = 120000 ms、300 秒 = 300000 ms；不要把 `timeout=120` 这种裸数字交给下游。",
        "- 网络超时只能说明本轮网络或上游源未完成，不代表没有证据；优先重试一次、使用 `--cache-ttl 3600`，或降低 `--read-top`，不要把正常 80 条候选池砍成小样本。",
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
    lines.append(
        "Agent 规则：如果用户问“你能做什么/观澜有哪些功能/该怎么查”，先调用 capabilities；"
        "如果用户给出具体问题但信源不清，先 route，再 search/research；"
        "如果用户说“查过资料别丢/长期记忆/Wiki/RAG/本地模型上下文”，优先使用 archive verify/context/wiki/pack，"
        "并说明它只基于本地 archive，不代表全网知识。"
    )
    return "\n".join(lines).rstrip()


def format_capabilities_json() -> str:
    """Return pretty JSON for the CLI."""
    return json.dumps(list_capabilities(), ensure_ascii=False, indent=2)
