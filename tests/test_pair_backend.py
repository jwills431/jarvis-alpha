"""NVIDIA PAIR as the primary model backend, with llama-server as the fallback."""
import json
from unittest.mock import patch

import pytest

from jarvis import backend
from jarvis.config import Config

PAIR = "http://127.0.0.1:11434"
LOCAL = "http://127.0.0.1:8081"
KEY = {"Authorization": "Bearer " + "k" * 40}
MESSAGES = [{"role": "user", "content": "hi"}]
DONE = b"data: [DONE]\n"


@pytest.fixture(autouse=True)
def fresh_pair_state(monkeypatch):
    monkeypatch.setattr(backend, "_pair_retry_at", 0.0)
    monkeypatch.setattr(backend, "_warm_next", float("-inf"))


def pair_config(**overrides):
    return Config(**{"pair_base_url": PAIR, "pair_model": "jarvis-qwen3.5-9b", **overrides}).validate()


def content_line(text):
    return ("data: " + json.dumps({"choices": [{"delta": {"content": text}, "finish_reason": None}]}) + "\n").encode()


class Reply:
    """A fake HTTP response. An exception among the lines is raised at that point."""

    def __init__(self, lines=(), body=b""):
        self._lines = list(lines)
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        for line in self._lines:
            if isinstance(line, BaseException):
                raise line
            yield line

    def read(self, *args):
        return self._body


class Recorder:
    """Stands in for urlopen: records every request and answers per backend."""

    def __init__(self, *, pair=None, local=None):
        self.replies = {"pair": pair, "local": local}
        self.requests = []

    def __call__(self, request, timeout=None):
        which = "pair" if request.full_url.startswith(PAIR) else "local"
        self.requests.append({
            "which": which,
            "url": request.full_url,
            "body": json.loads(request.data) if request.data else None,
            "auth": request.get_header("Authorization"),
            "timeout": timeout,
        })
        reply = self.replies[which]
        if isinstance(reply, BaseException):
            raise reply
        return reply

    @property
    def order(self):
        return [entry["which"] for entry in self.requests]


def run(function, recorder, *args, **kwargs):
    with patch("jarvis.backend._headers", return_value=KEY), \
         patch("jarvis.backend.urllib.request.urlopen", side_effect=recorder):
        result = function(*args, **kwargs)
        return result if result is None or isinstance(result, (str, dict)) else list(result)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def test_pair_is_off_by_default():
    assert Config().validate().pair_base_url == ""


def test_pair_url_must_be_loopback():
    with pytest.raises(ValueError, match="loopback"):
        Config(pair_base_url="http://192.168.7.85:11434", pair_model="m").validate()


def test_pair_needs_a_model():
    with pytest.raises(ValueError, match="pair_model"):
        Config(pair_base_url=PAIR).validate()


def test_pair_reasoning_effort_is_checked():
    with pytest.raises(ValueError, match="pair_reasoning_effort"):
        pair_config(pair_reasoning_effort="lots")


# --------------------------------------------------------------------------- #
# Routing and fallback
# --------------------------------------------------------------------------- #

def test_without_pair_only_llama_server_is_used():
    recorder = Recorder(local=Reply([content_line("Hi"), DONE]))
    events = run(backend.stream_chat, recorder, Config(), MESSAGES)
    assert recorder.order == ["local"]
    sent = recorder.requests[0]
    assert sent["body"]["model"] == Config().model
    assert "reasoning_effort" not in sent["body"]
    assert sent["auth"] == KEY["Authorization"]
    assert events[-1] == b"data: [DONE]\n\n"


def test_pair_is_tried_first_and_never_sees_the_local_key():
    config = pair_config()
    recorder = Recorder(pair=Reply([content_line("Hi"), DONE]), local=Reply([DONE]))
    events = run(backend.stream_chat, recorder, config, MESSAGES)
    assert recorder.order == ["pair"]
    sent = recorder.requests[0]
    assert sent["url"] == PAIR + "/v1/chat/completions"
    assert sent["body"]["model"] == "jarvis-qwen3.5-9b"
    assert sent["body"]["reasoning_effort"] == "none"
    assert sent["auth"] is None
    assert sent["timeout"] == config.pair_timeout_seconds
    assert b"Hi" in events[0]


def test_unreachable_pair_falls_back_to_llama_server():
    recorder = Recorder(pair=OSError("connection refused"), local=Reply([content_line("Local"), DONE]))
    events = run(backend.stream_chat, recorder, pair_config(), MESSAGES)
    assert recorder.order == ["pair", "local"]
    assert recorder.requests[1]["auth"] == KEY["Authorization"]
    assert b"Local" in events[0]


def test_error_event_before_any_output_falls_back():
    error = b'data: {"error":{"message":"no node available"}}\n'
    recorder = Recorder(pair=Reply([error]), local=Reply([content_line("Local"), DONE]))
    events = run(backend.stream_chat, recorder, pair_config(), MESSAGES)
    assert recorder.order == ["pair", "local"]
    assert b"Local" in events[0]


def test_failure_after_output_does_not_switch_backends():
    # Half a reply has already been shown and spoken; starting over locally would repeat it.
    recorder = Recorder(pair=Reply([content_line("Half a"), TimeoutError("read timed out")]),
                        local=Reply([content_line("Again"), DONE]))
    with pytest.raises(backend.BackendError):
        run(backend.stream_chat, recorder, pair_config(), MESSAGES)
    assert recorder.order == ["pair"]


