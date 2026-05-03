<h1 align="center">观澜 / Guanlan</h1>

<p align="center">
  <strong>让 AI Agent 看懂中文互联网</strong>
</p>

<p align="center">
  临流观势，循源取义。观澜是 AI Agent 的中文互联网研究底座：会路由信源、阅读网页、观察热榜、整理证据。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-1677ff?style=for-the-badge" alt="MIT License">
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/context-chinese--web-84cc16?style=for-the-badge" alt="Chinese web context">
  <img src="https://img.shields.io/badge/mode-read--first-06b6d4?style=for-the-badge" alt="Read-first mode">
  <img src="https://img.shields.io/badge/stage-pre--release-555555?style=for-the-badge" alt="Pre-release stage">
</p>

<p align="center">
  <a href="#tldr30-秒上手">TL;DR</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#使用场景与案例">使用案例</a> ·
  <a href="#当前能力图谱">能力图谱</a> ·
  <a href="#设计原则">设计原则</a>
</p>

<p align="center">
  语言：
  <strong>中文</strong> ·
  <a href="docs/README_en.md">English</a> ·
  <a href="docs/README_ja.md">日本語</a> ·
  <a href="docs/README_ko.md">한국어</a>
</p>

<p align="center">
  <img src="assets/guanlan-overview.png" alt="观澜 Guanlan 面向 AI Agent 的中文互联网研究底座流程图">
</p>

观澜当前是一个 CLI-first 的中文互联网研究工具。公开搜索、网页阅读、热榜观察、研究证据包、本地知识库和 Agent 集成入口已经可用；部分平台能力仍处于 best-effort 或实验阶段，按需依赖外部后端、授权或额外配置。

如果只看一眼，观澜最想解决的是这一件事：

> 普通搜索让 Agent 看见网页，观澜让 Agent 看懂中文互联网。

## 一眼看懂

| 极致点 | 观澜做了什么 |
| --- | --- |
| 中文互联网研究底座 | 不只返回链接，而是把搜索、阅读、热榜、归档整理成 Agent 可继续推理的证据包。 |
| 信源身份清楚 | 在中文语境里，“谁说的”很重要；观澜保留官方、党央媒、地方官媒、垂类媒体、社区样本和热榜信号的身份差异。 |
| 信息孤岛路由 | 政策看官方，口碑看社区和内容平台，技术看开发者社区，产业看垂类媒体；观澜先判断去哪搜。 |
| Agent-ready 输出 | `route`、`research`、`compare`、`timeline`、`dossier`、`--format context`、MCP、只读 HTTP 和本地模型 Prompt 都面向下游 Agent。 |
| 安全边界明确 | 默认只读、低扰、明源；Cookie、Keychain 和登录态访问都走显式授权。 |
| 本地模型联网 | 让 Ollama、LM Studio、Open WebUI 等没有原生搜索能力的模型拿到中文互联网证据上下文。 |

中文互联网的信息分布并不均匀。公众号、微博、知乎、B站、小红书、抖音、雪球、V2EX、RSS、开发者社区和新闻热榜各自带着不同的语气、圈层与偏见。观澜做的事情，是让 Agent 看见这些波纹，也看见它们各自从哪里来。

观澜不追求把网页一股脑堆给 Agent，而是先辨水势：谁在说、在哪里说、何时说、能支持什么结论、还缺什么证据。Agent 拿到的不是一包来源不明的链接，而是一份可以继续推理的中文互联网证据。

## TL;DR（30 秒上手）

安装/升级（任选一种，默认使用“强制拿最新”的命令）：

```bash
brew update && brew tap shenyangs/tap && brew reinstall shenyangs/tap/guanlan
```

```bash
uv tool install --force --upgrade guanlan
```

```bash
pipx install --force guanlan
```

验证：

```bash
guanlan version
guanlan doctor
```

常用三条命令：

```bash
guanlan search "关键词" --profile china
guanlan read "https://example.com/article"
guanlan hotnews today --brief
```

## 当前最稳能力

这些是当前最敢承诺、最适合作为默认工作流的能力：

- **公开网页搜索**：`guanlan search "关键词" --profile china`
- **中文信源白名单**：`--scope party_central/gov/local_official/ecommerce/university/entertainment`
- **英文互联网信源路由**：`guanlan search "OpenAI API pricing" --profile english --scope company_primary`
- **网页阅读与降级**：`guanlan read "URL"`，Jina Reader、直连 HTML、搜索兜底组合使用。
- **热榜观察**：原生多源入口 `guanlan hotnews today`，覆盖百度、微博、B站、IT之家、V2EX；NewsNow 可选增强源 `guanlan hotnews newsnow:36kr-quick`
- **研究证据包**：`guanlan research "关键词" --format context`
- **高阶研究工作流**：`compare` 做多对象对比，`timeline` 抽时间线，`dossier` 生成研究档案。
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
| 搜索 | Baidu/Bing/DuckDuckGo 多后端聚合、去重、信源分类、可信度评分、中文/英文 scope | 可用，持续优化 |
| 研究工作流 | `compare`、`timeline`、`dossier` 把证据包整理成对比、时间线和档案 | 可用 |
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

优先使用 Homebrew（先刷新 tap，避免装到旧公式）：
brew update
brew tap shenyangs/tap
brew reinstall shenyangs/tap/guanlan

如果当前环境没有 Homebrew，请改用 PyPI + uv：
uv tool install --force --upgrade guanlan

如果没有 uv，请先按当前系统安装 uv，然后再安装观澜。
安装完成后请运行：
guanlan version
guanlan doctor

