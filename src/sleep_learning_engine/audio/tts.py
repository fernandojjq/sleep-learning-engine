"""Text-to-speech subsystem."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..config import ProjectPaths, TTSBackend
from ..core import DependencyMissingError, SleeplensError
from ..utils.logging import get_logger

log = get_logger()


@dataclass(frozen=True)
class TTSSegment:
    """One rendered narration segment."""

    index: int
    text: str
    audio_path: Path
    duration: float  # Seconds.


@dataclass(frozen=True)
class TTSResult:
    """The concatenated voice track plus its segment timeline."""

    track_path: Path
    segments: list[TTSSegment]
    total_voice_duration: float


class TTSEngine:
    """Render a script into a single voice track.

    The default backend is ``edge-tts`` because it is free, unauthenticated,
    and ships high quality neural voices. Other backends are pluggable.
    """

    def __init__(
        self,
        *,
        backend: TTSBackend,
        voice: str,
        rate: str = "-5%",
        pitch: str = "-2Hz",
        ffmpeg_bin: Path | None = None,
    ) -> None:
        self.backend = backend
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.ffmpeg_bin = ffmpeg_bin

    # ----------------------------------------------------------------- public
    def render(
        self,
        paragraphs: Iterable[str],
        cache_dir: Path,
    ) -> TTSResult:
        """Render a list of paragraphs and stitch them into a single track."""
        paragraphs_list = [p.strip() for p in paragraphs if p and p.strip()]
        if not paragraphs_list:
            raise SleeplensError("No paragraphs to render.")

        cache_dir.mkdir(parents=True, exist_ok=True)
        segments_dir = cache_dir / "tts"
        segments_dir.mkdir(exist_ok=True)

        if self.backend is TTSBackend.EDGE:
            segments = self._render_edge(paragraphs_list, segments_dir)
        elif self.backend is TTSBackend.DISABLED:
            raise SleeplensError("TTS backend is disabled but no voice track was supplied.")
        else:
            raise SleeplensError(
                f"TTS backend '{self.backend.value}' is not bundled in this build. "
                "Use the default 'edge' backend or supply a pre-rendered voice track."
            )

        stitched = self._stitch(segments, cache_dir / "voice.mp3")
        return TTSResult(
            track_path=stitched,
            segments=segments,
            total_voice_duration=sum(s.duration for s in segments),
        )

    # --------------------------------------------------------------- backends
    def _render_edge(self, paragraphs: list[str], out_dir: Path) -> list[TTSSegment]:
        try:
            import edge_tts  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DependencyMissingError(
                "edge-tts is not installed. Run: pip install edge-tts"
            ) from exc

        async def _synth_all() -> list[TTSSegment]:
            communicate = edge_tts.Communicate(
                text="",
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch,
            )
            segments: list[TTSSegment] = []
            for i, text in enumerate(paragraphs):
                audio_path = out_dir / f"seg-{i:04d}.mp3"
                comm = edge_tts.Communicate(
                    text=text,
                    voice=self.voice,
                    rate=self.rate,
                    pitch=self.pitch,
                )
                await comm.save(str(audio_path))
                if not audio_path.exists() or audio_path.stat().st_size == 0:
                    raise SleeplensError(f"edge-tts produced no audio for segment {i}.")
                duration = _probe_duration(audio_path, self.ffmpeg_bin)
                log.info("Rendered TTS segment {} ({:.1f}s)", i, duration)
                segments.append(TTSSegment(index=i, text=text, audio_path=audio_path, duration=duration))
            return segments

        try:
            return asyncio.run(_synth_all())
        except RuntimeError:
            # asyncio.run cannot be called from a running loop (e.g. inside the
            # GUI thread). Fall back to a dedicated loop on this thread.
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_synth_all())
            finally:
                loop.close()

    # ----------------------------------------------------------------- stitch
    def _stitch(self, segments: list[TTSSegment], target: Path) -> Path:
        if not segments:
            raise SleeplensError("Cannot stitch an empty segment list.")
        if not self.ffmpeg_bin or not self.ffmpeg_bin.exists():
            raise DependencyMissingError(
                f"ffmpeg binary not found at {self.ffmpeg_bin}. "
                "Drop ffmpeg.exe into the project's cache/ directory."
            )

        if len(segments) == 1:
            shutil.copy(segments[0].audio_path, target)
            return target

        concat_file = target.with_suffix(".concat.txt")
        lines = [f"file '{seg.audio_path.as_posix()}'" for seg in segments]
        concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        cmd = [
            str(self.ffmpeg_bin),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(target),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error("ffmpeg concat failed: {}", result.stderr[-2000:])
            raise SleeplensError("Failed to stitch TTS segments.")
        return target


# ----------------------------------------------------------- helpers


def _probe_duration(audio_path: Path, ffmpeg_bin: Path | None) -> float:
    """Return the duration of an audio file in seconds, using ffprobe."""
    if ffmpeg_bin is None:
        # Fallback: best-effort guess based on file size.
        return max(0.1, audio_path.stat().st_size / 16_000)
    ffprobe_bin = ffmpeg_bin.with_name("ffprobe.exe" if ffmpeg_bin.name.endswith(".exe") else "ffprobe")
    if not ffprobe_bin.exists():
        ffprobe_bin = ffmpeg_bin
    cmd = [
        str(ffprobe_bin),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return 1.0
        return float(result.stdout.strip() or "0")
    except (ValueError, subprocess.TimeoutExpired):
        return 1.0


# Silence the unused-name lint; keep the helper for tooling/tests.
_ = tempfile.gettempdir
