# 观澜 / Guanlan 中文文档

这里是观澜的中文入口。根目录 [README.md](../README.md) 已经改为中文主文档，优先说明项目定位、设计原则、安全边界和面向中文互联网的能力路线。

## 推荐阅读顺序

| 文档 | 适合什么时候看 |
| --- | --- |
| [README.md](../README.md) | 第一次了解观澜：它是什么、为什么存在、默认边界是什么。 |
| [更新日志](../CHANGELOG.md) | 查看每个版本的能力变化、边界调整和下一步收口。 |
| [本地大模型联网指南](local-llm.md) | 让 Ollama、LM Studio、Open WebUI 等无联网模型使用观澜证据包。 |
| [Agent 使用说明](agent-usage.md) | 给 AI Agent 的搜索、阅读、热榜、社交平台和安全降级规则。 |
| [安装指南](install.md) | 让 Agent 按步骤安装、配置和自检。 |
| [排障手册](troubleshooting.md) | 遇到钥匙串弹窗、网络异常、Cookie 或平台失败时排查。 |
| [Cookie 导出](cookie-export.md) | 需要手动提供 Cookie 时，按安全方式导出。 |
| [来源说明](SOURCE_ATTRIBUTION.md) | 查看本项目参考过的开源项目。 |

## 维护者资料

下面这些资料主要服务维护、发布、质量验收或设计复盘，不建议作为官网和 README 的主入口展示：

| 文档 | 适合什么时候看 |
| --- | --- |
| [路线图](roadmap.md) | 跟踪后续迭代主线、验收标准和暂不做事项。 |
| [中文互联网设计](chinese-web-design.md) | 查看产品方案、平台矩阵和阶段路线。 |
| [质量测试计划](quality-test-plan.md) | 维护者发布前检查搜索、热榜、阅读、趋势和 advisor 质量。 |
| [发布冒烟样本](release-smoke-samples.md) | 第一版发布前或回归测试时复跑真实中文查询样本。 |
| [发布自动化](release-automation.md) | 维护者配置 PyPI 自动发布与 Homebrew tap 自动更新。 |
| [依赖锁定](dependency-locking.md) | 维护者更新依赖约束和复现实验环境。 |
| [MCP 配置示例](examples/mcporter.json) | 可选第三方 MCP 工具配置样例，不是观澜默认运行配置。 |
| [匿名遥测](telemetry.md) | 命令生命周期元数据采集、关闭方式与自托管配置。 |

## 当前重点

- 默认 `guanlan doctor` 不读取浏览器 Cookie，不主动触碰 macOS 钥匙串。
- 如需定位诊断路径，使用 `guanlan doctor --trace`。
- 如需深度检查登录态，才使用 `guanlan doctor --auth-check`。
- `guanlan status` 已区分 `verified`、`backend-ready`、`best-effort`，避免把后端存在误读为端到端稳定。
- Agent 基础搜索/阅读命令已经可用：`guanlan search "关键词"`、`guanlan search "关键词" --profile china`、`guanlan search "关键词" --scope party_central`、`guanlan read "URL"`。
- 搜索质量层已经可用：多后端聚合、URL 去重、中文信源分类、可信度评分、scope 语境优先和近期/热点类查询的时间收束。
- 来源分布诊断已经可用：`guanlan search "关键词" --source-chart`、`guanlan research "关键词" --source-chart`。
- 安全版话题回响已经可用：`guanlan pulse "关键词" --format context`，默认只基于公开搜索样本输出倾向、置信度和边界提醒。
- Jina Reader 已作为第一读取入口，但不是唯一依赖；读取不稳时可用 `guanlan read "URL" --backend direct` 直连原网页。
- 本地知识库已经可用：`guanlan archive add "URL"`、`guanlan archive search "关键词" --format context --trace`、`guanlan archive inspect 1`、`guanlan archive reindex`、`guanlan archive export --format rag-jsonl`；联网入库会返回 `ingest_audit`，解释为什么保留或跳过候选。
- 发版前稳健性闸门：`guanlan quality coverage`、`guanlan quality regression`、`guanlan quality robustness`、`guanlan eval benchmark`，或直接运行 `scripts/release_gate.sh`。
- 本地模型联网入口已经可用：`guanlan prompt "问题"`、`guanlan research "问题" --format prompt`、`guanlan mcp config --client codex`。
- 进阶能力已经有第一版骨架：`guanlan serve` 本地只读 HTTP、`hotnews --trends` 趋势归并、`archive ingest-research --dry-run` RAG 沉淀、`plugin register/template` 企业只读 connector、`eval scenarios` 评估集。
- 第一批原生热榜命令已经可用：`guanlan hotnews list`、`guanlan hotnews baidu --limit 50`、`guanlan hotnews v2ex --json`；`zhihu` 是 experimental 源，失败时使用搜索 fallback。
- 观澜当前优先强化中文搜索、热榜聚合、社交口碑、视频、财经和开发者社区。
