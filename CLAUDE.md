# JARVIS Alpha — project instructions & context

A private, local conversational assistant (text + push-to-talk + spoken replies).
Loopback-only by design: no LAN, remote access, telemetry, wake word, or cloud
fallback. See `README.md` for the full feature/safety spec.

Cowork/Claude sessions do **not** carry over between conversations or machines.
The `docs/` notes below are the context bridge — read them before continuing work.

## Where things stand (as of 2026-07-24)

The project is mid-migration from the old **Intel iMac Pro** host to a new
**dedicated Windows 11 server**, so Fish (OpenAudio S1-mini) neural voice can run
on a real CUDA GPU. Core app + memory + Piper TTS work on the Mac; the server
brings up the GPU stack. This move also intentionally shifts JARVIS toward being
**hosted on the server and accessible over the LAN** — a deliberate change from the
original loopback-only design (so the "server-ify" step below is now a goal, not a
maybe). An earlier PC had an RTX 4060 Ti 8 GB; Joseph moved to this RTX 3060 12 GB
box for the extra VRAM and to host JARVIS on the network.

- **Mac side (done):** app, bounded local memory, voice I/O, and Piper (resident
  worker) all working. 103 Python tests + browser-core tests passing. Details in
  `docs/HANDOFF.md`, `docs/TTS.md`.
- **Server side (in progress):** WSL2 + Ubuntu, GPU passthrough, Fish benchmarked
  (~60–65 tok/s), llama.cpp CUDA build done, **Qwen2.5-7B-Instruct Q4_K_M + GPU smoke
  test PASSED** (~65.7 tok/s, ~6 GB VRAM), **whisper.cpp v1.9.1 STT built + tested
  on CPU** (`base.en` + Silero VAD, ~0.65 s per clip), and **Fish neural TTS wired
  into JARVIS** (resident HTTP server, cloned "JARVIS" voice via `reference_id`,
  114 tests green). **Step 7 server-ify code landed 2026-07-26** — TLS, HTTP Basic
  auth, the non-loopback LAN-bind interlock (LAN bind refused unless TLS+auth set),
  and browser audio streaming (`tts_playback: "browser"` → `/api/speak` returns the
  WAV, client plays it); helper scripts `make_tls_cert.sh` + `make_auth.py`; README
  reconciled; 132 tests green. **2026-07-29/30: full stack brought up on the server
  (loopback, `localhost:8787`) for interactive voice testing; added the Fish
  voice-tuning panel, TTS pipelining, and low-latency Fish audio streaming
  (`/api/speak/stream`, raw PCM → Web Audio); server instability fixed by dropping
  RAM 6200→5000 MT/s; `start_jarvis.ps1`/`stop_jarvis.ps1` added; 136 tests green.**
  **2026-07-31: Step 8 DONE — JARVIS is hosted on the LAN over HTTPS with Basic
  auth and used from a phone (its own mic + speaker); the on-device voice test
  passed.** Required `networkingMode=mirrored` in `.wslconfig` (a 0.0.0.0 bind
  inside WSL is invisible to the LAN otherwise). Also added a mobile layout,
  a resident whisper-server for STT, and a measured voice-latency budget (~2.4 s
  button-release → first word). Next: run `jarvis_server_tuning.ps1` as admin,
  then the BIOS update. Full resume note: `docs/SERVER_BUILD_PROGRESS.md`.

## Capabilities work (post-migration) — Stage 0 tool loop

The next chapter is `docs/CAPABILITIES_PLAN.md` (staged: tool loop → timers → web
→ files → machine control → integrations). **Stage 0 (the tool loop) is DONE —
implemented and verified on-device 2026-08-05.** It is gated behind
`tools_enabled` (default **false**), so with tools off the app is unchanged. New:
`jarvis/tools.py` (registry, schema validation, GBNF grammar, audit log,
`get_time`), `jarvis/agent.py` (the loop + confirmation gate + `PendingActions`),
`backend.stream_chat_tools`, `/api/tools/<id>/approve|deny`, and frontend tool
cards. 186 tests green (Python + node), none needing the GPU. Run the tool loop
with llama-server on `--jinja` (`.\start_jarvis.ps1 -Tools`) and
`tools_enabled: true`; iterate on app/tool code with `.\restart_app.ps1` (no Fish
re-warm). Full detail: `docs/STAGE0_TOOL_LOOP.md`.

