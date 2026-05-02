# AGENTS.md

This repository is designed as a CLI-first search productivity tool for AI agents.

Install rule: after installing or upgrading Guanlan, always run `guanlan version` and compare it
with the version documented in README/release notes before configuring MCP, optional channels, or
auth. If Homebrew installs an older version, run `brew update` and reinstall
`shenyangs/tap/guanlan`; if it is still stale, use the GitHub/uv install path instead.

Agent operating rule: when using Guanlan for search, research, hotnews, pulse, or archive lookup,
prefer the largest sensible result pool instead of a tiny sample. Use the default 50 results for
normal work, raise to 80-100 for broad research when latency is acceptable, and only lower the
limit when the user explicitly asks for a small sample or a quick smoke check.

When using Guanlan as an agent, prefer this minimal command set:

```bash
guanlan capabilities
guanlan welcome
guanlan search "query" --limit 50
guanlan search "中文问题" --profile china --limit 50
guanlan search "政策或产业问题" --profile china --scope party_central
guanlan search "电商零售问题" --profile china --scope ecommerce
guanlan search "学术会议 投稿 检索问题" --profile china --scope academic
guanlan search --list-scopes
guanlan route "中文研究需求" --json
guanlan read "https://example.com/article" --max-chars 12000
guanlan read "https://example.com/article" --quality-report
guanlan read "https://example.com/article" --strict --trace
guanlan research "query" --profile china --advisor
guanlan research "EI会议 投稿 检索 要求" --preset academic --read-top 0
guanlan research "产品 用户评价" --preset reputation --read-top 0 --advisor
guanlan prompt "query" --profile china --style evidence
guanlan hotnews today --limit 50
guanlan hotnews today --limit 50 --trends
guanlan hotnews weibo --limit 50
guanlan hotnews bilibili --limit 50
guanlan hotnews ithome --limit 50
guanlan hotnews v2ex --limit 50
guanlan doctor --trace
guanlan archive ingest-search "query" --limit 80
guanlan quality coverage
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
- Use `guanlan research ... --preset academic --read-top 0` for EI/SCI/Scopus, academic conference, paper submission, indexing, and university-recognition questions; read selected official URLs afterward if needed.
- Use `guanlan read ... --quality-report` when deciding whether a page body is clean enough for downstream reasoning; use `--strict` when noisy page chrome would be harmful; use `--extract metadata` or `--extract links` for source/date/link checks.
- Before release, run `guanlan quality coverage` and do not ship if it fails; new versions must not silently shrink the default result pool or remove agent-facing evidence metadata.
- Use `guanlan research ... --advisor` when the user asks for advice, implications, next steps, or "why they might be searching this"; treat the advisor block as evidence-bound writing rules for your answer, not as the user's true intent or a final decision.
