"""Audio mixing subsystem."""

from __future__ import annotations

import re
import shutil
import subprocess
import wave
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..config import AmbientMode
from ..core import AssetNotFoundError, DependencyMissingError, SleeplensError
from ..utils.logging import get_logger

log = get_logger()


# Keywords found in ambient filenames. Order matters - first match wins.
AMBIENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "rain": ("rain", "storm", "shower"),
    "ocean": ("ocean", "wave", "sea", "shore"),
    "forest": ("forest", "wood", "jungle", "birds"),
    "fire": ("fire", "crackle", "hearth", "fireplace"),
    "river": ("river", "stream", "creek", "water"),
    "wind": ("wind", "breeze", "gust"),
    "alpha": ("alpha", "binaural", "432", "528", "isochronic"),
    "lofi": ("lofi", "lo-fi", "chill", "ambient", "drone"),
    "brown": ("brown", "pink", "white", "noise"),
    "night": ("night", "cricket", "owl"),
    "cafe": ("cafe", "coffee", "restaurant"),
    "train": ("train", "rail", "railway"),
}


@dataclass(frozen=True)
class AmbientTrack:
    """Metadata for one ambient audio file."""

    path: Path
    keywords: tuple[str, ...]
    title: str

    @property
    def size_mb(self) -> float:
        return self.path.stat().st_size / (1024 * 1024)


def scan_ambient_library(directory: Path) -> list[AmbientTrack]:
    """Index the ambient library, extracting keywords from filenames."""
    if not directory.exists():
        log.warning("Ambient library directory does not exist: {}", directory)
        return []
    tracks: list[AmbientTrack] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}:
            continue
        if path.stem.startswith("."):
            continue
        keywords = _extract_keywords(path.stem)
        tracks.append(AmbientTrack(path=path, keywords=keywords, title=path.stem))
    return tracks


def pick_ambient(
    tracks: Iterable[AmbientTrack],
    *,
    mode: AmbientMode,
    script_keywords: Iterable[str] = (),
) -> AmbientTrack | None:
    """Select a single track for the bed, honouring the chosen mode."""
    tracks_list = list(tracks)
    if not tracks_list:
        return None
    if mode is AmbientMode.DISABLED:
        return None
    if mode is AmbientMode.RANDOM:
        import random

        return random.choice(tracks_list)

    script_set = {kw.lower() for kw in script_keywords if kw}

    def score(track: AmbientTrack) -> int:
        if not script_set:
            return 1 if track.keywords else 0
        return sum(1 for kw in track.keywords if kw in script_set)

    matches = sorted(tracks_list, key=score, reverse=True)
    if mode is AmbientMode.KEYWORD and score(matches[0]) == 0:
        return None
    return matches[0]


def extract_script_keywords(text: str, limit: int = 12) -> list[str]:
    """Cheap keyword extraction for matching ambient tracks."""
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower())
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]


def _extract_keywords(stem: str) -> tuple[str, ...]:
    lowered = stem.lower()
    found: list[str] = []
    for canonical, synonyms in AMBIENT_KEYWORDS.items():
        if any(syn in lowered for syn in synonyms):
            found.append(canonical)
    return tuple(found)


# ------------------------------------------------------------- mixing


@dataclass(frozen=True)
class MixSpec:
    """Inputs to the audio mixer."""

    voice_path: Path
    ambient_path: Path | None
    target_duration: float
    output_path: Path
    voice_volume: float = 1.0
    ambient_volume: float = 0.18
    ambient_duck_db: float = 12.0
    ffmpeg_bin: Path | None = None


