# Reliability gate

Date: July 18, 2026

## Acceptance evidence

- The foreground service remained active for more than eight hours while continuing to answer loopback health requests.
- Eight consecutive chat requests returned HTTP 200, emitted content, and ended with the expected SSE completion marker.
- Repeated requests completed in 0.31–0.57 seconds after the first request for the short controlled prompt.
- Ctrl-C stopped the application and model backend and released loopback ports 8787 and 8081.
- An immediate restart initially exposed a macOS socket-reuse defect in the application server.
- Enabling address reuse on the still-loopback-only application socket fixed the defect.
- After the fix, the model reloaded, application health returned `ready`, local speech recognition returned `ready`, and a post-restart streamed inference completed.
- A synthetic 11-turn live conversation crossed the configured 20-message boundary. Every turn returned content and an SSE completion marker, retained history stayed correctly alternating, and the final turn recalled a marker from retained recent context.
- Malformed/orphaned context received HTTP 400, followed immediately by a successful valid streamed request.
- A simulated backend connection failure raised the bounded application error, while incomplete browser streams now roll back the pending turn rather than contaminating later context.
- Page exit or loss of local speech readiness explicitly closes push-to-talk and Conversation-mode microphone resources; page exit also requests local speech output to stop.
- A five-turn reminder test exposed genuine multilingual Qwen generation drift: the response contained Han characters, no replacement/encoding characters, and llama.cpp reported no prompt truncation. This was model output, not context overflow or display corruption.
- Reminder/timer/alarm intent now receives a deterministic local capability refusal and never reaches `/api/chat`. A live browser reminder test confirmed the local response and absence of a model request.
- Unexpected non-English-script generation is counted and rejected independently in the proxy and browser before stream completion; the pending turn then follows the normal context rollback path.
- A reported long voice turn produced one HTTP 422 transcription response while application health remained ready; the previous generic error mapping did not retain enough metadata to determine whether Whisper exited unsuccessfully or its runtime check failed. Transcription timeout and process failure are now distinct, metadata-only server outcomes, and the browser retries the same in-memory WAV once only after a process/runtime failure.
- A later recall turn was complete and untruncated but took 38.37 seconds: 22.49 seconds to evaluate 1,579 prompt tokens and 15.88 seconds to generate 182 tokens. The rolling 20-message window had shifted, leaving too little common prefix for the default cache behavior.
- A matched synthetic boundary benchmark retained 19 messages. With default cache reuse disabled, the shifted request took 16.98 seconds and reevaluated 1,314 prompt tokens. With `--cache-reuse 64`, it took 1.78 seconds and reevaluated 46 prompt tokens; the response remained complete and untruncated.
- Message roles now carry proposal provenance without adding visible text to assistant messages. A live synthetic conflict test established 1984 in user text, proposed 1997 in assistant text, explicitly withheld approval, and correctly returned only 1984 on recall. A legacy-marker scrub prevents an already-leaked prefix from perpetuating through later context.
- Explicit spelling corrections are now extracted only from user-role messages and injected as bounded, in-memory exact-character constraints. Regression coverage ignores an assistant-invented spelling and preserves quoted punctuation and letter-by-letter user spellings.
- A precisely timed live interruption terminated only the verified llama-server process while a synthetic response was actively streaming. The isolated browser tab discarded partial output, displayed the safe incomplete-response message, re-enabled text input, stopped speech, and reported the model offline while the application process remained responsive.
- A clean foreground restart restored health automatically in the same tab. The next synthetic request returned exactly `RECOVERY OK`; because an unrolled failed user turn would have violated the alternating-history contract, this successful request also verifies that the interrupted turn was removed from retained context.
- A bounded sustained-generation soak completed four consecutive long synthetic responses in 166.5 seconds. All four streams emitted content and the completion marker, and health remained ready after every request. Request times were 41.47, 41.60, 41.57, and 41.83 seconds (mean 41.62 seconds; 0.35-second range).
- Intel CPU and GPU thermal-pressure counters were both `0` before and after the soak. The safe built-in `pmset` interface could not expose actual temperature or power readings on this host, so this is pressure/stability evidence, not a measured-temperature claim.
- A user-assisted physical sleep/wake test passed without refreshing the existing page or restarting the foreground service. Backend, STT, and TTS health returned ready; the existing UI re-enabled Send, push-to-talk, Conversation mode, and speech.
- Post-wake acceptance included an exact text response, one successful push-to-talk transcription/submission, one successful Conversation-mode turn with automatic listening resumption, and a spoken `Goodbye, JARVIS` shutdown. No pre-sleep partial turn or duplicate submission appeared.
- The first post-wake text turn took 15.80 seconds because the preceding synthetic soak had replaced the single llama.cpp cache slot: 15.39 seconds reevaluated 1,258 prompt tokens and only 0.41 seconds generated the six-token reply. This is a cold-context-switch cost caused by the test sequence, not failed wake recovery.
- The structured spoken-context run retained established facts but exposed unsolicited recap behavior on forward-moving turns. Metadata showed complete, untruncated responses and strong cache overlap, ruling out overflow or corrupted context. The response contract now requires silent use of history and prohibits recaps unless requested, necessary, or corrective.
- Tightening response focus exposed a model regression in the exact-spelling synthetic check: the model selected a prior assistant misspelling despite the internal user-spelling constraint. Direct exact-spelling recall is now deterministic and local, returning the most recent explicit user spelling without asking the model to choose between variants.
- After activation, the focused no-recap synthetic check, canon-provenance check, and deterministic exact-spelling check passed together. A user-assisted spoken follow-up then confirmed that JARVIS answered only the new forward-moving question without reiterating earlier discussion.
- The next spoken acceptance turn exposed an analysis/invention ambiguity: asked for an observation about a species with no established traits, JARVIS asserted advanced telekinetic abilities. A prompt-only correction passed synthetic checks but failed the same real-conversation retest. Source-bound requests now deterministically exclude assistant-authored history before generation, leaving user messages as the only evidence; unsupported observations must report insufficient established information, while invention requires an explicit generative request and proposal labeling.
- The final spoken recap initially reported that no facts were established. Source-bound user messages had been passed as consecutive user chat turns, a representation the local model did not reliably interpret as one evidence set, and `recap` itself was missing from the source-bound classifier. Earlier user-authored statements are now consolidated into one chronological JSON evidence record with a separately labeled current request; assistant content remains excluded.
- A light phone-to-desk impact was reported to produce the Whisper phrase `Thanks for watching!` despite no speech. This is consistent with a short impulse passing the existing active-window count and a common canned decode. The server now requires activity to span at least 200 ms and rejects that narrow video-outro transcript before chat submission.
- A computer notification chime subsequently decoded as the standalone phrase `Thank you`. Because such a chime can have a sustained envelope, waveform-only rejection is harder than impact rejection. A proposed standalone-courtesy transcript filter was rejected because genuine courtesy speech must remain usable; confidence/voice-activity discrimination is under review instead.
- With user approval, the whisper.cpp-supported Silero VAD v6.2.0 model was added locally and enabled before decoding. Push-to-talk retains the documented default 0.5 speech threshold; Conversation mode uses a calibrated 0.6 threshold after 0.5 allowed one of fourteen built-in macOS sounds through. Both retain the documented 250 ms minimum speech duration, and standalone courtesy transcripts remain valid.
- The user-assisted final recap then returned only established facts as expected. This completes the structured 12-stage spoken-context acceptance run, including correction precedence, exact invented-name spelling and natural speech, rejected-proposal exclusion, and established-only recap behavior.

