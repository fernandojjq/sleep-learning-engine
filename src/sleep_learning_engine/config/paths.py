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


def _resolve_ambient_dir(assets_dir: Path) -> Path:
    """Pick the ambient library directory.

    The user is the source of all ambient music in this project - we
    do not bundle any tracks. Resolution order:

    1. ``<project_root>/assets/ambient/`` if it has at least one
       ``.mp3`` inside. This is the user's working library - a fresh
       upload, a curated set, anything the user has put there.
    2. The empty ``<project_root>/assets/ambient/`` (the historical
       path). The mixer will find zero files and the render will
       ship silent ambient; the user gets a clear log line instead
       of a crash. The user is expected to bring their own tracks.

    The bundled-package fallback was removed in v1.0.9: each user
    is responsible for the licensing of their own ambient music.
    Recommended generators: Minimax Music 2.6, Udio, Suno, Stable
    Audio, or any other source. The pipeline does not care where
    the music came from - it just needs ``.mp3`` files in a folder.
    """
    user_dir = assets_dir / "ambient"
    if user_dir.is_dir() and any(user_dir.glob("*.mp3")):
        return user_dir
    return user_dir


def _project_root() -> Path:
    """Locate the project root.

    Resolution order:
    1. ``$SLEEP_LEARNING_ENGINE_HOME`` environment variable (new name).
    2. ``$SLEEPLENS_HOME`` (legacy, kept for back-compat with old checkouts).
    3. Walk up from this file until we find ``pyproject.toml``.

    The env var is what makes the cloud notebooks work: the package
    is pip-installed, so the auto-detect lands in
    ``/usr/local/lib/python3.12/dist-packages/.../`` (where the
    bundled ``assets/ambient/`` is empty and the output dir is not
    writable). The notebook exports ``SLEEP_LEARNING_ENGINE_HOME``
    to a writable work directory, so the resolved root is
    ``/content/working`` and every subsequent path (ambient,
    output, cache, logs) lands there.
    """

    env = os.environ.get("SLEEP_LEARNING_ENGINE_HOME") or os.environ.get("SLEEPLENS_HOME")
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            print(
                f"[sleep_learning_engine] Project root from env: {p}",
                file=sys.stderr,
            )
            return p
        print(
            f"[sleep_learning_engine] WARNING: $SLEEP_LEARNING_ENGINE_HOME={env} "
            f"does not exist; falling back to auto-detect.",
            file=sys.stderr,
        )

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: two levels up from src/sleep_learning_engine/config/paths.py
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

    # Config file: new name is preferred, legacy ``.sleeplens.toml`` is
    # accepted as a fallback so users on existing checkouts do not
    # have to rename the file by hand.
    config_file = root / ".sleep_learning_engine.toml"
    if not config_file.exists() and (root / ".sleeplens.toml").exists():
        config_file = root / ".sleeplens.toml"

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
        # Ambient library: ONLY the project-root assets/ambient/ is
        # consulted. The user brings their own .mp3 files; the package
        # ships with zero bundled ambient. See _resolve_ambient_dir.
        ambient_dir=_resolve_ambient_dir(assets_dir),
        visuals_dir=assets_dir / "visuals",
        output_dir=root / "output",
        cache_dir=cache_dir,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_bin=ffprobe_bin,
        log_dir=root / "logs",
        # Honour the fallback resolved above: new name
        # ``.sleep_learning_engine.toml`` is preferred, legacy
        # ``.sleeplens.toml`` is accepted if the new one is missing.
        # The previous version hardcoded the new name here, so the
        # fallback was computed but discarded - any project root that
        # only had the legacy toml (every cloud notebook CONFIG cell)
        # silently fell through to package defaults.
        config_file=config_file,
    )
