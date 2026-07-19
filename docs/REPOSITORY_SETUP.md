# Repository and fresh-clone setup

## GitHub upload boundary

`jarvis-alpha/` is the repository root. Migration packages, preserved source snapshots, generated archives, and synchronized project-reference files outside this directory are not application source and must not be uploaded with it.

The repository intentionally excludes downloaded runtimes, model weights, memory data, local configuration, generated keys, raw benchmark results, generated speech, and editor/cache files. A clone therefore contains source, tests, prompts, scripts, and documentation only.

## Required local artifacts

The current launcher expects these ignored paths unless an environment override is supplied:

| Component | Default local path | Pinned baseline |
|---|---|---|
| llama.cpp server | `runtime/llama.cpp/build/bin/llama-server` | release `b10066`, commit `86a9c79` |
| Chat model | `models/qwen2.5-7b-instruct-q4_k_m.gguf` | Qwen2.5-7B-Instruct `Q4_K_M` |
| whisper.cpp CLI | `runtime/whisper.cpp/build/bin/whisper-cli` | v1.9.1, commit `f049fff` |
| Whisper model | `models/whisper/ggml-base.en.bin` | `base.en` |
| Silero VAD model | `models/whisper/ggml-silero-v6.2.0.bin` | v6.2.0 |
| Piper binary (optional) | `runtime/piper/piper` | rhasspy/piper `2023.11.14-2`, macOS x64 |
| Piper voice (optional) | `models/piper/en_GB-alan-medium.onnx` (+ `.onnx.json`) | `rhasspy/piper-voices` |

The Piper rows are required only for the optional natural neural voice, enabled by setting `tts_engine` to `piper`; step-by-step download and verification commands are in `docs/TTS.md`. The default `say` engine needs no downloads.

See `THIRD_PARTY.md`, `docs/BENCHMARK.md`, and `docs/VOICE.md` for upstream projects, licenses, selected hardware settings, and recorded checksums. Obtain model files only from their documented upstream publishers and verify their checksums before use.

## Local configuration

Copy `config.example.json` to ignored `config.local.json` only when overriding defaults. Never commit the local file. The backend launcher creates an ignored owner-readable `.runtime-api-key` on first start.

Environment overrides supported by the launcher include:

- `JARVIS_MODEL_PATH`
- `JARVIS_LLAMA_SERVER`
- `JARVIS_GPU_LAYERS`
- `JARVIS_CACHE_REUSE`
- `JARVIS_CONFIG`

All configured application and backend addresses must remain IPv4 loopback addresses; configuration validation fails closed otherwise.

## Source-only verification

The complete automated suite requires no runtime build, model download, microphone, or network connection:

```sh
python3 -m unittest discover -s tests -v
node tests/test_core.js
PYTHONPYCACHEPREFIX=/tmp/jarvis-alpha-pycache python3 -m py_compile jarvis/*.py
bash -n scripts/*.sh benchmark/run.sh
```

## Publishing checklist

1. Review `git status --short` and `git diff --cached`.
2. Confirm ignored artifacts with `git status --ignored --short`.
3. Run a value-suppressed secret scan or GitHub-supported local scanner.
4. Confirm no tracked file exceeds the intended source-only size limit.
5. Choose repository visibility and a project license deliberately. No project license is granted by the current source tree.
6. Commit locally using the personal Git identity intended for the repository.
7. Create the remote and push only after company policy permits using the Copilot account with a personal repository.
