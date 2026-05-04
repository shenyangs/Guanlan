# 观澜 Agent 使用说明

本文档写给 AI Agent，不是写给人类用户。你的目标是把观澜当作搜索生产力工具：先找到可信来源，再读取原文，最后把结论和来源一起交付给用户。

开始前先记住两份长期记忆文档：[docs/agent-playbook.md](agent-playbook.md) 和 [AGENTS.md](../AGENTS.md)。前者管工作流和 benchmark 纪律，后者管仓库级强规则。

## 核心定位

观澜优先服务这些任务：

- 搜索网页资料。
- 阅读网页、文章、文档和公开页面。
- 观察中文热榜和社区趋势。
- 搜索或读取社交平台内容。
- 在需要 Cookie、登录态或钥匙串时停下来请求用户授权。

默认原则：

- 用户或 Agent 不知道观澜有哪些能力时，先运行 `guanlan capabilities`；MCP 模式下调用 `guanlan_capabilities`。
- 新用户问“装好了怎么用”时，先运行 `guanlan welcome`，再按用户目标选择具体能力。
- 先读公开信息，不主动读取浏览器 Cookie。
- 先搜索和阅读，不自动发布、评论、点赞、私信。
- 输出结论时保留来源链接。
- 失败时降级，不要硬撞平台风控。
- 默认候选池按研究任务放大：搜索/研究/归档检索默认 80 条，热榜默认 80 条，读取失败后的搜索兜底默认 20 条。
- Agent 调用时应尽量多取结果再筛选：普通任务保持 80，复杂研究可设到 80-100；只有用户明确要求“小样本/快速看一下”时才降低 limit。
- 当 `--limit` 小于 30 时，把它当 smoke sample：可以先返回线索，但要提醒后续 Agent/用户补跑 `--limit 80`，不要用 5-10 条结果直接写强结论。
- Agent 平台外层 timeout 要宽松：不要用 10-30 秒去包住 `research`、`feeds` 或 `hotnews` 这种组合命令；超时只能说明网络/上游抖动，不代表没有证据。
- 用户需要建议、影响判断、下一步行动，或询问“为什么会搜这个”时，优先使用 `research --advisor`，但把助理视角当作证据边界和写作规则，由你结合用户问题生成自然建议；不要机械复述模板，也不要当作用户真实意图。
- 不确定该查哪些信源时，先用 `guanlan route "关键词"` 看需求路由；路由计划是软约束，优先源用于提高适配度，开放网页兜底用于防止信源池过窄。
- 页面读不出来时，先用 `guanlan diagnose page "URL"` 判断是可读正文、动态页壳、访问门槛、搜索兜底还是弱正文；不要把搜索兜底当原文，也不要反复重试登录/WAF 页面。
- 如果 `diagnose page` 输出 `browser_assist.recommended=true`，先请求用户授权，再使用宿主浏览器打开目标 URL 并只读取目标页面的浏览器可见内容作为补证；如需登录、验证或切换账号，让用户自己在浏览器里完成；本次可见页补证不要读取 Cookie、Token、钥匙串、私信、订单、后台或无关个人资料；如果仍需 Cookie，必须另行说明平台、用途和风险并获得用户明确同意，也不要执行任何写操作。授权后的可见页结果优先由宿主 Agent 直接提取 JSON/JSONL，并用 `guanlan archive add-browser-note --from-json browser-notes.jsonl` 入库；`--url "URL" --text-file notes.md` 只是无浏览器提取能力时的手动兜底，并保留 `browser_assisted` / `visible_page_only` 边界。
- 高频垂直任务用 `guanlan recipe list` / `guanlan recipe run <recipe> "问题"` 固化流程，例如 `finance-risk`、`university-advisor`、`product-reputation`、`entertainment-pulse`、`security-advisory`、`tech-radar`。

## 信源矩阵与公开基准

- 解释“为什么这些来源适合”时，用 `guanlan sources explain "关键词"`。
- 查某个来源身份时，用 `guanlan sources show gov.cn` 或 `guanlan sources list --scope finance_disclosure`。
- 做离线评测时，用 `guanlan eval suite run chinese-web-v1`；它是 100 题 deterministic suite，不联网，不把网络波动当失败。
- 做真实任务样本复测时，用 `guanlan eval suite run chinese-web-live --mode live`；报告会区分路由、候选池、RSS/热榜调用、时间窗口和网络/上游问题。
- 治理信源口径时，用 `guanlan sources audit`；它只做本地元数据体检，不联网、不自动改写。
- 给本地模型/RAG 做长期记忆时，先用 `archive verify`，再显式 `guanlan archive embed --backend local`；语义侧车不替代 FTS。

## 轻重分流

- 不确定该轻搜还是深查时，先跑 `guanlan workflow "关键词" --json`。它只做本地判断，不联网，不会改变基础搜索行为。
- `direct`：简单官网、链接、事实入口和轻量资料，直接 `search -> read optional`，不要过度规划。
- `guided`：政策、财经、安全、技术、热点、口碑等需要信源分层的问题，走 `route -> research -> scoped search`，科技题补 RSS，热点题补 hotnews。
- `investigate`：用户明确要深度研究、对比、时间线、档案、高影响核验或可复用证据包时，使用 `guanlan investigate "关键词" --limit 80 --format context`；不确定开销时先 `--dry-run`。
- 明确命中专门分类时，直接走对应 `--preset` 或 `--scope`，不要先泛搜一轮。欧美娱乐、日韩娱乐、CVE/反诈、天气灾害、体育、财经/股票/宏观金融、科学新闻、职场薪资面经、播客、考试备考、高校招生导师、学术投稿检索、产品/公司口碑都属于强路由。
- 重复出现的垂直研究模式先用 `recipe run` 输出计划，再执行对应 `search/read/research/stock/archive`，避免 Agent 临场拼错路由。
- `research` 会附带证据审计提示：如果同一模型、版本号、价格、参数量或发布时间出现不同说法，先把冲突和来源日期讲清楚，再给取舍依据；不要把观澜的冲突提示当成最终裁决。

