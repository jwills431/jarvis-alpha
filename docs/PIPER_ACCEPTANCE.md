# Piper voice acceptance

On-device acceptance for the optional local neural speech engine. These checks require physical control of the iMac and audible playback. They use no private content, make no network calls after provisioning, and change no macOS settings.

Source-only behavior — engine selection, rate-to-length-scale mapping, standard-input synthesis, rendered-audio playback, and interrupt handling — is already covered by the Python suite and needs no hardware. What follows is what mocks cannot answer: whether real Piper sounds good and responds fast enough on this machine.

Status: pending. The built-in `say` engine remains the default until these pass.

## Stage 1 — Provision and verify without JARVIS

Install the engine and voice, then run the provisioning and latency check. Neither step changes configuration.

```sh
cd jarvis-alpha
scripts/setup_piper.sh          # or: scripts/setup_piper.sh low
scripts/check_piper.sh --play
```

Pass criteria:

- All provisioning checks report `ok`, including that `piper-tts` imports and that the `.onnx.json` sidecar sits beside the model. A missing sidecar is the most common silent Piper failure.
- Synthesis produces audio and the real-time factor is below 1.0.
- Render time for the sample phrase is at or under roughly 1 second.

If the real-time factor is at or above 1.0, speech will fall progressively behind generation on long replies. Try a `low` quality voice before continuing; `medium` may be too slow for a 2017 Xeon without GPU acceleration.

Rollback at this stage: nothing has changed. Delete `runtime/piper-venv/` and `models/piper/`.

## Stage 2 — Latency in conversation

Restart with `scripts/start.sh` and confirm `curl -s http://127.0.0.1:8787/api/health` reports `"tts":"ready"`. No configuration change is needed: the Piper voice joins the existing list once its runtime is present.

1. Open **Speech** and confirm the list contains both your macOS voices and the Piper voice, labelled `neural`. Switching between them requires no restart, which is what makes the comparison in Stage 5 direct.
2. Ask a question with a short answer. Measure the gap between the first text appearing and the first audible word.
3. Ask a question with a long, multi-paragraph answer. Listen for whether speech falls behind the text as the reply continues.
4. Set the rate to 120 WPM, then to 350 WPM, and confirm both change speaking speed without distortion.

Pass criteria:

- First audible word arrives within roughly 2 seconds of the first text.
- Speech does not fall further behind as a long reply continues.
- The gap between spoken phrases does not grow over the course of a reply.

JARVIS renders each phrase completely before playing it, so unlike the built-in `say` engine, synthesis time is dead air before every phrase rather than overlapping playback. A resident worker holds the loaded model so that dead air is synthesis only; if these gaps are seconds rather than a fraction of a second, the worker is being restarted per phrase and the cause is worth finding before judging the voice.

## Stage 3 — Interrupt and stop

The render-then-play design means a stop can arrive while a phrase is still rendering, when there is no audio to cut off yet.

1. Ask a question with a long answer. Press **Stop speaking** while a phrase is mid-word. Confirm audio stops promptly.
2. Ask again and press **Stop speaking** during a silent gap between phrases — the window while the next phrase is rendering. Confirm no further audio plays.
3. Repeat step 2 several times in a row, pressing as close to each phrase boundary as possible. This is the specific race the generation guard in `speech.py` addresses. The render window is now short, so land the press just as one sentence ends.
4. Ask a question, and while it is still speaking, submit a second question. Confirm the first reply's remaining phrases are abandoned rather than played after the new reply begins.
5. Select **Voice muted** mid-reply and confirm speech stops.
6. Start a push-to-talk recording while JARVIS is speaking and confirm speech stops first, preventing microphone feedback.

Pass criteria:

- No phrase is ever spoken after the stop that should have cancelled it.
- No audio from an older reply plays after a newer reply starts.
- The written reply remains visible and complete regardless of interruption.

## Stage 4 — Temporary file hygiene

Piper renders to a temporary WAV under the OS temp directory and deletes it immediately. After completing stages 2 and 3, including several interruptions:

```sh
ls "${TMPDIR:-/tmp}"/jarvis-tts-* 2>/dev/null || echo "clean"
```

Pass criteria: `clean`. Any leftover file means a render path is not deleting its output, which would leave spoken reply audio on disk.

Also confirm one worker is running rather than many:

```sh
pgrep -fl piper_synthesize.py
```

One line while JARVIS is running, none after it stops.

## Stage 5 — Voice quality

Judged by the user, not automated.

1. Ask three questions covering ordinary prose, a list, and a reply containing numbers or an abbreviation.
2. Switch to the Piper voice in **Speech**, save, and ask the same three questions.
3. Switch back and forth on a single reply to compare directly.

Pass criteria: the neural voice is clearly more natural in ordinary prose, and its handling of numbers, abbreviations, and sentence boundaries is no worse. If the neural voice sounds better but mishandles numbers badly, that trade-off is worth recording here rather than resolving silently.

Invented proper names may be mispronounced by either engine. Exact spelling remains separate from pronunciation, and the pronunciation-alias feature remains deferred.

## Rollback

Select a macOS voice in **Speech** and save; nothing else is required. To remove Piper entirely, delete `runtime/piper-venv/` and `models/piper/` — both are ignored and hold no application source. The voice list then returns to macOS voices only.

If the Piper runtime or voice goes missing, the Piper voice simply drops out of the Speech list and the macOS voices remain available. Speech controls disable only if no engine at all can synthesize.

## Licensing note

The installed engine is `piper-tts` from `OHF-Voice/piper1-gpl`, which is **GPL-3.0**. It runs as a separate process invoked over standard input and is not linked into or distributed with JARVIS, but it is now a runtime dependency of the optional neural voice. This constrains the still-open license decision for this repository and should be settled before the repository is made public. The older MIT-licensed `rhasspy/piper` build is not a usable alternative on macOS; see the Enabling Piper section of `TTS.md`.
