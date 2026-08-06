"""Tool registry, argument validation, GBNF grammar, and audit log.

Stage 0 of the capabilities plan (docs/CAPABILITIES_PLAN.md). This module owns
*what tools exist* and *how a call is validated*; the agent loop (jarvis/agent.py)
owns *when* they run. Nothing here reaches the network or the model.

Design guarantees this module provides:

- **A malformed call cannot execute.** Every proposed call is checked against the
  tool's JSON-schema (a small stdlib validator, no third-party deps) before the
  handler is ever invoked. Anything that does not validate is rejected and the
  loop is told why, so "the model emitted nonsense" fails safe rather than
  running something unintended.
- **A GBNF grammar is generated from the same schemas**, so a llama.cpp build
  without native (`--jinja`) tool-calling can still be constrained to emit only
  well-formed calls. The native path is primary; this is the fallback, and it is
  belt-and-suspenders for the validator above.
- **Every tool is either read-only or side-effecting** (`side_effects`). The
  agent loop executes read-only tools inline but must get explicit approval
  before a side-effecting one runs. get_time (the only Stage 0 tool) is read-only.
- **An append-only audit log** records every proposal, execution, approval,
  denial, rejection, and failure, on disk and separate from the chat transcript.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import Config

ROOT = Path(__file__).resolve().parent.parent

# JSON-schema "type" -> the Python types an accepted value may have. bool is
# deliberately excluded from the numeric types: in JSON, true/false are not
# numbers, and Python's bool-is-an-int quirk would otherwise let them through.
_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


class ToolError(RuntimeError):
    """Base class for tool problems."""


class ToolValidationError(ToolError):
    """A proposed call did not match a registered tool's schema."""


class ToolExecutionError(ToolError):
    """A tool handler raised or timed out while running."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    # A restricted JSON-schema object: {"type":"object","properties":{...},
    # "required":[...]}. Property schemas may use type/enum/minimum/maximum/
    # description. additionalProperties is always treated as false.
    parameters: dict
    handler: Callable[[dict, Config], dict]
    side_effects: bool = False


class ToolRegistry:
    """An explicit, per-instance collection of tools.

    Deliberately not a global: the server owns one registry, tests build their
    own, and nothing is registered implicitly by import side effects.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not isinstance(tool.name, str) or not tool.name.isidentifier():
            raise ToolError("tool name must be a valid identifier")
        if tool.name in self._tools:
            raise ToolError(f"tool already registered: {tool.name}")
        _validate_schema_shape(tool.parameters)
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolValidationError(f"unknown tool: {name}") from None

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def is_empty(self) -> bool:
        return not self._tools

    def openai_payload(self) -> list[dict]:
        """The `tools` array for llama.cpp's OpenAI-compatible endpoint."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    def grammar(self) -> str:
        """GBNF constraining output to exactly one well-formed call object."""
        return build_grammar(self._tools.values())

    def validate_call(self, name: object, arguments: object) -> dict:
        """Return validated, coerced arguments or raise ToolValidationError.

        This is the guarantee that a malformed call never executes: the agent
        loop calls this before touching any handler.
        """
        if not isinstance(name, str):
            raise ToolValidationError("tool name must be a string")
        tool = self.get(name)
        return validate_arguments(tool.parameters, arguments)


# --------------------------------------------------------------------------- #
# Schema handling (a deliberately small subset of JSON Schema, stdlib only)
# --------------------------------------------------------------------------- #

def _validate_schema_shape(schema: object) -> None:
    """Reject a tool schema that uses features this validator does not cover."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ToolError("tool parameters must be a JSON-schema object")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ToolError("tool parameters.properties must be an object")
    required = schema.get("required", [])
    if not isinstance(required, list) or any(key not in properties for key in required):
        raise ToolError("tool parameters.required must list declared properties")
    for prop in properties.values():
        if not isinstance(prop, dict):
            raise ToolError("each property schema must be an object")
        prop_type = prop.get("type")
        if "enum" in prop:
            if not isinstance(prop["enum"], list) or not prop["enum"]:
                raise ToolError("property enum must be a non-empty list")
        elif prop_type not in _TYPE_CHECKS:
            raise ToolError(f"unsupported property type: {prop_type!r}")


