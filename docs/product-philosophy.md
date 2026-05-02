# 观澜产品哲学与增强计划

观澜不是“再接几个搜索源”的工具。它要解决的是 Agent 在进入中文互联网之前缺少的认知准备：信源身份、语境判断、平台路由、证据压缩、安全边界和动态观察。

普通 web search 给 Agent 一双眼睛；观澜要给 Agent 一套专业调研员的思维框架。它的目标不是让 Agent 看见更多网页，而是让 Agent 在看见之前就知道：该去哪里看、谁说的话更有分量、哪些材料只能当线索、哪些动作会越界。

## 一、核心判断

### 1. 信息源的身份比相关性更早出现

中文语境里的许多问题并不只是“谁写得相关”，而是“谁有资格这样说”。政策、监管、产业口径、地方动态和央媒表述都带着明确的主体差异。

观澜的 `scope` 机制要把这种判断工程化：`party_central`、`gov`、`local_official`、`ecommerce`、`finance`、`social_web` 不只是过滤器，而是 Agent 的信源身份提示器。

需要继续加强：

- 为每个 scope 增加“适用问题”和“不可支持结论”说明。
- 在 `--trace` 中明确展示结果为什么属于某个身份层级。
- 给政策类查询增加“原文优先”提示，避免媒体解读压过发文主体。
- 增加“同一说法的主体链”：原文、央媒报道、地方转发、商业解读、社交讨论。
- 对高风险领域自动提醒 Agent 区分事实、解读和行动建议。

### 2. 中文互联网是平台孤岛，不是单一网页集合

公众号、小红书、知乎、微博、B 站、雪球、V2EX、RSS、地方官媒和垂类媒体各有抓取限制、话语方式和样本偏差。观澜不是一个搜索引擎，而是一个路由器。

它应该让 Agent 明白：技术反馈去开发者社区，产品口碑看公开社交页，官方风向看部委和党央媒，产业动向看垂类媒体，实时水势看热榜。

需要继续加强：

- 建立更细的 query intent router，把“政策/口碑/技术/产业/财经/地方/热点”映射到多组搜索计划。
- 每个路由输出“为什么查这里”，让 Agent 能解释搜索路径。
- 强化公众号、小红书、微博、B 站、知乎的现实边界，不把 best-effort 包装成稳定能力。
- 对失败的平台自动给 fallback：站内公开搜索、同主题网页搜索、热榜入口、本地 archive。
- 增加垂类信源库：党央媒、核心地方官媒、电商零售、财经快讯、产业媒体、技术社区、招聘/组织动态。

### 3. Agent 需要的是证据包，不是网页碎片

搜索摘要太薄，全网页又太脏。Agent 真正需要的是 LLM-friendly 的上下文：来源、身份、时间、主题聚类、可信度、摘要、边界和下一步。

观澜的 `--format context`、`research`、`source-chart`、`query_quality` 已经是这个方向的第一层。

需要继续加强：

- `read` 正文抽取继续去噪，减少导航、页脚、登录按钮和推荐列表。
- 为 `research` 增加“证据矩阵”：事实、观点、原文、社交样本、风险、空白。
- 支持“先广搜 50-100，再精选 5-8 条代表证据”的两阶段模式。
- 对 topic 聚类增加“转载/同源重复”识别。
- 让 `context` 输出更适合直接给本地模型，减少 Markdown 装饰，保留机器可读字段。

### 4. 安全感来自显式授权

观澜必须保持默认只读、低扰、明源。Cookie、Keychain、登录态、浏览器读取都不能静默触发。

这不是保守，而是专业工具的部署条件。越是企业、研究、生产环境，越需要知道 Agent 动了什么、为什么动、有没有替代路径。

需要继续加强：

- 将所有可能触发敏感访问的命令集中登记，`doctor --trace` 能提前展示。
- 在 Keychain/浏览器读取前保持清晰提示，并给无授权 fallback。
- 增加“安全模式 profile”，默认禁用所有登录态平台。
- 对配置文件中的 token/cookie/proxy 凭据继续做本地扫描。
- 文档中保持口径：公开搜索和阅读是主路径，登录态能力是 opt-in。

### 5. Agent 需要动态观察，而不只是被动检索

热榜、快讯、RSS、社区热门和本地快照让 Agent 具备“巡视”能力。它可以先看今天水势，再决定要不要进入 research。

需要继续加强：

- `hotnews today` 做更稳定的多源合并和去重。
- 增加跨源趋势归并：同一事件在百度、微博、B站、IT之家、V2EX 中如何扩散。
- 为热点输出时间、平台、热度指标、来源可信度和后续 research 查询建议。
- 支持“今日简报”模式：热点、政策、产业、技术、财经分栏。
- 让 `pulse` 和 `hotnews` 打通：先识别趋势，再做公开讨论倾向分析。

