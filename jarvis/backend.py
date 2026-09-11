from __future__ import annotations

import http.client
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

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


# --------------------------------------------------------------------------- #
# Backend selection: NVIDIA PAIR first when configured, llama-server as fallback
# --------------------------------------------------------------------------- #
#
# llama-server and Fish share one RTX 3060 here, and sharing it slowed both about
# 2.4x (measured 2026-09-10), so the first spoken word landed after the text. PAIR's
# loopback proxy forwards a request to one LAN node running Ollama, which lets the
# model run on another machine's GPU. llama-server stays up as the fallback: a
# request that fails before producing anything is retried locally, and PAIR is then
# skipped for `pair_retry_after_seconds` so a node that is off does not cost a
# timeout on every turn. Once output has started it belongs to that backend —
# switching mid-reply would repeat or garble what has already been said.

# Failures that mean "this backend did not answer": refused or dropped connections,
# timeouts and HTTP errors are all OSErrors; a truncated response is not.
_TRANSPORT_ERRORS = (OSError, http.client.HTTPException)


@dataclass(frozen=True)
class _Target:
    pair: bool
    base_url: str
    model: str
    timeout: int
    extra: dict = field(default_factory=dict)


_pair_lock = threading.Lock()
_pair_retry_at = 0.0


def _now() -> float:
    return time.monotonic()


def _targets(config: Config) -> list[_Target]:
    targets = []
    if config.pair_base_url:
        with _pair_lock:
            ready = _now() >= _pair_retry_at
        if ready:
            extra = {"reasoning_effort": config.pair_reasoning_effort} if config.pair_reasoning_effort else {}
            targets.append(_Target(True, config.pair_base_url.rstrip("/"), config.pair_model,
                                   config.pair_timeout_seconds, extra))
    targets.append(_Target(False, config.llama_base_url.rstrip("/"), config.model,
                           config.request_timeout_seconds))
    return targets


def _pair_failed(config: Config, exc: BaseException) -> None:
    global _pair_retry_at
    with _pair_lock:
        _pair_retry_at = _now() + config.pair_retry_after_seconds
    # The class name only: an exception message can carry request details.
    sys.stderr.write(
        f"PAIR model request failed ({type(exc).__name__}); "
        f"using llama-server for {config.pair_retry_after_seconds}s\n"
    )


def _open(target: _Target, body: dict, grammar: str | None = None):
    payload = {**body, "model": target.model, **target.extra}
    # GBNF is a llama.cpp extension that Ollama does not honour.
    if grammar and not target.pair:
        payload["grammar"] = grammar
    # The llama-server key is for llama-server. PAIR forwards requests to another
    # machine, so it must never see it.
    headers = {"Content-Type": "application/json"}
    if not target.pair:
        headers.update(_headers())
    request = urllib.request.Request(
        f"{target.base_url}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=target.timeout)


def _is_error_event(raw_line: bytes) -> bool:
    if not raw_line.startswith(b"data: {"):
        return False
    try:
        event = json.loads(raw_line[6:])
    except ValueError:
        return False
    return isinstance(event, dict) and "error" in event and "choices" not in event


def _chat_lines(config: Config, body: dict, grammar: str | None = None) -> Iterator[bytes]:
    """Yield the raw SSE lines of one streamed completion from the first backend that answers."""
    failure: BaseException | None = None
    for target in _targets(config):
        started = False
        try:
            with _open(target, body, grammar) as response:
                for raw_line in response:
                    if not started:
                        if _is_error_event(raw_line):
                            raise BackendError("model backend reported an error")
                        is_event = raw_line.startswith(b"data: {") and b'"choices"' in raw_line
                        if not (is_event or raw_line.startswith(b"data: [DONE]")):
                            continue
                        started = True
                    yield raw_line
            return
        except (*_TRANSPORT_ERRORS, BackendError) as exc:
            if target.pair:
                _pair_failed(config, exc)
            if started:
                raise BackendError("local model request failed") from exc
            failure = exc
    raise BackendError("local model request failed") from failure


def _pair_serves_model(config: Config) -> bool:
    request = urllib.request.Request(f"{config.pair_base_url.rstrip('/')}/v1/models")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            listed = json.loads(response.read(262_144)).get("data") or []
    except (*_TRANSPORT_ERRORS, ValueError, AttributeError):
        return False
    names = {entry.get("id") for entry in listed if isinstance(entry, dict)}
    return config.pair_model in names or f"{config.pair_model}:latest" in names


def health(config: Config) -> dict:
    try:
        request = urllib.request.Request(f"{config.llama_base_url}/health", headers=_headers())
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read(65_536))
    except (*_TRANSPORT_ERRORS, ValueError, BackendError) as exc:
        failure = exc
    # Replies can still be served through PAIR while llama-server is down.
    if config.pair_base_url and _pair_serves_model(config):
        return {"status": "ok"}
    raise BackendError("local model server is unavailable") from failure


# Ollama unloads an idle model after 5 minutes, and a reload costs the next turn
# ~4 s (19 s the first time). Neither OLLAMA_KEEP_ALIVE on the node nor keep_alive
# on the OpenAI endpoint took effect through PAIR, but Ollama's native keep-alive
# call does, and it sticks until the model is unloaded. It also loads the model if
# it is not loaded, so it doubles as a pre-warm after the node restarts.
PAIR_KEEP_WARM_INTERVAL_SECONDS = 60

_warm_lock = threading.Lock()
_warm_next = float("-inf")


def _spawn(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True, name="pair-keep-warm").start()


