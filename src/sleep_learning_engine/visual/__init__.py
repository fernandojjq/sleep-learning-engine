"""Visual subsystem exports."""

from .assets import (
    IMAGE_SUFFIXES,
    VIDEO_SUFFIXES,
    VisualSource,
    generate_fallback,
    resolve_visual,
)

__all__ = [
    "IMAGE_SUFFIXES",
    "VIDEO_SUFFIXES",
    "VisualSource",
    "generate_fallback",
    "resolve_visual",
]
