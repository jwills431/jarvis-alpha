from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Config:
    app_host: str = "127.0.0.1"
    app_port: int = 8787
    llama_base_url: str = "http://127.0.0.1:8081"
    model: str = "qwen2.5-7b-instruct-q4_k_m.gguf"
    # Optional primary model backend through NVIDIA PAIR (Personal AI Router). Its
    # proxy is loopback (127.0.0.1:11434) and forwards each request to one LAN node
    # running Ollama, so the model can run on another machine's GPU and leave this
    # box's GPU to Fish — sharing it slowed both ~2.4x (measured 2026-09-10). Empty
    # keeps llama-server as the only backend. When set, llama-server stays the
    # fallback for any request PAIR fails before producing output (see backend.py).
    pair_base_url: str = ""
    pair_model: str = ""
    # Qwen 3.5 thinks before answering by default; in the trial it spent a whole
    # 400-token reply thinking and said nothing. "none" turns that off.
    pair_reasoning_effort: str = "none"
    # Per-socket-operation timeout toward PAIR: short, so an unreachable node falls
    # back quickly, but above a warm first token and a buffered tool call (~4 s).
    pair_timeout_seconds: int = 20
    # After a PAIR failure, use llama-server directly for this long rather than
    # paying the timeout on every turn while the node is off.
    pair_retry_after_seconds: int = 60
    # How long the PAIR node keeps the model loaded after JARVIS last asked. Ollama
    # unloads after 5 minutes by default (a ~4-19 s reload on the next turn), and
    # both OLLAMA_KEEP_ALIVE on the node and keep_alive on the OpenAI endpoint were
    # ignored in the trial. Ollama's native keep-alive call does stick, so JARVIS
    # sends it at startup and at most once a minute while a page is polling health:
    # warm while JARVIS is open, freed this long after it closes. "" disables it;
    # "-1" never unloads.
    pair_keep_alive: str = "30m"
    stt_enabled: bool = True
    whisper_binary: str = "runtime/whisper.cpp/build/bin/whisper-cli"
    whisper_model: str = "models/whisper/ggml-base.en.bin"
    whisper_vad_enabled: bool = True
    whisper_vad_model: str = "models/whisper/ggml-silero-v6.2.0.bin"
    whisper_vad_threshold: float = 0.5
    whisper_conversation_vad_threshold: float = 0.6
    whisper_vad_min_speech_ms: int = 250
    # Optional resident whisper.cpp server (whisper-server). Spawning whisper-cli
    # per utterance reloads the model every time, which measured ~0.9 s regardless
    # of clip length; a resident server keeps the model loaded and cuts that to
    # ~0.4-0.6 s. Empty string keeps the original spawn-per-request behaviour.
    whisper_server_url: str = ""
    transcription_timeout_seconds: int = 45
    max_audio_bytes: int = 1_000_000
    tts_enabled: bool = True
    tts_engine: str = "say"
    tts_voice: str = "Daniel"
    tts_rate: int = 190
    tts_timeout_seconds: int = 180
    max_tts_chars: int = 4_000
    piper_python: str = "runtime/piper-venv/bin/python3"
    piper_voice: str = "models/piper/en_GB-alan-medium.onnx"
    piper_voice_name: str = "JARVIS (British)"
    fish_enabled: bool = False
    fish_base_url: str = "http://127.0.0.1:8080"
    fish_voice_name: str = "JARVIS (Fish)"
    fish_reference_id: str = "jarvis"
    # Chosen by listening to a fixed-seed sweep of the same phrase (2026-08-23).
    # The previous 0.7/0.7/1.2 sat below Fish's own defaults on sampling and above
    # them on the penalty, which flattens prosody: the penalty discourages repeated
    # token patterns, and in an audio model those patterns include the rises and
    # falls that make speech sound alive. Costs nothing — render time was flat
    # across the whole sweep (3.2-3.5s for the same sentence).
    fish_temperature: float = 1.0
    fish_top_p: float = 0.95
    fish_repetition_penalty: float = 1.05
    fish_max_new_tokens: int = 1024
    request_timeout_seconds: int = 180
    max_request_bytes: int = 65_536
    max_history_messages: int = 20
    max_history_chars: int = 12_000
    max_message_chars: int = 8_000
    memory_enabled: bool = True
    auto_memory_enabled: bool = True
    memory_path: str = "data/memory.json"
    max_memory_items: int = 100
    max_memory_item_chars: int = 1_000
    max_memory_chars: int = 20_000
    max_memory_file_bytes: int = 65_536
    memory_context_chars: int = 6_000
    max_tokens: int = 512
    temperature: float = 0.6
    # --- Tool loop (Stage 0 of the capabilities plan) ---
    # Off by default: with tools disabled the chat endpoint behaves exactly as
    # before (direct llama.cpp SSE passthrough), so existing behaviour and every
    # prior test are unchanged until this is explicitly turned on. When enabled,
    # /api/chat runs the server-side propose->validate->execute->feed-back loop.
    tools_enabled: bool = False
    # Sampling temperature for tool-enabled turns. Lower than the conversational
    # `temperature` on purpose: a 7B follows the tool-calling protocol far more
    # reliably when it is more deterministic, which reduces "claimed to set a
    # timer but never called the tool" misses (a known limitation of Qwen-7B here
    # — see docs/STAGE1_TIMERS.md). Only affects turns where tools are active.
    tool_temperature: float = 0.3
    # Hybrid grammar mode. The primary path is llama.cpp's native tool-calling
    # (server started with --jinja), which constrains and returns tool_calls; our
    # own schema validation is the guarantee that a malformed call never runs. If
    # a build's native tool-calling misbehaves, set this true to *also* send a
    # GBNF grammar generated from the tool schemas. Off by default because some
    # builds reject a custom grammar alongside jinja tools.
    tool_grammar_enabled: bool = False
    # Hard cap on model<->tool round trips within a single turn, so the loop can
    # never spin. Each iteration is one model completion that may call tools.
    tool_max_iterations: int = 6
    # Per-call wall-clock budget for a tool handler, in seconds.
    tool_call_timeout_seconds: int = 20
    # On-disk audit log of tool activity (append-only JSONL), separate from chat.
    # Relative path under the project root; every proposal, execution, approval,
    # denial, and failure is recorded with a timestamp.
    tool_audit_path: str = "data/tool_audit.jsonl"
    # --- Stage 1 timers/reminders ---
    # Persisted so a pending timer survives an app restart. Firing is computed
    # from the wall clock on each client poll, so no background thread is needed.
    timers_path: str = "data/timers.json"
    max_timers: int = 50
    # Longest horizon a timer/reminder may be set for (default 7 days), bounding
    # both a relative duration and an absolute fire time.
    max_timer_seconds: int = 604_800
    # --- Server-ify (private-LAN hosting): TLS, auth, LAN bind, playback ---
    # TLS is active when both a certificate and its private key are configured.
    # Paths may be absolute (the server runs from the Linux fs) or relative to
    # the project root. Serving plain HTTP stays the default for local loopback
    # development; binding to a non-loopback address requires TLS (see validate).
    tls_cert: str = ""
    tls_key: str = ""
    # HTTP Basic auth over TLS. The password is never stored in the clear: only a
    # PBKDF2-HMAC-SHA256 digest and its salt (both lowercase hex) are kept, and
    # the server compares in constant time. Generate with scripts/make_auth.py.
    auth_enabled: bool = False
    auth_username: str = ""
    auth_password_hash: str = ""
    auth_password_salt: str = ""
    auth_pbkdf2_iterations: int = 200_000
    # Where synthesized speech is played. "host" keeps the macOS afplay path used
    # in local development; "browser" returns the rendered WAV to the web client
    # so audio plays on whichever LAN device is talking to JARVIS (the model for
    # the headless server, which has no audio output of its own).
    tts_playback: str = "host"

    @property
    def tls_enabled(self) -> bool:
        return bool(self.tls_cert) and bool(self.tls_key)

    @property
    def app_scheme(self) -> str:
        return "https" if self.tls_enabled else "http"

    def validate(self) -> "Config":
        if type(self.memory_enabled) is not bool or type(self.auto_memory_enabled) is not bool:
            raise ValueError("memory flags must be booleans")
        # app_host must be a valid IP. Loopback is always allowed. Exposing JARVIS
        # on the LAN (any non-loopback bind, e.g. 0.0.0.0) is permitted only behind
        # the full private-hosting interlock: TLS and Basic auth must both be
        # configured, so the box can never be exposed insecurely by misconfiguration.
        host_ip = ipaddress.ip_address(self.app_host)
        if not host_ip.is_loopback and not (self.tls_enabled and self.auth_enabled):
            raise ValueError("non-loopback app_host requires TLS and auth to be configured")
        backend = urlparse(self.llama_base_url)
        if backend.scheme != "http" or not backend.hostname:
            raise ValueError("llama_base_url must be an HTTP URL")
        if not ipaddress.ip_address(backend.hostname).is_loopback:
            raise ValueError("llama_base_url must use a loopback IP address")
        if self.pair_base_url:
            # PAIR itself reaches the LAN (over its own mTLS); JARVIS only ever talks
            # to the local proxy, so the loopback rule holds here too.
            pair = urlparse(self.pair_base_url)
            if pair.scheme != "http" or not pair.hostname:
                raise ValueError("pair_base_url must be an HTTP URL")
            if not ipaddress.ip_address(pair.hostname).is_loopback:
                raise ValueError("pair_base_url must use a loopback IP address")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", self.pair_model):
                raise ValueError("pair_model must name a model when pair_base_url is set")
        if self.pair_reasoning_effort not in ("", "none", "low", "medium", "high"):
            raise ValueError("pair_reasoning_effort must be empty, none, low, medium or high")
        if not 3 <= self.pair_timeout_seconds <= 120:
            raise ValueError("pair_timeout_seconds must be between 3 and 120")
        if not 0 <= self.pair_retry_after_seconds <= 3600:
            raise ValueError("pair_retry_after_seconds must be between 0 and 3600")
        if not re.fullmatch(r"|-1|\d{1,6}|\d{1,4}[smh]", self.pair_keep_alive):
            raise ValueError("pair_keep_alive must be empty, -1, seconds, or a duration like 30m")
        if not 1024 <= self.app_port <= 65535:
            raise ValueError("app_port must be between 1024 and 65535")
        if not 1 <= self.max_history_messages <= 100:
            raise ValueError("max_history_messages must be between 1 and 100")
        if not 1_000 <= self.max_history_chars <= 48_000:
            raise ValueError("max_history_chars must be between 1000 and 48000")
        if not 100 <= self.max_message_chars <= self.max_history_chars:
            raise ValueError("max_message_chars must be between 100 and max_history_chars")
        memory_path = Path(self.memory_path)
        if memory_path.is_absolute() or ".." in memory_path.parts or not memory_path.parts or memory_path.parts[0] != "data":
            raise ValueError("memory_path must be a relative path under data")
        if not 1 <= self.max_memory_items <= 500:
            raise ValueError("max_memory_items must be between 1 and 500")
        if not 100 <= self.max_memory_item_chars <= 4_000:
            raise ValueError("max_memory_item_chars must be between 100 and 4000")
        if not self.max_memory_item_chars <= self.max_memory_chars <= 100_000:
            raise ValueError("max_memory_chars must be between max_memory_item_chars and 100000")
        if not 4_096 <= self.max_memory_file_bytes <= 1_000_000:
            raise ValueError("max_memory_file_bytes must be between 4096 and 1000000")
        if not 500 <= self.memory_context_chars <= self.max_memory_chars:
            raise ValueError("memory_context_chars must be between 500 and max_memory_chars")
        if not 1 <= self.max_tokens <= 4096:
            raise ValueError("max_tokens must be between 1 and 4096")
        if not 5 <= self.request_timeout_seconds <= 600:
            raise ValueError("request_timeout_seconds must be between 5 and 600")
        if not 1_024 <= self.max_request_bytes <= 1_000_000:
            raise ValueError("max_request_bytes must be between 1024 and 1000000")
        if not 5 <= self.transcription_timeout_seconds <= 300:
            raise ValueError("transcription_timeout_seconds must be between 5 and 300")
        if not 0.1 <= self.whisper_vad_threshold <= 0.9:
            raise ValueError("whisper_vad_threshold must be between 0.1 and 0.9")
        if not self.whisper_vad_threshold <= self.whisper_conversation_vad_threshold <= 0.9:
            raise ValueError("whisper_conversation_vad_threshold must be between whisper_vad_threshold and 0.9")
        if not 100 <= self.whisper_vad_min_speech_ms <= 2_000:
            raise ValueError("whisper_vad_min_speech_ms must be between 100 and 2000")
        if not 32_044 <= self.max_audio_bytes <= 10_000_000:
            raise ValueError("max_audio_bytes must be between 32044 and 10000000")
        if self.tts_engine not in ("say", "piper", "fish"):
            raise ValueError("tts_engine must be 'say', 'piper', or 'fish'")
        piper_python = Path(self.piper_python)
        if piper_python.is_absolute() or ".." in piper_python.parts:
            raise ValueError("piper_python must be a relative path inside the project")
        piper_voice = Path(self.piper_voice)
        if piper_voice.is_absolute() or ".." in piper_voice.parts:
            raise ValueError("piper_voice must be a relative path inside the project")
        if not re.fullmatch(r"[^\x00-\x1f\x7f]{1,80}", self.tts_voice) or self.tts_voice.startswith("-"):
            raise ValueError("tts_voice is invalid")
        if not re.fullmatch(r"[^\x00-\x1f\x7f]{1,80}", self.piper_voice_name) or self.piper_voice_name.startswith("-"):
            raise ValueError("piper_voice_name is invalid")
        if type(self.fish_enabled) is not bool:
            raise ValueError("fish_enabled must be a boolean")
        fish_backend = urlparse(self.fish_base_url)
        if fish_backend.scheme != "http" or not fish_backend.hostname:
            raise ValueError("fish_base_url must be an HTTP URL")
        if not ipaddress.ip_address(fish_backend.hostname).is_loopback:
            raise ValueError("fish_base_url must use a loopback IP address")
        if not re.fullmatch(r"[^\x00-\x1f\x7f]{1,80}", self.fish_voice_name) or self.fish_voice_name.startswith("-"):
            raise ValueError("fish_voice_name is invalid")
        if not re.fullmatch(r"[a-zA-Z0-9\-_ ]{1,255}", self.fish_reference_id):
            raise ValueError("fish_reference_id is invalid")
        # Ranges match Fish's own ServeTTSRequest limits so a configured default
        # is never rejected by the Fish server at render time.
        if not 0.1 <= self.fish_temperature <= 1.0:
            raise ValueError("fish_temperature must be between 0.1 and 1.0")
        if not 0.1 <= self.fish_top_p <= 1.0:
            raise ValueError("fish_top_p must be between 0.1 and 1.0")
        if not 0.9 <= self.fish_repetition_penalty <= 2.0:
            raise ValueError("fish_repetition_penalty must be between 0.9 and 2.0")
        if not 64 <= self.fish_max_new_tokens <= 4096:
            raise ValueError("fish_max_new_tokens must be between 64 and 4096")
        if not 120 <= self.tts_rate <= 350:
            raise ValueError("tts_rate must be between 120 and 350")
        if not 5 <= self.tts_timeout_seconds <= 600:
            raise ValueError("tts_timeout_seconds must be between 5 and 600")
        if not 100 <= self.max_tts_chars <= 16_000:
            raise ValueError("max_tts_chars must be between 100 and 16000")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        # --- Tool loop ---
        if type(self.tools_enabled) is not bool:
            raise ValueError("tools_enabled must be a boolean")
        if type(self.tool_grammar_enabled) is not bool:
            raise ValueError("tool_grammar_enabled must be a boolean")
        if not 0 <= self.tool_temperature <= 2:
            raise ValueError("tool_temperature must be between 0 and 2")
        if not 1 <= self.tool_max_iterations <= 20:
            raise ValueError("tool_max_iterations must be between 1 and 20")
        if not 1 <= self.tool_call_timeout_seconds <= 120:
            raise ValueError("tool_call_timeout_seconds must be between 1 and 120")
        audit_path = Path(self.tool_audit_path)
        if audit_path.is_absolute() or ".." in audit_path.parts or not audit_path.parts or audit_path.parts[0] != "data":
            raise ValueError("tool_audit_path must be a relative path under data")
        timers_path = Path(self.timers_path)
        if timers_path.is_absolute() or ".." in timers_path.parts or not timers_path.parts or timers_path.parts[0] != "data":
            raise ValueError("timers_path must be a relative path under data")
        if not 1 <= self.max_timers <= 500:
            raise ValueError("max_timers must be between 1 and 500")
        if not 60 <= self.max_timer_seconds <= 31_536_000:
            raise ValueError("max_timer_seconds must be between 60 and 31536000")
        # TLS: certificate and key are all-or-nothing. Paths may be absolute or
        # relative; reject control characters but do not require the files to
        # exist at validation time (they are read when the socket is wrapped).
        for label, value in (("tls_cert", self.tls_cert), ("tls_key", self.tls_key)):
            if value and not re.fullmatch(r"[^\x00-\x1f\x7f]{1,4096}", value):
                raise ValueError(f"{label} is invalid")
        if bool(self.tls_cert) != bool(self.tls_key):
            raise ValueError("tls_cert and tls_key must be set together")
        # Auth: when enabled, a username plus a well-formed PBKDF2 digest and salt
        # are required. Hash is SHA-256 (64 hex chars); salt is 16+ bytes of hex.
        if type(self.auth_enabled) is not bool:
            raise ValueError("auth_enabled must be a boolean")
        if not 50_000 <= self.auth_pbkdf2_iterations <= 5_000_000:
            raise ValueError("auth_pbkdf2_iterations must be between 50000 and 5000000")
        if self.auth_enabled:
            if not re.fullmatch(r"[A-Za-z0-9._@-]{1,64}", self.auth_username):
                raise ValueError("auth_username is invalid")
            if not re.fullmatch(r"[0-9a-f]{64}", self.auth_password_hash):
                raise ValueError("auth_password_hash must be 64 lowercase hex characters")
            if not re.fullmatch(r"[0-9a-f]{32,128}", self.auth_password_salt):
                raise ValueError("auth_password_salt must be 32-128 lowercase hex characters")
        if self.tts_playback not in ("host", "browser"):
            raise ValueError("tts_playback must be 'host' or 'browser'")
        if self.whisper_server_url:
            stt = urlparse(self.whisper_server_url)
            if stt.scheme != "http" or not stt.hostname:
                raise ValueError("whisper_server_url must be an HTTP URL")
            # Audio is the most sensitive payload the app handles; the recognizer
            # must stay on this machine, like the model and speech backends.
            if not ipaddress.ip_address(stt.hostname).is_loopback:
                raise ValueError("whisper_server_url must use a loopback IP address")
        return self


def load_config(path: str | None = None) -> Config:
    config_path = Path(path or os.environ.get("JARVIS_CONFIG", "config.local.json"))
    values: dict = {}
    if config_path.exists():
        values = json.loads(config_path.read_text(encoding="utf-8"))
    allowed = set(Config.__dataclass_fields__)
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"unknown configuration keys: {', '.join(unknown)}")
    return Config(**values).validate()