如果 `guanlan version` 不是 README 标注的当前版本，请不要继续配置 MCP 或可选渠道，先改用 `uv tool install --force --upgrade guanlan` 重新安装。

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
brew update
brew tap shenyangs/tap
brew reinstall shenyangs/tap/guanlan
```

或（PyPI + `uv`）：

```bash
uv tool install --force --upgrade guanlan
```

或（PyPI + `pipx`）：

```bash
pipx install --force guanlan
```

**第三步：确认能用**

```bash
guanlan version
guanlan doctor
```

看到 `观澜 / Guanlan v0.5.1`，并且 `doctor` 通过基础自检，就说明基础部署成功。

如果 Homebrew 装出来的版本低于这里标注的版本，通常是 tap 或本地缓存滞后。先运行：

```bash
brew update
brew reinstall shenyangs/tap/guanlan
guanlan version
```

如果仍然不是当前版本，请临时改用 PyPI + `uv`：

```bash
uv tool install --force --upgrade guanlan
guanlan version
```

以后更新观澜，建议让 Agent 走“全量更新”而不是增量升级。全量更新的目标是避免旧的
`guanlan` 可执行文件、旧 Homebrew 公式或旧 pipx/uv tool 入口继续被 Agent 调用。

```bash
uv tool install --force --upgrade guanlan
```

注意：`uv tool install --force guanlan` 只保证重装，可能继续使用旧的锁定版本；更新时必须带
`--upgrade`。

如果你明确使用 Homebrew：

```bash
brew update
brew reinstall shenyangs/tap/guanlan
```

如果你明确使用 pipx：

```bash
pipx install --force guanlan
```

更新后必须核对入口和版本，并做最小 smoke：

```bash
hash -r 2>/dev/null || true
command -v guanlan
which -a guanlan
guanlan version
guanlan capabilities
guanlan doctor --install-check
guanlan doctor --trace
guanlan search "人工智能 政策" --profile china --limit 5 --trace
guanlan hotnews today --limit 5 --trends
```

如果 `guanlan version` 不是 README 标注的当前版本，或 `which -a guanlan` 显示 Agent 会优先
调用旧路径，请不要继续配置 MCP 或可选渠道，先改用 `uv tool install --force --upgrade guanlan` 重新安装。

### Agent / 开发者安装

推荐直接从 PyPI 安装：

```bash
uv tool install --force --upgrade guanlan
guanlan version
guanlan doctor
```

如果你使用 `pipx`：

```bash
pipx install --force guanlan
guanlan version
guanlan doctor
```

如果你偏好 Homebrew：

```bash
brew update
brew tap shenyangs/tap
brew reinstall shenyangs/tap/guanlan
guanlan version
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
| `guanlan welcome` | 重新查看首次安装后的简短使用介绍和 Agent 说法示例。 |
| `guanlan capabilities` | 展示观澜能力地图：何时用 search/route/research/advisor/hotnews 等能力。 |
| `guanlan doctor` | 健康检查，默认跳过敏感登录态探测。 |
| `guanlan doctor --trace` | 展示诊断路径，帮助定位是否存在敏感探测风险。 |
| `guanlan doctor --check-config` | 扫描本地配置中可能误存的明文 Cookie、Token、Key 或代理凭据。 |
| `guanlan doctor --install-check` | 检查当前命令路径、版本漂移和多安装入口，避免 Agent 调到旧版。 |
| `guanlan status` | 显示渠道运行、就绪、验证、稳定性、授权边界和本地缓存概览。 |
| `guanlan route "关键词"` | 解释需求路由、证据角色、优先 scope、推荐站点、推荐 RSS 和边界提醒。 |
| `guanlan route "关键词" --json` | 给 Agent 前置路由，输出 `recommended_commands` 作为下一步命令起手式。 |
| `guanlan workflow "关键词"` | 本地判断该轻搜、按路由研究，还是显式进入 `investigate`；不会联网，也不会让基础 search 自动变重。 |
| `guanlan investigate "复杂问题" --limit 80 --format context` | 显式上层深查入口：复用 route/research/read/feeds/hotnews，把工作流决策和证据包放在一起。 |
| `guanlan investigate "复杂问题" --budget deep --dry-run` | 只解释会执行哪些步骤、候选池和读取预算，不发起网络请求。 |
| `guanlan sources list --scope ecommerce` | 查看只读信源矩阵，理解某个 scope 下有哪些来源、角色、风险和适用边界。 |
| `guanlan sources show gov.cn` | 查看单个域名/信源/scope 的 authority、sample、freshness 和 risk tags。 |
| `guanlan sources explain "新质生产力 政策"` | 按 query 解释为什么优先某些 scope 和信源角色。 |
| `guanlan sources audit` | 体检高关注平台在 registry/channel/文档中的稳定性、授权和风险口径是否漂移。 |
| `guanlan sources export --format json` | 导出只读信源矩阵，便于 Agent/评测工具审计。 |
| `guanlan eval suite run chinese-web-v1` | 运行 100 题离线公开基准，覆盖政策、地方、电商、技术、财经、口碑、热点、学术、文娱和本地模型联网。 |
| `guanlan eval suite run chinese-web-live --mode live` | 运行真实任务样本池的可复测框架；网络/上游问题会单独归因，不进 release gate。 |
| `guanlan search "关键词"` | 搜索网页，输出适合 Agent 阅读的结果列表。 |
| `guanlan search "关键词" --trace` | 展示评分因子、后端顺序、聚类阈值和缓存命中状态。 |
| `guanlan search "最近 关键词 热点" --trace` | 自动识别时效性意图，收束到近期窗口，并在 trace 中解释结果日期。 |
| `guanlan search "关键词" --trace` | 同时展示查询策略：原始问题会如何拆成官方、媒体、社区、用户样本等证据角色。 |
| `guanlan search "关键词" --cache-ttl 3600` | 一小时内复用同条件搜索结果，降低上游扰动。 |
| `guanlan search "关键词" --format context` | 输出紧凑的 LLM-friendly 证据表格。 |
| `guanlan search "关键词" --format prompt` | 输出可直接喂给本地模型的完整 Prompt。 |
| `guanlan search "关键词" --source-chart` | 追加 ASCII 来源/域名分布图，快速判断信息面是否偏斜。 |
| `guanlan search "关键词" --backend plugin:my_company_api` | 显式调用本地自定义只读搜索 backend。 |
| `guanlan search "关键词" --scope party_central` | 在党央媒与中央重点媒体白名单内搜索。 |
| `guanlan search "关键词" --scope ecommerce` | 在电商/零售垂类媒体白名单内搜索。 |
| `guanlan search "电影 票房 评分" --scope entertainment` | 在文娱/内容平台信源内搜索，覆盖影视、综艺、明星、游戏、票房和口碑。 |
| `guanlan search "Taylor Swift latest" --profile english --scope global_entertainment` | 在欧美娱乐、音乐产业、榜单/奖项和英文行业媒体内搜索。 |
| `guanlan search "BLACKPINK K-pop comeback" --profile hybrid --scope jp_kr_entertainment` | 在日韩娱乐、K-pop/J-pop、Soompi、Oricon、Natalie、Naver 等来源内搜索。 |
| `guanlan search "OpenSSL CVE 最新 漏洞" --scope cybersecurity --trace` | 在漏洞库、厂商安全公告和反诈/安全权威源内搜索。 |
| `guanlan search "台风 路径 中央气象台" --scope weather_disaster --trace` | 在官方气象、灾害和应急信源内搜索。 |
| `guanlan search "梅西 比赛 伤病 最新" --scope sports` | 在体育赛事、伤病、转会和可信体育媒体源内搜索。 |
| `guanlan search "AI 创业 播客 小宇宙" --scope podcast` | 在播客目录、节目页、单集页和 RSS 相关来源内搜索。 |
| `guanlan search "EI会议 投稿 检索" --scope academic` | 在学术数据库、出版商和论文检索相关信源内搜索。 |
| `guanlan search "清华大学计算机系研究生招生 导师" --scope university` | 在高校、研究生招生网和院系官网信源内搜索。 |
| `guanlan search "OpenAI API pricing" --profile english --scope company_primary` | 在英文公司一手资料、文档、价格页和发布说明中搜索。 |
| `guanlan search "AI regulation NIST standard" --profile english --scope global_official` | 在英文官方、监管、标准和公共机构信源中搜索。 |
| `guanlan research "关键词"` | 生成 Agent 可直接使用的研究证据包，并附带版本/叫法冲突、来源时间线和核验建议。 |
| `guanlan research "关键词" --profile china` | 自动路由并按证据角色拆 query，合并 scope/site/open web 候选池。 |
| `guanlan research "影视 综艺 游戏 明星 票房口碑" --preset entertainment --read-top 0` | 用文娱路由整理平台热度、用户评分、产业报道和公开讨论样本。 |
| `guanlan research "OpenAI API pricing release notes" --preset company --profile english` | 用英文公司/产品一手资料模板生成研究证据包。 |
| `guanlan research --list-presets` | 查看研究模板和默认 scope/site 策略。 |
| `guanlan research "关键词" --format context` | 输出适合直接放进 prompt 的研究上下文。 |
| `guanlan research "关键词" --format prompt --prompt-style evidence` | 输出本地模型联网 Prompt，可指定证据型/决策型等风格。 |
| `guanlan research "关键词" --route-chart` | 追加 ASCII 路由诊断图，展示意图、证据角色和 scope 权重。 |
| `guanlan research "关键词" --advisor` | 在证据包后追加助理视角规则，帮助 Agent 基于证据生成建议。 |
| `guanlan research "关键词" --advisor --advisor-style risk` | 按风险/决策/策略等风格生成更自然的 Agent 作答骨架。 |
| `guanlan compare "A" "B" --focus "价格 口碑" --limit 80` | 对多个对象分别建证据包，再按官方/媒体/用户样本/近期动态/风险维度做对比。 |
| `guanlan timeline "某政策 最新进展" --limit 80` | 从宽候选池里抽取带日期的事件线索，并把无日期但可能重要的证据单列出来。 |
| `guanlan dossier "某公司" --focus "业务 口碑 风险" --limit 80` | 生成一个实体研究档案：信源概览、分面证据、近期时间线、待核验问题和下一步命令。 |
| `guanlan prompt "问题"` | 快速生成 Ollama / LM Studio / Open WebUI 可用的联网 Prompt。 |
| `guanlan context "问题"` | `prompt` 的别名，适合在本地 Agent 工作流里表达“给模型上下文”。 |
| `guanlan prompt "问题" --style decision` | 为本地模型生成决策型/证据型/简洁型/深度型联网 Prompt。 |
| `guanlan report html --input results.json --output report.html` | 旁支静态 HTML 报表渲染，只读取已有 JSON/stdin/demo 数据，不触发搜索、阅读或归档。 |
| `guanlan research "关键词" --sites zhihu.com,weibo.com` | 按多个指定站点生成平台定向证据块。 |
| `guanlan pulse "关键词"` | 安全版话题回响分析，输出讨论倾向、关键词信号和明确边界。 |
| `guanlan feeds curated --limit 80` | 读取公开精品 RSS，发现技术、AI、产品和商业科技内容；外部源超时时会优先返回最近成功缓存并标记 `stale_cache`。 |
| `guanlan feeds curated --category ai --min-score 85` | 按分类和评分筛选高质量内容。 |
| `guanlan feeds baidu-rss --limit 80` | 读取动态百度实时热点 RSS，补充热榜词和热度信号。 |
| `guanlan feeds wechat-rss --limit 80` | 读取动态微信热门文章 RSS，补充公众号热文线索。 |
| `guanlan feeds curated-sources --keyword AI` | 从公开 OPML 中检索精品 RSS 源目录。 |
| `guanlan feeds list` | 查看 RSS 信源定位、内容方向、质量口径和路由建议。 |
| `guanlan hotnews today --trends` | 多源热榜归并成趋势簇，观察中文互联网当日水势。 |
| `guanlan hotnews today --brief` | 生成今日水势简报、来源分布、边界提醒和后续查询建议。 |
| `guanlan read "URL"` | 读取网页并转成 Markdown。 |
| `guanlan read "URL" --trace` | 展示 Jina/direct/fallback 路径和正文质量评分。 |
| `guanlan read "URL" --quality-report` | 输出正文占比、噪声、可用性和后续补读建议。 |
| `guanlan read "URL" --strict` | 宁可触发 fallback，也尽量不把脏正文直接交给 Agent。 |
| `guanlan read "URL" --backend direct --extract metadata` | 只提取标题、摘要、作者、发布时间等网页元信息。 |
| `guanlan read "URL" --format prompt --question "问题"` | 把网页正文包装成本地模型 Prompt。 |
| `guanlan read batch urls.txt --format context` | 批量读取 URL 列表并输出紧凑上下文。 |
| `guanlan read batch urls.txt --concurrency 4 --format context` | 显式并发批量阅读；默认仍为串行，避免基础路径行为突变。 |
| `guanlan mcp config --client codex` | 输出可复制的 MCP 客户端配置。 |
| `guanlan read "URL" --watch` | 保存/比较本地快照，输出内容变化 diff。 |
| `guanlan read "URL" --backend direct` | 绕过 Jina Reader，直接读取原网页。 |
| `guanlan archive add "URL"` | 将网页读取为 Markdown 后沉淀进本地知识库。 |
| `guanlan archive ingest-search "关键词"` | 联网 research 一次，并把精选代表证据自动沉淀进本地知识库；不是本地库内搜索。 |
| `guanlan archive ingest-research "关键词"` | `ingest-search` 的语义别名，更适合 Agent 记忆“研究入库”。 |
| `guanlan archive search "关键词"` | 在本地知识库中检索已归档材料。 |
| `guanlan archive search "关键词" --trace` | 展示命中词、命中字段、排序分数和检索边界。 |
| `guanlan archive embed --backend local` | 显式建立本地轻量语义侧车；不联网、不替代 FTS。 |
| `guanlan archive search "关键词" --semantic` | 使用已建立的语义侧车检索；无侧车时回退到 FTS/LIKE 并保留边界。 |
| `guanlan archive inspect 1` | 查看单条归档的正文、元数据和内容诊断。 |
| `guanlan archive reindex` | 重建 SQLite FTS 索引，修复索引/正文不一致。 |
| `guanlan archive verify` | 体检本地库：索引一致性、空正文、样本召回、RAG/Wiki 就绪度。 |
| `guanlan archive context "问题"` | 从本地库生成给 Agent/本地模型的证据上下文。 |
| `guanlan archive wiki build --output ./guanlan-wiki` | 把本地库组织成静态 Markdown/HTML Agent Wiki。 |
| `guanlan archive wiki context "问题"` | 从 Agent Wiki/本地库生成 prompt-ready 上下文。 |
| `guanlan archive pack "问题" --format langchain-jsonl --output pack.jsonl` | 把本地命中资料打包给 RAG/本地模型加载器。 |
| `guanlan archive stats --quality` | 查看本地库阅读质量、入库审计和 RAG-ready 概览。 |
| `guanlan archive export --format jsonl --source-type 政府` | 按 domain/source_type/topic 导出 RAG 友好 JSONL。 |
| `guanlan archive export --format rag-jsonl --min-quality 60` | 只导出达到阅读质量阈值的 RAG 材料。 |
| `guanlan archive export --format llamaindex-jsonl` | 导出为 LlamaIndex 常见的 `text + metadata` JSONL。 |
| `guanlan archive export --format langchain-jsonl` | 导出为 LangChain 常见的 `page_content + metadata` JSONL。 |
| `guanlan archive export --format openwebui-jsonl` | 导出为 Open WebUI/通用导入更容易处理的 `content + metadata` JSONL。 |
| `guanlan archive export --format rag-jsonl` | 只导出 RAG 载入常用字段：id/text/source/title/domain/source_type/topic。 |
| `guanlan serve --host 127.0.0.1 --port 8765` | 启动本地只读 HTTP 服务。 |
| `guanlan serve --print-token` | 生成一个只读 HTTP token，便于安全暴露给本机工作流。 |
| `guanlan serve --host 0.0.0.0 --token "$TOKEN"` | 如必须暴露给局域网/服务器，启用只读 token 校验。 |
| `guanlan plugin template my_company_api` | 生成企业内部只读搜索 connector 模板。 |
| `guanlan eval scenarios --format jsonl` | 输出中文语境搜索质量评估集。 |
| `guanlan eval tasks --format jsonl` | 输出真实中文研究任务池骨架，用于 live/manual benchmark。 |
| `guanlan eval benchmark` | 跑离线确定性评测，检查路由、证据角色和候选池是否守住 Agent 契约。 |
| `guanlan quality run` | 一键跑搜索/阅读/热榜/advisor 质量闸门。 |
| `guanlan quality foundational` | 发版前检查轻重分流、默认候选池和基础工作流不回退。 |
| `guanlan quality coverage` | 发版前检查默认结果池和证据字段没有缩水。 |
| `guanlan quality regression` | 发版前检查结果池、来源多样性、RSS 兜底、正文抽取和 advisor 动态性没有退化。 |
| `guanlan quality robustness` | 更深的稳健性闸门，检查 Archive 入库审计、Agent 字段契约、空结果解释和发布脚本完整性。 |
| `guanlan quality performance` | 确定性性能护栏，检查显式并发、语义侧车 opt-in 和默认候选池不缩水。 |
| `guanlan quality live-smoke --limit 5` | 可选外网 smoke，用于观察源站/网络波动；默认不阻断发版。 |
| `scripts/release_gate.sh` | 维护者发版前一键跑静态检查、全量测试、质量闸门、构建、安装 smoke 和版本核对。 |
| `guanlan hotnews today --limit 80` | 拉取原生多源中文热榜。 |
| `guanlan profile set china` | 切换到中文场景画像。 |
| `guanlan configure --from-browser chrome` | 显式从浏览器提取支持平台的 Cookie。 |
| `guanlan skill --install` | 将观澜使用说明安装到 Agent skills 目录。 |

