# JARVIS Alpha

A private, local conversational assistant alpha with text, push-to-talk, and automatic spoken replies for the Intel iMac Pro. The migration package and synced references remain untouched.

This directory is the standalone GitHub repository boundary. Downloaded runtimes, model weights, local memory, configuration, generated credentials, and migration/reference packages are intentionally excluded. A fresh clone requires local runtime/model provisioning described in [`docs/REPOSITORY_SETUP.md`](docs/REPOSITORY_SETUP.md).

## Safety boundary

- Both the model server and application bind to IPv4 loopback only.
- Browser conversations stay in page memory and are not written as transcripts. Separately, Automatic memory may retain likely durable user-authored facts in the bounded local memory ledger; uncertain or conflicting items require approval.
- Recent context is bounded to complete alternating turns within 20 messages and 12,000 characters. Failed or incomplete generations are not retained in context.
- Historical assistant-role suggestions are treated as proposals; creative facts become established only when stated or explicitly approved by the user.
- Explicit user spelling corrections are extracted from the bounded conversation, retained only in memory, and supplied to the model as exact-character constraints. JARVIS does not infer spellings that the user did not explicitly provide.
- The application logs request metadata, never prompts or responses.
- No external tools, wake word, remote access, telemetry, or cloud fallback are present.
- Persistent memory is local, bounded, user-visible, editable, and removable. It rejects common credential/financial-secret categories and never extracts facts from assistant output.
- Reminder, timer, and alarm requests receive a deterministic local refusal while those tools are unavailable; JARVIS never pretends an alert was scheduled.
- This alpha is English-only. Unexpected non-English-script model drift is rejected and the turn is removed from retained context.
- Microphone capture occurs only while the user holds the button or has explicitly enabled visible Conversation mode. Audio is transcribed locally and deleted immediately after the request.
- Browser-supplied system messages are rejected; request size and history are bounded.
- The proxy authenticates to llama.cpp with a generated, ignored, owner-readable runtime key.

This is an alpha, not a security boundary against other software already running as the same local user.

## Selected baseline

- Model: Qwen2.5-7B-Instruct GGUF, `Q4_K_M`
- License: Apache 2.0
- Initial context: 4096 tokens
- Runtime: a pinned llama.cpp release built once with macOS Metal support
- Backend: selected only after identical CPU and Metal benchmark runs

## Verify the application without a model

```sh
cd jarvis-alpha
PYTHONPATH=. python3 -m unittest discover -s tests -v
python3 -m py_compile jarvis/*.py
```

GitHub Actions runs the same source-only Python, JavaScript, compilation, and shell checks on pushes and pull requests.

## Run

```sh
cd jarvis-alpha
scripts/start.sh
```

Open `http://127.0.0.1:8787`. Stop both foreground processes with Ctrl-C. No process is installed as a background service. The CPU backend is the measured default; see `docs/BENCHMARK.md`.

The foreground launcher supports an immediate stop and restart on the same loopback ports; see `docs/RELIABILITY.md` for the verified lifecycle and remaining reliability work.

Physical sleep/wake and structured spoken-context acceptance steps are defined in `docs/USER_ACCEPTANCE.md` and require the user at the machine.

For voice input, hold **Hold to talk**, speak for up to 30 seconds, and release. Recognized speech is submitted automatically and appears as your user message in the chat. The first use prompts for browser microphone permission. See `docs/VOICE.md`.

Quiet, very short, or low-energy captures are rejected in both the browser and server before transcription. The page reports **No speech detected** and submits nothing.

If the local transcription process fails, the refreshed browser retries the same in-memory recording once and then discards it. No-speech and timeout outcomes are not retried.

For opt-in hands-free use, select **Conversation mode**. After local room-noise calibration, JARVIS detects the beginning of speech, submits after roughly one second of silence, pauses microphone processing through transcription and the full spoken reply, then resumes listening. Select **Hands-free on** or say **Goodbye, JARVIS**, **Stop listening**, or **End conversation** to turn the mode off and close the microphone. See `docs/CONVERSATION_MODE.md`.

JARVIS begins speaking at completed sentence or phrase boundaries while each reply is still being generated through a locally installed macOS voice, whether the question was typed or spoken. The default remains `Daniel` at 190 words per minute. **Speech** selects another already-installed English voice and rate, **Voice on** mutes or enables future replies, and **Stop speaking** immediately interrupts the current reply and discards queued speech. See `docs/TTS.md`.

Open **Memory** to save, review, edit, or delete a fact or preference. Voice and text commands also support `Remember that ...`, `Remember as preference: ...`, `Forget that ...`, and `What do you remember?`. Memory is stored only in ignored `data/memory.json`; see `docs/MEMORY.md` for limits, privacy boundaries, and rollback.

**Auto memory on** is the default. After a successful turn, a deterministic relevance gate may submit the exact user statement and bounded preceding question to the same loopback-only model for classification. High-confidence durable facts are saved with a visible **Undo** notice; ambiguous, hypothetical, or conflicting items remain outside model context until approved in **Memory**. Toggle Auto memory off at any time without deleting prior entries.

Turn on **Learn mode** before a guided get-to-know-you conversation, or ask JARVIS to ask questions to get to know you. While the visible control says **Learning on**, each submitted answer is saved with the preceding JARVIS question as one reviewable general-memory entry. Learn mode is page-local, turns off when chat is cleared or the page reloads, and reports any rejected answer instead of silently losing it.

**Copy chat** copies the currently visible user/JARVIS conversation to the system clipboard only after an explicit click. It does not save a transcript, call the server, or include the pre-conversation ready message. This is a manual recovery/export control; clipboard contents may be readable by other local applications.

## Rollback

Stop the two foreground processes. Runtime source/builds, models, benchmark results, and memory data are isolated under ignored `runtime/`, `models/`, `benchmark/results/`, and `data/` directories. Removing runtime/model artifacts does not affect the source or migration references. Set `"auto_memory_enabled": false` to disable automatic classification while retaining explicit memory, or set `"memory_enabled": false` to disable all persistent memory without deleting it. To disable rolling-context cache reuse without changing files, start with `JARVIS_CACHE_REUSE=0 scripts/start.sh`.

## Contributing, security, and license

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for validation and privacy requirements and [`SECURITY.md`](SECURITY.md) for private vulnerability reporting. Third-party components retain their upstream licenses as listed in [`THIRD_PARTY.md`](THIRD_PARTY.md).

No license is currently granted for the original JARVIS Alpha source. Choose and add a project license before making the repository public; a private personal repository does not require that decision immediately.
