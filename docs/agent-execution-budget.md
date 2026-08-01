# Guanlan Agent 执行预算与数值规范

这份文档用于给宿主 Agent、MCP 客户端和自动化编排器设置可硬编码的执行边界。它解决的不是“命令能不能调用”，而是“调用多少次、每次拿多少条、何时升级、何时停止”。

## 1. 这类 Agent 常见的问题

从真实调用记录看，效果不稳定通常不是某一个搜索后端单独造成的，而是 Agent 编排问题叠加：

1. **把工具 Schema 上限当推荐值。** `read_top=5` 可以被接受，不代表普通任务应该读 5 页。
2. **把完整研究问题塞进每个 compare subject。** `subjects` 应该只放对象名，比较维度应放进 `focus`。
3. **同一任务重复跑多套重型流程。** 先泛搜、再 compare、再 research、再 compare，既重复取证，也放大超时概率。
4. **没有修复轮和停止条件。** 空结果后原参数重试，或者成功后仍继续搜，都会造成调用膨胀。
5. **盲从路由关键词。** “路径”不一定是台风路径，“销量”不一定是文娱销量；业务实体和完整语境必须能够否决弱关键词。
6. **把线索当正文。** 搜索结果 URL、direct seed、fallback context 都只是入口，只有可用正文或结构化一手数据才能支撑强结论。
7. **把质量缺口当工具失败。** `partial_salvage`、`usable_with_gaps` 通常表示可以回答但需要说明边界，不应触发无限补搜。
8. **把预测问题交给行情工具。** `stock` 适合当前行情和结构化数据，不会替 Agent 证明未来销量、盈利路径或战略判断。

## 2. 全局硬限制

建议宿主 Agent 直接硬编码以下上限：

| 项目 | 推荐值 | 可接受区间 | 硬上限 | 说明 |
| --- | ---: | ---: | ---: | --- |
| 单任务 Guanlan 工具调用总数 | 4-7 | 2-10 | 12 | 超过 12 次应停止并向用户说明证据缺口 |
| 同类搜索轮数 | 1 | 1-2 | 2 | 第二轮必须改变 scope/site/query role，禁止原参数空转 |
| 同一工具失败重试 | 0-1 | 0-1 | 1 | 参数校验错误可修正一次；网络超时可重试一次 |
| 单任务重型工具数 | 0-1 | 0-1 | 1 | `research/compare/timeline/dossier/investigate` 五选一 |
| 同时并发网络工具 | 2 | 1-3 | 3 | 相互依赖的 route/search/read 必须串行 |
| 同时并发重型工具 | 1 | 1 | 1 | 禁止并发跑多个 research/compare |
| query 长度 | 8-40 个中文字符 | 4-80 | 120 | 多实体、多目标要先拆任务，不靠超长 query 硬塞 |
| query 核心实体 | 1-3 | 1-4 | 4 | 超过 4 个实体应分批或用 compare |
| query 约束词 | 2-6 | 1-8 | 10 | 年份、地区、动作、证据类型都算约束词 |

## 3. 各工具数值带宽

### 3.1 search

| 参数/动作 | 推荐值 | 可接受区间 | 规则 |
| --- | ---: | ---: | --- |
| `limit` | 80 | 30-100 | 低于 30 只算 smoke；宽题可到 100 |
| 搜索轮数 | 1 | 1-2 | 一轮扩池，一轮定向修复 |
| 每轮 query 变体 | 1-3 | 1-4 | 不要让 Agent 自己生成十几个近义 query |
| 每轮 scope | 1 | 1-2 | 主 scope 加一个互补 scope；禁止无差别扫全 scope |
| 代表页读取 | 1-2 | 1-3 | 从高质量、不同域名和不同证据角色中选 |

第一轮应完成候选扩池。只有出现空结果、明显误路由、来源角色缺失或时间窗不符，才进入第二轮。第二轮必须改变至少一项：`scope`、`site`、证据角色或 query 表达。

