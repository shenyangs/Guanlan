# 搜索与热榜

观澜把“搜索”和“热榜”分开处理：搜索用于主动找资料，热榜用于观察中文互联网的当日流向。

## 中文热榜 / Hotnews

第一批原生公开源不需要 Cookie、登录态或钥匙串。当前稳定源是 `baidu`、`v2ex`；`zhihu` 暂列实验源，部分环境会返回 401/403。

```bash
# 查看支持的热榜源
guanlan hotnews list

# 百度热搜，Markdown 输出，适合直接放进 Agent 上下文
guanlan hotnews baidu --limit 10

# V2EX 热门
guanlan hotnews v2ex --limit 10

# 知乎热榜（实验源，失败时用搜索 fallback）
guanlan hotnews zhihu --limit 10 --json
```

统一字段包括：

| 字段 | 含义 |
| --- | --- |
| `platform` | 平台，如 `baidu`、`zhihu`、`v2ex` |
| `source_id` | 信源 id |
| `category` | 分类，如 `hotnews`、`community` |
| `title` | 标题 |
| `url` | 来源链接 |
| `summary` | 摘要或正文片段 |
| `metrics` | 热度、回复数、节点等指标 |
| `fetched_at` | 抓取时间 |
| `source_confidence` | 信源置信度 |

外部热榜 JSON 可以统一格式化：

```bash
cat /tmp/hotnews.json | guanlan format hotnews
```

使用建议：

- 用户问“今天国内有什么热点”：先 `guanlan hotnews baidu`，再按主题补搜索。
- 用户问“技术社区在讨论什么”：优先 `guanlan hotnews v2ex`。
- 用户问“知乎上怎么看”：可尝试 `guanlan hotnews zhihu`；如果返回 401/403，改用搜索 fallback。
- 不要为了热榜读取浏览器 Cookie；需要登录的深度平台应单独确认。

## 观澜统一搜索

默认网页搜索命令：

```bash
guanlan search "query" --limit 8
```

中文互联网搜索：

```bash
guanlan search "query" --profile china --limit 8
```

时效性搜索：

```bash
guanlan search "最近 query 热点" --profile china --trace
guanlan search "最新 query 进展" --profile china --format context
```

当用户说 `近期`、`最近`、`热点`、`热搜`、`最新`、`快讯` 等词时，观澜会自动补当前年月做搜索收束，并在排序里给近期结果加权、给明显陈旧结果降权。需要解释时使用 `--trace` 查看 `recency_boost`、`stale_penalty`、结果日期和时间窗口。

中文信源白名单：

```bash
# 查看全部 scope
guanlan search --list-scopes

# 党央媒与中央重点媒体
guanlan search "query" --profile china --scope party_central

# 政府与部委网站
guanlan search "query" --profile china --scope gov

# 核心地方官媒
guanlan search "query" --profile china --scope local_official

# 电商、零售、跨境和产业带，包含亿邦动力等
guanlan search "query" --profile china --scope ecommerce

# 科技与开发者社区
guanlan search "query" --profile china --scope tech_dev

# 财经与资本市场
guanlan search "query" --profile china --scope finance
```

限定站点：

```bash
guanlan search "query" --site zhihu.com --limit 8
guanlan search "query" --site mp.weixin.qq.com --limit 8
```

结构化输出：

```bash
guanlan search "query" --json
guanlan search "query" --format context
guanlan search "query" --source-chart
```

解释排序与聚类：

```bash
guanlan search "query" --trace
guanlan search "query" --cluster-threshold conservative
```

`--source-chart` 会追加 ASCII 来源类型和域名分布，用来快速判断这轮信息是否偏官方、偏社交、偏商业媒体或偏单一域名。它只解释来源结构，不替代事实核验。

## 话题回响 / Pulse

```bash
# 安全版讨论倾向，默认只基于公开搜索摘要
guanlan pulse "query" --format context

# 指定公开平台样本
guanlan pulse "query" --sites zhihu.com,weibo.com,xiaohongshu.com --format context

# 显式读取少量代表结果增强证据
guanlan pulse "query" --read-top 2 --format context
```

`pulse` 会输出讨论倾向、置信度、正负向关键词、争议点、来源分布和证据样本。它不代表全网舆情；回答用户时必须保留“基于当前公开样本”的边界提醒。

重复查询时使用本地 TTL 缓存，减少对上游搜索页的扰动：

```bash
guanlan search "query" --cache-ttl 3600
```

自定义只读 backend 只能显式调用，适合企业内部知识库：

```bash
guanlan search "query" --backend plugin:my_company_api
```

默认搜索后端使用公开 HTML 搜索解析，不需要 Cookie、API Key 或浏览器权限。搜索结果适合继续交给 `guanlan read` 读取原文。

## 观澜统一阅读

```bash
guanlan read "https://example.com/article" --max-chars 12000
```

适用：

- 普通网页。
- 博客和文档。
- 公开文章页。
- 搜索结果中的候选链接。

不适用或可能失败：

- 强登录页面。
- 需要验证码的平台页。
- 部分公众号文章。
- 已删除或强反爬页面。

## Exa AI 搜索

高质量 AI 搜索引擎，擅长技术和代码搜索。

```bash
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'
mcporter call 'exa.get_code_context_exa(query: "code question", tokensNum: 3000)'
```

### 使用场景

| 场景 | 参数 |
|-----|------|
| 网页搜索 | `web_search_exa(query: "...", numResults: 5)` |
| 代码搜索 | `get_code_context_exa(query: "...", tokensNum: 3000)` |

### 特点

- 擅长英文内容和技术文档
- 支持代码上下文搜索
- 结果质量高

## 与其他搜索工具对比

| 工具 | 来源 | 适用场景 |
|-----|------|---------|
| Exa | guanlan | 英文/技术/代码搜索 |
| 智谱搜索 | my-mcp-tools | 中文搜索 |
| GitHub 搜索 | guanlan (dev.md) | 仓库/代码搜索 |
