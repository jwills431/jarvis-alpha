import json
import io
import os
import subprocess
import struct
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jarvis.config import Config, load_config
from jarvis.backend import BackendError, count_unsupported_script_characters, sanitize_sse_line, stream_chat
from jarvis.server import SYSTEM_PROMPT, JarvisServer, exact_spelling_recall, extract_authoritative_spellings, is_source_bound_request, prepare_model_messages, validate_messages
from jarvis import speech
from jarvis.speech import (
    SpeechError,
    voice_engine,
    available_voices,
    default_voice,
    length_scale_for_rate,
    parse_installed_voices,
    piper_command,
    prepare_speech_text,
    resolve_speech_options,
    validate_text,
)
from jarvis.transcription import NoSpeechDetected, TranscriptionError, TranscriptionProcessError, TranscriptionTimeout, transcribe, validate_speech_energy, validate_transcript, validate_wav


def make_wav(frames=4800, channels=1, rate=16000, amplitude=0, steady=False):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        sample_count = frames * channels
        if amplitude:
            pattern = struct.pack("<h", amplitude) * 160 + struct.pack("<h", -amplitude) * 160
            quiet_samples = 0 if steady else min(sample_count, 960)
            signal_samples = sample_count - quiet_samples
            signal = (pattern * ((signal_samples + 319) // 320))[:signal_samples * 2]
            payload = b"\0\0" * quiet_samples + signal
        else:
            payload = b"\0\0" * sample_count
        audio.writeframes(payload)
    return output.getvalue()


def make_impulse_wav(frames=16000):
    levels = [12000, 8000, 5000, 3000, 1800, 900, 400, 200]
    samples = array('h', [0]) * frames
    start = frames // 2
    for window_index, level in enumerate(levels):
        offset = start + window_index * 320
        for sample_index in range(offset, min(offset + 320, frames)):
            samples[sample_index] = level if sample_index % 2 == 0 else -level
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(samples.tobytes())
    return output.getvalue()


class ConfigTests(unittest.TestCase):
    def test_default_config_is_loopback(self):
        self.assertEqual(Config().validate().app_host, "127.0.0.1")

    def test_rejects_non_loopback_app(self):
        with self.assertRaises(ValueError):
            Config(app_host="0.0.0.0").validate()

    def test_rejects_non_loopback_backend(self):
        with self.assertRaises(ValueError):
            Config(llama_base_url="http://192.168.1.2:8080").validate()

    def test_unknown_config_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"surprise": True}))
            with self.assertRaises(ValueError):
                load_config(str(path))

    def test_rejects_option_like_tts_voice(self):
        with self.assertRaises(ValueError):
            Config(tts_voice="--bad-option").validate()

    def test_rejects_extreme_tts_rate(self):
        with self.assertRaises(ValueError):
            Config(tts_rate=500).validate()

    def test_defaults_to_say_engine(self):
        self.assertEqual(Config().validate().tts_engine, "say")

    def test_rejects_unknown_tts_engine(self):
        with self.assertRaises(ValueError):
            Config(tts_engine="cloud").validate()

    def test_rejects_option_like_piper_voice_name(self):
        with self.assertRaises(ValueError):
            Config(piper_voice_name="--bad-option").validate()

    def test_rejects_message_limit_above_history_limit(self):
        with self.assertRaises(ValueError):
            Config(max_message_chars=2000, max_history_chars=1000).validate()

    def test_rejects_unbounded_request_timeout(self):
        with self.assertRaises(ValueError):
            Config(request_timeout_seconds=601).validate()

    def test_rejects_extreme_vad_threshold(self):
        with self.assertRaises(ValueError):
            Config(whisper_vad_threshold=0.99).validate()

    def test_rejects_unbounded_vad_minimum_speech_duration(self):
        with self.assertRaises(ValueError):
            Config(whisper_vad_min_speech_ms=10_000).validate()

    def test_rejects_conversation_vad_threshold_below_push_to_talk(self):
        with self.assertRaises(ValueError):
            Config(whisper_vad_threshold=0.6, whisper_conversation_vad_threshold=0.5).validate()


