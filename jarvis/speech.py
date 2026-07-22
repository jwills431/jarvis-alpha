from __future__ import annotations

import json
import os
import re
import selectors
import subprocess
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path

from .config import Config

ROOT = Path(__file__).resolve().parent.parent
SAY = Path("/usr/bin/say")
AFPLAY = Path("/usr/bin/afplay")
PIPER_SYNTHESIZE = ROOT / "scripts" / "piper_synthesize.py"
SPEECH_RATE_MIN = 120
SPEECH_RATE_MAX = 350
# Piper controls speed through a length scale (1.0 == normal). The configured
# baseline WPM maps to 1.0; faster rates shorten it, slower rates lengthen it.
PIPER_BASELINE_RATE = 190
PIPER_LENGTH_SCALE_MIN = 0.5
PIPER_LENGTH_SCALE_MAX = 2.0
# Loading the voice costs about a second; synthesis costs a fraction of that.
# One resident worker holds the model so the pause between spoken sentences is
# synthesis time rather than a cold start repeated per phrase.
PIPER_READY_TIMEOUT = 30.0
VOICE_LINE = re.compile(r"^(.+?)\s+([a-z]{2}_[A-Z0-9]{2,3})\s+#")
PIPER_LOCALE = re.compile(r"([a-z]{2}_[A-Z]{2})")


class SpeechError(RuntimeError):
    pass


_lock = threading.Lock()
_active: subprocess.Popen | None = None
# Monotonic speech generation. Claiming the channel for a new utterance and
# stopping speech both advance it. Piper renders a whole phrase before playing
# it, so playback must re-check that its generation still owns the channel; a
# stop that arrives between rendering and playback would otherwise be silently
# swallowed and the interrupted phrase would still be spoken.
_generation = 0


def _claim() -> int:
    """Cancel any current speech and take the channel. Caller holds _lock."""
    global _active, _generation
    _terminate(_active)
    _active = None
    _generation += 1
    return _generation


def _release(process: subprocess.Popen, generation: int) -> bool:
    """Give the channel back. Returns False if superseded. Caller holds _lock."""
    global _active
    if _active is not process or _generation != generation:
        return False
    _active = None
    return True


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _say_runtime_ready() -> bool:
    return SAY.is_file() and os.access(SAY, os.X_OK)


def runtime_ready(config: Config) -> bool:
    """True when at least one speech engine can synthesize."""
    if not config.tts_enabled:
        return False
    return _say_runtime_ready() or _piper_runtime_ready(config)


def _piper_runtime_ready(config: Config) -> bool:
    interpreter = _resolve(config.piper_python)
    model = _resolve(config.piper_voice)
    return (
        interpreter.is_file()
        and os.access(interpreter, os.X_OK)
        and PIPER_SYNTHESIZE.is_file()
        and model.is_file()
        and AFPLAY.is_file()
        and os.access(AFPLAY, os.X_OK)
    )


def parse_installed_voices(value: str) -> tuple[dict[str, str], ...]:
    """Parse `say -v ?` output. Every entry is a macOS `say` voice."""
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
        voices.append({"name": name, "locale": locale, "engine": "say"})
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


def piper_locale(config: Config) -> str:
    match = PIPER_LOCALE.match(Path(config.piper_voice).name)
    return match.group(1) if match else "en_GB"


def piper_voice_entry(config: Config) -> dict[str, str]:
    return {"name": config.piper_voice_name, "locale": piper_locale(config), "engine": "piper"}


def available_voices(config: Config) -> tuple[dict[str, str], ...]:
    """Every voice that can be spoken right now, each tagged with its engine.

    The engine is a property of the chosen voice rather than a global mode, so
    the installed macOS voices and a provisioned Piper voice can be compared
    side by side without restarting or editing configuration.
    """
    voices: list[dict[str, str]] = []
    if _say_runtime_ready():
        try:
            voices.extend(english_voices())
        except SpeechError:
            pass
    if _piper_runtime_ready(config):
        piper = piper_voice_entry(config)
        # A name collision would make the selection ambiguous on the way back in.
        if any(voice["name"] == piper["name"] for voice in voices):
            piper = dict(piper, name=f"{piper['name']} (Piper)")
        voices.append(piper)
    return tuple(voices)


def voice_engine(config: Config, voice: str) -> str:
    """Which engine speaks this voice.

    Falls back to the built-in engine for any voice that cannot be matched, so an
    unenumerable voice list degrades to `say` instead of failing. Selection of an
    invalid voice is rejected separately by resolve_speech_options.
    """
    if not _piper_runtime_ready(config):
        return "say"
    for entry in available_voices(config):
        if entry["name"] == voice:
            return entry["engine"]
    return "say"


def default_voice(config: Config) -> str:
    """The configured default, falling back to any available voice."""
    voices = available_voices(config)
    names = {voice["name"] for voice in voices}
    preferred = config.piper_voice_name if config.tts_engine == "piper" else config.tts_voice
    if preferred in names:
        return preferred
    fallback = config.tts_voice if config.tts_engine == "piper" else config.piper_voice_name
    if fallback in names:
        return fallback
    return voices[0]["name"] if voices else preferred


def length_scale_for_rate(rate: int) -> float:
    scale = PIPER_BASELINE_RATE / rate
    return round(max(PIPER_LENGTH_SCALE_MIN, min(PIPER_LENGTH_SCALE_MAX, scale)), 3)


def piper_command(config: Config) -> list[str]:
    # Only paths and flags; the utterance travels on standard input so it never
    # appears in an argument vector.
    return [
        str(_resolve(config.piper_python)),
        str(PIPER_SYNTHESIZE),
        "--serve",
        "--model", str(_resolve(config.piper_voice)),
    ]


