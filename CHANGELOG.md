# 观澜更新日志

本文记录观澜每个版本的能力变化、边界调整和下一步收口方向。

格式遵循“未发布 / 已发布”两段：`Unreleased` 只记录已经决定进入下一轮的计划，不代表已经完成；带版本号的条目只记录已经随 tag 发布的内容。

## Unreleased

- 暂无。下一轮变更先进入这里，发版时再移入对应版本。

## v0.1.6 - 2026-05-01

### Changed

- README、Agent 使用说明和 skill 搜索参考补充 NewsNow 可选热榜增强入口。
- 热榜说明区分原生稳定源 `baidu/v2ex` 与 `newsnow:<source>` best-effort 增强源，避免把外部后端误认为原生稳定能力。
- 文档补充 `newsnow-base-url` 配置方式，提示公共 NewsNow 不稳时可切换自有 endpoint。

### Verified

- 复用已有 NewsNow backend、source catalog、CLI 配置和测试覆盖。
- 版本同步到 `0.1.6`。

## v0.1.5 - 2026-05-01

### Added

- `doctor --trace` 和 `status` 增加 `readiness` / `verification` 展示，区分 `verified`、`backend-ready`、`best-effort` 和 `unavailable`。
- `status` 增加“就绪”和“验证”列，避免把后端存在误读为端到端稳定。
- 增加安装与发布 smoke 脚本 `scripts/release_smoke.sh`，覆盖 `pip install .`、可用时的 `pipx install .`、`guanlan --version`、`guanlan install --env=auto` 安全预演和 `guanlan status`。
- 增加版本一致性测试，校验 `pyproject.toml` 与 `guanlan.__version__` 保持一致。
- 增加直连 HTML 正文抽取测试，覆盖导航、页脚、登录按钮等噪音过滤。
- `research --advisor` 增加谨慎辅助判断，输出意图假设、证据支持、证据边界、场景化建议和下一步行动。
- MCP `guanlan_research` 增加 `advisor` 参数，可把辅助判断一起输出给 Agent 上下文。

### Changed

- 微信公众号能力口径改为诚实模式：检测到 Exa、WechatSogou 或 Camoufox 只报告 `backend-ready / unverified / best-effort`，不再因为 Exa 存在就返回 `ok` 或暗示端到端稳定。
- `read --backend direct` 的 HTML 抽取增加正文候选选择、页面 chrome 清理和噪音行过滤，降低导航、页脚、登录/分享按钮混入正文的概率。
- 知乎热榜口径降级为明确的 `experimental`，失败时提示 `site:zhihu.com` 搜索 fallback。
- README、安装文档和 Agent 文档明确 CLI-first，MCP 只是 Agent/平台集成的可选路径。
- README 增加“当前最稳能力”小节，只列公开搜索、白名单 scope、网页阅读、稳定热榜、研究证据包和本地知识库。
- 微信、知乎、小红书、微博等高关注渠道增加现实预期说明。

### Verified

- 针对性测试已覆盖 doctor/status、微信口径、知乎 fallback、正文抽取、advisor/MCP、版本一致性和 release smoke 脚本。
- `ruff check .` 通过。
- `pytest -q` 通过，`172 passed`。
- `uv build` 成功生成 `guanlan-0.1.5` wheel 和 sdist。
- `scripts/release_smoke.sh` 通过，验证 `pip install .`、可用时的 `pipx install .`、CLI 入口和 `status`。

## v0.1.4 - 2026-05-01

### Added

- 增加时效性搜索识别：`最近`、`近期`、`热点`、`热搜`、`最新`、`快讯`、`本周`、`今天` 等词会触发时间窗口。
- 搜索请求会在时效性意图下补当前年月或具体日期，帮助上游搜索收束时间线。
- 搜索排序增加 `recency_boost` 与 `stale_penalty`，优先近期结果，降权明显陈旧内容。
- `--trace` 增加结果日期、窗口大小、是否落入窗口等时效性解释。
- 增加测试覆盖，避免英文子串误触发时效搜索，例如 `knowledge` 不应被 `news` 误命中。

### Changed

- `pyproject.toml`、`guanlan.__version__` 和 `uv.lock` 同步到 `0.1.4`。
- README 和 Agent 文档补充近期热点搜索使用说明。

### Verified

- `ruff check .` 通过。
- `pytest -q` 通过，`163 passed`。
- `uv build` 成功生成 `guanlan-0.1.4` wheel 和 sdist。
- GitHub release workflow 成功发布 PyPI `guanlan 0.1.4`。

## v0.1.3 - 2026-05-01

### Added

- 增加安全版话题回响分析 `guanlan pulse`。
- `pulse` 默认基于公开搜索摘要输出讨论倾向、关键词信号、争议点、来源分布和边界提醒。
- MCP 工具面增加 `guanlan_pulse`。
- 增加 `pulse` 单元测试和 MCP 测试。

### Changed

- README、Agent 使用说明和 skill 文档补充 `pulse` 使用方式。
- 发布自动化文档更新到 `0.1.3`。

## v0.1.2 - 2026-05-01

### Added

- 增强 `read` 自动降级路径：Jina Reader 不稳时可回退到 direct HTML 或搜索兜底上下文。
- 微信搜索路径补充可选依赖与 Sogou WeChat backend 说明。
- 增加更多 `webtools` 测试，覆盖缓存、批量读取、fallback 和搜索解释。

### Changed

- README 的安装文档改为更适合小白和 Agent 使用的路径。
- 更新发布工作流与依赖锁定文件。

## v0.1.1 - 2026-05-01

### Added

- 增加来源分布诊断 `--source-chart`，用 ASCII 图展示来源类型和域名分布。
- 增加本地知识库能力：`guanlan archive add/search/export`。
- MCP 工具面增加本地知识库搜索入口。
- 增加 PyPI 发布和 Homebrew tap 自动更新 workflow。

### Changed

- README 和 Agent 文档补充来源分布、本地知识库和发布自动化说明。
- 版本同步到 `0.1.1`。

## v0.1.0 - 2026-05-01

### Added

- 观澜第一版发布。
- 确立 CLI-first 的中文互联网研究工具定位。
- README 改为中文主文档，重写项目表达、设计原则、能力图谱、安装方式和使用场景。
- 增加 MIT License、NOTICE 和来源说明。
- 建立基础版本元数据与项目发布骨架。
