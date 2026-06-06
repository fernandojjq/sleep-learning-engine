"""Compute the final video duration from audio segments and pauses."""

from __future__ import annotations

from dataclasses import dataclass

from ..audio.tts import TTSSegment


@dataclass(frozen=True)
class TimingPlan:
    """The mathematical breakdown of the final video runtime."""

    voice_seconds: float
    pause_seconds: float
    total_seconds: float
    pause_count: int
    fps: int
    frame_count: int

    @property
    def human_runtime(self) -> str:
        seconds = int(self.total_seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m:02d}m {s:02d}s"
        return f"{m}m {s:02d}s"


def compute_timing(
    *,
    segments: list[TTSSegment],
    pause_seconds: float,
    fps: int = 24,
) -> TimingPlan:
    """Sum narration + per-paragraph pauses to produce the final runtime.

    ``pause_seconds`` is inserted between every two adjacent segments. If there
    is only one segment, no trailing pause is added.
    """
    if pause_seconds < 0:
        raise ValueError("pause_seconds must be non-negative.")
    if fps <= 0:
        raise ValueError("fps must be positive.")
    voice_seconds = sum(max(0.0, seg.duration) for seg in segments)
    if voice_seconds <= 0:
        raise ValueError("Voice track is empty; cannot compute a runtime.")
    pause_count = max(0, len(segments) - 1)
    pause_total = pause_count * pause_seconds
    total = voice_seconds + pause_total
    frame_count = int(round(total * fps))
    return TimingPlan(
        voice_seconds=voice_seconds,
        pause_seconds=pause_total,
        total_seconds=total,
        pause_count=pause_count,
        fps=fps,
        frame_count=frame_count,
    )


__all__ = ["TimingPlan", "compute_timing"]
