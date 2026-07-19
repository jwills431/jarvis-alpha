# Local text-to-speech decision

## Confirmed local capability

- `/usr/bin/say` is present and enumerates macOS system voices without adding a dependency.
- Locally enumerated English choices include `Daniel` (`en_GB`), `Samantha` (`en_US`), `Karen` (`en_AU`), `Moira` (`en_IE`), and several newer character voices. `Daniel` was verified by silent file synthesis.
- Apple documents system voice selection and optional voice downloads in Accessibility > Read & Speak.

Primary references:

- https://support.apple.com/guide/mac-help/change-the-voice-your-mac-uses-to-speak-text-mchlp2290/mac
- https://developer.apple.com/documentation/avfaudio/speech-synthesis

## Selected alpha behavior

Speak every assistant reply, whether the question was typed or spoken. Begin at natural sentence or phrase boundaries while generation continues, and provide a visible speech toggle and stop control so output is never difficult to interrupt.

Initial voice: `Daniel` (`en_GB`). It fits the requested JARVIS character and is already enumerated by the local speech service.

## Proposed reversible design

1. Add bounded text-to-speech configuration using the selected behavior and voice.
2. Accept only bounded assistant text at a loopback-only synthesis endpoint.
3. Select the voice from validated server configuration, never from a request-supplied command argument.
4. Pass text to the synthesizer without invoking a shell.
5. Feed reply text through standard input so it is absent from process arguments and temporary files.
6. Track one active synthesizer process so new speech replaces old speech and the user can stop it immediately.
7. Stop active speech during application shutdown.

## Acceptance criteria

- The selected installed voice speaks a short assistant reply intelligibly.
- Voice-originated replies follow the chosen automatic/manual policy; typed replies follow the chosen policy.
- The user can stop playback immediately.
- A new response stops any prior playback rather than overlapping it.
- Ordered sentence chunks begin before a multi-sentence response finishes generating.
- Synthesis failures leave text chat and speech input usable.
- Input length and runtime are bounded; request text and audio are not logged or persisted.
- Reply text is absent from command arguments and temporary files.
- Active speech is stopped on cancellation, replacement, timeout, and application shutdown.
- The complete automated suite and restart checks continue to pass.

## Rollback

Disable text-to-speech in configuration and remove or hide its controls. Text chat and push-to-talk remain independent and continue to function.

## Decisions completed

- Speak replies automatically after every question.
- Use the `Daniel` voice for the first alpha implementation.

## Optional future enhancement: pronunciation aliases

Status: deferred by user choice; not part of the current explicit-memory milestone.

A later opt-in pronunciation lexicon may map a canonical written term to a separate user-approved spoken alias. The written chat, retained context, and creative canon must always preserve the canonical spelling; substitution may occur only in text sent to local speech synthesis.

Before implementation, decide whether aliases are session-only by default or may be explicitly persisted. Any persistent form must be local, user-editable, bounded, excluded from logs, and removable without affecting conversation history. JARVIS must never infer, silently create, or overwrite an alias.

Acceptance criteria:

- With the feature disabled, speech behavior is identical to the current alpha.
- Enabling an alias changes only synthesized pronunciation, never visible or model-visible text.
- Every alias requires an explicit canonical spelling and user-approved spoken form.
- Exact, case-sensitive matching is the safe default; ambiguous partial-word replacement is prohibited.
- Aliases are bounded, local-only, excluded from logs, and clearable independently.
- Invalid or unavailable aliases fall back to the canonical written term without blocking speech.
- Disabling the feature is an immediate rollback and does not modify canon or chat history.
