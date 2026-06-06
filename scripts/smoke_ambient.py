"""End-to-end smoke test with a real Edge-TTS voice and a bundled ambient bed."""

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
    proj = ROOT / "cache" / "smoke_ambient"
    if proj.exists():
        shutil.rmtree(proj)
    (proj / "assets" / "ambient").mkdir(parents=True)
    (proj / "assets" / "visuals").mkdir(parents=True)
    (proj / "output").mkdir(parents=True)
    (proj / "cache").mkdir(parents=True)
    shutil.copy(ROOT / "cache" / "ffmpeg.exe", proj / "cache" / "ffmpeg.exe")
    shutil.copy(ROOT / "cache" / "ffprobe.exe", proj / "cache" / "ffprobe.exe")
    # Stage ONE bundled ambient track for this smoke test.
    shutil.copy(ROOT / "assets" / "ambient" / "rain-gentle-60s.ogg",
                proj / "assets" / "ambient" / "rain-gentle-60s.ogg")

    script = proj / "script.txt"
    script.write_text(
        "Close your eyes.\n\n"
        "Listen to the rain against the window.\n\n"
        "Each drop is a small, soft reminder to let go.\n\n"
        "Tomorrow will be there when you wake.\n\n"
        "For now, simply rest.",
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
        ambient_mode=AmbientMode.AUTO,
        ambient_volume=0.22,
        ambient_duck_db=14.0,
        hardware_accel="libx264",
        last_output_stem="smoke-rain",
        progress_bar_height=8,
    )

    started = time.time()
    result = run_render(settings, paths)
    print(
        f"OK in {time.time() - started:.1f}s -> {result.output_path} "
        f"({result.output_path.stat().st_size / 1024:.1f} KB, "
        f"{result.duration_seconds:.1f}s)"
    )
    for note in result.notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