## Context and memory contract

- Conversation context is in-memory and page-local; it is never persisted by the application.
- The recent window is limited to 20 messages, 12,000 total characters, and 8,000 characters per message.
- The browser trims only valid alternating user/assistant suffixes and never sends an orphaned assistant reply as the first message.
- The server independently enforces role alternation, count, per-message, total-character, request-size, and last-user constraints.
- A turn enters retained context only after the stream contains usable assistant text and the expected completion marker.
- The visible chat can be copied manually for recovery, but the clipboard export is not retained or read back by JARVIS and does not change the bounded context contract.
- Memory is a separate local JSON record. The Memory editor and deterministic `Remember...` / `Forget...` commands mutate it directly; Learn mode is an explicit raw-answer capture override.
- Default-on automatic memory applies a deterministic relevance gate and then the existing local model as a bounded classifier after successful turns. It stores exact user source text only, excludes assistant output, auto-saves only at 0.90+ confidence, and holds uncertain or conflicting items outside prompt context for review.
- Memory is bounded to 100 entries, 1,000 characters per entry, 20,000 entry characters, a 65,536-byte file, and 6,000 characters of newest-first model context.
- Corrupt, oversized, or schema-invalid memory fails closed and is not overwritten. Each successful mutation keeps one owner-readable rollback copy.

## Regression control

`ServerLifecycleTests.test_allows_immediate_loopback_restart` protects the socket-reuse setting. The current complete automated suite contains 80 Python tests plus browser-core command/history/capability/Learn/automatic-memory tests. The cache change is reversible with `JARVIS_CACHE_REUSE=0`; role-based provenance, consolidated source-bound evidence with assistant-history exclusion, the legacy-marker scrub, exact-spelling extraction/recall and word-pronunciation handling, installed-voice/rate validation, waveform/Silero-VAD/canned-transcript rejection, no-recap behavior, the analysis/invention boundary, and memory validation/persistence/curation/corruption handling have focused regression coverage.

## Remaining reliability work

- Observe the existing one-time transcription retry during a naturally occurring Whisper process/runtime failure; forced and unit-level failure paths pass.
- Observe a naturally occurring transient Whisper failure with the refreshed browser code. The failure classes and cleanup paths are deterministic-test covered, but the immediate browser retry has not yet been exercised against a real transient process failure.

These tests do not require a broader architecture. Background launch, automatic restart, and login persistence remain deliberately excluded until the user chooses the desired operating model.

The remaining physical procedures and pass criteria are defined in `docs/USER_ACCEPTANCE.md`.
