"""End-to-end smoke tests that touch the local filesystem only.

These tests do NOT call any external provider. They exercise the timing
math, the visual fallback, the ambient scanner, and the orchestrator
short-circuit path that uses a pre-written script.
"""

from __future__ import annotations

import shutil
import sys
import wave
from pathlib import Path

import pytest

# Ensure the in-tree source is importable when pytest runs from the repo root.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sleeplens.audio import mixer  # noqa: E402
from sleeplens.audio.tts import TTSSegment  # noqa: E402
from sleeplens.config import AmbientMode, AppSettings, OutputPreset, TTSBackend  # noqa: E402
from sleeplens.core import run_render  # noqa: E402
from sleeplens.video.timing import compute_timing  # noqa: E402
from sleeplens.visual.assets import generate_fallback  # noqa: E402


# ----------------------------------------------------------------- timing


def test_timing_sums_voice_and_pauses() -> None:
    segments = [
        TTSSegment(index=0, text="a", audio_path=Path("x"), duration=12.5),
        TTSSegment(index=1, text="b", audio_path=Path("x"), duration=10.0),
        TTSSegment(index=2, text="c", audio_path=Path("x"), duration=7.5),
    ]
    plan = compute_timing(segments=segments, pause_seconds=1.8, fps=24)
    assert plan.voice_seconds == pytest.approx(30.0)
    assert plan.pause_count == 2
    assert plan.pause_seconds == pytest.approx(3.6)
    assert plan.total_seconds == pytest.approx(33.6)
    assert plan.frame_count == int(round(33.6 * 24))  # 806
    assert "m" in plan.human_runtime


def test_timing_rejects_empty_voice() -> None:
    with pytest.raises(ValueError):
        compute_timing(segments=[], pause_seconds=1.0, fps=24)


# ----------------------------------------------------- ambient scanner


def test_scan_ambient_library(tmp_path: Path) -> None:
    (tmp_path / "rain-soft.mp3").write_bytes(b"fake")
    (tmp_path / "ocean-waves.wav").write_bytes(b"fake")
    (tmp_path / "ignored.txt").write_text("nope")
    tracks = mixer.scan_ambient_library(tmp_path)
    assert len(tracks) == 2
    titles = {t.title for t in tracks}
    assert "rain-soft" in titles
    assert "ocean-waves" in titles
    rain_track = next(t for t in tracks if "rain" in t.title)
    assert "rain" in rain_track.keywords


def test_pick_ambient_keyword_match() -> None:
    tracks = [
        mixer.AmbientTrack(path=Path("a"), keywords=("rain",), title="rain"),
        mixer.AmbientTrack(path=Path("b"), keywords=("lofi",), title="lofi"),
    ]
    picked = mixer.pick_ambient(
        tracks, mode=AmbientMode.KEYWORD, script_keywords=["rain", "weather"]
    )
    assert picked is not None
    assert picked.title == "rain"


def test_pick_ambient_random_returns_one() -> None:
    tracks = [mixer.AmbientTrack(path=Path("a"), keywords=(), title="t")]
    assert mixer.pick_ambient(tracks, mode=AmbientMode.RANDOM) is tracks[0]
    assert mixer.pick_ambient(tracks, mode=AmbientMode.DISABLED) is None


# ----------------------------------------------------- visual fallback


def test_fallback_image_is_dark_and_correct_size(tmp_path: Path) -> None:
    target = tmp_path / "fb.png"
    result = generate_fallback(target_path=target, width=1280, height=720, seed=42)
    assert result == target
    assert target.exists()
    from PIL import Image

    img = Image.open(target).convert("RGB")
    assert img.size == (1280, 720)
    # Sample the corner: should be very dark (max channel < 80).
    px = img.getpixel((10, 10))
    assert max(px) < 80, f"Expected dark corner, got {px}"


# ----------------------------------------------------- script loader


def test_load_script_from_file(tmp_path: Path) -> None:
    from sleeplens.ai.script_writer import load_script_from_file

    f = tmp_path / "lesson.txt"
    f.write_text("First paragraph.\n\nSecond paragraph here.\n\nThird one too.", encoding="utf-8")
    script = load_script_from_file(f)
    assert len(script.paragraphs) == 3
    assert script.title


# ----------------------------------------------------- audio mixer glue


def _silent_wav(path: Path, seconds: float = 2.0, rate: int = 48000) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * int(rate * seconds))


def test_mix_bed_and_voice_voice_only(tmp_path: Path) -> None:
    from sleeplens.audio import mixer as am

    ffmpeg = Path("D:/proyectos/Proyectos Github/sleeplens/cache/ffmpeg.exe")
    if not ffmpeg.exists():
        pytest.skip("Bundled ffmpeg not available.")
    voice = tmp_path / "voice.wav"
    target = tmp_path / "mixed.wav"
    _silent_wav(voice, seconds=2.0)
    out = am.mix_bed_and_voice(
        am.MixSpec(
            voice_path=voice,
            ambient_paths=None,
            target_duration=2.0,
            output_path=target,
            ffmpeg_bin=ffmpeg,
        )
    )
    assert out.exists()
    assert out.stat().st_size > 0


