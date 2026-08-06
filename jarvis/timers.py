"""Persistent timers and reminders (Stage 1 of the capabilities plan).

A small file-backed store under ``data/timers.json``. The server owns the
authoritative clock; the browser polls ``/api/timers`` and, on each poll, the
store atomically transitions any *pending* timer whose ``fire_at`` has passed
into *fired* and returns it exactly once. The client then shows it and speaks it
through the existing Fish path.

Because firing is derived from the wall clock at poll time rather than from an
in-process timer, a pending reminder **survives an app restart** for free: after
a restart its ``fire_at`` is simply in the past, so the next poll fires it. No
background thread, no scheduler to re-arm.

The tool handlers (jarvis/tools.py) and the ``/api/timers`` route both construct
a ``TimerStore(config)`` on demand — it is cheap and file-backed — and a module
lock serialises the read-modify-write so concurrent request threads cannot
corrupt the file.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config

ROOT = Path(__file__).resolve().parent.parent

# One lock guards every store instance's writes: they all target the same file.
_LOCK = threading.RLock()

KINDS = ("timer", "reminder")
STATUSES = ("pending", "fired", "cancelled")
_MAX_LABEL_CHARS = 200


class TimerError(RuntimeError):
    pass


class TimerValidationError(TimerError):
    pass


class TimerNotFound(TimerError):
    pass


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ordinal(day: int) -> str:
    if 11 <= (day % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _spoken(epoch: float) -> str:
    """A natural local-time phrasing for a fire time, matching get_time's style."""
    local = datetime.fromtimestamp(epoch).astimezone()
    day = _ordinal(local.day)
    return f"{local.strftime('%A, %B')} {day} at {local.strftime('%-I:%M %p')}"


_CLOCK_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?\s*$", re.IGNORECASE)


def parse_clock_time(value: object) -> float:
    """Resolve a clock time ('10:42 PM', '22:42', '6:30am', '6 pm') to a UTC epoch.

    Picks the next occurrence: today if the time is still ahead, otherwise
    tomorrow. This lets the model pass the time the user said verbatim, with no
    date arithmetic and no get_time round trip.
    """
    if not isinstance(value, str) or not value.strip():
        raise TimerValidationError("at_time must be a clock time string")
    match = _CLOCK_RE.match(value)
    if not match:
        raise TimerValidationError("at_time is not a recognizable clock time")
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if minute > 59:
        raise TimerValidationError("at_time has an invalid minute")
    if meridiem:
        meridiem = meridiem[0].lower()
        if not 1 <= hour <= 12:
            raise TimerValidationError("at_time hour must be 1-12 with am/pm")
        if meridiem == "p" and hour != 12:
            hour += 12
        elif meridiem == "a" and hour == 12:
            hour = 0
    elif hour > 23:
        raise TimerValidationError("at_time hour must be 0-23")
    now = datetime.now().astimezone()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.timestamp()


def parse_fire_at(value: object) -> float:
    """Parse an absolute ISO datetime (naive treated as local) to a UTC epoch."""
    if not isinstance(value, str) or not value.strip():
        raise TimerValidationError("fire_at must be an ISO datetime string")
    text = value.strip()
    # Accept a trailing Z as UTC; datetime.fromisoformat handles offsets otherwise.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise TimerValidationError("fire_at is not a valid ISO datetime") from None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()  # interpret a naive time as this machine's local time
    return parsed.timestamp()


