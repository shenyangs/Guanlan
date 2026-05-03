# Guanlan 0.5.0 施工方案

本文是 0.5.0 的施工约束，不是对外产品哲学。核心目标是：在不破坏基础搜索、阅读、热榜和研究证据包的前提下，增加真正配得上 0.5.0 的上层研究能力。

一句话原则：

> 轻任务不打扰，重任务不偷懒。

观澜 0.5.0 不应把所有问题都变成“深度研究工程”。基础搜索必须继续轻、快、可解释；复杂研究才进入多步编排。

## v0.5.0 发布状态

本方案已在 `0.5.0` 完成主线落地：`guanlan workflow`、`guanlan investigate --budget/--dry-run`、`guanlan sources`、`guanlan eval suite`、Archive 语义 sidecar、页面诊断、研究 recipe、`quality performance` 和 MCP 对应工具面均已进入主线。后续迭代继续围绕稳定契约、真实样本复跑和局部重构推进，不做会牵动基础搜索/阅读主链路的大重构。

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


## 九、P2/P3 后续施工清单

P2/P3 的目标不是继续堆平台，而是在 P0/P1 已经建立的轻重分流、信源矩阵和离线基准之上，提升复杂研究的稳健性、可复用性和可证明性。所有改动仍遵守同一原则：基础 `search/read/hotnews/research` 不变重，高级能力显式调用，失败时可降级、可解释。

### P2：复杂研究质量层

P2 只增强上层研究工作流，不接管基础命令。

#### P2.1 Archive 语义桥接（可选后端）

目标：让 Agent 搜过、读过、研究过的材料更容易沉淀为本地知识资产，但默认仍保持 SQLite FTS/LIKE，不引入默认 embedding 依赖。

建议新增：

```bash
guanlan archive embed --backend ollama
guanlan archive embed --backend openai --model text-embedding-3-small
guanlan archive search "query" --semantic
guanlan archive context "query" --semantic --limit 20
```

设计约束：

- 默认不启用语义检索。
- 没有 embedding 后端时，archive 行为与现在完全一致。
- embedding 只处理本地 archive 记录，不主动联网。
- 输出必须保留原始 `url/title/source_card/read_quality/ingest_audit`，不能只返回向量命中分。
- 语义结果必须和 FTS 结果区分标记，例如 `retrieval_mode=semantic|hybrid|fts`。

验收：

- 未配置 embedding 时，`archive search/context` 全部原样可用。
- 配置 Ollama 后，能对本地 20 条测试文档生成向量并检索。
- RAG 导出不丢 `source_card`、`risk_tags`、`read_quality`。

#### P2.2 Live Benchmark 样本池

目标：把“观澜更适合中文互联网研究”从叙事推进到可复测证据。

建议新增：

```bash
guanlan eval suite run chinese-web-live --mode live --limit 80
guanlan eval suite report chinese-web-live --output report.html
```

样本结构：

- 政策/官方 10
- 地方/产业 10
- 电商/消费 10
- 技术/AI/RSS 10
- 财经/公司 10
- 口碑/社区 10
- 热点/趋势 10
- 学术/高校 10
- 文娱/体育 10
- 本地模型联网 10

设计约束：

- live suite 默认不进 release gate。
- 网络失败要归类为 `network_or_upstream`，不能直接算“搜索能力失败”。
- 对实时任务必须检查时间窗口。
- 对技术/AI 任务必须检查 RSS 二次发现。
- 对政策/官方任务必须检查官方源优先。

验收：

- 能生成 HTML/JSONL 报告。
- 报告区分：路由失败、候选池不足、来源过窄、网络失败、正文抽取失败、时间窗口失败。
- 至少保留 3 次历史报告用于对比趋势。

#### P2.3 Source Registry 收束治理

目标：降低 `source_registry`、`source_taxonomy`、`search_sources`、`channel_catalog` 之间口径漂移的风险，但不做一次性大重构。

建议新增：

```bash
guanlan sources audit
guanlan sources export --format json
guanlan sources explain "query" --trace
```

设计约束：

- 先做 audit/read-only，不直接移动数据结构。
- 找出口径冲突：稳定性、授权要求、风险标签、scope 归属、证据角色。
- 输出修复建议，不自动改写。

验收：

- `sources audit` 能发现高关注渠道（微信、知乎、小红书、微博、B站、抖音、雪球、RSS、web）的状态是否一致。
- README、doctor/status、hotnews list、MCP/Skill 不出现同一平台互相矛盾的稳定性描述。

#### P2.4 `investigate` 证据预算和降级策略

目标：让深度研究更可靠，但不无限补证。

建议增强字段：

