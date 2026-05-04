# 搜索质量与误杀治理专项排查和优化方案

日期：2026-05-04  
参考版本：v0.5.5  
目标版本建议：v0.5.6 或 v0.6.0 稳定性专项  
原则：不削弱质量门控，不放任污染结果；在不减少 Agent 可用结果池的前提下，降低中文真实证据被误杀的概率。

## 一、结论先行

这次专项排查确认：v0.5.5 的质量体系方向是对的，Bing 漂移、低相关批次、搜索兜底污染都能被诊断出来；但当前“粗粒度相关性门控”在中文复合词、地方政策、垂直政策场景里过于字面化，已经出现真实官方结果被整批拒绝的问题。

最需要先修的是三件事：

- P0：中文复合词误杀。`珠海横琴 跨境电商政策 2025` 这种查询，真实命中 `hengqin.gov.cn`、`zhuhai.gov.cn`、`gd.gov.cn`，但因为只匹配到 `政策`，`term_coverage=0.333`，整批被打成 `cjk_compound_terms_missing`。
- P0：意图路由误判。`豆包 付费 订阅 字节跳动` 被识别为 `career`，根因是“字节”被单独作为招聘意图触发词，导致 research 倾向牛客、招聘站。
- P1：阅读兜底污染。`IT之家` 文章直读失败后，搜索兜底 query 退化成路径数字 `0 946 250`，返回 GitHub、IT之家首页、站长之家、台湾 iThome 等弱相关线索。这类兜底应该标记为“无可用上下文”，而不是包装成可继续读的内容。

一句话：观澜现在不是缺“更宽松”，而是缺“更懂中文任务结构”。不能简单调低阈值；应该把质量门控从“词覆盖率”升级为“语义组覆盖 + 强信源救援 + 结果级保留 + 明确降级诊断”。

## 二、排查范围

本次排查参考：

- `/Users/sam/Downloads/guanlan_v055_review.md`
- Alice 原始工具输出：`alice-tool-guanlan_search-a620aacf.txt`、`d114b58b.txt`、`5004de44.txt`、`0e35a670.txt`
- `guanlan/search_quality.py`
- `guanlan/webtools.py`
- `guanlan/router.py`
- `guanlan/search_sources.py`
- 现有相关测试：`tests/test_webtools.py`、`tests/test_search_backend_contract.py`、`tests/test_quality.py`

本次没有改核心代码，只做专项诊断和施工方案。

## 三、复现与定位

### 1. 中文复合词误杀

当前 `query_relevance_terms("珠海横琴 跨境电商政策 2025")` 结果为：

```text
["珠海横琴", "跨境电商政策", "政策"]
```

当前 `query_entity_terms(...)` 结果为：

```text
["珠海横琴", "跨境电商政策", "政策"]
```

问题在于：

- `跨境电商政策` 被当成单一长词，但真实搜索结果常写成 `跨境电商`、`产业扶持`、`申报通知`、`办法`。
- `珠海横琴` 被当成单一长词，但真实结果可能分开写 `珠海`、`横琴`、`横琴粤澳深度合作区`。
- 只命中 `政策` 时，当前 coverage 为 `1/3=0.333`，低于 `0.5`，于是整批拒绝。

实测假样本：

```text
横琴粤澳深度合作区促进跨境电商高质量发展扶持办法
珠海市商务局关于组织申报跨境电子商务专项资金的通知
广东省商务厅跨境电子商务综试区政策汇总
```

当前门控结果：

```text
usable=False
reason=cjk_compound_terms_missing
term_coverage=0.333
entity_coverage=0.333
matched_terms=["政策"]
```

这说明误杀不是网络问题，而是本地质量门控规则本身的问题。

### 2. scope=gov 后仍误杀

`guanlan_search "珠海横琴 跨境电商政策 2025" --profile china --scope gov` 的原始输出显示：