class TimerStore:
    def __init__(self, config: Config):
        self.config = config
        path = Path(config.timers_path)
        self.path = path if path.is_absolute() else ROOT / path

    # -- creation -----------------------------------------------------------

    def add_timer(self, duration_seconds: object, label: object = None) -> dict:
        seconds = self._validate_duration(duration_seconds)
        return self._create("timer", _now() + seconds, self._validate_label(label, required=False))

    def add_reminder(self, message: object = None, *, duration_seconds: object = None,
                     fire_at: object = None, at_time: object = None) -> dict:
        # The message is optional: "set a reminder for 10:42 PM" is a valid alarm
        # with nothing to say. The time is required as exactly one of three forms.
        text = self._validate_label(message, required=False)
        provided = [duration_seconds is not None, fire_at is not None, at_time is not None]
        if sum(provided) != 1:
            raise TimerValidationError("provide exactly one of duration_seconds, at_time, or fire_at")
        if duration_seconds is not None:
            fire_epoch = _now() + self._validate_duration(duration_seconds)
        elif at_time is not None:
            fire_epoch = parse_clock_time(at_time)
            self._validate_horizon(fire_epoch)
        else:
            fire_epoch = parse_fire_at(fire_at)
            self._validate_horizon(fire_epoch)
        return self._create("reminder", fire_epoch, text)

    def _create(self, kind: str, fire_epoch: float, label: str | None) -> dict:
        now = _now()
        with _LOCK:
            items = self._load()
            if sum(1 for item in items if item["status"] == "pending") >= self.config.max_timers:
                raise TimerValidationError("the pending timer limit has been reached")
            record = {
                "id": uuid.uuid4().hex,
                "kind": kind,
                "label": label,
                "created_at": _iso(now),
                "fire_at": _iso(fire_epoch),
                "fire_epoch": round(fire_epoch, 3),
                "status": "pending",
                "fired_at": None,
            }
            items.append(record)
            self._save(items)
            return self._public(record)

    # -- queries ------------------------------------------------------------

    def list_pending(self) -> list[dict]:
        with _LOCK:
            items = self._load()
            pending = [self._public(item) for item in items if item["status"] == "pending"]
        pending.sort(key=lambda item: item["fire_epoch"])
        return pending

    def poll(self) -> dict:
        """Return still-pending timers and any that just fired (transitioned once)."""
        now = _now()
        with _LOCK:
            items = self._load()
            fired: list[dict] = []
            for item in items:
                if item["status"] == "pending" and item["fire_epoch"] <= now:
                    item["status"] = "fired"
                    item["fired_at"] = _iso(now)
                    fired.append(item)
            if fired:
                self._save(items)
            pending = [self._public(item) for item in items if item["status"] == "pending"]
        pending.sort(key=lambda item: item["fire_epoch"])
        return {"pending": pending, "fired": [self._public(item) for item in fired]}

    # -- cancellation -------------------------------------------------------

    def cancel(self, *, timer_id: object = None, label: object = None) -> list[dict]:
        """Cancel a pending timer by id, or all pending whose label matches.

        Returns the cancelled records. Raises TimerNotFound if nothing matched.
        """
        with _LOCK:
            items = self._load()
            targets: list[dict] = []
            if timer_id is not None:
                if not isinstance(timer_id, str):
                    raise TimerValidationError("timer id must be a string")
                targets = [i for i in items if i["id"] == timer_id and i["status"] == "pending"]
            elif label is not None:
                needle = self._validate_label(label, required=True).casefold()
                targets = [
                    i for i in items
                    if i["status"] == "pending" and isinstance(i["label"], str)
                    and i["label"].casefold() == needle
                ]
            else:
                raise TimerValidationError("provide a timer id or a label to cancel")
            if not targets:
                raise TimerNotFound("no matching pending timer was found")
            for item in targets:
                item["status"] = "cancelled"
            self._save(items)
            return [self._public(item) for item in targets]

    # -- validation helpers -------------------------------------------------

    def _validate_duration(self, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TimerValidationError("duration_seconds must be a number")
        seconds = int(value)
        if seconds < 1:
            raise TimerValidationError("duration_seconds must be at least 1 second")
        if seconds > self.config.max_timer_seconds:
            raise TimerValidationError("duration_seconds exceeds the allowed horizon")
        return seconds

    def _validate_horizon(self, fire_epoch: float) -> None:
        delta = fire_epoch - _now()
        if delta < 1:
            raise TimerValidationError("fire_at is in the past")
        if delta > self.config.max_timer_seconds:
            raise TimerValidationError("fire_at exceeds the allowed horizon")

    def _validate_label(self, value: object, *, required: bool) -> str | None:
        if value is None:
            if required:
                raise TimerValidationError("a label/message is required")
            return None
        if not isinstance(value, str):
            raise TimerValidationError("label must be a string")
        text = value.strip()
        if not text:
            if required:
                raise TimerValidationError("a label/message is required")
            return None
        if len(text) > _MAX_LABEL_CHARS:
            raise TimerValidationError("label is too long")
        return text

    # -- persistence --------------------------------------------------------

    @staticmethod
    def _public(item: dict) -> dict:
        return {
            "id": item["id"],
            "kind": item["kind"],
            "label": item["label"],
            "fire_at": item["fire_at"],
            "fire_epoch": item["fire_epoch"],
            "fire_at_spoken": _spoken(item["fire_epoch"]),
            "status": item["status"],
            "created_at": item["created_at"],
            "fired_at": item.get("fired_at"),
        }

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items = raw["timers"] if isinstance(raw, dict) else raw
        except (OSError, ValueError, KeyError, TypeError):
            raise TimerError("timer store is unreadable")
        if not isinstance(items, list):
            raise TimerError("timer store is malformed")
        clean: list[dict] = []
        for item in items:
            if not isinstance(item, dict) or item.get("kind") not in KINDS or item.get("status") not in STATUSES:
                raise TimerError("timer record is invalid")
            try:
                fire_epoch = float(item["fire_epoch"])
            except (KeyError, TypeError, ValueError):
                raise TimerError("timer record is invalid") from None
            clean.append({
                "id": str(item.get("id") or uuid.uuid4().hex),
                "kind": item["kind"],
                "label": item.get("label") if isinstance(item.get("label"), str) else None,
                "created_at": item.get("created_at") or _iso(_now()),
                "fire_at": item.get("fire_at") or _iso(fire_epoch),
                "fire_epoch": fire_epoch,
                "status": item["status"],
                "fired_at": item.get("fired_at"),
            })
        return clean

    def _save(self, items: list[dict]) -> None:
        payload = json.dumps(
            {"version": 1, "timers": items}, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8") + b"\n"
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix=f".{self.path.name}.", dir=self.path.parent, delete=False) as output:
                temp_name = output.name
                os.chmod(temp_name, 0o600)
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_name, self.path)
            temp_name = None
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
