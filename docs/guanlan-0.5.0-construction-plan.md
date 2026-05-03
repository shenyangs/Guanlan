# Guanlan 0.5.0 施工方案

本文是 0.5.0 的施工约束，不是对外产品哲学。核心目标是：在不破坏基础搜索、阅读、热榜和研究证据包的前提下，增加真正配得上 0.5.0 的上层研究能力。

一句话原则：

> 轻任务不打扰，重任务不偷懒。

观澜 0.5.0 不应把所有问题都变成“深度研究工程”。基础搜索必须继续轻、快、可解释；复杂研究才进入多步编排。

## v0.4.5 先行落地状态

本方案先在 `0.4.5` 落地 P0 基座：`guanlan workflow`、`guanlan investigate`、`guanlan quality foundational`、MCP `guanlan_workflow/guanlan_investigate`。这不是把 0.5.0 提前发布，而是先把轻重分流和基础护栏做稳，后续再继续推进更重的 source registry / benchmark / archive 语义能力。

## 一、版本目标

0.5.0 的主线不是“新增更多平台”，而是把观澜从“Agent 可用的中文搜索 CLI”推进到“Agent 可控的中文互联网研究工作流引擎”。

但这个升级必须满足三个前提：

- 不改变 `search/read/hotnews/research` 的基础默认行为。
- 不减少默认候选池、证据字段和诊断字段。
- 不让 Agent 在简单任务中过度规划、过度调用、过度解释。

## 二、施工铁律

### 1. 上层增强不接管底层命令

新增高级能力只能作为新命令或显式选项出现，例如：

```bash
guanlan investigate "复杂研究问题"
guanlan sources list --scope ecommerce
guanlan eval suite run chinese-web-v1
```

不得把现有命令默认改成深度模式：

```bash
guanlan search "query"
guanlan read "URL"
guanlan hotnews today
guanlan research "query"
```

这些基础命令继续保持当前语义。

### 2. 高级能力只编排，不重写

`investigate`、`sources`、`eval suite` 这类 0.5.0 能力应复用现有模块：

- route
- search
- read
- research
- hotnews
- feeds
- compare
- timeline
- dossier
- archive

不得在 `investigate` 内另写一套搜索后端、阅读后端或排序系统。这样即使高级工作流出问题，也不会拖垮基础功能。

### 3. 最小充分原则

Agent 不应该为了形式完整而盲目执行多步链路。

如果一次 `search` 已经满足以下条件，就可以先回答，最多给可选补证建议：

- 结果数量足够。
- Top 结果明显相关。
- 来源身份清楚。
- 没有关键 `quality_summary=warn`。
- 用户只问事实、链接、入口或轻量资料。

只有出现升级信号时，才进入 `research/investigate/compare/timeline/dossier`。

### 4. 新字段只能新增，不能替换

0.5.0 可以新增字段，但不能静默删除或改名：

- `title/url/snippet/domain/source_type/evidence_role/trace`
- `route_plan/query_strategy/source_diagnostics/evidence_audit`
- `read_quality_summary/quality_report`
- `source_card/risk_tags/score/rank`

任何字段调整必须先改 `docs/contract.md`，再补测试。

### 5. 默认候选池不得缩水

0.5.0 不得为了性能或工作流美观，降低 Agent 默认拿到的信息量。

最低线：

- search 默认不低于 80。
- research 默认不低于 80。
- hotnews 默认不低于 80。
- feeds 默认不低于 80。
- archive search 默认不低于 80。
- read fallback 不低于 20。

## 三、轻重分流规则

### 轻任务：直接执行

这些任务不应触发复杂规划：

- “查一下某个官网/链接/入口”
- “搜索某关键词”
- “读这个 URL”
- “今天热榜看一下”
- “找 3-5 个线索”
- “确认某个页面标题/发布时间”

推荐路径：

```bash
guanlan search "query" --limit 80
guanlan read "URL" --quality-report
guanlan hotnews today --limit 80
```

Agent 行为要求：

- 不先跑 `investigate`。
- 不强制 `route -> research -> scoped search`。
- 不把简单任务包装成研究报告。
- 输出简洁，同时保留来源。

### 中任务：按需升档

这些任务适合 `route -> research -> scoped search`：

