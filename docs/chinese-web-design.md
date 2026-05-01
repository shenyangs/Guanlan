# 观澜 Guanlan 设计方案

本文档记录 观澜 / Guanlan 的产品与技术设计。目标是构建“轻脚手架、可插拔渠道、Agent 直接调用上游工具”的中文互联网能力体系，系统性补齐中国大陆场景：中文搜索、热榜资讯、社交口碑、视频平台、财经、招聘、本地生活和内容发布。

本文档作为当前实现与后续迭代的设计参考，重点说明产品定位、能力边界和架构取舍。

## 0. 项目命名

项目正式名称：**观澜 / Guanlan**。

命名含义：

- `观`：观察、读取、理解中文互联网。
- `澜`：信息流、热点、舆情和平台趋势的波动。
- 不绑定某个具体平台，也不局限于新闻。
- 中文名自然，英文转写简洁，适合作为 CLI/package/plugin 名称。

推荐定位语：

> 观澜：面向 AI Agent 的中文互联网信源与平台路由器。

工程命名建议：

| 场景 | 名称 | 说明 |
| --- | --- | --- |
| 产品名 | 观澜 | 面向中文用户展示 |
| 英文名 | Guanlan | GitHub、包名、英文文档使用 |
| CLI | `guanlan` | 简短，便于命令行使用 |
| Python package | `guanlan` | 当前包名 |
| 配置目录 | `~/.guanlan/` | 独立存放观澜配置 |

## 1. 产品定位

观澜（Guanlan）是一个面向 AI Agent 的中文互联网能力路由器。

它聚焦于中文互联网的搜索、阅读、路由和整理。面对“查一下中文互联网”“看国内平台怎么讨论”“追热点”“读公众号”“研究 A 股/招聘/本地生活”这类任务，Agent 需要知道该走哪个平台、用哪个后端、怎样安全调用、如何把结果整理成可用上下文。

一句话定位：

> 让 Agent 看见中文互联网的潮汐，但默认只读、低频、透明、可控。

### 1.1 面向中文互联网，不等于平台堆砌

“观澜”首先想给 Agent 一套适合中文互联网的研究方法：

- 先看水势：热榜、快讯、社区热门、搜索结果先形成大势判断。
- 再辨源流：区分官方媒体、社区讨论、营销内容、财经快讯、开发者反馈和个人体验。
- 后取其要：把重复信息聚类，把相互矛盾的信息标出，把能追溯的原文链接留下。
- 少扰用户：公开信息优先；Cookie、钥匙串、登录态、写操作都必须显式授权。

工程上对应三条主线：

| 主线 | 目标 |
| --- | --- |
| 搜索生产力 | `guanlan search/read/hotnews` 成为 Agent 默认工具链。 |
| 中文信源图谱 | 将党央媒、政府部委、核心地方官媒、垂类媒体、热榜、公众号、社区、财经、视频和本地生活按信源类型组织。 |
| 安全可信 | 默认不读 Cookie，不碰钥匙串，所有敏感动作前置说明和授权。 |

第一批中文搜索白名单已经按 scope 落地：

| Scope | 说明 |
| --- | --- |
| `party_central` | 党央媒与中央重点媒体，如人民网、新华网、央视网、求是网、光明网等。 |
| `gov` | 政府与部委网站，如中国政府网、外交部、发改委、工信部、商务部、统计局等。 |
| `local_official` | 核心地方官媒，如北京日报、上观、南方网、羊城晚报、新华日报、大众网、大河网、红网等。 |
| `business` | 商业与产业媒体，如 36氪、虎嗅、创业邦、亿欧、亿邦动力等。 |
| `ecommerce` | 电商与零售垂类，如亿邦动力、联商网、网经社、雨果跨境等。 |
| `tech_dev` | 科技与开发者社区，如 V2EX、掘金、SegmentFault、CSDN、少数派、IT之家等。 |
| `finance` | 财经与资本市场，如财联社、华尔街见闻、东方财富、证券时报、财新等。 |
| `social_web` | 社交与内容平台公开页，如微博、小红书、知乎、B站、抖音等。 |

第一版搜索质量层已经落地：