- Baidu 返回 9 条，其中包含 `hengqin.gov.cn` 的 2025 年上下半年跨境电商产业扶持申报通知。
- DuckDuckGo 返回 10 条，其中包含 `hengqin.gov.cn`、`zhuhai.gov.cn`、`gd.gov.cn`。
- `duckduckgo:scope_lite` 的 rejected_samples 里也有高度相关官方结果。

但这些批次都被 `cjk_compound_terms_missing` 拒绝。

这暴露出一个契约问题：显式 `--scope gov` 下，如果结果来自高可信官方域名，并且满足地点/主题/政策角色中的主要组合，不应该被整批归零。它可以标记为 `usable_with_gaps`，提醒继续读原文和补证据角色，但不应该让 Agent 看到“暂无结果”。

### 3. 简化 query 能通过，说明误杀来自“复合词形态”

`珠海 跨境电商 --scope gov` 能成功返回：

- 珠海市政府网：2025 跨境电商年会开幕。
- 珠海市商务局：跨境电商+产业带项目采购公示。
- 中国政府网/商务部：跨境电商出口与海外仓意见。
- 珠海高新区：电子商务产业行动计划。

这说明搜索后端并非完全找不到中文政策材料，失败关键在更完整 query 的门控解析。

### 4. research 意图误判

本地探针结果：

```text
query: 豆包 付费 订阅 字节跳动
route: ["career"]
quality.intent: career
matched_terms: ["字节"]
```

根因：

- `router.py` 的 career 规则包含 `字节`。
- `webtools.py` 的 career quality profile 也包含 `字节`。
- 当前规则只要命中一个 career 词就可能优先进入 career。

这会把“字节跳动旗下产品豆包的付费订阅”误判为“字节招聘/面经/薪资”。真正的 career 触发应该需要“公司实体 + 招聘行为词/职位词/薪资面经词”的组合，而不是公司名本身。

### 5. read 搜索兜底污染

当前 `_query_from_url("https://www.ithome.com/0/946/250.htm")` 结果为：

```text
0 946 250
```

随后 `_read_search_context()` 会执行：

```text
search_web("0 946 250", site="ithome.com")
```

如果站内结果弱或解析失败，再尝试：

```text
search_web("ithome.com 0 946 250")
```

这类 query 对新闻语义几乎没有帮助，因此返回无关页面是可预期的。当前系统已经把 search fallback 标为 `search_context_only`，但还缺一步：当兜底结果与 URL/domain/title 关系很弱时，应该明确输出“兜底无可用上下文”，并建议 Agent 使用 `external_fetch_strategy` 或 `diagnose page`，而不是给出一包无关搜索结果。

## 四、问题分级

### P0-A：中文复合词质量门控误杀

风险：

- 政策、地方、产业、跨境、电商、专项资金、申报通知等中文真实需求容易被误杀。
- 对外观感会变成“观澜搜不到官方资料”，但实际是搜到了又删掉。

受影响模块：

- `guanlan/search_quality.py`
- `guanlan/webtools.py` 的 backend batch gate 调用链
- `tests/fixtures/search_quality/scenarios.json`

### P0-B：强信源缺少结果级救援

风险：

- `gov.cn`、地方政府子域、部委站点、官方垂类站明明命中，却因批次 coverage 不够被整批抛弃。
- 显式 `--scope gov` 的用户预期被破坏。

受影响模块：

- `search_quality.py`
- `rank_results`
- `search_quality_summary`
- trace/diagnostics 输出

### P0-C：career 过度触发

风险：

- 公司/产品/商业化问题被误带到招聘站。
- `research` 的多角色查询会把错误意图放大，造成结果集中在牛客、Boss、面经站。

受影响模块：

- `guanlan/router.py`
- `guanlan/webtools.py` 的 `_QUALITY_INTENT_PROFILES`
- research preset/route plan 推荐

### P1-A：read fallback query 过弱

风险：

- 动态页、反爬页、弱正文页直读失败后，会返回无关搜索兜底。
- Agent 可能误把“兜底线索”当成原文上下文。

