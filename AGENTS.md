# AGENTS.md

This repository is designed as a CLI-first search productivity tool for AI agents.

Memory rule: treat `AGENTS.md`, `docs/agent-playbook.md`, `docs/agent-usage.md`, and
`guanlan/skill/SKILL.md` as the durable memory surfaces for how to operate Guanlan. Before building
new benchmarks, automations, or MCP workflows, reread at least `AGENTS.md` and
`docs/agent-playbook.md`.

Commit/release language rule: Guanlan is a Chinese-web research tool. Use Chinese-first
commit subjects, changelog entries, and release notes. Keep conventional prefixes such as
`feat:` / `fix:` / `docs:` when useful, but write the description in Chinese, for example
`feat: 扩展垂直路由和搜索质量反馈`. In public-facing update text, commit subjects,
release notes, and changelog summaries, do not proactively mention telemetry/遥测 unless the user
explicitly asks for that topic or the change is specifically about its user-facing controls.

Version bump rule: every commit to Guanlan must increase the project version by `0.0.1`.
Before committing, bump the patch version across `pyproject.toml`, `guanlan/__init__.py`,
`uv.lock`, `README.md`, `docs/full-guide.md`, `docs/telemetry.md`, `website/index.html`, and
`CHANGELOG.md`; then run `scripts/pre_release_status.sh` or an equivalent version-sync check. Do
not make a code/docs commit on `main` that leaves the package version unchanged.

Release sync rule: when shipping a new Guanlan version, keep the public distribution surfaces in
lockstep. Do not call a release complete until the GitHub repo/tag, PyPI/uv install path, Homebrew
tap formula (`shenyangs/homebrew-tap`), and official website (`website/index.html` plus any deployed
site flow) all reflect the same version and positioning. If Homebrew reports an older stable version,
run `brew update` first; if the tap itself is stale, update and push `Formula/guanlan.rb` before
telling users Homebrew is current. If the website carries version, install, capability, or release
copy, update and deploy it in the same release pass.
Use `scripts/publish_release.sh` for real releases so pushing `main` and pushing the matching `v*`
tag happen together; PyPI publishing is tag-triggered, so a version commit without a tag is not a
complete release. Pushing `main` alone is never the end of a release. After the version commit lands,
you must continue through `scripts/publish_release.sh` or an equivalent full release path until tag,
PyPI, Homebrew tap, website deploy, and local installer verification all succeed for that same version.

Install/update rule: after installing or upgrading Guanlan, always do a full reinstall, not an
incremental upgrade, before configuring MCP, optional channels, or auth. Prefer one clean path:
`uv tool install --force --upgrade --refresh --default-index https://pypi.org/simple guanlan`; if the user explicitly wants Homebrew, run
`brew update && brew reinstall shenyangs/tap/guanlan`; for pipx, run `pipx install --force guanlan`.
For uv, `--force` alone is not enough because it can reinstall the previously locked version; include
`--upgrade` and `--refresh`.
Then refresh shell command lookup with `hash -r` when available, run `command -v guanlan` and
`which -a guanlan` (or the platform equivalent), and run `guanlan version`. If the version does not
match README/release notes, stop and report the path/version mismatch instead of configuring MCP or
using the tool. If an Agent reports PyPI as older than GitHub, verify with direct PyPI JSON and pip's
index source instead of search-result snippets or cached app text:
`curl -fsSL -H 'Cache-Control: no-cache' https://pypi.org/pypi/guanlan/json | python3 -c 'import json,sys; print(json.load(sys.stdin)["info"]["version"])'`
and `python3 -m pip index versions guanlan --index-url https://pypi.org/simple`. If Homebrew is stale, switch to the uv path.

Post-update smoke rule: after a full reinstall, run `guanlan capabilities`, `guanlan doctor --install-check`, `guanlan doctor --trace`,
`guanlan search "人工智能 政策" --profile china --limit 5 --trace`, and
`guanlan hotnews today --limit 5 --trends`. Report the exact version, executable path, and smoke
results to the user. Do not treat an old global executable as a successful update.

