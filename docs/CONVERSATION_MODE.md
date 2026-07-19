# Opt-in Conversation mode

## Behavior

1. Select **Conversation mode** to explicitly enable hands-free listening.
2. The browser requests microphone access if needed and spends about two seconds measuring the local room-noise floor.
3. The button remains visibly active and the page reports its current state.
4. Three consecutive speech-level audio windows start an utterance, including a short pre-roll so the first syllable is retained.
5. Approximately 0.9 seconds of silence or the 30-second cap ends the utterance.
6. Conversation-specific browser and server noise gates run before submission, followed by the existing transcript checks.
7. Microphone processing pauses while JARVIS transcribes, generates, and speaks the complete reply.
8. After a short echo-tail delay, local noise calibration and listening resume automatically.
9. Say **Goodbye, JARVIS**, **Stop listening**, or **End conversation**—alone or within a longer utterance—to disable the mode by voice, or select **Hands-free on**. Either path immediately stops all microphone tracks.

Typed messages also pause Conversation mode until the generated and spoken reply completes. Push-to-talk is disabled only while Conversation mode is enabled and returns when the mode is turned off.

## Privacy and safety

- Conversation mode is off by default and has no wake word or background activation.
- The microphone is active only after an explicit user gesture and only while the active indicator is visible.
- Audio analysis and the rolling pre-buffer remain in browser memory.
- Audio captured while JARVIS is responding is ignored; no response audio is submitted for transcription.
- Only a completed, speech-like utterance is converted to WAV and sent to the loopback transcription endpoint.
- Stop commands are normalized and matched on complete word boundaries against a fixed local allowlist before chat submission. If a stop phrase occurs within a longer utterance, the entire utterance is treated as a control command and is not sent to the model or added to chat history.
- The same duration, size, room-noise, non-speech, transcript, and temporary-file controls used by push-to-talk remain active.
- Disabling the mode, closing the page, or losing local model/STT readiness closes the microphone.
- There is no cloud call, persistence, telemetry, or LAN exposure.

## Current detector

- Audio windows are supplied by the browser's local Web Audio pipeline.
- The calibrated baseline is the 80th percentile of observed room levels, avoiding an unrealistically quiet estimate during a brief dip in fan noise.
- Initial start threshold: the greater of 0.008 RMS or 2.4 times the adaptive noise floor.
- End threshold: the greater of 0.005 RMS or 1.5 times the adaptive noise floor.
- Start confirmation: three consecutive windows.
- End confirmation: approximately 0.9 seconds below the end threshold.
- Pre-roll: approximately 0.35 seconds.
- Recalibration: 1 second after every reply; initial calibration is 2 seconds.
- Submission backstop: both browser and server require at least six active 20 ms windows at 2.4 times the measured clip floor.

These are alpha values, not universal microphone settings. The real office test determines whether they need adjustment.

## Rollback

Turn Conversation mode off. The microphone closes immediately and push-to-talk plus typed chat remain unchanged. The feature adds no model, dependency, background service, or OS setting.

## Acceptance criteria

- Ambient office fans do not trigger a turn.
- Normal speech starts capture without clipping the first word.
- A natural pause ends and submits the utterance once.
- JARVIS does not transcribe its own spoken reply.
- Listening resumes only after reply speech ends.
- Turning the mode off immediately extinguishes the active microphone state.
- Each allowed stop phrase, alone or embedded on complete word boundaries, closes the microphone, submits no chat turn, and produces a brief local acknowledgment when voice output is enabled.
- Push-to-talk and typed chat still work after disabling the mode.
