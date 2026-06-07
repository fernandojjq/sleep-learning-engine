"""Tests for the env-var overrides on load_settings.

Two overrides are supported today:

- ``SLEEP_LEARNING_ENGINE_TTS_VOICE`` (and the legacy
  ``SLEEPLENS_TTS_VOICE``) win over both the TOML value and the
  ``AppSettings`` default. This is the hook the cloud notebooks
  use so a single ``VOICE = "..."`` line at the top of cell 1 is
  enough to swap the narration voice.

The voice override is applied AFTER the TOML load so it wins
even when the user's .sleeplens.toml pins a different voice.
That matches the user's "I want the notebook to override the
config" intent: notebooks are a per-run override, the TOML is
the durable preference.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sleep_learning_engine.config import load_settings  # noqa: E402


def _write_toml(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_default_voice_is_brian(tmp_path: Path, monkeypatch) -> None:
    """The default (no TOML, no env) is Brian. This is the
    notebook / fresh-install path; no config file, just the
    built-in default."""
    monkeypatch.delenv("SLEEP_LEARNING_ENGINE_TTS_VOICE", raising=False)
    monkeypatch.delenv("SLEEPLENS_TTS_VOICE", raising=False)
    settings = load_settings(tmp_path / "missing.toml")
    assert settings.tts_voice == "en-US-BrianNeural"


def test_env_var_overrides_default(tmp_path: Path, monkeypatch) -> None:
    """A bare env var beats the default. This is the notebook path."""
    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_TTS_VOICE", "es-ES-ElviraNeural")
    settings = load_settings(tmp_path / "missing.toml")
    assert settings.tts_voice == "es-ES-ElviraNeural"


def test_env_var_overrides_toml(tmp_path: Path, monkeypatch) -> None:
    """The env var wins even when the TOML pins a different voice.
    This matches the user's intent: the notebook is a per-run
    override, the TOML is the durable preference, and a one-off
    notebook cell should be able to win."""
    cfg = tmp_path / "config.toml"
    _write_toml(cfg, 'tts_voice = "en-US-AriaNeural"\n')
    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_TTS_VOICE", "en-US-BrianNeural")
    settings = load_settings(cfg)
    assert settings.tts_voice == "en-US-BrianNeural"


def test_legacy_env_var_name_still_works(tmp_path: Path, monkeypatch) -> None:
    """Old scripts might still set $SLEEPLENS_TTS_VOICE; the new
    $SLEEP_LEARNING_ENGINE_TTS_VOICE name is preferred but the
    legacy one keeps working."""
    monkeypatch.delenv("SLEEP_LEARNING_ENGINE_TTS_VOICE", raising=False)
    monkeypatch.setenv("SLEEPLENS_TTS_VOICE", "en-US-EmmaNeural")
    settings = load_settings(tmp_path / "missing.toml")
    assert settings.tts_voice == "en-US-EmmaNeural"


def test_new_env_var_takes_priority_over_legacy(tmp_path: Path, monkeypatch) -> None:
    """If both env vars are set (rare, but possible from a
    process that inherits the old and sets the new), the new one
    wins because the new name is the canonical one."""
    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_TTS_VOICE", "en-US-BrianNeural")
    monkeypatch.setenv("SLEEPLENS_TTS_VOICE", "en-US-AriaNeural")
    settings = load_settings(tmp_path / "missing.toml")
    assert settings.tts_voice == "en-US-BrianNeural"


def test_empty_env_var_does_not_override(tmp_path: Path, monkeypatch) -> None:
    """An empty env var is treated as 'unset' so a stale empty
    export does not silently clear the voice."""
    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_TTS_VOICE", "")
    settings = load_settings(tmp_path / "missing.toml")
    # Falls through to the default.
    assert settings.tts_voice == "en-US-BrianNeural"
