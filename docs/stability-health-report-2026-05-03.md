# 观澜稳定性体检报告与优化计划

日期：2026-05-03  
目标版本建议：0.5.2 稳定性专项版  
版本原则：只做稳定性、质量闸门、代码瘦身和协作治理；不新增平台，不删除能力，不缩小默认结果池。

## 一、结论先行

这次 Bing 中文漂移和“固态电池拆字”问题不是一个孤立 bug，而是一个稳定性信号：观澜已经进入能力面很宽、模块很多、多人/多进程同时修改的阶段，继续只靠局部补丁会让系统变脆。

下一版应该明确冻结为“稳定性专项版”：

- 不追新能力，先保护已有能力。
- 不做大爆炸重构，只做带测试护栏的小切片瘦身。
- 不让任何搜索、研究、阅读、热榜、归档、MCP、Agent 文档能力倒退。
- 不降低默认候选池，不因为稳定性治理让下游 Agent 拿到的内容大面积变少。
- 不把上游网络失败伪装成“没有结果”，必须输出可解释诊断。

一句话：先把地基夯实，再继续盖楼。观澜现在需要的是“稳住澜面”，不是继续往水里扔新石头。

## 二、当前项目体检数据

### 代码体量

本次粗略扫描范围：`guanlan/`、`tests/`、`docs/`、`scripts/` 下的 Python、Markdown 和 shell 文件。

- 相关文件约 147 个。
- `guanlan/` Python 代码约 35,748 行。
- `tests/` Python 测试约 9,920 行。
- 当前测试规模已经很可观，但核心复杂度集中在少数文件。

### 最大文件

| 文件 | 行数 | 风险判断 |
| --- | ---: | --- |
| `guanlan/webtools.py` | 9,217 | P0，搜索、阅读、排序、质量、trace、research 过度集中 |
| `guanlan/cli.py` | 4,494 | P0，命令解析和大量命令实现混在一起 |
| `guanlan/hotnews.py` | 1,956 | P1，热榜聚合和外部源处理复杂 |
| `guanlan/router.py` | 1,892 | P1，路由规则越来越多，需防漂移 |
| `guanlan/archive.py` | 1,538 | P1，归档/RAG/审计链路较重 |
| `guanlan/integrations/mcp_server.py` | 1,056 | P1，MCP 工具定义和分发集中 |
| `guanlan/quality.py` | 995 | P1，质量闸门继续扩展会变重 |

### 最大函数和复杂热点

| 位置 | 函数 | 行数 | 分支数 | 风险判断 |
| --- | --- | ---: | ---: | --- |
| `guanlan/cli.py:86` | `main` | 797 | 3 | parser 构建过长，维护困难 |
| `guanlan/webtools.py:1183` | `search_web` | 614 | 52 | 搜索主路径过重，最容易被补丁污染 |
| `guanlan/integrations/mcp_server.py:42` | `_tool_definitions` | 506 | 0 | MCP schema 过长，易与 CLI 文档漂移 |
| `guanlan/integrations/mcp_server.py:561` | `_run_tool_inner` | 456 | 61 | MCP 命令分发复杂，回归风险高 |
| `guanlan/cli.py:2388` | `_cmd_archive` | 302 | 47 | archive 子命令过于集中 |
| `guanlan/webtools.py:6352` | `format_search_trace` | 241 | 55 | trace 输出和诊断逻辑混杂 |
| `guanlan/serve.py:25` | `dispatch_request` | 205 | 20 | HTTP 只读服务分发集中 |
| `guanlan/webtools.py:3991` | `build_research_packet` | 202 | 14 | research 证据包核心链路，需要契约保护 |

### 宽泛异常和外部调用

粗略扫描 `except Exception`、`subprocess.run`、`urlopen`：

- `guanlan/cli.py` 约 86 处相关匹配。
- `guanlan/webtools.py` 约 25 处相关匹配。
- `guanlan/hotnews.py` 约 7 处相关匹配。
- `guanlan/feeds.py` 约 6 处相关匹配。
- 多个 `channels/*` 模块也有宽泛异常和外部命令调用。

这不等于都有 bug，但说明目前很多外部依赖失败会被“吞掉并降级”。降级本身是观澜的优点，但如果没有分类诊断，就会把程序错误、网络波动、上游拦截、低相关结果混在一起。

## 三、当前稳定性基础

观澜不是没有工程纪律。当前已有基础是很好的：

- 全量测试当前已超过 500 个用例。
- `scripts/release_gate.sh` 已串起 ruff、pytest、coverage、regression、robustness、benchmark、performance、eval suite、build 和安装 smoke。
- 已有 contract/runtime 测试，能保护 Agent 依赖的字段。
- 已有 release smoke，能防版本号、入口命令、安装路径出错。
- 已有 `quality`、`eval`、`benchmark` 命令，说明项目已经开始自测。