| 能力 | 说明 |
| --- | --- |
| 多后端聚合 | `china` profile 默认按 Baidu、Bing、DuckDuckGo 顺序尝试，聚合后统一排序。 |
| 去重合并 | 同一 canonical URL 只保留一条，并合并来源标记。 |
| 信源分类 | 输出 `source_type`、`matched_scope`、`trust_level`，帮助 Agent 识别信源性质。 |
| 语境优先 | 对亿邦动力这类跨 scope 域名，若用户指定 `--scope ecommerce`，优先按电商垂类解释。 |
| 质量评分 | 综合可信度、摘要、关键词命中、后端顺序和广告迹象生成 `score`。 |
| 同题聚类 | 输出 `topic_key`、`topic_size`、`topic_role`，优先展示同题代表结果，降低转载/镜像对判断的干扰。 |
| 信源多样性 | 对代表结果按 `source_type` 交错排序，让 Agent 更容易获得官方、垂类、社区、财经等多侧面证据。 |
| 研究证据包 | `guanlan research` 整合搜索结果、信源概览和代表结果摘读，作为 Agent 回答前的证据上下文。 |
| 研究模板 | `--preset policy/industry/reputation/tech/...` 按场景自动选择多组 scope、平台定向站点、读取数量和提示语。 |

## 2. 核心原则

### 2.1 只读优先

默认能力聚焦读取、搜索、总结、对比、监控。不默认执行发帖、评论、点赞、私信、关注、打招呼、批量发布等写操作。

写操作如果未来支持，必须满足：

- 用户明确请求。
- Agent 二次确认。
- 默认草稿/预览优先。
- 文档中标注账号风险和平台风控风险。

### 2.2 显式授权

任何读取用户本机浏览器 Cookie、钥匙串、Token、登录态的行为，都必须由用户显式触发。例如：

```bash
guanlan configure --from-browser chrome
```

`doctor`、测试、普通搜索不应自动读取浏览器 Cookie。此前雪球检查触发 macOS 钥匙串弹窗，说明这个边界必须作为硬规则写进设计。

### 2.3 多后端 fallback

中国平台接口变化快、风控强，不能把单个平台或单个开源工具当成唯一方案。每个重要能力都应有：

- 主后端。
- 降级后端。
- 浏览器 fallback。
- 失败诊断文案。

网页阅读尤其如此。Jina Reader 可以作为第一读取入口，但在中国大陆地区会遇到几类结构性问题：

- 外部公共服务访问国内站点时，可能受跨境链路、机房 IP、目标站点风控影响。
- 微信公众号、小红书、微博、知乎等站点常有 JS 渲染、登录墙、验证码、移动端跳转和反爬策略。
- 国内站点对非浏览器 UA、无 Cookie 请求、短时间重复请求和境外网络更敏感。
- 一些页面即使返回 200，也可能只返回壳、错误页、验证码页或不完整正文。

因此 `guanlan read` 应采用三段式：

```text
Jina Reader -> Direct HTML fallback -> Search-as-context fallback
```

当前三段已经形成第一版闭环：默认 `auto` 先走 Jina，失败或疑似弱正文时直连原 URL 做轻量 HTML 清洗；若仍不可用，则返回“观澜阅读兜底”上下文包，包含原始 URL、失败原因和同域公开搜索线索。用户也可以显式使用 `--backend direct`，或用 `--no-fallback-search` 关闭搜索兜底。

### 2.4 本地优先

Cookie、Token、个人配置只保存在本机 `~/.guanlan/`，不上传、不外传。公共信源可使用远端服务，但用户登录态不应交给公共 demo 服务。

### 2.5 统一输出

不同平台原始数据结构差异很大，进入 Agent 上下文前要统一清洗，减少 token 浪费和字段漂移。

建议统一字段：

```json
{
  "platform": "zhihu",
  "source_id": "zhihu",
  "category": "hotnews",
  "title": "...",
  "url": "...",
  "mobile_url": "...",
  "published_at": "...",
  "summary": "...",
  "metrics": { "heat": "...", "comments": 0 },
  "media": [],
  "fetched_at": "...",
  "source_confidence": "high"
}
```

### 2.6 不做验证码规避

不设计验证码绕过、批量账号控制、风控规避、模拟真人刷量等能力。浏览器 fallback 只用于用户可见的公开页面读取、截图、导出文本和低频人工辅助。

## 3. 用户场景

### 3.1 中文搜索

示例：

- “查一下国内有没有人讨论这个产品。”
- “搜中文资料，对比几个 LLM Agent 框架。”
- “找一下微信公众号和中文技术博客里的资料。”

