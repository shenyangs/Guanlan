# 观澜第一版发布冒烟样本

本文档用于 GitHub 第一版发布前的真实环境核对。它不是单元测试，而是一组人工可复跑的中文互联网样本，重点检查“能否找到、能否解释、能否降级、能否给 Agent 上下文”。

## 运行前提

- 在干净终端执行，确认当前安装来自本仓库。
- 不启用 `doctor --auth-check`，不主动触碰 Cookie、钥匙串或浏览器登录态。
- 网络不可用、搜索引擎限流、站点 403 时，不直接判定项目失败；记录失败后看是否给出了清晰错误或降级路径。

```bash
guanlan version
guanlan doctor --trace
guanlan search --list-scopes
guanlan research --list-presets
```

## 样本矩阵

| 编号 | 场景 | 命令 | 通过标准 |
| --- | --- | --- | --- |
| S1 | 党央媒/中央重点媒体 | `guanlan search "人工智能 新质生产力" --profile china --scope party_central --limit 5 --trace` | 有结果时应优先出现党央媒/中央重点媒体；无结果时 trace 应说明 backend/error。 |
| S2 | 政府/部委 | `guanlan research "人工智能 政策" --preset policy --read-top 1 --max-read-chars 1200` | 输出研究证据包，包含 `gov`/`party_central` 搜索范围、来源概览和阅读结果或阅读错误。 |
| S3 | 核心地方官媒 | `guanlan search "低空经济 广东" --profile china --scope local_official --limit 5 --format context` | 输出紧凑上下文，结果应偏地方官媒或地方公开报道。 |
| S4 | 电商/零售垂类 | `guanlan search "跨境电商 AI" --profile china --scope ecommerce --limit 5 --trace` | 亿邦动力、网经社、雨果跨境等垂类域名应被 scope 识别；排序 trace 可解释。 |
| S5 | 技术/开发者社区 | `guanlan research "Python Agent 框架 对比" --preset tech --read-top 1 --max-read-chars 1200` | 输出技术证据包，结果应混合技术社区、开发者站点或 GitHub。 |
| S6 | 社交公开页口碑 | `guanlan research "某产品 用户评价" --preset reputation --read-top 0 --format context` | 不要求登录态；应返回公开网页层面的口碑线索，而不是触发社交账号批量读取。 |
| S7 | URL 阅读降级 | `guanlan read "https://www.gov.cn/" --max-chars 1200 --fallback-search` | 能返回正文、首页文本，或给出清晰的搜索兜底上下文。 |
| S8 | 热榜 | `guanlan hotnews baidu --limit 10` | 输出 `观澜热榜` Markdown，单条异常不应导致整个 CLI 崩溃。 |
| S9 | MCP 工具面 | `uv run python -c "from guanlan.integrations.mcp_server import _tool_definitions; print([t['name'] for t in _tool_definitions()])"` | 输出包含 `guanlan_search`、`guanlan_read`、`guanlan_research`、`guanlan_hotnews`、`guanlan_status`。 |

## 记录格式

发布前建议记录下面信息：

```text
日期：
网络环境：
观澜版本：
Python 版本：
通过样本：
失败样本：
失败是否有清晰诊断：
是否出现钥匙串/Cookie/浏览器授权弹窗：
```

第一版允许部分公开站点因为网络、反爬或限流失败；不允许默认诊断触发敏感授权弹窗，不允许错误信息泄露 Cookie、Token、代理密码或其他原值。

## 本轮验证摘要

2026-05-01 在当前开发环境完成了第一轮公开网络冒烟：

- `guanlan hotnews baidu --limit 3` 通过，返回百度热榜 Markdown。
- `guanlan search "人工智能 新质生产力" --profile china --scope party_central --limit 3 --trace` 通过，返回人民网、新华网、央视网等党央媒/中央重点媒体结果，并输出评分 trace。
- `guanlan search "跨境电商 AI" --profile china --scope ecommerce --limit 3 --format context` 通过，返回亿欧、网经社、亿邦动力等电商/零售垂类结果。
- `guanlan read "https://www.gov.cn/" --max-chars 600 --fallback-search` 通过，返回中国政府网首页 Markdown。
