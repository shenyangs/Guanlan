# CLAUDE.md

## Project
观澜 / Guanlan — Python CLI + library for AI-agent search, reading, hotnews, and source routing across the Chinese web.
Positioning: CLI-first, read-first router with explicit authorization boundaries.
License: MIT | Version: 0.3.10

## Commands
- `pip install -e .` — Dev install
- `uv run pytest` — All tests
- `uv run pytest tests/test_cli.py` — CLI tests only
- `bash scripts/manual_integration_test.sh` — Manual local integration smoke
- `python -m guanlan.cli doctor` — Run diagnostics
- `python -m guanlan.cli install --env=auto` — Auto-configure

## Structure
- `guanlan/cli.py` — CLI entry point (argparse)
- `guanlan/core.py` — Core read/search routing logic
- `guanlan/config.py` — Config management (YAML, env vars)
- `guanlan/doctor.py` — Diagnostics engine
- `guanlan/channels/` — One file per platform (twitter.py, reddit.py, youtube.py, etc.)
- `guanlan/channels/base.py` — Base channel class (all channels inherit from this)
- `guanlan/integrations/mcp_server.py` — MCP server integration
- `guanlan/skill/` — OpenClaw skill files
- `guanlan/guides/` — Usage guides
- `tests/` — pytest tests
- `docs/examples/mcporter.json` — Example MCP tool config

## Conventions
- Python 3.10+ with type hints
- Each channel is a single file in `channels/`, inherits from `BaseChannel`
- Channel contract: must implement `can_handle(url)`, `read(url)`, `search(query)`, `check()` methods
- Use `loguru` for logging, `rich` for CLI output
- Commit format: `type(scope): message` (one commit = one thing)
- All upstream tool calls go through public API/CLI, never hack internals

## Rules
- NEVER modify upstream open source projects' source code
- 观澜 / Guanlan keeps platform access modular: route, read, diagnose, and degrade cleanly.
- Version in THREE places must match: `pyproject.toml`, `__init__.py`, `tests/test_cli.py`
- Always new branch for changes, PR to main, never push to main directly
- Run `pytest tests/ -v` before committing — all tests must pass
- Cookie-based auth (Twitter, XHS): use Cookie-Editor export method only, no QR scan
- XHS login: Cookie-Editor browser export only (QR will hang)
