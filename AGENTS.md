# AGENTS.md

This repository is designed as a CLI-first search productivity tool for AI agents.

Memory rule: treat `AGENTS.md`, `docs/agent-playbook.md`, `docs/agent-usage.md`, and
`guanlan/skill/SKILL.md` as the durable memory surfaces for how to operate Guanlan. Before building
new benchmarks, automations, or MCP workflows, reread at least `AGENTS.md` and
`docs/agent-playbook.md`.

Commit/release language rule: Guanlan is a Chinese-web research tool. Use Chinese-first
commit subjects, changelog entries, and release notes. Keep conventional prefixes such as
`feat:` / `fix:` / `docs:` when useful, but write the description in Chinese, for example
`feat: 扩展垂直路由和搜索质量反馈`.

Install/update rule: after installing or upgrading Guanlan, always do a full reinstall, not an
incremental upgrade, before configuring MCP, optional channels, or auth. Prefer one clean path:
`uv tool install --force --upgrade guanlan`; if the user explicitly wants Homebrew, run
`brew update && brew reinstall shenyangs/tap/guanlan`; for pipx, run `pipx install --force guanlan`.
For uv, `--force` alone is not enough because it can reinstall the previously locked version; include
`--upgrade`.
Then refresh shell command lookup with `hash -r` when available, run `command -v guanlan` and
`which -a guanlan` (or the platform equivalent), and run `guanlan version`. If the version does not
match README/release notes, stop and report the path/version mismatch instead of configuring MCP or
using the tool. If Homebrew is stale, switch to the uv path.

Post-update smoke rule: after a full reinstall, run `guanlan capabilities`, `guanlan doctor --install-check`, `guanlan doctor --trace`,
`guanlan search "人工智能 政策" --profile china --limit 5 --trace`, and
`guanlan hotnews today --limit 5 --trends`. Report the exact version, executable path, and smoke
results to the user. Do not treat an old global executable as a successful update.

Agent operating rule: when using Guanlan for search, research, hotnews, pulse, or archive lookup,
prefer the largest sensible result pool instead of a tiny sample. Use the default 80 results for
normal work, raise to 80-100 for broad research when latency is acceptable, and only lower the
limit when the user explicitly asks for a small sample or a quick smoke check.