def validate_arguments(schema: dict, arguments: object) -> dict:
    """Validate call arguments against a tool schema; return a clean copy.

    Raises ToolValidationError on anything unexpected: wrong container, unknown
    key, missing required key, wrong type, enum miss, or out-of-range number.
    """
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ToolValidationError("arguments must be a JSON object")
    properties: dict = schema.get("properties", {})
    required: list = schema.get("required", [])
    unknown = set(arguments) - set(properties)
    if unknown:
        raise ToolValidationError(f"unexpected argument(s): {', '.join(sorted(unknown))}")
    missing = [key for key in required if key not in arguments]
    if missing:
        raise ToolValidationError(f"missing required argument(s): {', '.join(missing)}")
    clean: dict = {}
    for key, value in arguments.items():
        prop = properties[key]
        if "enum" in prop:
            if value not in prop["enum"]:
                raise ToolValidationError(f"argument {key!r} is not one of the allowed values")
        else:
            check = _TYPE_CHECKS[prop["type"]]
            if not check(value):
                raise ToolValidationError(f"argument {key!r} must be of type {prop['type']}")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if "minimum" in prop and value < prop["minimum"]:
                    raise ToolValidationError(f"argument {key!r} is below its minimum")
                if "maximum" in prop and value > prop["maximum"]:
                    raise ToolValidationError(f"argument {key!r} is above its maximum")
        clean[key] = value
    return clean


# --------------------------------------------------------------------------- #
# GBNF grammar generation (fallback path for builds without --jinja tools)
# --------------------------------------------------------------------------- #

_GBNF_PRIMITIVES = "\n".join(
    (
        r'ws ::= [ \t\n]*',
        r'jstring ::= "\"" ( [^"\\] | "\\" ["\\/bfnrt] | "\\u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] )* "\""',
        r'jinteger ::= "-"? ( "0" | [1-9] [0-9]* )',
        r'jnumber ::= "-"? ( "0" | [1-9] [0-9]* ) ( "." [0-9]+ )? ( [eE] [-+]? [0-9]+ )?',
        r'jbool ::= "true" | "false"',
    )
)


def _gbnf_string_literal(value: str) -> str:
    """A GBNF terminal matching one exact JSON string, e.g. get_time -> "\"get_time\"" ."""
    return '"\\"' + value.replace("\\", "\\\\").replace('"', '\\"') + '\\""'


def _gbnf_value_rule(prop: dict) -> str:
    if "enum" in prop:
        return "( " + " | ".join(_gbnf_string_literal(str(option)) for option in prop["enum"]) + " )"
    return {
        "string": "jstring",
        "integer": "jinteger",
        "number": "jnumber",
        "boolean": "jbool",
    }[prop["type"]]


def _gbnf_object_rule(tool: Tool, rule_name: str) -> tuple[str, list[str]]:
    """Build the GBNF rule(s) for one tool's arguments object."""
    properties: dict = tool.parameters.get("properties", {})
    required: list = tool.parameters.get("required", [])
    if not properties:
        return f'{rule_name} ::= "{{" ws "}}"', []
    # Required properties come first, in schema order, then optionals; each
    # member is `"key" ws ":" ws <value>`. Commas separate members; every member
    # after the first (whether required or optional) carries a leading comma so
    # optionals can be dropped without leaving a dangling separator.
    ordered = [k for k in properties if k in required] + [k for k in properties if k not in required]
    members: list[str] = []
    for index, key in enumerate(ordered):
        value_rule = _gbnf_value_rule(properties[key])
        member = f'{_gbnf_string_literal(key)} ws ":" ws {value_rule}'
        piece = member if index == 0 else f'ws "," ws {member}'
        members.append(piece if key in required else f'( {piece} )?')
    body = " ".join(members)
    return f'{rule_name} ::= "{{" ws {body} ws "}}"', []


