from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import Config


ROOT = Path(__file__).resolve().parent.parent
MEMORY_VERSION = 2
MEMORY_CATEGORIES = (
    "general",
    "preference",
    "people",
    "project",
    "environment",
    "terminology",
)
MEMORY_STATES = ("saved", "candidate")
MEMORY_ORIGINS = ("explicit", "learn", "auto")
CATEGORY_ALIASES = {
    "canon": "project",
    "story canon": "project",
    "person": "people",
    "device": "environment",
    "devices": "environment",
    "term": "terminology",
    "terms": "terminology",
}
SENSITIVE_MEMORY = re.compile(
    r"\b(?:password|passcode|pin code|api[ -]?key|access token|refresh token|"
    r"authentication token|private key|secret key|session cookie|credit card|"
    r"debit card|bank account|routing number|social security|ssn|serial number)\b",
    re.IGNORECASE,
)
ADD_WITH_CATEGORY = re.compile(
    r"^remember(?:\s+this)?\s+as\s+"
    r"(?P<category>general|preference|people?|project|canon|story canon|environment|devices?|terminology|terms?)"
    r"\s*[:,-]\s*(?P<text>.+)$",
    re.IGNORECASE | re.DOTALL,
)
ADD_GENERAL = re.compile(
    r"^(?:remember(?:\s+that)?|save\s+to\s+memory)\s*[:,-]?\s+(?P<text>.+)$",
    re.IGNORECASE | re.DOTALL,
)
FORGET_EXACT = re.compile(
    r"^(?:forget(?:\s+that|\s+memory)?|delete\s+memory)\s*[:,-]?\s+(?P<text>.+)$",
    re.IGNORECASE | re.DOTALL,
)
LIST_MEMORY = re.compile(
    r"^(?:what\s+do\s+you\s+remember(?:\s+about\s+me)?|show(?:\s+me)?\s+(?:your\s+)?memories|"
    r"list(?:\s+my|\s+the)?\s+memories)\s*[.!?]*$",
    re.IGNORECASE,
)


class MemoryError(RuntimeError):
    pass


class MemoryValidationError(MemoryError):
    pass


class MemoryNotFound(MemoryError):
    pass


class MemoryDuplicate(MemoryError):
    pass


@dataclass(frozen=True)
class MemoryCommand:
    action: str
    text: str = ""
    category: str = "general"


def normalize_category(value: object) -> str:
    if not isinstance(value, str):
        raise MemoryValidationError("memory category is invalid")
    category = value.strip().casefold()
    category = CATEGORY_ALIASES.get(category, category)
    if category not in MEMORY_CATEGORIES:
        raise MemoryValidationError("memory category is invalid")
    return category


def validate_memory_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        raise MemoryValidationError("memory text is required")
    text = value.strip()
    if not text or len(text) > limit:
        raise MemoryValidationError("memory text is invalid")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
        raise MemoryValidationError("memory text contains unsupported control characters")
    if SENSITIVE_MEMORY.search(text):
        raise MemoryValidationError("sensitive secrets cannot be stored in memory")
    return text


def parse_memory_command(value: str) -> MemoryCommand | None:
    text = value.strip()
    if LIST_MEMORY.fullmatch(text):
        return MemoryCommand("list")
    match = ADD_WITH_CATEGORY.fullmatch(text)
    if match:
        return MemoryCommand(
            "add",
            text=match.group("text").strip(),
            category=normalize_category(match.group("category")),
        )
    match = ADD_GENERAL.fullmatch(text)
    if match:
        return MemoryCommand("add", text=match.group("text").strip())
    match = FORGET_EXACT.fullmatch(text)
    if match:
        return MemoryCommand("forget", text=match.group("text").strip())
    return None


