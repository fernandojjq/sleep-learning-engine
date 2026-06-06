"""Studio-wide exceptions."""

from __future__ import annotations


class SleeplensError(Exception):
    """Base class for every error raised inside the studio."""


class ConfigError(SleeplensError):
    """User input or configuration is invalid."""


class AssetNotFoundError(SleeplensError):
    """A required asset (image, video, audio) is missing."""


class ProviderError(SleeplensError):
    """An upstream AI provider returned an error or rate limited the request."""


class RenderError(SleeplensError):
    """FFmpeg failed to produce a valid output."""


class DependencyMissingError(SleeplensError):
    """A required binary (ffmpeg, ffprobe) is not available."""