def keep_pair_warm(config: Config) -> bool:
    """Ask PAIR's node to keep the model loaded — in the background, at most once a minute."""
    global _warm_next
    if not (config.pair_base_url and config.pair_keep_alive):
        return False
    with _pair_lock:
        if _now() < _pair_retry_at:
            return False  # known to be down; the retry window decides when to try again
    with _warm_lock:
        now = _now()
        if now < _warm_next:
            return False
        _warm_next = now + PAIR_KEEP_WARM_INTERVAL_SECONDS
    _spawn(_send_keep_alive, config)
    return True


def _send_keep_alive(config: Config) -> None:
    value = config.pair_keep_alive
    body = {"model": config.pair_model, "keep_alive": int(value) if value.lstrip("-").isdigit() else value}
    request = urllib.request.Request(
        f"{config.pair_base_url.rstrip('/')}/api/generate",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.pair_timeout_seconds) as response:
            response.read(65_536)
    except _TRANSPORT_ERRORS as exc:
        # Learning the node is gone here spares the next turn its timeout.
        _pair_failed(config, exc)


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
    body = {
        "messages": messages,
        "stream": True,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    unsupported_script_chars = 0
    for raw_line in _chat_lines(config, body):
        clean = sanitize_sse_line(raw_line)
        if clean:
            if clean != b"data: [DONE]\n\n":
                event = json.loads(clean[6:].strip())
                content = event["choices"][0].get("delta", {}).get("content", "")
                unsupported_script_chars += count_unsupported_script_characters(content)
                if unsupported_script_chars >= 3:
                    raise BackendError("local model generated unsupported non-English text")
            yield clean


def stream_chat_tools(
    config: Config,
    messages: list[dict],
    tools: list[dict],
    *,
    grammar: str | None = None,
) -> Iterable[dict]:
    """Stream a tool-aware completion, yielding structured events.

    Talks to an OpenAI-compatible endpoint with a `tools` array and
    tool_choice="auto" — llama.cpp's native tool-calling (server started with
    --jinja), or Ollama behind PAIR. Content is streamed token by token so the
    final spoken answer keeps the low-latency TTS path; tool-call deltas are
    accumulated and parsed. (Ollama delivers a tool call whole, not in fragments;
    the accumulator handles both.)

    Yields dicts, one of:
      {"type": "content", "text": str}                       # forward to client
      {"type": "tool_call", "id", "name", "arguments"|None,  # a proposed call
       "malformed": bool}
      {"type": "done", "finish_reason": str|None}            # end of this turn

    A grammar, when provided, is passed through for llama.cpp builds that
    constrain via GBNF rather than native tool-calling; the native path leaves it
    None, and it is never sent to PAIR.
    """
    body: dict = {
        "messages": messages,
        "stream": True,
        # Lower, tool-specific temperature for more reliable tool-calling on a 7B.
        "temperature": config.tool_temperature,
        "max_tokens": config.max_tokens,
        "tools": tools,
        "tool_choice": "auto",
    }
    # Tool-call fragments arrive across many deltas, keyed by their index; each
    # carries an id, a function name, and a slice of the arguments JSON string.
    calls: dict[int, dict] = {}
    finish_reason: str | None = None
    unsupported_script_chars = 0
    for raw_line in _chat_lines(config, body, grammar):
        if len(raw_line) > 262_144 or not raw_line.startswith(b"data: "):
            continue
        value = raw_line[6:].strip()
        if value == b"[DONE]":
            break
        try:
            event = json.loads(value)
            choice = event["choices"][0]
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            continue
        # Streaming servers put the incremental payload in `delta`; some
        # llama.cpp builds emit a single non-streamed `message` frame for
        # a tool call. Accept either so calls are never missed.
        delta = choice.get("delta") or choice.get("message") or {}
        content = delta.get("content")
        if isinstance(content, str) and content:
            unsupported_script_chars += count_unsupported_script_characters(content)
            if unsupported_script_chars >= 3:
                raise BackendError("local model generated unsupported non-English text")
            yield {"type": "content", "text": content}
        for fragment in delta.get("tool_calls") or []:
            if not isinstance(fragment, dict):
                continue
            index = fragment.get("index", 0)
            slot = calls.setdefault(index, {"id": None, "name": None, "arguments": ""})
            if fragment.get("id"):
                slot["id"] = fragment["id"]
            function = fragment.get("function") or {}
            if function.get("name"):
                slot["name"] = function["name"]
            argument_fragment = function.get("arguments")
            if isinstance(argument_fragment, str):
                slot["arguments"] += argument_fragment
        if choice.get("finish_reason"):
            finish_reason = choice["finish_reason"]
    for _, slot in sorted(calls.items()):
        raw_arguments = slot["arguments"].strip()
        parsed: object = {}
        malformed = False
        if raw_arguments:
            try:
                parsed = json.loads(raw_arguments)
            except (ValueError, json.JSONDecodeError):
                parsed = None
                malformed = True
        yield {
            "type": "tool_call",
            "id": slot["id"],
            "name": slot["name"],
            "arguments": parsed,
            "malformed": malformed,
        }
    yield {"type": "done", "finish_reason": finish_reason}


def complete_chat(
    config: Config,
    messages: list[dict],
    *,
    max_tokens: int = 384,
    temperature: float = 0.0,
) -> str:
    body = {
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    failure: BaseException | None = None
    for target in _targets(config):
        try:
            with _open(target, body) as response:
                result = json.loads(response.read(262_144))
            content = result["choices"][0]["message"]["content"]
        except (*_TRANSPORT_ERRORS, KeyError, IndexError, TypeError, ValueError) as exc:
            if target.pair:
                _pair_failed(config, exc)
            failure = exc
            continue
        if not isinstance(content, str) or not content.strip():
            raise BackendError("local model returned an invalid completion")
        if count_unsupported_script_characters(content) >= 3:
            raise BackendError("local model generated unsupported non-English text")
        return content
    raise BackendError("local model completion failed") from failure
