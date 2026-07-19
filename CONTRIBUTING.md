# Contributing

JARVIS Alpha is an experimental, single-user, local assistant. Keep changes small, reversible, and inside the loopback-only privacy boundary.

## Before changing code

- Do not commit model weights, generated audio, runtime builds, local configuration, memory data, benchmark results, credentials, tokens, cookies, private identifiers, or absolute user paths.
- Do not add cloud fallbacks, telemetry, LAN listeners, background services, or operating-system changes without an explicit architecture decision.
- Treat user-authored facts and assistant proposals as different sources. Assistant output must never silently become authoritative memory.
- Preserve text-chat operation when speech input, speech output, or memory is unavailable.

## Validation

Run the repository checks before opening a pull request:

```sh
python3 -m unittest discover -s tests -v
node tests/test_core.js
PYTHONPYCACHEPREFIX=/tmp/jarvis-alpha-pycache python3 -m py_compile jarvis/*.py
bash -n scripts/*.sh benchmark/run.sh
```

Tests must not require a downloaded model, microphone, network connection, or private local configuration.

## Pull requests

- Explain the user-visible outcome and rollback.
- Document new dependencies, model files, licenses, storage, and network behavior.
- Add focused regression coverage for security, context, memory, and cancellation changes.
- Use synthetic data in tests and screenshots.
- Keep generated artifacts outside Git; update `THIRD_PARTY.md` when a dependency or model is adopted.
