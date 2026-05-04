---
name: guanlan
description: >
  观澜是面向 AI Agent 的中文互联网信源与平台路由器。
  默认只读、低扰、明源，覆盖搜索、热榜、社交、视频、开发者社区与网页阅读。

  【路由方式】SKILL.md 包含路由表和常用命令，复杂场景需按需阅读对应分类的 references/*.md。
  分类：search / hotnews / social (小红书/抖音/微博/推特/B站/V2EX/Reddit) / career(LinkedIn) / dev(github) / web(网页/文章/公众号/RSS) / video(YouTube/B站/播客).

  Use when user asks to search, read, or interact on any supported platform,
  shares a URL, or asks to search the web.
triggers:
  - search: 搜/查/找/search/搜索/查一下/帮我搜
  - hotnews: 热榜/热点/今日热点/快讯/趋势/舆情
  - social:
    - 小红书: xiaohongshu/xhs/小红书/红书
    - 抖音: douyin/抖音
    - Twitter: twitter/推特/x.com/推文
    - 微博: weibo/微博
    - B站: bilibili/b站/哔哩哔哩
    - V2EX: v2ex
    - Reddit: reddit
  - career: 招聘/职位/求职/linkedin/领英/找工作
  - dev: github/代码/仓库/gh/issue/pr/分支/commit
  - web: 网页/链接/文章/公众号/微信文章/rss/读一下/打开这个
  - video: youtube/视频/播客/字幕/小宇宙/转录/yt
  - finance: 雪球/股票/stock/xueqiu/行情/基金
  - entertainment: 文娱/娱乐/影视/电影/电视剧/综艺/明星/票房/豆瓣/猫眼/游戏/欧美娱乐/日韩娱乐/K-pop/J-pop
  - archive/wiki/rag: 本地知识库/archive/RAG/向量库/Agent Wiki/知识底座
  - diagnose/recipe: 页面读不到/动态页/登录墙/WAF/研究模板/固定流程/recipe
  - report: 报表/html report/可视化报告/汇报页/出个报告
metadata:
  openclaw:
    homepage: local-repo
---

# 观澜 / Guanlan — 路由器

面向 AI Agent 的中文互联网信源与平台路由器。根据用户意图选择对应分类。

## Agent 运行规则

- 把 `AGENTS.md`、`docs/agent-playbook.md`、`docs/agent-usage.md` 和本文件当作 Guanlan 的长期记忆入口；做新 benchmark、自动化或 MCP 编排前，至少重读前两份。
- 搜索、研究、热榜、回响和本地知识库检索时，默认使用 80 条候选池；复杂调研可提高到 80-100。
- 只有用户明确要“少量样本”“快速试一下”“只看前几条”时，才主动降低 limit。
- 如果命令或用户要求 `--limit` 小于 30，把它当作 smoke sample，不要直接下强结论；尽量说服 Agent/用户补跑 `--limit 80`。
- `--site` 是硬过滤：`--site gov.cn` 不允许返回知乎、SEO 页或其他域名当作结果；为空时按 `external_fetch_strategy` 或站内入口补证。
- 显式年份/年份范围是强时间窗，窗口外材料只作背景，不应进入主时间线或写成最新证据。
- 强路由命中时直接走对应 `--preset` 或 `--scope`，不要先泛搜一轮；只有意图混合、拿不准信源角色、或需要解释路由时，才先跑 `guanlan route "query" --json`。
- 强路由包括：欧美娱乐 `global_entertainment`、日韩娱乐 `jp_kr_entertainment`、CVE/反诈 `cybersecurity`、天气灾害 `weather_disaster`、体育 `sports`、财经/股票/宏观金融 `finance`、科学新闻 `science`、职场薪资面经 `career`、播客 `podcast`、考试备考 `test_prep`、高校招生导师 `university`、学术投稿检索 `academic`、产品/公司口碑 `reputation`。
- 信源解释：当需要说明“为什么该看这些来源/某来源能不能当主证据”时，先用 `guanlan sources explain "query"` 或 `guanlan sources show gov.cn`；需要治理口径漂移时用 `guanlan sources audit`。这些都是只读信源元数据，不是实际搜索结果。
- 轻重分流：不确定任务该轻搜还是深查时，先跑 `guanlan workflow "query" --json`；simple/direct 任务不要过度规划，复杂/高风险/对比/时间线/档案任务才用 `guanlan investigate "query" --limit 80 --format context`。
- 页面诊断：当 `read` 读到动态页壳、登录墙、WAF、安全验证、搜索兜底或弱正文时，先跑 `guanlan diagnose page "URL"`；诊断只解释页面是否能当证据，不读取 Cookie，不执行浏览器动作。
- 研究模板：高频垂直任务先用 `guanlan recipe list` / `guanlan recipe run <recipe> "query"` 固化流程，例如 `finance-risk`、`university-advisor`、`product-reputation`、`entertainment-pulse`、`security-advisory`、`tech-radar`。
- 不要把 Guanlan 降格成“一次泛搜”。默认工作流是动态分档：结果已可用时走 `search -> read`；普通研究至少走 `route -> research -> scoped search`；热点题再补 `hotnews`；技术/AI 题再补 `feeds`；来源过窄时再补 `dossier/compare/timeline`。
- 体育比分/赛程、财经行情/公告披露/宏观数据、天气灾害、CVE、安全公告、科学机构声明、文娱榜单/票房、考试官方信息等高确定性垂直题，优先执行 `route` 推荐的 direct `guanlan read` 命令，再用匹配的 `preset/scope` 扩大证据面；不要只看搜索引擎是否返回。
- 在完成当前档位要求的 Guanlan 工具前，不要立刻切 `web_search/web_fetch`。`quality_summary=warn` 通常表示证据包还不完整，不等于 Guanlan 搜索失败。
- `quality_gate.reason=partial_salvage` 表示观澜保留了强官方/垂直信源线索但仍有覆盖缺口；先读代表原文，不要写成失败。`read` 出现 `兜底状态: unusable` 时，不要引用搜索兜底，改用页面诊断、结构化入口、scope 搜索或 WebFetch 定点补证。
- 如果 Guanlan 输出 `external_fetch_strategy`，可以调用宿主 Agent 的 WebFetch/WebRead 读取候选 URL；外显时说明这是“Guanlan 规划信源 + WebFetch 定点补证”的搜索策略，不是 Guanlan 脆弱。
- 做 benchmark 时不要误用：实时题必须带 `hotnews`，技术/AI 题必须带 `feeds` 或 `research --preset tech`，政策题不要只测单次泛搜。
- 如果 Agent/MCP/自动化平台能设置工具 timeout：`search/read/status/doctor` 用 60-90 秒；`hotnews/feeds/pulse/read batch` 和默认 `archive ingest-research` 用 120 秒；`research/compare/timeline/dossier/archive ingest-research --read-top N` 用 180-300 秒；安装/升级/发布 smoke 用 300-600 秒。
- 超时只代表网络或上游源未完成，不代表没有证据；优先重试一次、加 `--cache-ttl 3600`，或把 `--read-top` 降到 0/1，不要为了速度把 80 条候选池砍成小样本。
- 科技/AI/开发者/工程实践类问题必须额外补一轮 RSS/精品内容流；`research --preset tech` 会自动补，若只跑 `route` 或 `search`，再跑 `guanlan feeds curated --limit 80` 或 `guanlan feeds curated --category ai --limit 80`。
- 文娱/影视/综艺/明星/游戏/票房/评分/口碑类问题优先用 `route` 或 `research --preset entertainment`；把平台热度、用户评分、产业报道、宣发通稿和粉圈讨论分层看。
- 欧美娱乐、Hollywood、Taylor Swift、Billboard、Grammy、巡演、新歌专辑等问题优先用 `research --preset global_entertainment --profile english`；英文行业媒体、榜单/奖项和艺人/厂牌一手信息优先于粉丝账号和八卦站。
- 日韩娱乐、K-pop/J-pop、韩剧日剧、Soompi、Oricon、Naver 等问题优先用 `research --preset jp_kr_entertainment --profile hybrid`；区分本地媒体/榜单、经纪公司口径、英文翻译站和粉丝讨论。
- 财经、股票、行情、公告、财报、监管、宏观金融、ETF/基金、雪球/股吧情绪和研报问题优先用 `guanlan stock ...` / `guanlan-stock ...` 获取结构化行情、榜单、资金流向和大盘概览，再用 `research --preset finance` 或 `search --scope finance_quote|finance_disclosure|finance_macro|finance_sentiment|finance_research` 扩展证据；把行情、公告披露、监管/宏观、新闻、研报观点和投资者情绪分层看，不输出买卖建议。
- CVE/漏洞/补丁/反诈/诈骗短信用 `research --preset cybersecurity` 或 `search --scope cybersecurity --trace`；优先 CVE/NVD/CISA/厂商公告/监管来源。
- 台风/天气/地震/灾害预警用 `search --scope weather_disaster --trace`；优先官方气象和应急来源，并检查时间戳。
- 体育、科学新闻、招聘薪资面经、播客、考试备考分别用 `sports`、`science`、`career`、`podcast`、`test_prep` preset/scope，不要停在泛搜索。
- 如果新用户问“装好了怎么用/怎么让 Agent 用观澜”，先运行 `guanlan welcome`。
- 如果用户或 Agent 不知道观澜有哪些功能、该用哪个命令，先运行 `guanlan capabilities`；MCP 模式下调用 `guanlan_capabilities`。
- `--advisor` 输出的是证据边界和写作规则，Agent 需要据此生成自然建议，不要机械复述固定小标题。
- `research` 证据包会附带证据审计提示；遇到版本号、价格、参数量、发布日期冲突时，先说明不同来源分别怎么说，再给取舍依据。
- `report html` 是旁支展示层，只把已有 JSON/stdin/demo 数据渲染成静态 HTML；不要用它替代 search/read/research/hotnews 主链路。
- `archive wiki/context/pack` 是本地 archive 的旁支组织层：只使用已归档资料，不代表全网知识，不自动上传。
- 更新观澜时必须全量更新，不要只跑增量 upgrade：优先 `uv tool install --force --upgrade guanlan`，注意 uv 只有 `--force` 可能重装旧锁定版本；Homebrew 用 `brew update && brew reinstall shenyangs/tap/guanlan`；pipx 用 `pipx install --force guanlan`。更新后运行 `hash -r`、`command -v guanlan`、`which -a guanlan`、`guanlan version`，再跑 `guanlan capabilities`、`guanlan doctor --install-check`、`guanlan doctor --trace`、`guanlan search "人工智能 政策" --profile china --limit 5 --trace`、`guanlan hotnews today --limit 5 --trends`。版本或路径不一致时停止配置 MCP。

## 路由表

| 用户意图 | 分类 | 详细文档 |
|---------|------|---------|
| 网页搜索/代码搜索 | search | [references/search.md](references/search.md) |
| 中文热榜/今日热点/快讯 | hotnews | [references/search.md](references/search.md) |
| 小红书/抖音/微博/推特/B站/V2EX/Reddit | social | [references/social.md](references/social.md) |
| 招聘/职位/LinkedIn | career | [references/career.md](references/career.md) |
| GitHub/代码 | dev | [references/dev.md](references/dev.md) |
| 网页/文章/公众号/RSS | web | [references/web.md](references/web.md) |
| YouTube/B站/播客字幕 | video | [references/video.md](references/video.md) |
| 文娱/影视/综艺/游戏/明星/票房口碑 | entertainment | `guanlan research "关键词" --preset entertainment` |
| 欧美娱乐/音乐产业/明星动态 | global_entertainment | `guanlan research "关键词" --preset global_entertainment --profile english` |
| 日韩娱乐/K-pop/J-pop/韩剧日剧 | jp_kr_entertainment | `guanlan research "关键词" --preset jp_kr_entertainment --profile hybrid` |
| 财经/股票/行情/财报公告/宏观金融 | finance | `guanlan research "关键词" --preset finance --advisor` |
| 行情/指数/股价/ETF | finance_quote | `guanlan search "关键词" --scope finance_quote --trace` |
| 公告/财报/监管/问询函 | finance_disclosure | `guanlan search "关键词" --scope finance_disclosure --trace` |
| 宏观/央行/统计局/利率 | finance_macro | `guanlan search "关键词" --scope finance_macro --trace` |
| CVE/漏洞/反诈/补丁 | cybersecurity | `guanlan research "关键词" --preset cybersecurity` |
| 天气/台风/地震/灾害预警 | weather_disaster | `guanlan search "关键词" --scope weather_disaster --trace` |
| 体育赛事/伤病/转会 | sports | `guanlan research "关键词" --preset sports` |
| 科学发现/NASA/论文核验 | science | `guanlan research "关键词" --preset science --profile english` |
| 招聘/薪资/面经 | career | `guanlan research "关键词" --preset career` |
| 播客/小宇宙/音频 RSS | podcast | `guanlan search "关键词" --scope podcast` |
| 雅思/托福/题库/机经 | test_prep | `guanlan research "关键词" --preset test_prep` |

## 零配置快速命令

```bash
# Exa 网页搜索
mcporter call 'exa.web_search_exa(query: "query", numResults: 50)'

# 观澜统一网页搜索（默认公开搜索，不需要 Cookie）
guanlan welcome
guanlan capabilities
guanlan search "query" --limit 80
guanlan search "EI会议 投稿 检索" --profile china --scope academic
guanlan search "清华大学计算机系研究生招生 导师" --profile china --scope university
guanlan search "电影 票房 评分" --profile china --scope entertainment
guanlan search "贵州茅台 公告 财报" --profile china --scope finance_disclosure --limit 80 --trace
guanlan search "上证指数 今日 行情" --profile china --scope finance_quote --limit 80 --trace
guanlan search "社融 CPI 降息 央行" --profile china --scope finance_macro --limit 80 --trace
guanlan stock quote "贵州茅台"
guanlan stock detail "600519"
guanlan stock fundflow "宁德时代"
guanlan-stock rank --sort turnover --limit 20
guanlan-stock index
guanlan search "Taylor Swift latest" --profile english --scope global_entertainment
guanlan search "BLACKPINK K-pop comeback" --profile hybrid --scope jp_kr_entertainment
guanlan search "OpenSSL CVE 最新 漏洞 影响版本" --scope cybersecurity --limit 80 --trace
guanlan search "台风 路径 中央气象台 日本气象厅" --scope weather_disaster --limit 80 --trace
guanlan search "梅西 比赛 伤病 最新" --scope sports --limit 80
guanlan research "NBA季后赛2026年首轮战绩比分" --preset sports --read-top 5
guanlan search "AI 创业 播客 小宇宙" --scope podcast --limit 80
guanlan search "最近 query 热点" --profile china --trace
guanlan search "中文问题" --profile china --limit 80 --trace  # 查看 Baidu/Bing/DDG 状态与 backend_recovery
guanlan diagnose page "https://example.com/article"
guanlan recipe list
guanlan recipe run finance-risk "宁德时代 股价 财报 公告 最近风险"
guanlan search "query" --site zhihu.com --limit 80
guanlan search "query" --site gov.cn --limit 80 --trace  # 硬过滤，空结果不放宽到域外
guanlan search "query" --trace
guanlan search "query" --cache-ttl 3600
guanlan search "query" --format context
guanlan search "query" --format prompt
guanlan search "query" --source-chart
guanlan route "query"
guanlan workflow "query" --json
guanlan investigate "query" --limit 80 --format context
guanlan investigate "query" --budget deep --dry-run
guanlan sources explain "query"
guanlan eval suite run chinese-web-v1
guanlan sources audit
guanlan quality performance
guanlan research "query" --profile china --advisor
guanlan research "query" --profile china --format prompt
guanlan research "EI会议 投稿 检索 要求" --preset academic --read-top 0
guanlan research "清华大学计算机系研究生招生 导师" --preset university --read-top 0
guanlan research "电影/综艺/游戏/明星 票房口碑" --preset entertainment --read-top 0
guanlan research "宁德时代 股价 财报 公告 最近风险" --preset finance --read-top 5 --advisor
guanlan research "Taylor Swift 最新动态 新专辑 巡演" --preset global_entertainment --profile english
guanlan research "BLACKPINK K-pop 最新回归" --preset jp_kr_entertainment --profile hybrid
guanlan research "OpenSSL CVE 最新 漏洞 影响版本" --preset cybersecurity --read-top 5
guanlan research "字节 AI 产品经理 校招 薪资 面经" --preset career --read-top 5
guanlan research "雅思 口语 题库 机经" --preset test_prep --read-top 4
guanlan prompt "query" --profile china --style evidence
guanlan context "query" --profile china --style evidence
guanlan research "product 用户评价" --preset reputation --read-top 0 --advisor
guanlan compare "A" "B" --focus "价格 口碑 风险" --limit 80 --format context
guanlan timeline "某事件 最新进展" --limit 80 --format context
guanlan timeline "某事件 2024-2025" --limit 80 --format context
guanlan dossier "某对象" --focus "业务 口碑 风险" --limit 80 --format context
guanlan pulse "query" --format context

# 通用网页阅读
guanlan read "URL" --max-chars 12000
guanlan read "URL" --strict --trace
guanlan read "URL" --backend direct --extract metadata
guanlan read batch urls.txt --format context
guanlan read batch urls.txt --concurrency 4 --format context
guanlan read "URL" --watch
guanlan feeds curated --limit 80
guanlan feeds curated --category ai --min-score 85 --limit 80
guanlan feeds baidu-rss --limit 80
guanlan feeds wechat-rss --limit 80
guanlan feeds curated-sources --keyword AI --limit 80
guanlan feeds list

# 本地知识库
guanlan archive add "URL"
guanlan archive ingest-research "query" --limit 80
guanlan archive ingest-research "query" --limit 80 --read-top 3
guanlan archive ingest-research "query" --limit 80 --dry-run
guanlan archive search "query" --format context --trace
guanlan archive embed --backend local
guanlan archive search "query" --semantic --format context --trace
guanlan archive inspect 1
guanlan archive reindex
guanlan archive verify
guanlan archive context "query" --limit 20
guanlan archive wiki build --output ./guanlan-wiki
guanlan archive wiki context "query"
guanlan archive pack "query" --format langchain-jsonl --output guanlan-pack.jsonl
guanlan archive export --format rag-jsonl
guanlan mcp config --client codex
guanlan serve --host 127.0.0.1 --port 8765
guanlan plugin template my_company_api
guanlan quality robustness
guanlan eval benchmark
guanlan eval scenarios --format jsonl
guanlan report html --input results.json --output report.html

# GitHub 搜索
gh search repos "query" --sort stars --limit 50

# 中文热榜（原生公开源，不需要 Cookie）
guanlan hotnews today --limit 80
guanlan hotnews today --limit 80 --trends
guanlan hotnews weibo --limit 80
guanlan hotnews bilibili --limit 80
guanlan hotnews ithome --limit 80
guanlan hotnews tophub:weibo --limit 80
guanlan hotnews tophub:catalog:news --limit 80
guanlan hotnews hotboard:catalog:finance --limit 30
guanlan hotnews hotboard:snapshots:weibo --limit 20
guanlan hotnews uapis:catalog --limit 80
guanlan hotnews vvhan:all --limit 80
guanlan hotnews zhihu --json  # experimental，失败时改用 site:zhihu.com 搜索
guanlan hotnews list

# 助理视角：用户要建议、影响、下一步、或“可能为什么搜这个”时使用
guanlan research "query" --profile china --advisor

# Twitter 搜索
twitter search "query" --limit 50

# YouTube/B站字幕
yt-dlp --write-sub --skip-download -o "/tmp/%(id)s" "URL"

# Reddit 搜索
rdt search "query" --limit 50

# Reddit 读帖 + 评论
rdt read POST_ID

# V2EX 热门
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: guanlan/1.0"
```

Archive 入库时如果看到 `skipped` 或 `ingest_audit`，优先把它理解为质量保护：观澜在写入本地知识库前检查了相关性、平台首页、重复候选、正文厚度和漂移风险。

## 环境检查

```bash
# 检查可用 channel
guanlan doctor

# 查看诊断路径，确认是否跳过认证/Cookie/登录态探测
guanlan doctor --trace

# 扫描本地配置中的明文 Cookie、Token、Key 或代理凭据
guanlan doctor --check-config

# 查看 channel 稳定性、授权边界、批量边界和缓存概览
guanlan status

# 查看所有 MCP 服务
mcporter_list_servers()
```

## 工作区规则

**不要在 agent workspace 创建文件。** 使用 `/tmp/` 存放临时输出，`~/.guanlan/` 存放持久数据。

## 详细文档

根据用户需求，阅读对应的详细文档：

- [搜索工具](references/search.md) — Exa AI 搜索
- [社交媒体](references/social.md) — 小红书, 抖音, Twitter, B站, V2EX, Reddit
- [职场招聘](references/career.md) — LinkedIn
- [开发工具](references/dev.md) — GitHub CLI
- [网页阅读](references/web.md) — Jina Reader, 微信公众号, RSS
- [视频播客](references/video.md) — YouTube, B站, 小宇宙

## 配置渠道

如果某个 channel 需要配置，获取安装指南：
docs/install.md

用户只需提供 cookies，其他配置由 agent 完成。