**Stage 1 (clock/timers/reminders) is DONE — verified on-device 2026-08-05.**
Adds `set_timer`, `set_reminder`, `list_timers`, `cancel_timer` to the registry; a
file-backed `jarvis/timers.py` `TimerStore` (`data/timers.json`); `GET /api/timers`
(poll → atomically fire due timers → return once); and browser polling (~4 s) that
renders an ⏰ alert card and speaks it. Decisions: timers **auto-run** (not gated —
a deliberate timers-only deviation), and **relative + absolute** times both work.
`set_reminder` takes `at_time` (a clock string the server resolves to the next
occurrence) with an optional message — this was the key reliability fix; the model
would otherwise fall back to `set_timer` rather than compute an ISO time. No
scheduler thread — firing is wall-clock at poll time, so a pending timer survives a
restart for free. Iterate on app code with `.\restart_app.ps1` (ships its launcher
to WSL as base64 to dodge PowerShell/CRLF issues). 215 tests green.

**Known limitation (config-dependent):** Qwen-7B intermittently *claims* a tool
action without emitting the tool call (observed a fabricated "I set a timer" with
no `set_timer` in the audit log). Mitigated with a lower `tool_temperature`
(0.3) and a stiffened anti-fabrication prompt, but not eliminated — the durable
fix is a more capable/tool-tuned model (ties to the GPU decision). The audit log
is ground truth. See `docs/STAGE1_TIMERS.md` and the `jarvis-7b-toolcall-reliability`
memory.

**Timer/reminder alert sounds (shipped 2026-08-05):** a fired timer/reminder now
plays a synthesized Web-Audio alert (client-side, distinct sound per kind,
always audible even when voice is muted, then the spoken announcement) chosen
from a built-in set in the Speech settings panel; choice persists per-browser
(`jarvis.alert.timer`/`jarvis.alert.reminder`). Pure JS (`ALERT_SOUNDS` in
`app.js`, `resolveAlertSound` in `core.js`), no assets shipped.

