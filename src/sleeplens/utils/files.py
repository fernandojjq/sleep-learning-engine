"""Filesystem utilities used across the studio."""

from __future__ import annotations

import re
from pathlib import Path

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(stem: str, max_length: int = 64) -> str:
    """Normalize a string for use as a filename stem."""
    cleaned = _FILENAME_SAFE.sub("-", stem.strip())
    cleaned = cleaned.strip("-_.")
    if not cleaned:
        cleaned = "sleeplens-output"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip("-_.")
    return cleaned


def file_size_mb(path: Path) -> float:
    """Return the size of a file in megabytes, or 0.0 if missing."""
    try:
        return path.stat().st_size / (1024 * 1024)
    except FileNotFoundError:
        return 0.0
