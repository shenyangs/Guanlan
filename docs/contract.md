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

When a backend is explicitly requested, it must still obey the same evidence-quality contract. If the batch is blocked, unsafe, low-relevance, or parser-drifted, Guanlan should return structured diagnostics such as `backend_diagnostics.status=low_relevance|unsafe_filtered|blocked|parser_miss` instead of passing polluted results to agents.

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

## Workflow Contract

`guanlan compare`, `guanlan timeline`, `guanlan dossier`, MCP workflow tools, and HTTP `/compare` `/timeline` `/dossier` are structured views over research evidence packets.

| Workflow | Stable Fields |
| --- | --- |
| `compare` | `mode`, `subjects`, `focus`, `subject_reports`, `comparison_table`, `shared_caveats`, `suggested_next`, `boundary`. |
| `timeline` | `mode`, `query`, `event_count`, `events`, `undated_evidence`, `source_diagnostics`, `route_plan`, `evidence_audit`, `boundary`. |
| `dossier` | `mode`, `entity`, `focus`, `query`, `source_mix`, `source_diagnostics`, `route_plan`, `read_quality_summary`, `sections`, `timeline`, `open_questions`, `suggested_next`, `boundary`. |

Workflow JSON should stay compact enough for agents: public payloads should not embed the full raw research packet unless an explicit future flag asks for it. Workflows may add new sections, but should keep source links, evidence roles, and boundary wording visible.

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

The local HTTP service exposes `GET /tools` as a read-only registry view so agents can verify the supported tool surface before calling `/search`, `/research`, `/hotnews`, `/feeds`, or `/archive/search`.

Stable MCP tools include:

- `guanlan_capabilities`
- `guanlan_search`
- `guanlan_route`
- `guanlan_read`
- `guanlan_research`
- `guanlan_compare`
- `guanlan_timeline`
- `guanlan_dossier`
- `guanlan_pulse`
- `guanlan_hotnews`
- `guanlan_feeds`
- `guanlan_archive_search`
- `guanlan_status`

The local HTTP service defaults to `127.0.0.1`. If exposed beyond localhost, use `--token` or `GUANLAN_SERVE_TOKEN` and treat local archive contents as private user data.

Use `guanlan serve --print-token` to generate a local token without starting the service. `--token auto` may generate and print a token before starting; clients still authenticate with `Authorization: Bearer <token>` or `X-Guanlan-Token`.


## 0.5.0 上层工作流新增字段

- `workflow_decision`: `tier`、`recommended_entrypoint`、`recommended_limit`、`recommended_read_top`、`do_not_overthink` 和 `fallback_policy`。
- `investigation`: `budget`、`dry_run`、`planned_steps`、`executed_steps`、`skipped_steps`、`limits`、`step_budget`、`timeout_budget_seconds`、`fallback_used`、`external_fetch_strategy`、`network_diagnosis`、`evidence_sufficiency` 和 `next_views`。
- `sources`: `source_id`、`domain`、`scope_id`、`authority_score`、`sample_value`、`freshness_value`、`risk_tags`、`content_roles`、`best_for`、`not_for` 和 `stability`；`sources audit` 额外保留 `summary/checks/boundary/suggested_next`。
- `eval_suite`: `suite`、`summary`、`category_summary`、`cases` 和每个 case 的 `workflow_decision` / `route` / `checks` / `failure_category`。
- `archive_semantic`: 显式语义侧车输出 `retrieval_mode=semantic`、`semantic_score` 和原有 `metadata/source_card/read_quality`；无侧车时不得破坏 FTS/LIKE 回退。
- `quality_performance`: `summary`、`checks` 和 `contract.metrics`，只做确定性性能护栏。

这些字段只新增，不替换既有 `search/research/read/archive` 核心字段。