需要能力：中文搜索、站内搜索、公众号搜索、结果去重、来源可信度标注。

### 3.2 热点与舆情

示例：

- “今天 AI 圈国内有什么热点？”
- “看一下微博/知乎/B站/抖音上大家怎么评价这件事。”
- “帮我每周做竞品舆情摘要。”

需要能力：热榜聚合、关键词监控、跨平台去重、日报/周报。

### 3.3 内容阅读

示例：

- “读一下这篇公众号。”
- “总结这个知乎问题下的主要观点。”
- “B站这个视频讲了什么？”

需要能力：网页正文提取、公众号阅读、视频字幕/转录、评论采样。

### 3.4 财经研究

示例：

- “看看今天 A 股有哪些热点。”
- “查一下某股票在财联社和华尔街见闻的讨论。”
- “整理某公司公告和市场反应。”

需要能力：财联社、华尔街见闻、东方财富、巨潮资讯、公告读取。

### 3.5 招聘与公司研究

示例：

- “看看国内 Agent 工程师岗位要求。”
- “帮我研究这家公司在招聘什么方向。”

需要能力：Boss 直聘、拉勾、猎聘、企业信息站点、搜索 fallback。

### 3.6 本地生活

示例：

- “帮我规划上海两天路线。”
- “找附近适合商务会面的咖啡馆。”

需要能力：高德/百度地图、POI、路线、天气。美团/大众点评只做谨慎浏览器 fallback，不默认批量抓取。

### 3.7 内容运营

示例：

- “把这篇文章发到公众号草稿。”
- “同步到知乎、掘金、CSDN。”
- “准备一条小红书图文草稿。”

需要能力：草稿、预览、明确确认、发布记录。该阶段靠后实现。

## 4. 系统架构

### 4.1 三层结构

```text
Guanlan
├── Profile 层
│   ├── global
│   ├── china
│   └── hybrid
├── Channel 层
│   ├── search
│   ├── hotnews
│   ├── social
│   ├── video
│   ├── finance
│   ├── maps
│   ├── career
│   └── publishing
└── Backend 层
    ├── MCP
    ├── CLI
    ├── HTTP API
    ├── RSS
    ├── Browser fallback
    └── Python native fetchers
```

### 4.2 Profile

新增区域画像：

| Profile | 用途 | 默认排序 |
| --- | --- | --- |
| `global` | 通用全球资料检索 | GitHub、YouTube、Twitter、Reddit、Exa、Web |
| `china` | 中国大陆用户和中文互联网任务 | 中文搜索、热榜、公众号、微博、小红书、抖音、B站、财经 |
| `hybrid` | 跨境开发者、研究任务 | GitHub、Exa、中文搜索、热榜、Web、视频、社交 |

建议命令：

```bash
guanlan profile show
guanlan profile set china
guanlan doctor --profile china
guanlan install --profile china --channels=newsnow,search,maps
```

### 4.3 Channel Catalog

当前 channel 信息散落在 channel 文件、README、SKILL 和 install guide 里。中国版需要集中元数据，作为 doctor、install、文档和 skill 的共同数据源。

建议字段：

| 字段 | 含义 |
| --- | --- |
| `id` | channel/source id |
| `name` | 展示名 |
| `region` | `global/china/hybrid` |
| `category` | search/hotnews/social/video/finance/maps/career/publishing |
| `tier` | 0 装好即用，1 需要安装，2 需要登录/key，3 高风险/重依赖 |
| `risk` | low/medium/high |
| `read_actions` | 支持的只读动作 |
| `write_actions` | 支持的写动作，默认空 |
| `requires_login` | 是否需要登录 |
| `requires_cookie` | 是否需要 Cookie |
| `recommended_backend` | 推荐后端 |
| `fallback_backends` | 降级后端 |
| `refresh_interval` | 建议刷新间隔 |
| `notes` | 风控、限制、使用提示 |

## 5. NewsNow 判断

### 5.1 结论

NewsNow 非常适合作为观澜的信源参考和可选后端，但不建议整仓库搬进观澜。

建议定位：

```text
NewsNow = optional backend + source catalog seed
```

### 5.2 为什么有用

NewsNow 已具备这些特征：

- 支持 MCP server。
- 有 HTTP API：`/api/s?id=SOURCE_ID`。
- 有统一 `NewsItem` 结构：`id/title/url/mobileUrl/pubDate/extra`。
- 有默认 30 分钟 TTL 和 source 级刷新间隔。
- 覆盖大量中文热门信源。
- MIT License。

