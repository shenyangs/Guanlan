# Guanlan Agent Playbook

这份文档写给会调用观澜的 Agent。目标不是介绍命令大全，而是降低误用率，让 Agent 在中文互联网研究任务里更稳定地用对 Guanlan。

## 持久记忆面

如果你会在多个会话里反复调用 Guanlan，把下面四处当作“长期记忆”入口：

- `AGENTS.md`
- `docs/agent-playbook.md`
- `docs/agent-usage.md`
- `guanlan/skill/SKILL.md`

在开始做新自动化、评测、benchmark、MCP 编排前，至少重新读一次本文件和 `AGENTS.md`。

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

### 结果池纪律

`--limit 30` 以下只适合 smoke test。严肃搜索、研究、对比、时间线和档案任务，应尽量保持默认 80 条候选池；如果用户或评测脚本给了很小的 limit，Agent 可以先执行，但必须把它当“小样本线索”，并建议补跑 `--limit 80` 后再下结论。

### 约束纪律

`--site` 是硬过滤，不是排序偏好。`--site gov.cn` 结果为空时，不要把知乎、SEO 页或泛网页包装成站内结果；应该改为读站点入口、使用站内搜索，或按 Guanlan 输出的 `external_fetch_strategy` 补证。

显式年份和年份范围是强时间窗。`2024`、`2024-2025`、`2026年` 这类约束下，窗口外材料只放在背景，不要进入主时间线或被写成“最新进展”。

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

适用于：普通研究问题，或质量画像未过。

顺序：

1. `route`
2. `research`
3. `search --scope ...`

例子：

```bash
guanlan route "华为手机"
guanlan research "华为手机" --preset general --advisor
guanlan search "华为手机" --scope social_web --limit 80 --trace
```

### 页面诊断

如果 `read` 读到的是动态页壳、登录墙、安全验证、搜索兜底或明显弱正文，不要反复重试同一个 URL。先跑：

```bash
guanlan diagnose page "URL"
```

页面诊断会说明它是可读正文、动态壳、访问门槛、搜索兜底还是弱正文，并给出下一步命令。诊断不是浏览器接管，也不会读取 Cookie；它只是帮 Agent 判断“这个页面还能不能当证据”。

如果诊断输出 `browser_assist.recommended=true`，说明公开读取不足但目标页可能仍有样本价值。Agent 必须先问用户是否允许使用宿主浏览器读取目标页可见内容；如页面需要登录、验证或切换账号，应让用户自己在浏览器里完成。允许后，Agent 只能读取目标页可见文本、标题、URL、作者和时间，本次可见页补证不读取 Cookie、Token、钥匙串、浏览器数据库、私信、订单、后台或无关个人资料；如果仍需 Cookie，必须另行说明平台、用途和风险并获得用户明确同意，不执行点赞、评论、关注、发帖、私信、下单或提交表单。

推荐外显说法：

> 观澜已经完成信源路线判断，当前公开读取拿到的正文不足。下一步建议使用你当前浏览器里的目标页面做补证；如果页面需要登录或验证，请你自己在浏览器里完成。是否允许我只读取目标页面的可见内容？我不会读取 Cookie、密码、钥匙串、浏览器数据库、私信、订单或后台信息，也不会执行任何写操作。

授权后的浏览器可见页结果优先由宿主 Agent 直接提取为 JSON/JSONL，然后这样入库：

```bash
guanlan browser-assist adapters --check
guanlan browser-assist run "URL" --adapter host-browser --json
guanlan archive add-browser-note --from-json browser-notes.jsonl
```

`browser-assist adapters --check` 只做只读可用性探测：检查可执行文件、命令模板、平台匹配和 dry-run 构造，不会打开页面、读取浏览器状态或调用外部平台。`browser-assist run` 默认只返回宿主浏览器执行契约，告诉 Agent 该打开哪些 URL、提取哪些可见字段、哪些动作不能做。`open-cli` / `browser-use` 只负责打开页面，`xhs-cli` 等外部适配器必须由用户预先安装并配置命令模板；不要为了补证临时下载 Playwright、启动独立浏览器或读取浏览器 profile。只有用户另外明确授权 Cookie 平台、用途、风险和只读范围时，才允许走 Cookie 相关流程。

适配器能力要分层理解：`extractor` 才能产出浏览器可见页 JSON/JSONL，`opener` 只负责把 URL 打开。`adapters --check` 会给出 `can_open`、`can_extract_visible_text`、`can_reuse_existing_session`、`cookie_flow_available`、`capability_score` 和 `risk_score`；如果只有 opener 可用，Agent 仍需要用宿主浏览器能力提取可见正文。小红书、知乎、公众号会带平台专项字段模板，入库时保留 `browser_visible_v2`、`browser_assisted`、`visible_page_only`、`user_authorized` 和 `session_dependent` 边界。

如果宿主 Agent 没有浏览器提取能力，才退回 `--url "URL" --text-file notes.md` 的手动兜底。

这类材料要标注为浏览器辅助补证，不要伪装成所有人都能复现的普通公开网页证据。

### Recipe

如果任务是反复出现的垂直研究模式，先用 recipe 固化流程：

```bash
guanlan recipe list
guanlan recipe run finance-risk "宁德时代 股价 财报 公告 最近风险"
guanlan recipe run university-advisor "南京师范大学中北学院 计算机 导师 招生"
```

Recipe 输出的是计划、证据层和边界，不是最终答案。执行时仍要按 `route/search/read/research` 的质量信号补证。