def build_grammar(tools) -> str:
    """Generate a GBNF grammar constraining output to one valid tool call.

    The model is forced to emit `{"name": <a registered tool>, "arguments": {…}}`
    where the arguments object matches that specific tool's schema. Used as the
    fallback when a llama.cpp build lacks native tool-calling; the native path
    does not need it.
    """
    tools = list(tools)
    if not tools:
        raise ToolError("cannot build a grammar with no tools")
    call_rules: list[str] = []
    object_rules: list[str] = []
    alternatives: list[str] = []
    for index, tool in enumerate(tools):
        obj_name = f"args{index}"
        call_name = f"call{index}"
        object_rule, _ = _gbnf_object_rule(tool, obj_name)
        object_rules.append(object_rule)
        call_rules.append(
            f'{call_name} ::= "{{" ws "\\"name\\"" ws ":" ws {_gbnf_string_literal(tool.name)} '
            f'ws "," ws "\\"arguments\\"" ws ":" ws {obj_name} ws "}}"'
        )
        alternatives.append(call_name)
    root = "root ::= " + " | ".join(alternatives)
    return "\n".join([root, *call_rules, *object_rules, _GBNF_PRIMITIVES]) + "\n"


# --------------------------------------------------------------------------- #
# Audit log (append-only JSONL, on disk, separate from chat)
# --------------------------------------------------------------------------- #

_AUDIT_LOCK = threading.Lock()


def _audit_path(config: Config) -> Path:
    path = Path(config.tool_audit_path)
    return path if path.is_absolute() else ROOT / path


def audit(config: Config, event: str, *, tool: str | None = None,
          arguments: object = None, outcome: object = None,
          action_id: str | None = None) -> None:
    """Append one tool-activity record. Never raises into the caller."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "tool": tool,
        "arguments": arguments,
        "outcome": outcome,
        "id": action_id,
    }
    try:
        path = _audit_path(config)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with _AUDIT_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError:
        # The audit log is important but must not take the turn down with it.
        pass


# --------------------------------------------------------------------------- #
# Built-in tools
# --------------------------------------------------------------------------- #

def _ordinal(day: int) -> str:
    """1 -> '1st', 2 -> '2nd', 5 -> '5th', 21 -> '21st' — so TTS says 'fifth'."""
    if 11 <= (day % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _get_time(arguments: dict, config: Config) -> dict:
    """Return the server's current local date and time (read-only).

    `spoken` is deliberately US month-day-with-ordinal and carries no timezone:
    the model reads it aloud, so "August 5th" is spoken "August fifth" (a bare
    "5" would be read "five"). The timezone is *omitted entirely* unless the
    caller sets with_timezone — a 7B will read aloud any field it is handed, so
    the reliable way to keep the zone out of ordinary answers is to not include
    it. The model sets with_timezone only when the user asks about the zone.
    """
    now = datetime.now().astimezone()
    day = _ordinal(now.day)
    clock = now.strftime("%-I:%M %p")
    result = {
        "iso": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time_24h": now.strftime("%H:%M"),
        "time_12h": clock,
        "spoken": f"{now.strftime('%A, %B')} {day}, {now.strftime('%Y')} at {clock}",
    }
    if arguments.get("with_timezone"):
        result["timezone"] = now.tzname() or "local"
        result["utc_offset"] = now.strftime("%z")
    return result


GET_TIME = Tool(
    name="get_time",
    description=(
        "Get the current local date and time on the server. Call this whenever "
        "the user asks what time or date it is, or when the current time is "
        "needed to answer. When telling the user, read the natural 'spoken' "
        "field. Leave with_timezone unset for ordinary time questions; set it "
        "true only when the user specifically asks which timezone or zone it is."
    ),
    parameters={
        "type": "object",
        "properties": {
            "with_timezone": {
                "type": "boolean",
                "description": "Include the timezone in the result. Set true only if the user asks which timezone it is.",
            },
        },
        "required": [],
    },
    handler=_get_time,
    side_effects=False,
)


def default_registry() -> ToolRegistry:
    """The tools JARVIS ships with at this stage. Stage 0: get_time only."""
    registry = ToolRegistry()
    registry.register(GET_TIME)
    return registry