工作流分流遵循“轻任务不打扰，重任务不偷懒”：简单官网、链接、事实查找继续走 `search/read`；政策、财经、安全、医疗、法律、复杂对比、时间线和档案类问题才升级到 `research/investigate/compare/timeline/dossier`。

默认候选池从 `v0.1.10` 起按 Agent 研究场景放大：`search`、`research`、`archive search` 默认 80 条，`feeds` 默认 80 条，`hotnews` 默认 80 条且 MCP 最高 100 条，`read` 的搜索兜底默认 20 条。`v0.2.5` 增加 Coverage Guard，发版前会检查这些下限和关键证据字段，避免下游 Agent 因更新拿到的材料大面积变少。

## 0.5.0 级上层工作流

`workflow`、`investigate`、`sources` 和 `eval suite` 是上层增强，不接管基础搜索。

- `workflow`：本地轻重分流，判断 direct/guided/investigate。
- `investigate`：显式深查，支持 `--budget light|standard|deep` 和 `--dry-run`。
- `sources`：只读信源矩阵，解释来源身份、角色、风险和适用边界；`audit/export` 用来治理口径漂移。
- `eval suite`：公开离线基准和 live 样本池，用来证明路由和工作流是否守住 Agent 契约。
- `archive semantic`：显式本地语义侧车，不联网、不替代 FTS，专为 RAG/本地模型长期记忆准备。
- `performance guard`：只守确定性性能边界，不把真实网络波动写进阻断式 release gate。