## 动态工作流档位

不要把 Guanlan 理解成“一次 `search` 就结束”。默认按场景走这三档：

- `2-step`：`search -> read`。适合结果已经明显可用，只需要核代表原文。
- `3-step`：`route -> research -> scoped search`。适合普通研究题，或质量画像未过。
- `4-step`：在 `3-step` 基础上，热点/时效题补 `hotnews`，技术/AI 题补 `feeds`，证据面过窄时补 `dossier`、`compare` 或 `timeline`。

只有完成当前档位要求的 Guanlan 工具后，仍缺关键证据，才切到通用 `web_search` / `web_fetch`。
如果 trace 或 context 中出现 `external_fetch_strategy`，可以临时调用宿主平台的 WebFetch/WebRead 读取 Guanlan 推荐 URL。外显时要说清楚：这是 Guanlan 主动规划的“定点补证”策略，不是 Guanlan 搜索失败。

如果 trace 中出现 `quality_gate.reason=partial_salvage`，说明 Guanlan 已从低覆盖批次里保留强官方/垂直信源线索；它可作为继续读取和核验的入口，不应汇报成失败。如果 `read` 输出 `兜底状态: unusable`，说明搜索兜底无法确认同一页面，不能引用兜底内容，应改用 `diagnose page`、结构化入口、scope 搜索或 WebFetch 定点补证。

对于体育比分/赛程、财经行情/公告披露/宏观数据、天气灾害、CVE/安全公告、科学机构声明、文娱榜单/票房、考试官方信息这类高确定性垂直题，先看 `guanlan route` 给出的 direct `guanlan read` 命令。这些是权威入口候选，应该先读取核验，再用 `research/search` 扩大信源面。

## Benchmark 纪律

如果是在评测 Guanlan，不要用不符合最佳使用方式的打法：

- 不要只跑一次 `search` 就定性 Guanlan 的最终能力。
- 不要把 `quality_summary=warn` 直接写成 “Guanlan 搜索失败”。
- 实时/热点题必须补 `hotnews`。
- 实时体育、灾害预警、安全漏洞等垂直题必须读取 Guanlan 推荐的 direct source seeds。
- 技术/AI 题必须补 `feeds` 或直接走 `research --preset tech`。
- 政策/办事题优先 `search + read` 或 `research`，不要只测单次泛搜。

## Agent 外层超时建议

观澜内部会给单个网页、RSS、热榜源设置较短的请求超时，避免一个源站无限卡住。但 Agent/MCP/自动化平台包住整个命令时，需要给组合流程更大的外层预算。建议值：

| 场景 | 建议外层 timeout |
| --- | --- |
| `guanlan status`、`doctor`、`search`、单 URL `read` | 60-90 秒 |
| `hotnews`、`feeds`、`pulse`、`read batch`、默认 `archive ingest-research` | 120 秒 |
| `research`、`compare`、`timeline`、`dossier`、`archive ingest-research --read-top N` | 180-300 秒 |
| 安装、升级、发布 smoke、Homebrew/PyPI 校验 | 300-600 秒 |

如果发生超时：

- 先重试一次；对 `search`、`read`、`pulse` 可加 `--cache-ttl 3600` 降低重复请求扰动。
- 对 `research` 优先降低 `--read-top` 到 0 或 1，而不是把 `--limit` 从 50 砍到很小。
- 对 `feeds` 看到 `feed_status=stale_cache` 时，要说明这是最近成功缓存，不是实时榜单。
- 不要把 timeout 写成“没有结果”或“没有证据”；只能写成“本轮网络/上游未能完成，需要稍后重试或换后端”。

## 最小命令集

