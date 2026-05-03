# 观澜更新日志

本文记录观澜每个版本的能力变化、边界调整和下一步收口方向。

格式遵循“未发布 / 已发布”两段：`Unreleased` 只记录已经决定进入下一轮的计划，不代表已经完成；带版本号的条目只记录已经随 tag 发布的内容。

## Unreleased

- 暂无。下一轮变更先进入这里，发版时再移入对应版本。

## v0.4.0 - 2026-05-03

### Added

- 大幅扩展路由体系：新增 `university`、`cybersecurity`、`weather_disaster`、`science`、`sports`、`career`、`podcast`、`test_prep`、`global_entertainment`、`jp_kr_entertainment` 等专门 scope / preset，让 Agent 不再把高校招生、漏洞补丁、台风预警、体育转会、科学新闻、薪资面经、播客和考试备考都塞进泛搜索。
- 高校招生/导师场景新增专门路由：`academic` 继续负责 EI/SCI/Scopus、论文投稿和会议检索；`university` 优先研究生招生网、院系官网、导师主页、招生目录和官方通知，并对学校实体不匹配结果做降噪。
- 文娱路由升级为分区研究：中文文娱继续走豆瓣、猫眼、B站、微博等平台；欧美娱乐走 Variety、Deadline、Hollywood Reporter、Billboard、Rolling Stone 等英文行业/榜单源；日韩娱乐走 Soompi、Oricon、Natalie、Naver 娱乐、本地媒体与经纪公司口径。
- 新增网络安全/反诈路线：`cybersecurity` 优先 CVE/NVD/CISA、CNVD/CNNVD、厂商安全公告和补丁说明，避免把论坛复现、恐吓式安全营销或无编号转载当主证据。
- 新增天气灾害、科学、体育、职场、播客、考试备考等路由画像，并同步接入 `route`、`search --scope`、`research --preset`、source taxonomy、能力清单、Skill、Agent 文档和评测场景。
- 新增 agent 侧搜索质量反馈通道（`/v1/feedback`）：当 Agent 环境里的搜索/研究出现明显低质量信号时，可上报“搜索词、问题原因、命令上下文”到专门诊断队列，用于后续路由和排序治理。
- 遥测采集端新增 `/v1/feedback` 接口、SQLite `feedback` 表和反馈面板，支持查看高频问题词、问题原因、反馈命令分布与最近反馈明细。

### Changed

- 搜索后端稳健性增强：当某个后端返回明显低相关候选时，会标记 `low_relevance` 并继续尝试后续后端，不再因为“看似有结果”的垃圾批次提前停止。
- scope 搜索更稳：短站点表达会限制 `site:` 数量，避免查询过长导致无结果；scope 查询为空时会回到开放查询补搜，并继续保留 scope-aware 排序。
- 高校搜索新增自动补救：`site:edu.cn` 未产出可用结果时会开放补搜；如果结果里识别到学校主域，会自动追加一轮站内搜索，并在 context/trace 里解释原因。
- `--format context` 增加质量诊断：把质量状态、谨慎原因、观澜补证动作、Agent 执行策略和汇报约束直接放进上下文，提醒下游 Agent 不要把“低质量候选”包装成可靠结论。
- `search --trace` 增加 `scope_rewrite`、`low_relevance`、补搜路径、质量解释、follow-up action 和汇报约束，便于排查为什么某些结果被降权或补搜。
- 高风险场景的路由更保守：网络安全、天气灾害、医疗、法律、财经、全球政策等场景会收窄主证据范围，把社交、论坛、粉丝或经验样本降为辅助材料。
- `docs/telemetry.md` 增补搜索不满意反馈的采集边界；遥测默认策略不变，但反馈路径会明确包含搜索词和问题原因，供质量治理使用。
- README、AGENTS、Agent 使用文档、Skill、capabilities 和评测基准同步补充新路由、新命令和边界说明。
- 官网展示版本号同步到 `0.4.0`。

### Notes

- 这是一次从“中文互联网研究工具”走向“多领域信源路由底座”的重要版本：核心目标不是堆平台，而是让 Agent 在更多真实问题里知道“该去哪里搜、什么能当主证据、什么只能作样本”。
- 本版继续保持默认候选池不缩水；性能优化以跳过低价值后端、补救空 scope 和减少无效等待为主，不牺牲 Agent 拿到的证据量。

