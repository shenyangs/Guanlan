# AGENTS.md

This repository is designed as a CLI-first search productivity tool for AI agents.

When using Guanlan as an agent, prefer this minimal command set:

```bash
guanlan search "query" --limit 8
guanlan search "中文问题" --profile china --limit 8
guanlan search "政策或产业问题" --profile china --scope party_central
guanlan search "电商零售问题" --profile china --scope ecommerce
guanlan search --list-scopes
guanlan read "https://example.com/article" --max-chars 12000
guanlan hotnews baidu --limit 10
guanlan hotnews v2ex --limit 10
guanlan doctor --trace
```

Read [docs/agent-usage.md](docs/agent-usage.md) for the full agent routing guide.

Safety rules:

- Do not read browser cookies unless the user explicitly asks.
- Do not run `guanlan configure --from-browser ...` without user approval.
- Do not run `guanlan doctor --auth-check` unless the user wants deep auth checks.
- Do not post, comment, like, follow, or send messages automatically.
- Prefer public search/read/hotnews first, then ask for authorization only when needed.
