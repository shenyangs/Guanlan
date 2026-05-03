# Guanlan

> Observe the current, trace the source, keep the boundary clear.

Guanlan is a CLI-first Chinese-web research and source-routing tool for AI agents. It is not just a search wrapper: it routes a question to suitable source pools, reads public pages, tracks hot topics, builds evidence packets, and tells downstream agents what can be treated as official evidence, media reporting, user samples, or only open-web context.

The canonical documentation is maintained in Chinese. This English page is a synchronized summary for international users and agent integrators.

## Start Here

| Document | Use it for |
| --- | --- |
| [Chinese README](../README.md) | Canonical positioning, install path, examples, and release notes. |
| [Changelog](../CHANGELOG.md) | Version-by-version changes and boundary adjustments. |
| [Agent Playbook](agent-playbook.md) | Durable agent memory: dynamic workflows, benchmark discipline, fallback rules. |
| [Agent usage guide](agent-usage.md) | Search/read/hotnews/archive/MCP usage for AI agents. |
| [Contract](contract.md) | Stable output fields for CLI/MCP/HTTP/RAG integrations. |
| [Local LLM guide](local-llm.md) | Let Ollama, LM Studio, Open WebUI, and local models use Guanlan as a web evidence provider. |
| [Troubleshooting](troubleshooting.md) | Keychain prompts, network failures, cookies, and platform fallbacks. |
| [Source attribution](SOURCE_ATTRIBUTION.md) | Open-source projects and public sources referenced by Guanlan. |

## What Is Stable Now

- Public web search with China-aware profiles, source classification, evidence roles, source cards, quality scoring, and default broad result pools.
- URL reading with Jina Reader first, direct HTML fallback, quality reports, strict mode, batch reading, caching, and local snapshots.
- Chinese hot lists and trend clustering via `hotnews`, including multi-source status and stale/cache signals.
- Structured research workflows: `research`, `compare`, `timeline`, and `dossier` turn search results into evidence packets, comparisons, event timelines, and entity dossiers.
- Local archive and RAG bridge: SQLite/FTS archive, ingest audit, prompt-ready context, wiki export, and LangChain/LlamaIndex/OpenWebUI packs.
- Agent integration: CLI-first usage, optional MCP, optional local read-only HTTP service, and prompt/context commands for local models.

## v0.4.1 Search Reliability Updates

- Query guard: meaningless or keyboard-mash queries are rejected before hitting search backends, with diagnostics instead of random pages.
- Query rewrite: short factual queries, short reputation/ecommerce queries, and overlong queries are conservatively expanded or compressed.
- Recovery search: DuckDuckGo fallback passes and multi-entity fan-out reduce empty or one-entity-only result sets.
- Agent workflow plan: quality summaries now explain whether a task should follow a `2-step`, `3-step`, or `4-step` Guanlan workflow before falling back to generic web search.
- Empty JSON results can include structured `diagnostics`, so agents can report “query needs rewriting” instead of “search failed”.

## Core Commands

```bash
guanlan capabilities
guanlan welcome
guanlan search "query" --profile china --limit 80
guanlan search "policy topic" --profile china --scope party_central --trace
guanlan search "product reviews" --profile china --scope ecommerce --format context
guanlan route "mixed Chinese research task" --json
guanlan research "query" --profile china --advisor
guanlan compare "A" "B" --focus "price reputation risk" --limit 80 --format context
guanlan timeline "event latest progress" --limit 80 --format context
guanlan dossier "company or product" --focus "business reputation risk" --limit 80 --format context
guanlan read "https://example.com/article" --quality-report
guanlan hotnews today --limit 80 --trends
guanlan feeds curated --limit 80
guanlan archive ingest-research "query" --limit 80
guanlan archive context "query" --limit 20
guanlan doctor --trace
```

## Agent Workflow Rule

Do not reduce Guanlan to a single generic `search` call.

- `2-step`: `search -> read` when results are already usable and you only need to verify a representative original page.
- `3-step`: `route -> research -> scoped search` for normal research tasks or when quality signals are not yet strong enough.
- `4-step`: add `hotnews` for recent/hot tasks, `feeds` for tech/AI/developer tasks, or `compare/timeline/dossier` when source diversity is too narrow.

Only fall back to generic `web_search` / `web_fetch` after the appropriate Guanlan workflow has been completed and still lacks key evidence.

## Safety Notes

Guanlan is not a stealth crawler and not an account automation framework. It is read-first, low-disturbance, source-aware, and explicit about authentication. Public sources are preferred. Cookie, browser, Keychain, and login-state access must be requested by the user. Guanlan does not post, comment, like, follow, or send messages automatically.
