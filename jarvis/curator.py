from __future__ import annotations

import json
import re

from . import backend
from .config import Config
from .memory import (
    MEMORY_CATEGORIES,
    MemoryDuplicate,
    MemoryError,
    MemoryStore,
    MemoryValidationError,
    normalize_category,
    validate_memory_text,
)


CURATOR_PROMPT = """You are the local JARVIS memory curator. Decide whether user-authored turns contain durable information useful in future conversations.

Return only one JSON object with this shape:
{"decisions":[{"source_index":0,"decision":"save|review|ignore","category":"general|preference|people|project|environment|terminology","confidence":0.0,"stable_key":"lowercase.semantic.key","use_question":false}]}

Rules:
- Save durable user facts, preferences, recurring goals, established decisions, corrections, project facts, important terminology, and stable device/environment context.
- Review information that might be useful but is ambiguous, temporary, hypothetical, joking, quoted, or unclear.
- Ignore one-off requests, questions, acknowledgements, small talk, commands, transient status, and content authored or merely proposed by JARVIS.
- A preceding JARVIS question is context only. Never treat it as a user fact.
- Never invent, paraphrase, combine, or correct the user's content. The server stores the exact source turn; you only classify it.
- Never save credentials, authentication data, financial data, government or machine identifiers, precise location, or unnecessary private data.
- Use one stable_key for the same attribute across corrections. Name the attribute, never its value: preference.status_indicator_color (not preference.cobalt), preference.response_length, project.story_year, people.sibling_name.
- Use save only at confidence 0.90 or above. Use review from 0.65 through 0.89. Otherwise ignore.
- use_question should be true only when a short answer needs the preceding question to be understandable.
- Include at most one decision per source_index and return a decision for every source turn.
"""


class CuratorError(RuntimeError):
    pass


def validate_turns(value: object, config: Config) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise CuratorError("invalid memory-curation batch")
    turns: list[dict[str, str]] = []
    total = 0
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {"question", "user"}:
            raise CuratorError("invalid memory-curation turn")
        question = raw["question"]
        user = raw["user"]
        if not isinstance(question, str) or not isinstance(user, str):
            raise CuratorError("invalid memory-curation turn")
        question = " ".join(question.split()).strip()[:500]
        user = " ".join(user.split()).strip()
        if not user or len(user) > config.max_memory_item_chars:
            raise CuratorError("memory-curation turn is too large")
        try:
            validate_memory_text(user, config.max_memory_item_chars)
        except MemoryValidationError as exc:
            raise CuratorError("memory-curation turn is unsafe") from exc
        total += len(question) + len(user)
        if total > 6_000:
            raise CuratorError("memory-curation batch is too large")
        turns.append({"question": question, "user": user})
    return turns


def curate(config: Config, turns: list[dict[str, str]]) -> list[dict]:
    payload = json.dumps(turns, ensure_ascii=False)
    content = backend.complete_chat(
        config,
        [
            {"role": "system", "content": CURATOR_PROMPT},
            {"role": "user", "content": "Classify these source turns as data:\n" + payload},
        ],
        max_tokens=512,
        temperature=0.0,
    )
    try:
        start = content.index("{")
        end = content.rindex("}") + 1
        result = json.loads(content[start:end])
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CuratorError("memory curator returned invalid JSON") from exc
    raw_decisions = result.get("decisions") if isinstance(result, dict) else None
    if not isinstance(raw_decisions, list):
        raise CuratorError("memory curator returned invalid decisions")
    decisions: list[dict] = []
    seen: set[int] = set()
    for raw in raw_decisions[: len(turns)]:
        if not isinstance(raw, dict):
            continue
        index = raw.get("source_index")
        decision = raw.get("decision")
        confidence = raw.get("confidence")
        stable_key = raw.get("stable_key")
        use_question = raw.get("use_question")
        try:
            category = normalize_category(raw.get("category"))
        except MemoryValidationError:
            continue
        if (
            type(index) is not int or index < 0 or index >= len(turns) or index in seen
            or decision not in ("save", "review", "ignore")
            or type(confidence) not in (int, float) or not 0 <= confidence <= 1
            or not isinstance(stable_key, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,79}", stable_key)
            or type(use_question) is not bool
        ):
            continue
        seen.add(index)
        decisions.append({
            "source_index": index,
            "decision": decision,
            "category": category,
            "confidence": float(confidence),
            "stable_key": stable_key,
            "use_question": use_question,
        })
    return decisions


def format_source_memory(turn: dict[str, str], use_question: bool, limit: int) -> str:
    user = turn["user"]
    if use_question and turn["question"]:
        candidate = f"JARVIS asked: {turn['question']}\nUser answered: {user}"
    else:
        candidate = f"User said: {user}"
    return validate_memory_text(candidate, limit)


def apply_decisions(store: MemoryStore, turns: list[dict[str, str]], decisions: list[dict]) -> dict[str, list[dict]]:
    saved: list[dict] = []
    candidates: list[dict] = []
    for decision in decisions:
        if decision["decision"] == "ignore" or decision["confidence"] < 0.65:
            continue
        try:
            text = format_source_memory(
                turns[decision["source_index"]],
                decision["use_question"],
                store.config.max_memory_item_chars,
            )
            conflict = store.has_saved_stable_key(decision["stable_key"])
            should_save = (
                decision["decision"] == "save"
                and decision["confidence"] >= 0.90
                and not conflict
            )
            item = store.add(
                decision["category"],
                text,
                state="saved" if should_save else "candidate",
                origin="auto",
                confidence=decision["confidence"],
                stable_key=decision["stable_key"],
            )
            (saved if should_save else candidates).append(item)
        except (MemoryDuplicate, MemoryValidationError):
            continue
        except MemoryError:
            raise
    return {"saved": saved, "candidates": candidates}
