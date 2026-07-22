#!/usr/bin/env python3
"""Render utterances with Piper, reading the text from standard input.

Two modes:

  one-shot   Render a single utterance read from standard input, then exit.
             Used by scripts/check_piper.sh for measurement.

  --serve    Load the voice once and stay resident, rendering one utterance per
             request line. This is what JARVIS uses. Loading the model costs
             roughly a second and synthesis costs a fraction of that, so paying
             the load per phrase would dominate the pause between sentences.

The piper-tts command line takes its text as a positional argument, which would
place reply text in process arguments visible to any local process listing. Both
modes here read the text from standard input instead, so it never appears in an
argument vector or a temporary text file.

Serve protocol, one JSON object per line in each direction:

  request   {"text": "...", "output_file": "/path.wav", "length_scale": 1.0}
  response  {"status": "ok"} | {"status": "error", "error": "<ExceptionType>"}

JSON escapes newlines, so an utterance never spans lines. Responses never echo
the utterance text.
"""
from __future__ import annotations

import argparse
import json
import sys
import wave

MAX_REQUEST_BYTES = 200_000


def _load_voice(model: str):
    from piper import PiperVoice

    return PiperVoice.load(model)


def _render(voice, text: str, output_file: str, length_scale: float) -> None:
    from piper import SynthesisConfig

    settings = SynthesisConfig(length_scale=length_scale)
    with wave.open(output_file, "wb") as output:
        voice.synthesize_wav(text, output, syn_config=settings)


def _serve(model: str) -> int:
    try:
        voice = _load_voice(model)
    except Exception as error:  # noqa: BLE001
        print(f"voice load failed: {type(error).__name__}", file=sys.stderr)
        return 1

    # Signals readiness so the caller does not send a request into a process
    # that is still loading and mistake the load time for synthesis time.
    print(json.dumps({"status": "ready"}), flush=True)

    for line in sys.stdin:
        if len(line) > MAX_REQUEST_BYTES:
            print(json.dumps({"status": "error", "error": "RequestTooLarge"}), flush=True)
            continue
        try:
            request = json.loads(line)
            text = request["text"]
            output_file = request["output_file"]
            length_scale = float(request.get("length_scale", 1.0))
            if not isinstance(text, str) or not isinstance(output_file, str):
                raise TypeError("invalid request")
        except (ValueError, KeyError, TypeError) as error:
            print(json.dumps({"status": "error", "error": type(error).__name__}), flush=True)
            continue
        try:
            _render(voice, text, output_file, length_scale)
        except Exception as error:  # noqa: BLE001
            # The type name is safe to report; the message could quote the text.
            print(json.dumps({"status": "error", "error": type(error).__name__}), flush=True)
            continue
        print(json.dumps({"status": "ok"}), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Render speech with Piper.")
    parser.add_argument("--model", required=True, help="path to the .onnx voice model")
    parser.add_argument("--serve", action="store_true", help="stay resident and serve requests")
    parser.add_argument("--output-file", help="WAV to write (one-shot mode)")
    parser.add_argument("--length-scale", type=float, default=1.0, help="1.0 is the voice's normal speed")
    arguments = parser.parse_args()

    try:
        import piper  # noqa: F401
    except ImportError:
        print("piper-tts is not installed in this interpreter", file=sys.stderr)
        return 3

    if arguments.serve:
        return _serve(arguments.model)

    if not arguments.output_file:
        print("--output-file is required without --serve", file=sys.stderr)
        return 2
    text = sys.stdin.read().strip()
    if not text:
        print("no text on standard input", file=sys.stderr)
        return 2
    try:
        _render(_load_voice(arguments.model), text, arguments.output_file, arguments.length_scale)
    except Exception as error:  # noqa: BLE001
        print(f"synthesis failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