| 用户意图 | 首选命令 |
| --- | --- |
| “刚装好，怎么用/怎么让 Agent 用” | `guanlan welcome` |
| “观澜能做什么/我该用哪个能力” | `guanlan capabilities` |
| “查一下/搜一下” | `guanlan search "关键词" --limit 80` |
| “查中文互联网/国内资料” | `guanlan search "关键词" --profile china --limit 80` |
| “查英文互联网/全球资料” | `guanlan search "query" --profile english --limit 80` |
| “查近期/最近/热点/最新进展” | `guanlan search "最近 关键词 热点" --profile china --trace` |
| “只搜某个网站” | `guanlan search "关键词" --site zhihu.com --limit 80` |
| “搜微信公众号文章” | `guanlan search "关键词" --site mp.weixin.qq.com --profile china --limit 80`，结果按 best-effort 处理 |
| “查官方/央媒表述” | `guanlan search "关键词" --profile china --scope party_central` |
| “查地方官媒/区域政策” | `guanlan search "关键词" --profile china --scope local_official` |
| “查电商/零售/产业带” | `guanlan search "关键词" --profile china --scope ecommerce` |
| “查高校招生/导师/院系官网” | `guanlan research "关键词" --preset university --read-top 0` |
| “查影视/综艺/明星/游戏/票房口碑” | `guanlan research "关键词" --preset entertainment --read-top 0` |
| “查股票/公司财报公告/风险” | 先 `guanlan stock detail "宁德时代"`，再 `guanlan research "宁德时代 股价 财报 公告 最近风险" --preset finance --read-top 5 --advisor` |
| “查行情/指数/股价” | `guanlan stock quote "上证指数"` 或 `guanlan stock quote "600519"`，再按需 `guanlan search "上证指数 今日 行情" --scope finance_quote --limit 80 --trace` |
| “查资金流向/榜单/大盘概览” | `guanlan stock fundflow "600519"`、`guanlan-stock rank --sort turnover --limit 20`、`guanlan-stock index` |
| “页面读出来像脚本/登录墙/兜底” | `guanlan diagnose page "URL"` |
| “需要生成浏览器可见页补证任务” | `guanlan browser-assist plan "URL" --json` |
| “用户授权后把浏览器可见页补证入库” | `guanlan archive add-browser-note --from-json browser-notes.jsonl` |
| “按固定流程查高校/财经/口碑/安全/技术” | `guanlan recipe list`，再 `guanlan recipe run finance-risk "问题"` |
| “查公告/财报/监管/问询函” | `guanlan search "贵州茅台 公告 财报" --scope finance_disclosure --limit 80 --trace` |
| “查宏观金融/央行/统计局数据” | `guanlan search "社融 CPI 降息 央行" --scope finance_macro --limit 80 --trace` |
| “查雪球/股吧/投资者情绪” | `guanlan search "某股票 雪球 股吧 情绪" --scope finance_sentiment --limit 80 --trace` |
| “查欧美娱乐/明星/巡演/新专辑/榜单” | `guanlan research "Taylor Swift 最新动态" --preset global_entertainment --profile english` |
| “查日韩娱乐/K-pop/J-pop/韩剧日剧” | `guanlan research "BLACKPINK K-pop 最新回归" --preset jp_kr_entertainment --profile hybrid` |
| “查 CVE/漏洞/补丁/诈骗短信” | `guanlan research "OpenSSL CVE 最新 漏洞" --preset cybersecurity --read-top 5` |
| “查台风路径/天气/地震/灾害预警” | `guanlan search "台风 路径 中央气象台" --scope weather_disaster --trace` |
| “查体育比赛/伤病/转会” | `guanlan research "梅西 比赛 伤病 最新" --preset sports` |
| “查 NBA/赛事实时比分和战绩” | `guanlan route "NBA季后赛2026年首轮战绩比分" --json` 后先读推荐的 ESPN/NBA direct read |
| “查科学发现/NASA/论文核验” | `guanlan research "詹姆斯韦伯 外星生命 NASA" --preset science --profile english` |
| “查校招/薪资/面经” | `guanlan research "字节 AI 产品经理 校招 薪资 面经" --preset career` |
| “查播客/小宇宙节目” | `guanlan search "AI 创业 播客 小宇宙" --scope podcast --limit 80` |
| “查雅思/托福/题库/机经” | `guanlan research "雅思 口语 题库 机经" --preset test_prep` |
| “查英文公司官网/文档/价格/发布说明” | `guanlan research "OpenAI API pricing release notes" --preset company --profile english` |
| “查英文政策/监管/标准原文” | `guanlan research "AI regulation NIST standard" --preset global_policy --profile english` |
| “查英文社区/评价样本” | `guanlan research "Product reviews Reddit G2" --preset global_reputation --profile english --read-top 0` |
| “我该去哪搜/怎么分信源/该跑哪个命令” | `guanlan route "关键词"`，先看 `recommended_commands` |
| “这个任务该轻搜还是深查” | `guanlan workflow "关键词" --json` |
| “我要系统深查/证据包/高影响核验” | `guanlan investigate "关键词" --limit 80 --format context` |
| “帮我查清楚并给依据” | `guanlan research "关键词" --profile china` |
| “查完后给建议/下一步/可能原因” | `guanlan research "关键词" --profile china --advisor` |
| “帮我对比/竞品分析/多个方案怎么选” | `guanlan compare "A" "B" --focus "价格 口碑 风险" --limit 80 --format context` |
| “按时间线梳理/最近发生了什么” | `guanlan timeline "关键词 最新进展" --limit 80 --format context` |
| “整理一个公司/产品/政策档案” | `guanlan dossier "对象" --focus "业务 口碑 风险" --limit 80 --format context` |
| “查政策/监管/官方通知” | `guanlan research "关键词" --preset policy` |
| “查产品口碑/用户评价” | `guanlan research "关键词" --preset reputation` |
| “查 EI/SCI/Scopus、学术会议、投稿/检索/收录要求” | `guanlan research "关键词" --preset academic --read-top 0` |
| “查文娱口碑/票房/评分/粉圈讨论” | `guanlan research "关键词" --preset entertainment --read-top 0` |
| “查欧美娱乐圈可靠动态” | `guanlan research "关键词" --preset global_entertainment --profile english` |
| “查日韩娱乐圈可靠动态” | `guanlan research "关键词" --preset jp_kr_entertainment --profile hybrid` |
| “查产品口碑并给购买/处理建议” | `guanlan research "关键词" --preset reputation --read-top 0 --advisor` |
| “指定多个平台查口碑” | `guanlan research "关键词" --preset reputation --sites zhihu.com,weibo.com,xiaohongshu.com` |
| “看话题是被夸还是被骂” | `guanlan pulse "关键词" --format context` |
| “查技术选型/开发者反馈” | `guanlan research "关键词" --preset tech` |
| “只要证据包，不读原文” | `guanlan research "关键词" --read-top 0` |
| “读这个链接” | `guanlan read "URL"` |
| “Jina 读不了/读取不完整” | `guanlan read "URL" --backend direct` |
| “页面噪声太多，宁可少给” | `guanlan read "URL" --strict --trace` |
| “只核验标题/发布时间/链接” | `guanlan read "URL" --backend direct --extract metadata` 或 `--extract links` |
| “只读原文，不要兜底搜索” | `guanlan read "URL" --no-fallback-search` |
| “今天有什么热点” | `guanlan hotnews today --limit 80` |
| “需要找某类平台热榜入口” | `guanlan hotnews hotboard:catalog:finance --limit 30` |
| “需要确认某个榜单今天有哪些快照” | `guanlan hotnews hotboard:snapshots:weibo --limit 20` |
| “技术社区在讨论什么” | `guanlan hotnews v2ex --limit 80` |
| “今天有什么值得读的技术/AI 文章” | `guanlan feeds curated --limit 80` |
| “今天微信/公众号有什么热文” | `guanlan feeds wechat-rss --limit 80` |
| “补一个百度热点 RSS 视角” | `guanlan feeds baidu-rss --limit 80` |
| “找精品 RSS 源目录” | `guanlan feeds curated-sources --keyword AI --limit 80` |
| “这些 RSS 源怎么路由” | `guanlan feeds list` |
| “输出结构化结果” | 给命令加 `--json` |
| “检查哪些渠道可用” | `guanlan doctor --trace` |
| “确认装到的是最新版/没调到旧路径” | `guanlan doctor --install-check` |
| “看渠道稳定性/授权边界/缓存概况” | `guanlan status`，重点看 `就绪` 和 `验证` 列 |
| “解释为什么这条排第一” | `guanlan search "关键词" --trace` |
| “小样本搜索但要稳一点” | `guanlan search "关键词" --limit 80 --trace`，若用户坚持小 limit，应说明样本风险 |
| “严格只看某站” | `guanlan search "关键词" --site gov.cn --limit 80 --trace`，结果为空时不要放宽到域外 |
| “按年份/年份范围梳理” | `guanlan timeline "关键词 2024-2025" --limit 80 --format context`，主线只用窗口内事件 |
| “重复查同一题，减少请求” | `guanlan search "关键词" --cache-ttl 3600` |
| “把搜索结果直接塞进 prompt” | `guanlan search "关键词" --format context` |
| “给没有联网能力的本地模型准备输入” | `guanlan context "关键词" --profile china --style evidence` |
| “把研究证据包直接喂给本地模型” | `guanlan research "关键词" --format prompt` |
| “把结果做成静态 HTML 报表/汇报页” | `guanlan report html --input results.json --output report.html`，这是旁支渲染器，不替代主链路 |
| “生成 MCP 客户端配置” | `guanlan mcp config --client codex` |
| “本地工具不支持 MCP，但能调 HTTP” | `guanlan serve --host 127.0.0.1 --port 8765` |
| “必须把 HTTP 服务暴露到局域网” | `guanlan serve --host 0.0.0.0 --token "$TOKEN"` |
| “查企业内部只读搜索后端” | `guanlan search "关键词" --backend plugin:my_company_api` |
| “注册企业内部只读搜索 connector” | `guanlan plugin register my_company_api ./backend.py` |
| “批量读一组链接” | `guanlan read batch urls.txt --format context` |
| “批量读很多链接且网络允许” | `guanlan read batch urls.txt --concurrency 4 --format context` |
| “追踪网页内容变化” | `guanlan read "URL" --watch` |
| “看来源是否偏斜” | `guanlan search "关键词" --source-chart` |
| “看研究路由是否偏斜” | `guanlan research "关键词" --route-chart` |
| “把链接存入本地知识库” | `guanlan archive add "URL"` |
| “把用户授权的浏览器可见页补证入库” | `guanlan archive add-browser-note --from-json browser-notes.jsonl` |
| “联网查一轮并把代表证据入库” | `guanlan archive ingest-research "关键词" --limit 80` |
| “联网查一轮、再深读少量原文入库” | `guanlan archive ingest-research "关键词" --limit 80 --read-top 3` |
| “搜索本地知识库” | `guanlan archive search "关键词" --format context` |
| “解释本地库为什么命中/没命中” | `guanlan archive search "关键词" --trace` |
| “确认一条归档是否真的有正文” | `guanlan archive inspect 1` |
| “修复/重建本地索引” | `guanlan archive reindex` |
| “体检 archive 能不能作为记忆/RAG 使用” | `guanlan archive verify` |
| “从本地库给模型准备上下文” | `guanlan archive context "问题" --limit 20` |
| “把归档整理成 AI Agent Wiki” | `guanlan archive wiki build --output ./guanlan-wiki` |
| “从 Wiki/归档里取一个主题上下文” | `guanlan archive wiki context "问题"` |
| “打包给 LangChain/LlamaIndex/Open WebUI” | `guanlan archive pack "问题" --format langchain-jsonl --output pack.jsonl` |
| “导出给 RAG 系统” | `guanlan archive export --format rag-jsonl` |
| “看跨源热点趋势” | `guanlan hotnews today --trends` |
| “拿评估集比较搜索质量” | `guanlan eval scenarios --format jsonl` |
| “发版前检查观澜契约” | `guanlan eval benchmark` |
| “导出真实任务评测池” | `guanlan eval tasks --format jsonl` |
| “发版前检查稳健性” | `guanlan quality robustness` |

