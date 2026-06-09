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


# --------------------------------------------------------------------- prompt


def test_default_prompt_is_sleeping_dev() -> None:
    """The default system prompt the script writer sends on every
    call is the Sleeping Dev master-class prompt. The check is
    content-shape rather than byte-exact so a future edit to the
    file (new section, added paragraph) does not break the test;
    the rule is that the prompt is the long-form Sleeping Dev
    one shipped in docs/prompts/sleeping_dev.md, not a one-
    paragraph built-in fallback."""

    from sleep_learning_engine.ai.script_writer import (
        _BUILTIN_FALLBACK_PROMPT,
        SYSTEM_PROMPT,
    )

    assert len(SYSTEM_PROMPT) > 2000, (
        f"Default prompt is suspiciously short ({len(SYSTEM_PROMPT)} chars). "
        f"Expected the full Sleeping Dev prompt (4000+ chars); the built-in "
        f"fallback is only {len(_BUILTIN_FALLBACK_PROMPT)} chars and would "
        f"indicate the package data file is not being shipped."
    )
    assert "SLEEPING DEV" in SYSTEM_PROMPT, (
        "Default prompt does not mention the Sleeping Dev channel - either "
        "the wrong file is being loaded or the prompt was overwritten."
    )
    assert "audio" in SYSTEM_PROMPT.lower(), (
        "Default prompt does not mention audio - either the wrong file is "
        "being loaded or the prompt was edited in a way that lost the "
        "audio-first contract."
    )


def test_default_prompt_loaded_from_package_data() -> None:
    """The pip-install path uses importlib.resources to load the
    prompt from the wheel. Verify the file ships with the wheel
    (the file is declared in pyproject.toml's package-data)."""

    from importlib import resources

    packaged = resources.files("sleep_learning_engine").joinpath(
        "prompts", "sleeping_dev.md"
    )
    assert packaged.is_file(), (
        "docs/prompts/sleeping_dev.md is in the source tree but the "
        "wheel does not include sleep_learning_engine/prompts/sleeping_dev.md. "
        "Check pyproject.toml's [tool.setuptools.package-data] section."
    )
    assert packaged.stat().st_size > 2000, (
        f"Packaged prompt is {packaged.stat().st_size} bytes, smaller than "
        f"expected for the full Sleeping Dev prompt. The built-in fallback "
        f"may have been committed by mistake."
    )


# ---------------------------------------------------------------------------
# resolve_paths() legacy-toml fallback regression
# ---------------------------------------------------------------------------
# The cloud notebooks' CONFIG cell writes ``.sleeplens.toml`` (the legacy
# name), not the new ``.sleep_learning_engine.toml``. ``resolve_paths``
# MUST honour that fallback so the cloud-rendered video picks up the user's
# settings - the previous build computed the fallback correctly and then
# dropped it on the floor by hardcoding the new name in the
# ``ProjectPaths`` constructor. This test pins both halves: the toml that
# exists wins, and ``paths.config_file`` actually points at it.


def test_resolve_paths_legacy_toml_fallback(tmp_path, monkeypatch):
    """A work dir with only the legacy .sleeplens.toml is picked up."""
    from sleep_learning_engine.config import load_settings, resolve_paths

    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_HOME", str(tmp_path))
    # Ensure no leftover legacy env var pollutes the test.
    monkeypatch.delenv("SLEEPLENS_HOME", raising=False)

    # Only the legacy name is on disk.
    (tmp_path / ".sleeplens.toml").write_text(
        'tts_voice = "en-US-BrianNeural"\n'
        'ambient_volume = 0.34\n',
        encoding="utf-8",
    )
    assert not (tmp_path / ".sleep_learning_engine.toml").exists()

    paths = resolve_paths()

    assert paths.config_file == tmp_path / ".sleeplens.toml", (
        f"Expected the legacy .sleeplens.toml to be picked up, got "
        f"{paths.config_file}. The fallback in resolve_paths() is not "
        f"flowing through to ProjectPaths.config_file."
    )
    settings = load_settings(paths.config_file)
    assert settings.tts_voice == "en-US-BrianNeural"
    assert settings.ambient_volume == 0.34


def test_resolve_paths_new_toml_wins_over_legacy(tmp_path, monkeypatch):
    """If both names exist, the new one wins (the documented preference)."""
    from sleep_learning_engine.config import resolve_paths

    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_HOME", str(tmp_path))
    monkeypatch.delenv("SLEEPLENS_HOME", raising=False)

    (tmp_path / ".sleep_learning_engine.toml").write_text(
        "tts_voice = \"en-US-AriaNeural\"\n", encoding="utf-8"
    )
    (tmp_path / ".sleeplens.toml").write_text(
        "tts_voice = \"en-US-BrianNeural\"\n", encoding="utf-8"
    )

    paths = resolve_paths()
    assert paths.config_file == tmp_path / ".sleep_learning_engine.toml"


def test_resolve_paths_no_toml_does_not_crash(tmp_path, monkeypatch):
    """Missing toml is fine - paths.config_file is just the new-name path."""
    from sleep_learning_engine.config import resolve_paths

    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_HOME", str(tmp_path))
    monkeypatch.delenv("SLEEPLENS_HOME", raising=False)

    paths = resolve_paths()
    # No toml on disk; resolve_paths still returns a usable ProjectPaths
    # pointing at the (non-existent) preferred name. load_settings handles
    # the missing-file case separately by falling back to AppSettings().
    assert paths.config_file == tmp_path / ".sleep_learning_engine.toml"


