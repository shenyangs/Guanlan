# Guanlan Agent Playbook

## v0.9 evidence provenance boundary

- Treat `evidence_bundle_v1` as an additive provenance view, not as a new ranking or truth engine.
- Cite snapshot/passages only when they came from `can_cite_as_page_body=true`; unread URLs remain clues.
- `relation=mentions` means only that an exact token occurs in the passage. Never rewrite it as
  `supports` or `refutes` without a separate, explicit verification step.
- Archive current-document search remains compatible; use `archive history` / `archive snapshot`
  only when change history or exact passage offsets matter.
- MCP stays `full` by default. Choose `--profile compact` only when the host benefits from a smaller
  tool list and can operate with the six core research tools.

这份文档写给会调用观澜的 Agent。目标不是介绍命令大全，而是降低误用率，让 Agent 在中文互联网研究任务里更稳定地用对 Guanlan。

## 持久记忆面

如果你会在多个会话里反复调用 Guanlan，把下面四处当作“长期记忆”入口：

- `AGENTS.md`
- `docs/agent-playbook.md`
- `docs/agent-usage.md`
- `guanlan/skill/SKILL.md`

在开始做新自动化、评测、benchmark、MCP 编排前，至少重新读一次本文件和 `AGENTS.md`。

需要给宿主 Agent 硬编码调用轮次、并发、结果数、超时和停止条件时，使用 [Agent 执行预算与数值规范](agent-execution-budget.md)。

## 发版纪律

版本提交不是完整发版。只把 `main` 推上远端，不能算完成；必须继续完成同版本 tag、PyPI、Homebrew tap、官网部署和本地安装验证。推荐直接使用 `scripts/publish_release.sh`，不要把“稍后再打 tag / 稍后再同步官网”留成口头约定。

## 先记住定位

Guanlan 不是“单次泛搜引擎”，而是给 Agent 用的中文互联网证据路由器。

它最擅长：

- 中文政策、政务、官方原文、办事指南
- 需要区分官方、报道、样本、热度、社区反馈的研究任务
- 需要结构化信源卡、质量画像、证据角色的任务

它不该被单独拿来承担：

- 纯实时股价、天气、汇率
- 只靠一次 `search` 就想下结论的复杂问题
- 需要 1 小时内突发进展的任务
- 无意义 query、超长 query、多实体超密集 query 的最终判断

## 默认工作流策略

不要把 “每次都至少 3 个工具” 写死成硬 KPI。更稳的规则是按场景分档：

### 自动挡入口

当 Agent 只是卡在“该用哪个 Guanlan 命令”时，先跑：

```bash
guanlan agent "用户需求" --json
```

它不会联网，只会把本地 route/workflow 结果压成一张 `agent_plan_v2` 决策卡：`primary_command`、少量 `agent_next_steps`、`task_model`、`capability_selection`、`execution_contract`、`self_check_contract` 和 `user_facing_boundary`。默认先执行 `primary_command`；只有质量信号不足、用户要求更深结论，或任务是热点/技术/WPS/AI Office 等需要补线索的场景，才继续执行后续命令。`--mode quick` 适合快速线索，`--mode fresh` 会把 hotnews/feeds 放进短链路，`--mode deep` 直接进入可复用证据包工作流。

执行后不要让 Agent 自己猜下一步。把 Guanlan 的 JSON 输出、trace 摘要或错误摘要交回 review 模式：

```bash
guanlan agent "用户需求" --phase review --observation-json result.json --json
```

review 会返回 `next_decision=answer|continue|repair|ask_user|authorize_browser|stop` 和最短 `next_commands`。常见动作是：空结果或小样本时补 `--limit 80`，read 不可用时先 `diagnose page`，official-only 时补外部报道/社区样本，research timeout 时降级为 `search + read`，不要继续加大 `read_top`。

### 结果池纪律

`--limit 30` 以下只适合 smoke test。严肃搜索、研究、对比、时间线和档案任务，应尽量保持默认 80 条候选池；如果用户或评测脚本给了很小的 limit，Agent 可以先执行，但必须把它当“小样本线索”。`search --trace` 会在 `agent_limit_advice.silent_repair_commands` 里给出扩大到 `--limit 80` 的补跑命令；除非用户明确只要 smoke，先无感执行该命令，再压缩输出给用户。

