from __future__ import annotations

import glob
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WHISPER = ROOT / "runtime/whisper.cpp/build/bin/whisper-cli"
MODEL = ROOT / "models/whisper/ggml-base.en.bin"
VAD_MODEL = ROOT / "models/whisper/ggml-silero-v6.2.0.bin"


def main() -> None:
    sounds = sorted(glob.glob("/System/Library/Sounds/*.aiff"))
    if not sounds:
        raise RuntimeError("no macOS system sounds were found")
    decoded: list[str] = []
    for sound in sounds:
        result = subprocess.run(
            [
                str(WHISPER),
                "--model", str(MODEL),
                "--file", sound,
                "--threads", "10",
                "--language", "en",
                "--no-timestamps",
                "--no-prints",
                "--no-gpu",
                "--no-fallback",
                "--suppress-nst",
                "--vad",
                "--vad-model", str(VAD_MODEL),
                "--vad-threshold", "0.6",
                "--vad-min-speech-duration-ms", "250",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"VAD check failed for {Path(sound).name}")
        transcript = " ".join(result.stdout.split()).strip()
        if transcript:
            decoded.append(f"{Path(sound).name}: {transcript}")
    if decoded:
        raise RuntimeError("notification sounds produced transcripts: " + "; ".join(decoded))
    print(f"VAD rejected all {len(sounds)} macOS system sounds")


if __name__ == "__main__":
    main()
