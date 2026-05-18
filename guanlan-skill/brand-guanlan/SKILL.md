---
name: brand-guanlan
description: Install, update, verify, and use Guanlan for Chinese-web research by brand communications, PR, marketing, campaign, partnership, and reputation teams. Use when Codex needs to help an agent get the latest Guanlan CLI working, diagnose version/path drift, configure safe update checks, choose Guanlan commands for brand monitoring, campaign planning, media/reputation research, crisis tracking, competitor comparison, or create evidence-bound Chinese internet briefs for communications work.
---

# 品牌观澜

## Core Rule

Use Guanlan as a Chinese-web evidence router, not as a one-shot search box. For brand, PR, marketing, campaign, external relations, and reputation tasks, first make sure the running `guanlan` is current and then choose a workflow that separates official statements, media reporting, community samples, platform heat, and evidence gaps.

## Install Or Update

Prefer one clean install path. For most agents, use `uv`:

```bash
uv tool install --force --upgrade --refresh --default-index https://pypi.org/simple guanlan
hash -r || true
command -v guanlan
which -a guanlan
guanlan version
guanlan doctor --install-check
```

If the user explicitly wants Homebrew:

```bash
brew update
brew reinstall shenyangs/tap/guanlan
hash -r || true
which -a guanlan
guanlan version
```

If `guanlan version` is lower than public PyPI/Homebrew or README, stop before configuring MCP or using the tool. Report the exact executable path and version mismatch. Clear stale update cache when update checks claim an old version is latest:

```bash
rm -f ~/.guanlan/cache/update-check.json
curl -fsSL -H 'Cache-Control: no-cache' https://pypi.org/pypi/guanlan/json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["info"]["version"])'
python3 -m pip index versions guanlan --index-url https://pypi.org/simple
```

For a repeatable full install/update smoke, run:

```bash
bash scripts/install_or_update_guanlan.sh
```

Read [references/install-update.md](references/install-update.md) when a user reports version drift, stale PyPI, Homebrew lag, multiple `guanlan` paths, or a screenshot saying an old version is latest.

## Post-Update Smoke

After any install or update, run:

```bash
guanlan capabilities
guanlan doctor --install-check
guanlan doctor --trace
guanlan search "人工智能 政策" --profile china --limit 5 --trace
guanlan hotnews today --limit 5 --trends
```

Treat `--limit 5` as smoke only. For real communications research, rerun with `--limit 80`.

## Workflow Selection

Use this fast routing:

- Brand reputation, product perception, UGC sample: `guanlan research "品牌/产品 用户评价 口碑 风险" --preset reputation --limit 80 --advisor`
- Crisis or negative trend: `guanlan timeline "品牌/事件 最新进展" --limit 80 --format context`, plus `guanlan hotnews today --limit 80 --trends`
- Campaign planning or launch terrain: `guanlan research "品牌 活动 竞品 用户讨论 媒体报道" --profile china --limit 80 --advisor`, then read representative URLs.
- Competitor messaging: `guanlan compare "品牌A" "品牌B" --focus "传播声量 口碑 风险 卖点" --limit 80 --format context`
- Media / KOL / community mapping: `guanlan search "品牌 话题 媒体 报道 KOL 社区讨论" --profile china --limit 80 --trace`
- Daily pulse: `guanlan hotnews today --limit 80 --trends`, platform-specific hotnews when relevant, and `guanlan feeds curated --limit 80` for tech/AI/developer topics.
- Evidence identity explanation: `guanlan sources explain "品牌传播研究需求"`

Read [references/brand-comms-workflows.md](references/brand-comms-workflows.md) for detailed playbooks and answer frames.

## Evidence Discipline

Separate evidence roles in every final answer:

- `official`: brand, regulator, exchange, court, agency, or platform official sources.
- `media`: news, trade press, vertical media, industry commentary.
- `community_sample`: social posts, forums, reviews, fandom/user samples. Do not overclaim representativeness.
- `hot_signal`: hotlists and trends. Report as visible platform heat, not fact.
- `unknown/gap`: missing time, source identity, original statement, or sample bias.

For serious claims, read representative source URLs with `guanlan read "URL" --quality-report`. If `read` is weak or fallback-only, run `guanlan diagnose page "URL"` before citing it.

## Safety

Do not read cookies, tokens, keychains, browser databases, private messages, orders, admin pages, or unrelated personal data. Do not post, like, comment, follow, message, purchase, or submit forms. If browser-visible evidence is recommended, ask for explicit permission and read only the target page's visible content.

## Timeout Units

Outer tool budgets are seconds unless the host field explicitly says milliseconds. Convert explicitly for `timeout_ms`: 90 seconds = `90000`, 120 seconds = `120000`, 300 seconds = `300000`, 600 seconds = `600000`. Do not pass bare `timeout=120` to another agent without confirming the unit.
