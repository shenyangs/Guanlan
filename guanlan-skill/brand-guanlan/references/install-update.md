# Install And Update Playbook

Use this when Guanlan appears stale, multiple paths exist, PyPI/Homebrew disagree, or a user asks an agent to install/update Guanlan before doing communications research.

## Goal

End with a single command path that reports the public latest version and passes basic smoke checks. Do not configure MCP, optional channels, browser auth, or platform credentials until version/path checks are clean enough to trust.

## Latest Version Check

Prefer direct PyPI JSON through `curl`, because some Python installations have local certificate chain issues:

```bash
curl -sS https://pypi.org/pypi/guanlan/json | rg -o '"version":\s*"[0-9]+\.[0-9]+\.[0-9]+"' -m 1
```

If that fails, use Homebrew tap as a second public surface:

```bash
brew update
brew info shenyangs/tap/guanlan
```

If an app says "already latest" but shows an older version, suspect one of:

- the app is running a bundled or old `guanlan`;
- `~/.guanlan/cache/update-check.json` cached an older public version;
- `uv` reused an old index cache;
- Homebrew tap was not updated before reinstall;
- `PATH` calls `/Users/.../.local/bin/guanlan` while the user is looking at `/opt/homebrew/bin/guanlan`, or vice versa.

## Clean Update Commands

Default path:

```bash
rm -f ~/.guanlan/cache/update-check.json
uv tool install --force --upgrade --refresh --index-url https://pypi.org/simple guanlan
hash -r || true
command -v guanlan
which -a guanlan
guanlan version
guanlan doctor --install-check
```

Homebrew path:

```bash
brew update
brew reinstall shenyangs/tap/guanlan
hash -r || true
which -a guanlan
/opt/homebrew/bin/guanlan version
guanlan version
guanlan doctor --install-check
```

pipx path:

```bash
pipx install --force guanlan
hash -r || true
which -a guanlan
guanlan version
```

## Interpreting `doctor --install-check`

- `status=ok`: proceed to smoke checks.
- `status=warn` with multiple paths but all same version: safe enough to use; report current priority path.
- `status=fail` or stale paths: stop and fix before using Guanlan for research.
- Homebrew shadowed by `.local/bin`: not an error if both versions match. It means shell priority is not Homebrew.

## Post-Update Smoke

Run these after updating:

```bash
guanlan capabilities
guanlan doctor --trace
guanlan search "人工智能 政策" --profile china --limit 5 --trace
guanlan hotnews today --limit 5 --trends
```

Expected interpretation:

- `search --limit 5` may warn that it is only a smoke sample. That is healthy.
- Some optional channels may be `warn` or `off`; that does not block public search/read/hotnews.
- Network warnings are evidence about network/upstream state, not proof that the topic has no results.

## Timeout Budgets

Use 300-600 seconds for install/update workflows. If a host tool expects milliseconds, pass `300000` to `600000`, not bare `300` or `600`.
