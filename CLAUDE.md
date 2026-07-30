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
  Next: LAN mic (RDP redirection) + Step 8 LAN test + more voice-quality tuning.
  Full resume note: `docs/SERVER_BUILD_PROGRESS.md`.

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

- `docs/SERVER_BUILD_PROGRESS.md` — newest, authoritative server resume note.
- `docs/HANDOFF.md` — Mac-side voice-engine work + the architecture fork.
- `docs/JARVIS_SERVER_PLAN.md`, `docs/PC_FISH_SESSION.md` — server plan + Fish setup.
- `docs/TTS.md` / `docs/TTS_PLAN.md` / `docs/VOICE.md` — voice engines & pipeline.
- `docs/MEMORY.md` — the app's own memory feature spec.
- `docs/RELIABILITY.md`, `docs/*_ACCEPTANCE.md` — lifecycle & on-device checklists.