受影响模块：

- `_query_from_url`
- `_read_search_context`
- read quality report
- page diagnosis

### P1-B：Bing 中文漂移需要继续保留诊断，但不要被误解

风险：

- Bing 的 CJK 召回漂移确实存在，当前观澜能拒绝污染结果。
- 但当 Bing 作为中文查询后端时，需要继续把 `agent_note` 说清楚：这是 Bing 上游候选池/排序漂移，不是观澜质量门槛过紧。

受影响模块：

- Bing recovery diagnostics
- `format_search_trace`
- Agent docs / skill docs

## 五、优化方案

### P0-1：把中文 term coverage 改成“语义组覆盖”

不要再只用扁平 terms 做 coverage。建议新增 `query_relevance_groups(query)`：

```text
珠海横琴 跨境电商政策 2025

location_group:
  珠海 / 横琴 / 横琴粤澳深度合作区 / 广东

topic_group:
  跨境电商 / 跨境电子商务 / 电子商务 / 跨境电商产业

policy_group:
  政策 / 扶持 / 办法 / 通知 / 申报 / 指南 / 公示 / 专项资金 / 意见

time_group:
  2025 / 2025年 / 上半年 / 下半年
```

通过规则：

- 政策/官方/地方查询：命中 `location_group + topic_group` 可作为基本相关。
- 命中 `topic_group + policy_group` 可作为基本相关。
- 命中 `location_group + policy_group` 且来自强官方域名，可作为 `usable_with_gaps`。
- 时间组不作为硬拒绝项，只作为时效排序和 trace 提醒，除非用户显式要求具体年份且结果日期明确冲突。

验收：

- `珠海横琴 跨境电商政策 2025` 对官方样本不再被整批拒绝。
- `固态电池量产时间表` 仍能拒绝“固态硬盘/胆固醇/固本培元”等拆字污染。
- `原研哉 设计哲学` 仍能拒绝“原神”漂移。

### P0-2：增加强信源结果级救援

在 batch gate 返回 `low_relevance` 之前增加救援层：

- 对每条结果计算 `result_group_coverage`。
- 如果结果来自显式 scope 的高可信域名，并命中至少两个语义组，则保留为 `salvaged=True`。
- 如果整批失败但有 salvaged 结果，批次状态应为 `usable_with_gaps` 或 `partial_salvage`，而不是 `low_relevance`。
- trace 中显示：

```text
quality_gate.reason=partial_salvage
salvaged_count=3
salvage_reason=official_domain_with_location_topic_match
```

强信源候选：

- `*.gov.cn`
- `*.hengqin.gov.cn`
- `*.zhuhai.gov.cn`
- `*.gd.gov.cn`
- 部委、地方商务局、发改委、海关、市场监管等已在 source registry 中有高 authority_score 的域名

验收：

- 显式 `--scope gov` 不再返回空结果，只要确有官方相关候选。
- 强信源救援不影响 adult/unsafe、明显站群、Bing CJK 漂移污染样本。

### P0-3：把“公司名”从 career 单点触发中移除

career 不应被单个公司名触发。建议：

- 从 career `terms` 中移除或降级 `字节`。
- career 触发改为二段式：

```text
company_or_role_group:
  字节 / 腾讯 / 阿里 / 美团 / 产品经理 / 算法工程师 / 后端 / 前端

career_action_group:
  招聘 / 求职 / 岗位 / 薪资 / 面试 / 简历 / 校招 / 社招 / 面经 / offer / hc
```

触发条件：

- `career_action_group` 命中至少 1 个，才允许 career 成为 primary。
- 只有 `公司名` 命中时，不进入 career。
- 如果 query 含 `付费 / 订阅 / 价格 / 套餐 / 商业化 / 发布 / 上线 / 回应 / 会员`，显式压制 career，优先 `company_primary + industry + hot_trend`。

验收：