## v0.3.11 - 2026-05-03

### Added

- `hotnews` 新增外部热榜聚合旁支：`tophub:*`、`uapis:*`、`vvhan:*`，可按需补充 TopHub、UAPI、HotList/VVHan 的更大热榜目录和单平台热榜。
- 外部热榜源新增本地缓存与 `stale_cache` 兜底；条目统一标记 `external_backend`、`third_party_aggregation`、`provider_volatility`，避免把第三方聚合误当权威事实。
- 新增 `docs/hotnews-provider-integration.md`，说明外部热榜源的接入原则、风险边界和 Agent 使用建议。

### Changed

- `guanlan hotnews list`、README、AGENTS、Skill、capabilities 和 MCP schema 同步补充 TopHub/UAPI/VVHan 用法。
- `guanlan setup` 不再交互式索要 GitHub/Groq 可选 token，改为明确提示基础搜索不依赖这些凭据，降低误触授权和钥匙串焦虑。
- HTTP 只读服务的 `/search`、`/hotnews`、`/archive/search`、`/compare` 默认 limit 与统一候选池常量对齐，继续保持 Agent 默认 80 条结果池。
- 搜索后端使用更短的单后端超时，并在候选池已满时跳过后续后端，减少外层 Agent/MCP 调用超时，同时不缩小默认结果池。
- 官网展示版本号同步到 `0.3.11`。

## v0.3.10 - 2026-05-03

### Added

- 新增文娱/内容消费路由：覆盖影视、综艺、音乐、游戏、明星、票房、播放热度、豆瓣评分、猫眼/灯塔、B站/微博公开讨论等场景。
- `research` 证据包新增 `freshness_guard` 和 `source_mix_guard`，帮助 Agent 显式识别旧内容风险、无日期候选、UGC 占比和权威/一手材料不足。
- 文娱能力纳入 `route`、`search --scope entertainment`、`research --preset entertainment`、source taxonomy、capabilities、MCP 说明和评测场景。

### Changed

- 默认候选池继续向 Agent 研究场景倾斜：`search`、`research`、`hotnews`、`archive`、`pulse` 默认提升到 80 条，避免下游 Agent 因样本池过小而错判。
- `research` 在未显式指定 `--read-top` 时默认读取更多代表证据，政策、官方、技术、产业等场景优先补足正文核验。
- README、Agent 文档、Skill、质量文档和能力清单同步更新 80 条候选池、文娱路线和更宽松的外层超时建议。
- 官网展示版本号同步到 `0.3.10`。

## v0.3.9 - 2026-05-02

### Added

- 科技/AI/开发者/工程实践类路由新增强约束：必须额外补一轮 RSS/精品内容流，避免只依赖搜索引擎排名或社区单点样本。
- `research` 在科技类路线中自动把 `feeds curated` 作为 forced feed group 纳入候选池；RSS 失败会进入 `search_errors/result_groups`，不拖垮整份研究证据包。
- Agent 文档、Skill、README 和 `guanlan capabilities` 新增外层 timeout 预算建议：搜索/单 URL 阅读 60-90 秒，热榜/feeds/pulse 120 秒，research/compare/timeline/dossier 180-300 秒，安装/发布 smoke 300-600 秒。

### Changed

- `route` 对科技类问题会明确推荐 `guanlan feeds curated --limit 80` 或 `--category ai`，并输出 RSS 边界提醒。
- `research` 的 guidance 会提示 RSS 是阅读发现和新鲜线索，不替代官方文档、代码仓库、issue、benchmark 原文或可复现验证。
- 官网展示版本号同步到 `0.3.9`。

## v0.3.8 - 2026-05-02

### Added

