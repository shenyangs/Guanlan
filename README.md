<h1 align="center">观澜 / Guanlan</h1>

<p align="center">
  <strong>给你的 AI Agent 装上中文互联网能力</strong>
</p>

<p align="center">
  临流观势，循源取义。观澜是面向 AI Agent 的中文互联网信源与平台路由器。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-1677ff?style=for-the-badge" alt="MIT License">
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/context-chinese--web-84cc16?style=for-the-badge" alt="Chinese web context">
  <img src="https://img.shields.io/badge/mode-read--first-06b6d4?style=for-the-badge" alt="Read-first mode">
  <img src="https://img.shields.io/badge/stage-pre--release-555555?style=for-the-badge" alt="Pre-release stage">
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> ·
  <a href="#使用场景与案例">使用案例</a> ·
  <a href="#当前能力图谱">能力图谱</a> ·
  <a href="#设计原则">设计原则</a>
</p>

观澜当前是一个 CLI-first 的中文互联网研究工具。公开搜索、网页阅读、热榜观察和研究证据包已经可用；部分平台能力仍处于 best-effort 或实验阶段，按需依赖外部后端、授权或额外配置。

它首先想把这几件事做好：

- **搜得更准**：针对中文语境组织搜索后端、白名单 scope 和来源分类。
- **读得更稳**：在公开网页、Jina Reader、直连 HTML 和搜索兜底之间做降级。
- **边界更清楚**：默认只读、低扰，Cookie、Keychain 和登录态访问都走显式授权。

中文互联网的信息分布并不均匀。公众号、微博、知乎、B站、小红书、抖音、雪球、V2EX、RSS、开发者社区和新闻热榜各自带着不同的语气、圈层与偏见。观澜做的事情，是让 Agent 看见这些波纹，也看见它们各自从哪里来。

## 当前最稳能力

这些是当前最敢承诺、最适合作为默认工作流的能力：

- **公开网页搜索**：`guanlan search "关键词" --profile china`
- **中文信源白名单**：`--scope party_central/gov/local_official/ecommerce`
- **网页阅读与降级**：`guanlan read "URL"`，Jina Reader、直连 HTML、搜索兜底组合使用。
- **热榜观察**：原生多源入口 `guanlan hotnews today`，覆盖百度、微博、B站、IT之家、V2EX；NewsNow 可选增强源 `guanlan hotnews newsnow:36kr-quick`
- **研究证据包**：`guanlan research "关键词" --format context`
- **本地知识库**：`guanlan archive add/search/export`

## 为什么是“观澜”

“观”强调观察与判断，“澜”强调流动、回响与趋势。这个名字对应一种更适合中文互联网的研究方式：先看水势，再辨源流，最后取其所要。

观澜关心三件事：

- Agent 知道该去哪里找中文资料。
- 不同平台的结果能被整理成统一上下文。
- 需要授权的动作始终清楚、显式、可控。

一句话定位：

> 观澜让 Agent 观其流、辨其源、取其要。

## 设计原则

如果把观澜看作一套长期可用的 Agent 工具链，底层要求其实很简单：

| 原则 | 含义 |
| --- | --- |
| 守界 | 默认只读、低频、透明，不做验证码规避、批量控制账号或风控绕行。 |
| 明源 | 输出尽量保留平台、链接、抓取时间和可信度，避免“无来源总结”。 |
| 低扰 | 默认诊断不触碰浏览器 Cookie、钥匙串、登录态；需要深度认证时由用户显式开启。 |
| 可换 | 每个平台后端都应可替换，不把项目命运绑定在单一工具或服务上。 |
| 先读后写 | 搜索、阅读、摘要、对比优先；发布、评论、点赞等写操作未来也必须走草稿和二次确认。 |

## 当前能力图谱

当前版本按 `Profile + Channel + Backend` 组织能力：Profile 负责区域画像，Channel 负责任务类型，Backend 负责实际执行。