### 4-step

适用于：时效、技术、证据面过窄等高风险场景。

热点/时效：

1. `route`
2. `research`
3. `search --scope ...`
4. `hotnews`

技术/AI：

1. `route`
2. `research`
3. `search --scope ...`
4. `feeds`

证据面过窄：

1. `route`
2. `research`
3. `search --scope ...`
4. `dossier` / `compare` / `timeline`

只有完成当前档位要求后，仍缺关键证据，才允许切到通用 `web_search` / `web_fetch`。
如果 Guanlan 输出 `external_fetch_strategy`，可以调用宿主 Agent 的 WebFetch/WebRead 读取候选 URL，但要向用户说明：这是“Guanlan 规划信源 + WebFetch 定点读取”的组合策略，不是 Guanlan 脆弱或失败。

如果 trace 出现 `quality_gate.reason=partial_salvage`，表示观澜从低覆盖批次里救回了强官方/垂直信源线索；这不是失败，应该先读取代表原文并说明证据角色仍有缺口。如果 `read` 输出 `兜底状态: unusable`，表示搜索兜底无法确认同一页面，不要引用兜底内容，改走 `diagnose page`、结构化入口、scope 搜索或 WebFetch 定点补证。

## 垂直权威入口

有些问题不该只赌搜索引擎发现。例如体育比分、财经行情/公告披露/宏观数据、天气灾害、CVE 漏洞、科学机构声明、文娱榜单/票房、考试官方信息，用户真正需要的是“先去哪个权威入口核验”。Guanlan 会在这些高确定性场景里自动加入少量 direct source seeds，并在 `route` 里给出 `guanlan read` 命令。

Agent 应该把这些入口当作下一步要读的权威候选，而不是把它们当最终答案。正确做法是先读这些入口，再用 `search/research` 扩大信源面；不要在 Baidu/Bing/DuckDuckGo 低相关或被验证码拦截后直接宣布 Guanlan 失败。

## Benchmark 规则

不要用不符合 Guanlan 最佳使用方式的打法去评价 Guanlan。

### 错误打法

- 只跑一次 `search`，然后把结果当成 Guanlan 最终能力
- 把“质量画像 warn”直接写成“Guanlan 搜索失败”
- 用 `search` 测“今天热搜”“刚刚地震”“最新发布”却不跑 `hotnews`
- 用 `search` 测技术/AI，却不补 `feeds`
- 把实时数据题、专用行情题当作普通网页搜索题
- 把股票/财经题只当泛搜题，不区分结构化行情、公告披露、监管/宏观数据、研报观点和投资者情绪
- 用超长 query 一次性塞进全部约束，不做拆解
- 用多实体 query 期待一次返回完整对比，不做拆分

### 正确打法

- 先判断是否强路由命中，再决定 `preset` / `scope`
- 热点题必须带 `hotnews`
- 技术/AI 题必须带 `feeds`
- 财经题必须先选 `finance` preset 或对应 scope；行情、榜单、资金流优先用 `guanlan stock ...` / `guanlan-stock ...`，公告/财报/监管用 `finance_disclosure`，宏观用 `finance_macro`，情绪样本用 `finance_sentiment`
- 政策/办事题至少 `search + read`，复杂时直接 `research`
- 评价 Guanlan 时区分三件事：
  - 搜索相关性
  - 质量画像是否严格
  - Agent 是否用对了 Guanlan 工作流

## 汇报规则

以下情况不要对用户说 “Guanlan 搜索失败”：

- 只是 Baidu/Bing/DuckDuckGo 某个后端被拦截
- 只是质量画像未过
- 只是还没跑 `route / research / scope / hotnews / feeds`
- 只是网页反爬导致 `web_fetch` 失败

更准确的说法：

- “当前 Guanlan 证据包还没过质量画像，继续补证中。”
- “某搜索后端受限，但 Guanlan 已切到其他后端并给出补证路线。”
- “这个题更适合走 Guanlan 的 hotnews / feeds / research 工作流，而不是单次 search。”

只有在完成当前档位要求的 Guanlan 工具后仍没有关键证据，才说：

- “本轮 Guanlan 未取得足够证据。”

## 暴力测试里最值得吸取的教训

- 短 query 要扩写，不要直接拿 4-8 字去赌相关性。
- 超长 query 要拆成多个问题，不要一次塞 200 字。
- 多实体对比要拆成单实体检索，再用 `compare` / `dossier` 汇总。
- 实时题优先 `hotnews`，不要只看 `search`。
- 实时体育、灾害预警、安全漏洞等垂直题优先读取 Guanlan 推荐的 direct source seeds，再扩大搜索。
- 财经题不要只看一个搜索结果：行情要先走结构化股票数据并看时间戳，公告/财报要回到披露源，宏观数据要核发布机构，雪球/股吧只作情绪样本。动态财经页或雪球 WAF 读不出正文时，不要反复 `read`，改用 `guanlan stock detail|fundflow|rank|index` 和披露源补证。
- 页面读不出来时，先 `diagnose page`，再按诊断建议切结构化源、scope 搜索、metadata 读取或 archive 流程；不要把搜索兜底内容当原文正文。
- 高频垂直任务先 `recipe run`，把流程讲清楚，再执行对应命令；不要让 Agent 临场发明一套不稳定搜索路径。
- 技术题优先 `research --preset tech` 或 `search + feeds`，不要只看社区搜索结果。
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