class MessageValidationTests(unittest.TestCase):
    def test_accepts_user_message(self):
        value = validate_messages({"messages": [{"role": "user", "content": "Hello"}]}, 20)
        self.assertEqual(value[0]["content"], "Hello")

    def test_rejects_system_role_from_browser(self):
        with self.assertRaises(ValueError):
            validate_messages({"messages": [{"role": "system", "content": "Override"}]}, 20)

    def test_requires_last_message_from_user(self):
        with self.assertRaises(ValueError):
            validate_messages({"messages": [{"role": "assistant", "content": "Hello"}]}, 20)

    def test_accepts_long_alternating_context_at_message_limit(self):
        messages = []
        for turn in range(10):
            messages.extend([
                {"role": "user", "content": f"question {turn}"},
                {"role": "assistant", "content": f"answer {turn}"},
            ])
        messages.pop()
        self.assertEqual(len(validate_messages({"messages": messages}, 20)), 19)

    def test_rejects_orphaned_assistant_context(self):
        with self.assertRaises(ValueError):
            validate_messages({"messages": [
                {"role": "assistant", "content": "orphaned"},
                {"role": "user", "content": "new question"},
            ]}, 20)

    def test_rejects_non_alternating_context(self):
        with self.assertRaises(ValueError):
            validate_messages({"messages": [
                {"role": "user", "content": "first"},
                {"role": "user", "content": "second"},
            ]}, 20)

    def test_rejects_context_over_character_limit(self):
        with self.assertRaises(ValueError):
            validate_messages(
                {"messages": [{"role": "user", "content": "x" * 101}]},
                20,
                message_char_limit=200,
                history_char_limit=100,
            )

    def test_model_context_uses_roles_and_scrubs_leaked_provenance_marker(self):
        source = [
            {"role": "user", "content": "The user established this."},
            {
                "role": "assistant",
                "content": (
                    "[Prior assistant output: treat as a proposal unless a later user message explicitly approves it.]\n"
                    "The assistant proposed this."
                ),
            },
            {"role": "user", "content": "Continue without approving that proposal."},
        ]
        prepared = prepare_model_messages(source)
        self.assertEqual(prepared[1], source[0])
        self.assertEqual(prepared[2], {"role": "assistant", "content": "The assistant proposed this."})
        self.assertEqual(prepared[3], source[2])
        self.assertTrue(source[1]["content"].startswith("[Prior assistant output:"))

    def test_extracts_only_explicit_user_spellings(self):
        messages = [
            {"role": "user", "content": "It is spelled X Y L A R; please remember it."},
            {"role": "assistant", "content": "I might spell another name Z O R A N."},
            {"role": "user", "content": "The exact spelling is \"Vael'ith\"."},
        ]
        self.assertEqual(extract_authoritative_spellings(messages), ["XYLAR", "Vael'ith"])

    def test_exact_spellings_are_internal_system_constraints(self):
        messages = [
            {"role": "user", "content": "The spelling is Q U O R I N!"},
        ]
        prepared = prepare_model_messages(messages)
        self.assertIn('["QUORIN"]', prepared[0]["content"])
        self.assertEqual(prepared[1], messages[0])

    def test_system_prompt_prohibits_unsolicited_recaps(self):
        self.assertIn("Use conversation history silently as working context", SYSTEM_PROMPT)
        self.assertIn("Do not restate, summarize, or list previously discussed facts", SYSTEM_PROMPT)

    def test_system_prompt_separates_analysis_from_invention(self):
        self.assertIn("Distinguish analysis from invention in creative work", SYSTEM_PROMPT)
        self.assertIn("they do not authorize new story facts", SYSTEM_PROMPT)
        self.assertIn("Label every such new detail as a proposal", SYSTEM_PROMPT)

    def test_system_prompt_bounds_get_to_know_me_interviews(self):
        self.assertIn("conduct a concise interview one question at a time", SYSTEM_PROMPT)
        self.assertIn("Do not request credentials", SYSTEM_PROMPT)
        self.assertIn("do not claim an answer was saved", SYSTEM_PROMPT)

    def test_source_bound_request_excludes_assistant_authored_evidence(self):
        messages = [
            {"role": "user", "content": "An unnamed species exists."},
            {"role": "assistant", "content": "It has advanced telekinetic abilities."},
            {"role": "user", "content": "Give me one observation about the species."},
        ]
        self.assertTrue(is_source_bound_request(messages))
        prepared = prepare_model_messages(messages)
        self.assertEqual([message["role"] for message in prepared], ["system", "user"])
        self.assertNotIn("telekinetic", json.dumps(prepared).lower())
        self.assertIn("source-bound request", prepared[0]["content"])
        self.assertIn("An unnamed species exists.", prepared[1]["content"])
        self.assertIn("Current request", prepared[1]["content"])

    def test_recap_is_source_bound(self):
        messages = [{"role": "user", "content": "Recap only the facts I established."}]
        self.assertTrue(is_source_bound_request(messages))

    def test_direct_question_about_assistant_output_retains_that_output(self):
        messages = [
            {"role": "user", "content": "Review this concept."},
            {"role": "assistant", "content": "I proposed a telepathic species."},
            {"role": "user", "content": "Analyze your previous response."},
        ]
        self.assertFalse(is_source_bound_request(messages))
        self.assertIn("telepathic", json.dumps(prepare_model_messages(messages)).lower())

    def test_direct_exact_spelling_recall_is_deterministic(self):
        messages = [
            {"role": "user", "content": "The species name is spelled Q U O R I N; use it exactly."},
            {"role": "assistant", "content": "I will use Quoren."},
            {"role": "user", "content": "What is the exact spelling I gave? Reply with that name only."},
        ]
        self.assertEqual(exact_spelling_recall(messages), "QUORIN")
        messages[-1]["content"] = "Continue the outline."
        self.assertIsNone(exact_spelling_recall(messages))