- “帮我查清楚”
- “给我依据”
- “这个说法靠谱吗”
- “用户评价如何”
- “政策/产业/公司背景”
- 搜索结果质量提示 `warn`
- 来源类型过窄或域名集中

推荐路径：

```bash
guanlan route "query" --json
guanlan research "query" --profile china --advisor
guanlan search "query" --scope <scope> --limit 80 --trace
```

### 重任务：进入 investigate

这些任务才适合 0.5.0 的 `investigate`：

- 用户明确说“深入研究 / 系统分析 / 形成报告”
- 多实体、多平台、多维度比较
- 需要时间线、档案、竞品对比
- 涉及政策、法律、医疗、财经、安全等高准确性领域
- 涉及近期、热点、趋势，且需要交叉验证
- 需要把结果沉淀进 archive/RAG

推荐路径：

```bash
guanlan investigate "query" --profile china --format context
```

`investigate` 内部可以动态调用：

- route
- research
- scoped search
- read
- hotnews
- feeds
- compare/timeline/dossier
- archive ingest dry-run

但必须输出它实际调用了什么，为什么升级，以及还有哪些边界。

## 四、0.5.0 功能设计

### P0：基础功能防回退闸门

先做，不做完不允许动高级工作流。

新增：

```bash
guanlan quality foundational
```

检查：

- `search` 默认候选池和核心字段。
- `read` 正文和质量报告。
- `hotnews` 多源基础输出。
- `research` 证据包字段。
- `compare/timeline/dossier` 来源链接和边界。
- `archive` 本地检索和 RAG 字段。

验收：

- 加入 `scripts/release_gate.sh`。
- 新功能不能让 foundational guard 失败。

### P0：Agent 升档决策器

新增内部模块，建议命名：

```text
guanlan/workflow_decider.py
```

职责：

- 判断当前 query 是轻任务、中任务还是重任务。
- 给出 `workflow_tier`：`direct` / `guided` / `investigate`。
- 给出 `upgrade_reasons`。
- 给出 `do_not_overthink` 标记。

示例输出：

```json
{
  "workflow_tier": "direct",
  "reason": "用户只要求搜索入口，未出现研究/对比/高风险信号",
  "recommended_commands": ["guanlan search \"query\" --limit 80"],
  "do_not_overthink": true
}
```

验收：

- 简单事实查询不升级到 investigate。
- 多实体/高风险/近期热点查询能升级。
- Agent 文档明确：这个决策器是建议，不是硬锁。

### P1：`guanlan investigate`

新增显式深度研究命令。

定位：

- 不替代 `search`。
- 不替代 `research`。
- 只服务复杂研究场景。

建议参数：

```bash
guanlan investigate "query"
guanlan investigate "query" --profile china
guanlan investigate "query" --budget light|standard|deep
guanlan investigate "query" --format json|context|markdown
guanlan investigate "query" --dry-run
```

预算含义：

- `light`：route + research，少量 read。
- `standard`：route + research + scoped search + read。
- `deep`：在 standard 基础上按需补 hotnews/feeds/compare/timeline/dossier。

默认建议：

- 默认 `standard`。
- 如果 workflow_decider 判断是轻任务，`investigate` 可以提示“这个任务更适合 search/read”，但用户显式调用时仍可执行。

输出字段：

- `query`
- `workflow_tier`
- `budget`
- `executed_steps`
- `skipped_steps`
- `route_plan`
- `evidence_packet`
- `read_quality_summary`
- `source_diversity_guard`
- `time_window`
- `external_fetch_strategy`
- `final_context`
- `open_questions`
- `suggested_next`

验收：

- 不改变 `search` 默认行为。
- dry-run 能解释会跑哪些命令，不发请求。
- standard 模式不会无限补证。
- 所有步骤有 timeout 和最大调用数。

### P1：Source Registry 2.0

目标是把“信源身份”进一步产品化，但先做只读查询，不做大重构。

新增命令：

```bash
guanlan sources list
guanlan sources list --scope ecommerce
guanlan sources show gov.cn
guanlan sources explain "新质生产力 政策"
```

数据来源：

