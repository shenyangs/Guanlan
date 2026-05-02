# Guanlan Benchmark Notes

This document records how Guanlan evaluates whether it is becoming a better Chinese web research substrate for agents, not merely a larger bundle of commands.

## Two Layers

| Layer | Command | Network | Purpose |
| --- | --- | --- | --- |
| Deterministic contract gate | `guanlan eval benchmark` | No | Checks routing intent, source scope, evidence roles, and result-pool floors. This is release-gate material. |
| Live/manual task pool | `guanlan eval tasks --format jsonl` | Optional | Provides realistic Chinese research tasks for comparing ordinary search, `guanlan search`, and `guanlan route + research`. |

The deterministic gate is intentionally conservative. It proves that the tool still knows where to look before any external site is contacted. The live/manual layer is where maintainers can verify real source freshness, body extraction quality, and whether Guanlan reduces agent hallucination in messy public-web conditions.

## Current Task Pool

The first public task pool contains 40 tasks across eight categories:

| Category | Count | What It Tests |
| --- | ---: | --- |
| `policy` | 5 | Official-source priority and policy wording boundaries. |
| `local` | 5 | Local government and local official-media source routing. |
| `ecommerce` | 5 | Vertical media, platform announcements, and industry context. |
| `tech` | 5 | Developer-community and source-code oriented evidence. |
| `reputation` | 5 | User-sample routing and sample-bias caveats. |
| `hot` | 5 | Recent trend and hotnews observation paths. |
| `academic` | 5 | Database, publisher, conference, and institution distinction. |
| `local_llm` | 5 | Evidence packets for local models without native web access. |

## Suggested Live Comparison

For each task, compare three outputs:

1. Ordinary web search or the agent's built-in search.
2. `guanlan search "..." --profile china --limit 50 --trace`.
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
guanlan quality live-smoke --limit 5
```

`quality live-smoke` is deliberately optional. It is useful for seeing live network or upstream-source wobble, but the default release gate remains deterministic so a transient RSS timeout does not block an otherwise safe release.

## Public Reports

- [v0.3.7 benchmark and workflow report](benchmark-report-v0.3.7.md): records the first benchmark plan that includes compare/timeline/dossier, search-quality v2, read-quality summaries, and local-LLM workflow checks.