class ServerLifecycleTests(unittest.TestCase):
    def test_allows_immediate_loopback_restart(self):
        self.assertTrue(JarvisServer.allow_reuse_address)


class SpeechTests(unittest.TestCase):
    def test_rejects_oversized_speech(self):
        with self.assertRaises(SpeechError):
            validate_text("x" * 101, 100)

    def test_exact_uppercase_name_is_pronounced_as_a_word(self):
        displayed = "The species is QUORIN."
        self.assertEqual(prepare_speech_text(displayed, ("QUORIN",)), "The species is Quorin.")
        self.assertEqual(displayed, "The species is QUORIN.")

    def test_mixed_case_exact_name_is_not_rewritten_for_speech(self):
        self.assertEqual(prepare_speech_text("Meet Vael'ith.", ("Vael'ith",)), "Meet Vael'ith.")

    def test_speech_name_rewrite_requires_a_complete_token(self):
        self.assertEqual(prepare_speech_text("QUORIN and QUORINITE", ("QUORIN",)), "Quorin and QUORINITE")

    def test_parses_installed_voice_names_with_spaces(self):
        value = (
            "Daniel              en_GB    # Hello\n"
            "Eddy (English (UK)) en_GB    # Hello\n"
            "malformed line\n"
        )
        self.assertEqual(parse_installed_voices(value), (
            {"name": "Daniel", "locale": "en_GB", "engine": "say"},
            {"name": "Eddy (English (UK))", "locale": "en_GB", "engine": "say"},
        ))

    def test_browser_speech_options_require_an_installed_english_voice_and_bounded_rate(self):
        voices = (
            {"name": "Daniel", "locale": "en_GB", "engine": "say"},
            {"name": "Reed (English (UK))", "locale": "en_GB", "engine": "say"},
        )
        with patch("jarvis.speech.installed_voices", return_value=voices), \
             patch("jarvis.speech._say_runtime_ready", return_value=True):
            self.assertEqual(
                resolve_speech_options(Config(), "Reed (English (UK))", 205),
                ("Reed (English (UK))", 205),
            )
            with self.assertRaises(SpeechError):
                resolve_speech_options(Config(), "Uninstalled", 205)
            with self.assertRaises(SpeechError):
                resolve_speech_options(Config(), "Daniel", 500)

    def test_speech_text_uses_standard_input(self):
        observed = {}

        class Sink:
            def __init__(self):
                self.data = b""

            def write(self, value):
                self.data += value

            def close(self):
                pass

        class FakeProcess:
            def __init__(self):
                self.stdin = Sink()
                self.returncode = None

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

            def terminate(self):
                self.returncode = -15

            def kill(self):
                self.returncode = -9

        def fake_popen(command, **kwargs):
            observed["command"] = command
            observed["process"] = FakeProcess()
            return observed["process"]

        with patch("jarvis.speech.runtime_ready", return_value=True), patch("jarvis.speech.subprocess.Popen", side_effect=fake_popen):
            speech.speak(Config(), "private reply text")
        self.assertNotIn("private reply text", observed["command"])
        self.assertEqual(observed["process"].stdin.data, b"private reply text")
        self.assertEqual(observed["command"][-2:], ["-r", "190"])

    def test_speech_timeout_terminates_process(self):
        class Sink:
            def write(self, value):
                pass

            def close(self):
                pass

        class TimedOutProcess:
            def __init__(self):
                self.stdin = Sink()
                self.returncode = None
                self.waits = 0
                self.terminated = False

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                self.waits += 1
                if self.waits == 1:
                    raise speech.subprocess.TimeoutExpired("say", timeout)
                self.returncode = -15
                return self.returncode

            def terminate(self):
                self.terminated = True

            def kill(self):
                self.returncode = -9

        process = TimedOutProcess()
        with patch("jarvis.speech.runtime_ready", return_value=True), patch("jarvis.speech.subprocess.Popen", return_value=process):
            with self.assertRaises(SpeechError):
                speech.speak(Config(tts_timeout_seconds=5), "bounded speech")
        self.assertTrue(process.terminated)

    def test_both_engines_are_offered_together_for_comparison(self):
        # The engine is a property of the voice, so a neural voice and the
        # built-in ones appear in one list and can be switched without a restart.
        config = Config(tts_engine="say", piper_voice_name="JARVIS (British)")
        say_voices = ({"name": "Daniel", "locale": "en_GB", "engine": "say"},)
        with patch("jarvis.speech.english_voices", return_value=say_voices), \
             patch("jarvis.speech._say_runtime_ready", return_value=True), \
             patch("jarvis.speech._piper_runtime_ready", return_value=True):
            voices = available_voices(config)
            self.assertEqual([voice["name"] for voice in voices], ["Daniel", "JARVIS (British)"])
            self.assertEqual(voice_engine(config, "Daniel"), "say")
            self.assertEqual(voice_engine(config, "JARVIS (British)"), "piper")
            # Either voice is selectable regardless of the configured default.
            self.assertEqual(resolve_speech_options(config, "JARVIS (British)", 205), ("JARVIS (British)", 205))
            self.assertEqual(resolve_speech_options(config, "Daniel", 205), ("Daniel", 205))

    def test_piper_voice_is_absent_until_its_runtime_is_installed(self):
        config = Config(tts_engine="piper", piper_voice_name="JARVIS (British)")
        say_voices = ({"name": "Daniel", "locale": "en_GB", "engine": "say"},)
        with patch("jarvis.speech.english_voices", return_value=say_voices), \
             patch("jarvis.speech._say_runtime_ready", return_value=True), \
             patch("jarvis.speech._piper_runtime_ready", return_value=False):
            self.assertEqual([voice["name"] for voice in available_voices(config)], ["Daniel"])
            # The configured default is unreachable, so a usable voice is chosen
            # rather than naming one that cannot speak.
            self.assertEqual(default_voice(config), "Daniel")
            with self.assertRaises(SpeechError):
                resolve_speech_options(config, "JARVIS (British)", 205)

    def test_a_colliding_piper_name_stays_distinguishable(self):
        config = Config(tts_engine="say", piper_voice_name="Daniel")
        say_voices = ({"name": "Daniel", "locale": "en_GB", "engine": "say"},)
        with patch("jarvis.speech.english_voices", return_value=say_voices), \
             patch("jarvis.speech._say_runtime_ready", return_value=True), \
             patch("jarvis.speech._piper_runtime_ready", return_value=True):
            names = [voice["name"] for voice in available_voices(config)]
            self.assertEqual(names, ["Daniel", "Daniel (Piper)"])
            self.assertEqual(voice_engine(config, "Daniel"), "say")
            self.assertEqual(voice_engine(config, "Daniel (Piper)"), "piper")

    def test_length_scale_maps_and_clamps_rate(self):
        self.assertEqual(length_scale_for_rate(190), 1.0)
        self.assertLess(length_scale_for_rate(350), 1.0)
        self.assertGreater(length_scale_for_rate(120), 1.0)
        self.assertGreaterEqual(length_scale_for_rate(350), speech.PIPER_LENGTH_SCALE_MIN)
        self.assertLessEqual(length_scale_for_rate(120), speech.PIPER_LENGTH_SCALE_MAX)

    def test_piper_command_never_contains_the_text(self):
        # piper-tts takes text as a positional argument; the worker protocol
        # keeps it on standard input so it never reaches an argument vector.
        command = piper_command(Config(tts_engine="piper"))
        self.assertIn("--model", command)
        self.assertIn("--serve", command)
        self.assertTrue(command[1].endswith("piper_synthesize.py"))
        self.assertNotIn("private reply text", command)

    def test_playback_is_skipped_when_stop_lands_between_render_and_playback(self):
        # Piper renders a whole phrase before playing it. A stop that arrives in
        # that gap has no process to terminate, so the guard must refuse to start
        # playback rather than speaking a phrase the user already interrupted.
        speech.stop()
        with speech._lock:
            rendered_generation = speech._generation
        speech.stop()
        calls = []

        def fake_popen(command, **kwargs):
            calls.append(command)
            raise AssertionError("interrupted playback must not spawn a process")

        with patch("jarvis.speech.subprocess.Popen", side_effect=fake_popen):
            speech._play_audio(Config(tts_engine="piper"), "/tmp/jarvis-test.wav", rendered_generation)
        self.assertEqual(calls, [])

    def test_playback_proceeds_when_its_generation_still_owns_the_channel(self):
        speech.stop()
        with speech._lock:
            current = speech._generation
        commands = []

        class DoneProcess:
            returncode = 0

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return 0

            def terminate(self):
                self.returncode = -15

            def kill(self):
                self.returncode = -9

        def fake_popen(command, **kwargs):
            commands.append(command)
            return DoneProcess()

        with patch("jarvis.speech.subprocess.Popen", side_effect=fake_popen):
            speech._play_audio(Config(tts_engine="piper"), "/tmp/jarvis-test.wav", current)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], str(speech.AFPLAY))
        speech.stop()

    def test_newer_utterance_supersedes_an_earlier_pending_render(self):
        speech.stop()
        with speech._lock:
            earlier = speech._generation
        # A newer phrase claims the channel while the earlier one was rendering.
        with speech._lock:
            speech._claim()
        calls = []
        with patch("jarvis.speech.subprocess.Popen", side_effect=lambda *a, **k: calls.append(a)):
            speech._play_audio(Config(tts_engine="piper"), "/tmp/jarvis-test.wav", earlier)
        self.assertEqual(calls, [], "an out-of-order phrase must not play after a newer one starts")
        speech.stop()


    def test_removes_backend_metadata(self):
        raw = b'data: {"model":"/private/path/model.gguf","system_fingerprint":"secret","choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}\n'
        clean = sanitize_sse_line(raw)
        self.assertEqual(clean, b'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}\n\n')
        self.assertNotIn(b"model.gguf", clean)

    def test_preserves_done_marker(self):
        self.assertEqual(sanitize_sse_line(b"data: [DONE]\n"), b"data: [DONE]\n\n")

    def test_backend_connection_failure_is_bounded(self):
        with patch("jarvis.backend._headers", return_value={}), patch(
            "jarvis.backend.urllib.request.urlopen", side_effect=OSError("offline")
        ):
            with self.assertRaises(BackendError):
                list(stream_chat(Config(), [{"role": "user", "content": "test"}]))

    def test_counts_unsupported_model_scripts(self):
        self.assertEqual(count_unsupported_script_characters("English only"), 0)
        self.assertEqual(count_unsupported_script_characters("测试内容"), 4)

    def test_rejects_unexpected_script_before_stream_completion(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                return iter([
                    'data: {"choices":[{"delta":{"content":"测"},"finish_reason":null}]}\n'.encode(),
                    'data: {"choices":[{"delta":{"content":"试"},"finish_reason":null}]}\n'.encode(),
                    'data: {"choices":[{"delta":{"content":"内"},"finish_reason":null}]}\n'.encode(),
                    b"data: [DONE]\n",
                ])

        with patch("jarvis.backend._headers", return_value={}), patch(
            "jarvis.backend.urllib.request.urlopen", return_value=FakeResponse()
        ):
            with self.assertRaises(BackendError):
                list(stream_chat(Config(), [{"role": "user", "content": "test"}]))


    # --- Resident Piper worker ---------------------------------------------
    #
    # These run a real subprocess speaking the real protocol. A fake interpreter
    # stands in for the piper virtual environment: it records each start, then
    # answers requests exactly as scripts/piper_synthesize.py --serve does.

    FAKE_WORKER = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys, wave\n"
        "open(os.environ['WORKER_STARTS'], 'a').write('start\\n')\n"
        "if os.environ.get('WORKER_FAIL_LOAD'): sys.exit(1)\n"
        "print(json.dumps({'status': 'ready'}), flush=True)\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    open(os.environ['WORKER_REQUESTS'], 'a').write(line)\n"
        "    if os.environ.get('WORKER_DIE_ON_REQUEST'): sys.exit(1)\n"
        "    with wave.open(request['output_file'], 'wb') as out:\n"
        "        out.setnchannels(1); out.setsampwidth(2); out.setframerate(22050)\n"
        "        out.writeframes(b'\\x00\\x00' * 2205)\n"
        "    print(json.dumps({'status': 'ok'}), flush=True)\n"
    )

    def _worker_fixture(self, root):
        interpreter = Path(root) / "python3"
        interpreter.write_text(self.FAKE_WORKER)
        interpreter.chmod(0o755)
        model = Path(root) / "voice.onnx"
        model.write_text("")
        starts = Path(root) / "starts.log"
        requests = Path(root) / "requests.log"
        starts.write_text("")
        requests.write_text("")
        os.environ["WORKER_STARTS"] = str(starts)
        os.environ["WORKER_REQUESTS"] = str(requests)
        self.addCleanup(speech.shutdown)
        for key in ("WORKER_STARTS", "WORKER_REQUESTS", "WORKER_DIE_ON_REQUEST", "WORKER_FAIL_LOAD"):
            self.addCleanup(os.environ.pop, key, None)
        speech.shutdown()
        config = Config(tts_engine="piper", piper_python=str(interpreter), piper_voice=str(model))
        return config, starts, requests

    def _piper_patches(self):
        return (
            patch("jarvis.speech.runtime_ready", return_value=True),
            patch("jarvis.speech.voice_engine", return_value="piper"),
        )

    def test_the_voice_model_loads_once_across_many_phrases(self):
        # The point of the worker: three sentences must not pay three model
        # loads, which is what made the pause between spoken sentences long.
        with tempfile.TemporaryDirectory() as root:
            config, starts, requests = self._worker_fixture(root)
            played = []
            ready, engine = self._piper_patches()
            with ready, engine, patch("jarvis.speech._play_audio", side_effect=lambda *a, **k: played.append(a)):
                for phrase in ("First sentence.", "Second sentence.", "Third sentence."):
                    speech.speak(config, phrase)
            self.assertEqual(starts.read_text().count("start"), 1)
            self.assertEqual(len(played), 3)
            sent = [json.loads(line) for line in requests.read_text().splitlines()]
            self.assertEqual([item["text"] for item in sent],
                             ["First sentence.", "Second sentence.", "Third sentence."])

    def test_worker_restarts_once_after_it_dies(self):
        with tempfile.TemporaryDirectory() as root:
            config, starts, _ = self._worker_fixture(root)
            ready, engine = self._piper_patches()
            with ready, engine, patch("jarvis.speech._play_audio"):
                speech.speak(config, "First sentence.")
                self.assertEqual(starts.read_text().count("start"), 1)
                with speech._worker_lock:
                    speech._worker.terminate()
                speech.speak(config, "Second sentence.")
            self.assertEqual(starts.read_text().count("start"), 2)

    def test_a_worker_that_fails_every_request_reports_failure(self):
        with tempfile.TemporaryDirectory() as root:
            config, starts, _ = self._worker_fixture(root)
            os.environ["WORKER_DIE_ON_REQUEST"] = "1"
            ready, engine = self._piper_patches()
            with ready, engine, patch("jarvis.speech._play_audio"):
                with self.assertRaises(SpeechError):
                    speech.speak(config, "Doomed sentence.")
            # Retried exactly once rather than looping.
            self.assertEqual(starts.read_text().count("start"), 2)

    def test_a_worker_that_cannot_load_the_voice_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as root:
            config, _, _ = self._worker_fixture(root)
            os.environ["WORKER_FAIL_LOAD"] = "1"
            ready, engine = self._piper_patches()
            with ready, engine, patch("jarvis.speech._play_audio"):
                with self.assertRaises(SpeechError):
                    speech.speak(config, "Never spoken.")

    def test_the_utterance_never_reaches_the_worker_arguments(self):
        with tempfile.TemporaryDirectory() as root:
            config, _, requests = self._worker_fixture(root)
            ready, engine = self._piper_patches()
            with ready, engine, patch("jarvis.speech._play_audio"):
                speech.speak(config, "private reply text")
            self.assertNotIn("private reply text", " ".join(piper_command(config)))
            # It arrived on standard input instead.
            self.assertIn("private reply text", requests.read_text())

    def test_stop_during_rendering_discards_the_phrase_and_its_file(self):
        with tempfile.TemporaryDirectory() as root:
            config, _, _ = self._worker_fixture(root)
            rendered = []

            def render_then_stop(cfg, text, path, scale):
                rendered.append(path)
                Path(path).write_bytes(b"RIFF")
                # The user presses Stop while this phrase was still rendering.
                speech.stop()

            ready, engine = self._piper_patches()
            with ready, engine, \
                 patch("jarvis.speech._render_piper", side_effect=render_then_stop), \
                 patch("jarvis.speech.subprocess.Popen", side_effect=AssertionError("must not play")):
                speech.speak(config, "interrupted reply text")
            self.assertFalse(os.path.exists(rendered[0]), "the discarded render must be deleted")

    def test_shutdown_releases_the_worker(self):
        with tempfile.TemporaryDirectory() as root:
            config, _, _ = self._worker_fixture(root)
            ready, engine = self._piper_patches()
            with ready, engine, patch("jarvis.speech._play_audio"):
                speech.speak(config, "First sentence.")
            self.assertIsNotNone(speech._worker)
            process = speech._worker.process
            speech.shutdown()
            self.assertIsNone(speech._worker)
            self.assertIsNotNone(process.poll(), "the worker process must be reaped")


