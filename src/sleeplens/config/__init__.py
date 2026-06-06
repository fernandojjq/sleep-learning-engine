"""Runtime configuration, paths and constants."""

from .paths import ProjectPaths, resolve_paths
from .settings import (
    PROVIDER_PRESETS,
    AIProvider,
    AmbientMode,
    AppSettings,
    OutputPreset,
    ProviderPreset,
    TTSBackend,
    load_settings,
    save_settings,
)

__all__ = [
    "AIProvider",
    "AmbientMode",
    "AppSettings",
    "OutputPreset",
    "PROVIDER_PRESETS",
    "ProjectPaths",
    "ProviderPreset",
    "TTSBackend",
    "load_settings",
    "resolve_paths",
    "save_settings",
]
