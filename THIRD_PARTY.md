# Third-party components

- llama.cpp `b10066` (`86a9c79`), MIT license, obtained from the official `ggml-org/llama.cpp` repository.
- Qwen2.5-7B-Instruct GGUF `Q4_K_M`, Apache 2.0 license, obtained from the official `Qwen/Qwen2.5-7B-Instruct-GGUF` repository.
- whisper.cpp v1.9.1 (`f049fff`), MIT license, obtained from the official `ggml-org/whisper.cpp` repository.
- Whisper `base.en` ggml model, obtained from the official whisper.cpp model repository; upstream checksum verified.
- Piper (rhasspy/piper) `2023.11.14-2`, MIT license, obtained from the official `rhasspy/piper` releases. Used only when the optional neural voice engine (`tts_engine: piper`) is enabled.
- Piper voice models (for example `en_GB-alan-medium`), obtained from the official `rhasspy/piper-voices` repository. Each voice retains its own upstream license; verify the per-voice license before use.
- Apple Accelerate and Metal frameworks supplied by macOS.

Runtime source, build products, and model weights are intentionally ignored by this project and retain their upstream licenses.

## piper-tts (optional)

- Source: [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl), installed from PyPI as `piper-tts`.
- License: **GPL-3.0**.
- Used only when a Piper voice is selected. Installed into the ignored `runtime/piper-venv/` and invoked as a separate process; it is not linked into or redistributed with JARVIS.
- Voice models are downloaded separately and carry their own upstream licenses.
- The archived MIT-licensed `rhasspy/piper` macOS binaries are unusable: they omit required libraries (upstream issue 404).