def test_mix_filter_uses_long_labels(tmp_path: Path) -> None:
    """Regression: the filter graph must use ``[voice]`` / ``[bed]`` link labels.

    A previous version used ``[v]`` and ``[b]`` which ffmpeg rejects
    with 'Stream specifier v in filtergraph description matches no
    streams' on real-world long renders (the smoke test happened to
    succeed because the target duration was sub-second).
    """
    from sleeplens.audio import mixer as am

    ffmpeg = Path("D:/proyectos/Proyectos Github/sleeplens/cache/ffmpeg.exe")
    if not ffmpeg.exists():
        pytest.skip("Bundled ffmpeg not available.")
    voice = tmp_path / "voice.wav"
    bed = tmp_path / "bed.wav"
    target = tmp_path / "mixed.wav"
    _silent_wav(voice, seconds=2.0)
    _silent_wav(bed, seconds=2.0)
    out = am.mix_bed_and_voice(
        am.MixSpec(
            voice_path=voice,
            ambient_paths=[bed],
            target_duration=2.0,
            output_path=target,
            ffmpeg_bin=ffmpeg,
        )
    )
    assert out.exists()
    assert out.stat().st_size > 0


# ----------------------------------------------------- orchestrator


def test_orchestrator_with_prewritten_script(tmp_path_factory: pytest.TempPathFactory) -> None:
    """End-to-end run with a pre-written script (no provider, no edge-tts call).

    This exercises the timing engine, visual fallback, mixer, and encoder.
    """
    from sleeplens.config import resolve_paths
    from sleeplens.audio import tts as tts_mod

    # pytest's default tmp_path lives on the C: drive on Windows; force the
    # workspace onto D: so we never touch the nearly-full C: partition.
    on_d = Path(r"D:\proyectos\Proyectos Github\sleeplens\cache\pytest-tmp")
    on_d.mkdir(parents=True, exist_ok=True)
    # Use a timestamped subfolder so reruns do not collide on stale state.
    import time

    tmp_path = on_d / f"studio-{int(time.time() * 1000)}"
    tmp_path.mkdir(parents=True, exist_ok=True)

    # Stage a script file inside a fresh project layout.
    proj = tmp_path / "studio"
    (proj / "assets" / "ambient").mkdir(parents=True)
    (proj / "assets" / "visuals").mkdir(parents=True)
    (proj / "output").mkdir(parents=True)
    (proj / "cache").mkdir(parents=True)
    shutil.copy(
        Path("D:/proyectos/Proyectos Github/sleeplens/cache/ffmpeg.exe"),
        proj / "cache" / "ffmpeg.exe",
    )
    shutil.copy(
        Path("D:/proyectos/Proyectos Github/sleeplens/cache/ffprobe.exe"),
        proj / "cache" / "ffprobe.exe",
    )
    script_path = proj / "script.txt"
    script_path.write_text("Hello world. " * 80, encoding="utf-8")

    paths = resolve_paths(proj)
    paths.ensure()
    settings = AppSettings(
        script_file=str(script_path),
        script_topic="",
        tts_backend=TTSBackend.DISABLED,  # Skip real TTS in this test.
        target_word_count=400,
        video_fps=12,
        video_width=320,
        video_height=180,
        output_preset=OutputPreset.SLEEP_720P,
        ambient_mode=AmbientMode.DISABLED,
        hardware_accel="libx264",
        last_output_stem="test-render",
    )

    # Stub the TTS engine to avoid network calls. We do this by monkey-patching
    # the engine's render method.
    class FakeSegment:
        def __init__(self, idx: int, text: str) -> None:
            self.index = idx
            self.text = text
            self.audio_path = paths.cache_dir / f"fake-{idx}.wav"
            self.duration = 1.0
            _silent_wav(self.audio_path, seconds=1.0)

    class FakeTTSResult:
        def __init__(self) -> None:
            self.track_path = paths.cache_dir / "fake-voice.wav"
            self.segments = [FakeSegment(0, "Hello world.")]
            self.total_voice_duration = 1.0
            _silent_wav(self.track_path, seconds=1.0)

    def fake_render(self, paragraphs, cache_dir):  # type: ignore[no-untyped-def]
        cache_dir.mkdir(parents=True, exist_ok=True)
        return FakeTTSResult()

    monkey = pytest.MonkeyPatch()
    monkey.setattr(tts_mod.TTSEngine, "render", fake_render)
    try:
        result = run_render(settings, paths)
    finally:
        monkey.undo()

    assert result.output_path.exists()
    assert result.output_path.stat().st_size > 0
    assert result.timing.total_seconds > 0