### Evidence Mixer 影子诊断

`search` 会输出 Evidence Mixer 诊断，用来估算“哪些候选更适合作为优先阅读证据”。默认是 `shadow`：不删除、不重排、不让空结果扩大，只在 trace/context 里给 `selected_evidence`、增益估计、fallback 和空结果风险。需要让 Agent 明确按优先阅读顺序补证时，用 `--evidence-mode assist`；排障或对照基线时，用 `--evidence-mode off`。看到 `fallback=coverage_floor` 时，不要收窄结果集，应继续用完整候选池补读。

### AnySearch 激活

AnySearch 是外部搜索后端，适合英文、技术、学术、金融、安全、API/MCP/GitHub/CVE/论文等跨域 Agent 搜索补强。默认策略是 `anysearch-auto=fallback` 且允许匿名免费额度：只有路由命中强适配场景、默认后端证据不足或需要补强时，才自动把 AnySearch 加到后端链路。强适配英文/技术链路会先跑快速公开基线，再跑 AnySearch；如果候选池已经足够，会跳过较慢的 DuckDuckGo HTML 兜底。用户显式运行 `--backend anysearch` 时也可以直接使用。

如果用户不希望默认使用外部 AnySearch 匿名额度，可运行 `guanlan configure anysearch-auto off` 完全关闭自动路由，或运行 `guanlan configure anysearch-anonymous-auto off` 仅关闭无 key 匿名自动调用。

如果 AnySearch 匿名额度耗尽并返回自动注册 key，Agent 只能在用户确认后保存到 `anysearch_api_key`；不要读取浏览器 Cookie、Token、密码、控制台页面或浏览器存储来“无感获取” key。推荐路径是用户自带 key：`guanlan configure anysearch-key <key>`。

### 搜索入口目录

Guanlan 内部维护了一个只读搜索入口目录，用来解释 Baidu、Bing、DuckDuckGo、搜狗微信、头条搜索、集思录、Google、Brave、WolframAlpha 等入口的适用场景、风控边界和高级检索语法。这个目录会出现在 `query_strategy.search_entrypoint_policy` 和 `sources explain/export` 中。

它不是“逐个裸抓 17 个搜索引擎”的执行计划。Agent 不应把目录入口当默认后端，也不应把临时 session cookie retry 包装成稳定恢复能力。真正执行仍走 Guanlan 的 `search` 后端顺序、scope/site 约束、AnySearch 策略、quality gate 和 `external_fetch_strategy`。

### 约束纪律

`--site` 是硬过滤，不是排序偏好。`--site gov.cn` 结果为空时，不要把知乎、SEO 页或泛网页包装成站内结果；应该改为读站点入口、使用站内搜索，或按 Guanlan 输出的 `external_fetch_strategy` 补证。

显式年份和年份范围是强时间窗。`2024`、`2024-2025`、`2026年` 这类约束下，窗口外材料只放在背景，不要进入主时间线或被写成“最新进展”。

### 已知站点入口发现

当用户给出明确网站/域名，并要求“在这个站里找文档、价格、公告、API、联系方式、下载页”时，先用：

```bash
guanlan map "https://example.com" --query "pricing docs" --limit 80 --read-top 2
```

`map` 只从公开 `robots.txt`、sitemap XML 和页面链接里发现候选 URL；它不是全网搜索，也不是规模化爬取。加 `--read-top 2` 时会顺手读取少量代表页并返回 `read_pack.readings` / `readings` 质量报告；回答只能引用 `read_evidence_v1.usable=true` 的正文，未读 URL 仍只是入口线索。没有可用 `readings` 时，必须继续 `guanlan read "URL" --quality-report` 后再引用事实。

### 2-step

适用于：结果已经可用，只需要核正文。

顺序：

1. `search`
2. `read`

例子：

```bash
guanlan search "横琴封关政策 2025 最新" --profile china --scope gov --limit 80
guanlan read "https://..." --quality-report
```

