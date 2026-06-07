"""Tests for the random-without-repetition ambient playlist builder.

The user reported that the old single-track pick was boring: a 6-hour
video would play the same 60-second loop ~360 times. This suite
pins the behaviour of :func:`build_ambient_playlist` so future
refactors do not regress it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sleeplens.audio.mixer import (  # noqa: E402
    AmbientTrack,
    build_ambient_playlist,
)


def _track(name: str, *keywords: str, duration: float = 60.0) -> AmbientTrack:
    """Build a fake AmbientTrack without touching the filesystem.

    The path does not need to exist for the playlist builder tests
    because the builder only reads the dataclass fields. The real
    duration probe happens in the mixer when a render runs.
    """
    return AmbientTrack(
        path=Path(f"/fake/{name}.ogg"),
        keywords=keywords,
        title=name,
    )


def test_playlist_covers_total_seconds_with_no_repeat_within_cycle() -> None:
    tracks = [_track(f"rain_{i}", "rain", "storm", duration=60.0) for i in range(5)]
    playlist = build_ambient_playlist(tracks, total_seconds=120.0, seed=42)
    # Two entries of 60s each cover 120s, no track should appear twice
    # in a single cycle (5 unique tracks are available so we just
    # take the first two of the shuffled list).
    assert len(playlist) == 2
    assert len(set(playlist)) == 2
    # No track repeats before the pool is exhausted.
    assert playlist[0] != playlist[1]


def test_playlist_repeats_full_cycle_only_when_voice_exceeds_one_cycle() -> None:
    tracks = [_track(f"rain_{i}", "rain", "storm", duration=60.0) for i in range(3)]
    # 3 tracks * 60s = 180s per cycle. 360s target = 2 full cycles.
    playlist = build_ambient_playlist(tracks, total_seconds=360.0, seed=42)
    assert len(playlist) == 6
    # Each track must appear exactly twice (once per cycle).
    from collections import Counter
    counts = Counter(playlist)
    assert all(v == 2 for v in counts.values()), counts
    # Within a cycle, no two adjacent entries should be the same track.
    for i in range(0, len(playlist), 3):
        cycle = playlist[i : i + 3]
        assert len(set(cycle)) == 3, f"Cycle {i // 3} has repeats: {cycle}"


def test_playlist_is_deterministic_for_a_given_seed() -> None:
    tracks = [_track(f"rain_{i}", "rain", "storm", duration=60.0) for i in range(4)]
    a = build_ambient_playlist(tracks, total_seconds=240.0, seed=1234)
    b = build_ambient_playlist(tracks, total_seconds=240.0, seed=1234)
    assert a == b


def test_playlist_shuffles_differently_for_different_seeds() -> None:
    tracks = [_track(f"rain_{i}", "rain", "storm", duration=60.0) for i in range(4)]
    a = build_ambient_playlist(tracks, total_seconds=240.0, seed=1)
    b = build_ambient_playlist(tracks, total_seconds=240.0, seed=999)
    # Same track set, but the order of first appearances should differ
    # with overwhelming probability (4! = 24 permutations, only 1
    # collision; we tolerate 0.05 false-fail rate by checking first 3).
    assert a[:3] != b[:3]


def test_playlist_filters_by_script_keywords_when_any_match() -> None:
    rain_tracks = [_track(f"rain_{i}", "rain") for i in range(3)]
    ocean_tracks = [_track(f"ocean_{i}", "ocean") for i in range(3)]
    fire_tracks = [_track(f"fire_{i}", "fire") for i in range(2)]
    library = rain_tracks + ocean_tracks + fire_tracks
    # Script is about rain. The pool should narrow to the 3 rain
    # tracks; the other 5 should not appear.
    playlist = build_ambient_playlist(
        library, total_seconds=300.0,
        script_keywords=["rain"], seed=42,
    )
    rain_paths = {t.path for t in rain_tracks}
    assert all(p in rain_paths for p in playlist), (
        "Non-rain track leaked into the rain-keyword playlist"
    )


def test_playlist_falls_back_to_full_library_when_no_keyword_match() -> None:
    library = [
        _track("rain", "rain"),
        _track("ocean", "ocean"),
        _track("fire", "fire"),
    ]
    # Script with no matching keyword: full library is the pool.
    playlist = build_ambient_playlist(
        library, total_seconds=180.0,
        script_keywords=["quantum", "physics"], seed=42,
    )
    assert set(playlist) == {t.path for t in library}


def test_playlist_returns_empty_for_empty_library() -> None:
    assert build_ambient_playlist([], total_seconds=300.0) == []


def test_playlist_returns_empty_for_zero_duration() -> None:
    tracks = [_track("rain", "rain")]
    assert build_ambient_playlist(tracks, total_seconds=0.0) == []


@pytest.mark.parametrize("track_count,total_seconds,expected_entries", [
    (1, 60.0, 1),    # 1 track, 1 entry
    (1, 120.0, 2),   # 1 track loops (no choice, same path twice)
    (3, 60.0, 1),    # 3 tracks, first 60s track covers it
    (3, 180.0, 3),   # 3 tracks, full cycle
    (3, 360.0, 6),   # 3 tracks, 2 full cycles
    (14, 3600.0, 60),  # 14 tracks * 60s = 840s/cycle, 3600s = 4.3 cycles
])
def test_playlist_entry_count_matches_cycles(track_count, total_seconds, expected_entries) -> None:
    # The entry count is the number of tracks needed to cover
    # total_seconds without re-using any track within a cycle. With
    # 60s tracks and N tracks per cycle, one cycle covers N*60s.
    # We need at least ceil(total / (N*60)) cycles worth.
    tracks = [
        _track(f"t{i}", "ambient", duration=60.0)
        for i in range(track_count)
    ]
    playlist = build_ambient_playlist(tracks, total_seconds=total_seconds, seed=42)
    assert len(playlist) == expected_entries, (
        f"track_count={track_count} total={total_seconds}: "
        f"expected {expected_entries} entries, got {len(playlist)}"
    )