源码中有效 source 约 64 个，其中适合我们优先关注的包括：

| 分类 | Source |
| --- | --- |
| 综合热榜 | 知乎、微博、抖音、贴吧、今日头条、百度热搜、B站热搜、澎湃、腾讯新闻、凤凰网 |
| 科技开发 | V2EX、36氪、IT之家、少数派、掘金、酷安、Hacker News、GitHub Trending |
| 财经 | 财联社、华尔街见闻、格隆汇、金十数据、法布财经、MKTNews |
| 世界资讯 | 联合早报、参考消息、卫星通讯社 |
| 文娱消费 | 豆瓣热门电影、腾讯视频、爱奇艺、什么值得买 |

### 5.3 为什么不整包引入

NewsNow 是 TypeScript/Nitro/Vite/Node 服务端项目。直接 vendoring 会把观澜从 Python CLI 脚手架变成 Python + Node 全栈服务，复杂度明显上升。

它依赖：

- Nitro/H3 route。
- `$fetch`/`myFetch`。
- `defineSource`。
- `shared/sources.json`。
- db0/D1/sqlite 缓存。
- pnpm/Node 20 构建链。

这些都不是观澜当前架构的自然组成部分。

### 5.4 是否有登录/Cookie 风险

NewsNow 的 GitHub OAuth 主要用于用户同步、缓存和强制刷新，不是大多数新闻源必需。

多数核心中文 source 使用公开 API、RSS 或普通网页解析。部分源会使用临时 cookie 或固定 header，例如：

- 微博热搜：网页解析，带固定 Cookie/header。
- 抖音热榜：先访问登录域获取临时 Set-Cookie，再请求热榜。
- （延后）雪球热股：后续单独评估，当前版本不接入。

这类风险低于读取用户 Chrome Cookie/钥匙串，但仍然需要低频、缓存和失败 fallback。

### 5.5 推荐接入策略

分三步：

1. 先支持 NewsNow 作为可选后端。
2. 复制它的 source catalog 思路，整理我们自己的 source matrix。
3. 精选稳定源，用 Python 重写 fetcher，逐步沉淀为 观澜原生能力。

不建议做：

- 不把 NewsNow 整仓库复制进来。
- 不默认依赖公共 demo 服务高频请求。
- 不把公共 demo 服务用于用户登录态或私有数据。

### 5.6 观澜中的目标形态

外部后端模式：

```bash
guanlan configure newsnow-base-url https://newsnow.busiyi.world
guanlan doctor --profile china
guanlan hotnews zhihu --limit 10
```

MCP 模式：

```bash
mcporter call 'newsnow.get_hotest_latest_news(id: "zhihu", count: 10)'
```

HTTP fallback：

```bash
curl -s "https://newsnow.busiyi.world/api/s?id=zhihu"
```

原生 Python fetcher 模式：

```bash
guanlan hotnews zhihu --backend native
```

## 6. 平台优先级矩阵

评分说明：

- 价值：1-5，越高越该做。
- 稳定性：1-5，越高越稳定。
- 风险：低/中/高。
- 难度：低/中/高。
- 策略：`external` 先接外部后端，`native` 适合 Python 原生移植，`browser` 暂用浏览器 fallback，`later` 后置。

### 6.1 Phase 1 必做

| 能力 | 价值 | 稳定性 | 风险 | 难度 | 策略 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| Profile China | 5 | 5 | 低 | 低 | native | 中国区排序和默认体验入口 |
| Channel Catalog | 5 | 5 | 低 | 中 | native | 后续所有平台的元数据基础 |
| Safety Policy | 5 | 5 | 低 | 中 | native | 禁止 doctor 自动读浏览器 Cookie |
| NewsNow optional backend | 5 | 4 | 低 | 中 | external | 快速获得中文热榜覆盖 |
| Hotnews formatter | 5 | 5 | 低 | 低 | native | 统一热榜输出 |
| Skill 中国区路由 | 5 | 5 | 低 | 中 | native | 让 Agent 会选平台 |

### 6.2 Phase 2 搜索与热榜