class StreamSanitizationTests(unittest.TestCase):
    def test_removes_backend_metadata(self):
        raw = b'data: {"model":"/private/path/model.gguf","system_fingerprint":"secret","choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}\n'
        clean = sanitize_sse_line(raw)
        self.assertEqual(clean, b'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}\n\n')
        self.assertNotIn(b"model.gguf", clean)

    def test_preserves_done_marker(self):
        self.assertEqual(sanitize_sse_line(b"data: [DONE]\n"), b"data: [DONE]\n\n")

    def test_backend_connection_failure_is_bounded(self):
        with patch("jarvis.backend._headers", return_value={}), patch(
            "jarvis.backend.urllib.request.urlopen", side_effect=OSError("offline")
        ):
            with self.assertRaises(BackendError):
                list(stream_chat(Config(), [{"role": "user", "content": "test"}]))

    def test_counts_unsupported_model_scripts(self):
        self.assertEqual(count_unsupported_script_characters("English only"), 0)
        self.assertEqual(count_unsupported_script_characters("测试内容"), 4)

    def test_rejects_unexpected_script_before_stream_completion(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                return iter([
                    'data: {"choices":[{"delta":{"content":"测"},"finish_reason":null}]}\n'.encode(),
                    'data: {"choices":[{"delta":{"content":"试"},"finish_reason":null}]}\n'.encode(),
                    'data: {"choices":[{"delta":{"content":"内"},"finish_reason":null}]}\n'.encode(),
                    b"data: [DONE]\n",
                ])

        with patch("jarvis.backend._headers", return_value={}), patch(
            "jarvis.backend.urllib.request.urlopen", return_value=FakeResponse()
        ):
            with self.assertRaises(BackendError):
                list(stream_chat(Config(), [{"role": "user", "content": "test"}]))

class TranscriptionTests(unittest.TestCase):
    def test_accepts_bounded_pcm_wav(self):
        self.assertEqual(validate_wav(make_wav()), 4800)

    def test_rejects_stereo_audio(self):
        with self.assertRaises(TranscriptionError):
            validate_wav(make_wav(channels=2))

    def test_rejects_wrong_sample_rate(self):
        with self.assertRaises(TranscriptionError):
            validate_wav(make_wav(rate=44100))

    def test_rejects_audio_over_thirty_seconds(self):
        with self.assertRaises(TranscriptionError):
            validate_wav(make_wav(frames=480001))

    def test_rejects_audio_under_three_tenths_second(self):
        with self.assertRaises(TranscriptionError):
            validate_wav(make_wav(frames=4799))

    def test_rejects_silent_audio(self):
        with self.assertRaises(NoSpeechDetected):
            validate_speech_energy(make_wav())

    def test_accepts_sustained_speech_energy(self):
        validate_speech_energy(make_wav(amplitude=2000))

    def test_accepts_sustained_speech_energy_with_conversation_gate(self):
        validate_speech_energy(
            make_wav(amplitude=2000),
            min_active_windows=6,
            min_peak_to_floor_ratio=2.4,
        )

    def test_rejects_steady_fan_like_energy(self):
        with self.assertRaises(NoSpeechDetected):
            validate_speech_energy(make_wav(amplitude=700, steady=True))

    def test_rejects_short_high_energy_impact(self):
        with self.assertRaises(NoSpeechDetected):
            validate_speech_energy(make_impulse_wav())

    def test_rejects_music_symbols_as_transcript(self):
        with self.assertRaises(NoSpeechDetected):
            validate_transcript("♪ ♫ ♪")

    def test_rejects_bracketed_non_speech_caption(self):
        with self.assertRaises(NoSpeechDetected):
            validate_transcript("[Music]")

    def test_rejects_known_canned_video_outro_hallucination(self):
        with self.assertRaises(NoSpeechDetected):
            validate_transcript("Thanks for watching!")

    def test_accepts_standalone_courtesy_phrase(self):
        self.assertEqual(validate_transcript("Thank you."), "Thank you.")

    def test_accepts_spoken_transcript_text(self):
        self.assertEqual(validate_transcript(" Hello there. "), "Hello there.")

    def test_temporary_audio_is_deleted(self):
        observed_path = None

        def fake_run(command, **kwargs):
            nonlocal observed_path
            observed_path = command[command.index("--file") + 1]
            self.assertTrue(os.path.exists(observed_path))
            self.assertIn("--vad", command)
            self.assertEqual(command[command.index("--vad-model") + 1], str(Path("models/whisper/ggml-silero-v6.2.0.bin").resolve()))
            self.assertEqual(command[command.index("--vad-threshold") + 1], "0.5")
            self.assertEqual(command[command.index("--vad-min-speech-duration-ms") + 1], "250")
            return SimpleNamespace(returncode=0, stdout=" local transcription ")

        with patch("jarvis.transcription.runtime_ready", return_value=True), patch("jarvis.transcription.subprocess.run", side_effect=fake_run):
            self.assertEqual(transcribe(Config(), make_wav(amplitude=2000)), "local transcription")
        self.assertIsNotNone(observed_path)
        self.assertFalse(os.path.exists(observed_path))

    def test_conversation_mode_uses_stricter_vad_threshold(self):
        def fake_run(command, **kwargs):
            self.assertEqual(command[command.index("--vad-threshold") + 1], "0.6")
            return SimpleNamespace(returncode=0, stdout="thank you")

        with patch("jarvis.transcription.runtime_ready", return_value=True), patch(
            "jarvis.transcription.subprocess.run", side_effect=fake_run
        ):
            self.assertEqual(
                transcribe(Config(), make_wav(amplitude=2000), conversation_mode=True),
                "thank you",
            )

    def test_transcription_timeout_is_distinct_and_deletes_audio(self):
        observed_path = None

        def fake_run(command, **kwargs):
            nonlocal observed_path
            observed_path = command[command.index("--file") + 1]
            raise subprocess.TimeoutExpired(command[0], 45)

        with patch("jarvis.transcription.runtime_ready", return_value=True), patch(
            "jarvis.transcription.subprocess.run", side_effect=fake_run
        ):
            with self.assertRaises(TranscriptionTimeout):
                transcribe(Config(), make_wav(amplitude=2000))
        self.assertIsNotNone(observed_path)
        self.assertFalse(os.path.exists(observed_path))

    def test_transcription_process_failure_is_distinct(self):
        failed = SimpleNamespace(returncode=1, stdout="")
        with patch("jarvis.transcription.runtime_ready", return_value=True), patch(
            "jarvis.transcription.subprocess.run", return_value=failed
        ):
            with self.assertRaises(TranscriptionProcessError):
                transcribe(Config(), make_wav(amplitude=2000))


if __name__ == "__main__":
    unittest.main()
