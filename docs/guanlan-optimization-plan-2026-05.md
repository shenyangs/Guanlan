# Guanlan 优化计划（2026-05）

本计划基于 2026-05-03 暴力测试、现有 trace/quality 输出、以及 Agent 实际使用反馈整理。目标不是追求“像通用搜索引擎一样什么都搜”，而是优先修复最影响 Agent 体验和误判的缺口。

## 当前落地状态

本轮发布已完成：

- Agent 工作流输出：`quality_summary` 会给出 `2-step / 3-step / 4-step`、最低 Guanlan 工具数、fallback 前置条件。
- Query guard：无意义 query 会被拒识并返回诊断，不再随机吐噪声网页。
- Query rewrite：短事实、短电商、超长 query 会进入保守扩写或压缩路径，并在 trace 中标注 `query_shape`。
- 多实体 fan-out：多城市/多对象查询会自动拆前几个实体补搜，降低“只保留首实体”的概率。
- 强一手证据降压：政策/官方等强命中结果会进入 `usable_with_gaps`，避免把“证据角色不全”误报为“搜索失败”。
- source_type 一致性：补充 Apple、Samsung、Huawei、Zhihu、Weibo、Xiaohongshu、Bilibili 等高频域名覆盖。
- 发布门禁：`scripts/release_gate.sh` 已覆盖 ruff、pytest、quality coverage/regression/robustness、eval benchmark、build、install smoke 和版本核对。

仍属于长期优化的方向：

- live 搜索相关性要继续用真实网络 benchmark 观察，不能只靠离线单测判断。
- 实时金融、天气、突发事件仍应优先专用 API 或 `hotnews`，不把普通 search 伪装成实时事实源。

## P0：先修会导致错误汇报的问题

### 1. Agent 工作流升级

问题：

- Agent 容易只跑一次 `search` 就下结论
- 质量画像未过时，会被误报成 “Guanlan 搜索失败”

措施：

- 把 `2-step / 3-step / 4-step` Guanlan 工作流写入输出契约
- 在 `quality_summary` 中显式给出 `agent_workflow_plan`
- 在 `agent_execution_policy` 中明确最低 Guanlan 工具数和 fallback 前置条件

验收：

- quality trace/context 中出现工作流档位、最少工具数、工具顺序
- Agent 在质量未过时优先继续跑 Guanlan，而不是直接切 `web_search`

### 2. Benchmark 使用规范

问题：

- 不符合最佳使用方式的 benchmark 会把产品边界和调用策略混在一起

措施：

- 新增 `docs/agent-playbook.md`
- 在 `AGENTS.md`、`docs/agent-usage.md`、`guanlan/skill/SKILL.md` 中固化 benchmark 规则

验收：

- 新 benchmark 默认按场景要求补 `route/research/hotnews/feeds`
- 报告中不再把 quality warn 直接写成搜索失败

## P1：提高搜索结果的可用性

### 3. 短 query 与歧义 query 加强

问题：

- 4-9 字短 query 容易跑偏
- 歧义 query 缺乏稳定消解

措施：

- 对短 query 增加 query rewrite 扩写模板
- 对消费、政策、技术等常见歧义词增加上下文提示词
- 对显式 scope 场景提高 scope 相关性权重

验收：

- 针对短 query 的 regression case 补入测试集
- Top1/Top3 相关性提升，错误主题命中下降

### 4. 无意义 query 拒识

问题：

- 无意义输入仍返回随机网页

措施：

- 增加最小相关性阈值和拒识分支
- 在 trace 中明确标记 `no_meaningful_evidence`

验收：

- 无意义 query 返回空结果或清晰解释
- Agent 不再基于随机网页继续推理

### 5. 超长 query 与多实体拆分

问题：

- 超长 query 退化为空搜
- 多实体 query 只保留首实体

措施：

- 在 query_strategy 中增加超长 query 拆分
- 对多实体任务自动建议 `compare` / `dossier` / 多轮 research

验收：

- trace 中能看见拆分后的 query variants
- 多实体测试不再只剩首实体

## P1：提高时效与技术场景体验

### 6. 时效性词路由增强

问题：

- “今天 / 刚刚 / 最新” 场景仍可能只走普通搜索

措施：

- 对强时效意图提高 `hotnews` 的默认优先级
- 对结果日期缺失场景强化 freshness 降权

验收：

- 热点/突发题默认升级为 4-step 工作流
- 历史旧文在实时题里的排序显著后移

### 7. 技术/AI 题的 RSS 强约束

问题：

- 技术题容易只看到社区 SEO 页面

措施：

- 技术/AI 问题默认纳入 `feeds curated`
- 强化官方文档、GitHub、release/issue 的权重

验收：

- `tech` 场景工作流默认至少 4 步
- 技术题结果里官方/代码仓信源占比提升

## P2：分类与标注一致性

### 8. source_type 一致性修复

问题：

- 同类官方来源标签不稳定

措施：

- 补充企业 newsroom、官方社区、产品站点分类规则
- 为高频争议域名增加回归测试

验收：

- Samsung Newsroom、Apple 社区、华为官网等标签稳定

### 9. 日期提取与 freshness 标注

问题：

- `published_at`、`freshness_confidence`、`stale_risk` 仍有不少空值或偏保守

措施：

- 扩展标题/摘要日期提取模式
- 对明确日期结果提高 freshness 置信度

验收：

- 有显式日期的结果不再大量落入 `unknown`

### 10. 质量画像阈值微调

问题：

- 强结果也经常 `warn`

措施：

- 把“结果可用”和“证据包完备”分层表达
- 允许优质政策/官方结果进入更温和状态，而不是一律高压 warn

验收：

- 高质量强命中场景的误报警减少
- 同时保留继续补证的能力，不牺牲边界提示

## 验证方式

- 为每个问题补 deterministic regression case
- 对短 query、热点、技术、政策、多实体、无意义输入建立最小基准集
- benchmark 报告区分：
  - 搜索相关性问题
  - 质量画像严格问题
  - Agent 调用策略问题

## 成功标准

- Agent 不再轻易把 Guanlan 汇报成“老是失败”
- 强路由场景下，Guanlan 继续保持明显优势
- 弱场景下，要么给出更稳定的补证路线，要么更早拒识，而不是随机返回