| 平台/能力 | 价值 | 稳定性 | 风险 | 难度 | 策略 | 第一版动作 |
| --- | --- | --- | --- | --- | --- | --- |
| NewsNow HTTP/MCP | 5 | 4 | 低 | 中 | external | 接 `BASE_URL`、source list、单 source 拉取 |
| 百度热搜 | 5 | 4 | 低 | 低 | native | 参考 NewsNow Python 化 |
| 知乎热榜 | 5 | 4 | 低 | 低 | native | 参考 NewsNow Python 化 |
| 微博热搜 | 5 | 3 | 中 | 中 | native/external | 先 NewsNow，后原生低频 |
| 今日头条热榜 | 4 | 3 | 中 | 中 | native/external | 先 NewsNow |
| B站热搜 | 4 | 4 | 低 | 低 | native | 可结合现有 Bilibili channel |
| open-webSearch | 5 | 3 | 低 | 中 | external | 中文搜索后端，不做唯一依赖 |
| 微信公众号搜索 | 5 | 3 | 中 | 中 | external/browser | Exa/domain search + reader fallback |

### 6.3 Phase 3 内容平台

| 平台 | 价值 | 稳定性 | 风险 | 难度 | 策略 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 微信公众号阅读 | 5 | 3 | 中 | 中 | external/browser | 只读，优先已有 wechat reader |
| 小红书 | 5 | 2 | 高 | 高 | external | 搜索/阅读低频，Cookie 显式导入 |
| 抖音 | 5 | 3 | 中 | 中 | external/native | 视频解析和热榜分开做 |
| B站 | 5 | 4 | 低 | 中 | native/external | 字幕、热门、搜索 |
| 微博内容搜索 | 4 | 3 | 中 | 中 | external/native | 区分热搜和内容搜索 |
| 知乎问题阅读 | 4 | 3 | 中 | 中 | browser/external | 热榜先做，全文后做 |
| 贴吧 | 3 | 3 | 中 | 中 | native/external | 舆情补充 |
| 快手 | 3 | 2 | 中 | 高 | later | 后置 |

### 6.4 Phase 4 财经、招聘、地图

| 平台/能力 | 价值 | 稳定性 | 风险 | 难度 | 策略 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 财联社 | 5 | 4 | 低 | 低 | native | NewsNow 已有可参考实现 |
| 华尔街见闻 | 4 | 4 | 低 | 低 | native | 快讯/热门 |
| 雪球热股 | 4 | 3 | 中 | 中 | later | 当前阶段下线，后续单独评估 |
| 巨潮资讯 | 5 | 4 | 低 | 中 | native | 公告研究很重要 |
| 东方财富 | 4 | 3 | 中 | 中 | native/browser | 行情和公告补充 |
| 高德地图 | 5 | 5 | 低 | 中 | external | MCP/API key 模式 |
| 百度地图 | 4 | 5 | 低 | 中 | external | MCP/API key 模式 |
| Boss 直聘 | 4 | 2 | 高 | 高 | external/browser | 登录强，后置谨慎做 |
| 拉勾/猎聘 | 3 | 3 | 中 | 中 | browser | 搜索 fallback 优先 |

### 6.5 Phase 5 发布自动化

| 平台/能力 | 价值 | 稳定性 | 风险 | 难度 | 策略 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 微信公众号草稿 | 5 | 4 | 中 | 中 | external | AppID/AppSecret，草稿优先 |
| 微信公众号发布 | 4 | 4 | 高 | 中 | external | 必须二次确认 |
| 知乎/掘金/CSDN 同步 | 3 | 2 | 高 | 高 | later | 先设计，不急做 |
| 抖音/小红书/B站上传 | 4 | 2 | 高 | 高 | later | 需要账号隔离和草稿策略 |

## 7. 第一版 MVP 范围

第一版不追求“全平台”。只做一条稳定主线：中文资讯和热榜。

### 7.1 MVP 必须包含

- `profile china`。
- `channel_catalog` 基础元数据。
- `newsnow` channel：检测、配置、HTTP/MCP 使用指南。
- `guanlan hotnews` 命令或等价 skill 路由。
- `format hotnews`。
- 安全策略：doctor 不自动读取浏览器 Cookie。
- 文档：如何配置 NewsNow 公共/自建 `BASE_URL`。

### 7.2 MVP 不包含

- 小红书/微博/抖音深度内容抓取。
- 发布、评论、点赞、私信。
- 自动读取 Chrome Cookie。
- 自动部署 NewsNow 服务。
- 绕过验证码或批量抓取。

### 7.3 MVP 用户体验

用户可以这样问：