- 新增 `guanlan archive verify`：体检本地 archive 的索引一致性、空正文、样本召回和 RAG/Wiki 就绪度，帮助 Agent 在把本地库当作记忆前先确认边界。
- 新增 `guanlan archive context`、`guanlan archive wiki context` 和 `guanlan archive pack`：从本地 archive 生成 prompt-ready 上下文，或打包成 Markdown / JSONL 供本地模型、RAG 和 Agent 工作流复用。
- 新增 `guanlan archive wiki build`：把已归档资料组织成静态 Markdown/HTML Agent Wiki，并区分 core / candidate 材料。
- Archive 导出新增 `llamaindex-jsonl`、`langchain-jsonl`、`openwebui-jsonl` 三种常见加载器 profile。
- MCP 新增 `guanlan_archive_context` 和 `guanlan_archive_verify`，并在 `guanlan_archive_search --trace` 输出本地检索诊断。
- 新增 `guanlan/archive_wiki.py` 和对应测试，覆盖 Wiki 构建、上下文生成、RAG pack 与 CLI 工作流。

### Changed

- `archive search --trace` 增加本地库文档数、查询词、索引类型、FTS/LIKE 边界、`semantic=not-vector` 和空结果建议。
- README、Agent 使用文档、本地模型指南、Skill、welcome 和 capabilities 同步补充 Archive Wiki / RAG / 本地模型上下文用法，并继续强调本地 archive 不是全网知识库。
- 官网展示版本号同步到 `0.3.8`。

## v0.3.7 - 2026-05-02

### Added

- 新增 `guanlan compare`：对多个对象分别建立研究证据包，并按官方/媒体/用户样本/近期动态/风险等维度输出对比表、代表证据、共同边界和下一步命令。
- 新增 `guanlan timeline`：从宽候选池抽取可见日期线索，生成事件时间线，并把无日期但可能重要的证据单列出来，避免把“无日期材料”静默丢掉。
- 新增 `guanlan dossier`：为公司、产品、政策、事件或主题生成研究档案，包含信源概览、分面证据、近期时间线、待核验问题、advisor 规则和下一步命令。
- MCP 新增 `guanlan_compare`、`guanlan_timeline`、`guanlan_dossier` 三个只读工具；本地 HTTP 服务新增 `/compare`、`/timeline`、`/dossier` 只读接口。
- 新增 `guanlan report html` 旁支静态 HTML 报表渲染器，只读取已有 JSON/stdin/demo 数据，不触发搜索、阅读、归档或网络请求。
- 新增 `docs/benchmark-report-v0.3.7.md`，记录高阶工作流、搜索质量 v2、阅读质量摘要和本地模型工作流的测试口径。
- 新增官网发布辅助脚本：`scripts/sync_website_version.py` 同步官网版本号，`scripts/deploy_website_ecs.sh` 用于部署 `website/` 静态站点。

### Changed

- `query_strategy` 增加 `time_window` 和 `search_quality_v2`，近期/热点类查询会更明确提醒 Agent 按时间窗口解释结果，窗口外材料仅作背景。
- `read_quality_summary` 增加 `status_counts`、`low_quality_count`、`low_quality_urls` 和 `recommendation`，让下游 Agent 更清楚哪些正文可引用、哪些只能作线索。
- README、Agent 文档、Skill、本地模型指南、契约文档和官网同步新增 compare/timeline/dossier 用法，并把安装命令继续收束到“强制拿最新 + 安装后校验版本”。
- README、Agent 文档、Skill 和能力地图同步补充 `report html` 的旁支定位，明确它不是主搜索/阅读/研究链路的替代品。
- 官网展示版本号同步到 `0.3.7`，并补充对比研究、时间线和研究档案的命令入口。

## v0.3.6 - 2026-05-02

### Changed

- README 顶部强化市场传播主轴：观澜不是普通搜索 CLI，而是“让 AI Agent 看懂中文互联网”的研究底座。
- README 新增“一眼看懂”极致点表格，集中说明中文互联网研究底座、信源身份、信息孤岛路由、Agent-ready 输出、安全边界和本地模型联网。
- 官网首屏同步新版定位、核心卖点 chips、真实 Agent 命令和“为什么是观澜”能力区块，让访客第一屏理解差异化价值。
- 官网 Open Graph / Twitter 元信息切换到 `https://Guanlan.xin`。
- 匿名遥测默认端点切换到 `https://guanlan.xin/guanlan-telemetry/v1/events`，遥测默认开启策略和采集字段不变。
- 官网展示版本号同步到 `0.3.6`。

