# AGENTS.md

This repository is designed as a CLI-first search productivity tool for AI agents.

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
guanlan search "影视 综艺 游戏 明星 票房口碑" --profile china --scope entertainment
guanlan search --list-scopes
guanlan route "中文研究需求" --json
guanlan read "https://example.com/article" --max-chars 12000
guanlan read "https://example.com/article" --quality-report
guanlan read "https://example.com/article" --strict --trace
guanlan research "query" --profile china --advisor
guanlan research "EI会议 投稿 检索 要求" --preset academic --read-top 0
guanlan research "影视 综艺 游戏 明星 票房口碑" --preset entertainment --read-top 0
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

Read [docs/agent-usage.md](docs/agent-usage.md) for the full agent routing guide.

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
- Use `guanlan research ... --preset entertainment --read-top 0` for film, drama, variety show, music, celebrity, game, box-office, rating, and fandom/public-discussion questions; separate platform metrics, user ratings, industry reports, promotion copy, and fandom samples.
- For technology/AI/developer routing, always include one RSS discovery pass. `guanlan research ... --preset tech` does this automatically; if you only run `route` or `search`, also run `guanlan feeds curated --limit 80` or `guanlan feeds curated --category ai --limit 80` as a second pass.
- Use `guanlan read ... --quality-report` when deciding whether a page body is clean enough for downstream reasoning; use `--strict` when noisy page chrome would be harmful; use `--extract metadata` or `--extract links` for source/date/link checks.
- Use `guanlan archive verify` before relying on archive as memory/RAG/Wiki; use `archive context` or `archive wiki context` when a local model needs evidence-bound context from stored materials.
- Use `guanlan archive wiki build` only as a local sidecar export over existing archive records; it must not be treated as whole-web truth or cloud sync.
- Use `guanlan report html ...` only as a sidecar renderer when the user asks for an HTML report; it reads existing JSON/stdin/demo data and must not replace the main search/read/research/hotnews flows.
- Before release, run `guanlan quality coverage`, `guanlan quality regression`, and `guanlan eval benchmark` and do not ship if it fails; new versions must not silently shrink the default result pool or remove agent-facing evidence metadata.
- Use `guanlan research ... --advisor` when the user asks for advice, implications, next steps, or "why they might be searching this"; treat the advisor block as evidence-bound writing rules for your answer, not as the user's true intent or a final decision.