### 3-step

适用于：普通研究问题，或质量画像未过。默认不要把 `research` 放在第一轮；先用 route 选源、scope 搜索扩池，再读代表 URL。

顺序：

1. `route`
2. `search --scope ...`
3. `read`

例子：

```bash
guanlan route "华为手机"
guanlan search "华为手机" --scope social_web --limit 80 --trace
guanlan read "https://..." --quality-report
```

`research` 现在按重型/受控工具使用：只有用户明确要可复用证据包、深度综合、或 `search + read` 后仍缺信源角色覆盖时再调用；MCP/Agent 自动挡默认应把 `read_top` 控在 0-2，并优先用单独的 `guanlan read` 补代表 URL。Schema 接受 `read_top=0-5`，其中 3-5 只用于用户明确要求多页深查且宿主提供 180-300 秒外层预算的场景。

### 页面诊断

如果 `read` 读到的是动态页壳、登录墙、安全验证、搜索兜底或明显弱正文，不要反复重试同一个 URL。先跑：

```bash
guanlan diagnose page "URL"
```

页面诊断会说明它是可读正文、动态壳、访问门槛、搜索兜底还是弱正文，并给出下一步命令。诊断不是浏览器接管，也不会读取 Cookie；它只是帮 Agent 判断“这个页面还能不能当证据”。

公众号文章先用普通 `read`。`mp.weixin.qq.com` 文章链接在 `auto` 模式下会优先尝试公众号专项提取；`--trace` 中出现 `selected_backend=wechat_article` 时，表示正文来自公开文章 HTML 的标题、作者、发布时间和正文块。这条路径不读取 Cookie、credentials、IndexedDB 或公众号后台。只有这条路径、Jina 和 direct HTML 都失败或正文弱时，才进入页面诊断或请求用户授权浏览器可见页补证。

如果用户已经自配公众号导出服务，才使用 `guanlan wechat-exporter status --probe`、`account-search`、`articles` 或 `download`。它只读取当前 shell 里的 `GUANLAN_WECHAT_EXPORTER_BASE_URL` / `GUANLAN_WECHAT_EXPORTER_AUTH_KEY`，auth key 不写进提示词、日志、文档、commit 或 release note。公众号历史文章、阅读量、评论等输出要标注为授权账号/会话依赖证据。

如果诊断输出 `browser_assist.recommended=true`，说明公开读取不足但目标页可能仍有样本价值。Agent 必须先问用户是否允许使用宿主浏览器读取目标页可见内容；如页面需要登录、验证或切换账号，应让用户自己在浏览器里完成。允许后，Agent 只能读取目标页可见文本、标题、URL、作者和时间，本次可见页补证不读取 Cookie、Token、钥匙串、浏览器数据库、localStorage、sessionStorage、浏览器 profile 或无关个人资料。若任务目标本身是私信、订单、后台或账号页，需要用户对该目标页、用途、风险和只读范围单独明确授权，并标记 `private_account_evidence=true`；如果仍需 Cookie 或其他凭据材料，必须另行说明平台、用途和风险并获得用户明确同意，且凭据材料不得进入 browser-visible payload。不执行点赞、评论、关注、发帖、私信、下单或提交表单。

推荐外显说法：

> 观澜已经完成信源路线判断，当前公开读取拿到的正文不足。下一步建议使用你当前浏览器里的目标页面做补证；如果页面需要登录或验证，请你自己在浏览器里完成。是否允许我只读取目标页面的可见内容？如果目标页是私信、订单、后台或账号页，我会再确认该目标页和用途。我不会读取 Cookie、Token、密码、钥匙串、浏览器数据库、localStorage、sessionStorage 或浏览器 profile，也不会执行任何写操作。

授权后的浏览器可见页结果优先由宿主 Agent 直接提取为 JSON/JSONL，然后这样入库：

```bash
guanlan browser-assist adapters --check
guanlan browser-assist setup-openguanlan --json
guanlan browser-assist sessions "URL" --min-visible-items 30 --json
guanlan browser-assist run "URL" --adapter openguanlan --json
guanlan archive add-browser-note --from-json browser-notes.jsonl
```