Agent operating rule: when using Guanlan for search, research, hotnews, pulse, or archive lookup,
prefer the largest sensible result pool instead of a tiny sample. Use the default 80 results for
normal work, raise to 80-100 for broad research when latency is acceptable, and only lower the
limit when the user explicitly asks for a small sample or a quick smoke check.
If a user, benchmark, or downstream Agent asks for `--limit` below 30, accept the command but treat
it as a smoke sample, not as a research-grade evidence pool. Persuade the Agent/user to rerun with
`--limit 80` before making strong claims.

Source registry rule: use `guanlan sources list/show/explain` when the Agent needs to explain source identity, authority/sample/freshness values, risk tags, or why a route prefers official/vertical/community sources. This is read-only metadata and must not be reported as actual search results.

Workflow decision rule: use `guanlan agent "query" --json` (or MCP `guanlan_agent`) when the Agent is unsure which Guanlan command to run and wants the smallest safe command chain; execute its `primary_command` first, inspect `quality_tripwires`, and only continue through `agent_next_steps` when quality signals or the user need justify it. If a tripwire fires, run `silent_repair_commands` before answering and present the result as an evidence-bound补证, not as Guanlan failure. Use `guanlan workflow "query"` when the Agent specifically needs the light/heavy decision contract without a command shortlist. Keep simple lookups direct; do not run `investigate` for basic website/link/fact searches. Use `guanlan investigate "query" --limit 80 --format context` only when the user explicitly needs deep research, cross-source evidence, comparison, timeline, dossier, high-impact verification, or a reusable evidence packet.

Page diagnosis rule: use `guanlan diagnose page "URL"` when `guanlan read` returns a weak body,
dynamic shell, login/WAF/access gate, or search-fallback-only context. A page diagnosis is not a
browser automation request; it is a read-only explanation of why the page is or is not evidence and
which Guanlan command should be used next. Do not keep retrying a blocked/dynamic page before trying
the recommended structured source, scoped search, or archive workflow.
If diagnosis emits `browser_assist.recommended=true`, ask the user for explicit permission before
using the host Agent browser to open the target URL and read only the target page's visible content. If login, verification, or account switching is needed, let the user complete it in the browser first. Report it as
"Guanlan planned the route, then I used user-authorized browser-visible evidence as supplementary
evidence." For the visible-page task, do not read Cookie, Token, password, keychain, browser storage/profile, or
unrelated personal data. Private messages, orders, admin pages, and account pages may only be read as target-page visible evidence after separate explicit authorization for that target page, purpose, risk, and read-only scope; mark them as `private_account_evidence`. Cookie/credential access is a separate authorization flow and must not enter browser-visible payloads. Do not post, like, comment, follow, message, purchase, or submit forms.
If the user authorizes visible-page evidence, it may be archived with
`guanlan archive add-browser-note --from-json browser-notes.jsonl`; keep the
`browser_assisted` / `visible_page_only` boundary. `--url ... --text-file` is only a manual fallback when the host Agent has no browser extraction capability.

Quality salvage rule: when trace shows `quality_gate.reason=partial_salvage`, treat it as usable
strong-source evidence with gaps, not as a failed search. Read representative official/vertical URLs
before drawing conclusions. When read fallback reports `兜底状态: unusable`, do not cite fallback
search context; use page diagnosis, structured sources, scoped search, or host WebFetch as planned
supplemental reading.

Recipe rule: use `guanlan recipe list` and `guanlan recipe run <recipe> "query"` when a task matches
a repeated research pattern, such as university advisors, finance risk, product reputation,
public opinion, brand risk, competitor watch, pricing watch, review mining, app review,
entertainment pulse, security advisory, or tech radar. Recipes are explicit workflow templates; they
do not replace search/read/research, and they should not be treated as final answers.

Site/time constraint rule: `--site` is a hard filter. If `guanlan search ... --site gov.cn` returns
zero results after filtering, do not relax to Zhihu, generic SEO pages, or other domains. For explicit
years or year ranges, treat the requested window as a strong constraint: window-outside materials can
be background, not the main timeline or "latest" evidence.