但这次事故说明，还缺三类护栏：

- 针对具体搜索后端的“坏样本夹具”。
- 针对显式 backend 的质量契约。
- 针对多人/多进程并发改动的发布前卫生检查。

## 四、核心风险清单

### P0：搜索后端质量漂移

表现：

- 某个后端返回了低相关、拆字、成人站、站群、平台首页或英文漂移结果。
- `backend=auto` 可能能 fallback，但显式 `--backend bing`、`--backend baidu` 等路径更容易绕过质量闸门。
- Agent 看到结果就可能误以为“观澜找到了证据”。

稳定性原则：

- 搜索后端必须遵守契约：要么返回可用证据，要么返回结构化诊断，不能返回未标注的污染结果。
- 低相关不是“空结果”，而是可解释的后端质量状态。
- 对中文复合词、实体名、政策词、产业词要优先保护，不能被拆成无关汉字。

### P0：`webtools.py` 成为搜索系统的风险中枢

表现：

- 搜索后端、阅读、质量评估、排序、trace、research 包装都在一个文件里。
- 新补丁很容易在同一个文件叠加，形成“补丁沉积层”。
- 回归时定位困难，修改范围很难被 review。

稳定性原则：

- 不做一次性大拆分。
- 先提取纯函数和低副作用模块。
- 每一步都跑现有测试和新增黄金样本。
- 对外 API 和 CLI 行为保持不变。

### P0：多进程写代码导致发布风险

表现：

- 多个进程同时改动时，版本号、changelog、README、website、测试夹具、release 文件可能不同步。
- 发布前如果有未提交文件，很容易误把其他进程的半成品带进去，或者漏掉必要文件。
- 当前工作区已经出现其他进程留下的未提交文件，需要发布工具显式识别。

稳定性原则：

- 发布前必须有 dirty worktree 检查。
- 未提交文件必须被列出并人工确认归属。
- 版本、README、docs、website、lockfile、changelog 必须统一核验。
- 不能自动 revert 其他进程改动。

### P1：CLI / MCP / HTTP 分发逻辑重复

表现：

- CLI、MCP、HTTP 都在暴露相似能力，但命令定义、参数、文案和输出契约分散。
- 容易出现 CLI 有某能力，MCP 没同步；README 写了，实际工具 schema 没跟上。

稳定性原则：

- 暂不重写命令系统。
- 先建立只读的命令能力登记表，用于文档、MCP schema 和测试核验。
- 保持现有入口稳定。

### P1：信源身份信息有重复真相表

表现：

- `source_taxonomy.py`、`source_registry.py`、`search_sources.py`、`channel_catalog.py`、hotnews/feeds/router 都在描述平台、风险、角色或 scope。
- 这些信息越丰富，越容易出现某处写 stable、某处写 experimental 的矛盾。

稳定性原则：

- 不立刻大迁移。
- 先定义 source registry 的只读真相接口。
- 新增测试检查高关注渠道口径一致：微信、知乎、小红书、微博、B 站、雪球、Bing、百度、DuckDuckGo。

### P1：异常分类不够细

表现：

- 许多路径使用 `except Exception`。
- 对用户来说，网络超时、HTTP 403、解析失败、程序错误、低相关结果可能都表现为“warn”。

稳定性原则：

- 顶层 CLI 可以保留兜底异常，保证用户体验。
- 核心搜索/阅读/热榜/feeds 路径应尽量分类：network_timeout、blocked、parse_error、low_relevance、unsafe_filtered、contract_error。
- 不因为异常分类而破坏优雅降级。

### P1：真实网络稳定性没有足够纳入质量闸门

表现：

- 离线 deterministic 测试很多，但真实网络/RSS/热榜源会超时、403、变结构。
- release gate 当前不适合作为强依赖真实网络的阻塞项，但需要一个非阻塞报告。

稳定性原则：

- deterministic gate 继续阻塞发布。
- live smoke 生成报告，不默认阻塞发布。
- 真实网络失败要记录为“上游状态”，不是“功能失败”。

### P2：官网、README、多语言文档和版本同步

表现：

- 官网不走 GitHub，但版本号仍需要同步。
- README 多语言容易滞后。
- 文档大幅增长后，首页理解成本上升。

稳定性原则：

- 稳定性专项版不做大文案改造。
- 只补发布检查和关键版本同步检查。
- 文档瘦身可单独排期。

## 五、0.5.2 稳定性专项施工计划

### P0-1：新增后端坏样本夹具

新增命令或质量子项：

```bash
guanlan quality backend-fixtures
```

覆盖最少这些场景：