## v0.3.5 - 2026-05-02

### Added

- 新增 `docs/benchmark.md`，把离线契约评测、40 个真实任务池和 live/manual benchmark 方法拆开说明。
- 新增运行时契约测试，直接覆盖 search result、research packet 和 archive/RAG 输出字段，防止文档契约与实际 JSON 漂移。
- `archive stats --quality` 新增本地库阅读质量、入库审计和 RAG-ready 概览；`archive export --min-quality` 支持显式过滤低阅读质量材料。
- `guanlan serve --print-token` 可只生成只读 HTTP token；`--token auto` 可启动前自动生成 token。
- 新增 `guanlan quality live-smoke`，作为可选外网探针观察网络/源站波动；默认不阻断发版，`--strict` 才按失败退出。

### Changed

- `eval tasks` 的 Markdown 输出改为共享格式器，便于 README、CLI 和后续报告保持一致。
- source registry 增加 HTTP `/sources` 与 feeds 模块一致性测试，继续以中央信源矩阵作为事实来源，但不做高风险重构。
- README 和中文文档入口补充 benchmark、live smoke、Archive 质量视图和只读 HTTP token 工作流。
- 官网展示版本号同步到 `0.3.5`。

## v0.3.4 - 2026-05-02

### Added

- 新增 `docs/contract.md`，明确 Agent/MCP/HTTP/RAG 集成方可依赖的稳定字段和边界承诺。
- `guanlan serve` 新增 `--token`，也支持 `GUANLAN_SERVE_TOKEN`；非本机监听时可用 Bearer token 或 `X-Guanlan-Token` 保护只读接口。
- 新增 40 个真实中文研究任务种子，并通过 `guanlan eval tasks` 暴露，作为后续 live/manual benchmark 的任务池骨架。

### Changed

- `source_registry` 增加一致性护栏测试，先验证信源矩阵字段、状态值和 hotnews/channel_catalog 现实边界，不做大重构。
- README、Agent 文档、本地模型指南和中文文档入口补充 Agent 输出契约与 HTTP token 边界。
- 遥测默认开启策略保持不变；本次只纳入遥测面板中英双语展示改动，不扩大采集范围。

## v0.3.3 - 2026-05-02

### Added

- 新增 `guanlan quality robustness`，在 coverage/regression 之上增加更深的稳健性闸门，覆盖 Archive 入库审计、Agent 字段契约、空结果解释和发布脚本完整性。
- 新增 `scripts/release_gate.sh`，一键运行 `ruff`、全量 `pytest`、coverage/regression/robustness、`eval benchmark`、构建、安装 smoke 和版本核对。
- Archive 入库候选新增 `ingest_audit`，对相关性、平台首页、重复候选、正文厚度和英文漂移做可解释审计。

### Changed

- `archive ingest-search` / `archive ingest-research` 在写入前会先审计候选，跳过明显低相关、平台首页、重复和过薄内容；dry-run 与 JSON/Markdown 输出同步返回审计摘要。
- `quality robustness` 固化 v0.3.0 测试暴露的 KV Cache / vLLM / SGLang / KIVI 场景，防止本地知识库召回和入库质量再次退化。
- README、Agent 文档和发布文档同步稳健性用法，把发布前验收从人工记忆收束为可复跑闸门。
- 官网展示版本号同步到 `0.3.3`。

## v0.3.2 - 2026-05-02

### Added

- `archive search` 新增 `--trace`，输出 query terms、matched terms、命中字段、排序分数和 `semantic=not-vector` 边界，方便 Agent 判断本地知识库召回质量。
- 新增 `archive inspect <id|url>`，查看单条归档正文、元数据、字符数和内容诊断，确认材料是否真实入库。
- 新增 `archive remove <id|url>` 和 `archive reindex`，支持删除单条归档与重建 SQLite FTS 索引。
- `archive ingest-search` / `archive ingest-research` 新增 `--dry-run`，可预览将入库的代表证据而不写入数据库。
- MCP `guanlan_archive_search` 新增 `trace` 参数，Agent 可直接拿到本地库命中依据。

### Changed

