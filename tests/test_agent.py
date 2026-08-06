import json
from unittest.mock import patch

import pytest

from jarvis import agent, backend
from jarvis.config import Config
from jarvis.tools import Tool, ToolRegistry, default_registry


class _FakeResponse:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self._lines)


def _run_stream_tools(lines):
    with patch("jarvis.backend._headers", return_value={}), \
         patch("jarvis.backend.urllib.request.urlopen", return_value=_FakeResponse(lines)):
        return list(backend.stream_chat_tools(Config(), [{"role": "user", "content": "hi"}], []))


def test_backend_parses_streamed_tool_call_fragments():
    events = _run_stream_tools([
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"get_time","arguments":""}}]}}]}\n',
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{}"}}]}}]}\n',
        b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n',
        b"data: [DONE]\n",
    ])
    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["name"] == "get_time"
    assert calls[0]["arguments"] == {}
    assert not calls[0]["malformed"]
    assert events[-1] == {"type": "done", "finish_reason": "tool_calls"}


def test_backend_parses_single_message_frame_tool_call():
    events = _run_stream_tools([
        b'data: {"choices":[{"message":{"tool_calls":[{"id":"c2","function":{"name":"get_time","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}\n',
        b"data: [DONE]\n",
    ])
    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 1 and calls[0]["name"] == "get_time"


def test_backend_flags_malformed_arguments():
    events = _run_stream_tools([
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c3","function":{"name":"get_time","arguments":"{bad"}}]}}]}\n',
        b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n',
        b"data: [DONE]\n",
    ])
    calls = [e for e in events if e["type"] == "tool_call"]
    assert calls[0]["malformed"] is True and calls[0]["arguments"] is None


def test_stream_chat_tools_uses_tool_temperature():
    captured = {}

    def fake(request, timeout=None):
        captured["body"] = json.loads(request.data)
        return _FakeResponse([b"data: [DONE]\n"])

    with patch("jarvis.backend._headers", return_value={}), \
         patch("jarvis.backend.urllib.request.urlopen", side_effect=fake):
        list(backend.stream_chat_tools(Config(tool_temperature=0.25),
                                       [{"role": "user", "content": "hi"}], []))
    assert captured["body"]["temperature"] == 0.25  # tool_temperature, not the conversational one


def test_backend_streams_plain_content():
    events = _run_stream_tools([
        b'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}\n',
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n',
        b"data: [DONE]\n",
    ])
    assert [e for e in events if e["type"] == "content"] == [{"type": "content", "text": "Hello"}]


# --------------------------------------------------------------------------- #
# Helpers: scripted backend + event collection
# --------------------------------------------------------------------------- #

def content(text):
    return {"type": "content", "text": text}


def tool_call(name, arguments, *, malformed=False, call_id="c1"):
    return {"type": "tool_call", "id": call_id, "name": name, "arguments": arguments, "malformed": malformed}


def done(reason="stop"):
    return {"type": "done", "finish_reason": reason}


def script_backend(monkeypatch, turns):
    """Make backend.stream_chat_tools replay one scripted turn per model call.

    `turns` is a list of event-lists; each model call consumes the next. After
    the scripts run out, a plain final answer is returned so a loop always ends.
    """
    calls = {"n": 0}
    turns_iter = iter(turns)

    def fake(config, messages, tools, grammar=None):
        calls["n"] += 1
        try:
            return iter(next(turns_iter))
        except StopIteration:
            return iter([content("(default answer)"), done("stop")])

    monkeypatch.setattr(agent.backend, "stream_chat_tools", fake)
    return calls


def collect(generator):
    """Drive an SSE byte generator into (text, jarvis_events, terminated)."""
    text_parts, jarvis_events, terminated = [], [], False
    for chunk in generator:
        for line in chunk.decode("utf-8").split("\n"):
            if not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data == "[DONE]":
                terminated = True
                continue
            obj = json.loads(data)
            if "jarvis" in obj:
                jarvis_events.append(obj["jarvis"])
            else:
                text_parts.append(obj["choices"][0]["delta"].get("content", ""))
    return "".join(text_parts), jarvis_events, terminated


def make_config(tmp_path, **overrides):
    return Config(tools_enabled=True, tool_audit_path=str(tmp_path / "audit.jsonl"), **overrides)


def read_audit(config):
    from pathlib import Path
    path = Path(config.tool_audit_path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "what time is it?"}]