CLI 是默认主路径；命令轻重不确定时先跑 `guanlan workflow "用户需求"`，信源不确定时再跑 `guanlan route "用户需求"`，按 `recommended_commands` 起手。若当前 Agent 或平台明确支持 MCP，再使用观澜 MCP 工具面：`guanlan_capabilities`、`guanlan_search`、`guanlan_workflow`、`guanlan_route`、`guanlan_read`、`guanlan_research`、`guanlan_compare`、`guanlan_timeline`、`guanlan_dossier`、`guanlan_pulse`、`guanlan_hotnews`、`guanlan_feeds`、`guanlan_archive_search`、`guanlan_status`。这些 MCP 工具保持只读，不提供发布、评论、点赞、私信等写操作。

本地 HTTP 服务默认只建议监听 `127.0.0.1`。如果用户明确要求监听局域网或服务器公网地址，必须提醒其设置 `--token` 或 `GUANLAN_SERVE_TOKEN`，因为只读接口也可能暴露本地 archive 内容和搜索行为。

MCP 客户端安装入口：

```json
{
  "mcpServers": {
    "guanlan": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/shenyangs/Guanlan.git", "guanlan-mcp"]
    }
  }
}
```

## 推荐工作流

### 网页搜索

用户说：

```text
查一下某个主题。
```