- `豆包 付费 订阅 字节跳动` 不再 route 到 career。
- `字节 AI 产品经理 校招 薪资 面经` 仍 route 到 career。
- `字节跳动 招聘 产品经理 薪资` 仍 route 到 career。

### P0-4：research query rewrite 必须验证角色，不让错误意图放大

research 当前会按 route/preset 生成多组 query。这个方向正确，但需要防止误判后放大噪声。

建议：

- `base` 原始 query 永远保留，并且在前两轮候选池中权重不低于意图扩写 query。
- 对 career/reputation/ecommerce 等样本型 query，先做一轮小型质量验证：如果 role query 的 top domain 过度集中且与主查询关键实体/语义组不匹配，降权或跳过。
- `query_strategy` 中新增 `variant_validation`：

```json
{
  "role": "career",
  "status": "suppressed",
  "reason": "product_subscription_terms_conflict_with_career_intent"
}
```

验收：

- `豆包 付费 订阅 字节跳动` 的 selected evidence 中，招聘站不超过 1 条，且不能排在主证据前列。
- career 真需求仍保持牛客、Boss、Levels、Glassdoor 等来源。

### P1-1：read fallback 从“路径 query”升级成“页面身份 query”

当前 `_query_from_url` 对数字路径很弱。建议：

- 先识别高价值媒体域名。
- 对 `ithome.com/0/946/250.htm` 这类路径，只把 URL 作为身份，不把数字路径当语义 query。
- 如果无法提取标题，兜底 query 应为：

```text
site:ithome.com 946250
site:ithome.com 0/946/250
ithome 946250
```

但返回结果必须满足：

- same-domain 优先。
- URL/path/id 相似度达标。
- title/snippet 中至少有一个非数字语义词，或者能命中原 URL 的 canonical/id。

如果不达标：

```text
selected_backend=search_fallback
fallback_status=unusable
reason=url_identity_not_resolved
agent_instruction=不要把兜底搜索当成原文；请使用 diagnose page 或 WebFetch 读取该 URL。
```

验收：

- IT之家直读失败时，不再输出大段无关搜索结果。
- 能找到同 URL 或同新闻标题时，才输出搜索兜底上下文。
- read quality report 明确 `usable=false`，且给 Agent 下一步。

### P1-2：Bing 继续作为补充后端，但中文场景默认更谨慎

建议：

- 保留 Bing，不删除。
- 中文 query 下，Bing 结果必须过 CJK drift gate。
- Bing 若返回 0 可用结果，trace 明确：

```text
bing_low_relevance_reason=upstream_cjk_retrieval_drift
agent_note=这是 Bing 上游中文候选池/排序漂移，不是观澜质量门槛过紧。
```

验收：

- `固态电池量产时间表`、`原研哉 设计哲学` 仍拒绝污染。
- 其他后端可用时，Bing 的 low relevance 不让最终结果为空。

### P1-3：将误杀样本纳入回归夹具

新增 fixtures：

- `policy_local_crossborder_ecommerce_zhuhai_2025`
- `policy_scope_gov_hengqin_salvage`
- `product_subscription_doubao_not_career`
- `read_fallback_ithome_unusable_search_context`
- `bing_cjk_drift_genshin_vs_hara_kenya`

建议新增测试：

- `tests/test_search_quality.py`
- `tests/test_router.py`
- `tests/test_webtools.py`
- `tests/test_read_fallback_quality.py` 或继续放在 `test_webtools.py`

验收：

- 全量测试通过。
- `guanlan quality backend-fixtures` 通过。
- `guanlan quality regression` 通过。
- release gate 通过。

## 六、建议施工顺序

### 第一阶段：先救误杀，不动大架构

1. 新增中文语义组工具函数。
2. 扩充政策/地方/产业/电商常见同义词。
3. 调整 batch gate：先算 group coverage，再决定是否 hard reject。
4. 增加强信源 salvage，并在 trace 中显式标注。
5. 补政策误杀回归测试。

风险控制：