- `step_budget`
- `timeout_budget_seconds`
- `fallback_used`
- `external_fetch_strategy`
- `network_diagnosis`
- `evidence_sufficiency`

设计约束：

- `light/standard/deep` 每档都有最大步骤数。
- 搜索全挂时，只输出建议让宿主 Agent 临时调用 WebFetch，不在 Guanlan 内隐式调用。
- 如果建议 WebFetch，必须说明这是增强搜索策略，不是 Guanlan 静默失败。

验收：

- 模拟搜索后端全挂时，`investigate` 能输出清晰降级建议。
- 深度模式不会无限调用 read/search。
- `--dry-run` 可以展示预算和降级路径。

### P3：性能与长期架构治理

P3 是稳定后的工程治理层。除非 P2 已稳定，否则不动主链路大结构。

#### P3.1 并发读取和多后端搜索

目标：提升 `research`、`read batch`、`archive ingest-research` 的吞吐，不改变输出字段和排序语义。

设计约束：

- 先用 `ThreadPoolExecutor` 做有限并发，不直接全量 asyncio 重写。
- 默认并发保守，例如 `--concurrency 4`。
- 每个任务有 timeout、错误隔离和结果顺序稳定策略。
- 基础 `search "query"` 不因并发改造变慢或变不稳定。

验收：

- 10 个 URL 批量读取耗时明显下降。
- 任意单个 URL 失败不影响其他 URL。
- JSON 输出顺序可预测。
- 测试覆盖 timeout、部分失败、缓存命中。

#### P3.2 拆分神文件，但只做边界内抽离

目标：降低 `cli.py`、`webtools.py` 的维护风险，但不在 0.5.0 前后做破坏性重构。

建议顺序：

1. 先抽纯 formatter/helper。
2. 再抽 CLI command handler。
3. 最后才考虑 runtime adapter。

禁止：

- 禁止一次性重写 `webtools.py` 主链路。
- 禁止在没有契约测试保护时改 ranking/read/search 输出。
- 禁止为了“架构好看”改变用户命令行为。

验收：

- 每次抽离后 full pytest + release gate 必须通过。
- diff 应以移动代码为主，不混入行为变化。
- Agent-facing JSON 字段零删除。

#### P3.3 Channel Runtime Adapter 试点

目标：验证是否值得把 channel 从 doctor/status 概念推进到运行时适配器，但只选低风险渠道试点。

试点范围：

- RSS
- web/read
- GitHub
- V2EX

建议接口：

```python
class ChannelRuntime:
    def search(self, query: str, limit: int) -> list[SearchResult]: ...
    def read(self, url: str) -> ReadResult: ...
    def health(self) -> ChannelHealth: ...
```

设计约束：

- 不触碰小红书、微博、知乎、抖音等高风控渠道。
- 旧路径保留，新 adapter 只做内部可选试点。
- adapter 输出必须转换回现有结果结构。

验收：

- RSS/web 试点通过 contract tests。
- doctor/status 与 runtime health 不冲突。
- 可随时回退旧路径。

#### P3.4 性能基准和退化监控

目标：防止优化后“看起来更高级，实际更慢、更窄、更脆”。

建议新增：

```bash
guanlan quality performance
guanlan eval compare-runs before.json after.json
```

指标：

- 查询耗时 p50/p90
- 结果池大小
- 域名多样性
- 官方/社区/媒体比例
- read 正文占比
- cache 命中率
- timeout/fallback 次数

验收：

- 每次大改前后可对比。
- 报告能明确“变慢但更准”或“更快但结果变窄”。
- release gate 只纳入轻量 deterministic performance，不阻断真实网络波动。

## 十、P2/P3 暂停条件

出现以下情况，应停止继续做高级优化，回到基础稳定性：

- `search/read/hotnews/research` 任一基础命令行为出现非预期变化。
- 默认候选池缩水。
- Agent-facing JSON 字段删除或改名。
- release gate 失败。
- 新增高级命令导致安装 smoke 失败。
- 真实网络失败被误判为“无结果”。
- 为了并发或重构引入不可解释的排序变化。

## 十一、建议执行顺序

1. P2.4 `investigate` 预算/降级字段。
2. P2.3 `sources audit/export`，先治理口径。
3. P2.2 live benchmark 报告，不进 release gate。
4. P2.1 archive semantic 可选后端，默认关闭。
5. P3.4 performance guard。
6. P3.1 有限并发读取。
7. P3.2 小步拆分 formatter/handler。
8. P3.3 Channel Runtime Adapter 低风险试点。

这个顺序的原因是：先增强可解释和可测性，再碰性能和架构。观澜不是为了显得复杂而复杂，所有高级能力都必须服务 Agent 更稳地拿到中文互联网证据。
