# Automatic local speech

## Behavior

- JARVIS speaks every assistant reply, regardless of whether the question was typed or spoken.
- Speech begins at the first completed sentence or natural phrase boundary while the rest of the reply is still being generated.
- Complete sentences are preferred; unusually long sentences are split near punctuation or whitespace after about 220 characters.
- The default voice is the installed macOS `Daniel` (`en_GB`) voice at 190 words per minute.
- **Speech** lists English voices already installed on this Mac and accepts a bounded 120–350 WPM rate. The saved choice applies to subsequent spoken replies.
- **Preview** speaks one fixed, non-private sentence using the currently selected controls. It is never triggered automatically.
- **Voice on** toggles automatic speech. Muting also stops the current reply.
- **Stop speaking** interrupts the current phrase and discards queued phrases without muting future replies.
- Starting a new push-to-talk recording stops current speech first to avoid microphone feedback.
- A new response replaces any older speech rather than overlapping it.
- Phrase requests are serialized so speech remains in response order even when generation runs ahead.

## Privacy and security

- Synthesis uses the built-in `/usr/bin/say`; there is no cloud TTS call or added dependency.
- Reply text is sent to `say` through standard input, not command-line arguments or a temporary text file.
- The browser calls only the loopback JARVIS endpoint.
- Speech requests are limited to 4,000 characters and the process is capped at 180 seconds.
- Prompts, replies, and spoken text are not logged or persisted by JARVIS.
- A browser-selected voice must exactly match the server's installed-English-voice enumeration; arbitrary process arguments are rejected.
- A browser-selected rate must be an integer from 120 through 350 WPM.
- Voice and rate preferences use this loopback origin's browser storage. They contain no conversation text and do not modify macOS settings.
- Active speech is terminated when the foreground JARVIS service stops.

## Failure behavior

Speech synthesis is independent from text generation and speech recognition. If synthesis is unavailable or fails, the written answer remains visible and both text and push-to-talk input continue to work.

Exact written spelling and spoken pronunciation are separate. The built-in voice guesses pronunciation from text and may mispronounce invented names. An optional pronunciation-alias feature is deferred for later consideration; it must store a user-approved spoken alias separately from canonical written spelling and may affect only synthesis. The current alpha does not guess or silently rewrite either value.

## Rollback

Set `tts_enabled` to `false` in local configuration. The health endpoint will mark speech unavailable, controls will disable, and text plus push-to-talk remain operational. **Use defaults** restores the configured `Daniel`/190 selection without changing configuration files.
