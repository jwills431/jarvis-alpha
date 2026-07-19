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
    stt_enabled: bool = True
    whisper_binary: str = "runtime/whisper.cpp/build/bin/whisper-cli"
    whisper_model: str = "models/whisper/ggml-base.en.bin"
    whisper_vad_enabled: bool = True
    whisper_vad_model: str = "models/whisper/ggml-silero-v6.2.0.bin"
    whisper_vad_threshold: float = 0.5
    whisper_conversation_vad_threshold: float = 0.6
    whisper_vad_min_speech_ms: int = 250
    transcription_timeout_seconds: int = 45
    max_audio_bytes: int = 1_000_000
    tts_enabled: bool = True
    tts_voice: str = "Daniel"
    tts_rate: int = 190
    tts_timeout_seconds: int = 180
    max_tts_chars: int = 4_000
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

    def validate(self) -> "Config":
        if type(self.memory_enabled) is not bool or type(self.auto_memory_enabled) is not bool:
            raise ValueError("memory flags must be booleans")
        if not ipaddress.ip_address(self.app_host).is_loopback:
            raise ValueError("app_host must be a loopback IP address")
        backend = urlparse(self.llama_base_url)
        if backend.scheme != "http" or not backend.hostname:
            raise ValueError("llama_base_url must be an HTTP URL")
        if not ipaddress.ip_address(backend.hostname).is_loopback:
            raise ValueError("llama_base_url must use a loopback IP address")
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
        if not re.fullmatch(r"[^\x00-\x1f\x7f]{1,80}", self.tts_voice) or self.tts_voice.startswith("-"):
            raise ValueError("tts_voice is invalid")
        if not 120 <= self.tts_rate <= 350:
            raise ValueError("tts_rate must be between 120 and 350")
        if not 5 <= self.tts_timeout_seconds <= 600:
            raise ValueError("tts_timeout_seconds must be between 5 and 600")
        if not 100 <= self.max_tts_chars <= 16_000:
            raise ValueError("max_tts_chars must be between 100 and 16000")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
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