`browser-assist adapters --check` 只做只读可用性探测：检查可执行文件、命令模板、平台匹配和 dry-run 构造，不会打开页面、读取浏览器状态或调用外部平台。`browser-assist run` 默认返回 OpenGuanlan 浏览器补证契约，告诉 Agent 该打开哪些 URL、提取哪些可见字段、哪些动作不能做。这里的 OpenGuanlan 指 Guanlan 的浏览器补证总层，默认复用宿主 Agent 浏览器读取目标页可见内容，不要求安装 Chrome 扩展、daemon、OpenCLI、Playwright 或独立浏览器 profile。`open-cli` 默认仍可只作为 opener；如果检测到 OpenCLI 浏览器桥或用户配置了可输出 browser-visible JSON/JSONL 的命令模板，能力层会升级为 extractor。`host-browser` 是 OpenGuanlan 主路径里的执行面，而不是另一个产品定义。`browser-use` 只负责打开页面，`xhs-cli` 等外部适配器必须由用户预先安装并配置命令模板；不要为了补证临时下载 Playwright、启动独立浏览器或读取浏览器 profile。只有用户另外明确授权 Cookie 平台、用途、风险和只读范围时，才允许走凭据相关流程，且凭据材料不进入可见页入库 payload。

如果用户需要独立浏览器桥，才进入可选侧车：`guanlan browser-assist setup-openguanlan --json` 查看边界，然后用 `guanlan browser-assist run "URL" --adapter openguanlan-bridge --json`。不要把安装 OpenCLI 或 Chrome 扩展当成观澜核心前置条件。`setup-opencli` 只保留给已经明确想用 OpenCLI 的兼容用户。可选桥的 Chrome 扩展必须由用户在浏览器里手动安装/启用。OpenGuanlan 可选桥的商店版权限模型应保持“默认只连本机 daemon，目标网站按当前站点授权”；用 `scripts/build_openguanlan_extension.sh` 生成商店 zip 并检查 manifest 权限，不要把 `<all_urls>` 放回默认 host permissions。配对也只属于可选桥：运行 `openguanlan pair-code --json` 获取一次性配对码，在 popup 中保存；需要轮换时用 `openguanlan pair-reset --json`。

适配器能力要分层理解：`extractor` 才能产出浏览器可见页 JSON/JSONL，`opener` 只负责把 URL 打开。`adapters --check` 会给出 `can_open`、`can_extract_visible_text`、`can_reuse_existing_session`、`can_wait_dynamic_ready`、`can_scroll_until_min_items`、`can_read_private_account_visible_pages`、`credential_material_access_allowed`、`cookie_flow_available`、`capability_score` 和 `risk_score`；如果只有 opener 可用，Agent 仍需要用宿主浏览器能力提取可见正文。小红书、知乎、公众号会带平台专项字段模板，入库时保留 `browser_visible_v2`、`browser_assisted`、`visible_page_only`、`user_authorized` 和 `session_dependent` 边界。

`browser-assist sessions` 是给 Agent 的会话契约，不读取浏览器状态。多步补证应使用同一目标页会话，登录、验证、SPA 跳转、排序/筛选变化后必须重新确认 URL、标题、正文和结果数，不复用旧快照。Rednote 与小红书按同类公开笔记处理，但保留平台标签。

动态页不要用固定 sleep 当作就绪证据。优先等待标题/主正文出现、结果数增长、DOM 连续无增长、或宿主工具能看到的相关网络响应。`aria-label`、`placeholder`、`title`、按钮文字等会随语言环境变化，不要用单一中文/英文 UI 文本做唯一 selector；如果定位失败，输出 `selector_or_locale_mismatch` 或 `skipped_reason`，不要返回空正文假成功。

列表、评论或搜索页需要较大样本时，用 `--min-visible-items` 告诉宿主 Agent 目标数量。Agent 应滚动到达到请求数量、连续两轮无新增、触达平台边界或达到滚动上限；输出里保留 `requested_min_items`、`collected_count` 和 `partial_reason`。不要为了凑数量跳到无关推荐流或私域页面。