| 领域 | 当前能力 | 状态 |
| --- | --- | --- |
| 网页阅读 | 普通网页正文提取、Markdown 化阅读 | 可用 |
| RSS | RSS/Atom 订阅源解析 | 可用 |
| GitHub | 公开仓库、Issue、PR、搜索；认证后可访问更多能力 | 可用 |
| 搜索 | Baidu/Bing/DuckDuckGo 多后端聚合、去重、信源分类、可信度评分、中文白名单 scope | 可用，持续优化 |
| 视频 | YouTube、B站字幕与元信息读取 | 可用 |
| 开发者社区 | V2EX 热门、节点、帖子与回复 | 可用 |
| 微博 | 热搜、搜索、用户与话题读取 | best-effort，按环境和授权波动 |
| 微信公众号 | 搜索与文章阅读的轻量路径 | backend-ready / unverified / best-effort，不承诺端到端稳定 |
| 小红书 | 搜索、笔记读取等能力，依赖外部后端和登录态 | opt-in，现实可用性取决于登录态和后端 |
| 抖音 | 视频解析与内容提取路径 | 可选 |
| Twitter/X | 推文、搜索、时间线等能力，依赖 Cookie 或外部 CLI | 可选 |
| Reddit | 帖子与评论读取，部分环境需要认证或网络配置 | 可选 |
| 雪球 | 股票搜索、行情、热门讨论等财经入口 | 可选，需谨慎处理登录态 |
| 小宇宙 | 播客音频转文字与摘要路径 | 可选 |
| LinkedIn | Profile、公司页、职位搜索等研究入口 | 实验 |

这些状态更接近当前实现信号，而不是环境无关的承诺。中国互联网平台变化快，观澜更重视可诊断、可替换和可降级。

## 快速开始

### 小白三步部署

如果你只是想先用起来，不想理解 Python、虚拟环境或 MCP，按下面三步走就可以。

**可以直接复制给 Agent 的安装指令**

如果你在 Codex、Claude Code、Cursor、Devin 或其他 AI Agent 里使用，可以先把下面这段直接发给它：

```text
请帮我安装观澜 CLI，并验证基础功能可用。

优先使用 Homebrew：
brew tap shenyangs/tap && brew install guanlan

如果当前环境没有 Homebrew，请改用 PyPI + uv：
uv tool install guanlan

如果没有 uv，请先按当前系统安装 uv，然后再安装观澜。
安装完成后请运行：
guanlan version
guanlan doctor
guanlan search "人工智能 新质生产力" --profile china --scope party_central --limit 5

安全要求：不要读取浏览器 Cookie，不要触发登录授权，不要请求钥匙串权限。
```

**第一步：选择安装路线**

- 如果你用 `Homebrew`，可以直接跳到第二步，不需要安装 `uv`。
- 如果你用 PyPI + `uv`，先安装 `uv`：

macOS / Linux：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装后如果终端提示找不到 `uv`，关掉当前终端，重新打开一次。

- 如果你用 PyPI + `pipx`，请先确保本机已安装 `pipx`。

**第二步：安装观澜（任选一种）**

```bash
brew tap shenyangs/tap
brew install guanlan
```

或（PyPI + `uv`）：

```bash
uv tool install guanlan
```

或（PyPI + `pipx`）：

```bash
pipx install guanlan
```

**第三步：确认能用**

```bash
guanlan version
guanlan doctor
guanlan search "人工智能 新质生产力" --profile china --scope party_central --limit 5
```

看到 `观澜 / Guanlan v0.1.7`，并且 `search` 能返回中文搜索结果，就说明基础部署成功。

以后更新观澜：

```bash
brew upgrade guanlan
uv tool upgrade guanlan
pipx upgrade guanlan
```

如果更新失败，也可以直接重装：

```bash
brew reinstall guanlan
uv tool install --force guanlan
pipx install --force guanlan
```

### Agent / 开发者安装

推荐直接从 PyPI 安装：

```bash
uv tool install guanlan
guanlan doctor
```

如果你使用 `pipx`：

