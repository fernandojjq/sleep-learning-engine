"""Text-to-speech subsystem."""

from __future__ import annotations

import asyncio
import re
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

        # Chunk any paragraph that exceeds a safe character limit for edge-tts
        chunked_paragraphs = []
        for p in paragraphs_list:
            chunked_paragraphs.extend(_chunk_text(p))
        paragraphs_list = chunked_paragraphs

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

        # We re-encode (libmp3lame at the same 48 kbps bitrate edge-tts
        # ships) instead of the previous -c copy. The -c copy path
        # preserves each per-segment mp3 encoder pre-roll as a
        # ~30-100 ms silent frame at the start of every segment, which
        # the ear hears as a micro-pause at every paragraph boundary
        # - so a sentence that has the word "of" at the start of a
        # paragraph reads as "... of <pause> ...", which sounds like
        # the TTS is randomly hesitating. Re-encoding drops the
        # pre-roll because the libmp3lame encoder starts from a
        # clean timeline. The 48 kbps bitrate matches edge-tts's
        # default mp3 output so the final size and quality are
        # essentially identical to the -c copy version; the
        # per-segment CPU cost is the only real change (a few
        # seconds for a 27-paragraph script).
        cmd = [
            str(self.ffmpeg_bin),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-af",
            "aresample=async=1:first_pts=0",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "48k",
            "-write_xing",
            "1",
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


def _chunk_text(text: str, max_chars: int = 3000) -> list[str]:
    """Split a long text block into smaller chunks, trying to split at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    # Split by sentence endings (. ? ! followed by whitespace)
    sentences = re.split(r'(?<=[.?!])\s+', text)
    chunks = []
    current_chunk = []
    current_len = 0

    for sentence in sentences:
        if current_len + len(sentence) + 1 > max_chars:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_len = len(sentence)
        else:
            current_chunk.append(sentence)
            current_len += len(sentence) + 1

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    # If any single sentence is still larger than max_chars, split it by words
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
        else:
            words = chunk.split()
            sub_chunk = []
            sub_len = 0
            for word in words:
                if sub_len + len(word) + 1 > max_chars:
                    if sub_chunk:
                        final_chunks.append(" ".join(sub_chunk))
                    sub_chunk = [word]
                    sub_len = len(word)
                else:
                    sub_chunk.append(word)
                    sub_len += len(word) + 1
            if sub_chunk:
                final_chunks.append(" ".join(sub_chunk))

    return final_chunks