- Archive 入库增加低相关/平台首页跳过逻辑，减少 Toyota Camry、平台首页等明显漂移内容自动沉淀进本地库。
- `archive stats` 增加索引状态、正文字符数、schema version、FTS 文档数和检索边界说明。
- `quality regression` 增加 Archive 技术词召回护栏，持续检查 KV Cache / vLLM / SGLang / KIVI 这类中文技术查询不会回退到 0 召回。
- README、Agent 文档、Skill、本地模型指南和中文 README 同步 Archive 质量工作流：`list -> search --trace -> inspect -> reindex -> ingest-research --dry-run`。
- 官网展示版本号同步到 `0.3.2`。

## v0.3.1 - 2026-05-02

### Fixed

- 修复 `archive search` 对中文长短语和技术词过度严格的问题：本地检索现在会保留精确短语，同时把长中文查询切成可召回片段，并按标题、域名、URL、正文命中权重排序。
- 增加 KV Cache / vLLM / SGLang / KIVI 回归测试，防止“已归档但搜不到”的技术词场景再次退化。
- `archive search` 无结果时给出 `archive list` 和 `archive ingest-research` 的下一步提示。

### Changed

- README、Agent 文档、Skill 和能力说明明确 `archive ingest-search` / `archive ingest-research` 是“联网研究并入库”，`archive search` 才是本地库检索。
- README 明确 Archive 当前是 SQLite FTS/LIKE 宽召回检索，不包装成向量语义搜索。
- 官网展示版本号同步到 `0.3.1`。

## v0.3.0 - 2026-05-02

### Added

- 新增 `guanlan eval benchmark`，提供离线确定性评测基准，覆盖政策、口碑、热点、技术、学术、地方、电商和本地模型联网场景，检查路由意图、scope、证据角色和候选池下限。
- 新增 `guanlan doctor --install-check`，只读检查当前 `guanlan` 命令路径、公开最新版本、多安装入口和升级建议，降低 Agent 调到旧版 CLI 的风险。
- `research` 新增 `--route-chart`，输出 ASCII 路由诊断图，展示意图、证据角色、优先 scope 和路由置信度。
- `archive export` 新增 `--format rag-jsonl`，只导出 RAG 常用字段，便于本地向量库、个人知识库和无联网模型接入。
- `archive ingest-search` 增加语义别名 `archive ingest-research`，让 Agent 更容易把一次 research 的代表证据沉淀成本地知识。

### Changed

- 评估场景扩展到学术检索、地方官方、电商产业和本地模型联网，观澜的“专业调研员框架”从表达进一步落到可测命令。
- README、Agent 文档、Skill 和质量测试计划同步安装自检、路由诊断图、RAG JSONL、评测基准和发布前质量闸门。
- 官网展示版本号同步到 `0.3.0`。

## v0.2.9 - 2026-05-02

### Changed

- 安装与更新文档进一步明确 `uv tool install --force --upgrade guanlan`，避免只用 `--force` 时重装旧锁定版本。
- README、Agent 指南、Skill 文档和更新提醒同步 `--force --upgrade` 口径。
- README 增加观澜面向 AI Agent 的中文互联网研究底座流程图。
- 更新 release smoke / update-check 测试，防止后续文档回退到容易误导的旧安装命令。

## v0.2.8 - 2026-05-02

### Changed

- 更新安装与升级口径：默认建议 Agent 使用全量重装而不是增量升级，优先 `uv tool install --force guanlan`，Homebrew / pipx 也使用 reinstall / force install。
- 更新后要求刷新 shell 命令缓存、核对 `command -v guanlan` 与 `which -a guanlan`，避免旧全局可执行文件遮蔽新版。
- `format_update_notice`、README、`docs/update.md` 和 `AGENTS.md` 增加最小 post-update smoke：`capabilities`、`doctor --trace`、`search --trace` 和 `hotnews today --trends`。
- 更新检查测试覆盖 pipx 强制安装、路径核对和热榜 smoke 提示。

## v0.2.7 - 2026-05-02

### Added

