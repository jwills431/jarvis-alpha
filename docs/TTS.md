# Automatic local speech

## Behavior

- JARVIS speaks every assistant reply, regardless of whether the question was typed or spoken.
- Speech begins at the first completed sentence or natural phrase boundary while the rest of the reply is still being generated.
- Complete sentences are preferred; unusually long sentences are split near punctuation or whitespace after about 220 characters.
- The default voice is the installed macOS `Daniel` (`en_GB`) voice at 190 words per minute.
- **Speech** lists English voices already installed on this Mac and accepts a bounded 120–350 WPM rate. The saved choice applies to subsequent spoken replies.

## Voice precedence

Configuration is authoritative. The `tts_voice`/`tts_rate` values in `config.local.json` are used unless this browser holds a saved override from the **Speech** panel.

- A saved override is stored with the configured default it was chosen against.
- Editing `tts_voice` or `tts_rate` in configuration invalidates that override; the new configured value takes effect on the next page load and the stale browser entry is removed.
- Saving a selection that equals the configured default removes the override rather than pinning it, so future configuration changes continue to apply.
- Selecting an override for a voice that is no longer installed also discards it.
- Until the installed-voice list loads, the browser sends no voice at all and the server synthesizes with its configured voice. The client never names a voice that configuration did not choose.

Configuration is read once at startup, so restart with `scripts/start.sh` after editing `config.local.json`. Confirm what the server resolved with:

```sh
curl -s http://127.0.0.1:8787/api/speech/options | python3 -m json.tool
```

`default_voice` must exactly match a `name` in the `voices` list. Voice names come from `/usr/bin/say -v '?'`, where Enhanced/Premium voices are listed with their suffix (for example `Jamie (Premium)`). If the configured name is not listed verbatim, it cannot be selected.
- **Preview** speaks one fixed, non-private sentence using the currently selected controls. It is never triggered automatically.
- **Voice on** toggles automatic speech. Muting also stops the current reply.
- **Stop speaking** interrupts the current phrase and discards queued phrases without muting future replies.
- Starting a new push-to-talk recording stops current speech first to avoid microphone feedback.
- A new response replaces any older speech rather than overlapping it.
- Phrase requests are serialized so speech remains in response order even when generation runs ahead.

## Speech engines

Two local synthesis engines are available; both play on this Mac only and make no network calls. The engine is a property of each voice rather than a global mode: installed macOS voices and a provisioned Piper voice appear together in the **Speech** panel, so they can be compared without a restart. `tts_engine` selects which one supplies the default voice.