这些能力遵循“轻任务不打扰，重任务不偷懒”：简单查找继续 `search/read`，复杂研究才上升到 `investigate`。

## 使用场景与案例

下面这些例子按真实使用场景组织，可以直接复制到终端里跑。观澜的默认思路是：先用公开搜索看水势，再追原文辨源流，最后把证据整理成 Agent 可以继续推理的上下文。

### 1. 快速查一个中文问题

适合“先给我找一圈资料”“看看公开网页上有什么线索”。

```bash
guanlan search "AI 眼镜 产业链" --profile china --limit 80
guanlan search "AI 眼镜 产业链" --profile china --format context
guanlan search "AI 眼镜 产业链" --profile china --source-chart
```

`--format context` 会输出更紧凑的证据表格，适合直接放进 Agent prompt。
`--source-chart` 会追加来源类型和域名分布，帮助判断这轮结果是偏官方、偏社交、偏商业媒体，还是来源比较均衡。

### 2. 查近期热点、最新动态和时效性问题

适合“最近有什么进展”“今天/本周有什么热点”“某事件最新消息”。观澜会识别 `最近`、`近期`、`热点`、`热搜`、`最新`、`快讯` 等词，把搜索词补上当前年月，并在排序时优先近期结果、降权明显陈旧内容。

```bash
guanlan search "最近 AI 眼镜 热点" --profile china --limit 80 --trace
guanlan search "本周 跨境电商 热点" --profile china --scope ecommerce --format context
guanlan research "最新 人工智能 政策 进展" --preset policy --read-top 5
```

如果要排查为什么某条排在前面，加 `--trace` 查看 `recency_boost`、`stale_penalty`、结果日期和是否落在时间窗口内。

### 3. 查政策、部委通知和官方原文

适合政策研究、监管变化、行业规则、政府公告。优先找原文，不用媒体解读替代政策文本。

