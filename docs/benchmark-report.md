# 观澜 Benchmark Report

版本：v0.5.0  
日期：2026-05-03  
状态：公开样本池已锁定；离线基线进入 release gate，真实网络三组对比持续复跑补数。

## 摘要

本报告的目标不是证明“观澜永远比普通搜索多搜到几条链接”，而是验证一个更适合 Agent 的问题：

> 面对中文互联网研究任务，Agent 是否拿到了正确的信源类型、清楚的证据边界、足够大的候选池，以及可审计的证据包？

当前自动化基线：

| 检查 | 命令 | 结果 | 说明 |
| --- | --- | --- | --- |
| Deterministic route gate | `guanlan eval benchmark` | 已进 release gate | 不联网，检查意图、scope、证据角色和候选池下限。 |
| Public eval suite | `guanlan eval suite run chinese-web-v1` | 100/100 pass | 不联网，覆盖政策、地方、电商、技术、财经、口碑、热点、学术、文娱、本地模型联网。 |
| Live sample pool | 本报告 80 题 | 样本已锁定 | 用于后续真实网络复跑和三组对比，不把网络波动伪装成确定结论。 |

本报告后续应逐步补齐真实网络得分。没有跑过的分数不在本文中伪造。

## 对比对象

每个任务对比三组输出：

| 组别 | 方法 | 代表命令/行为 | 观察重点 |
| --- | --- | --- | --- |
| A | 普通搜索 | 浏览器搜索、Agent 内置 web_search 或通用搜索 API | 是否命中正确来源；是否被 SEO、英文漂移或二手内容带偏。 |
| B | Guanlan search | `guanlan search "query" --profile china --limit 80 --trace` | 是否保留来源身份、评分 trace、候选池和时效窗口。 |
| C | Guanlan route + research | `guanlan route "query" --json` + `guanlan research "query" --profile china --limit 80 --advisor` | 是否形成可审计证据包，是否区分官方、媒体、社区样本和风险边界。 |

## 评分指标

每个任务 5 项，每项 0/1/2 分，总分 10 分。

| 指标 | 2 分 | 1 分 | 0 分 |
| --- | --- | --- | --- |
| 正确信源类型 | 命中任务需要的官方、地方、垂类、开发者、学术、社区或热榜来源。 | 有部分相关来源，但主证据偏窄或混杂。 | 主证据类型错误，或被无关页面主导。 |
| 证据边界 | 明确区分“谁说的”、平台属性、样本偏差、时间和风险。 | 有来源链接，但边界说明不足。 | 把不同角色证据混为一谈。 |
| 英文漂移控制 | 中文任务不被无关英文页面、SEO 页面或平台首页带偏。 | 有少量漂移，但不影响主结论。 | 英文/SEO/首页主导结果。 |
| 候选池充足 | 候选池至少 80，来源多样，适合 Agent 筛选。 | 候选池不足但仍有可用线索。 | 样本太少，无法支撑判断。 |
| 可审计证据包 | 有 trace、route/research 结构、selected evidence、读页质量或下一步建议。 | 有部分证据结构，但审计链不完整。 | 只有片段或无来源总结。 |

## 80 个真实任务样本

### 政策 10

| ID | Query | 期望信源类型 |
| --- | --- | --- |
| policy_01 | 新质生产力 政策 原文 | 中央政府、部委、党央媒 |
| policy_02 | 人工智能治理 暂行办法 官方 原文 | 部委/网信办/官方发布 |
| policy_03 | 数据要素 政策 国家发改委 原文 | 国家发改委、国务院、权威解读 |
| policy_04 | 低空经济 政策 官方口径 | 国务院、发改/工信/民航等官方源 |
| policy_05 | 制造业 数字化转型 政策 部委 | 工信部、地方经信、党央媒 |
| policy_06 | 算力基础设施 政策 国家数据局 | 国家数据局、发改委、官方发布 |
| policy_07 | 人形机器人 产业政策 部委 | 工信部、地方政府、产业政策原文 |
| policy_08 | 生成式人工智能 服务 管理办法 官方 | 网信办/部委官方原文 |
| policy_09 | 民营经济促进法 官方 解读 | 全国人大/新华社/人民日报/部委 |
| policy_10 | 银发经济 政策 国务院 原文 | 国务院、民政/发改等官方源 |

