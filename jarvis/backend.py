from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

from .config import Config

ROOT = Path(__file__).resolve().parent.parent


class BackendError(RuntimeError):
    pass


UNSUPPORTED_SCRIPT_RANGES = (
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x3040, 0x30FF),  # Hiragana and Katakana
    (0xAC00, 0xD7AF),  # Hangul syllables
    (0x0400, 0x052F),  # Cyrillic
    (0x0600, 0x06FF),  # Arabic
)


def count_unsupported_script_characters(value: str) -> int:
    return sum(
        any(start <= ord(character) <= end for start, end in UNSUPPORTED_SCRIPT_RANGES)
        for character in value
    )


def _headers() -> dict[str, str]:
    key_path = ROOT / ".runtime-api-key"
    if not key_path.exists():
        raise BackendError("local model API key is missing")
    key = key_path.read_text(encoding="utf-8").strip()
    if len(key) < 32:
        raise BackendError("local model API key is invalid")
    return {"Authorization": f"Bearer {key}"}


def health(config: Config) -> dict:
    request = urllib.request.Request(f"{config.llama_base_url}/health", headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read(65_536))
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        raise BackendError("local model server is unavailable") from exc


def sanitize_sse_line(raw_line: bytes) -> bytes | None:
    if len(raw_line) > 65_536 or not raw_line.startswith(b"data: "):
        return None
    value = raw_line[6:].strip()
    if value == b"[DONE]":
        return b"data: [DONE]\n\n"
    try:
        event = json.loads(value)
        choice = event["choices"][0]
        content = choice.get("delta", {}).get("content")
        finish_reason = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None
    clean = {"choices": [{"delta": {}, "finish_reason": finish_reason}]}
    if isinstance(content, str):
        clean["choices"][0]["delta"]["content"] = content
    return b"data: " + json.dumps(clean, separators=(",", ":")).encode("utf-8") + b"\n\n"


def stream_chat(config: Config, messages: list[dict]) -> Iterable[bytes]:
    payload = json.dumps(
        {
            "model": config.model,
            "messages": messages,
            "stream": True,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{config.llama_base_url}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", **_headers()},
        method="POST",
    )
    try:
        unsupported_script_chars = 0
        with urllib.request.urlopen(request, timeout=config.request_timeout_seconds) as response:
            for raw_line in response:
                clean = sanitize_sse_line(raw_line)
                if clean:
                    if clean != b"data: [DONE]\n\n":
                        event = json.loads(clean[6:].strip())
                        content = event["choices"][0].get("delta", {}).get("content", "")
                        unsupported_script_chars += count_unsupported_script_characters(content)
                        if unsupported_script_chars >= 3:
                            raise BackendError("local model generated unsupported non-English text")
                    yield clean
    except (OSError, urllib.error.HTTPError) as exc:
        raise BackendError("local model request failed") from exc


def complete_chat(
    config: Config,
    messages: list[dict],
    *,
    max_tokens: int = 384,
    temperature: float = 0.0,
) -> str:
    payload = json.dumps({
        "model": config.model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{config.llama_base_url}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", **_headers()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.request_timeout_seconds) as response:
            result = json.loads(response.read(262_144))
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise BackendError("local model returned an invalid completion")
        if count_unsupported_script_characters(content) >= 3:
            raise BackendError("local model generated unsupported non-English text")
        return content
    except (OSError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, urllib.error.HTTPError) as exc:
        raise BackendError("local model completion failed") from exc