- `say` (default): the built-in macOS `/usr/bin/say`. Zero extra downloads. **Quick quality win:** install an Enhanced/Premium `en_GB` voice (System Settings → Accessibility → Spoken Content → System Voice → Manage Voices) and set `tts_voice` to it — far more natural than the compact `Daniel` voice, with no code change.
- `piper`: a local neural engine ([Piper](https://github.com/rhasspy/piper)) for a natural, British JARVIS-style voice while staying fully offline. JARVIS pipes the reply text to Piper through standard input (never process arguments or a temporary text file), renders a temporary WAV under the OS temp directory, plays it with `/usr/bin/afplay`, and deletes it immediately.

### Enabling Piper

Piper runs fully offline once installed. It lives in an isolated virtual environment under the ignored `runtime/` directory, with voices under `models/`; nothing here is committed.

```sh
scripts/setup_piper.sh          # or: scripts/setup_piper.sh low
scripts/check_piper.sh --play
```

`setup_piper.sh` creates `runtime/piper-venv`, installs `piper-tts`, verifies the package imports, and downloads the voice with its required `.onnx.json` sidecar. `check_piper.sh` renders a sample phrase the same way JARVIS does and reports the real-time factor. Neither changes configuration.

Restart JARVIS afterwards. The Piper voice then appears in the **Speech** panel alongside the installed macOS voices, labelled `neural`, and can be selected without editing configuration or restarting again.

#### Why not the standalone binary

The archived `rhasspy/piper` repository published macOS tarballs that omit the libraries their own binary links against, producing `Library not loaded: @rpath/libespeak-ng.1.dylib` on first synthesis ([upstream issue 404](https://github.com/rhasspy/piper/issues/404), never fixed before the repository was archived in October 2025). `libpiper_phonemize` is not packaged anywhere else, so the dependency cannot be satisfied without building from source. The `piper-tts` wheel from `OHF-Voice/piper1-gpl` bundles its libraries and espeak-ng data, which is why it is used instead.

#### One resident worker

Loading the voice model costs roughly a second; synthesizing a sentence costs a fraction of that — measured on the target Mac, a 4.4-second utterance rendered in 0.17 seconds, a real-time factor of about 0.04. Spawning a fresh process per phrase therefore spent most of its time reloading a model it had just discarded, and because JARVIS does not begin rendering a phrase until the previous one finishes playing, that cost landed directly in the silence between spoken sentences.

JARVIS keeps one Piper process resident with the model loaded and sends it one phrase per request. The worker starts lazily on the first Piper phrase, is replaced once if it dies, and is released when the foreground service stops. The gap between sentences becomes synthesis time rather than a repeated cold start.

#### Keeping reply text out of process arguments

The `piper-tts` command line takes its text as a positional argument, which would expose reply text to any local process listing. JARVIS therefore calls `scripts/piper_synthesize.py` with the virtual environment's interpreter; that wrapper uses Piper's Python API and reads each utterance from standard input as one JSON request line. Arguments carry only the model path and the `--serve` flag. Responses report a status and, on failure, an exception type — never the utterance. This preserves the same guarantee the built-in `say` engine has.

### Engines evaluated and set aside

- **Fish Audio / OpenAudio S1-mini** (zero-shot cloning, the voice at fish.audio): evaluated 2026-07 and not pursued on this machine. The open model is MIT-licensed and runs offline, but the vendor's own local-setup docs require a 12 GB CUDA GPU and Linux, list CPU-only as "not recommended," and note `--compile` is unsupported on macOS. Their entry-level recommended GPU (RTX 3060) reaches ~15x real-time; a 2017 Intel CPU with no usable GPU would be far slower — plausibly seconds to tens of seconds per sentence, versus Piper's measured ~0.17 s. It would erase the resident-worker latency gain. The linked "JARVIS" voice is also a zero-shot clone of a real actor's performance, carrying the same voice-likeness/right-of-publicity concern noted below. Revisit only if a CUDA GPU is added (the migration package's historical RTX 3060 eGPU path would suffice).

### Voice likeness and cloning

Piper voices are original synthetic voices. Cloning a specific real person's voice — including a film characterization such as Paul Bettany's JARVIS — implicates that person's voice-likeness/right-of-publicity and the studio's IP. For private, on-device, non-distributed use the practical risk is low, but do not train on or distribute an unauthorized clone of a real individual. The recommended approach is a *JARVIS-inspired* British voice (calm, precise, measured), or, if cloning, an ethically sourced reference: your own voice, a consenting speaker, or a properly licensed professional voice.

## Privacy and security

- Synthesis uses the built-in `/usr/bin/say`, or a locally installed Piper binary when selected; there is no cloud TTS call in either case.
- Reply text is sent to `say` through standard input, not command-line arguments or a temporary text file.
- The browser calls only the loopback JARVIS endpoint.
- Speech requests are limited to 4,000 characters and the process is capped at 180 seconds.
- Prompts, replies, and spoken text are not logged or persisted by JARVIS.
- A browser-selected voice must exactly match the server's installed-English-voice enumeration; arbitrary process arguments are rejected.
- A browser-selected rate must be an integer from 120 through 350 WPM.
- Voice and rate preferences use this loopback origin's browser storage. They contain no conversation text and do not modify macOS settings.
- Active speech is terminated when the foreground JARVIS service stops.
- Piper renders to a temporary WAV under the OS temp directory and deletes it immediately, including when synthesis is interrupted.
- A stop or a newer reply advances an internal speech generation. A phrase that finished rendering before that point is discarded rather than played, so an interrupted phrase is never spoken afterwards.

## Failure behavior

Speech synthesis is independent from text generation and speech recognition. If synthesis is unavailable or fails, the written answer remains visible and both text and push-to-talk input continue to work.

Exact written spelling and spoken pronunciation are separate. The built-in voice guesses pronunciation from text and may mispronounce invented names. An optional pronunciation-alias feature is deferred for later consideration; it must store a user-approved spoken alias separately from canonical written spelling and may affect only synthesis. The current alpha does not guess or silently rewrite either value.

## Rollback

Set `tts_enabled` to `false` in local configuration. The health endpoint will mark speech unavailable, controls will disable, and text plus push-to-talk remain operational. **Use defaults** restores the configured voice and rate without changing configuration files. To revert the neural voice without disabling speech, set `"tts_engine": "say"`; the built-in voice resumes and no Piper runtime is required.
