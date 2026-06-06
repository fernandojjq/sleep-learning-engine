"""Filesystem layout for the studio.

All paths resolve relative to the project root so the studio can sit anywhere
on disk. On a fresh checkout the directory tree is created on demand.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


def _project_root() -> Path:
    """Locate the project root.

    Resolution order:
    1. ``$SLEEPLENS_HOME`` environment variable.
    2. Walk up from this file until we find ``pyproject.toml``.
    """

    env = os.environ.get("SLEEPLENS_HOME")
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: two levels up from src/sleeplens/config/paths.py
    return here.parents[2]


@dataclass(frozen=True)
class ProjectPaths:
    """Strongly typed paths used by every subsystem."""

    root: Path
    src: Path
    assets_dir: Path
    ambient_dir: Path
    visuals_dir: Path
    output_dir: Path
    cache_dir: Path
    ffmpeg_bin: Path
    ffprobe_bin: Path
    log_dir: Path
    config_file: Path

    def ensure(self) -> None:
        """Create every directory that does not exist yet."""
        for path in (
            self.assets_dir,
            self.ambient_dir,
            self.visuals_dir,
            self.output_dir,
            self.cache_dir,
            self.log_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def unique_output(self, stem: str) -> Path:
        """Return a non-clobbering path inside ``output_dir``."""
        target = self.output_dir / f"{stem}.mp4"
        counter = 1
        while target.exists():
            target = self.output_dir / f"{stem}-{counter}.mp4"
            counter += 1
        return target


def resolve_paths(
    project_root: Path | None = None,
    ffmpeg_override: Path | None = None,
) -> ProjectPaths:
    """Build a ``ProjectPaths`` value, honouring the bundled ffmpeg fallback."""
    root = (project_root or _project_root()).resolve()
    src = root / "src"
    assets_dir = root / "assets"
    cache_dir = root / "cache"

    # 1. Caller-provided override wins.
    # 2. Bundled binary at ``cache/ffmpeg.exe`` (Windows) or ``cache/ffmpeg`` (POSIX).
    # 3. ``$FFMPEG_BIN`` env var.
    # 4. PATH lookup.
    candidates: list[Path] = []
    if ffmpeg_override is not None:
        candidates.append(ffmpeg_override)
    bundled = cache_dir / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
    if bundled.exists():
        candidates.append(bundled)
    env_bin = os.environ.get("FFMPEG_BIN")
    if env_bin:
        candidates.append(Path(env_bin).expanduser())
    on_path = shutil.which("ffmpeg")
    if on_path:
        candidates.append(Path(on_path))

    ffmpeg_bin = candidates[0] if candidates else bundled
    probe_candidate = ffmpeg_bin.with_name("ffprobe.exe" if sys.platform.startswith("win") else "ffprobe")
    if not probe_candidate.exists():
        env_probe = os.environ.get("FFPROBE_BIN")
        if env_probe:
            probe_candidate = Path(env_probe).expanduser()
        else:
            found = shutil.which("ffprobe")
            if found:
                probe_candidate = Path(found)
    ffprobe_bin = probe_candidate

    return ProjectPaths(
        root=root,
        src=src,
        assets_dir=assets_dir,
        ambient_dir=assets_dir / "ambient",
        visuals_dir=assets_dir / "visuals",
        output_dir=root / "output",
        cache_dir=cache_dir,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
        log_dir=root / "logs",
        config_file=root / ".sleeplens.toml",
    )
