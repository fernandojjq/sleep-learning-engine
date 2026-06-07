"""Logging helpers - loguru sink that lives under the project log dir."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:  # pragma: no cover
    from ..config.paths import ProjectPaths


def configure_logging(paths: "ProjectPaths", level: str = "INFO") -> None:
    """Configure the global loguru logger.

    Logs are written to ``<project>/logs/sleep_learning_engine.log`` and mirrored to the
    console. Old logs are rotated at 5 MB with a 5-file retention.
    """
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = paths.log_dir / "sleep_learning_engine.log"

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{module}</cyan>:<cyan>{function}</cyan> - "
            "<level>{message}</level>"
        ),
        enqueue=True,
    )
    logger.add(
        log_file,
        level=level,
        rotation="5 MB",
        retention=5,
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{module}:{function}:{line} - {message}"
        ),
    )


def get_logger():
    """Return the shared logger."""
    return logger
