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
from jarvis.speech import SpeechError, parse_installed_voices, prepare_speech_text, resolve_speech_options, validate_text
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
            {"name": "Daniel", "locale": "en_GB"},
            {"name": "Eddy (English (UK))", "locale": "en_GB"},
        ))

    def test_browser_speech_options_require_an_installed_english_voice_and_bounded_rate(self):
        voices = (
            {"name": "Daniel", "locale": "en_GB"},
            {"name": "Reed (English (UK))", "locale": "en_GB"},
        )
        with patch("jarvis.speech.installed_voices", return_value=voices):
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
