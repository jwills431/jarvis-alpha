# Server build progress — resume note

Working note from the dedicated-server build session, 2026-07-24 (~3 AM stop),
updated 2026-07-25 (Qwen + GPU smoke test PASS ~65.7 tok/s; whisper.cpp STT on CPU
~0.65 s/clip; Fish neural TTS wired into JARVIS with the cloned voice, 114 tests
green), and 2026-07-26 (Step 7 server-ify code landed: TLS, HTTP Basic auth, the
LAN-bind interlock, and browser audio streaming; 132 tests green), and
**2026-07-29/30 (full stack brought up on the server + interactive voice testing
over loopback; Fish voice-tuning panel, TTS pipelining, and low-latency Fish
audio streaming added; 136 tests green)**. Next: on-device LAN mic (RDP mic
redirection) + more voice-quality tuning.
Companion to `JARVIS_SERVER_PLAN.md` and `PC_FISH_SESSION.md`. This is the context
bridge for the next session — it does not carry over automatically.

## This machine (the dedicated JARVIS server)

- Ryzen 7 7800X3D / RTX 3060 12 GB (Gigabyte Gaming OC) / 64 GB DDR5 / 4 TB NVMe.
- Fresh Windows 11. Set up headless via RDP/SSH.
- Ubuntu username inside WSL: `jaydubya`. Machine name: `GUItech-CORE`.

## DONE this session

1. **Windows env confirmed.** git installed (2.55). `nvidia-smi` on Windows sees the
   3060 (driver 610.62, CUDA UMD 13.3, 12288 MiB).
2. **Repo cloned** to `D:\Claude Projects\JARVIS AI Assistant` (this connected folder).
3. **WSL2 + Ubuntu 26.04 LTS ("resolute")** installed (`wsl --install`, no reboot
   needed). `nvidia-smi` works INSIDE Ubuntu — GPU passthrough confirmed.
4. **Fish (OpenAudio S1-mini) installed + benchmarked — GO.**
   - Location: `~/jarvis/fish-speech` (Linux fs, per the recipe).
   - Pinned to commit `d3df505` on branch `s1-mini` (Apache-2.0 pure-S1 state).
   - `uv sync --extra cu128 --python 3.12`; torch `2.8.0+cu128`, `cuda.is_available()`
     = True. Never `uv run` — call `.venv/bin/python` directly.
   - Model downloaded via `hf` to `checkpoints/openaudio-s1-mini` (~3.6 GB, gated repo,
     agreed to terms + fine-grained token, login successful).
   - Warm benchmark with `--compile`: **~60-65 tok/s** (60.3 / 63.0 / 65.0). Voice
     clone from a reference clip sounded close. Matches the earlier 8 GB proof-of-concept.
   - Resume Fish: `cd ~/jarvis/fish-speech && .venv/bin/python -m tools.run_webui --compile`
     then open http://127.0.0.1:7860.

## DONE — llama.cpp CUDA build (built successfully)

