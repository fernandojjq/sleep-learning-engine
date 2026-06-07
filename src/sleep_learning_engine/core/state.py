"""State machine shared by the GUI and the CLI runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RenderStage(StrEnum):
    SCRIPT = "script"
    VOICE = "voice"
    TIMING = "timing"
    AMBIENT = "ambient"
    MIX = "mix"
    VISUAL = "visual"
    ENCODE = "encode"
    DONE = "done"


class RenderStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RenderEvent:
    """A progress event surfaced to the UI."""

    stage: RenderStage
    status: RenderStatus
    message: str
    fields: dict = field(default_factory=dict)
    percent: float | None = None
