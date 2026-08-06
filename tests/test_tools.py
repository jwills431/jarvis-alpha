import json

import pytest

from jarvis.config import Config
from jarvis.tools import (
    GET_TIME,
    Tool,
    ToolError,
    ToolValidationError,
    ToolRegistry,
    audit,
    build_grammar,
    default_registry,
    validate_arguments,
)


# --------------------------------------------------------------------------- #
# Argument validation — the guarantee a malformed call never executes
# --------------------------------------------------------------------------- #

SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "minutes": {"type": "integer", "minimum": 1, "maximum": 120},
        "ratio": {"type": "number"},
        "loud": {"type": "boolean"},
        "unit": {"enum": ["seconds", "minutes", "hours"]},
    },
    "required": ["label", "minutes"],
}


def test_valid_arguments_pass_through():
    clean = validate_arguments(SCHEMA, {"label": "oven", "minutes": 20, "unit": "minutes"})
    assert clean == {"label": "oven", "minutes": 20, "unit": "minutes"}


def test_none_arguments_treated_as_empty_object():
    schema = {"type": "object", "properties": {}, "required": []}
    assert validate_arguments(schema, None) == {}


def test_missing_required_argument_rejected():
    with pytest.raises(ToolValidationError):
        validate_arguments(SCHEMA, {"label": "oven"})


def test_unknown_argument_rejected():
    with pytest.raises(ToolValidationError):
        validate_arguments(SCHEMA, {"label": "oven", "minutes": 5, "surprise": 1})


def test_wrong_type_rejected():
    with pytest.raises(ToolValidationError):
        validate_arguments(SCHEMA, {"label": "oven", "minutes": "twenty"})


def test_bool_is_not_accepted_as_integer():
    with pytest.raises(ToolValidationError):
        validate_arguments(SCHEMA, {"label": "oven", "minutes": True})


def test_numeric_bounds_enforced():
    with pytest.raises(ToolValidationError):
        validate_arguments(SCHEMA, {"label": "oven", "minutes": 999})


def test_enum_membership_enforced():
    with pytest.raises(ToolValidationError):
        validate_arguments(SCHEMA, {"label": "oven", "minutes": 5, "unit": "fortnights"})


def test_non_object_arguments_rejected():
    with pytest.raises(ToolValidationError):
        validate_arguments(SCHEMA, ["oven", 5])


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

def _noop(arguments, config):
    return {"ok": True}


def test_registry_register_and_lookup():
    registry = ToolRegistry()
    tool = Tool("do_thing", "does a thing", {"type": "object", "properties": {}, "required": []}, _noop)
    registry.register(tool)
    assert "do_thing" in registry
    assert registry.get("do_thing") is tool
    assert registry.names() == ["do_thing"]
    assert not registry.is_empty()


def test_registry_rejects_duplicate():
    registry = ToolRegistry()
    tool = Tool("do_thing", "d", {"type": "object", "properties": {}, "required": []}, _noop)
    registry.register(tool)
    with pytest.raises(ToolError):
        registry.register(tool)


def test_registry_rejects_bad_schema():
    registry = ToolRegistry()
    with pytest.raises(ToolError):
        registry.register(Tool("bad", "d", {"type": "array"}, _noop))
    with pytest.raises(ToolError):
        registry.register(Tool("bad2", "d", {"type": "object", "properties": {"x": {"type": "blob"}}}, _noop))


def test_unknown_tool_lookup_raises_validation_error():
    registry = default_registry()
    with pytest.raises(ToolValidationError):
        registry.get("nonexistent")
    with pytest.raises(ToolValidationError):
        registry.validate_call("nonexistent", {})


def test_openai_payload_shape():
    payload = default_registry().openai_payload()
    assert payload[0]["type"] == "function"
    assert payload[0]["function"]["name"] == "get_time"
    assert "parameters" in payload[0]["function"]


# --------------------------------------------------------------------------- #
# get_time built-in
# --------------------------------------------------------------------------- #

def test_get_time_returns_expected_fields():
    result = GET_TIME.handler({}, Config())
    for key in ("iso", "date", "time_24h", "time_12h", "spoken"):
        assert key in result
    assert not GET_TIME.side_effects


def test_get_time_omits_timezone_by_default():
    # A 7B reads aloud any field it is handed, so the zone must be absent unless
    # explicitly requested. Default (no args) carries no timezone at all.
    result = GET_TIME.handler({}, Config())
    assert "timezone" not in result and "utc_offset" not in result


def test_get_time_includes_timezone_only_when_requested():
    result = GET_TIME.handler({"with_timezone": True}, Config())
    assert "timezone" in result and "utc_offset" in result


def test_get_time_spoken_uses_ordinal_and_never_carries_timezone():
    import re
    result = GET_TIME.handler({"with_timezone": True}, Config())
    # US month-day-ordinal form ("August 5th"), so TTS reads "fifth" not "five".
    assert re.search(r"[A-Z][a-z]+ \d{1,2}(st|nd|rd|th),", result["spoken"])
    # Even with the zone included as a field, it is never inside the spoken text.
    assert result["timezone"] not in result["spoken"]


def test_get_time_accepts_optional_with_timezone_argument():
    registry = default_registry()
    assert registry.validate_call("get_time", {}) == {}
    assert registry.validate_call("get_time", {"with_timezone": True}) == {"with_timezone": True}
    with pytest.raises(ToolValidationError):
        registry.validate_call("get_time", {"when": "now"})
    with pytest.raises(ToolValidationError):
        registry.validate_call("get_time", {"with_timezone": "yes"})  # must be boolean


# --------------------------------------------------------------------------- #
# GBNF grammar generation
# --------------------------------------------------------------------------- #

def test_grammar_contains_tool_name_and_root():
    grammar = default_registry().grammar()
    assert "root ::=" in grammar
    assert r'\"get_time\"' in grammar
    assert "ws ::=" in grammar


def test_grammar_handles_properties():
    tool = Tool("set_timer", "d", SCHEMA, _noop, side_effects=True)
    grammar = build_grammar([tool])
    assert r'\"label\"' in grammar
    assert "jstring" in grammar
    assert "jinteger" in grammar
    # enum options appear as string literals
    assert r'\"seconds\"' in grammar


def test_grammar_empty_raises():
    with pytest.raises(ToolError):
        build_grammar([])


# --------------------------------------------------------------------------- #
# Audit log
# --------------------------------------------------------------------------- #

def test_audit_appends_jsonl(tmp_path):
    log = tmp_path / "audit.jsonl"
    config = Config(tool_audit_path=str(log))  # absolute path, constructed without validate()
    audit(config, "executed", tool="get_time", arguments={}, outcome={"time": "10:00:00"}, action_id="abc")
    audit(config, "proposed", tool="set_timer", arguments={"minutes": 5}, action_id="def")
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event"] == "executed"
    assert first["tool"] == "get_time"
    assert first["id"] == "abc"
    assert "ts" in first


def test_audit_never_raises_on_bad_path(tmp_path):
    # A directory where a file is expected must not take the turn down.
    bad = tmp_path / "a_dir"
    bad.mkdir()
    config = Config(tool_audit_path=str(bad))
    audit(config, "executed", tool="get_time")  # should swallow the OSError
