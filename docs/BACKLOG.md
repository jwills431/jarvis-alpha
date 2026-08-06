# Backlog — to review & refine (captured 2026-08-05)

Items Joseph flagged after the Stage 0/1 + alert-sounds session. Not started;
each has a problem statement, what already exists, and candidate directions to
discuss before building.

## 1. Non-speech audio is transcribed as user input

**Problem:** the recognizer sometimes hears background/non-speech audio, produces
text from it, and JARVIS responds to a nonsense prompt.

**What already exists** (`jarvis/transcription.py`):
- `validate_speech_energy()` — an RMS energy/activity gate, applied on **every**
  path, with stricter thresholds in conversation mode
  (`CONVERSATION_MIN_ACTIVE_WINDOWS`, `CONVERSATION_MIN_PEAK_TO_FLOOR_RATIO`).
- Silero **VAD** (`--vad`, `--vad-threshold`, conversation-specific threshold)
  and `NON_SPEECH_CAPTIONS` filtering ("music", "applause", "[BLANK_AUDIO]", …).
- **Likely root cause:** the VAD flags are only passed on the `whisper-cli`
  path. The **resident `whisper-server` path (which the server is currently
  using, `whisper_server_url` = :8088) does NOT apply Silero VAD or the stricter
  conversation threshold** — only `validate_speech_energy` gates it. This is
  already noted in `docs/SERVER_BUILD_PROGRESS.md`.

**Directions to explore:** enable VAD on the whisper-server path (server launch
flags or per-request params, if v1.9.1's server supports them); tighten the
energy-gate thresholds; reject low-confidence / `no_speech`-heavy results; or run
a lightweight VAD client-side before uploading the clip. Decide per-path vs a
single shared gate. Measure against real false-trigger clips.

## 2. Timer/reminder alert can be "lost" if it fires mid-speech

**Problem:** if JARVIS is speaking when a timer/reminder fires, the alert can
collide with or be swallowed by the in-progress reply and effectively be missed.

**What exists:** on fire the client plays the alert sound then speaks the
announcement (`announceFiredTimers` → `speakFiredTimers`), but `speakFiredTimers`
bumps `speechRequestId` and resets `speechQueue`, which can clobber / be clobbered
by current speech. The server returns each fired timer **exactly once**, so a
dropped client-side alert is gone.

**Directions:** hold fired alerts in a client-side queue and play the sound +
announcement only once current speech goes idle (chain onto `speechQueue` instead
of resetting it), so the alert is deferred rather than lost. Keep the ⏰ card
visible immediately regardless. Consider a max-defer so it still fires reasonably
promptly, and dedupe if multiple accumulate.

## 3. Desktop GUI panel listing existing timers/reminders

**Problem:** no at-a-glance view of pending timers/reminders; only voice
`list_timers`.

**What exists:** `GET /api/timers` already returns the pending list (with fire
times), and the client polls it every ~4 s. A Memory-panel-style dialog already
exists as a UI pattern to mirror.

**Directions:** a desktop-only panel showing pending timers/reminders with their
fire times and a cancel button each (reuse the poll data; cancel via a new
`DELETE /api/timers/<id>` or the existing tool). Explicitly **desktop/PC layout
first**; mobile layout deferred. Longer-term/back-burner: a **native mobile app**
instead of the browser — revisit once JARVIS is more fully functional.

## 4. Default to Conversation Mode on entry; natural "conversation off" triggers

**Problem:** after pressing **Initiate**, the app should drop straight into
Conversation Mode so you can just start talking. And turning it off should be
sayable naturally, not only via the button.

**What exists:** `isConversationStopCommand` (core.js) already matches "goodbye
jarvis", "stop listening", "end conversation"; there's a conversation-mode toggle
and start/stop plumbing. The Initiate press is a user gesture (also used to
unlock audio), so auto-starting the mic there is feasible.

**Directions:** auto-start Conversation Mode after Initiate once `voiceReady`
(handle mic-permission denial gracefully; confirm we *want* the mic live on
entry — it does mean listening immediately). Extend the stop-command matching to
natural phrasings like "turn off conversation mode", "Jarvis, I need to go silent
for a bit but keep going via text". Consider a matching approach robust to
transcription variation (keyword/intent rather than exact strings), and a spoken
confirmation when switching to text-only.