# ---------------------------------------------------------------------------
# Cloud notebook cell 5 (download) picks the newest MP4 by mtime
# ---------------------------------------------------------------------------
# The CLI calls paths.unique_output() which NEVER overwrites an existing
# file - the second render goes to <stem>-1.mp4, the third to <stem>-2.mp4,
# etc. The cloud notebook cell 5 (download) must therefore match
# <stem>*.mp4 (not just <stem>.mp4) and pick the newest by mtime.
# The previous version of cell 5 used glob('<stem>.mp4') which only
# matched the first render's file, so every re-run downloaded the OLD MP4
# and the user thought the new render was identical to the previous one.


def test_unique_output_never_overwrites(tmp_path, monkeypatch):
    """paths.unique_output returns -1.mp4, -2.mp4, etc. for repeat stems."""
    from sleep_learning_engine.config import ProjectPaths, resolve_paths

    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_HOME", str(tmp_path))
    monkeypatch.delenv("SLEEPLENS_HOME", raising=False)
    paths = resolve_paths()
    paths.ensure()

    a = paths.unique_output("demo")
    a.write_bytes(b"render-one")
    b = paths.unique_output("demo")
    b.write_bytes(b"render-two")
    c = paths.unique_output("demo")
    c.write_bytes(b"render-three")

    assert a.name == "demo.mp4"
    assert b.name == "demo-1.mp4"
    assert c.name == "demo-2.mp4"
    # All three are distinct files, none was overwritten.
    assert a.read_bytes() == b"render-one"
    assert b.read_bytes() == b"render-two"
    assert c.read_bytes() == b"render-three"


def test_cell5_glob_picks_newest_by_mtime(tmp_path):
    """Mirror the cell 5 logic: glob '<stem>*.mp4' + sort by mtime desc."""
    import os
    import time
    import glob

    out = tmp_path / "output"
    out.mkdir()

    # Simulate three renders, oldest first.
    names = ["demo.mp4", "demo-1.mp4", "demo-2.mp4"]
    for i, n in enumerate(names):
        p = out / n
        p.write_bytes(f"render-{i}".encode())
        # Touch with strictly increasing mtimes.
        t = time.time() + i
        os.utime(p, (t, t))

    # The OLD cell 5 pattern - matches only the first render.
    old_matches = sorted(glob.glob(str(out / "demo.mp4")))
    assert old_matches == [str(out / "demo.mp4")], (
        "Sanity: the old pattern only finds the first render. If the user "
        "uses this pattern in cell 5, they download the OLD MP4 on every "
        "re-run. This is the bug the cell 5 fix prevents."
    )

    # The NEW cell 5 pattern - matches all, picks newest by mtime.
    new_matches = sorted(
        glob.glob(str(out / "demo*.mp4")),
        key=os.path.getmtime,
        reverse=True,
    )
    assert new_matches[0] == str(out / "demo-2.mp4"), (
        f"Expected the newest render (demo-2.mp4) to be picked, got "
        f"{new_matches[0]}. The cell 5 fix is broken."
    )


# ---------------------------------------------------------------------------
# resolve_paths() ambient fallback
# ---------------------------------------------------------------------------
# The 97 ambient tracks ship inside the installed package (under
# src/sleep_learning_engine/assets/ambient/). Cloud notebook setup
# cells copy them to the work dir; the local CLI uses them via
# importlib.resources when the repo-root assets/ambient/ is empty.
# This test pins both directions of the fallback.


def test_resolve_paths_ambient_prefers_user_dir_when_populated(tmp_path, monkeypatch):
    """If the work dir has its own ambient, use it (do not touch the package)."""
    from sleep_learning_engine.config import resolve_paths

    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_HOME", str(tmp_path))
    monkeypatch.delenv("SLEEPLENS_HOME", raising=False)

    user_amb = tmp_path / "assets" / "ambient"
    user_amb.mkdir(parents=True)
    (user_amb / "mine.mp3").write_bytes(b"user-track")

    paths = resolve_paths()
    assert paths.ambient_dir == user_amb
    assert list(paths.ambient_dir.glob("*.mp3")) == [user_amb / "mine.mp3"]


def test_resolve_paths_ambient_falls_back_to_bundled(tmp_path, monkeypatch):
    """Empty work-dir ambient -> use the package's bundled 97 tracks."""
    from sleep_learning_engine.config import resolve_paths

    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_HOME", str(tmp_path))
    monkeypatch.delenv("SLEEPLENS_HOME", raising=False)

    # Work dir has no ambient at all.
    paths = resolve_paths()
    # The fallback should point at the package's bundled dir.
    assert "sleep_learning_engine" in str(paths.ambient_dir)
    assert paths.ambient_dir.name == "ambient"
    # The bundled dir should have all 97 mp3s.
    mp3s = list(paths.ambient_dir.glob("*.mp3"))
    assert len(mp3s) == 97, (
        f"Expected 97 bundled ambient tracks, found {len(mp3s)}. "
        f"The package_data in pyproject.toml is not including the "
        f"assets/ambient/*.mp3 glob, or the files are not in the "
        f"expected location."
    )


def test_resolve_paths_ambient_falls_back_when_user_dir_empty(tmp_path, monkeypatch):
    """Work-dir ambient dir exists but is empty -> use bundled."""
    from sleep_learning_engine.config import resolve_paths

    monkeypatch.setenv("SLEEP_LEARNING_ENGINE_HOME", str(tmp_path))
    monkeypatch.delenv("SLEEPLENS_HOME", raising=False)

    user_amb = tmp_path / "assets" / "ambient"
    user_amb.mkdir(parents=True)
    # No mp3s in the user's ambient dir.

    paths = resolve_paths()
    assert paths.ambient_dir != user_amb, (
        "Empty user ambient dir should trigger the bundled fallback."
    )
    assert "sleep_learning_engine" in str(paths.ambient_dir)
