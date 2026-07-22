# Session handoff — voice engine work

A working note for continuing on a different machine. The Cowork/Claude session
that produced this does not carry over between computers, so this file is the
context bridge. Written 2026-07-21.

## What changed this session

- **Fixed the voice-selection bug.** Configured `tts_voice` was being shadowed by
  a stale browser `localStorage` override. Selection now defers to configuration
  unless a still-current override exists (`static/core.js`
  `resolveSpeechSelection`, tested).
- **Added Piper as a second local engine**, installed as the `piper-tts` wheel
  (`OHF-Voice/piper1-gpl`, GPL-3.0) into `runtime/piper-venv`. The archived
  `rhasspy/piper` macOS binaries are unusable — they omit their own libraries
  (upstream issue 404). See `docs/TTS.md`.
- **Voices are engine-tagged.** macOS `say` voices and the Piper voice appear in
  one Speech-panel list and switch without a restart. The engine is a property of
  the selected voice, not a global mode (`jarvis/speech.py` `available_voices`,
  `voice_engine`).
- **Reply text never reaches process arguments.** JARVIS talks to Piper through
  `scripts/piper_synthesize.py` over stdin, because the `piper-tts` CLI would put
  text in argv.
- **Resident Piper worker.** Loading the voice model costs ~0.9 s; synthesis costs
  ~0.15 s. One worker holds the model so the gap between spoken sentences is
  synthesis time, not a repeated cold start. Starts lazily, restarts once on
  failure, released on shutdown (`jarvis/speech.py` `_PiperWorker`,
  `_render_piper`, `shutdown`).
- **Stop-race guard.** A monotonic speech generation ensures a Stop that lands
  while a phrase is still rendering discards that phrase instead of speaking it.

Test suite: 103 Python tests plus the browser-core tests, all passing.

## Measured on the Intel iMac Pro (the old host)

- Piper `en_GB-alan-medium`: warm synthesis ~0.17 s for a 4.4 s utterance
  (real-time factor ~0.04). Between-sentence gap ~0.2 s after the resident-worker
  change.
- First-word latency on a reply is dominated by llama.cpp generating the first
  sentence on CPU, not by TTS.

## Why we are looking at the PC

Fish Audio / OpenAudio S1-mini (the nicer neural voice, incl. the JARVIS clone)
needs a CUDA GPU — the vendor states 12 GB VRAM minimum, Linux/WSL, CPU "not
recommended", and `--compile` unsupported on macOS. The iMac Pro cannot run it
usably. The PC has an **RTX 4070 Ti (12 GB)**, which clears that bar, so the PC is
where Fish becomes viable. Full evaluation note in `docs/TTS.md` under "Engines
evaluated and set aside".

## The architecture fork (decide before integrating Fish)

JARVIS is deliberately loopback-only; `README.md` lists LAN and remote access as
excluded. The PC is a different machine, so:

1. **Relocate the whole JARVIS stack to the PC.** Keeps everything local and
   loopback-only, and the 4070 Ti also accelerates llama.cpp and whisper. Most
   effort, cleanest fit. The migration package already floated a Windows+RTX host.
2. **Fish as a LAN service on the PC, JARVIS stays on the Mac.** Fastest, but
   crosses the loopback-only boundary — reply text would leave the Mac.
3. **Try Fish standalone on the PC first.** No JARVIS changes; hear the voice and
   get the real latency number before committing. Recommended first step.

## Next steps on the PC (Windows 11)

1. Install prerequisites: Git, Python 3.12. For Fish at full speed, use **WSL2**
   with CUDA (native Windows works but cannot use `--compile`).
2. `git clone https://github.com/jwills431/jarvis-alpha.git`
3. Re-provision the gitignored runtimes and models locally: build/download
   llama.cpp with CUDA, the Qwen model, whisper. These did not travel via git.
4. For Piper on the PC: `pip install piper-tts` in a venv, adjust
   `config.local.json` paths (the `runtime/piper-venv/bin/python3` path is
   POSIX; on native Windows it is `Scripts\\python.exe`).
5. For Fish: clone `fishaudio/fish-speech`, install per their docs in WSL2,
   `hf download fishaudio/openaudio-s1-mini`, benchmark one sentence warm before
   any JARVIS integration.

## Still open

- **License.** `README.md` grants no license for the JARVIS source. Piper adds a
  GPL-3.0 runtime dependency; Fish (MIT) would add another. Settle before making
  the repo public.
- **Piper acceptance stages 3–5** in `docs/PIPER_ACCEPTANCE.md` are unrun.
- **Windows path handling** in `config.py`/`speech.py` assumes POSIX venv layout;
  revisit if JARVIS itself moves to Windows.
