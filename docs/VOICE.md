# Push-to-talk voice input

## Baseline

- Runtime: whisper.cpp v1.9.1, commit `f049fff`.
- Model: English `base.en`, approximately 142 MiB.
- Model SHA-1: `137c40403d78fd54d454da0f9bd998f78703390c`.
- Execution: CPU with Apple Accelerate; GPU explicitly disabled.

## Use

1. Hold **Hold to talk**.
2. Approve microphone permission on first use.
3. Speak while the button says **Listening**.
4. Release within 30 seconds.
5. The recognized speech appears as your chat message and is submitted automatically.

If the recording is too short or does not contain sustained speech-level energy, the page reports **No speech detected. Nothing was submitted.**

Shift+Enter still inserts a newline. Text chat remains usable if microphone access or transcription fails.

If the local Whisper process fails, the browser keeps the WAV only long enough for one immediate retry and then discards it. Silence/no-speech results and transcription timeouts are not retried; the page reports each outcome separately.

## Privacy and security behavior

- There is no background listening or wake word.
- Browser capture starts only from an explicit press/hold gesture.
- Microphone tracks stop immediately on release or at 30 seconds.
- Audio is resampled in browser memory to mono 16-bit 16 kHz PCM.
- Only the loopback JARVIS endpoint receives the WAV.
- The server accepts at most 30 seconds and approximately 1 MB per request.
- Recordings shorter than 0.3 seconds are rejected.
- The browser and server independently measure the recording's room-noise floor and require at least four 20 ms windows with speech-like energy at least 1.6 times above that floor.
- whisper.cpp temperature fallback is disabled and non-speech tokens are suppressed to reduce ambiguous-audio hallucinations.
- whisper.cpp now runs the locally stored Silero VAD v6.2.0 model before decoding. Push-to-talk uses the documented 0.5 speech threshold; ambient Conversation mode uses a locally calibrated 0.6 threshold. Both use a 250 ms minimum speech duration, and only VAD-detected speech segments reach Whisper.
- Symbol-only transcripts, musical-note output, bracketed captions such as `[Music]`, and narrowly identified canned non-speech video-outro phrases are rejected before chat submission. Standalone courtesy phrases remain valid speech.
- Every server-side temporary WAV is deleted in a `finally` cleanup path on success, failure, or timeout. A process/runtime failure may cause one new temporary file during the browser's bounded retry of the same in-memory WAV.
- Neither audio nor transcript is logged or persisted by JARVIS.
- A successful transcript is submitted directly as a user chat message without entering the text composer.

## Verified evidence

- The upstream model checksum matches.
- The bundled public JFK WAV transcribed correctly end to end.
- No temporary JARVIS WAV remained after the request.
- Invalid channels, sample rates, durations, and file formats are rejected.
- Synthetic silence, steady fan-like energy, and short high-energy impact envelopes are rejected before Whisper runs, while sustained speech-like changing energy passes both gates.
- The VAD model file is `models/whisper/ggml-silero-v6.2.0.bin` (885,098 bytes; SHA-256 `2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987`).
- Musical-note-only and explicit non-speech caption transcripts are rejected after decoding.
- The live browser shows an enabled, accessible push-to-talk control while text fallback continues to work.
- Timeout and nonzero Whisper-process outcomes are distinct in regression tests, and both preserve temporary-file cleanup. A real transient process failure has not yet been available to acceptance-test the browser retry end to end.

## Remaining limitation

Noise-floor contrast, local Silero VAD, and transcript filtering reduce steady-ambience hallucinations, but they cannot prove that active sound is the user's voice. Clearly audible speech, music, or television may still be transcribed.