```bash
pipx install guanlan
guanlan doctor
```

如果你偏好 Homebrew：

```bash
brew tap shenyangs/tap
brew install guanlan
guanlan doctor
```

想先试运行、不持久安装（`uvx`）：

```bash
uvx --from guanlan guanlan version
```

如果已经克隆本仓库，也可以在仓库根目录安装：

```bash
pipx install .
guanlan install --env=auto
guanlan doctor
```

MCP 客户端可以使用 `guanlan-mcp` 入口。以支持 JSON 配置的客户端为例：

```json
{
  "mcpServers": {
    "guanlan": {
      "command": "uvx",
      "args": ["--from", "guanlan", "guanlan-mcp"]
    }
  }
}
```

如果你的 Python 环境受到 PEP 668 限制，也可以使用虚拟环境：

```bash
python3 -m venv ~/.guanlan-venv
source ~/.guanlan-venv/bin/activate
pip install .
guanlan install --env=auto
guanlan doctor
```

切到中文场景画像：

```bash
guanlan profile set china
guanlan doctor --profile china
```

安全安装预演：

```bash
guanlan install --env=auto --safe
guanlan install --env=auto --dry-run
```

## 默认不触碰钥匙串

这是观澜非常明确的一条边界。

普通诊断只检查工具是否存在、基础后端是否可用，不主动读取浏览器 Cookie、不主动访问 macOS 钥匙串、不主动做登录态深度探测：

```bash
guanlan doctor
```

如果你想知道为什么某个渠道被判定为可用、跳过或需要配置，可以打开追踪输出：

```bash
guanlan doctor --trace
```

只有当你明确要检查认证、Cookie 或登录态时，才使用：

```bash
guanlan doctor --auth-check
```

只有当你明确要从本机浏览器提取 Cookie 时，才使用：

```bash
guanlan configure --from-browser chrome
```

如果系统弹出钥匙串提示，不建议反射性点击“始终允许”。先用 `guanlan doctor --trace` 看触发路径，再决定是否需要深度认证检查。观澜的默认方向是：少打扰、可解释、可关停。

## 命令速查

| 命令 | 用途 |
| --- | --- |
| `guanlan install --env=auto` | 自动安装基础能力与必要依赖。 |
| `guanlan install --env=auto --safe` | 安全模式，只提示需要什么，不主动改系统。 |
| `guanlan install --env=auto --dry-run` | 预演安装步骤，不做实际改动。 |
| `guanlan doctor` | 健康检查，默认跳过敏感登录态探测。 |
| `guanlan doctor --trace` | 展示诊断路径，帮助定位是否存在敏感探测风险。 |
| `guanlan doctor --check-config` | 扫描本地配置中可能误存的明文 Cookie、Token、Key 或代理凭据。 |
| `guanlan status` | 显示渠道运行、就绪、验证、稳定性、授权边界和本地缓存概览。 |
| `guanlan search "关键词"` | 搜索网页，输出适合 Agent 阅读的结果列表。 |
| `guanlan search "关键词" --trace` | 展示评分因子、后端顺序、聚类阈值和缓存命中状态。 |
| `guanlan search "最近 关键词 热点" --trace` | 自动识别时效性意图，收束到近期窗口，并在 trace 中解释结果日期。 |
| `guanlan search "关键词" --cache-ttl 3600` | 一小时内复用同条件搜索结果，降低上游扰动。 |
| `guanlan search "关键词" --format context` | 输出紧凑的 LLM-friendly 证据表格。 |
| `guanlan search "关键词" --source-chart` | 追加 ASCII 来源/域名分布图，快速判断信息面是否偏斜。 |
| `guanlan search "关键词" --backend plugin:my_company_api` | 显式调用本地自定义只读搜索 backend。 |
| `guanlan search "关键词" --scope party_central` | 在党央媒与中央重点媒体白名单内搜索。 |
| `guanlan search "关键词" --scope ecommerce` | 在电商/零售垂类媒体白名单内搜索。 |
| `guanlan research "关键词"` | 生成 Agent 可直接使用的研究证据包。 |
| `guanlan research --list-presets` | 查看研究模板和默认 scope/site 策略。 |
| `guanlan research "关键词" --format context` | 输出适合直接放进 prompt 的研究上下文。 |
| `guanlan research "关键词" --sites zhihu.com,weibo.com` | 按多个指定站点生成平台定向证据块。 |
| `guanlan pulse "关键词"` | 安全版话题回响分析，输出讨论倾向、关键词信号和明确边界。 |
| `guanlan read "URL"` | 读取网页并转成 Markdown。 |
| `guanlan read batch urls.txt --format context` | 批量读取 URL 列表并输出紧凑上下文。 |
| `guanlan read "URL" --watch` | 保存/比较本地快照，输出内容变化 diff。 |
| `guanlan read "URL" --backend direct` | 绕过 Jina Reader，直接读取原网页。 |
| `guanlan archive add "URL"` | 将网页读取为 Markdown 后沉淀进本地知识库。 |
| `guanlan archive search "关键词"` | 在本地知识库中检索已归档材料。 |
| `guanlan archive export --format jsonl` | 导出本地知识库，方便接入 RAG 或其他系统。 |
| `guanlan hotnews today --limit 10` | 拉取原生多源中文热榜。 |
| `guanlan profile set china` | 切换到中文场景画像。 |
| `guanlan configure --from-browser chrome` | 显式从浏览器提取支持平台的 Cookie。 |
| `guanlan skill --install` | 将观澜使用说明安装到 Agent skills 目录。 |

