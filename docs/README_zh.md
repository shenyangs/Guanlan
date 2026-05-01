# 观澜 / Guanlan 中文文档

这里是观澜的中文入口。根目录 [README.md](../README.md) 已经改为中文主文档，优先说明项目定位、设计原则、安全边界和面向中文互联网的能力路线。

## 推荐阅读顺序

| 文档 | 适合什么时候看 |
| --- | --- |
| [README.md](../README.md) | 第一次了解观澜：它是什么、为什么存在、默认边界是什么。 |
| [Agent 使用说明](agent-usage.md) | 给 AI Agent 的搜索、阅读、热榜、社交平台和安全降级规则。 |
| [安装指南](install.md) | 让 Agent 按步骤安装、配置和自检。 |
| [发布自动化](release-automation.md) | 维护者用：PyPI 自动发布与 Homebrew tap 自动更新。 |
| [排障手册](troubleshooting.md) | 遇到钥匙串弹窗、网络异常、Cookie 或平台失败时排查。 |
| [中文互联网设计](chinese-web-design.md) | 查看产品方案、平台矩阵和阶段路线。 |
| [发布冒烟样本](release-smoke-samples.md) | 第一版发布前的真实中文查询样本和通过标准。 |
| [Cookie 导出](cookie-export.md) | 需要手动提供 Cookie 时，按安全方式导出。 |
| [来源说明](SOURCE_ATTRIBUTION.md) | 查看本项目参考过的开源项目。 |

## 当前重点

- 默认 `guanlan doctor` 不读取浏览器 Cookie，不主动触碰 macOS 钥匙串。
- 如需定位诊断路径，使用 `guanlan doctor --trace`。
- 如需深度检查登录态，才使用 `guanlan doctor --auth-check`。
- Agent 基础搜索/阅读命令已经可用：`guanlan search "关键词"`、`guanlan search "关键词" --profile china`、`guanlan search "关键词" --scope party_central`、`guanlan read "URL"`。
- 搜索质量层已经可用：多后端聚合、URL 去重、中文信源分类、可信度评分和 scope 语境优先。
- 来源分布诊断已经可用：`guanlan search "关键词" --source-chart`、`guanlan research "关键词" --source-chart`。
- 安全版话题回响已经可用：`guanlan pulse "关键词" --format context`，默认只基于公开搜索样本输出倾向、置信度和边界提醒。
- Jina Reader 已作为第一读取入口，但不是唯一依赖；读取不稳时可用 `guanlan read "URL" --backend direct` 直连原网页。
- 本地知识库雏形已经可用：`guanlan archive add "URL"`、`guanlan archive search "关键词" --format context`、`guanlan archive export --format jsonl`。
- 第一批原生热榜命令已经可用：`guanlan hotnews list`、`guanlan hotnews baidu --limit 10`、`guanlan hotnews v2ex --json`。
- 观澜当前优先强化中文搜索、热榜聚合、社交口碑、视频、财经和开发者社区。