def test_failed_pair_is_skipped_until_the_retry_window_passes(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(backend, "_now", lambda: clock[0])
    config = pair_config(pair_retry_after_seconds=60)
    recorder = Recorder(pair=OSError("node off"), local=Reply([DONE]))
    run(backend.stream_chat, recorder, config, MESSAGES)
    run(backend.stream_chat, recorder, config, MESSAGES)
    assert recorder.order == ["pair", "local", "local"]
    clock[0] += 61
    run(backend.stream_chat, recorder, config, MESSAGES)
    assert recorder.order[-2:] == ["pair", "local"]


def test_tool_turns_fall_back_and_keep_the_grammar_local():
    finish = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'
    recorder = Recorder(pair=OSError("node off"), local=Reply([content_line("ok"), finish, DONE]))
    events = run(backend.stream_chat_tools, recorder, pair_config(), MESSAGES, [], grammar="root ::= x")
    assert recorder.order == ["pair", "local"]
    assert "grammar" not in recorder.requests[0]["body"]
    assert recorder.requests[1]["body"]["grammar"] == "root ::= x"
    assert recorder.requests[1]["body"]["tool_choice"] == "auto"
    assert events[-1] == {"type": "done", "finish_reason": "stop"}


def test_whole_tool_call_through_pair_is_parsed():
    # Ollama delivers a tool call in one delta rather than in fragments.
    lines = [
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":'
        b'{"name":"set_timer","arguments":"{\\"duration_seconds\\":300}"}}]},"finish_reason":null}]}\n',
        b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n',
        DONE,
    ]
    recorder = Recorder(pair=Reply(lines), local=Reply([DONE]))
    events = run(backend.stream_chat_tools, recorder, pair_config(), MESSAGES, [])
    assert recorder.order == ["pair"]
    assert [event for event in events if event["type"] == "tool_call"] == [{
        "type": "tool_call", "id": "call_1", "name": "set_timer",
        "arguments": {"duration_seconds": 300}, "malformed": False,
    }]
    assert events[-1] == {"type": "done", "finish_reason": "tool_calls"}


def test_completion_falls_back_to_llama_server():
    reply = Reply(body=json.dumps({"choices": [{"message": {"content": "Saved."}}]}).encode())
    recorder = Recorder(pair=OSError("node off"), local=reply)
    assert run(backend.complete_chat, recorder, pair_config(), MESSAGES) == "Saved."
    assert recorder.order == ["pair", "local"]


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

def test_health_is_ready_through_pair_while_llama_server_is_down():
    models = Reply(body=json.dumps({"data": [{"id": "jarvis-qwen3.5-9b:latest"}]}).encode())
    recorder = Recorder(pair=models, local=OSError("llama-server down"))
    assert run(backend.health, recorder, pair_config()) == {"status": "ok"}


def test_health_fails_when_neither_backend_can_answer():
    models = Reply(body=json.dumps({"data": [{"id": "some-other-model"}]}).encode())
    recorder = Recorder(pair=models, local=OSError("llama-server down"))
    with pytest.raises(backend.BackendError):
        run(backend.health, recorder, pair_config())


# --------------------------------------------------------------------------- #
# Keeping the node's model loaded
# --------------------------------------------------------------------------- #

def test_pair_keep_alive_is_checked():
    for bad in ("forever", "30 minutes", "1d"):
        with pytest.raises(ValueError, match="pair_keep_alive"):
            pair_config(pair_keep_alive=bad)
    for good in ("", "-1", "1800", "30m", "2h"):
        pair_config(pair_keep_alive=good)


def test_keep_warm_does_nothing_without_pair_or_keep_alive(monkeypatch):
    spawned = []
    monkeypatch.setattr(backend, "_spawn", lambda *args: spawned.append(args))
    assert backend.keep_pair_warm(Config()) is False
    assert backend.keep_pair_warm(pair_config(pair_keep_alive="")) is False
    assert spawned == []


def test_keep_warm_runs_at_most_once_a_minute(monkeypatch):
    clock = [1000.0]
    spawned = []
    monkeypatch.setattr(backend, "_now", lambda: clock[0])
    monkeypatch.setattr(backend, "_spawn", lambda *args: spawned.append(args))
    config = pair_config()
    assert backend.keep_pair_warm(config) is True
    clock[0] += 5  # the browser's next health poll
    assert backend.keep_pair_warm(config) is False
    clock[0] += backend.PAIR_KEEP_WARM_INTERVAL_SECONDS
    assert backend.keep_pair_warm(config) is True
    assert len(spawned) == 2


def test_keep_warm_skips_a_node_known_to_be_down(monkeypatch):
    spawned = []
    monkeypatch.setattr(backend, "_spawn", lambda *args: spawned.append(args))
    monkeypatch.setattr(backend, "_pair_retry_at", backend._now() + 60)
    assert backend.keep_pair_warm(pair_config()) is False
    assert spawned == []


def test_keep_alive_call_uses_the_native_endpoint_without_the_local_key():
    recorder = Recorder(pair=Reply(body=b"{}"))
    run(backend._send_keep_alive, recorder, pair_config(pair_keep_alive="30m"))
    sent = recorder.requests[0]
    assert sent["url"] == PAIR + "/api/generate"
    assert sent["body"] == {"model": "jarvis-qwen3.5-9b", "keep_alive": "30m"}
    assert sent["auth"] is None
    recorder = Recorder(pair=Reply(body=b"{}"))
    run(backend._send_keep_alive, recorder, pair_config(pair_keep_alive="-1"))
    assert recorder.requests[0]["body"]["keep_alive"] == -1  # a number, as Ollama expects


def test_failed_keep_alive_sends_the_next_turn_straight_to_llama_server():
    config = pair_config()
    run(backend._send_keep_alive, Recorder(pair=OSError("node off")), config)
    recorder = Recorder(pair=Reply([DONE]), local=Reply([DONE]))
    run(backend.stream_chat, recorder, config, MESSAGES)
    assert recorder.order == ["local"]