## 使用场景与案例

下面这些例子按真实使用场景组织，可以直接复制到终端里跑。观澜的默认思路是：先用公开搜索看水势，再追原文辨源流，最后把证据整理成 Agent 可以继续推理的上下文。

### 1. 快速查一个中文问题

适合“先给我找一圈资料”“看看公开网页上有什么线索”。

```bash
guanlan search "AI 眼镜 产业链" --profile china --limit 8
guanlan search "AI 眼镜 产业链" --profile china --format context
guanlan search "AI 眼镜 产业链" --profile china --source-chart
```

`--format context` 会输出更紧凑的证据表格，适合直接放进 Agent prompt。
`--source-chart` 会追加来源类型和域名分布，帮助判断这轮结果是偏官方、偏社交、偏商业媒体，还是来源比较均衡。

### 2. 查近期热点、最新动态和时效性问题

适合“最近有什么进展”“今天/本周有什么热点”“某事件最新消息”。观澜会识别 `最近`、`近期`、`热点`、`热搜`、`最新`、`快讯` 等词，把搜索词补上当前年月，并在排序时优先近期结果、降权明显陈旧内容。

```bash
guanlan search "最近 AI 眼镜 热点" --profile china --limit 8 --trace
guanlan search "本周 跨境电商 热点" --profile china --scope ecommerce --format context
guanlan research "最新 人工智能 政策 进展" --preset policy --read-top 2
```

如果要排查为什么某条排在前面，加 `--trace` 查看 `recency_boost`、`stale_penalty`、结果日期和是否落在时间窗口内。

### 3. 查政策、部委通知和官方原文

适合政策研究、监管变化、行业规则、政府公告。优先找原文，不用媒体解读替代政策文本。

```bash
guanlan search "人工智能 政策" --profile china --scope gov --limit 8
guanlan research "人工智能 政策" --preset policy --read-top 2 --max-read-chars 2400
```

如果想看宏观表述和权威报道，可以切到党央媒与中央重点媒体：

```bash
guanlan search "人工智能 新质生产力" --profile china --scope party_central --limit 8
guanlan research "人工智能 新质生产力" --preset official --read-top 2
```

### 4. 查地方政策和核心地方官媒

适合地方产业、城市治理、区域政策、地方舆论表述。

```bash
guanlan search "低空经济 广东 政策" --profile china --scope local_official --limit 8
guanlan research "低空经济 广东 政策" --preset local --read-top 2
```

