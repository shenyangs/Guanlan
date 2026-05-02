# Guanlan anonymous telemetry

Guanlan sends privacy-preserving command/tool lifecycle events to the default
Guanlan telemetry collector. This is intended for aggregate usage and
concurrency metrics.

Telemetry never includes:

- queries
- URLs
- result content
- cookies, tokens, or keys
- local file paths
- raw configuration values

## Configure

```bash
guanlan status
```

To point Guanlan at a self-hosted collector:

```bash
guanlan configure telemetry-endpoint https://your-metrics.example/v1/events
guanlan configure telemetry on
```

Environment variables are also supported:

```bash
export GUANLAN_TELEMETRY_ENDPOINT=https://your-metrics.example/v1/events
export GUANLAN_TELEMETRY=1
```

To disable telemetry:

```bash
guanlan configure telemetry off
# or
export GUANLAN_TELEMETRY=0
```

`CI=true` disables telemetry by default unless `GUANLAN_TELEMETRY=1` is set.

## Event shape

Each CLI command or MCP tool call emits a best-effort `invocation_start` and
`invocation_end` event. Long-running calls also emit `invocation_heartbeat`
events so the collector can keep current concurrency accurate while the task is
still running:

```json
{
  "schema": 1,
  "event": "invocation_start",
  "install_id": "anonymous-uuid",
  "session_id": "uuid",
  "invocation_id": "uuid",
  "surface": "cli",
  "command": "search",
  "version": "0.2.7",
  "agent_kind": "codex",
  "agent_id": "anonymous-hash",
  "platform": "darwin",
  "python": "3.12",
  "ts": 1777700000000
}
```

Collector-side concurrency can be calculated from active `invocation_start`
events minus matching `invocation_end` events, with heartbeat-updated TTLs for
abandoned invocations.

`install_id` is the anonymous device/install identifier. `agent_id` is an
anonymous stable agent identifier: if `GUANLAN_AGENT_ID` is set, Guanlan hashes
that value before sending it; otherwise it falls back to one agent instance per
`install_id + agent_kind`.
