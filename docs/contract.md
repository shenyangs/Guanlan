# Guanlan Agent Contract

This document records the fields Guanlan treats as stable for downstream agents, MCP clients, local HTTP clients, and RAG importers. Guanlan is still Alpha, so new fields may be added freely, but the fields below should not be removed, renamed, or silently narrowed without a changelog entry and release-gate update.

## Principles

- Keep output broad enough for agents: default research/search pools should not shrink below the documented limits.
- Preserve source identity: agents must be able to tell who said something, not only what was said.
- Preserve evidence roles: official, media, user-sample, developer, industry, and trend evidence should remain distinguishable.
- Preserve quality and boundary metadata: noisy reads, stale feeds, optional backends, and non-semantic archive search must be visible.
- Add fields rather than replacing fields when possible.

## Search Result Contract

`guanlan search` and MCP/HTTP search results should preserve these fields when available:

| Field | Purpose |
| --- | --- |
| `title` | Human-readable result title. |
| `url` | Canonical result URL used for source linking. |
| `snippet` | Search snippet or compact summary. |
| `domain` | Normalized source domain. |
| `source_type` | Guanlan source family, such as `政府/部委`, `党央媒`, `社交/内容平台`, `科技/开发者社区`. |
| `evidence_role` | Role in the evidence packet, such as `official_primary`, `authoritative_report`, `user_sample`, `developer_discussion`. |
| `source_card` | Structured source card where available: authority/sample/freshness/risk/content role signals. |
| `risk_tags` | Known caveats, such as sample bias, login wall, market volatility, or platform framing. |
| `score` / `rank` | Ranking signal exposed to agents. |
| `trace` | Optional explanation when `--trace` is used: backend order, cache status, route plan, query strategy, source diagnostics, recency. |

## Research Packet Contract

`guanlan research`, `guanlan prompt`, MCP research, and HTTP `/research` should preserve:

| Field | Purpose |
| --- | --- |
| `query` | Original user query. |
| `preset` | Research preset used by Guanlan. |
| `result_count` | Candidate pool size returned before final selection. |
| `route_plan` | Intent, preferred scopes, recommended sites, fallback range, caveats. |
| `query_strategy` | Query rewrites by evidence role. |
| `results` | Ranked broad candidate pool. |
| `selected_evidence` | Representative evidence selected for downstream reasoning. |
| `source_diagnosis` / `source_mix` | Source distribution, missing roles, and coverage hints when available. |
| `readings` | Optional full/partial reads of representative URLs. |
| `read_quality_summary` | Aggregate body quality and noise signal for readings. |
| `advisor` | Evidence-bound guidance when requested, not a claim about hidden user intent. |

## Archive Contract

`guanlan archive` is local-only and currently uses SQLite FTS/LIKE broad recall, not vector semantic search by default.

| Field | Purpose |
| --- | --- |
| `id` | Local archive row id. |
| `url` | Source URL. |
| `title` | Archived title. |
| `domain` | Source domain. |
| `excerpt` | Compact excerpt for prompt context. |
| `content_hash` | Local content hash for change detection. |
| `metadata.source_card` | Source identity and source-role metadata. |
| `metadata.read_quality` | Body quality signal. |
| `metadata.quality_report` | Noise/body-ratio/recommendation diagnostics. |
| `metadata.route_plan` | Route plan that led to the archived evidence when ingested through research. |
| `metadata.query_strategy` | Query rewrites used during research ingest when available. |
| `metadata.ingest_audit` | Ingest decision, reasons, matched terms, and quality score. |
| `search_trace` | Matched terms, hit fields, retrieval boundary, and `semantic=not-vector` when `--trace` is used. |
| `rag` | RAG-friendly export fields: `id`, `text`, `source`, `title`, `domain`, `source_type`, `topic`, `updated_at`. |

`guanlan archive stats --quality` should expose aggregate read-quality and RAG-readiness signals. `archive export --min-quality N` may filter noisy records for RAG import, but filtering is explicit and should not silently delete local archive rows.

## Hotnews And Feeds Contract

`hotnews` and `feeds` are public read-only discovery surfaces. They should preserve:

| Field | Purpose |
| --- | --- |
| `title` | Trend/feed item title. |
| `url` | Source URL when available. |
| `source_id` | Guanlan source id. |
| `source_name` | Human-readable source name. |
| `source_domain` / `domain` | Source domain where available. |
| `evidence_role` | Trend, media, reading-discovery, developer, or discussion signal role. |
| `risk_tags` | Caveats such as stale cache, sample bias, third-party aggregation. |
| `feed_status` | Fresh/cache/stale/error status for feeds. |
| `metrics` | Rank/heat/comment/count style metrics when a public source provides them. |

## MCP And HTTP Contract

MCP and HTTP surfaces should stay read-only. They may expose fewer formatting options than CLI, but should not remove the same evidence and boundary metadata from JSON payloads.

Stable MCP tools include:

- `guanlan_capabilities`
- `guanlan_search`
- `guanlan_route`
- `guanlan_read`
- `guanlan_research`
- `guanlan_pulse`
- `guanlan_hotnews`
- `guanlan_feeds`
- `guanlan_archive_search`
- `guanlan_status`

The local HTTP service defaults to `127.0.0.1`. If exposed beyond localhost, use `--token` or `GUANLAN_SERVE_TOKEN` and treat local archive contents as private user data.

Use `guanlan serve --print-token` to generate a local token without starting the service. `--token auto` may generate and print a token before starting; clients still authenticate with `Authorization: Bearer <token>` or `X-Guanlan-Token`.
