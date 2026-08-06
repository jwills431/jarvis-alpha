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

- `docs/CAPABILITIES_PLAN.md` — staged plan for giving JARVIS the ability to act.
- `docs/STAGE0_TOOL_LOOP.md` — Stage 0 tool-loop design + on-device checklist.
- `docs/STAGE1_TIMERS.md` — Stage 1 timers/reminders design + on-device checklist.
- `docs/SERVER_BUILD_PROGRESS.md` — newest, authoritative server resume note.
- `docs/HANDOFF.md` — Mac-side voice-engine work + the architecture fork.
- `docs/JARVIS_SERVER_PLAN.md`, `docs/PC_FISH_SESSION.md` — server plan + Fish setup.
- `docs/TTS.md` / `docs/TTS_PLAN.md` / `docs/VOICE.md` — voice engines & pipeline.
- `docs/MEMORY.md` — the app's own memory feature spec.
- `docs/RELIABILITY.md`, `docs/*_ACCEPTANCE.md` — lifecycle & on-device checklists.
