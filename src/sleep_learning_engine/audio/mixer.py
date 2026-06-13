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
    # Default 60s covers the procedural generator's output. The
    # playlist builder uses this to size cycles without re-probing.
    duration_seconds: float = 60.0

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
    mode: object,
    script_keywords: Iterable[str] = (),
) -> AmbientTrack | None:
    """Select a single track for the bed, honouring the chosen mode.

    Kept for backwards compatibility with callers that still want a
    single-track pick. New code should use :func:`build_ambient_playlist`
    to get the full random-without-repetition playlist.
    """
    tracks_list = list(tracks)
    if not tracks_list:
        return None
    if mode == "random":
        import random
        if not list(script_keywords):
            return random.choice(tracks_list)
        script_set = {kw.lower() for kw in script_keywords}
        candidates = [t for t in tracks_list if t.keywords and (set(t.keywords) & script_set)]
        pool = candidates or tracks_list
        return random.choice(pool)
    if mode == "auto":
        # Score by keyword overlap with the script. Fall back to the first
        # track if no keyword matches.
        script_set = {kw.lower() for kw in script_keywords}
        def score(track: AmbientTrack) -> int:
            if not script_set:
                return 1 if track.keywords else 0
            return sum(1 for kw in track.keywords if kw in script_set)
        matches = sorted(tracks_list, key=score, reverse=True)
        # All tracks with the top score are equally valid; pick one at
        # random so successive renders do not always land on the same
        # track. Use the keyword set as the seed so the choice is
        # deterministic per script (good for reproducibility).
        top = matches[0]
        top_score = score(top)
        tied = [t for t in matches if score(t) == top_score]
        if len(tied) == 1:
            return tied[0]
        import random
        rng = random.Random(tuple(sorted(script_set)))
        return rng.choice(tied)
    if mode == "keyword":
        # Strict keyword match: pick the highest-scoring track. If
        # nothing matches at all, return None (the caller falls back
        # to voice-only rather than picking an unrelated track).
        script_set = {kw.lower() for kw in script_keywords}
        candidates = [
            t for t in tracks_list
            if t.keywords and (set(t.keywords) & script_set)
        ]
        if not candidates:
            return None
        def score(track: AmbientTrack) -> int:
            return sum(1 for kw in track.keywords if kw in script_set)
        candidates.sort(key=score, reverse=True)
        top_score = score(candidates[0])
        tied = [t for t in candidates if score(t) == top_score]
        if len(tied) == 1:
            return tied[0]
        import random
        rng = random.Random(tuple(sorted(script_set)))
        return rng.choice(tied)
    return None


def build_ambient_playlist(
    tracks: Iterable[AmbientTrack],
    total_seconds: float,
    *,
    script_keywords: Iterable[str] = (),
    seed: int | None = None,
) -> list[Path]:
    """Build a shuffled ambient playlist that covers ``total_seconds``.

    Selection rules:
    1. Tracks whose keywords overlap with the script form the primary
       pool. If no track matches, the entire library is the pool.
    2. The pool is shuffled with a deterministic seed (per-script by
       default, so re-renders stay reproducible).
    3. The shuffled list is repeated end-to-end until the cumulative
       duration is at least ``total_seconds``. Each track plays once
       per cycle; only when the voice is longer than one full cycle
       does the playlist loop.

    This means a 6-hour video with 14 tracks plays each track ~25 times
    spread evenly across the runtime, not back-to-back. A 5-minute
    video with 14 tracks plays roughly the first 5 tracks of one
    shuffled cycle, never the same track twice.
    """
    import random as _random

    tracks_list = list(tracks)
    if not tracks_list or total_seconds <= 0:
        return []

    script_set = {kw.lower() for kw in script_keywords}
    candidates = [
        t for t in tracks_list
        if script_set and t.keywords and (set(t.keywords) & script_set)
    ]
    pool = candidates or tracks_list
    if not pool:
        return []

    rng = _random.Random(seed) if seed is not None else _random.Random()
    rng.shuffle(pool)

    # Repeat the shuffled pool until we cover total_seconds. We
    # measure duration by reading ffprobe lazily; the first probe per
    # track is cached so a long playlist only reads each file once.
    durations: dict[Path, float] = {}
    for t in pool:
        if t.path in durations:
            continue
        try:
            d = probe_duration(t.path, None)
            if d <= 0.0:
                d = t.duration_seconds
            durations[t.path] = d
        except Exception:
            durations[t.path] = t.duration_seconds

    playlist: list[Path] = []
    accumulated = 0.0
    # Cap the cycle count to avoid pathological cases (e.g. a 1-second
    # track and a 1000-hour target). 10,000 cycles is a sane upper
    # bound that still produces a manageable concat file.
    max_cycles = 10_000
    cycle = 0
    while accumulated < total_seconds and cycle < max_cycles:
        for t in pool:
            playlist.append(t.path)
            accumulated += durations[t.path]
            if accumulated >= total_seconds:
                break
        cycle += 1
    return playlist
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
    """Inputs to the audio mixer.

    ``ambient_paths`` is a list (not a single path) so the bed can be
    a shuffled playlist. A single-element list is the simple "loop
    this one track" case; a multi-element list is the random-no-repeat
    playlist. Pass ``None`` or an empty list to render voice-only.
    """

    voice_path: Path
    ambient_paths: list[Path] | None
    target_duration: float
    output_path: Path
    voice_volume: float = 1.0
    ambient_volume: float = 0.18
    ambient_duck_db: float = 12.0
    ffmpeg_bin: Path | None = None

    @property
    def has_ambient(self) -> bool:
        return bool(self.ambient_paths)


