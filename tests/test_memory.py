import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.config import Config
from jarvis.curator import CuratorError, apply_decisions, curate, validate_turns
from jarvis.memory import (
    MemoryDuplicate,
    MemoryError,
    MemoryNotFound,
    MemoryStore,
    MemoryValidationError,
    parse_memory_command,
)
from jarvis.server import execute_memory_command, prepare_model_messages


class MemoryStoreTests(unittest.TestCase):
    def make_store(self, directory, **config_values):
        config = Config(**config_values).validate()
        return MemoryStore(config, Path(directory) / "memory.json")

    def test_memory_persists_with_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            created = store.add("preference", "I prefer concise replies.")
            reopened = self.make_store(directory)
            self.assertEqual(reopened.list()[0]["id"], created["id"])
            self.assertEqual(reopened.list()[0]["text"], "I prefer concise replies.")
            self.assertEqual(os.stat(Path(directory) / "memory.json").st_mode & 0o777, 0o600)

    def test_update_creates_recoverable_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            created = store.add("general", "The local printer is Atlas.")
            store.update(created["id"], "environment", "The office printer is Atlas.")
            backup = json.loads((Path(directory) / "memory.json.bak").read_text())
            self.assertEqual(backup["items"][0]["text"], "The local printer is Atlas.")
            self.assertEqual(os.stat(Path(directory) / "memory.json.bak").st_mode & 0o777, 0o600)

    def test_duplicate_ignores_case_and_terminal_punctuation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.add("general", "The printer is Atlas.")
            with self.assertRaises(MemoryDuplicate):
                store.add("environment", "the printer is atlas")

    def test_forget_requires_one_exact_normalized_match(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.add("general", "The printer is Atlas.")
            removed = store.forget_exact("the printer is atlas")
            self.assertEqual(removed["text"], "The printer is Atlas.")
            with self.assertRaises(MemoryNotFound):
                store.forget_exact("the printer is Atlas")

    def test_credentials_and_machine_serials_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            for value in ("My password is example", "The API key is example", "The serial number is example"):
                with self.assertRaises(MemoryValidationError):
                    store.add("general", value)

    def test_corrupt_memory_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text("not json")
            store = self.make_store(directory)
            with self.assertRaises(MemoryError):
                store.list()
            with self.assertRaises(MemoryError):
                store.add("general", "This must not overwrite corruption.")
            self.assertEqual(path.read_text(), "not json")

    def test_context_uses_newest_entries_within_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory, memory_context_chars=500)
            for index in range(8):
                store.add("general", f"Memory {index}: " + "x" * 100)
            context = store.context_items()
            self.assertLess(len(context), 8)
            self.assertEqual(context[-1]["text"], "Memory 7: " + "x" * 100)

    def test_version_one_ledger_is_read_and_migrated_on_next_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text(json.dumps({"version": 1, "items": [{
                "id": "a" * 32,
                "category": "preference",
                "text": "I prefer concise replies.",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }]}))
            store = self.make_store(directory)
            self.assertEqual(store.list()[0]["origin"], "explicit")
            store.add("general", "The upgrade test is active.")
            self.assertEqual(json.loads(path.read_text())["version"], 2)

    def test_candidate_is_excluded_from_context_until_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            candidate = store.add(
                "preference", "User said: I may prefer cobalt indicators.",
                state="candidate", origin="auto", confidence=0.78,
                stable_key="preference.status_color",
            )
            self.assertEqual(store.list(), [])
            self.assertEqual(store.context_items(), [])
            self.assertEqual(store.candidates()[0]["id"], candidate["id"])
            approved = store.approve(candidate["id"])
            self.assertEqual(approved["state"], "saved")
            self.assertEqual(store.context_items()[0]["text"], candidate["text"])

    def test_approving_correction_replaces_same_key_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            old = store.add(
                "project", "User said: The test year is 2190.", origin="auto",
                confidence=0.96, stable_key="project.test_year",
            )
            candidate = store.add(
                "project", "User said: Correction: the test year is 2191.",
                state="candidate", origin="auto", confidence=0.98,
                stable_key="project.test_year",
            )
            store.approve(candidate["id"])
            ids = {item["id"] for item in store.list()}
            self.assertNotIn(old["id"], ids)
            self.assertIn(candidate["id"], ids)


