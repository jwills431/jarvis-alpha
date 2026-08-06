import time
from datetime import datetime, timedelta

import pytest

from jarvis.config import Config
from jarvis.timers import (
    TimerNotFound,
    TimerStore,
    TimerValidationError,
    parse_clock_time,
    parse_fire_at,
)
from jarvis.tools import ToolExecutionError, default_registry


def make_config(tmp_path, **overrides):
    # Constructed directly (no validate) so an absolute tmp path is allowed.
    return Config(tools_enabled=True, timers_path=str(tmp_path / "timers.json"), **overrides)


# --------------------------------------------------------------------------- #
# Store: create / list / poll
# --------------------------------------------------------------------------- #

def test_add_timer_and_list(tmp_path):
    store = TimerStore(make_config(tmp_path))
    rec = store.add_timer(600, "tea")
    assert rec["kind"] == "timer" and rec["label"] == "tea" and rec["status"] == "pending"
    pending = store.list_pending()
    assert len(pending) == 1 and pending[0]["id"] == rec["id"]


def test_add_reminder_relative_and_absolute(tmp_path):
    store = TimerStore(make_config(tmp_path))
    store.add_reminder("check the oven", duration_seconds=1200)
    future = (datetime.now() + timedelta(hours=2)).replace(microsecond=0).isoformat()
    store.add_reminder("standup", fire_at=future)
    assert len(store.list_pending()) == 2


def test_reminder_requires_exactly_one_time(tmp_path):
    store = TimerStore(make_config(tmp_path))
    with pytest.raises(TimerValidationError):
        store.add_reminder("x")  # no time spec
    with pytest.raises(TimerValidationError):
        store.add_reminder("x", duration_seconds=60, fire_at="2099-01-01T00:00:00")  # two specs
    with pytest.raises(TimerValidationError):
        store.add_reminder("x", duration_seconds=60, at_time="10:42 PM")  # two specs


def test_reminder_message_is_optional(tmp_path):
    # "set a reminder for 10:42 PM" — an alarm with nothing to say.
    store = TimerStore(make_config(tmp_path))
    rec = store.add_reminder(at_time="10:42 PM")
    assert rec["kind"] == "reminder" and rec["label"] is None
    assert len(store.list_pending()) == 1


def test_reminder_at_time_resolves_to_next_occurrence(tmp_path):
    store = TimerStore(make_config(tmp_path))
    rec = store.add_reminder("call mum", at_time="11:59 PM")
    assert rec["status"] == "pending"
    # Fire time is within the next 24h.
    assert 0 < rec["fire_epoch"] - __import__("time").time() <= 24 * 3600 + 5


def test_poll_fires_once_then_not_again(tmp_path):
    store = TimerStore(make_config(tmp_path))
    store.add_timer(1, "quick")
    assert store.poll()["fired"] == []  # not due yet
    time.sleep(1.1)
    fired = store.poll()["fired"]
    assert len(fired) == 1 and fired[0]["label"] == "quick" and fired[0]["status"] == "fired"
    assert store.poll()["fired"] == []  # already fired, never again
    assert store.list_pending() == []


def test_list_pending_sorted_by_fire_time(tmp_path):
    store = TimerStore(make_config(tmp_path))
    store.add_timer(3600, "late")
    store.add_timer(60, "soon")
    labels = [t["label"] for t in store.list_pending()]
    assert labels == ["soon", "late"]


# --------------------------------------------------------------------------- #
# Persistence across store instances (survives restart)
# --------------------------------------------------------------------------- #

def test_pending_timer_survives_a_new_store_instance(tmp_path):
    config = make_config(tmp_path)
    TimerStore(config).add_reminder("feed the cat", duration_seconds=5000)
    # A brand-new store (as after an app restart) still sees it.
    reloaded = TimerStore(config)
    assert len(reloaded.list_pending()) == 1


def test_past_timer_fires_on_first_poll_after_restart(tmp_path):
    config = make_config(tmp_path)
    TimerStore(config).add_timer(1, "oven")
    time.sleep(1.1)
    # Fresh instance, timer's fire time already passed -> fires immediately.
    assert len(TimerStore(config).poll()["fired"]) == 1


# --------------------------------------------------------------------------- #
# Bounds / validation
# --------------------------------------------------------------------------- #

def test_pending_limit_enforced(tmp_path):
    store = TimerStore(make_config(tmp_path, max_timers=2))
    store.add_timer(100)
    store.add_timer(200)
    with pytest.raises(TimerValidationError):
        store.add_timer(300)


def test_duration_over_horizon_rejected(tmp_path):
    store = TimerStore(make_config(tmp_path, max_timer_seconds=3600))
    with pytest.raises(TimerValidationError):
        store.add_timer(7200)