**Planned next (Joseph's request, deferred to a future session):
server-side custom alert sound files** — upload your own audio to the JARVIS
server so a custom sound is shared across every device/browser. Chosen the
server-side (shared) option over browser-local. It's a bigger, more sensitive
build: a file-upload endpoint, on-disk storage (under `data/`), type/size
validation, serving with correct MIME, and a CSP update — do it as its own
focused pass. **Also next: Stage 2 (reading the web — the first egress,
prompt-injection defence).**

## Backlog refinements (2026-08-23) — built, not yet verified on-device

All four `docs/BACKLOG.md` items are implemented and green in the suite, but the
stack was down that session, so **none is confirmed on hardware**. The on-device
pass is written out at the bottom of `docs/BACKLOG.md` and is the next thing to do.

- **Speech gate on the resident recognizer.** The VAD/suppression flags only ever
  reached the `whisper-cli` path; the `whisper-server` the box actually uses got
  none of them. It now receives `vad`, `vad_threshold`,
  `vad_min_speech_duration_ms` and `suppress_nst` as per-request fields.
  **`start_jarvis.ps1` now passes `--vad-model`, which is launch-only — start the
  recognizer with it or every request fails.** Use `.\start_jarvis.ps1 -Tools`,
  not `restart_app.ps1`, the first time.
- **Fired alerts are queued**, released once the reply is completely finished (a
  2-minute ceiling is only a safety net), so an alert can no longer cut off a reply
  or be cut off by one (it was lost for good when that happened — the server hands
  each fired timer over exactly once). *Originally a 20 s ceiling — see 2026-09-10.*
- **A desktop Timers panel** listing pending timers/reminders with per-row cancel,
  through a new `DELETE /api/timers/<id>`. Hidden under 700 px by design.
- **Conversation mode starts after Initiate** (once the greeting finishes — it
  cannot start inside the gesture without cutting the greeting off), and can be
  ended in far more ways, guarded so a question about the feature is not a command.

**Test tooling now exists on this box.** WSL has `nodejs`, `python3-pytest` and
`python3-venv` (installed 2026-08-23). Run the full suite there:
`wsl -d Ubuntu -e bash -c "cd '/mnt/d/Claude Projects/JARVIS AI Assistant' && python3 -m pytest -q && node tests/test_core.js"` — **222 pytest + the node
suite, all green**. Windows Python also has pytest but skips 5 POSIX-only tests
(`%-I` was glibc-only and is now built by hand, so the rest run anywhere).

**Static assets are at `v=19`** — bump `?v=` in `static/index.html` whenever
`app.js`, `core.js`, or `styles.css` changes, or browsers serve stale copies.

## On-device pass + fixes (2026-09-10)

Stack brought up with `.\start_jarvis.ps1 -Tools` and tested over RDP. Results:

- **VAD on whisper-server: PASS.** Loads with `--vad-model`, no per-request errors;
  synthetic noise and music-only clips are rejected (`422 no_speech_detected`), and
  speech over music transcribed cleanly.
- **Timer + reminder: fire exactly once**, sound then spoken announcement.
- **Found 1 — conversation turn never ended with music at the mic.** The browser's
  end-of-turn threshold came only from the calibrated (quiet) floor. Fixed:
  `conversationEndThreshold` in `core.js` also measures the ~1.2 s of background just
  before speech. See `docs/CONVERSATION_MODE.md`.
- **Found 2 — alert sound split from its words.** The 20 s ceiling tripped during an
  ordinary long reply: the sound played mid-reply and the words queued behind audio
  already scheduled on the Web Audio clock (and bumping `speechRequestId` could drop
  unsent reply chunks). Fixed: `replyInProgress()` in `app.js` holds sound + words
  until text, rendering and playback are all done; ceiling now 120 s, and if it
  trips the speech is stopped first.
- **Found 3 — speech started only after the text finished.** Root cause, measured:
  **llama-server and Fish share the RTX 3060 and slow each other ~2.4×** — a
  153-char Fish render took 3.7 s alone vs **8.8 s during a generation** (llama fell
  to ~170 chars/s). The first speech chunk renders exactly then, and it was a whole
  110–150-char sentence, so first word came 6–9 s in. Fixed: `SPEECH_FIRST_MAX_CHARS`
  (80) — the first chunk breaks at a clause past 80 chars. Later chunks unchanged.
  On one GPU a very long reply may still pause briefly after the first phrase.
- **All three fixes are green in the suite (222 pytest + node) but need re-testing
  on-device.** Tests 2, 3, 5, 6 of the `docs/BACKLOG.md` pass were not yet run.

**PAIR is now being trialled to remove the GPU sharing** (see `docs/BACKLOG.md`).
Joseph's PAIR cluster: GUITECH-CORE (this box, 3060), GUITECH-TOWER (192.168.7.85,
4060 Ti — also the usual RDP client), GUITECH-MOBILE (3070 Laptop), and the Intel
iMac Pro (LM Studio can't install there — no Intel-Mac build; Ollama is CPU-only).
Decisions: route the LLM to **qwen3.5:9b on TOWER** via PAIR's loopback endpoint
`127.0.0.1:11434` (reachable from WSL); Ollama switched **off** on CORE and the iMac
in PAIR (PAIR's routing ignores GPU model, free VRAM and warmness, and cannot pin
a node); JARVIS to **fall back to local llama-server** when PAIR/TOWER is down;
`OLLAMA_KEEP_ALIVE` set on TOWER (PAIR is a user app, not a service — set a user
env var and restart PAIR + Ollama); Qwen 3.5 thinking must be off.

**PAIR trial results (measured from this box):** streaming ✅, tool calls ✅ (Ollama
delivers a call whole after ~3–4 s rather than in fragments), thinking off via
`reasoning_effort: "none"` ✅ (default spent a 400-token reply thinking, no answer).
Ollama's default loaded qwen3.5:9b with a **131k context → 11 GB, 45% on GPU, 11
tok/s**; at 4096 context it is 5.5 GB, 100% on GPU, **33 tok/s (~187 chars/s)**,
first token 0.1–0.3 s warm, cold load ~4 s. So TOWER has a Modelfile tag
**`jarvis-qwen3.5-9b`** (`FROM qwen3.5:9b` + `PARAMETER num_ctx 4096`) — it also
pins routing in practice, since only TOWER holds it. qwen3.5:4b ran 76 tok/s but
first word is Fish-bound either way, so 9b (better tool-caller) was chosen. The
real `agent.run` loop (`get_time` → result → answer) worked end-to-end through PAIR.

**Code landed (2026-09-10), off by default:** `pair_base_url` / `pair_model` /
`pair_reasoning_effort` / `pair_timeout_seconds` / `pair_retry_after_seconds` in
`config.py`; `backend.py` tries PAIR first and falls back to llama-server only when
PAIR fails **before any output** (never mid-reply), then skips PAIR for the retry
window; the llama-server API key is never sent to PAIR; `grammar` stays local;
`health` passes through PAIR if llama-server is down. `tests/test_pair_backend.py`,
237 pytest green. **To switch on:** add `"pair_base_url": "http://127.0.0.1:11434"`
and `"pair_model": "jarvis-qwen3.5-9b"` to `config.local.json`, `.\restart_app.ps1`.
Keep llama-server running — it is the fallback, and idle it costs VRAM, not speed.

**Keep-alive (do not re-derive):** `OLLAMA_KEEP_ALIVE` on TOWER did **not** take effect
(set + PAIR/Ollama restarted, still 5 min), and `keep_alive` on the OpenAI
`/v1/chat/completions` endpoint is ignored through PAIR. What works: Ollama's native
`POST /api/generate {"model", "keep_alive"}` with no prompt — 0.02 s through PAIR,
and the expiry **sticks** across later `/v1` requests until the model unloads (it
also loads the model if unloaded). So `backend.keep_pair_warm` sends it at app
startup and at most once a minute from `/api/health` (the page polls every 5 s),
with `pair_keep_alive` (default `"30m"`): warm while JARVIS is open, freed 30 min
after. A failed keep-alive marks PAIR down so the next turn goes straight to
llama-server. 243 pytest green.

**PAIR switched on in `config.local.json` (23:10, 2026-09-10)** — verified the
startup keep-alive reached TOWER (expiry = startup + 30 min). First-word timing on
PAIR still to be measured on-device.

**Fabricated reminders (found 23:01, 2026-09-10, still on Qwen2.5-7B):** asked for an
alarm at 11:02, JARVIS "set" one for 11:02 AM, then "corrected" it to PM — the audit
log and `data/timers.json` show **no tool call at all**; both confirmations were
invented. Fixes, 261 pytest green:
- `agent.claims_timer_action` + `_timer_tool_succeeded`: if the final answer claims a
  timer/reminder was set/cancelled and no timer tool succeeded in the turn, a spoken
  **"Correction: I didn't actually do that…"** is appended and an `unbacked_claim` is
  audited. Offers, questions and negatives are ignored.
- `timers.parse_clock_time`: a bare 1–12 hour ("11:02") is whichever AM/PM comes
  next (it was read as 24-hour → 11:02 AM tomorrow); a time that passed within
  `JUST_PASSED_SECONDS` (120) is refused with a message the model relays, instead of
  silently rolling to tomorrow night. Takes an optional `now` for tests.

**qwen3.5 refused alarms on PAIR (23:18, 2026-09-10) — fixed, 263 pytest green.**
Speech started sooner on PAIR, but JARVIS answered "I cannot set alarms… unavailable in
this alpha". Cause: `prompts/system.txt` (pre-tools) says "You currently have no
external tools" and "You cannot create reminders, timers, alarms…"; the tool guidance
only said "disregard that". Qwen2.5-7B obeyed the later line, qwen3.5 the earlier one.
Fixes in `server.py`: `TOOLLESS_PROMPT_REPLACEMENTS` *replaces* those sentences when
tools are on (a test asserts they still exist in the prompt file, so it cannot silently
stop matching); `_drop_stale_timer_refusals` removes earlier "can't set alarms"
exchanges from history (with two in history, qwen3.5 repeated the refusal verbatim);
guidance now says never add AM/PM the user didn't say (it had turned "11.1" into
"11:01 AM"); `parse_clock_time` accepts "11.20" (Whisper writes times with a dot).
Replayed through PAIR after the fix: stuck conversation → `set_reminder("11:55")` 2/2,
"11.50" → 11:50 PM tonight, "remind me at 11:58 to lock the door" → message kept.
**Verified on-device 23:28–23:31:** "11:28" at 11:28:45 PM was refused by the
just-passed guard (audited `failed`, relayed to the user); `set_reminder("11:31 PM")`
executed and **fired at 11:31 PM**. A second alert during a long reply showed its card
at once and held sound + speech until the reply finished. No `unbacked_claim` events.