### 地方 10

| ID | Query | 期望信源类型 |
| --- | --- | --- |
| local_01 | 上海 人工智能 产业政策 原文 | 上海市政府、经信委、官方媒体 |
| local_02 | 深圳 低空经济 政策 原文 | 深圳政府、发改/工信部门 |
| local_03 | 杭州 算力券 政策 官方 | 杭州政府、经信/科技部门 |
| local_04 | 成都 人工智能 产业扶持 政策 | 成都政府、产业主管部门 |
| local_05 | 苏州 生物医药 产业政策 原文 | 苏州政府、园区/工信部门 |
| local_06 | 合肥 新能源汽车 产业政策 官方 | 合肥政府、发改/经信部门 |
| local_07 | 广州 直播电商 政策 扶持 官方 | 广州政府、商务部门 |
| local_08 | 武汉 光电子 信息产业 政策 官方 | 武汉政府、东湖高新区 |
| local_09 | 南京 集成电路 产业政策 原文 | 南京政府、开发区官方源 |
| local_10 | 青岛 低空经济 产业园 政策 官方 | 青岛政府、地方官方媒体 |

### 电商 10

| ID | Query | 期望信源类型 |
| --- | --- | --- |
| ecommerce_01 | 即时零售 电商 产业趋势 亿邦动力 | 垂类媒体、平台公告、行业报告 |
| ecommerce_02 | 跨境电商 AI 工具 卖家反馈 | 亿邦动力、雨果跨境、卖家样本 |
| ecommerce_03 | 抖音电商 商家 服务商 趋势 | 平台公告、垂类媒体、商家样本 |
| ecommerce_04 | 美团 闪购 即时零售 商家 案例 | 平台公告、垂类媒体、案例报道 |
| ecommerce_05 | 淘宝天猫 AI 电商 产品趋势 | 平台官方、垂类媒体、商家反馈 |
| ecommerce_06 | 京东 内容电商 直播 生态 趋势 | 京东官方、垂类媒体、行业分析 |
| ecommerce_07 | 拼多多 跨境 Temu 商家 成本 风险 | 平台规则、卖家样本、行业媒体 |
| ecommerce_08 | 小红书 电商 买手 直播 口碑 | 平台公开信息、社区样本、垂类媒体 |
| ecommerce_09 | 私域电商 视频号 商家 增长 案例 | 微信公开信息、垂类媒体、案例 |
| ecommerce_10 | 2026 电商 大促 消费趋势 报告 | 垂类媒体、平台战报、行业报告 |

### 技术 10

| ID | Query | 期望信源类型 |
| --- | --- | --- |
| tech_01 | vLLM SGLang KV Cache 推理框架 对比 | GitHub、文档、issue、开发者讨论 |
| tech_02 | LangGraph AutoGen CrewAI GitHub issue 对比 | GitHub、官方文档、社区讨论 |
| tech_03 | MCP server Python SDK issue 实践 | GitHub、官方文档、开发者博客 |
| tech_04 | RAG reranker bge m3 中文 实测 | 论文/模型卡、GitHub、技术社区 |
| tech_05 | Ollama 本地模型 联网搜索 工具 | 官方文档、GitHub、教程样本 |
| tech_06 | Qwen 本地部署 vLLM 性能 参数 | 官方模型卡、GitHub、开发者实测 |
| tech_07 | OpenWebUI RAG 导入 中文文档 | 官方文档、GitHub issue、教程 |
| tech_08 | Dify 工作流 Agent MCP 集成 | 官方文档、GitHub、社区实践 |
| tech_09 | Milvus Qdrant Chroma 中文 RAG 对比 | 官方文档、GitHub、技术文章 |
| tech_10 | AI Agent 浏览器自动化 安全 风险 | 官方文档、安全讨论、开发者社区 |

