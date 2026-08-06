# Stage 0 — the tool loop (implemented + verified on-device 2026-08-05)

Implements Stage 0 of `docs/CAPABILITIES_PLAN.md`: the propose → validate →
execute → feed-back loop, a tool registry, the confirmation gate, an audit log,
and one trivial read-only tool (`get_time`). Everything is **off by default**
(`tools_enabled: false`) — with tools disabled the chat path is byte-for-byte the
old direct-passthrough behaviour, so nothing regresses until it is turned on.

**Verified on-device 2026-08-05:** asked "what time is it?" on GUItech-CORE with
`tools_enabled: true` and llama-server on `--jinja` — the `get_time` card showed
in the transcript, the answer spoke cleanly, and `data/tool_audit.jsonl` recorded
the `executed` line. Two formatting refinements landed during verification:
`get_time`'s `spoken` field is US month-day-ordinal ("August 5th", so TTS says
"fifth", not "five"), and the timezone is omitted unless the caller sets the new
optional `with_timezone` argument (a 7B reads aloud any field it is handed, so the
zone is withheld rather than merely discouraged). The smoke-test steps below
remain valid for re-verifying after changes.

## What landed

- **`jarvis/config.py`** — new flags: `tools_enabled` (master switch, default
  false), `tool_grammar_enabled` (send the GBNF grammar alongside native tools,
  default false), `tool_max_iterations` (6), `tool_call_timeout_seconds` (20),
  `tool_audit_path` (`data/tool_audit.jsonl`, must be under `data/`).
- **`jarvis/tools.py`** — `Tool`, `ToolRegistry`, a stdlib JSON-schema argument
  validator (the guarantee a malformed call never executes), a JSON-schema→GBNF
  grammar generator, the append-only audit log, and the `get_time` built-in.
- **`jarvis/agent.py`** — the loop as a generator of SSE-ready bytes, plus
  `PendingActions` (bounded, TTL'd store of paused side-effecting calls) and the
  `resume()` path for approve/deny.
- **`jarvis/backend.py`** — `stream_chat_tools()`: streams a tool-aware
  completion, forwarding prose token-by-token (so the Fish/TTS pipeline is
  untouched) and accumulating tool-call deltas; accepts both streamed `delta`
  fragments and a single `message` frame.
- **`jarvis/server.py`** — `/api/chat` routes through the agent when tools are
  active; new `POST /api/tools/<id>/approve` and `/deny`; registry + pending
  store built once on the server; tool guidance appended to the system prompt
  only when tools are active.
- **Frontend** — `static/core.js` `parseStreamLine()` (unit-tested); `app.js`
  renders tool-result cards and an approve/deny card, and streams the
  continuation after a decision; `static/styles.css` tool-card styles.
- **`scripts/run_backend.sh`** — `--jinja` added, opt-in via
  `JARVIS_ENABLE_TOOLS=1`.
- **Tests** — `tests/test_tools.py`, `tests/test_agent.py`, additions to
  `tests/test_config.py` and `tests/test_core.js`. Full suite: **183 pytest +
  node**, all green, none needing the GPU or model.

## The streamed SSE protocol

Content keeps the OpenAI shape so existing parsing/TTS is unchanged:

    data: {"choices":[{"delta":{"content":"It is ten o'clock."},"finish_reason":null}]}

Tool activity rides in a top-level `jarvis` envelope (older parsers ignore it):

    data: {"jarvis":{"kind":"tool_result","id":"c1","name":"get_time","arguments":{},"status":"ok","result":{...}}}
    data: {"jarvis":{"kind":"tool_result","id":"c1","name":"get_time","arguments":{...},"status":"error","error":"..."}}
    data: {"jarvis":{"kind":"tool_proposal","id":"<action-id>","name":"set_timer","arguments":{...}}}

Every turn (including a paused proposal) ends with `data: [DONE]`.

## The confirmation gate

A read-only tool executes inline. A side-effecting tool is **not** run: the loop
emits a `tool_proposal`, stores a pending action, and ends the stream. The client
shows Approve/Deny and POSTs to `/api/tools/<id>/approve|deny`; the server
executes (or records a decline) and streams the continuation. Stage 0 ships no
side-effecting tool, so this path is exercised by unit tests now and will light
up for real with Stage 1's `set_timer`.

## On-device verification checklist (run on GUItech-CORE)

Pure Python/JS — **no rebuild** of llama.cpp/whisper/Fish needed. Pull the branch
on the server, then:

1. **Launch the LLM backend with `--jinja`.** Native tool-calling needs it:

       JARVIS_ENABLE_TOOLS=1 JARVIS_MODEL_PATH=~/jarvis/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
       JARVIS_LLAMA_SERVER=~/jarvis/llama.cpp/build/bin/llama-server \
       JARVIS_GPU_LAYERS=99 scripts/run_backend.sh

   (`start_jarvis.ps1` sets the model/server/GPU env already — add
   `JARVIS_ENABLE_TOOLS=1` to its backend launch line, or run the backend by
   hand as above.)

2. **Enable tools** in `config.local.json`: add `"tools_enabled": true`. Leave
   `tool_grammar_enabled` false for the first run.

3. **Start JARVIS** (`start_jarvis.ps1`) and open `https://…:8787`.

4. **Smoke test — get_time.** Ask “what time is it?” Expect: a grey tool card
   `✓ Tool · get_time` in the transcript, then a spoken/typed answer with the
   correct local time. This is the Stage 0 “done when”.

5. **Check the audit log:** `data/tool_audit.jsonl` should gain one `"executed"`
   line for `get_time` per call (plus `proposed/approved/denied/rejected/failed`
   as those occur).

6. **Malformed-call safety** is covered by `tests/test_agent.py`
   (`test_malformed_call_is_rejected_not_executed` et al.); no manual step. If
   the model ever emits a bad call live, the turn should degrade gracefully (an
   error tool card + a normal reply), never crash.

7. **Rollback:** set `"tools_enabled": false` (and drop `JARVIS_ENABLE_TOOLS`) →
   exact prior behaviour.

### If tool calls are not detected
- Confirm the backend was started with `--jinja` (step 1). Without it, llama.cpp
  will not parse Qwen's tool-call format and the model will only answer in prose.
- Confirm the llama.cpp build supports tools (recent builds do; this one is the
  July-2026 CUDA build).
- As a fallback, set `"tool_grammar_enabled": true` to also send a GBNF grammar
  generated from the tool schemas. Some builds reject a custom grammar alongside
  jinja tools — if enabling it breaks generation, turn it back off and rely on
  native tools + our schema validation.

## Notes / small follow-ups
- When tools are active, a turn's assistant bubble is created before streaming,
  so if the model calls a tool with no preamble the bubble is briefly empty above
  the tool card, then fills with the answer. Cosmetic; can be made lazy later.
- The reminder/timer refusal in `core.js`/`system.txt` is intentionally left in
  place — those tools arrive in Stage 1, which removes the refusal.
