# Guanlan v0.3.7 Benchmark And Workflow Report

This report records the quality target for v0.3.7. It is intentionally modest: deterministic checks are release-blocking, while live checks remain advisory because public Chinese web sources can timeout, rate-limit, or change markup without a Guanlan code change.

## Scope

v0.3.7 focuses on six areas:

| Area | What Changed | Validation |
| --- | --- | --- |
| Research workflows | Added `compare`, `timeline`, and `dossier` as structured views over research packets. | Unit tests cover core builders, CLI, MCP, and HTTP surfaces. |
| Search quality v2 | `query_strategy` now exposes `time_window` and `search_quality_v2` for recency-bound tasks. | Webtools tests check recent reputation queries add fresh sample variants and time-window metadata. |
| Read quality | `read_quality_summary` now exposes low-quality counts, status counts, low-quality URLs, and recommendations. | Research packet tests check aggregate quality metadata remains present. |
| Local LLM bridge | Local-model docs now show workflow context for compare/timeline/dossier. | Documentation smoke via README/docs references. |
| Agent contract | Workflow output fields are documented as stable agent-facing contracts. | `docs/contract.md` updated. |
| Propagation clarity | README and website explain high-level workflows as “source-aware research products,” not just commands. | README/website review plus release gate. |

## Deterministic Gate

Run before release:

```bash
ruff check .
pytest -q
guanlan quality coverage
guanlan quality regression
guanlan quality robustness
guanlan eval benchmark
```

The important release promise is not “every live website succeeds.” The promise is that a new version should not silently shrink the default evidence pool, remove source identity, remove evidence roles, or hide read-quality boundaries from downstream agents.

## Live/Manual Matrix

For external testing, use at least these nine tasks:

| Category | Command | What To Inspect |
| --- | --- | --- |
| Policy | `guanlan research "新质生产力 政策 原文 最新" --preset policy --limit 80 --read-top 5` | Official sources, recency window, source/date boundaries. |
| Local | `guanlan timeline "低空经济 广东 政策 最新进展" --preset local --limit 80` | Dated local official/media events and undated evidence separation. |
| Ecommerce | `guanlan research "跨境电商 AI 工具 趋势" --preset ecommerce --limit 80 --read-top 5` | Vertical media and open-web fallback balance. |
| Reputation | `guanlan pulse "某产品 用户评价" --limit 80 --format context` | Sample caveats and tendency confidence. |
| Compare | `guanlan compare "LangGraph" "AutoGen" "CrewAI" --focus "中文资料 技术选型 社区反馈" --preset tech --limit 80` | Per-subject evidence breadth and fair missing-evidence wording. |
| Dossier | `guanlan dossier "某公司" --focus "业务 口碑 风险 近期动态" --limit 80 --read-top 5` | Section coverage, open questions, read quality summary. |
| Hotnews | `guanlan hotnews today --limit 80 --trends --brief` | Cross-source trend grouping and single-platform caveats. |
| Read | `guanlan read "URL" --quality-report --trace` | Main-body extraction, fallback path, and noise recommendations. |
| Local LLM | `guanlan prompt "最近 AI 眼镜 在中国市场有什么变化？" --profile china --style evidence` | Prompt includes evidence rules and source boundaries. |

## Scoring

Use a simple 0-2 score per task:

| Score | Meaning |
| --- | --- |
| 0 | Not usable: wrong route, no meaningful evidence, or output loses source boundaries. |
| 1 | Usable with caveats: enough material exists but freshness, read quality, or source diversity needs manual repair. |
| 2 | Agent-ready: broad enough evidence, source roles preserved, boundaries visible, and next steps clear. |

## Known Boundaries

- RSS and live hotnews can timeout; stale-cache metadata is acceptable if clearly marked.
- Social platforms remain best-effort or opt-in; Guanlan should not imply stable logged-in scraping.
- `timeline` extracts visible dates and should not claim complete chronology.
- `compare` depends on public evidence density for each subject; missing evidence must be shown, not hidden.
- `dossier` is an investigation skeleton, not a final report or factual verdict.
