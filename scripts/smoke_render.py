"""Manual smoke test that runs the full pipeline with the real Edge TTS engine.

Usage:
    .venv/Scripts/python scripts/smoke_render.py
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from sleeplens.audio.tts import TTSEngine
from sleeplens.config import (
    AmbientMode,
    AppSettings,
    OutputPreset,
    TTSBackend,
    resolve_paths,
)
from sleeplens.core import run_render


def main() -> int:
    proj = ROOT / "cache" / "smoke"
    if proj.exists():
        shutil.rmtree(proj)
    (proj / "assets" / "ambient").mkdir(parents=True)
    (proj / "assets" / "visuals").mkdir(parents=True)
    (proj / "output").mkdir(parents=True)
    (proj / "cache").mkdir(parents=True)
    shutil.copy(ROOT / "cache" / "ffmpeg.exe", proj / "cache" / "ffmpeg.exe")
    shutil.copy(ROOT / "cache" / "ffprobe.exe", proj / "cache" / "ffprobe.exe")

    script = proj / "script.txt"
    script.write_text(
        "Close your eyes.\n\n"
        "Take a slow, deep breath in.\n\n"
        "And let it go.\n\n"
        "Feel the weight of the day melting away.\n\n"
        "Tomorrow will take care of itself.",
        encoding="utf-8",
    )

    paths = resolve_paths(proj)
    settings = AppSettings(
        script_file=str(script),
        tts_backend=TTSBackend.EDGE,
        tts_voice="en-US-AriaNeural",
        tts_rate="-15%",
        target_word_count=30,
        pause_between_paragraphs=0.6,
        video_fps=24,
        video_width=640,
        video_height=360,
        output_preset=OutputPreset.SLEEP_720P,
        ambient_mode=AmbientMode.DISABLED,
        hardware_accel="libx264",
        last_output_stem="smoke",
        progress_bar_height=8,
    )

    started = time.time()
    result = run_render(settings, paths)
    print(
        f"OK in {time.time() - started:.1f}s -> {result.output_path} "
        f"({result.output_path.stat().st_size / 1024:.1f} KB, "
        f"{result.duration_seconds:.1f}s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
