"""The agent loop: propose -> validate -> execute -> feed back, with a gate.

Stage 0 of the capabilities plan. This is the *when* to the tools module's
*what*. It drives one chat turn that may involve tools:

  1. Stream a model completion (native tool-calling via llama.cpp).
  2. Forward prose content to the client as it arrives (unchanged SSE shape, so
     the existing streaming + TTS pipeline is untouched).
  3. If the model called tools, validate each call against its schema. A call
     that does not validate is *rejected* — never executed — and the error is
     fed back so the model can recover. This is the "malformed call fails safe"
     guarantee.
  4. Read-only tools execute inline. A side-effecting tool is *not* run: the loop
     emits a proposal and pauses, storing a pending action. The client shows an
     approve/deny control; approval resumes the loop and runs the tool, denial
     resumes it with a "declined" result so the model can acknowledge.
  5. Tool results are appended and the loop repeats, bounded by a hard iteration
     cap so it can never spin.

Every proposal, execution, approval, denial, rejection, and failure is written
to the on-disk audit log (tools.audit).

The public generators yield SSE-ready bytes; the server writes them straight to
the wire. Content uses the standard {"choices":[{"delta":{"content":...}}]}
shape; tool activity uses a top-level {"jarvis": {...}} envelope the client
renders and which older parsers safely ignore.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from . import backend, tools as tools_module
from .config import Config
from .tools import ToolExecutionError, ToolRegistry, ToolValidationError

_HANDLER_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="jarvis-tool")


# --------------------------------------------------------------------------- #
# Pending side-effecting actions awaiting the user's approval
# --------------------------------------------------------------------------- #

class PendingActions:
    """A bounded, thread-safe store of paused tool calls awaiting approval.

    Keyed by an opaque action id handed to the client. Bounded in size (oldest
    evicted) and by age, so an abandoned proposal cannot accumulate state.
    """

    def __init__(self, max_items: int = 32, ttl_seconds: int = 900) -> None:
        self._items: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._max_items = max_items
        self._ttl = ttl_seconds

    def put(self, action: dict) -> str:
        action_id = uuid.uuid4().hex
        with self._lock:
            self._evict_expired()
            while len(self._items) >= self._max_items:
                oldest = min(self._items, key=lambda key: self._items[key]["created"])
                del self._items[oldest]
            self._items[action_id] = {**action, "created": time.monotonic()}
        return action_id

    def pop(self, action_id: str) -> dict | None:
        with self._lock:
            self._evict_expired()
            return self._items.pop(action_id, None)

    def _evict_expired(self) -> None:
        cutoff = time.monotonic() - self._ttl
        for key in [k for k, v in self._items.items() if v["created"] < cutoff]:
            del self._items[key]


# --------------------------------------------------------------------------- #
# SSE helpers
# --------------------------------------------------------------------------- #

def _sse(payload: dict) -> bytes:
    return b"data: " + json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n\n"


def _content_event(text: str) -> bytes:
    return _sse({"choices": [{"delta": {"content": text}, "finish_reason": None}]})


def _tool_result_event(call_id: str, name: str, arguments: object,
                       *, result: object = None, error: str | None = None) -> bytes:
    body = {"kind": "tool_result", "id": call_id, "name": name, "arguments": arguments}
    if error is None:
        body["status"] = "ok"
        body["result"] = result
    else:
        body["status"] = "error"
        body["error"] = error
    return _sse({"jarvis": body})


def _proposal_event(action_id: str, name: str, arguments: object) -> bytes:
    return _sse({"jarvis": {"kind": "tool_proposal", "id": action_id, "name": name, "arguments": arguments}})


_DONE = b"data: [DONE]\n\n"


# --------------------------------------------------------------------------- #
# Message construction
# --------------------------------------------------------------------------- #

def _assistant_tool_message(calls: list[dict]) -> dict:
    """The assistant turn that requested the tools, in OpenAI shape."""
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"] or "",
                    "arguments": json.dumps(call["arguments"] if isinstance(call["arguments"], dict) else {}),
                },
            }
            for call in calls
        ],
    }


def _tool_result_message(call_id: str, payload: object) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": json.dumps(payload, ensure_ascii=False)}


def _run_handler(tool, arguments: dict, config: Config) -> object:
    future = _HANDLER_POOL.submit(tool.handler, arguments, config)
    try:
        return future.result(timeout=config.tool_call_timeout_seconds)
    except FutureTimeout:
        raise ToolExecutionError(f"{tool.name} timed out") from None
    except Exception as exc:  # a handler bug must not crash the turn
        raise ToolExecutionError(f"{tool.name} failed: {exc}") from exc


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #

def run(config: Config, registry: ToolRegistry, messages: list[dict],
        pending: PendingActions):
    """Drive a fresh turn. Yields SSE-ready bytes, terminating with [DONE]."""
    yield from _drive(config, registry, list(messages), pending, 0)


def resume(config: Config, registry: ToolRegistry, pending: PendingActions,
           action_id: str, approved: bool):
    """Resume a paused turn after the user approved or denied a proposal.

    Yields SSE-ready bytes for the continuation, terminating with [DONE]. If the
    action id is unknown or expired, yields a single explanatory content event.
    """
    action = pending.pop(action_id)
    if action is None:
        yield _content_event(
            "That action has expired or was already handled, so I did not run it. "
            "Please ask again if you still want it."
        )
        yield _DONE
        return
    messages: list[dict] = action["messages"]
    calls: list[dict] = action["calls"]
    index: int = action["index"]
    results: list[dict] = action["results"]
    iteration: int = action["iteration"]
    call = calls[index]
    call_id = call["id"]
    name = call["name"]
    try:
        arguments = registry.validate_call(name, None if call.get("malformed") else call["arguments"])
    except ToolValidationError as exc:
        tools_module.audit(config, "rejected", tool=name, arguments=call.get("arguments"),
                           outcome=str(exc), action_id=action_id)
        results.append(_tool_result_message(call_id, {"error": str(exc)}))
        yield _tool_result_event(call_id, name, call.get("arguments"), error=str(exc))
        yield from _process_calls(config, registry, messages, calls, index + 1, results, pending, iteration)
        return
    if approved:
        tools_module.audit(config, "approved", tool=name, arguments=arguments, action_id=action_id)
        try:
            result = _run_handler(registry.get(name), arguments, config)
            tools_module.audit(config, "executed", tool=name, arguments=arguments,
                               outcome=result, action_id=action_id)
            results.append(_tool_result_message(call_id, result))
            yield _tool_result_event(call_id, name, arguments, result=result)
        except ToolExecutionError as exc:
            tools_module.audit(config, "failed", tool=name, arguments=arguments,
                               outcome=str(exc), action_id=action_id)
            results.append(_tool_result_message(call_id, {"error": str(exc)}))
            yield _tool_result_event(call_id, name, arguments, error=str(exc))
    else:
        tools_module.audit(config, "denied", tool=name, arguments=arguments, action_id=action_id)
        results.append(_tool_result_message(
            call_id, {"declined": True, "note": "The user declined to run this action."}
        ))
        yield _tool_result_event(call_id, name, arguments, error="declined by user")
    yield from _process_calls(config, registry, messages, calls, index + 1, results, pending, iteration)


def _drive(config: Config, registry: ToolRegistry, messages: list[dict],
           pending: PendingActions, iteration: int):
    if iteration >= config.tool_max_iterations:
        yield _content_event(
            "I reached the limit on tool steps for this request, so I stopped rather than continue."
        )
        yield _DONE
        return
    collected: list[dict] = []
    grammar = registry.grammar() if config.tool_grammar_enabled else None
    try:
        for event in backend.stream_chat_tools(config, messages, registry.openai_payload(),
                                                grammar=grammar):
            kind = event["type"]
            if kind == "content" and event["text"]:
                yield _content_event(event["text"])
            elif kind == "tool_call":
                collected.append(event)
    except backend.BackendError:
        # Match the non-tool path: end the stream and let the client show its
        # generic retry message. No partial state is retained server-side.
        yield _DONE
        return
    if not collected:
        yield _DONE
        return
    for call in collected:
        if not call.get("id"):
            call["id"] = "call_" + uuid.uuid4().hex[:12]
    messages.append(_assistant_tool_message(collected))
    yield from _process_calls(config, registry, messages, collected, 0, [], pending, iteration)


def _process_calls(config: Config, registry: ToolRegistry, messages: list[dict],
                   calls: list[dict], start_index: int, results: list[dict],
                   pending: PendingActions, iteration: int):
    for i in range(start_index, len(calls)):
        call = calls[i]
        call_id = call["id"]
        name = call["name"]
        # Validate first: a malformed or schema-violating call never executes.
        try:
            if call.get("malformed"):
                raise ToolValidationError("the call arguments were not valid JSON")
            arguments = registry.validate_call(name, call["arguments"])
        except ToolValidationError as exc:
            tools_module.audit(config, "rejected", tool=name, arguments=call.get("arguments"),
                               outcome=str(exc))
            results.append(_tool_result_message(call_id, {"error": str(exc)}))
            yield _tool_result_event(call_id, name, call.get("arguments"), error=str(exc))
            continue
        tool = registry.get(name)
        if tool.side_effects:
            # Pause: record everything needed to resume this exact batch, emit a
            # proposal, and stop. Approval/denial re-enters via resume().
            action_id = pending.put({
                "messages": messages,
                "calls": calls,
                "index": i,
                "results": results,
                "iteration": iteration,
            })
            tools_module.audit(config, "proposed", tool=name, arguments=arguments, action_id=action_id)
            yield _proposal_event(action_id, name, arguments)
            yield _DONE
            return
        # Read-only: execute inline.
        try:
            result = _run_handler(tool, arguments, config)
            tools_module.audit(config, "executed", tool=name, arguments=arguments, outcome=result)
            results.append(_tool_result_message(call_id, result))
            yield _tool_result_event(call_id, name, arguments, result=result)
        except ToolExecutionError as exc:
            tools_module.audit(config, "failed", tool=name, arguments=arguments, outcome=str(exc))
            results.append(_tool_result_message(call_id, {"error": str(exc)}))
            yield _tool_result_event(call_id, name, arguments, error=str(exc))
    messages.extend(results)
    yield from _drive(config, registry, messages, pending, iteration + 1)