```bash
guanlan search "人工智能 政策" --profile china --scope gov --limit 80
guanlan research "人工智能 政策" --preset policy --read-top 5 --max-read-chars 2400
```

如果想看宏观表述和权威报道，可以切到党央媒与中央重点媒体：

```bash
guanlan search "人工智能 新质生产力" --profile china --scope party_central --limit 80
guanlan research "人工智能 新质生产力" --preset official --read-top 5
```

### 4. 查地方政策和核心地方官媒

适合地方产业、城市治理、区域政策、地方舆论表述。

```bash
guanlan search "低空经济 广东 政策" --profile china --scope local_official --limit 80
guanlan research "低空经济 广东 政策" --preset local --read-top 5
```

### 5. 查产业、电商和垂类媒体

适合跨境电商、零售、新消费、平台生态、产业带研究。这里会优先利用亿邦动力、网经社、雨果跨境、联商网等垂类信源。

```bash
guanlan search "跨境电商 AI 工具" --profile china --scope ecommerce --limit 80
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

### 7. 查文娱、影视、综艺、游戏和明星口碑

文娱路由适合票房、播放量、豆瓣评分、粉圈争议、游戏评价和内容消费判断。它不会把结果硬限制在白名单里，而是优先让 Agent 分清平台数据、用户评分、产业报道、宣发通稿和公开讨论样本。

```bash
guanlan research "某电影 票房 豆瓣评分 最近热议" --preset entertainment --read-top 0 --format context
guanlan search "某综艺 口碑 争议" --profile china --scope entertainment --limit 80
guanlan research "Taylor Swift 最新动态 新专辑 巡演" --preset global_entertainment --profile english --format context
guanlan research "BLACKPINK K-pop 最新回归 Soompi Oricon" --preset jp_kr_entertainment --profile hybrid --format context
guanlan pulse "某明星 最近评价" --profile china --limit 80 --format context
```

如果你只想看某个平台的公开网页结果：

```bash
guanlan search "某产品 用户评价" --profile china --site zhihu.com --limit 80
guanlan search "某产品 使用体验" --profile china --site bilibili.com --limit 80
```

`pulse` 只给“基于当前公开样本的讨论倾向”，不是全网舆情结论。默认不读原文；如果需要更强证据，可以显式加 `--read-top 2`。

### 8. 查技术选型和开发者反馈

适合框架对比、开源项目调研、工程实践、社区反馈。

```bash
guanlan research "Python Agent 框架 对比" --preset tech --read-top 5
guanlan search "LangGraph AutoGen CrewAI 对比" --profile china --scope tech_dev --format context
guanlan feeds curated --category ai --limit 80
```

科技、AI、开发者、工程实践类问题有一条硬规则：必须额外补一轮 RSS/精品内容流。`research --preset tech` 会自动把 `feeds curated` 纳入候选池和 `result_groups`；如果 Agent 只使用 `route` 或 `search`，则需要再跑 `guanlan feeds curated --limit 80` 或 `guanlan feeds curated --category ai --limit 80`。RSS 只作为阅读发现和新鲜线索，不替代官方文档、代码仓库、issue、benchmark 原文。

### 9. 查学术会议、投稿和检索要求

适合 EI/SCI/Scopus、学术会议、论文投稿、数据库检索、会议 CFP 和学校/单位认定口径。

```bash
guanlan research "EI会议 投稿 检索 要求" --preset academic --read-top 0
guanlan search "EI会议 投稿 检索" --profile china --scope academic --format context
```

### 10. 查高校招生、导师和院系官网

适合研究生招生、导师名单、院系介绍、招生目录、招生简章、推免复试和培养方案。它和 `academic` 不同：`academic` 主要查论文数据库/出版商/会议检索，`university` 主要查高校与院系官方页面。

```bash
guanlan research "清华大学计算机系研究生招生 导师" --preset university --read-top 0
guanlan search "清华大学计算机系研究生招生 导师" --profile china --scope university --format context
```

这类问题会优先区分数据库/出版商口径、会议 CFP、学校或单位认定口径和经验帖；不要把 SEO 代投文章当成最终标准。

### 高阶研究工作流：对比、时间线和档案

当用户不是简单问“搜一下”，而是要“帮我比较”“梳理脉络”“整理一个完整档案”，可以直接使用三类高阶工作流。它们仍然基于 `research` 的公开证据包，不替代事实核验，但能让下游 Agent 少做很多结构化整理。

```bash
guanlan compare "LangGraph" "AutoGen" "CrewAI" --focus "中文资料 技术选型 社区反馈" --preset tech --limit 80 --format context
guanlan timeline "低空经济 广东 政策 最新进展" --preset local --limit 80
guanlan dossier "某公司" --focus "业务 口碑 风险 近期动态" --limit 80 --read-top 5
```

三者适用边界：

- `compare`：适合多产品、多公司、多政策方案、多技术路线对照；它会按官方/产业/用户样本/近期动态/风险维度提示“证据足不足”。
- `timeline`：适合近期进展、事件演变、政策发布、版本发布；日期来自公开材料可见线索，缺日期的重要证据会单列。
- `dossier`：适合做公司、产品、政策、事件的研究档案；输出的是可继续补证的骨架，不是最终定论。

### 11. 读取单篇文章或网页

适合用户给你一个 URL，希望你读完再总结。默认会先尝试更干净的阅读路径，再按情况降级。

```bash
guanlan read "https://example.com/article" --max-chars 12000
guanlan read "https://example.com/article" --format context
```

如果 Jina Reader 在中国网络环境里不稳定，或网页被转写得不完整，可以显式走直连：

```bash
guanlan read "https://example.com/article" --backend direct --max-chars 12000
```

如果要排查正文为什么脏、为什么走了某个后端，打开 trace：

```bash
guanlan read "https://example.com/article" --trace
guanlan read "https://example.com/article" --format json --trace
```

`--trace` 会显示 Jina、direct、search fallback 的尝试顺序、最终选中的后端、正文质量标签（`clean/noisy/weak/fallback`）、噪声命中和乱码判断。

如果你宁可少给，也不想让 Agent 吃进导航、登录按钮、页脚和广告，可以打开严格模式：

```bash
guanlan read "https://example.com/article" --strict --trace
```

直连读取还可以只抽某一类信息：

```bash
guanlan read "https://example.com/article" --backend direct --extract metadata
guanlan read "https://example.com/article" --backend direct --extract links
```

`metadata` 适合核验标题、摘要、作者、发布时间；`links` 适合让 Agent 看页面里真正指向了哪些原文或相关材料。

### 12. 批量读取一组链接

适合 Agent 已经搜到一批材料，需要统一读成上下文。

```bash
cat > urls.txt <<'EOF'
https://example.com/a
https://example.com/b
EOF