class _PiperWorker:
    """A resident Piper process holding the loaded voice model."""

    def __init__(self, process: subprocess.Popen) -> None:
        self.process = process
        self._buffer = bytearray()

    def alive(self) -> bool:
        return self.process.poll() is None

    def read_response(self, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        try:
            while True:
                if b"\n" in self._buffer:
                    line, _, rest = bytes(self._buffer).partition(b"\n")
                    self._buffer = bytearray(rest)
                    try:
                        return json.loads(line)
                    except ValueError as exc:
                        raise SpeechError("speech synthesis failed") from exc
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise SpeechError("speech synthesis timed out")
                chunk = os.read(self.process.stdout.fileno(), 65_536)
                if not chunk:
                    raise SpeechError("speech synthesis failed")
                self._buffer.extend(chunk)
        finally:
            selector.close()

    def terminate(self) -> None:
        _terminate(self.process)
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        # Close both pipes explicitly. A worker that is restarted after a crash
        # would otherwise leak a descriptor pair on every restart.
        for pipe in (self.process.stdin, self.process.stdout):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass


_worker_lock = threading.Lock()
_worker: _PiperWorker | None = None


def _start_worker(config: Config) -> _PiperWorker:
    try:
        process = subprocess.Popen(
            piper_command(config),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise SpeechError("speech synthesis is unavailable") from exc
    if process.stdin is None or process.stdout is None:
        _terminate(process)
        raise SpeechError("speech synthesis is unavailable")
    worker = _PiperWorker(process)
    # Wait for the load to finish so the first phrase is not charged for it and
    # a model that cannot load fails here rather than mid-reply.
    try:
        if worker.read_response(PIPER_READY_TIMEOUT).get("status") != "ready":
            raise SpeechError("speech synthesis is unavailable")
    except SpeechError:
        worker.terminate()
        raise
    return worker


def _render_piper(config: Config, text: str, output_path: str, length_scale: float) -> None:
    """Render one phrase through the resident worker, restarting it once if it died."""
    global _worker
    request = json.dumps(
        {"text": text, "output_file": output_path, "length_scale": length_scale},
        ensure_ascii=False,
    ).encode("utf-8") + b"\n"
    with _worker_lock:
        for attempt in (1, 2):
            if _worker is None or not _worker.alive():
                _worker = _start_worker(config)
            try:
                assert _worker.process.stdin is not None
                _worker.process.stdin.write(request)
                _worker.process.stdin.flush()
                response = _worker.read_response(config.tts_timeout_seconds)
            except (OSError, BrokenPipeError, SpeechError):
                # A worker that died between phrases is replaced once; a second
                # failure is reported rather than retried indefinitely.
                if _worker is not None:
                    _worker.terminate()
                _worker = None
                if attempt == 2:
                    raise SpeechError("speech synthesis failed")
                continue
            if response.get("status") != "ok":
                raise SpeechError("speech synthesis failed")
            return


def shutdown() -> None:
    """Stop speech and release the resident worker."""
    global _worker
    stop()
    with _worker_lock:
        if _worker is not None:
            _worker.terminate()
            _worker = None


def resolve_speech_options(config: Config, voice: object = None, rate: object = None) -> tuple[str, int]:
    selected_voice = default_voice(config)
    selected_rate = config.tts_rate
    if voice is not None:
        if not isinstance(voice, str) or voice not in {item["name"] for item in available_voices(config)}:
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
    if not runtime_ready(config):
        raise SpeechError("speech synthesis is unavailable")
    text = validate_text(value, config.max_tts_chars)
    selected_voice, selected_rate = resolve_speech_options(config, voice, rate)
    prepared = prepare_speech_text(text, word_pronunciations)
    if voice_engine(config, selected_voice) == "piper":
        _speak_piper(config, prepared, selected_rate)
    else:
        _speak_say(config, prepared, selected_voice, selected_rate)


def _speak_say(config: Config, prepared: str, selected_voice: str, selected_rate: int) -> None:
    global _active
    encoded = prepared.encode("utf-8")
    process: subprocess.Popen | None = None
    with _lock:
        generation = _claim()
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
            was_current = _release(process, generation)
    if timed_out:
        raise SpeechError("speech synthesis timed out")
    if process.returncode not in (0, None) and was_current:
        raise SpeechError("speech synthesis failed")


def _speak_piper(config: Config, prepared: str, selected_rate: int) -> None:
    length_scale = length_scale_for_rate(selected_rate)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="jarvis-tts-", suffix=".wav", delete=False) as handle:
            temp_path = handle.name
        # Claiming here cancels any current speech and marks this phrase as the
        # one that owns the channel, so a stop arriving during the render is
        # detected before playback starts.
        with _lock:
            generation = _claim()
        _render_piper(config, prepared, temp_path, length_scale)
        _play_audio(config, temp_path, generation)
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


def _play_audio(config: Config, path: str, generation: int | None = None) -> None:
    global _active
    process: subprocess.Popen | None = None
    with _lock:
        if generation is not None and _generation != generation:
            # A stop or newer utterance arrived while this phrase was rendering.
            # The finished file is discarded rather than spoken after the stop.
            return
        claimed = _claim()
        try:
            process = subprocess.Popen(
                [str(AFPLAY), path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            _terminate(process)
            raise SpeechError("speech playback failed") from exc
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
            was_current = _release(process, claimed)
    if timed_out:
        raise SpeechError("speech playback timed out")
    if process.returncode not in (0, None) and was_current:
        raise SpeechError("speech playback failed")


def stop() -> None:
    global _active, _generation
    with _lock:
        process = _active
        _active = None
        _generation += 1
        _terminate(process)


def is_speaking() -> bool:
    with _lock:
        return _active is not None and _active.poll() is None


def _terminate(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