class MemoryStore:
    def __init__(self, config: Config, path: Path | None = None):
        self.config = config
        self.path = path or (ROOT / config.memory_path)
        self.backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        self._lock = threading.RLock()

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._load_items() if item["state"] == "saved"]

    def candidates(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._load_items() if item["state"] == "candidate"]

    def all_items(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._load_items()]

    def context_items(self) -> list[dict]:
        items = self.list()
        selected: list[dict] = []
        used = 0
        for item in reversed(items):
            size = len(item["text"]) + len(item["category"]) + 32
            if selected and used + size > self.config.memory_context_chars:
                break
            if size > self.config.memory_context_chars:
                continue
            selected.append({"category": item["category"], "text": item["text"]})
            used += size
        selected.reverse()
        return selected

    def add(
        self,
        category: object,
        text: object,
        *,
        state: str = "saved",
        origin: str = "explicit",
        confidence: float | None = None,
        stable_key: str | None = None,
    ) -> dict:
        category_value = normalize_category(category)
        text_value = validate_memory_text(text, self.config.max_memory_item_chars)
        state_value, origin_value, confidence_value, stable_key_value = _validate_metadata(
            state, origin, confidence, stable_key
        )
        with self._lock:
            items = self._load_items()
            if len(items) >= self.config.max_memory_items:
                raise MemoryValidationError("memory item limit reached")
            if any(_comparison_key(item["text"]) == _comparison_key(text_value) for item in items):
                raise MemoryDuplicate("that memory already exists")
            now = _utc_now()
            item = {
                "id": uuid.uuid4().hex,
                "category": category_value,
                "text": text_value,
                "state": state_value,
                "origin": origin_value,
                "confidence": confidence_value,
                "stable_key": stable_key_value,
                "created_at": now,
                "updated_at": now,
            }
            items.append(item)
            self._save_items(items)
            return dict(item)

    def approve(self, memory_id: str) -> dict:
        _validate_id(memory_id)
        with self._lock:
            items = self._load_items()
            target = next((item for item in items if item["id"] == memory_id), None)
            if target is None or target["state"] != "candidate":
                raise MemoryNotFound("memory candidate was not found")
            if target["stable_key"]:
                items = [
                    item for item in items
                    if item["id"] == memory_id
                    or item["state"] != "saved"
                    or item["stable_key"] != target["stable_key"]
                ]
                target = next(item for item in items if item["id"] == memory_id)
            target["state"] = "saved"
            target["updated_at"] = _utc_now()
            self._save_items(items)
            return dict(target)

    def has_saved_stable_key(self, stable_key: str) -> bool:
        if not _valid_stable_key(stable_key):
            return False
        with self._lock:
            return any(
                item["state"] == "saved" and item["stable_key"] == stable_key
                for item in self._load_items()
            )

    def update(self, memory_id: str, category: object, text: object) -> dict:
        _validate_id(memory_id)
        category_value = normalize_category(category)
        text_value = validate_memory_text(text, self.config.max_memory_item_chars)
        with self._lock:
            items = self._load_items()
            target = next((item for item in items if item["id"] == memory_id), None)
            if target is None:
                raise MemoryNotFound("memory was not found")
            if any(
                item["id"] != memory_id and _comparison_key(item["text"]) == _comparison_key(text_value)
                for item in items
            ):
                raise MemoryDuplicate("that memory already exists")
            target["category"] = category_value
            target["text"] = text_value
            target["updated_at"] = _utc_now()
            self._save_items(items)
            return dict(target)

    def delete(self, memory_id: str) -> dict:
        _validate_id(memory_id)
        with self._lock:
            items = self._load_items()
            for index, item in enumerate(items):
                if item["id"] == memory_id:
                    removed = items.pop(index)
                    self._save_items(items)
                    return dict(removed)
        raise MemoryNotFound("memory was not found")

    def forget_exact(self, text: str) -> dict:
        text_value = validate_memory_text(text, self.config.max_memory_item_chars)
        with self._lock:
            items = self._load_items()
            matches = [item for item in items if _comparison_key(item["text"]) == _comparison_key(text_value)]
            if len(matches) != 1:
                raise MemoryNotFound("an exact memory match was not found")
            return self.delete(matches[0]["id"])

    def _load_items(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            if self.path.stat().st_size > self.config.max_memory_file_bytes:
                raise MemoryError("memory file exceeds its limit")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MemoryError("memory file is unreadable") from exc
        if not isinstance(payload, dict) or set(payload) != {"version", "items"}:
            raise MemoryError("memory file schema is invalid")
        if payload["version"] not in (1, MEMORY_VERSION) or not isinstance(payload["items"], list):
            raise MemoryError("memory file version is unsupported")
        if len(payload["items"]) > self.config.max_memory_items:
            raise MemoryError("memory item limit is exceeded")
        items: list[dict] = []
        for raw in payload["items"]:
            if not isinstance(raw, dict):
                raise MemoryError("memory item schema is invalid")
            if payload["version"] == 1:
                if set(raw) != {"id", "category", "text", "created_at", "updated_at"}:
                    raise MemoryError("memory item schema is invalid")
                raw = {
                    **raw,
                    "state": "saved",
                    "origin": "explicit",
                    "confidence": None,
                    "stable_key": None,
                }
            elif set(raw) != {
                "id", "category", "text", "state", "origin", "confidence", "stable_key",
                "created_at", "updated_at"
            }:
                raise MemoryError("memory item schema is invalid")
            try:
                _validate_id(raw["id"])
                category = normalize_category(raw["category"])
                text = validate_memory_text(raw["text"], self.config.max_memory_item_chars)
                _validate_timestamp(raw["created_at"])
                _validate_timestamp(raw["updated_at"])
                state, origin, confidence, stable_key = _validate_metadata(
                    raw["state"], raw["origin"], raw["confidence"], raw["stable_key"]
                )
            except MemoryValidationError as exc:
                raise MemoryError("memory item is invalid") from exc
            items.append({
                "id": raw["id"],
                "category": category,
                "text": text,
                "state": state,
                "origin": origin,
                "confidence": confidence,
                "stable_key": stable_key,
                "created_at": raw["created_at"],
                "updated_at": raw["updated_at"],
            })
        total_chars = sum(len(item["text"]) for item in items)
        if total_chars > self.config.max_memory_chars:
            raise MemoryError("memory character limit is exceeded")
        return items

    def _save_items(self, items: list[dict]) -> None:
        total_chars = sum(len(item["text"]) for item in items)
        if total_chars > self.config.max_memory_chars:
            raise MemoryValidationError("memory character limit reached")
        payload = json.dumps(
            {"version": MEMORY_VERSION, "items": items},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8") + b"\n"
        if len(payload) > self.config.max_memory_file_bytes:
            raise MemoryValidationError("memory file limit reached")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        if self.path.exists():
            _atomic_write(self.backup_path, self.path.read_bytes())
        _atomic_write(self.path, payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _comparison_key(value: str) -> str:
    return " ".join(value.casefold().split()).rstrip(".!?")


def _validate_id(value: object) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise MemoryValidationError("memory id is invalid")


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise MemoryValidationError("memory timestamp is invalid")


def _valid_stable_key(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,79}", value))


def _validate_metadata(
    state: object,
    origin: object,
    confidence: object,
    stable_key: object,
) -> tuple[str, str, float | None, str | None]:
    if state not in MEMORY_STATES or origin not in MEMORY_ORIGINS:
        raise MemoryValidationError("memory metadata is invalid")
    if confidence is not None and (type(confidence) not in (int, float) or not 0 <= confidence <= 1):
        raise MemoryValidationError("memory confidence is invalid")
    if stable_key is not None and not _valid_stable_key(stable_key):
        raise MemoryValidationError("memory stable key is invalid")
    return str(state), str(origin), float(confidence) if confidence is not None else None, stable_key


def _atomic_write(path: Path, payload: bytes) -> None:
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.name}.",
            dir=path.parent,
            delete=False,
        ) as output:
            temp_name = output.name
            os.chmod(temp_name, 0o600)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, path)
        temp_name = None
        os.chmod(path, 0o600)
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
