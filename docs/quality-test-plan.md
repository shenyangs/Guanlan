# 观澜质量测试计划

这份计划用于反复检查观澜的实际使用质量，不作为产品理念文档。重点看 Agent 能否拿到可靠、及时、可读、可解释的中文互联网证据。

## 测试维度

| 维度 | 目标 | 最低验收 |
| --- | --- | --- |
| 轻重分流 | 简单任务保持 direct，政策/高风险任务 guided，对比/档案任务 investigate。 | `guanlan workflow` 与 `quality foundational` 不让基础 search 被上层工作流拖重。 |
| 搜索质量 | 查询能被正确路由到适合的中文信源，并保留开放网页兜底。 | 结果数量足够；前列结果与意图匹配；`--trace` 能解释 route、scope、质量评分和缓存。 |
| 热点时效 | 热榜能反映当天或近期水势，单源失败不拖垮整体。 | `today` 多源可返回；单源有状态说明；结果含 rank/source/time 线索。 |
| 正文抽取 | `read` 输出应尽量接近正文，而不是导航、登录、推荐和页脚。 | 中文新闻/官方页正文占比明显高于噪声；失败时能给搜索兜底。 |
| 趋势归并 | 多源热点能把同一事件聚到一起，同时避免错聚类。 | `--trends` 能展示跨源来源数、代表标题和分布；聚类解释可读。 |
| advisor 自然度 | `--advisor` 给 Agent 规则和边界，不机械复述模板。 | 输出能结合 query intent、证据类型、样本偏差和下一步；不声称知道用户真实动机。 |
| 研究工作流 | `compare/timeline/dossier` 能把证据包整理成对比、时间线和档案，不吞掉来源和边界。 | JSON/Markdown/context 都保留来源链接、证据角色、边界提示和下一步命令。 |
| 约束执行 | `--site`、显式年份和小结果池不会被误用。 | `--site` 硬过滤；年份窗口内证据优先；`limit<30` 有 Agent 提醒。 |
| 外部补证 | 搜索后端受限时，Agent 能理解 WebFetch 是观澜规划的定点补证策略。 | 输出 `external_fetch_strategy`；说明候选 URL、原因和外显话术。 |
| 路由评测 | 固定场景能命中合适的意图、scope、证据角色和候选池下限。 | `eval benchmark` 通过；覆盖政策、口碑、热点、技术、学术、地方、电商和本地模型。 |
| 发版回归 | 每次更新不能让下游 Agent 拿到的材料变少、变窄或变脏。 | `quality regression` 通过；默认池、RSS 兜底、正文抽取和 advisor 动态性保持。 |

## 固定测试集

### 搜索质量

- 政策原文：`新质生产力 政策 原文 最新`
- 地方政策：`上海 人工智能 产业政策 2026`
- 产品口碑：`某新能源车 用户评价 值不值得买`
- 电商零售：`即时零售 行业趋势 2026`
- 技术问题：`Python Agent 框架 GitHub issue 对比`
- 近期热点：`最近 中文互联网 AI 热点`
- 站点硬过滤：`人工智能 政策 --site gov.cn`，不得返回知乎或域外结果。
- 年份窗口：`具身智能 2024-2025 进展`，窗口外材料只作背景。
- 小样本护栏：`--limit 10 --trace` 必须提示 Agent 这只是 smoke sample。

### 热点与趋势

- `guanlan hotnews today --limit 80`
- `guanlan hotnews today --limit 80 --trends`
- `guanlan hotnews baidu --limit 80`
- `guanlan hotnews weibo --limit 80`
- `guanlan hotnews bilibili --limit 80`
- `guanlan hotnews ithome --limit 80`
- `guanlan hotnews v2ex --limit 80`

### 正文抽取

- 官方政策页或部委新闻页。
- 党央媒新闻页。
- 地方官媒新闻页。
- 垂类媒体文章页。
- JS/登录/移动端噪声较重的转载页。

### advisor

- `guanlan research "某产品 用户评价 值不值得买" --preset reputation --read-top 0 --advisor`
- `guanlan research "新质生产力 政策 原文 最新" --preset policy --read-top 1 --advisor`
- `guanlan research "最近 中文互联网 AI 热点" --profile china --read-top 0 --advisor`

### 研究工作流

- `guanlan compare "产品A" "产品B" --focus "价格 口碑 风险" --limit 80 --format context`
- `guanlan timeline "低空经济 广东 政策 最新进展" --limit 80 --format context`
- `guanlan timeline "具身智能 2024-2025 产业进展" --limit 80 --format context`
- `guanlan dossier "某公司" --focus "业务 口碑 风险" --limit 80 --format context`

## 评分方法

每条用例按 0-2 分粗评：

- `0`：不可用、明显错路由、没有有效证据或输出不可读。
- `1`：可用但有明显缺口，例如结果偏少、噪声高、时效不足、advisor 过模板化。
- `2`：可直接给 Agent 使用，且边界说明清楚。

每轮测试记录：

- 命令和时间。
- 返回数量、主要来源、是否命中预期 scope。
- 失败源、异常、超时或降级路径。
- 输出给 Agent 后是否需要二次清洗。
- 下一步应修的具体点。

## 发布前质量闸门

- `ruff check .`
- `pytest -q`
- `guanlan quality foundational`
- `guanlan quality coverage`
- `guanlan quality regression`
- `guanlan eval benchmark`
- 至少跑 6 条搜索质量用例。
- 至少跑 5 个热榜源和一次 `today --trends`。
- 至少读 5 篇中文页面并记录正文/噪声观察。
- 至少跑 3 条 `research --advisor`，人工检查自然度。
- 至少跑 1 条 `compare`、1 条 `timeline`、1 条 `dossier`，检查输出是否仍保留信源身份、证据角色和边界。
- 至少跑 1 条 `--site` 硬过滤、1 条显式年份 timeline、1 条 `limit<30` trace，检查 Agent 护栏是否可见。
- 至少模拟 1 次搜索后端异常或站点过滤空结果，检查 `external_fetch_strategy` 是否给出 WebFetch 定点补证话术。
- 更新薄弱点清单，不把实验能力包装成稳定能力。