### 学术 10

| ID | Query | 期望信源类型 |
| --- | --- | --- |
| academic_01 | EI会议 投稿 检索 收录 要求 | EI/Engineering Village、会议官网、出版商 |
| academic_02 | CCF 推荐会议 人工智能 投稿 官网 | CCF、会议官网、出版商 |
| academic_03 | SCI 期刊 APC 出版商 官方说明 | 出版商官网、期刊官网 |
| academic_04 | 高校 科研奖励 论文认定 政策 | 高校/学院官方政策 |
| academic_05 | arXiv 论文 代码 GitHub 中文解读 | arXiv、GitHub、技术解读 |
| academic_06 | Scopus 收录会议 查询 官方 | Scopus、会议官网、出版商 |
| academic_07 | Web of Science 期刊 检索 官方 | Clarivate、期刊官网、出版商 |
| academic_08 | 计算机硕士 导师 研究方向 院系官网 | 高校院系、导师主页、招生网 |
| academic_09 | 论文撤稿 查询 官方 数据库 | Retraction Watch、出版商、期刊官网 |
| academic_10 | ACL 会议 投稿 deadline 官网 | ACL/会议官网、CFP 官方源 |

### 口碑 10

| ID | Query | 期望信源类型 |
| --- | --- | --- |
| reputation_01 | 某 AI 笔记软件 用户评价 值不值得买 | 社区样本、产品页、评测 |
| reputation_02 | AI 眼镜 用户评价 小红书 知乎 | 用户样本、社区讨论、评测媒体 |
| reputation_03 | 新能源汽车 车主评价 缺点 | 车主样本、汽车媒体、投诉/论坛 |
| reputation_04 | 儿童学习机 用户反馈 真实体验 | 家长样本、评测、平台评论 |
| reputation_05 | 国产数据库 用户口碑 迁移成本 | 开发者社区、案例、官方文档 |
| reputation_06 | 某 SaaS 软件 客户评价 续费 风险 | 用户样本、企业案例、公开评论 |
| reputation_07 | 扫地机器人 用户评价 避坑 | 电商评论、社区样本、评测 |
| reputation_08 | AI 编程工具 Cursor Windsurf 用户评价 | 开发者社区、GitHub、社交样本 |
| reputation_09 | 某在线教育产品 家长 投诉 口碑 | 用户样本、投诉平台、媒体报道 |
| reputation_10 | 某国产大模型 API 稳定性 用户反馈 | 开发者社区、官方状态页、技术样本 |

### 热点 10

| ID | Query | 期望信源类型 |
| --- | --- | --- |
| hot_01 | 今天 中文互联网 热点 AI | 多源热榜、媒体快讯、社区讨论 |
| hot_02 | 今天 微博 B站 科技 热点 | 微博/B站热榜、科技媒体 |
| hot_03 | 最近 AI 应用 创业 热点 | 热榜、RSS、创业/科技媒体 |
| hot_04 | 今天 财经 市场 热点 财联社 | 财经快讯、交易所/公司公告辅助 |
| hot_05 | 最近 开发者社区 热门项目 | GitHub/V2EX/HN/RSS |
| hot_06 | 今天 消费 品牌 热点 社交平台 | 热榜、垂类媒体、社区样本 |
| hot_07 | 最近 影视 综艺 明星 热议 | 微博/B站/豆瓣/文娱媒体 |
| hot_08 | 今天 政策 发布 热点 国务院 | 官方发布、党央媒、热榜辅助 |
| hot_09 | 最近 安全漏洞 热点 CVE | CVE/NVD/CISA/厂商公告 |
| hot_10 | 今天 台风 地震 灾害 预警 | 气象/应急官方、权威媒体 |

### 本地模型 Prompt 10