def _write_concat_playlist(paths: list[Path], target: Path) -> None:
    """Write an ffmpeg concat demuxer playlist file.

    The format is one ``file '...'`` line per entry. The file is
    written to ``target`` (a sibling of the output WAV) so the
    mixer can pass it to ffmpeg with ``-f concat -safe 0 -i``.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for p in paths:
            # ffmpeg's concat demuxer requires forward slashes and
            # single-quoted paths. Windows backslashes confuse it.
            normalised = str(p.resolve()).replace("\\", "/")
            fh.write(f"file '{normalised}'\n")


def mix_bed_and_voice(spec: MixSpec) -> Path:
    """Produce a single stereo track that plays the voice over the ambient bed.

    The bed is sourced from ``spec.ambient_paths`` (one or many files).
    A single-element list loops that one track. A multi-element list
    is treated as a shuffled playlist that plays end-to-end before
    looping, so each track is heard once per cycle. The bed is
    filtered to a comfortable level and ducked whenever the voice is
    active. The voice track is explicitly padded to ``target_duration``
    so the silent pauses between paragraphs become real silence
    gaps in the output. The result is a stereo 48 kHz WAV ready to
    feed the video encoder.
    """
    if not spec.voice_path.exists():
        raise AssetNotFoundError(f"Voice track not found: {spec.voice_path}")
    if spec.ffmpeg_bin is None or not spec.ffmpeg_bin.exists():
        raise DependencyMissingError(
            "ffmpeg binary not configured. Drop ffmpeg.exe into cache/."
        )
    if not spec.has_ambient:
        # No ambient: just convert the voice to a stereo WAV at the right length.
        return _convert_voice_only(spec)

    spec.output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build the bed input. The single-track case is the legacy fast
    # path (no concat demuxer, no temp file). The multi-track case
    # writes a playlist file and uses ffmpeg's concat demuxer with
    # -stream_loop -1 so the whole playlist repeats end-to-end.
    if len(spec.ambient_paths or []) == 1:
        ambient_input: list[str] = [
            "-stream_loop", "-1",
            "-i", str(spec.ambient_paths[0]),
        ]
        bed_label_in = "[1:a]"
    else:
        playlist_path = spec.output_path.with_suffix(".ambient.txt")
        _write_concat_playlist(list(spec.ambient_paths), playlist_path)
        ambient_input = [
            "-f", "concat", "-safe", "0",
            "-i", str(playlist_path),
        ]
        bed_label_in = "[1:a]"

    # Filter graph:
    #   1. Trim the voice to target_duration (no padding - we don't
    #      want to insert any code-side silence; any inter-paragraph
    #      gaps come from the TTS stitch's natural silences only).
    #   2. Trim the (already looped) bed to match the voice duration.
    #   3. Apply ambient_duck_db as a CONSTANT offset to the bed
    #      before mixing. Earlier versions used sidechaincompress
    #      with hardcoded ratio/threshold/release, so changing the
    #      setting in the CONFIG dict had no effect. The new approach
    #      does the attenuation statically: the bed is multiplied by
    #      10**(-duck_db/20) regardless of whether the voice is
    #      active. This means:
    #        - No 'pumping' when the voice starts and stops (the
    #          music is at a constant level, not ducking back and
    #          forth).
    #        - ambient_duck_db actually does what the name promises:
    #          a setting of 6.0 gives 6 dB of attenuation, 12.0
    #          gives 12 dB, 0.0 leaves the bed at ambient_volume.
    #      The voice is naturally loud enough (voice_volume=1.0
    #      by default) to dominate the mix even without dynamic
    #      ducking, which is the right behaviour for sleep content
    #      (the listener is barely conscious and any sudden changes
    #      in the bed are more distracting than a constant low bed).
    duck_db = max(0.0, float(spec.ambient_duck_db))
    # Round to 4 decimals so the filter graph string is deterministic.
    duck_attenuation = round(10 ** (-duck_db / 20), 4)
    filter_complex = (
        f"[0:a]volume={spec.voice_volume},aresample=48000,asetpts=PTS-STARTPTS,"
        f"atrim=0:{spec.target_duration:.3f}[voice];"
        f"{bed_label_in}atrim=0:{spec.target_duration:.3f},"
        f"volume={spec.ambient_volume},aresample=48000[bed];"
        f"[bed]volume={duck_attenuation}[bed_attenuated];"
        f"[voice][bed_attenuated]amix=inputs=2:duration=first:dropout_transition=0,"
        f"alimiter=limit=0.95,aresample=48000[aout]"
    )

    cmd = [
        str(spec.ffmpeg_bin),
        "-y",
        "-i",
        str(spec.voice_path),
        *ambient_input,
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
    # No apad: any code-inserted silence is undesirable for sleep
    # content. If the voice is shorter than target_duration the mix
    # just ends with a beat of ambient-only (the bed continues to
    # play) and then the encode finishes; if it's longer, the
    # atrim cuts the tail. Both are bounded by <100 ms in practice
    # because the TTS stitch now preserves exact per-segment
    # durations (re-encode with first_pts=0, no encoder pre-roll).
    filter_complex = (
        f"[0:a]aresample=48000,atrim=0:{spec.target_duration:.3f},"
        f"asetpts=PTS-STARTPTS[aout]"
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