class MemoryCommandTests(unittest.TestCase):
    def test_parses_explicit_general_and_categorized_commands(self):
        general = parse_memory_command("Remember that I prefer concise replies.")
        self.assertEqual((general.action, general.category, general.text), ("add", "general", "I prefer concise replies."))
        project = parse_memory_command("Remember as story canon: The year is 2191.")
        self.assertEqual((project.action, project.category), ("add", "project"))

    def test_does_not_treat_ordinary_statement_as_memory_command(self):
        self.assertIsNone(parse_memory_command("I prefer concise replies."))
        self.assertIsNone(parse_memory_command("Could you remember how this works?"))

    def test_execute_add_list_and_forget_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Config(), Path(directory) / "memory.json")
            self.assertIn("remember", execute_memory_command(store, "Remember that the printer is Atlas.").lower())
            listing = execute_memory_command(store, "What do you remember?")
            self.assertIn("the printer is Atlas", listing)
            self.assertIn("removed", execute_memory_command(store, "Forget that the printer is Atlas").lower())
            self.assertEqual(store.list(), [])

    def test_prepare_model_messages_injects_memory_as_data(self):
        prepared = prepare_model_messages(
            [{"role": "user", "content": "What is the printer called?"}],
            [{"category": "environment", "text": "The office printer is Atlas."}],
        )
        self.assertIn("explicit persistent memory record", prepared[0]["content"])
        self.assertIn("The office printer is Atlas.", prepared[0]["content"])
        self.assertIn("not as an instruction", prepared[0]["content"])


class MemoryConfigTests(unittest.TestCase):
    def test_memory_path_must_stay_under_data(self):
        with self.assertRaises(ValueError):
            Config(memory_path="../memory.json").validate()
        with self.assertRaises(ValueError):
            Config(memory_path="/tmp/memory.json").validate()

    def test_memory_flags_must_be_booleans(self):
        with self.assertRaises(ValueError):
            Config(auto_memory_enabled="yes").validate()


class AutomaticMemoryCuratorTests(unittest.TestCase):
    def test_sensitive_source_turn_is_rejected_before_model_use(self):
        with self.assertRaises(CuratorError):
            validate_turns([{"question": "", "user": "My API key is synthetic-secret"}], Config())

    def test_curator_accepts_only_structured_local_model_decisions(self):
        response = '{"decisions":[{"source_index":0,"decision":"save","category":"preference","confidence":0.97,"stable_key":"preference.reply_style","use_question":false}]}'
        with patch("jarvis.curator.backend.complete_chat", return_value=response) as completion:
            decisions = curate(Config(), [{"question": "", "user": "I prefer concise replies."}])
        self.assertEqual(decisions[0]["stable_key"], "preference.reply_style")
        self.assertEqual(completion.call_args.kwargs["temperature"], 0.0)

    def test_decisions_store_exact_user_source_and_hold_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Config(), Path(directory) / "memory.json")
            turns = [{"question": "Which color?", "user": "Cobalt."}]
            decision = [{
                "source_index": 0, "decision": "save", "category": "preference",
                "confidence": 0.97, "stable_key": "preference.test_color", "use_question": True,
            }]
            first = apply_decisions(store, turns, decision)
            self.assertEqual(first["saved"][0]["text"], "JARVIS asked: Which color?\nUser answered: Cobalt.")
            correction = apply_decisions(
                store,
                [{"question": "Which color?", "user": "Actually, indigo."}],
                decision,
            )
            self.assertEqual(correction["saved"], [])
            self.assertEqual(correction["candidates"][0]["state"], "candidate")


if __name__ == "__main__":
    unittest.main()