如果宿主 Agent 没有浏览器提取能力，才退回 `--url "URL" --text-file notes.md` 的手动兜底。

这类材料要标注为浏览器辅助补证，不要伪装成所有人都能复现的普通公开网页证据。

### Recipe

如果任务是反复出现的垂直研究模式，先用 recipe 固化流程：

```bash
guanlan recipe list
guanlan recipe run finance-risk "宁德时代 股价 财报 公告 最近风险"
guanlan recipe run university-advisor "南京师范大学中北学院 计算机 导师 招生"
guanlan recipe run wps-office-radar "WPS AI PPT Agent 办公选题 最近热点"
```

Recipe 输出的是计划、证据层和边界，不是最终答案。执行时仍要按 `route/search/read/research` 的质量信号补证。

### Watch

当用户说“持续关注、每天扫、定期看、监控某主题”时，不要只给一次 `search`。先把它规划或保存为 Guanlan 自己的 standing intent：

```bash
guanlan watch plan "OpenAI API release notes" --profile english
guanlan watch add "WPS AI PPT Agent 办公选题" --feed-source curated --schedule "daily 09:00"
guanlan watch fire <id> --limit 30
guanlan watch fire <id> --record-seen --limit 30
```

`watch` 是轻量拉取式雷达，不启动后台服务、不发通知、不引入 Qdrant/Docker。`fire` 默认是诊断调用，不写 seen；只有显式 `--record-seen` 才更新本地去重状态。重要事实仍要回读原文：对 NEW 线索先 `guanlan read URL --quality-report`，需要长期沉淀时再 `guanlan archive ingest-research "query" --limit 80 --read-top 3`。

### Daily

当用户要“日报、晨报、每日简报、今日 WPS AI/品牌/舆情动态”时，优先使用 `guanlan daily`，而不是手工拼 `search + feeds + hotnews`。日报是多源采编工作流：它会把候选线索分成一手/官方、外部报道/产业媒体、社区样本、风险/信任和弱线索，并聚合成 `storylines`。主正文不应由 D 层 SEO、下载站、镜像站或标题党转载撑起；如果 `editorial_health.status=block`，只能把输出当线索池，不能当成品日报。

推荐命令：

```bash
guanlan daily "WPS AI" --format markdown --time-window 3d --read-top 3
guanlan daily "某品牌 最近舆情" --edition reputation --format im
guanlan daily "AI Office 市场动态" --format html --output daily.html
guanlan daily "WPS AI" --record-history --compare-days 7
```

使用规则：

- `time_window` 控制能不能使用“今天/最新”口径：旧材料只能进背景或候补线索。
- `storylines` 是日报主线；`items` 和 `overflow_items` 是兼容字段和候补线索池。
- 社区层必须标成样本，不外推总体口碑。
- 官方口径只能代表一手事实，不能写成“全网情况”。
- `--record-history` 才写入 `~/.guanlan/daily/history.jsonl`；默认只读低扰。
- HTML/IM 只是同一份 report 的交付形态，证据边界和来源层级必须保留。

### 4-step

适用于：时效、技术、证据面过窄等高风险场景。

热点/时效：

1. `route`
2. `hotnews`
3. `search --scope ...`
4. `read`

电商/零售/跨境/品牌/产业互联网类任务如果命中亿邦动力垂类语境，可在第 4 步补一个小窗口频道入口，例如 `guanlan hotnews ebrun:cross-border --limit 10`、`guanlan hotnews ebrun:retail --limit 10`、`guanlan hotnews ebrun:brand-globalization --limit 10`。它用于发现最新垂类线索，不能替代 `search/research --scope ecommerce --limit 80`。

技术/AI/WPS/AI Office：

1. `route`
2. `search --scope ...`
3. `feeds`
4. `read`

技术和 WPS/AI Office 题必须补 RSS/精品内容流。优先显式跑 `guanlan feeds curated --category ai --limit 80` 或 `guanlan feeds curated --limit 80`；AI 公司、模型、Agent、开发者平台更新类任务再补 `guanlan feeds ai-official --limit 80` 和 `guanlan feeds ai-media --limit 80`。`research --preset tech|wps_office` 只在深查/证据包模式下使用，不能替代官方文档、代码仓库、原始公告或产品页面；关键事实要回读原始 URL。