# --------------------------------------------------------------------------- #
# Read-only tool: the happy path
# --------------------------------------------------------------------------- #

def test_get_time_executes_and_answer_streams(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    script_backend(monkeypatch, [
        [tool_call("get_time", {}), done("tool_calls")],
        [content("It is "), content("10 o'clock."), done("stop")],
    ])
    text, events, terminated = collect(
        agent.run(config, default_registry(), MESSAGES, agent.PendingActions())
    )
    assert terminated
    assert text == "It is 10 o'clock."
    results = [e for e in events if e["kind"] == "tool_result"]
    assert len(results) == 1
    assert results[0]["name"] == "get_time"
    assert results[0]["status"] == "ok"
    assert "iso" in results[0]["result"]  # the real handler actually ran
    events_logged = [r["event"] for r in read_audit(config)]
    assert "executed" in events_logged


# --------------------------------------------------------------------------- #
# Malformed / invalid calls fail safe (never execute)
# --------------------------------------------------------------------------- #

def test_malformed_call_is_rejected_not_executed(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    script_backend(monkeypatch, [
        [tool_call("get_time", None, malformed=True), done("tool_calls")],
        [content("Sorry, I could not read that."), done("stop")],
    ])
    text, events, terminated = collect(
        agent.run(config, default_registry(), MESSAGES, agent.PendingActions())
    )
    assert terminated
    results = [e for e in events if e["kind"] == "tool_result"]
    assert results and results[0]["status"] == "error"
    # The handler never ran, so no result ever carried a real time field.
    assert all("result" not in e or "iso" not in (e.get("result") or {}) for e in results)
    assert "rejected" in [r["event"] for r in read_audit(config)]
    assert text  # the model still gets to answer


def test_unknown_tool_is_rejected(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    script_backend(monkeypatch, [
        [tool_call("delete_everything", {}), done("tool_calls")],
        [content("I don't have that tool."), done("stop")],
    ])
    _, events, terminated = collect(
        agent.run(config, default_registry(), MESSAGES, agent.PendingActions())
    )
    assert terminated
    results = [e for e in events if e["kind"] == "tool_result"]
    assert results and results[0]["status"] == "error"


def test_schema_violation_is_rejected(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    script_backend(monkeypatch, [
        [tool_call("get_time", {"unexpected": 1}), done("tool_calls")],
        [content("done"), done("stop")],
    ])
    _, events, _ = collect(agent.run(config, default_registry(), MESSAGES, agent.PendingActions()))
    results = [e for e in events if e["kind"] == "tool_result"]
    assert results and results[0]["status"] == "error"


# --------------------------------------------------------------------------- #
# Iteration cap: the loop cannot spin
# --------------------------------------------------------------------------- #

def test_iteration_cap_stops_the_loop(tmp_path, monkeypatch):
    config = make_config(tmp_path, tool_max_iterations=3)
    calls = {"n": 0}

    def always_calls_a_tool(config, messages, tools, grammar=None):
        calls["n"] += 1
        return iter([tool_call("get_time", {}), done("tool_calls")])

    monkeypatch.setattr(agent.backend, "stream_chat_tools", always_calls_a_tool)
    text, events, terminated = collect(
        agent.run(config, default_registry(), MESSAGES, agent.PendingActions())
    )
    assert terminated
    assert calls["n"] == 3  # never exceeds the cap
    assert "limit on tool steps" in text


# --------------------------------------------------------------------------- #
# Side-effecting tool: the confirmation gate
# --------------------------------------------------------------------------- #

def side_effect_registry():
    registry = ToolRegistry()

    def handler(arguments, config):
        return {"ran": True, "label": arguments["label"]}

    registry.register(Tool(
        name="do_danger",
        description="a side-effecting action",
        parameters={"type": "object", "properties": {"label": {"type": "string"}}, "required": ["label"]},
        handler=handler,
        side_effects=True,
    ))
    return registry


def _pause_for_approval(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    pending = agent.PendingActions()
    script_backend(monkeypatch, [
        [tool_call("do_danger", {"label": "x"}), done("tool_calls")],
    ])
    text, events, terminated = collect(
        agent.run(config, side_effect_registry(), MESSAGES, pending)
    )
    assert terminated
    proposals = [e for e in events if e["kind"] == "tool_proposal"]
    assert len(proposals) == 1
    assert proposals[0]["name"] == "do_danger"
    # Nothing executed; a pending action is waiting.
    assert not [e for e in events if e["kind"] == "tool_result"]
    audit_events = [r["event"] for r in read_audit(config)]
    assert audit_events == ["proposed"]
    return config, pending, proposals[0]["id"]


def test_side_effect_call_pauses_for_approval(tmp_path, monkeypatch):
    _pause_for_approval(tmp_path, monkeypatch)


def test_approval_executes_and_resumes(tmp_path, monkeypatch):
    config, pending, action_id = _pause_for_approval(tmp_path, monkeypatch)
    # A fresh continuation turn once the tool has run.
    script_backend(monkeypatch, [[content("Done — I ran it."), done("stop")]])
    text, events, terminated = collect(
        agent.resume(config, side_effect_registry(), pending, action_id, approved=True)
    )
    assert terminated
    results = [e for e in events if e["kind"] == "tool_result"]
    assert results and results[0]["status"] == "ok"
    assert results[0]["result"] == {"ran": True, "label": "x"}
    assert text == "Done — I ran it."
    audit_events = [r["event"] for r in read_audit(config)]
    assert "approved" in audit_events and "executed" in audit_events


def test_denial_does_not_execute_but_resumes(tmp_path, monkeypatch):
    config, pending, action_id = _pause_for_approval(tmp_path, monkeypatch)
    script_backend(monkeypatch, [[content("Understood, I won't."), done("stop")]])
    text, events, terminated = collect(
        agent.resume(config, side_effect_registry(), pending, action_id, approved=False)
    )
    assert terminated
    results = [e for e in events if e["kind"] == "tool_result"]
    assert results and results[0]["status"] == "error"
    assert "declined" in results[0]["error"]
    assert text == "Understood, I won't."
    assert "denied" in [r["event"] for r in read_audit(config)]


def test_resume_with_unknown_id_is_graceful(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    text, events, terminated = collect(
        agent.resume(config, side_effect_registry(), agent.PendingActions(), "deadbeef", approved=True)
    )
    assert terminated
    assert "expired" in text
    assert not events


def test_set_timer_through_the_loop_persists(tmp_path, monkeypatch):
    from jarvis.timers import TimerStore
    config = Config(tools_enabled=True, tool_audit_path=str(tmp_path / "a.jsonl"),
                    timers_path=str(tmp_path / "t.json"))
    script_backend(monkeypatch, [
        [tool_call("set_timer", {"duration_seconds": 600, "label": "tea"}), done("tool_calls")],
        [content("Timer set for ten minutes."), done("stop")],
    ])
    text, events, terminated = collect(
        agent.run(config, default_registry(), MESSAGES, agent.PendingActions())
    )
    assert terminated
    results = [e for e in events if e["kind"] == "tool_result"]
    assert results and results[0]["status"] == "ok"
    assert results[0]["name"] == "set_timer"
    assert text == "Timer set for ten minutes."
    # The side-effecting tool ran inline (auto-run decision) and persisted.
    assert len(TimerStore(config).list_pending()) == 1


def test_pending_actions_evicts_and_expires():
    store = agent.PendingActions(max_items=2, ttl_seconds=900)
    a = store.put({"index": 0})
    b = store.put({"index": 1})
    store.put({"index": 2})  # evicts the oldest (a)
    assert store.pop(a) is None
    assert store.pop(b) is not None