guanlan read batch urls.txt --format context --cache-ttl 3600
```

批量读取会对微博、小红书、抖音、Twitter/X、LinkedIn 等高风险社交域名保留更谨慎的边界，避免不透明地触碰登录态。

### 13. 追踪网页变化

适合政策页、公告页、价格页、项目 README 这类“今天和上次有什么不同”的任务。

```bash
guanlan read "https://www.gov.cn/" --watch
guanlan read "https://github.com/shenyangs/Guanlan" --watch
```

第一次运行会保存本地快照；之后再次运行，会输出内容变化 diff。

### 14. 看中文热榜，再顺藤摸瓜

适合“今天有什么热点”“国内讨论在往哪里流”。

```bash
guanlan hotnews list
guanlan hotnews today --limit 80
guanlan hotnews weibo --limit 80
guanlan hotnews bilibili --limit 80
guanlan hotnews ithome --limit 80
guanlan hotnews v2ex --limit 80
guanlan hotnews newsnow:36kr-quick --limit 80
guanlan hotnews tophub:weibo --limit 80
guanlan hotnews tophub:catalog:news --limit 80
guanlan hotnews uapis:catalog --limit 80
guanlan hotnews vvhan:all --limit 80
```

`today` 是默认推荐入口，会把百度热搜、微博热搜、B站热门视频、IT之家 RSS 和 V2EX 热门混合成一个多源快照；其中单个公开端点失败时不会拖垮其它来源。

如果想让 Agent 先看一份更像“今日水势”的简报：

```bash
guanlan hotnews today --limit 80 --brief
guanlan hotnews today --limit 80 --trends --brief
```

`--brief` 会输出来源分布、边界提醒、值得追踪的趋势，以及每个趋势后续可交给 `research` 的查询建议。

`--trends` 会额外标出跨平台共振、单平台孤岛风险和可继续追踪的 research 命令。观澜不会把单平台水花直接说成全网趋势。

`newsnow:<source>` 是可选增强后端，适合补 36氪、B站热搜、财联社、华尔街见闻等更多来源；稳定性取决于 NewsNow BASE_URL、Cloudflare 和上游抓取状态。公共站不稳时可配置自己的 NewsNow：

```bash
guanlan configure newsnow-base-url https://your-newsnow.example
guanlan hotnews newsnow:ithome --limit 80
```

`tophub:*`、`uapis:*`、`vvhan:*` 是外部热榜聚合旁支，用来补 TopHub、UAPI、HotList/VVHan 的更大信源池。观澜会把这些条目标记为 `external_backend` / `third_party_aggregation`，并做本地缓存兜底；如果上游返回旧快照或无法解析，不会把它误报成“没有热点”。

`zhihu` 热榜是实验源，部分环境会返回 401/403。需要知乎视角时，优先把它当作可选尝试；失败后用站内搜索兜底：

```bash
guanlan hotnews zhihu --limit 80
guanlan search "热点关键词" --site zhihu.com --profile china --limit 80
```

看到关键词后，可以继续交给 `search` 或 `research` 追原文：

```bash
guanlan research "热榜里的关键词" --profile china --format context
```

### 15. 解释搜索结果为什么这样排

适合排查“为什么这个结果在前面”“有没有缓存”“是不是 scope 生效了”。

```bash
guanlan search "跨境电商 AI" --profile china --scope ecommerce --trace
guanlan search "最新 人工智能 政策" --profile china --cluster-threshold conservative --trace
```

`--trace` 会展示后端顺序、缓存命中、评分因子、query_quality、topic 聚类、来源分类和时效性判断，方便 Agent 把检索过程讲清楚。

从 `0.2.4` 开始，trace 还会显示 `query_strategy`：观澜会把一个问题拆成官方原文、权威报道、用户样本、行业材料、近期进展等不同证据角色。`research` 会用这些 query 变体分头搜索，再合并去重，避免一个宽泛 query 把水面看窄。

从 `0.3.7` 开始，`query_strategy` 还会暴露 `time_window` 和 `search_quality_v2`：涉及“近期、最近、热点、最新”等问题时，Agent 会被提醒按时间窗口解释结果，窗口外材料只作为背景；同时保持 80-100 的较大候选池，先宽取再筛选。

从 `0.2.5` 开始，每条搜索结果还会带 `evidence_role`，例如 `official_primary`、`authoritative_report`、`user_sample`、`industry_report`。如果结果池缺少某类关键证据，`search --trace` 会给出“缺什么信源、建议补什么”的提示。

### 16. 给 AI Agent 的最短工作流

如果你是在另一个 Agent、MCP 客户端或自动化脚本里调用观澜，优先使用这几类输出：

```bash
guanlan search "问题" --profile china --format context
guanlan route "问题"
guanlan search "最近 问题 热点" --profile china --format context --trace
guanlan research "问题" --preset policy --format context --source-chart
guanlan research "产品 用户评价" --preset reputation --read-top 0 --format context
guanlan prompt "问题" --profile china
guanlan pulse "产品 用户评价" --format context
guanlan read batch urls.txt --format context --cache-ttl 3600
guanlan archive search "问题" --format context
guanlan hotnews today --trends
```

CLI 是默认主路径；如果当前 Agent 或平台支持 MCP，可以把 `guanlan-mcp` 作为可选集成接进去，让 Agent 直接调用 `guanlan_search`、`guanlan_read`、`guanlan_research`、`guanlan_pulse`、`guanlan_hotnews`、`guanlan_archive_search` 和 `guanlan_status`。

**Agent 外层 timeout 建议**

观澜内部会给单个网页、RSS 和热榜源设置请求超时，防止一个上游无限卡住；但 Agent/MCP/自动化平台包住整个命令时，要给组合流程更大的外层 timeout。建议：

| 命令场景 | 外层 timeout |
| --- | --- |
| `status`、`doctor`、`search`、单 URL `read` | 60-90 秒 |
| `hotnews`、`feeds`、`pulse`、`read batch` | 120 秒 |
| `research`、`compare`、`timeline`、`dossier`、`archive ingest-research` | 180-300 秒 |
| 安装、升级、发布 smoke、Homebrew/PyPI 校验 | 300-600 秒 |

如果超时，先重试一次；支持缓存的命令可加 `--cache-ttl 3600`。严肃研究优先降低 `--read-top` 到 0 或 1，而不是把 `--limit 80` 砍成很小样本。超时只能说明本轮网络或上游源未完成，不代表没有证据。

### 17. 本地大模型联网

很多本地模型本身没有搜索网页和读取网页的能力，例如通过 Ollama、LM Studio、llama.cpp、Jan、Open WebUI 或本地 Agent 运行的模型。观澜可以作为它们的联网前置器：先由观澜搜索、阅读和整理中文互联网证据，再把证据包交给本地模型回答。

最简单的方式是直接生成完整 Prompt：

```bash
guanlan prompt "最近 AI 眼镜 在中国市场有什么变化？" --profile china > context.md
ollama run qwen3:latest < context.md
```

`guanlan context` 是同一个能力的别名，更适合在 Agent 脚本里表达“先取联网上下文，再交给本地模型”：

```bash
guanlan context "今天中文互联网有哪些 AI 技术文章值得读？" --profile china --read-top 1 > context.md
ollama run qwen3:latest < context.md
```

如果你希望本地模型按不同方式输出，可以选择 Prompt 风格：

```bash
guanlan prompt "这个产品现在值不值得买？" --preset reputation --style decision > prompt.md
guanlan prompt "新质生产力 最新政策影响" --preset policy --style evidence > prompt.md
guanlan prompt "今天中文互联网 AI 相关热点" --style concise > prompt.md
```

`decision` 更适合行动建议，`evidence` 更适合证据表，`concise` 更适合短上下文模型，默认 `deep` 更适合完整调研。

如果你想自己控制证据包，可以用 `--format prompt`：

```bash
guanlan research "跨境电商 AI 工具 趋势" --preset ecommerce --format prompt > prompt.md
guanlan search "新质生产力 政策 原文" --profile china --scope party_central --format prompt > prompt.md
guanlan read "https://example.com/article" --format prompt --question "请提炼这篇文章的关键信息" > prompt.md
```

如果本地模型要做更复杂的研究整理，可以先让观澜输出结构化上下文，再交给模型写答案：

```bash
guanlan compare "产品A" "产品B" --focus "价格 口碑 风险" --format context > context.md
guanlan timeline "某事件 最新进展" --limit 80 --format context > context.md
guanlan dossier "某公司" --focus "业务 口碑 风险" --format context > context.md
ollama run qwen3:latest < context.md
```

如果本地 Agent 支持 MCP，可以生成配置：

```bash
guanlan mcp config --client codex
guanlan mcp config --client openwebui
```

如果工具不支持 MCP，可以启动只读 HTTP 服务：

```bash
guanlan serve --host 127.0.0.1 --port 8765
```

服务默认只监听本机，提供 `/search`、`/research`、`/compare`、`/timeline`、`/dossier`、`/read`、`/hotnews`、`/feeds`、`/route`、`/context`、`/prompt` 和 `/archive/search` 等只读接口，不提供发布、评论、点赞、私信等写操作。如果必须监听 `0.0.0.0` 或局域网地址，请使用 `--token` 或 `GUANLAN_SERVE_TOKEN`，请求侧通过 `Authorization: Bearer <token>` 或 `X-Guanlan-Token` 传入；否则虽然只读，也可能暴露本地 archive 内容和搜索行为。对本地模型来说，推荐工作流是：

1. 用 `hotnews --brief` 或 `route` 判断该去哪找。
2. 用 `search/research --format context` 拿证据表。
3. 用 `read --quality-report` 或 `read --trace` 检查关键原文质量。
4. 把 `prompt` 或 `context` 交给本地模型，让它基于来源回答。

如果你的本地工具能发 HTTP 请求，可以直接取 Prompt：

```bash
curl -s http://127.0.0.1:8765/context \
  -H 'content-type: application/json' \
  -d '{"query":"最近 AI Agent 在中国的产品化进展","profile":"china","read_top":1}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["prompt"])'