学术发现：

1. `route`
2. `research --preset academic`
3. `feeds arxiv --keyword "..."`
4. 读取代表论文/出版商/数据库页面

`feeds arxiv` 返回的是预印本或论文线索。`preprint_record` 不等于同行评议结论；如果 arXiv API 被限流，输出会给 `preprint_search_entrypoint` 和 `api_unavailable`，Agent 应继续用返回的 arXiv 搜索入口或 `research --preset academic` 补证。

长期订阅源观察：

1. 准备显式 RSS/Atom 清单
2. `guanlan feeds watchlist --watchlist PATH --limit 80`
3. 对重要更新再 `read`

watchlist 支持 JSON、JSONL 或每行一个 feed URL。`watchlist_update_signal` 只说明用户维护清单里的公开源有更新，带 `user_watchlist` / `feed_dependent` 边界，不代表全网发现。

证据面过窄：

1. `route`
2. `research`
3. `search --scope ...`
4. `dossier` / `compare` / `timeline`

只有完成当前档位要求后，仍缺关键证据，才允许切到通用 `web_search` / `web_fetch`。
如果 Guanlan 输出 `external_fetch_strategy`，可以调用宿主 Agent 的 WebFetch/WebRead 读取候选 URL，但要向用户说明：这是“Guanlan 规划信源 + WebFetch 定点读取”的组合策略，不是 Guanlan 脆弱或失败。

对外不要顺嘴吐槽工具状态。不要写“Guanlan 崩了 / 抽风了 / 挂了 / 炸了 / 翻车 / 拉胯 / 坏了”这类口语化失败标签。只有当超时、补证或浏览器可见页会改变证据边界、复现方式或置信度时，才简洁说明：“Guanlan 已规划信源路线；目标页公开读取超时或上游响应慢，所以按计划用 WebFetch/浏览器可见页做定点补证。”如果最终答案已经能直接引用来源，就不要额外加一句工具状态。

如果 trace 出现 `quality_gate.reason=partial_salvage`，表示观澜从低覆盖批次里救回了强官方/垂直信源线索；这不是失败，应该先读取代表原文并说明证据角色仍有缺口。如果 `read` 输出 `兜底状态: unusable`，表示搜索兜底无法确认同一页面，不要引用兜底内容，改走 `diagnose page`、结构化入口、scope 搜索或 WebFetch 定点补证。

`guanlan read --format json` 会给 Agent 一个轻量抽取契约：`backend_capability` 说明当前后端是正文读取、缓存、弱正文片段还是搜索上下文；`extract_contract` 说明这次输出能否作为目标页正文证据。只在 `extract_contract.can_cite_as_page_body=true` 时引用页面正文。`status=context_only` 只是搜索兜底线索，必须继续读原文或代表页；`truncation.content_truncated=true` 说明返回内容被 `max_chars` 截断，若结论依赖后文，应提高 `--max-chars` 或换更聚焦 URL。不要把这些契约字段外显成工具报错。

Jina 默认保持兼容模式：仍使用 `text/plain`、上游默认 engine 和默认 content 输出，不默认打开 `agent preset`、frontmatter 或 chunking。只有 Jina 与 direct 都快速返回明确动态页壳时，观澜才在搜索兜底前暗中追加一次有界 browser 修复；登录墙、验证码/WAF、网络错误和动态财经页不会触发该重试。`--no-cache` 是显式强刷新，会同时绕过观澜本地缓存和 Jina 上游缓存。JSON/trace 中的 `jina_read_contract_v1` 只用于复现请求边界，不应机械外显给普通用户。

### Timeout 单位契约

Guanlan 输出给 Agent 的外层预算默认是秒：`status`、`doctor`、`search`、单 URL `read` 用 60-90 秒；`hotnews`、`feeds`、`pulse`、批量读取和默认 `archive ingest-research` 用 120 秒；`research`、`compare`、`timeline`、`dossier` 和带 `--read-top` 的入库用 180-300 秒；安装、升级、发布 smoke 用 300-600 秒。