| 场景 | 预期 |
| --- | --- |
| `固态电池量产时间表` + Bing 低相关夹具 | 返回空结果 + diagnostics，不返回拆字污染 |
| `宁德时代 固态电池 进展` + Bing 低相关夹具 | 标记 `cjk_compound_terms_missing` 或同类诊断 |
| 成人/擦边域名夹具 | 标记 `unsafe_filtered` |
| 政策查询返回纯站群夹具 | 标记 low_relevance，不进入主结果 |
| 英文漂移夹具 | 中文 profile 下不能覆盖中文证据池 |
| 平台首页夹具 | 不能被当成正文证据 |
| 单域名刷屏夹具 | 标记 source diversity 风险 |
| 正常 gov/media 夹具 | 不误杀好结果 |

验收标准：

- 加入 release gate。
- 显式 backend 和 auto backend 都有测试。
- 坏样本不能悄悄进入 `results`。
- 好样本不能被过度过滤。

### P0-2：建立搜索后端契约测试

契约：

- 每个 backend batch 必须输出 `status`、`result_count`、`diagnostics` 或等价字段。
- 显式后端如果不可用，不能静默返回污染结果。
- `backend=auto` 遇到 blocked/low_relevance/unsafe_filtered 时必须继续 fallback。
- `--json` 空结果必须保留 backend diagnostics，方便 Agent 知道下一步怎么补证。

验收标准：

- 新增 `tests/test_search_backend_contract.py`。
- 覆盖 Bing、Baidu、DuckDuckGo 和 fallback 聚合路径。
- 不改变现有用户命令输出的主结构。

### P0-3：发布前工作区卫生检查

新增脚本：

```bash
scripts/pre_release_status.sh
```

检查：

- 当前分支和远端状态。
- 是否存在未提交文件。
- 是否存在未跟踪文件。
- 版本号是否在 `pyproject.toml`、`guanlan/__init__.py`、lockfile、README/docs、website 中一致。
- changelog 是否包含当前版本。
- release gate 是否在干净状态下执行。

验收标准：

- 接入 release gate 的最前面。
- 有未提交文件时默认失败，并列出路径。
- 支持显式 allowlist，但不自动提交、不自动删除、不自动 revert。

### P0-4：保护默认结果池和 Agent 字段

新增质量检查：

- 默认 search/research/hotnews/feeds/archive limit 不能被意外调低。
- `--format context` 必须保留 Agent 关键字段。
- `search`、`research`、`archive` 的稳定契约字段不能缺失。

验收标准：

- 加入 `quality foundational` 或独立 guard。
- 若默认候选池缩水，release gate 失败。

## 六、屎山瘦身计划

### 原则

- 只提取，不改行为。
- 先纯函数，后副作用函数。
- 先测试覆盖高的路径，后测试薄弱路径。
- 每个切片都必须能单独回滚。
- 不为了“架构好看”影响 CLI、MCP 或 Agent 使用体验。

### 第一阶段：从 `webtools.py` 提取搜索质量层

建议新增：

- `guanlan/search_quality.py`
- `guanlan/search_backends.py`
- `guanlan/search_trace.py`

第一阶段只迁移这些相对独立的逻辑：

- relevance term expansion。
- unsafe result filter。
- backend batch quality assessment。
- backend diagnostic labels。
- trace 格式化的纯展示片段。

不迁移：

- `search_web` 主流程。
- `read_url` 主流程。
- `build_research_packet` 主流程。

验收标准：

- `webtools.py` 减少 800 行左右是理想目标，但不作为硬指标；硬指标是测试全绿、行为不变。
- `search_web` 行为 golden tests 不变。
- 新模块单元测试覆盖新增或迁移函数。

### 第二阶段：CLI 命令实现瘦身

建议新增：

- `guanlan/commands/archive.py`
- `guanlan/commands/configure.py`
- `guanlan/commands/install.py`

先迁移 `_cmd_archive`、`_cmd_configure`、`_cmd_install` 这类较独立命令。

不迁移：

- parser 构建主干。
- 命令名和参数。
- 输出格式。

验收标准：

- `guanlan --help`、各子命令 help 不变或只做等价整理。
- CLI smoke 全过。

### 第三阶段：MCP 工具定义登记表

建议新增：

- `guanlan/tool_registry.py`

用途：

- CLI capabilities、MCP tool definitions、Agent docs 的核心工具列表从同一份只读登记表衍生。
- 先用于测试一致性，不立刻替换全部运行时。

验收标准：

- MCP 工具名不减少。
- Agent docs 中的核心命令和 MCP schema 不漂移。

## 七、真实网络稳定性计划

新增非阻塞命令：

```bash
guanlan quality live-smoke --profile china --timeout-budget 180
```

建议样本：