```

### 18. 把读过的网页沉淀成本地知识库

适合把 Agent 搜过、读过、核验过的材料保存下来，后续不用重复请求上游，也能导出给 RAG 系统。

```bash
guanlan archive add "https://example.com/article"
guanlan archive add batch urls.txt
guanlan archive ingest-research "人工智能 政策" --limit 80 --dry-run
guanlan archive ingest-research "人工智能 政策" --limit 80
guanlan archive list --limit 20
guanlan archive search "人工智能 政策" --format context --trace
guanlan archive inspect 1
guanlan archive stats
guanlan archive reindex
guanlan archive verify
guanlan archive context "人工智能 政策" --limit 20
guanlan archive wiki build --output ./guanlan-wiki --format both
guanlan archive wiki context "人工智能 政策"
guanlan archive pack "人工智能 政策" --format langchain-jsonl --output guanlan-pack.jsonl
guanlan archive export --format jsonl > guanlan-archive.jsonl
guanlan archive export --format rag-jsonl > guanlan-rag.jsonl
guanlan archive export --format llamaindex-jsonl > guanlan-llamaindex.jsonl
guanlan archive export --format openwebui-jsonl > guanlan-openwebui.jsonl
```

本地知识库默认保存在 `~/.guanlan/archive.db`。当前使用 SQLite FTS/LIKE 检索，不依赖外部 embedding 服务；`archive search` 会对中文短语和技术词做宽召回并排序，适合快速复用已读材料，但不是向量语义搜索。`archive search --trace` 会说明命中词、字段、排序分数和 `semantic=not-vector` 边界，方便 Agent 判断是否需要补搜。`archive verify` 会体检索引一致性、空正文、样本召回和 RAG/Wiki 就绪度，适合在把本地库交给 Agent 或 RAG 前先跑一遍。

`archive ingest-search` / `archive ingest-research` 的行为是“联网研究并入库”，如果只想查本地库，请使用 `archive search` 或 `archive context`；写入前可用 `--dry-run` 预览。观澜会为每个候选生成 `ingest_audit`，解释相关性、平台首页、重复候选、正文厚度和漂移风险，跳过明显低相关或平台首页结果。归档元数据会保留 `source_card`、`read_quality`、`quality_report`、`route_plan`、`query_strategy` 和 `ingest_audit`，方便后续接 RAG 时知道材料的来源角色、正文质量、检索路径和入库理由。

Agent Wiki 是 archive 的旁支组织层，不是全网知识库。`archive wiki build` 会把已归档资料导出成静态 Markdown/HTML，按 topic/source/domain 组织，并把低质量材料标为 candidate；`archive wiki context` 和 `archive context` 则更适合给 LM Studio、Ollama、Open WebUI 或其他 Agent 准备证据约束的上下文。`rag-jsonl` 会把每条材料收束成 `id/text/source/title/domain/source_type/topic/updated_at`；`llamaindex-jsonl`、`langchain-jsonl`、`openwebui-jsonl` 是面向常见本地 RAG/加载器的结构化导出。它不是云同步，也不会自动上传内容。

### 19. 质量闸门

适合维护者和高级用户在发版前快速检查“观澜是不是真的更好了”。

```bash
guanlan quality run
guanlan quality run --format json
guanlan quality run --coverage
guanlan quality foundational
guanlan quality coverage
guanlan quality regression
guanlan quality robustness
guanlan eval benchmark
guanlan eval tasks --format jsonl
guanlan quality live-smoke --limit 5
scripts/release_gate.sh
guanlan quality run --mode live --limit 5
```

默认 `quick` 模式不依赖网络，会检查搜索排序、中文错配、正文质量评分、趋势归并和 advisor 自然度；`live` 模式会额外跑少量真实网络探测。

`quality foundational` 是轻重分流和基础能力护栏：检查简单任务仍保持 direct、政策/高风险任务会升级 guided、对比/档案任务会进入 investigate，同时确认默认候选池不缩水。

`quality coverage` 是给发版用的防缩水护栏：检查 `search/research/archive/hotnews/read fallback` 的默认结果池下限，检查搜索结果是否保留 `evidence_role`，检查 research/read/archive 是否保留质量元数据。它不保证每个网络请求都成功，但能防止一次更新把 Agent 赖以判断的信息面悄悄变窄。

`quality regression` 是更完整的发版回归闸门：除默认结果池外，还检查来源多样性、RSS 缓存兜底元数据、正文主体抽取信号和 advisor 是否会随任务变化。它的目标很朴素：每次更新，都不能让下游 Agent 拿到的材料突然变少、变窄、变脏。

`quality robustness` 是更深一层的稳健性闸门：它检查 Archive 入库前是否会审计噪声和漂移，检查本地库 `search --trace` / `inspect` / `rag-jsonl` 是否保留 Agent 需要的字段，检查空结果是否解释下一步，也检查发布脚本是否覆盖完整验收链路。

`eval benchmark` 是更偏“观澜契约”的离线评测：不依赖外网，固定检查政策、口碑、热点、技术、学术、地方、电商和本地模型场景是否被路由到合适的意图、scope、证据角色和足够大的候选池。

`eval tasks` 是真实中文研究任务池骨架，覆盖政策、地方、电商、技术、口碑、热点、学术和本地模型联网。它先用于人工/半自动评测，不替代 `eval benchmark` 的离线发布闸门。

如果要做更接近真实使用的横向比较，可以参考 [Benchmark 说明](benchmark.md)：同一任务分别跑普通搜索、`guanlan search --trace`、`guanlan route + research`，再看是否命中正确信源家族、是否保留来源身份、证据角色、候选池深度和漂移控制。观澜不是只比“搜到几条”，更要比 Agent 最后拿到的材料是否足够稳、足够明源。

### 20. 安全检查和授权边界

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
guanlan route "某产品 用户评价 值不值得买"
guanlan research "人工智能 新质生产力" --profile china --scope party_central
guanlan research "跨境电商 AI" --profile china --scope ecommerce --read-top 3
guanlan research "某产品 用户评价" --profile china --site zhihu.com --read-top 0
guanlan research "某产品 用户评价" --preset reputation --sites zhihu.com,weibo.com,xiaohongshu.com
guanlan research "某产品 用户评价" --preset reputation --read-top 0 --advisor
```