**Music test result:** 4 of 6 spoken turns ended ~1 s after speech; music-only pickups
mostly 1–3 s and rejected. The two turns that ran 7–13 s long were when the music got
louder mid-turn — the energy detector's limit; the durable fix is a browser-side VAD
(backlog). Starting music *after* conversation mode is on is still untested. **Security, parked until PAIR is proven:** PAIR's
ollama/lmstudio proxies listen on all interfaces with firewall rules open to the
whole local subnet and no auth seen — scope them to Joseph's machines.

## Fish does not stream within a request (measured 2026-08-23)

Do not re-derive this. `streaming: true` on Fish's `/v1/tts` returns the WAV
header immediately and then **nothing until the whole request is synthesised**.
Measured here: an 880-character request producing 43 s of audio delivered its
first audio byte at **14.9 s**, complete at 15.6 s, in two bursts. `chunk_length`
(100/200/300) makes no useful difference, and `format: "pcm"` is rejected —
*"Streaming only supports WAV format"*. The per-segment yield path exists in
`fish_speech/inference_engine/__init__.py`, but the segments do not leave the
server early at this pin/config (`--compile` is a suspect; not chased down).

**Consequence:** splitting a reply into several requests is the *only* way to
speak before the whole thing is synthesised — the client-side chunking is not
overhead to remove, it is the mechanism. Two figures worth keeping:

- time to first audio ≈ **0.3 s + 0.0165 s per character**
- synthesis runs at about **2.8× realtime** (audio ≈ 0.049 s per character)

Because generation outruns playback nearly 3:1, only the **first** chunk affects
perceived latency. `SPEECH_CHUNK_RAMP` in `core.js` (30 → 60 → 120, then the
steady 90) exists for that: measured first word **2.3 s → 1.2 s, no gaps**. For
reference, llama-server generates at ~324 chars/s, so a short reply is fully
written before the first word is spoken — that is expected, not a fault.

## The dedicated server (this machine)

- Ryzen 7 7800X3D / **RTX 3060 12 GB** / 64 GB DDR5 / 4 TB NVMe. Fresh Windows 11,
  run headless via RDP/SSH. WSL Ubuntu user `jaydubya`, host `GUItech-CORE`.
- Repo is this connected folder: `D:\Claude Projects\JARVIS AI Assistant`.

## Standing gotchas (do not rediscover — from `docs/SERVER_BUILD_PROGRESS.md`)

- Fish needs **Python 3.12** (3.13 has no numpy 1.26.4 wheel). **Never `uv run`**
  (swaps CUDA torch for CPU torch) — call `.venv/bin/python` directly.
- Fish pinned to commit `d3df505` (branch `s1-mini`, Apache-2.0); main moved to S2.
  Keep Fish code + venv on the **Linux fs (`~/`)**, not `/mnt/...`. S1-mini is a
  **gated HF repo** (must be logged in + accept terms).
