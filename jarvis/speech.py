from __future__ import annotations

import os
import re
import subprocess
import threading
from functools import lru_cache
from pathlib import Path

from .config import Config

SAY = Path("/usr/bin/say")
SPEECH_RATE_MIN = 120
SPEECH_RATE_MAX = 350
VOICE_LINE = re.compile(r"^(.+?)\s+([a-z]{2}_[A-Z0-9]{2,3})\s+#")


class SpeechError(RuntimeError):
    pass


_lock = threading.Lock()
_active: subprocess.Popen | None = None


def runtime_ready(config: Config) -> bool:
    return config.tts_enabled and SAY.is_file() and os.access(SAY, os.X_OK)


def parse_installed_voices(value: str) -> tuple[dict[str, str], ...]:
    voices: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in value.splitlines():
        match = VOICE_LINE.match(line)
        if not match:
            continue
        name = match.group(1).strip()
        locale = match.group(2)
        if not name or name in seen:
            continue
        seen.add(name)
        voices.append({"name": name, "locale": locale})
    return tuple(voices)


@lru_cache(maxsize=1)
def installed_voices() -> tuple[dict[str, str], ...]:
    if not SAY.is_file() or not os.access(SAY, os.X_OK):
        raise SpeechError("speech synthesis is unavailable")
    try:
        result = subprocess.run(
            [str(SAY), "-v", "?"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SpeechError("installed voices are unavailable") from exc
    voices = parse_installed_voices(result.stdout[:65_536])
    if not voices:
        raise SpeechError("installed voices are unavailable")
    return voices


def english_voices() -> tuple[dict[str, str], ...]:
    return tuple(voice for voice in installed_voices() if voice["locale"].startswith("en_"))


def resolve_speech_options(config: Config, voice: object = None, rate: object = None) -> tuple[str, int]:
    selected_voice = config.tts_voice
    selected_rate = config.tts_rate
    if voice is not None:
        if not isinstance(voice, str) or voice not in {item["name"] for item in english_voices()}:
            raise SpeechError("speech voice is invalid")
        selected_voice = voice
    if rate is not None:
        if type(rate) is not int or not SPEECH_RATE_MIN <= rate <= SPEECH_RATE_MAX:
            raise SpeechError("speech rate is invalid")
        selected_rate = rate
    return selected_voice, selected_rate


def validate_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        raise SpeechError("speech text is required")
    text = value.strip()
    if not text or len(text) > limit:
        raise SpeechError("speech text is invalid")
    return text


def prepare_speech_text(value: str, word_pronunciations: tuple[str, ...] = ()) -> str:
    """Make explicitly spelled names word-like for TTS without changing chat text."""
    prepared = value
    for exact in word_pronunciations:
        letters = re.sub(r"[^A-Za-z]", "", exact)
        if len(letters) < 3 or letters != letters.upper():
            continue
        if not re.fullmatch(r"[A-Z][A-Z'’.-]{1,79}", exact):
            continue
        spoken = exact[0] + exact[1:].lower()
        prepared = re.sub(
            rf"(?<![A-Za-z]){re.escape(exact)}(?![A-Za-z])",
            lambda _match: spoken,
            prepared,
        )
    return prepared


def speak(
    config: Config,
    value: object,
    word_pronunciations: tuple[str, ...] = (),
    *,
    voice: object = None,
    rate: object = None,
) -> None:
    global _active
    if not runtime_ready(config):
        raise SpeechError("speech synthesis is unavailable")
    text = validate_text(value, config.max_tts_chars)
    selected_voice, selected_rate = resolve_speech_options(config, voice, rate)
    encoded = prepare_speech_text(text, word_pronunciations).encode("utf-8")
    process: subprocess.Popen | None = None
    with _lock:
        _terminate(_active)
        _active = None
        try:
            process = subprocess.Popen(
                [str(SAY), "-v", selected_voice, "-r", str(selected_rate)],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if process.stdin is None:
                raise OSError("speech input is unavailable")
            process.stdin.write(encoded)
            process.stdin.close()
        except (OSError, BrokenPipeError) as exc:
            _terminate(process)
            raise SpeechError("speech synthesis failed") from exc
        assert process is not None
        _active = process
    timed_out = False
    try:
        process.wait(timeout=config.tts_timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    finally:
        with _lock:
            was_current = _active is process
            if was_current:
                _active = None
    if timed_out:
        raise SpeechError("speech synthesis timed out")
    if process.returncode not in (0, None) and was_current:
        raise SpeechError("speech synthesis failed")


def stop() -> None:
    global _active
    with _lock:
        process = _active
        _active = None
        _terminate(process)


def is_speaking() -> bool:
    with _lock:
        return _active is not None and _active.poll() is None


def _terminate(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