def test_fire_at_in_past_rejected(tmp_path):
    store = TimerStore(make_config(tmp_path))
    past = (datetime.now() - timedelta(minutes=5)).isoformat()
    with pytest.raises(TimerValidationError):
        store.add_reminder("late", fire_at=past)


def test_bad_duration_types_rejected(tmp_path):
    store = TimerStore(make_config(tmp_path))
    for bad in (True, "600", 0, -5):
        with pytest.raises(TimerValidationError):
            store.add_timer(bad)


# --------------------------------------------------------------------------- #
# parse_fire_at
# --------------------------------------------------------------------------- #

def test_parse_clock_time_variants():
    import time
    now = time.time()
    for value in ("10:42 PM", "22:42", "6:30am", "6 pm", "12:00 AM", "12 pm"):
        epoch = parse_clock_time(value)
        assert isinstance(epoch, float)
        assert now < epoch <= now + 24 * 3600 + 5  # always the next occurrence, within a day
    for bad in (None, "", "not a time", "25:00", "10:99 PM", "13 pm"):
        with pytest.raises(TimerValidationError):
            parse_clock_time(bad)


def test_parse_fire_at_variants():
    assert parse_fire_at("2026-08-05T18:30:00Z") == pytest.approx(
        datetime(2026, 8, 5, 18, 30, tzinfo=__import__("datetime").timezone.utc).timestamp()
    )
    # Naive is interpreted as local; just assert it parses to a float.
    assert isinstance(parse_fire_at("2026-08-05T18:30:00"), float)
    for bad in (None, "", "not-a-date", 123):
        with pytest.raises(TimerValidationError):
            parse_fire_at(bad)


# --------------------------------------------------------------------------- #
# Cancellation
# --------------------------------------------------------------------------- #

def test_cancel_by_id(tmp_path):
    store = TimerStore(make_config(tmp_path))
    rec = store.add_timer(600, "tea")
    cancelled = store.cancel(timer_id=rec["id"])
    assert len(cancelled) == 1
    assert store.list_pending() == []


def test_cancel_by_label(tmp_path):
    store = TimerStore(make_config(tmp_path))
    store.add_reminder("check the oven", duration_seconds=600)
    cancelled = store.cancel(label="Check The Oven")  # case-insensitive
    assert len(cancelled) == 1
    assert store.list_pending() == []


def test_cancel_no_match_raises(tmp_path):
    store = TimerStore(make_config(tmp_path))
    with pytest.raises(TimerNotFound):
        store.cancel(label="nonexistent")
    with pytest.raises(TimerValidationError):
        store.cancel()  # neither id nor label


# --------------------------------------------------------------------------- #
# Tool handlers (the model-facing surface)
# --------------------------------------------------------------------------- #

def test_set_timer_tool_persists(tmp_path):
    config = make_config(tmp_path)
    result = default_registry().get("set_timer").handler({"duration_seconds": 600, "label": "pasta"}, config)
    assert result["status"] == "set" and result["duration"] == "10 minutes"
    assert len(TimerStore(config).list_pending()) == 1


def test_set_reminder_tool_persists(tmp_path):
    config = make_config(tmp_path)
    result = default_registry().get("set_reminder").handler(
        {"message": "call mum", "duration_seconds": 300}, config)
    assert result["kind"] == "reminder" and result["message"] == "call mum"


def test_set_reminder_tool_at_time_no_message(tmp_path):
    # The exact failing case: "set a reminder for 10:42 PM".
    config = make_config(tmp_path)
    result = default_registry().get("set_reminder").handler({"at_time": "10:42 PM"}, config)
    assert result["status"] == "set" and result["kind"] == "reminder" and result["message"] is None
    assert len(TimerStore(config).list_pending()) == 1


def test_set_reminder_tool_keeps_message_with_at_time(tmp_path):
    # "remind me to check the oven at 6pm" — the message must be retained.
    config = make_config(tmp_path)
    result = default_registry().get("set_reminder").handler(
        {"message": "check the oven", "at_time": "6pm"}, config)
    assert result["message"] == "check the oven"
    assert TimerStore(config).list_pending()[0]["label"] == "check the oven"


def test_list_and_cancel_tools(tmp_path):
    config = make_config(tmp_path)
    reg = default_registry()
    reg.get("set_timer").handler({"duration_seconds": 600, "label": "tea"}, config)
    assert reg.get("list_timers").handler({}, config)["count"] == 1
    cancelled = reg.get("cancel_timer").handler({"label": "tea"}, config)
    assert cancelled["count"] == 1
    assert reg.get("list_timers").handler({}, config)["count"] == 0


def test_timer_tool_domain_error_surfaces_cleanly(tmp_path):
    config = make_config(tmp_path, max_timer_seconds=3600)
    with pytest.raises(ToolExecutionError):
        default_registry().get("set_timer").handler({"duration_seconds": 999999}, config)