- CUDA 12.4 rejects gcc-15 (Ubuntu 26.04 default) → build llama.cpp with
  **gcc-13** as host compiler.
- WSL2 caps Ubuntu RAM at ~32 GB (50% of 64) → build llama.cpp CUDA at **`-j 4`**,
  not full `-j`, or the OOM killer terminates it. Fix long-term via `.wslconfig`
  (see the optimization checklist in `docs/SERVER_BUILD_PROGRESS.md`).
- Big build/model files (llama.cpp build, Qwen, whisper) are **gitignored** — they
  live only on this machine and must be rebuilt/redownloaded here with CUDA.

## Next actions (Step 5 remainder → 6–8)

1. ~~Download a ~7–8B Q4 Qwen GGUF, GPU smoke test.~~ ✅ Done 2026-07-25 (Q4_K_M,
   ~65.7 tok/s, ~6 GB VRAM; test via `llama-server` + HTTP, not `llama-cli`).
2. ~~whisper.cpp (STT) on CPU.~~ ✅ Done 2026-07-25 (v1.9.1 `f049fff`, `base.en` +
   Silero VAD in `~/jarvis/models/whisper/`, ~0.65 s/clip; CPU-only keeps VRAM free).
3. ~~Wire JARVIS to the local Fish worker.~~ ✅ Done 2026-07-25 (Fish as a resident
   HTTP server / `tools.api_server`; new `fish_*` config + `_render_fish`/`_speak_fish`
   in `speech.py`; cloned voice via `reference_id="jarvis"`; 114 tests green).
4. ~~Server-ify: HTTPS/TLS, bind web UI to LAN, basic auth, browser audio
   streaming.~~ ✅ Code done 2026-07-26 (config interlock + `server.py` auth/TLS +
   `speech.render_audio` + `static/app.js` browser queue; `scripts/make_tls_cert.sh`
   + `scripts/make_auth.py`; 132 tests green). Remaining on-device: add the Windows
   firewall rule scoped to Joseph's devices.
5. End-to-end voice test from another LAN device (over HTTPS, Fish reply plays on
   the client device). **← next** — must run on the server + a second device.
6. Server lean/efficiency checklist (power plan, `.wslconfig`, Windows Update,
   startup trim, Defender exclusions) — walk through one at a time.

## Open decisions / cautions

- **License still unchosen.** No license granted for JARVIS source. Fish weights
  are CC-BY-NC-SA-4.0 (non-commercial) at the pin; Piper is GPL-3.0. Settle before
  the repo goes public/commercial.
- The Fish "JARVIS" voice clones a real actor — private offline use only; do **not**
  distribute the cloned voice.
- `config.py`/`speech.py` assume a POSIX venv layout; revisit if JARVIS itself
  (not just Fish) moves onto Windows.

## Doc map

- `docs/BACKLOG.md` — to-review/refine items (noise-gate false triggers, alert
  queuing during speech, desktop timers panel, default conversation mode), plus
  parked ideas evaluated for later (NVIDIA PAIR inference router).
- `docs/CAPABILITIES_PLAN.md` — staged plan for giving JARVIS the ability to act.
- `docs/STAGE0_TOOL_LOOP.md` — Stage 0 tool-loop design + on-device checklist.
- `docs/STAGE1_TIMERS.md` — Stage 1 timers/reminders design + on-device checklist.
- `docs/SERVER_BUILD_PROGRESS.md` — newest, authoritative server resume note.
- `docs/HANDOFF.md` — Mac-side voice-engine work + the architecture fork.
- `docs/JARVIS_SERVER_PLAN.md`, `docs/PC_FISH_SESSION.md` — server plan + Fish setup.
- `docs/TTS.md` / `docs/TTS_PLAN.md` / `docs/VOICE.md` — voice engines & pipeline.
- `docs/MEMORY.md` — the app's own memory feature spec.
- `docs/RELIABILITY.md`, `docs/*_ACCEPTANCE.md` — lifecycle & on-device checklists.