### 5. 查产业、电商和垂类媒体

适合跨境电商、零售、新消费、平台生态、产业带研究。这里会优先利用亿邦动力、网经社、雨果跨境、联商网等垂类信源。

```bash
guanlan search "跨境电商 AI 工具" --profile china --scope ecommerce --limit 8
guanlan research "跨境电商 AI 工具" --preset ecommerce --read-top 3
```

更宽一点的产业研究可以用：

```bash
guanlan research "AI Agent 商业化 国内公司" --preset industry --read-top 3
```

### 6. 查产品口碑和公开社交讨论

适合产品调研、竞品分析、用户反馈收集。第一版默认走公开网页层面的线索，不要求登录，也不批量触碰高风险社交账号。

```bash
guanlan research "某产品 用户评价" --preset reputation --read-top 0 --format context
guanlan research "某产品 用户评价" --preset reputation --sites zhihu.com,weibo.com,xiaohongshu.com --read-top 0
guanlan pulse "某产品 用户评价" --sites zhihu.com,weibo.com,xiaohongshu.com --format context
```

如果你只想看某个平台的公开网页结果：

```bash
guanlan search "某产品 用户评价" --profile china --site zhihu.com --limit 8
guanlan search "某产品 使用体验" --profile china --site bilibili.com --limit 8
```

`pulse` 只给“基于当前公开样本的讨论倾向”，不是全网舆情结论。默认不读原文；如果需要更强证据，可以显式加 `--read-top 2`。

### 7. 查技术选型和开发者反馈

适合框架对比、开源项目调研、工程实践、社区反馈。

```bash
guanlan research "Python Agent 框架 对比" --preset tech --read-top 2
guanlan search "LangGraph AutoGen CrewAI 对比" --profile china --scope tech_dev --format context
```

### 8. 读取单篇文章或网页

适合用户给你一个 URL，希望你读完再总结。默认会先尝试更干净的阅读路径，再按情况降级。

```bash
guanlan read "https://example.com/article" --max-chars 12000
guanlan read "https://example.com/article" --format context
```

如果 Jina Reader 在中国网络环境里不稳定，或网页被转写得不完整，可以显式走直连：

```bash
guanlan read "https://example.com/article" --backend direct --max-chars 12000
```

### 9. 批量读取一组链接

适合 Agent 已经搜到一批材料，需要统一读成上下文。

```bash
cat > urls.txt <<'EOF'
https://example.com/a
https://example.com/b
EOF

guanlan read batch urls.txt --format context --cache-ttl 3600
```

批量读取会对微博、小红书、抖音、Twitter/X、LinkedIn 等高风险社交域名保留更谨慎的边界，避免不透明地触碰登录态。

### 10. 追踪网页变化

适合政策页、公告页、价格页、项目 README 这类“今天和上次有什么不同”的任务。

```bash
guanlan read "https://www.gov.cn/" --watch
guanlan read "https://github.com/shenyangs/Guanlan" --watch
```

第一次运行会保存本地快照；之后再次运行，会输出内容变化 diff。

### 11. 看中文热榜，再顺藤摸瓜

适合“今天有什么热点”“国内讨论在往哪里流”。

```bash
guanlan hotnews list
guanlan hotnews today --limit 12
guanlan hotnews weibo --limit 10
guanlan hotnews bilibili --limit 10
guanlan hotnews ithome --limit 10
guanlan hotnews v2ex --limit 10
guanlan hotnews newsnow:36kr-quick --limit 10
```

`today` 是默认推荐入口，会把百度热搜、微博热搜、B站热门视频、IT之家 RSS 和 V2EX 热门混合成一个多源快照；其中单个公开端点失败时不会拖垮其它来源。

`newsnow:<source>` 是可选增强后端，适合补 36氪、B站热搜、财联社、华尔街见闻等更多来源；稳定性取决于 NewsNow BASE_URL、Cloudflare 和上游抓取状态。公共站不稳时可配置自己的 NewsNow：

