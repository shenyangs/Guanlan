# CLAUDE.md

## Project

观澜 / Guanlan — CLI-first, read-first Chinese-web research substrate for AI agents.

Positioning: source router + webpage reader + hotnews/feeds observer + evidence packet builder + local archive/RAG bridge, with explicit authorization boundaries.

License: MIT | Current version: 0.5.10 | Stage: Alpha

## Durable Memory Surfaces

Before changing Agent behavior, MCP tools, workflows, browser-assisted evidence, benchmarks, or release automation, reread:

- `AGENTS.md`
- `docs/agent-playbook.md`
- `docs/agent-usage.md`
- `guanlan/skill/SKILL.md`

These files define how downstream agents should actually operate Guanlan.

## Development Commands

```bash
uv sync --all-extras --dev
uv run guanlan version
uv run ruff check guanlan tests
uv run pytest
scripts/pre_release_status.sh
```

Release-quality checks:

```bash
guanlan quality foundational
guanlan quality coverage
guanlan quality regression
guanlan quality robustness
guanlan quality backend-fixtures
guanlan eval benchmark
scripts/release_gate.sh
```

## Core Structure

- `guanlan/cli.py` — CLI entry point and command dispatch
- `guanlan/webtools.py` — public search/read/research orchestration
- `guanlan/router.py` — local intent routing and source-role planning
- `guanlan/source_registry.py` / `guanlan/source_packs.py` — source identity, roles, and curated packs
- `guanlan/browser_assist.py` — read-only browser-assisted evidence planning
- `guanlan/archive.py` — local SQLite archive, quality audit, RAG/Wiki export, browser-note ingest
- `guanlan/hotnews.py` / `guanlan/feeds.py` — hotnews, RSS, and trend observation
- `guanlan/integrations/mcp_server.py` — MCP integration
- `guanlan/skill/` — packaged Agent skill surfaces
- `docs/` — public docs and agent playbooks
- `tests/` — unit, contract, regression, robustness, CLI, MCP, and release smoke tests

## Conventions

- Python 3.10+.
- Commit subjects, changelog entries, and release notes are Chinese-first. Conventional prefixes such as `feat:` / `fix:` / `docs:` are fine.
- Keep code identifiers English, user-facing CLI/docs Chinese-first where appropriate.
- Do not shrink default result pools or remove agent-facing evidence metadata without an explicit migration note and tests.
- Treat route plans, source cards, risk tags, quality reports, trace, and archive metadata as downstream Agent contracts.
- Prefer graceful degradation over silent failure: blocked backend, WAF, captcha, dynamic shell, stale cache, partial salvage, and external fetch strategy must be visible.

## Safety Rules

- Public search/read/hotnews first; ask for authorization only when needed.
- Browser-assisted evidence is a supplementary visible-page workflow, not a default browser crawler.
- Visible-page browser assist may read only target-page visible content after user authorization.
- Cookie access requires a separate explicit authorization for the target platform, purpose, risk, and read-only scope.
- Do not read passwords, Keychain, browser databases, private messages, orders, admin pages, or unrelated personal data.
- Do not post, comment, like, follow, message, purchase, or submit forms.
- Do not implement default Playwright-profile, browser-cookie3, Keychain, or browser-storage scraping paths for browser assist.
- `guanlan configure --from-browser ...`, deep auth checks, and Cookie import flows need explicit user approval.

## Release Rules

- Version truth must match `pyproject.toml`, `guanlan/__init__.py`, tests, docs, and website version text when doing a versioned release.
- For ordinary no-version doc fixes, record meaningful behavior changes in `CHANGELOG.md` under `Unreleased`.
- Before release, run the full gate or explain exactly which checks were skipped and why.
- Never push a release if `scripts/pre_release_status.sh` reports unknown dirty files unless they are intentionally included.
