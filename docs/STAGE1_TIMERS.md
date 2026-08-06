# Stage 1 — clock, timers, reminders (implemented + verified on-device 2026-08-05)

**Verified on-device 2026-08-05:** a 1-minute timer, a bare "set a reminder for
<clock time>" alarm, and a "remind me to <task> at <time>" reminder all fired and
spoke correctly. Two fixes landed during verification: (1) `set_reminder` gained
an `at_time` argument (a clock string like "10:42 PM" the *server* resolves to the
next occurrence) and made its message optional — the model kept falling back to
`set_timer` because computing an ISO `fire_at` from `get_time` was too much
friction for a 7B, and a bare alarm had no valid message to supply; (2)
`restart_app.ps1` now ships the launcher to WSL as base64 rather than piping text,
because PowerShell re-adds CRLF when piping to a native process and bash choked on
the carriage returns.


Stage 1 of `docs/CAPABILITIES_PLAN.md`, built on the Stage 0 tool loop
(`docs/STAGE0_TOOL_LOOP.md`). Adds four tools alongside `get_time`:
`set_timer`, `set_reminder`, `list_timers`, `cancel_timer`. Gated by the same
`tools_enabled` flag — off by default.

Two design decisions Joseph made up front:
- **Auto-run, not gated.** set/cancel execute immediately and JARVIS confirms
  verbally (the tools are registered `side_effects=False`). This is a deliberate,
  timers-only deviation from the plan's "all side effects are proposed" line: a
  timer is low-risk and forcing an Approve click per timer breaks hands-free use.
  The confirmation gate stays intact and reserved for the risky later stages.
- **Relative + absolute times.** "in twenty minutes" and "at 6:30am" both work.
  The model converts natural language to a structured argument (a
  `duration_seconds`, or an ISO `fire_at`), calling `get_time` first when it needs
  today's date for an absolute time.

## Known limitation — 7B tool-calling reliability (expect occasional misses)

**Qwen2.5-7B occasionally fabricates a tool action instead of calling the tool.**
Observed 2026-08-05: asked to "set a timer for two minutes," the model replied
"I've set a timer… it will go off at 11:19 PM" as plain text **without emitting
any `set_timer` call** — the audit log and `data/timers.json` had no such timer,
so it would never have fired, and the stated time was invented (and wrong). Most
turns it calls tools correctly; this is an intermittent miss, and it even
contradicts the explicit "never claim you did it without calling the tool" rule.

This is the exact risk `docs/CAPABILITIES_PLAN.md` flagged for Stage 0: *"a 7B
model is competent but not reliable at multi-step tool use… expect to evaluate a
larger model."* **It will keep happening at some rate in this configuration.**

Mitigations applied (reduce the rate, do not eliminate it):
- `tool_temperature` (default **0.3**, separate from the conversational
  `temperature`) — a more deterministic model follows the tool protocol more
  reliably. Used only on tool-enabled turns (`backend.stream_chat_tools`).
- A stiffened system-prompt rule forbidding a confirmation or a fire time that
  did not come from an actual tool result.

The durable fix is a **more capable or tool-tuned model**, which ties to the open
GPU/VRAM decision — re-measure reliability after any model change. A possible
future app-side safety net: cross-check the store and warn when a reply claims a
timer that the audit log does not show.

## Architecture — why there is no scheduler thread

The server is headless; audio only exists in the browser. So a timer can only
*sound* when a tab is open, regardless of how firing is triggered. That makes
polling the natural design:

- **`jarvis/timers.py` — `TimerStore`**, a file-backed store at
  `data/timers.json`. The server owns the authoritative clock. `poll()` atomically
  transitions any pending timer whose `fire_at` has passed into `fired` and
  returns it **exactly once**.
- **`GET /api/timers`** (gated on `tools_enabled`) calls `poll()`, audit-logs each
  fire, and returns `{pending, fired}`.
- **The browser** polls that every ~4 s; for each `fired` it renders an ⏰ alert
  card and speaks it through the existing Fish path (one combined utterance if
  several fire together).

Because firing is derived from the wall clock at poll time, **a pending reminder
survives an app restart for free**: after a restart its `fire_at` is simply in the
past, so the next poll fires it. No background thread, nothing to re-arm.

The old client-side refusal (`unsupportedActionResponse`) and the system-prompt
"you cannot create timers" line are now suppressed when tools are on: the client
skips the refusal when `/api/health` reports `tools: ready`, and the server's tool
guidance explicitly tells the model to disregard the earlier statement. With tools
off, both still apply (timers genuinely don't exist).

## Tools

| tool | args | notes |
|---|---|---|
| `set_timer` | `duration_seconds` (int), `label?` | relative countdown |
| `set_reminder` | `message` + exactly one of `duration_seconds` / `fire_at` | `fire_at` is a local ISO datetime |
| `list_timers` | — | read-only |
| `cancel_timer` | `id?` or `label?` | cancels matching pending timers |

## Tests

`tests/test_timers.py` (store create/list/poll-fires-once/persistence-across-
instances/bounds/parse_fire_at/cancel, plus the tool handlers), an agent-loop
integration test in `tests/test_agent.py` (set_timer runs inline and persists),
and config validation in `tests/test_config.py`. **208 pytest + node green**, none
needing the GPU or model.

## On-device verification checklist (GUItech-CORE)

Tools are already enabled from Stage 0; only the app changed, so:

1. `.\restart_app.ps1` (llama already has `--jinja` from `start_jarvis.ps1 -Tools`).
2. **Relative timer:** "set a timer for 1 minute." Expect a `set_timer` card + a
   spoken confirmation; ~1 min later an ⏰ alert card appears and speaks.
3. **Relative reminder:** "remind me in 2 minutes to stretch" → fires and speaks
   "Reminder: stretch."
4. **Absolute:** "remind me at 6:30pm to call mum" → the model should call
   get_time, then set_reminder with a `fire_at`.
5. **List / cancel:** "what timers do I have?" then "cancel the stretch reminder."
6. **Persistence:** set a 3-minute timer, `.\restart_app.ps1`, keep a tab open —
   it still fires. Confirms restart survival.
7. Inspect `data/timers.json` and the `timer_fired` lines in
   `data/tool_audit.jsonl`.

Note: a browser tab must be open for an alert to sound (the browser is the only
audio device); firing latency is the ~4 s poll interval.