- 不删除现有 `term_coverage`，先并行输出 `group_coverage`。
- 不降低 adult/unsafe/known_low_value_domain 过滤。
- 只对 policy/local/ecommerce/gov scope 开启第一批 group gate。

### 第二阶段：修 route/research 漂移

1. career 触发从单词命中改成组合命中。
2. 增加产品/订阅/商业化 suppress career 规则。
3. research query variants 增加轻量验证。
4. 补 `豆包 付费 订阅 字节跳动` 和真实 career query 对照测试。

风险控制：

- 不降低 career 真需求召回。
- route plan 中保留 secondary intent，但 primary 不误跳 career。

### 第三阶段：修 read fallback

1. `_query_from_url` 识别数字路径/弱路径。
2. `_read_search_context` 增加 same-url/same-domain/path-id 约束。
3. 无法验证的搜索兜底输出 `fallback_status=unusable`。
4. 补 IT之家样本测试。

风险控制：

- 不影响 21经济网、广东省政府网等已能直读的路径。
- 不把 fallback 搜索包装成原文证据。

### 第四阶段：更新 Agent 文档和质量说明

需要同步：

- `AGENTS.md`
- `docs/agent-playbook.md`
- `docs/agent-usage.md`
- `guanlan/skill/SKILL.md`
- `docs/contract.md`

新增说明：

- `quality_summary=warn` 不等于无结果。
- `partial_salvage` 表示观澜保留了强信源线索，但需要继续读原文。
- `search_fallback_unusable` 表示读 URL 失败且兜底搜索无法确认页面身份，不应引用。

## 七、验收标准

### 必过样本

```bash
guanlan search "珠海横琴 跨境电商政策 2025" --profile china --scope gov --limit 80 --trace
guanlan search "珠海横琴 跨境电商政策 2025" --profile china --limit 80 --trace
guanlan research "豆包 付费 订阅 字节跳动" --profile china --read-top 3 --limit 80
guanlan research "字节 AI 产品经理 校招 薪资 面经" --preset career --read-top 3 --limit 80
guanlan read "https://www.ithome.com/0/946/250.htm" --strict --quality-report
guanlan search "固态电池量产时间表" --backend bing --profile china --limit 30 --trace
guanlan search "原研哉 设计哲学" --backend bing --profile china --limit 30 --trace
```

### 结果标准

- 珠海横琴政策查询不能再空结果；至少保留 3 条强相关官方/地方官方候选。
- `--scope gov` 不能放宽到知乎、SEO 页或泛网页，但可以保留 `gov.cn` 子域和地方政府入口。
- 豆包订阅查询不能被 primary route 到 career。
- 真 career 查询不能被压成 product/company。
- IT之家 read 失败时，如果找不到同 URL/同新闻身份，不输出无关搜索结果作为上下文。
- Bing 漂移仍被拒绝，且说明是 Bing 上游中文召回问题。
- 默认结果池不得缩小，Agent 面向搜索/研究仍建议 80。

## 八、不建议的修法

不要做这些：

- 不要简单把 `term_coverage < 0.5` 改成更低阈值。这会放进更多 Bing/站群/拆字污染。
- 不要关闭 `cjk_compound_terms_missing`。它对固态电池、原研哉这类漂移仍然有价值。
- 不要把 Bing 删除。Bing 仍可作为补充后端和英文/部分中文兜底，只是中文需要强诊断。
- 不要让 read fallback 总是输出搜索结果。无关兜底比失败更危险。
- 不要做一次性大重构。先把质量门控和路由规则修稳，再考虑拆模块。

## 九、最终判断

这次问题很有价值：它暴露的不是“观澜质量系统太多余”，而是“观澜已经有了质量系统，但还没有足够中文任务结构感”。

下一步应该把观澜的质量门控从“防污染”进化成“既防污染，也不误杀一手证据”。这非常符合观澜的底层气质：临流观势，不只看水面有没有浪，也要分得清哪一朵是真浪，哪一朵只是光影。