- `固态电池量产时间表`
- `低空经济政策补贴`
- `宁德时代 固态电池 进展`
- `新质生产力 政策 原文`
- `OpenSSL CVE 最新 漏洞 影响版本`
- `AI 最新论文 工具 RSS`
- `hotnews today`
- 1 个 gov.cn 正文读取样本
- 1 个中文新闻正文读取样本

输出：

- upstream_status。
- timeout_count。
- blocked_count。
- low_relevance_count。
- fallback_success_count。
- stale_cache_used。
- 建议的 Agent 外层 timeout。

验收标准：

- 默认不阻塞 release。
- release notes 可引用其结果。
- 如果连续多次同源失败，进入 risk register。

## 八、多进程协作治理

建议把这些规则写入 `AGENTS.md` 和 release 文档：

- 同一时间只能有一个进程拥有 release 文件：`pyproject.toml`、`guanlan/__init__.py`、`uv.lock`、`CHANGELOG.md`、README 版本文案、website 版本号。
- 其他进程可以改功能文件，但合并前必须重新跑 targeted tests。
- 发布前必须看 `git status --short`，未提交文件不得默默忽略。
- 如果发现非本人改动，先报告归属，不自动 revert。
- changelog 和 commit subject 中文优先。

## 九、下一版不做什么

为避免“越修越乱”，0.5.2 建议明确不做：

- 不新增平台。
- 不新增大型用户可见工作流。
- 不把同步 I/O 全面改成 async。
- 不重写 CLI parser。
- 不重写 MCP server。
- 不改变默认 telemetry 策略。
- 不移动或删除现有命令。
- 不缩小默认 limit。
- 不把 live network smoke 作为强阻塞项。

## 十、发布验收标准

0.5.2 可以发版的最低标准：

- 全量 `pytest` 通过。
- `scripts/release_gate.sh` 通过。
- 新增 backend fixtures guard 通过。
- 新增 dirty worktree / version consistency guard 通过。
- Bing 相关坏样本保持已修复行为。
- `search/research/read/hotnews/feeds/archive/MCP` 核心 smoke 均通过。
- Agent-facing 字段不减少。
- 默认候选池不减少。
- 文档明确说明本版是稳定性专项版。

## 十一、建议执行顺序

1. 先做 P0-1 和 P0-2：后端坏样本夹具 + 搜索后端契约测试。
2. 再做 P0-3 和 P0-4：发布卫生检查 + 结果池/Agent 字段保护。
3. 然后做 `webtools.py` 第一阶段瘦身，只迁移搜索质量纯函数。
4. 跑全量测试和 release gate。
5. 根据测试结果决定是否继续 CLI/MCP 瘦身，还是把 0.5.2 先作为稳定性专项发出。

## 十二、最终判断

观澜现在不缺想象力，也不缺功能。真正的风险是：能力越来越多，但质量边界、模块边界和协作边界没有同步变硬。

下一版最重要的不是“更聪明”，而是“更不容易胡来”：

- 搜索后端不能胡来。
- Agent 字段不能胡来。
- 发布流程不能胡来。
- 多进程协作不能胡来。
- 重构更不能胡来。

如果 0.5.2 能把这些护栏立起来，观澜后续再做性能并发、信源矩阵治理和更高级研究工作流，才会更安全。

## 十三、0.5.2 执行结果补记

执行日期：2026-05-04。

本报告中的 P0 项已经全部进入 0.5.2：后端坏样本夹具、显式 backend 契约测试、发布前工作区卫生检查、默认结果池和 Agent 字段保护均已接入质量闸门。

P1/P2 项按“低风险、小切片、不丢能力”原则完成第一轮收口：

- `webtools.py` 的搜索质量层已抽出到 `guanlan/search_quality.py`，搜索主流程保持行为不变。
- `cli.py` 的 archive 命令实现已迁移到 `guanlan.commands.archive`，保留原 CLI 参数和输出。
- `guanlan.tool_registry` 成为 CLI/MCP/HTTP 工具面的只读登记表；HTTP 新增 `/tools` 暴露该登记表。
- `quality robustness` 已纳入 backend fixtures、source registry 高关注平台口径、tool registry/MCP/HTTP 一致性检查。
- `guanlan.errors` 提供统一异常分类，HTTP/live-smoke 等边界输出可区分 timeout、blocked、parse_error、network_error 等状态。
- `quality live-smoke` 已补充真实网络样本池和 `--timeout-budget`，默认仍不阻断发版。

仍然不把本轮视为“大重构完成”：`hotnews.py`、`router.py`、`MCP _run_tool_inner` 等大函数后续还可以继续小切片瘦身。但 0.5.2 已经把稳定性专项要求中会影响发版安全、后端污染、工具面漂移和多进程协作的主要风险转成了机器可检查护栏。