执行：

```bash
guanlan search "某个主题" --limit 80
```

中文互联网任务优先使用中文场景画像：

```bash
guanlan search "某个主题" --profile china --limit 80
```

如果 trace 里出现 `baidu=blocked`，这表示百度安全验证/反爬拦截，不是“没有搜索结果”。
不要反复重试百度，也不要尝试自动破解验证码；观澜会自动降级到后续后端，并在
`backend_recovery` 里给出可执行的多源补搜命令：

```bash
guanlan search "某个主题" --profile china --limit 80 --trace
guanlan search "某个主题" --profile china --backend bing --limit 80 --trace
guanlan search "某个主题" --profile china --scope gov --limit 80 --trace
guanlan research "某个主题" --profile china --limit 80 --read-top 0
```

需要更可信的中文信源时使用白名单 scope：

```bash
# 党央媒与中央重点媒体
guanlan search "人工智能 新质生产力" --profile china --scope party_central

# 政府与部委网站
guanlan search "人工智能 政策" --profile china --scope gov

# 核心地方官媒
guanlan search "低空经济 广东" --profile china --scope local_official

# 电商与零售垂类，包含亿邦动力等
guanlan search "跨境电商 AI" --profile china --scope ecommerce

# 文娱与内容消费，包含豆瓣、猫眼、B站、微博、TapTap 等
guanlan search "某电影 票房 豆瓣评分" --profile china --scope entertainment
```

文娱、影视、综艺、明星、游戏、票房和评分问题使用文娱 scope。它是软路由，不会只看白名单；重点是让 Agent 分清平台热度、用户评分、产业报道、宣发通稿和粉圈讨论。

财经、股票、行情、资金流向和榜单问题先走结构化数据层，避免把雪球、东方财富等动态行情页当成普通文章硬读。`guanlan stock` 是主 CLI 入口，`guanlan-stock` 是同能力的独立入口；它只整理公开行情证据，不输出买卖建议。

```bash
guanlan stock quote "贵州茅台"
guanlan stock detail "600519"
guanlan stock fundflow "宁德时代"
guanlan-stock rank --sort turnover --limit 20
guanlan-stock index
```

如果 `guanlan read` 对雪球等财经页返回 WAF、安全验证或动态页壳，Agent 不要反复重试，也不要读取 Cookie；改用结构化行情、公告披露源和财经新闻交叉补证。

如果不确定页面是否真的可读，先诊断：

```bash
guanlan diagnose page "https://example.com/article"
```

如果不确定一类任务该怎么组织，先用 recipe：

```bash
guanlan recipe list
guanlan recipe run finance-risk "宁德时代 股价 财报 公告 最近风险"
guanlan recipe run university-advisor "南京师范大学中北学院 计算机 导师 招生"
```

```bash
guanlan search "清华大学计算机系研究生招生 导师" --profile china --scope university
guanlan research "清华大学计算机系研究生招生 导师" --preset university --read-top 0
```

高校招生、导师、院系官网、招生目录和培养方案问题使用 `university`。`academic` 保留给 EI/SCI/Scopus、论文投稿、会议 CFP 和数据库检索，不要把论文数据库首页当作导师/招生信息的主证据。

公众号文章搜索优先使用站内定向搜索；当公开搜索结果不足且已安装可选依赖时，
观澜会把 `wechat-sogou` 作为备份后端追加到末尾。搜狗微信反爬较强，后端遇到验证码会直接降级，
不会自动打码或读取浏览器 Cookie：

```bash
guanlan search "关键词" --site mp.weixin.qq.com --profile china --limit 80
guanlan search "关键词" --backend wechat-sogou --limit 80
```

查看全部白名单：

```bash
guanlan search --list-scopes
```

观澜会对搜索结果做质量层处理：

- 多后端聚合，不把结论押在单一搜索引擎上。
- URL 去重，合并来自多个后端的重复结果。
- 标注 `source_type`、`matched_scope`、`trust_level` 和 `score`。
- 标注 `query_quality`，按政策、电商、财经、技术、口碑等意图调整信源偏好。
- 标注 `topic_key`、`topic_size` 和 `topic_role`，帮助识别同题转载、镜像和重复报道。
- 按 `source_type` 交错展示同题代表结果，优先形成多侧面证据组合。
- 当用户指定 `--scope` 时，优先按该研究语境解释重叠域名。
- 当用户使用 `近期`、`最近`、`热点`、`最新`、`快讯` 等时效词时，自动收束时间窗口，优先近期结果，降权明显陈旧内容。

