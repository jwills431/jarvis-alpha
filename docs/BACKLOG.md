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
released when the speech goes idle, or after **20 s** regardless so a long reply
cannot swallow one (`shouldReleaseAlerts`, both pure and unit-tested in `core.js`).
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

---

## Later — evaluated, deliberately parked

### NVIDIA PAIR (Personal AI Router) — added 2026-09-10

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
