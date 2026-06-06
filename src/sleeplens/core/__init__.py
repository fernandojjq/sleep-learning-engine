"""Core orchestration primitives (exceptions + retry + state)."""

from .exceptions import (
    AssetNotFoundError,
    ConfigError,
    DependencyMissingError,
    ProviderError,
    RenderError,
    SleeplensError,
)
from .retry import call_with_backoff
from .state import RenderEvent, RenderStage, RenderStatus

__all__ = [
    "AssetNotFoundError",
    "ConfigError",
    "DependencyMissingError",
    "ProviderError",
    "RenderError",
    "RenderEvent",
    "RenderStage",
    "RenderStatus",
    "SleeplensError",
    "call_with_backoff",
]


def __getattr__(name: str):  # pragma: no cover - lazy loader
    """Lazily expose the pipeline helpers to avoid circular imports."""
    if name in {"run_render", "build_connector", "RenderResult", "PROVIDER_PRESETS"}:
        from . import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