如果 Markdown 中出现 `topic=representative/2`，表示这条是同题簇代表结果，该 topic 共有 2 条相关结果。回答用户时优先选不同 topic 的代表结果做依据，不要把同题转载当成多个独立证据。

如果前几条结果来自不同 `source_type`，这是观澜为了交叉验证刻意做的排序。回答时优先混合使用官方、垂类、社区、财经等不同类型信源；不要只拿同一种信源类型的高分结果。

如果用户需要直观看到这轮信息是否偏斜，追加来源分布图：

```bash
guanlan search "某主题" --profile china --source-chart
guanlan research "某主题" --preset industry --source-chart
```

`--source-chart` 会输出 ASCII 来源类型和域名分布。它不代表结论真假，只用于提醒 Agent：这轮证据主要来自哪里，是否需要补官方、垂类、社交或开发者社区视角。

### 话题回响

用户说：

```text
看看这个产品现在是被骂还是被夸。
```

优先使用安全版回响分析：

```bash
guanlan pulse "产品名 用户评价" --format context
```

指定公开平台样本：

```bash
guanlan pulse "产品名 用户评价" --sites zhihu.com,weibo.com,xiaohongshu.com --format context
```

需要少量原文增强时，才显式开启摘读：

```bash
guanlan pulse "产品名 用户评价" --read-top 2 --format context
```

`pulse` 只输出“基于当前公开样本的讨论倾向”，不是全网舆情结论。回答用户时必须保留置信度、样本来源、关键词信号和边界提醒。不要把 `偏正向` / `偏负向` 写成绝对事实。

如果用户希望你直接形成回答依据，而不是只列链接，优先使用研究证据包：

```bash
guanlan route "某主题"
guanlan research "某主题" --profile china --limit 80 --read-top 5
```

`research` 会自动整合搜索质量层、同题聚类、信源多样性和原文摘读。输出仍然不是最终答案，Agent 需要基于证据包再组织结论、依据和不确定性。

`route` 会输出主要意图、证据角色、优先 scope、推荐站点、兜底 scope、查询改写和边界提醒。不要把 route 当成硬过滤：除非用户显式指定 `--scope` 或 `--site`，否则 `research` 会同时保留开放网页兜底，避免只在白名单里打转。

科技、AI、开发者、工程实践类问题必须额外补一轮 RSS/精品内容流。`guanlan research "问题" --preset tech` 会自动把 `feeds curated` 作为 forced feed group 纳入候选池；如果 Agent 只跑了 `route` 或 `search`，还需要再跑：

```bash
guanlan feeds curated --category ai --limit 80
guanlan feeds curated --limit 80
```

RSS 适合作阅读发现、新鲜技术文章和趋势线索，不替代官方文档、代码仓库、issue、benchmark 原文或可复现验证。

`feeds` 依赖真实外部 RSS/OPML 源，默认会缓存最近一次成功结果。若源站超时，输出中可能出现 `feed_status=stale_cache` 和 `risk_tags=stale_cache`；这代表“用最近成功缓存保住线索”，不是实时状态，回答时要说明边界。

如果用户需要你在证据包之外给一个谨慎的“助理视角”，加 `--advisor`：

```bash
guanlan research "某主题" --profile china --limit 80 --read-top 5 --advisor
guanlan research "某产品 用户评价" --preset reputation --read-top 0 --advisor
```

助理视角会返回证据约束、可展开角度和写作规则。Agent 应据此生成自己的建议，而不是机械复述固定小标题；建议必须保留“可能/建议/仅供参考”的边界，不能写成用户真实目的，也不能替代医疗、法律、金融等高风险专业判断。

Preset 会自动选择一个或多个 scope，并可包含平台定向站点。用户显式传入 `--scope` 时，只查用户指定 scope；显式传入 `--site` 或 `--sites` 时，优先做站内/平台定向研究。

常用 preset：

