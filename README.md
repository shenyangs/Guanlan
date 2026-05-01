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
  <a href="#当前能力图谱">能力图谱</a> ·
  <a href="#设计原则">设计原则</a>
</p>

观澜是一个面向 AI Agent 的中文互联网 CLI，用来组织搜索、阅读与信源路由。它把公开搜索、网页阅读、热榜观察、来源分类和显式授权边界放进同一条工作流。

它首先想把这几件事做好：

- **搜得更准**：针对中文语境组织搜索后端、白名单 scope 和来源分类。
- **读得更稳**：在公开网页、Jina Reader、直连 HTML 和搜索兜底之间做降级。
- **边界更清楚**：默认只读、低扰，Cookie、Keychain 和登录态访问都走显式授权。

中文互联网的信息分布并不均匀。公众号、微博、知乎、B站、小红书、抖音、雪球、V2EX、RSS、开发者社区和新闻热榜各自带着不同的语气、圈层与偏见。观澜做的事情，是让 Agent 看见这些波纹，也看见它们各自从哪里来。

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
| 微博 | 热搜、搜索、用户与话题读取 | 可用 |
| 微信公众号 | 搜索与文章阅读的轻量路径 | 可用，需继续增强稳定性 |
| 小红书 | 搜索、笔记读取等能力，依赖外部后端和登录态 | 可选 |
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

**第一步：安装 `uv`**

macOS / Linux：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装后如果终端提示找不到 `uv`，关掉当前终端，重新打开一次。

**第二步：安装观澜**

```bash
uv tool install git+https://github.com/shenyangs/Guanlan.git
```

**第三步：确认能用**

```bash
guanlan version
guanlan doctor
guanlan search "人工智能 新质生产力" --profile china --scope party_central --limit 5
```

看到 `观澜 / Guanlan v0.1.0`，并且 `search` 能返回中文搜索结果，就说明基础部署成功。

以后更新观澜：

```bash
uv tool upgrade guanlan
```

如果更新失败，也可以直接重装：

```bash
uv tool install --force git+https://github.com/shenyangs/Guanlan.git
```

### Agent / 开发者安装

观澜第一版优先以 GitHub 源码发布。推荐用 `uv` 一条命令安装为全局 CLI：

```bash
uv tool install git+https://github.com/shenyangs/Guanlan.git
guanlan doctor
```

如果你使用 `pipx`：

```bash
pipx install git+https://github.com/shenyangs/Guanlan.git
guanlan doctor
```

想先试运行、不持久安装：

```bash
uvx --from git+https://github.com/shenyangs/Guanlan.git guanlan version
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
      "args": ["--from", "git+https://github.com/shenyangs/Guanlan.git", "guanlan-mcp"]
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
| `guanlan status` | 显示渠道运行状态、稳定性标签、授权边界和本地缓存概览。 |
| `guanlan search "关键词"` | 搜索网页，输出适合 Agent 阅读的结果列表。 |
| `guanlan search "关键词" --trace` | 展示评分因子、后端顺序、聚类阈值和缓存命中状态。 |
| `guanlan search "关键词" --cache-ttl 3600` | 一小时内复用同条件搜索结果，降低上游扰动。 |
| `guanlan search "关键词" --format context` | 输出紧凑的 LLM-friendly 证据表格。 |
| `guanlan search "关键词" --backend plugin:my_company_api` | 显式调用本地自定义只读搜索 backend。 |
| `guanlan search "关键词" --scope party_central` | 在党央媒与中央重点媒体白名单内搜索。 |
| `guanlan search "关键词" --scope ecommerce` | 在电商/零售垂类媒体白名单内搜索。 |
| `guanlan research "关键词"` | 生成 Agent 可直接使用的研究证据包。 |
| `guanlan research --list-presets` | 查看研究模板和默认 scope/site 策略。 |
| `guanlan research "关键词" --format context` | 输出适合直接放进 prompt 的研究上下文。 |
| `guanlan research "关键词" --sites zhihu.com,weibo.com` | 按多个指定站点生成平台定向证据块。 |
| `guanlan read "URL"` | 读取网页并转成 Markdown。 |
| `guanlan read batch urls.txt --format context` | 批量读取 URL 列表并输出紧凑上下文。 |
| `guanlan read "URL" --watch` | 保存/比较本地快照，输出内容变化 diff。 |
| `guanlan read "URL" --backend direct` | 绕过 Jina Reader，直接读取原网页。 |
| `guanlan hotnews baidu --limit 10` | 拉取原生中文热榜。 |
| `guanlan profile set china` | 切换到中文场景画像。 |
| `guanlan configure --from-browser chrome` | 显式从浏览器提取支持平台的 Cookie。 |
| `guanlan skill --install` | 将观澜使用说明安装到 Agent skills 目录。 |

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
| [Agent 使用说明](docs/agent-usage.md) | 给 AI Agent 的搜索、阅读、热榜和安全路由规则。 |
| [安装指南](docs/install.md) | 给 Agent 执行的安装流程与边界。 |
| [更新指南](docs/update.md) | 更新观澜与依赖工具。 |
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