- 优先复用 `source_registry.py`、`source_taxonomy.py`、`search_sources.py`。
- 0.5.0 不强行合并三套结构，先做 read-only adapter。
- 后续再考虑单一真相表重构。

输出字段：

- `source_id`
- `domain`
- `source_type`
- `authority_score`
- `sample_value`
- `freshness_value`
- `risk_tags`
- `content_roles`
- `best_for`
- `not_for`
- `stability`

验收：

- README/文档/doctor/status 对高关注平台的口径不冲突。
- `sources explain` 能说明为什么政策优先 gov/party_central，口碑优先 community/social。

### P1：Eval Suite 公开基准

目标是证明观澜能力，而不是只靠 README 叙事。

新增：

```bash
guanlan eval suite list
guanlan eval suite run chinese-web-v1
guanlan eval suite report --output report.html
```

任务集：

- 政策 10
- 地方 10
- 电商 10
- 技术 10
- 财经 10
- 口碑 10
- 热点 10
- 学术 10
- 文娱 10
- 本地模型联网 10

评测原则：

- 轻任务用 search/read，不强行 investigate。
- 重任务才允许 investigate。
- 实时/热点必须包含 hotnews。
- 技术/AI 必须包含 feeds。
- 不把 `quality_summary=warn` 直接记为失败。

验收：

- 可离线跑 deterministic suite。
- 可选 live suite 不阻断发版。
- 报告区分“搜索能力问题”“工作流调用问题”“网络/上游问题”。

## 五、暂不做

0.5.0 不做这些事：

- 不大拆 `webtools.py` 主链路。
- 不把 `search` 默认改成 `investigate`。
- 不默认引入向量库或 embedding 依赖。
- 不默认读取 Cookie、钥匙串或浏览器登录态。
- 不自动调用宿主 WebFetch，除非 Agent 根据 `external_fetch_strategy` 显式执行。
- 不把小红书、知乎、微博等高风控平台包装成稳定端到端能力。
- 不把 NewsNow 或其他项目整仓库 vendoring 进来。

## 六、风险控制

### 风险：高级工作流过度调用

控制：

- workflow_decider 默认保守。
- investigate 必须显式调用。
- 文档写清楚轻任务直接 search/read。
- 每个 budget 有最大步骤数。

### 风险：基础搜索变慢

控制：

- 不在 `search` 默认路径增加额外网络请求。
- `search --trace` 可以增加诊断字段，但不额外跑完整研究链。
- 小 limit 提醒只输出建议，不擅自扩大请求。

### 风险：输出复杂到 Agent 读不懂

控制：

- direct 搜索保持紧凑。
- investigate 输出分层：summary、evidence、diagnostics、next。
- `--format context` 保持可直接放进 prompt。

### 风险：功能看起来高级但不可测

控制：

- P0 先加 foundational guard。
- P1 每个新增命令都有 contract tests。
- release gate 必须跑通。
- live benchmark 单独看，不阻断离线发版。

## 七、建议里程碑

### 0.4.x 收口

- 补齐 foundational guard。
- 补 workflow_decider 离线测试。
- 更新 docs/contract.md 的新增字段草案。

### 0.5.0-alpha

- 新增 `guanlan investigate --dry-run`。
- 新增 `guanlan sources list/show`。
- 新增 `guanlan eval suite list`。
- 不改变基础命令。

### 0.5.0-beta

- `investigate` 支持 `light/standard/deep`。
- `sources explain` 可用。
- `eval suite run chinese-web-v1` 可用。
- Agent 文档加入轻重分流示例。

### 0.5.0

- release gate 加入 foundational guard。
- `investigate`、`sources`、`eval suite` 有稳定 JSON/context 输出。
- README 只低调展示“深度研究工作流”，不让用户误以为普通搜索必须走复杂链路。

## 八、验收总标准

0.5.0 可以发布的标准：

- 基础功能全量测试和 release gate 通过。
- `guanlan search "query"` 行为不因 0.5.0 变重。
- `guanlan read "URL"` 行为不因 0.5.0 变复杂。
- `guanlan investigate` 能明显减少复杂研究任务的 Agent 编排负担。
- Agent 文档能说明什么时候不用 investigate。
- 默认候选池和核心证据字段没有缩水。
- 新能力失败时能解释边界，不影响基础命令继续可用。