| Preset | 默认信源策略 | 适合任务 |
| --- | --- |
| `policy` | `gov` + `party_central` | 政策、监管、部委通知、法规原文和权威解读。 |
| `official` | `party_central` + `gov` | 党央媒、中央重点媒体、宏观表述。 |
| `industry` | `business` + `ecommerce` + `finance`；36氪、虎嗅、一财 | 产业趋势、商业模式、公司动态。 |
| `ecommerce` | `ecommerce` + `business`；亿邦动力、网经社、雨果跨境 | 电商、零售、跨境、品牌和产业带。 |
| `reputation` | `social_web` + `tech_dev` + `business`；知乎、微博、小红书、B站 | 产品口碑、用户评价、社交平台公开讨论。 |
| `entertainment` | `entertainment` + `social_web` + `business`；豆瓣、猫眼/灯塔、B站、微博、TapTap | 影视、综艺、音乐、游戏、明星、票房、播放热度和公开口碑。 |
| `global_entertainment` | `global_entertainment` + `community_sample` + `global_news`；Variety、Deadline、Hollywood Reporter、Billboard、Rolling Stone、People | 欧美娱乐、Hollywood、音乐榜单、奖项、巡演、新歌专辑和明星动态。 |
| `jp_kr_entertainment` | `jp_kr_entertainment` + `global_entertainment` + `community_sample`；Soompi、Oricon、Natalie、Naver 娱乐、Korea Herald、Korea Times | 日韩娱乐、K-pop/J-pop、韩剧日剧、经纪公司动态、榜单和翻译站交叉验证。 |
| `cybersecurity` | `cybersecurity` + `developer` + `global_official`；NVD、CISA、CNVD/CNNVD、厂商安全公告 | CVE、漏洞、补丁、反诈、诈骗短信和安全公告。 |
| `sports` | `sports` + `global_news` + `community_sample`；ESPN、Sky Sports、联赛/俱乐部官方、虎扑/懂球帝 | 体育赛事、伤病、转会、合同和球迷讨论。 |
| `weather_disaster` | `weather_disaster` + `gov` + `global_official`；中央气象台、日本气象厅、NOAA、USGS | 台风路径、天气预警、地震和灾害应急。 |
| `science` | `science` + `academic` + `global_official`；NASA、ESA、Nature、Science、arXiv | 科学发现核验、航天/天文和科研新闻。 |
| `career` | `career` + `social_web` + `business`；牛客、应届生、Boss、Levels.fyi、Glassdoor | 校招、薪资、面经、公司口碑和招聘供需。 |
| `podcast` | `podcast` + `social_web` + `tech_dev`；小宇宙、Apple Podcasts、Spotify、Listen Notes | 播客节目、单集、主播、RSS 和听众样本。 |
| `test_prep` | `test_prep` + `social_web` + `company_primary`；IELTS/ETS/NEEA、培训资料、考生经验 | 雅思、托福、题库、机经和考试政策。 |
| `tech` | `tech_dev` + `social_web`；V2EX、掘金、SegmentFault、GitHub | 技术选型、开发者社区、工程实践。 |
| `academic` | `academic` + `tech_dev` + `business`；Elsevier、Engineering Village、IEEE、CNKI、百度学术 | EI/SCI/Scopus、学术会议、论文投稿、数据库检索和高校认定口径。 |
| `university` | `university` + `academic` + `tech_dev`；高校、研究生招生网和院系官网 | 研究生招生、导师名单、院系介绍、招生目录、招生简章、推免复试和培养方案。 |
| `finance` | `finance_disclosure` + `finance_quote` + `finance_news` + `finance_macro` + `finance_research` + `finance_sentiment`；巨潮、交易所、东方财富、财联社、央行/统计局、雪球 | 股票/基金/ETF、行情、公告财报、监管风险、宏观金融、研报观点和投资者情绪；必须分层，不输出投资建议。 |
| `local` | `local_official` + `gov` + `party_central` | 地方政策、区域产业、城市治理。 |

然后选择 2-4 个高质量结果继续读原文：

```bash
guanlan read "https://example.com/article" --max-chars 12000
```

如果默认读取失败或正文明显不完整，改用直连后端：

```bash
guanlan read "https://example.com/article" --backend direct --max-chars 12000
```

默认 `guanlan read` 在 `auto` 模式下会做三段降级：

```text
Jina Reader -> Direct HTML -> Search-as-context
```

最后一段会返回“观澜阅读兜底”上下文包，包括原始 URL、失败原因和同域公开搜索线索。它只用于继续核验，不能当作原文全文。用户如果明确要求只读原文，用：

```bash
guanlan read "https://example.com/article" --no-fallback-search
```

回答用户时给出：

- 简短结论。
- 关键证据。
- 来源链接。
- 不确定性或需要进一步验证的点。

### 中文热点

用户说：

```text
今天国内 AI 圈有什么热点？
```

优先：

```bash
guanlan hotnews today --limit 80
guanlan hotnews weibo --limit 80
guanlan hotnews bilibili --limit 80
guanlan hotnews ithome --limit 80
guanlan hotnews v2ex --limit 80
```

`today` 会混合百度热搜、微博热搜、B站热门视频、IT之家 RSS 和 V2EX 热门，适合作为“今天发生了什么”的默认入口。单个公开源失败时，观澜会保留其它源的结果。

如果需要更多来源，可以使用 NewsNow 可选增强后端，例如：

```bash
guanlan hotnews newsnow:36kr-quick --limit 80
guanlan hotnews newsnow:ithome --limit 80
guanlan hotnews newsnow:bilibili-hot-search --limit 80
```

NewsNow 源覆盖面更广，但稳定性取决于 `BASE_URL`、Cloudflare 和上游抓取状态；公共站不稳时可先配置自有或可用 endpoint：

```bash
guanlan configure newsnow-base-url https://your-newsnow.example
```

`zhihu` 热榜是 experimental 源，不要当作稳定热榜入口。需要知乎视角时可尝试：

```bash
guanlan hotnews zhihu --limit 80
guanlan search "热点关键词" --site zhihu.com --profile china --limit 80
```

如果需要更深入，再对热点关键词做搜索：

```bash
guanlan search "热点关键词" --limit 80
```

### 站内搜索

用户说：

```text
看看知乎上有没有讨论这个产品。
```

优先用站内搜索：

```bash
guanlan search "产品名 评价" --site zhihu.com --limit 80
```

如果用户明确要求微博、小红书、Twitter 等平台，再先检查可用性：

```bash
guanlan doctor --profile china --trace
```

如果配置里可能粘贴过 Cookie、Token、API key 或代理地址，先做本地配置扫描：

```bash
guanlan doctor --check-config
```

需要解释搜索排序时，使用 `--trace`。它会展示评分因子、query_quality、query_strategy、topic 信息、缓存状态、后端顺序和时效性判断，适合排查“为什么 A 在 B 前面”。

```bash
guanlan search "最新 AI 政策" --profile china --trace
```

严肃研究不要只依赖一个宽泛 query。`research` 会按路由计划把问题拆成官方原文、权威报道、用户样本、行业材料、近期进展等 query variant，再按 scope/site/open web 合并去重；Agent 回答时应保留这些证据角色差异。

