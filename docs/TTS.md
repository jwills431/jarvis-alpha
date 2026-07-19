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

## Speech engines

Two local synthesis engines are selectable with `tts_engine`; both play on this Mac only and make no network calls.

- `say` (default): the built-in macOS `/usr/bin/say`. Zero extra downloads. **Quick quality win:** install an Enhanced/Premium `en_GB` voice (System Settings → Accessibility → Spoken Content → System Voice → Manage Voices) and set `tts_voice` to it — far more natural than the compact `Daniel` voice, with no code change.
- `piper`: a local neural engine ([Piper](https://github.com/rhasspy/piper)) for a natural, British JARVIS-style voice while staying fully offline. JARVIS pipes the reply text to Piper through standard input (never process arguments or a temporary text file), renders a temporary WAV under the OS temp directory, plays it with `/usr/bin/afplay`, and deletes it immediately.

### Enabling Piper

Piper runs fully offline. Its binary and voices are downloaded artifacts that live under the same ignored `runtime/` and `models/` directories as the chat and Whisper runtimes; nothing here is committed. Run these from the repository root.

1. **Create the directories:**

   ```sh
   mkdir -p runtime/piper models/piper
   ```

2. **Download the Piper binary** for the Intel iMac Pro (macOS x86_64). Confirm the current asset on the [releases page](https://github.com/rhasspy/piper/releases); the Intel build is `piper_macos_x64.tar.gz`:

   ```sh
   curl -L -o /tmp/piper.tar.gz \
     https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_macos_x64.tar.gz
   tar -xzf /tmp/piper.tar.gz -C runtime/          # creates runtime/piper/piper and its libraries
   chmod +x runtime/piper/piper
   xattr -dr com.apple.quarantine runtime/piper    # only if macOS Gatekeeper blocks the unsigned binary
   ```

3. **Download a British voice.** Both the model and its adjacent `.onnx.json` config are required — Piper loads the config from beside the model:

   ```sh
   base=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium
   curl -L -o models/piper/en_GB-alan-medium.onnx      "$base/en_GB-alan-medium.onnx"
   curl -L -o models/piper/en_GB-alan-medium.onnx.json "$base/en_GB-alan-medium.onnx.json"
   ```

   Other calm British male options include `en_GB-northern_english_male-medium` and `en_GB-cori-high`. Browse them all at [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).

4. **Verify synthesis independently of JARVIS** (recommended):

   ```sh
   echo 'At your service.' | runtime/piper/piper \
     --model models/piper/en_GB-alan-medium.onnx --output_file /tmp/jarvis-voice-test.wav
   afplay /tmp/jarvis-voice-test.wav && rm /tmp/jarvis-voice-test.wav
   ```

5. **Select the engine** in ignored `config.local.json` (copy it from `config.example.json` first if you do not have one):

   ```json
   {
     "tts_engine": "piper",
     "piper_binary": "runtime/piper/piper",
     "piper_voice": "models/piper/en_GB-alan-medium.onnx",
     "piper_voice_name": "JARVIS (British)"
   }
   ```

6. **Start JARVIS** (`scripts/start.sh`) and confirm the voice is live:

   ```sh
   curl -s http://127.0.0.1:8787/api/health    # expect "tts":"ready"
   ```

   The Speech panel now lists `piper_voice_name`; the rate slider, mute, and stop controls work unchanged. The 120–350 WPM rate maps to Piper's length scale (the `tts_rate` baseline maps to a normal 1.0 scale; faster rates shorten it, slower rates lengthen it).

If the binary or voice is missing, health reports `tts: unavailable`, the speech controls disable, and text plus push-to-talk keep working. Revert to the built-in voice at any time with `"tts_engine": "say"`; no Piper runtime is then required.

### Voice likeness and cloning

Piper voices are original synthetic voices. Cloning a specific real person's voice — including a film characterization such as Paul Bettany's JARVIS — implicates that person's voice-likeness/right-of-publicity and the studio's IP. For private, on-device, non-distributed use the practical risk is low, but do not train on or distribute an unauthorized clone of a real individual. The recommended approach is a *JARVIS-inspired* British voice (calm, precise, measured), or, if cloning, an ethically sourced reference: your own voice, a consenting speaker, or a properly licensed professional voice.

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

Set `tts_enabled` to `false` in local configuration. The health endpoint will mark speech unavailable, controls will disable, and text plus push-to-talk remain operational. **Use defaults** restores the configured `Daniel`/190 selection without changing configuration files. To revert the neural voice without disabling speech, set `"tts_engine": "say"`; the built-in voice resumes and no Piper runtime is required.