def mix_bed_and_voice(spec: MixSpec) -> Path:
    """Produce a single stereo track that plays the voice over the ambient bed.

    The bed is looped to match the voice duration, filtered to a comfortable
    level, and ducked whenever the voice is active. The voice track is
    explicitly padded to ``target_duration`` so the silent pauses between
    paragraphs become real silence gaps in the output. The result is a stereo
    48 kHz WAV ready to feed the video encoder.
    """
    if not spec.voice_path.exists():
        raise AssetNotFoundError(f"Voice track not found: {spec.voice_path}")
    if spec.ffmpeg_bin is None or not spec.ffmpeg_bin.exists():
        raise DependencyMissingError(
            "ffmpeg binary not configured. Drop ffmpeg.exe into cache/."
        )
    if spec.ambient_path is None:
        # No ambient: just convert the voice to a stereo WAV at the right length.
        return _convert_voice_only(spec)

    spec.output_path.parent.mkdir(parents=True, exist_ok=True)

    # Filter graph:
    #   1. Pad the voice to target_duration so silent paragraph pauses survive.
    #   2. Loop the bed to match the voice duration.
    #   3. Apply sidechain ducking on the bed whenever the voice is active.
    # Link labels are intentionally spelled out ("voice", "bed") because
    # single-letter labels such as ``[v]`` or ``[b]`` collide with
    # ffmpeg's stream-specifier parsing and get rejected with
    # "Stream specifier 'v' in filtergraph description matches no streams"
    # on real-world long renders (the smoke test did not catch this
    # because it used a sub-second target).
    filter_complex = (
        f"[0:a]volume={spec.voice_volume},aresample=48000,asetpts=PTS-STARTPTS,"
        f"apad=whole_dur={spec.target_duration:.3f},"
        f"atrim=0:{spec.target_duration:.3f}[voice];"
        f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{spec.target_duration:.3f},"
        f"volume={spec.ambient_volume},aresample=48000[bed];"
        f"[bed][voice]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=1500:"
        f"makeup=1[ducked];"
        f"[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0,"
        f"alimiter=limit=0.95,aresample=48000[aout]"
    )

    cmd = [
        str(spec.ffmpeg_bin),
        "-y",
        "-i",
        str(spec.voice_path),
        "-stream_loop",
        "-1",
        "-i",
        str(spec.ambient_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[aout]",
        "-t",
        f"{spec.target_duration:.3f}",
        "-c:a",
        "pcm_s16le",
        "-ac",
        "2",
        "-ar",
        "48000",
        str(spec.output_path),
    ]
    log.debug("ffmpeg mix command: {}", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Skip the noisy version banner; show only the meaningful tail.
        tail = "\n".join(
            line for line in result.stderr.splitlines() if "configuration" not in line
        )[-2000:]
        log.error("ffmpeg mix failed: {}", tail)
        raise SleeplensError("Failed to mix voice and ambient bed.")
    return spec.output_path


def _convert_voice_only(spec: MixSpec) -> Path:
    spec.output_path.parent.mkdir(parents=True, exist_ok=True)
    # Use apad + atrim to actually pad with silence, not just stop early.
    filter_complex = (
        f"[0:a]aresample=48000,apad=whole_dur={spec.target_duration:.3f},"
        f"atrim=0:{spec.target_duration:.3f},asetpts=PTS-STARTPTS[aout]"
    )
    cmd = [
        str(spec.ffmpeg_bin),
        "-y",
        "-i",
        str(spec.voice_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[aout]",
        "-c:a",
        "pcm_s16le",
        "-ac",
        "2",
        "-ar",
        "48000",
        str(spec.output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("ffmpeg voice convert failed: {}", result.stderr[-2000:])
        raise SleeplensError("Failed to convert voice track.")
    return spec.output_path


def read_wav_duration(path: Path) -> float:
    """Return the duration of a WAV file via the wave module."""
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate() or 1
        return frames / float(rate)


def probe_duration(path: Path, ffmpeg_bin: Path | None) -> float:
    """Return the duration of an arbitrary audio file via ffprobe."""
    if ffmpeg_bin is None or not ffmpeg_bin.exists():
        if path.suffix.lower() == ".wav":
            return read_wav_duration(path)
        raise DependencyMissingError("ffmpeg/ffprobe not available for probe.")
    ffprobe = ffmpeg_bin.with_name("ffprobe.exe" if ffmpeg_bin.name.endswith(".exe") else "ffprobe")
    if not ffprobe.exists():
        ffprobe = ffmpeg_bin
    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip() or "0")
    except ValueError:
        return 0.0


# Re-export for convenience.
__all__ = [
    "AmbientTrack",
    "AmbientMode",
    "MixSpec",
    "extract_script_keywords",
    "mix_bed_and_voice",
    "pick_ambient",
    "probe_duration",
    "scan_ambient_library",
]


# Avoid unused-import lint on shutil (kept for future copy operations).
_ = shutil