- Location: `~/jarvis/llama.cpp` (from `https://github.com/ggml-org/llama.cpp`).
- **CUDA toolkit 12.4** is installed (came from Ubuntu's `nvidia-cuda-toolkit` package —
  installed by accident but it's fine and supports the 3060). `nvcc` = release 12.4.
- **gcc gotcha (Ubuntu 26.04):** system default is **gcc-15**, which CUDA 12.4 rejects.
  Fix in place: `gcc-13`/`g++-13` installed; the CUDA build points at gcc-13.
- Configured with:
  `cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/gcc-13`
  (86 = the 3060's compute capability). Confirmed "Including CUDA backend", host
  compiler GNU 13.4.0. Harmless warnings: ccache/NCCL/OpenSSL not found (none matter —
  OpenSSL only affects llama.cpp's own server, and JARVIS handles TLS itself).
- **Compile OOM gotcha (SOLVED):** WSL2 caps Ubuntu RAM at ~32 GB (50% of 64). A full
  `-j` (16 jobs) compile of the CUDA files blew past 32 GB → OOM killer terminated it,
  and it even dropped the shell back to PowerShell once. Rebuilt at **`-j 4`** → success.
- **Built cleanly.** `build/bin` contains `llama-cli`, `llama-server`, and
  `libggml-cuda.so` (GPU backend). Rebuild/resume anytime with:
  `cd ~/jarvis/llama.cpp && cmake --build build --config Release -j 4`.
- Smoke-tested on GPU 2026-07-25 — PASS (see below).

## DONE — Qwen model + GPU smoke test (2026-07-25) — PASS

- **Model:** Qwen2.5-7B-Instruct, **Q4_K_M** GGUF (README baseline, Apache-2.0).
  Source: `bartowski/Qwen2.5-7B-Instruct-GGUF` (single file, ~4.68 GB, not gated).
  Saved to **`~/jarvis/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf`** (Linux fs).
- **GPU offload confirmed:** all transformer layers assigned to `CUDA0`
  (RTX 3060, ARCHS=860). VRAM at load ~6.0 GB via `llama-server` (headroom to spare
  on 12 GB). `llama-cli` alone showed ~7.5 GB with a 4096 KV cache.
- **Generation works.** `llama-server` `/completion` returned a coherent reply
  ("I am JARVIS, your personal artificial intelligence assistant, designed to
  provide information, manage tasks, and enhance your daily life.").
- **Speed (RTX 3060, Q4_K_M, -c 4096):** generation **~65.7 tok/s**, prompt
  processing **~332 tok/s**. Comfortably interactive.
- Reproduce the server + test:
  `./build/bin/llama-server -m ~/jarvis/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf -ngl 99 --host 127.0.0.1 --port 8080 -c 4096`
  then `curl -s http://127.0.0.1:8080/health` and POST to `/completion`.
- **Gotcha (this build, 10109):** `llama-cli` spins up server components and binds a
  port, so a one-shot `llama-cli ... -p "..." -n N` **hangs** instead of printing and
  exiting. Use **`llama-server` + HTTP** for testing (and it's what JARVIS wires to
  anyway). Its logs are block-buffered to stderr — redirect `2>file` and read the
  file rather than expecting live stdout.

## DONE — whisper.cpp STT on CPU (2026-07-25) — PASS

- **Pinned to the version JARVIS validated against:** whisper.cpp **v1.9.1
  (`f049fff`)** at `~/jarvis/whisper.cpp` (Linux fs). Built CPU-only
  (`cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j 8`).
  gcc-15 is fine here — the gcc-13 rule is CUDA-only, and this is a CPU build.
  Produced `build/bin/whisper-cli` (and `whisper-server`).
- **Models** in `~/jarvis/models/whisper/` (checksums match the docs exactly):
  - `ggml-base.en.bin` — 147,964,211 B, SHA-1 `137c40403d78fd54d454da0f9bd998f78703390c`
    (from `huggingface.co/ggerganov/whisper.cpp`).
  - `ggml-silero-v6.2.0.bin` (VAD) — 885,098 B, SHA-256
    `2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987`
    (from `huggingface.co/ggml-org/whisper-vad`; the repo's
    `models/download-vad-model.sh silero-v6.2.0` uses the same source).
- **Smoke test PASS.** Ran `samples/jfk.wav` with the *exact* flags `transcription.py`
  uses (incl. `--vad --suppress-nst --no-gpu`): clean transcript, **~0.65 s** for an
  11 s clip (RTF ~0.06) on the 7800X3D. CPU-only keeps VRAM free for the LLM + Fish.
- **Wiring note (for step 6):** JARVIS resolves relative whisper paths against the repo
  root but takes absolute paths as-is, so when the app runs on the server point
  `config.local.json` at these Linux-fs paths:
  ```json
  {
    "whisper_binary": "/home/jaydubya/jarvis/whisper.cpp/build/bin/whisper-cli",
    "whisper_model": "/home/jaydubya/jarvis/models/whisper/ggml-base.en.bin",
    "whisper_vad_model": "/home/jaydubya/jarvis/models/whisper/ggml-silero-v6.2.0.bin"
  }
  ```

## DONE — Fish (neural TTS) wired into JARVIS (2026-07-25) — PASS

Fish is now a third TTS engine in `jarvis/speech.py`, alongside `say` and `piper`.
Chosen shape: Fish runs as a **resident HTTP server** (its own `tools.api_server`),
exactly like the llama.cpp backend — not a stdin worker. This keeps the model
resident (no per-phrase cold start) and JARVIS talks to it over loopback HTTP with
pure stdlib (no msgpack/torch deps in the app).

- **Reference voice (the JARVIS clone).** Joseph's 24 s MCU J.A.R.V.I.S clip
  (`Reference Audio/…Good ...... sir..mp3`) was converted to mono 44.1 kHz WAV and
  staged as a Fish reference folder: `~/jarvis/fish-speech/references/jarvis/`
  containing `sample.wav` + `sample.lab` (the exact transcript). JARVIS passes only
  `reference_id: "jarvis"` — the reference audio never enters the app, and only reply
  text leaves the process (over loopback).
- **Server launch (run in the Fish venv, never `uv run`):**
  ```
  cd ~/jarvis/fish-speech && .venv/bin/python -m tools.api_server \
    --listen 127.0.0.1:8080 --half --compile \
    --llama-checkpoint-path checkpoints/openaudio-s1-mini \
    --decoder-checkpoint-path checkpoints/openaudio-s1-mini/codec.pth \
    --decoder-config-name modded_dac_vq
  ```
  Use **`--compile`** for production (~60 tok/s, first request pays a one-time
  compile). Without it, generation is ~6 tok/s. Health: `GET /v1/health` → 200.
- **JARVIS config (`config.local.json`)** to enable Fish on the server:
  ```json
  { "tts_engine": "fish", "fish_enabled": true,
    "fish_base_url": "http://127.0.0.1:8080", "fish_reference_id": "jarvis" }
  ```
  New `Config` fields: `fish_enabled`, `fish_base_url` (loopback-enforced),
  `fish_voice_name`, `fish_reference_id`, `fish_temperature/top_p/repetition_penalty/
  max_new_tokens`. `tts_engine` now accepts `"fish"`.
- **Code:** `_render_fish` POSTs JSON to `/v1/tts` and writes the returned WAV;
  `_speak_fish` mirrors `_speak_piper` (claim → render → `_play_audio`, with the same
  stop-race guard). Fish appears in `available_voices` tagged `engine:"fish"`, gated
  by `_fish_runtime_ready` (enabled + server healthy + afplay present).
- **Tests:** full suite green — **114 passing** (103 + 11 new Fish tests). Verified
  the real `speech._render_fish` against the live server (4.8 s clip). Sample outputs:
  `jarvis_voice_test.wav`, `jarvis_integration_test.wav` (repo root; safe to delete).
- **Known limitation (feeds step 7):** playback still uses macOS `afplay`, so audio
  plays on whatever host runs JARVIS. For the LAN model the reply audio must instead
  stream to the browser client — a change that affects `say`, `piper`, AND `fish`
  together, and belongs to the server-ify step below.

## DONE — Step 7 server-ify (code) (2026-07-26)

All in the JARVIS app (Python + static JS); no server-side model work. 132 tests
green (114 + 18 new). Files: `jarvis/config.py`, `jarvis/server.py`,
`jarvis/speech.py`, `static/app.js`, plus two setup scripts.

- **TLS.** `config.tls_cert` + `config.tls_key` (both-or-neither). When set, the
  app serves HTTPS — `JarvisServer.__init__` wraps the listening socket with an
  `ssl.SSLContext` (TLS 1.2+). A bad cert fails at startup, not mid-request.
  Generate one with **`scripts/make_tls_cert.sh <LAN-IP> [hostname]`** → writes
  `certs/jarvis.crt` + `certs/jarvis.key` (gitignored) with SANs for localhost +
  the LAN IP. `config.app_scheme`/`config.tls_enabled` are derived helpers.
- **Auth.** HTTP Basic over TLS. `auth_enabled`, `auth_username`,
  `auth_password_hash`, `auth_password_salt`, `auth_pbkdf2_iterations` (default
  200000). Only a PBKDF2-HMAC-SHA256 digest + salt are stored; `verify_password`
  compares in constant time (`hmac.compare_digest`), and the password hash is
  derived even on a wrong username to avoid a timing oracle. Every verb
  (`do_GET/POST/PATCH/DELETE`) calls `_require_auth`, which 401s with
  `WWW-Authenticate: Basic realm="JARVIS"`. Generate creds:
  **`python3 scripts/make_auth.py`** → prints the `auth_*` config block.
- **LAN-bind interlock.** `Config.validate()` now allows a non-loopback
  `app_host` (e.g. `0.0.0.0`) **only** when TLS **and** auth are both configured;
  otherwise it raises, exactly as before. `llama_base_url` and `fish_base_url`
  stay loopback-enforced. `Config(app_host="0.0.0.0")` alone still fails (old
  guarantee preserved).
- **Browser audio.** New `config.tts_playback` = `"host"` (default; macOS
  `afplay`, unchanged) or `"browser"`. In browser mode `/api/speak` returns the
  rendered `audio/wav` bytes and the client plays them; `speech.render_audio()`
  renders say/piper/fish to WAV without host playback (`say -o … --file-format=WAVE`),
  and `_playback_ready()` drops the afplay requirement in browser mode so the
  headless server (no audio device) is still "ready". `/api/health` now reports
  `"playback"`. Frontend (`static/app.js`) plays the WAV via a blob-URL `<audio>`
  queued through the existing `speechQueue` promise chain, stops it client-side,
  and shows "speaking on this device". CSP gained `media-src 'self' blob:`.
- **Verified together (loopback + TLS + auth):** real HTTPS handshake, 401 on
  missing/bad creds, 200 with valid creds, and a script-generated hash validated
  by `verify_password`.

### Resume commands (server-ify)

```sh
# 1. TLS cert for the server's LAN IP (writes certs/, gitignored)
scripts/make_tls_cert.sh 192.168.x.y guitech-core.local
# 2. Basic-auth credentials → paste the printed auth_* keys into config.local.json
python3 scripts/make_auth.py
# 3. config.local.json for LAN hosting:
#    { "app_host": "0.0.0.0", "app_port": 8787,
#      "tls_cert": "certs/jarvis.crt", "tls_key": "certs/jarvis.key",
#      "auth_enabled": true, "auth_username": "...", "auth_password_hash": "...",
#      "auth_password_salt": "...", "tts_playback": "browser",
#      "tts_engine": "fish", "fish_enabled": true, ... }
# 4. Windows firewall: allow the port inbound, scoped to your own devices only.
# 5. Start JARVIS; open https://<LAN-IP>:8787 from another device.
```

## DONE — full-stack bring-up + voice UX (2026-07-29/30)

First time the whole app ran on the server, plus a lot of voice-quality work. All
on **loopback** (`http://localhost:8787` in the RDP browser) — the LAN/HTTPS path
(Step 8) is still not exercised. 136 tests green.

- **Stack bring-up.** `config.local.json` created (loopback, `tts_engine:"fish"`,
  `fish_enabled`, `tts_playback:"browser"`, absolute whisper paths). llama.cpp
  (`run_backend.sh` with `JARVIS_MODEL_PATH`/`JARVIS_LLAMA_SERVER`/`JARVIS_GPU_LAYERS=99`)
  + `python3 -m jarvis.server` + Fish `tools.api_server --compile` all run detached
  in WSL. **Gotcha:** launch each with `setsid` AND keep the launching shell alive
  a few seconds (health-wait or `sleep`), or WSL reaps the backgrounded child before
  it establishes. Turnkey scripts delivered: **`start_jarvis.ps1`** / **`stop_jarvis.ps1`**
  (repo root; pipe a bash launcher into `wsl` over stdin to dodge quoting).
- **Server stability RESOLVED (provisionally).** The recurring hard resets were
  **4×16GB DDR5 @ 6200 MT/s (EXPO) on the 7800X3D** — 4 DIMMs is too much for the
  memory controller at that speed. Owner dropped to **5000 MT/s**; survived a CPU+RAM
  soak, the full Qwen+Fish load, and hours of testing with zero resets. See the
  `jarvis-server-instability` memory. BIOS is still the old 2613 (2024-04) — worth
  updating for more margin.
- **Lean checklist (partial):** High-Performance power plan + never-sleep set;
  `.wslconfig` = 52GB/16proc/16GB-swap (fixed the `-j` OOM, confirmed live);
  Windows Update active hours 5–23. OneDrive startup disabled. Defender exclusions
  + Logitech-startup disable are in `jarvis_server_tuning.ps1` on the Desktop (needs
  one admin run). The forced-reboot WU policy key is blocked by registry protection.
- **Fish voice-tuning panel.** `/api/speech/options` exposes `fish.parameters`
  (value+range); Speech panel shows live sliders for temperature/top_p/repetition_
  penalty/max_new_tokens when a Fish voice is selected; values persist per-browser
  and ride along on each `/api/speak(/stream)` as a `fish` object, validated
  server-side (`speech.resolve_fish_options` + `FISH_OPTION_BOUNDS`).
  **CRITICAL gotcha:** ranges MUST match Fish's own `ServeTTSRequest` schema —
  **temperature 0.1–1.0, top_p 0.1–1.0, repetition_penalty 0.9–2.0** (max_new_tokens
  effectively unbounded int). We first allowed temperature up to 2.0; a value >1.0
  made Fish 422 and `_render_fish` surfaced it as a silent "synthesis failed."
  Config/bounds/options/sliders are now all pinned to Fish's limits.
- **Latency + smoothness work (all in `static/app.js`):**
  - Autoplay unlock (silent WAV + AudioContext resume on first gesture) — fixed the
    first reply being silently swallowed by the browser autoplay policy.
  - Mid-reply cut-off fix: per-clip guards no longer gate on `speechReady` (which
    flaps when the Fish health probe times out under load) — only stop/mute/new-reply.
  - TTS pipelining: render the next sentence while the current plays.
  - **Fish streaming (the big win).** `/api/speak/stream` proxies Fish's
    `streaming:true` output — **raw headerless int16 PCM, mono, 44.1 kHz** — chunk by
    chunk (first byte ~2 ms vs ~2.5 s for a full render). Client (`streamFishSentence`)
    decodes PCM and schedules it on a shared Web Audio clock (`streamClock`) spanning
    all sentences of a reply, with generation pipelined ahead of playback → gapless
    between sentences. Opt-in toggle "Low-latency streaming" (default on for Fish);
    blob path kept as fallback. Lead-in trimmed to 600 ms (blob path only).
- **"Only the first sentence spoke" — ROOT-CAUSED + FIXED (2026-07-30).** Caught
  live via the Chrome-extension debugger: sentence 1 rendered 200, sentences 2–5
  got **422 on both `/api/speak/stream` and `/api/speak`, and Fish never saw them**
  (only health pings in its log). Cause: Fish's single-threaded event loop is
  BLOCKED while it generates a sentence, so the app's `/v1/health` probe times out
  and `_fish_server_healthy` cached Fish as *unavailable* for a few seconds — which
  dropped the Fish voice from `available_voices`, so `resolve_speech_options`/
  `voice_engine` rejected the next sentences' renders (422). A **busy** Fish was
  misread as a **down** Fish. Fix: **sticky health** in `speech.py` — a Fish that
  answered healthy within `FISH_HEALTH_GRACE` (45 s) is treated as "busy, still up"
  on a probe timeout (probe timeout also raised 1→2 s); only a sustained outage past
  the grace reports down. Verified: pre-fix 1/5 sentences spoke, post-fix 5/5.
  Regression test `test_fish_health_is_sticky_while_busy`; 137 tests green. (This
  same flap almost certainly explains the earlier "cut after (chainring)" report —
  that was a later sentence in its reply.)
- **Sentences cutting off mid-word — ROOT-CAUSED + FIXED (2026-07-30).** Symptom:
  a sentence stops mid-word and the next one starts immediately. NOT truncation —
  it was **overlap**. `streamTaskSettled` reset `streamClock = 0` on a timer when
  `pendingSpeech` was momentarily empty (which happens between sentences whenever
  Fish finishes generating before the LLM emits the next sentence). With the clock
  zeroed while ~10 s of audio was still queued, the next sentence scheduled at
  "now" and played **on top of** the still-speaking audio, drowning its tail. Fix:
  never zero `streamClock` there, and only return to idle once
  `streamClock <= currentTime` (a clock already in the past is handled naturally
  where the next sentence starts scheduling). Verified live: clock stayed 9–16 s
  ahead of playback throughout a 6-sentence reply, going negative only after all
  audio finished. Confirmed Fish itself is NOT truncating — the two reported
  sentences render fully (6.97 s / 11.47 s streamed ≈ their blob renders).
- **Gap after a SHORT sentence — FIXED by minimum-size chunking (2026-07-30).**
  Every TTS chunk pays a fixed **~1.8 s engine startup** (text encode + first
  tokens) before any of its audio arrives, so a chunk whose spoken audio is shorter
  than that drains the buffer and leaves an audible gap. "You're welcome!" = 15
  chars ≈ 0.8 s of speech → guaranteed gap before the next sentence. Fix in
  `speechBoundary`/`feedSpeech`: a sentence end that would yield fewer than
  `SPEECH_MIN_CHARS` (90 ≈ 4.7 s at the measured ~19 chars/s) is **skipped**, so
  short sentences merge forward into the next chunk. The first chunk of a reply
  uses `SPEECH_FIRST_MIN_CHARS` (50 ≈ 2.6 s — still > the 1.8 s startup) so speech
  starts promptly; the final chunk is exempt (nothing follows it, so no gap).
  `SPEECH_MAX_CHARS` (220) unchanged. Note the counter-intuitive part: chunking
  *smaller* (e.g. by word count) makes this WORSE — more boundaries, each paying
  the startup — so the lever is a minimum, not a maximum.
- **Why speech seems to start only after the reply finishes (measured, expected).**
  Text IS already streamed to TTS sentence-by-sentence (`feedSpeech`/`speechBoundary`
  split at sentence boundaries and queue each as it arrives). Measured on a
  6-sentence reply: sentences queued at t=538/741/1252/2070/2661/3377 ms, **LLM
  finished at 3420 ms**, but Fish's **first audio chunk only arrived at ~3.7 s**.
  The LLM is simply faster than Fish's first render. GPU contention makes it worse:
  first-chunk latency was **3.7 s while llama.cpp was generating vs ~1.8–2.0 s once
  it had finished** (both share the RTX 3060). So the gap is Fish render speed under
  contention, not missing text streaming. Levers if it matters later: smaller/faster
  TTS for the first sentence, splitting the first sentence at a comma to shorten the
  first render, or serialising LLM/TTS GPU use.

## Voice latency budget — measured (2026-07-30/31)

Measured end to end rather than guessed, from the moment the push-to-talk button
is released to the first spoken word:

| stage | cost | notes |
|---|---|---|
| upload of the clip | ~0.05 s | 16 kHz mono; a 5 s utterance is ~156 KB. Negligible even over wifi. |
| speech recognition | ~0.4 s | was ~0.6 s warm / ~0.9 s cold — see resident recognizer below |
| LLM to first sentence | ~0.5 s | Qwen is not the bottleneck |
| Fish to first audio | ~1.4 s | for a ~50-char first chunk |
| **total** | **~2.4 s** | the realistic floor on this hardware |

- **Resident speech recognizer (implemented).** `whisper-cli` was spawned per
  utterance, reloading the 148 MB model every time: transcription measured ~0.9 s
  **regardless of clip length** (3 s, 5 s and 11 s audio all ~0.9 s), which is the
  signature of fixed reload cost rather than compute. New optional
  `whisper_server_url` (loopback-enforced, empty = old behaviour) posts the clip
  to a resident `whisper-server` instead; the model stays loaded and no temp file
  is written. Measured 0.57 s → 0.36 s min on a warm cache (larger gain cold).
  Started by `start_jarvis.ps1` on :8088. Note: per-request VAD thresholds
  (the stricter conversation-mode threshold) do not apply on this path; the app's
  own `validate_speech_energy` gating still does.
- **Fish time-to-first-audio scales with text length** — 4 chars 0.85 s, 20 chars
  0.86 s, 58 chars 1.51 s, 128 chars 2.68 s. So there is a fixed ~0.85 s floor plus
  ~0.014 s per character. Importantly, full generation completes only ~0.2 s after
  the first audio arrives, i.e. Fish emits per segment rather than progressively —
  our streaming wins come from chunk pipelining, not intra-sentence streaming.
- **The first-chunk minimum is already near optimal.** Solving "next chunk must be
  ready before the current one finishes playing" with the measured constants gives
  a first chunk of **≥ ~44 characters** when the following chunk is ~90 chars.
  `SPEECH_FIRST_MIN_CHARS` is 50, just above the threshold — shrinking it would
  start speech slightly sooner at the cost of reintroducing a gap.
- **REJECTED (2026-07-31): hybrid Piper-then-Fish first chunk.** Rendering the
  first chunk with the much faster Piper voice would cut time-to-first-word, but
  the voice would change mid-reply. Joseph's call: the cloned JARVIS voice must
  stay consistent — a voice switch "ruins the experience". Do not re-propose.
  Remaining paths to lower latency are hardware (a GPU with more memory bandwidth
  would raise Fish's ~60 tok/s roughly in proportion) or a faster TTS model in the
  same voice — not mixing engines within a reply.

## DONE — Step 8: private-LAN hosting + on-device voice test (2026-07-31)

**The original goal of the whole server build is now working**: JARVIS is hosted
on GUItech-CORE and used from a phone over the LAN, with the phone's own mic and
speaker. Joseph confirmed the on-device voice test "worked much better".

- **Config** (`config.local.json`, gitignored): `app_host: "0.0.0.0"`,
  `tls_cert`/`tls_key` → `certs/`, `auth_*` from `scripts/make_auth.py`,
  `tts_playback: "browser"`. LAN IP **192.168.7.83**, host `guitech-core`.
- **Cert**: `scripts/make_tls_cert.sh 192.168.7.83 guitech-core` → SANs cover
  localhost, 127.0.0.1, ::1, the LAN IP and hostname. Valid to Nov 2028.
- **Firewall**: `jarvis_firewall_rule.ps1` (repo root, run as admin) allows
  inbound TCP 8787 **only** from `192.168.4.0/22` (the /22 subnet 192.168.7.83
  belongs to). Everything off-LAN is refused.
- **THE BLOCKER — WSL2 networking.** Binding `0.0.0.0` *inside WSL* binds the WSL
  VM's own network namespace, NOT the Windows LAN interface: Windows only
  auto-forwards *localhost*, so the LAN saw "connection actively refused" while
  the app was demonstrably listening. Fix: **`networkingMode=mirrored`** in
  `.wslconfig` (needs Win11 22621+; this box is 25H2/26200), plus
  `[experimental] hostAddressLoopback=true`. After `wsl --shutdown`, WSL reports
  the *same* IP as Windows (192.168.7.83) and LAN binds just work. Chosen over
  `netsh portproxy` because the WSL IP changes on most restarts, which would need
  re-creating the proxy on a 24/7 box.
- **iOS/WebKit auth gotcha.** The 401 challenge originally carried
  `charset="UTF-8"`; WebKit (every browser on iOS) then failed to show its login
  prompt and rendered the raw `{"error":"unauthorized"}` body instead. Simplified
  to `WWW-Authenticate: Basic realm="JARVIS"` and the prompt appears. Safari also
  refuses to proceed past a self-signed cert as readily as Firefox — to use
  Safari, install `certs/jarvis.crt` as a trusted profile (Settings → General →
  About → Certificate Trust Settings) rather than clicking through the warning.
- Verified: LAN TCP reachable, 401 without credentials and with a wrong password,
  cert presented correctly on the LAN address, llama + Fish still loopback-only.

## Server lean checklist — status (2026-07-31)

1. **Power plan** ✅ High Performance; sleep and hibernate never (display off ok).
2. **`.wslconfig`** ✅ `memory=52GB processors=16 swap=16GB autoMemoryReclaim=gradual`
   + `networkingMode=mirrored`. Fixed the llama.cpp `-j` OOM and the LAN bind.
3. **Windows Update** ⚠️ Active hours 5–23 + `NoAutoRebootWithLoggedOnUsers` are
   set by `jarvis_server_tuning.ps1` (admin). **Windows silently deleted this key
   once already** — if the box ever reboots unexpectedly, re-run that script.
4. **Startup trim** ✅ OneDrive (HKCU) and both Logitech Download Assistant entries
   (HKLM) disabled. Realtek audio + Defender tray intentionally left enabled.
5. **Defender exclusions** ✅/verify — the WSL disk
   (`%LOCALAPPDATA%\wsl\{78caa623-…}`, a 30.7 GB `ext4.vhdx`) and the project
   folder, applied by `jarvis_server_tuning.ps1`. Real-time protection stays ON.
6. **NVIDIA** ✅ Nothing to do: no GeForce Experience/overlay processes, ~1 GB idle
   VRAM, 42 °C idle.

`jarvis_server_tuning.ps1` is idempotent — re-run it any time to verify or repair
items 3–5.

## STILL TO DO

- **Run `jarvis_server_tuning.ps1` as admin** to close out lean-checklist items 3–5
  (Windows Update active hours + no forced reboot; verify Defender exclusions).
- **BIOS update** (ASUS TUF A620M-PLUS, still on 2613 / 2024-04) for additional AM5
  memory-stability margin. RAM currently 5000 MT/s and stable — see
  `jarvis-server-instability` memory before touching memory settings.
- **Considering a newer GPU** (Joseph, 2026-07-31 — not decided). Fish generation is
  memory-bandwidth bound at ~60 tok/s on the 3060 (~360 GB/s), so a ~700 GB/s card
  would roughly halve time-to-first-audio (~1.4 s → ~0.8 s) and a ~1 TB/s card a bit
  more. Caveats: there is a fixed ~0.85 s floor in Fish that does not scale with the
  GPU; extra VRAM would also remove LLM/TTS contention (measured ~1.9 s penalty on
  the first render) and allow a larger LLM. Realistic whole-trip effect ~2.4 s → ~1.7 s.
- **Mic in an RDP session (informational).** RDP has no microphone unless the *client*
  enables it: mstsc → Local Resources → Remote audio → Settings → "Record from this
  computer" → reconnect. Server side already allows it (`fDisableAudioCapture=0`).
  Largely moot now that voice runs from a LAN device's own browser.

## Design boundary change — loopback-only → private LAN host (2026-07-25)

JARVIS was originally designed **loopback-only** (no LAN/remote/telemetry — see
`README.md` "Safety boundary"). That is changing deliberately. The new concept:
JARVIS is **hosted on this dedicated local machine and used privately over the home
network** (for now). This makes the "server-ify" work (item 7) a first-class goal,
not an optional maybe.

- **DONE (2026-07-26): reconciled `README.md`.** The safety-boundary bullets now
  describe loopback-by-default with opt-in private-LAN hosting behind the TLS +
  auth interlock, and a new "Private-LAN hosting (optional)" section documents the
  cert/auth/bind/firewall/browser-audio steps. `config.example.json` gained the
  `tls_*`, `auth_*`, and `tts_playback` keys (blank/host defaults, still copyable).
- **Future idea (not yet designed): remote access from a phone.** Joseph is
  considering a bridge — e.g. a **Discord bot** (or similar) — so he can talk to
  JARVIS from his cell phone off the home network. If pursued, design for it
  explicitly: it would move reply text off the LAN to a third-party service, so
  decide the privacy trade-off, auth model, and which data leaves the box before
  building. Keep it opt-in and separable from the core local app.

## Standing gotchas (do not rediscover)

- Python **3.12** for Fish (3.13 fails: no numpy 1.26.4 wheel).
- **Never `uv run`** — swaps CUDA torch for CPU torch. Use `.venv/bin/python`.
- Fish pinned to **`d3df505`** (branch `s1-mini`); main has moved to S2 (restrictive).
- Keep Fish code + venv on the **Linux fs (~/)**, not `/mnt/...`.
- S1-mini is a **gated HF repo** — must be logged in + "Agree and access repository".
- CUDA 12.4 needs **gcc <= 13** as host compiler; Ubuntu 26.04 default is gcc-15.
- WSL2 RAM cap ~32 GB → build llama.cpp CUDA with **`-j 4`**, not full `-j`.

## Server optimization / lean-and-efficient checklist (do next session, one at a time)

Goal: maximum, stable resource utilization for the AI on a 24/7 headless box. All
high-impact + low-risk. Walk through with the user; most are a few clicks + one file.

1. **Power settings (most important for always-on).** Power plan = High Performance;
   set sleep = Never and hibernate = Off (display-off is fine). A headless server that
   sleeps drops RDP/SSH. `powercfg` or Settings > System > Power.
2. **`.wslconfig` — give WSL a real budget (also prevents the OOM we hit).** Create
   `C:\Users\<user>\.wslconfig`. Starting point (64 GB machine, leave ~12 GB for Windows):
   ```
   [wsl2]
   memory=52GB
   processors=16
   swap=16GB
   autoMemoryReclaim=gradual
   ```
   Apply with `wsl --shutdown` then reopen. This is the lever for a bigger LLM via the
   64 GB. (After this, llama.cpp could build at higher `-j`.)
3. **Windows Update reboots.** Set active hours / pause auto-restart so it can't reboot
   mid-task. Critical for always-on.
4. **Trim startup + background bloat.** Disable startup apps not needed on a server
   (OneDrive, Edge preload, Xbox/Game Bar, Widgets, Cortana, background apps). Frees
   RAM/CPU, no downside headless. Task Manager > Startup; Settings > Apps > Startup.
5. **Windows Defender exclusions.** Exclude the WSL/project folders from real-time
   scanning to speed compiles + model loads. (Docs noted Avast caused trouble before —
   keep Defender, just tuned.) Settings > Privacy & security > Virus & threat protection
   > Manage settings > Exclusions.
6. **NVIDIA housekeeping.** Skip GeForce Experience/overlays; watch idle VRAM (desktop
   currently holds ~1 GB of the 12).

**AVOID:** aggressive online "debloat" scripts — they can break Windows Update or WSL.
The six items above capture almost all the safe benefit.

## Cautions (unchanged)

- The Fish "JARVIS" voice clones a real actor — fine for private offline use; do NOT
  distribute the cloned voice.
- License for JARVIS itself still unchosen. Fish weights CC-BY-NC-SA-4.0 (non-commercial)
  at the pin; Piper GPL-3.0. Flag before the repo goes public/commercial.
- Big model/build files (llama.cpp build, Qwen, whisper) are gitignored — they live only
  on this machine and must be rebuilt/redownloaded here with CUDA.