同一个 query 需要反复查时，可以加 TTL 缓存，默认缓存落在 `~/.guanlan/cache/`：

```bash
guanlan search "AI 政策" --cache-ttl 3600
```

多 URL 读取时，优先用批量模式；社交平台、登录态平台仍然遵循显式授权和低频原则：

```bash
guanlan read batch urls.txt --format context
```

### 本地知识库

用户说：

```text
把这篇文章存起来，以后查资料时能用。
```

执行：

```bash
guanlan archive add "https://example.com/article"
```

已有 URL 列表时：

```bash
guanlan archive add batch urls.txt
```

把一次 research 的代表证据直接沉淀下来。注意：这是联网研究并入库，不是在已有 archive 内部搜索。写入前可以先 dry-run：

```bash
guanlan archive ingest-research "人工智能 政策" --limit 80 --dry-run
guanlan archive ingest-research "人工智能 政策" --limit 80
```

入库前观澜会为每个候选生成 `ingest_audit`，解释相关性、平台首页、重复候选、正文厚度和漂移风险。Agent 看到 `skipped` 时，不要把它理解为失败，而应理解为“这条材料不适合沉淀进本地知识库”。

查询本地沉淀材料：

```bash
guanlan archive search "人工智能 政策" --format context --trace
guanlan archive inspect 1
guanlan archive reindex
guanlan archive verify
guanlan archive context "人工智能 政策" --limit 20
guanlan archive wiki build --output ./guanlan-wiki --format both
guanlan archive wiki context "人工智能 政策"
guanlan archive pack "人工智能 政策" --format langchain-jsonl --output guanlan-pack.jsonl
```

导出给 RAG、向量库或其他本地系统：

```bash
guanlan archive export --format jsonl
guanlan archive export --format rag-jsonl
guanlan archive export --format llamaindex-jsonl
guanlan archive export --format langchain-jsonl
guanlan archive export --format openwebui-jsonl
```

Archive 默认保存在 `~/.guanlan/archive.db`。它只保存本机归档内容，不自动上传。当前本地检索默认是 SQLite FTS/LIKE 宽召回；如果显式运行 `guanlan archive embed --backend local`，可以再用 `archive search/context --semantic` 调用本地轻量语义侧车。语义侧车不联网、不替代 FTS；`--trace` 会返回 matched terms、field hits、score 和语义边界。`archive verify` 用来检查索引一致性、空正文、样本召回和 RAG/Wiki 就绪度；把 archive 交给长期 Agent 记忆前应先跑一遍。`archive wiki build` 只是把已有 archive records 组织成静态 Markdown/HTML Wiki，不代表全网知识；低质量资料会被标为 candidate。`rag-jsonl` 会导出本地 RAG 常用的 `id/text/source/title/domain/source_type/topic` 字段；`llamaindex-jsonl`、`langchain-jsonl`、`openwebui-jsonl` 适合常见本地加载器。如果需要完整元数据，用普通 `jsonl`。批量归档仍遵守高风险社交域名保护；遇到微博、小红书、抖音、Twitter/X、LinkedIn 等平台时，不要绕过授权边界批量读取。

自定义 backend 只在显式调用时启用。配置示例：

```yaml
backends:
  my_company_api:
    type: plugin
    path: ./backends/my_api.py
```

插件脚本接收 `query limit` 两个参数，输出 JSON 数组，字段至少包含 `title` 和 `url`。

### 社交平台

社交平台能力分三类：

| 类型 | 处理方式 |
| --- | --- |
| 公开可读 | 直接搜索或读取公开页面。 |
| 需要外部 CLI/MCP | 先 `doctor --trace` 判断是否可用。 |
| 需要 Cookie/登录态 | 必须向用户说明风险并请求授权。 |

不要自动执行：

- `guanlan configure --from-browser ...`
- 登录命令。
- 发帖、评论、点赞、关注、私信。

除非用户明确要求，并且你已经说明风险。

## 降级策略

| 失败场景 | 降级路径 |
| --- | --- |
| `guanlan search` 失败 | 尝试缩短关键词，或改用具体站点搜索。 |
| 中文搜索质量不够 | 加 `--profile china`，或用 `--scope` 选择官方/地方/垂类信源池。 |
| `guanlan read` 失败 | 默认会先尝试 `--backend direct`，仍失败则返回搜索兜底上下文。 |
| Jina Reader 读不到正文 | 这是大陆中文站点常见情况，改用 `--backend direct`，或换同题公开信源。 |
| 热榜源失败 | 先换 `today`、`baidu`、`weibo`、`bilibili`、`ithome` 或 `v2ex`，不要强行读取登录平台。 |
| 社交平台不可用 | 用 `guanlan search "关键词 site:平台域名"` 或普通站内搜索替代。 |
| 命令提示需要认证 | 停下来问用户是否授权，不要自动读取 Cookie。 |

## 输出格式建议

面向用户的回答应尽量这样组织：

```text
结论：
...

依据：
1. 来源标题 — URL
2. 来源标题 — URL

需要注意：
...
```

如果来源互相矛盾，要明确说明“不同来源说法不一致”，不要把搜索结果硬揉成一个确定结论。

## 安全边界

观澜默认不会触碰钥匙串。你也不要主动触发敏感动作。

安全命令：

```bash
guanlan doctor
guanlan doctor --trace
guanlan search "关键词"
guanlan read "URL"
guanlan read "URL" --backend direct
guanlan read "URL" --no-fallback-search
guanlan hotnews today
```

敏感命令：

```bash
guanlan doctor --auth-check
guanlan configure --from-browser chrome
```

只有在用户明确同意后，才运行敏感命令。
