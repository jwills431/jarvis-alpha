# Alpha status

## Confirmed working

- Pinned llama.cpp CPU runtime and Qwen2.5-7B-Instruct model load.
- Authenticated OpenAI-compatible backend on `127.0.0.1:8081`.
- JARVIS proxy/UI on `127.0.0.1:8787`.
- Streaming browser chat through the proxy.
- Hold-to-record browser audio capture with a clear listening indicator and 30-second cap.
- Local English transcription through whisper.cpp v1.9.1 and `base.en`.
- Local speech-segment validation through whisper.cpp's supported Silero VAD v6.2.0 model; no audio leaves the machine.
- Successful voice transcripts are submitted directly and shown as user chat messages without entering the text composer.
- Browser and server noise-floor gates reject quiet, steady fan-like, short impact-like, or shorter-than-0.3-second recordings before transcription; symbol-only, non-speech-caption, and narrowly identified canned non-speech transcripts are rejected after decoding, with no chat submission.
- Opt-in Conversation mode passed real office/fan-noise acceptance, automatically pauses through replies, resumes listening, and can be closed by fixed local voice phrases without submitting a chat turn.
- Assistant replies are spoken in ordered sentence or phrase chunks while generation continues through the local macOS `Daniel` voice at 190 WPM, with visible mute and stop controls.
- A visible Speech panel enumerates only English voices already installed by macOS, validates voice and 120–350 WPM rate choices on the server, and retains the preference in loopback-origin browser storage without changing OS settings or downloading a voice.
- Speech text is passed to `/usr/bin/say` through standard input and is not exposed in process arguments or temporary text files.
- CPU backend selection based on a measured CPU-versus-Metal comparison.
- More than eight hours of foreground uptime with continuing health responses.
- Eight consecutive streamed inference requests completed, followed by a clean shutdown, immediate restart, health recovery, and successful post-restart inference.
- A controlled live model-process interruption during synthetic streaming produced the safe UI failure state, discarded partial output and the failed context turn, preserved application responsiveness, and recovered to a successful exact response after a clean restart.
- Four consecutive long synthetic generations completed in 166.5 seconds with health preserved after every request, a 41.62-second mean, and only a 0.35-second timing range. Intel CPU and GPU thermal-pressure counters remained zero before and after; actual temperature telemetry was unavailable.
- Physical sleep/wake recovery passed without a page refresh or service restart: health, exact text, push-to-talk, spoken reply, Conversation-mode resumption, and voice-command shutdown all recovered successfully.
- The loopback application socket permits immediate reuse after shutdown so macOS socket cleanup does not block a restart.
- Generated local backend key with owner-only file permissions.
- No server-side prompt, response, or conversation persistence.
- General-purpose memory is available through a visible editor, deterministic text/voice commands, Learn mode, and default-on automatic local curation. It uses a bounded, owner-readable local JSON file, never derives entries from assistant output, and rejects common secret/credential categories.
- Automatic memory stores exact user source text only. High-confidence durable facts are immediately visible with Undo; uncertain or stable-key-conflicting items remain outside model context in a review queue until approved or rejected.
- Visibly opt-in Learn mode supports guided get-to-know-you interviews without model-driven profile extraction: each user answer is saved with the preceding question, reported immediately, and remains reviewable/editable in Memory. Clearing chat or reloading turns capture off without deleting saved answers.
- Saved memory is supplied to the model as authoritative user-authored data, including for source-bound recall, without converting memory text into instructions.
- Recent in-page context is bounded to 20 messages, 12,000 characters, and 8,000 characters per message; trimming preserves complete alternating user/assistant turns.
- Conversation roles provide creative-source provenance: assistant-role history is treated as proposal material, while recall is instructed to use only user-stated or explicitly user-approved facts. A synthetic conflict test returned the user-established year rather than the assistant-proposed year. Legacy visible provenance markers are scrubbed from retained context.
- Explicit user spelling statements are extracted deterministically from recent user-role messages and supplied as exact-character constraints; assistant-invented spellings are ignored. Invented proper names are prohibited unless the user requests suggestions.
- Direct exact-spelling recall is answered locally from the most recent explicit user spelling, preventing the model from selecting an assistant-created variant.
- Creative analysis is constrained to user-established or explicitly approved facts. For source-bound observation, analysis, inference, recall, recap, summary, established-fact, and canon requests, the server deterministically excludes assistant-authored history and consolidates earlier user messages into one chronological evidence record before generation. New story details require an explicit generative request and must remain labeled proposals until approved.
- Explicitly spelled all-uppercase names remain exact in visible chat but are converted to a word-like capitalization only in the local TTS input, preventing the system voice from treating an invented name as an acronym. Custom pronunciation aliases remain deferred.
- Rolling-context prompt-cache reuse is enabled at a conservative 64-token threshold. In the matched 19-message synthetic boundary test, the shifted request fell from 16.98 seconds to 1.78 seconds while remaining complete and untruncated.
- Failed or incomplete streamed generations are rolled back from internal context so the next request can recover cleanly.
- Reminder, timer, and alarm requests are handled locally with an explicit capability refusal; they never enter a scheduling workflow or reach the model while no alert tool exists.
- The English-only alpha rejects unexpected Han, Japanese, Korean, Cyrillic, or Arabic model-script drift in both proxy and browser layers; rejected turns are not retained in context.
- Browser streams omit backend paths, fingerprints, and timing metadata.
- An explicit **Copy chat** control formats the visible conversation locally and writes it to the clipboard only after a user click; JARVIS still does not persist transcripts.
- Request size, message roles, history, output length, and timeouts are bounded.
- Eighty Python tests, browser-core logic tests, Python/JavaScript compilation, shell syntax checks, HTTP health, authentication rejection, live inference, local sample transcription, and in-app browser interaction pass.
- An 11-turn live context test crossed the 20-message boundary with complete streams and retained recent context; malformed context rejection was followed immediately by a successful valid request.