Agent routing shortcut rule: when a query clearly matches a dedicated route, go directly to that
route's `--preset` or `--scope` instead of starting with generic web search. Use `guanlan route
"query" --json` only when the intent is mixed, ambiguous, or you need to inspect evidence roles and
caveats first. Strong direct-route matches include: Western entertainment (`global_entertainment`),
Japanese/Korean entertainment (`jp_kr_entertainment`), cybersecurity/CVE/fraud (`cybersecurity`),
weather/disaster alerts (`weather_disaster`), sports (`sports`), science-news verification
(`science`), job/salary/interview research (`career`), podcast discovery (`podcast`), exam prep
(`test_prep`), university admissions/advisor pages (`university`), academic indexing/submission
(`academic`), and product/company reputation (`reputation`).

Vertical entrypoint rule: for high-confidence vertical lookup tasks, Guanlan may inject direct
source seeds and `guanlan read` followups before or alongside search results. Treat these as
authoritative entrypoints to read, not as final answers. This is especially important for sports
scores/schedules/standings, weather or disaster alerts, CVE/security advisories, science agency
claims, entertainment charts/ratings/box office, academic indexing, and exam-official information.
Do not report "Guanlan found nothing" until the recommended direct `read` commands and the matching
scope/preset search have been tried.

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

Agent timeout budget rule: Guanlan may touch multiple public web/RSS/hotnews sources in one command,
and weak networks can make some upstreams slow before Guanlan falls back or marks stale cache. If an
agent platform, MCP client, or automation runner lets you set a tool timeout, use these outer budgets:
60-90 seconds for `status`, `doctor`, `search`, and single-URL `read`; 120 seconds for `hotnews`,
`feeds`, `pulse`, and batch reads; 180-300 seconds for `research`, `compare`, `timeline`, `dossier`,
and `archive ingest-research`; 300-600 seconds for install/update/release smoke workflows. On timeout,
retry once with `--cache-ttl 3600` where supported or reduce `--read-top`, but do not shrink the
result pool below the normal 80 just to make the command finish faster. A timeout is network evidence,
not evidence that the topic has no results.

When using Guanlan as an agent, prefer this minimal command set:

```bash
guanlan capabilities
guanlan welcome
guanlan search "query" --limit 80
guanlan search "中文问题" --profile china --limit 80
guanlan search "政策或产业问题" --profile china --scope party_central
guanlan search "电商零售问题" --profile china --scope ecommerce
guanlan search "学术会议 投稿 检索问题" --profile china --scope academic
guanlan search "高校 研究生招生 导师 院系官网" --profile china --scope university
guanlan search "影视 综艺 游戏 明星 票房口碑" --profile china --scope entertainment
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
guanlan read "https://example.com/article" --max-chars 12000
guanlan read "https://example.com/article" --quality-report
guanlan read "https://example.com/article" --strict --trace
guanlan research "query" --profile china --advisor
guanlan research "EI会议 投稿 检索 要求" --preset academic --read-top 0
guanlan research "清华大学计算机系研究生招生 导师" --preset university --read-top 0
guanlan research "影视 综艺 游戏 明星 票房口碑" --preset entertainment --read-top 0
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
guanlan hotnews uapis:catalog --limit 80
guanlan hotnews vvhan:all --limit 80
guanlan doctor --install-check
guanlan doctor --trace
guanlan archive ingest-research "query" --limit 80
guanlan archive verify
guanlan archive context "query" --limit 20
guanlan archive wiki build --output ./guanlan-wiki
guanlan archive pack "query" --format langchain-jsonl --output guanlan-pack.jsonl
guanlan report html --input results.json --output report.html
guanlan quality coverage
guanlan eval benchmark
guanlan eval scenarios --format jsonl
```

Read [docs/agent-playbook.md](docs/agent-playbook.md) and [docs/agent-usage.md](docs/agent-usage.md) for the full agent routing guide.

Safety rules:

- Do not read browser cookies unless the user explicitly asks.
- Do not run `guanlan configure --from-browser ...` without user approval.
- Do not run `guanlan doctor --auth-check` unless the user wants deep auth checks.
- Do not post, comment, like, follow, or send messages automatically.
- Prefer public search/read/hotnews first, then ask for authorization only when needed.
- Use `guanlan welcome` when a new user asks how to start using Guanlan with their agent.
- Use `guanlan capabilities` when the user asks what Guanlan can do, which Guanlan command/tool to use, or why the tool is relevant.
- Use `guanlan route "query"` when deciding which source pools, sites, evidence roles, and caveats fit a request; route plans are soft guidance, not hard filters.
- Use `guanlan search ... --trace` or `guanlan research ...` when you need query_strategy, source diagnostics, and evidence-role query rewrites; do not rely on one broad query for serious research.
- Use `guanlan compare`, `guanlan timeline`, or `guanlan dossier` when the user asks for comparison, event chronology, or an entity dossier; these are structured views over evidence packets, not final truth.
- Use `guanlan research ... --preset academic --read-top 0` for EI/SCI/Scopus, academic conference, paper submission, indexing, and university-recognition questions; read selected official URLs afterward if needed.
- Use `guanlan research ... --preset university --read-top 0` or `guanlan search ... --scope university` for graduate admissions, advisor/faculty lists, department pages, program catalogs, and university official notices. Do not use academic databases as primary evidence for admissions/advisor lists.
- Use `guanlan research ... --preset entertainment --read-top 0` for film, drama, variety show, music, celebrity, game, box-office, rating, and fandom/public-discussion questions; separate platform metrics, user ratings, industry reports, promotion copy, and fandom samples.
- Use `guanlan research ... --preset global_entertainment --profile english` for Western entertainment, Hollywood, pop stars, tours, albums, Billboard/Grammy/award questions; prioritize English trade media, charts/awards, and official artist/label statements over fan or tabloid claims.
- Use `guanlan research ... --preset jp_kr_entertainment --profile hybrid` for Japanese/Korean entertainment, K-pop/J-pop, K-drama/J-drama, Oricon/Soompi/Naver questions; separate local media/charts, agency statements, translation sites, and fandom samples.
- Use `guanlan research ... --preset cybersecurity` or `search --scope cybersecurity --trace` for CVE, vulnerabilities, patches, vendor advisories, phishing, fraud, and suspicious messages; prioritize CVE/NVD/CISA/vendor/regulator sources.
- Use `guanlan search ... --scope weather_disaster --trace` for typhoon, weather alert, earthquake, disaster, and official safety questions; prioritize official meteorological/emergency sources and check timestamps.
- Use `guanlan research ... --preset sports`, `--preset science`, `--preset career`, `--preset podcast`, or `--preset test_prep` for sports, science-news verification, job/salary/interview, podcast discovery, and exam-prep questions instead of leaving them as generic web search.
- Use `guanlan hotnews tophub:*`, `guanlan hotnews uapis:*`, or `guanlan hotnews vvhan:*` only as optional external hotboard expansion. Keep the `external_backend` and cache/staleness metadata in mind; do not treat third-party aggregate lists as authoritative facts.
- For technology/AI/developer routing, always include one RSS discovery pass. `guanlan research ... --preset tech` does this automatically; if you only run `route` or `search`, also run `guanlan feeds curated --limit 80` or `guanlan feeds curated --category ai --limit 80` as a second pass.
- Use `guanlan read ... --quality-report` when deciding whether a page body is clean enough for downstream reasoning; use `--strict` when noisy page chrome would be harmful; use `--extract metadata` or `--extract links` for source/date/link checks.
- Use `guanlan archive verify` before relying on archive as memory/RAG/Wiki; use `archive context` or `archive wiki context` when a local model needs evidence-bound context from stored materials.
- Use `guanlan archive wiki build` only as a local sidecar export over existing archive records; it must not be treated as whole-web truth or cloud sync.
- Use `guanlan report html ...` only as a sidecar renderer when the user asks for an HTML report; it reads existing JSON/stdin/demo data and must not replace the main search/read/research/hotnews flows.
- Before release, run `guanlan quality coverage`, `guanlan quality regression`, and `guanlan eval benchmark` and do not ship if it fails; new versions must not silently shrink the default result pool or remove agent-facing evidence metadata.
- Use `guanlan research ... --advisor` when the user asks for advice, implications, next steps, or "why they might be searching this"; treat the advisor block as evidence-bound writing rules for your answer, not as the user's true intent or a final decision.