- 新增 `guanlan quality regression`，把默认结果池、防缩水字段、来源多样性、RSS 缓存兜底、正文抽取信号和 advisor 动态性纳入发版回归闸门。
- `guanlan prompt` 增加 `context` 命令别名，可用 `guanlan context "问题"` 直接生成适合 Ollama、LM Studio、Open WebUI 和本地 Agent 的联网 Prompt。
- 只读 HTTP 服务新增 `/context` 和 `/prompt`，本地模型或本地工作流可以通过 HTTP 直接获取观澜整理后的 Prompt。
- 新增 `academic` 学术/论文检索 scope，覆盖 EI/Scopus/Web of Science/CNKI/万方/维普等论文索引、出版商规范和高校认定场景。

### Changed

- `feeds` 外部 RSS/OPML 成功拉取后会写入本地缓存；后续遇到超时或源站抖动时，优先返回最近一次成功结果并显式标记 `feed_status=stale_cache` 和 `risk_tags=stale_cache`。
- `read --backend direct` 增加段落密度兜底，面对不规则中文新闻、政务或转载页时，更倾向保留连续正文、过滤导航和页脚。
- `research --advisor` 的助理视角增加 `natural_guidance`，给下游 Agent 更自然的表达提示，同时继续保持“证据边界/非最终结论”的口径。
- README、Agent 文档、Skill 文档和质量计划同步 `context`、RSS 缓存兜底与 `quality regression` 用法。
- 官网展示版本号同步到 `0.2.7`。

## v0.2.6 - 2026-05-02

### Added

- 新增 `guanlan feeds` 内容发现入口，覆盖精品内容流、精品 RSS 源目录、百度实时热点 RSS 和微信热门文章 RSS。
- MCP 新增 `guanlan_feeds`，HTTP 只读服务新增 `/feeds`，方便本地 Agent、MCP 客户端和无搜索能力模型接入 RSS 内容池。
- `route` 输出 `recommended_feeds` 和 `recommended_commands`，让 Agent 在不知道该跑哪个命令时能直接拿到下一步起手式。
- `hotnews` 新增 `snapshot` / `--watch`，可显式保存本地快照并比较新上榜、消失项和排名变化。
- 热榜条目增加 `evidence_role`、`source_card`、`risk_tags`，趋势简报增加来源分布、证据角色和样本边界。
- 新增中央信源矩阵 `source_registry`，统一 hotnews、feeds、router、MCP 和 HTTP 的信源身份、风险、适用场景和可选后端边界。
- Coverage Guard 增加 `feeds >= 80` 默认结果池下限检查。

### Changed

- `today` 多源热榜改用 B 站热搜词作为默认 B 站信号，保留 B 站热门视频为独立源。
- 微信渠道诊断加入 `wechat-rss` 低摩擦热文线索能力，同时继续明确公众号全文读取仍是 best-effort。
- README、Agent 文档和 Skill 文档同步 feeds、recommended_commands、RSS 路由和 `/feeds` 用法。
- 官网展示版本号同步到 `0.2.6`。

## v0.2.5 - 2026-05-02

### Added

- 新增 `guanlan quality coverage`，作为发版前 Coverage Guard，检查 `search/research/hotnews/archive/read fallback` 默认候选池下限，防止下游 Agent 因更新拿到的材料大面积变少。
- `guanlan quality run --coverage` 可把 Coverage Guard 合并进常规质量闸门。
- `read` 新增 `--quality-report`，输出正文质量、噪声命中、正文占比、可用性和补读建议；JSON 输出同步包含 `quality_report`。
- 搜索结果新增 `evidence_role`，把信源身份压缩为 Agent 可直接使用的证据角色，例如官方原文、权威报道、用户样本、产业材料、开发者讨论等。
- `search --trace` 的质量摘要会给出“缺什么信源，建议补什么”的补搜建议。
- `research` 的原文摘读记录增加 `read_quality`、`quality_report` 和整体 `read_quality_summary`。
- `archive` 归档元数据默认保留 `source_card`、`read_quality`、`quality_report`、`route_plan` 和 `query_strategy`，便于后续接 RAG 时保留来源角色和阅读质量。
- 发布 workflow 增加 Homebrew tap 真实安装验证，降低 tap 已更新但用户装到旧版本的风险。
- `doctor`、`welcome`、`check-update` 增加轻量更新提醒，安装后优先校验当前版本。

### Changed

