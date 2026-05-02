# 观澜更新日志

本文记录观澜每个版本的能力变化、边界调整和下一步收口方向。

格式遵循“未发布 / 已发布”两段：`Unreleased` 只记录已经决定进入下一轮的计划，不代表已经完成；带版本号的条目只记录已经随 tag 发布的内容。

## Unreleased

- 暂无。下一轮变更先进入这里，发版时再移入对应版本。

## v0.1.12 - 2026-05-02

### Added

- 新增 `guanlan prompt "问题"`，直接生成适合 Ollama、LM Studio、Open WebUI 等本地模型使用的完整联网 Prompt。
- `search`、`research`、`read` 和 `read batch` 增加 `--format prompt`，输出“证据 + 回答规则 + 用户问题”的本地模型输入格式。
- `research` 增加精选代表证据层，从 50-100 条广搜候选池中挑出多 topic、多信源、多域名的代表材料。
- 新增 `guanlan mcp config`，输出可复制的 MCP 客户端配置，支持 `generic`、`claude`、`cursor`、`codex`、`openwebui` 口径。
- 新增 `docs/local-llm.md`，说明无联网本地模型如何通过 CLI、Prompt 和 MCP 接入观澜。

### Changed

- `research --format context` 默认优先输出精选代表证据，而不是把完整候选池直接塞给模型。
- 直连网页阅读继续加强正文去噪，过滤登录、APP、推荐、相关阅读、评论、广告等页面噪声块。
- MCP `guanlan_search` 和 `guanlan_research` 增加 `prompt` 输出格式，方便支持 MCP 的本地 Agent 直接拿完整上下文。
- P0/P1 路线在产品哲学文档中标记为已落地。

## v0.1.11 - 2026-05-02

### Added

- 新增 `docs/product-philosophy.md`，沉淀观澜的产品哲学：信源身份、中文平台孤岛、证据包、安全授权、动态观察，以及“专业调研员思维框架”的长期方向。
- 新增本地大模型联网计划，覆盖 CLI 前置器、MCP 工具层、只读 HTTP 服务和 archive/RAG 路线，帮助 Ollama、LM Studio、Open WebUI 等无联网模型接入中文互联网证据。

### Changed

- Agent 指令层明确提醒：搜索、研究、热榜、回响和归档检索应优先使用 50+ 候选池，复杂研究可提高到 80-100，再由 Agent 筛选代表证据。
- `research --advisor` 从固定建议块调整为“助理视角规则”，输出证据边界、写作规则、可展开方向和响应边界，让调用 Agent 自行生成自然建议。
- MCP tool 描述同步提示扩大 limit，并明确 advisor 返回的是 evidence-bound writing rules，不是最终建议或用户真实意图。
- README 增加产品哲学入口，并把观澜定位为面向 AI Agent 的中文互联网专业调研框架，而不仅是通用搜索封装。

## v0.1.10 - 2026-05-02

### Added

- 显性化“助理视角”能力：`guanlan research --advisor` 在研究证据包后追加谨慎假设块，覆盖可能意图、证据支持边界和下一步建议。
- MCP `guanlan_research` 增强 `advisor` 字段描述和工具说明，明确适用场景与边界，避免把假设性判断当作用户真实意图。

### Changed

- README、Agent 使用说明、Skill 文档和 Web 参考补充 `--advisor` 用法与安全边界，便于 Agent 在“要建议/要下一步/问为什么搜这个”场景默认使用。
- MCP 回归测试增加对 `advisor` 描述文本的断言，防止后续文案回退成隐性能力。

## v0.1.9 - 2026-05-02

### Changed

- 将 CLI 搜索默认候选池从 8 提升到 50，避免 Agent 只基于少量结果做排序和归纳。
- 将研究证据包各 preset 默认搜索量统一提升到 50，MCP `guanlan_research` schema 上限提升到 100。
- 将本地知识库 `archive search/list` 默认结果提升到 50，MCP `guanlan_archive_search` 上限提升到 100。
- 将 `hotnews` 默认热榜条数提升到 50，MCP 上限提升到 100；今日多源聚合单源抓取上限同步提高，避免 50 条请求被单源上限截断。
- 将 `read` 和 `archive add` 的搜索兜底默认结果提升到 20，MCP `fallback_limit` 上限同步提升到 20。
- 将 `pulse` 默认公开样本池提升到 50，MCP 上限提升到 100。
- 将 V2EX、雪球 channel 的 hot/search 默认 limit 上调到 50。

### Added

- 新增 `guanlan.limits` 统一维护 CLI、MCP、内部函数的默认结果数和 schema 上限。
- 增加 CLI、MCP、热榜聚合和 research 默认 limit 回归测试，防止后续默认值回落。

## v0.1.8 - 2026-05-02

### Added

- 增加搜索质量画像 `query_quality`，识别政策、地方、电商、财经、技术和口碑等查询意图。
- 搜索排序增加 `intent_fit` 与 `source_quality` 因子，不同查询意图会偏好不同信源类型。
- `guanlan search --trace` 增加 query quality、命中数和质量警告，帮助 Agent 解释排序原因。
- 时效性识别补充“今年”“近24小时”“近48小时”等时间窗口。
- 增加 `tests/fixtures/search_quality/scenarios.json`，用固定样例回归搜索排序质量。
- 新增 `docs/roadmap.md`，记录后续版本路线、验收标准和暂不做事项。

### Changed

- README 的 trace 说明补充 `query_quality`，文档区新增路线图入口。
- 版本同步到 `0.1.8`。

### Verified

- 搜索质量 fixtures 覆盖政策类和电商类排序。
- 针对性测试覆盖质量画像、trace、时效性窗口和搜索排序。

## v0.1.7 - 2026-05-01

### Added

- `guanlan hotnews` 默认入口改为 `today`，聚合百度热搜、微博热搜、B站热门视频、IT之家 RSS 和 V2EX 热门。
- 新增原生公开热榜源：`weibo`、`bilibili`、`ithome`。
- `today` 多源聚合会 round-robin 合并各源结果，并容忍单个公开端点失败。
- MCP `guanlan_hotnews` 默认源同步为 `today`。

### Changed

- README、Agent 使用说明、skill 和 AGENTS.md 更新为 `today` 优先的热榜路径。
- 微博和 B站单源标记为 `best-effort`，避免对公开端点稳定性过度承诺。

### Verified

- 新增测试覆盖微博、B站、IT之家、`today` 聚合和 NewsNow fallback。
- `guanlan hotnews today --limit 5 --json` 在当前环境可返回多源结果。
- 版本同步到 `0.1.7`。

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
