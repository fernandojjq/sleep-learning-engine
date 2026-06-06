"""Typed application settings with sane defaults."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class AIProvider(StrEnum):
    """Known backends the studio can talk to."""

    NVIDIA_NIM = "nvidia_nim"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"  # Only via OpenAI-compatible proxies.
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    CUSTOM = "custom"


class TTSBackend(StrEnum):
    """Supported text-to-speech engines."""

    EDGE = "edge"
    ELEVENLABS = "elevenlabs"
    AZURE = "azure"
    LOCAL_PIPER = "piper"
    DISABLED = "disabled"  # Use a pre-recorded voice track only.


class AmbientMode(StrEnum):
    """How the ambient bed is chosen."""

    AUTO = "auto"  # Match keywords, fallback to random.
    KEYWORD = "keyword"  # Strict keyword match.
    RANDOM = "random"  # Pick any track.
    DISABLED = "disabled"


class OutputPreset(StrEnum):
    """Target encoding profile."""

    SLEEP_720P = "sleep_720p"
    SLEEP_1080P = "sleep_1080p"
    AUDIO_ONLY = "audio_only"


@dataclass(frozen=True)
class ProviderPreset:
    """A preconfigured AI endpoint that appears in the GUI dropdown."""

    id: str
    label: str
    provider: AIProvider
    base_url: str
    default_model: str
    requires_key: bool
    notes: str = ""


# Curated dropdown choices. The first entry is the out-of-the-box default.
PROVIDER_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        id="nvidia_nim_deepseek",
        label="NVIDIA NIM (DeepSeek V4) - free tier default",
        provider=AIProvider.NVIDIA_NIM,
        base_url="https://integrate.api.nvidia.com/v1",
        default_model="deepseek-ai/deepseek-v4",
        requires_key=True,
        notes="Free tier. 40 RPM. Get a key at build.nvidia.com.",
    ),
    ProviderPreset(
        id="openai_gpt",
        label="OpenAI (GPT-4o, GPT-4.1, o-series)",
        provider=AIProvider.OPENAI,
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        requires_key=True,
    ),
    ProviderPreset(
        id="anthropic_proxy",
        label="Anthropic Claude (via OpenAI-compatible proxy)",
        provider=AIProvider.ANTHROPIC,
        base_url="https://api.anthropic.com/v1",
        default_model="claude-sonnet-4-5",
        requires_key=True,
        notes="Requires an OpenAI-compatible proxy such as LiteLLM.",
    ),
    ProviderPreset(
        id="ollama_local",
        label="Ollama (local, offline)",
        provider=AIProvider.OLLAMA,
        base_url="http://127.0.0.1:11434/v1",
        default_model="llama3.1",
        requires_key=False,
        notes="No key required. Pull a model with `ollama pull llama3.1`.",
    ),
    ProviderPreset(
        id="lmstudio_local",
        label="LM Studio (local, offline)",
        provider=AIProvider.LM_STUDIO,
        base_url="http://127.0.0.1:1234/v1",
        default_model="local-model",
        requires_key=False,
        notes="Start LM Studio's local server before connecting.",
    ),
    ProviderPreset(
        id="custom",
        label="Custom OpenAI-compatible endpoint",
        provider=AIProvider.CUSTOM,
        base_url="",
        default_model="",
        requires_key=True,
    ),
)


@dataclass
class AppSettings:
    """Everything the studio needs to run a render."""

    # AI connector
    provider_id: str = "nvidia_nim_deepseek"
    base_url: str = "https://integrate.api.nvidia.com/v1"
    api_key: str = ""
    # Default to a real model id (verified against
    # https://integrate.api.nvidia.com/v1/models on 2026-06-06).
    # The "v4" prefix alone does not exist; the actual ids are
    # "deepseek-ai/deepseek-v4-flash" and "deepseek-ai/deepseek-v4-pro".
    model: str = "deepseek-ai/deepseek-v4-flash"
    temperature: float = 0.7
    max_tokens: int = 4096
    request_timeout: float = 120.0
    max_retries: int = 6
    system_prompt: str = ""  # Empty = use the built-in default in script_writer.py.

    # TTS
    tts_backend: TTSBackend = TTSBackend.EDGE
    tts_voice: str = "en-US-AriaNeural"
    tts_rate: str = "-5%"  # Slightly slower for sleepy narration.
    tts_pitch: str = "-2Hz"

    # Scripting
    script_topic: str = ""
    script_file: str = ""
    target_word_count: int = 4500  # ~30 min of narration.
    pause_between_paragraphs: float = 1.8
    language: str = "en"

    # Visual
    background_image: str = ""
    background_video: str = ""
    video_fps: int = 24
    video_width: int = 1280
    video_height: int = 720
    fallback_seed: int = 20251123

    # Audio mixing
    ambient_mode: AmbientMode = AmbientMode.AUTO
    ambient_volume: float = 0.18
    ambient_duck_db: float = 12.0
    voice_volume: float = 1.0

    # Render
    output_preset: OutputPreset = OutputPreset.SLEEP_720P
    progress_bar_color: str = "#00FF00"
    progress_bar_height: int = 6
    progress_bar_position: str = "bottom"
    hardware_accel: str = "auto"  # auto|nvenc|qsv|amf|libx264
    render_threads: int = 0  # 0 = auto

    # App behaviour
    theme: str = "midnight"
    last_output_stem: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def load_settings(path: Path) -> AppSettings:
    """Read settings from a TOML file. Missing file returns defaults."""
    if not path.exists():
        return AppSettings()
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    settings = AppSettings()
    for key, value in raw.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
        else:
            settings.extra[key] = value
    # TOML round-trip turns StrEnum members into plain strings. Cast
    # the known enum fields back to their enum type so callers can
    # keep using ``settings.tts_backend.value`` etc.
    if isinstance(settings.tts_backend, str):
        try:
            settings.tts_backend = TTSBackend(settings.tts_backend)
        except ValueError:
            settings.tts_backend = TTSBackend.EDGE
    if isinstance(settings.ambient_mode, str):
        try:
            settings.ambient_mode = AmbientMode(settings.ambient_mode)
        except ValueError:
            settings.ambient_mode = AmbientMode.AUTO
    if isinstance(settings.output_preset, str):
        try:
            settings.output_preset = OutputPreset(settings.output_preset)
        except ValueError:
            settings.output_preset = OutputPreset.SLEEP_720P
    return settings


def save_settings(path: Path, settings: AppSettings) -> None:
    """Persist the current settings as TOML."""
    from datetime import datetime, timezone

    payload: dict[str, Any] = {
        "provider_id": settings.provider_id,
        "base_url": settings.base_url,
        "model": settings.model,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "request_timeout": settings.request_timeout,
        "max_retries": settings.max_retries,
        "system_prompt": settings.system_prompt,
        "tts_backend": settings.tts_backend.value,
        "tts_voice": settings.tts_voice,
        "tts_rate": settings.tts_rate,
        "tts_pitch": settings.tts_pitch,
        "script_topic": settings.script_topic,
        "script_file": settings.script_file,
        "target_word_count": settings.target_word_count,
        "pause_between_paragraphs": settings.pause_between_paragraphs,
        "language": settings.language,
        "background_image": settings.background_image,
        "background_video": settings.background_video,
        "video_fps": settings.video_fps,
        "video_width": settings.video_width,
        "video_height": settings.video_height,
        "fallback_seed": settings.fallback_seed,
        "ambient_mode": settings.ambient_mode.value,
        "ambient_volume": settings.ambient_volume,
        "ambient_duck_db": settings.ambient_duck_db,
        "voice_volume": settings.voice_volume,
        "output_preset": settings.output_preset.value,
        "progress_bar_color": settings.progress_bar_color,
        "progress_bar_height": settings.progress_bar_height,
        "progress_bar_position": settings.progress_bar_position,
        "hardware_accel": settings.hardware_accel,
        "render_threads": settings.render_threads,
        "theme": settings.theme,
        "last_output_stem": settings.last_output_stem,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(settings.extra)

    # Avoid pulling in a TOML writer dependency: emit by hand.
    lines: list[str] = ["# Sleeplens studio configuration", ""]
    for k, v in payload.items():
        lines.append(f"{k} = {_toml_literal(v)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _toml_literal(value: Any) -> str:
    """Best-effort TOML literal for the values we emit."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # Use triple-quoted multi-line strings when the value contains a
        # newline, so the saved config stays readable.
        if "\n" in value:
            inner = value.replace('"""', '\\"\\"\\"')
            return f'"""\n{inner}\n"""'
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_literal(v) for v in value) + "]"
    return f'"{value}"'
