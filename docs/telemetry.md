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
  "version": "0.10.9",
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

## Time semantics and delayed delivery

The collector records both the client event time (`ts`) and its own receipt
time. Health cards such as 24-hour calls, duration, error rate, and unclosed
calls use the client event time, so an offline queue replay cannot be presented
as fresh usage. Receipt time is retained only for delivery-lag diagnostics.

Telemetry is best effort. The client and collector acknowledge but discard
lifecycle events older than seven days by default; this keeps historical local
queues from degrading current telemetry or delaying normal Guanlan commands.
The client limit can be adjusted with `GUANLAN_TELEMETRY_QUEUE_MAX_AGE_SECONDS`.

`install_id` is the anonymous device/install identifier. `agent_id` is an
anonymous stable agent identifier: if `GUANLAN_AGENT_ID` is set, Guanlan hashes
that value before sending it; otherwise it falls back to one agent instance per
`install_id + agent_kind`.

## Collector reliability model

The dashboard has separate liveness boundaries for lifecycle events, feedback,
and retention. A new collector keeps raw events as the audit log, but computes
retention from a durable compact model of anonymous first-active dates and
active dates. Historical events are backfilled in bounded, restart-safe batches;
until that replay is complete, the dashboard explicitly says `建立中` with
progress and does not show a partial retention rate as fact.

Health metrics use the latest complete snapshot. The collector exposes recent
event age and the separate latest-feedback receipt time, so a stale feedback
inbox cannot be mistaken for a stalled lifecycle pipeline. The collector does
not replace existing raw SQLite data during this migration.

## Search dissatisfaction feedback

For agent workflows, Guanlan can auto-submit diagnostic feedback when a search
or research run shows clear low-quality signals (for example backend failures,
low source-fit, or weak evidence mix). This record includes query text and
reason text and is sent to a dedicated endpoint (`/v1/feedback`) for quality
triage dashboards.

This pathway is intended for agent-side automation rather than end-user manual
submission.

Automatic feedback remains opt-in (`GUANLAN_AUTO_FEEDBACK=1` or the matching
local setting). Therefore an empty or old feedback inbox means no feedback was
submitted by an opted-in client; it is not by itself evidence that anonymous
lifecycle telemetry has stopped. The dashboard labels the latest receipt time
to make that distinction visible.
