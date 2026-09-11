# Backlog — captured 2026-08-05, built 2026-08-23

Items Joseph flagged after the Stage 0/1 + alert-sounds session. **All four are
now implemented and covered by tests, but none has been confirmed on-device** —
the stack was down for this session, so everything below is verified only by the
suite (222 pytest + `tests/test_core.js`, all green on WSL). The on-device pass at
the bottom is the remaining work.

---

## 1. Non-speech audio transcribed as user input — DONE (code)

**Was:** the recognizer heard background noise, produced text from it, and JARVIS
answered a nonsense prompt.

**Cause, as suspected in the original note:** the VAD and non-speech suppression
flags were only ever passed on the `whisper-cli` path. Since Step 8 the server has
used the resident `whisper-server`, which got **none** of them — only
`validate_speech_energy` stood between noise and the model.

**Fix:** whisper.cpp v1.9.1's server accepts `vad`, `vad_threshold`,
`vad_min_speech_duration_ms` and `suppress_nst` as **per-request** multipart
fields (confirmed in `examples/server/server.cpp`, ~line 596 and the wiring at
~line 960). `_transcribe_via_server` now sends them, including the stricter
conversation-mode threshold — the CLI path's behaviour, per request.

**Coupling to know about:** `vad_model` is **launch-only**, so `start_jarvis.ps1`
now passes `--vad-model`. If whisper-server is ever started without it while
`whisper_vad_enabled` is true, every request fails. The two move together.

## 2. Alert lost when it fires mid-speech — DONE (code)

**Was:** `speakFiredTimers` bumped `speechRequestId` and reset `speechQueue`,
invalidating the utterance in flight — so an alert either cut the reply off or was
cut off by the next one. Either way it was gone, because the server hands each
fired timer over exactly once.

**Fix:** fired alerts go into a queue (`mergeFiredAlerts`, deduped by id) and are
released when the speech goes idle, or after a ceiling regardless so a stuck
speaking state cannot swallow one (**20 s** originally; raised to 120 s with speech
stopped first on 2026-09-10, after the 20 s ceiling split the sound from the words) (`shouldReleaseAlerts`, both pure and unit-tested in `core.js`).
The ⏰ card still appears the instant it fires.

## 3. Desktop panel of pending timers/reminders — DONE (code)

A **Timers** control appears in the header when the tool loop is on, opening a
dialog that mirrors the memory/speech panels. It reads the `pending` list the
timer poll was already fetching and throwing away, so it costs no extra requests.
Each row cancels through a new **`DELETE /api/timers/<id>`** — a thin route over
the same `TimerStore.cancel` the `cancel_timer` tool uses, audited identically.

**Desktop only**, as decided: the toggle is hidden under 700 px. Mobile and the
longer-term native app remain deferred.

## 4. Conversation Mode on entry + natural stop phrases — DONE (code)

**Entry:** pressing Initiate now schedules conversation mode rather than leaving
it for a second click. It cannot start inside that gesture — the greeting is
playing and `startConversation` stops speech in progress, so it would cut the
greeting off and open the mic onto JARVIS's own voice. It waits for the recognizer
to be up and the speech to finish, gives up after 30 s, and stands down if the user
touches anything first. Mic denial was already handled and still is.