External fetch strategy rule: when Guanlan emits `external_fetch_strategy`, the Agent may call the
host platform's WebFetch/WebRead tool to read Guanlan-selected candidate URLs. Report this as "Guanlan
planned the source route, then I used WebFetch to read target pages for extra evidence"; do not frame
it as Guanlan being fragile or failed.

User-facing wording rule: do not proactively tell users that Guanlan "崩了", "抽风了", "挂了",
"炸了", "翻车", "拉胯", "坏了", or similar. Tool/network details should be surfaced only when they
change the evidence boundary or reproducibility. Prefer: "Guanlan planned the source route; the target
page public read timed out or the upstream was slow, so I used the planned WebFetch/browser-visible
supplemental read and kept the source boundary." If the final answer can simply cite evidence, do that
without a side comment about tool status.

Agent routing shortcut rule: when a query clearly matches a dedicated route, go directly to that
route's `--preset` or `--scope` instead of starting with generic web search. Use `guanlan route
"query" --json` only when the intent is mixed, ambiguous, or you need to inspect evidence roles and
caveats first. Strong direct-route matches include: Western entertainment (`global_entertainment`),
Japanese/Korean entertainment (`jp_kr_entertainment`), cybersecurity/CVE/fraud (`cybersecurity`),
weather/disaster alerts (`weather_disaster`), sports (`sports`), science-news verification
(`science`), job/salary/interview research (`career`), podcast discovery (`podcast`), exam prep
(`test_prep`), university admissions/advisor pages (`university`), academic indexing/submission
(`academic`), finance/capital-market lookup (`finance`, `finance_quote`, `finance_disclosure`,
`finance_macro`, `finance_sentiment`, `finance_research`), and product/company reputation
(`reputation`).

Vertical entrypoint rule: for high-confidence vertical lookup tasks, Guanlan may inject direct
source seeds and `guanlan read` followups before or alongside search results. Treat these as
authoritative entrypoints to read, not as final answers. This is especially important for sports
scores/schedules/standings, finance quotes/disclosures/macro data, weather or disaster alerts,
CVE/security advisories, science agency claims, entertainment charts/ratings/box office, academic
indexing, and exam-official information.
Do not report "Guanlan found nothing" until the recommended direct `read` commands and the matching
scope/preset search have been tried.
If results are only direct source seeds because normal search backends timed out or were blocked,
read those seeds and follow `external_fetch_strategy`; direct seeds are authoritative entrypoints,
not full answers.

Agent workflow ladder rule: do not reduce Guanlan to one generic `search` call. Use a dynamic
minimum workflow:
- 2-step: `search -> read` when the result set is already clearly usable and you only need to verify a representative original page.
- 3-step: `route -> research -> scoped search` for normal research tasks or whenever quality signals are not yet good enough.
- 4-step: upgrade to `route -> research -> scoped search -> hotnews` for recent/hot tasks, `route -> research -> scoped search -> feeds` for tech/AI/developer tasks, and `route -> research -> scoped search -> dossier|compare|timeline` when source diversity is too narrow.
Do not fall back to generic `web_search` / `web_fetch` until the current Guanlan workflow tier has been completed and still lacks key evidence.

Benchmark rule: do not call a benchmark fair if it tests Guanlan with a workflow Guanlan is not
meant to use. Real-time or “today/just now/latest” queries must include `hotnews`; tech/AI queries
must include `feeds` or `research --preset tech`; policy/official tasks should usually be measured
with `research` or `search + read`, not with a single generic search pass. Do not report
`quality_summary=warn` as “Guanlan search failed”; that usually means “the evidence packet is not
complete enough yet.”

Routing regression rule: automatic routing changes must be covered by deterministic positive,
negative, and near-miss cases before they are trusted. Add high-error or tricky Agent queries to
`tests/fixtures/routing_regression_cases.jsonl` with expected and forbidden intents/scopes/command
fragments, then run `tests/test_routing_regression_cases.py`. For vertical benchmark changes, use
the optional `expected_*` and `forbidden_*` fields in `guanlan/evaluation.py`; do not rely only on
one happy-path query per category.

Live smoke trend rule: `guanlan quality live-smoke` is an optional公网漂移探针, not a default release
blocker. Scheduled or repeated checks may use `--record-history --trend-window N` (and optionally
`--history-path PATH`) to write JSONL under `~/.guanlan/quality/live-smoke-history.jsonl` and inspect
`live_trend_report` for new, recovered, persistent, or likely network/upstream failures. `--strict`
still controls only the current run's exit behavior; trends are evidence for diagnosis, not proof
that the topic has no results.

Agent timeout budget rule: Guanlan may touch multiple public web/RSS/hotnews sources in one command,
and weak networks can make some upstreams slow before Guanlan falls back or marks stale cache. If an
agent platform, MCP client, or automation runner lets you set a tool timeout, use these outer budgets:
60-90 seconds for `status`, `doctor`, `search`, and single-URL `read`; 120 seconds for `hotnews`,
`feeds`, `pulse`, batch reads, and default search-first `archive ingest-research`; 180-300 seconds
for `research`, `compare`, `timeline`, `dossier`, and `archive ingest-research --read-top N`;
300-600 seconds for install/update/release smoke workflows. These budgets are seconds by default.
If the host field is named `timeout_ms`, `timeout_milliseconds`, or otherwise documents milliseconds,
convert explicitly: 90 seconds = 90000 ms, 120 seconds = 120000 ms, 300 seconds = 300000 ms, and
600 seconds = 600000 ms. Do not pass a bare number such as `timeout=120` to downstream agents or
tools without confirming the unit. On timeout, retry once with `--cache-ttl 3600` where supported or
reduce `--read-top`, but do not shrink the result pool below the normal 80 just to make the command
finish faster. A timeout is network evidence, not evidence that the topic has no results.

When using Guanlan as an agent, prefer this minimal command set:

```bash
guanlan capabilities
guanlan welcome
guanlan agent "query" --json
guanlan search "query" --limit 80
guanlan search "中文问题" --profile china --limit 80
guanlan search "政策或产业问题" --profile china --scope party_central
guanlan search "电商零售问题" --profile china --scope ecommerce
guanlan hotnews ebrun:cross-border --limit 10
guanlan hotnews ebrun:retail --limit 10
guanlan hotnews ebrun:ai --limit 10
guanlan search "学术会议 投稿 检索问题" --profile china --scope academic
guanlan search "高校 研究生招生 导师 院系官网" --profile china --scope university
guanlan search "影视 综艺 游戏 明星 票房口碑" --profile china --scope entertainment
guanlan search "股票 股价 财报 公告 风险" --profile china --scope finance_disclosure --limit 80 --trace
guanlan search "上证指数 今日 行情" --profile china --scope finance_quote --limit 80 --trace
guanlan search "社融 CPI 降息 央行" --profile china --scope finance_macro --limit 80 --trace
guanlan stock plan "宁德时代 股价 财报 公告 最近风险"
guanlan stock quote "贵州茅台"
guanlan stock quote "024051"
guanlan stock detail "600519"
guanlan stock fundflow "宁德时代"
guanlan-stock rank --sort turnover --limit 20
guanlan-stock index
guanlan search "Taylor Swift 最新动态" --profile english --scope global_entertainment
guanlan search "K-pop 最新回归" --profile hybrid --scope jp_kr_entertainment
guanlan search "OpenSSL CVE 最新 漏洞 影响版本" --scope cybersecurity --limit 80 --trace
guanlan search "台风 路径 中央气象台 日本气象厅" --scope weather_disaster --limit 80 --trace
guanlan search "梅西 比赛 伤病 最新" --scope sports --limit 80
guanlan research "NBA季后赛2026年首轮战绩比分" --preset sports --read-top 5
guanlan search "詹姆斯韦伯 外星生命 NASA" --scope science --profile english --limit 80
guanlan search "AI 创业 播客 小宇宙" --scope podcast --limit 80
guanlan search --list-scopes
guanlan route "中文研究需求" --json
guanlan workflow "中文研究需求" --json
guanlan diagnose page "https://example.com/article"
guanlan browser-assist plan "https://example.com/article" --json
guanlan browser-assist adapters
guanlan browser-assist setup-openguanlan --json
guanlan browser-assist setup-opencli --json
guanlan browser-assist run "https://example.com/article" --adapter openguanlan --json
guanlan browser-assist run "https://example.com/article" --adapter browser-use --json
guanlan recipe list
guanlan recipe run finance-risk "宁德时代 股价 财报 公告 最近风险"
guanlan recipe run university-advisor "南京师范大学中北学院 计算机 导师 招生"
guanlan recipe run trajectory-map "Cursor 发展历程 竞品格局"
guanlan recipe run public-opinion-pulse "某产品 最近风评 被夸还是被骂"
guanlan recipe run brand-risk-watch "某品牌 负面 投诉 道歉 澄清"
guanlan recipe run competitor-watch "某产品 竞品 功能 定价 口碑"
guanlan recipe run pricing-watch "某产品 定价变化 套餐调整"
guanlan recipe run review-mining "某产品 用户评论 差评 好评 反馈"
guanlan recipe run app-review-pulse "某 App 应用商店评论 差评主题"
guanlan investigate "复杂研究需求" --limit 80 --format context
guanlan investigate "复杂研究需求" --budget deep --dry-run
guanlan sources explain "中文研究需求"
guanlan sources audit
guanlan eval suite run chinese-web-v1
guanlan eval suite run chinese-web-live --mode live
guanlan quality performance
guanlan quality live-smoke --record-history --trend-window 10
guanlan read "https://example.com/article" --max-chars 12000
guanlan read "https://mp.weixin.qq.com/s/ARTICLE_ID" --trace --max-chars 12000
guanlan wechat-exporter status
guanlan wechat-exporter status --probe --json
guanlan wechat-exporter account-search "公众号名称" --json
guanlan wechat-exporter articles "fakeid" --size 20 --json
guanlan wechat-exporter download "https://mp.weixin.qq.com/s/ARTICLE_ID" --format markdown
guanlan read "https://example.com/article" --quality-report
guanlan read "https://example.com/article" --strict --trace
guanlan feeds arxiv --keyword "AI Agent" --limit 80
guanlan feeds watchlist --watchlist ~/.guanlan/feeds-watchlist.json --limit 80
guanlan research "query" --profile china --advisor
guanlan research "EI会议 投稿 检索 要求" --preset academic --read-top 0
guanlan research "清华大学计算机系研究生招生 导师" --preset university --read-top 0
guanlan research "影视 综艺 游戏 明星 票房口碑" --preset entertainment --read-top 0
guanlan research "宁德时代 股价 财报 公告 最近风险" --preset finance --read-top 5 --advisor
guanlan research "Taylor Swift 最新动态 新专辑 巡演" --preset global_entertainment --profile english
guanlan research "BLACKPINK K-pop 最新回归" --preset jp_kr_entertainment --profile hybrid
guanlan research "OpenSSL CVE 最新 漏洞 影响版本" --preset cybersecurity --read-top 5
guanlan research "字节 AI 产品经理 校招 薪资 面经" --preset career --read-top 5
guanlan research "雅思 口语 题库 机经" --preset test_prep --read-top 4
guanlan research "产品 用户评价" --preset reputation --read-top 0 --advisor
guanlan compare "A" "B" --focus "价格 口碑 风险" --limit 80 --format context
guanlan timeline "某事件 最新进展" --limit 80 --format context
guanlan dossier "某对象" --focus "业务 口碑 风险" --limit 80 --format context
guanlan prompt "query" --profile china --style evidence
guanlan hotnews today --limit 80
guanlan hotnews today --limit 80 --trends
guanlan hotnews weibo --limit 80
guanlan hotnews bilibili --limit 80
guanlan hotnews ithome --limit 80
guanlan hotnews v2ex --limit 80
guanlan hotnews tophub:weibo --limit 80
guanlan hotnews tophub:catalog:news --limit 80
guanlan hotnews hotboard:catalog:finance --limit 30
guanlan hotnews hotboard:snapshots:weibo --limit 20
guanlan hotnews uapis:catalog --limit 80
guanlan hotnews vvhan:all --limit 80
guanlan doctor --install-check
guanlan doctor --trace
guanlan archive add-browser-note --from-json browser-notes.jsonl
guanlan archive ingest-research "query" --limit 80
guanlan archive ingest-research "query" --limit 80 --read-top 3
guanlan archive verify
guanlan archive embed --backend local
guanlan archive search "query" --semantic --limit 20
guanlan archive context "query" --semantic --limit 20
guanlan archive wiki build --output ./guanlan-wiki
guanlan archive pack "query" --format langchain-jsonl --output guanlan-pack.jsonl
guanlan report html --input results.json --output report.html
guanlan quality coverage
guanlan eval benchmark
guanlan eval scenarios --format jsonl
```

Read [docs/agent-playbook.md](docs/agent-playbook.md) and [docs/agent-usage.md](docs/agent-usage.md) for the full agent routing guide.

Safety rules:

- Do not read browser cookies unless the user gives separate explicit authorization for the target platform, purpose, risk, and read-only scope.
- Do not run `guanlan configure --from-browser ...` without user approval.
- Do not run `guanlan doctor --auth-check` unless the user wants deep auth checks.
- Do not post, comment, like, follow, or send messages automatically.
- Prefer public search/read/hotnews first, then ask for authorization only when needed.
- Use `guanlan welcome` when a new user asks how to start using Guanlan with their agent.
- Use `guanlan capabilities` when the user asks what Guanlan can do, which Guanlan command/tool to use, or why the tool is relevant.
- Use `guanlan route "query"` when deciding which source pools, sites, evidence roles, and caveats fit a request; route plans are soft guidance, not hard filters.
- Use `guanlan diagnose page "URL"` before repeatedly retrying a weak `read`; if it reports dynamic shell, access gate, or search-fallback-only context, use the recommended structured/scoped/archive path instead of treating the page as evidence.
- If `diagnose page` recommends browser-assisted evidence, ask first and only read the target browser-visible page content; use `browser-assist adapters` / `browser-assist run --adapter openguanlan` to get the OpenGuanlan execution contract. OpenGuanlan means the whole Guanlan browser-assist layer: by default it uses the host Agent browser visible-page contract and does not require a Chrome extension, daemon, OpenCLI, Playwright, a separate browser profile, or browser profile reads. Private/account pages require separate target-page authorization and `private_account_evidence=true`. Cookie/credential material stays outside browser-visible payloads. Archive authorized visible notes with `archive add-browser-note` and preserve the evidence boundary.
- If the user explicitly wants a dedicated browser bridge beyond the host Agent browser, use the optional sidecar path: `guanlan browser-assist setup-openguanlan --json` and `guanlan browser-assist run "URL" --adapter openguanlan-bridge --json`. Do not define OpenGuanlan as "the plugin"; the Chrome extension/daemon/pair-code flow is only `openguanlan-bridge`. Do not require users to install OpenCLI for Guanlan core workflows. `open-cli` / `setup-opencli` remain compatibility paths only for users who already want OpenCLI. For Chrome Web Store builds, keep optional bridge default host permissions limited to localhost daemon access and request target website access through the popup's per-site optional permission flow; build the zip with `scripts/build_openguanlan_extension.sh`. Bridge pairing is a manual user step only when that optional sidecar is used: run `openguanlan pair-code --json`, paste the code into the popup once, and use `openguanlan pair-reset --json` when rotating trust.
- Treat browser-assist adapters by capability layer. `extractor` adapters can produce browser-visible JSON/JSONL; `opener` adapters only open target URLs and still require the host Agent browser to extract visible text. Read `can_open`, `can_extract_visible_text`, `can_reuse_existing_session`, `can_wait_dynamic_ready`, `can_scroll_until_min_items`, `can_read_private_account_visible_pages`, `credential_material_access_allowed`, `cookie_flow_available`, `capability_score`, and `risk_score` before choosing an adapter.
- Use `guanlan recipe run <recipe> "query"` when the user task matches a reusable vertical workflow; recipes are plans and boundaries, not final conclusions.
- Use `guanlan search ... --trace` or `guanlan research ...` when you need query_strategy, source diagnostics, and evidence-role query rewrites; do not rely on one broad query for serious research.
- Use `guanlan compare`, `guanlan timeline`, or `guanlan dossier` when the user asks for comparison, event chronology, or an entity dossier; these are structured views over evidence packets, not final truth.
- Use `guanlan research ... --preset academic --read-top 0` for EI/SCI/Scopus, academic conference, paper submission, indexing, and university-recognition questions; read selected official URLs afterward if needed.
- Use `guanlan feeds arxiv --keyword "query" --limit 80` when a task asks for arXiv, preprints, paper leads, recent academic work, or research discovery. Treat `preprint_record` as a paper lead, not a peer-reviewed conclusion. If arXiv API is rate-limited and the output contains `preprint_search_entrypoint` or `api_unavailable`, use the returned arXiv search entrypoint or a matching `research --preset academic` follow-up rather than reporting no academic evidence.
- Use `guanlan research ... --preset university --read-top 0` or `guanlan search ... --scope university` for graduate admissions, advisor/faculty lists, department pages, program catalogs, and university official notices. Do not use academic databases as primary evidence for admissions/advisor lists.
- Use `guanlan research ... --preset entertainment --read-top 0` for film, drama, variety show, music, celebrity, game, box-office, rating, and fandom/public-discussion questions; separate platform metrics, user ratings, industry reports, promotion copy, and fandom samples.
- Use `guanlan research ... --preset global_entertainment --profile english` for Western entertainment, Hollywood, pop stars, tours, albums, Billboard/Grammy/award questions; prioritize English trade media, charts/awards, and official artist/label statements over fan or tabloid claims.
- Use `guanlan research ... --preset jp_kr_entertainment --profile hybrid` for Japanese/Korean entertainment, K-pop/J-pop, K-drama/J-drama, Oricon/Soompi/Naver questions; separate local media/charts, agency statements, translation sites, and fandom samples.
- Use `guanlan stock ...` or `guanlan-stock ...` for structured stock quotes, ETF/fund NAV, market overview, rankings, fund flow, plates, and stock news before trying to read dynamic finance pages. If the Agent does not know how to handle a stock/fund task, run `guanlan stock plan "query"` first. Trigger it for 股票、股价、ETF、基金、净值、联接基金、行情、指数、大盘、资金流向、财报、公告、雪球、股吧、研报、风险 and similar terms. Use `guanlan research ... --preset finance`, `search --scope finance_disclosure`, `search --scope finance_quote`, `search --scope finance_macro`, `search --scope finance_sentiment`, or `search --scope finance_research` for broader evidence. Separate quote/NAV data, company or fund disclosures, regulation, news, research opinions, and sentiment samples. Do not output buy/sell/hold advice.
- Use `guanlan research ... --preset cybersecurity` or `search --scope cybersecurity --trace` for CVE, vulnerabilities, patches, vendor advisories, phishing, fraud, and suspicious messages; prioritize CVE/NVD/CISA/vendor/regulator sources.
- Use `guanlan search ... --scope weather_disaster --trace` for typhoon, weather alert, earthquake, disaster, and official safety questions; prioritize official meteorological/emergency sources and check timestamps.
- Use `guanlan research ... --preset sports`, `--preset science`, `--preset career`, `--preset podcast`, or `--preset test_prep` for sports, science-news verification, job/salary/interview, podcast discovery, and exam-prep questions instead of leaving them as generic web search.
- Use `guanlan hotnews hotboard:catalog:*` as the local full hotboard directory when a task needs platform-level hotboard routing; this uses the packaged hotboard catalog and does not require a key. Use `guanlan hotnews hotboard:snapshots:<node>` for free snapshot IDs when a key and active balance are configured. Use `guanlan hotnews hotboard:<node>` only as explicit opt-in detail fetching; it is cache-backed and metered, so keep `paid_api` / `cost_u` metadata visible to downstream agents.
- Use `guanlan hotnews ebrun:<channel>` when an ecommerce/retail/cross-border/brand/industrial-internet/AI-commerce task needs a fresh Ebrun vertical channel signal. Useful aliases include `cross-border`, `retail`, `temu`, `amazon`, `tiktok-shop`, `brand-globalization`, `industrial`, and `ai`. Treat it as a small latest-items discovery window, then run `search/research --scope ecommerce --limit 80` or read representative URLs before making claims.
- Use `guanlan hotnews tophub:*`, `guanlan hotnews uapis:*`, `guanlan hotnews vvhan:*`, or `guanlan hotnews hotboard:*` only as optional external hotboard expansion. Keep the `external_backend`, cache/staleness, and cost metadata in mind; do not treat third-party aggregate lists as authoritative facts.
- For technology/AI/developer routing, always include one RSS discovery pass. `guanlan research ... --preset tech` does this automatically; when a query matches AI/WPS/Agent/large-model semantics, research also internally includes an AI vertical selected-dynamics source as a discovery layer. This is not a new user command and does not replace original URLs, official docs, code repositories, announcements, or product pages. If you only run `route` or `search`, also run `guanlan feeds curated --limit 80` or `guanlan feeds curated --category ai --limit 80` as a second pass.
- Use `guanlan read ... --quality-report` when deciding whether a page body is clean enough for downstream reasoning; use `--strict` when noisy page chrome would be harmful; use `--extract metadata` or `--extract links` for source/date/link checks.
- `guanlan read` has a native WeChat article extractor for `mp.weixin.qq.com` article URLs. For public WeChat article links, try normal `read` first; it should expose `selected_backend=wechat_article` in trace when the article body is directly readable. This path extracts public article HTML only and must not read Cookie, Token, credentials, IndexedDB, localStorage, browser profile, or公众号后台 pages. Only move to `diagnose page` or user-authorized browser-visible evidence when the WeChat extractor, Jina, and direct HTML path still return weak/blocked content.
- Use `guanlan wechat-exporter ...` only when the user has explicitly configured a WeChat article exporter service. It reads `GUANLAN_WECHAT_EXPORTER_BASE_URL` and optional `GUANLAN_WECHAT_EXPORTER_AUTH_KEY` from the current environment; never ask the user to paste the auth key into prompts, logs, README, docs, commits, or release notes. Treat account search, article history, reading metrics, comments, and batch download as `wechat_exporter_authorized_account_api` or `wechat_exporter_download` evidence with session/auth-key expiry boundaries. Do not use wxdown-service, mitmproxy, credentials, Cookie, or browser storage unless the user separately authorizes the target platform, purpose, risk, and read-only scope.
- Use `guanlan feeds watchlist --watchlist PATH --limit 80` when the Agent needs to observe a user-maintained RSS/Atom set, project/blog watchlist, or explicit long-term source pool. The watchlist file may be JSON, JSONL, or plain text with one feed URL per line. Treat `watchlist_update_signal` as source-update evidence with `user_watchlist` / `feed_dependent` boundaries, not as whole-web discovery.
- Use `guanlan archive verify` before relying on archive as memory/RAG/Wiki; use `archive context` or `archive wiki context` when a local model needs evidence-bound context from stored materials.
- Use `guanlan archive wiki build` only as a local sidecar export over existing archive records; it must not be treated as whole-web truth or cloud sync.
- Use `guanlan report html ...` only as a sidecar renderer when the user asks for an HTML report; it reads existing JSON/stdin/demo data and must not replace the main search/read/research/hotnews flows.
- Before release, run `scripts/pre_release_status.sh`, `guanlan quality foundational`, `guanlan quality coverage`, `guanlan quality regression`, `guanlan quality robustness`, `guanlan quality backend-fixtures`, and `guanlan eval benchmark`; the full `scripts/release_gate.sh` remains the source of truth. Do not ship if it fails; new versions must not silently shrink the default result pool, remove agent-facing evidence metadata, or return polluted backend results without diagnostics.
- Use `guanlan research ... --advisor` when the user asks for advice, implications, next steps, or "why they might be searching this"; treat the advisor block as evidence-bound writing rules for your answer, not as the user's true intent or a final decision.