## 二、advisor 的正确形态

`advisor` 不应该替 Agent 写一段固定模板建议。它应该告诉 Agent 如何基于证据写建议。

理想形态：

- 输出证据能支持什么、不能支持什么。
- 给出可能展开方向，但不声称知道用户真实目的。
- 提醒 Agent 避免把社交样本当总体结论。
- 提醒 Agent 区分事实、推断、风险和行动建议。
- 让 Agent 自己结合用户问题写自然语言建议。

因此 `--advisor` 的定位应是“助理视角规则”，而不是“最终建议生成器”。

后续增强：

- 增加 `--advisor-style brief|decision|risk|strategy`。
- 让 advisor 输出面向 Agent 的 JSON schema，方便不同模型按规则生成。
- 根据 query_quality 自动决定 advisor 重点：政策看主体和时点，口碑看样本偏差，财经看公告和风险，技术看版本和复现。
- 增加“不可回答清单”，当证据不足时明确告诉 Agent 不要硬答。

## 三、本地大模型联网计划

观澜也应该服务完全没有联网能力的本地模型，例如 Ollama、LM Studio、llama.cpp、Jan、Open WebUI 或本地 Agent。

目标：让本地模型不用内置浏览器，也能通过观澜获得可引用、可压缩、可控的中文互联网上下文。

### 第一阶段：CLI 作为联网前置器

最简单的工作流：

```bash
guanlan research "问题" --profile china --format context --limit 80 > context.md
{
  cat context.md
  printf "\n请基于以上观澜证据回答用户问题，保留来源和不确定性。\n"
} | ollama run qwen3:latest
```

需要补齐：

- README 增加“本地模型联网”小节。
- 提供 `docs/local-llm.md`，覆盖 Ollama、Open WebUI、LM Studio。
- 增加 `--format prompt`，输出“证据 + 回答规则 + 用户问题”的完整 prompt。
- 增加 `guanlan prompt "问题"` 快捷命令，直接生成本地模型可用上下文。

### 第二阶段：MCP 作为本地 Agent 工具层

很多本地 Agent 支持 MCP。观澜已有 `guanlan-mcp`，下一步要把它做成更清晰的本地模型接入方式。

需要补齐：

- 给 Open WebUI / Cursor / Claude Desktop / Continue / Codex 写 MCP 配置样例。
- MCP tool description 明确提示：复杂研究默认 `limit=50-100`。
- 为本地模型默认返回 `context` 格式，避免大模型吞入过多 Markdown 噪声。
- 增加 `guanlan mcp config` 输出可复制配置。

### 第三阶段：轻量 HTTP 服务

不是所有本地模型工具都支持 MCP。需要一个只读本地 HTTP 服务：

```bash
guanlan serve --host 127.0.0.1 --port 8765
```

目标接口：

- `POST /search`
- `POST /research`
- `POST /read`
- `GET /hotnews`
- `POST /archive/search`

安全边界：

- 默认只监听 `127.0.0.1`。
- 默认不启用 Cookie/登录态能力。
- 所有敏感能力必须显式打开，例如 `--allow-auth-tools`。
- 返回结果保留来源和诊断信息。

### 第四阶段：本地知识库与 RAG

本地模型最需要长期记忆。观澜的 archive 可以成为轻量中文知识库入口。

需要补齐：

- `guanlan archive ingest-search "问题"`：把一次 research 的代表结果沉淀进 archive。
- `guanlan archive export --format jsonl` 强化字段，适配 RAG。
- 支持按 domain/source_type/topic 导出。
- 可选增加 embeddings 后端，但保持 SQLite/JSONL 作为默认轻量路径。

## 四、优先级建议

### P0：马上做

- Agent 指令层强提醒：默认多搜，复杂研究 80-100。
- advisor 改成“规则/边界/写作约束”而不是固定建议。
- 增加产品哲学文档并链接到 README。
- 新增本地大模型联网计划文档或章节。

### P1：下一轮做

- `--format prompt`，专门服务本地模型。
- `research` 两阶段模式：广搜候选池 + 精选代表证据。
- `read` 正文抽取继续去噪。
- MCP 配置生成器：`guanlan mcp config`。

### P2：稳定后做

- `guanlan serve` 本地只读 HTTP 服务。
- 热榜跨源趋势归并。
- 更细的 query intent router。
- archive 到 RAG 的结构化导出增强。

### P3：长期做

- 平台插件生态。
- 企业内部只读搜索 connector。
- 可视化来源/趋势面板。
- 多模型评估集：比较普通 web_search 与观澜证据包对幻觉率、引用质量、中文语境准确率的影响。