```bash
guanlan configure newsnow-base-url https://your-newsnow.example
guanlan hotnews newsnow:ithome --limit 10
```

`zhihu` 热榜是实验源，部分环境会返回 401/403。需要知乎视角时，优先把它当作可选尝试；失败后用站内搜索兜底：

```bash
guanlan hotnews zhihu --limit 10
guanlan search "热点关键词" --site zhihu.com --profile china --limit 8
```

看到关键词后，可以继续交给 `search` 或 `research` 追原文：

```bash
guanlan research "热榜里的关键词" --profile china --format context
```

### 12. 解释搜索结果为什么这样排

适合排查“为什么这个结果在前面”“有没有缓存”“是不是 scope 生效了”。

```bash
guanlan search "跨境电商 AI" --profile china --scope ecommerce --trace
guanlan search "最新 人工智能 政策" --profile china --cluster-threshold conservative --trace
```

`--trace` 会展示后端顺序、缓存命中、评分因子、topic 聚类、来源分类和时效性判断，方便 Agent 把检索过程讲清楚。

### 13. 给 AI Agent 的最短工作流

如果你是在另一个 Agent、MCP 客户端或自动化脚本里调用观澜，优先使用这几类输出：

```bash
guanlan search "问题" --profile china --format context
guanlan search "最近 问题 热点" --profile china --format context --trace
guanlan research "问题" --preset policy --format context --source-chart
guanlan research "产品 用户评价" --preset reputation --read-top 0 --format context
guanlan pulse "产品 用户评价" --format context
guanlan read batch urls.txt --format context --cache-ttl 3600
guanlan archive search "问题" --format context
```

CLI 是默认主路径；如果当前 Agent 或平台支持 MCP，可以把 `guanlan-mcp` 作为可选集成接进去，让 Agent 直接调用 `guanlan_search`、`guanlan_read`、`guanlan_research`、`guanlan_pulse`、`guanlan_hotnews`、`guanlan_archive_search` 和 `guanlan_status`。

### 14. 把读过的网页沉淀成本地知识库

适合把 Agent 搜过、读过、核验过的材料保存下来，后续不用重复请求上游，也能导出给 RAG 系统。

```bash
guanlan archive add "https://example.com/article"
guanlan archive add batch urls.txt
guanlan archive search "人工智能 政策" --format context
guanlan archive stats
guanlan archive export --format jsonl > guanlan-archive.jsonl
```

本地知识库默认保存在 `~/.guanlan/archive.db`。第一版使用 SQLite + FTS/LIKE 检索，保存 URL、标题、域名、Markdown 正文、摘要、更新时间和元数据。它不是云同步，也不会自动上传内容。

### 15. 安全检查和授权边界

如果你担心配置里误存了 Cookie、Token、API key 或代理凭据，先跑：

```bash
guanlan doctor --check-config
guanlan status
```

如果你只是做公开搜索和网页阅读，通常不需要浏览器 Cookie，也不需要钥匙串授权。只有明确要检查登录态或从浏览器提取 Cookie 时，才使用：

```bash
guanlan doctor --auth-check
guanlan configure --from-browser chrome
```

## 适合的任务

观澜更适合下面这些研究型工作：

- 查中文资料，快速形成可继续验证的证据面。
- 看今天国内热点，再按主题往下追原文。
- 对比不同平台对同一事件、产品或公司的表达差异。
- 读公众号、网页、视频、Issue、社区帖子，再整理成 Agent 上下文。
- 做政策、产业、电商、口碑、技术、财经这类需要多来源交叉验证的任务。

遇到“帮我查清楚再回答”这类任务，通常可以直接用：

```bash
guanlan research "人工智能 新质生产力" --profile china --scope party_central
guanlan research "跨境电商 AI" --profile china --scope ecommerce --read-top 3
guanlan research "某产品 用户评价" --profile china --site zhihu.com --read-top 0
guanlan research "某产品 用户评价" --preset reputation --sites zhihu.com,weibo.com,xiaohongshu.com
```