### 3.2 read / map

| 参数/动作 | 推荐值 | 可接受区间 | 硬上限 |
| --- | ---: | ---: | ---: |
| 单页 `max_chars` | 8000-12000 | 5000-20000 | 30000 |
| 每个主题代表页 | 1-2 | 1-3 | 3 |
| 单任务总读页数 | 2-4 | 1-6 | 6 |
| `map --read-top` | 2 | 0-3 | 5 |
| 同一 URL 公开读取尝试 | 1 | 1-2 | 2 |

同一 URL 第一次读不到正文时，第二步应是 `diagnose page` 或切换建议后端，不是无限重复 `read`。只有 `read_evidence.usable=true` 或 `extract_contract.can_cite_as_page_body=true` 的正文可以直接引用。

### 3.3 research

| 参数/动作 | 推荐值 | 可接受区间 | 硬上限 |
| --- | ---: | ---: | ---: |
| `limit` | 80 | 50-100 | 100 |
| `read_top` | 0-2 | 0-5 | 5 |
| `max_search_jobs` | 1 | 1-2 | 4 |
| 单任务调用次数 | 1 | 0-1 | 1 |
| 外层 timeout | 240 秒 | 180-300 秒 | 300 秒 |

`read_top=3-5` 是显式深查档，只适合用户确实要求多页证据包且宿主能提供 180-300 秒外层预算的情况。普通 Agent 自动挡仍应使用 `0-2`。若 research 超时，降级为 `search + selected read`，不要继续增加 `read_top`。

### 3.4 compare

| 参数/动作 | 推荐值 | 可接受区间 | 硬上限 |
| --- | ---: | ---: | ---: |
| `subjects` 数量 | 2-3 | 2-4 | 4 |
| `focus` 维度 | 2-5 | 1-6 | 8 |
| `limit` | 80 | 50-100 | 100 |
| `read_top` | 0-1 | 0-2 | 5 |
| 单任务调用次数 | 1 | 0-1 | 1 |

正确输入：

```text
subjects = ["蔚来", "小鹏", "理想"]
focus = "销量 现金储备 产品规划 盈利路径 2025-2028"
```

错误输入：

```text
subjects = [
  "蔚来 未来三年 销量 现金储备 产品规划 盈利路径",
  "小鹏 未来三年 销量 现金储备 产品规划 盈利路径",
  "理想 未来三年 销量 现金储备 产品规划 盈利路径"
]
```

`compare` 会为每个对象独立建立证据包，不复用 Agent 之前的泛搜结果。因此要么直接调用一次 compare，要么由 Agent 自己分别 `search/read` 后手工比较；不要两套流程同时完整执行。

### 3.5 hotnews / feeds / daily

| 工具 | 推荐调用 | 结果数 | 外层 timeout |
| --- | ---: | ---: | ---: |
| `hotnews` | 每个时效任务 1 次 | 30-80 | 120 秒 |
| `feeds` | 每个 AI/技术任务 1 次 | 30-80 | 120 秒 |
| `daily` | 每个主题 1 次 | `read_top=2-3` | 180 秒 |

热点任务并不是多跑几次普通 search，而是固定补一次 hotnews。AI、开发者、WPS/AI Office 任务固定补一次 feeds。两者返回的是线索层，重要事实仍需读取原文。

## 4. 按任务分配调用预算

| 任务类型 | 建议链路 | 推荐调用数 | 硬上限 |
| --- | --- | ---: | ---: |
| 简单事实/官网入口 | `search -> read` | 2-3 | 4 |
| 普通研究 | `agent/route -> scoped search -> read` | 3-5 | 7 |
| 今日/最新/突发 | `route -> hotnews -> scoped search -> read` | 4-6 | 8 |
| AI/技术/WPS | `route -> scoped search -> feeds -> read` | 4-6 | 8 |
| 品牌舆情/日报 | `daily` 或 `pulse -> search -> read` | 3-6 | 8 |
| 2-4 对象比较 | 单次 `compare` + 缺口补读 | 3-7 | 10 |
| 深度证据包 | `route/search -> research`，必要时补 1-2 页 | 4-8 | 10 |

