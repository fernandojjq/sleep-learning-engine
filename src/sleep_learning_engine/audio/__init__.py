"""Audio subsystem exports."""

from .mixer import (
    AmbientMode,
    AmbientTrack,
    MixSpec,
    extract_script_keywords,
    mix_bed_and_voice,
    pick_ambient,
    probe_duration,
    scan_ambient_library,
)
from .tts import TTSEngine, TTSResult, TTSSegment

__all__ = [
    "AmbientMode",
    "AmbientTrack",
    "MixSpec",
    "TTSEngine",
    "TTSResult",
    "TTSSegment",
    "extract_script_keywords",
    "mix_bed_and_voice",
    "pick_ambient",
    "probe_duration",
    "scan_ambient_library",
]