- 直连正文抽取加强中文站点识别，优先 `js_content`、`rich_media_content`、正文/稿件/详情/文章等容器，并提取作者、来源和发布时间线索。
- README 补充 Coverage Guard、阅读质量报告、证据角色、归档元数据和安装后版本校验说明。
- AGENTS 使用说明补充发版质量护栏和 Agent 默认使用大结果池的规则。
- 官网展示版本号同步到 `0.2.5`。

## v0.2.4 - 2026-05-02

### Added

- 新增查询策略层：`search --trace` 和 `research` 会展示/使用按证据角色拆出的 query variants，例如官方原文、权威报道、用户样本、行业材料和近期进展。
- `research` 增加信源诊断，统计权威度、样本价值、新鲜度、证据角色、风险标签和来源多样性提醒。
- `read` 增加 `--strict`，在正文偏脏或质量不足时更倾向 fallback，而不是把噪声直接交给 Agent。
- `read` 增加 `--extract article|text|metadata|links`，支持直连抽取正文、纯文本、网页元信息和页面链接。
- `hotnews --trends/--brief` 增加跨平台共振、单平台孤岛提醒、时间线和可继续执行的 research 命令。
- `guanlan prompt` 增加 `--style concise|deep|evidence|decision`，方便 Ollama、LM Studio、Open WebUI 等本地模型按任务类型接入联网证据。
- 匿名遥测增加默认 collector、失败本地队列、heartbeat 事件和 collector 并发面板增强；仍只发送命令生命周期元数据，不发送 query、URL、正文或凭据。

### Changed

- `research` 会按 scope/site/open web 自动选择更贴近证据角色的 query variant，再合并去重，减少一个宽泛 query 带来的信息面偏斜。
- MCP/context 输出补充证据审计提示，帮助 Agent 标出版本/叫法冲突、来源时间线和待核验结构化事实。
- README 补充严格阅读、元信息抽取、查询策略、热榜水势和本地模型 Prompt 风格说明。
- 官网展示版本号同步到 `0.2.4`。

## v0.2.3 - 2026-05-02

### Added

- 新增 `guanlan welcome`，安装后可展示面向新用户和 Agent 的简短上手卡片。
- 新增 `guanlan capabilities` 和 `guanlan capabilities --json`，提供可读、可编排的能力地图。
- MCP 新增 `guanlan_capabilities` 工具，让 Agent 在不知道该调用什么能力时可以先做能力发现。
- 新增能力发现和首次欢迎的 CLI/MCP 测试，并补充手动集成 smoke 脚本。

### Changed

- README、Agent 文档、Skill 文档和 `llms.txt` 增加 `welcome/capabilities` 入口，强化 Agent-first 的上手路径。
- 将维护者资料从 README 主入口收束到中文文档入口，降低外部阅读噪音。
- 将示例 MCP 配置迁移到 `docs/examples/mcporter.json`，避免被误认为默认运行配置。
- 官网展示版本号同步到 `0.2.3`。

## v0.2.2 - 2026-05-02

### Added

- 新增 `guanlan quality run`，把搜索排序、中文错配、阅读质量、趋势归并和 advisor 自然度纳入一键质量闸门；默认 `quick` 稳定可复跑，`--mode live` 可做网络探测。
- `read` 增加 `--trace`，输出 Jina/direct/search fallback 尝试、选中后端和正文质量评分。
- `hotnews` 增加 `--brief`，生成“今日水势简报”、来源分布、边界提醒和后续 research 查询建议。
- `research` 和 `prompt` 增加 `--advisor-style brief|decision|risk|strategy`，让 Agent 按不同任务组织建议骨架。

### Changed

- 搜索排序增加中文语境错配降权，减少中文口碑/产品查询混入无关英文结果。
- README 新增“本地大模型联网”专节，说明 Ollama、LM Studio、Open WebUI、MCP 和只读 HTTP 的接入方式。
- 官网展示版本号同步到 `0.2.2`。

## v0.2.1 - 2026-05-02

### Added