如果宿主工具字段名是 `timeout_ms`、`timeout_milliseconds`，或平台文档说明按毫秒解释，要显式换算：90 秒 = 90000 ms，120 秒 = 120000 ms，300 秒 = 300000 ms，600 秒 = 600000 ms。不要把 `timeout=120` 这种裸数字交给下游 Agent 或自动化工具，必须先确认单位。

## 垂直权威入口

有些问题不该只赌搜索引擎发现。例如体育比分、财经行情/公告披露/宏观数据、天气灾害、CVE 漏洞、科学机构声明、文娱榜单/票房、考试官方信息、WPS/AI Office 官方入口，用户真正需要的是“先去哪个权威入口核验”。Guanlan 会在这些高确定性场景里自动加入少量 direct source seeds，并在 `route` 里给出 `guanlan read` 命令。

Agent 应该把这些入口当作下一步要读的权威候选，而不是把它们当最终答案。正确做法是先读这些入口，再用 `search/research` 扩大信源面；不要在 Baidu/Bing/DuckDuckGo 低相关或被验证码拦截后直接宣布 Guanlan 失败。

## Benchmark 规则

不要用不符合 Guanlan 最佳使用方式的打法去评价 Guanlan。

### 错误打法

- 只跑一次 `search`，然后把结果当成 Guanlan 最终能力
- 把“质量画像 warn”直接写成“Guanlan 搜索失败”
- 用 `search` 测“今天热搜”“刚刚地震”“最新发布”却不跑 `hotnews`
- 用 `search` 测技术/AI/WPS/AI Office，却不补 `feeds`
- 把实时数据题、专用行情题当作普通网页搜索题
- 把股票/财经题只当泛搜题，不区分结构化行情、公告披露、监管/宏观数据、研报观点和投资者情绪
- 用超长 query 一次性塞进全部约束，不做拆解
- 用多实体 query 期待一次返回完整对比，不做拆分

### 正确打法

- 先判断是否强路由命中，再决定 `preset` / `scope`
- 热点题必须带 `hotnews`
- 电商/零售/跨境题可补 `hotnews ebrun:*` 频道线索，但仍要用 `ecommerce` 大池搜索和代表 URL 阅读核验
- 技术/AI/WPS/AI Office 题必须带 `feeds`
- 学术预印本/论文线索题应补 `feeds arxiv --keyword ...`
- 长期关注指定博客、项目或机构更新的题应补 `feeds watchlist --watchlist ...`
- 财经题必须先选 `finance` preset 或对应 scope；Agent 不确定时先跑 `guanlan stock plan "问题"`；股票行情、ETF/基金净值、榜单、资金流优先用 `guanlan stock ...` / `guanlan-stock ...`，公告/财报/基金公告/监管用 `finance_disclosure`，宏观用 `finance_macro`，情绪样本用 `finance_sentiment`
- 政策/办事题至少 `search + read`，复杂时直接 `research`
- 评价 Guanlan 时区分三件事：
  - 搜索相关性
  - 质量画像是否严格
  - Agent 是否用对了 Guanlan 工作流

### 自动挡回归集

自动挡不能靠“看起来挺聪明”发布。每次修路由或工作流选择，都要把新发现的错例沉淀到 `tests/fixtures/routing_regression_cases.jsonl`，并写成机器可断言的 `expected_*` / `forbidden_*`。

- `positive`：应该命中某垂类，例如 WPS AI、台风、CVE、高校导师。
- `negative`：不该误进某垂类，例如“体育馆出租”不该进 sports。
- `near_miss`：长得像但语义不同，例如“魔法学院 漫画 导师 角色”不该进 university，“DeepSeek-V4 智能体 Agent 最新”不该进 wps_office。

新增样本后运行：

```bash
uv run pytest tests/test_routing_regression_cases.py -q
guanlan eval benchmark
guanlan eval suite run chinese-web-v1
```

评测结论要看 `expected_*` 和 `forbidden_*` 是否都满足；只看一条 happy path 不算覆盖自动挡风险。

### Live Smoke 趋势