| ID | Query | 期望信源类型 |
| --- | --- | --- |
| local_llm_01 | 给本地 Ollama 模型联网搜索 中文政策信息 | 官方源 + prompt-ready evidence |
| local_llm_02 | Open WebUI 调用本地 HTTP 搜索证据 | 本地 HTTP/CLI 文档、示例 |
| local_llm_03 | LM Studio 本地模型 RAG 导入 中文网页 | RAG 导出、本地模型文档 |
| local_llm_04 | 本地模型 读取网页 生成引用证据 | read/research/context 输出 |
| local_llm_05 | 无联网大模型 获取今日热点 上下文 | hotnews + context/prompt |
| local_llm_06 | 用本地模型 分析政策 原文 需要哪些证据 | 官方源 + 证据边界 prompt |
| local_llm_07 | Ollama 分析用户口碑 避免样本偏差 | 社区样本 + caveat prompt |
| local_llm_08 | 本地 RAG 导入 观澜 archive jsonl | archive pack/export |
| local_llm_09 | 本地模型 比较两个产品 需要证据包 | compare/research context |
| local_llm_10 | 本地模型 追踪事件时间线 需要引用 | timeline context |

## 复跑流程

### A. 普通搜索

每个任务用同一 query 在普通搜索或 Agent 内置 `web_search` 中执行。记录前 10 条结果：标题、URL、摘要、时间、是否官方/垂类/社区/热榜。

### B. Guanlan search

```bash
guanlan search "QUERY" --profile china --limit 80 --trace --format json > search.json
```

对技术/AI 类任务额外跑 RSS：

```bash
guanlan feeds curated --category ai --limit 80 --format json > feeds.json
```

### C. Guanlan route + research

```bash
guanlan route "QUERY" --json > route.json
guanlan research "QUERY" --profile china --limit 80 --advisor --format json > research.json
```

近期/热点类任务额外跑：

```bash
guanlan hotnews today --limit 80 --trends --json > hotnews.json
```

## 结果记录表

| ID | 普通搜索 | Guanlan search | Guanlan route+research | 备注 |
| --- | ---: | ---: | ---: | --- |
| policy_01 | 待测 | 待测 | 待测 | 首轮真实网络报告补齐。 |
| local_01 | 待测 | 待测 | 待测 | 首轮真实网络报告补齐。 |
| ecommerce_01 | 待测 | 待测 | 待测 | 首轮真实网络报告补齐。 |
| tech_01 | 待测 | 待测 | 待测 | 技术类需检查 RSS 二次发现。 |
| academic_01 | 待测 | 待测 | 待测 | 学术类需区分数据库/出版商/高校。 |
| reputation_01 | 待测 | 待测 | 待测 | 口碑类需检查样本偏差提醒。 |
| hot_01 | 待测 | 待测 | 待测 | 热点类需检查时间窗口和 hotnews。 |
| local_llm_01 | 待测 | 待测 | 待测 | 本地模型类需检查 prompt-ready context。 |

完整 80 题评分建议使用 JSONL 或表格保存，避免手工编辑 README。

## 当前初步结论

目前可以公开承诺的是：

- Guanlan 已有 deterministic benchmark 和 release gate，用来防止路由、证据角色、候选池和关键字段退化。
- 80 个真实任务样本已锁定，覆盖中文互联网最常见的八类 Agent 研究任务。
- 三组对比方法已经明确，后续可以持续补真实网络得分。
- 真实网络结果必须区分“Guanlan 能力问题”和“网络/上游/源站波动”，不能把超时直接记成“无结果”。

暂不公开承诺的是：

- 不声称所有社交平台端到端稳定。
- 不声称 live benchmark 已经完整跑完。
- 不把普通搜索的表现写成假想分数。
- 不把一次网络波动当作模型或工具能力结论。

## 下一步

1. 建立 `benchmark-runs/` 或外部表格，保存每次真实网络复跑的 JSON 输出。
2. 固定评分员规则：每题 5 项，每项 0/1/2 分，至少两轮复核。
3. 首轮先跑 8 个代表任务，每类 1 个，确认评分表可用。
4. 第二轮跑完整 80 题，发布带分数的 `benchmark-report.md` 更新版。
5. 后续每个大版本保留一份历史报告，观察是否变宽、变稳、变可审计。