> 今天国内 AI 圈有什么热点？

Agent 路由：

1. 读取 `profile=china`。
2. 查询 NewsNow sources：`zhihu`、`weibo`、`bilibili-hot-search`、`36kr-quick`、`ithome`、`juejin`、`sspai`。
3. 统一格式化。
4. 去重聚类。
5. 输出摘要和来源链接。

## 8. 技术设计

### 8.0 当前已落地

本设计文档中的一部分 M1 能力已经进入代码：

| 能力 | 状态 |
| --- | --- |
| `china` / `hybrid` profile 排序 | 已实现 |
| `doctor` 默认跳过敏感登录态探测 | 已实现 |
| `doctor --trace` 诊断追踪 | 已实现 |
| `hotnews` channel 原生可用检测 | 已实现 |
| `guanlan hotnews` 命令 | 已实现，稳定源 `baidu`、`v2ex`；实验源 `zhihu` |
| `format hotnews` 统一格式化 | 已实现，可接受通用数组与 NewsNow-like JSON |

### 8.1 新增模块建议

```text
guanlan/
├── profiles.py
├── channel_catalog.py
├── sources/
│   ├── __init__.py
│   ├── base.py
│   ├── newsnow.py
│   ├── hotnews_native.py
│   └── formatters.py
├── channels/
│   ├── newsnow.py
│   ├── open_websearch.py
│   └── hotnews.py
└── skill/references/
    ├── china.md
    ├── hotnews.md
    └── safety.md
```

### 8.2 NewsNow Adapter

建议接口：

```python
class NewsNowClient:
    def __init__(self, base_url: str): ...
    def get_source(self, source_id: str, latest: bool = False) -> SourceResponse: ...
    def list_sources(self) -> list[SourceMeta]: ...
```

HTTP：

```text
GET {base_url}/api/s?id=zhihu
```

MCP：

```text
newsnow.get_hotest_latest_news(id, count)
```

配置：

```yaml
newsnow_base_url: https://newsnow.busiyi.world
```

注意：公共 demo 只作为默认试用和 fallback，建议用户有稳定需求时自建。

### 8.3 Native Source Fetcher

参考 NewsNow 时不复制运行时，只沉淀稳定 source 的“请求和解析逻辑”。第一批建议：

| Source | 原因 |
| --- | --- |
| `baidu` | 简单、价值高、公开热榜 |
| `zhihu` | 简单、价值高、结构清晰 |
| `tieba` | 简单、中文社区补充 |
| `thepaper` | 简单、新闻权重高 |
| `cls-telegraph` | 财经价值高 |
| `wallstreetcn-quick` | 财经快讯 |
| `v2ex-share` | 稳定 RSS/JSON |
| `36kr-quick` | 科技快讯 |
| `sspai` | 科技/效率内容 |
| `juejin` | 中文开发内容 |

每个 native source 必须有：

- timeout。
- User-Agent。
- 最小刷新间隔。
- 异常时返回清晰错误。
- 单元测试使用 mock，不访问真实网络。

### 8.4 Formatter

新增：

```bash
guanlan format hotnews
guanlan format search
guanlan format source
```

`format hotnews` 输入可以是：

- NewsNow `/api/s` JSON。
- MCP 返回文本。
- native source JSON。

输出统一为 compact JSON 或 Markdown table。

### 8.5 Doctor

`doctor --profile china` 应展示：

- NewsNow backend 可用性。
- open-webSearch 可用性。
- 已配置的地图/财经/社交能力。
- 安全提示：是否启用过自动浏览器 Cookie 读取。

不应触发：

- 浏览器 Cookie 读取。
- macOS Keychain。
- 平台登录弹窗。
- 大量网络请求。

### 8.6 Skill 路由

新增 `skill/references/china.md`：

```text
用户问“今天热点”：优先 NewsNow -> hotnews formatter。
用户问“中文搜索”：优先 open-webSearch -> Exa/Jina fallback。
用户问“公众号”：优先 wechat reference。
用户问“财经快讯”：NewsNow 财经 sources -> 财联社/华尔街见闻 channel。
用户问“社交口碑”：先热榜/搜索，再按平台低频读取。
```

## 9. 实施计划

### Week 1: 设计与 MVP 骨架

目标：让中国版有清晰入口，但不做深度平台抓取。

任务：