`research` 会把搜索结果、同题聚类、信源多样性和原文摘读整理成一份更适合 Agent 消化的证据包。

Preset 会自动选择多组 scope 和平台定向站点。例如 `policy` 会查 `gov + party_central`，`reputation` 会查 `social_web + tech_dev + business`，并补充知乎、微博、小红书、B站等公开页证据块。用户显式传入 `--scope`、`--site` 或 `--sites` 时，以用户指定范围为准。

## 中文语境

观澜生长在中文互联网语境里。它关心的不只是补充更多平台名称，也是在重建一套更适合本地信息结构的工作流：

- **先看全局**：`hotnews` 和 `search` 用来判断今天的信息流向与主要出处。
- **再追原文**：`read` 在 Jina Reader、直连 HTML 和搜索兜底之间做降级。
- **最后整理证据**：`research` 负责把多来源结果组织成可继续推理的上下文。

当前版本已经落下来的重点包括：

- `china` profile 与中文白名单 scope。
- 多后端搜索、同题聚类、信源分类和多样性排序。
- 热榜、网页阅读与公开搜索之间的降级链路。
- 默认只读、低扰、显式授权的安全边界。

更完整的设计与阶段路线见 [中文互联网设计](docs/chinese-web-design.md)。

## 给 Agent 的使用方式

安装 skill 后，Agent 不需要记住每个平台的细节命令。用户可以直接说：

```text
查一下国内今天 AI 圈有什么热点。
看看微博和小红书上大家怎么评价这个产品。
读一下这篇公众号，提炼论点和证据。
总结这个 B 站视频，并列出可验证出处。
帮我看一下这个 GitHub 项目的 Issue 里主要在抱怨什么。
```

观澜负责把任务拆成更合适的搜索、阅读、授权和降级路径。

## 文档

| 文档 | 内容 |
| --- | --- |
| [中文入口](docs/README_zh.md) | 中文文档导航。 |
| [更新日志](CHANGELOG.md) | 记录每个版本的能力变化、边界调整和下一步收口。 |
| [Agent 使用说明](docs/agent-usage.md) | 给 AI Agent 的搜索、阅读、热榜和安全路由规则。 |
| [安装指南](docs/install.md) | 给 Agent 执行的安装流程与边界。 |
| [更新指南](docs/update.md) | 更新观澜与依赖工具。 |
| [发布自动化](docs/release-automation.md) | 维护者用：PyPI 自动发布与 Homebrew tap 自动更新。 |
| [排障手册](docs/troubleshooting.md) | 网络、Cookie、钥匙串、平台异常排查。 |
| [中文互联网设计](docs/chinese-web-design.md) | 产品方案、平台矩阵与阶段路线。 |
| [发布冒烟样本](docs/release-smoke-samples.md) | 第一版发布前的真实中文查询样本和通过标准。 |
| [Cookie 导出](docs/cookie-export.md) | 手动导出 Cookie 的安全流程。 |
| [来源说明](docs/SOURCE_ATTRIBUTION.md) | 开源参考与来源集中说明。 |

## 本地数据与隐私

观澜默认将配置保存在：

```text
~/.guanlan/
```

建议：

- 不要把主账号 Cookie 交给任何自动化工具。
- 需要登录的平台优先使用专用小号。
- 不把 `~/.guanlan/config.yaml` 提交到任何仓库。
- 可运行 `guanlan doctor --check-config` 检查配置中是否有明文 Cookie、Token、Key 或代理凭据。
- 如果使用共享电脑，检查配置文件权限是否为仅本人可读写。
- 不确定是否需要授权时，先运行 `guanlan doctor --trace`。

## 许可证与来源

观澜采用 MIT License。

本项目在设计和工程上参考了若干开源项目，来源集中记录在 [docs/SOURCE_ATTRIBUTION.md](docs/SOURCE_ATTRIBUTION.md)。除来源说明外，项目文档和产品表达以观澜自身定位为准。