`guanlan quality live-smoke` 是可选公网探针，默认不阻断。长期观察公网/源站/后端漂移时，用历史趋势：

```bash
guanlan quality live-smoke --record-history --trend-window 10
```

它会在输出里带 `live_trend_report`，区分 `new_failures`、`recovered`、`persistent_failures` 和 `likely_network_or_upstream`。这只是诊断线索，不等于“没有资料”；`--strict` 仍只按本次 `summary.fail` 决定退出码。

## 汇报规则

以下情况不要对用户说 “Guanlan 搜索失败”：

- 只是 Baidu/Bing/DuckDuckGo 某个后端被拦截
- 只是质量画像未过
- 只是还没跑 `route / research / scope / hotnews / feeds`
- 只是网页反爬导致 `web_fetch` 失败
- 只是目标页公开读取超时、源站响应慢，或已经切到 WebFetch/浏览器可见页做补证

更准确的说法：

- “当前 Guanlan 证据包还没过质量画像，继续补证中。”
- “某搜索后端受限，但 Guanlan 已切到其他后端并给出补证路线。”
- “这个题更适合走 Guanlan 的 hotnews / feeds / research 工作流，而不是单次 search。”
- “目标页公开读取超时，我已按 Guanlan 规划的补证路线读取目标页，并保留来源边界。”

只有在完成当前档位要求的 Guanlan 工具后仍没有关键证据，才说：

- “本轮 Guanlan 未取得足够证据。”

## 暴力测试里最值得吸取的教训

- 短 query 要扩写，不要直接拿 4-8 字去赌相关性。
- 超长 query 要拆成多个问题，不要一次塞 200 字。
- 多实体对比要拆成单实体检索，再用 `compare` / `dossier` 汇总。
- 实时题优先 `hotnews`，不要只看 `search`。
- 实时体育、灾害预警、安全漏洞等垂直题优先读取 Guanlan 推荐的 direct source seeds，再扩大搜索。
- 财经题不要只看一个搜索结果：行情/ETF/基金净值要先走结构化股票数据并看时间戳，公告/财报/基金公告要回到披露源，宏观数据要核发布机构，雪球/股吧只作情绪样本。动态财经页或雪球 WAF 读不出正文时，不要反复 `read`，改用 `guanlan stock detail|fundflow|rank|index` 和披露源补证。
- 页面读不出来时，先 `diagnose page`，再按诊断建议切结构化源、scope 搜索、metadata 读取或 archive 流程；不要把搜索兜底内容当原文正文。
- 公众号链接先看 `read --trace` 是否走到 `wechat_article`；如果已经拿到正文，不要再要求用户授权浏览器或 Cookie。用户自配 exporter 后，再用 `wechat-exporter` 查历史文章或下载结果。
- 高频垂直任务先 `recipe run`，把流程讲清楚，再执行对应命令；不要让 Agent 临场发明一套不稳定搜索路径。
- 技术题优先 `search --scope tech_dev + feeds + read`；WPS/AI Office 选题优先 `search --scope wps_office + feeds` 或 `recipe run wps-office-radar`，深查时再用受控 `research --read-top 0-2 --max-search-jobs 2`，不要只看品牌稿或社区搜索结果。
- `source_type` 只作辅助，不要把它当唯一真相；结合 domain、authority_score、evidence_role 一起判断。
- `compare` 若提示 `source_diversity_guard=warn`，先补公司一手、垂直媒体或社区样本，不要拿单站结果做横向结论。
- `timeline` 若提示 `timeline_quality=warn`，说明主时间窗证据不足；窗口外事件只能当背景。

## 最后一道护栏

当你准备 fallback 到通用 `web_search` / `web_fetch` 时，先问自己四件事：

1. 我已经用够当前档位要求的 Guanlan 工具了吗？
2. 我有没有跑过更适合这个题的 `preset` 或 `scope`？
3. 这个题是不是本来就该走 `hotnews` / `feeds` / `research`？
4. 我会不会把“质量画像严格”误报成“Guanlan 搜索失败”？

四个问题里只要有一个答案是否定的，就先继续用 Guanlan，而不是立刻切走。