**Stopping:** beyond the four fixed phrases, loose intent patterns match a stopping
verb near what is being stopped ("turn off conversation mode", "exit conversation
mode", "I need to go silent", "switch to text only", "close the microphone"),
guarded so a *question* about the feature ("how do I turn off conversation mode?")
is not treated as a request to use it. The fixed phrases keep their exact previous
behaviour — a false negative matters more than a false positive here.

---

## On-device pass (GUItech-CORE) — the remaining work

Everything above needs one run of the real stack. `.\start_jarvis.ps1 -Tools`
(**not** `restart_app.ps1` — whisper-server must restart to pick up `--vad-model`).
Hard-refresh the browser; assets are at `v=16`.

1. **VAD.** Check `/tmp/jarvis_whisper.log` shows the VAD model loading and no
   per-request errors. Then make the noise that used to trigger it — TV, music,
   a fan — and confirm nothing is transcribed. Then confirm ordinary speech still
   is, in both push-to-talk and conversation mode.
2. **Entry.** Press Initiate. The greeting should play *complete*, then the mic
   should open on its own. Deny mic permission once and confirm the graceful
   fallback still works.
3. **Stop phrases.** "Turn off conversation mode." Then restart it and try
   "I need to go silent for a bit." Then ask "how do I turn off conversation
   mode?" and confirm it does **not** stop.
4. **Alert queuing.** Set a timer for ~40 s, then ask a question with a long
   answer so JARVIS is mid-reply when it fires. The reply should finish, then the
   alert should sound and speak. Nothing lost, nothing cut off.
5. **Panel.** Set two timers, open **Timers**, confirm both appear with their fire
   times, cancel one, confirm it goes and does not fire, and check the
   `timer_cancelled` line in `data/tool_audit.jsonl`.
6. **Phone.** Confirm the Timers control is absent and nothing else regressed.

### Results of the first on-device run (2026-09-10)

1. **VAD — PASS** on the server (noise and music-only clips rejected, speech over
   music clean). The *browser* end-of-turn detector held the turn open with music at
   the mic → fixed with `conversationEndThreshold`. **Re-test (23:00): much better,
   not perfect** — 4 of 6 spoken turns ended ~1 s after speech (was: never, until the
   phone moved away); music-only pickups mostly 1–3 s and rejected. Two turns ran
   7–13 s long when the music got louder mid-turn — the limit of an energy detector.
   **Durable fix: a browser-side VAD** (e.g. Silero via onnxruntime-web, vendored —
   ~2 MB, needs a CSP review). Untested: music started *after* conversation mode is on.
4. **Alert queuing — PARTIAL.** Fired once, nothing lost, but the 20 s ceiling split
   the sound (mid-reply) from the words (after the reply) → fixed. **Re-test PASS
   (22:51):** a 1-minute timer fired mid-reply; sound and words came together once the
   reply finished (announcement 29 s after firing — past the old 20 s ceiling).
- **New: first word only after the text finished** — GPU sharing between
  llama-server and Fish (~2.4× slowdown) plus a long first chunk → fixed with
  `SPEECH_FIRST_MAX_CHARS`; **re-test**. Full detail in `CLAUDE.md`.
- **New: fabricated reminders, then refusals on qwen3.5** → claim guard, tool-aware
  prompt, stale-refusal history filter, bare/dotted/just-passed time handling. **PASS
  on-device (23:31):** a reminder set through PAIR fired on time, and a second alert
  waited out a long reply with sound and speech together. Detail in `CLAUDE.md`.
2. **Entry — PASS (23:40).** Initiate played the greeting in full, then the mic opened
   on its own; with mic permission denied it fell back to push-to-talk and text.
3. **Stop phrases — PASS.** "Turn off conversation mode" and "I need to go silent for a
   bit" both stopped it; "how do I turn off conversation mode?" did not.
5. **Timers panel — PASS (23:45).** Two timers listed with fire times; the 10-minute one
   cancelled from the panel (`timer_cancelled` audited, store status `cancelled`); the
   5-minute one fired on time at 23:50, and the cancelled one never fired (checked at
   23:56, past its 23:55:15 due time: no `timer_fired`, `fired_at` null).
6. **Phone — PASS.** Timers control hidden under 700 px; chat and voice worked.
- **Music started after conversation mode was on — interferes (23:46–23:50).** Music-only
  pickups were still rejected (1.2–1.8 s clips), but one recording was held open
  **19.3 s** and contained only **0.31 s** of VAD speech — and it still transcribed and
  went to chat as a turn. Another ran 8.7 s for 5.5 s of speech. The background level
  was measured before the music started, so the energy detector cannot tell it from
  speech. Durable fix: browser-side VAD (below). Possible stopgap: reject a turn whose
  VAD speech is a tiny share of a long clip (whisper-server's verbose_json segments
  would give the speech coverage), rather than raising the minimum speech length,
  which would cost short answers like "yes". **The false turn's transcript was "you"**
  — Whisper's stock output for non-speech — so a lone "you" is now rejected as a canned
  non-speech transcript (`transcription.CANNED_NON_SPEECH_TRANSCRIPTS`); "thank you"
  is still accepted. That stops this instance, not the detector problem behind it.

---

## Later — evaluated, deliberately parked

### NVIDIA PAIR (Personal AI Router) — added 2026-09-10

**Status update, same day: un-parked and in trial.** The "revisit when" condition
below turned out to be met already — the 3060 is shared by llama-server and Fish,
measured at a ~2.4× mutual slowdown — and Joseph has TOWER (4060 Ti) on PAIR.
Plan and decisions are in `CLAUDE.md` ("On-device pass + fixes (2026-09-10)").

**What it is:** NVIDIA's free, open-source (Apache-2.0) beta, released 2026-09-03.
It pairs machines on the LAN (mDNS discovery, PIN pairing, mTLS between nodes) and
exposes one local OpenAI/Ollama-compatible endpoint (default `127.0.0.1:11434`),
routing each request to **one** node running **Ollama or LM Studio**. It does not
pool VRAM, shard a model, or split a request. Hardware: RTX 20-series+, DGX Spark,
Apple M4+ (the old Intel iMac Pro does not qualify).
Repo: https://github.com/NVIDIA/Personal-AI-Router

**Why parked:** it only pays off when several *independent* requests run at once.
JARVIS makes one sequential LLM call per turn, on one GPU box. PAIR routes only the
LLM — not Fish or whisper — and adds a proxy hop plus the risk of landing on a slow
or cold node, which works against the ~1.2 s first-word budget.

**Revisit when either is true:**
- JARVIS gains **concurrent** LLM work — Stage 2+ fetching/summarising several
  pages at once, or subagents.
- The 3060's 12 GB gets **tight** (a bigger tool-tuned model + Fish) and a second
  supported GPU box is available to take the LLM. Note PAIR picks nodes itself, so
  pinning the model to one box means only loading it there — a direct URL may be
  simpler for that case.

**Integration touchpoints (estimated: ~½ day code, 1–2 sessions ops + re-verify):**
- `llama_base_url` → the PAIR endpoint. Still loopback, so the check in
  `config.py` passes; confirm WSL (mirrored networking) reaches a Windows-side PAIR
  at `127.0.0.1`, or install the Linux `.deb` inside WSL.
- `backend.health` probes llama-server's `/health`; Ollama has no such route.
- `config.model` must match an Ollama model tag (llama-server ignores it).
- The `grammar` field in `stream_chat_tools` is not honoured by Ollama — off by
  default, but the GBNF fallback is lost.
- Replace llama-server with Ollama: import the Qwen GGUF via a Modelfile, rework
  `start_jarvis.ps1` / `stop_jarvis.ps1` and the `-Tools` / `--jinja` path.
- **Re-verify Stage 0/1 on-device** — tool-call reliability was tuned against
  llama.cpp `--jinja`; Ollama's Qwen chat template differs. PAIR's docs don't say
  whether tool calls and streaming pass through the proxy — test that first.
- Re-measure the voice-latency budget.

**Cheap first experiment:** install PAIR and point a scratch config at it, leaving
the working llama-server setup untouched.