## 5. 停止条件

满足以下条件时应回答，不再继续堆工具：

- 候选池不少于 30，且至少有 2 个独立域名。
- 至少覆盖 2 类证据角色；高风险题必须包含一手/官方证据。
- 至少有 1 个可引用的代表页正文或结构化一手数据。
- 用户核心问题的每个对象都有证据，或已明确指出哪个对象证据不足。
- `agent_followup.should_answer=true`，或 review 返回 `next_decision=answer|stop`。

满足以下条件时停止补搜并说明边界：

- 两轮搜索后仍无可用正文。
- 同一后端/页面已按不同策略尝试两次。
- 已达到 12 次总调用或 300 秒重型预算。
- 新增结果不再增加域名、证据角色或关键事实。
- 继续执行需要登录、Cookie、私域页或用户身份授权。

## 6. 错误与修复规则

| 信号 | Agent 动作 | 禁止动作 |
| --- | --- | --- |
| Schema validation | 按 Schema 修正一次 | 原参数重复调用 |
| `read_top` 超范围 | 普通任务改为 2；显式深查最多 5 | 把结果条数也缩小 |
| timeout / aborted | 重试一次；可加 cache 或降低 `read_top` | 宣称没有资料 |
| empty results | 读取 diagnostics、direct seeds，换 scope/site | 原 query 连续重试 |
| `partial_salvage` | 读强来源后带缺口回答 | 当成完全失败 |
| official-only | 补 1 轮媒体/社区样本 | 把官网写成全网共识 |
| compare 证据不足 | 只补缺口对象和缺口维度 | 整套 compare 重跑多次 |
| 路由与常识冲突 | 用实体/任务语境否决弱关键词 | 盲从单个关键词 |

## 7. 可直接复制的策略块

```yaml
guanlan_agent_policy_v1:
  total_tool_calls:
    recommended: [4, 7]
    hard_max: 12
  network_concurrency:
    recommended: 2
    hard_max: 3
  heavy_tool_concurrency: 1
  heavy_tools_per_task: 1
  same_tool_retry_max: 1
  search:
    limit_default: 80
    limit_research_range: [50, 100]
    smoke_below: 30
    rounds_max: 2
    variants_per_round_max: 4
  read:
    representative_pages_per_topic: [1, 2]
    total_pages_max: 6
    max_chars_default: 12000
  research:
    limit_default: 80
    read_top_recommended: [0, 2]
    read_top_accepted: [0, 5]
    max_search_jobs_default: 1
    max_search_jobs_deep: 2
    calls_max: 1
  compare:
    subjects: [2, 4]
    focus_dimensions: [1, 6]
    calls_max: 1
    subjects_must_be_entity_names: true
  timeout_seconds:
    search_read: 90
    hotnews_feeds: 120
    research_compare: 300
  stop:
    minimum_domains: 2
    minimum_evidence_roles: 2
    minimum_usable_reads: 1
    stop_after_no_gain_rounds: 1
```

如果宿主字段使用毫秒，必须显式换算：90 秒为 `90000 ms`，120 秒为 `120000 ms`，300 秒为 `300000 ms`。

## 8. 最推荐的 Agent 纪律

1. 先用 `guanlan_agent` 拿决策卡，执行 primary，再把结果交给 review。
2. 普通任务最多两轮搜索，每轮目的不同。
3. 一个任务只选一个重型工具。
4. compare 的 subject 只放对象名，维度只放 focus。
5. 搜索负责找候选，read 负责建立正文证据，Agent 负责综合判断。
6. 达到停止条件就回答；不要把“工具调用数量”当成研究深度。
