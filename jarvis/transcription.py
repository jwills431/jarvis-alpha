from __future__ import annotations

import io
import math
import os
import re
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path

from .config import Config

ROOT = Path(__file__).resolve().parent.parent
MIN_FRAMES = 4_800
MAX_FRAMES = 480_000
ENERGY_WINDOW_FRAMES = 320
MIN_WINDOW_RMS = 0.006
MIN_ACTIVE_WINDOWS = 4
MIN_ACTIVITY_SPAN_WINDOWS = 10
MIN_PEAK_TO_FLOOR_RATIO = 1.6
CONVERSATION_MIN_ACTIVE_WINDOWS = 6
CONVERSATION_MIN_PEAK_TO_FLOOR_RATIO = 2.4
MUSIC_SYMBOLS = frozenset("♪♫♬♩🎵🎶")
NON_SPEECH_CAPTIONS = "music|music playing|instrumental music|applause|laughter|silence|noise|background noise|inaudible"
CANNED_NON_SPEECH_TRANSCRIPTS = (
    re.compile(r"^(?:thanks|thank you)\s+for\s+watching(?:\s+this\s+video)?[.!?]*$", re.IGNORECASE),
)


class TranscriptionError(RuntimeError):
    pass


class NoSpeechDetected(TranscriptionError):
    pass


class TranscriptionTimeout(TranscriptionError):
    pass


class TranscriptionProcessError(TranscriptionError):
    pass


def runtime_ready(config: Config) -> bool:
    if not config.stt_enabled:
        return False
    binary = _resolve(config.whisper_binary)
    model = _resolve(config.whisper_model)
    vad_model = _resolve(config.whisper_vad_model)
    return (
        binary.is_file()
        and os.access(binary, os.X_OK)
        and model.is_file()
        and (not config.whisper_vad_enabled or vad_model.is_file())
    )


def validate_wav(data: bytes) -> int:
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            if audio.getnchannels() != 1:
                raise TranscriptionError("audio must be mono")
            if audio.getsampwidth() != 2:
                raise TranscriptionError("audio must use 16-bit PCM")
            if audio.getframerate() != 16_000:
                raise TranscriptionError("audio must use a 16 kHz sample rate")
            if audio.getcomptype() != "NONE":
                raise TranscriptionError("audio must be uncompressed PCM")
            frames = audio.getnframes()
            if not MIN_FRAMES <= frames <= MAX_FRAMES:
                raise TranscriptionError("audio duration must be between 0.3 and 30 seconds")
            return frames
    except (EOFError, wave.Error) as exc:
        raise TranscriptionError("audio is not a valid WAV file") from exc


def transcribe(config: Config, data: bytes, *, conversation_mode: bool = False) -> str:
    if not runtime_ready(config):
        raise TranscriptionError("speech recognition is unavailable")
    validate_wav(data)
    validate_speech_energy(
        data,
        min_active_windows=CONVERSATION_MIN_ACTIVE_WINDOWS if conversation_mode else MIN_ACTIVE_WINDOWS,
        min_peak_to_floor_ratio=(
            CONVERSATION_MIN_PEAK_TO_FLOOR_RATIO if conversation_mode else MIN_PEAK_TO_FLOOR_RATIO
        ),
    )
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="jarvis-stt-", suffix=".wav", delete=False) as audio_file:
            temp_path = audio_file.name
            audio_file.write(data)
        command = [
            str(_resolve(config.whisper_binary)),
            "--model", str(_resolve(config.whisper_model)),
            "--file", temp_path,
            "--threads", "10",
            "--language", "en",
            "--no-timestamps",
            "--no-prints",
            "--no-gpu",
            "--no-fallback",
            "--suppress-nst",
        ]
        if config.whisper_vad_enabled:
            vad_threshold = (
                config.whisper_conversation_vad_threshold
                if conversation_mode
                else config.whisper_vad_threshold
            )
            command.extend([
                "--vad",
                "--vad-model", str(_resolve(config.whisper_vad_model)),
                "--vad-threshold", str(vad_threshold),
                "--vad-min-speech-duration-ms", str(config.whisper_vad_min_speech_ms),
            ])
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=config.transcription_timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise TranscriptionProcessError("speech recognition failed")
        return validate_transcript(result.stdout)
    except subprocess.TimeoutExpired as exc:
        raise TranscriptionTimeout("speech recognition timed out") from exc
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def validate_speech_energy(
    data: bytes,
    *,
    min_active_windows: int = MIN_ACTIVE_WINDOWS,
    min_peak_to_floor_ratio: float = MIN_PEAK_TO_FLOOR_RATIO,
) -> None:
    with wave.open(io.BytesIO(data), "rb") as audio:
        samples = array("h")
        samples.frombytes(audio.readframes(audio.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    window_levels: list[float] = []
    for offset in range(0, len(samples), ENERGY_WINDOW_FRAMES):
        window = samples[offset:offset + ENERGY_WINDOW_FRAMES]
        if len(window) < ENERGY_WINDOW_FRAMES // 2:
            continue
        mean = sum(window) / len(window)
        rms = math.sqrt(sum((sample - mean) ** 2 for sample in window) / len(window)) / 32768
        window_levels.append(rms)
    if window_levels:
        ordered = sorted(window_levels)
        noise_floor = ordered[int((len(ordered) - 1) * 0.2)]
        activity_threshold = max(MIN_WINDOW_RMS, noise_floor * min_peak_to_floor_ratio)
        active_indices = [index for index, level in enumerate(window_levels) if level >= activity_threshold]
        activity_span = active_indices[-1] - active_indices[0] + 1 if active_indices else 0
        if len(active_indices) >= min_active_windows and activity_span >= MIN_ACTIVITY_SPAN_WINDOWS:
            return
    raise NoSpeechDetected("no speech energy was detected")


def validate_transcript(value: object) -> str:
    if not isinstance(value, str):
        raise TranscriptionError("speech recognition returned invalid text")
    transcript = " ".join(value.split()).strip()
    if not transcript or len(transcript) > 16_000:
        raise NoSpeechDetected("no usable speech was detected")
    if not any(character.isalnum() for character in transcript):
        raise NoSpeechDetected("only non-speech symbols were detected")
    caption = transcript.casefold()
    bracketed_caption = rf"^[\[(<]\s*(?:{NON_SPEECH_CAPTIONS})\s*[\])>]$"
    if re.fullmatch(bracketed_caption, caption):
        raise NoSpeechDetected("a non-speech caption was detected")
    if any(symbol in transcript for symbol in MUSIC_SYMBOLS):
        without_symbols = "".join(character for character in caption if character not in MUSIC_SYMBOLS).strip(" .,:;!?-_—")
        if re.fullmatch(rf"(?:{NON_SPEECH_CAPTIONS})?", without_symbols):
            raise NoSpeechDetected("music notation was detected")
    if any(pattern.fullmatch(transcript) for pattern in CANNED_NON_SPEECH_TRANSCRIPTS):
        raise NoSpeechDetected("a known canned non-speech transcript was detected")
    return transcript