1. 整理并提交本文档。
2. 收敛已写的草稿代码，删除或保留为最小可用骨架。
3. 实现 `profile china`。
4. 实现 `newsnow` channel 检测。
5. 实现 `newsnow_base_url` 配置。
6. 实现 `format hotnews`。
7. 更新 SKILL 中国区路由。
8. 增加测试，确保不读取浏览器 Cookie。

验收：

- `guanlan doctor --profile china` 不触发钥匙串。
- 可以从 NewsNow 拉取 `zhihu` 或 `baidu` source。
- 可以格式化为统一热榜输出。
- 文档说明公共 demo 和自建服务区别。

### Week 2: 原生 Source 第一批

目标：开始把 NewsNow 的稳定 source 逻辑沉淀到 Python。

任务：

1. 建立 `guanlan/sources` 抽象。
2. 移植 `baidu`、`zhihu`、`tieba`、`thepaper`。
3. 移植 `v2ex-share`、`36kr-quick`、`sspai`。
4. 增加 source 级缓存和 refresh interval。
5. `newsnow` backend 和 native backend 可切换。

验收：

- 无 NewsNow 外部服务时，仍能跑部分中文热榜。
- 每个 source 有 mock 测试。
- 网络失败时能给出 fallback 建议。

### Week 3: 财经与技术资讯

目标：补强高价值研究场景。

任务：

1. 移植 `cls-telegraph`。
2. 移植 `wallstreetcn-quick`。
3. 评估 `xueqiu-hotstock` 原生实现（暂缓，不进入当前版本）。
4. 设计巨潮资讯/东方财富入口。
5. 增加财经 formatter 字段。

验收：

- 可以生成 A 股/财经快讯摘要。
- 不读取浏览器 Cookie。
- 雪球能力默认关闭，不进入当前版本执行路径。

### Week 4: 搜索、公众号和监控设计

目标：让 Agent 从“看热点”升级到“研究主题”。

任务：

1. open-webSearch 作为中文搜索后端。
2. 公众号搜索和阅读路径定稿。
3. 关键词监控设计。
4. 日报/周报模板。
5. 浏览器 fallback 规范。

验收：

- 用户问一个中文主题，Agent 能组合搜索 + 热榜 + 资讯源。
- 能输出带来源链接的研究摘要。
- 监控能力仍停留在设计或显式自动化，不偷偷运行。

## 10. 暂不做清单

这些先不碰：

- 自动读取 Chrome/Keychain Cookie。
- 小红书/微博/抖音批量深抓。
- 发帖、评论、点赞、私信、关注。
- 自动绕过验证码。
- 电商价格大规模抓取。
- 复杂浏览器自动化。
- 把 NewsNow 整仓库 vendoring 进观澜。

## 11. 决策记录

### DR-001: NewsNow 是否直接搬代码

结论：不整包引入，采用“可选后端 + source catalog seed + 原生 Python 逐步沉淀”。

理由：

- NewsNow 工程形态是 Node/Nitro/Vite，直接引入会破坏观澜的轻量 Python CLI 架构。
- NewsNow 的 source 逻辑非常有价值，适合参考和复用思路。
- 外部 NewsNow 服务可作为快速 MVP 后端。
- 长期稳定性来自我们自己的 Python native sources 和 fallback。

### DR-002: 是否允许 doctor 自动读浏览器 Cookie

结论：不允许。

理由：

- 会触发 macOS 钥匙串弹窗。
- 用户无法判断请求范围。
- 健康检查不应触碰敏感凭据。
- 如需 Cookie，必须由 `guanlan configure --from-browser` 显式触发。

### DR-003: MVP 是否包含社交深抓

结论：不包含。

理由：

- 小红书、抖音、微博深度读取风控和账号风险更高。
- 第一版更需要稳定的信息发现能力。
- 热榜/搜索/公开资讯能覆盖大量初始价值。

## 12. 参考项目

- NewsNow: https://github.com/ourongxing/newsnow
- open-webSearch: https://github.com/Aas-ee/open-webSearch
- mcp-hotnews-server: https://github.com/wopal-cn/mcp-hotnews-server
- Baidu Maps MCP: https://github.com/baidu-maps/mcp
- Amap MCP Server: https://github.com/sugarforever/amap-mcp-server
- MediaCrawler: https://github.com/NanmiCoder/MediaCrawler
- Wechatsync: https://github.com/wechatsync/Wechatsync
- social-auto-upload: https://github.com/dreammis/social-auto-upload