## Deliberately excluded

- Wake word and always-on background activation.
- Semantic/vector retrieval, external tools, agents, desktop control, and home automation.
- LAN access, background launch agents, cloud fallback, and telemetry.
- Multi-user isolation and authentication for remote clients.

## Known limitations

- This is a single-user local alpha, not a security boundary against other processes running as the same macOS user.
- Client-side chat history exists in page memory until cleared or the tab closes.
- Conversation context remains a bounded recent window rather than a transcript archive or summarization system; older complete turns are discarded when message or character limits are reached. Explicit saved memories are a separate, user-controlled channel.
- Creative-source provenance is prompt-enforced within the conversation window. Project/canon memories can be durable, but assistant output is never curator source and ambiguous or conflicting user statements require review.
- Conversation history is instructed to remain silent working context; unsolicited recaps are prohibited. This remains model-enforced rather than a deterministic semantic output filter.
- Client-side audio samples exist in page memory only while recording/transcribing, including at most one immediate retry after a local transcription-process failure, and are not persisted by the application.
- STT currently assumes English and uses the speed-oriented `base.en` model.
- Assistant output is deliberately English-only. Requests for non-Latin-script output are rejected by the alpha safeguards rather than supported as translation.
- Noise-floor, minimum-activity-span, and transcript gates reduce ambience and impact-triggered hallucinations but cannot distinguish the user's voice from clearly audible background speech or music.
- Conversation mode uses browser-side amplitude detection rather than a trained VAD model. Its room-noise calibration and browser/server gates are deliberately stricter than push-to-talk, but thresholds may still need tuning for different rooms and microphones.
- TTS currently uses the installed macOS `Daniel` voice. The first audible output waits for a complete sentence or a roughly 220-character phrase boundary; it does not speak individual tokens.
- Exact spelling does not determine pronunciation for invented words. The current macOS voice may mispronounce them. A separate, user-approved pronunciation-alias feature is documented as an optional deferred enhancement and is not active in this alpha.
- The current model is capable but materially weaker than large hosted systems.
- The structured 12-stage real spoken-context run, sleep/wake, bounded sustained-generation stability, and thermal-pressure checks pass. Longer unstructured daily use remains appropriate alpha observation; actual temperature telemetry remains unavailable. Deterministic and live backend failure, rollback, and clean restart paths are covered.
- The backend health route is public on loopback; inference routes require the generated key.

## Current milestone

Automatic and explicit local memory is implemented and awaiting the short user-assisted acceptance in `docs/USER_ACCEPTANCE.md`. It covers preferences, people, projects/canon, environment/devices, terminology, and general facts rather than optimizing for a single project type. Semantic retrieval, wake-word activation, voice-quality replacement, and external tools remain separate future decisions.

## Pending acceptance

- Software context/recovery acceptance is complete for bounded text/API operation.
- Extended spoken-context, physical sleep/wake, controlled in-flight interruption, and bounded thermal-pressure/latency acceptance are complete.
- The optional local neural voice engine (Piper) is implemented and covered by source-only tests (engine selection, rate-to-length-scale mapping, standard-input synthesis, and rendered-audio playback). On-device audio acceptance on the target Mac — natural-voice quality, per-phrase playback latency, and interrupt/stop behavior through `afplay` — remains pending. The default built-in `say` engine is unchanged.
