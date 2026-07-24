# Guanlan Benchmark Notes

This document records how Guanlan evaluates whether it is becoming a better Chinese web research substrate for agents, not merely a larger bundle of commands.

## Two Layers

| Layer | Command | Network | Purpose |
| --- | --- | --- | --- |
| Deterministic contract gate | `guanlan eval benchmark` | No | Checks routing intent, source scope, evidence roles, and result-pool floors. This is release-gate material. |
| Live/manual task pool | `guanlan eval tasks --format jsonl` | Optional | Provides realistic Chinese research tasks for comparing ordinary search, `guanlan search`, and `guanlan route + research`. |

The deterministic gate is intentionally conservative. It proves that the tool still knows where to look before any external site is contacted. The live/manual layer is where maintainers can verify real source freshness, body extraction quality, and whether Guanlan reduces agent hallucination in messy public-web conditions.

## Current Task Pool

The public live/manual report now locks 80 real-world tasks across eight categories:

| Category | Count | What It Tests |
| --- | ---: | --- |
| `policy` | 10 | Official-source priority and policy wording boundaries. |
| `local` | 10 | Local government and local official-media source routing. |
| `ecommerce` | 10 | Vertical media, platform announcements, and industry context. |
| `tech` | 10 | Developer-community, RSS, source-code, and docs-oriented evidence. |
| `academic` | 10 | Database, publisher, conference, and institution distinction. |
| `reputation` | 10 | User-sample routing and sample-bias caveats. |
| `hot` | 10 | Recent trend, hotnews, and time-window observation paths. |
| `local_llm` | 10 | Evidence packets and prompt-ready context for local models without native web access. |

## Suggested Live Comparison

For each task, compare three outputs:

1. Ordinary web search or the agent's built-in search.
2. `guanlan search "..." --profile china --limit 80 --trace`.
3. `guanlan route "..." --json` followed by `guanlan research "..." --profile china --limit 80 --advisor`.

Score each task on five simple signals:

| Signal | Pass Condition |
| --- | --- |
| Source family | The result hits the expected official/media/community/developer/source family. |
| Source identity | The answer preserves who said it, where, and under what platform boundary. |
| Evidence role | Official, user sample, media report, developer discussion, and trend signal are not mixed together. |
| Context depth | Candidate pool and selected evidence are broad enough for an agent to reason from. |
| Drift control | The result avoids stale, English-drift, SEO-only, or platform-homepage dominated evidence. |

## Commands

```bash
guanlan eval benchmark
guanlan eval tasks --format markdown
guanlan eval tasks --format jsonl > guanlan-benchmark-tasks.jsonl
guanlan eval suite run chinese-web-v1
guanlan eval suite run chinese-web-live --mode live
guanlan quality live-smoke --limit 5
```

`quality live-smoke` is deliberately optional. It is useful for seeing live network or upstream-source wobble, but the default release gate remains deterministic so a transient RSS timeout does not block an otherwise safe release.

## Public Reports

- [Current public quality report](benchmark-report.md): generated from deterministic benchmark, the 100-task eval suite, routing-regression inventory, quality gates, and explicit live/distribution boundaries. It is reproducible; it does not fabricate live-network scores.
- [v0.3.7 benchmark and workflow report](benchmark-report-v0.3.7.md): records the first benchmark plan that includes compare/timeline/dossier, search-quality v2, read-quality summaries, and local-LLM workflow checks.