- 新增质量测试计划 `docs/quality-test-plan.md`，把搜索质量、热点时效、正文抽取、趋势归并和 advisor 自然度纳入可复跑质量闸门。
- 新增匿名遥测能力：CLI 与 MCP 可在显式配置 endpoint 后上报命令/tool 生命周期元数据，不包含 query、URL、正文、Cookie、Token 或本地路径。
- 新增轻量遥测采集脚本 `scripts/telemetry_collector.py`，用于自托管聚合使用深度、错误率、并发和留存面板。
- 更新三组观澜 logo 资产，改为更统一的朱砂方印视觉。

### Changed

- `research --advisor` 增加动态 briefing 和“自然作答骨架”，让 Agent 能把证据边界转化成更自然的回答，而不是机械复述规则清单。
- `read "URL" --format json/context` 现在对单 URL 生效，便于 Agent 和脚本稳定解析网页正文。
- 网页阅读增强国内老站编码处理：支持按 HTTP/meta charset 解析，并对 GBK/GB2312/GB18030 页面做兜底。
- Jina Reader 若返回明显乱码，会被视为弱读取并触发直连降级。
- 热榜趋势归并收紧相似度规则，降低通用中文 bigram 导致的错聚类风险。
- `guanlan status` 增加匿名遥测状态展示，并避免缓存目录未创建时提前返回。

## v0.1.14 - 2026-05-02

### Changed

- 移除对外独立的理念说明文档，不再把底层设计判断做成显性入口。
- README 保留更低调的观澜表达，把信源身份、证据边界、中文平台语境和“先辨水势”的判断融入主文档。
- 中文文档入口移除对应链接，避免用户看到一份过度解释的内部设计稿。

## v0.1.13 - 2026-05-02

### Added

- 新增 `guanlan route "query"` 与 MCP `guanlan_route`，输出需求路由、意图、证据角色、优先 scope、推荐站点、兜底范围和边界提醒。
- 新增 `guanlan/router.py` 和 `guanlan/source_taxonomy.py`，把需求识别和信源价值拆成可解释的本地启发式结构。
- 新增 `guanlan serve`，提供默认绑定 `127.0.0.1` 的只读 HTTP 服务，覆盖 `/route`、`/search`、`/research`、`/read`、`/hotnews`、`/archive/search`。
- 新增热榜跨源趋势归并：`guanlan hotnews today --trends` 可输出多源趋势簇。
- 新增 `guanlan archive ingest-search "query"`，把一次 research 的精选代表证据沉淀进本地知识库。
- `archive export` 增加 RAG 字段和 `--domain`、`--source-type`、`--topic` 过滤。
- 新增只读插件生态入口：`guanlan plugin list/register/template`，方便企业内部搜索 connector 接入 `search --backend plugin:name`。
- 新增 `guanlan eval scenarios`，提供比较普通 web_search 与观澜证据包的中文语境评估集。

### Changed

- `search --trace` 展示 route plan，并把路由与结构化 source card 纳入评分解释。
- `research` 会把 route 优先源与 open web 兜底一起纳入候选池，避免信源规则过窄。
- README、Agent 文档、Skill 文档同步 route、serve、plugin、archive/RAG、趋势归并和评估集用法。
- README 和中文入口同步 route、serve、plugin、archive/RAG、趋势归并和评估集用法。

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
- README、Agent 文档和本地模型指南同步本地模型联网用法。

## v0.1.11 - 2026-05-02

### Added

- README 增加观澜的产品定位表达：信源身份、中文平台孤岛、证据包、安全授权和动态观察。
- 新增本地大模型联网计划，覆盖 CLI 前置器、MCP 工具层、只读 HTTP 服务和 archive/RAG 路线，帮助 Ollama、LM Studio、Open WebUI 等无联网模型接入中文互联网证据。

### Changed

- Agent 指令层明确提醒：搜索、研究、热榜、回响和归档检索应优先使用 50+ 候选池，复杂研究可提高到 80-100，再由 Agent 筛选代表证据。
- `research --advisor` 从固定建议块调整为“助理视角规则”，输出证据边界、写作规则、可展开方向和响应边界，让调用 Agent 自行生成自然建议。
- MCP tool 描述同步提示扩大 limit，并明确 advisor 返回的是 evidence-bound writing rules，不是最终建议或用户真实意图。
- README 增加产品定位入口，并把观澜定位为面向 AI Agent 的中文互联网研究工具，而不仅是通用搜索封装。

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