`research` 会把搜索结果、同题聚类、信源多样性和原文摘读整理成一份更适合 Agent 消化的证据包。

`route` 会先解释“为什么这样搜”：识别需求标签，给出优先 scope、推荐站点、证据角色、风险提醒和查询改写。它是软路由，不会把世界缩小成白名单；`research` 会把优先信源和开放网页兜底一起纳入候选池，避免信源池过窄。

如果用户需要建议、下一步、风险提醒，或希望你判断“他为什么搜这个”，加 `--advisor`。助理视角规则会告诉 Agent 当前证据能支持什么、不能支持什么，以及回答时必须守住哪些边界；最终建议应由 Agent 结合用户问题自然生成，不能机械复述模板，也不能当作用户真实目的或高风险专业结论。

Preset 会自动选择多组 scope 和平台定向站点。例如 `policy` 会查 `gov + party_central`，`reputation` 会查 `social_web + tech_dev + business`，`entertainment` 会查 `entertainment + social_web + business` 并补充豆瓣、猫眼/灯塔、B站、微博、TapTap 等公开页证据块；`global_entertainment` 会查 Variety、Deadline、Hollywood Reporter、Billboard 等欧美文娱源；`jp_kr_entertainment` 会查 Soompi、Oricon、Natalie、Naver 娱乐等日韩源；`cybersecurity`、`weather_disaster`、`sports`、`science`、`career`、`podcast`、`test_prep` 会分别路由到漏洞/反诈、天气灾害、体育、科学、职场、播客和考试备考信源。用户显式传入 `--scope`、`--site` 或 `--sites` 时，以用户指定范围为准。

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

更完整的设计与阶段路线见 [路线图](roadmap.md) 和 [中文互联网设计依据](chinese-web-design.md)。

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
| [中文入口](README_zh.md) | 中文文档导航。 |
| [更新日志](CHANGELOG.md) | 记录每个版本的能力变化、边界调整和下一步收口。 |
| [本地大模型联网指南](local-llm.md) | Ollama、LM Studio、Open WebUI 等无联网模型如何接入观澜。 |
| [Agent 使用说明](agent-usage.md) | 给 AI Agent 的搜索、阅读、热榜和安全路由规则。 |
| [Agent 输出契约](contract.md) | 给 Agent/MCP/HTTP/RAG 集成方看的稳定字段与边界承诺。 |
| [Benchmark 说明](benchmark.md) | 离线契约评测、真实任务池和 live/manual benchmark 方法。 |
| [安装指南](install.md) | 给 Agent 执行的安装流程与边界。 |
| [更新指南](update.md) | 更新观澜与依赖工具。 |
| [排障手册](troubleshooting.md) | 网络、Cookie、钥匙串、平台异常排查。 |
| [Cookie 导出](cookie-export.md) | 手动导出 Cookie 的安全流程。 |
| [来源说明](SOURCE_ATTRIBUTION.md) | 开源参考与来源集中说明。 |

维护者、贡献者或对设计细节感兴趣的读者，可在 [中文入口](README_zh.md) 查看路线图、质量测试、发布自动化、匿名遥测和发布冒烟样本等资料。

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
- 匿名遥测默认发送命令生命周期元数据，用于聚合使用量与并发统计；不发送 query、URL、正文或凭据。可用 `guanlan configure telemetry off` 或 `GUANLAN_TELEMETRY=0` 关闭；如需自托管统计，可配置 `guanlan configure telemetry-endpoint ...`。
- Agent/MCP/HTTP/RAG 集成方可参考 [Agent 输出契约](contract.md)。观澜仍处 Alpha，但这些核心字段不应静默移除或改名。

## 许可证与来源

观澜采用 MIT License。

本项目在设计和工程上参考了若干开源项目，来源集中记录在 [docs/SOURCE_ATTRIBUTION.md](SOURCE_ATTRIBUTION.md)。除来源说明外，项目文档和产品表达以观澜自身定位为准。

如在项目中复用本项目思路或代码，欢迎在文档中注明来源并附仓库链接。
